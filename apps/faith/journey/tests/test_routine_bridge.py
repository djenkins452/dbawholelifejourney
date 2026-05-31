"""Journey ⇄ Routine completion bridge.

The trust-break this guards against:

  User completes today's Bible reading inside the Journey module
  ("Walking With God Through Scripture"), and the dashboard's "Do This
  Next" / Daily Rhythm continues to show "Bible Reading" as still open
  because the legacy MarkDayCompleteView pattern (auto_complete_routine_
  schedules) was never wired into the new journey service.

When `mark_day_complete()` runs, the Bible Reading RoutineSchedule for
today must get a matching RoutineLog so the canonical execution path
(_apply_routine_faith_bridge in execution_truth_engine) flips
faith['bible_reading_completed'] to True.

Architectural intent:
  Faith completion → canonical daily routine completion
  (NOT: dashboard polling faith state every render)
"""

from datetime import time as dtime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.faith.journey.models import (
    JourneyArc, JourneyDay, JourneyPath, UserJourney,
)
from apps.faith.journey.services import mark_day_complete
from apps.life.models import Routine, RoutineLog, RoutineSchedule


User = get_user_model()


def _make_user(email="routine-bridge@test.com"):
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _make_bible_routine(user, name="Bible Reading", activity_type=None):
    routine = Routine.objects.create(user=user, name="Morning Routine")
    return RoutineSchedule.objects.create(
        routine=routine,
        name=name,
        scheduled_time=dtime(7, 0),
        days_of_week="0,1,2,3,4,5,6",
        is_active=True,
        activity_type=activity_type or '',
    )


class JourneyRoutineBridgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("load_journey_path", "walking_with_god")
        cls.path = JourneyPath.objects.get(slug="walking_with_god")
        cls.arc = JourneyArc.objects.get(slug="creation_to_egypt")
        cls.day1 = JourneyDay.objects.get(arc=cls.arc, day_number=1)
        cls.day2 = JourneyDay.objects.get(arc=cls.arc, day_number=2)

    def setUp(self):
        self.user = _make_user()
        self.journey = UserJourney.objects.create(
            user=self.user,
            journey_path=self.path,
            current_arc=self.arc,
            current_day_number=1,
            journey_status="active",
            preferred_difficulty="standard",
        )

    # ── PROOF 1: completing a journey day creates the RoutineLog ─────
    def test_complete_journey_day_creates_bible_routine_log(self):
        sched = _make_bible_routine(self.user)
        self.assertFalse(
            RoutineLog.objects.filter(schedule=sched).exists(),
            "precondition: no RoutineLog yet",
        )

        mark_day_complete(self.journey, self.day1)

        log = RoutineLog.objects.filter(schedule=sched).first()
        self.assertIsNotNone(
            log, "FAIL: journey completion did not create a RoutineLog",
        )
        self.assertEqual(log.completion_source, 'bible')
        self.assertIn(
            log.log_status, ('completed', 'completed_late'),
            f"Unexpected status: {log.log_status}",
        )

    # ── PROOF 2: idempotency — second completion does NOT duplicate ──
    def test_repeat_completion_is_idempotent(self):
        sched = _make_bible_routine(self.user)
        mark_day_complete(self.journey, self.day1)
        count_after_first = RoutineLog.objects.filter(schedule=sched).count()
        self.assertEqual(count_after_first, 1)

        # Simulate a second completion attempt on a different day record.
        mark_day_complete(self.journey, self.day2)
        count_after_second = RoutineLog.objects.filter(schedule=sched).count()
        # Same calendar day → still a single log for today.
        self.assertEqual(
            count_after_second, 1,
            "FAIL: second completion should not duplicate today's log",
        )

    # ── PROOF 3: manual dashboard complete first → journey is a no-op ─
    def test_manual_dashboard_complete_before_journey_wins(self):
        sched = _make_bible_routine(self.user)
        # Simulate the dashboard manual-complete path.
        from apps.core.utils import get_user_today
        today = get_user_today(self.user)
        manual_log = RoutineLog.objects.create(
            user=self.user, schedule=sched, scheduled_date=today,
            log_status='completed', completion_source='manual',
        )

        mark_day_complete(self.journey, self.day1)

        # No duplicate log; manual provenance preserved.
        logs = list(RoutineLog.objects.filter(schedule=sched, scheduled_date=today))
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].pk, manual_log.pk)
        self.assertEqual(logs[0].completion_source, 'manual')

    # ── PROOF 4: works regardless of journey path / no hardcoded name ─
    def test_bridge_matches_via_name_fallback_on_any_path(self):
        """Confirms domain-agnostic matching — no hardcoded plan name.
        Routine schedule with no activity_type must still match via
        the name__icontains='bible' fallback."""
        sched = _make_bible_routine(
            self.user, name="My Bible Reading Habit", activity_type='',
        )
        mark_day_complete(self.journey, self.day1)
        self.assertTrue(
            RoutineLog.objects.filter(schedule=sched).exists(),
            "FAIL: name fallback must match 'bible' in any routine name",
        )

    # ── PROOF 5: activity_type-tagged schedules match preferentially ──
    def test_bridge_matches_via_activity_type(self):
        sched = _make_bible_routine(
            self.user, name="Daily Devotion", activity_type='bible',
        )
        mark_day_complete(self.journey, self.day1)
        self.assertTrue(
            RoutineLog.objects.filter(schedule=sched).exists(),
            "FAIL: activity_type='bible' should match even with non-'bible' name",
        )

    # ── PROOF 6: dashboard immediately reads completion ──────────────
    def test_journey_completion_propagates_to_execution_truth_bridge(self):
        """The canonical execution path (_apply_routine_faith_bridge in
        execution_truth_engine) must report bible_reading_completed=True
        immediately after journey completion — no dashboard reload, no
        cache warmup needed."""
        from apps.core.execution.execution_truth_engine import (
            get_execution_truth,
        )
        _make_bible_routine(self.user)

        mark_day_complete(self.journey, self.day1)

        truth = get_execution_truth(self.user)
        faith = truth.get('domains', {}).get('faith', {})
        self.assertTrue(
            faith.get('bible_reading_completed'),
            "FAIL: bible_reading_completed should be True after journey "
            "completion. truth.domains.faith=%s" % faith,
        )

    # ── PROOF 7: failure of the bridge does not block the user ──────
    def test_bridge_failure_does_not_break_journey_completion(self):
        """Trust contract — if the routine bridge raises (e.g. routine
        helper import error), the user's journey completion still
        succeeds. The warning is logged for observability."""
        from unittest.mock import patch
        sched = _make_bible_routine(self.user)

        with patch(
            'apps.life.services.routine_helpers.auto_complete_routine_schedules',
            side_effect=RuntimeError("simulated"),
        ):
            progress = mark_day_complete(self.journey, self.day1)

        # Journey progress still committed.
        self.assertTrue(progress.is_completed)
        # Routine log NOT created (because the call raised).
        self.assertFalse(
            RoutineLog.objects.filter(schedule=sched).exists(),
        )
