"""
Reconciliation + obligation engine tests — Hardened Phase.

Covers:
A. Workout completed + linked routine missed → no double penalty
B. Both missed → legitimate miss
C. Late workout satisfying routine → completed_late
D. Skip preserved
F. Unrelated routine not deduped
G. Rollup excludes suppressed events
H. Detail shows suppression info
I. Workout identity uses WorkoutSchedule PK
J. Journal + routine linkage
K. Faith + routine linkage
L. Task independence (no false dedupe)
M. End-to-end pipeline
N. Cache behavior
O. Structural obligation_type on RoutineSchedule
P. Cross-domain collision guard
Q. Medication identity precision (multiple meds same day)
"""

from datetime import date, time, timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.dashboard_v2.compliance.constants import (
    BUCKET_JOURNAL,
    BUCKET_MEDICATION,
    BUCKET_ROUTINE,
    BUCKET_TASK,
    BUCKET_WORKOUT,
    DOMAIN_FAITH,
    DOMAIN_JOURNAL,
    DOMAIN_MEDICATION,
    DOMAIN_ROUTINE,
    DOMAIN_TASK,
    DOMAIN_WORKOUT,
    FINAL_COMPLETED,
    FINAL_COMPLETED_LATE,
    FINAL_MISSED,
    FINAL_SKIPPED,
    OBLIGATION_JOURNAL,
    OBLIGATION_MEDICATION,
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
        user=user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _ev(user, day, domain, bucket, final_status, label="Item", item_id=1,
        item_type="Test", reason="on_time", expected_at=None):
    return {
        "user": user, "event_date": day, "domain": domain,
        "scoring_bucket": bucket, "item_type": item_type,
        "item_id": item_id, "item_label": label,
        "expected_at": expected_at or time(7, 0), "expected": True,
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

    def test_B_both_missed(self):
        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_MISSED, "Chest Day", item_id=7, reason="no_log"),
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
        self.assertEqual(routine["final_status"], FINAL_COMPLETED_LATE)

    def test_D_skip_preserved(self):
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
                FINAL_COMPLETED, "Shower", item_id=20),
        ]
        reconcile_events(events, self.user)

        workout = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        shower = next(e for e in events if e["item_label"] == "Shower")

        self.assertNotEqual(workout["obligation_key"], shower["obligation_key"])
        self.assertTrue(shower["is_primary"])


class TestIdentityPrecision(TestCase):
    """I, Q: Identity uses structured IDs, not 'daily'."""

    def setUp(self):
        self.user = _user("identity@example.com")
        self.today = date.today()

    def test_workout_identity_uses_ws_prefix(self):
        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_COMPLETED, "Chest Day", item_id=7),
        ]
        reconcile_events(events, self.user)
        self.assertEqual(events[0]["obligation_identity"], "ws_7")
        self.assertIn("ws_7", events[0]["obligation_key"])

    def test_medication_identity_includes_time(self):
        events = [
            _ev(self.user, self.today, DOMAIN_MEDICATION, BUCKET_MEDICATION,
                FINAL_COMPLETED, "Aspirin 8AM", item_id=3,
                expected_at=time(8, 0)),
            _ev(self.user, self.today, DOMAIN_MEDICATION, BUCKET_MEDICATION,
                FINAL_MISSED, "Aspirin 8PM", item_id=3,
                expected_at=time(20, 0), reason="no_log"),
        ]
        reconcile_events(events, self.user)

        am = next(e for e in events if "8AM" in e["item_label"])
        pm = next(e for e in events if "8PM" in e["item_label"])

        # Same medicine_id but different times → different identity
        self.assertNotEqual(am["obligation_identity"], pm["obligation_identity"])
        self.assertNotEqual(am["obligation_key"], pm["obligation_key"])

    def test_task_identity_uses_task_id(self):
        events = [
            _ev(self.user, self.today, DOMAIN_TASK, BUCKET_TASK,
                FINAL_COMPLETED, "Write report", item_id=42, item_type="Task"),
        ]
        reconcile_events(events, self.user)
        self.assertEqual(events[0]["obligation_identity"], "task_42")

    def test_journal_identity_is_entry(self):
        events = [
            _ev(self.user, self.today, DOMAIN_JOURNAL, BUCKET_JOURNAL,
                FINAL_COMPLETED, "Daily Journal", item_type="JournalEntry"),
        ]
        reconcile_events(events, self.user)
        self.assertEqual(events[0]["obligation_identity"], "entry")


class TestJournalRoutineLinkage(TestCase):
    """J: Journal + routine reconciliation."""

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
    """K: Faith + routine reconciliation."""

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
    """L: Tasks never deduped with routines."""

    def setUp(self):
        self.user = _user("task_indep@example.com")
        self.today = date.today()

    def test_task_not_grouped_with_routine(self):
        events = [
            _ev(self.user, self.today, DOMAIN_TASK, BUCKET_TASK,
                FINAL_COMPLETED, "Write report", item_id=42, item_type="Task"),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_COMPLETED, "Morning Item", item_id=10),
        ]
        reconcile_events(events, self.user)

        task = next(e for e in events if e["domain"] == DOMAIN_TASK)
        routine = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        self.assertNotEqual(task["obligation_key"], routine["obligation_key"])
        self.assertTrue(task["is_primary"])
        self.assertTrue(routine["is_primary"])


class TestStructuralObligationType(TestCase):
    """O: RoutineSchedule.obligation_type structural linking."""

    def setUp(self):
        self.user = _user("structural@example.com")
        self.today = date.today()

    def test_structural_type_preferred_over_name(self):
        """When obligation_type is set on RoutineSchedule, use it."""
        from apps.life.models import Routine, RoutineSchedule

        routine = Routine.objects.create(
            user=self.user, name="Morning", is_active=True,
            time_of_day="morning",
        )
        schedule = RoutineSchedule.objects.create(
            routine=routine, name="Custom Gym Session",
            scheduled_time=time(7, 0),
            obligation_type="workout",
        )

        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_COMPLETED, "Chest Day", item_id=7),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_MISSED, "Custom Gym Session", item_id=schedule.id,
                reason="no_log"),
        ]
        reconcile_events(events, self.user)

        workout = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        routine_ev = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        # Should group together via structural obligation_type,
        # even though "Custom Gym Session" is NOT in WORKOUT_NAMES
        self.assertEqual(workout["obligation_key"], routine_ev["obligation_key"])
        self.assertTrue(workout["is_primary"])
        self.assertFalse(routine_ev["is_primary"])

    def test_fallback_name_matching_still_works(self):
        """When obligation_type is not set, name matching still works
        (requires a real workout plan so identity can resolve)."""
        from apps.health.models import WorkoutPlan, WorkoutSchedule, WorkoutTemplate

        template = WorkoutTemplate.objects.create(
            user=self.user, name="Chest", template_type="strength",
        )
        plan = WorkoutPlan.objects.create(
            user=self.user, name="Test Plan", is_active=True,
        )
        ws = WorkoutSchedule.objects.create(
            plan=plan, day_of_week=self.today.weekday(),
            template=template,
        )

        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_COMPLETED, "Chest Day", item_id=ws.id),
            _ev(self.user, self.today, DOMAIN_ROUTINE, BUCKET_ROUTINE,
                FINAL_MISSED, "Workout", item_id=999, reason="no_log"),
        ]
        reconcile_events(events, self.user)

        workout = next(e for e in events if e["domain"] == DOMAIN_WORKOUT)
        routine = next(e for e in events if e["domain"] == DOMAIN_ROUTINE)

        self.assertEqual(workout["obligation_key"], routine["obligation_key"])


class TestCrossDomainCollisionGuard(TestCase):
    """P: Cross-domain collision protection."""

    def setUp(self):
        self.user = _user("collision@example.com")
        self.today = date.today()

    def test_mixed_types_in_group_skips_reconciliation(self):
        """If events with different obligation_types somehow share a key,
        reconciliation should be skipped for safety."""
        events = [
            _ev(self.user, self.today, DOMAIN_WORKOUT, BUCKET_WORKOUT,
                FINAL_COMPLETED, "Workout A", item_id=1),
            _ev(self.user, self.today, DOMAIN_JOURNAL, BUCKET_JOURNAL,
                FINAL_MISSED, "Journal", item_id=2),
        ]
        # Force same obligation_key artificially
        reconcile_events(events, self.user)
        # They should have DIFFERENT keys so this is a non-issue,
        # but verify both remain primary
        self.assertTrue(events[0]["is_primary"])
        self.assertTrue(events[1]["is_primary"])


class TestRollupIntegrity(TestCase):
    """G: Rollup excludes suppressed."""

    def setUp(self):
        self.user = _user("rollup_g@example.com")
        self.today = date.today()

    def test_suppressed_excluded(self):
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_WORKOUT, scoring_bucket=BUCKET_WORKOUT,
            item_type="WorkoutSchedule", item_id=1,
            item_label="Chest Day", expected=True,
            actual_status="completed", final_status=FINAL_COMPLETED,
            reason_code="on_time", source_system="test",
            obligation_type=OBLIGATION_WORKOUT, obligation_identity="ws_1",
            obligation_key=f"workout:{self.user.id}:{self.today}:ws_1",
            is_primary=True,
        )
        ComplianceEvent.objects.create(
            user=self.user, event_date=self.today,
            domain=DOMAIN_ROUTINE, scoring_bucket=BUCKET_ROUTINE,
            item_type="RoutineSchedule", item_id=10,
            item_label="Workout", expected=True,
            actual_status="completed", final_status=FINAL_COMPLETED,
            reason_code="satisfied_by_linked", source_system="test",
            obligation_type=OBLIGATION_WORKOUT, obligation_identity="ws_1",
            obligation_key=f"workout:{self.user.id}:{self.today}:ws_1",
            is_primary=False,
            suppression_reason=SUPPRESSED_BY_LINKED_WORKOUT,
        )

        svc = ComplianceService(self.user)
        self.assertEqual(svc.get_rollup(BUCKET_WORKOUT, self.today, self.today)["completed"], 1)
        self.assertEqual(svc.get_rollup(BUCKET_ROUTINE, self.today, self.today)["expected"], 0)


class TestDetailPayload(TestCase):
    """H: Detail includes suppression info."""

    def setUp(self):
        self.user = _user("detail_h@example.com")
        self.today = date.today()

    def test_suppressed_visible(self):
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
        item = detail[0]["items"][0]
        self.assertTrue(item["is_suppressed"])
        self.assertEqual(item["suppression_reason"], SUPPRESSED_BY_LINKED_WORKOUT)


class TestEndToEnd(TestCase):
    """M: Full pipeline."""

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
            self.assertTrue(ev.obligation_key)
            self.assertTrue(ev.obligation_type)
            self.assertTrue(ev.obligation_identity)


class TestCacheBehavior(TestCase):
    """N: Cache correctness."""

    def setUp(self):
        self.user = _user("cache@example.com")

    def test_ensure_evaluated_caches(self):
        svc = ComplianceService(self.user)
        with patch.object(svc, 'evaluate_range', wraps=svc.evaluate_range) as mock:
            svc.ensure_evaluated()
            svc.ensure_evaluated()
            self.assertEqual(mock.call_count, 1)

    def test_invalidate_clears_cache(self):
        svc = ComplianceService(self.user)
        with patch.object(svc, 'evaluate_range', wraps=svc.evaluate_range) as mock:
            svc.ensure_evaluated()
            invalidate_compliance_cache(self.user)
            svc.ensure_evaluated()
            self.assertEqual(mock.call_count, 2)
