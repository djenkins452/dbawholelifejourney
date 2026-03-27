# ==============================================================================
# File: test_recurring_delete.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for recurring task series deletion
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-10
# ==============================================================================

from datetime import date, timedelta

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.life.models import Task
from apps.life.services.recurrence import RecurrenceService
from apps.users.models import User


class RecurringDeleteTestBase(TestCase):
    """Base class with shared setup."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='recurring-delete-test@example.com',
            password='testpass123',
        )
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def _create_recurring_series(self, title='Approve Payroll', pattern='biweekly',
                                  count=3):
        """Create a series of recurring task instances."""
        tasks = []
        base_date = date.today()
        for i in range(count):
            task = Task.objects.create(
                user=self.user,
                title=title,
                is_recurring=True,
                recurrence_pattern=pattern,
                start_date=base_date,
                due_date=base_date + timedelta(days=14 * i),
            )
            tasks.append(task)
        return tasks


class TestDeleteTaskSeries(RecurringDeleteTestBase):
    """Test RecurrenceService.delete_task_series()."""

    def test_deletes_all_active_instances(self):
        """Should soft-delete all active instances of the series."""
        tasks = self._create_recurring_series(count=5)
        result = RecurrenceService.delete_task_series(tasks[0])
        self.assertEqual(result, 5)

        # All should be soft-deleted
        for t in tasks:
            t.refresh_from_db()
            self.assertEqual(t.status, 'deleted')

    def test_sets_is_recurring_false_on_all(self):
        """Should set is_recurring=False to prevent regeneration."""
        tasks = self._create_recurring_series(count=3)
        RecurrenceService.delete_task_series(tasks[0])

        for t in tasks:
            t.refresh_from_db()
            self.assertFalse(t.is_recurring)

    def test_does_not_affect_other_users_tasks(self):
        """Should only delete tasks belonging to the same user."""
        other_user = User.objects.create_user(
            email='other-recurring@example.com',
            password='testpass123',
        )
        # Create same-titled task for another user
        other_task = Task.objects.create(
            user=other_user,
            title='Approve Payroll',
            is_recurring=True,
            recurrence_pattern='biweekly',
            due_date=date.today(),
        )

        tasks = self._create_recurring_series(count=2)
        RecurrenceService.delete_task_series(tasks[0])

        other_task.refresh_from_db()
        self.assertEqual(other_task.status, 'active')
        self.assertTrue(other_task.is_recurring)

    def test_does_not_affect_different_pattern(self):
        """Tasks with same title but different pattern are different series."""
        tasks = self._create_recurring_series(
            title='Weekly Review', pattern='weekly', count=2,
        )
        different = Task.objects.create(
            user=self.user,
            title='Weekly Review',
            is_recurring=True,
            recurrence_pattern='monthly',
            due_date=date.today(),
        )

        RecurrenceService.delete_task_series(tasks[0])

        different.refresh_from_db()
        self.assertEqual(different.status, 'active')
        self.assertTrue(different.is_recurring)

    def test_includes_completed_instances_in_is_recurring_reset(self):
        """Completed instances should also have is_recurring set to False."""
        tasks = self._create_recurring_series(count=3)
        # Mark one as completed
        tasks[1].completion_status = 'completed'
        tasks[1].save(update_fields=['completion_status'])

        RecurrenceService.delete_task_series(tasks[0])

        tasks[1].refresh_from_db()
        self.assertFalse(tasks[1].is_recurring)

    def test_returns_zero_for_nonrecurring_task(self):
        """Non-recurring task should return 0 (no series to delete)."""
        task = Task.objects.create(
            user=self.user,
            title='One-off Task',
            is_recurring=False,
            recurrence_pattern='',
            due_date=date.today(),
        )
        result = RecurrenceService.delete_task_series(task)
        self.assertEqual(result, 0)


class TestCountSeriesInstances(RecurringDeleteTestBase):
    """Test RecurrenceService.count_series_instances()."""

    def test_counts_active_instances(self):
        self._create_recurring_series(count=4)
        task = Task.objects.filter(
            user=self.user, title='Approve Payroll',
        ).first()
        count = RecurrenceService.count_series_instances(task)
        self.assertEqual(count, 4)

    def test_excludes_deleted_instances(self):
        tasks = self._create_recurring_series(count=3)
        tasks[0].soft_delete()
        count = RecurrenceService.count_series_instances(tasks[1])
        self.assertEqual(count, 2)


class TestHandleMutateTaskDelete(RecurringDeleteTestBase):
    """Test the action handler's delete logic with recurring tasks."""

    def _get_handler(self):
        from apps.ai.action_handlers import ActionHandler
        return ActionHandler(self.user)

    def test_recurring_task_asks_about_series(self):
        """Deleting a recurring task without delete_series should ask."""
        self._create_recurring_series(count=3)
        handler = self._get_handler()

        result = handler.handle_mutate_task(
            action='delete',
            task_query='Approve Payroll',
        )

        self.assertFalse(result.success)
        self.assertIn('recurring', result.message.lower())
        self.assertIn('series', result.message.lower())

    def test_recurring_task_with_delete_series_asks_confirmation(self):
        """delete_series=True still requires confirmation first."""
        self._create_recurring_series(count=3)
        handler = self._get_handler()

        result = handler.handle_mutate_task(
            action='delete',
            task_query='Approve Payroll',
            delete_series=True,
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error, 'delete_confirmation_required')
        self.assertIn('3 instances', result.message)

    def test_recurring_task_series_delete_confirmed(self):
        """Confirmed series delete should delete all instances."""
        self._create_recurring_series(count=4)
        handler = self._get_handler()

        result = handler.handle_mutate_task(
            action='delete',
            task_query='Approve Payroll',
            delete_series=True,
            delete_confirmed=True,
        )

        self.assertTrue(result.success)
        self.assertIn("won't come back", result.message)

        # Verify all instances are deleted
        active_count = Task.objects.filter(
            user=self.user,
            title='Approve Payroll',
            status='active',
        ).count()
        self.assertEqual(active_count, 0)

    def test_single_instance_delete_still_works(self):
        """delete_series=False should only delete the matched instance."""
        tasks = self._create_recurring_series(count=3)
        handler = self._get_handler()

        result = handler.handle_mutate_task(
            action='delete',
            task_query='Approve Payroll',
            delete_series=False,
            delete_confirmed=True,
        )

        self.assertTrue(result.success)
        # Should still have 2 active instances
        active_count = Task.objects.filter(
            user=self.user,
            title='Approve Payroll',
            status='active',
        ).count()
        self.assertGreaterEqual(active_count, 1)

    def test_non_recurring_task_unaffected(self):
        """Non-recurring tasks should use normal delete flow."""
        Task.objects.create(
            user=self.user,
            title='Buy Groceries',
            is_recurring=False,
            due_date=date.today(),
        )
        handler = self._get_handler()

        # First call: confirmation
        result = handler.handle_mutate_task(
            action='delete',
            task_query='Buy Groceries',
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'delete_confirmation_required')
        self.assertNotIn('recurring', result.message.lower())

        # Confirmed delete
        result = handler.handle_mutate_task(
            action='delete',
            task_query='Buy Groceries',
            delete_confirmed=True,
        )
        self.assertTrue(result.success)
        self.assertIn('Buy Groceries', result.message)

    def test_no_crud_records_created_on_series_delete(self):
        """Series delete should only soft-delete, not create any new records."""
        tasks = self._create_recurring_series(count=3)
        task_count_before = Task.all_objects.filter(user=self.user).count()

        handler = self._get_handler()
        handler.handle_mutate_task(
            action='delete',
            task_query='Approve Payroll',
            delete_series=True,
            delete_confirmed=True,
        )

        # No new tasks should be created
        task_count_after = Task.all_objects.filter(user=self.user).count()
        self.assertEqual(task_count_before, task_count_after)


class TestEnsureRoutineTasksEndDate(RecurringDeleteTestBase):
    """Test that _ensure_routine_tasks_for_today respects end_date."""

    def test_skips_task_past_end_date(self):
        """Task with end_date in the past should not regenerate."""
        yesterday = date.today() - timedelta(days=1)
        Task.objects.create(
            user=self.user,
            title='Expired Routine',
            is_routine=True,
            is_recurring=True,
            recurrence_pattern='daily',
            due_date=yesterday,
            end_date=yesterday,
            scheduled_time='07:00',
        )

        from apps.ai.executive_briefing import _ensure_routine_tasks_for_today
        _ensure_routine_tasks_for_today(self.user, date.today())

        # Should NOT create today's instance
        exists = Task.objects.filter(
            user=self.user,
            title='Expired Routine',
            due_date=date.today(),
        ).exists()
        self.assertFalse(exists)

    def test_creates_task_before_end_date(self):
        """Task with end_date in the future should still regenerate."""
        tomorrow = date.today() + timedelta(days=1)
        Task.objects.create(
            user=self.user,
            title='Active Routine',
            is_routine=True,
            is_recurring=True,
            recurrence_pattern='daily',
            due_date=date.today() - timedelta(days=1),
            end_date=tomorrow,
            scheduled_time='07:00',
        )

        from apps.ai.executive_briefing import _ensure_routine_tasks_for_today
        _ensure_routine_tasks_for_today(self.user, date.today())

        exists = Task.objects.filter(
            user=self.user,
            title='Active Routine',
            due_date=date.today(),
        ).exists()
        self.assertTrue(exists)


class TestRoutineScheduleDeactivation(RecurringDeleteTestBase):
    """Test that AI delete handler deactivates RoutineSchedule items."""

    def _get_handler(self):
        from apps.ai.action_handlers import ActionHandler
        return ActionHandler(self.user)

    def _create_routine_with_schedule(self, item_name='Workout'):
        """Create a Routine + RoutineSchedule for testing."""
        from apps.life.models import Routine, RoutineSchedule
        routine = Routine.objects.create(
            user=self.user,
            name='Morning Routine',
            time_of_day='morning',
            is_active=True,
        )
        schedule = RoutineSchedule.objects.create(
            routine=routine,
            name=item_name,
            scheduled_time='06:00',
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )
        return routine, schedule

    def test_fallback_finds_routine_schedule(self):
        """When no Task matches, handler should find RoutineSchedule."""
        _routine, _schedule = self._create_routine_with_schedule('Workout')
        handler = self._get_handler()

        result = handler.handle_mutate_task(
            action='delete',
            task_query='Workout',
        )

        # Should ask for confirmation (found as routine item)
        self.assertFalse(result.success)
        self.assertIn('routine item', result.message.lower())

    def test_confirmed_deactivation(self):
        """Confirmed delete should set is_active=False on schedule."""
        from apps.life.models import RoutineSchedule
        _routine, schedule = self._create_routine_with_schedule('Workout')
        handler = self._get_handler()

        result = handler.handle_mutate_task(
            action='delete',
            task_query='Workout',
            delete_confirmed=True,
        )

        self.assertTrue(result.success)
        self.assertIn("won't come back", result.message.lower())

        schedule.refresh_from_db()
        self.assertFalse(schedule.is_active)

    def test_deactivation_also_kills_shadow_tasks(self):
        """Deactivating schedule should also stop shadow Task regeneration."""
        _routine, _schedule = self._create_routine_with_schedule('Work on WLJ')
        # Create shadow Task (as _ensure_routine_tasks_for_today would)
        Task.objects.create(
            user=self.user,
            title='Work on WLJ',
            is_routine=True,
            is_recurring=True,
            recurrence_pattern='daily',
            due_date=date.today(),
        )

        handler = self._get_handler()
        handler.handle_mutate_task(
            action='delete',
            task_query='Work on WLJ',
            delete_confirmed=True,
        )

        # Shadow task should have is_recurring=False
        shadow = Task.all_objects.filter(
            user=self.user,
            title__iexact='Work on WLJ',
            is_routine=True,
        ).first()
        self.assertIsNotNone(shadow)
        self.assertFalse(shadow.is_recurring)

    def test_series_delete_also_deactivates_schedule(self):
        """delete_task_series should also deactivate matching schedule."""
        from apps.life.models import RoutineSchedule
        _routine, schedule = self._create_routine_with_schedule('Approve Payroll')
        self._create_recurring_series(count=2)

        handler = self._get_handler()
        handler.handle_mutate_task(
            action='delete',
            task_query='Approve Payroll',
            delete_series=True,
            delete_confirmed=True,
        )

        schedule.refresh_from_db()
        self.assertFalse(schedule.is_active)

    def test_other_routine_items_unaffected(self):
        """Deactivating one item should not affect others in the routine."""
        from apps.life.models import RoutineSchedule
        routine, _workout = self._create_routine_with_schedule('Workout')
        prayer = RoutineSchedule.objects.create(
            routine=routine,
            name='Prayer Time',
            scheduled_time='06:30',
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )

        handler = self._get_handler()
        handler.handle_mutate_task(
            action='delete',
            task_query='Workout',
            delete_confirmed=True,
        )

        prayer.refresh_from_db()
        self.assertTrue(prayer.is_active)
