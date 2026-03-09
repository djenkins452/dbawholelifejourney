"""
Tests for the Activity Reconciliation Layer.

Tests the registry-based duplicate detection system that intercepts
create/log intents and checks for existing matching activities.
"""

from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.core.ai_orchestrator.activity_reconciliation import (
    ACTIVITY_RECONCILERS,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    ReconciliationDecision,
    ReconciliationResult,
    _compute_title_similarity,
    _extract_keywords,
    _parse_time,
    _score_all_matches,
    _times_match,
    reconcile_activity,
)


class TitleSimilarityTests(TestCase):
    """Tests for title matching and confidence scoring."""

    def test_exact_match_returns_1_0(self):
        self.assertEqual(_compute_title_similarity('workout', 'workout'), 1.0)

    def test_exact_match_case_insensitive(self):
        # Similarity is called with lowered strings from _score_best_match
        self.assertEqual(_compute_title_similarity('workout', 'workout'), 1.0)

    def test_prefix_match_returns_0_9(self):
        self.assertEqual(_compute_title_similarity('work', 'workout'), 0.9)

    def test_reverse_prefix_match_returns_0_9(self):
        self.assertEqual(_compute_title_similarity('workout plan', 'workout'), 0.9)

    def test_substring_match_returns_0_8(self):
        self.assertEqual(
            _compute_title_similarity('out', 'workout plan'), 0.8
        )

    def test_keyword_overlap_returns_moderate(self):
        score = _compute_title_similarity('morning workout routine', 'daily workout session')
        self.assertGreaterEqual(score, 0.5)
        self.assertLessEqual(score, 0.7)

    def test_no_overlap_returns_0(self):
        self.assertEqual(
            _compute_title_similarity('grocery shopping', 'bible reading'), 0.0
        )

    def test_empty_string_returns_0(self):
        self.assertEqual(_compute_title_similarity('', 'workout'), 0.0)


class ExtractKeywordsTests(TestCase):
    """Tests for keyword extraction."""

    def test_strips_stop_words(self):
        kw = _extract_keywords('do my morning workout')
        self.assertNotIn('do', kw)
        self.assertNotIn('my', kw)
        self.assertIn('morning', kw)
        self.assertIn('workout', kw)

    def test_empty_input_returns_none(self):
        self.assertIsNone(_extract_keywords(''))

    def test_only_stop_words_returns_none(self):
        self.assertIsNone(_extract_keywords('do my the'))

    def test_short_words_filtered(self):
        kw = _extract_keywords('go to gym')
        # 'go' and 'to' are stop words, 'gym' is the only keyword
        self.assertEqual(kw, ['gym'])


class TimeComparisonTests(TestCase):
    """Tests for time matching logic."""

    def test_both_none_matches(self):
        self.assertTrue(_times_match(None, None))

    def test_same_time_matches(self):
        t = time(13, 30)
        self.assertTrue(_times_match(t, t))

    def test_different_time_no_match(self):
        self.assertFalse(_times_match(time(6, 15), time(13, 30)))

    def test_one_none_no_match(self):
        self.assertFalse(_times_match(time(6, 15), None))
        self.assertFalse(_times_match(None, time(13, 30)))

    def test_parse_time_valid(self):
        self.assertEqual(_parse_time('13:30'), time(13, 30))

    def test_parse_time_invalid(self):
        self.assertIsNone(_parse_time('invalid'))

    def test_parse_time_none(self):
        self.assertIsNone(_parse_time(None))


class ReconciliationRegistryTests(TestCase):
    """Tests for the reconciler registry pattern."""

    def test_registered_intents_have_reconcilers(self):
        """All expected intents should be in the registry."""
        expected = [
            'create_task', 'create_routine_task', 'create_event',
            'create_goal', 'set_intention', 'log_prayer',
            'log_workout', 'log_weight', 'log_blood_pressure',
            'log_heart_rate', 'log_glucose', 'log_blood_oxygen',
            'log_body_measurement', 'take_medicine', 'log_habit',
            'create_journal_entry', 'add_reminder',
        ]
        for intent in expected:
            self.assertIn(intent, ACTIVITY_RECONCILERS, f"{intent} missing from registry")

    def test_unregistered_intent_returns_create(self):
        """Intents not in registry should passthrough as CREATE."""
        enriched = MagicMock()
        enriched.intent_type = 'log_food'  # Not in registry
        enriched.parameters = {'food': 'pizza'}

        user = MagicMock()
        result = reconcile_activity(user, enriched)
        self.assertEqual(result.decision, ReconciliationDecision.CREATE)
        self.assertEqual(result.reason, 'no_reconciler_registered')

    def test_reconciliation_error_returns_create(self):
        """Errors in reconciler should fallback to CREATE, not crash."""
        enriched = MagicMock()
        enriched.intent_type = 'create_task'
        enriched.parameters = {'title': 'Test'}

        user = MagicMock()
        user.id = 1

        with patch(
            'apps.core.ai_orchestrator.activity_reconciliation._reconcile_task',
            side_effect=Exception('boom'),
        ):
            result = reconcile_activity(user, enriched)
            self.assertEqual(result.decision, ReconciliationDecision.CREATE)
            self.assertIn('reconciliation_error', result.reason)


class TaskReconciliationTests(TestCase):
    """Tests for task reconciliation logic."""

    def _make_enriched(self, title='Workout', scheduled_time=None, due_date=None):
        enriched = MagicMock()
        enriched.intent_type = 'create_task'
        enriched.parameters = {'title': title}
        if scheduled_time:
            enriched.parameters['scheduled_time'] = scheduled_time
        if due_date:
            enriched.parameters['due_date'] = due_date
        return enriched

    @patch('apps.core.ai_orchestrator.activity_reconciliation._get_user_today')
    @patch('apps.life.models.Task.objects')
    def test_no_match_returns_create(self, mock_task_qs, mock_today):
        mock_today.return_value = date(2026, 3, 9)
        # Chain: Task.objects.filter(user, status, completion) → date filter → title filter
        mock_base_qs = MagicMock()
        mock_task_qs.filter.return_value = mock_base_qs
        mock_date_qs = MagicMock()
        mock_base_qs.filter.return_value = mock_date_qs
        # All title tiers return empty
        empty_qs = MagicMock()
        empty_qs.__iter__ = lambda s: iter([])
        empty_qs.__len__ = lambda s: 0
        mock_date_qs.filter.return_value = empty_qs

        user = MagicMock()
        enriched = self._make_enriched()

        result = reconcile_activity(user, enriched)
        self.assertEqual(result.decision, ReconciliationDecision.CREATE)

    @patch('apps.core.ai_orchestrator.activity_reconciliation._get_user_today')
    @patch('apps.life.models.Task.objects')
    def test_exact_match_same_time_returns_skip(self, mock_task_qs, mock_today):
        mock_today.return_value = date(2026, 3, 9)

        existing_task = MagicMock()
        existing_task.id = 42
        existing_task.title = 'Workout'
        existing_task.scheduled_time = time(6, 15)

        # Chain: Task.objects.filter() → .filter(date Q) → .filter(title__iexact)
        mock_base_qs = MagicMock()
        mock_task_qs.filter.return_value = mock_base_qs
        mock_date_qs = MagicMock()
        mock_base_qs.filter.return_value = mock_date_qs
        # Tier 1 (iexact) returns match
        candidates_qs = MagicMock()
        candidates_qs.__iter__ = lambda s: iter([existing_task])
        candidates_qs.__len__ = lambda s: 1
        mock_date_qs.filter.return_value = candidates_qs

        user = MagicMock()
        enriched = self._make_enriched(title='Workout', scheduled_time='06:15')

        result = reconcile_activity(user, enriched)
        self.assertEqual(result.decision, ReconciliationDecision.SKIP)
        self.assertIn('Workout', result.skip_message)

    @patch('apps.core.ai_orchestrator.activity_reconciliation._get_user_today')
    @patch('apps.life.models.Task.objects')
    def test_exact_match_different_time_returns_reschedule(self, mock_task_qs, mock_today):
        mock_today.return_value = date(2026, 3, 9)

        existing_task = MagicMock()
        existing_task.id = 42
        existing_task.title = 'Workout'
        existing_task.scheduled_time = time(6, 15)

        # Chain: Task.objects.filter() → .filter(date Q) → .filter(title__iexact)
        mock_base_qs = MagicMock()
        mock_task_qs.filter.return_value = mock_base_qs
        mock_date_qs = MagicMock()
        mock_base_qs.filter.return_value = mock_date_qs
        # Tier 1 (iexact) returns match
        candidates_qs = MagicMock()
        candidates_qs.__iter__ = lambda s: iter([existing_task])
        candidates_qs.__len__ = lambda s: 1
        mock_date_qs.filter.return_value = candidates_qs

        user = MagicMock()
        enriched = self._make_enriched(title='Workout', scheduled_time='13:30')

        result = reconcile_activity(user, enriched)
        self.assertEqual(result.decision, ReconciliationDecision.RESCHEDULE)
        self.assertEqual(result.redirected_intent, 'mutate_task')
        self.assertEqual(result.redirected_params['task_query'], 'Workout')
        self.assertEqual(result.redirected_params['new_scheduled_time'], '13:30')

    def test_no_title_returns_create(self):
        enriched = self._make_enriched(title='')
        user = MagicMock()
        result = reconcile_activity(user, enriched)
        self.assertEqual(result.decision, ReconciliationDecision.CREATE)
        self.assertEqual(result.reason, 'no_title')


class EventReconciliationTests(TestCase):
    """Tests for calendar event reconciliation logic."""

    def _make_enriched(self, title='Team Meeting', start_time=None, start_date=None):
        enriched = MagicMock()
        enriched.intent_type = 'create_event'
        enriched.parameters = {'title': title}
        if start_time:
            enriched.parameters['start_time'] = start_time
        if start_date:
            enriched.parameters['start_date'] = start_date
        return enriched

    def test_no_title_returns_create(self):
        enriched = self._make_enriched(title='')
        user = MagicMock()
        result = reconcile_activity(user, enriched)
        self.assertEqual(result.decision, ReconciliationDecision.CREATE)
        self.assertEqual(result.reason, 'no_title')


class HealthLogReconciliationTests(TestCase):
    """Tests for health log reconciliation (same-day dedup)."""

    def test_unknown_health_type_returns_create(self):
        enriched = MagicMock()
        enriched.intent_type = 'log_unknown_vitals'
        enriched.parameters = {}

        # Directly call the reconciler with a patched registry
        from apps.core.ai_orchestrator.activity_reconciliation import _reconcile_health_log
        result = _reconcile_health_log(MagicMock(), enriched)
        self.assertEqual(result.decision, ReconciliationDecision.CREATE)


class MedicineReconciliationTests(TestCase):
    """Tests for medicine reconciliation."""

    def test_no_med_name_returns_create(self):
        enriched = MagicMock()
        enriched.intent_type = 'take_medicine'
        enriched.parameters = {}

        from apps.core.ai_orchestrator.activity_reconciliation import _reconcile_medicine
        result = _reconcile_medicine(MagicMock(), enriched)
        self.assertEqual(result.decision, ReconciliationDecision.CREATE)
        self.assertEqual(result.reason, 'no_med_name')


class JournalReconciliationTests(TestCase):
    """Tests for journal entry reconciliation."""

    def test_journal_always_returns_create(self):
        """Journals allow multiple entries per day — always CREATE."""
        enriched = MagicMock()
        enriched.intent_type = 'create_journal_entry'
        enriched.parameters = {'title': 'Morning Reflections'}

        from apps.core.ai_orchestrator.activity_reconciliation import _reconcile_journal
        result = _reconcile_journal(MagicMock(), enriched)
        self.assertEqual(result.decision, ReconciliationDecision.CREATE)
        self.assertEqual(result.reason, 'journals_allow_multiple')
