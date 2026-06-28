# ==============================================================================
# File: apps/ai/tests/test_reasoning_lane_deterministic_decline.py
# Description: Regression for DEFECT CLASS 2 — Personal Reasoning was consuming
#   deterministic status/count questions (workout/journal/appointments) and
#   producing generic health/sleep coaching. The reasoning lane must DECLINE these
#   so they fall through to deterministic retrieval (Law 0 + Law 4). Health
#   REASONING questions must still reach the planner (no regression).
# ==============================================================================
from unittest import mock

from django.test import SimpleTestCase

from apps.ai.chatgpt_cos import lanes

_DET = ["Did I workout today?", "Have I worked out today?", "Did I exercise today?",
        "Did I journal today?", "Have I journaled today?",
        "Do I have any appointments today?", "Any meetings today?",
        "What's on my calendar?", "Do I have anything scheduled today?"]

_REASONING = ["How is my health?", "What's my biggest health risk?",
              "How am I doing overall?", "Am I on track for my France goal?",
              "Why is this my top priority?"]


class DeterministicDeclineTests(SimpleTestCase):
    def test_detector_flags_deterministic_status_questions(self):
        for q in _DET:
            self.assertTrue(lanes._is_deterministic_status_question(q), q)

    def test_detector_preserves_reasoning_questions(self):
        for q in _REASONING:
            self.assertFalse(lanes._is_deterministic_status_question(q), q)

    def test_reasoning_lane_declines_deterministic_without_calling_planner(self):
        with mock.patch("apps.ai.chatgpt_cos.reasoning.answer_reasoning_question",
                        return_value={"answer": "PLANNER"}) as planner:
            for q in _DET:
                self.assertIsNone(lanes._reasoning_lane(mock.Mock(id=1), q), q)
            self.assertFalse(planner.called,
                             "planner must NOT run for deterministic status questions")

    def test_reasoning_lane_still_runs_planner_for_reasoning(self):
        with mock.patch("apps.ai.chatgpt_cos.reasoning.answer_reasoning_question",
                        return_value={"answer": "PLANNER"}) as planner:
            out = lanes._reasoning_lane(mock.Mock(id=1), "What's my biggest health risk?")
            self.assertEqual(out, {"answer": "PLANNER"})
            self.assertTrue(planner.called)
