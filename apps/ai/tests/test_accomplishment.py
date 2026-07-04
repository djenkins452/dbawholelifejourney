# ==============================================================================
# File: apps/ai/tests/test_accomplishment.py
# Description: WI-2 — RECOGNIZE MISSION-SIGNIFICANT ACCOMPLISHMENTS. A first-person
#   report ("I made up my workouts from Wednesday and Friday") is not a fact to look
#   up — it materially changes today's picture. Beth recognizes it, celebrates, and
#   RECORDS it as today's evidence for the rest of the reasoning to consume.
# ==============================================================================
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai.chatgpt_cos import accomplishment as ac

User = get_user_model()
TODAY = date(2026, 7, 4)
_TODAY = "apps.core.utils.get_user_today"


class AccomplishmentDetectTests(TestCase):
    def test_made_up_workouts_with_days(self):
        sig = ac.detect("I made up my workouts from Wednesday and Friday")
        self.assertIsNotNone(sig)
        self.assertEqual(sig.kind, "made_up")
        self.assertIn("2", sig.label)
        self.assertIn("Wednesday", sig.label)
        self.assertIn("Friday", sig.label)

    def test_made_up_two_missed_sessions(self):
        sig = ac.detect("I made up two missed sessions today")
        self.assertEqual(sig.kind, "made_up")
        self.assertIn("2", sig.label)

    def test_completed_workout_report(self):
        for m in ("I got my workout in", "I finished my session", "Crushed my workout today"):
            sig = ac.detect(m)
            self.assertIsNotNone(sig, m)
            self.assertEqual(sig.kind, "completed")

    def test_questions_are_not_accomplishments(self):
        for m in ("Did you see my workout?", "did I work out today", "what was my workout"):
            self.assertIsNone(ac.detect(m), m)


class AccomplishmentRecordTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ac@test.com", password="x")
        cache.clear()

    def test_answer_celebrates_and_records(self):
        with mock.patch(_TODAY, return_value=TODAY):
            out = ac.answer(self.user, "I made up my workouts from Wednesday and Friday")
            self.assertEqual(out["lane"], "accomplishment")
            self.assertIn("genuine win", out["answer"])
            self.assertIn("recovery", out["answer"].lower())
            self.assertIn("made up 2 missed workouts (Wednesday, Friday)", ac.todays(self.user))

    def test_todays_starts_empty(self):
        with mock.patch(_TODAY, return_value=TODAY):
            self.assertEqual(ac.todays(self.user), [])


class AccomplishmentRoutingTests(TestCase):
    def setUp(self):
        from apps.ai.models import AssistantConversation
        self.user = User.objects.create_user(email="acr@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)
        cache.clear()

    def test_report_routes_to_accomplishment_not_workout_history(self):
        # "made up my workouts from Wednesday and Friday" contains weekdays — it must be
        # recognized as a REPORT, not retrieved as Wednesday's workout.
        from apps.ai.chatgpt_cos.lanes import route_message
        with mock.patch(_TODAY, return_value=TODAY), \
                mock.patch("apps.core.utils.get_user_now") as gn:
            from datetime import datetime, timezone as tz
            gn.return_value = datetime(2026, 7, 4, 18, 0, tzinfo=tz.utc)
            out = route_message(self.user,
                                "I made up my workouts from Wednesday and Friday", self.conv)
        self.assertEqual(out["lane"], "accomplishment")
