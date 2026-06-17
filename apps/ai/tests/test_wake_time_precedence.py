"""Wake-time source precedence (F1, 2026-06-16).

Sleep wake_time (real biometric) must beat routine performed_at (marked/click
time, can equal scheduled). Beth must never present scheduled/routine-marked
time as actual when sleep data exists; honest uncertainty when neither exists.
"""
from datetime import time as dt_time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai import deterministic_router as dr

User = get_user_model()


class WakeTimePrecedence(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(email="wt@test.com", password="x" * 20)
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        from apps.core.utils import get_user_today
        self.today = get_user_today(self.user)

    def _wake_routine(self, performed_hour=5, performed_min=0):
        from apps.life.models import Routine, RoutineSchedule, RoutineLog
        r = Routine.objects.create(user=self.user, name="Morning")
        sched = RoutineSchedule.objects.create(
            routine=r, name="Wake Up", scheduled_time=dt_time(5, 0))
        ts = timezone.now().replace(
            hour=performed_hour, minute=performed_min, second=0, microsecond=0)
        RoutineLog.objects.create(
            user=self.user, schedule=sched, scheduled_date=self.today,
            log_status=RoutineLog.STATUS_COMPLETED, completed_at=ts, performed_at=ts)

    def _sleep(self, wake_hour=5, wake_min=50):
        from apps.health.models import SleepEntry
        wake = timezone.now().replace(
            hour=wake_hour, minute=wake_min, second=0, microsecond=0)
        SleepEntry.objects.create(
            user=self.user, sleep_date=self.today,
            bedtime=wake - timedelta(hours=7), wake_time=wake)

    def test_sleep_beats_routine_marked_time(self):
        # Routine marked at scheduled 5:00; sleep shows real 5:50 → sleep wins.
        self._wake_routine(5, 0)
        self._sleep(5, 50)
        resp = dr._handle_actual_wake_query(self.user)
        print(f"\n>>>F1 sleep-vs-routine: {resp}\n<<<")
        self.assertIn("5:50", resp)
        self.assertNotIn("5:00 AM, but based on your sleep/wake data you actually "
                         "woke around 5:00", resp)
        self.assertIn("sleep", resp.lower())
        self.assertIn("scheduled to wake at 5:00", resp)  # scheduled shown separately

    def test_routine_fallback_when_no_sleep(self):
        self._wake_routine(5, 50)  # no sleep entry; routine performed 5:50
        resp = dr._handle_actual_wake_query(self.user)
        self.assertIn("5:50", resp)
        self.assertIn("routine", resp.lower())

    def test_sleep_only(self):
        self._sleep(6, 5)
        resp = dr._handle_actual_wake_query(self.user)
        self.assertIn("6:05", resp)
        self.assertIn("sleep", resp.lower())

    def test_honest_uncertainty_when_neither(self):
        resp = dr._handle_actual_wake_query(self.user)
        self.assertIn("don't have a confirmed", resp.lower())
        self.assertNotIn("5:00", resp)  # never substitutes scheduled

    def test_routes_deterministically(self):
        self._wake_routine(5, 0)
        self._sleep(5, 50)
        res = dr.classify_and_route("what time did i wake up today?", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "actual_wake_time")
        self.assertIn("5:50", res.response)
