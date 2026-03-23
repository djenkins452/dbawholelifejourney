"""
Tests for Routine views — first-class routine domain.

Tests cover: list, create, update, delete, toggle, skip, and migration.
"""

from datetime import time, date

from django.conf import settings
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from apps.life.models import Routine, RoutineLog, RoutineSchedule, Task
from apps.users.models import User, TermsAcceptance


class RoutineTestMixin:
    """Shared setup for routine tests."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='routine@test.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client.login(email='routine@test.com', password='testpass123')

    def _create_routine(self, name='Morning Routine', time_of_day='morning'):
        return Routine.objects.create(
            user=self.user, name=name, time_of_day=time_of_day, is_active=True,
        )

    def _create_schedule(self, routine, name='Prayer', hour=6, minute=30):
        return RoutineSchedule.objects.create(
            routine=routine, name=name,
            scheduled_time=time(hour, minute),
            grace_period_minutes=30,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )


class RoutineListViewTests(RoutineTestMixin, TestCase):

    def test_requires_auth(self):
        self.client.logout()
        response = self.client.get(reverse('life:routine_list'))
        self.assertEqual(response.status_code, 302)

    def test_renders_empty(self):
        response = self.client.get(reverse('life:routine_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No routines yet')

    def test_renders_with_routines(self):
        routine = self._create_routine()
        self._create_schedule(routine)
        response = self.client.get(reverse('life:routine_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Morning Routine')
        self.assertContains(response, 'Prayer')

    def test_groups_by_window(self):
        morning = self._create_routine('AM', 'morning')
        evening = self._create_routine('PM', 'evening')
        self._create_schedule(morning, 'Wake up', 6, 0)
        self._create_schedule(evening, 'Journal', 20, 0)
        response = self.client.get(reverse('life:routine_list'))
        self.assertEqual(response.status_code, 200)
        context = response.context
        windows = context['windows']
        morning_window = next(w for w in windows if w['key'] == 'morning')
        evening_window = next(w for w in windows if w['key'] == 'evening')
        self.assertEqual(len(morning_window['items']), 1)
        self.assertEqual(len(evening_window['items']), 1)

    def test_shows_today_logs(self):
        routine = self._create_routine()
        schedule = self._create_schedule(routine)
        from apps.core.utils import get_user_today
        today = get_user_today(self.user)
        RoutineLog.objects.create(
            user=self.user, schedule=schedule,
            scheduled_date=today, log_status='completed',
            completed_at=timezone.now(),
        )
        response = self.client.get(reverse('life:routine_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1/1')  # completed count in summary


class RoutineCreateViewTests(RoutineTestMixin, TestCase):

    def test_get_form(self):
        response = self.client.get(reverse('life:routine_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'New Routine')

    def test_create_routine_with_items(self):
        data = {
            'name': 'Test Routine',
            'description': 'A test',
            'time_of_day': 'morning',
            'is_active': 'on',
            'sort_order': '0',
            # Formset management
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '0',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            # First item
            'items-0-name': 'Exercise',
            'items-0-importance': 'flexible',
            'items-0-scheduled_time': '07:00',
            'items-0-grace_period_minutes': '30',
            'items-0-active_days': ['0', '1', '2', '3', '4'],
            'items-0-sort_order': '0',
            'items-0-routine_type': 'binary',
        }
        response = self.client.post(reverse('life:routine_create'), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Routine.objects.filter(name='Test Routine').exists())
        routine = Routine.objects.get(name='Test Routine')
        self.assertEqual(routine.items.count(), 1)
        item = routine.items.first()
        self.assertEqual(item.name, 'Exercise')
        self.assertEqual(item.days_of_week, '0,1,2,3,4')


class RoutineUpdateViewTests(RoutineTestMixin, TestCase):

    def test_update_routine(self):
        routine = self._create_routine()
        schedule = self._create_schedule(routine)
        data = {
            'name': 'Updated Routine',
            'description': '',
            'time_of_day': 'evening',
            'is_active': 'on',
            'sort_order': '0',
            'items-TOTAL_FORMS': '1',
            'items-INITIAL_FORMS': '1',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            'items-0-id': str(schedule.pk),
            'items-0-name': 'Updated Item',
            'items-0-importance': 'important',
            'items-0-scheduled_time': '20:00',
            'items-0-grace_period_minutes': '15',
            'items-0-active_days': ['0', '1', '2', '3', '4', '5', '6'],
            'items-0-sort_order': '0',
            'items-0-routine_type': 'binary',
        }
        response = self.client.post(
            reverse('life:routine_update', args=[routine.pk]), data
        )
        self.assertEqual(response.status_code, 302)
        routine.refresh_from_db()
        self.assertEqual(routine.name, 'Updated Routine')
        self.assertEqual(routine.time_of_day, 'evening')


class RoutineDeleteViewTests(RoutineTestMixin, TestCase):

    def test_soft_delete(self):
        routine = self._create_routine()
        response = self.client.post(
            reverse('life:routine_delete', args=[routine.pk])
        )
        self.assertEqual(response.status_code, 302)
        routine.refresh_from_db()
        self.assertEqual(routine.status, 'deleted')

    def test_cannot_delete_other_users_routine(self):
        other_user = User.objects.create_user(
            email='other@test.com', password='testpass123'
        )
        routine = Routine.objects.create(
            user=other_user, name='Other', time_of_day='morning',
        )
        response = self.client.post(
            reverse('life:routine_delete', args=[routine.pk])
        )
        self.assertEqual(response.status_code, 404)


class RoutineToggleViewTests(RoutineTestMixin, TestCase):

    def test_create_completed_log(self):
        routine = self._create_routine()
        schedule = self._create_schedule(routine)
        response = self.client.post(
            reverse('life:routine_toggle'),
            {'schedule_id': schedule.pk},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_completed'])
        self.assertTrue(RoutineLog.objects.filter(
            schedule=schedule, log_status__in=('completed', 'completed_late'),
        ).exists())

    def test_un_complete_log(self):
        routine = self._create_routine()
        schedule = self._create_schedule(routine)
        from apps.core.utils import get_user_today
        today = get_user_today(self.user)
        RoutineLog.objects.create(
            user=self.user, schedule=schedule,
            scheduled_date=today, log_status='completed',
            completed_at=timezone.now(),
        )
        response = self.client.post(
            reverse('life:routine_toggle'),
            {'schedule_id': schedule.pk},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        data = response.json()
        self.assertTrue(data['success'])
        self.assertFalse(data['is_completed'])
        self.assertFalse(RoutineLog.objects.filter(
            schedule=schedule, scheduled_date=today,
        ).exists())

    def test_convert_skipped_to_completed(self):
        routine = self._create_routine()
        schedule = self._create_schedule(routine)
        from apps.core.utils import get_user_today
        today = get_user_today(self.user)
        RoutineLog.objects.create(
            user=self.user, schedule=schedule,
            scheduled_date=today, log_status='skipped',
        )
        response = self.client.post(
            reverse('life:routine_toggle'),
            {'schedule_id': schedule.pk},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_completed'])
        log = RoutineLog.objects.get(schedule=schedule, scheduled_date=today)
        # Status depends on whether current time is within grace window.
        # The log should be completed (or completed_late if past grace).
        self.assertIn(log.log_status, ('completed', 'completed_late'))
        # performed_at and timing should be set
        self.assertIsNotNone(log.performed_at)
        self.assertIn(log.timing, ('on_time', 'late', 'early'))


class RoutineSkipViewTests(RoutineTestMixin, TestCase):

    def test_skip_creates_log(self):
        routine = self._create_routine()
        schedule = self._create_schedule(routine)
        response = self.client.post(
            reverse('life:routine_skip'),
            {'schedule_id': schedule.pk},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'skipped')


class RoutineMigrationViewTests(RoutineTestMixin, TestCase):

    def test_get_shows_routine_tasks(self):
        Task.objects.create(
            user=self.user, title='Legacy Routine',
            is_routine=True, scheduled_time=time(7, 0),
        )
        response = self.client.get(reverse('life:routine_migration'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Legacy Routine')

    def test_migrate_creates_routine(self):
        task = Task.objects.create(
            user=self.user, title='Migrate Me',
            is_routine=True, scheduled_time=time(7, 0),
        )
        response = self.client.post(
            reverse('life:routine_migration'),
            {'task_ids': [str(task.pk)]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Routine.objects.filter(name='Migrate Me').exists())
        task.refresh_from_db()
        self.assertEqual(task.completion_status, 'completed')
        self.assertFalse(task.is_routine)

    def test_idempotent_migration(self):
        """Migrating same task twice should not create duplicate routines."""
        task = Task.objects.create(
            user=self.user, title='Already Migrated',
            is_routine=True, scheduled_time=time(7, 0),
        )
        # First migration
        self.client.post(
            reverse('life:routine_migration'),
            {'task_ids': [str(task.pk)]},
        )
        # Create another task with same name
        task2 = Task.objects.create(
            user=self.user, title='Already Migrated',
            is_routine=True, scheduled_time=time(8, 0),
        )
        # Second migration should skip
        self.client.post(
            reverse('life:routine_migration'),
            {'task_ids': [str(task2.pk)]},
        )
        self.assertEqual(
            Routine.objects.filter(name='Already Migrated').count(), 1
        )


class RoutineCompletionServiceTests(RoutineTestMixin, TestCase):
    """Tests for routine-level completion (bidirectional sync)."""

    def test_get_completion_state_empty(self):
        """Routine with no items returns zero state."""
        from apps.life.services.routine_helpers import get_routine_completion_state
        from apps.core.utils import get_user_today
        routine = self._create_routine()
        # No items added
        today = get_user_today(self.user)
        state = get_routine_completion_state(self.user, routine, today)
        self.assertEqual(state['total_count'], 0)
        self.assertFalse(state['all_complete'])

    def test_get_completion_state_partial(self):
        """Routine with some items completed."""
        from apps.life.services.routine_helpers import get_routine_completion_state
        from apps.core.utils import get_user_today
        routine = self._create_routine()
        s1 = self._create_schedule(routine, 'Prayer', 6, 0)
        s2 = self._create_schedule(routine, 'Bible', 6, 30)
        today = get_user_today(self.user)
        RoutineLog.objects.create(
            user=self.user, schedule=s1, scheduled_date=today, log_status='completed',
        )
        state = get_routine_completion_state(self.user, routine, today)
        self.assertEqual(state['completed_count'], 1)
        self.assertEqual(state['total_count'], 2)
        self.assertFalse(state['all_complete'])

    def test_get_completion_state_all_complete(self):
        """Routine fully complete."""
        from apps.life.services.routine_helpers import get_routine_completion_state
        from apps.core.utils import get_user_today
        routine = self._create_routine()
        s1 = self._create_schedule(routine, 'Prayer', 6, 0)
        s2 = self._create_schedule(routine, 'Bible', 6, 30)
        today = get_user_today(self.user)
        RoutineLog.objects.create(
            user=self.user, schedule=s1, scheduled_date=today, log_status='completed',
        )
        RoutineLog.objects.create(
            user=self.user, schedule=s2, scheduled_date=today, log_status='completed',
        )
        state = get_routine_completion_state(self.user, routine, today)
        self.assertTrue(state['all_complete'])

    def test_toggle_routine_complete_checks_all(self):
        """Toggling incomplete routine completes all items."""
        from apps.life.services.routine_helpers import toggle_routine_complete
        from apps.core.utils import get_user_today
        routine = self._create_routine()
        s1 = self._create_schedule(routine, 'Prayer', 6, 0)
        s2 = self._create_schedule(routine, 'Bible', 6, 30)
        s3 = self._create_schedule(routine, 'Workout', 7, 0)
        today = get_user_today(self.user)

        result = toggle_routine_complete(self.user, routine, today)
        self.assertTrue(result['all_complete'])
        self.assertEqual(result['completed_count'], 3)
        # Verify logs exist (completed or completed_late depending on time of day)
        self.assertEqual(
            RoutineLog.objects.filter(
                scheduled_date=today,
                log_status__in=('completed', 'completed_late'),
                schedule__in=[s1, s2, s3],
            ).count(), 3
        )

    def test_toggle_routine_complete_unchecks_all(self):
        """Toggling complete routine reverts all items to pending."""
        from apps.life.services.routine_helpers import toggle_routine_complete
        from apps.core.utils import get_user_today
        routine = self._create_routine()
        s1 = self._create_schedule(routine, 'Prayer', 6, 0)
        s2 = self._create_schedule(routine, 'Bible', 6, 30)
        today = get_user_today(self.user)
        # Pre-complete both
        RoutineLog.objects.create(
            user=self.user, schedule=s1, scheduled_date=today, log_status='completed',
        )
        RoutineLog.objects.create(
            user=self.user, schedule=s2, scheduled_date=today, log_status='completed',
        )
        result = toggle_routine_complete(self.user, routine, today)
        self.assertFalse(result['all_complete'])
        self.assertEqual(result['completed_count'], 0)
        # Logs should be deleted
        self.assertEqual(
            RoutineLog.objects.filter(
                scheduled_date=today, schedule__in=[s1, s2],
            ).count(), 0
        )

    def test_completing_last_item_makes_routine_complete(self):
        """Child→parent: completing the last item makes routine all_complete."""
        from apps.life.services.routine_helpers import (
            toggle_routine_completion, get_routine_completion_state,
        )
        from apps.core.utils import get_user_today
        routine = self._create_routine()
        s1 = self._create_schedule(routine, 'Prayer', 6, 0)
        s2 = self._create_schedule(routine, 'Bible', 6, 30)
        today = get_user_today(self.user)
        # Complete first item
        toggle_routine_completion(self.user, s1, today)
        state = get_routine_completion_state(self.user, routine, today)
        self.assertFalse(state['all_complete'])
        # Complete last item
        toggle_routine_completion(self.user, s2, today)
        state = get_routine_completion_state(self.user, routine, today)
        self.assertTrue(state['all_complete'])

    def test_unchecking_one_item_makes_routine_incomplete(self):
        """Child→parent: unchecking any item makes routine incomplete."""
        from apps.life.services.routine_helpers import (
            toggle_routine_completion, get_routine_completion_state,
        )
        from apps.core.utils import get_user_today
        routine = self._create_routine()
        s1 = self._create_schedule(routine, 'Prayer', 6, 0)
        s2 = self._create_schedule(routine, 'Bible', 6, 30)
        today = get_user_today(self.user)
        # Complete both
        toggle_routine_completion(self.user, s1, today)
        toggle_routine_completion(self.user, s2, today)
        state = get_routine_completion_state(self.user, routine, today)
        self.assertTrue(state['all_complete'])
        # Uncheck one
        toggle_routine_completion(self.user, s1, today)
        state = get_routine_completion_state(self.user, routine, today)
        self.assertFalse(state['all_complete'])

    def test_only_target_date_affected(self):
        """Toggling routine only affects target date logs."""
        from apps.life.services.routine_helpers import toggle_routine_complete
        from apps.core.utils import get_user_today
        from datetime import timedelta
        routine = self._create_routine()
        s1 = self._create_schedule(routine, 'Prayer', 6, 0)
        today = get_user_today(self.user)
        yesterday = today - timedelta(days=1)
        # Create yesterday's log
        RoutineLog.objects.create(
            user=self.user, schedule=s1, scheduled_date=yesterday, log_status='completed',
        )
        # Toggle today
        toggle_routine_complete(self.user, routine, today)
        # Yesterday's log must be untouched
        self.assertTrue(
            RoutineLog.objects.filter(
                schedule=s1, scheduled_date=yesterday, log_status='completed',
            ).exists()
        )

    def test_zero_applicable_items_noop(self):
        """Routine with items not applicable today no-ops safely."""
        from apps.life.services.routine_helpers import toggle_routine_complete
        from apps.core.utils import get_user_today
        routine = self._create_routine()
        # Create item only for Monday (weekday 0)
        schedule = RoutineSchedule.objects.create(
            routine=routine, name='Monday Only',
            scheduled_time=time(6, 0),
            grace_period_minutes=30,
            days_of_week='0',  # Monday only
            is_active=True,
        )
        today = get_user_today(self.user)
        # If today is not Monday, no-op
        if today.weekday() != 0:
            result = toggle_routine_complete(self.user, routine, today)
            self.assertEqual(result['total_count'], 0)


class RoutineCompleteToggleViewTests(RoutineTestMixin, TestCase):
    """Tests for the routine-level toggle endpoint."""

    def test_toggle_endpoint(self):
        from apps.core.utils import get_user_today
        routine = self._create_routine()
        s1 = self._create_schedule(routine, 'Prayer', 6, 0)
        s2 = self._create_schedule(routine, 'Bible', 6, 30)
        response = self.client.post(
            reverse('life:routine_complete_toggle', args=[routine.pk]),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['all_complete'])
        self.assertEqual(data['completed_count'], 2)

    def test_state_builder_includes_routine_completion(self):
        from apps.core.ai_state.state_builder import build_routine_state
        from apps.core.utils import get_user_today
        routine = self._create_routine()
        s1 = self._create_schedule(routine, 'Prayer', 6, 0)
        s2 = self._create_schedule(routine, 'Bible', 6, 30)
        today = get_user_today(self.user)
        RoutineLog.objects.create(
            user=self.user, schedule=s1, scheduled_date=today, log_status='completed',
        )
        state = build_routine_state(self.user)
        contract = state.get('_contract', {})
        rc = contract.get('today', {}).get('routine_completion', {})
        self.assertIn(routine.id, rc)
        self.assertEqual(rc[routine.id]['completed_count'], 1)
        self.assertEqual(rc[routine.id]['total_count'], 2)
        self.assertFalse(rc[routine.id]['all_complete'])
