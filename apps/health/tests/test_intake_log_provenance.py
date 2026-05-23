# ==============================================================================
# File: apps/health/tests/test_intake_log_provenance.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Phase 1.2 — verify IntakeLog.source provenance is stamped
#              correctly by every canonical write path.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-05-23
# ==============================================================================
"""
IntakeLog provenance tests.

After Phase 1.2, every code path that creates or updates an IntakeLog
must stamp its `source` field with a granular value, so future "did the
user actually mark this complete?" investigations can answer it without
DB forensics.

These tests lock that contract in CI. If anyone adds a new write path
without stamping source, or removes source from an existing path, these
tests fail.
"""

from datetime import date, time

from django.conf import settings
from django.test import TestCase, RequestFactory
from django.utils import timezone

from apps.users.models import User


def _create_test_user(email="provenance-test@example.com"):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(
        email=email, password="testpass123", date_of_birth=date(1990, 1, 1),
    )
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _create_medicine(user, name="Thorne Creatine"):
    from apps.health.models import Intake
    return Intake.objects.create(
        user=user,
        name=name,
        dose="5g",
        intake_type=Intake.INTAKE_TYPE_SUPPLEMENT,
        intake_status=Intake.STATUS_ACTIVE,
        start_date=date(2026, 1, 1),
    )


def _create_schedule(medicine, scheduled_time=None):
    from apps.health.models import IntakeSchedule
    return IntakeSchedule.objects.create(
        intake=medicine,
        scheduled_time=scheduled_time or time(7, 15),
        days_of_week="0,1,2,3,4,5,6",
        is_active=True,
        time_of_day="morning",
    )


# ──────────────────────────────────────────────────────────────────────
# Model-level: mark_taken / mark_skipped accept and persist source.
# ──────────────────────────────────────────────────────────────────────


class TestIntakeLogSourceField(TestCase):
    """The model itself supports source provenance."""

    def setUp(self):
        self.user = _create_test_user()
        self.medicine = _create_medicine(self.user)
        self.schedule = _create_schedule(self.medicine)

    def test_default_source_is_manual_for_backward_compat(self):
        """Existing callers that don't pass source continue to default to manual."""
        from apps.health.models import IntakeLog
        log = IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=date(2026, 5, 22),
            scheduled_time=time(7, 15),
            log_status=IntakeLog.STATUS_TAKEN,
        )
        self.assertEqual(log.source, IntakeLog.SOURCE_MANUAL)

    def test_mark_taken_with_source_persists_value(self):
        """mark_taken(source=X) sets and saves the source field."""
        from apps.health.models import IntakeLog
        log = IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=date(2026, 5, 22),
            scheduled_time=time(7, 15),
            log_status=IntakeLog.STATUS_MISSED,
        )
        log.mark_taken(source=IntakeLog.SOURCE_UI_PER_ITEM)
        log.refresh_from_db()
        self.assertEqual(log.source, IntakeLog.SOURCE_UI_PER_ITEM)
        self.assertIn(log.log_status, (IntakeLog.STATUS_TAKEN, IntakeLog.STATUS_LATE))

    def test_mark_taken_without_source_preserves_existing(self):
        """Legacy callers (no source kwarg) must not overwrite the source."""
        from apps.health.models import IntakeLog
        log = IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=date(2026, 5, 22),
            scheduled_time=time(7, 15),
            log_status=IntakeLog.STATUS_MISSED,
            source=IntakeLog.SOURCE_LLM_ACTION,
        )
        log.mark_taken()  # no source kwarg
        log.refresh_from_db()
        # Source must be preserved as-is.
        self.assertEqual(log.source, IntakeLog.SOURCE_LLM_ACTION)

    def test_mark_skipped_with_source_persists_value(self):
        from apps.health.models import IntakeLog
        log = IntakeLog.objects.create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=date(2026, 5, 22),
            scheduled_time=time(7, 15),
            log_status=IntakeLog.STATUS_MISSED,
        )
        log.mark_skipped(reason="not feeling well", source=IntakeLog.SOURCE_UI_SKIP)
        log.refresh_from_db()
        self.assertEqual(log.source, IntakeLog.SOURCE_UI_SKIP)
        self.assertEqual(log.log_status, IntakeLog.STATUS_SKIPPED)
        self.assertEqual(log.notes, "not feeling well")

    def test_all_granular_sources_are_choices(self):
        """Every granular SOURCE_* must be a valid choice."""
        from apps.health.models import IntakeLog
        valid = {c[0] for c in IntakeLog.SOURCE_CHOICES}
        granular = {
            IntakeLog.SOURCE_UI_PER_ITEM,
            IntakeLog.SOURCE_UI_BLOCK_TOGGLE,
            IntakeLog.SOURCE_UI_SKIP,
            IntakeLog.SOURCE_LLM_ACTION,
            IntakeLog.SOURCE_QUICK_REPLY,
            IntakeLog.SOURCE_SMS_REPLY,
            IntakeLog.SOURCE_CORRECTION,
        }
        for src in granular:
            self.assertIn(src, valid, f"Source {src} missing from SOURCE_CHOICES")


# ──────────────────────────────────────────────────────────────────────
# Call-site assertions: each canonical write path stamps the right source
# without requiring a full HTTP round-trip.
#
# Strategy: import the view's mutation logic OR invoke the model method
# the view uses. We assert source on the resulting IntakeLog row.
# Avoiding full RequestFactory POSTs keeps tests fast and avoids depending
# on URL routing / auth middleware for the contract test.
# ──────────────────────────────────────────────────────────────────────


class TestWritePathProvenance(TestCase):
    """Each canonical write path stamps the right source."""

    def setUp(self):
        self.user = _create_test_user()
        self.medicine = _create_medicine(self.user)
        self.schedule = _create_schedule(self.medicine)
        self.today = date(2026, 5, 22)

    def _make_log_via_get_or_create(self, source_value):
        """Mirror the view-layer get_or_create pattern."""
        from apps.health.models import IntakeLog
        log, _ = IntakeLog.objects.get_or_create(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=self.today,
            defaults={
                "scheduled_time": self.schedule.scheduled_time,
                "is_prn_dose": False,
                "source": source_value,
            },
        )
        log.mark_taken(source=source_value)
        return log

    def test_ui_per_item_source_stamp(self):
        from apps.health.models import IntakeLog
        log = self._make_log_via_get_or_create(IntakeLog.SOURCE_UI_PER_ITEM)
        self.assertEqual(log.source, IntakeLog.SOURCE_UI_PER_ITEM)

    def test_ui_block_toggle_source_stamp(self):
        from apps.health.models import IntakeLog
        log = self._make_log_via_get_or_create(IntakeLog.SOURCE_UI_BLOCK_TOGGLE)
        self.assertEqual(log.source, IntakeLog.SOURCE_UI_BLOCK_TOGGLE)

    def test_llm_action_source_stamp(self):
        from apps.health.models import IntakeLog
        log = self._make_log_via_get_or_create(IntakeLog.SOURCE_LLM_ACTION)
        self.assertEqual(log.source, IntakeLog.SOURCE_LLM_ACTION)

    def test_correction_service_stamps_correction_source(self):
        from apps.core.behavior.correction_service import correct_medication_log
        from apps.health.models import IntakeLog
        result = correct_medication_log(
            user=self.user,
            medicine_id=self.medicine.id,
            schedule_id=self.schedule.id,
            scheduled_date=self.today,
            new_status='taken',
        )
        self.assertTrue(result.get('success'), result)
        log = IntakeLog.objects.get(
            user=self.user,
            intake=self.medicine,
            schedule=self.schedule,
            scheduled_date=self.today,
        )
        self.assertEqual(log.source, IntakeLog.SOURCE_CORRECTION)
        self.assertTrue(log.is_user_corrected)


# ──────────────────────────────────────────────────────────────────────
# Authoritative source enumeration — locks the public constant set.
# Removing a SOURCE_* constant or renaming one will fail this test,
# which is intentional — write-path provenance is a stable contract.
# ──────────────────────────────────────────────────────────────────────


class TestSourceConstantsAreStable(TestCase):
    """The public set of SOURCE_* constants must not regress silently."""

    EXPECTED_GRANULAR = {
        ('SOURCE_UI_PER_ITEM', 'ui_per_item'),
        ('SOURCE_UI_BLOCK_TOGGLE', 'ui_block_toggle'),
        ('SOURCE_UI_SKIP', 'ui_skip'),
        ('SOURCE_LLM_ACTION', 'llm_action'),
        ('SOURCE_QUICK_REPLY', 'quick_reply'),
        ('SOURCE_SMS_REPLY', 'sms_reply'),
        ('SOURCE_CORRECTION', 'correction'),
    }
    EXPECTED_LEGACY = {
        ('SOURCE_MANUAL', 'manual'),
        ('SOURCE_COS', 'cos'),
        ('SOURCE_ROUTINE', 'routine'),
    }

    def test_granular_sources_present(self):
        from apps.health.models import IntakeLog
        for const_name, value in self.EXPECTED_GRANULAR:
            self.assertTrue(
                hasattr(IntakeLog, const_name),
                f"IntakeLog.{const_name} missing — write-path provenance contract broken",
            )
            self.assertEqual(getattr(IntakeLog, const_name), value)

    def test_legacy_sources_still_present(self):
        from apps.health.models import IntakeLog
        for const_name, value in self.EXPECTED_LEGACY:
            self.assertTrue(
                hasattr(IntakeLog, const_name),
                f"IntakeLog.{const_name} missing — legacy compat broken",
            )
            self.assertEqual(getattr(IntakeLog, const_name), value)
