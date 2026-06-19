"""Executive-lens chat routing — Phase 1 (2026-06-18).

Strategic / executive-lens questions are answered from the ONE executive
reasoning layer the dashboard uses (build_executive_summary), not scattered
across the decision engine / health-analyze / check-in / LLM by wording.
Standalone risk/fix-first stay on the decision engine (Phase 1 boundary);
execution questions stay on the execution / Today-Engine path.
"""
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai import deterministic_router as dr

User = get_user_model()

_ES = {
    "trajectory": "mixed",
    "going_well": [{"title": "Bible reading streak: 15 days"},
                   {"title": "Weight down 12.7 lb"}],
    "biggest_win": {"domain": "weight", "title": "Weight down 12.7 lb",
                    "message": "Down 12.7 lb since you started tracking."},
    "biggest_improvement": {"domain": "medication",
                            "message": "Medications 100% this week."},
    "biggest_decline": {"domain": "sleep",
                        "message": "Sleep is trending down (6.7h, 43/100)."},
    "most_important_trend": {"domain": "weight", "message": "Weight down 12.7 lb."},
    "biggest_opportunity": None,
    "biggest_risk": {"title": "Med risk", "message": "A medication risk."},
}


class ExecutiveMatcher(SimpleTestCase):
    def test_matches_executive_lenses(self):
        for q in (
            "what is my biggest win right now",
            "what is my biggest opportunity",
            "what is my biggest improvement",
            "what is my biggest decline",
            "what is the most important trend in my life",
            "what should i protect the most right now",
            "what story do the data tell about my life",
            "how am i doing overall",
            "give me a chief of staff briefing",
            "give me an executive briefing",
            "strategic briefing please",
            "what are the most important things happening in my life",
        ):
            self.assertTrue(dr._match_executive_query(q), q)

    def test_excludes_risk_fix_and_execution(self):
        for q in (
            "what is my biggest risk right now",   # decision engine (Phase 1 boundary)
            "what should i fix first",
            "what needs my attention",
            "what should i do next",
            "am i behind",
            "check in",
            "list everything remaining today",
            "how am i doing",                       # bare → not executive
            "give me a briefing",                   # bare → check-in, not executive
            "how did i sleep",
        ):
            self.assertFalse(dr._match_executive_query(q), q)


class ExecutiveLensMapping(SimpleTestCase):
    def test_lens_routing(self):
        cases = {
            "what is my biggest win": "biggest_win",
            "biggest improvement this month": "biggest_improvement",
            "biggest decline lately": "biggest_decline",
            "biggest opportunity right now": "biggest_opportunity",
            "most important trend in my life": "most_important_trend",
            "what should i protect": "protect",
            "story do the data tell": "story",
            "how am i doing overall": "overall",
            "chief of staff briefing": "overall",
        }
        for q, lens in cases.items():
            self.assertEqual(dr._executive_lens_for(q), lens, q)


def _user(email):
    u = User.objects.create_user(email=email, password="x" * 20)
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class ExecutiveRouting(TestCase):
    def setUp(self):
        self.user = _user("exq@test.com")

    def _route(self, q):
        with patch("apps.core.cos_briefing.build_executive_summary",
                   return_value=_ES):
            return dr.classify_and_route(q, self.user)

    def test_single_lenses_route_to_executive_layer(self):
        for q, needle in (
            ("what is my biggest win right now", "Down 12.7 lb"),
            ("what is my biggest improvement", "Medications 100%"),
            ("what is my biggest decline", "Sleep is trending down"),
            ("what is the most important trend in my life", "Weight down"),
        ):
            res = self._route(q)
            self.assertEqual(res.route_name, "executive_summary_query", q)
            self.assertIn(needle, res.response, q)

    def test_overall_and_briefing_are_synthesis_not_checklist(self):
        for q in ("how am i doing overall", "give me a chief of staff briefing"):
            res = self._route(q)
            self.assertEqual(res.route_name, "executive_summary_query", q)
            self.assertIn("Win:", res.response, q)
            self.assertIn("Watch:", res.response, q)
            # NOT the daily-checklist briefing.
            self.assertNotIn("of 24", res.response)

    def test_protect_combines_win_and_threat(self):
        res = self._route("what should i protect the most right now")
        self.assertEqual(res.route_name, "executive_summary_query")
        self.assertIn("Down 12.7 lb", res.response)
        self.assertIn("Sleep is trending down", res.response)

    def test_story_is_grounded_narrative(self):
        res = self._route("what story do the data tell about my life")
        self.assertEqual(res.route_name, "executive_summary_query")
        self.assertIn("Down 12.7 lb", res.response)

    def test_honest_when_lens_has_no_signal(self):
        res = self._route("what is my biggest opportunity right now")
        self.assertEqual(res.route_name, "executive_summary_query")
        self.assertIn("don't have enough grounded", res.response.lower())

    def test_reflective_governor_still_routes_executive(self):
        # Even if the governor flags the turn REFLECTIVE, a strategic question
        # routes deterministically (carve-out, like faith/glucose).
        from apps.ai.response_governor import ResponseType
        with patch("apps.ai.response_governor.resolve_response_type",
                   return_value=ResponseType.REFLECTIVE), \
             patch("apps.core.cos_briefing.build_executive_summary",
                   return_value=_ES):
            res = dr.classify_and_route("what is my biggest win", self.user)
        self.assertEqual(res.route_name, "executive_summary_query")
        self.assertNotEqual(res.route_name, "governor_reflective")


class ExecutiveBoundaryPreserved(TestCase):
    """Standalone risk stays on the decision engine; execution unchanged."""

    def setUp(self):
        self.user = _user("exb@test.com")

    def test_standalone_risk_stays_on_decision_engine(self):
        res = dr.classify_and_route("what is my biggest risk right now", self.user)
        self.assertIsNotNone(res)
        self.assertNotEqual(res.route_name, "executive_summary_query")
        self.assertTrue((res.route_name or "").startswith("decision_query"))

    def test_fix_first_stays_on_decision_engine(self):
        res = dr.classify_and_route("what should i fix first", self.user)
        self.assertNotEqual(getattr(res, "route_name", None),
                            "executive_summary_query")

    def test_execution_questions_not_executive(self):
        for q in ("check in", "what should i do next", "am i behind",
                  "list everything remaining today"):
            res = dr.classify_and_route(q, self.user)
            route = getattr(res, "route_name", None) if res else None
            self.assertNotEqual(route, "executive_summary_query", q)
