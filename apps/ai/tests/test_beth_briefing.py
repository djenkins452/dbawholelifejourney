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
    _assess_situation_structured,
    _build_day_narrative,
    _BANNED_WORDS,
    _ORIENTATION_PHRASES,
    _NUDGE_PHRASES,
    _BEHIND_PHRASES,
    _AHEAD_PHRASES,
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

    def test_slightly_overdue_no_completions_is_orientation(self):
        """Items only slightly past schedule with no completions → orientation."""
        user_now = timezone.now().replace(hour=7, minute=0)
        sched = user_now.replace(hour=6, minute=30)  # 30 min ago
        state, text = _assess_situation_structured(
            overdue=[{'label': 'x', 'item': {'scheduled_time': sched}}],
            completed=[],
            coming_up=[],
            user_now=user_now,
        )
        # Orientation tier: on_track state, phrase from orientation bank
        self.assertEqual(state, 'on_track')
        self.assertIn(text, _ORIENTATION_PHRASES)

    def test_significantly_overdue_means_behind(self):
        """Items 2+ hours past schedule → behind."""
        user_now = timezone.now().replace(hour=9, minute=0)
        sched = user_now.replace(hour=6, minute=0)  # 3 hours ago
        entry = {'label': 'x', 'item': {'scheduled_time': sched}}
        state, text = _assess_situation_structured(
            overdue=[entry, entry, entry],
            completed=[],
            coming_up=[],
            user_now=user_now,
        )
        self.assertEqual(state, 'behind')
        self.assertIn(text, _BEHIND_PHRASES)

    def test_moderate_overdue_with_activity_means_nudge(self):
        """Overdue items when user has some completions → nudge."""
        user_now = timezone.now().replace(hour=7, minute=30)
        sched = user_now.replace(hour=6, minute=30)  # 60 min ago
        state, text = _assess_situation_structured(
            overdue=[{'label': 'x', 'item': {'scheduled_time': sched}}],
            completed=[{'label': 'done'}],
            coming_up=[],
            user_now=user_now,
        )
        self.assertEqual(state, 'behind')
        self.assertIn(text, _NUDGE_PHRASES)

    def test_completed_no_upcoming_means_ahead(self):
        state, text = _assess_situation_structured(
            overdue=[],
            completed=[{'label': 'x'}],
            coming_up=[],
            user_now=timezone.now().replace(hour=7),
        )
        self.assertEqual(state, 'ahead')
        self.assertIn(text, _AHEAD_PHRASES)

    def test_phrases_rotate_by_day(self):
        """Different days produce different phrases from same bank."""
        from apps.ai.beth_checkin_renderer import _rotating_phrase
        phrases = ("A", "B", "C", "D")
        # Two different days should get different phrases (unless same mod)
        day1 = timezone.now().replace(month=1, day=1)
        day2 = timezone.now().replace(month=1, day=2)
        p1 = _rotating_phrase(phrases, day1)
        p2 = _rotating_phrase(phrases, day2)
        self.assertIn(p1, phrases)
        self.assertIn(p2, phrases)
        self.assertNotEqual(p1, p2)

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

    def test_tight_morning_orientation_no_reschedule(self):
        """Scenario: 5:53 AM, shower at 7:00 AM, slightly overdue items.
        Orientation tier (< 90 min, no completions) → no reschedule suggestion.
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
        # Orientation: should NOT suggest rescheduling
        self.assertNotIn("later today", output)
        # Should NOT contain domain labels
        for word in _BANNED_WORDS:
            self.assertNotIn(word, output.lower())

    def test_tight_morning_behind_shows_reschedule(self):
        """Scenario: 8:30 AM, shower at 9:00 AM, 2h+ overdue items.
        Behind tier → reschedule suggestion appears.
        """
        user_now = timezone.now().replace(hour=8, minute=30, second=0)
        bible = _make_item('Bible Reading', '5:00 AM', 5, 0, priority='foundational')
        prayer = _make_item('Prayer', '5:15 AM', 5, 15, priority='foundational')
        workout = _make_item('Workout', '6:15 AM', 6, 15, priority='foundational')
        shower = _make_item('Shower', '9:00 AM', 9, 0)

        ctx = {
            'all_items': [bible, prayer, workout, shower],
            'foundation': [],
            'overdue': [
                _make_entry(bible), _make_entry(prayer), _make_entry(workout),
            ],
            'coming_up': [],
            'later': [_make_entry(shower)],
            'completed': [{'label': 'Wake up'}],
            'next': 'Bible Reading',
        }

        output = _render_morning(ctx, self.user, user_now)

        # Behind: should mention items and reschedule
        self.assertIn('Bible Reading', output)
        self.assertIn('Workout', output)
        self.assertIn("later today", output)
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
        self.assertNotIn("later today", output)

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

    def test_evening_future_items_not_marked_missed(self):
        """Items in coming_up/later should say 'Still ahead', not 'Missed'."""
        user = MagicMock()
        user.first_name = 'Danny'
        user.id = 1
        user_now = timezone.now().replace(hour=19, minute=0)

        done = _make_item('Bible Reading', '5:00 AM', 5, 0, completed=True)
        overdue_item = _make_item('Workout', '6:15 AM', 6, 15)
        future_item = _make_item('Journal', '8:00 PM', 20, 0)
        late_item = _make_item('Magnesium', '10:00 PM', 22, 0)

        ctx = {
            'all_items': [done, overdue_item, future_item, late_item],
            'foundation': [],
            'overdue': [_make_entry(overdue_item)],
            'coming_up': [_make_entry(future_item)],
            'later': [_make_entry(late_item)],
            'completed': [_make_entry(done)],
            'next': '',
        }

        output = _render_evening(ctx, user, user_now)

        # Overdue item should be "Missed"
        self.assertIn('Missed', output)
        self.assertIn('Workout', output)
        # Future items should be "Still ahead", not "Missed"
        self.assertIn('Still ahead', output)
        self.assertIn('Journal', output)
        self.assertIn('Magnesium', output)
        # Verify future items are NOT in the Missed line
        missed_line = [l for l in output.split('\n') if 'Missed' in l][0]
        self.assertNotIn('Journal', missed_line)
        self.assertNotIn('Magnesium', missed_line)


class TestCanonicalRendererEnforcement(TestCase):
    """Enforce that all user-facing CoS paths use the canonical renderer.

    These tests verify that:
    1. No user-facing path produces domain labels (Faith:, Routines:, etc.)
    2. The fallback response uses the canonical renderer
    3. Proactive generators use the canonical renderer
    4. No path produces count-dump language (x/y completed, x/y done)
    """

    # Domain labels that must NEVER appear in user-facing output
    _DOMAIN_LABELS = [
        'Faith:', 'Routines:', 'Tasks:', 'Medications:',
        'Workout:', 'Journal:', 'Health:',
    ]

    # Count-dump patterns that must NEVER appear in user-facing output
    _COUNT_PATTERNS = [
        'Day closing:',
        'Meds:',
    ]

    def test_fallback_response_no_domain_labels(self):
        """_get_fallback_response must not produce domain labels."""
        from apps.ai.personal_assistant import PersonalAssistant

        # The fallback uses build_cos_structured_output which needs a real
        # user, but we can test the code path by verifying the function
        # no longer references cos_fact_statements for user-facing output.
        import ast
        import inspect
        source = inspect.getsource(PersonalAssistant._get_fallback_response)
        # Must NOT contain domain-dump format strings
        self.assertNotIn("Faith:", source)
        self.assertNotIn("Routines:", source)
        self.assertNotIn("Tasks:", source)
        self.assertNotIn("Workout:", source)
        self.assertNotIn("Journal:", source)
        # Must reference the canonical renderer
        self.assertIn('build_cos_structured_output', source)

    def test_midday_generator_uses_canonical_renderer(self):
        """generate_midday_alignment_for_user must use render_checkin_for_time."""
        import inspect
        from apps.ai.proactive_checkins import (
            generate_midday_alignment_for_user,
        )
        source = inspect.getsource(generate_midday_alignment_for_user)
        # Must use canonical renderer
        self.assertIn('render_checkin_for_time', source)
        # Must NOT build count-dump strings
        self.assertNotIn('/{', source)  # No f"x/{y}" patterns
        self.assertNotIn('done"', source)  # No "x done" strings

    def test_evening_generator_uses_canonical_renderer(self):
        """generate_evening_wrap_for_user must use render_checkin_for_time."""
        import inspect
        from apps.ai.proactive_checkins import (
            generate_evening_wrap_for_user,
        )
        source = inspect.getsource(generate_evening_wrap_for_user)
        # Must use canonical renderer
        self.assertIn('render_checkin_for_time', source)
        # Must NOT build count-dump strings
        self.assertNotIn('Day closing', source)
        self.assertNotIn('Meds:', source)
        self.assertNotIn('/{', source)

    def test_afternoon_generator_no_count_language(self):
        """generate_afternoon_momentum_for_user must not use count language."""
        import inspect
        from apps.ai.proactive_checkins import (
            generate_afternoon_momentum_for_user,
        )
        source = inspect.getsource(generate_afternoon_momentum_for_user)
        # Must NOT say "N non-negotiables still pending"
        self.assertNotIn('non-negotiables still pending', source)

    def test_canonical_renderer_bans_domain_words(self):
        """The canonical renderer must enforce banned words."""
        self.assertTrue(
            'items' in _BANNED_WORDS
            and 'tasks' in _BANNED_WORDS
            and 'routines' in _BANNED_WORDS,
            "Canonical renderer must ban domain aggregate words",
        )

    def test_build_cos_structured_output_returns_required_keys(self):
        """build_cos_structured_output fallback must return all keys."""
        from apps.ai.beth_checkin_renderer import build_cos_structured_output
        from unittest.mock import patch

        # Force an exception to test the fallback path
        with patch(
            'apps.ai.beth_checkin_renderer._build_structured_from_truth',
            side_effect=Exception('test'),
        ):
            result = build_cos_structured_output(MagicMock(id=1))

        required_keys = [
            'greeting', 'day_narrative', 'state', 'state_text',
            'next_commitment', 'do_now', 'sequence', 'move_later',
            'adjustment_reason', 'decision_required', 'completed',
            'phase', 'rendered_text',
        ]
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")

        # Fallback rendered_text must not contain domain labels
        text = result['rendered_text']
        for label in self._DOMAIN_LABELS:
            self.assertNotIn(label, text)
