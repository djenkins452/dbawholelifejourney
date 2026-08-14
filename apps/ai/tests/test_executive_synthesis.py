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

    def test_build_orientation_strips_predecided_verdicts_keeps_facts(self):
        # The Phase-2 orientation must carry FACTS (who Danny is / what he's working toward)
        # but NEVER a pre-decided progress/drift verdict (momentum score/band, biggest_risk,
        # strategic summary) — handed one, the model narrated it as its own judgment with no
        # lineage to defend on challenge (proven on the live runtime 2026-08-14).
        sc = {
            "missions": {"g1": {"title": "Serve Others", "why_it_matters": "beyond self",
                                "progress": {"milestone_percent": 0, "momentum_score": 25,
                                             "momentum_7d_avg": 22}}},
            "current_action": {"primary_action": "Work on WLJ", "reason": "overdue foundational"},
            "personal_truth": {"summary": "Danny, faith-centered"},
            "deterministic_understanding": {
                "executive": {"biggest_risk": "sleep debt is the main thing to watch",
                              "primary_challenge": "workload"},
                "priority": {"executive": "batch the overdue tasks"},
                "direction": {"momentum": 25, "strategic_summary": "drifting rather than progressing"},
            },
        }
        out = S.build_orientation(sc)
        # Facts survive
        self.assertIn("Serve Others", out)
        self.assertIn("milestone_percent", out)
        self.assertIn("Work on WLJ", out)          # deterministic current action
        self.assertIn("faith-centered", out)       # personal truth
        # Pre-decided verdicts are gone
        self.assertNotIn("25", out)                        # momentum score
        self.assertNotIn("momentum", out.lower())          # any momentum score/band
        self.assertNotIn("biggest_risk", out)
        self.assertNotIn("sleep debt is the main thing", out)
        self.assertNotIn("primary_challenge", out)
        self.assertNotIn("strategic_summary", out)
        self.assertNotIn("drifting rather than progressing", out)
        self.assertNotIn("understanding_read", out)        # the whole du verdict block dropped

    def test_render_evidence_drops_verdict_labels_keeps_metric_facts(self):
        # A domain STATE may carry a scalar verdict label (momentum='low',
        # momentum_summary='behind pace') beside real facts. The verdict is stripped from the
        # Phase-2 evidence; the numeric facts are kept.
        ev = [{"tool": "get_analysis", "args": {"domain": "goals", "subject": "overall"},
               "result": {"status": "ready", "holds_data": True,
                          "state": {"momentum": "low", "momentum_summary": "behind pace",
                                    "recommended_action": "complete a task today",
                                    "milestones_completed": 3, "milestones_overdue": 1}}}]
        out = S.render_evidence(ev)
        self.assertIn("milestones_completed: 3", out)   # fact kept
        self.assertIn("milestones_overdue: 1", out)     # fact kept
        self.assertNotIn("behind pace", out)            # verdict stripped
        self.assertNotIn("momentum", out.lower())       # verdict stripped
        self.assertNotIn("complete a task today", out)  # prescription stripped

    def test_run_executive_synthesis_single_bounded_call(self):
        # Phase 2 is a single, hard-bounded, no-retry client call (bypasses _call_api's retry
        # loop/circuit breaker so it can never hang a turn), no tools, bounded timeout.
        from types import SimpleNamespace
        captured = {}

        class FakeCompletions:
            def create(self, **kw):
                captured.update(kw)
                msg = SimpleNamespace(content="  My read is you're progressing on X.  ")
                return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

        ai = SimpleNamespace(model="gpt-4o",
                             client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())),
                             _call_api=lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not use _call_api")))
        ans = S.run_executive_synthesis(
            ai, message="how am I doing overall?",
            evidence=[{"tool": "get_analysis", "args": {"domain": "health"},
                       "result": {"holds_data": True, "subjects": {}}}],
            standing_context={"missions": {"primary": "France 2027"}})
        self.assertEqual(ans, "My read is you're progressing on X.")
        self.assertEqual(captured.get("timeout"), S.SYNTHESIS_TIMEOUT_SECONDS)  # bounded
        msgs = captured.get("messages")
        self.assertEqual(msgs[0]["role"], "system")
        self.assertIn("SECOND phase", msgs[0]["content"])
        self.assertIn("France 2027", msgs[1]["content"])   # orientation carried
        self.assertNotIn("tools", captured)                # no tools

    def test_run_executive_synthesis_returns_empty_on_error(self):
        # On any client error/timeout, return "" so the caller keeps the grounded Phase-1 answer.
        from types import SimpleNamespace

        class Boom:
            def create(self, **kw):
                raise RuntimeError("timeout")
        ai = SimpleNamespace(model="gpt-4o",
                             client=SimpleNamespace(chat=SimpleNamespace(completions=Boom())))
        self.assertEqual(S.run_executive_synthesis(
            ai, message="q", evidence=[], standing_context={}), "")


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
