# ==============================================================================
# File: tests/test_calendar_crud.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for Calendar CRUD via CoS (read_calendar_events + mutate_calendar_event)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-02-23
# ==============================================================================
"""
Calendar CRUD Tests

Validates:
1) read_calendar_events returns created events
2) mutate_calendar_event create works
3) mutate_calendar_event update works and uses select_for_update
4) mutate_calendar_event delete performs soft delete (status='canceled')
5) ExecutionLog written for time-change updates and deletes
6) Idempotency replay does not duplicate
7) Learning Mode blocks mutation
8) View PATCH uses CalendarMutationService (soft delete, not hard delete)
9) View DELETE uses CalendarMutationService (soft delete, not hard delete)
"""

import datetime as dt
import json
from unittest.mock import patch
from uuid import uuid4

import pytz
from django.conf import settings
from django.test import TestCase, TransactionTestCase

from apps.calendar_engine.models import CalendarEvent
from apps.calendar_engine.utils.idempotency import compute_idempotency_key
from apps.users.models import User


class CalendarCRUDTestMixin:
    """Shared setup for Calendar CRUD tests."""

    def _create_user(self, email='calcrud@example.com'):
        user = User.objects.create_user(
            email=email,
            password='testpass123',
            first_name='Test',
        )
        prefs = user.preferences
        prefs.timezone = 'America/New_York'
        prefs.ai_enabled = True
        prefs.ai_data_consent = True
        prefs.personal_assistant_enabled = True
        prefs.personal_assistant_consent = True
        prefs.save()
        return user

    def _create_event(self, user, title='Test Event', hours_offset=0, **kwargs):
        """Helper to create a CalendarEvent with auto-generated idempotency_key."""
        tz = pytz.timezone('America/New_York')
        start = tz.localize(dt.datetime(2026, 2, 25, 10 + hours_offset, 0))
        end = start + dt.timedelta(hours=1)
        idem_key = kwargs.pop('idempotency_key', uuid4().hex)
        return CalendarEvent.objects.create(
            user=user,
            title=title,
            start_dt=start,
            end_dt=end,
            idempotency_key=idem_key,
            **kwargs,
        )


class ReadCalendarEventsTests(CalendarCRUDTestMixin, TestCase):
    """Tests for handle_read_calendar_events."""

    def setUp(self):
        self.user = self._create_user()
        from apps.ai.action_handlers import ActionHandler
        self.handler = ActionHandler(self.user)

    def test_read_returns_created_events(self):
        """read_calendar_events returns events that were created."""
        self._create_event(self.user, 'Morning Workout')
        self._create_event(self.user, 'Team Meeting', hours_offset=2)

        result = self.handler.handle_read_calendar_events(
            timezone='America/New_York',
            date_range_start='2026-02-25',
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action_type, 'read_calendar_events')
        events = result.created_object['events']
        self.assertEqual(len(events), 2)
        titles = [e['title'] for e in events]
        self.assertIn('Morning Workout', titles)
        self.assertIn('Team Meeting', titles)

    def test_read_filters_by_title(self):
        """read_calendar_events filters by query_text."""
        self._create_event(self.user, 'Morning Workout')
        self._create_event(self.user, 'Team Meeting', hours_offset=2)

        result = self.handler.handle_read_calendar_events(
            timezone='America/New_York',
            query_text='workout',
            date_range_start='2026-02-25',
        )

        self.assertTrue(result.success)
        events = result.created_object['events']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['title'], 'Morning Workout')

    def test_read_excludes_canceled_by_default(self):
        """read_calendar_events excludes canceled events unless include_deleted=True."""
        ev1 = self._create_event(self.user, 'Active Event')
        ev2 = self._create_event(self.user, 'Canceled Event', hours_offset=1)
        ev2.status = CalendarEvent.STATUS_CANCELED
        ev2.save(update_fields=['status'])

        result = self.handler.handle_read_calendar_events(
            timezone='America/New_York',
            date_range_start='2026-02-25',
        )
        events = result.created_object['events']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['title'], 'Active Event')

        # Now include deleted
        result2 = self.handler.handle_read_calendar_events(
            timezone='America/New_York',
            date_range_start='2026-02-25',
            include_deleted=True,
        )
        events2 = result2.created_object['events']
        self.assertEqual(len(events2), 2)

    def test_read_returns_event_ids(self):
        """Events include 'id' field for use with mutate_calendar_event."""
        ev = self._create_event(self.user, 'Test Event')

        result = self.handler.handle_read_calendar_events(
            timezone='America/New_York',
            date_range_start='2026-02-25',
        )
        events = result.created_object['events']
        self.assertEqual(events[0]['id'], ev.pk)


class MutateCreateTests(CalendarCRUDTestMixin, TestCase):
    """Tests for mutate_calendar_event(action='create')."""

    def setUp(self):
        self.user = self._create_user('mutcreate@example.com')
        from apps.ai.action_handlers import ActionHandler
        self.handler = ActionHandler(self.user)

    def test_mutate_create_works(self):
        """mutate_calendar_event(action='create') creates an event."""
        result = self.handler.handle_mutate_calendar_event(
            action='create',
            idempotency_key='test-create-123',
            timezone='America/New_York',
            title='Created via Mutate',
            start_date='2026-02-25',
            start_time='14:00',
            event_type='work',
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action_type, 'create_event')  # Delegates to create_event

        # Verify in DB
        events = CalendarEvent.objects.filter(user=self.user, title='Created via Mutate')
        self.assertEqual(events.count(), 1)


class MutateUpdateTests(CalendarCRUDTestMixin, TestCase):
    """Tests for mutate_calendar_event(action='update')."""

    def setUp(self):
        self.user = self._create_user('mutupdate@example.com')
        from apps.ai.action_handlers import ActionHandler
        self.handler = ActionHandler(self.user)

    def test_mutate_update_title(self):
        """Update changes title and reflects in DB."""
        ev = self._create_event(self.user, 'Original Title')

        result = self.handler.handle_mutate_calendar_event(
            action='update',
            idempotency_key='update-title-test',
            timezone='America/New_York',
            event_id=ev.pk,
            title='Updated Title',
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action_type, 'mutate_calendar_event')

        # Verify DB state
        ev.refresh_from_db()
        self.assertEqual(ev.title, 'Updated Title')

    def test_mutate_update_time(self):
        """Update changes start_dt and end_dt."""
        ev = self._create_event(self.user, 'Meeting')

        result = self.handler.handle_mutate_calendar_event(
            action='update',
            idempotency_key='update-time-test',
            timezone='America/New_York',
            event_id=ev.pk,
            start_date='2026-02-26',
            start_time='15:00',
        )

        self.assertTrue(result.success)

        ev.refresh_from_db()
        eastern = pytz.timezone('America/New_York')
        local_start = ev.start_dt.astimezone(eastern)
        self.assertEqual(local_start.date(), dt.date(2026, 2, 26))
        self.assertEqual(local_start.hour, 15)
        self.assertEqual(local_start.minute, 0)

    def test_mutate_update_requires_event_id(self):
        """Update without event_id fails."""
        result = self.handler.handle_mutate_calendar_event(
            action='update',
            idempotency_key='no-event-id',
            timezone='America/New_York',
            title='New Title',
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'missing_event_id')

    def test_mutate_update_nonexistent_event(self):
        """Update on non-existent event fails gracefully."""
        result = self.handler.handle_mutate_calendar_event(
            action='update',
            idempotency_key='ghost-event',
            timezone='America/New_York',
            event_id=99999,
            title='Nope',
        )
        self.assertFalse(result.success)

    def test_update_uses_select_for_update(self):
        """CalendarMutationService.update uses select_for_update."""
        ev = self._create_event(self.user, 'Lock Test')

        from apps.calendar_engine.services.calendar_mutation_service import (
            CalendarMutationService,
        )
        service = CalendarMutationService(self.user)

        with patch.object(
            CalendarEvent.objects, 'select_for_update',
            wraps=CalendarEvent.objects.select_for_update,
        ) as mock_sfu:
            service.update(ev.pk, title='Locked Update')
            mock_sfu.assert_called_once()


class MutateDeleteTests(CalendarCRUDTestMixin, TestCase):
    """Tests for mutate_calendar_event(action='delete')."""

    def setUp(self):
        self.user = self._create_user('mutdelete@example.com')
        from apps.ai.action_handlers import ActionHandler
        self.handler = ActionHandler(self.user)

    def test_mutate_delete_soft_deletes(self):
        """Delete sets status='canceled' and deleted_at, does NOT hard delete."""
        ev = self._create_event(self.user, 'To Delete')

        result = self.handler.handle_mutate_calendar_event(
            action='delete',
            idempotency_key='delete-test',
            timezone='America/New_York',
            event_id=ev.pk,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.action_type, 'mutate_calendar_event')

        # Verify soft delete — row still exists
        ev.refresh_from_db()
        self.assertEqual(ev.status, CalendarEvent.STATUS_CANCELED)
        self.assertIsNotNone(ev.deleted_at)

        # Verify NOT hard deleted
        self.assertTrue(CalendarEvent.objects.filter(pk=ev.pk).exists())

    def test_mutate_delete_requires_event_id(self):
        """Delete without event_id fails."""
        result = self.handler.handle_mutate_calendar_event(
            action='delete',
            idempotency_key='no-event-id-delete',
            timezone='America/New_York',
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'missing_event_id')

    def test_delete_already_canceled_is_idempotent(self):
        """Deleting an already-canceled event returns success."""
        ev = self._create_event(self.user, 'Already Canceled')
        ev.status = CalendarEvent.STATUS_CANCELED
        ev.save(update_fields=['status'])

        from apps.calendar_engine.services.calendar_mutation_service import (
            CalendarMutationService,
        )
        service = CalendarMutationService(self.user)
        result = service.delete(ev.pk)
        self.assertTrue(result.success)


class ExecutionLogTests(CalendarCRUDTestMixin, TestCase):
    """Tests for ExecutionLog writes on mutations."""

    def setUp(self):
        self.user = self._create_user('execlog@example.com')

    def test_execution_log_written_on_time_change(self):
        """DriftEngine.record_schedule_change fires when start_dt changes."""
        from apps.core.drift.models import ExecutionLog

        ev = self._create_event(self.user, 'Time Change Test')
        original_start = ev.start_dt

        from apps.calendar_engine.services.calendar_mutation_service import (
            CalendarMutationService,
        )
        service = CalendarMutationService(self.user)

        new_start = original_start + dt.timedelta(hours=2)
        new_end = new_start + dt.timedelta(hours=1)
        result = service.update(ev.pk, start_dt=new_start, end_dt=new_end)

        self.assertTrue(result.success)

        # Verify ExecutionLog was written
        logs = ExecutionLog.objects.filter(
            user=self.user, calendar_event=ev,
        )
        self.assertGreaterEqual(logs.count(), 1)

    def test_execution_log_written_on_delete(self):
        """ExecutionLog(event_type='canceled') is written on soft delete."""
        from apps.core.drift.models import ExecutionLog

        ev = self._create_event(self.user, 'Delete Log Test')

        from apps.calendar_engine.services.calendar_mutation_service import (
            CalendarMutationService,
        )
        service = CalendarMutationService(self.user)
        result = service.delete(ev.pk)

        self.assertTrue(result.success)

        logs = ExecutionLog.objects.filter(
            user=self.user, calendar_event=ev,
            event_type=ExecutionLog.EVENT_TYPE_CANCELED,
        )
        self.assertEqual(logs.count(), 1)

    def test_no_duplicate_execution_log(self):
        """Idempotent mutation does not create duplicate ExecutionLog rows."""
        from apps.core.drift.models import ExecutionLog

        ev = self._create_event(self.user, 'Dedup Test')

        from apps.calendar_engine.services.calendar_mutation_service import (
            CalendarMutationService,
        )
        service = CalendarMutationService(self.user)

        # Delete twice — second should not create another log
        service.delete(ev.pk)
        result2 = service.delete(ev.pk)  # Already canceled

        self.assertTrue(result2.success)

        logs = ExecutionLog.objects.filter(
            user=self.user, calendar_event=ev,
            event_type=ExecutionLog.EVENT_TYPE_CANCELED,
        )
        self.assertEqual(logs.count(), 1)  # Only one log row


class IdempotencyTests(CalendarCRUDTestMixin, TestCase):
    """Tests for idempotency enforcement."""

    def setUp(self):
        self.user = self._create_user('idempotent@example.com')

    def test_create_idempotency_no_duplicate(self):
        """Creating with same idempotency_key returns existing event."""
        from apps.calendar_engine.services.calendar_mutation_service import (
            CalendarMutationService,
        )
        service = CalendarMutationService(self.user)

        tz = pytz.timezone('America/New_York')
        start = tz.localize(dt.datetime(2026, 2, 25, 10, 0))
        end = start + dt.timedelta(hours=1)

        idem_key = 'test-idem-key-abc'

        result1 = service.create(
            title='Idem Event',
            start_dt=start,
            end_dt=end,
            idempotency_key=idem_key,
        )
        self.assertTrue(result1.success)
        self.assertFalse(result1.reused)
        event_id_1 = result1.event.pk

        result2 = service.create(
            title='Idem Event',
            start_dt=start,
            end_dt=end,
            idempotency_key=idem_key,
        )
        self.assertTrue(result2.success)
        self.assertTrue(result2.reused)
        event_id_2 = result2.event.pk

        self.assertEqual(event_id_1, event_id_2)

        # Only one row in DB
        count = CalendarEvent.objects.filter(
            user=self.user, idempotency_key=idem_key,
        ).count()
        self.assertEqual(count, 1)


class LearningModeTests(CalendarCRUDTestMixin, TestCase):
    """Tests for Learning Mode gating."""

    def setUp(self):
        self.user = self._create_user('learnmode@example.com')
        from apps.ai.action_handlers import ActionHandler
        self.handler = ActionHandler(self.user)

    @patch('apps.core.blueprint.learning_mode.is_learning_mode_active')
    def test_learning_mode_blocks_mutation(self, mock_lm):
        """
        When Learning Mode is active, mutations are blocked via execution_engine.
        The execution_engine imports is_learning_mode_active from
        apps.core.blueprint.learning_mode — patch it there.
        """
        mock_lm.return_value = True

        from apps.core.ai_orchestrator.action_router import EnrichedAction
        from apps.core.ai_orchestrator.execution_engine import execute_action

        enriched = EnrichedAction(
            intent_type='mutate_calendar_event',
            parameters={
                'action': 'delete',
                'event_id': 1,
                'idempotency_key': 'lm-test',
                'timezone': 'America/New_York',
            },
        )

        result = execute_action(self.user, enriched)
        self.assertFalse(result.success)
        self.assertEqual(result.error, 'learning_mode_active')


class ViewLayerIntegrationTests(CalendarCRUDTestMixin, TransactionTestCase):
    """Tests that view-layer PATCH/DELETE use CalendarMutationService."""

    def setUp(self):
        self.user = self._create_user('viewtest@example.com')
        # Ensure terms acceptance for view access
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.get_or_create(
            user=self.user,
            defaults={
                'terms_version': settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
            },
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client.force_login(self.user)

    def test_view_patch_uses_mutation_service(self):
        """PATCH /calendar/api/events/<pk>/ uses CalendarMutationService."""
        ev = self._create_event(self.user, 'View Patch Test')

        response = self.client.patch(
            f'/calendar/api/events/{ev.pk}/',
            json.dumps({'title': 'View Updated'}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        ev.refresh_from_db()
        self.assertEqual(ev.title, 'View Updated')

    def test_view_delete_soft_deletes(self):
        """DELETE /calendar/api/events/<pk>/ now soft-deletes (status='canceled')."""
        ev = self._create_event(self.user, 'View Delete Test')

        response = self.client.delete(
            f'/calendar/api/events/{ev.pk}/',
        )

        self.assertEqual(response.status_code, 200)

        # Verify soft delete — row still exists with status='canceled'
        ev.refresh_from_db()
        self.assertEqual(ev.status, CalendarEvent.STATUS_CANCELED)
        self.assertIsNotNone(ev.deleted_at)

        # Verify NOT hard deleted
        self.assertTrue(CalendarEvent.objects.filter(pk=ev.pk).exists())

    def test_view_delete_no_hard_delete(self):
        """Confirm that the old hard-delete behavior is gone."""
        ev = self._create_event(self.user, 'No Hard Delete')
        pk = ev.pk

        self.client.delete(f'/calendar/api/events/{pk}/')

        # Row must still exist — no hard delete
        self.assertTrue(CalendarEvent.objects.filter(pk=pk).exists())


class DriftHookTests(CalendarCRUDTestMixin, TestCase):
    """Tests that DriftEngine fires exactly once on time change."""

    def setUp(self):
        self.user = self._create_user('drifthook@example.com')

    def test_drift_fires_once_on_update(self):
        """DriftEngine.record_schedule_change called exactly once on time update."""
        from apps.core.drift.models import ExecutionLog

        ev = self._create_event(self.user, 'Drift Test')
        original_start = ev.start_dt
        new_start = original_start + dt.timedelta(hours=3)
        new_end = new_start + dt.timedelta(hours=1)

        from apps.calendar_engine.services.calendar_mutation_service import (
            CalendarMutationService,
        )
        service = CalendarMutationService(self.user)
        result = service.update(ev.pk, start_dt=new_start, end_dt=new_end)

        self.assertTrue(result.success)

        # DriftEngine.record_schedule_change writes ExecutionLog — verify exactly one
        logs = ExecutionLog.objects.filter(
            user=self.user, calendar_event=ev,
        ).exclude(event_type=ExecutionLog.EVENT_TYPE_CANCELED)
        self.assertEqual(logs.count(), 1)
