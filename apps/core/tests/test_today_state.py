"""
Tests for the Today State deterministic truth layer.

Covers:
  - Fresh morning (no activity)
  - Partial completion
  - Strong signals but no activity (signals don't override truth)
  - Missing data guidance
  - Routine accuracy
  - Format injection output
"""

from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.core.services.today_state import (
    _build_confidence_rollup,
    _classify_domain_states,
    build_today_state,
    format_today_state_injection,
)
from apps.core.execution.execution_truth_engine import (
    _apply_routine_faith_bridge as _bridge_routine_to_faith,
)


def _mock_user(user_today=None):
    """Create a mock user with preferences."""
    user = MagicMock()
    user.id = 1
    user.preferences = MagicMock()
    user.preferences.timezone = 'America/Chicago'
    return user


class TestBuildTodayState(TestCase):
    """Test build_today_state returns correct structure."""

    @patch('apps.core.execution.execution_truth_engine.get_execution_truth')
    def test_returns_complete_structure(self, mock_truth):
        mock_truth.return_value = {
            'date': '2026-03-20',
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False, 'prayer_source': None, 'bible_source': None},
                'workout': {'completed': False},
                'journal': {'completed': False},
            },
            'routines': {'items': {}, 'total': 0, 'completed': 0, 'fully_complete': False, '_raw_items': {}},
            'tasks': {'total': 0, 'completed': 0, 'completed_today_all': 0},
            'medications': {'taken': 0, 'expected': 0, 'all_taken': True},
        }

        user = _mock_user()
        state = build_today_state(user)

        self.assertEqual(state['date'], '2026-03-20')
        self.assertIn('domains', state)
        self.assertIn('faith', state['domains'])
        self.assertIn('health', state['domains'])
        self.assertIn('journal', state['domains'])
        self.assertIn('routines', state)
        self.assertIn('tasks', state)
        self.assertIn('medications', state)
        self.assertIn('data_confidence', state)


class TestFreshMorning(TestCase):
    """Test 1: Fresh morning — no activity logged."""

    def test_all_domains_not_done(self):
        state = {
            'date': '2026-03-20',
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False, 'confidence': 'high'},
                'health': {'workout_completed': False, 'medications_taken': False, 'confidence': 'high'},
                'journal': {'completed': False, 'confidence': 'high'},
            },
            'routines': {'items': {}, 'total': 4, 'completed': 0, 'fully_complete': False},
            'tasks': {'completed': 0, 'total': 3},
            'medications': {'taken': 0, 'expected': 5, 'all_taken': False},
            'data_confidence': {},
        }
        state['data_confidence'] = _build_confidence_rollup(state)

        output = format_today_state_injection(state)

        self.assertIn('NOT DONE', output)
        self.assertIn('Faith: NOT DONE', output)
        self.assertIn('Workout: NOT DONE', output)
        self.assertIn('Journaling: NOT DONE', output)
        self.assertIn('0/4 completed', output)
        self.assertIn('0/3 completed', output)
        self.assertIn('0/5 taken', output)


class TestPartialCompletion(TestCase):
    """Test 2: Prayer complete, workout not."""

    def test_mixed_completion(self):
        state = {
            'date': '2026-03-20',
            'domains': {
                'faith': {'prayer_completed': True, 'bible_reading_completed': False, 'confidence': 'high'},
                'health': {'workout_completed': False, 'medications_taken': False, 'confidence': 'high'},
                'journal': {'completed': False, 'confidence': 'high'},
            },
            'routines': {'items': {}, 'total': 0, 'completed': 0, 'fully_complete': False},
            'tasks': {'completed': 0, 'total': 0},
            'medications': {'taken': 0, 'expected': 0, 'all_taken': True},
            'data_confidence': {},
        }
        state['data_confidence'] = _build_confidence_rollup(state)

        output = format_today_state_injection(state)

        self.assertIn('Faith: DONE', output)
        self.assertIn('prayer', output)
        self.assertIn('Workout: NOT DONE', output)

        # Domain classification
        domain_states = _classify_domain_states(state)
        self.assertEqual(domain_states['faith'], 'SATISFIED')
        self.assertEqual(domain_states['workout'], 'ACTIONABLE')


class TestSignalsDontOverrideTruth(TestCase):
    """Test 3: Strong signals exist but no activity logged today.

    Signals must NEVER override today_state. The injection should show
    NOT DONE even when signals suggest high consistency.
    """

    def test_no_activity_despite_signals(self):
        # State shows nothing done — regardless of what signals say
        state = {
            'date': '2026-03-20',
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False, 'confidence': 'high'},
                'health': {'workout_completed': False, 'medications_taken': False, 'confidence': 'high'},
                'journal': {'completed': False, 'confidence': 'high'},
            },
            'routines': {'items': {}, 'total': 0, 'completed': 0, 'fully_complete': False},
            'tasks': {'completed': 0, 'total': 0},
            'medications': {'taken': 0, 'expected': 0, 'all_taken': True},
            'data_confidence': {},
        }
        state['data_confidence'] = _build_confidence_rollup(state)

        output = format_today_state_injection(state)

        # Every domain must show NOT DONE
        self.assertIn('Faith: NOT DONE', output)
        self.assertIn('Workout: NOT DONE', output)
        self.assertIn('Journaling: NOT DONE', output)

        # The injection must include the anti-inference rule
        self.assertIn('NEVER infer completion from streaks', output)


class TestMissingDataGuidance(TestCase):
    """Test 4: Missing data generates explainable guidance."""

    def test_missing_journal_guidance(self):
        state = {
            'date': '2026-03-20',
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False, 'confidence': 'high'},
                'health': {'workout_completed': False, 'medications_taken': False, 'confidence': 'high'},
                'journal': {'completed': False, 'confidence': 'high'},
            },
            'routines': {'items': {}, 'total': 0, 'completed': 0, 'fully_complete': False},
            'tasks': {'completed': 0, 'total': 0},
            'medications': {'taken': 0, 'expected': 0, 'all_taken': True},
            'data_confidence': {},
        }
        state['data_confidence'] = _build_confidence_rollup(state)

        output = format_today_state_injection(state)

        # Missing journal should produce specific guidance
        self.assertIn('JOURNAL', output)
        self.assertIn('journal', output.lower())
        self.assertIn('Why it matters', output)
        self.assertIn('/journal/', output)


class TestRoutineAccuracy(TestCase):
    """Test 5: Routine progress is deterministically reported."""

    def test_routine_progress(self):
        state = {
            'date': '2026-03-20',
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False, 'confidence': 'high'},
                'health': {'workout_completed': False, 'medications_taken': False, 'confidence': 'high'},
                'journal': {'completed': False, 'confidence': 'high'},
            },
            'routines': {
                'items': {
                    'Morning Routine': {'total': 4, 'completed': 0, 'fully_complete': False},
                },
                'total': 4,
                'completed': 0,
                'fully_complete': False,
            },
            'tasks': {'completed': 0, 'total': 0},
            'medications': {'taken': 0, 'expected': 0, 'all_taken': True},
            'data_confidence': {},
        }
        state['data_confidence'] = _build_confidence_rollup(state)

        output = format_today_state_injection(state)

        self.assertIn('0/4 completed', output)
        self.assertIn('Morning Routine', output)
        self.assertIn('NOT ALL DONE', output)


class TestDomainStateClassification(TestCase):
    """Test domain state classification logic."""

    def test_all_actionable(self):
        state = {
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False},
                'health': {'workout_completed': False},
                'journal': {'completed': False},
            },
            'routines': {'total': 3, 'completed': 0, 'fully_complete': False},
            'tasks': {'total': 2, 'completed': 0},
            'medications': {'expected': 5, 'taken': 0, 'all_taken': False},
        }
        states = _classify_domain_states(state)

        self.assertEqual(states['faith'], 'ACTIONABLE')
        self.assertEqual(states['workout'], 'ACTIONABLE')
        self.assertEqual(states['journaling'], 'ACTIONABLE')
        self.assertEqual(states['medicine'], 'ACTIONABLE')
        self.assertEqual(states['routines'], 'ACTIONABLE')
        self.assertEqual(states['tasks'], 'ACTIONABLE')

    def test_all_satisfied(self):
        state = {
            'domains': {
                'faith': {'prayer_completed': True, 'bible_reading_completed': True},
                'health': {'workout_completed': True},
                'journal': {'completed': True},
            },
            'routines': {'total': 3, 'completed': 3, 'fully_complete': True},
            'tasks': {'total': 2, 'completed': 2},
            'medications': {'expected': 5, 'taken': 5, 'all_taken': True},
        }
        states = _classify_domain_states(state)

        self.assertEqual(states['faith'], 'SATISFIED')
        self.assertEqual(states['workout'], 'SATISFIED')
        self.assertEqual(states['journaling'], 'SATISFIED')
        self.assertEqual(states['medicine'], 'SATISFIED')
        self.assertEqual(states['routines'], 'SATISFIED')
        self.assertEqual(states['tasks'], 'SATISFIED')

    def test_no_meds_is_irrelevant(self):
        state = {
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False},
                'health': {'workout_completed': False},
                'journal': {'completed': False},
            },
            'routines': {'total': 0, 'completed': 0, 'fully_complete': False},
            'tasks': {'total': 0, 'completed': 0},
            'medications': {'expected': 0, 'taken': 0, 'all_taken': True},
        }
        states = _classify_domain_states(state)

        self.assertEqual(states['medicine'], 'IRRELEVANT')
        self.assertEqual(states['routines'], 'IRRELEVANT')
        self.assertEqual(states['tasks'], 'IRRELEVANT')


class TestConfidenceRollup(TestCase):
    """Test data confidence assessment."""

    def test_all_present(self):
        state = {
            'domains': {
                'faith': {'prayer_completed': True, 'bible_reading_completed': False, 'confidence': 'high'},
                'health': {'workout_completed': True, 'medications_taken': True, 'confidence': 'high'},
                'journal': {'completed': True, 'confidence': 'high'},
            },
            'routines': {'total': 3, 'completed': 3, 'fully_complete': True},
            'tasks': {'total': 2, 'completed': 2},
        }
        rollup = _build_confidence_rollup(state)

        self.assertEqual(rollup['faith'], 'present')
        self.assertEqual(rollup['health'], 'present')
        self.assertEqual(rollup['journal'], 'present')
        self.assertEqual(rollup['routines'], 'present')
        self.assertEqual(rollup['tasks'], 'present')

    def test_all_missing(self):
        state = {
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False, 'confidence': 'high'},
                'health': {'workout_completed': False, 'medications_taken': False, 'confidence': 'high'},
                'journal': {'completed': False, 'confidence': 'high'},
            },
            'routines': {'total': 0, 'completed': 0, 'fully_complete': False},
            'tasks': {'total': 0, 'completed': 0},
        }
        rollup = _build_confidence_rollup(state)

        self.assertEqual(rollup['faith'], 'missing')
        self.assertEqual(rollup['health'], 'missing')
        self.assertEqual(rollup['journal'], 'missing')
        self.assertEqual(rollup['routines'], 'missing')
        self.assertEqual(rollup['tasks'], 'missing')

    def test_partial_routines(self):
        state = {
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False, 'confidence': 'high'},
                'health': {'workout_completed': False, 'medications_taken': False, 'confidence': 'high'},
                'journal': {'completed': False, 'confidence': 'high'},
            },
            'routines': {'total': 4, 'completed': 2, 'fully_complete': False},
            'tasks': {'total': 3, 'completed': 1},
        }
        rollup = _build_confidence_rollup(state)

        self.assertEqual(rollup['routines'], 'partial')
        self.assertEqual(rollup['tasks'], 'partial')


class TestFormatInjection(TestCase):
    """Test format_today_state_injection output."""

    def test_includes_truth_enforcement(self):
        state = {
            'date': '2026-03-20',
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False, 'confidence': 'high'},
                'health': {'workout_completed': False, 'medications_taken': False, 'confidence': 'high'},
                'journal': {'completed': False, 'confidence': 'high'},
            },
            'routines': {'items': {}, 'total': 0, 'completed': 0, 'fully_complete': False},
            'tasks': {'completed': 0, 'total': 0},
            'medications': {'taken': 0, 'expected': 0, 'all_taken': True},
            'data_confidence': {'faith': 'missing', 'health': 'missing', 'journal': 'missing', 'routines': 'missing', 'tasks': 'missing'},
        }

        output = format_today_state_injection(state)

        # Must include authoritative header
        self.assertIn("TODAY'S TRUTH STATE", output)
        self.assertIn('AUTHORITATIVE', output)

        # Must include truth enforcement
        self.assertIn('TRUTH ENFORCEMENT', output)
        self.assertIn('MUST NOT say it is done', output)

        # Must include anti-inference rule
        self.assertIn('NEVER infer completion from streaks', output)

        # Must include response mode
        self.assertIn('RESPONSE MODE', output)

    def test_reinforcement_mode_when_all_done(self):
        state = {
            'date': '2026-03-20',
            'domains': {
                'faith': {'prayer_completed': True, 'bible_reading_completed': True, 'confidence': 'high'},
                'health': {'workout_completed': True, 'medications_taken': True, 'confidence': 'high'},
                'journal': {'completed': True, 'confidence': 'high'},
            },
            'routines': {'items': {}, 'total': 0, 'completed': 0, 'fully_complete': False},
            'tasks': {'completed': 0, 'total': 0},
            'medications': {'taken': 0, 'expected': 0, 'all_taken': True},
            'data_confidence': {'faith': 'present', 'health': 'present', 'journal': 'present', 'routines': 'missing', 'tasks': 'missing'},
        }

        output = format_today_state_injection(state)

        self.assertIn('REINFORCEMENT', output)
        self.assertIn('All domains satisfied', output)


class TestRoutineToFaithBridge(TestCase):
    """Test that routine items bridge to faith domain."""

    def test_prayer_routine_bridges_to_faith(self):
        """Completing 'Prayer Time' in routine should mark faith prayer done."""
        state = {
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False, 'confidence': 'high'},
            },
            'routines': {
                'items': {'Morning Routine': {'total': 4, 'completed': 1, 'fully_complete': False}},
                'total': 4, 'completed': 1, 'fully_complete': False,
                '_raw_items': {
                    'morning': [
                        {'item_name': 'Prayer Time', 'is_completed': True, 'routine_name': 'Morning Routine'},
                        {'item_name': 'Exercise', 'is_completed': False, 'routine_name': 'Morning Routine'},
                    ],
                },
            },
        }

        _bridge_routine_to_faith(state)

        self.assertTrue(state['domains']['faith']['prayer_completed'])
        self.assertFalse(state['domains']['faith']['bible_reading_completed'])

    def test_bible_routine_bridges_to_faith(self):
        """Completing 'Bible Reading' in routine should mark faith bible done."""
        state = {
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False, 'confidence': 'high'},
            },
            'routines': {
                'items': {}, 'total': 2, 'completed': 1, 'fully_complete': False,
                '_raw_items': {
                    'morning': [
                        {'item_name': 'Bible Reading', 'is_completed': True, 'routine_name': 'Morning Routine'},
                    ],
                },
            },
        }

        _bridge_routine_to_faith(state)

        self.assertFalse(state['domains']['faith']['prayer_completed'])
        self.assertTrue(state['domains']['faith']['bible_reading_completed'])

    def test_bridge_does_not_downgrade(self):
        """If faith already shows prayer done, bridge must not downgrade it."""
        state = {
            'domains': {
                'faith': {'prayer_completed': True, 'bible_reading_completed': True, 'confidence': 'high'},
            },
            'routines': {
                'items': {}, 'total': 2, 'completed': 0, 'fully_complete': False,
                '_raw_items': {
                    'morning': [
                        {'item_name': 'Prayer Time', 'is_completed': False, 'routine_name': 'Morning Routine'},
                        {'item_name': 'Bible Reading', 'is_completed': False, 'routine_name': 'Morning Routine'},
                    ],
                },
            },
        }

        _bridge_routine_to_faith(state)

        # Should stay True — bridge only upgrades, never downgrades
        self.assertTrue(state['domains']['faith']['prayer_completed'])
        self.assertTrue(state['domains']['faith']['bible_reading_completed'])

    def test_bridge_no_raw_items_is_noop(self):
        """If no _raw_items, bridge does nothing."""
        state = {
            'domains': {
                'faith': {'prayer_completed': False, 'bible_reading_completed': False, 'confidence': 'high'},
            },
            'routines': {'items': {}, 'total': 0, 'completed': 0, 'fully_complete': False},
        }

        _bridge_routine_to_faith(state)

        self.assertFalse(state['domains']['faith']['prayer_completed'])
        self.assertFalse(state['domains']['faith']['bible_reading_completed'])
