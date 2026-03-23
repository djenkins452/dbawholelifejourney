"""
Tests for Signal Engine Phase 2: Expected + State Integration.

Verifies that SignalSnapshots carry correct `expected` and `state` fields
based on the Execution Truth Engine expected map.
"""
import datetime
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.core.ai_eae.models import SignalSnapshot
from apps.core.ai_eae.signal_aggregation import SignalAggregationService
from apps.users.models import User


def _create_test_user(email='signal-state@test.com'):
    """Create a test user with required onboarding setup."""
    from apps.users.models import TermsAcceptance
    user = User.objects.create_user(email=email, password='testpass123')
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# Default expected map where nothing is expected
NOTHING_EXPECTED = {
    'workout': False,
    'journal': False,
    'faith': False,
    'medication': False,
    'tasks': False,
    'biometrics': False,
    'nutrition': False,
    'brain_training': False,
    'relationships': False,
}

# Expected map with all core domains expected
ALL_EXPECTED = {
    'workout': True,
    'journal': True,
    'faith': True,
    'medication': True,
    'tasks': True,
    'biometrics': False,
    'nutrition': False,
    'brain_training': False,
    'relationships': False,
}


class TestExpectedMap(TestCase):
    """Test the expected map module."""

    def setUp(self):
        self.user = _create_test_user()
        self.today = datetime.date.today()

    @patch('apps.core.execution.expected_map.get_execution_truth')
    def test_expected_map_parses_ete_output(self, mock_ete):
        """Expected map correctly extracts flags from ETE output."""
        from apps.core.execution.expected_map import get_expected_map

        mock_ete.return_value = {
            'domains': {
                'workout': {'expected': True, 'completed': False},
                'journal': {'expected': False, 'completed': False},
                'faith': {
                    'prayer_expected': True,
                    'bible_expected': False,
                    'prayer_completed': False,
                    'bible_reading_completed': False,
                },
            },
            'medications': {'expected': 3, 'taken': 1, 'all_taken': False},
            'tasks': {'total': 2, 'completed': 0},
            'routines': {'total': 0, 'completed': 0},
        }

        result = get_expected_map(self.user, self.today)
        self.assertTrue(result['workout'])
        self.assertFalse(result['journal'])
        self.assertTrue(result['faith'])  # prayer_expected=True
        self.assertTrue(result['medication'])  # expected=3 > 0
        self.assertTrue(result['tasks'])  # total=2 > 0
        self.assertFalse(result['biometrics'])
        self.assertFalse(result['nutrition'])

    @patch('apps.core.execution.expected_map.get_execution_truth')
    def test_expected_map_fails_safe(self, mock_ete):
        """On ETE failure, all flags default to False."""
        from apps.core.execution.expected_map import get_expected_map

        mock_ete.side_effect = Exception("ETE down")

        result = get_expected_map(self.user, self.today)
        self.assertFalse(any(result.values()))


class TestSignalSnapshotState(TestCase):
    """Test that signal computers set expected and state correctly."""

    def setUp(self):
        self.user = _create_test_user('state-test@test.com')
        self.today = datetime.date.today()

    def test_zero_fill_not_expected(self):
        """Zero-fill with nothing expected → state=not_expected, expected=False."""
        with patch(
            'apps.core.ai_eae.signal_aggregation.get_expected_map',
            return_value=NOTHING_EXPECTED,
        ):
            results = SignalAggregationService.compute_daily_signals(
                self.user, self.today,
            )

        # All base types should be produced (zero-fill)
        types = {s.signal_type for s in results}
        expected_types = {
            'health_activity', 'health_biometrics', 'medication_adherence',
            'nutrition_compliance', 'faith_practice', 'mental_reflection',
            'cognitive_fitness', 'productivity_progress', 'relational_engagement',
        }
        self.assertTrue(expected_types.issubset(types))

        # Check a few specific snapshots
        workout = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        self.assertEqual(workout.score, 0.0)
        self.assertFalse(workout.expected)
        self.assertEqual(workout.state, 'not_expected')

        journal = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='mental_reflection',
        )
        self.assertFalse(journal.expected)
        self.assertEqual(journal.state, 'not_expected')

    def test_zero_fill_expected_is_missed(self):
        """Zero-fill with expected=True → state=missed."""
        with patch(
            'apps.core.ai_eae.signal_aggregation.get_expected_map',
            return_value=ALL_EXPECTED,
        ):
            results = SignalAggregationService.compute_daily_signals(
                self.user, self.today,
            )

        workout = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        self.assertEqual(workout.score, 0.0)
        self.assertTrue(workout.expected)
        self.assertEqual(workout.state, 'missed')

        journal = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='mental_reflection',
        )
        self.assertTrue(journal.expected)
        self.assertEqual(journal.state, 'missed')

    def test_completed_workout(self):
        """Workout with activity → state=completed or partial."""
        from apps.health.models import WorkoutSession
        from django.utils import timezone

        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            duration_minutes=50,
            completed_at=timezone.now(),
        )

        with patch(
            'apps.core.ai_eae.signal_aggregation.get_expected_map',
            return_value=ALL_EXPECTED,
        ):
            SignalAggregationService.compute_daily_signals(
                self.user, self.today,
            )

        workout = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        self.assertEqual(workout.score, 1.0)
        self.assertTrue(workout.expected)
        self.assertEqual(workout.state, 'completed')

    def test_partial_workout(self):
        """Short workout → state=partial."""
        from apps.health.models import WorkoutSession
        from django.utils import timezone

        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            duration_minutes=15,
            completed_at=timezone.now(),
        )

        with patch(
            'apps.core.ai_eae.signal_aggregation.get_expected_map',
            return_value=ALL_EXPECTED,
        ):
            SignalAggregationService.compute_daily_signals(
                self.user, self.today,
            )

        workout = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        self.assertGreater(workout.score, 0.0)
        self.assertLess(workout.score, 1.0)
        self.assertEqual(workout.state, 'partial')

    def test_completed_journal(self):
        """Journal entry with substantial content → state=completed."""
        from apps.journal.models import JournalEntry

        JournalEntry.objects.create(
            user=self.user,
            entry_date=self.today,
            content="This is a detailed journal entry with plenty of words to exceed "
                    "the hundred word threshold that determines a full score. " * 5,
        )

        with patch(
            'apps.core.ai_eae.signal_aggregation.get_expected_map',
            return_value=ALL_EXPECTED,
        ):
            SignalAggregationService.compute_daily_signals(
                self.user, self.today,
            )

        journal = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='mental_reflection',
        )
        self.assertTrue(journal.expected)
        self.assertEqual(journal.state, 'completed')

    def test_all_domains_produce_daily_snapshot(self):
        """Every base signal type produces a snapshot (no gaps)."""
        with patch(
            'apps.core.ai_eae.signal_aggregation.get_expected_map',
            return_value=NOTHING_EXPECTED,
        ):
            results = SignalAggregationService.compute_daily_signals(
                self.user, self.today,
            )

        expected_types = {
            'health_activity', 'health_biometrics', 'medication_adherence',
            'nutrition_compliance', 'faith_practice', 'mental_reflection',
            'cognitive_fitness', 'productivity_progress', 'relational_engagement',
        }
        produced_types = {s.signal_type for s in results}
        missing = expected_types - produced_types
        self.assertEqual(
            missing, set(),
            f"Missing daily snapshots: {missing}",
        )

    def test_backward_compat_legacy_state(self):
        """Old snapshots with state='' are valid (no crash)."""
        snapshot = SignalSnapshot.objects.create(
            user=self.user,
            date=self.today,
            signal_type='health_activity',
            domain='health',
            signal_class='verified_action',
            score=0.8,
            confidence=1.0,
            expected=True,
            state='',  # Legacy
        )
        self.assertEqual(snapshot.state, '')
        self.assertTrue(snapshot.expected)

    def test_not_expected_workout_with_activity(self):
        """Activity in a not-expected domain → expected=False, state=completed."""
        from apps.health.models import WorkoutSession
        from django.utils import timezone

        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            duration_minutes=50,
            completed_at=timezone.now(),
        )

        with patch(
            'apps.core.ai_eae.signal_aggregation.get_expected_map',
            return_value=NOTHING_EXPECTED,
        ):
            SignalAggregationService.compute_daily_signals(
                self.user, self.today,
            )

        workout = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        self.assertEqual(workout.score, 1.0)
        self.assertFalse(workout.expected)
        self.assertEqual(workout.state, 'completed')


class TestExpectedMapKeys(TestCase):
    """Verify SIGNAL_EXPECTED_KEYS covers all zero-fill types."""

    def test_all_zero_fill_types_have_keys(self):
        """Every zero-fill signal type has a mapping in SIGNAL_EXPECTED_KEYS."""
        from apps.core.execution.expected_map import SIGNAL_EXPECTED_KEYS

        zero_fill_types = [
            'health_activity', 'health_biometrics', 'medication_adherence',
            'nutrition_compliance', 'faith_practice', 'mental_reflection',
            'cognitive_fitness', 'productivity_progress', 'relational_engagement',
        ]
        for sig_type in zero_fill_types:
            self.assertIn(
                sig_type, SIGNAL_EXPECTED_KEYS,
                f"{sig_type} missing from SIGNAL_EXPECTED_KEYS",
            )
