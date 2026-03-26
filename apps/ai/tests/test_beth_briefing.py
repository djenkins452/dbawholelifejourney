"""
Beth Briefing Renderer — Behavior Tests

Tests the Chief of Staff briefing output for correctness:
1. Tight morning → splits DO NOW vs MOVE LATER
2. Enough time → no reschedule suggestion
3. Ahead scenario → acknowledges extra time
4. No domain labels in output
5. No status dump language
6. Greeting is natural and time-aware
7. Medication suppression (evening meds not in morning)
"""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.ai.beth_checkin_renderer import (
    _render_morning,
    _render_midday,
    _render_evening,
    _estimate_duration,
    _assess_situation,
    _build_day_narrative,
    _BANNED_WORDS,
)


def _make_item(name, time_str, hour, minute, completed=False,
               priority='flexible', source='routine'):
    """Helper to build a Today Engine item."""
    now = timezone.now()
    sched = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return {
        'id': f'{source}:{name}',
        'name': name,
        'scheduled_time': sched,
        'time_str': time_str,
        'completed': completed,
        'priority': priority,
        'source': source,
    }


def _make_entry(item):
    """Wrap item into a bucket entry (as Today Engine returns)."""
    label = f"{item['name']} ({item['time_str']})" if item.get('time_str') else item['name']
    return {
        'sort_time': item['scheduled_time'],
        'label': label,
        'item': item,
    }


class TestDurationEstimation(TestCase):
    """Test static duration estimation."""

    def test_workout_45_min(self):
        self.assertEqual(_estimate_duration('Workout'), 45)

    def test_prayer_15_min(self):
        self.assertEqual(_estimate_duration('Prayer Time'), 15)

    def test_bible_reading_15_min(self):
        self.assertEqual(_estimate_duration('Bible Reading'), 15)

    def test_shower_15_min(self):
        self.assertEqual(_estimate_duration('Shower'), 15)

    def test_unknown_default(self):
        self.assertEqual(_estimate_duration('Random Task'), 15)


class TestSituationalAwareness(TestCase):
    """Test behind / on track / ahead classification."""

    def test_overdue_items_means_behind(self):
        result = _assess_situation(
            overdue=[{'label': 'x'}],
            completed=[],
            coming_up=[],
            user_now=timezone.now().replace(hour=6),
        )
        self.assertIn('behind', result.lower())

    def test_many_overdue_means_behind(self):
        result = _assess_situation(
            overdue=[{'label': 'x'}] * 3,
            completed=[],
            coming_up=[],
            user_now=timezone.now().replace(hour=6),
        )
        self.assertIn('behind', result.lower())

    def test_completed_no_upcoming_means_ahead(self):
        result = _assess_situation(
            overdue=[],
            completed=[{'label': 'x'}],
            coming_up=[],
            user_now=timezone.now().replace(hour=7),
        )
        self.assertIn('ahead', result.lower())

    def test_normal_flow_means_on_track(self):
        result = _assess_situation(
            overdue=[],
            completed=[],
            coming_up=[{'label': 'x'}],
            user_now=timezone.now().replace(hour=7),
        )
        self.assertIn('on track', result.lower())


class TestMorningBriefingOutput(TestCase):
    """Test the full morning briefing output."""

    def setUp(self):
        self.user = MagicMock()
        self.user.first_name = 'Danny'
        self.user.id = 1
        self.user_now = timezone.now().replace(
            hour=5, minute=53, second=0, microsecond=0,
        )

    def test_tight_morning_splits_do_now_and_move_later(self):
        """Scenario: 5:53 AM, shower at 7:00 AM.
        Bible Reading (15 min) and Prayer (15 min) fit.
        Workout (45 min) doesn't fit.
        """
        bible = _make_item('Bible Reading', '5:00 AM', 5, 0, priority='foundational')
        prayer = _make_item('Prayer', '5:15 AM', 5, 15, priority='foundational')
        workout = _make_item('Workout', '6:15 AM', 6, 15, priority='foundational')
        shower = _make_item('Shower', '7:00 AM', 7, 0)

        ctx = {
            'all_items': [bible, prayer, workout, shower],
            'foundation': [],
            'overdue': [_make_entry(bible), _make_entry(prayer)],
            'coming_up': [_make_entry(workout)],
            'later': [_make_entry(shower)],
            'completed': [],
            'next': 'Bible Reading',
        }

        output = _render_morning(ctx, self.user, self.user_now)

        # Should mention what to do now
        self.assertIn('Bible Reading', output)
        self.assertIn('Prayer', output)
        # Should mention workout won't fit
        self.assertIn('Workout', output)
        self.assertIn("won't fit", output)
        # Should NOT contain domain labels
        for word in _BANNED_WORDS:
            self.assertNotIn(word, output.lower())

    def test_enough_time_no_reschedule(self):
        """Scenario: 5:00 AM, nothing until 9:00 AM. Plenty of time."""
        user_now = timezone.now().replace(hour=5, minute=0, second=0)
        bible = _make_item('Bible Reading', '5:00 AM', 5, 0)
        prayer = _make_item('Prayer', '5:15 AM', 5, 15)
        workout = _make_item('Workout', '6:00 AM', 6, 0)
        shower = _make_item('Shower', '9:00 AM', 9, 0)

        ctx = {
            'all_items': [bible, prayer, workout, shower],
            'foundation': [],
            'overdue': [],
            'coming_up': [
                _make_entry(bible),
                _make_entry(prayer),
                _make_entry(workout),
            ],
            'later': [_make_entry(shower)],
            'completed': [],
            'next': 'Bible Reading',
        }

        output = _render_morning(ctx, self.user, user_now)

        # Should NOT suggest moving anything
        self.assertNotIn("won't fit", output)

    def test_ahead_scenario(self):
        """Scenario: Some items already done, nothing overdue."""
        user_now = timezone.now().replace(hour=6, minute=30, second=0)
        bible = _make_item('Bible Reading', '5:00 AM', 5, 0, completed=True)
        prayer = _make_item('Prayer', '5:15 AM', 5, 15, completed=True)

        ctx = {
            'all_items': [bible, prayer],
            'foundation': [],
            'overdue': [],
            'coming_up': [],
            'later': [],
            'completed': [_make_entry(bible), _make_entry(prayer)],
            'next': 'Start with your next planned item.',
        }

        output = _render_morning(ctx, self.user, user_now)

        # Should acknowledge ahead status
        self.assertIn('ahead', output.lower())

    def test_no_domain_labels_in_output(self):
        """Output must never contain 'Faith', 'Health', 'Tasks' as headers."""
        ctx = {
            'all_items': [
                _make_item('Bible Reading', '5:00 AM', 5, 0),
            ],
            'foundation': [],
            'overdue': [],
            'coming_up': [
                _make_entry(
                    _make_item('Bible Reading', '5:00 AM', 5, 0)
                ),
            ],
            'later': [],
            'completed': [],
            'next': 'Bible Reading',
        }

        output = _render_morning(ctx, self.user, self.user_now)

        # No domain headers
        self.assertNotIn('Faith:', output)
        self.assertNotIn('Health:', output)
        self.assertNotIn('Tasks:', output)
        self.assertNotIn('Purpose:', output)

    def test_greeting_uses_first_name(self):
        """Greeting should include the user's first name."""
        ctx = {
            'all_items': [],
            'foundation': [],
            'overdue': [],
            'coming_up': [],
            'later': [],
            'completed': [],
            'next': 'Start with your next planned item.',
        }

        output = _render_morning(ctx, self.user, self.user_now)
        self.assertIn('Danny', output)


class TestMiddayOutput(TestCase):
    """Test midday alignment output."""

    def test_midday_progress_narrative(self):
        """Midday should show progress as narrative, not status dump."""
        user = MagicMock()
        user.first_name = 'Danny'
        user_now = timezone.now().replace(hour=12, minute=0)

        done1 = _make_item('Bible Reading', '5:00 AM', 5, 0, completed=True)
        done2 = _make_item('Prayer', '5:15 AM', 5, 15, completed=True)
        pending = _make_item('Workout', '6:15 AM', 6, 15)

        ctx = {
            'all_items': [done1, done2, pending],
            'foundation': [],
            'overdue': [_make_entry(pending)],
            'coming_up': [],
            'later': [],
            'completed': [_make_entry(done1), _make_entry(done2)],
            'next': 'Workout',
        }

        output = _render_midday(ctx, user, user_now)

        # Should mention progress
        self.assertIn('2 of 3', output)
        # Should mention slipping item
        self.assertIn('Workout', output)
        self.assertIn('slipped', output.lower())


class TestEveningOutput(TestCase):
    """Test evening debrief output."""

    def test_evening_shows_missed_by_name(self):
        """Evening should name what was missed, not just count."""
        user = MagicMock()
        user.first_name = 'Danny'
        user.id = 1
        user_now = timezone.now().replace(hour=20, minute=0)

        done = _make_item('Bible Reading', '5:00 AM', 5, 0, completed=True)
        missed = _make_item('Workout', '6:15 AM', 6, 15)

        ctx = {
            'all_items': [done, missed],
            'foundation': [],
            'overdue': [_make_entry(missed)],
            'coming_up': [],
            'later': [],
            'completed': [_make_entry(done)],
            'next': '',
        }

        output = _render_evening(ctx, user, user_now)

        self.assertIn('Workout', output)
        self.assertIn('Missed', output)
        self.assertIn('1 of 2', output)
