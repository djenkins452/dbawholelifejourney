# ==============================================================================
# File: test_state_invalidation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests that task mutations (complete, skip, delete, update)
#              properly invalidate CoS and SAE caches.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-12
# ==============================================================================

from unittest.mock import patch, MagicMock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

LOCMEM_CACHE = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'state-invalidation-test',
    }
}

from apps.life.models import Task
from apps.users.models import User


@override_settings(CACHES=LOCMEM_CACHE)
class TestTaskStateInvalidation(TestCase):
    """Verify task state changes invalidate CoS context cache."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='state-test@example.com',
            password='testpass123',
            first_name='Test',
        )
        self.today = timezone.now().date()
        self.task = Task.objects.create(
            user=self.user,
            title="Test Task",
            due_date=self.today,
            completion_status='pending',
        )

    @patch('apps.ai.readiness_cache.invalidate_cos_context_on_action')
    def test_mark_complete_invalidates_cos_cache(self, mock_invalidate):
        """mark_complete() must invalidate CoS context."""
        self.task.mark_complete()
        mock_invalidate.assert_called_once_with(self.user)

    @patch('apps.ai.readiness_cache.invalidate_cos_context_on_action')
    def test_mark_skipped_invalidates_cos_cache(self, mock_invalidate):
        """mark_skipped() must invalidate CoS context."""
        self.task.mark_skipped()
        mock_invalidate.assert_called_once_with(self.user)

    @patch('apps.ai.readiness_cache.invalidate_cos_context_on_action')
    def test_mark_incomplete_invalidates_cos_cache(self, mock_invalidate):
        """mark_incomplete() must invalidate CoS context."""
        self.task.completion_status = 'completed'
        self.task.save(update_fields=['completion_status'])
        mock_invalidate.reset_mock()

        self.task.mark_incomplete()
        mock_invalidate.assert_called_once_with(self.user)

    @patch('apps.ai.readiness_cache.invalidate_cos_context_on_action')
    def test_soft_delete_invalidates_cos_cache(self, mock_invalidate):
        """soft_delete() must invalidate CoS context."""
        self.task.soft_delete()
        mock_invalidate.assert_called_once_with(self.user)

    def test_soft_delete_emits_task_deleted_event(self):
        """soft_delete() on a Task must emit TASK_DELETED event."""
        with patch('apps.core.events.domain_events.safe_emit_event') as mock_emit:
            self.task.soft_delete()
            # Find the TASK_DELETED call among all calls
            deleted_calls = [
                c for c in mock_emit.call_args_list
                if len(c.args) >= 1 and c.args[0] == 'task.deleted'
            ]
            self.assertEqual(len(deleted_calls), 1)

    def test_mark_skipped_emits_task_skipped_event(self):
        """mark_skipped() must emit TASK_SKIPPED event."""
        with patch('apps.core.events.domain_events.safe_emit_event') as mock_emit:
            self.task.mark_skipped()
            skipped_calls = [
                c for c in mock_emit.call_args_list
                if len(c.args) >= 1 and c.args[0] == 'task.skipped'
            ]
            self.assertEqual(len(skipped_calls), 1)

    def test_completion_status_not_affected_by_time_change(self):
        """Changing scheduled_time must not change completion_status."""
        from datetime import time
        self.task.scheduled_time = time(12, 0)
        self.task.save(update_fields=['scheduled_time', 'updated_at'])

        self.task.refresh_from_db()
        self.assertEqual(self.task.completion_status, 'pending')


@override_settings(CACHES=LOCMEM_CACHE)
class TestProjectionRefreshFromDb(TestCase):
    """Verify calendar projection refreshes task state from DB."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='projection-test@example.com',
            password='testpass123',
            first_name='Test',
        )
        prefs = self.user.preferences
        prefs.timezone = 'America/Chicago'
        prefs.save()
        self.today = timezone.now().date()

    @patch('apps.calendar_engine.services.projection.CalendarEvent')
    def test_upsert_from_task_refreshes_completion_status(self, mock_ce):
        """upsert_from_task must refresh_from_db before checking is_completed."""
        from datetime import time
        task = Task.objects.create(
            user=self.user,
            title="Refresh Test",
            due_date=self.today,
            scheduled_time=time(9, 0),
            completion_status='pending',
        )
        # Simulate stale in-memory state
        task.completion_status = 'completed'

        # The projection should call refresh_from_db, which returns
        # the DB value ('pending'), not the stale in-memory 'completed'
        from apps.calendar_engine.services.projection import upsert_from_routine_task
        with patch.object(task, 'refresh_from_db') as mock_refresh:
            def _do_refresh(fields=None):
                task.completion_status = 'pending'
            mock_refresh.side_effect = _do_refresh
            try:
                upsert_from_routine_task(task)
            except Exception:
                pass  # CalendarEvent mock may not have full API
            mock_refresh.assert_called_once()
