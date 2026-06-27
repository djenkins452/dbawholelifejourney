# ==============================================================================
# File: apps/ai/tests/test_foundational_routing.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Defect Class 1 — foundational Chief-of-Staff questions must ALWAYS
#   route to a deterministic intent by MEANING (not exact wording), with no goal
#   name, no deictic, and no planner/OpenAI. Prevents silent orchestration
#   termination / empty responses for the core CoS questions.
# ==============================================================================
from django.test import SimpleTestCase

from apps.ai.chatgpt_cos.reasoning import plan as planmod


class FoundationalGoalRoutingTests(SimpleTestCase):
    """The pre-router resolves mission-implicit goal questions with NO titles."""

    def _route(self, msg):
        # title-independent + OpenAI-independent (empty titles, no mission)
        return planmod.named_goal_intent(msg, [], None)[0]

    def test_next_milestone_variants(self):
        for q in ("What is my next milestone?", "What's the next checkpoint?",
                  "What's the next step toward my goal?", "Where should I be next?",
                  "What milestone am I working on now?", "What comes next in this mission?"):
            self.assertEqual(self._route(q), "goal_next_milestone", q)

    def test_why_priority_variants(self):
        for q in ("Why is this my highest priority goal?", "Why does this goal matter so much?",
                  "Why is this important?", "Why should I keep focusing on this mission?"):
            self.assertEqual(self._route(q), "goal_why_priority", q)

    def test_confidence_variants(self):
        for q in ("How confident are you that I'll achieve this?", "What are my odds of making it?",
                  "Do you think I'll be ready?", "How likely is success?",
                  "Am I going to make it?"):
            self.assertEqual(self._route(q), "goal_confidence", q)

    def test_on_track_variants(self):
        for q in ("Am I still on track?", "Am I on pace?", "Am I behind?",
                  "Do I need to adjust the timeline?"):
            self.assertEqual(self._route(q), "goal_on_track", q)

    def test_biggest_risk_variant(self):
        self.assertEqual(self._route("What is my biggest risk?"), "biggest_goal_risk")
        self.assertEqual(self._route("Which goal worries you most?"), "biggest_goal_risk")

    def test_health_questions_not_stolen_by_goal_prerouter(self):
        # health-context questions must NOT be claimed by the goal pre-router
        for q in ("How is my health?", "Am I on track with my health?",
                  "What is my biggest health risk?", "How healthy am I right now?",
                  "What is a healthy weight generally?"):
            self.assertIsNone(self._route(q), q)


class FoundationalDeterministicResilienceTests(SimpleTestCase):
    """The resilience matcher (used when the planner/OpenAI is down) routes the
    same foundational questions — goals AND health."""

    def test_goal_questions_route_when_planner_down(self):
        self.assertEqual(planmod.deterministic_intent("What is my next milestone?"),
                         "goal_next_milestone")
        self.assertEqual(planmod.deterministic_intent("How confident are you I'll achieve this?"),
                         "goal_confidence")

    def test_health_questions_route_when_planner_down(self):
        for q in ("How is my health?", "How healthy am I right now?",
                  "How am I doing physically?", "How's my health?"):
            self.assertEqual(planmod.deterministic_intent(q), "overall_progress", q)

    def test_health_context_not_routed_to_goals(self):
        # "on track with my health" -> not a goal intent (health-aware gate)
        self.assertIsNone(planmod._foundational_goal_intent("am i on track with my health"))

    def test_unrelated_questions_still_decline(self):
        for q in ("who was abraham lincoln", "thanks", "what is the weather"):
            self.assertIsNone(planmod.deterministic_intent(q), q)


class RhythmDoesNotStealGoalMilestoneTests(SimpleTestCase):
    def test_rhythm_lane_yields_milestone_questions_to_goals(self):
        from apps.ai.chatgpt_cos.lanes import _next_rhythm_lane
        # the guard returns before touching the rhythm API, so a dummy user is fine
        self.assertIsNone(_next_rhythm_lane(object(), "what's my next milestone"))
        self.assertIsNone(_next_rhythm_lane(object(), "what is my next checkpoint"))
