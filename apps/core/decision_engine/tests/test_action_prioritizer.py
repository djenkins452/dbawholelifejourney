"""Tests for action_prioritizer — medicine urgency fix.

Covers:
1. Overdue medicine groups get urgency "overdue" (not hardcoded "next")
2. Overdue medicine groups sort above non-overdue items
3. Non-overdue medicine groups still get time-aware urgency
"""

import datetime

from django.test import SimpleTestCase

from apps.core.decision_engine.action_prioritizer import (
    build_action_priorities,
    classify_urgency,
)


class TestMedicineGroupUrgency(SimpleTestCase):
    """Medicine groups must respect overdue status."""

    def test_overdue_medicine_gets_overdue_urgency(self):
        """Medicine group with has_overdue=True → urgency 'overdue'."""
        actions = build_action_priorities(
            medicine_groups=[{
                'title': 'Morning Medications',
                'time_of_day': 'morning',
                'is_foundational': True,
                'goal_name': '',
                'all_taken': False,
                'has_overdue': True,
                'scheduled_time': '09:00',
            }],
            current_time=datetime.time(9, 30),
        )
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]['urgency'], 'overdue')
        self.assertEqual(actions[0]['title'], 'Morning Medications')

    def test_non_overdue_medicine_not_overdue(self):
        """Medicine group without overdue doses → time-based urgency."""
        actions = build_action_priorities(
            medicine_groups=[{
                'title': 'Evening Medications',
                'time_of_day': 'evening',
                'is_foundational': True,
                'goal_name': '',
                'all_taken': False,
                'has_overdue': False,
                'scheduled_time': '18:00',
            }],
            current_time=datetime.time(9, 30),
        )
        self.assertEqual(len(actions), 1)
        # 18:00 is 8.5 hours away → "upcoming"
        self.assertEqual(actions[0]['urgency'], 'upcoming')

    def test_overdue_medicine_sorts_above_non_overdue(self):
        """Overdue morning meds must rank above non-overdue evening meds."""
        actions = build_action_priorities(
            medicine_groups=[
                {
                    'title': 'Evening Medications',
                    'time_of_day': 'evening',
                    'is_foundational': True,
                    'goal_name': '',
                    'all_taken': False,
                    'has_overdue': False,
                    'scheduled_time': '18:00',
                },
                {
                    'title': 'Morning Medications',
                    'time_of_day': 'morning',
                    'is_foundational': True,
                    'goal_name': '',
                    'all_taken': False,
                    'has_overdue': True,
                    'scheduled_time': '09:00',
                },
            ],
            current_time=datetime.time(9, 30),
        )
        self.assertEqual(len(actions), 2)
        # Morning (overdue) must sort first
        self.assertEqual(actions[0]['title'], 'Morning Medications')
        self.assertEqual(actions[0]['urgency'], 'overdue')
        self.assertEqual(actions[1]['title'], 'Evening Medications')

    def test_taken_medicine_excluded(self):
        """All-taken medicine groups are excluded."""
        actions = build_action_priorities(
            medicine_groups=[{
                'title': 'Morning Medications',
                'time_of_day': 'morning',
                'is_foundational': True,
                'goal_name': '',
                'all_taken': True,
                'has_overdue': False,
                'scheduled_time': '09:00',
            }],
            current_time=datetime.time(9, 30),
        )
        self.assertEqual(len(actions), 0)

    def test_overdue_medicine_sorts_above_routine(self):
        """Overdue meds (foundational+overdue) beat non-overdue routines."""
        actions = build_action_priorities(
            pending_routines=[{
                'pk': 1,
                'title': 'Organize workbench',
                'is_foundational': False,
                'commitment_level': 'flexible',
                'goal_name': '',
                'time': datetime.time(10, 45),
                'time_display': '10:45 AM',
                'is_overdue': False,
            }],
            medicine_groups=[{
                'title': 'Morning Medications',
                'time_of_day': 'morning',
                'is_foundational': True,
                'goal_name': '',
                'all_taken': False,
                'has_overdue': True,
                'scheduled_time': '09:00',
            }],
            current_time=datetime.time(9, 30),
        )
        # Morning Medications (foundational+overdue) must be first
        self.assertEqual(actions[0]['title'], 'Morning Medications')


class TestParseTime(SimpleTestCase):
    """_parse_time must handle both 24h and 12h formats."""

    def test_24h_format(self):
        from apps.core.decision_engine.action_prioritizer import _parse_time
        result = _parse_time('08:00')
        self.assertEqual(result, datetime.time(8, 0))

    def test_12h_format_am(self):
        from apps.core.decision_engine.action_prioritizer import _parse_time
        result = _parse_time('8:00 AM')
        self.assertEqual(result, datetime.time(8, 0))

    def test_12h_format_pm(self):
        from apps.core.decision_engine.action_prioritizer import _parse_time
        result = _parse_time('2:30 PM')
        self.assertEqual(result, datetime.time(14, 30))

    def test_none_returns_none(self):
        from apps.core.decision_engine.action_prioritizer import _parse_time
        self.assertIsNone(_parse_time(None))
        self.assertIsNone(_parse_time(''))

    def test_time_object_passthrough(self):
        from apps.core.decision_engine.action_prioritizer import _parse_time
        t = datetime.time(14, 30)
        self.assertEqual(_parse_time(t), t)


class TestNormalizeTimeTo24h(SimpleTestCase):
    """_normalize_time_to_24h in today_execution must produce HH:MM."""

    def test_12h_to_24h(self):
        from apps.core.execution.today_execution import _normalize_time_to_24h
        self.assertEqual(_normalize_time_to_24h('8:00 AM'), '08:00')
        self.assertEqual(_normalize_time_to_24h('2:30 PM'), '14:30')
        self.assertEqual(_normalize_time_to_24h('12:00 PM'), '12:00')
        self.assertEqual(_normalize_time_to_24h('12:00 AM'), '00:00')

    def test_already_24h(self):
        from apps.core.execution.today_execution import _normalize_time_to_24h
        self.assertEqual(_normalize_time_to_24h('08:00'), '08:00')
        self.assertEqual(_normalize_time_to_24h('14:30'), '14:30')

    def test_none_returns_none(self):
        from apps.core.execution.today_execution import _normalize_time_to_24h
        self.assertIsNone(_normalize_time_to_24h(None))
        self.assertIsNone(_normalize_time_to_24h(''))

    def test_time_object(self):
        from apps.core.execution.today_execution import _normalize_time_to_24h
        self.assertEqual(_normalize_time_to_24h(datetime.time(14, 30)), '14:30')


class TestScheduledItemsNeverInFlexible(SimpleTestCase):
    """Items with scheduled_time must NEVER appear in the flexible group."""

    def _make_exec_item(self, source_type, source_id, title, scheduled_time=None,
                        completed=False, importance='standard'):
        return {
            'source_type': source_type,
            'source_id': source_id,
            'title': title,
            'domain': 'health',
            'importance': importance,
            'time_status': 'upcoming',
            'scheduled_time': scheduled_time,
            'grace_minutes': 0,
            'completion_status': 'completed' if completed else 'pending',
            'completed_today': completed,
            'is_actionable': not completed,
            'is_foundational': False,
            'toggle_url': '',
            'detail_url': '',
            'execution_group_type': 'medication_window' if 'med' in source_type else 'standalone',
            'execution_group_id': 'morning' if scheduled_time else None,
            'parent_title': 'Morning Medications' if scheduled_time else '',
        }

    def test_med_with_time_in_time_block_not_flexible(self):
        """Medication with scheduled_time → time block, NOT flexible."""
        from apps.core.decision_engine.action_prioritizer import build_grouped_action_center
        items = [
            self._make_exec_item('medication_dose', 1, 'Lisinopril', '08:00'),
            self._make_exec_item('medication_dose', 2, 'Metformin', '08:00'),
        ]
        result = build_grouped_action_center(items, datetime.time(7, 0))
        # Should have exactly one time block group, no flexible
        flexible_groups = [g for g in result['groups'] if g['group_type'] == 'flexible']
        time_groups = [g for g in result['groups'] if g.get('is_time_block')]
        self.assertEqual(len(flexible_groups), 0, "Scheduled items must NOT be in flexible")
        self.assertEqual(len(time_groups), 1)
        self.assertEqual(time_groups[0]['total'], 2)

    def test_item_without_time_goes_to_flexible(self):
        """Item with no scheduled_time → flexible."""
        from apps.core.decision_engine.action_prioritizer import build_grouped_action_center
        items = [
            self._make_exec_item('task', 10, 'Buy groceries', None),
        ]
        result = build_grouped_action_center(items, datetime.time(10, 0))
        flexible_groups = [g for g in result['groups'] if g['group_type'] == 'flexible']
        self.assertEqual(len(flexible_groups), 1)
        self.assertEqual(flexible_groups[0]['items'][0]['title'], 'Buy groceries')

    def test_no_duplicate_ids_across_groups(self):
        """Same source_id must NOT appear in multiple groups."""
        from apps.core.decision_engine.action_prioritizer import build_grouped_action_center
        items = [
            self._make_exec_item('medication_dose', 1, 'Lisinopril', '08:00'),
            self._make_exec_item('task', 2, 'Buy groceries', None),
            self._make_exec_item('supplement_dose', 3, 'Vitamin D', '08:00'),
        ]
        result = build_grouped_action_center(items, datetime.time(7, 0))
        all_ids = []
        for g in result['groups']:
            for item in g['items']:
                all_ids.append(item['source_id'])
        self.assertEqual(len(all_ids), len(set(all_ids)), "Duplicate IDs found across groups")

    def test_12h_time_format_still_classified_correctly(self):
        """Even if scheduled_time is '8:00 AM' format, item must be in time block.

        This tests the defense-in-depth _parse_time fallback.
        """
        from apps.core.decision_engine.action_prioritizer import build_grouped_action_center
        items = [
            self._make_exec_item('medication_dose', 1, 'Lisinopril', '8:00 AM'),
        ]
        result = build_grouped_action_center(items, datetime.time(7, 0))
        flexible_groups = [g for g in result['groups'] if g['group_type'] == 'flexible']
        self.assertEqual(len(flexible_groups), 0, "12h-format time must NOT land in flexible")

    def test_ordering_by_scheduled_time(self):
        """Items in time blocks must be ordered by scheduled_time."""
        from apps.core.decision_engine.action_prioritizer import build_grouped_action_center
        items = [
            self._make_exec_item('medication_dose', 1, 'Evening Med', '18:00'),
            self._make_exec_item('medication_dose', 2, 'Morning Med', '08:00'),
            self._make_exec_item('task', 3, 'Flexible Task', None),
        ]
        result = build_grouped_action_center(items, datetime.time(7, 0))
        time_groups = [g for g in result['groups'] if g.get('is_time_block')]
        # Should have 2 time blocks (08:00 and 18:00), morning first
        self.assertEqual(len(time_groups), 2)
        self.assertEqual(time_groups[0]['time_block_key'], '08:00')
        self.assertEqual(time_groups[1]['time_block_key'], '18:00')

    def test_completed_past_items_in_done_phase(self):
        """Completed items from hours ago should be in 'done' phase, not NOW."""
        from apps.core.decision_engine.action_prioritizer import build_grouped_action_center
        # 5 AM item, completed — viewed at 5 PM
        items = [
            self._make_exec_item('medication_dose', 1, 'Morning Med', '05:00', completed=True),
            self._make_exec_item('medication_dose', 2, 'Evening Med', '18:00'),
        ]
        result = build_grouped_action_center(items, datetime.time(17, 0))
        done_groups = result['phase_groups'].get('done', [])
        now_groups = result['phase_groups'].get('now', [])
        upcoming_groups = result['phase_groups'].get('upcoming', [])
        # Morning med should be in done, NOT in now or upcoming
        done_titles = [i['title'] for g in done_groups for i in g['items']]
        now_titles = [i['title'] for g in now_groups for i in g['items']]
        upcoming_titles = [i['title'] for g in upcoming_groups for i in g['items']]
        self.assertIn('Morning Med', done_titles)
        self.assertNotIn('Morning Med', now_titles)
        self.assertNotIn('Morning Med', upcoming_titles)

    def test_incomplete_past_items_are_overdue(self):
        """Incomplete items well past scheduled time should be overdue."""
        from apps.core.decision_engine.action_prioritizer import build_grouped_action_center
        # 9 AM item, NOT completed — viewed at 5 PM
        items = [
            self._make_exec_item('routine_item', 5, 'Morning Workout', '09:00'),
        ]
        result = build_grouped_action_center(items, datetime.time(17, 0))
        now_groups = result['phase_groups'].get('now', [])
        # Should be in now (overdue)
        now_titles = [i['title'] for g in now_groups for i in g['items']]
        self.assertIn('Morning Workout', now_titles)
