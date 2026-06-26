# ==============================================================================
# File: apps/ai/tests/test_p25_shadow.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: P25 Personal Truth First — SHADOW classifier (no routing change).
# ==============================================================================
"""
Validates the deterministic P25 shadow classifier against the required example
table. SHADOW ONLY — these prove classification accuracy; routing is unchanged.
"""

from django.test import TestCase

from apps.ai.chatgpt_cos.p25_classifier import (
    LANE_TO_P25,
    classify_request,
    log_p25_shadow,
)


class P25ClassifierTests(TestCase):
    CASES = [
        ("What is my weight?", "PERSONAL"),
        ("How am I doing?", "PERSONAL"),
        ("Check in", "AMBIGUOUS"),
        ("What should I do next?", "PERSONAL"),
        ("Review my week", "PERSONAL"),
        ("Who was Abraham Lincoln?", "EXTERNAL"),
        ("Explain photosynthesis", "EXTERNAL"),
        ("What is Delphi?", "EXTERNAL"),
        ("Should I eat fruit?", "MIXED"),
        ("What's the best exercise for me?", "MIXED"),
    ]

    def test_required_example_table(self):
        for message, expected in self.CASES:
            got = classify_request(message)["classification"]
            self.assertEqual(got, expected, f"{message!r} -> {got} (want {expected})")

    def test_outputs_have_confidence_and_signal(self):
        r = classify_request("What is my weight?")
        self.assertIn("confidence", r)
        self.assertIn("signal", r)
        self.assertGreater(r["confidence"], 0.0)

    def test_explicit_general_overrides_domain(self):
        # 'how do people generally lose weight' -> EXTERNAL despite 'weight'
        self.assertEqual(
            classify_request("how do people generally lose weight")["classification"],
            "EXTERNAL")

    def test_empty_and_unclassified_are_ambiguous(self):
        self.assertEqual(classify_request("")["classification"], "AMBIGUOUS")
        self.assertEqual(classify_request("   ")["classification"], "AMBIGUOUS")

    def test_all_four_classes_are_reachable(self):
        classes = {classify_request(m)["classification"] for m, _ in self.CASES}
        self.assertEqual(classes, {"PERSONAL", "EXTERNAL", "MIXED", "AMBIGUOUS"})

    def test_lane_to_p25_mapping_complete(self):
        for lane in ("foundational_facts", "personal_reasoning", "next_rhythm",
                     "clarification", "clarification_reply", "general_conversation",
                     "tool_loop"):
            self.assertIn(lane, LANE_TO_P25)

    def test_log_p25_shadow_never_raises_and_returns_none(self):
        # shadow logging is side-effect-free w.r.t. routing
        self.assertIsNone(
            log_p25_shadow("Who was Abraham Lincoln?", current_lane="general_conversation"))
        self.assertIsNone(log_p25_shadow(None, current_lane="tool_loop"))
