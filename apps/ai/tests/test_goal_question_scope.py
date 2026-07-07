# ==============================================================================
# File: apps/ai/tests/test_goal_question_scope.py
# Description: QUESTION-SCOPE DISCIPLINE (Phase 2). A question about ONE named goal
#   ("how am I doing towards my 2027 France goal?") returns ONLY that goal — its
#   trajectory, milestone, and next move — never the whole goal portfolio (Launch WLJ,
#   Relationship with God, Serve Others). It may offer, in one sentence, to review the
#   others. The portfolio intent (goals_progress) is reserved for an explicit plural ask.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.reasoning import plan as planmod
from apps.ai.chatgpt_cos.reasoning import stages

_PORTFOLIO = {"goal_evidence": [
    {"goal": "France 2027 Family 18K Mission", "state": "stable",
     "whats_working": ["weight down 3 lb"], "recommended_action": "protein early, cardio"},
    {"goal": "Launch Whole Life Journey", "state": "stable"},
    {"goal": "Relationship with God", "state": "thriving"},
    {"goal": "Serve Others", "state": "stable"}],
    "active_goals": ["France 2027 Family 18K Mission", "Launch Whole Life Journey",
                     "Relationship with God", "Serve Others"]}


class NamedGoalIntentTests(SimpleTestCase):
    def test_progress_toward_a_named_goal_is_goal_specific_not_portfolio(self):
        for m in ("how am i doing overall towards my 2027 france goal",
                  "how's my france goal coming along",
                  "how am i doing on france 2027",
                  "where do i stand on france",
                  "give me an update on france 2027"):
            self.assertEqual(planmod._infer_named_goal_intent(m), "goal_on_track", m)

    def test_specific_goal_intents_are_still_distinguished(self):
        self.assertEqual(planmod._infer_named_goal_intent("whats my next milestone"),
                         "goal_next_milestone")
        self.assertEqual(planmod._infer_named_goal_intent("why is this my priority"),
                         "goal_why_priority")
        self.assertEqual(planmod._infer_named_goal_intent("how confident are you i'll hit it"),
                         "goal_confidence")

    def test_preroute_returns_the_focal_goal(self):
        intent, focal = planmod.named_goal_intent(
            "how am i doing towards France 2027",
            ["France 2027 Family 18K Mission", "Launch Whole Life Journey"], None)
        self.assertEqual(intent, "goal_on_track")
        self.assertTrue(focal and "france" in focal.lower())


class ScopeToFocalGoalTests(SimpleTestCase):
    def test_scoping_keeps_only_the_named_goal_and_drops_the_portfolio(self):
        scoped = stages._scope_to_focal_goal(_PORTFOLIO, "france")
        titles = [e["goal"] for e in scoped["goal_evidence"]]
        self.assertEqual(titles, ["France 2027 Family 18K Mission"])
        self.assertNotIn("active_goals", scoped)          # no portfolio enumeration
        self.assertEqual(scoped["other_active_goal_count"], 3)

    def test_scoping_no_match_leaves_facts_untouched(self):
        scoped = stages._scope_to_focal_goal(_PORTFOLIO, "nonexistent goal")
        self.assertEqual(len(scoped["goal_evidence"]), 4)

    def test_build_working_memory_scopes_a_goal_specific_intent(self):
        import unittest.mock as mock
        plan = planmod.synthesize_plan("goal_on_track", focal_goal="france")
        truth = {"goals_state": {"state": {}}, "habits_state": {"state": {}}}
        with mock.patch.dict(stages.INTENT_CURATORS,
                             {"goal_on_track": lambda t, u: dict(_PORTFOLIO)}):
            wm = stages.build_working_memory(plan, truth, None)
        ev = wm["facts"]["goal_evidence"]
        self.assertEqual([e["goal"] for e in ev], ["France 2027 Family 18K Mission"])

    def test_portfolio_intent_is_not_scoped(self):
        import unittest.mock as mock
        plan = planmod.synthesize_plan("goals_progress", focal_goal="france")
        truth = {"goals_state": {"state": {}}, "habits_state": {"state": {}}}
        with mock.patch.dict(stages.INTENT_CURATORS,
                             {"goals_progress": lambda t, u: dict(_PORTFOLIO)}):
            wm = stages.build_working_memory(plan, truth, None)
        # goals_progress is the deliberate PORTFOLIO intent — it keeps every goal.
        self.assertEqual(len(wm["facts"]["goal_evidence"]), 4)


class GoalOnTrackFallbackScopeTests(SimpleTestCase):
    def test_fallback_answers_only_the_named_goal_and_offers_the_rest(self):
        scoped = stages._scope_to_focal_goal(_PORTFOLIO, "france")
        out = stages._goal_on_track_fallback({"facts": scoped})
        self.assertIn("France 2027", out)
        for other in ("Launch Whole Life Journey", "Relationship with God", "Serve Others"):
            self.assertNotIn(other, out)
        # a single-sentence offer to review the others — never an unasked brief
        self.assertIn("other 3 goals", out)
        self.assertTrue(out.rstrip().endswith("?"))
