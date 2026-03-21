"""Tests for Routine Signal → Action Service."""

from django.test import TestCase

from apps.life.services.routine_action_service import generate_routine_actions


class GenerateActionsTest(TestCase):
    """Test action generation from signals."""

    def test_empty_signals_returns_empty(self):
        self.assertEqual(generate_routine_actions([]), [])

    def test_overdue_produces_high_priority(self):
        signals = [{
            'schedule_id': 1,
            'schedule_name': 'Oil Change',
            'routine_name': 'Vehicle',
            'top_signal': {
                'type': 'maintenance_overdue',
                'severity': 'high',
                'detail': 'Oil Change is 15 days overdue',
                'days': 15,
            },
            'all_signals': [],
        }]
        actions = generate_routine_actions(signals)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['priority'], 'high')
        self.assertEqual(actions[0]['action'], 'perform_maintenance')
        self.assertIn('15 days overdue', actions[0]['message'])

    def test_drift_produces_medium_priority(self):
        signals = [{
            'schedule_id': 2,
            'schedule_name': 'Prayer',
            'routine_name': 'Morning',
            'top_signal': {
                'type': 'drift',
                'severity': 'medium',
                'detail': 'Prayer is slipping',
                'days': 0,
            },
            'all_signals': [],
        }]
        actions = generate_routine_actions(signals)
        self.assertEqual(actions[0]['priority'], 'medium')
        self.assertIn('slipping', actions[0]['message'])

    def test_over_maintenance_produces_low_priority(self):
        signals = [{
            'schedule_id': 3,
            'schedule_name': 'Oil Change',
            'routine_name': 'Vehicle',
            'top_signal': {
                'type': 'over_maintenance',
                'severity': 'low',
                'detail': 'Done too often',
                'days': 0,
            },
            'all_signals': [],
        }]
        actions = generate_routine_actions(signals)
        self.assertEqual(actions[0]['priority'], 'low')

    def test_sorted_by_priority_then_days(self):
        signals = [
            {
                'schedule_id': 1,
                'schedule_name': 'Low Item',
                'routine_name': 'R',
                'top_signal': {'type': 'over_maintenance', 'severity': 'low', 'days': 0},
                'all_signals': [],
            },
            {
                'schedule_id': 2,
                'schedule_name': 'High Item',
                'routine_name': 'R',
                'top_signal': {'type': 'maintenance_overdue', 'severity': 'high', 'days': 20},
                'all_signals': [],
            },
            {
                'schedule_id': 3,
                'schedule_name': 'Medium Item',
                'routine_name': 'R',
                'top_signal': {'type': 'drift', 'severity': 'medium', 'days': 0},
                'all_signals': [],
            },
        ]
        actions = generate_routine_actions(signals)
        self.assertEqual(actions[0]['schedule_name'], 'High Item')
        self.assertEqual(actions[1]['schedule_name'], 'Medium Item')
        self.assertEqual(actions[2]['schedule_name'], 'Low Item')

    def test_max_three_actions(self):
        signals = [
            {
                'schedule_id': i,
                'schedule_name': f'Item {i}',
                'routine_name': 'R',
                'top_signal': {'type': 'neglect', 'severity': 'high', 'days': i * 10},
                'all_signals': [],
            }
            for i in range(5)
        ]
        actions = generate_routine_actions(signals)
        self.assertEqual(len(actions), 3)

    def test_neglect_message(self):
        signals = [{
            'schedule_id': 1,
            'schedule_name': 'HVAC Filter',
            'routine_name': 'Home',
            'top_signal': {
                'type': 'neglect',
                'severity': 'high',
                'detail': 'No activity',
                'days': 180,
            },
            'all_signals': [],
        }]
        actions = generate_routine_actions(signals)
        self.assertIn('needs attention', actions[0]['message'])
