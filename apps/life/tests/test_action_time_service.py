"""Tests for Action → Time Block Service."""

from django.test import TestCase

from apps.life.services.action_time_service import assign_time_blocks


class AssignTimeBlocksTest(TestCase):
    """Test time block assignment logic."""

    def test_empty_actions_returns_empty(self):
        self.assertEqual(assign_time_blocks([]), [])

    def test_high_priority_gets_morning(self):
        actions = [{
            'schedule_id': 1, 'schedule_name': 'Oil Change',
            'priority': 'high', 'action': 'perform_maintenance',
            'message': 'Overdue',
        }]
        result = assign_time_blocks(actions, current_hour=6)
        self.assertEqual(result[0]['time_block'], 'morning')
        self.assertEqual(result[0]['suggested_duration'], 45)
        self.assertIn('this morning', result[0]['guidance'])

    def test_medium_priority_gets_afternoon(self):
        actions = [{
            'schedule_id': 2, 'schedule_name': 'Prayer',
            'priority': 'medium', 'action': 'stabilize_routine',
            'message': 'Drifting',
        }]
        result = assign_time_blocks(actions, current_hour=6)
        self.assertEqual(result[0]['time_block'], 'afternoon')
        self.assertEqual(result[0]['suggested_duration'], 15)

    def test_low_priority_gets_evening(self):
        actions = [{
            'schedule_id': 3, 'schedule_name': 'Oil Change',
            'priority': 'low', 'action': 'slow_down',
            'message': 'Overdoing',
        }]
        result = assign_time_blocks(actions, current_hour=6)
        self.assertEqual(result[0]['time_block'], 'evening')

    def test_skips_past_windows(self):
        """At 3 PM (15), morning/mid_morning/lunch should be skipped."""
        actions = [{
            'schedule_id': 1, 'schedule_name': 'Task',
            'priority': 'high', 'action': 'perform_maintenance',
            'message': 'Do it',
        }]
        result = assign_time_blocks(actions, current_hour=15)
        # Morning (5-10), mid_morning (10-12), lunch (12-14) all passed
        # Afternoon (14-17) is current — should be assigned
        self.assertEqual(result[0]['time_block'], 'afternoon')

    def test_no_duplicate_windows(self):
        """Multiple actions should not share the same window."""
        actions = [
            {'schedule_id': 1, 'schedule_name': 'A',
             'priority': 'high', 'action': 'perform_maintenance', 'message': 'X'},
            {'schedule_id': 2, 'schedule_name': 'B',
             'priority': 'high', 'action': 'reset_routine', 'message': 'Y'},
        ]
        result = assign_time_blocks(actions, current_hour=6)
        windows = [r['time_block'] for r in result]
        self.assertEqual(len(set(windows)), 2)  # No duplicates

    def test_late_night_gets_nightly_or_tomorrow(self):
        """At 11 PM (23), nightly window still available."""
        actions = [{
            'schedule_id': 1, 'schedule_name': 'Task',
            'priority': 'high', 'action': 'perform_maintenance',
            'message': 'Do it',
        }]
        result = assign_time_blocks(actions, current_hour=23)
        # At 23, nightly (21-24) is still active
        self.assertIn(result[0]['time_block'], ('nightly', 'morning'))

    def test_past_midnight_defers_to_tomorrow(self):
        """At hour 24+ (or beyond all windows), defers to morning."""
        actions = [{
            'schedule_id': 1, 'schedule_name': 'Task',
            'priority': 'high', 'action': 'perform_maintenance',
            'message': 'Do it',
        }]
        # Simulate all windows passed by using a very high hour
        # In practice current_hour maxes at 23, but test the fallback
        result = assign_time_blocks(actions, current_hour=25)
        self.assertIn('tomorrow', result[0]['time_label'])

    def test_guidance_is_human_readable(self):
        actions = [{
            'schedule_id': 1, 'schedule_name': 'Yard Work',
            'priority': 'medium', 'action': 'stabilize_routine',
            'message': 'Drifting',
        }]
        result = assign_time_blocks(actions, current_hour=8)
        self.assertIn('Yard Work', result[0]['guidance'])
        self.assertIn('minutes', result[0]['guidance'])

    def test_no_current_hour_uses_all_windows(self):
        """When current_hour is None, all windows are available."""
        actions = [{
            'schedule_id': 1, 'schedule_name': 'Task',
            'priority': 'high', 'action': 'perform_maintenance',
            'message': 'Do it',
        }]
        result = assign_time_blocks(actions, current_hour=None)
        self.assertEqual(result[0]['time_block'], 'morning')
