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
    "most_important_trend": {"domain": "synthesis",
                             "message": "Your weight is improving — but your "
                                        "sleep is the gating constraint."},
    "biggest_opportunity": None,                  # legacy event field (unused by chat now)
    "biggest_risk": {"title": "Med risk", "message": "A medication risk."},
    # The differentiated executive layer the chat must now consume.
    "executive_lenses": {
        "biggest_win": {"domain": "weight", "message": "Down 12.7 lb."},
        "biggest_improvement": {"domain": "medication", "message": "Meds 100%."},
        "biggest_decline": {"domain": "sleep", "message": "Sleep slipping."},
        "biggest_opportunity": {"domain": "sleep", "message": "Sleep slipping."},
        "opportunity": "Your sleep is your highest-leverage fix — improving it "
                       "lifts several areas at once.",
        "most_important_trend": "Your weight is improving — but your sleep is "
                                "the gating constraint.",
        "protect": "Protect your weight and your faith consistency — the thing "
                   "quietly eroding them is your sleep.",
        "story": "On the upside: Weight down; Meds 100%; Bible streak. The "
                 "drag: Sleep slipping; 2 relationships drifting.",
        "overall": "Net: mostly positive but with real pressure — your weight "
                   "is your strongest gain, your sleep is the area to watch.",
        "chief_of_staff_briefing": "Win: Down 12.7 lb Risk: A medication risk. "
                                   "Opportunity: your sleep is your highest-"
                                   "leverage fix. Protect: your faith. "
                                   "Action: put your effort into your sleep.",
    },
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
            # 2026-06-20 reclassification — holistic / trajectory / assessment
            "how am i doing",
            "how is my life going",
            "how are things going",
            "how am i doing these days",
            "what is my trajectory",
            "what's my trajectory",
            "where am i headed",
            "am i moving in the right direction",
            "am i on the right path",
            "give me an executive assessment",
            "give me a strategic assessment",
            "assess my life",
            "give me an overall assessment",
            # 2026-06-21 cross-domain CoS coaching (the marquee question)
            "what do i need to do to continue losing 1-2 pounds per week",
            "what's the highest leverage thing i can do this week",
            "what's helping and what's hurting my weight loss",
            "what one thing should i focus on",
        ):
            self.assertTrue(dr._match_executive_query(q), q)

    def test_coaching_does_not_swallow_single_domain_coaching(self):
        # Single-domain coaching keeps its own route — NOT executive.
        for q in ("how can i improve my sleep", "how do i improve my glucose",
                  "what should i eat for more protein", "how do i sleep better"):
            self.assertFalse(dr._match_executive_query(q), q)

    def test_coaching_phrases_map_to_coaching_lens(self):
        for q in ("what do i need to do to keep losing weight",
                  "what's the highest leverage move",
                  "what's helping and what's hurting"):
            self.assertEqual(dr._executive_lens_for(q), "coaching", q)

    def test_excludes_risk_fix_and_execution(self):
        for q in (
            "what is my biggest risk right now",   # decision engine (Phase 1 boundary)
            "what should i fix first",
            "what needs my attention",
            "what should i do next",
            "am i behind",
            "check in",
            "list everything remaining today",
            "give me a briefing",                   # bare → check-in, not executive
            "how did i sleep",
        ):
            self.assertFalse(dr._match_executive_query(q), q)

    def test_domain_guard_keeps_domain_questions_off_executive(self):
        # "How am I doing on protein?" etc. must NOT route to the executive
        # layer — they belong to their domain status / execution routes.
        for q in (
            "how am i doing on protein",
            "how am i doing with my workouts",
            "how am i doing with sleep",
            "how am i doing with glucose",
            "how am i doing with nutrition",
            "how am i doing with my goals",
            "how am i doing financially",
            "how am i doing today",                 # operational time-window
            "how am i doing with my health",        # health-analyze owns this
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
            "chief of staff briefing": "briefing",      # now distinct from overall
            "give me an executive briefing": "briefing",
            "strategic briefing please": "briefing",
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

    def test_cos_coaching_renders_cross_domain(self):
        # The marquee CoS question: cross-domain coaching (helping/hurting/
        # leverage), not a single-domain answer.
        for q in ("what do i need to do to continue losing 1-2 pounds per week",
                  "what's the highest leverage thing i can do this week",
                  "what's helping and what's hurting my weight loss"):
            res = self._route(q)
            self.assertEqual(res.route_name, "executive_summary_query", q)
            r = res.response.lower()
            self.assertIn("what's working for you", r, q)   # helping
            self.assertIn("working against you", r, q)       # hurting
            self.assertIn("highest-leverage", r, q)          # leverage move
            # draws from MULTIPLE domains (win=weight + decline=sleep)
            self.assertIn("12.7", res.response, q)
            self.assertIn("sleep", r, q)

    def test_reclassified_holistic_questions_route_executive(self):
        # 2026-06-20: bare "how am i doing" + trajectory + assessment phrasings
        # now reach the executive layer (were execution / LLM before).
        for q in ("how am i doing",
                  "what is my trajectory",
                  "am i moving in the right direction",
                  "give me an executive assessment"):
            res = self._route(q)
            self.assertIsNotNone(res, q)
            self.assertEqual(res.route_name, "executive_summary_query", q)

    def test_single_lenses_route_to_executive_layer(self):
        for q, needle in (
            ("what is my biggest win right now", "Down 12.7 lb"),
            ("what is my biggest improvement", "Medications 100%"),
            ("what is my biggest decline", "Sleep is trending down"),
            ("what is the most important trend in my life", "gating constraint"),
        ):
            res = self._route(q)
            self.assertEqual(res.route_name, "executive_summary_query", q)
            self.assertIn(needle, res.response, q)

    def test_trend_is_differentiated_synthesis(self):
        res = self._route("what is the most important trend in my life")
        self.assertIn("gating constraint", res.response.lower())
        # synthesis references both a positive and the constraint.
        self.assertIn("weight", res.response.lower())
        self.assertIn("sleep", res.response.lower())

    def test_opportunity_uses_leverage_framing(self):
        res = self._route("what is my biggest opportunity right now")
        self.assertEqual(res.route_name, "executive_summary_query")
        self.assertIn("highest-leverage", res.response.lower())

    def test_protect_is_value_times_vulnerability(self):
        res = self._route("what should i protect the most right now")
        self.assertEqual(res.route_name, "executive_summary_query")
        self.assertIn("Protect", res.response)
        self.assertIn("faith", res.response.lower())     # a valuable asset
        self.assertIn("sleep", res.response.lower())     # the threat

    def test_story_references_multiple_domains(self):
        res = self._route("what story do the data tell about my life")
        self.assertEqual(res.route_name, "executive_summary_query")
        self.assertIn("upside", res.response.lower())
        n = sum(d in res.response.lower() for d in (
            "weight", "sleep", "relationship", "meds", "bible", "streak"))
        self.assertGreaterEqual(n, 3)

    def test_overall_is_net_read_not_briefing(self):
        res = self._route("how am i doing overall")
        self.assertEqual(res.route_name, "executive_summary_query")
        self.assertIn("Net:", res.response)
        self.assertNotIn("of 24", res.response)          # not the daily checklist
        brief = self._route("give me a chief of staff briefing")
        self.assertNotEqual(res.response, brief.response)  # Overall != Briefing

    def test_briefing_has_all_five_dimensions(self):
        res = self._route("give me a chief of staff briefing")
        self.assertEqual(res.route_name, "executive_summary_query")
        for dim in ("Win:", "Risk:", "Opportunity:", "Protect:", "Action:"):
            self.assertIn(dim, res.response, dim)

    def test_honest_when_lens_has_no_signal(self):
        empty = dict(_ES)
        empty["executive_lenses"] = {}
        with patch("apps.core.cos_briefing.build_executive_summary",
                   return_value=empty):
            res = dr.classify_and_route(
                "what should i protect the most right now", self.user)
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
                  "list everything remaining today", "what remains today"):
            res = dr.classify_and_route(q, self.user)
            route = getattr(res, "route_name", None) if res else None
            self.assertNotEqual(route, "executive_summary_query", q)

    def test_domain_status_questions_not_executive(self):
        # Domain-qualified "how am i doing" stays on its domain route (guard).
        for q in ("how am i doing on protein", "how am i doing with sleep",
                  "how am i doing with glucose"):
            res = dr.classify_and_route(q, self.user)
            route = getattr(res, "route_name", None) if res else None
            self.assertNotEqual(route, "executive_summary_query", q)
