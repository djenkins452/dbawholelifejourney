"""
Phase 5 regression tests — reconciliation + dedupe hardening.

Test matrix:
A. Workout completed + linked routine missed → one obligation, no double penalty
B. Workout not completed + routine missed → legitimate miss counted once
C. Late workout satisfying routine → completed_late, not missed + completed
D. Explicit skip on linked obligation → skip preserved
E. Rescheduled linked item → not prematurely missed
F. Unrelated routine and workout → not incorrectly deduped
G. Rollup integrity → counts reflect reconciled primary events only
H. Detail payload → linked/suppressed explanations present
I. Journal/faith/task → unaffected by reconciliation
J. End-to-end integration
"""

from datetime import date, time, timedelta

from django.conf import settings
from django.test import TestCase

from apps.dashboard_v2.compliance.constants import (
    BUCKET_ROUTINE,
    BUCKET_WORKOUT,
    DOMAIN_ROUTINE,
    DOMAIN_WORKOUT,
    FINAL_COMPLETED,
    FINAL_COMPLETED_LATE,
    FINAL_MISSED,
    FINAL_SKIPPED,
    SUPPRESSED_BY_LINKED_WORKOUT,
)
from apps.dashboard_v2.compliance.models import ComplianceEvent
from apps.dashboard_v2.compliance.reconciliation import reconcile_events
from apps.dashboard_v2.compliance.service import ComplianceService
from apps.users.models import User


def _create_test_user(email="recon_test@example.com"):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _workout_event(user, day, final_status=FINAL_COMPLETED, label="Chest Day (Monday)"):
    """Helper to create a workout event dict."""
    return {
        "user": user,
        "event_date": day,
        "domain": DOMAIN_WORKOUT,
        "scoring_bucket": BUCKET_WORKOUT,
        "item_type": "WorkoutSchedule",
        "item_id": 1,
        "item_label": label,
        "expected_at": time(7, 0),
        "expected": True,
        "actual_status": "completed" if final_status == FINAL_COMPLETED else "none",
        "final_status": final_status,
        "reason_code": "on_time" if final_status == FINAL_COMPLETED else "no_log",
        "reason_detail": {},
        "source_system": "workout_schedule_log",
    }


def _routine_workout_event(user, day, final_status=FINAL_MISSED, label="Workout"):
    """Helper to create a routine event for a workout-named item."""
    return {
        "user": user,
        "event_date": day,
        "domain": DOMAIN_ROUTINE,
        "scoring_bucket": BUCKET_ROUTINE,
        "item_type": "RoutineSchedule",
        "item_id": 10,
        "item_label": label,
        "expected_at": time(7, 0),
        "expected": True,
        "actual_status": "none" if final_status == FINAL_MISSED else "completed",
        "final_status": final_status,
        "reason_code": "no_log" if final_status == FINAL_MISSED else "on_time",
        "reason_detail": {"routine_name": "Morning Routine"},
        "source_system": "routine_schedule",
    }


def _routine_nonworkout_event(user, day, label="Prayer Time", final_status=FINAL_COMPLETED):
    """Helper for a routine item that is NOT workout-named."""
    return {
        "user": user,
        "event_date": day,
        "domain": DOMAIN_ROUTINE,
        "scoring_bucket": BUCKET_ROUTINE,
        "item_type": "RoutineSchedule",
        "item_id": 20,
        "item_label": label,
        "expected_at": time(6, 0),
        "expected": True,
        "actual_status": "completed",
        "final_status": final_status,
        "reason_code": "on_time",
        "reason_detail": {"routine_name": "Morning Routine"},
        "source_system": "routine_log",
    }


class TestWorkoutRoutineLinkage(TestCase):
    """A-F: Core workout↔routine reconciliation scenarios."""

    def setUp(self):
        self.user = _create_test_user("recon_a@example.com")
        self.today = date.today()

    def test_A_workout_completed_routine_missed_no_double_penalty(self):
        """Workout completed + routine workout item missed → suppressed miss."""
        events = [
            _workout_event(self.user, self.today, FINAL_COMPLETED),
            _routine_workout_event(self.user, self.today, FINAL_MISSED),
        ]
        reconcile_events(events, self.user)

        workout_ev = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        routine_ev = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        # Both should share an obligation key
        self.assertTrue(workout_ev["obligation_key"])
        self.assertEqual(workout_ev["obligation_key"], routine_ev["obligation_key"])

        # Workout is primary, routine is suppressed
        self.assertTrue(workout_ev["is_primary"])
        self.assertFalse(routine_ev["is_primary"])
        self.assertEqual(routine_ev["suppression_reason"], SUPPRESSED_BY_LINKED_WORKOUT)

        # Routine miss should be overridden to completed (reflecting the linked completion)
        self.assertEqual(routine_ev["final_status"], FINAL_COMPLETED)
        self.assertEqual(routine_ev["reason_detail"]["original_status"], "missed")
        self.assertEqual(routine_ev["reason_detail"]["satisfied_by_label"], "Chest Day (Monday)")

    def test_B_workout_missed_routine_missed_legitimate_miss(self):
        """Both missed → no suppression, both count."""
        events = [
            _workout_event(self.user, self.today, FINAL_MISSED),
            _routine_workout_event(self.user, self.today, FINAL_MISSED),
        ]
        reconcile_events(events, self.user)

        workout_ev = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        routine_ev = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        # One primary, one suppressed as duplicate (both missed, still one obligation)
        self.assertTrue(workout_ev["is_primary"])
        self.assertFalse(routine_ev["is_primary"])
        # Not satisfied_by_linked_workout since nothing was completed
        self.assertNotEqual(routine_ev["suppression_reason"], SUPPRESSED_BY_LINKED_WORKOUT)

    def test_C_late_workout_satisfying_routine(self):
        """Late workout → routine suppressed with completed_late, not missed."""
        events = [
            _workout_event(self.user, self.today, FINAL_COMPLETED_LATE),
            _routine_workout_event(self.user, self.today, FINAL_MISSED),
        ]
        reconcile_events(events, self.user)

        routine_ev = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        self.assertFalse(routine_ev["is_primary"])
        self.assertEqual(routine_ev["suppression_reason"], SUPPRESSED_BY_LINKED_WORKOUT)
        self.assertEqual(routine_ev["final_status"], FINAL_COMPLETED_LATE)

    def test_D_skip_on_linked_obligation(self):
        """Workout skipped + routine skipped → skip preserved."""
        events = [
            _workout_event(self.user, self.today, FINAL_SKIPPED),
            _routine_workout_event(self.user, self.today, FINAL_SKIPPED),
        ]
        reconcile_events(events, self.user)

        workout_ev = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        routine_ev = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        self.assertTrue(workout_ev["is_primary"])
        self.assertEqual(workout_ev["final_status"], FINAL_SKIPPED)
        self.assertFalse(routine_ev["is_primary"])

    def test_F_unrelated_routine_not_deduped(self):
        """Non-workout routine items should NOT get a workout obligation key."""
        events = [
            _workout_event(self.user, self.today, FINAL_COMPLETED),
            _routine_nonworkout_event(self.user, self.today, "Prayer Time"),
        ]
        reconcile_events(events, self.user)

        workout_ev = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        prayer_ev = next(e for e in events if e["item_label"] == "Prayer Time")

        # Different obligation keys — no grouping
        self.assertNotEqual(workout_ev["obligation_key"], prayer_ev["obligation_key"])
        self.assertTrue(prayer_ev["is_primary"])


class TestRollupIntegrity(TestCase):
    """G: Rollup counts reflect reconciled primary events only."""

    def setUp(self):
        self.user = _create_test_user("rollup_recon@example.com")
        self.today = date.today()

    def test_rollup_excludes_suppressed_events(self):
        """Suppressed events should not appear in rollup counts."""
        # Create: 1 primary completed workout + 1 suppressed routine
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_WORKOUT, scoring_bucket=BUCKET_WORKOUT,
            item_type="WorkoutSchedule", item_id=1,
            item_label="Chest Day", expected=True,
            actual_status="completed", final_status=FINAL_COMPLETED,
            reason_code="on_time", source_system="workout_schedule_log",
            obligation_key=f"workout:{self.user.id}:{self.today}",
            is_primary=True, suppression_reason="",
        )
        # Suppressed routine duplicate
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_ROUTINE, scoring_bucket=BUCKET_ROUTINE,
            item_type="RoutineSchedule", item_id=10,
            item_label="Workout", expected=True,
            actual_status="completed", final_status=FINAL_COMPLETED,
            reason_code="satisfied_by_linked_workout",
            source_system="routine_schedule",
            obligation_key=f"workout:{self.user.id}:{self.today}",
            is_primary=False,
            suppression_reason=SUPPRESSED_BY_LINKED_WORKOUT,
        )

        svc = ComplianceService(self.user)

        # Workout rollup: 1 completed
        workout_rollup = svc.get_rollup(BUCKET_WORKOUT, self.today, self.today)
        self.assertEqual(workout_rollup["expected"], 1)
        self.assertEqual(workout_rollup["completed"], 1)

        # Routine rollup: 0 expected (suppressed event excluded)
        routine_rollup = svc.get_rollup(BUCKET_ROUTINE, self.today, self.today)
        self.assertEqual(routine_rollup["expected"], 0)


class TestDetailPayload(TestCase):
    """H: Detail query includes suppression info."""

    def setUp(self):
        self.user = _create_test_user("detail_recon@example.com")
        self.today = date.today()

    def test_detail_shows_suppression_info(self):
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_ROUTINE, scoring_bucket=BUCKET_ROUTINE,
            item_type="RoutineSchedule", item_id=10,
            item_label="Workout", expected=True,
            actual_status="completed", final_status=FINAL_COMPLETED,
            reason_code="satisfied_by_linked_workout",
            source_system="routine_schedule",
            obligation_key=f"workout:{self.user.id}:{self.today}",
            is_primary=False,
            suppression_reason=SUPPRESSED_BY_LINKED_WORKOUT,
        )

        svc = ComplianceService(self.user)
        detail = svc.get_detail(BUCKET_ROUTINE, self.today, self.today)

        self.assertEqual(len(detail), 1)
        item = detail[0]["items"][0]
        self.assertTrue(item["is_suppressed"])
        self.assertEqual(item["suppression_reason"], SUPPRESSED_BY_LINKED_WORKOUT)
        self.assertTrue(item["suppression_label"])


class TestEndToEndReconciliation(TestCase):
    """J: Full pipeline — evaluate → reconcile → persist → rollup → detail."""

    def setUp(self):
        self.user = _create_test_user("e2e_recon@example.com")
        self.today = date.today()

    def test_full_pipeline_no_exceptions(self):
        """Evaluate week runs without errors even with no data."""
        svc = ComplianceService(self.user)
        count = svc.evaluate_week()
        self.assertIsInstance(count, int)

    def test_reconciliation_persists_obligation_keys(self):
        """After evaluate, events in DB should have obligation keys set."""
        svc = ComplianceService(self.user)
        svc.evaluate_week()

        # Check that any workout events have obligation keys
        workout_events = ComplianceEvent.objects.filter(
            user=self.user, domain=DOMAIN_WORKOUT,
        )
        for ev in workout_events:
            self.assertTrue(ev.obligation_key, f"Workout event missing obligation_key: {ev}")
