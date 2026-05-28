"""Tests for VERIFIED AUTO-COMPLETION — deterministic completion from
verified in-app activity.

Covers:
  - The formal facade completes the matching RoutineSchedule (provenance)
    and Task for each registered activity.
  - Idempotency (second call is a no-op — first-write-wins).
  - Provenance is recorded on RoutineLog.completion_source.
  - The wake-up convenience fires on authenticated presence.
  - No completion happens for unknown / unproven activities (never infers).
"""

from datetime import time as dtime

from django.conf import settings
from django.test import TestCase

from apps.core.execution.verified_completion import (
    VERIFIED_ACTIVITIES,
    apply_verified_completion,
    on_authenticated_presence,
)
from apps.core.utils import get_user_today
from apps.life.models import Routine, RoutineSchedule, RoutineLog, Task
from apps.users.models import TermsAcceptance, User


class VerifiedCompletionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="verified@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.today = get_user_today(self.user)

    def _make_routine_schedule(self, name, activity_type=None):
        routine = Routine.objects.create(user=self.user, name=f"{name} Routine")
        return RoutineSchedule.objects.create(
            routine=routine,
            name=name,
            scheduled_time=dtime(6, 0),
            days_of_week="0,1,2,3,4,5,6",
            is_active=True,
            activity_type=activity_type,
        )

    def _make_routine_task(self, title):
        return Task.objects.create(
            user=self.user,
            title=title,
            is_routine=True,
            completion_status="pending",
            due_date=self.today,
        )

    # ── Registry sanity ──
    def test_registry_has_three_rules(self):
        self.assertIn("wake_up", VERIFIED_ACTIVITIES)
        self.assertIn("workout", VERIFIED_ACTIVITIES)
        self.assertIn("bible", VERIFIED_ACTIVITIES)
        # Each carries a provenance reason + source.
        for spec in VERIFIED_ACTIVITIES.values():
            self.assertIn("source", spec)
            self.assertIn("reason", spec)

    # ── Rule 1: Wake Up ──
    def test_wake_up_completes_schedule_with_provenance(self):
        sched = self._make_routine_schedule("Wake Up")
        result = apply_verified_completion(self.user, "wake_up")
        self.assertTrue(result["completed"])
        self.assertEqual(result["reason"], "authenticated_presence")
        log = RoutineLog.objects.get(schedule=sched, scheduled_date=self.today)
        self.assertEqual(log.completion_source, "auto")
        self.assertIn(log.log_status, ("completed", "completed_late"))

    def test_wake_up_completes_routine_task(self):
        task = self._make_routine_task("Wake Up")
        result = apply_verified_completion(self.user, "wake_up")
        self.assertTrue(result["completed"])
        task.refresh_from_db()
        self.assertEqual(task.completion_status, "completed")

    def test_on_authenticated_presence_is_wake_up(self):
        self._make_routine_schedule("Wake Up")
        result = on_authenticated_presence(self.user)
        self.assertEqual(result["activity"], "wake_up")
        self.assertTrue(result["completed"])

    # ── Rule 2: Workout ──
    def test_workout_completes_with_workout_provenance(self):
        sched = self._make_routine_schedule(
            "Morning Workout", activity_type="workout"
        )
        result = apply_verified_completion(
            self.user, "workout", source_object_id=999
        )
        self.assertTrue(result["completed"])
        self.assertEqual(result["reason"], "workout_completed")
        log = RoutineLog.objects.get(schedule=sched, scheduled_date=self.today)
        self.assertEqual(log.completion_source, "workout")
        self.assertEqual(log.source_object_id, 999)

    # ── Rule 3: Bible ──
    def test_bible_completes_with_bible_provenance(self):
        sched = self._make_routine_schedule(
            "Bible Reading", activity_type="bible"
        )
        result = apply_verified_completion(self.user, "bible")
        self.assertTrue(result["completed"])
        self.assertEqual(result["reason"], "bible_activity_completed")
        log = RoutineLog.objects.get(schedule=sched, scheduled_date=self.today)
        self.assertEqual(log.completion_source, "bible")

    # ── Idempotency ──
    def test_idempotent_second_call_is_noop(self):
        self._make_routine_schedule("Wake Up")
        first = apply_verified_completion(self.user, "wake_up")
        self.assertTrue(first["completed"])
        # Second call: first-write-wins → no new schedule completion.
        second = apply_verified_completion(self.user, "wake_up")
        # Exactly one RoutineLog exists for today.
        self.assertEqual(
            RoutineLog.objects.filter(scheduled_date=self.today).count(), 1
        )
        # Second call reports no NEW schedule completions.
        self.assertEqual(second["schedules"], [])

    # ── Safety: never infers ──
    def test_unknown_activity_does_nothing(self):
        result = apply_verified_completion(self.user, "made_up_activity")
        self.assertFalse(result["completed"])
        self.assertEqual(result["reason"], "unknown_activity")
        self.assertEqual(RoutineLog.objects.count(), 0)

    def test_no_matching_schedule_or_task_completes_nothing(self):
        # No Wake Up routine/task exists → nothing to complete, no error.
        result = apply_verified_completion(self.user, "wake_up")
        self.assertFalse(result["completed"])
        self.assertEqual(RoutineLog.objects.count(), 0)


class WakeUpDefectRegressionTests(TestCase):
    """Regression guard for the 2026-05-28 defect: wake-up was gated behind
    the day-start cache, so a single early no-op permanently disabled it for
    the rest of the day. These tests prove wake-up completes regardless of
    the cache state, and via the contract-driven completer for BOTH a
    routine_item and a task."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="wakedefect@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.today = get_user_today(self.user)

    def _wake_up_routine_schedule(self):
        routine = Routine.objects.create(user=self.user, name="Morning Routine")
        return RoutineSchedule.objects.create(
            routine=routine,
            name="Wake up",                 # lowercase 'u', as Danny has it
            scheduled_time=dtime(5, 0),
            days_of_week="0,1,2,3,4,5,6",
            is_active=True,
        )

    def test_contract_driven_completes_routine_item(self):
        """complete_wake_up finds the 'Wake up' routine item in the canonical
        execution contract and completes that exact schedule."""
        from apps.core.execution.verified_completion import complete_wake_up
        sched = self._wake_up_routine_schedule()
        result = complete_wake_up(self.user)
        self.assertTrue(result["completed"])
        self.assertIn("routine_item", result["source_types"])
        log = RoutineLog.objects.get(schedule=sched, scheduled_date=self.today)
        self.assertEqual(log.completion_source, "auto")

    def test_wake_up_completes_even_when_daystart_cache_already_set(self):
        """THE core defect: simulate an earlier CoS interaction having set
        the day-start cache. handle_day_start must STILL complete wake-up."""
        from django.core.cache import cache
        from apps.ai.executive_briefing import handle_day_start
        sched = self._wake_up_routine_schedule()

        # Simulate "already initialized today" from an earlier entry point
        # that did NOT complete wake-up.
        cache.set(f"wlj:day_start:{self.user.id}:{self.today}", True, 86400)
        self.assertFalse(
            RoutineLog.objects.filter(schedule=sched).exists()
        )

        result = handle_day_start(self.user)
        self.assertTrue(
            result["wake_completed"],
            "Wake-up must complete even when the day-start cache is set",
        )
        self.assertTrue(
            RoutineLog.objects.filter(
                schedule=sched, scheduled_date=self.today
            ).exists()
        )

    def test_idempotent_repeat_calls(self):
        from apps.core.execution.verified_completion import complete_wake_up
        sched = self._wake_up_routine_schedule()
        complete_wake_up(self.user)
        complete_wake_up(self.user)  # second call — no error, no double log
        self.assertEqual(
            RoutineLog.objects.filter(
                schedule=sched, scheduled_date=self.today
            ).count(),
            1,
        )
