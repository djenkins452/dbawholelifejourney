"""Deterministic faith-status recognition route (2026-06-16).

Trust-critical factual recognition must resolve from canonical execution truth,
never LLM synthesis, and never contradict completion history.
"""
from datetime import time as dt_time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.ai import deterministic_router as dr

User = get_user_model()


class FaithStatusMatcher(SimpleTestCase):
    def test_matches_recognition_questions(self):
        for q in (
            "do you see i've completed my bible reading recently",
            "do you see i've been reading recently",
            "how consistent have i been with bible reading",
            "how is my faith lately",
            "am i staying on track spiritually",
            "how am i doing with prayer",
        ):
            self.assertTrue(dr._is_faith_status_query(q), q)

    def test_excludes_non_faith_and_logging(self):
        for q in (
            "what do i need to work on overall",       # no faith token (S1/S4)
            "what time did i wake up",                  # S2
            "log my bible reading",                     # mutation
            "remind me to read scripture",              # reminder, not status
        ):
            self.assertFalse(dr._is_faith_status_query(q), q)


class FaithStatusHandler(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(email="fs@test.com", password="x" * 20)
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        from apps.core.utils import get_user_today
        self.today = get_user_today(self.user)

    def _complete(self, name, d):
        from apps.life.models import Routine, RoutineSchedule, RoutineLog
        routine, _ = Routine.objects.get_or_create(user=self.user, name="Daily")
        sched, _ = RoutineSchedule.objects.get_or_create(
            routine=routine, name=name, defaults={"scheduled_time": dt_time(6, 0)})
        ts = timezone.now()
        RoutineLog.objects.create(
            user=self.user, schedule=sched, scheduled_date=d,
            log_status=RoutineLog.STATUS_COMPLETED, completed_at=ts, performed_at=ts)

    def test_recognizes_recent_completion_confidently(self):
        for off in (0, 1, 2, 3):
            self._complete("Bible Reading", self.today - timedelta(days=off))
        self._complete("Prayer Time", self.today)

        resp = dr._handle_faith_status_query(
            self.user, "do you see i've completed my bible reading recently")
        self.assertIn("Yes", resp)
        self.assertIn("completed your Bible reading today", resp)
        self.assertNotIn("don't have", resp.lower())
        self.assertNotIn("visibility", resp.lower())
        # Consistency grounded in canonical dates.
        self.assertIn("last 7 days", resp)

    def test_routes_deterministically(self):
        for off in (0, 1):
            self._complete("Bible Reading", self.today - timedelta(days=off))
        res = dr.classify_and_route(
            "do you see i've completed my bible reading recently", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "faith_status")
        self.assertIn("Yes", res.response)

    def test_no_data_is_honest_not_contradictory(self):
        resp = dr._handle_faith_status_query(self.user, "how is my faith lately")
        self.assertIn("don't see any bible reading", resp.lower())
        # Honest absence — must NOT claim completion it can't verify.
        self.assertNotIn("Yes — you've completed", resp)
