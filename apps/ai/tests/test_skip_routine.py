"""
Regression tests for natural-language routine skip + check-in honoring.

Trust investigation 2026-05-31: Beth verbally acknowledged "I'll skip the
shower" but no skip mutation occurred, and even an existing button-skip would
still surface in check-ins because the Today Engine ignored skip status.

Covers:
  - NL skip writes a skipped RoutineLog and returns deterministic success
  - A skipped routine is hidden from Today Engine actionable buckets
  - The existing button/helper skip path is honored the same way
  - Skipping today does not affect tomorrow (natural reset)
  - Unknown routine returns an honest failure (no fake acknowledgment)
"""

from datetime import date, time, timedelta

from django.conf import settings
from django.test import TestCase

from apps.ai.action_handlers import ActionHandler
from apps.core.today.today_engine import (
    _collect_routine_items,
    get_today_context,
)
from apps.core.utils import get_user_today
from apps.life.models import Routine, RoutineLog, RoutineSchedule
from apps.life.services.routine_helpers import skip_routine
from apps.users.models import TermsAcceptance, User


class SkipRoutineTestMixin:
    def setUp(self):
        self.user = User.objects.create_user(
            email='skip-routine@test.com', password='testpass123',
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.timezone = 'America/Chicago'
        self.user.preferences.save()

        self.routine = Routine.objects.create(
            user=self.user, name='Morning', time_of_day='morning',
            is_active=True,
        )
        self.shower = RoutineSchedule.objects.create(
            routine=self.routine, name='Shower',
            scheduled_time=time(7, 0),
            grace_period_minutes=30,
            days_of_week='0,1,2,3,4,5,6',
            is_active=True,
        )


class TestNLSkipRoutineHandler(SkipRoutineTestMixin, TestCase):
    """handle_skip_routine performs a real deterministic mutation."""

    def test_skip_writes_skipped_log_and_succeeds(self):
        handler = ActionHandler(self.user)
        result = handler.handle_skip_routine(item_keyword='shower')

        self.assertTrue(result.success)
        # Confirmation only after a real mutation exists.
        log = RoutineLog.objects.get(schedule=self.shower)
        self.assertEqual(log.log_status, 'skipped')
        # Skipping is NOT completing.
        self.assertNotIn('done', result.message.lower())
        self.assertNotIn('complete', result.message.lower())

    def test_unknown_routine_fails_honestly(self):
        handler = ActionHandler(self.user)
        result = handler.handle_skip_routine(item_keyword='moonwalking')

        self.assertFalse(result.success)
        self.assertEqual(result.error, 'item_not_found')
        # No skip log was written for a nonexistent routine.
        self.assertFalse(RoutineLog.objects.exists())
        # Honest failure — never implies success.
        self.assertNotIn("i'll skip", result.message.lower())


class TestSkippedRoutineHiddenFromCheckIn(SkipRoutineTestMixin, TestCase):
    """A skipped routine must not appear in actionable check-in surfaces."""

    def _all_check_in_labels(self):
        ctx = get_today_context(self.user)
        labels = []
        for bucket in ('overdue', 'coming_up', 'later', 'foundation',
                       'completed'):
            labels.extend(e['label'] for e in ctx.get(bucket, []))
        labels.extend(i['name'] for i in ctx.get('all_items', []))
        return labels

    def test_shower_present_before_skip(self):
        labels = self._all_check_in_labels()
        self.assertTrue(any('Shower' in l for l in labels))

    def test_shower_hidden_after_nl_skip(self):
        ActionHandler(self.user).handle_skip_routine(item_keyword='shower')
        labels = self._all_check_in_labels()
        self.assertFalse(
            any('Shower' in l for l in labels),
            f"Skipped Shower leaked into check-in: {labels}",
        )

    def test_shower_hidden_after_button_skip(self):
        # Existing quick-reply/helper path writes the same skipped log.
        skip_routine(self.user, self.shower, get_user_today(self.user))
        labels = self._all_check_in_labels()
        self.assertFalse(any('Shower' in l for l in labels))


class TestCollectorSkipExclusion(TestCase):
    """_collect_routine_items drops only skipped items, keeps the rest."""

    def _truth(self, status):
        return {
            'routines': {
                '_raw_items': {
                    'morning': [{
                        'item_name': 'Shower',
                        'scheduled_time': '7:00 AM',
                        'is_completed': False,
                        'status': status,
                        'schedule_id': 1,
                        'importance': 'flexible',
                    }],
                },
            },
        }

    def test_skipped_item_dropped(self):
        from django.utils import timezone
        items = _collect_routine_items(self._truth('skipped'), timezone.now())
        self.assertEqual(items, [])

    def test_pending_item_kept(self):
        from django.utils import timezone
        items = _collect_routine_items(self._truth('pending'), timezone.now())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['name'], 'Shower')


class TestTomorrowResetAfterSkip(SkipRoutineTestMixin, TestCase):
    """Skipping today must not suppress the routine tomorrow."""

    def test_skip_is_scoped_to_today(self):
        today = get_user_today(self.user)
        skip_routine(self.user, self.shower, today)

        # Skip log exists for today only.
        self.assertTrue(
            RoutineLog.objects.filter(
                schedule=self.shower, scheduled_date=today,
                log_status='skipped',
            ).exists()
        )
        # No skip log exists for tomorrow — it resets naturally.
        tomorrow = today + timedelta(days=1)
        self.assertFalse(
            RoutineLog.objects.filter(
                schedule=self.shower, scheduled_date=tomorrow,
            ).exists()
        )
