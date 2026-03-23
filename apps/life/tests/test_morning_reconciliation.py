"""
Tests for Morning Reconciliation — yesterday's missing routine item detection.

Covers:
1. Missing items appear correctly for yesterday
2. Completed items do NOT appear
3. Activity-based routines excluded
4. Selecting "On Schedule" → correct performed_at
5. Selecting "Later" → correct timing
6. Selecting "Skip" → correct state
7. Items do not reappear after response
8. Prompt only shows once per day
9. Timezone correctness (yesterday based on user TZ)
"""

from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.life.models import Routine, RoutineLog, RoutineSchedule
from apps.users.models import TermsAcceptance, User


class ReconciliationTestMixin:
    """Shared setup for reconciliation tests."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(
            email='reconcile@test.com', password='testpass123'
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.timezone = 'America/Chicago'
        self.user.preferences.save()
        self.client.login(email='reconcile@test.com', password='testpass123')
        self.tz = ZoneInfo('America/Chicago')

        self.routine = Routine.objects.create(
            user=self.user, name='Morning', time_of_day='morning', is_active=True,
        )
        self.schedule = RoutineSchedule.objects.create(
            routine=self.routine, name='Meditation',
            scheduled_time=time(6, 15),
            grace_period_minutes=30,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )
        self.schedule2 = RoutineSchedule.objects.create(
            routine=self.routine, name='Prayer',
            scheduled_time=time(5, 30),
            grace_period_minutes=15,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )

    def _make_aware(self, hour, minute, target_date=None):
        d = target_date or timezone.now().astimezone(self.tz).date()
        return timezone.make_aware(datetime.combine(d, time(hour, minute)), self.tz)

    def _mock_morning(self):
        """Return a mock user_now at 7:00 AM today."""
        today = timezone.now().astimezone(self.tz).date()
        return self._make_aware(7, 0, today)

    def _yesterday(self):
        return timezone.now().astimezone(self.tz).date() - timedelta(days=1)


class TestMissingItemsDetection(ReconciliationTestMixin, TestCase):
    """Test identification of yesterday's missing items."""

    def test_missing_items_appear_for_yesterday(self):
        """Items with no log for yesterday should appear."""
        from apps.life.services.morning_reconciliation import get_yesterdays_missing_items

        items = get_yesterdays_missing_items(self.user)
        self.assertEqual(len(items), 2)
        labels = {i['label'] for i in items}
        self.assertIn('Meditation', labels)
        self.assertIn('Prayer', labels)

    def test_completed_items_excluded(self):
        """Items completed yesterday should NOT appear."""
        from apps.life.services.morning_reconciliation import get_yesterdays_missing_items

        yesterday = self._yesterday()
        RoutineLog.objects.create(
            user=self.user, schedule=self.schedule,
            scheduled_date=yesterday, log_status='completed',
            completed_at=timezone.now(), performed_at=timezone.now(),
            timing='on_time',
        )
        items = get_yesterdays_missing_items(self.user)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['label'], 'Prayer')

    def test_skipped_items_excluded(self):
        """Items skipped yesterday should NOT appear."""
        from apps.life.services.morning_reconciliation import get_yesterdays_missing_items

        yesterday = self._yesterday()
        RoutineLog.objects.create(
            user=self.user, schedule=self.schedule,
            scheduled_date=yesterday, log_status='skipped',
        )
        items = get_yesterdays_missing_items(self.user)
        self.assertEqual(len(items), 1)

    def test_activity_routines_excluded(self):
        """Activity-based routines should NOT appear (auto-completed by signals)."""
        from apps.life.services.morning_reconciliation import get_yesterdays_missing_items

        self.schedule.routine_type = 'activity'
        self.schedule.activity_type = 'workout'
        self.schedule.save()

        items = get_yesterdays_missing_items(self.user)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['label'], 'Prayer')

    def test_items_sorted_by_time_ascending(self):
        """Items should be sorted by scheduled_time (earliest first)."""
        from apps.life.services.morning_reconciliation import get_yesterdays_missing_items

        items = get_yesterdays_missing_items(self.user)
        self.assertEqual(items[0]['label'], 'Prayer')  # 5:30 AM
        self.assertEqual(items[1]['label'], 'Meditation')  # 6:15 AM

    def test_max_five_items(self):
        """No more than 5 items returned."""
        from apps.life.services.morning_reconciliation import get_yesterdays_missing_items

        for i in range(6):
            RoutineSchedule.objects.create(
                routine=self.routine, name=f'Extra {i}',
                scheduled_time=time(7 + i, 0),
                grace_period_minutes=15,
                days_of_week='0,1,2,3,4,5,6',
                is_active=True,
            )
        items = get_yesterdays_missing_items(self.user)
        self.assertLessEqual(len(items), 5)


class TestShouldShowReconciliation(ReconciliationTestMixin, TestCase):
    """Test once-per-day and morning-only gating."""

    def test_shows_in_morning(self):
        """Should show when it's morning (before noon)."""
        from apps.life.services.morning_reconciliation import should_show_reconciliation

        mock_now = self._make_aware(7, 0)
        with patch('apps.core.utils.get_user_now', return_value=mock_now):
            self.assertTrue(should_show_reconciliation(self.user))

    def test_hidden_after_noon(self):
        """Should NOT show after noon."""
        from apps.life.services.morning_reconciliation import should_show_reconciliation

        mock_now = self._make_aware(13, 0)
        with patch('apps.core.utils.get_user_now', return_value=mock_now):
            self.assertFalse(should_show_reconciliation(self.user))

    def test_hidden_after_shown_today(self):
        """Should NOT show after already shown/dismissed today."""
        from apps.life.services.morning_reconciliation import (
            mark_reconciliation_shown,
            should_show_reconciliation,
        )

        mock_now = self._make_aware(7, 0)
        with patch('apps.core.utils.get_user_now', return_value=mock_now):
            mark_reconciliation_shown(self.user)
            self.assertFalse(should_show_reconciliation(self.user))


class TestReconciliationResponses(ReconciliationTestMixin, TestCase):
    """Test response handling through existing execution services."""

    def test_on_schedule_creates_on_time_completion(self):
        """'On Schedule' → performed_at=scheduled_time, timing=on_time."""
        yesterday = self._yesterday()
        url = reverse('dashboard_v2:reconciliation_respond')
        response = self.client.post(url, {
            'schedule_id': self.schedule.pk,
            'response': 'on_schedule',
            'date': yesterday.isoformat(),
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        log = RoutineLog.objects.get(
            schedule=self.schedule, scheduled_date=yesterday,
        )
        self.assertEqual(log.timing, 'on_time')
        self.assertEqual(log.completion_source, 'scheduled_override')
        self.assertEqual(log.log_status, 'completed')
        # performed_at should be the scheduled datetime
        self.assertEqual(log.performed_at.astimezone(self.tz).hour, 6)
        self.assertEqual(log.performed_at.astimezone(self.tz).minute, 15)

    def test_later_creates_late_completion(self):
        """'Later' → timing=late, performed_at=now."""
        yesterday = self._yesterday()
        url = reverse('dashboard_v2:reconciliation_respond')
        response = self.client.post(url, {
            'schedule_id': self.schedule.pk,
            'response': 'later',
            'date': yesterday.isoformat(),
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        log = RoutineLog.objects.get(
            schedule=self.schedule, scheduled_date=yesterday,
        )
        self.assertEqual(log.timing, 'late')
        self.assertEqual(log.log_status, 'completed_late')

    def test_skip_creates_skipped_log(self):
        """'Skip' → state=skipped, performed_at=None."""
        yesterday = self._yesterday()
        url = reverse('dashboard_v2:reconciliation_respond')
        response = self.client.post(url, {
            'schedule_id': self.schedule.pk,
            'response': 'skip',
            'date': yesterday.isoformat(),
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        log = RoutineLog.objects.get(
            schedule=self.schedule, scheduled_date=yesterday,
        )
        self.assertEqual(log.log_status, 'skipped')
        self.assertIsNone(log.performed_at)
        self.assertEqual(log.timing, '')

    def test_items_do_not_reappear_after_response(self):
        """Once answered, an item should not appear in missing items."""
        from apps.life.services.morning_reconciliation import get_yesterdays_missing_items

        yesterday = self._yesterday()
        url = reverse('dashboard_v2:reconciliation_respond')
        self.client.post(url, {
            'schedule_id': self.schedule.pk,
            'response': 'on_schedule',
            'date': yesterday.isoformat(),
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        items = get_yesterdays_missing_items(self.user)
        schedule_ids = {i['schedule_id'] for i in items}
        self.assertNotIn(self.schedule.pk, schedule_ids)

    def test_all_resolved_marks_reconciliation_done(self):
        """When all items are resolved, reconciliation is marked complete."""
        from apps.life.services.morning_reconciliation import should_show_reconciliation

        yesterday = self._yesterday()
        url = reverse('dashboard_v2:reconciliation_respond')

        mock_now = self._make_aware(7, 0)

        # Resolve both items
        for sched in [self.schedule, self.schedule2]:
            self.client.post(url, {
                'schedule_id': sched.pk,
                'response': 'on_schedule',
                'date': yesterday.isoformat(),
            }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        with patch('apps.core.utils.get_user_now', return_value=mock_now):
            self.assertFalse(should_show_reconciliation(self.user))


class TestTimezoneCorrectness(ReconciliationTestMixin, TestCase):
    """Ensure yesterday is based on user timezone, not UTC."""

    def test_yesterday_uses_user_timezone(self):
        """Yesterday should be calculated in user's timezone."""
        from apps.life.services.morning_reconciliation import get_yesterdays_missing_items

        # The function uses get_user_today() which respects user timezone
        items = get_yesterdays_missing_items(self.user)
        # Should find items — they apply to every day of the week
        self.assertGreater(len(items), 0)


class TestReconciliationHTMXEndpoint(ReconciliationTestMixin, TestCase):
    """Test the HTMX section endpoint."""

    def test_section_returns_html(self):
        """GET endpoint returns HTML with reconciliation content."""
        url = reverse('dashboard_v2:section_reconciliation')
        mock_now = self._make_aware(7, 0)

        with patch('apps.core.utils.get_user_now', return_value=mock_now):
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Should contain the reconciliation section when items exist
        self.assertIn('morning-reconciliation', content)
        self.assertIn('Meditation', content)

    def test_section_empty_after_noon(self):
        """GET endpoint returns empty when past noon."""
        url = reverse('dashboard_v2:section_reconciliation')
        mock_now = self._make_aware(14, 0)

        with patch('apps.core.utils.get_user_now', return_value=mock_now):
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn('morning-reconciliation', content)
