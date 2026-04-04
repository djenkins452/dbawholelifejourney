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
