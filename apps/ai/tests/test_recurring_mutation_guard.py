# ==============================================================================
# File: test_recurring_mutation_guard.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests that recurring task mutations are properly scoped —
#              time/date changes ask "this instance or series?" just like
#              commitment_level changes do. Verifies no unintended cascade.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-12
# ==============================================================================

from datetime import date, time, timedelta

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'recurring-mutation-test',
    }
}

from apps.ai.action_handlers import ActionHandler
from apps.life.models import Task
from apps.users.models import User


@override_settings(CACHES=LOCMEM_CACHE)
class TestRecurringTaskMutationGuard(TestCase):
    """Verify recurring task time/date mutations trigger disambiguation."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='recurring@example.com',
            password='testpass123',
            first_name='Test',
        )
        prefs = self.user.preferences
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.timezone = 'America/Chicago'
        prefs.save()
        self.handler = ActionHandler(self.user)
        self.today = timezone.now().date()

        # Create a recurring task with 3 pending instances
        for i in range(3):
            Task.objects.create(
                user=self.user,
                title="Morning Workout",
                due_date=self.today + timedelta(days=i),
                scheduled_time=time(6, 15),
                is_recurring=True,
                recurrence_pattern="daily",
                completion_status='pending',
            )

    def test_time_change_triggers_series_disambiguation(self):
        """Moving scheduled_time on recurring task asks 'this or series?'"""
        result = self.handler.handle_mutate_task(
            action='update',
            task_query='Morning Workout',
            new_scheduled_time='12:00',
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'series_scope_required')
        self.assertIn('recurring task', result.message)
        self.assertIn('Just today', result.message)
        self.assertIn('entire series', result.message)

    def test_due_date_change_triggers_series_disambiguation(self):
        """Changing due_date on recurring task asks 'this or series?'"""
        result = self.handler.handle_mutate_task(
            action='update',
            task_query='Morning Workout',
            new_due_date='2026-04-01',
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'series_scope_required')

    def test_date_specific_phrase_defaults_to_single_instance(self):
        """'today' in due_date signals single-instance — no disambiguation."""
        result = self.handler.handle_mutate_task(
            action='update',
            task_query='Morning Workout',
            new_due_date='today',
            new_scheduled_time='12:00',
        )
        # Should succeed (single instance) or at least not ask series question
        self.assertNotEqual(result.error, 'series_scope_required')

    def test_update_series_false_limits_to_one_instance(self):
        """update_series=False updates only today's instance."""
        result = self.handler.handle_mutate_task(
            action='update',
            task_query='Morning Workout',
            new_scheduled_time='12:00',
            update_series=False,
        )
        self.assertTrue(result.success)
        # Only 1 task should have been updated
        updated = Task.objects.filter(
            user=self.user,
            title='Morning Workout',
            scheduled_time=time(12, 0),
        )
        self.assertEqual(updated.count(), 1)

    def test_update_series_true_updates_all_instances(self):
        """update_series=True updates entire series."""
        result = self.handler.handle_mutate_task(
            action='update',
            task_query='Morning Workout',
            new_scheduled_time='12:00',
            update_series=True,
        )
        self.assertTrue(result.success)
        updated = Task.objects.filter(
            user=self.user,
            title='Morning Workout',
            scheduled_time=time(12, 0),
        )
        self.assertEqual(updated.count(), 3)

    def test_time_change_does_not_affect_completion_status(self):
        """Changing time must NEVER imply completion."""
        task = Task.objects.filter(
            user=self.user, title='Morning Workout', due_date=self.today,
        ).first()
        self.assertEqual(task.completion_status, 'pending')

        self.handler.handle_mutate_task(
            action='update',
            task_query='Morning Workout',
            new_scheduled_time='12:00',
            update_series=False,
        )

        task.refresh_from_db()
        self.assertEqual(task.completion_status, 'pending')
        self.assertIsNone(task.completed_at)

    def test_past_instance_mutation_does_not_cascade(self):
        """Moving a past instance doesn't affect future instances."""
        yesterday = self.today - timedelta(days=1)
        Task.objects.create(
            user=self.user,
            title="Evening Prayer",
            due_date=yesterday,
            scheduled_time=time(21, 0),
            is_recurring=True,
            recurrence_pattern="daily",
        )
        Task.objects.create(
            user=self.user,
            title="Evening Prayer",
            due_date=self.today,
            scheduled_time=time(21, 0),
            is_recurring=True,
            recurrence_pattern="daily",
        )

        result = self.handler.handle_mutate_task(
            action='update',
            task_query='Evening Prayer',
            new_scheduled_time='22:00',
            update_series=False,
        )
        self.assertTrue(result.success)

        # Only 1 instance changed
        changed = Task.objects.filter(
            user=self.user, title='Evening Prayer', scheduled_time=time(22, 0),
        ).count()
        unchanged = Task.objects.filter(
            user=self.user, title='Evening Prayer', scheduled_time=time(21, 0),
        ).count()
        self.assertEqual(changed, 1)
        self.assertEqual(unchanged, 1)

    def test_commitment_level_still_triggers_disambiguation(self):
        """Original commitment_level guard still works."""
        result = self.handler.handle_mutate_task(
            action='update',
            task_query='Morning Workout',
            new_commitment_level='non_negotiable',
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'series_scope_required')

    def test_non_recurring_task_skips_guard(self):
        """Non-recurring tasks are updated directly without disambiguation."""
        Task.objects.create(
            user=self.user,
            title="One-Off Meeting",
            due_date=self.today,
            scheduled_time=time(14, 0),
        )
        result = self.handler.handle_mutate_task(
            action='update',
            task_query='One-Off Meeting',
            new_scheduled_time='15:00',
        )
        self.assertTrue(result.success)
