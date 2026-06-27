# ==============================================================================
# File: apps/ai/tests/test_acceptance_rules.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Unit tests for the shared acceptance EVALUATOR (used by the live
#   `beth_acceptance` harness). Verifies the rule logic deterministically AND
#   proves the deterministic-fallback FLOOR passes the live harness rules — so the
#   live harness can only fail on LLM-phrasing/routing/reliability, never the floor.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos import acceptance_rules as ar
from apps.ai.chatgpt_cos.reasoning import stages

MISSION = "France 2027 Family 18K Mission"
_CTX = {
    "has_milestones": True, "current_phase": "weight-loss foundation phase",
    "active_milestone_detail": "reach 284.9 lb — protein, hydration, scheduled workouts",
    "next_milestones": ["a return to running base"],
    "recently_completed_milestone": "bought running shoes",
    "why_it_matters": "To run the 18K in France with my family and stay healthy enough "
                      "to keep up with my kids for decades.",
    "success_definition": "Crossing the France 18K finish line together as a family in 2027.",
}
_EV = {
    "state": "stable", "momentum": "moderate", "trend": "stable",
    "phase": "weight-loss foundation phase", "momentum_summary": "on pace",
    "success_drivers": ["weight trending down", "workouts on schedule"],
    "risk_drivers": ["workout frequency is light"],
    "recommended_action": "complete today's scheduled workout and hit your protein target",
}
FRANCE = {
    "goals_state": {"state": {
        "active_goal_count": 1, "completion_rate": 0.4, "overdue_goal_count": 0,
        "active_titles": [{"title": MISSION, "target_date": None, "context": _CTX, "evidence": _EV}],
        "upcoming_titles": [], "overdue_titles": [],
        "mission": {"title": MISSION, "context": _CTX, "evidence": _EV},
    }},
    "habits_state": {"state": {"active_habit_count": 1, "avg_completion_rate": 0.6,
                               "streaks_per_habit": []}},
}


def _wm():
    return {"facts": stages.goals_working_memory(FRANCE)}


class EvaluatorLogicTests(SimpleTestCase):
    def test_empty_fails(self):
        self.assertEqual(ar.evaluate({"domain": "goals"}, ""), ["empty"])

    def test_failure_message_fails(self):
        f = ar.evaluate({"domain": "general"},
                        "I reached OpenAI, but the response came back empty after retries.")
        self.assertIn("openai_failure_message", f)

    def test_banned_phrase_fails(self):
        f = ar.evaluate({"domain": "goals", "expect_intent": "goals_focus_today"},
                        "Today, just work on your goal and make progress.",
                        intent="goals_focus_today")
        self.assertTrue(any("banned_phrase" in x for x in f))

    def test_wrong_domain_fails(self):
        # a named-goal question answered by a HEALTH intent
        f = ar.evaluate({"domain": "goals", "expect_intent": "goals_progress"},
                        "Your weight is 248 lb and glucose is 165.",
                        intent="biggest_health_risk")
        self.assertTrue(any("wrong_domain" in x for x in f))

    def test_missing_required_and_forbidden(self):
        f = ar.evaluate({"domain": "goals", "required": ["France 2027"],
                         "forbidden": ["active goal count"]},
                        "Your active goal count is 3.", intent="goals_progress")
        self.assertIn("missing_required:France 2027", f)
        self.assertIn("forbidden:active goal count", f)

    def test_gate_failures(self):
        f = ar.evaluate({"domain": "goals", "gates": ["evidence", "actionable", "synthesis"]},
                        "You're doing fine overall.", intent="goals_progress")
        self.assertIn("gate_evidence", f)
        self.assertIn("gate_actionable", f)
        self.assertIn("gate_synthesis", f)

    def test_general_clean_answer_passes(self):
        f = ar.evaluate(
            {"domain": "general", "required_any": ["president", "lincoln"], "gates": []},
            "Abraham Lincoln was the 16th U.S. president, who led during the Civil War.",
            intent=None, lane="general_conversation")
        self.assertEqual(f, [])


class DeterministicFloorPassesHarness(SimpleTestCase):
    """Every goal question's deterministic FALLBACK must pass its live-harness
    spec — so the live run can only fail on LLM phrasing/routing/reliability."""
    FALLBACKS = {
        "goal_progress": stages._goals_progress_fallback,
        "goal_on_track": stages._goal_on_track_fallback,
        "goal_why": stages._goal_why_priority_fallback,
        "goal_milestone": stages._goal_next_milestone_fallback,
        "goal_failure": stages._goal_failure_modes_fallback,
        "goal_confidence": stages._goal_confidence_fallback,
        "goal_focus": stages._goals_focus_today_fallback,
        "goal_slipping": stages._goal_concerns_fallback,
        "goal_risk": stages._goal_risk_fallback,
    }

    def _spec(self, key):
        return next(q for q in ar.QUESTIONS if q["key"] == key)

    def test_each_goal_fallback_passes_its_spec(self):
        wm = _wm()
        for key, fb in self.FALLBACKS.items():
            spec = self._spec(key)
            answer = fb(wm)
            fails = ar.evaluate(spec, answer, intent=spec.get("expect_intent"))
            self.assertEqual(fails, [], f"{key} floor FAILED harness: {fails}\n  {answer!r}")

    def test_goal_fallbacks_are_distinct(self):
        wm = _wm()
        answers = [fb(wm) for fb in self.FALLBACKS.values()]
        # the six "reasoning" intents (exclude focus/slipping/risk overlap-by-design)
        core = [self.FALLBACKS[k](wm) for k in
                ("goal_progress", "goal_on_track", "goal_why", "goal_milestone",
                 "goal_failure", "goal_confidence")]
        self.assertEqual(len(set(core)), 6, "core goal intents collapsed")


class QuestionSpecSanity(SimpleTestCase):
    def test_all_questions_have_text_and_domain(self):
        for q in ar.QUESTIONS:
            self.assertIn("text", q)
            self.assertIn("domain", q)

    def test_command_imports(self):
        from apps.ai.management.commands import beth_acceptance  # noqa: F401
        self.assertTrue(hasattr(beth_acceptance, "Command"))
