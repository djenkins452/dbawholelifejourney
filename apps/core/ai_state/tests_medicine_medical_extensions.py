"""
build_medicine_state + build_medical_state extensions (Phase 1A · C6) —
regression coverage.

Asserts:

1. build_medicine_state populates the new insulin-aggregate keys
   (insulin_total_today_units, insulin_total_7d_units,
   insulin_total_30d_units, insulin_daily_avg_30d_units) when insulin
   IntakeLogs exist with dose_amount, and OMITS them entirely when no
   insulin observation exists (None, not zero).

2. build_medicine_state's existing flat keys and _contract shape are
   unchanged (additive only).

3. build_medical_state populates recent_glycemic_labs with LabResults
   whose canonical_test.category == 'diabetes', and emits an empty
   list when none exist. Existing medical_alerts and recent_lab_panels
   are unchanged.

4. Bible Journey's faith state remains intact (cross-check from C5
   guardrail; C6 only edits build_medicine_state and build_medical_state
   so the regression bar is lower, but we re-pin it).

Signal mute: reuses the mixin pattern from C3's insulin regression
tests. Disconnect Intake/IntakeLog/IntakeSchedule SAE-refresh signals
at class setup; reconnect at teardown.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import date, datetime, timedelta, timezone
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
from apps.core.ai_state.state_builder import (
    build_faith_state,
    build_medical_state,
    build_medicine_state,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


class _MuteIntakeSignals:
    """Same mute pattern as C3 — scoped to test class only."""

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


def _make_user(email: str = "c6@test.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ── build_medicine_state insulin extensions ─────────────────────────


class MedicineStateInsulinExtensionsTests(_MuteIntakeSignals, TestCase):
    """Insulin aggregate keys are populated when insulin logs exist
    and absent (None / unset) when they don't."""

    INSULIN_KEYS = (
        "insulin_total_today_units",
        "insulin_total_7d_units",
        "insulin_total_30d_units",
        "insulin_daily_avg_30d_units",
    )

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("medicine_insulin@test.com")

    def test_no_insulin_data_omits_insulin_keys(self):
        # The builder uses dict-set assignment guarded on data presence;
        # with no insulin logs, the keys should not appear at all (or
        # equivalently, .get() returns None).
        state = build_medicine_state(self.user)
        for key in self.INSULIN_KEYS:
            self.assertIsNone(
                state.get(key),
                f"{key} should be None/absent when no insulin logged",
            )

    def test_insulin_totals_populated_from_intakelogs(self):
        from apps.health.models import Intake, IntakeLog

        insulin = Intake.objects.create(
            user=self.user,
            name="Lantus",
            dose="varies",
            frequency="daily",
            start_date=date(2026, 5, 1),
            intake_status=Intake.STATUS_ACTIVE,
            intake_type=Intake.INTAKE_TYPE_MEDICATION,
            intake_subtype=Intake.INTAKE_SUBTYPE_INSULIN_BASAL,
        )
        today = date.today()
        # 5 days of logs in last 7d: 18 + 18 + 20 + 18 + 17 = 91 units.
        # All within both 7d and 30d windows.
        for offset, dose in ((0, 18), (1, 18), (2, 20), (3, 18), (5, 17)):
            IntakeLog.objects.create(
                user=self.user,
                intake=insulin,
                scheduled_date=today - timedelta(days=offset),
                log_status="taken",
                dose_amount=Decimal(dose),
                dose_unit=IntakeLog.DOSE_UNIT_UNITS,
                dose_event_type=IntakeLog.DOSE_EVENT_BASAL,
            )

        state = build_medicine_state(self.user)
        # Today only (offset 0) → 18
        self.assertEqual(state["insulin_total_today_units"], 18.0)
        # 7d window includes all five logs → 91
        self.assertEqual(state["insulin_total_7d_units"], 91.0)
        # 30d window also includes all five → 91, daily avg ~3.03
        self.assertEqual(state["insulin_total_30d_units"], 91.0)
        self.assertAlmostEqual(
            state["insulin_daily_avg_30d_units"], 91.0 / 30, places=2,
        )

    def test_missed_or_skipped_insulin_logs_excluded(self):
        # Only 'taken' and 'late' count toward dose totals — same rule
        # as the existing adherence math.
        from apps.health.models import Intake, IntakeLog

        insulin = Intake.objects.create(
            user=self.user,
            name="Humalog",
            dose="varies",
            frequency="daily",
            start_date=date(2026, 5, 1),
            intake_status=Intake.STATUS_ACTIVE,
            intake_type=Intake.INTAKE_TYPE_MEDICATION,
            intake_subtype=Intake.INTAKE_SUBTYPE_INSULIN_BOLUS,
        )
        today = date.today()
        # One taken at 10 units, one missed at 8 units (should be excluded).
        IntakeLog.objects.create(
            user=self.user, intake=insulin, scheduled_date=today,
            log_status="taken", dose_amount=Decimal(10),
            dose_unit=IntakeLog.DOSE_UNIT_UNITS,
        )
        IntakeLog.objects.create(
            user=self.user, intake=insulin, scheduled_date=today,
            log_status="missed", dose_amount=Decimal(8),
            dose_unit=IntakeLog.DOSE_UNIT_UNITS,
        )
        state = build_medicine_state(self.user)
        self.assertEqual(state["insulin_total_today_units"], 10.0)

    def test_non_insulin_logs_do_not_contribute(self):
        # Non-insulin medications with dose_amount somehow set (edge
        # case) MUST NOT pollute insulin totals. The filter is by
        # intake_subtype in INSULIN_SUBTYPES.
        from apps.health.models import Intake, IntakeLog

        regular_med = Intake.objects.create(
            user=self.user,
            name="Lisinopril",
            dose="10mg",
            frequency="daily",
            start_date=date(2026, 5, 1),
            intake_status=Intake.STATUS_ACTIVE,
            intake_type=Intake.INTAKE_TYPE_MEDICATION,
            # intake_subtype intentionally null.
        )
        IntakeLog.objects.create(
            user=self.user, intake=regular_med, scheduled_date=date.today(),
            log_status="taken", dose_amount=Decimal(999),
            dose_unit=IntakeLog.DOSE_UNIT_MG,
        )
        state = build_medicine_state(self.user)
        self.assertIsNone(state.get("insulin_total_today_units"))


# ── build_medicine_state existing shape preserved ───────────────────


class MedicineStateExistingShapePreservedTests(_MuteIntakeSignals, TestCase):
    """Existing flat keys and _contract shape unchanged by C6."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("medicine_shape@test.com")

    def test_contract_section_keys_unchanged(self):
        state = build_medicine_state(self.user)
        contract = state.get("_contract", {})
        for required in ("summary", "today", "upcoming", "alerts"):
            self.assertIn(required, contract, f"_contract.{required} missing")

    def test_existing_flat_keys_present(self):
        state = build_medicine_state(self.user)
        for key in (
            "active_count", "active_medicines", "active_medications",
            "active_supplements", "medication_count", "supplement_count",
            "medication_status", "medication_status_reason",
        ):
            self.assertIn(key, state, f"existing flat key {key} missing")

    def test_meta_completeness_unchanged(self):
        state = build_medicine_state(self.user)
        meta = state.get("_meta", {})
        self.assertEqual(meta.get("completeness"), "full")
        self.assertEqual(meta.get("confidence"), "high")


# ── build_medical_state glycemic labs extension ─────────────────────


class MedicalStateGlycemicLabsTests(TestCase):
    """recent_glycemic_labs is populated from LabResults with
    canonical_test.category == 'diabetes'."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("medical_glycemic@test.com")

    def test_no_glycemic_labs_emits_empty_list(self):
        state = build_medical_state(self.user)
        self.assertEqual(state.get("recent_glycemic_labs"), [])

    def test_glycemic_labs_populated_from_lab_results(self):
        from apps.medical.models import LabResult, LabTestCatalog

        # get_or_create: the seed migration (medical/0002) already
        # inserts these catalog rows, so creating them outright raises a
        # UNIQUE violation on name. Take the seeded row when present.
        hba1c_catalog, _ = LabTestCatalog.objects.get_or_create(
            name="Hemoglobin A1c",
            defaults={
                "short_name": "HbA1c",
                "category": "diabetes",
                "default_unit": "%",
            },
        )
        # One glycemic lab + one non-glycemic lab; only the glycemic
        # one should appear.
        lipid_catalog, _ = LabTestCatalog.objects.get_or_create(
            name="LDL Cholesterol",
            defaults={
                "short_name": "LDL",
                "category": "lipids",
                "default_unit": "mg/dL",
            },
        )
        LabResult.objects.create(
            id=uuid.uuid4(),
            user=self.user,
            canonical_test=hba1c_catalog,
            raw_test_name="Hemoglobin A1c",
            value_text="7.2",
            value_numeric=Decimal("7.2"),
            unit="%",
            collected_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        LabResult.objects.create(
            id=uuid.uuid4(),
            user=self.user,
            canonical_test=lipid_catalog,
            raw_test_name="LDL Cholesterol",
            value_text="110",
            value_numeric=Decimal("110"),
            unit="mg/dL",
            collected_at=datetime.now(timezone.utc) - timedelta(days=10),
        )
        state = build_medical_state(self.user)
        glycemic = state.get("recent_glycemic_labs", [])
        self.assertEqual(len(glycemic), 1)
        entry = glycemic[0]
        self.assertEqual(entry["test"], "HbA1c")
        self.assertEqual(entry["value_numeric"], 7.2)
        self.assertEqual(entry["unit"], "%")

    def test_existing_medical_alerts_and_panels_unchanged(self):
        state = build_medical_state(self.user)
        # Both keys must be present (additive guarantee).
        self.assertIn("medical_alerts", state)
        self.assertIn("recent_lab_panels", state)
        # _contract structure preserved.
        contract = state.get("_contract", {})
        for required in ("summary", "today", "upcoming", "alerts", "detail"):
            self.assertIn(required, contract)


# ── Bible Journey faith-state guardrail (re-pinned) ─────────────────


class FaithStateUnchangedByC6Tests(TestCase):
    """C6 only edits build_medicine_state and build_medical_state.
    build_faith_state and its journey integration must remain intact."""

    def test_journey_integration_still_wired(self):
        source = inspect.getsource(build_faith_state)
        self.assertIn(
            "from apps.faith.journey.state import build_journey_state",
            source,
        )
        self.assertIn(
            'state["journey"] = build_journey_state(user)',
            source,
        )
        self.assertIn("except ImportError", source)
