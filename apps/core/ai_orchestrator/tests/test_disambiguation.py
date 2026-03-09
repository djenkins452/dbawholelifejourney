"""
Tests for the Activity Disambiguation system.

Tests the DISAMBIGUATE decision type, disambiguation response parsing,
disambiguation message building, and the two-step flow
(disambiguate → select → CRUD gate).
"""

from datetime import date, time
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.ai_orchestrator.activity_reconciliation import (
    ACTIVITY_RECONCILERS,
    CONFIDENCE_MEDIUM,
    ReconciliationDecision,
    ReconciliationResult,
    _build_event_candidate_info,
    _build_task_candidate_info,
    _score_all_matches,
    reconcile_activity,
)
from apps.core.ai_orchestrator.crud_confirmation import (
    build_disambiguation_message,
    parse_disambiguation_response,
)


# ── _score_all_matches Tests ──────────────────────────────────────────


class ScoreAllMatchesTests(TestCase):
    """Tests for _score_all_matches helper."""

    def test_returns_sorted_descending(self):
        obj1 = MagicMock(title='Workout')
        obj2 = MagicMock(title='Workout Plan')
        # 'workout' exact match = 1.0, 'workout plan' prefix = 0.9
        scored = _score_all_matches('workout', [obj1, obj2])
        self.assertEqual(len(scored), 2)
        self.assertEqual(scored[0][0].title, 'Workout')
        self.assertGreaterEqual(scored[0][1], scored[1][1])

    def test_filters_below_confidence_medium(self):
        obj1 = MagicMock(title='Workout')
        obj2 = MagicMock(title='Grocery Shopping')
        # 'workout' exact = 1.0, 'grocery shopping' vs 'workout' = 0.0
        scored = _score_all_matches('workout', [obj1, obj2])
        self.assertEqual(len(scored), 1)
        self.assertEqual(scored[0][0].title, 'Workout')

    def test_empty_candidates_returns_empty(self):
        scored = _score_all_matches('workout', [])
        self.assertEqual(len(scored), 0)


# ── Candidate Info Builder Tests ──────────────────────────────────────


class TaskCandidateInfoTests(TestCase):
    """Tests for _build_task_candidate_info."""

    def test_includes_time_string(self):
        task = MagicMock()
        task.id = 1
        task.title = 'Workout'
        task.scheduled_time = time(6, 15)
        task.due_date = date(2026, 3, 9)

        info = _build_task_candidate_info(task)
        self.assertEqual(info['id'], 1)
        self.assertEqual(info['title'], 'Workout')
        self.assertEqual(info['time'], '6:15 AM')
        self.assertEqual(info['model'], 'Task')

    def test_none_time_returns_none(self):
        task = MagicMock()
        task.id = 2
        task.title = 'Read'
        task.scheduled_time = None
        task.due_date = None

        info = _build_task_candidate_info(task)
        self.assertIsNone(info['time'])


class EventCandidateInfoTests(TestCase):
    """Tests for _build_event_candidate_info."""

    def test_includes_time_string(self):
        from datetime import datetime, timezone as tz
        event = MagicMock()
        event.id = 10
        event.title = 'Team Meeting'
        event.start_dt = datetime(2026, 3, 9, 14, 30, tzinfo=tz.utc)

        info = _build_event_candidate_info(event, tz.utc)
        self.assertEqual(info['id'], 10)
        self.assertEqual(info['title'], 'Team Meeting')
        self.assertEqual(info['time'], '2:30 PM')
        self.assertEqual(info['model'], 'CalendarEvent')


# ── Task Reconciliation DISAMBIGUATE Tests ────────────────────────────


class TaskDisambiguateTests(TestCase):
    """Tests that multiple same-title tasks trigger DISAMBIGUATE."""

    def _make_enriched(self, title='Workout', scheduled_time=None):
        enriched = MagicMock()
        enriched.intent_type = 'create_task'
        enriched.parameters = {'title': title}
        if scheduled_time:
            enriched.parameters['scheduled_time'] = scheduled_time
        return enriched

    @patch('apps.core.ai_orchestrator.activity_reconciliation._get_user_today')
    @patch('apps.life.models.Task.objects')
    def test_two_exact_match_tasks_returns_disambiguate(self, mock_task_qs, mock_today):
        """Two tasks named 'Workout' at different times → DISAMBIGUATE."""
        mock_today.return_value = date(2026, 3, 9)

        task1 = MagicMock()
        task1.id = 1
        task1.title = 'Workout'
        task1.scheduled_time = time(6, 15)
        task1.due_date = date(2026, 3, 9)

        task2 = MagicMock()
        task2.id = 2
        task2.title = 'Workout'
        task2.scheduled_time = time(13, 30)
        task2.due_date = date(2026, 3, 9)

        # Chain: Task.objects.filter() → .filter(date Q) → .filter(title__iexact)
        mock_base_qs = MagicMock()
        mock_task_qs.filter.return_value = mock_base_qs
        mock_date_qs = MagicMock()
        mock_base_qs.filter.return_value = mock_date_qs
        candidates_qs = MagicMock()
        candidates_qs.__iter__ = lambda s: iter([task1, task2])
        candidates_qs.__len__ = lambda s: 2
        mock_date_qs.filter.return_value = candidates_qs

        user = MagicMock()
        enriched = self._make_enriched(title='Workout', scheduled_time='16:00')

        result = reconcile_activity(user, enriched)
        self.assertEqual(result.decision, ReconciliationDecision.DISAMBIGUATE)
        self.assertEqual(len(result.candidates), 2)
        self.assertIn('Workout', result.confirm_message)
        # Candidates should include time info
        self.assertEqual(result.candidates[0]['model'], 'Task')
        self.assertIn('time', result.candidates[0])

    @patch('apps.core.ai_orchestrator.activity_reconciliation._get_user_today')
    @patch('apps.life.models.Task.objects')
    def test_three_similar_tasks_returns_disambiguate(self, mock_task_qs, mock_today):
        """Three matching tasks → DISAMBIGUATE."""
        mock_today.return_value = date(2026, 3, 9)

        tasks = []
        for i, t in enumerate([time(6, 0), time(12, 0), time(18, 0)]):
            task = MagicMock()
            task.id = i + 1
            task.title = 'Meeting'
            task.scheduled_time = t
            task.due_date = date(2026, 3, 9)
            tasks.append(task)

        mock_base_qs = MagicMock()
        mock_task_qs.filter.return_value = mock_base_qs
        mock_date_qs = MagicMock()
        mock_base_qs.filter.return_value = mock_date_qs
        candidates_qs = MagicMock()
        candidates_qs.__iter__ = lambda s: iter(tasks)
        candidates_qs.__len__ = lambda s: 3
        mock_date_qs.filter.return_value = candidates_qs

        user = MagicMock()
        enriched = self._make_enriched(title='Meeting', scheduled_time='10:00')

        result = reconcile_activity(user, enriched)
        self.assertEqual(result.decision, ReconciliationDecision.DISAMBIGUATE)
        self.assertEqual(len(result.candidates), 3)

    @patch('apps.core.ai_orchestrator.activity_reconciliation._get_user_today')
    @patch('apps.life.models.Task.objects')
    def test_single_task_no_disambiguate(self, mock_task_qs, mock_today):
        """Single matching task → SKIP/RESCHEDULE, not DISAMBIGUATE."""
        mock_today.return_value = date(2026, 3, 9)

        task = MagicMock()
        task.id = 1
        task.title = 'Workout'
        task.scheduled_time = time(6, 15)

        mock_base_qs = MagicMock()
        mock_task_qs.filter.return_value = mock_base_qs
        mock_date_qs = MagicMock()
        mock_base_qs.filter.return_value = mock_date_qs
        candidates_qs = MagicMock()
        candidates_qs.__iter__ = lambda s: iter([task])
        candidates_qs.__len__ = lambda s: 1
        mock_date_qs.filter.return_value = candidates_qs

        user = MagicMock()
        enriched = self._make_enriched(title='Workout', scheduled_time='14:00')

        result = reconcile_activity(user, enriched)
        # Should NOT be DISAMBIGUATE — only one match
        self.assertNotEqual(result.decision, ReconciliationDecision.DISAMBIGUATE)
        self.assertEqual(result.decision, ReconciliationDecision.RESCHEDULE)

    @patch('apps.core.ai_orchestrator.activity_reconciliation._get_user_today')
    @patch('apps.life.models.Task.objects')
    def test_one_high_one_low_confidence_no_disambiguate(self, mock_task_qs, mock_today):
        """One exact match + one unrelated → single match (no DISAMBIGUATE)."""
        mock_today.return_value = date(2026, 3, 9)

        task1 = MagicMock()
        task1.id = 1
        task1.title = 'Workout'
        task1.scheduled_time = time(6, 15)
        task1.due_date = date(2026, 3, 9)

        task2 = MagicMock()
        task2.id = 2
        task2.title = 'Bible Reading'  # Low confidence match for "Workout"
        task2.scheduled_time = time(7, 0)
        task2.due_date = date(2026, 3, 9)

        mock_base_qs = MagicMock()
        mock_task_qs.filter.return_value = mock_base_qs
        mock_date_qs = MagicMock()
        mock_base_qs.filter.return_value = mock_date_qs
        candidates_qs = MagicMock()
        candidates_qs.__iter__ = lambda s: iter([task1, task2])
        candidates_qs.__len__ = lambda s: 2
        mock_date_qs.filter.return_value = candidates_qs

        user = MagicMock()
        enriched = self._make_enriched(title='Workout', scheduled_time='14:00')

        result = reconcile_activity(user, enriched)
        # Only 'Workout' scores >= 0.7, 'Bible Reading' scores 0.0
        # So only 1 high scorer → no DISAMBIGUATE
        self.assertNotEqual(result.decision, ReconciliationDecision.DISAMBIGUATE)


# ── parse_disambiguation_response Tests ───────────────────────────────


class ParseDisambiguationResponseTests(TestCase):
    """Tests for parse_disambiguation_response."""

    def test_numeric_1(self):
        result = parse_disambiguation_response('1', 3)
        self.assertEqual(result, {'action': 'select', 'index': 0})

    def test_numeric_2(self):
        result = parse_disambiguation_response('2', 3)
        self.assertEqual(result, {'action': 'select', 'index': 1})

    def test_numeric_3(self):
        result = parse_disambiguation_response('3', 3)
        self.assertEqual(result, {'action': 'select', 'index': 2})

    def test_hash_prefix(self):
        result = parse_disambiguation_response('#1', 3)
        self.assertEqual(result, {'action': 'select', 'index': 0})

    def test_first_ordinal(self):
        result = parse_disambiguation_response('first', 3)
        self.assertEqual(result, {'action': 'select', 'index': 0})

    def test_second_ordinal(self):
        result = parse_disambiguation_response('second', 3)
        self.assertEqual(result, {'action': 'select', 'index': 1})

    def test_the_first_one(self):
        result = parse_disambiguation_response('the first one', 3)
        self.assertEqual(result, {'action': 'select', 'index': 0})

    def test_out_of_range(self):
        result = parse_disambiguation_response('5', 3)
        self.assertIsNone(result)

    def test_zero(self):
        result = parse_disambiguation_response('0', 3)
        self.assertIsNone(result)

    def test_cancel(self):
        result = parse_disambiguation_response('cancel', 3)
        self.assertEqual(result, {'action': 'cancel'})

    def test_no(self):
        result = parse_disambiguation_response('no', 3)
        self.assertEqual(result, {'action': 'cancel'})

    def test_none_creates_new(self):
        result = parse_disambiguation_response('none', 3)
        self.assertEqual(result, {'action': 'create_new'})

    def test_new_creates_new(self):
        result = parse_disambiguation_response('new', 3)
        self.assertEqual(result, {'action': 'create_new'})

    def test_unrecognized(self):
        result = parse_disambiguation_response('hello world', 3)
        self.assertIsNone(result)

    def test_empty(self):
        result = parse_disambiguation_response('', 3)
        self.assertIsNone(result)

    def test_case_insensitive(self):
        result = parse_disambiguation_response('CANCEL', 3)
        self.assertEqual(result, {'action': 'cancel'})


# ── build_disambiguation_message Tests ────────────────────────────────


class BuildDisambiguationMessageTests(TestCase):
    """Tests for build_disambiguation_message."""

    def test_includes_numbered_list(self):
        recon = ReconciliationResult(
            decision=ReconciliationDecision.DISAMBIGUATE,
            original_intent='create_task',
            confirm_message='I found 2 tasks matching "Workout". Which one?',
            candidates=[
                {'id': 1, 'title': 'Workout', 'time': '6:15 AM', 'model': 'Task'},
                {'id': 2, 'title': 'Workout', 'time': '1:30 PM', 'model': 'Task'},
            ],
        )
        msg = build_disambiguation_message(recon)
        self.assertIn('1. Workout (6:15 AM)', msg)
        self.assertIn('2. Workout (1:30 PM)', msg)
        self.assertIn('CANCEL', msg)
        self.assertIn('NONE', msg)

    def test_includes_due_date(self):
        recon = ReconciliationResult(
            decision=ReconciliationDecision.DISAMBIGUATE,
            original_intent='create_task',
            candidates=[
                {'id': 1, 'title': 'Report', 'time': None, 'due_date': '2026-03-10', 'model': 'Task'},
            ],
        )
        msg = build_disambiguation_message(recon)
        self.assertIn('[due 2026-03-10]', msg)

    def test_no_time_no_due_date(self):
        recon = ReconciliationResult(
            decision=ReconciliationDecision.DISAMBIGUATE,
            original_intent='create_task',
            candidates=[
                {'id': 1, 'title': 'Read', 'time': None, 'model': 'Task'},
            ],
        )
        msg = build_disambiguation_message(recon)
        self.assertIn('1. Read', msg)
        self.assertNotIn('(', msg.split('Read')[1].split('\n')[0])

    def test_default_message_when_no_confirm_message(self):
        recon = ReconciliationResult(
            decision=ReconciliationDecision.DISAMBIGUATE,
            original_intent='create_task',
            candidates=[
                {'id': 1, 'title': 'A', 'time': None, 'model': 'Task'},
                {'id': 2, 'title': 'B', 'time': None, 'model': 'Task'},
            ],
        )
        msg = build_disambiguation_message(recon)
        self.assertIn('I found multiple matches', msg)


# ── handle_disambiguation_response Tests ──────────────────────────────


class HandleDisambiguationResponseTests(TestCase):
    """Tests for intent_service.handle_disambiguation_response."""

    def setUp(self):
        from apps.ai.intent_service import intent_service
        self.intent_service = intent_service
        self.user = MagicMock()
        self.user.id = 99

    def _store_pending(self, candidates=None):
        if candidates is None:
            candidates = [
                {'id': 1, 'title': 'Workout', 'time': '6:15 AM', 'model': 'Task'},
                {'id': 2, 'title': 'Workout', 'time': '1:30 PM', 'model': 'Task'},
            ]
        self.intent_service.store_pending_disambiguation(self.user, {
            'candidates': candidates,
            'original_intent': 'create_task',
            'create_params': {'title': 'Workout', 'scheduled_time': '16:00'},
            'original_input': 'workout at 4',
            'confirmation_message': 'Which one?',
        })

    def test_expired_returns_expiry_message(self):
        # Don't store anything — it's "expired"
        result = self.intent_service.handle_disambiguation_response(self.user, '1')
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, 'expired')

    def test_cancel_clears_state(self):
        self._store_pending()
        result = self.intent_service.handle_disambiguation_response(self.user, 'cancel')
        self.assertIsNotNone(result)
        self.assertEqual(result.action_type, 'cancelled')
        # Should be cleared
        self.assertIsNone(self.intent_service.get_pending_disambiguation(self.user))

    def test_create_new_stores_crud_pending(self):
        self._store_pending()
        result = self.intent_service.handle_disambiguation_response(self.user, 'none')
        self.assertIsNotNone(result)
        self.assertEqual(result.error, 'crud_confirmation_required')
        # Disambiguation should be cleared
        self.assertIsNone(self.intent_service.get_pending_disambiguation(self.user))
        # CRUD action should be pending
        crud = self.intent_service.get_pending_crud_action(self.user)
        self.assertIsNotNone(crud)
        self.assertEqual(crud['intent_type'], 'create_task')
        # Clean up
        self.intent_service.clear_pending_crud_action(self.user)

    @patch('apps.life.models.Task.objects')
    def test_select_stores_crud_pending(self, mock_task_qs):
        """Selecting a candidate stores a CRUD pending action."""
        task_obj = MagicMock()
        task_obj.scheduled_time = time(6, 15)
        mock_task_qs.get.return_value = task_obj

        self._store_pending()
        result = self.intent_service.handle_disambiguation_response(self.user, '1')
        self.assertIsNotNone(result)
        self.assertEqual(result.error, 'crud_confirmation_required')
        # Disambiguation should be cleared
        self.assertIsNone(self.intent_service.get_pending_disambiguation(self.user))
        # CRUD action should be pending (reschedule since times differ: 6:15 AM vs 16:00)
        crud = self.intent_service.get_pending_crud_action(self.user)
        self.assertIsNotNone(crud)
        self.assertEqual(crud['intent_type'], 'mutate_task')
        self.assertEqual(crud['recon_decision'], 'reschedule')
        # Clean up
        self.intent_service.clear_pending_crud_action(self.user)

    @patch('apps.life.models.Task.objects')
    def test_select_same_time_stores_skip(self, mock_task_qs):
        """Selecting a candidate with same time stores a SKIP pending action."""
        task_obj = MagicMock()
        task_obj.scheduled_time = time(16, 0)  # Same as create_params
        mock_task_qs.get.return_value = task_obj

        self._store_pending()
        result = self.intent_service.handle_disambiguation_response(self.user, '1')
        self.assertIsNotNone(result)
        crud = self.intent_service.get_pending_crud_action(self.user)
        self.assertIsNotNone(crud)
        self.assertEqual(crud['recon_decision'], 'skip')
        # Clean up
        self.intent_service.clear_pending_crud_action(self.user)

    def test_unrecognized_returns_none(self):
        self._store_pending()
        result = self.intent_service.handle_disambiguation_response(self.user, 'hello world')
        self.assertIsNone(result)
        # Pending should still exist
        self.assertIsNotNone(self.intent_service.get_pending_disambiguation(self.user))
        # Clean up
        self.intent_service.clear_pending_disambiguation(self.user)

    def test_out_of_range_returns_none(self):
        self._store_pending()
        result = self.intent_service.handle_disambiguation_response(self.user, '5')
        self.assertIsNone(result)
        # Clean up
        self.intent_service.clear_pending_disambiguation(self.user)
