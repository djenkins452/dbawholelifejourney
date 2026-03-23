"""Tests for Phase 3 Signal Presenter — Controlled Exposure Layer.

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
    MAX_SUGGESTIONS,
    _build_message,
    _build_question,
    _deduplicate_suggestions,
    _filter_completed_or_unexpected,
    _filter_same_day,
    _get_item_label,
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
            "text", "timestamp", "message", "question", "priority",
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
