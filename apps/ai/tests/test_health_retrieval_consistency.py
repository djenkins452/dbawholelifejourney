"""Health retrieval consistency — Phase 1 (2026-06-19).

No-abstain + latest/today correctness for trust-critical health retrieval:
factual handlers must return a GROUNDED answer or an honest no-data/stale
statement — never None (which drops the question to the LLM, where the rolling
7-day average lives and gets parroted as latest/today). And "latest/today"
questions must never be answered with an average.
"""
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai import deterministic_router as dr

User = get_user_model()


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class NutritionNoAbstain(TestCase):
    """calories/protein today → today value or 'nothing logged', never rolling avg."""

    def setUp(self):
        self.user = _user("nutq@test.com")

    def _poison(self, **kw):
        # The exact failure shape: today=0 but snapshot can't confirm today's
        # count, while a non-zero rolling 7-day average is present.
        d = {'daily_calories': 0.0, 'daily_protein_g': 0.0,
             'calorie_target': 2000, 'protein_target': 40,
             'food_entries_today': None, 'food_entries_7d': 5,
             'rolling_7d_calories_avg': 1355, 'rolling_7d_protein_avg': 120,
             'macro_compliance_score': None}
        d.update(kw)
        return d

    def test_calories_today_is_zero_not_rolling_average(self):
        with patch('apps.core.ai_state.state_freshness.ensure_fresh'), \
             patch('apps.core.ai_state.state_engine.get_module_state',
                   return_value=self._poison()):
            out = dr._handle_nutrition_query(
                self.user, "how many calories have i had today")
        print(f"\n>>>CAL: {out}\n<<<")
        self.assertIsNotNone(out)                 # NO-ABSTAIN (test #7)
        self.assertNotIn("1355", out)             # never the rolling average
        self.assertIn("today", out.lower())
        self.assertTrue("0" in out or "nothing" in out.lower())

    def test_protein_today_is_zero_not_rolling_average(self):
        with patch('apps.core.ai_state.state_freshness.ensure_fresh'), \
             patch('apps.core.ai_state.state_engine.get_module_state',
                   return_value=self._poison()):
            out = dr._handle_nutrition_query(self.user, "how much protein today")
        self.assertIsNotNone(out)
        self.assertNotIn("120", out)
        self.assertTrue("0g" in out or "nothing" in out.lower())

    def test_calories_today_matcher_fires(self):
        # The reported gap: "how many calories have I had today?" fell through to
        # the LLM (food-estimate heuristic tripped on "have I had").
        for q in ("how many calories have i had today",
                  "how many calories today", "calories so far today",
                  "how much protein today", "calories right now"):
            self.assertTrue(dr._match_nutrition_query(q), q)

    def test_factual_today_never_returns_none_even_with_empty_state(self):
        with patch('apps.core.ai_state.state_freshness.ensure_fresh'), \
             patch('apps.core.ai_state.state_engine.get_module_state',
                   return_value={'daily_calories': None, 'food_entries_7d': 0}):
            out = dr._handle_nutrition_query(self.user, "calories today")
        self.assertIsNotNone(out)                 # honest, not abstain


class GlucoseLatest(TestCase):
    def setUp(self):
        self.user = _user("gluq@test.com")

    def _g(self, value, mins_ago):
        from apps.health.models import GlucoseEntry
        GlucoseEntry.objects.create(
            user=self.user, value=value, unit="mg/dL",
            recorded_at=timezone.now() - timedelta(minutes=mins_ago))

    def test_glucose_right_now_is_latest_not_average(self):
        self._g(98, 30)                            # latest
        for i in range(1, 8):                       # older, higher → pull avg up
            self._g(140, 60 * 24 * i)
        res = dr.classify_and_route("what is my glucose right now", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "glucose_latest_query")
        self.assertIn("98", res.response)
        self.assertNotIn("140", res.response)      # not an older/avg value

    def test_last_glucose_returns_latest_with_time(self):
        self._g(98, 30)
        res = dr.classify_and_route(
            "when was my last glucose reading", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "glucose_latest_query")
        self.assertIn("98", res.response)

    def test_explicit_7day_average_still_returns_summary(self):
        for i in range(20):
            self._g(119, 0)  # all 119 → avg 119
        res = dr.classify_and_route(
            "what is my 7 day glucose average", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "glucose_query")   # summary, by design
        self.assertIn("119", res.response)


class SleepLastNight(TestCase):
    def setUp(self):
        self.user = _user("slpq@test.com")

    def test_last_night_via_live_when_snapshot_missing(self):
        from apps.health.models import SleepEntry
        from apps.core.utils import get_user_today
        SleepEntry.objects.create(
            user=self.user, sleep_date=get_user_today(self.user),
            total_duration_minutes=402, quality_score=90,
            bedtime=timezone.now() - timedelta(hours=8), wake_time=timezone.now())
        health = {'sleep_avg_duration_7d': 378, 'sleep_trend': 'declining',
                  'sleep_last_night_hours': None, 'sleep_last_night_quality': None}
        with patch('apps.ai.cognitive_mode.health_truth.ensure_health_fresh'), \
             patch('apps.core.ai_state.state_engine.get_module_state',
                   return_value=health):
            out = dr._handle_sleep_query(self.user, "how did i sleep last night")
        print(f"\n>>>SLEEP: {out}\n<<<")
        self.assertIsNotNone(out)
        self.assertIn("6.7", out)                  # 402 min = 6.7h last night
        self.assertIn("90", out)                   # quality
        self.assertNotIn("don't have last night", out.lower())  # not avg-fallback

    def test_no_sleep_is_honest_not_none(self):
        health = {'sleep_avg_duration_7d': None, 'sleep_last_night_hours': None}
        with patch('apps.ai.cognitive_mode.health_truth.ensure_health_fresh'), \
             patch('apps.core.ai_state.state_engine.get_module_state',
                   return_value=health):
            out = dr._handle_sleep_query(self.user, "how did i sleep last night")
        self.assertIsNotNone(out)
        self.assertIn("don't see any sleep", out.lower())


class WorkoutLast(TestCase):
    def setUp(self):
        self.user = _user("wkq@test.com")

    def test_last_workout_via_live_when_snapshot_missing(self):
        from apps.health.models import WorkoutSession
        from apps.core.utils import get_user_today
        WorkoutSession.objects.create(
            user=self.user, name="Adjusted Upper Body",
            date=get_user_today(self.user), completed_at=timezone.now())
        with patch('apps.core.ai_state.state_engine.get_module_state',
                   return_value={}):
            out = dr._handle_last_workout_query(self.user)
        print(f"\n>>>WORKOUT: {out}\n<<<")
        self.assertIsNotNone(out)                  # NO-ABSTAIN
        self.assertIn("Adjusted Upper Body", out)  # structured, named
        self.assertNotIn("got up early", out)      # no narrative contamination

    def test_no_workout_is_honest_not_none(self):
        with patch('apps.core.ai_state.state_engine.get_module_state',
                   return_value={}):
            out = dr._handle_last_workout_query(self.user)
        self.assertIsNotNone(out)
        self.assertIn("don't see any completed workouts", out.lower())
