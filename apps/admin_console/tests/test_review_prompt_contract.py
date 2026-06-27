# ==============================================================================
# File: apps/admin_console/tests/test_review_prompt_contract.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The GENERATED Acceptance Center review prompts must be complete
#   enough for ChatGPT/Claude to perform an expert architectural review with NO
#   human augmentation — rigid output schema, full controlled vocabularies (7
#   layers, subsystems, severities), infra/content separation, trustworthiness
#   Q&A, one regression test per defect class, and the stable-tag condition list.
# ==============================================================================
from types import SimpleNamespace

from django.test import TestCase

from apps.ai.chatgpt_cos import acceptance_service as svc


def _fake_run():
    rows = [
        {"key": "goal_milestone", "suite": "goals", "question": "Next milestone?",
         "answer": "Lock in consistency with protein.", "expected_intent": "goal_next_milestone",
         "intent": "goal_next_milestone", "lane": "personal_reasoning", "openai_called": False,
         "fallback_used": True, "ms": 800, "fails": ["banned_phrase:lock in consistency"],
         "passed": False, "spec": {"depth": "full"}},
        {"key": "gen_lincoln", "suite": "general", "question": "Who was Lincoln?",
         "answer": "I couldn't reach it.", "expected_intent": "", "intent": None,
         "lane": "general_conversation", "openai_called": False, "fallback_used": True,
         "ms": 500, "fails": ["openai_failure_message"], "passed": False,
         "spec": {"depth": "full"}},
    ]
    a = svc.analyze(rows)
    run = SimpleNamespace(
        environment="production", git_commit="abc123", suite_name="full", depth="full",
        completed_at="2026-06-27", created_at="2026-06-27", score_percent=80,
        pass_count=8, total_count=10, fail_count=2, grade="RED", critical_count=1,
        warning_count=0, avg_response_ms=900, category_summary={}, analysis=a,
        trustworthy=a["trustworthy"])
    return run, rows


class ChatGPTReviewContractTests(TestCase):
    def setUp(self):
        self.run, self.rows = _fake_run()
        self.p = svc.build_chatgpt_review_prompt(self.run, self.rows)

    def test_has_required_output_schema_sections(self):
        for marker in ("REQUIRED OUTPUT", "A. SYSTEMIC DEFECT CLASSES",
                       "B. INFRASTRUCTURE vs CONTENT", "C. RANKED ROOT CAUSES",
                       "D. RUN TRUSTWORTHINESS", "E. RELEASE READINESS"):
            self.assertIn(marker, self.p, marker)

    def test_lists_full_seven_layer_vocabulary(self):
        for layer in svc.REVIEW_LAYER_VOCAB:        # incl. deterministic_truth + unknown
            self.assertIn(layer, self.p, layer)
        self.assertIn("deterministic_truth", self.p)
        self.assertIn("unknown", self.p)

    def test_lists_subsystem_vocabulary(self):
        for s in ("planner", "tool loop", "lane selection", "deterministic fallback",
                  "goal narration", "health narration", "acceptance guard",
                  "OpenAI integration"):
            self.assertIn(s, self.p, s)

    def test_requires_severity_ranking(self):
        for s in svc.REVIEW_SEVERITIES:             # BLOCKER/HIGH/MEDIUM/LOW
            self.assertIn(s, self.p, s)

    def test_requires_infra_vs_content_counts_with_examples(self):
        self.assertIn("Infrastructure defects:", self.p)
        self.assertIn("Content defects:", self.p)
        self.assertIn("empty responses", self.p)
        self.assertIn("banned phrases", self.p)
        # live automated tally present for cross-check
        self.assertIn(f"infrastructure={self.run.analysis['infra_fails']}", self.p)

    def test_requires_trustworthiness_qanda(self):
        for q in ("FALSELY GREEN", "FALSELY RED",
                  "invalidate the quality conclusions"):
            self.assertIn(q, self.p, q)

    def test_requires_one_regression_test_per_class(self):
        self.assertIn("permanent regression test", self.p.lower())
        self.assertIn("every production defect becomes a permanent test", self.p.lower())

    def test_requires_stable_tag_conditions(self):
        self.assertIn("beth-stable-v3", self.p)
        for cond in svc.STABLE_TAG_CONDITIONS:
            self.assertIn(cond, self.p, cond)

    def test_no_followup_questions_and_invariants_present(self):
        self.assertIn("Do NOT ask follow-up questions", self.p)
        self.assertIn("ARCHITECTURAL INVARIANTS", self.p)


class ClaudeFixContractTests(TestCase):
    def setUp(self):
        self.run, self.rows = _fake_run()
        self.p = svc.build_claude_fix_prompt(self.run, self.rows)

    def test_requires_per_class_classification(self):
        for layer in svc.REVIEW_LAYER_VOCAB:
            self.assertIn(layer, self.p, layer)
        for s in svc.REVIEW_SEVERITIES:
            self.assertIn(s, self.p, s)
        self.assertIn("probable subsystem", self.p.lower())

    def test_requires_per_class_regression_test(self):
        self.assertIn("permanent regression test", self.p.lower())
        self.assertIn("every production defect becomes a permanent test", self.p.lower())
        self.assertIn("ACTUAL", self.p)             # validate actual rendered responses

    def test_infrastructure_first_and_stable_conditions(self):
        self.assertIn("INFRASTRUCTURE defects FIRST", self.p)
        for cond in svc.STABLE_TAG_CONDITIONS:
            self.assertIn(cond, self.p, cond)

    def test_green_run_short_circuits(self):
        run, rows = _fake_run()
        for r in rows:
            r["passed"] = True
            r["fails"] = []
        run.grade = "GREEN"
        p = svc.build_claude_fix_prompt(run, rows)
        self.assertIn("GREEN", p)
        self.assertIn("no fixes required", p)
