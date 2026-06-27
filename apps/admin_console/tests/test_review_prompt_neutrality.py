# ==============================================================================
# File: apps/admin_console/tests/test_review_prompt_neutrality.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A+ prompt hardening — the generated review prompts must GUIDE not
#   ANCHOR. Hypotheses are advisory ("may be wrong"), repository evidence is
#   supreme, subsystem attribution is telemetry-driven (a HEALTH failure is NOT
#   blamed on Goals), confidence is exposed, and discrepancy reporting is forced.
#   Origin: production health-suite banned_phrase mis-attributed to Goals.
# ==============================================================================
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.ai.chatgpt_cos import acceptance_service as svc


def _run_with(rows):
    a = svc.analyze(rows)
    return SimpleNamespace(
        environment="production", git_commit="abc123", suite_name="full", depth="full",
        completed_at="2026-06-27", created_at="2026-06-27", score_percent=90,
        pass_count=9, total_count=10, fail_count=1, grade="RED", critical_count=0,
        warning_count=0, avg_response_ms=1100, category_summary={}, analysis=a,
        trustworthy=a["trustworthy"])


# The cited production failure: HEALTH suite, LLM narration, banned coaching phrase.
_HEALTH_BANNED = [{
    "key": "hp_overall", "suite": "health", "question": "How is my health?",
    "answer": "You're doing well — maintain momentum.", "expected_intent": "overall_progress",
    "intent": "overall_progress", "lane": "personal_reasoning", "openai_called": True,
    "fallback_used": False, "ms": 1200, "fails": ["banned_phrase:maintain momentum"],
    "passed": False, "spec": {"depth": "smoke"}}]


class SubsystemInferenceTests(SimpleTestCase):
    def _subs(self, row):
        return svc.probable_subsystems(row)[0]

    def test_health_banned_attributes_to_health_not_goals(self):
        subs = self._subs(_HEALTH_BANNED[0])
        self.assertIn("health narration", subs)
        self.assertNotIn("goal narration", subs)

    def test_goal_banned_attributes_to_goal(self):
        row = dict(_HEALTH_BANNED[0], suite="goals", intent="goals_progress")
        self.assertIn("goal narration", self._subs(row))

    def test_outage_attributes_to_deterministic_fallback(self):
        row = {"key": "g1", "suite": "goals", "fails": ["openai_failure_message"],
               "openai_called": False, "fallback_used": True, "intent": "goals_progress",
               "lane": "personal_reasoning", "passed": False}
        self.assertIn("deterministic fallback", self._subs(row))

    def test_empty_attributes_to_tool_loop(self):
        row = {"key": "g1", "suite": "goals", "fails": ["empty"], "openai_called": False,
               "fallback_used": None, "intent": None, "lane": None, "passed": False}
        subs = self._subs(row)
        self.assertIn("tool loop", subs)
        self.assertIn("conversation orchestration", subs)

    def test_general_outage_attributes_to_openai_integration(self):
        row = {"key": "gen1", "suite": "general", "fails": ["openai_failure_message"],
               "openai_called": False, "fallback_used": True, "intent": None,
               "lane": "general_conversation", "passed": False}
        subs = self._subs(row)
        self.assertIn("OpenAI integration", subs)
        self.assertIn("general outage fallback", subs)

    def test_wrong_domain_attributes_to_routing(self):
        row = {"key": "b1", "suite": "boundary", "fails": ["wrong_domain(intent=x,lane=y)"],
               "openai_called": True, "fallback_used": False, "intent": "x", "lane": "y",
               "passed": False}
        self.assertIn("routing", self._subs(row))

    def test_missing_required_points_at_acceptance_guard_not_leak(self):
        # A content/missing_required failure is NOT a narration leak — it may be an
        # over-narrow evaluator contract (origin: goal_failure_modes was). The
        # hypothesis must invite checking the evaluator, not just Beth narration.
        row = {"key": "goal_failure_modes__0", "suite": "goals",
               "fails": ["missing_required_any:fail|risk|slip"], "openai_called": True,
               "fallback_used": False, "intent": "goal_failure_modes",
               "lane": "personal_reasoning", "passed": False}
        subs = self._subs(row)
        self.assertEqual(subs[0], "acceptance guard")
        title = svc.analyze([dict(row, question="q", answer="a", spec={"depth": "full"})]
                            )["hypotheses"][0]["title"].lower()
        self.assertIn("acceptance contract", title)
        self.assertNotIn("leak", title)

    def test_confidence_exposed(self):
        self.assertIn(svc.probable_subsystems(_HEALTH_BANNED[0])[1],
                      ("LOW", "MEDIUM", "HIGH"))


class ChatGPTNeutralityTests(SimpleTestCase):
    def setUp(self):
        self.p = svc.build_chatgpt_review_prompt(_run_with(_HEALTH_BANNED), _HEALTH_BANNED)

    def test_hypotheses_are_advisory(self):
        self.assertIn("may be wrong", self.p.lower())
        self.assertIn("AUTOMATED HYPOTHESES", self.p)
        self.assertNotIn("LIKELY ROOT CAUSES", self.p)

    def test_evidence_supremacy_present(self):
        self.assertIn("repository evidence takes precedence", self.p.lower())

    def test_agreement_question_present(self):
        self.assertIn("do you agree with the automated hypotheses", self.p.lower())

    def test_per_question_subsystem_is_telemetry_driven(self):
        self.assertIn("probable subsystem(s)", self.p.lower())
        self.assertIn("health narration", self.p)
        # the anchoring bug must NOT recur — the health failure is not blamed on Goals
        # ("goal narration" still appears once, in the controlled-vocabulary list).
        self.assertNotIn("Possible narration leak in GOAL narration", self.p)
        self.assertNotIn("into LLM goal answers", self.p)

    def test_confidence_shown_in_hypotheses(self):
        self.assertIn("confidence=", self.p)


class ClaudeNeutralityTests(SimpleTestCase):
    def setUp(self):
        self.p = svc.build_claude_fix_prompt(_run_with(_HEALTH_BANNED), _HEALTH_BANNED)

    def test_advisory_and_evidence_supremacy(self):
        self.assertIn("may be wrong", self.p.lower())
        self.assertIn("repository evidence takes precedence", self.p.lower())

    def test_discrepancy_reporting_forced(self):
        low = self.p.lower()
        self.assertIn("document the discrepancy", low)
        self.assertIn("corrected", low)
        self.assertIn("why the heuristic failed", low)
        self.assertIn("whether prompt generation should improve", low)

    def test_health_not_misattributed_to_goals(self):
        self.assertIn("health narration", self.p)
        self.assertNotIn("into LLM goal answers", self.p)
        self.assertNotIn("Possible narration leak in GOAL narration", self.p)


class CleanRunStillWorksTests(SimpleTestCase):
    def test_green_run_arch_block_has_no_hypotheses(self):
        rows = [{"key": "ok", "suite": "goals", "question": "q", "answer": "France on pace.",
                 "expected_intent": "goals_progress", "intent": "goals_progress",
                 "lane": "personal_reasoning", "openai_called": True, "fallback_used": False,
                 "ms": 800, "fails": [], "passed": True, "spec": {"depth": "smoke"}}]
        a = svc.analyze(rows)
        self.assertEqual(a["hypotheses"], [])
