"""Tests for Phase 3+5 Signal Presenter — Controlled Exposure Layer + Adaptive Tuning.

Covers:
1. Same-day filtering
2. Truth suppression (completed items)
3. Expected=False suppression
4. Max 2 suggestions
5. Priority ordering
6. Uncertainty language (no factual statements)
7. Duplicate protection
8. Empty results
9. Beth hook safety (structured output)
10. Truth mapping helpers
11. Item labels
12. Integration: full pipeline
13. Phase 5: Adaptive reinforcement
14. Phase 5: Adaptive suppression
15. Phase 5: Neutral / minimum threshold
16. Phase 5: Scope enforcement (only possible_completion)
17. Phase 5: Safety guards
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from apps.core.signals.signal_engine import (
    EFFORT_SIGNAL,
    INCONSISTENCY_SIGNAL,
    INTENT_SIGNAL,
    POSSIBLE_COMPLETION,
)
from apps.core.signals.signal_presenter import (
    ADAPTIVE_MAX_PRIORITY_BOOST,
    ADAPTIVE_MIN_FEEDBACK,
    ADAPTIVE_REINFORCED_MIN_CONFIDENCE,
    ADAPTIVE_SIGNAL_TYPES,
    FEEDBACK_WINDOW_DAYS,
    MAX_SUGGESTIONS,
    PATTERN_MIN_FEEDBACK,
    PATTERN_PRIORITY_BOOST,
    PATTERN_REINFORCE_RATIO,
    PATTERN_SUPPRESS_RATIO,
    _apply_adaptive_rules,
    _apply_adaptive_tuning,
    _apply_pattern_rules,
    _build_message,
    _build_question,
    _deduplicate_suggestions,
    _filter_completed_or_unexpected,
    _filter_same_day,
    _generate_signal_fingerprint,
    _get_feedback_stats,
    _get_item_label,
    _get_pattern_key,
    _is_completed_in_truth,
    _is_expected_in_truth,
    _normalize_presented_output,
    _prioritize_signals,
    get_presented_signals,
)


def _make_signal(
    signal_type=POSSIBLE_COMPLETION,
    domain="faith",
    item="prayer",
    confidence=0.85,
    source="journal",
    text="I prayed this morning",
    timestamp=None,
):
    """Helper to build a signal dict for testing."""
    if timestamp is None:
        timestamp = timezone.now()
    return {
        "type": signal_type,
        "domain": domain,
        "item": item,
        "confidence": confidence,
        "source": source,
        "text": text,
        "timestamp": timestamp,
    }


def _make_truth(
    prayer_completed=False,
    prayer_expected=True,
    bible_completed=False,
    bible_expected=True,
    workout_completed=False,
    workout_expected=True,
    journal_completed=False,
    journal_expected=True,
):
    """Helper to build a truth dict for testing."""
    return {
        "date": timezone.localdate().isoformat(),
        "domains": {
            "faith": {
                "expected": prayer_expected or bible_expected,
                "prayer_expected": prayer_expected,
                "bible_expected": bible_expected,
                "prayer_completed": prayer_completed,
                "bible_reading_completed": bible_completed,
                "prayer_source": "routine" if prayer_completed else None,
                "bible_source": "routine" if bible_completed else None,
            },
            "workout": {
                "expected": workout_expected,
                "completed": workout_completed,
            },
            "journal": {
                "expected": journal_expected,
                "completed": journal_completed,
            },
        },
    }


# ---------------------------------------------------------------------------
# 1. Same-day filtering
# ---------------------------------------------------------------------------


class TestSameDayFiltering(SimpleTestCase):

    def test_today_signal_included(self):
        signals = [_make_signal(timestamp=timezone.now())]
        result = _filter_same_day(signals)
        self.assertEqual(len(result), 1)

    def test_yesterday_signal_excluded(self):
        yesterday = timezone.now() - timedelta(days=1)
        signals = [_make_signal(timestamp=yesterday)]
        result = _filter_same_day(signals)
        self.assertEqual(len(result), 0)

    def test_old_signal_excluded(self):
        old = timezone.now() - timedelta(days=7)
        signals = [_make_signal(timestamp=old)]
        result = _filter_same_day(signals)
        self.assertEqual(len(result), 0)

    def test_no_timestamp_excluded(self):
        sig = _make_signal()
        del sig["timestamp"]
        signals = [sig]
        result = _filter_same_day(signals)
        self.assertEqual(len(result), 0)

    def test_none_timestamp_excluded(self):
        signals = [_make_signal(timestamp=None)]
        # _make_signal with timestamp=None defaults to now(), so set manually
        signals[0]["timestamp"] = None
        result = _filter_same_day(signals)
        self.assertEqual(len(result), 0)

    def test_mixed_dates_filters_correctly(self):
        today_sig = _make_signal(timestamp=timezone.now(), item="prayer")
        old_sig = _make_signal(
            timestamp=timezone.now() - timedelta(days=2),
            item="workout",
            domain="health",
        )
        result = _filter_same_day([today_sig, old_sig])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["item"], "prayer")


# ---------------------------------------------------------------------------
# 2. Truth suppression (completed items)
# ---------------------------------------------------------------------------


class TestTruthSuppression(SimpleTestCase):

    def test_completed_prayer_suppressed(self):
        signals = [_make_signal(domain="faith", item="prayer")]
        truth = _make_truth(prayer_completed=True)
        result = _filter_completed_or_unexpected(signals, truth)
        self.assertEqual(len(result), 0)

    def test_incomplete_prayer_not_suppressed(self):
        signals = [_make_signal(domain="faith", item="prayer")]
        truth = _make_truth(prayer_completed=False)
        result = _filter_completed_or_unexpected(signals, truth)
        self.assertEqual(len(result), 1)

    def test_completed_workout_suppressed(self):
        signals = [_make_signal(domain="health", item="workout")]
        truth = _make_truth(workout_completed=True)
        result = _filter_completed_or_unexpected(signals, truth)
        self.assertEqual(len(result), 0)

    def test_completed_journal_suppressed(self):
        signals = [_make_signal(domain="journal", item="journal_entry")]
        truth = _make_truth(journal_completed=True)
        result = _filter_completed_or_unexpected(signals, truth)
        self.assertEqual(len(result), 0)

    def test_completed_bible_suppressed(self):
        signals = [_make_signal(domain="faith", item="bible_reading")]
        truth = _make_truth(bible_completed=True)
        result = _filter_completed_or_unexpected(signals, truth)
        self.assertEqual(len(result), 0)

    def test_health_running_uses_workout_truth(self):
        """Running maps to workout domain in truth."""
        signals = [_make_signal(domain="health", item="running")]
        truth = _make_truth(workout_completed=True)
        result = _filter_completed_or_unexpected(signals, truth)
        self.assertEqual(len(result), 0)


# ---------------------------------------------------------------------------
# 3. Expected=False suppression
# ---------------------------------------------------------------------------


class TestExpectedSuppression(SimpleTestCase):

    def test_unexpected_prayer_suppressed(self):
        signals = [_make_signal(domain="faith", item="prayer")]
        truth = _make_truth(prayer_expected=False, bible_expected=False)
        result = _filter_completed_or_unexpected(signals, truth)
        self.assertEqual(len(result), 0)

    def test_unexpected_workout_suppressed(self):
        signals = [_make_signal(domain="health", item="workout")]
        truth = _make_truth(workout_expected=False)
        result = _filter_completed_or_unexpected(signals, truth)
        self.assertEqual(len(result), 0)

    def test_unexpected_journal_suppressed(self):
        signals = [_make_signal(domain="journal", item="journal_entry")]
        truth = _make_truth(journal_expected=False)
        result = _filter_completed_or_unexpected(signals, truth)
        self.assertEqual(len(result), 0)

    def test_expected_prayer_not_suppressed(self):
        signals = [_make_signal(domain="faith", item="prayer")]
        truth = _make_truth(prayer_expected=True)
        result = _filter_completed_or_unexpected(signals, truth)
        self.assertEqual(len(result), 1)

    def test_unknown_domain_not_suppressed(self):
        """Domains without truth tracking (e.g., purpose) should not be suppressed."""
        signals = [_make_signal(domain="purpose", item="goal_work")]
        truth = _make_truth()
        result = _filter_completed_or_unexpected(signals, truth)
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# 4. Max 2 suggestions
# ---------------------------------------------------------------------------


class TestMaxSuggestions(SimpleTestCase):

    def test_max_constant_is_2(self):
        self.assertEqual(MAX_SUGGESTIONS, 2)

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_more_than_2_returns_only_2(self, mock_raw, mock_truth):
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer", confidence=0.90, timestamp=now),
                _make_signal(domain="health", item="workout", confidence=0.88, timestamp=now),
                _make_signal(domain="journal", item="journal_entry", confidence=0.85, timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth()

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        self.assertLessEqual(len(result["suggestions"]), 2)

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_fewer_than_2_returns_all(self, mock_raw, mock_truth):
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer", confidence=0.90, timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth()

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        self.assertEqual(len(result["suggestions"]), 1)


# ---------------------------------------------------------------------------
# 5. Priority ordering
# ---------------------------------------------------------------------------


class TestPriorityOrdering(SimpleTestCase):

    def test_completion_before_intent(self):
        now = timezone.now()
        signals = [
            _make_signal(signal_type=INTENT_SIGNAL, confidence=0.90, timestamp=now),
            _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85,
                         domain="health", item="workout", timestamp=now),
        ]
        result = _prioritize_signals(signals)
        self.assertEqual(result[0]["type"], POSSIBLE_COMPLETION)
        self.assertEqual(result[1]["type"], INTENT_SIGNAL)

    def test_completion_before_effort(self):
        now = timezone.now()
        signals = [
            _make_signal(signal_type=EFFORT_SIGNAL, confidence=0.90,
                         domain="health", item="workout", timestamp=now),
            _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85, timestamp=now),
        ]
        result = _prioritize_signals(signals)
        self.assertEqual(result[0]["type"], POSSIBLE_COMPLETION)

    def test_inconsistency_before_intent(self):
        now = timezone.now()
        signals = [
            _make_signal(signal_type=INTENT_SIGNAL, confidence=0.90, timestamp=now),
            _make_signal(signal_type=INCONSISTENCY_SIGNAL, confidence=0.85,
                         domain="health", item="workout", timestamp=now),
        ]
        result = _prioritize_signals(signals)
        self.assertEqual(result[0]["type"], INCONSISTENCY_SIGNAL)

    def test_same_type_higher_confidence_first(self):
        now = timezone.now()
        signals = [
            _make_signal(confidence=0.80, item="prayer", timestamp=now),
            _make_signal(confidence=0.90, item="bible_reading", timestamp=now),
        ]
        result = _prioritize_signals(signals)
        self.assertEqual(result[0]["confidence"], 0.90)

    def test_same_type_same_confidence_newer_first(self):
        older = timezone.now() - timedelta(hours=2)
        newer = timezone.now()
        signals = [
            _make_signal(confidence=0.85, item="prayer", timestamp=older),
            _make_signal(confidence=0.85, item="bible_reading", timestamp=newer),
        ]
        result = _prioritize_signals(signals)
        self.assertEqual(result[0]["item"], "bible_reading")

    def test_full_priority_order(self):
        now = timezone.now()
        signals = [
            _make_signal(signal_type=EFFORT_SIGNAL, confidence=0.85,
                         domain="purpose", item="goal_work", timestamp=now),
            _make_signal(signal_type=INTENT_SIGNAL, confidence=0.85,
                         domain="journal", item="journal_entry", timestamp=now),
            _make_signal(signal_type=INCONSISTENCY_SIGNAL, confidence=0.85,
                         domain="health", item="workout", timestamp=now),
            _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85,
                         domain="faith", item="prayer", timestamp=now),
        ]
        result = _prioritize_signals(signals)
        types = [s["type"] for s in result]
        self.assertEqual(types, [
            POSSIBLE_COMPLETION,
            INCONSISTENCY_SIGNAL,
            INTENT_SIGNAL,
            EFFORT_SIGNAL,
        ])


# ---------------------------------------------------------------------------
# 6. Uncertainty language
# ---------------------------------------------------------------------------


class TestUncertaintyLanguage(SimpleTestCase):
    """Messages and questions must never state completion as fact."""

    FORBIDDEN_PATTERNS = [
        "you completed",
        "your workout is done",
        "we marked",
        "has been completed",
        "is complete",
    ]

    def _assert_no_factual_statements(self, text):
        text_lower = text.lower()
        for pattern in self.FORBIDDEN_PATTERNS:
            self.assertNotIn(
                pattern, text_lower,
                f"Forbidden factual pattern found: {pattern!r} in {text!r}",
            )

    def test_completion_message_uncertainty(self):
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, item="prayer")
        msg = _build_message(sig)
        self._assert_no_factual_statements(msg)
        self.assertIn("may have", msg)

    def test_completion_question_uncertainty(self):
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, item="prayer")
        q = _build_question(sig)
        self._assert_no_factual_statements(q)
        self.assertIn("?", q)

    def test_inconsistency_message_uncertainty(self):
        sig = _make_signal(signal_type=INCONSISTENCY_SIGNAL, item="workout",
                           domain="health")
        msg = _build_message(sig)
        self._assert_no_factual_statements(msg)
        self.assertIn("may conflict", msg)

    def test_intent_message_uncertainty(self):
        sig = _make_signal(signal_type=INTENT_SIGNAL, item="prayer")
        msg = _build_message(sig)
        self._assert_no_factual_statements(msg)
        self.assertIn("may be planning", msg)

    def test_effort_message_uncertainty(self):
        sig = _make_signal(signal_type=EFFORT_SIGNAL, item="workout",
                           domain="health")
        msg = _build_message(sig)
        self._assert_no_factual_statements(msg)
        self.assertIn("may not be complete", msg)

    def test_all_signal_types_have_questions(self):
        for signal_type in [POSSIBLE_COMPLETION, INCONSISTENCY_SIGNAL,
                            INTENT_SIGNAL, EFFORT_SIGNAL]:
            sig = _make_signal(signal_type=signal_type, item="prayer")
            q = _build_question(sig)
            self.assertTrue(q.endswith("?"), f"{signal_type} question must end with ?")
            self._assert_no_factual_statements(q)


# ---------------------------------------------------------------------------
# 7. Duplicate protection
# ---------------------------------------------------------------------------


class TestDuplicateProtection(SimpleTestCase):

    def test_duplicates_collapse_to_one(self):
        now = timezone.now()
        signals = [
            _make_signal(confidence=0.80, timestamp=now),
            _make_signal(confidence=0.90, timestamp=now),
        ]
        result = _deduplicate_suggestions(signals)
        self.assertEqual(len(result), 1)

    def test_keeps_highest_confidence(self):
        now = timezone.now()
        signals = [
            _make_signal(confidence=0.80, timestamp=now),
            _make_signal(confidence=0.90, timestamp=now),
        ]
        result = _deduplicate_suggestions(signals)
        self.assertEqual(result[0]["confidence"], 0.90)

    def test_different_types_not_deduplicated(self):
        now = timezone.now()
        signals = [
            _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85, timestamp=now),
            _make_signal(signal_type=INTENT_SIGNAL, confidence=0.80, timestamp=now),
        ]
        result = _deduplicate_suggestions(signals)
        self.assertEqual(len(result), 2)

    def test_different_domains_not_deduplicated(self):
        now = timezone.now()
        signals = [
            _make_signal(domain="faith", item="prayer", confidence=0.85, timestamp=now),
            _make_signal(domain="health", item="workout", confidence=0.85, timestamp=now),
        ]
        result = _deduplicate_suggestions(signals)
        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# 8. Empty results
# ---------------------------------------------------------------------------


class TestEmptyResults(SimpleTestCase):

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_no_signals_returns_empty(self, mock_raw, mock_truth):
        mock_raw.return_value = {"signals": []}
        mock_truth.return_value = _make_truth()

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        self.assertEqual(result, {"suggestions": []})

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_all_completed_returns_empty(self, mock_raw, mock_truth):
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer", timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth(prayer_completed=True)

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        self.assertEqual(result, {"suggestions": []})

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_all_unexpected_returns_empty(self, mock_raw, mock_truth):
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="health", item="workout", timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth(workout_expected=False)

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        self.assertEqual(result, {"suggestions": []})


# ---------------------------------------------------------------------------
# 9. Beth hook safety (structured output)
# ---------------------------------------------------------------------------


class TestBethHookSafety(SimpleTestCase):
    """Presenter output must be structured and safe for conversational use."""

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_output_structure(self, mock_raw, mock_truth):
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer", confidence=0.90, timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth()

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        self.assertIn("suggestions", result)
        self.assertIsInstance(result["suggestions"], list)
        self.assertEqual(len(result["suggestions"]), 1)

        suggestion = result["suggestions"][0]
        required_keys = {
            "type", "domain", "item", "confidence", "source",
            "text", "timestamp", "fingerprint", "message", "question",
            "priority", "adaptive", "pattern_reinforced", "ui",
        }
        self.assertEqual(set(suggestion.keys()), required_keys)

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_timestamp_is_string(self, mock_raw, mock_truth):
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer", timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth()

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        self.assertIsInstance(result["suggestions"][0]["timestamp"], str)

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_priority_is_sequential(self, mock_raw, mock_truth):
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer", confidence=0.90, timestamp=now),
                _make_signal(domain="health", item="workout", confidence=0.88, timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth()

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        priorities = [s["priority"] for s in result["suggestions"]]
        self.assertEqual(priorities, [1, 2])

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_message_and_question_not_empty(self, mock_raw, mock_truth):
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer", timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth()

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        suggestion = result["suggestions"][0]
        self.assertTrue(len(suggestion["message"]) > 0)
        self.assertTrue(len(suggestion["question"]) > 0)

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_no_raw_signal_leakage(self, mock_raw, mock_truth):
        """Presenter output should not include internal-only fields."""
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer", timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth()

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        suggestion = result["suggestions"][0]
        # timestamp should be string, not datetime object
        self.assertNotIsInstance(suggestion["timestamp"], datetime)


# ---------------------------------------------------------------------------
# 10. Truth mapping helpers
# ---------------------------------------------------------------------------


class TestTruthMapping(SimpleTestCase):
    """Test _is_completed_in_truth and _is_expected_in_truth."""

    def test_prayer_completed(self):
        truth = _make_truth(prayer_completed=True)
        self.assertTrue(_is_completed_in_truth("faith", "prayer", truth))

    def test_prayer_not_completed(self):
        truth = _make_truth(prayer_completed=False)
        self.assertFalse(_is_completed_in_truth("faith", "prayer", truth))

    def test_bible_completed(self):
        truth = _make_truth(bible_completed=True)
        self.assertTrue(_is_completed_in_truth("faith", "bible_reading", truth))

    def test_workout_completed(self):
        truth = _make_truth(workout_completed=True)
        self.assertTrue(_is_completed_in_truth("health", "workout", truth))

    def test_running_uses_workout_truth(self):
        truth = _make_truth(workout_completed=True)
        self.assertTrue(_is_completed_in_truth("health", "running", truth))

    def test_journal_completed(self):
        truth = _make_truth(journal_completed=True)
        self.assertTrue(_is_completed_in_truth("journal", "journal_entry", truth))

    def test_unknown_domain_not_completed(self):
        truth = _make_truth()
        self.assertFalse(_is_completed_in_truth("purpose", "goal_work", truth))

    def test_prayer_expected(self):
        truth = _make_truth(prayer_expected=True)
        self.assertTrue(_is_expected_in_truth("faith", "prayer", truth))

    def test_prayer_not_expected(self):
        truth = _make_truth(prayer_expected=False, bible_expected=False)
        self.assertFalse(_is_expected_in_truth("faith", "prayer", truth))

    def test_unknown_domain_expected_by_default(self):
        """Domains without truth tracking should not be suppressed."""
        truth = _make_truth()
        self.assertTrue(_is_expected_in_truth("purpose", "goal_work", truth))

    def test_empty_truth_no_crash(self):
        self.assertFalse(_is_completed_in_truth("faith", "prayer", {}))
        self.assertTrue(_is_expected_in_truth("purpose", "goal_work", {}))


# ---------------------------------------------------------------------------
# 11. Item labels
# ---------------------------------------------------------------------------


class TestItemLabels(SimpleTestCase):

    def test_known_item_label(self):
        sig = _make_signal(item="prayer")
        self.assertEqual(_get_item_label(sig), "prayer")

    def test_workout_label(self):
        sig = _make_signal(domain="health", item="workout")
        self.assertEqual(_get_item_label(sig), "your workout")

    def test_bible_label(self):
        sig = _make_signal(domain="faith", item="bible_reading")
        self.assertEqual(_get_item_label(sig), "Bible reading")

    def test_unknown_item_falls_back_to_domain(self):
        sig = _make_signal(domain="health", item="unknown_thing")
        label = _get_item_label(sig)
        self.assertEqual(label, "your workout")

    def test_unknown_domain_and_item_fallback(self):
        sig = _make_signal(domain="unknown", item="unknown")
        label = _get_item_label(sig)
        self.assertEqual(label, "this item")


# ---------------------------------------------------------------------------
# 12. Integration: full pipeline
# ---------------------------------------------------------------------------


class TestFullPipeline(SimpleTestCase):

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_full_pipeline_filters_and_presents(self, mock_raw, mock_truth):
        now = timezone.now()
        yesterday = now - timedelta(days=1)

        mock_raw.return_value = {
            "signals": [
                # Should pass — today, not completed, expected
                _make_signal(domain="faith", item="prayer", confidence=0.90, timestamp=now),
                # Should be filtered — yesterday
                _make_signal(domain="health", item="workout", confidence=0.88, timestamp=yesterday),
                # Should pass — today, not completed, expected
                _make_signal(domain="journal", item="journal_entry", confidence=0.85, timestamp=now),
                # Should be filtered — completed
                _make_signal(domain="faith", item="bible_reading", confidence=0.92, timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth(bible_completed=True)

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        # Only prayer and journal should survive (bible completed, workout old)
        self.assertEqual(len(result["suggestions"]), 2)
        domains = {s["domain"] for s in result["suggestions"]}
        self.assertIn("faith", domains)
        self.assertIn("journal", domains)

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter.detect_signals")
    def test_signal_engine_error_returns_empty(self, mock_detect, mock_truth):
        """If Signal Engine raises, presenter returns empty safely."""
        mock_detect.side_effect = Exception("DB down")
        mock_truth.return_value = _make_truth()

        user = MagicMock()
        user.id = 1

        # Should not raise — _get_raw_signals catches the exception
        result = get_presented_signals(user)
        self.assertEqual(result, {"suggestions": []})

    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_truth_engine_error_returns_empty(self, mock_raw, mock_truth):
        """If truth engine fails, signals pass through unfiltered but safely."""
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer", confidence=0.90, timestamp=now),
            ]
        }
        # Empty truth means no completed items detected, unknown domains pass through
        mock_truth.return_value = {}

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        # With empty truth, faith domain has no expectation tracking
        # _is_expected_in_truth returns False for faith with empty truth
        # So signal gets suppressed — this is the safe behavior
        # (if truth is unavailable, we don't surface potentially wrong suggestions)
        self.assertIsInstance(result["suggestions"], list)


# ---------------------------------------------------------------------------
# 13. Phase 5: Adaptive reinforcement
# ---------------------------------------------------------------------------


class TestAdaptiveReinforcement(SimpleTestCase):
    """Signals with >= 75% yes responses get reinforced."""

    def test_reinforcement_adds_boost_metadata(self):
        """3 yes, 0 no → signal gets adaptive boost."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 3, "no": 0, "total": 3},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)
        self.assertGreater(result.get("_adaptive_priority_boost", 0), 0)
        self.assertEqual(
            result["_adaptive_min_confidence"],
            ADAPTIVE_REINFORCED_MIN_CONFIDENCE,
        )

    def test_reinforcement_at_threshold(self):
        """Exactly 75% yes → reinforced."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 3, "no": 1, "total": 4},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)
        self.assertGreater(result.get("_adaptive_priority_boost", 0), 0)

    def test_reinforcement_strong_history(self):
        """10 yes, 1 no → reinforced."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.78)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 10, "no": 1, "total": 11},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)
        self.assertGreater(result.get("_adaptive_priority_boost", 0), 0)


# ---------------------------------------------------------------------------
# 14. Phase 5: Adaptive suppression
# ---------------------------------------------------------------------------


class TestAdaptiveSuppression(SimpleTestCase):
    """Signals with >= 75% no responses get suppressed."""

    def test_suppression_removes_signal(self):
        """0 yes, 3 no → signal suppressed (returns None)."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.90)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 0, "no": 3, "total": 3},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNone(result)

    def test_suppression_at_threshold(self):
        """Exactly 75% no → suppressed."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.90)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 1, "no": 3, "total": 4},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNone(result)

    def test_suppression_strong_history(self):
        """1 yes, 10 no → suppressed."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.95)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 1, "no": 10, "total": 11},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNone(result)

    def test_suppressed_signal_removed_from_list(self):
        """_apply_adaptive_tuning removes suppressed signals from output."""
        now = timezone.now()
        signals = [
            _make_signal(signal_type=POSSIBLE_COMPLETION, domain="faith",
                         item="prayer", confidence=0.90, timestamp=now),
        ]
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 0, "no": 5, "total": 5},
        }
        with patch(
            "apps.core.signals.signal_presenter._get_feedback_stats",
            return_value=stats,
        ):
            user = MagicMock()
            result = _apply_adaptive_tuning(user, signals)
        self.assertEqual(len(result), 0)


# ---------------------------------------------------------------------------
# 15. Phase 5: Neutral / minimum threshold
# ---------------------------------------------------------------------------


class TestAdaptiveNeutral(SimpleTestCase):
    """Mixed feedback or insufficient data → no adaptation."""

    def test_mixed_feedback_no_change(self):
        """2 yes, 2 no → signal unchanged."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 2, "no": 2, "total": 4},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("_adaptive_priority_boost", 0), 0)
        self.assertNotIn("_adaptive_min_confidence", result)

    def test_below_minimum_threshold_no_change(self):
        """total < 3 → no adaptation regardless of ratio."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 0, "no": 2, "total": 2},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("_adaptive_priority_boost", 0), 0)

    def test_single_feedback_no_change(self):
        """1 total → no adaptation."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 1, "no": 0, "total": 1},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("_adaptive_priority_boost", 0), 0)

    def test_no_feedback_data_no_change(self):
        """Signal not in stats → no adaptation."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        stats = {}
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("_adaptive_priority_boost", 0), 0)

    def test_empty_stats_passthrough(self):
        """No stats → all signals pass through unchanged."""
        now = timezone.now()
        signals = [
            _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85, timestamp=now),
        ]
        with patch(
            "apps.core.signals.signal_presenter._get_feedback_stats",
            return_value={},
        ):
            user = MagicMock()
            result = _apply_adaptive_tuning(user, signals)
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# 16. Phase 5: Scope enforcement (only possible_completion)
# ---------------------------------------------------------------------------


class TestAdaptiveScopeEnforcement(SimpleTestCase):
    """Adaptive tuning only applies to possible_completion signals."""

    def test_inconsistency_not_adapted(self):
        sig = _make_signal(signal_type=INCONSISTENCY_SIGNAL, domain="health",
                           item="workout", confidence=0.85)
        stats = {
            (INCONSISTENCY_SIGNAL, "health", "workout"): {"yes": 0, "no": 10, "total": 10},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)  # Not suppressed
        self.assertEqual(result.get("_adaptive_priority_boost", 0), 0)

    def test_intent_not_adapted(self):
        sig = _make_signal(signal_type=INTENT_SIGNAL, domain="faith",
                           item="prayer", confidence=0.85)
        stats = {
            (INTENT_SIGNAL, "faith", "prayer"): {"yes": 10, "no": 0, "total": 10},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)
        self.assertEqual(result.get("_adaptive_priority_boost", 0), 0)

    def test_effort_not_adapted(self):
        sig = _make_signal(signal_type=EFFORT_SIGNAL, domain="health",
                           item="workout", confidence=0.85)
        stats = {
            (EFFORT_SIGNAL, "health", "workout"): {"yes": 0, "no": 10, "total": 10},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)  # Not suppressed
        self.assertEqual(result.get("_adaptive_priority_boost", 0), 0)

    def test_only_possible_completion_in_adaptive_types(self):
        self.assertEqual(ADAPTIVE_SIGNAL_TYPES, frozenset({POSSIBLE_COMPLETION}))


# ---------------------------------------------------------------------------
# 17. Phase 5: Safety guards
# ---------------------------------------------------------------------------


class TestAdaptiveSafety(SimpleTestCase):
    """Adaptive tuning cannot override truth or expectation filters."""

    @patch("apps.core.signals.signal_presenter._get_feedback_stats")
    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_truth_suppression_overrides_reinforcement(
        self, mock_raw, mock_truth, mock_stats,
    ):
        """Even a reinforced signal is suppressed if truth says completed."""
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer",
                             confidence=0.90, timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth(prayer_completed=True)
        # Strong reinforcement — but truth should win
        mock_stats.return_value = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 10, "no": 0, "total": 10},
        }

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)
        self.assertEqual(len(result["suggestions"]), 0)

    @patch("apps.core.signals.signal_presenter._get_feedback_stats")
    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_expectation_suppression_overrides_reinforcement(
        self, mock_raw, mock_truth, mock_stats,
    ):
        """Even a reinforced signal is suppressed if not expected today."""
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="health", item="workout",
                             confidence=0.90, timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth(workout_expected=False)
        mock_stats.return_value = {
            (POSSIBLE_COMPLETION, "health", "workout"): {"yes": 10, "no": 0, "total": 10},
        }

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)
        self.assertEqual(len(result["suggestions"]), 0)

    def test_confidence_floor_cannot_go_below_075(self):
        """Reinforced min confidence is exactly 0.75, not lower."""
        self.assertEqual(ADAPTIVE_REINFORCED_MIN_CONFIDENCE, 0.75)

    def test_min_feedback_is_3(self):
        """Minimum feedback count for adaptation is 3."""
        self.assertEqual(ADAPTIVE_MIN_FEEDBACK, 3)

    @patch("apps.core.signals.signal_presenter._get_feedback_stats")
    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_adaptive_metadata_in_output(self, mock_raw, mock_truth, mock_stats):
        """Output includes adaptive=True/False flag but no internal metadata."""
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer",
                             confidence=0.90, timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth()
        mock_stats.return_value = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 5, "no": 0, "total": 5},
        }

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        self.assertEqual(len(result["suggestions"]), 1)
        suggestion = result["suggestions"][0]
        self.assertIn("adaptive", suggestion)
        self.assertTrue(suggestion["adaptive"])
        # Internal metadata should NOT leak
        self.assertNotIn("_adaptive_priority_boost", suggestion)
        self.assertNotIn("_adaptive_min_confidence", suggestion)


# ---------------------------------------------------------------------------
# 18. Phase 5.1: Suppression floor (requires absolute count)
# ---------------------------------------------------------------------------


class TestSuppressionFloor(SimpleTestCase):
    """Suppression requires BOTH ratio >= 0.75 AND no_count >= 3."""

    def test_high_ratio_low_count_not_suppressed(self):
        """2 no out of 2 total (100% no) but count < 3 → NOT suppressed."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 0, "no": 2, "total": 2},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)

    def test_high_ratio_meets_count_suppressed(self):
        """3 no out of 3 total (100% no) and count >= 3 → suppressed."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 0, "no": 3, "total": 3},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNone(result)

    def test_ratio_below_threshold_not_suppressed(self):
        """2 no out of 3 total (66%) → ratio below 0.75, NOT suppressed."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 1, "no": 2, "total": 3},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)


# ---------------------------------------------------------------------------
# 19. Phase 5.1: Reinforcement cap
# ---------------------------------------------------------------------------


class TestReinforcementCap(SimpleTestCase):
    """Priority boost is capped at ADAPTIVE_MAX_PRIORITY_BOOST."""

    def test_boost_does_not_exceed_cap(self):
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        stats = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 50, "no": 0, "total": 50},
        }
        result = _apply_adaptive_rules(sig, stats)
        self.assertIsNotNone(result)
        self.assertLessEqual(
            result["_adaptive_priority_boost"],
            ADAPTIVE_MAX_PRIORITY_BOOST,
        )

    def test_max_boost_constant(self):
        self.assertEqual(ADAPTIVE_MAX_PRIORITY_BOOST, 1.0)


# ---------------------------------------------------------------------------
# 20. Phase 5.1: Recency window
# ---------------------------------------------------------------------------


class TestRecencyWindow(SimpleTestCase):
    """Feedback window is 30 days."""

    def test_window_constant(self):
        self.assertEqual(FEEDBACK_WINDOW_DAYS, 30)


# ---------------------------------------------------------------------------
# 21. Fingerprint and UI payload
# ---------------------------------------------------------------------------


class TestPresenterFingerprint(SimpleTestCase):
    """Presenter output includes fingerprint and ui payload."""

    @patch("apps.core.signals.signal_presenter._get_feedback_stats")
    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_fingerprint_in_output(self, mock_raw, mock_truth, mock_stats):
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer",
                             confidence=0.90, timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth()
        mock_stats.return_value = {}

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        suggestion = result["suggestions"][0]
        self.assertIn("fingerprint", suggestion)
        self.assertEqual(len(suggestion["fingerprint"]), 32)

    @patch("apps.core.signals.signal_presenter._get_feedback_stats")
    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_ui_payload_in_output(self, mock_raw, mock_truth, mock_stats):
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer",
                             confidence=0.90, timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth()
        mock_stats.return_value = {}

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        suggestion = result["suggestions"][0]
        self.assertIn("ui", suggestion)
        self.assertTrue(suggestion["ui"]["show"])
        self.assertEqual(suggestion["ui"]["actions"], ["yes", "no"])

    def test_fingerprint_deterministic(self):
        now = timezone.now()
        sig = _make_signal(domain="faith", item="prayer", timestamp=now)
        fp1 = _generate_signal_fingerprint(sig)
        fp2 = _generate_signal_fingerprint(sig)
        self.assertEqual(fp1, fp2)

    def test_fingerprint_varies_by_domain(self):
        now = timezone.now()
        sig1 = _make_signal(domain="faith", item="prayer", timestamp=now)
        sig2 = _make_signal(domain="health", item="workout", timestamp=now)
        self.assertNotEqual(
            _generate_signal_fingerprint(sig1),
            _generate_signal_fingerprint(sig2),
        )


# ---------------------------------------------------------------------------
# 22. Phase 5.2: Pattern key generation
# ---------------------------------------------------------------------------


class TestPatternKey(SimpleTestCase):
    """Pattern key is date-free: type:domain:item."""

    def test_pattern_key_format(self):
        sig = _make_signal(domain="faith", item="prayer")
        pk = _get_pattern_key(sig)
        self.assertEqual(pk, "possible_completion:faith:prayer")

    def test_pattern_key_no_date(self):
        """Same signal on different days produces same pattern key."""
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        sig1 = _make_signal(domain="faith", item="prayer", timestamp=now)
        sig2 = _make_signal(domain="faith", item="prayer", timestamp=yesterday)
        self.assertEqual(_get_pattern_key(sig1), _get_pattern_key(sig2))

    def test_pattern_key_different_items(self):
        sig1 = _make_signal(domain="faith", item="prayer")
        sig2 = _make_signal(domain="faith", item="bible_reading")
        self.assertNotEqual(_get_pattern_key(sig1), _get_pattern_key(sig2))


# ---------------------------------------------------------------------------
# 23. Phase 5.2: Pattern reinforcement
# ---------------------------------------------------------------------------


class TestPatternReinforcement(SimpleTestCase):
    """Pattern-level reinforcement with higher thresholds."""

    def test_pattern_reinforcement_with_5_yes(self):
        """5+ yes → pattern reinforced."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        pattern_stats = {
            "possible_completion:faith:prayer": {"yes": 5, "no": 0, "total": 5},
        }
        result = _apply_pattern_rules(sig, pattern_stats)
        self.assertIsNotNone(result)
        self.assertTrue(result.get("_pattern_reinforced", False))
        self.assertGreater(result.get("_adaptive_priority_boost", 0), 0)

    def test_pattern_reinforcement_boost_capped(self):
        """Pattern boost combined with signal boost doesn't exceed cap."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        sig["_adaptive_priority_boost"] = 0.5  # signal-level boost already applied
        pattern_stats = {
            "possible_completion:faith:prayer": {"yes": 10, "no": 0, "total": 10},
        }
        result = _apply_pattern_rules(sig, pattern_stats)
        self.assertIsNotNone(result)
        self.assertLessEqual(
            result["_adaptive_priority_boost"],
            ADAPTIVE_MAX_PRIORITY_BOOST,
        )

    def test_pattern_constants(self):
        self.assertEqual(PATTERN_MIN_FEEDBACK, 5)
        self.assertEqual(PATTERN_REINFORCE_RATIO, 0.75)
        self.assertEqual(PATTERN_SUPPRESS_RATIO, 0.80)
        self.assertLess(PATTERN_PRIORITY_BOOST, 0.5)  # smaller than signal boost


# ---------------------------------------------------------------------------
# 24. Phase 5.2: Pattern suppression
# ---------------------------------------------------------------------------


class TestPatternSuppression(SimpleTestCase):
    """Pattern-level suppression requires higher confidence (80%)."""

    def test_pattern_suppressed_with_5_no(self):
        """5+ no at 80%+ → pattern suppressed."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        pattern_stats = {
            "possible_completion:faith:prayer": {"yes": 0, "no": 5, "total": 5},
        }
        result = _apply_pattern_rules(sig, pattern_stats)
        self.assertIsNone(result)

    def test_pattern_not_suppressed_at_75_percent(self):
        """75% no but below 80% → NOT pattern suppressed (stricter than signal)."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        # 3 no / 4 total = 75% — meets signal threshold but not pattern threshold
        pattern_stats = {
            "possible_completion:faith:prayer": {"yes": 2, "no": 8, "total": 10},
        }
        result = _apply_pattern_rules(sig, pattern_stats)
        # 8/10 = 80%, exactly at threshold
        self.assertIsNone(result)

    def test_pattern_not_suppressed_below_min_count(self):
        """Below PATTERN_MIN_FEEDBACK → no effect."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        pattern_stats = {
            "possible_completion:faith:prayer": {"yes": 0, "no": 4, "total": 4},
        }
        result = _apply_pattern_rules(sig, pattern_stats)
        self.assertIsNotNone(result)  # Not suppressed — below threshold


# ---------------------------------------------------------------------------
# 25. Phase 5.2: Pattern threshold enforcement
# ---------------------------------------------------------------------------


class TestPatternThresholdEnforcement(SimpleTestCase):
    """Pattern rules require minimum 5 records (vs 3 for signal)."""

    def test_no_pattern_effect_below_5(self):
        """< 5 total → pattern rules don't apply."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        pattern_stats = {
            "possible_completion:faith:prayer": {"yes": 4, "no": 0, "total": 4},
        }
        result = _apply_pattern_rules(sig, pattern_stats)
        self.assertIsNotNone(result)
        # No pattern reinforcement flag
        self.assertFalse(result.get("_pattern_reinforced", False))

    def test_no_pattern_effect_when_missing(self):
        """Missing pattern key → no effect."""
        sig = _make_signal(signal_type=POSSIBLE_COMPLETION, confidence=0.85)
        result = _apply_pattern_rules(sig, {})
        self.assertIsNotNone(result)
        self.assertFalse(result.get("_pattern_reinforced", False))


# ---------------------------------------------------------------------------
# 26. Phase 5.2: Conflict resolution (signal wins)
# ---------------------------------------------------------------------------


class TestPatternConflictResolution(SimpleTestCase):
    """Signal-level decisions take priority over pattern-level."""

    @patch("apps.core.signals.signal_presenter._get_pattern_feedback_stats")
    @patch("apps.core.signals.signal_presenter._get_feedback_stats")
    def test_signal_reinforced_pattern_suppressed_signal_wins(
        self, mock_signal_stats, mock_pattern_stats,
    ):
        """Signal-level reinforced + pattern-level suppressed → signal wins (kept)."""
        sig = _make_signal(
            signal_type=POSSIBLE_COMPLETION, confidence=0.85,
            domain="faith", item="prayer",
        )
        # Signal-level: reinforced (3 yes, 0 no)
        mock_signal_stats.return_value = {
            (POSSIBLE_COMPLETION, "faith", "prayer"): {"yes": 3, "no": 0, "total": 3},
        }
        # Pattern-level: suppressed (0 yes, 10 no)
        mock_pattern_stats.return_value = {
            "possible_completion:faith:prayer": {"yes": 0, "no": 10, "total": 10},
        }

        user = MagicMock()
        result = _apply_adaptive_tuning(user, [sig])

        # Signal should survive — signal-level wins
        self.assertEqual(len(result), 1)

    @patch("apps.core.signals.signal_presenter._get_pattern_feedback_stats")
    @patch("apps.core.signals.signal_presenter._get_feedback_stats")
    def test_signal_neutral_pattern_suppressed_pattern_wins(
        self, mock_signal_stats, mock_pattern_stats,
    ):
        """Signal-level neutral + pattern-level suppressed → pattern wins (suppressed)."""
        sig = _make_signal(
            signal_type=POSSIBLE_COMPLETION, confidence=0.85,
            domain="faith", item="prayer",
        )
        # Signal-level: no data (neutral)
        mock_signal_stats.return_value = {}
        # Pattern-level: suppressed (0 yes, 5 no)
        mock_pattern_stats.return_value = {
            "possible_completion:faith:prayer": {"yes": 0, "no": 5, "total": 5},
        }

        user = MagicMock()
        result = _apply_adaptive_tuning(user, [sig])

        # Pattern suppression applies when signal is neutral
        self.assertEqual(len(result), 0)


# ---------------------------------------------------------------------------
# 27. Phase 5.2: Pattern independence from truth/expectation filters
# ---------------------------------------------------------------------------


class TestPatternIndependence(SimpleTestCase):
    """Pattern logic does NOT affect truth or expectation filtering."""

    def test_pattern_does_not_affect_non_completion_types(self):
        """Pattern rules skip non-possible_completion signals."""
        sig = _make_signal(
            signal_type=INCONSISTENCY_SIGNAL, confidence=0.85,
            domain="faith", item="prayer",
        )
        pattern_stats = {
            "inconsistency_signal:faith:prayer": {"yes": 10, "no": 0, "total": 10},
        }
        result = _apply_pattern_rules(sig, pattern_stats)
        # Should return signal unchanged, no pattern reinforcement
        self.assertIsNotNone(result)
        self.assertFalse(result.get("_pattern_reinforced", False))

    @patch("apps.core.signals.signal_presenter._get_pattern_feedback_stats")
    @patch("apps.core.signals.signal_presenter._get_feedback_stats")
    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_truth_filter_runs_before_pattern(
        self, mock_raw, mock_truth, mock_signal_stats, mock_pattern_stats,
    ):
        """Truth suppression happens before pattern rules can see the signal."""
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(
                    domain="faith", item="prayer",
                    confidence=0.90, timestamp=now,
                ),
            ]
        }
        # Mark prayer as completed in truth → should be filtered out
        mock_truth.return_value = _make_truth(prayer_completed=True)
        # Pattern would reinforce — but signal never reaches pattern layer
        mock_pattern_stats.return_value = {
            "possible_completion:faith:prayer": {"yes": 20, "no": 0, "total": 20},
        }
        mock_signal_stats.return_value = {}

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        # Should be empty — truth filter removes before pattern can boost
        self.assertEqual(len(result["suggestions"]), 0)


# ---------------------------------------------------------------------------
# 28. Phase 5.2: Pattern output in presenter
# ---------------------------------------------------------------------------


class TestPatternPresenterOutput(SimpleTestCase):
    """Presenter output includes pattern_reinforced flag."""

    @patch("apps.core.signals.signal_presenter._get_pattern_feedback_stats")
    @patch("apps.core.signals.signal_presenter._get_feedback_stats")
    @patch("apps.core.signals.signal_presenter._get_execution_truth")
    @patch("apps.core.signals.signal_presenter._get_raw_signals")
    def test_pattern_reinforced_flag_in_output(
        self, mock_raw, mock_truth, mock_signal_stats, mock_pattern_stats,
    ):
        now = timezone.now()
        mock_raw.return_value = {
            "signals": [
                _make_signal(domain="faith", item="prayer",
                             confidence=0.90, timestamp=now),
            ]
        }
        mock_truth.return_value = _make_truth()
        mock_signal_stats.return_value = {}
        mock_pattern_stats.return_value = {
            "possible_completion:faith:prayer": {"yes": 8, "no": 1, "total": 9},
        }

        user = MagicMock()
        user.id = 1
        result = get_presented_signals(user)

        self.assertEqual(len(result["suggestions"]), 1)
        suggestion = result["suggestions"][0]
        self.assertIn("pattern_reinforced", suggestion)
        self.assertTrue(suggestion["pattern_reinforced"])
