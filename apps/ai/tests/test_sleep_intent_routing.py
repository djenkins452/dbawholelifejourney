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


class SleepIntentPrecedence(SimpleTestCase):
    """Intent-CATEGORY recognition (not today's literal phrases) + precedence.

    Each message must classify to exactly ONE of status / coaching / diagnostic,
    using paraphrases NOT used in the original examples — proving the pattern
    recognizes the intent category, not memorized wording.
    """

    def _intent(self, q):
        # Exactly-one-of classification, mirroring route precedence:
        # coaching → diagnostic → status.
        if dr._is_sleep_coaching_request(q):
            return "coaching"
        if dr._is_sleep_diagnostic_request(q):
            return "diagnostic"
        if dr._match_sleep_query(q):
            return "status"
        return "none"

    def test_diagnostic_category_paraphrases(self):
        for q in (
            "why don't i sleep well",
            "what's behind my poor sleep",
            "what's limiting my sleep",
            "root cause of my bad sleep",
            "why can't i sleep through the night",
            "what is causing my sleep problems",
        ):
            self.assertEqual(self._intent(q), "diagnostic", q)

    def test_coaching_category_paraphrases(self):
        for q in (
            "any tips for better sleep",
            "ways to sleep better",
            "what should i change about my sleep",
            "recommend something for my sleep",
        ):
            self.assertEqual(self._intent(q), "coaching", q)

    def test_status_category_paraphrases(self):
        for q in (
            "how did i sleep last night",
            "what's my sleep quality",
            "how is my sleep this week",
        ):
            self.assertEqual(self._intent(q), "status", q)

    def test_precedence_action_verb_beats_diagnostic(self):
        # Contains BOTH a cause cue ("why") and an action verb ("fix"/"how do i")
        # → coaching wins (actionable over explanatory).
        q = "why is my sleep bad and how do i fix it"
        self.assertEqual(self._intent(q), "coaching", q)

    def test_each_intent_mutually_exclusive_in_matchers(self):
        diag = "why is my sleep holding me back"
        coach = "how can i improve my sleep"
        stat = "how did i sleep"
        # diagnostic excluded from coaching+status matchers
        self.assertTrue(dr._is_sleep_diagnostic_request(diag))
        self.assertFalse(dr._is_sleep_coaching_request(diag))
        self.assertFalse(dr._match_sleep_query(diag))
        # coaching excluded from status; diagnostic excludes coaching
        self.assertFalse(dr._match_sleep_query(coach))
        self.assertFalse(dr._is_sleep_diagnostic_request(coach))
        # status excluded from coaching+diagnostic
        self.assertFalse(dr._is_sleep_coaching_request(stat))
        self.assertFalse(dr._is_sleep_diagnostic_request(stat))


class SleepDiagnosticHandler(TestCase):
    def setUp(self):
        from apps.users.models import TermsAcceptance
        self.user = User.objects.create_user(email="sd@test.com", password="x" * 20)
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_grounded_causes_no_speculation(self):
        analyze = {
            "rolling_7d": {"sleep_hours": 5.6},
            "weaknesses": ["Inconsistent sleep duration (±1.4h variance)"],
            "trends": {"sleep": "declining"},
        }
        with patch(
            "apps.health.services.trend_analyzer.HealthTrendAnalyzer.analyze",
            return_value=analyze,
        ), patch(
            "apps.core.ai_state.state_engine.get_module_state",
            return_value={"sleep_quality_avg_7d": 94},
        ):
            out = dr._handle_sleep_diagnostic_query(
                self.user, "why is my sleep holding me back")
        print(f"\n>>>DIAG: {out}\n<<<")
        self.assertIn("duration", out.lower())
        self.assertIn("5.6", out)
        self.assertIn("7-hour target", out)
        self.assertIn("quantity", out.lower())            # quality-vs-quantity, grounded
        self.assertNotIn("hours last night", out)          # NOT status metrics
        for bad in ("stress", "anxious", "probably", "might be"):
            self.assertNotIn(bad, out.lower())             # no speculative psychology

    def test_no_data_is_honest(self):
        with patch(
            "apps.health.services.trend_analyzer.HealthTrendAnalyzer.analyze",
            return_value={"rolling_7d": {}},
        ):
            out = dr._handle_sleep_diagnostic_query(
                self.user, "why is my sleep holding me back")
        self.assertIn("don't have enough recent sleep data", out.lower())

    def test_diagnostic_routes_not_to_status(self):
        res = dr.classify_and_route("why is my sleep holding me back", self.user)
        self.assertIsNotNone(res)
        self.assertEqual(res.route_name, "sleep_diagnostic_query")
        self.assertNotIn("hours last night", (res.response or "").lower())
