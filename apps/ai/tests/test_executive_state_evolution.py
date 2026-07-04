# ==============================================================================
# File: apps/ai/tests/test_executive_state_evolution.py
# Description: WI-1 — EXECUTIVE STATE EVOLUTION. Today's executive picture must evolve
#   as the user reports updates; Beth must not keep reasoning from the morning state.
#   Origin: user made up two workouts, then "I won't be doing the bike ride tonight" —
#   Beth accepted the decision but failed to connect it to what was already
#   accomplished ("You've already exceeded expectations today; recovery is the
#   highest-value decision"). Decision Support now consumes today's reported
#   accomplishments (from WI-2) so the recommendation reflects them.
# ==============================================================================
from datetime import date
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.ai.chatgpt_cos import accomplishment as ac
from apps.ai.chatgpt_cos import decision_support as ds

User = get_user_model()
TODAY = date(2026, 7, 4)
_TODAY = "apps.core.utils.get_user_today"


class ExecutiveStateEvolutionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ese@test.com", password="x")
        cache.clear()

    def test_bike_ride_is_recognized_as_a_decision(self):
        sig = ds.detect_decision("I won't be doing the bike ride tonight")
        self.assertIsNotNone(sig)
        self.assertEqual(sig.kind, "abandon")
        self.assertIn("workout", sig.abandoned)     # bike ride is a workout commitment

    def test_decision_reflects_todays_accomplishments(self):
        with mock.patch(_TODAY, return_value=TODAY):
            ac.record(self.user, "made up 2 missed workouts (Wednesday, Friday)")
            out = ds.respond(self.user, "I won't be doing the bike ride tonight")
        self.assertIsNotNone(out)
        self.assertEqual(out["lane"], "decision_support")
        # The recommendation now connects the skip to what was already accomplished.
        self.assertIn("made up 2 missed workouts", out["answer"])
        low = out["answer"].lower()
        self.assertIn("already", low)
        self.assertIn("ahead of plan", low)
        self.assertIn("recovery", low)

    def test_without_accomplishments_no_ahead_of_plan_framing(self):
        # Protect existing behavior: no reported accomplishment → normal endorse.
        with mock.patch(_TODAY, return_value=TODAY):
            out = ds.respond(self.user, "I won't be doing the bike ride tonight")
        self.assertNotIn("ahead of plan", out["answer"].lower())

    def test_full_production_sequence(self):
        # Report the accomplishment, THEN voice the skip — the skip reflects it.
        from apps.ai.models import AssistantConversation
        from datetime import datetime, timezone as tz
        conv = AssistantConversation.objects.create(user=self.user)
        from apps.ai.chatgpt_cos.lanes import route_message
        with mock.patch(_TODAY, return_value=TODAY), \
                mock.patch("apps.core.utils.get_user_now",
                           return_value=datetime(2026, 7, 4, 18, 0, tzinfo=tz.utc)):
            r1 = route_message(self.user,
                               "I made up my workouts from Wednesday and Friday", conv)
            self.assertEqual(r1["lane"], "accomplishment")
            r2 = route_message(self.user, "I won't be doing the bike ride tonight", conv)
        self.assertEqual(r2["lane"], "decision_support")
        self.assertIn("made up 2 missed workouts", r2["answer"])
