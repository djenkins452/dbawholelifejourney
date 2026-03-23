"""
Tests for the routine schedule days_of_week save bug.

Regression tests to ensure that editing days on a RoutineSchedule
persists correctly and is not reverted by the extra formset form.
"""

from datetime import time

from django.conf import settings
from django.test import TestCase, Client
from django.urls import reverse

from apps.life.models import Routine, RoutineSchedule
from apps.users.models import User, TermsAcceptance


class RoutineDaysSaveMixin:
    """Shared setup for routine days save tests."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='daytest@test.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client.login(email='daytest@test.com', password='testpass123')
        self.routine = Routine.objects.create(
            user=self.user, name='Morning', time_of_day='morning', is_active=True,
        )
        self.sched = RoutineSchedule.objects.create(
            routine=self.routine, name='Prayer', scheduled_time=time(6, 30),
            grace_period_minutes=30, days_of_week='0,1,2,3,4,5,6', is_active=True,
        )

    def _post_data(self, active_days, extra_form=True):
        """Build realistic POST data matching what the browser sends."""
        data = {
            'name': 'Morning', 'description': '', 'time_of_day': 'morning',
            'is_active': 'on', 'sort_order': '0',
            'items-TOTAL_FORMS': '2' if extra_form else '1',
            'items-INITIAL_FORMS': '1',
            'items-MIN_NUM_FORMS': '0',
            'items-MAX_NUM_FORMS': '1000',
            # Existing schedule item
            'items-0-id': str(self.sched.pk),
            'items-0-name': 'Prayer',
            'items-0-importance': 'flexible',
            'items-0-scheduled_time': '06:30',
            'items-0-grace_period_minutes': '30',
            'items-0-is_active': 'on',
            'items-0-active_days': active_days,
            'items-0-sort_order': '0',
            'items-0-routine_type': 'binary',
            'items-0-maintenance_type': 'maintenance',
            'items-0-maintenance_area': '',
            'items-0-default_maintenance_title': '',
        }
        if extra_form:
            data.update({
                'items-1-name': '',
                'items-1-importance': 'flexible',
                'items-1-scheduled_time': '',
                'items-1-grace_period_minutes': '30',
                'items-1-sort_order': '0',
                'items-1-active_days': ['0', '1', '2', '3', '4', '5', '6'],
                'items-1-routine_type': 'binary',
                'items-1-maintenance_type': 'maintenance',
                'items-1-maintenance_area': '',
                'items-1-default_maintenance_title': '',
            })
        return data


class RoutineDaysRemoveSundayTest(RoutineDaysSaveMixin, TestCase):
    """Regression: removing Sunday must persist and not revert."""

    def test_remove_sunday_persists(self):
        """Uncheck Sunday, save, verify DB and re-rendered page."""
        url = reverse('life:routine_update', args=[self.routine.pk])
        data = self._post_data(['0', '1', '2', '3', '4', '5'])

        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302, "Should redirect on success")

        self.sched.refresh_from_db()
        self.assertEqual(self.sched.days_of_week, '0,1,2,3,4,5')
        self.assertNotIn('6', self.sched.days_of_week.split(','))

    def test_remove_sunday_reflected_on_reload(self):
        """After saving without Sunday, the edit page shows Sunday unchecked."""
        import re

        url = reverse('life:routine_update', args=[self.routine.pk])
        self.client.post(url, self._post_data(['0', '1', '2', '3', '4', '5']))

        resp = self.client.get(url)
        content = resp.content.decode()
        checks = re.findall(
            r'name="items-0-active_days"\s+value="(\d)"\s*(checked)?',
            content,
        )
        checked_days = {v for v, c in checks if c}
        self.assertNotIn('6', checked_days, "Sunday should not be checked")
        self.assertEqual(checked_days, {'0', '1', '2', '3', '4', '5'})


class RoutineDaysVariousCombinationsTest(RoutineDaysSaveMixin, TestCase):
    """Ensure various day combinations persist correctly."""

    def test_weekdays_only(self):
        url = reverse('life:routine_update', args=[self.routine.pk])
        self.client.post(url, self._post_data(['0', '1', '2', '3', '4']))
        self.sched.refresh_from_db()
        self.assertEqual(self.sched.days_of_week, '0,1,2,3,4')

    def test_weekends_only(self):
        url = reverse('life:routine_update', args=[self.routine.pk])
        self.client.post(url, self._post_data(['5', '6']))
        self.sched.refresh_from_db()
        self.assertEqual(self.sched.days_of_week, '5,6')

    def test_single_day(self):
        url = reverse('life:routine_update', args=[self.routine.pk])
        self.client.post(url, self._post_data(['3']))
        self.sched.refresh_from_db()
        self.assertEqual(self.sched.days_of_week, '3')

    def test_all_days(self):
        url = reverse('life:routine_update', args=[self.routine.pk])
        # First remove some days
        self.client.post(url, self._post_data(['0', '1']))
        self.sched.refresh_from_db()
        self.assertEqual(self.sched.days_of_week, '0,1')
        # Then add all back
        self.client.post(url, self._post_data(['0', '1', '2', '3', '4', '5', '6']))
        self.sched.refresh_from_db()
        self.assertEqual(self.sched.days_of_week, '0,1,2,3,4,5,6')


class RoutineExtraFormNoSideEffectTest(RoutineDaysSaveMixin, TestCase):
    """Empty extra form must not block saving or create spurious items."""

    def test_extra_form_does_not_block_save(self):
        url = reverse('life:routine_update', args=[self.routine.pk])
        data = self._post_data(['0', '1', '2'], extra_form=True)
        resp = self.client.post(url, data)
        self.assertEqual(resp.status_code, 302, "Extra form should not block save")
        self.sched.refresh_from_db()
        self.assertEqual(self.sched.days_of_week, '0,1,2')

    def test_extra_form_does_not_create_item(self):
        url = reverse('life:routine_update', args=[self.routine.pk])
        data = self._post_data(['0', '1', '2', '3', '4', '5'], extra_form=True)
        self.client.post(url, data)
        self.assertEqual(self.routine.items.count(), 1, "Should not create extra item")
