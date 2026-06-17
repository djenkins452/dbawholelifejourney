"""Sleep intent routing (F4, 2026-06-17).

Status questions → metrics. Coaching/action questions ("how can I improve my
sleep") → coaching, NOT the same metrics. Routing keys on intent, not just the
"sleep" keyword.
"""
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai import deterministic_router as dr

User = get_user_model()


class SleepIntentMatchers(SimpleTestCase):
    def test_coaching_detected(self):
        for q in (
            "how can i improve my sleep",
            "what is the best way to improve my sleep",
            "what actions can i take to improve my sleep",
            "give me tips to sleep better",
            "what should i do to fix my sleep",
        ):
            self.assertTrue(dr._is_sleep_coaching_request(q), q)
            self.assertTrue(dr._match_sleep_coaching_query(q), q)
            # Coaching must be EXCLUDED from the status matcher.
            self.assertFalse(dr._match_sleep_query(q), q)

    def test_status_still_matches(self):
        for q in (
            "what was my sleep score last night",
            "how did i sleep",
            "how is my sleep this week",
            "my sleep quality",
        ):
            self.assertFalse(dr._is_sleep_coaching_request(q), q)
            self.assertTrue(dr._match_sleep_query(q), q)
            self.assertFalse(dr._match_sleep_coaching_query(q), q)

    def test_non_sleep_not_matched(self):
        self.assertFalse(dr._is_sleep_coaching_request("how can i improve my diet"))


class SleepCoachingHandler(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(email="sc@test.com", password="x" * 20)
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_returns_deterministic_coaching_when_sleep_is_constraint(self):
        coaching = {
            "primary_constraint": "sleep",
            "insight": "Sleep is your primary limiter right now.",
            "primary_action": "Increase sleep by ~45 minutes tonight — wind down earlier.",
            "secondary_action": "Reduce screen time 30 minutes before bed.",
        }
        with patch(
            "apps.health.services.trend_analyzer.HealthTrendAnalyzer.analyze",
            return_value={"coaching": coaching},
        ):
            out = dr._handle_sleep_coaching_query(self.user, "how can i improve my sleep")
        print(f"\n>>>F4 coaching: {out}\n<<<")
        self.assertIsNotNone(out)
        self.assertIn("Increase sleep by", out)
        self.assertNotIn("hours last night", out)   # NOT status metrics

    def test_falls_through_when_sleep_not_constraint(self):
        with patch(
            "apps.health.services.trend_analyzer.HealthTrendAnalyzer.analyze",
            return_value={"coaching": {"primary_constraint": "nutrition"}},
        ):
            out = dr._handle_sleep_coaching_query(self.user, "how can i improve my sleep")
        self.assertIsNone(out)  # → LLM general sleep tips

    def test_coaching_question_does_not_route_to_status_metrics(self):
        # The core bug: coaching must not return the sleep_query status route.
        res = dr.classify_and_route("how can i improve my sleep", self.user)
        route = getattr(res, "route_name", None) if res is not None else None
        self.assertNotEqual(route, "sleep_query")
