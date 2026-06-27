# ==============================================================================
# File: apps/ai/tests/test_p27_convergence.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P27 Deep convergence — three architectural classes made permanent:
#   DC#1 goal IDENTITY resolution (distinctive title token + referents + framing,
#        not full-string matching) — and general questions are NOT stolen;
#   DC#2 deterministic CoS capability coverage (truth exists -> Beth reaches it);
#   Acceptance Center: "deterministic capability gap" classification (truth exists
#        but no deterministic path reaches it) distinct from infrastructure.
#   Validates ACTUAL rendered responses, not templates.
# ==============================================================================
from types import SimpleNamespace
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase

from apps.ai.chatgpt_cos.reasoning import plan as planmod
from apps.ai.chatgpt_cos.reasoning.plan import preroute_named_goal
from apps.ai.chatgpt_cos.lanes import route_message
from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos import acceptance_service as svc

User = get_user_model()
_C = "apps.ai.services.ai_service._call_api"
_CT = "apps.ai.services.ai_service._call_api_with_tools"
_TITLES = ["France 2027 Family 18K Mission"]


# ---------------------------------------------------------------------------
# DC#1 — goal IDENTITY resolution (pure: distinctive token + referent + framing).
# ---------------------------------------------------------------------------
class GoalIdentityResolutionTests(SimpleTestCase):
    def _r(self, msg):
        return planmod.named_goal_intent(msg, _TITLES, _TITLES[0])[0]

    def test_distinctive_token_with_framing_resolves_to_goal(self):
        for q in ("How is France going?", "my France goal", "status update on France",
                  "how's France 2027 tracking?", "progress on my France goal",
                  "What's the status of my France mission?"):
            self.assertIsNotNone(self._r(q), f"{q!r} did not resolve to a goal")

    def test_mission_referents_resolve(self):
        for q in ("How is the mission going?", "what's the mission status?",
                  "is the mission on track?", "what's the biggest threat to the mission?",
                  "am I behind on the mission?"):
            self.assertIsNotNone(self._r(q), f"{q!r} did not resolve to a goal")

    def test_general_mentions_are_NOT_stolen(self):
        # a goal's distinctive token in a NON-goal-framed sentence stays general.
        for q in ("what is the capital of France?", "tell me about France",
                  "France is in Europe", "I love French food"):
            self.assertIsNone(self._r(q), f"{q!r} was wrongly claimed by goals")

    def test_distinctive_tokens_exclude_generic_words(self):
        toks = planmod._distinctive_title_tokens(_TITLES)
        self.assertIn("france", toks)
        for generic in ("family", "mission", "goal", "the"):
            self.assertNotIn(generic, toks)

    def test_unrelated_goal_token_needs_framing(self):
        # identity alone is insufficient; framing is required for the partial token.
        self.assertIsNone(self._r("France"))            # bare token, no framing
        self.assertIsNotNone(self._r("how is France doing"))  # token + framing


# ---------------------------------------------------------------------------
# DC#2 — deterministic CoS capability coverage (OpenAI disabled => still answers).
# ---------------------------------------------------------------------------
class CoSCapabilityCoverageTests(TestCase):
    CAPABILITIES = ["Give me a health summary.", "What's my biggest health concern?",
                    "what's my mission status?", "how is my diabetes doing?",
                    "diabetes status", "How is France going?", "what needs my attention?"]

    def setUp(self):
        from apps.users.models import TermsAcceptance
        from apps.purpose.models import LifeGoal
        self.u = User.objects.create_user(email="p27cap@x.com", password="x")
        TermsAcceptance.objects.create(
            user=self.u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.u.preferences.has_completed_onboarding = True
        self.u.preferences.save()
        LifeGoal.objects.create(user=self.u, title="France 2027 Family 18K Mission",
                                status="active", is_primary_mission=True)

    def test_capabilities_answer_without_openai(self):
        with mock.patch(_C, side_effect=RuntimeError("down")), \
             mock.patch(_CT, side_effect=RuntimeError("down")):
            for q in self.CAPABILITIES:
                res = route_message(self.u, q, None)
                self.assertIsNotNone(res, f"{q!r} fell to the tool loop (capability gap)")
                ans = (res.get("answer") or "").strip()
                self.assertTrue(ans, f"{q!r} produced empty")
                self.assertFalse(ar.is_failure_message(ans),
                                 f"{q!r} degraded to an outage message: {ans[:70]!r}")


# ---------------------------------------------------------------------------
# Acceptance Center — "deterministic capability gap" classification.
# ---------------------------------------------------------------------------
class CapabilityGapClassificationTests(SimpleTestCase):
    def _row(self, suite, fails, openai):
        return {"key": f"{suite}_x", "suite": suite, "fails": fails,
                "openai_called": openai, "fallback_used": True, "intent": "overall_progress",
                "lane": "personal_reasoning", "passed": False, "ms": 100,
                "question": "q", "answer": "couldn't reach", "expected_intent": "",
                "spec": {"depth": "deep"}}

    def test_personal_outage_is_capability_gap_not_infrastructure(self):
        subs, _ = svc.probable_subsystems(
            self._row("health", ["openai_failure_message"], False))
        self.assertEqual(subs[0], "deterministic capability gap")

    def test_general_outage_is_infrastructure_not_capability_gap(self):
        subs, _ = svc.probable_subsystems(
            self._row("general", ["openai_failure_message"], False))
        self.assertIn("OpenAI integration", subs)
        self.assertNotIn("deterministic capability gap", subs)

    def test_capability_gap_hypothesis_layer_is_deterministic_truth(self):
        a = svc.analyze([dict(self._row("goals", ["openai_failure_message"], False),
                              question="q", answer="couldn't reach", spec={"depth": "deep"})])
        h = a["hypotheses"][0]
        self.assertEqual(h["layer"], "deterministic_truth")
        self.assertIn("capability gap", h["title"].lower())

    def test_review_prompt_asks_the_five_way_classification(self):
        rows = [dict(self._row("health", ["openai_failure_message"], False),
                     question="q", answer="couldn't reach", spec={"depth": "deep"})]
        a = svc.analyze(rows)
        run = SimpleNamespace(
            environment="production", git_commit="x", suite_name="full", depth="deep",
            completed_at="t", created_at="t", score_percent=80, pass_count=4,
            total_count=5, fail_count=1, grade="RED", critical_count=0, warning_count=0,
            avg_response_ms=200, category_summary={}, analysis=a, trustworthy=a["trustworthy"])
        p = svc.build_chatgpt_review_prompt(run, rows)
        self.assertIn("primary classification", p.lower())
        for c in svc.FAILURE_CLASSIFICATION:
            self.assertIn(c, p)
        self.assertIn("Capability Gap", p)
