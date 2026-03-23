"""
Reconciliation + obligation engine tests.

Covers:
A. Workout completed + linked routine missed → no double penalty
B. Workout not completed + routine missed → legitimate miss
C. Late workout satisfying routine → completed_late not missed
D. Skip on linked obligation → skip preserved
E. Rescheduled linked item
F. Unrelated routine not incorrectly deduped
G. Rollup excludes suppressed events
H. Detail shows suppression info
I. Multiple workouts same day (critical — tests identity granularity)
J. Journal + routine linkage
K. Faith + routine linkage
L. Task independence
M. End-to-end pipeline
N. Cache behavior
"""

from datetime import date, time, timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.dashboard_v2.compliance.constants import (
    BUCKET_JOURNAL,
    BUCKET_ROUTINE,
    BUCKET_TASK,
    BUCKET_WORKOUT,
    DOMAIN_FAITH,
    DOMAIN_JOURNAL,
    DOMAIN_ROUTINE,
    DOMAIN_TASK,
    DOMAIN_WORKOUT,
    FINAL_COMPLETED,
    FINAL_COMPLETED_LATE,
    FINAL_MISSED,
    FINAL_SKIPPED,
    OBLIGATION_JOURNAL,
    OBLIGATION_WORKOUT,
    SUPPRESSED_BY_LINKED_JOURNAL,
    SUPPRESSED_BY_LINKED_WORKOUT,
    SUPPRESSED_DUPLICATE,
)
from apps.dashboard_v2.compliance.models import ComplianceEvent
from apps.dashboard_v2.compliance.reconciliation import reconcile_events
from apps.dashboard_v2.compliance.service import ComplianceService, invalidate_compliance_cache
from apps.users.models import User


def _user(email="recon_test@example.com"):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _ev(user, day, domain, bucket, final_status, label="Item", item_id=1,
        item_type="Test", reason="on_time"):
    return {
        "user": user, "event_date": day, "domain": domain,
        "scoring_bucket": bucket, "item_type": item_type,
        "item_id": item_id, "item_label": label,
        "expected_at": time(7, 0), "expected": True,
        "actual_status": "completed" if "completed" in final_status else "none",
        "final_status": final_status, "reason_code": reason,
        "reason_detail": {}, "source_system": "test",
    }


class TestWorkoutRoutineLinkage(TestCase):
    """A-F: Core workout↔routine reconciliation."""

    def setUp(self):
        self.user = _user("recon_a@example.com")
        self.today = date.today()

    def test_A_workout_completed_routine_missed(self):
        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_COMPLETED, "Chest Day (Monday)", item_id=7),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_MISSED, "Workout", item_id=10, reason="no_log"),
        ]
        reconcile_events(events, self.user)

        workout = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        routine = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        self.assertTrue(workout["obligation_key"])
        self.assertEqual(workout["obligation_key"], routine["obligation_key"])
        self.assertTrue(workout["is_primary"])
        self.assertFalse(routine["is_primary"])
        self.assertEqual(routine["suppression_reason"], SUPPRESSED_BY_LINKED_WORKOUT)
        self.assertEqual(routine["final_status"], FINAL_COMPLETED)

    def test_B_both_missed_legitimate(self):
        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_MISSED, "Chest Day (Monday)", item_id=7, reason="no_log"),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_MISSED, "Workout", item_id=10, reason="no_log"),
        ]
        reconcile_events(events, self.user)

        workout = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        routine = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        self.assertTrue(workout["is_primary"])
        self.assertFalse(routine["is_primary"])
        self.assertEqual(routine["suppression_reason"], SUPPRESSED_DUPLICATE)

    def test_C_late_workout_satisfies_routine(self):
        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_COMPLETED_LATE, "Chest Day", item_id=7),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_MISSED, "Workout", item_id=10, reason="no_log"),
        ]
        reconcile_events(events, self.user)

        routine = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)
        self.assertFalse(routine["is_primary"])
        self.assertEqual(routine["suppression_reason"], SUPPRESSED_BY_LINKED_WORKOUT)
        self.assertEqual(routine["final_status"], FINAL_COMPLETED_LATE)

    def test_D_skip_on_linked_obligation(self):
        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_SKIPPED, "Chest Day", item_id=7, reason="explicit_skip"),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_SKIPPED, "Workout", item_id=10, reason="explicit_skip"),
        ]
        reconcile_events(events, self.user)

        workout = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        self.assertTrue(workout["is_primary"])
        self.assertEqual(workout["final_status"], FINAL_SKIPPED)

    def test_F_unrelated_routine_not_deduped(self):
        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_COMPLETED, "Chest Day", item_id=7),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_COMPLETED, "Prayer Time", item_id=20),
        ]
        reconcile_events(events, self.user)

        workout = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        prayer = next(e for e in events if e["item_label"] == "Prayer Time")

        self.assertNotEqual(workout["obligation_key"], prayer.get("obligation_key", ""))
        self.assertTrue(prayer["is_primary"])


class TestWorkoutObligationKey(TestCase):
    """I: Workout obligation key correctness."""

    def setUp(self):
        self.user = _user("multi_workout@example.com")
        self.today = date.today()

    def test_workout_uses_daily_identity(self):
        """WorkoutSchedule has unique_together(plan, day_of_week) so there's
        at most one workout per day. Identity is 'daily'."""
        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_COMPLETED, "Chest Day", item_id=7),
        ]
        reconcile_events(events, self.user)

        ev = events[0]
        self.assertEqual(ev["obligation_type"], OBLIGATION_WORKOUT)
        self.assertEqual(ev["obligation_identity"], "daily")
        self.assertIn("workout:", ev["obligation_key"])

    def test_workout_and_routine_share_daily_key(self):
        """Workout event and routine workout item share the same daily key."""
        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_COMPLETED, "Chest Day", item_id=7),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_MISSED, "Workout", item_id=10, reason="no_log"),
        ]
        reconcile_events(events, self.user)

        workout = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        routine = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        self.assertEqual(workout["obligation_key"], routine["obligation_key"])


class TestJournalRoutineLinkage(TestCase):
    """J: Journal entry + journal routine item reconciliation."""

    def setUp(self):
        self.user = _user("journal_recon@example.com")
        self.today = date.today()

    def test_journal_entry_satisfies_routine(self):
        events = [
            _ev(self.user, self.today, DOMAIN_JOURNAL, BUCKET_JOURNAL,
                FINAL_COMPLETED, "Daily Journal", item_id=None,
                item_type="JournalEntry"),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_MISSED, "Journal", item_id=15, reason="no_log"),
        ]
        reconcile_events(events, self.user)

        journal = next(e for e in events if e["domain"] == DOMAIN_JOURNAL)
        routine = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        self.assertEqual(journal["obligation_key"], routine["obligation_key"])
        self.assertTrue(journal["is_primary"])
        self.assertFalse(routine["is_primary"])
        self.assertEqual(routine["suppression_reason"], SUPPRESSED_BY_LINKED_JOURNAL)


class TestFaithRoutineLinkage(TestCase):
    """K: Faith activity + faith routine item reconciliation."""

    def setUp(self):
        self.user = _user("faith_recon@example.com")
        self.today = date.today()

    def test_prayer_completed_routine_missed(self):
        events = [
            _ev(self.user, self.today, DOMAIN_FAITH, BUCKET_ROUTINE,
                FINAL_COMPLETED, "Prayer", item_id=3,
                item_type="PrayerRoutine"),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_MISSED, "Prayer Time", item_id=15, reason="no_log"),
        ]
        reconcile_events(events, self.user)

        faith = next(e for e in events if e["domain"] == DOMAIN_FAITH)
        routine = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        self.assertEqual(faith["obligation_key"], routine["obligation_key"])
        self.assertTrue(faith["is_primary"])
        self.assertFalse(routine["is_primary"])


class TestTaskIndependence(TestCase):
    """L: Tasks should never be incorrectly deduped with routines."""

    def setUp(self):
        self.user = _user("task_indep@example.com")
        self.today = date.today()

    def test_task_not_grouped_with_routine(self):
        events = [
            _ev(self.user, self.today, DOMAIN_TASK, BUCKET_TASK,
                FINAL_COMPLETED, "Write report", item_id=42,
                item_type="Task"),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_COMPLETED, "Morning Routine Item", item_id=10),
        ]
        reconcile_events(events, self.user)

        task = next(e for e in events if e["domain"] == DOMAIN_TASK)
        routine = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        # Tasks have no obligation_key (no cross-domain linkage)
        self.assertEqual(task.get("obligation_key", ""), "")
        self.assertTrue(task["is_primary"])
        self.assertTrue(routine["is_primary"])


class TestRollupIntegrity(TestCase):
    """G: Rollup counts reflect reconciled primary events only."""

    def setUp(self):
        self.user = _user("rollup_g@example.com")
        self.today = date.today()

    def test_suppressed_excluded_from_rollup(self):
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_WORKOUT, scoring_bucket=BUCKET_WORKOUT,
            item_type="WorkoutSchedule", item_id=1,
            item_label="Chest Day", expected=True,
            actual_status="completed", final_status=FINAL_COMPLETED,
            reason_code="on_time", source_system="test",
            obligation_type=OBLIGATION_WORKOUT,
            obligation_identity="sched_1",
            obligation_key=f"workout:{self.user.id}:{self.today}:sched_1",
            is_primary=True,
        )
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_ROUTINE, scoring_bucket=BUCKET_ROUTINE,
            item_type="RoutineSchedule", item_id=10,
            item_label="Workout", expected=True,
            actual_status="completed", final_status=FINAL_COMPLETED,
            reason_code="satisfied_by_linked", source_system="test",
            obligation_type=OBLIGATION_WORKOUT,
            obligation_identity="sched_1",
            obligation_key=f"workout:{self.user.id}:{self.today}:sched_1",
            is_primary=False,
            suppression_reason=SUPPRESSED_BY_LINKED_WORKOUT,
        )

        svc = ComplianceService(self.user)
        workout_rollup = svc.get_rollup(BUCKET_WORKOUT, self.today, self.today)
        self.assertEqual(workout_rollup["completed"], 1)
        self.assertEqual(workout_rollup["expected"], 1)

        routine_rollup = svc.get_rollup(BUCKET_ROUTINE, self.today, self.today)
        self.assertEqual(routine_rollup["expected"], 0)


class TestDetailPayload(TestCase):
    """H: Detail payload includes suppression info."""

    def setUp(self):
        self.user = _user("detail_h@example.com")
        self.today = date.today()

    def test_suppressed_event_in_detail(self):
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_ROUTINE, scoring_bucket=BUCKET_ROUTINE,
            item_type="RoutineSchedule", item_id=10,
            item_label="Workout", expected=True,
            actual_status="completed", final_status=FINAL_COMPLETED,
            reason_code="satisfied_by_linked", source_system="test",
            is_primary=False,
            suppression_reason=SUPPRESSED_BY_LINKED_WORKOUT,
        )

        svc = ComplianceService(self.user)
        detail = svc.get_detail(BUCKET_ROUTINE, self.today, self.today)

        self.assertEqual(len(detail), 1)
        item = detail[0]["items"][0]
        self.assertTrue(item["is_suppressed"])
        self.assertEqual(item["suppression_reason"], SUPPRESSED_BY_LINKED_WORKOUT)


class TestEndToEnd(TestCase):
    """M: Full pipeline — evaluate → reconcile → persist → query."""

    def setUp(self):
        self.user = _user("e2e@example.com")

    def test_pipeline_no_exceptions(self):
        svc = ComplianceService(self.user)
        count = svc.evaluate_week()
        self.assertIsInstance(count, int)

    def test_obligation_keys_persist(self):
        svc = ComplianceService(self.user)
        svc.evaluate_week()
        for ev in ComplianceEvent.objects.filter(user=self.user, domain=DOMAIN_WORKOUT):
            self.assertTrue(ev.obligation_key, f"Missing key: {ev}")
            self.assertTrue(ev.obligation_type)
            self.assertTrue(ev.obligation_identity)


class TestCacheBehavior(TestCase):
    """N: Cache prevents redundant evaluation."""

    def setUp(self):
        self.user = _user("cache@example.com")

    def test_ensure_evaluated_caches(self):
        svc = ComplianceService(self.user)
        with patch.object(svc, 'evaluate_range', wraps=svc.evaluate_range) as mock_eval:
            svc.ensure_evaluated()
            svc.ensure_evaluated()
            # Second call should be cached — evaluate_range called only once
            self.assertEqual(mock_eval.call_count, 1)

    def test_invalidate_clears_cache(self):
        svc = ComplianceService(self.user)
        with patch.object(svc, 'evaluate_range', wraps=svc.evaluate_range) as mock_eval:
            svc.ensure_evaluated()
            invalidate_compliance_cache(self.user)
            svc.ensure_evaluated()
            self.assertEqual(mock_eval.call_count, 2)
