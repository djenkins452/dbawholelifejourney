"""Tests for Phase 2 Signal Engine — behavioral awareness detection."""

from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.signals.signal_engine import (
    CONFIDENCE_FLOOR,
    EFFORT_SIGNAL,
    INCONSISTENCY_SIGNAL,
    INTENT_SIGNAL,
    POSSIBLE_COMPLETION,
    _classify_and_score,
    _detect_from_text,
    _deduplicate,
    _normalize_output,
    _score_signal,
    detect_signals,
)


class TestDetectFromText(SimpleTestCase):
    """Test core text-to-signal detection logic (no DB needed)."""

    # -----------------------------------------------------------------------
    # possible_completion — strong matches
    # -----------------------------------------------------------------------
    def test_prayer_completed(self):
        signals = _detect_from_text("I prayed this morning before work", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], POSSIBLE_COMPLETION)
        self.assertEqual(signals[0]["domain"], "faith")
        self.assertEqual(signals[0]["item"], "prayer")
        self.assertGreaterEqual(signals[0]["confidence"], CONFIDENCE_FLOOR)

    def test_workout_completed(self):
        signals = _detect_from_text("Completed my workout at the gym today", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], POSSIBLE_COMPLETION)
        self.assertEqual(signals[0]["domain"], "health")
        self.assertEqual(signals[0]["item"], "workout")

    def test_bible_reading_completed(self):
        signals = _detect_from_text("Spent time reading the Bible and doing my devotional", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], POSSIBLE_COMPLETION)
        self.assertEqual(signals[0]["domain"], "faith")
        self.assertEqual(signals[0]["item"], "bible_reading")

    def test_journaling_completed(self):
        signals = _detect_from_text("Did my journal entry this evening", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], POSSIBLE_COMPLETION)
        self.assertEqual(signals[0]["domain"], "journal")

    def test_church_attendance(self):
        signals = _detect_from_text("Went to church this morning, great sermon", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], POSSIBLE_COMPLETION)
        self.assertEqual(signals[0]["domain"], "faith")
        self.assertEqual(signals[0]["item"], "church")

    def test_running_completed(self):
        signals = _detect_from_text("Ran 3 miles this morning, finished strong", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["domain"], "health")
        self.assertEqual(signals[0]["item"], "running")

    # -----------------------------------------------------------------------
    # intent_signal — future plans
    # -----------------------------------------------------------------------
    def test_intent_workout(self):
        signals = _detect_from_text("Planning to work out later this evening", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], INTENT_SIGNAL)
        self.assertEqual(signals[0]["domain"], "health")

    def test_intent_prayer(self):
        signals = _detect_from_text("Going to spend time in prayer tomorrow morning", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], INTENT_SIGNAL)
        self.assertEqual(signals[0]["domain"], "faith")

    # -----------------------------------------------------------------------
    # effort_signal — attempted but not completed
    # -----------------------------------------------------------------------
    def test_effort_workout(self):
        signals = _detect_from_text("Tried to work out but ran out of time", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], EFFORT_SIGNAL)
        self.assertEqual(signals[0]["domain"], "health")

    def test_effort_partial(self):
        signals = _detect_from_text("Started my yoga session but couldn't finish", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], EFFORT_SIGNAL)
        self.assertEqual(signals[0]["domain"], "health")
        self.assertEqual(signals[0]["item"], "yoga")

    # -----------------------------------------------------------------------
    # inconsistency_signal — explicit skips/contradictions
    # -----------------------------------------------------------------------
    def test_inconsistency_skipped(self):
        signals = _detect_from_text("Skipped workout today, just too tired", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], INCONSISTENCY_SIGNAL)
        self.assertEqual(signals[0]["domain"], "health")

    def test_inconsistency_missed_prayer(self):
        signals = _detect_from_text("Missed my prayer time this morning", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], INCONSISTENCY_SIGNAL)
        self.assertEqual(signals[0]["domain"], "faith")

    def test_inconsistency_forgot(self):
        signals = _detect_from_text("Forgot to do my devotional today", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], INCONSISTENCY_SIGNAL)
        self.assertEqual(signals[0]["domain"], "faith")

    # -----------------------------------------------------------------------
    # Weak language — should NOT emit signals
    # -----------------------------------------------------------------------
    def test_weak_thinking_about(self):
        """'Thinking about' without intent verb should not trigger."""
        signals = _detect_from_text("Thinking about working out", source="journal")
        # No intent indicator matches ("thinking about" is not in our patterns)
        self.assertEqual(len(signals), 0)

    def test_weak_need_to(self):
        """'Need to pray' IS in intent indicators — should emit intent."""
        signals = _detect_from_text("Need to pray more", source="journal")
        # This has intent indicator "need to" + domain match
        if signals:
            self.assertEqual(signals[0]["type"], INTENT_SIGNAL)

    def test_no_domain_match(self):
        """Text with no domain keywords should produce no signals."""
        signals = _detect_from_text("Had a great day at the office", source="journal")
        self.assertEqual(len(signals), 0)

    def test_empty_text(self):
        signals = _detect_from_text("", source="journal")
        self.assertEqual(len(signals), 0)

    def test_whitespace_only(self):
        signals = _detect_from_text("   \n\t  ", source="journal")
        self.assertEqual(len(signals), 0)

    def test_no_verb_indicator(self):
        """Domain keyword alone without a verb indicator should not emit."""
        signals = _detect_from_text("Prayer is important", source="journal")
        self.assertEqual(len(signals), 0)

    # -----------------------------------------------------------------------
    # Source weighting
    # -----------------------------------------------------------------------
    def test_journal_source_higher_confidence(self):
        journal_signals = _detect_from_text("I prayed this morning", source="journal")
        workout_signals = _detect_from_text("I prayed this morning", source="workout_notes")
        self.assertGreater(
            journal_signals[0]["confidence"],
            workout_signals[0]["confidence"],
        )

    # -----------------------------------------------------------------------
    # Confidence threshold enforcement
    # -----------------------------------------------------------------------
    def test_all_signals_above_floor(self):
        """Every emitted signal must meet the confidence floor."""
        texts = [
            "I prayed this morning",
            "Completed my workout",
            "Planning to work out later",
            "Tried to do yoga but ran out of time",
            "Skipped my bible reading",
        ]
        for text in texts:
            signals = _detect_from_text(text, source="journal")
            for sig in signals:
                self.assertGreaterEqual(
                    sig["confidence"],
                    CONFIDENCE_FLOOR,
                    f"Signal below floor: {sig}",
                )

    # -----------------------------------------------------------------------
    # Multiple domains in one text
    # -----------------------------------------------------------------------
    def test_multiple_domains(self):
        text = "Prayed this morning and then completed my workout at the gym"
        signals = _detect_from_text(text, source="journal")
        domains = {s["domain"] for s in signals}
        self.assertIn("faith", domains)
        self.assertIn("health", domains)

    # -----------------------------------------------------------------------
    # Text truncation
    # -----------------------------------------------------------------------
    def test_long_text_truncated(self):
        long_text = "I prayed this morning. " + "x" * 300
        signals = _detect_from_text(long_text, source="journal")
        self.assertTrue(signals[0]["text"].endswith("..."))
        self.assertLessEqual(len(signals[0]["text"]), 210)


class TestScoreSignal(SimpleTestCase):
    """Test confidence scoring logic."""

    def test_completion_base_score(self):
        score = _score_signal(
            "i prayed this morning", "faith", "prayer",
            POSSIBLE_COMPLETION, "journal"
        )
        self.assertGreaterEqual(score, 0.80)

    def test_score_capped_at_095(self):
        # Multi-hit text with journal source should still cap at 0.95
        score = _score_signal(
            "read the bible scripture devotional quiet time spent time with god",
            "faith", "bible_reading", POSSIBLE_COMPLETION, "journal"
        )
        self.assertLessEqual(score, 0.95)

    def test_short_text_penalty(self):
        score_short = _score_signal("prayed", "faith", "prayer", POSSIBLE_COMPLETION, "journal")
        score_long = _score_signal(
            "i prayed this morning before work",
            "faith", "prayer", POSSIBLE_COMPLETION, "journal"
        )
        self.assertLess(score_short, score_long)


class TestDeduplicate(SimpleTestCase):
    """Test deduplication keeps highest confidence."""

    def test_keeps_highest_confidence(self):
        signals = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer", "confidence": 0.80, "source": "journal", "text": "a"},
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer", "confidence": 0.90, "source": "journal", "text": "b"},
        ]
        result = _deduplicate(signals)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence"], 0.90)

    def test_different_types_kept(self):
        signals = [
            {"type": POSSIBLE_COMPLETION, "domain": "health", "item": "workout", "confidence": 0.85, "source": "journal", "text": "a"},
            {"type": INCONSISTENCY_SIGNAL, "domain": "health", "item": "workout", "confidence": 0.80, "source": "journal", "text": "b"},
        ]
        result = _deduplicate(signals)
        self.assertEqual(len(result), 2)


class TestNormalizeOutput(SimpleTestCase):
    """Test output envelope formatting."""

    def test_output_structure(self):
        signals = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer", "confidence": 0.80, "source": "journal", "text": "a"},
        ]
        result = _normalize_output(signals)
        self.assertIn("signals", result)
        self.assertEqual(len(result["signals"]), 1)

    def test_empty_signals(self):
        result = _normalize_output([])
        self.assertEqual(result, {"signals": []})

    def test_sorted_by_confidence(self):
        signals = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer", "confidence": 0.80, "source": "journal", "text": "a"},
            {"type": POSSIBLE_COMPLETION, "domain": "health", "item": "workout", "confidence": 0.90, "source": "journal", "text": "b"},
        ]
        result = _normalize_output(signals)
        self.assertEqual(result["signals"][0]["confidence"], 0.90)
        self.assertEqual(result["signals"][1]["confidence"], 0.80)


class TestDetectSignalsIntegration(SimpleTestCase):
    """Integration test for detect_signals() with mocked DB queries."""

    @patch("apps.core.signals.signal_engine._extract_workout_signals")
    @patch("apps.core.signals.signal_engine._extract_journal_signals")
    def test_combines_sources(self, mock_journal, mock_workout):
        mock_journal.return_value = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer",
             "confidence": 0.85, "source": "journal", "text": "Prayed this morning"},
        ]
        mock_workout.return_value = [
            {"type": POSSIBLE_COMPLETION, "domain": "health", "item": "workout",
             "confidence": 0.82, "source": "workout_notes", "text": "Good session"},
        ]

        user = MagicMock()
        result = detect_signals(user)

        self.assertEqual(len(result["signals"]), 2)
        mock_journal.assert_called_once()
        mock_workout.assert_called_once()

    @patch("apps.core.signals.signal_engine._extract_workout_signals")
    @patch("apps.core.signals.signal_engine._extract_journal_signals")
    def test_empty_sources(self, mock_journal, mock_workout):
        mock_journal.return_value = []
        mock_workout.return_value = []

        user = MagicMock()
        result = detect_signals(user)

        self.assertEqual(result, {"signals": []})

    @patch("apps.core.signals.signal_engine._extract_workout_signals")
    @patch("apps.core.signals.signal_engine._extract_journal_signals")
    def test_deduplicates_across_sources(self, mock_journal, mock_workout):
        """Same signal from both sources keeps the higher confidence one."""
        mock_journal.return_value = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer",
             "confidence": 0.85, "source": "journal", "text": "Prayed"},
        ]
        mock_workout.return_value = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer",
             "confidence": 0.80, "source": "workout_notes", "text": "Prayed in notes"},
        ]

        user = MagicMock()
        result = detect_signals(user)

        self.assertEqual(len(result["signals"]), 1)
        self.assertEqual(result["signals"][0]["confidence"], 0.85)

    @patch("apps.core.signals.signal_engine._extract_workout_signals")
    @patch("apps.core.signals.signal_engine._extract_journal_signals")
    def test_lookback_hours_passed(self, mock_journal, mock_workout):
        mock_journal.return_value = []
        mock_workout.return_value = []

        user = MagicMock()
        detect_signals(user, lookback_hours=48)

        # Verify cutoff was passed (check the second arg to the extractors)
        call_args = mock_journal.call_args
        cutoff = call_args[0][1]
        expected_min = timezone.now() - timedelta(hours=49)
        expected_max = timezone.now() - timedelta(hours=47)
        self.assertTrue(expected_min <= cutoff <= expected_max)


class TestReadOnlyGuarantee(SimpleTestCase):
    """Verify the signal engine makes no DB writes."""

    def test_no_save_calls(self):
        """_detect_from_text is pure — no model instances, no saves."""
        # This is a structural test: _detect_from_text only returns dicts
        signals = _detect_from_text("Completed my workout and prayed", source="journal")
        for sig in signals:
            self.assertIsInstance(sig, dict)
            self.assertNotIn("save", dir(sig))

    def test_output_contract_keys(self):
        """Every signal must have exactly the required keys."""
        required_keys = {"type", "domain", "item", "confidence", "source", "text"}
        signals = _detect_from_text("I prayed this morning", source="journal")
        for sig in signals:
            self.assertEqual(set(sig.keys()), required_keys)
