# ==============================================================================
# File: apps/admin_console/tests/test_acceptance_architecture.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Architecture-level acceptance hardening — failure LAYER aggregation,
#   infrastructure-vs-content split, stronger grading, run trustworthiness, the
#   empty-response invariant + emergency fallback, and the upgraded review prompts.
# ==============================================================================
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos import acceptance_service as svc

User = get_user_model()


def _row(key, suite, fails, intent=None, lane=None, answer="x", ms=100, passed=None):
    return {"key": key, "suite": suite, "question": key, "answer": answer,
            "expected_intent": "", "intent": intent, "lane": lane,
            "openai_called": False, "fallback_used": None, "ms": ms,
            "distinct_group": "", "criticality": "normal", "spec": {"depth": "full"},
            "fails": fails, "passed": (not fails) if passed is None else passed}


# ---------------------------------------------------------------------------
class LayerAggregationTests(TestCase):
    def test_every_category_maps_to_a_layer(self):
        for _prefix, cat in ar._RULE_CATEGORY:
            self.assertIn(ar.layer_of(cat), ar.INFRA_LAYERS + ar.CONTENT_LAYERS,
                          f"{cat} -> unknown layer")

    def test_layer_mapping_is_deterministic(self):
        self.assertEqual(ar.layer_of("empty_response"), "conversation_orchestration")
        self.assertEqual(ar.layer_of("general_failure"), "infrastructure")
        self.assertEqual(ar.layer_of("wrong_domain"), "routing")
        self.assertEqual(ar.layer_of("banned_phrase"), "narration")
        self.assertEqual(ar.layer_of("response_quality"), "content_quality")

    def test_row_layer_precedence_infra_over_content(self):
        # a row with both a content gate AND an empty/infra failure -> infra layer
        self.assertEqual(ar.row_layer(["gate_actionable", "empty"]),
                         "conversation_orchestration")
        self.assertEqual(ar.row_layer(["gate_evidence"]), "content_quality")

    def test_infra_vs_content_partition_is_complete(self):
        for lyr in ar.FAILURE_LAYERS.values():
            self.assertIn(lyr, ar.INFRA_LAYERS + ar.CONTENT_LAYERS)


class StrongerGradingTests(TestCase):
    def test_empty_forces_red(self):
        self.assertEqual(ar.compute_grade(100, 0, empty_present=True), "RED")

    def test_entire_suite_failure_forces_red(self):
        self.assertEqual(ar.compute_grade(99, 0, entire_suite_failed=True), "RED")

    def test_infra_threshold_forces_red(self):
        self.assertEqual(ar.compute_grade(99, 0, infra_fails=3), "RED")

    def test_clean_high_score_is_green(self):
        self.assertEqual(ar.compute_grade(96, 0), "GREEN")


class AnalyzeTests(TestCase):
    def _rows(self):
        return [
            _row("goal_why", "goals", ["empty"], intent=None, lane=None, answer=""),
            _row("goal_next", "goals", ["empty"], intent=None, lane=None, answer=""),
            _row("gen_lincoln", "general", ["openai_failure_message"], answer="couldn't reach"),
            _row("gen_photo", "general", ["openai_failure_message"], answer="couldn't reach"),
            _row("gen_delphi", "general", ["openai_failure_message"], answer="couldn't reach"),
            _row("goal_ok", "goals", [], answer="France 2027 is on pace.", passed=True),
        ]

    def test_layers_and_infra_content_split(self):
        a = svc.analyze(self._rows())
        self.assertEqual(a["empty_count"], 2)
        self.assertGreaterEqual(a["infra_fails"], 5)        # 2 empty + 3 general
        self.assertEqual(a["content_fails"], 0)
        self.assertIn("conversation_orchestration", a["layers"])
        self.assertIn("infrastructure", a["layers"])

    def test_entire_general_suite_detected(self):
        a = svc.analyze(self._rows())
        self.assertIn("general", a["entire_suites_failed"])

    def test_run_marked_untrustworthy(self):
        a = svc.analyze(self._rows())
        self.assertFalse(a["trustworthy"])
        self.assertIn("partially invalid", a["trust_reason"].lower())

    def test_hypotheses_identify_orchestration_and_openai(self):
        a = svc.analyze(self._rows())
        titles = " ".join(h["title"].lower() for h in a["hypotheses"])
        self.assertIn("orchestration", titles)
        self.assertTrue("openai" in titles or "general" in titles)

    def test_blockers_listed(self):
        a = svc.analyze(self._rows())
        self.assertTrue(a["blockers"])
        self.assertTrue(any(b["layer"] == "conversation_orchestration" for b in a["blockers"]))

    def test_clean_run_is_trustworthy(self):
        a = svc.analyze([_row("ok", "goals", [], passed=True)])
        self.assertTrue(a["trustworthy"])
        self.assertEqual(a["infra_fails"], 0)


class ArchPromptTests(TestCase):
    def _fake(self):
        rows = AnalyzeTests()._rows()
        a = svc.analyze(rows)
        run = SimpleNamespace(
            environment="production", git_commit="abc", suite_name="full", depth="full",
            completed_at="t", created_at="t", score_percent=40, pass_count=1,
            total_count=6, fail_count=5, grade="RED", critical_count=5,
            warning_count=0, avg_response_ms=200, category_summary={}, analysis=a,
            trustworthy=a["trustworthy"])
        return run, rows

    def test_chatgpt_prompt_has_invariants_layers_trust(self):
        run, rows = self._fake()
        p = svc.build_chatgpt_review_prompt(run, rows)
        self.assertIn("ARCHITECTURAL INVARIANTS", p)
        self.assertIn("INFRASTRUCTURE vs CONTENT", p)
        self.assertIn("ARCHITECTURAL LAYER AGGREGATION", p)
        self.assertIn("AUTOMATED HYPOTHESES", p)     # renamed from "LIKELY ROOT CAUSES"
        self.assertIn("RUN TRUSTWORTHINESS", p)
        self.assertIn("RELEASE BLOCKERS", p)
        self.assertIn("falsely", p.lower())

    def test_claude_prompt_has_invariants_and_precedence(self):
        run, rows = self._fake()
        p = svc.build_claude_fix_prompt(run, rows)
        self.assertIn("ARCHITECTURAL INVARIANTS", p)
        self.assertIn("FIX INFRASTRUCTURE DEFECTS FIRST", p)
        self.assertIn("RUN TRUSTWORTHINESS", p)
        self.assertIn("Do not stop for approval unless", p)


class EmptyResponseInvariantTests(TestCase):
    """generate() must NEVER return an empty answer (invariant #1)."""
    def setUp(self):
        from apps.users.models import TermsAcceptance
        from apps.ai.models import AssistantConversation
        self.user = User.objects.create_user(email="invar@example.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.conv = AssistantConversation.objects.create(user=self.user, is_active=False)

    def test_empty_tool_loop_yields_emergency_fallback(self):
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService
        with patch("apps.ai.chatgpt_cos.lanes.route_message", return_value=None), \
             patch("apps.ai.cos_services.get_standing_context", return_value={}), \
             patch("apps.ai.cos_services.get_tool_schemas", return_value=[]), \
             patch("apps.ai.services.ai_service._call_api_with_tools", return_value=None):
            res = ChatGPTCoSService(self.user).generate(self.conv, "zxqv nonsense??")
        self.assertTrue(res["answer"].strip(), "empty answer violates invariant #1")
        self.assertEqual(res["empty_reason"], "openai_fallback_empty")

    def test_emergency_fallback_is_graceful_not_empty(self):
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService
        msg = ChatGPTCoSService(self.user)._emergency_fallback()
        self.assertTrue(len(msg) > 30)
        # it is classified by the evaluator as an infrastructure failure (correct)
        self.assertTrue(ar.is_failure_message(msg))
