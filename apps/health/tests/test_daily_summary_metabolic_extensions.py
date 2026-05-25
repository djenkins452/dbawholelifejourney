"""
DailyHealthSummary metabolic extensions (Phase 1A · C7) — regression
coverage.

Asserts:

1. The six new fields exist on DailyHealthSummary with the expected
   defaults (nullable Decimals → None; PositiveSmallInteger → 0;
   JSONField → {}). Migration 0089 is the source of truth; tests
   pin the in-Python defaults so a future schema drift fails loudly.

2. DailyHealthSummaryBuilder._collect_glucose populates the new
   glucose_readings_count and overnight_avg_glucose fields without
   regressing existing glucose_avg / glucose_min / glucose_max /
   glucose_variability / time_in_range_pct outputs.

3. DailyHealthSummaryBuilder._collect_insulin populates
   insulin_total_units / insulin_basal_units / insulin_bolus_units
   from C3 insulin IntakeLogs, and returns None when no insulin is
   logged.

4. build_for_date wires _collect_insulin into the pipeline and
   includes 'insulin' in the signals_present list when data exists.

5. meal_response_distribution defaults to {} on every new row; C8
   will populate it.

Uses the C3 signal-mute mixin pattern (test-class scoped) because
creating IntakeLogs would otherwise hit the Redis-retry storm.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models.signals import post_delete, post_save
from django.test import TestCase

from apps.ai.signals import (
    invalidate_cache_on_medicine_log_delete,
    invalidate_cache_on_medicine_log_save,
    refresh_sae_on_medicine_change,
    refresh_sae_on_medicine_schedule_change,
)
from apps.health.models import (
    DailyHealthSummary,
    GlucoseEntry,
    Intake,
    IntakeLog,
)
from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
from apps.users.models import TermsAcceptance

User = get_user_model()


class _MuteIntakeSignals:
    _MUTED = (
        (post_save, "health.IntakeLog", invalidate_cache_on_medicine_log_save),
        (post_delete, "health.IntakeLog", invalidate_cache_on_medicine_log_delete),
        (post_save, "health.Intake", refresh_sae_on_medicine_change),
        (post_delete, "health.Intake", refresh_sae_on_medicine_change),
        (post_save, "health.IntakeSchedule", refresh_sae_on_medicine_schedule_change),
        (post_delete, "health.IntakeSchedule", refresh_sae_on_medicine_schedule_change),
    )

    @classmethod
    def setUpClass(cls):
        for signal, sender, handler in cls._MUTED:
            signal.disconnect(handler, sender=sender)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        for signal, sender, handler in cls._MUTED:
            signal.connect(handler, sender=sender)


def _make_user(email: str = "c7@test.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ── Model surface ───────────────────────────────────────────────────


class DailyHealthSummaryNewFieldsTests(TestCase):
    """The six new C7 fields exist with expected defaults."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("daily_fields@test.com")

    def test_overnight_avg_glucose_defaults_to_none(self):
        summary = DailyHealthSummary.objects.create(
            user=self.user, summary_date=date.today(),
        )
        self.assertIsNone(summary.overnight_avg_glucose)

    def test_glucose_readings_count_defaults_to_zero(self):
        summary = DailyHealthSummary.objects.create(
            user=self.user, summary_date=date.today(),
        )
        self.assertEqual(summary.glucose_readings_count, 0)

    def test_meal_response_distribution_defaults_to_empty_dict(self):
        summary = DailyHealthSummary.objects.create(
            user=self.user, summary_date=date.today(),
        )
        self.assertEqual(summary.meal_response_distribution, {})

    def test_insulin_fields_default_to_none(self):
        summary = DailyHealthSummary.objects.create(
            user=self.user, summary_date=date.today(),
        )
        self.assertIsNone(summary.insulin_total_units)
        self.assertIsNone(summary.insulin_basal_units)
        self.assertIsNone(summary.insulin_bolus_units)


# ── Glucose collector extension ─────────────────────────────────────


class CollectGlucoseExtensionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("collect_glucose@test.com")
        cls.builder = DailyHealthSummaryBuilder()
        cls.target = date(2026, 5, 20)

    def _make_reading(self, hour: int, value: int):
        # Date stored in UTC to match recorded_at__date filter behavior.
        return GlucoseEntry.objects.create(
            user=self.user,
            value=Decimal(value),
            unit="mg/dL",
            recorded_at=datetime.combine(
                self.target, time(hour, 0), tzinfo=timezone.utc,
            ),
        )

    def test_glucose_readings_count_populated(self):
        for h, v in ((3, 100), (8, 130), (14, 145), (20, 120)):
            self._make_reading(h, v)
        result = self.builder._collect_glucose(self.user, self.target)
        self.assertEqual(result["glucose_readings_count"], 4)

    def test_overnight_avg_uses_midnight_to_6am_window(self):
        # Two overnight readings (hour 1 and 4) at 110 and 130 → avg 120.
        # Three daytime readings (8, 12, 18) that should be excluded.
        for h, v in ((1, 110), (4, 130), (8, 90), (12, 95), (18, 100)):
            self._make_reading(h, v)
        result = self.builder._collect_glucose(self.user, self.target)
        self.assertEqual(result["overnight_avg_glucose"], Decimal("120.00"))

    def test_no_overnight_readings_omits_overnight_avg(self):
        # All readings during the day → overnight_avg_glucose absent.
        for h, v in ((8, 100), (12, 110), (18, 120)):
            self._make_reading(h, v)
        result = self.builder._collect_glucose(self.user, self.target)
        self.assertNotIn("overnight_avg_glucose", result)

    def test_existing_glucose_outputs_preserved(self):
        for h, v in ((8, 100), (12, 130), (18, 145)):
            self._make_reading(h, v)
        result = self.builder._collect_glucose(self.user, self.target)
        # All pre-C7 keys must still be present and computed.
        self.assertIn("glucose_avg", result)
        self.assertIn("glucose_min", result)
        self.assertIn("glucose_max", result)
        self.assertIn("glucose_variability", result)
        self.assertIn("time_in_range_pct", result)
        self.assertEqual(result["glucose_avg"], Decimal("125.00"))
        self.assertEqual(result["glucose_min"], Decimal("100.00"))
        self.assertEqual(result["glucose_max"], Decimal("145.00"))

    def test_no_readings_returns_none(self):
        # No GlucoseEntry rows on this date → collector returns None
        # exactly as before C7.
        result = self.builder._collect_glucose(self.user, self.target)
        self.assertIsNone(result)


# ── Insulin collector ───────────────────────────────────────────────


class CollectInsulinTests(_MuteIntakeSignals, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("collect_insulin@test.com")
        cls.builder = DailyHealthSummaryBuilder()
        cls.target = date(2026, 5, 20)

    def _make_insulin_intake(self, name: str, subtype: str):
        return Intake.objects.create(
            user=self.user,
            name=name,
            dose="varies",
            frequency="daily",
            start_date=date(2026, 5, 1),
            intake_status=Intake.STATUS_ACTIVE,
            intake_type=Intake.INTAKE_TYPE_MEDICATION,
            intake_subtype=subtype,
        )

    def test_no_insulin_logs_returns_none(self):
        self.assertIsNone(self.builder._collect_insulin(self.user, self.target))

    def test_basal_only(self):
        lantus = self._make_insulin_intake(
            "Lantus", Intake.INTAKE_SUBTYPE_INSULIN_BASAL,
        )
        IntakeLog.objects.create(
            user=self.user, intake=lantus, scheduled_date=self.target,
            log_status="taken", dose_amount=Decimal("18.0"),
            dose_unit=IntakeLog.DOSE_UNIT_UNITS,
            dose_event_type=IntakeLog.DOSE_EVENT_BASAL,
        )
        result = self.builder._collect_insulin(self.user, self.target)
        self.assertEqual(result["insulin_total_units"], Decimal("18.00"))
        self.assertEqual(result["insulin_basal_units"], Decimal("18.00"))
        self.assertIsNone(result["insulin_bolus_units"])

    def test_basal_plus_bolus_plus_correction(self):
        lantus = self._make_insulin_intake(
            "Lantus", Intake.INTAKE_SUBTYPE_INSULIN_BASAL,
        )
        humalog = self._make_insulin_intake(
            "Humalog", Intake.INTAKE_SUBTYPE_INSULIN_BOLUS,
        )
        # Basal 18u, two meal boluses 5+7=12u, one correction 3u.
        # Total = 18 + 12 + 3 = 33. Basal = 18. Bolus = 12 + 3 = 15.
        IntakeLog.objects.create(
            user=self.user, intake=lantus, scheduled_date=self.target,
            log_status="taken", dose_amount=Decimal("18"),
            dose_unit=IntakeLog.DOSE_UNIT_UNITS,
            dose_event_type=IntakeLog.DOSE_EVENT_BASAL,
        )
        for dose in (5, 7):
            IntakeLog.objects.create(
                user=self.user, intake=humalog, scheduled_date=self.target,
                log_status="taken", dose_amount=Decimal(dose),
                dose_unit=IntakeLog.DOSE_UNIT_UNITS,
                dose_event_type=IntakeLog.DOSE_EVENT_MEAL_BOLUS,
            )
        IntakeLog.objects.create(
            user=self.user, intake=humalog, scheduled_date=self.target,
            log_status="taken", dose_amount=Decimal(3),
            dose_unit=IntakeLog.DOSE_UNIT_UNITS,
            dose_event_type=IntakeLog.DOSE_EVENT_CORRECTION,
        )
        result = self.builder._collect_insulin(self.user, self.target)
        self.assertEqual(result["insulin_total_units"], Decimal("33.00"))
        self.assertEqual(result["insulin_basal_units"], Decimal("18.00"))
        self.assertEqual(result["insulin_bolus_units"], Decimal("15.00"))

    def test_missed_or_skipped_insulin_excluded(self):
        lantus = self._make_insulin_intake(
            "Lantus", Intake.INTAKE_SUBTYPE_INSULIN_BASAL,
        )
        IntakeLog.objects.create(
            user=self.user, intake=lantus, scheduled_date=self.target,
            log_status="taken", dose_amount=Decimal(18),
            dose_unit=IntakeLog.DOSE_UNIT_UNITS,
            dose_event_type=IntakeLog.DOSE_EVENT_BASAL,
        )
        IntakeLog.objects.create(
            user=self.user, intake=lantus, scheduled_date=self.target,
            log_status="missed", dose_amount=Decimal(10),
            dose_unit=IntakeLog.DOSE_UNIT_UNITS,
            dose_event_type=IntakeLog.DOSE_EVENT_BASAL,
        )
        result = self.builder._collect_insulin(self.user, self.target)
        self.assertEqual(result["insulin_total_units"], Decimal("18.00"))

    def test_non_insulin_log_with_dose_amount_excluded(self):
        # Edge case: a non-insulin medication somehow has dose_amount set.
        # The C7 collector filters by intake_subtype in INSULIN_SUBTYPES,
        # so such a log must NOT pollute insulin totals.
        regular_med = Intake.objects.create(
            user=self.user, name="Lisinopril", dose="10mg", frequency="daily",
            start_date=date(2026, 5, 1),
            intake_status=Intake.STATUS_ACTIVE,
            intake_type=Intake.INTAKE_TYPE_MEDICATION,
        )
        IntakeLog.objects.create(
            user=self.user, intake=regular_med, scheduled_date=self.target,
            log_status="taken", dose_amount=Decimal(999),
            dose_unit=IntakeLog.DOSE_UNIT_MG,
        )
        self.assertIsNone(self.builder._collect_insulin(self.user, self.target))


# ── Build pipeline integration ──────────────────────────────────────


class BuildForDateInsulinSignalTests(_MuteIntakeSignals, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("build_insulin@test.com")
        cls.builder = DailyHealthSummaryBuilder()
        cls.target = date(2026, 5, 20)

    def test_insulin_signal_added_when_data_present(self):
        lantus = Intake.objects.create(
            user=self.user, name="Lantus", dose="varies", frequency="daily",
            start_date=date(2026, 5, 1),
            intake_status=Intake.STATUS_ACTIVE,
            intake_type=Intake.INTAKE_TYPE_MEDICATION,
            intake_subtype=Intake.INTAKE_SUBTYPE_INSULIN_BASAL,
        )
        IntakeLog.objects.create(
            user=self.user, intake=lantus, scheduled_date=self.target,
            log_status="taken", dose_amount=Decimal(18),
            dose_unit=IntakeLog.DOSE_UNIT_UNITS,
            dose_event_type=IntakeLog.DOSE_EVENT_BASAL,
        )
        summary = self.builder.build_for_date(self.user, self.target)
        self.assertIn("insulin", summary.signals_present)
        self.assertEqual(summary.insulin_total_units, Decimal("18.00"))

    def test_no_insulin_no_signal_no_fields(self):
        summary = self.builder.build_for_date(self.user, self.target)
        self.assertNotIn("insulin", summary.signals_present)
        self.assertIsNone(summary.insulin_total_units)
        self.assertEqual(summary.meal_response_distribution, {})
