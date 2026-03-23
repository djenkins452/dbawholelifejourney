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

    @patch('apps.core.execution.execution_truth_engine.get_execution_truth')
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

    @patch('apps.core.execution.execution_truth_engine.get_execution_truth')
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
            'apps.core.execution.expected_map.get_expected_map',
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
            'apps.core.execution.expected_map.get_expected_map',
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
            'apps.core.execution.expected_map.get_expected_map',
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
            'apps.core.execution.expected_map.get_expected_map',
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

    def test_journal_entry_produces_signal(self):
        """Journal entry creates a mental_reflection signal with state set."""
        from apps.journal.models import JournalEntry

        JournalEntry.objects.create(
            user=self.user,
            entry_date=self.today,
            title='Test Entry',
            body="Reflecting on my day today.",
        )

        with patch(
            'apps.core.execution.expected_map.get_expected_map',
            return_value=ALL_EXPECTED,
        ):
            SignalAggregationService.compute_daily_signals(
                self.user, self.today,
            )

        journal = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='mental_reflection',
        )
        self.assertTrue(journal.expected)
        self.assertIn(journal.state, ('completed', 'partial'))
        self.assertGreater(journal.score, 0.0)

    def test_all_domains_produce_daily_snapshot(self):
        """Every base signal type produces a snapshot (no gaps)."""
        with patch(
            'apps.core.execution.expected_map.get_expected_map',
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
            'apps.core.execution.expected_map.get_expected_map',
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


# =========================================================================
# Phase 2.1 Tests: Skipped + Confidence
# =========================================================================


class TestConfidenceRules(TestCase):
    """Test centralized confidence scoring."""

    def test_confidence_values_are_deterministic(self):
        """confidence_for_state returns known values for all states."""
        from apps.core.ai_eae.signal_confidence import (
            confidence_for_state,
            CONFIDENCE_EXPLICIT,
            CONFIDENCE_DERIVED,
            CONFIDENCE_ABSENCE,
            CONFIDENCE_NOT_EXPECTED,
        )
        self.assertEqual(confidence_for_state('completed'), CONFIDENCE_EXPLICIT)
        self.assertEqual(confidence_for_state('completed', has_explicit_evidence=False), CONFIDENCE_DERIVED)
        self.assertEqual(confidence_for_state('partial'), CONFIDENCE_DERIVED)
        self.assertEqual(confidence_for_state('missed'), CONFIDENCE_ABSENCE)
        self.assertEqual(confidence_for_state('skipped'), CONFIDENCE_EXPLICIT)
        self.assertEqual(confidence_for_state('not_expected'), CONFIDENCE_NOT_EXPECTED)

    def test_confidence_ordering(self):
        """Explicit > derived > absence."""
        from apps.core.ai_eae.signal_confidence import (
            CONFIDENCE_EXPLICIT,
            CONFIDENCE_DERIVED,
            CONFIDENCE_ABSENCE,
        )
        self.assertGreater(CONFIDENCE_EXPLICIT, CONFIDENCE_DERIVED)
        self.assertGreater(CONFIDENCE_DERIVED, CONFIDENCE_ABSENCE)


class TestSkippedState(TestCase):
    """Test explicit skip evidence wiring."""

    def setUp(self):
        self.user = _create_test_user('skip-test@test.com')
        self.today = datetime.date.today()

    def test_skipped_medication_all_doses(self):
        """All medication doses explicitly skipped → state=skipped."""
        from apps.health.models import Medicine, MedicineSchedule, MedicineLog

        med = Medicine.objects.create(
            user=self.user, name='TestMed', medicine_status='active',
            start_date=self.today,
        )
        sched = MedicineSchedule.objects.create(
            medicine=med,
            scheduled_time=datetime.time(8, 0),
            is_active=True,
            days_of_week=str(self.today.weekday()),
        )

        # Create skipped log
        MedicineLog.objects.create(
            user=self.user,
            medicine=med,
            schedule=sched,
            scheduled_date=self.today,
            log_status='skipped',
        )

        expected = ALL_EXPECTED.copy()
        expected['medication'] = True

        with patch(
            'apps.core.execution.expected_map.get_expected_map',
            return_value=expected,
        ):
            SignalAggregationService.compute_daily_signals(self.user, self.today)

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='medication_adherence',
        )
        self.assertEqual(snap.state, 'skipped')
        self.assertEqual(snap.score, 0.0)
        self.assertTrue(snap.expected)

    def test_skipped_task_all_due(self):
        """All due tasks explicitly skipped → state=skipped."""
        from apps.life.models import Task
        from django.utils import timezone

        Task.objects.create(
            user=self.user,
            title='Skipped Task',
            due_date=self.today,
            completion_status='skipped',
            last_skipped_at=timezone.now(),
        )

        expected = ALL_EXPECTED.copy()
        expected['tasks'] = True

        with patch(
            'apps.core.execution.expected_map.get_expected_map',
            return_value=expected,
        ):
            SignalAggregationService.compute_daily_signals(self.user, self.today)

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='productivity_progress',
        )
        self.assertEqual(snap.state, 'skipped')
        self.assertEqual(snap.score, 0.0)

    def test_no_skip_evidence_produces_missed_not_skipped(self):
        """Expected + no activity + no skip log → missed, not skipped."""
        with patch(
            'apps.core.execution.expected_map.get_expected_map',
            return_value=ALL_EXPECTED,
        ):
            SignalAggregationService.compute_daily_signals(self.user, self.today)

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        self.assertEqual(snap.state, 'missed')
        self.assertNotEqual(snap.state, 'skipped')


class TestConfidenceInSnapshots(TestCase):
    """Verify confidence values flow through to actual snapshots."""

    def setUp(self):
        self.user = _create_test_user('conf-test@test.com')
        self.today = datetime.date.today()

    def test_zero_fill_missed_has_lower_confidence(self):
        """Zero-fill missed snapshots use CONFIDENCE_ABSENCE (0.6)."""
        from apps.core.ai_eae.signal_confidence import CONFIDENCE_ABSENCE

        with patch(
            'apps.core.execution.expected_map.get_expected_map',
            return_value=ALL_EXPECTED,
        ):
            SignalAggregationService.compute_daily_signals(self.user, self.today)

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        self.assertEqual(snap.state, 'missed')
        self.assertEqual(snap.confidence, CONFIDENCE_ABSENCE)

    def test_zero_fill_not_expected_has_high_confidence(self):
        """Not-expected snapshots use CONFIDENCE_NOT_EXPECTED (0.9)."""
        from apps.core.ai_eae.signal_confidence import CONFIDENCE_NOT_EXPECTED

        with patch(
            'apps.core.execution.expected_map.get_expected_map',
            return_value=NOTHING_EXPECTED,
        ):
            SignalAggregationService.compute_daily_signals(self.user, self.today)

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        self.assertEqual(snap.state, 'not_expected')
        self.assertEqual(snap.confidence, CONFIDENCE_NOT_EXPECTED)

    def test_completed_workout_has_explicit_confidence(self):
        """Completed workout with full duration → CONFIDENCE_EXPLICIT (1.0)."""
        from apps.health.models import WorkoutSession
        from django.utils import timezone
        from apps.core.ai_eae.signal_confidence import CONFIDENCE_EXPLICIT

        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            duration_minutes=50,
            completed_at=timezone.now(),
        )

        with patch(
            'apps.core.execution.expected_map.get_expected_map',
            return_value=ALL_EXPECTED,
        ):
            SignalAggregationService.compute_daily_signals(self.user, self.today)

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        self.assertEqual(snap.state, 'completed')
        self.assertEqual(snap.confidence, CONFIDENCE_EXPLICIT)

    def test_partial_workout_has_derived_confidence(self):
        """Short workout → partial state, CONFIDENCE_DERIVED (0.8)."""
        from apps.health.models import WorkoutSession
        from django.utils import timezone
        from apps.core.ai_eae.signal_confidence import CONFIDENCE_DERIVED

        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            duration_minutes=15,
            completed_at=timezone.now(),
        )

        with patch(
            'apps.core.execution.expected_map.get_expected_map',
            return_value=ALL_EXPECTED,
        ):
            SignalAggregationService.compute_daily_signals(self.user, self.today)

        snap = SignalSnapshot.objects.get(
            user=self.user, date=self.today, signal_type='health_activity',
        )
        self.assertEqual(snap.state, 'partial')
        self.assertEqual(snap.confidence, CONFIDENCE_DERIVED)

    def test_all_domains_still_produce_daily_snapshot(self):
        """Daily coverage guarantee still holds with confidence changes."""
        with patch(
            'apps.core.execution.expected_map.get_expected_map',
            return_value=ALL_EXPECTED,
        ):
            results = SignalAggregationService.compute_daily_signals(
                self.user, self.today,
            )

        expected_types = {
            'health_activity', 'health_biometrics', 'medication_adherence',
            'nutrition_compliance', 'faith_practice', 'mental_reflection',
            'cognitive_fitness', 'productivity_progress', 'relational_engagement',
        }
        produced = {s.signal_type for s in results}
        self.assertTrue(expected_types.issubset(produced))
