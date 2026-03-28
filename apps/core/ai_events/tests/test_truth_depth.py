# ==============================================================================
# File: apps/core/ai_events/tests/test_truth_depth.py
# Project: Whole Life Journey
# Description: Tests for Truth Depth classifier
# ==============================================================================
"""
Tests for the Truth Depth classifier.

Validates that user messages are correctly classified into
SUMMARY, SIGNAL, or EVENT depth levels.
"""

from django.test import TestCase

from apps.core.ai_events.truth_depth import (
    DEPTH_EVENT,
    DEPTH_SIGNAL,
    DEPTH_SUMMARY,
    classify_event_query_type,
    classify_truth_depth,
    detect_domain_hint,
    needs_event_access,
)


class TruthDepthClassificationTest(TestCase):
    """Test that messages are classified to the correct truth depth."""

    # ── EVENT depth: missed queries ──

    def test_what_did_i_miss(self):
        self.assertEqual(classify_truth_depth("what did i miss"), DEPTH_EVENT)

    def test_what_have_i_missed(self):
        self.assertEqual(classify_truth_depth("what have i missed"), DEPTH_EVENT)

    def test_missed_dose(self):
        self.assertEqual(classify_truth_depth("missed dose"), DEPTH_EVENT)

    def test_missed_doses(self):
        self.assertEqual(classify_truth_depth("missed doses"), DEPTH_EVENT)

    def test_which_medication_did_i_miss(self):
        self.assertEqual(classify_truth_depth("which medication did i miss"), DEPTH_EVENT)

    def test_did_i_miss_anything(self):
        self.assertEqual(classify_truth_depth("did i miss anything"), DEPTH_EVENT)

    def test_what_routine_did_i_miss(self):
        self.assertEqual(classify_truth_depth("what routine did i miss"), DEPTH_EVENT)

    def test_missed_medications(self):
        self.assertEqual(classify_truth_depth("missed medications"), DEPTH_EVENT)

    # ── EVENT depth: timeline queries ──

    def test_what_happened_yesterday(self):
        self.assertEqual(classify_truth_depth("what happened yesterday"), DEPTH_EVENT)

    def test_what_happened_today(self):
        self.assertEqual(classify_truth_depth("what happened today"), DEPTH_EVENT)

    def test_what_did_i_do_yesterday(self):
        self.assertEqual(classify_truth_depth("what did i do yesterday"), DEPTH_EVENT)

    def test_show_me_yesterday(self):
        self.assertEqual(classify_truth_depth("show me yesterday"), DEPTH_EVENT)

    # ── EVENT depth: slippage queries ──

    def test_when_did_routine_start_slipping(self):
        self.assertEqual(classify_truth_depth("when did my routine start slipping"), DEPTH_EVENT)

    def test_when_did_i_start_missing(self):
        self.assertEqual(classify_truth_depth("when did i start missing"), DEPTH_EVENT)

    def test_when_did_i_fall_off(self):
        self.assertEqual(classify_truth_depth("when did i fall off"), DEPTH_EVENT)

    # ── SIGNAL depth ──

    def test_why_am_i_slipping(self):
        self.assertEqual(classify_truth_depth("why am i slipping"), DEPTH_SIGNAL)

    def test_what_caused_this(self):
        self.assertEqual(classify_truth_depth("what caused this"), DEPTH_SIGNAL)

    def test_what_patterns(self):
        self.assertEqual(classify_truth_depth("what patterns do you see"), DEPTH_SIGNAL)

    # ── SUMMARY depth (default) ──

    def test_how_am_i_doing(self):
        self.assertEqual(classify_truth_depth("how am i doing"), DEPTH_SUMMARY)

    def test_general_greeting(self):
        self.assertEqual(classify_truth_depth("good morning beth"), DEPTH_SUMMARY)

    def test_medication_status(self):
        """'did i take my meds' is a SUMMARY question (existing route handles it)."""
        self.assertEqual(classify_truth_depth("did i take my meds"), DEPTH_SUMMARY)

    def test_unrelated_question(self):
        self.assertEqual(classify_truth_depth("what's the weather like"), DEPTH_SUMMARY)


class NeedsEventAccessTest(TestCase):
    """Test the quick-check helper."""

    def test_missed_query_needs_event(self):
        self.assertTrue(needs_event_access("what did i miss"))

    def test_timeline_needs_event(self):
        self.assertTrue(needs_event_access("what happened yesterday"))

    def test_summary_does_not_need_event(self):
        self.assertFalse(needs_event_access("how am i doing"))

    def test_general_does_not_need_event(self):
        self.assertFalse(needs_event_access("hello beth"))


class EventQueryTypeTest(TestCase):
    """Test event query type classification."""

    def test_missed_type(self):
        self.assertEqual(classify_event_query_type("what did i miss"), "missed")

    def test_timeline_type(self):
        self.assertEqual(classify_event_query_type("what happened yesterday"), "timeline")

    def test_slippage_type(self):
        self.assertEqual(classify_event_query_type("when did my routine start slipping"), "slippage")

    def test_non_event_returns_none(self):
        self.assertIsNone(classify_event_query_type("how am i doing"))


class DomainHintTest(TestCase):
    """Test domain hint detection."""

    def test_medication_hint(self):
        self.assertEqual(detect_domain_hint("which medication did i miss"), "medication")

    def test_dose_hint(self):
        self.assertEqual(detect_domain_hint("what dose did i miss"), "medication")

    def test_routine_hint(self):
        self.assertEqual(detect_domain_hint("what routine did i miss"), "routine")

    def test_workout_hint(self):
        self.assertEqual(detect_domain_hint("did i miss a workout"), "workout")

    def test_no_hint(self):
        self.assertIsNone(detect_domain_hint("what did i miss"))
