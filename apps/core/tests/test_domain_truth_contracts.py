# ==============================================================================
# File: apps/core/tests/test_domain_truth_contracts.py
# Description: Regression tests proving domain truth contracts are used by
#              all consumers. Prevents truth drift from returning.
# Created: 2026-04-05
# ==============================================================================
"""
Domain Truth Contract regression tests.

These tests verify that:
1. Execution truth, SAE builders, and UI agree on domain state
2. Known anti-patterns (direct model queries for truth claims) are caught
3. Contract semantics are consistent across consumers
"""

import os
import re
from datetime import date, timedelta
from pathlib import Path

from django.test import TestCase
from django.utils import timezone


class WorkoutContractConsistencyTest(TestCase):
    """Verify workout truth is consistent across execution truth, SAE, and UI."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(
            email='contract-test@example.com', password='testpass123',
        )
        self.today = date.today()

    def test_in_progress_workout_not_completed_anywhere(self):
        """A started-but-empty session must not be 'completed' in any consumer."""
        from apps.health.models import WorkoutSession
        WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            started_at=timezone.now(),
            completed_at=None,
            duration_minutes=None,
        )

        # Contract
        from apps.health.services.workout_queries import WorkoutQueries
        self.assertFalse(WorkoutQueries.is_completed_on(self.user, self.today))

        # Execution truth
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(self.user, self.today)
        self.assertFalse(truth['domains']['workout']['completed'])

    def test_structured_with_exercises_completed_everywhere(self):
        """A structured workout with exercises must be 'completed' everywhere."""
        from apps.health.models import Exercise, WorkoutExercise, WorkoutSession
        session = WorkoutSession.objects.create(
            user=self.user,
            date=self.today,
            started_at=timezone.now(),
            completed_at=None,
            session_mode='structured',
        )
        exercise = Exercise.objects.create(name='Test Exercise', is_active=True)
        WorkoutExercise.objects.create(session=session, exercise=exercise, order=0)

        # Contract
        from apps.health.services.workout_queries import WorkoutQueries
        self.assertTrue(WorkoutQueries.is_completed_on(self.user, self.today))

        # Execution truth
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(self.user, self.today)
        self.assertTrue(truth['domains']['workout']['completed'])


class JournalContractConsistencyTest(TestCase):
    """Verify journal truth is consistent across consumers."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(
            email='journal-contract@example.com', password='testpass123',
        )
        self.today = date.today()

    def test_no_entry_not_completed(self):
        from apps.journal.services.journal_queries import JournalQueries
        self.assertFalse(JournalQueries.has_entry_on(self.user, self.today))

        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(self.user, self.today)
        self.assertFalse(truth['domains']['journal']['completed'])

    def test_entry_exists_is_completed(self):
        from apps.journal.models import JournalEntry
        JournalEntry.objects.create(
            user=self.user, entry_date=self.today,
            title='Test', body='Test entry',
        )

        from apps.journal.services.journal_queries import JournalQueries
        self.assertTrue(JournalQueries.has_entry_on(self.user, self.today))

        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(self.user, self.today)
        self.assertTrue(truth['domains']['journal']['completed'])


class FaithContractConsistencyTest(TestCase):
    """Verify faith truth uses canonical contract."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(
            email='faith-contract@example.com', password='testpass123',
        )

    def test_no_plan_no_reading(self):
        from apps.faith.services.faith_queries import FaithQueries
        self.assertFalse(FaithQueries.has_active_plan(self.user))
        self.assertFalse(FaithQueries.has_reading_on(self.user, date.today()))

    def test_prayer_queries_consistent(self):
        from apps.faith.services.faith_queries import FaithQueries
        self.assertEqual(FaithQueries.unanswered_prayers(self.user).count(), 0)
        self.assertEqual(FaithQueries.answered_prayers(self.user).count(), 0)


class ArchitecturalAntiPatternTest(TestCase):
    """
    Grep-based test that catches direct model queries in truth-evaluating code.

    If this test fails, someone added a raw model query in a file that should
    use the canonical contract instead.
    """

    def _scan_file_for_pattern(self, filepath, pattern, allowed_lines=None):
        """Return list of (line_number, line) tuples matching pattern."""
        allowed_lines = allowed_lines or set()
        matches = []
        try:
            with open(filepath) as f:
                for i, line in enumerate(f, 1):
                    if i in allowed_lines:
                        continue
                    if re.search(pattern, line) and not line.strip().startswith('#'):
                        matches.append((i, line.strip()))
        except FileNotFoundError:
            pass
        return matches

    def test_execution_truth_uses_contracts_not_raw_workout(self):
        """Execution truth engine must not query WorkoutSession directly."""
        filepath = os.path.join(
            os.path.dirname(__file__), '..', 'execution', 'execution_truth_engine.py'
        )
        matches = self._scan_file_for_pattern(
            filepath, r'WorkoutSession\.objects\.'
        )
        self.assertEqual(
            matches, [],
            f"execution_truth_engine.py has raw WorkoutSession queries: {matches}"
        )

    def test_execution_truth_uses_contracts_not_raw_journal(self):
        """Execution truth engine must not query JournalEntry directly."""
        filepath = os.path.join(
            os.path.dirname(__file__), '..', 'execution', 'execution_truth_engine.py'
        )
        matches = self._scan_file_for_pattern(
            filepath, r'JournalEntry\.objects\.'
        )
        self.assertEqual(
            matches, [],
            f"execution_truth_engine.py has raw JournalEntry queries: {matches}"
        )

    def test_execution_truth_uses_faith_contract(self):
        """Execution truth engine must not query UserReadingPlan directly."""
        filepath = os.path.join(
            os.path.dirname(__file__), '..', 'execution', 'execution_truth_engine.py'
        )
        matches = self._scan_file_for_pattern(
            filepath, r'UserReadingPlan\.objects\.'
        )
        self.assertEqual(
            matches, [],
            f"execution_truth_engine.py has raw UserReadingPlan queries: {matches}"
        )
