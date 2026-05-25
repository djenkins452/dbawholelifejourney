"""
Insulin model fields — regression coverage (Phase 1A · C3).

These tests exist to satisfy the C3 guardrail: the new insulin-related
fields (Intake.intake_subtype, IntakeLog.dose_amount/dose_unit/
dose_event_type) MUST be invisible to non-insulin medications and
supplements. Anything that worked before C3 must work identically
after C3.

Specifically asserts:

1. Non-insulin Intakes save without intake_subtype; field defaults to
   null and is_insulin returns False.
2. Non-insulin IntakeLogs save without any dose_* fields; all default
   to null.
3. calculate_single_medicine_adherence() for a non-insulin medicine
   returns identical values when insulin intakes coexist alongside.
4. Querysets returning IntakeLogs for non-insulin meds are unchanged
   in count and dose-field contents.
5. MedicineForm validates and saves without intake_subtype.
6. __str__ output for Intake and IntakeLog is unchanged.

The principle being defended: ``if medication != insulin, nothing
changes`` (Phase 1A guardrail, 2026-05-24).

Signal mute note: the IntakeLog post_save handler in apps.ai.signals
schedules a Celery task to refresh SAE state. In the test environment
Redis is not available, and the Celery client retries 20 times before
falling back to sync — adding ~20s of redis-retry latency per log
created. We disconnect that handler at class setup and reconnect at
class teardown so these tests run in seconds, not minutes.
"""

from __future__ import annotations

from datetime import date, time, timedelta
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
from apps.health.forms import MedicineForm
from apps.health.medicine_utils import (
    calculate_medicine_adherence,
    calculate_single_medicine_adherence,
)
from apps.health.models import Intake, IntakeLog, IntakeSchedule
from apps.users.models import TermsAcceptance

User = get_user_model()


# ── Signal mute mixin ───────────────────────────────────────────────


class _MuteIntakeLogSignals:
    """Disconnect Intake/IntakeLog/IntakeSchedule SAE-refresh signals for
    the duration of a test class. The handlers in apps.ai.signals call
    _refresh_sae_module(), which dispatches to Celery; Celery then tries
    to reach Redis (not available in tests) and retries 20 times before
    falling back to sync — adding ~20s per save. Disconnecting brings
    these tests from minutes to seconds.

    We leave dashboard and SMS handlers connected — they are fast.
    """

    _MUTED_SIGNALS = (
        (post_save, "health.IntakeLog", invalidate_cache_on_medicine_log_save),
        (post_delete, "health.IntakeLog", invalidate_cache_on_medicine_log_delete),
        (post_save, "health.Intake", refresh_sae_on_medicine_change),
        (post_delete, "health.Intake", refresh_sae_on_medicine_change),
        (post_save, "health.IntakeSchedule", refresh_sae_on_medicine_schedule_change),
        (post_delete, "health.IntakeSchedule", refresh_sae_on_medicine_schedule_change),
    )

    @classmethod
    def setUpClass(cls):
        for signal, sender, handler in cls._MUTED_SIGNALS:
            signal.disconnect(handler, sender=sender)
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        for signal, sender, handler in cls._MUTED_SIGNALS:
            signal.connect(handler, sender=sender)


# ── Test helpers ────────────────────────────────────────────────────


def _make_user(email: str = "insulin_regression@test.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _make_intake(user, name: str = "Lisinopril", **overrides) -> Intake:
    defaults = dict(
        user=user,
        name=name,
        dose="10mg",
        frequency="daily",
        start_date=date(2026, 5, 1),
        intake_status=Intake.STATUS_ACTIVE,
        intake_type=Intake.INTAKE_TYPE_MEDICATION,
    )
    defaults.update(overrides)
    return Intake.objects.create(**defaults)


def _make_schedule(intake, scheduled_time=None) -> IntakeSchedule:
    return IntakeSchedule.objects.create(
        intake=intake,
        scheduled_time=scheduled_time or time(8, 0),
        days_of_week="0,1,2,3,4,5,6",
        is_active=True,
    )


def _make_log(user, intake, scheduled_date, status="taken", **overrides) -> IntakeLog:
    defaults = dict(
        user=user,
        intake=intake,
        scheduled_date=scheduled_date,
        log_status=status,
    )
    defaults.update(overrides)
    return IntakeLog.objects.create(**defaults)


# ── Default-state regressions ───────────────────────────────────────


class NonInsulinDefaultStateTests(_MuteIntakeLogSignals, TestCase):
    """Non-insulin Intakes/IntakeLogs save with new fields null."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("defaults@test.com")

    def test_intake_saves_without_intake_subtype(self):
        intake = _make_intake(self.user)
        self.assertIsNone(intake.intake_subtype)

    def test_intake_is_insulin_false_when_subtype_null(self):
        intake = _make_intake(self.user)
        self.assertFalse(intake.is_insulin)

    def test_intake_is_insulin_false_for_supplement(self):
        intake = _make_intake(
            self.user,
            name="Vitamin D",
            intake_type=Intake.INTAKE_TYPE_SUPPLEMENT,
        )
        self.assertFalse(intake.is_insulin)

    def test_intake_is_insulin_true_for_basal(self):
        intake = _make_intake(
            self.user,
            name="Lantus",
            intake_subtype=Intake.INTAKE_SUBTYPE_INSULIN_BASAL,
        )
        self.assertTrue(intake.is_insulin)

    def test_intake_is_insulin_true_for_bolus(self):
        intake = _make_intake(
            self.user,
            name="Humalog",
            intake_subtype=Intake.INTAKE_SUBTYPE_INSULIN_BOLUS,
        )
        self.assertTrue(intake.is_insulin)

    def test_intakelog_saves_without_dose_fields(self):
        intake = _make_intake(self.user)
        log = _make_log(self.user, intake, date(2026, 5, 10))
        self.assertIsNone(log.dose_amount)
        self.assertIsNone(log.dose_unit)
        self.assertIsNone(log.dose_event_type)

    def test_intakelog_str_unchanged_for_non_insulin(self):
        intake = _make_intake(self.user, name="Aspirin")
        log = _make_log(self.user, intake, date(2026, 5, 10))
        self.assertIn("Aspirin", str(log))
        self.assertIn("2026-05-10", str(log))

    def test_intake_str_unchanged_for_non_insulin(self):
        intake = _make_intake(self.user, name="Metformin", dose="500mg")
        self.assertEqual(str(intake), "Metformin (500mg)")


# ── Insulin coexistence regressions ─────────────────────────────────


class NonInsulinAdherenceUnchangedWhenInsulinCoexistsTests(
    _MuteIntakeLogSignals, TestCase
):
    """Per-medicine adherence for a non-insulin med is unchanged when
    insulin intakes coexist in the same user's data."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("coexist@test.com")
        cls.start = date(2026, 5, 1)
        cls.end = date(2026, 5, 7)

        # A non-insulin daily med with a 7-day schedule and all doses taken.
        cls.med = _make_intake(cls.user, name="Lisinopril")
        _make_schedule(cls.med)
        for offset in range(7):
            _make_log(
                cls.user,
                cls.med,
                cls.start + timedelta(days=offset),
                status="taken",
            )

    def test_baseline_non_insulin_single_med_adherence(self):
        result = calculate_single_medicine_adherence(
            self.user, self.med, self.start, self.end,
        )
        self.assertEqual(result["expected_doses"], 7)
        self.assertEqual(result["taken_doses"], 7)
        self.assertEqual(result["adherence_rate"], 100)

    def test_single_med_adherence_unchanged_when_insulin_added(self):
        baseline = calculate_single_medicine_adherence(
            self.user, self.med, self.start, self.end,
        )

        # Add an insulin intake with per-event dose data alongside.
        insulin = _make_intake(
            self.user,
            name="Lantus",
            intake_subtype=Intake.INTAKE_SUBTYPE_INSULIN_BASAL,
        )
        _make_schedule(insulin, scheduled_time=time(22, 0))
        for offset in range(7):
            IntakeLog.objects.create(
                user=self.user,
                intake=insulin,
                scheduled_date=self.start + timedelta(days=offset),
                log_status="taken",
                dose_amount=Decimal("18.0"),
                dose_unit=IntakeLog.DOSE_UNIT_UNITS,
                dose_event_type=IntakeLog.DOSE_EVENT_BASAL,
            )

        after = calculate_single_medicine_adherence(
            self.user, self.med, self.start, self.end,
        )
        # Every field of the non-insulin medicine's adherence dict must
        # be identical to baseline. If insulin presence perturbed the
        # math for a non-insulin med, this assertion fails.
        self.assertEqual(after, baseline)

    def test_overall_adherence_includes_insulin_as_medication(self):
        # Sanity guardrail in the other direction: insulin IS a
        # medication (intake_type='medication'), so the overall medication
        # adherence calc should count it. C3 must NOT silently exclude
        # insulin from medication aggregates — that would be a behavior
        # change to existing reporting.
        baseline = calculate_medicine_adherence(
            self.user, self.start, self.end,
            intake_type=Intake.INTAKE_TYPE_MEDICATION,
        )
        self.assertEqual(baseline["expected_doses"], 7)

        insulin = _make_intake(
            self.user,
            name="Lantus",
            intake_subtype=Intake.INTAKE_SUBTYPE_INSULIN_BASAL,
        )
        _make_schedule(insulin, scheduled_time=time(22, 0))
        for offset in range(7):
            IntakeLog.objects.create(
                user=self.user,
                intake=insulin,
                scheduled_date=self.start + timedelta(days=offset),
                log_status="taken",
                dose_amount=Decimal("18.0"),
                dose_unit=IntakeLog.DOSE_UNIT_UNITS,
                dose_event_type=IntakeLog.DOSE_EVENT_BASAL,
            )

        after = calculate_medicine_adherence(
            self.user, self.start, self.end,
            intake_type=Intake.INTAKE_TYPE_MEDICATION,
        )
        # Insulin's 7 expected/7 taken get added to the aggregate; this
        # mirrors pre-C3 behavior for any newly-added daily medication.
        self.assertEqual(after["expected_doses"], 14)
        self.assertEqual(after["taken_doses"], 14)

    def test_intakelog_queryset_unchanged_for_non_insulin(self):
        # Add insulin logs alongside the existing non-insulin logs.
        insulin = _make_intake(
            self.user,
            name="Humalog",
            intake_subtype=Intake.INTAKE_SUBTYPE_INSULIN_BOLUS,
        )
        IntakeLog.objects.create(
            user=self.user,
            intake=insulin,
            scheduled_date=self.start,
            log_status="taken",
            dose_amount=Decimal("4.0"),
            dose_unit=IntakeLog.DOSE_UNIT_UNITS,
            dose_event_type=IntakeLog.DOSE_EVENT_MEAL_BOLUS,
        )

        non_insulin_logs = IntakeLog.objects.filter(
            user=self.user,
            intake=self.med,
        )
        self.assertEqual(non_insulin_logs.count(), 7)
        for log in non_insulin_logs:
            self.assertIsNone(log.dose_amount)
            self.assertIsNone(log.dose_unit)
            self.assertIsNone(log.dose_event_type)


# ── Form regressions ───────────────────────────────────────────────


class MedicineFormBackwardCompatibilityTests(_MuteIntakeLogSignals, TestCase):
    """MedicineForm validates and saves without the new intake_subtype field."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("form@test.com")

    def _base_form_data(self):
        return {
            "intake_type": Intake.INTAKE_TYPE_MEDICATION,
            # intake_subtype intentionally omitted.
            "category": "prescription",
            "priority": Intake.PRIORITY_CRITICAL,
            "name": "Metformin",
            "purpose": "Glucose",
            "dose": "500mg",
            "dosage_unit": "mg",
            "frequency": "daily",
            "is_prn": False,
            "start_date": date(2026, 5, 1),
            "end_date": "",
            "current_supply": "",
            "refill_threshold": 7,
            "prescribing_doctor": "",
            "pharmacy": "",
            "rx_number": "",
            "instructions": "",
            "notes": "",
            "grace_period_minutes": 60,
        }

    def test_form_includes_intake_subtype_in_fields(self):
        form = MedicineForm()
        self.assertIn("intake_subtype", form.fields)

    def test_form_validates_without_intake_subtype(self):
        form = MedicineForm(data=self._base_form_data())
        self.assertTrue(form.is_valid(), msg=str(form.errors))

    def test_form_saves_with_null_intake_subtype(self):
        form = MedicineForm(data=self._base_form_data())
        self.assertTrue(form.is_valid(), msg=str(form.errors))
        intake = form.save(commit=False)
        intake.user = self.user
        intake.save()
        self.assertIsNone(intake.intake_subtype)
        self.assertFalse(intake.is_insulin)

    def test_form_accepts_explicit_insulin_subtype(self):
        data = self._base_form_data()
        data["name"] = "Lantus"
        data["intake_subtype"] = Intake.INTAKE_SUBTYPE_INSULIN_BASAL
        form = MedicineForm(data=data)
        self.assertTrue(form.is_valid(), msg=str(form.errors))
        intake = form.save(commit=False)
        intake.user = self.user
        intake.save()
        self.assertTrue(intake.is_insulin)


# ── Choices & constants regressions ────────────────────────────────


class ChoiceSurfaceTests(TestCase):
    """Pin the new choice surfaces to catch accidental drift."""

    def test_insulin_subtypes_set_is_exact(self):
        self.assertEqual(
            Intake.INSULIN_SUBTYPES,
            frozenset({"insulin_basal", "insulin_bolus"}),
        )

    def test_intake_subtype_choices_exact(self):
        keys = {choice[0] for choice in Intake.INTAKE_SUBTYPE_CHOICES}
        self.assertEqual(keys, {"insulin_basal", "insulin_bolus"})

    def test_dose_unit_choices_exact(self):
        keys = {choice[0] for choice in IntakeLog.DOSE_UNIT_CHOICES}
        self.assertEqual(keys, {"units", "ml", "mg"})

    def test_dose_event_type_choices_exact(self):
        keys = {choice[0] for choice in IntakeLog.DOSE_EVENT_TYPE_CHOICES}
        self.assertEqual(keys, {"basal", "meal_bolus", "correction"})

    def test_intake_type_choices_unchanged(self):
        # Guardrail: C3 must not change the existing intake_type set.
        keys = {choice[0] for choice in Intake.INTAKE_TYPE_CHOICES}
        self.assertEqual(keys, {"medication", "supplement"})
