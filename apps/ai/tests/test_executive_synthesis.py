"""Bounded Executive Synthesis Phase (Phase 2) — unit + generate() wiring tests.

Phase 1 investigates + gathers evidence; Phase 2 (same model, no tools) synthesizes the
executive judgment over that evidence, only for turns that drew on >=2 independent
substantive truth surfaces. Not judge-the-judge (Phase 2 never sees Phase 1's prose);
on failure the grounded Phase-1 answer is kept.
"""
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.ai.model_interface import synthesis as S
from apps.ai.model_interface.service import ModelInterfaceService
from apps.users.models import TermsAcceptance

try:
    from apps.users.models import User
except ImportError:
    from django.contrib.auth import get_user_model
    User = get_user_model()


def _user(email):
    u = User.objects.create_user(email=email, password="pw12345!")
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    p = u.preferences
    p.has_completed_onboarding = True
    p.use_model_interface = True
    p.save()
    return u


class EligibilityTests(TestCase):
    def test_is_substantive_truth(self):
        self.assertTrue(S.is_substantive_truth("get_analysis", {"holds_data": True}))
        self.assertTrue(S.is_substantive_truth("get_history", {"status": "ready"}))
        self.assertFalse(S.is_substantive_truth("get_analysis", {"status": "empty"}))
        self.assertFalse(S.is_substantive_truth("mutate_task", {"holds_data": True}))
        self.assertFalse(S.is_substantive_truth("get_analysis", {"status": "unsupported"}))

    def test_eligibility_needs_two_distinct_surfaces(self):
        one = [{"tool": "get_analysis", "args": {"domain": "health", "subject": "overall"}}]
        dup = one + [{"tool": "get_analysis", "args": {"domain": "health", "subject": "overall"}}]
        two = one + [{"tool": "get_analysis", "args": {"domain": "nutrition", "subject": "overall"}}]
        self.assertFalse(S.synthesis_eligible([]))          # narrow: 0 surfaces
        self.assertFalse(S.synthesis_eligible(one))         # narrow: 1 surface
        self.assertFalse(S.synthesis_eligible(dup))         # same surface twice != 2
        self.assertTrue(S.synthesis_eligible(two))          # 2 distinct domains -> eligible

    def test_render_evidence_compact_facts_pooled_scaffolding_stripped(self):
        ev = [{"tool": "get_analysis", "args": {"domain": "health", "subject": "overall"},
               "result": {"status": "ready", "holds_data": True, "scope": "long prose…",
                          "note": "facts only", "schema_version": "1", "generated_at": "x",
                          "concepts": {"body": {"members": {"weight": {
                              "label": "Weight", "value": "274.5", "unit": "lb", "change": "-9.2"}}}},
                          "subjects": {"weight": {"present": True,
                              "change": {"first": "280", "last": "274.5", "delta": "-5.5",
                                         "direction": "falling"}}}}}]
        out = S.render_evidence(ev)
        self.assertIn("health", out)
        self.assertIn("274.5", out)          # current value fact preserved
        self.assertIn("-9.2", out)           # concept change preserved
        self.assertIn("falling", out)        # trend fact preserved
        self.assertNotIn("long prose", out)  # scope scaffolding stripped
        self.assertNotIn("facts only", out)  # note stripped
        self.assertNotIn("schema_version", out)
        self.assertNotIn("{", out)           # compact flat facts, not nested json

    def test_run_executive_synthesis_no_tools_returns_answer(self):
        class FakeAI:
            model = "gpt-4o"
            calls = []
            def _call_api(self, system, user_prompt, **kw):
                FakeAI.calls.append((system, user_prompt, kw))
                return "  My read is you're progressing on X.  "
        ai = FakeAI()
        ans = S.run_executive_synthesis(
            ai, message="how am I doing overall?",
            evidence=[{"tool": "get_analysis", "args": {"domain": "health"},
                       "result": {"holds_data": True, "subjects": {}}}],
            standing_context={"missions": {"primary": "France 2027"}})
        self.assertEqual(ans, "My read is you're progressing on X.")
        # synthesis uses the dedicated contract + endpoint, no tools
        sys_prompt, up, kw = FakeAI.calls[-1]
        self.assertIn("SECOND phase", sys_prompt)
        self.assertEqual(kw.get("endpoint"), "model_interface_synthesis")
        self.assertIn("France 2027", up)   # standing orientation carried


class SynthesisTimeoutTests(TestCase):
    def test_synthesis_endpoint_has_full_timeout_not_utility(self):
        # Phase 2 is a large-prompt executive-judgment call; it must get the model_interface
        # timeout, never the 8s utility default (which would silently time out -> no synthesis).
        from apps.ai.services import (
            ENDPOINT_TIMEOUTS, LLM_TIMEOUT_MODEL_INTERFACE, LLM_TIMEOUT_UTILITY,
        )
        self.assertEqual(ENDPOINT_TIMEOUTS.get("model_interface_synthesis"),
                         LLM_TIMEOUT_MODEL_INTERFACE)
        self.assertNotEqual(ENDPOINT_TIMEOUTS.get("model_interface_synthesis"),
                            LLM_TIMEOUT_UTILITY)


class GenerateTwoPhaseWiringTests(TestCase):
    """generate() routes an eligible turn through Phase 2, keeps Phase-1 on failure,
    and stays single-phase for a narrow turn."""

    def setUp(self):
        self.user = _user("synth_wire@test.com")
        self.svc = ModelInterfaceService(self.user)
        from apps.ai.models import AssistantConversation
        self.conv = AssistantConversation.get_or_create_active(self.user)

    def _run(self, *, eligible, synth_answer):
        with patch.object(self.svc, "build_standing_context", return_value={"missions": {}}), \
             patch.object(self.svc, "_system_prompt", return_value="sys"), \
             patch.object(self.svc.ai, "_call_api_with_tools", return_value="PHASE1 DASHBOARD"), \
             patch("apps.ai.model_interface.synthesis.synthesis_eligible", return_value=eligible), \
             patch("apps.ai.model_interface.synthesis.run_executive_synthesis",
                   return_value=synth_answer):
            return self.svc.generate(self.conv, "how am I doing overall in my life?")

    def test_eligible_turn_uses_phase2_answer(self):
        out = self._run(eligible=True, synth_answer="PHASE2 JUDGMENT")
        self.assertEqual(out["answer"], "PHASE2 JUDGMENT")
        self.assertTrue(out["synthesis_used"])

    def test_phase2_failure_keeps_grounded_phase1_answer(self):
        out = self._run(eligible=True, synth_answer="")   # synthesis failed/empty
        self.assertEqual(out["answer"], "PHASE1 DASHBOARD")  # durable turn not lost
        self.assertFalse(out["synthesis_used"])

    def test_narrow_turn_stays_single_phase(self):
        out = self._run(eligible=False, synth_answer="PHASE2 JUDGMENT")
        self.assertEqual(out["answer"], "PHASE1 DASHBOARD")
        self.assertFalse(out["synthesis_used"])
