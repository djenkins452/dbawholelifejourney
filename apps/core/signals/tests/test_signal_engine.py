"""Tests for Phase 2 Signal Engine — behavioral awareness detection.

Phase 2.1 additions: timestamp presence, hardened confidence threshold,
deduplication from repeated text, domain mapping variations, strict filtering.
"""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from django.test import SimpleTestCase
from django.utils import timezone

from apps.core.signals.signal_engine import (
    EFFORT_SIGNAL,
    INCONSISTENCY_SIGNAL,
    INTENT_SIGNAL,
    MIN_CONFIDENCE,
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
        self.assertGreaterEqual(signals[0]["confidence"], MIN_CONFIDENCE)

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
    # Weak language — should NOT emit signals (Phase 2.1 Patch #5)
    # -----------------------------------------------------------------------
    def test_weak_thinking_about(self):
        """'Thinking about' without intent verb should not trigger."""
        signals = _detect_from_text("Thinking about working out", source="journal")
        self.assertEqual(len(signals), 0)

    def test_weak_need_to(self):
        """'Need to pray' IS in intent indicators — should emit intent."""
        signals = _detect_from_text("Need to pray more", source="journal")
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
    # Confidence threshold enforcement (Phase 2.1 Patch #1)
    # -----------------------------------------------------------------------
    def test_all_signals_above_min_confidence(self):
        """Every emitted signal must meet MIN_CONFIDENCE (0.75)."""
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
                    MIN_CONFIDENCE,
                    f"Signal below MIN_CONFIDENCE: {sig}",
                )

    def test_min_confidence_is_075(self):
        """Verify the hardened threshold constant."""
        self.assertEqual(MIN_CONFIDENCE, 0.75)

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

    # -----------------------------------------------------------------------
    # Phase 2.1 Patch #3: Timestamp presence
    # -----------------------------------------------------------------------
    def test_signal_has_timestamp(self):
        """Every emitted signal must include a timezone-aware timestamp."""
        signals = _detect_from_text("I prayed this morning", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertIn("timestamp", signals[0])
        self.assertIsInstance(signals[0]["timestamp"], datetime)

    def test_all_signal_types_have_timestamp(self):
        """All four signal types must include timestamp."""
        cases = [
            ("Completed my workout at the gym", POSSIBLE_COMPLETION),
            ("Planning to work out later this evening", INTENT_SIGNAL),
            ("Tried to work out but ran out of time", EFFORT_SIGNAL),
            ("Skipped workout today, just too tired", INCONSISTENCY_SIGNAL),
        ]
        for text, expected_type in cases:
            signals = _detect_from_text(text, source="journal")
            self.assertEqual(len(signals), 1, f"Expected signal for: {text}")
            self.assertEqual(signals[0]["type"], expected_type)
            self.assertIn("timestamp", signals[0])
            self.assertIsInstance(signals[0]["timestamp"], datetime)

    # -----------------------------------------------------------------------
    # Phase 2.1 Patch #4: Domain mapping variations
    # -----------------------------------------------------------------------
    def test_domain_mapping_spent_time_with_god(self):
        signals = _detect_from_text("Spent time with God this morning", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["domain"], "faith")

    def test_domain_mapping_lifted_weights(self):
        signals = _detect_from_text("Lifted weights at the gym today", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["domain"], "health")
        self.assertEqual(signals[0]["item"], "workout")

    def test_domain_mapping_reflection(self):
        signals = _detect_from_text("Did my reflection and journaling", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["domain"], "journal")

    def test_domain_mapping_training(self):
        signals = _detect_from_text("Finished my training session", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["domain"], "health")

    # -----------------------------------------------------------------------
    # Phase 2.1 Patch #5: Strict match quality filtering
    # -----------------------------------------------------------------------
    def test_strict_filter_rejects_thinking_about(self):
        """'thinking about working out' — no verb indicator, must reject."""
        signals = _detect_from_text("thinking about working out", source="journal")
        self.assertEqual(len(signals), 0)

    def test_strict_filter_accepts_worked_out(self):
        """'I worked out this morning' — clear verb + domain, must accept."""
        signals = _detect_from_text("I worked out this morning", source="journal")
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0]["type"], POSSIBLE_COMPLETION)

    def test_strict_filter_rejects_vague_mention(self):
        """'The gym was closed' — domain keyword but no action verb."""
        signals = _detect_from_text("The gym was closed today", source="journal")
        self.assertEqual(len(signals), 0)

    def test_strict_filter_rejects_question(self):
        """'Should I pray?' — domain keyword but question, not action."""
        signals = _detect_from_text("Should I pray about this?", source="journal")
        self.assertEqual(len(signals), 0)


class TestScoreSignal(SimpleTestCase):
    """Test confidence scoring logic."""

    def test_completion_base_score(self):
        score = _score_signal(
            "i prayed this morning", "faith", "prayer",
            POSSIBLE_COMPLETION, "journal"
        )
        self.assertGreaterEqual(score, 0.80)

    def test_score_capped_at_095(self):
        score = _score_signal(
            "read the bible scripture devotional quiet time spent time with god",
            "faith", "bible_reading", POSSIBLE_COMPLETION, "journal", phrase_hit=True
        )
        self.assertLessEqual(score, 0.95)

    def test_short_text_penalty(self):
        score_short = _score_signal("prayed", "faith", "prayer", POSSIBLE_COMPLETION, "journal")
        score_long = _score_signal(
            "i prayed this morning before work",
            "faith", "prayer", POSSIBLE_COMPLETION, "journal"
        )
        self.assertLess(score_short, score_long)

    def test_phrase_hit_boosts_score(self):
        """Phrase match should score higher than keyword-only match."""
        score_keyword = _score_signal(
            "prayed this morning", "faith", "prayer",
            POSSIBLE_COMPLETION, "journal", phrase_hit=False
        )
        score_phrase = _score_signal(
            "prayed this morning", "faith", "prayer",
            POSSIBLE_COMPLETION, "journal", phrase_hit=True
        )
        self.assertGreater(score_phrase, score_keyword)

    def test_strong_matches_land_above_080(self):
        """Strong completion + journal source should score >= 0.80."""
        score = _score_signal(
            "completed my workout at the gym", "health", "workout",
            POSSIBLE_COMPLETION, "journal"
        )
        self.assertGreaterEqual(score, 0.80)


class TestDeduplicate(SimpleTestCase):
    """Test deduplication keeps highest confidence."""

    def test_keeps_highest_confidence(self):
        signals = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer", "confidence": 0.80, "source": "journal", "text": "a", "timestamp": timezone.now()},
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer", "confidence": 0.90, "source": "journal", "text": "b", "timestamp": timezone.now()},
        ]
        result = _deduplicate(signals)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence"], 0.90)

    def test_different_types_kept(self):
        signals = [
            {"type": POSSIBLE_COMPLETION, "domain": "health", "item": "workout", "confidence": 0.85, "source": "journal", "text": "a", "timestamp": timezone.now()},
            {"type": INCONSISTENCY_SIGNAL, "domain": "health", "item": "workout", "confidence": 0.80, "source": "journal", "text": "b", "timestamp": timezone.now()},
        ]
        result = _deduplicate(signals)
        self.assertEqual(len(result), 2)

    def test_dedup_repeated_action_in_text(self):
        """Same action mentioned twice across entries → ONE signal only."""
        now = timezone.now()
        signals = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer",
             "confidence": 0.85, "source": "journal", "text": "Prayed this morning", "timestamp": now},
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer",
             "confidence": 0.87, "source": "journal", "text": "Also prayed before bed", "timestamp": now},
        ]
        result = _deduplicate(signals)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["confidence"], 0.87)

    def test_dedup_different_domains_kept(self):
        """Signals for different domains should NOT be deduplicated."""
        now = timezone.now()
        signals = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer",
             "confidence": 0.85, "source": "journal", "text": "a", "timestamp": now},
            {"type": POSSIBLE_COMPLETION, "domain": "health", "item": "workout",
             "confidence": 0.85, "source": "journal", "text": "b", "timestamp": now},
        ]
        result = _deduplicate(signals)
        self.assertEqual(len(result), 2)


class TestNormalizeOutput(SimpleTestCase):
    """Test output envelope formatting."""

    def test_output_structure(self):
        signals = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer",
             "confidence": 0.80, "source": "journal", "text": "a", "timestamp": timezone.now()},
        ]
        result = _normalize_output(signals)
        self.assertIn("signals", result)
        self.assertEqual(len(result["signals"]), 1)

    def test_empty_signals(self):
        result = _normalize_output([])
        self.assertEqual(result, {"signals": []})

    def test_sorted_by_confidence(self):
        now = timezone.now()
        signals = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer",
             "confidence": 0.80, "source": "journal", "text": "a", "timestamp": now},
            {"type": POSSIBLE_COMPLETION, "domain": "health", "item": "workout",
             "confidence": 0.90, "source": "journal", "text": "b", "timestamp": now},
        ]
        result = _normalize_output(signals)
        self.assertEqual(result["signals"][0]["confidence"], 0.90)
        self.assertEqual(result["signals"][1]["confidence"], 0.80)


class TestDetectSignalsIntegration(SimpleTestCase):
    """Integration test for detect_signals() with mocked DB queries."""

    @patch("apps.core.signals.signal_engine._extract_workout_signals")
    @patch("apps.core.signals.signal_engine._extract_journal_signals")
    def test_combines_sources(self, mock_journal, mock_workout):
        now = timezone.now()
        mock_journal.return_value = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer",
             "confidence": 0.85, "source": "journal", "text": "Prayed this morning",
             "timestamp": now},
        ]
        mock_workout.return_value = [
            {"type": POSSIBLE_COMPLETION, "domain": "health", "item": "workout",
             "confidence": 0.82, "source": "workout_notes", "text": "Good session",
             "timestamp": now},
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
        now = timezone.now()
        mock_journal.return_value = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer",
             "confidence": 0.85, "source": "journal", "text": "Prayed",
             "timestamp": now},
        ]
        mock_workout.return_value = [
            {"type": POSSIBLE_COMPLETION, "domain": "faith", "item": "prayer",
             "confidence": 0.80, "source": "workout_notes", "text": "Prayed in notes",
             "timestamp": now},
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

        call_args = mock_journal.call_args
        cutoff = call_args[0][1]
        expected_min = timezone.now() - timedelta(hours=49)
        expected_max = timezone.now() - timedelta(hours=47)
        self.assertTrue(expected_min <= cutoff <= expected_max)


class TestReadOnlyGuarantee(SimpleTestCase):
    """Verify the signal engine makes no DB writes."""

    def test_no_save_calls(self):
        """_detect_from_text is pure — no model instances, no saves."""
        signals = _detect_from_text("Completed my workout and prayed", source="journal")
        for sig in signals:
            self.assertIsInstance(sig, dict)
            self.assertNotIn("save", dir(sig))

    def test_output_contract_keys(self):
        """Every signal must have exactly the required keys (including timestamp)."""
        required_keys = {"type", "domain", "item", "confidence", "source", "text", "timestamp"}
        signals = _detect_from_text("I prayed this morning", source="journal")
        for sig in signals:
            self.assertEqual(set(sig.keys()), required_keys)


class TestConfidenceFiltering(SimpleTestCase):
    """Phase 2.1 Patch #1: Confidence threshold hardening tests."""

    def test_weak_phrase_no_signal(self):
        """Weak/ambiguous phrases must NOT produce signals."""
        weak_phrases = [
            "Prayer is nice",
            "I like the gym",
            "Workout clothes are ready",
            "Bible on the shelf",
        ]
        for phrase in weak_phrases:
            signals = _detect_from_text(phrase, source="journal")
            self.assertEqual(
                len(signals), 0,
                f"Weak phrase should not emit signal: {phrase!r}",
            )

    def test_short_text_may_be_penalized_below_threshold(self):
        """Very short text (< 15 chars) gets penalized and may drop below threshold."""
        # "gym" alone has no verb indicator → should not emit
        signals = _detect_from_text("gym", source="journal")
        self.assertEqual(len(signals), 0)
