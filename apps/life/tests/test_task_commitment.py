"""
Tests for Task Commitment Level System.

Tests commitment_level field, skip_streak tracking, recency guard,
recurrence propagation, and escalation behavior.
"""

from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.life.models import Task
from apps.users.models import User


class TaskCommitmentLevelTest(TestCase):
    """Tests for commitment_level field defaults and choices."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='commitment@test.com',
            password='testpass123'
        )

    def test_default_commitment_level_is_important(self):
        """New tasks default to 'important' commitment level."""
        task = Task.objects.create(user=self.user, title='Default task')
        self.assertEqual(task.commitment_level, 'important')

    def test_commitment_level_optional(self):
        """Tasks can be created with 'flexible' commitment level."""
        task = Task.objects.create(
            user=self.user, title='Flexible task',
            commitment_level='flexible'
        )
        self.assertEqual(task.commitment_level, 'flexible')

    def test_commitment_level_foundational(self):
        """Tasks can be created with 'foundational' commitment level."""
        task = Task.objects.create(
            user=self.user, title='NN task',
            commitment_level='foundational'
        )
        self.assertEqual(task.commitment_level, 'foundational')

    def test_default_skip_streak_is_zero(self):
        """New tasks have skip_streak of 0."""
        task = Task.objects.create(user=self.user, title='New task')
        self.assertEqual(task.skip_streak, 0)

    def test_default_last_skipped_at_is_none(self):
        """New tasks have no last_skipped_at timestamp."""
        task = Task.objects.create(user=self.user, title='New task')
        self.assertIsNone(task.last_skipped_at)


class SkipStreakTest(TestCase):
    """Tests for skip streak increment/reset behavior."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='streak@test.com',
            password='testpass123'
        )

    def test_skip_increments_streak(self):
        """mark_skipped() increments skip_streak by 1."""
        task = Task.objects.create(
            user=self.user, title='Skip me',
            commitment_level='foundational'
        )
        task.mark_skipped()
        task.refresh_from_db()
        self.assertEqual(task.skip_streak, 1)

    def test_skip_sets_last_skipped_at(self):
        """mark_skipped() sets last_skipped_at timestamp."""
        task = Task.objects.create(
            user=self.user, title='Skip me',
            commitment_level='foundational'
        )
        task.mark_skipped()
        task.refresh_from_db()
        self.assertIsNotNone(task.last_skipped_at)

    def test_multiple_skips_accumulate(self):
        """Multiple skips increment streak each time."""
        task = Task.objects.create(
            user=self.user, title='Skip me lots',
            commitment_level='foundational'
        )
        # Simulate multiple skips on the same task (not recurring)
        task.mark_skipped()
        task.completion_status = 'pending'  # Reset to pending for next skip
        task.save(update_fields=['completion_status'])
        task.mark_skipped()
        task.refresh_from_db()
        self.assertEqual(task.skip_streak, 2)

    def test_complete_resets_streak(self):
        """mark_complete() resets skip_streak to 0."""
        task = Task.objects.create(
            user=self.user, title='Complete me',
            skip_streak=3
        )
        task.mark_complete()
        task.refresh_from_db()
        self.assertEqual(task.skip_streak, 0)

    def test_incomplete_resets_streak(self):
        """mark_incomplete() resets skip_streak to 0."""
        task = Task.objects.create(
            user=self.user, title='Incomplete me',
            skip_streak=2
        )
        task.mark_incomplete()
        task.refresh_from_db()
        self.assertEqual(task.skip_streak, 0)


class RecencyGuardTest(TestCase):
    """Tests for effective_skip_streak recency guard."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='recency@test.com',
            password='testpass123'
        )

    def test_effective_streak_zero_when_no_last_skipped(self):
        """effective_skip_streak is 0 when last_skipped_at is None."""
        task = Task.objects.create(
            user=self.user, title='Never skipped',
            skip_streak=3, last_skipped_at=None
        )
        self.assertEqual(task.effective_skip_streak, 0)

    def test_effective_streak_zero_when_streak_is_zero(self):
        """effective_skip_streak is 0 when skip_streak is 0."""
        task = Task.objects.create(
            user=self.user, title='Zero streak',
            skip_streak=0, last_skipped_at=timezone.now()
        )
        self.assertEqual(task.effective_skip_streak, 0)

    def test_effective_streak_returns_streak_when_recent(self):
        """effective_skip_streak returns skip_streak when last skip was recent."""
        task = Task.objects.create(
            user=self.user, title='Recent skip',
            skip_streak=3,
            last_skipped_at=timezone.now() - timedelta(days=2)
        )
        self.assertEqual(task.effective_skip_streak, 3)

    def test_effective_streak_zero_when_stale(self):
        """effective_skip_streak returns 0 when last skip > 7 days ago."""
        task = Task.objects.create(
            user=self.user, title='Stale skip',
            skip_streak=5,
            last_skipped_at=timezone.now() - timedelta(days=8)
        )
        self.assertEqual(task.effective_skip_streak, 0)

    def test_effective_streak_boundary_within_7_days(self):
        """effective_skip_streak returns streak when just under 7 days."""
        task = Task.objects.create(
            user=self.user, title='Boundary skip',
            skip_streak=2,
            last_skipped_at=timezone.now() - timedelta(days=6, hours=23)
        )
        self.assertEqual(task.effective_skip_streak, 2)

    def test_raw_streak_preserved_when_stale(self):
        """Raw skip_streak is preserved in DB even when effective returns 0."""
        task = Task.objects.create(
            user=self.user, title='Audit trail',
            skip_streak=5,
            last_skipped_at=timezone.now() - timedelta(days=10)
        )
        self.assertEqual(task.effective_skip_streak, 0)
        self.assertEqual(task.skip_streak, 5)  # Raw value preserved


class RecurrenceCommitmentPropagationTest(TestCase):
    """Tests for commitment field propagation in recurring tasks."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='recurrence@test.com',
            password='testpass123'
        )

    def test_commitment_level_propagates_to_next_occurrence(self):
        """commitment_level is copied to next recurring task occurrence."""
        task = Task.objects.create(
            user=self.user, title='Daily workout',
            commitment_level='foundational',
            is_recurring=True,
            recurrence_pattern='daily',
            due_date=timezone.now().date()
        )
        task.mark_complete()

        # Find the new task
        next_task = Task.objects.filter(
            user=self.user, title='Daily workout',
            completion_status='pending'
        ).first()
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task.commitment_level, 'foundational')

    def test_skip_streak_propagates_on_skip(self):
        """skip_streak carries to next occurrence after skip."""
        task = Task.objects.create(
            user=self.user, title='Daily workout skip',
            commitment_level='foundational',
            is_recurring=True,
            recurrence_pattern='daily',
            due_date=timezone.now().date()
        )
        task.mark_skipped()  # streak becomes 1

        next_task = Task.objects.filter(
            user=self.user, title='Daily workout skip',
            completion_status='pending'
        ).first()
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task.skip_streak, 1)

    def test_skip_streak_zero_on_complete(self):
        """skip_streak resets to 0 on next occurrence after completion."""
        task = Task.objects.create(
            user=self.user, title='Daily workout complete',
            commitment_level='foundational',
            skip_streak=3,
            is_recurring=True,
            recurrence_pattern='daily',
            due_date=timezone.now().date()
        )
        task.mark_complete()  # streak resets to 0

        next_task = Task.objects.filter(
            user=self.user, title='Daily workout complete',
            completion_status='pending'
        ).first()
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task.skip_streak, 0)

    def test_optional_level_propagates(self):
        """Flexible commitment level also propagates correctly."""
        task = Task.objects.create(
            user=self.user, title='Flexible recurring',
            commitment_level='flexible',
            is_recurring=True,
            recurrence_pattern='daily',
            due_date=timezone.now().date()
        )
        task.mark_complete()

        next_task = Task.objects.filter(
            user=self.user, title='Flexible recurring',
            completion_status='pending'
        ).first()
        self.assertIsNotNone(next_task)
        self.assertEqual(next_task.commitment_level, 'flexible')


class SkipEscalationTest(TestCase):
    """Tests for skip escalation messaging in action handlers."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='escalation@test.com',
            password='testpass123'
        )
        # Ensure user has preferences
        from apps.users.models import UserPreferences
        UserPreferences.objects.get_or_create(user=self.user)

    def test_no_escalation_for_optional_task(self):
        """Flexible tasks do not trigger escalation on skip."""
        from apps.ai.action_handlers import ActionHandler
        task = Task.objects.create(
            user=self.user, title='Flexible task',
            commitment_level='flexible',
        )
        handler = ActionHandler(self.user)
        result = handler.handle_skip_task(task_keyword='Flexible task')
        self.assertTrue(result.success)
        # No escalation note in message
        self.assertNotIn('non-negotiable', result.message.lower())

    def test_no_escalation_for_important_task(self):
        """Important tasks do not trigger escalation on skip."""
        from apps.ai.action_handlers import ActionHandler
        task = Task.objects.create(
            user=self.user, title='Important task',
            commitment_level='important',
        )
        handler = ActionHandler(self.user)
        result = handler.handle_skip_task(task_keyword='Important task')
        self.assertTrue(result.success)
        self.assertNotIn('non-negotiable', result.message.lower())

    def test_escalation_day1_gentle(self):
        """First skip of NN task produces gentle escalation."""
        from apps.ai.action_handlers import ActionHandler
        task = Task.objects.create(
            user=self.user, title='Workout',
            commitment_level='foundational',
        )
        handler = ActionHandler(self.user)
        result = handler.handle_skip_task(task_keyword='Workout')
        self.assertTrue(result.success)
        # Should contain some form of escalation
        self.assertIn('Workout', result.message)

    def test_escalation_day2_pattern(self):
        """Second consecutive skip triggers pattern awareness."""
        from apps.ai.action_handlers import ActionHandler
        task = Task.objects.create(
            user=self.user, title='Prayer time',
            commitment_level='foundational',
            skip_streak=1,
            last_skipped_at=timezone.now() - timedelta(hours=12),
        )
        handler = ActionHandler(self.user)
        result = handler.handle_skip_task(task_keyword='Prayer time')
        self.assertTrue(result.success)
        # streak is now 2 — should have escalation note
        self.assertIn('Prayer time', result.message)

    def test_escalation_capped_at_day4(self):
        """Escalation does not intensify beyond Day 3 (streak >= 4)."""
        from apps.ai.action_handlers import ActionHandler
        task = Task.objects.create(
            user=self.user, title='Exercise',
            commitment_level='foundational',
            skip_streak=4,
            last_skipped_at=timezone.now() - timedelta(hours=6),
        )
        handler = ActionHandler(self.user)
        result = handler.handle_skip_task(task_keyword='Exercise')
        self.assertTrue(result.success)
        # Should have supportive message, not escalating
        self.assertIn('Exercise', result.message)

    def test_create_task_with_commitment_level(self):
        """create_task handler accepts and stores commitment_level."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)
        result = handler.handle_create_task(
            title='Morning run',
            commitment_level='foundational'
        )
        self.assertTrue(result.success)
        task = Task.objects.get(user=self.user, title='Morning run')
        self.assertEqual(task.commitment_level, 'foundational')

    def test_create_task_default_commitment_level(self):
        """create_task defaults to 'important' commitment_level."""
        from apps.ai.action_handlers import ActionHandler
        handler = ActionHandler(self.user)
        result = handler.handle_create_task(title='Check email')
        self.assertTrue(result.success)
        task = Task.objects.get(user=self.user, title='Check email')
        self.assertEqual(task.commitment_level, 'important')


class GoalCommitmentLevelTest(TestCase):
    """Tests for LifeGoal commitment_level."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='goal@test.com',
            password='testpass123'
        )

    def test_goal_default_commitment_level(self):
        """LifeGoal defaults to 'important' commitment level."""
        from apps.purpose.models import LifeGoal
        goal = LifeGoal.objects.create(
            user=self.user,
            title='Test Goal'
        )
        self.assertEqual(goal.commitment_level, 'important')

    def test_goal_foundational(self):
        """LifeGoal can be set to 'foundational'."""
        from apps.purpose.models import LifeGoal
        goal = LifeGoal.objects.create(
            user=self.user,
            title='Essential Goal',
            commitment_level='foundational'
        )
        self.assertEqual(goal.commitment_level, 'foundational')
