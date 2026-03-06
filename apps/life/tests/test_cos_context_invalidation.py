# ==============================================================================
# File: apps/life/tests/test_cos_context_invalidation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Regression tests for CoS context cache invalidation on task save
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-06
# ==============================================================================
"""
Regression Tests — CoS Context Stale After Task Mutation

Verifies that:
1. Saving a task (e.g. moving due_date) invalidates the Redis CoS context cache,
   so the next CoS interaction rebuilds context with fresh CalendarEvent data.
2. The in-request _cos_context_cache is cleared after action execution,
   so downstream validators don't use stale schedule data.

Root cause: "What's for Dinner" task was moved from Wednesday to Sunday via CoS,
but CoS still reported it as due on Wednesday because:
  (a) Redis CoS cache was never invalidated on Task post_save
  (b) In-request context was built once at the start and never refreshed
"""

import datetime as dt
from unittest.mock import patch, MagicMock

from django.core.cache import cache
from django.test import TestCase

from apps.users.models import User


class CosContextInvalidationMixin:
    """Common setup for CoS context invalidation tests."""

    def create_user(self, email='costest@example.com', password='testpass123'):
        user = User.objects.create_user(email=email, password=password)
        from django.conf import settings as django_settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=django_settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def setUp(self):
        super().setUp()
        cache.clear()


class TaskSaveInvalidatesCosCache(CosContextInvalidationMixin, TestCase):
    """
    Regression: Task post_save signal must invalidate CoS context cache.

    Before the fix, saving a Task (moving its due_date) did NOT clear the
    Redis CoS cache, so the next CoS interaction still saw the old date.
    """

    def test_task_save_invalidates_cos_cache(self):
        """Saving a task clears all CoS cache layers for that user."""
        from apps.life.models import Task
        from apps.ai.readiness_cache import (
            set_cached_cos_context,
            get_cached_cos_context,
            _stable_key,
            _dynamic_key,
            _context_key,
        )

        user = self.create_user()

        # Pre-populate all cache layers with fake context
        fake_context = {'calendar_events': [{'title': 'Stale Event'}]}
        set_cached_cos_context(user, fake_context)
        cache.set(_stable_key(user), {'blueprint_state': 'stale'}, 300)
        cache.set(_dynamic_key(user), {'calendar': 'stale'}, 45)

        # Verify cache is populated
        self.assertIsNotNone(get_cached_cos_context(user))
        self.assertIsNotNone(cache.get(_stable_key(user)))
        self.assertIsNotNone(cache.get(_dynamic_key(user)))

        # Save a task — signal should invalidate all cache layers
        with patch('apps.calendar_engine.services.projection.upsert_from_task'):
            Task.objects.create(
                user=user,
                title='Test Task',
                due_date=dt.date(2026, 3, 10),
            )

        # All cache layers should be cleared
        self.assertIsNone(
            get_cached_cos_context(user),
            "Flat CoS cache should be invalidated after task save"
        )
        self.assertIsNone(
            cache.get(_stable_key(user)),
            "Stable cache layer should be invalidated after task save"
        )
        self.assertIsNone(
            cache.get(_dynamic_key(user)),
            "Dynamic cache layer should be invalidated after task save"
        )

    def test_task_date_move_invalidates_cache(self):
        """Moving a task's due_date from one day to another clears CoS cache."""
        from apps.life.models import Task
        from apps.ai.readiness_cache import (
            set_cached_cos_context,
            get_cached_cos_context,
        )

        user = self.create_user()

        # Create a task (this save also invalidates, but we re-seed after)
        with patch('apps.calendar_engine.services.projection.upsert_from_task'):
            task = Task.objects.create(
                user=user,
                title='Whats for Dinner',
                due_date=dt.date(2026, 3, 4),  # Wednesday
            )

        # Seed cache with context that includes the old date
        stale_context = {
            'calendar_events': [
                {'title': 'Whats for Dinner', 'date': '2026-03-04'},
            ],
        }
        set_cached_cos_context(user, stale_context)
        self.assertIsNotNone(get_cached_cos_context(user))

        # Move task to Sunday — signal fires on save
        with patch('apps.calendar_engine.services.projection.upsert_from_task'):
            task.due_date = dt.date(2026, 3, 8)  # Sunday
            task.save(update_fields=['due_date'])

        # Cache should be cleared
        self.assertIsNone(
            get_cached_cos_context(user),
            "CoS cache must be cleared when task due_date changes"
        )

    def test_cache_invalidation_does_not_block_task_save(self):
        """Cache invalidation failure must not prevent task creation."""
        from apps.life.models import Task

        user = self.create_user()

        # Make cache operations fail
        with patch('apps.calendar_engine.services.projection.upsert_from_task'):
            with patch('apps.ai.readiness_cache.invalidate_cos_context',
                       side_effect=Exception("Redis down")):
                # Should not raise — cache invalidation is best-effort
                task = Task.objects.create(
                    user=user,
                    title='Resilient Task',
                    due_date=dt.date(2026, 3, 10),
                )
                self.assertIsNotNone(task.pk)

    def test_other_users_cache_not_affected(self):
        """Saving user A's task must not invalidate user B's cache."""
        from apps.life.models import Task
        from apps.ai.readiness_cache import (
            set_cached_cos_context,
            get_cached_cos_context,
        )

        user_a = self.create_user(email='usera@example.com')
        user_b = self.create_user(email='userb@example.com')

        # Seed both users' caches
        set_cached_cos_context(user_a, {'user': 'A'})
        set_cached_cos_context(user_b, {'user': 'B'})

        # Save user A's task
        with patch('apps.calendar_engine.services.projection.upsert_from_task'):
            Task.objects.create(
                user=user_a,
                title='User A Task',
                due_date=dt.date(2026, 3, 10),
            )

        # User A's cache: cleared. User B's cache: untouched.
        self.assertIsNone(get_cached_cos_context(user_a))
        self.assertIsNotNone(
            get_cached_cos_context(user_b),
            "Other user's CoS cache must not be affected"
        )


class InRequestCacheInvalidationTest(CosContextInvalidationMixin, TestCase):
    """
    Regression: In-request _cos_context_cache must be cleared after action
    execution so downstream validators don't see stale schedule data.

    This tests the code pattern (not end-to-end) that _cos_context_cache
    is set to None when actions_taken is non-empty.
    """

    def test_non_streaming_clears_cache_after_action(self):
        """
        Verify that the non-streaming send_message path sets
        _cos_context_cache = None after successful action execution.

        We test this by inspecting the source code pattern, since
        end-to-end testing of send_message requires extensive mocking.
        """
        import inspect
        from apps.ai.personal_assistant import PersonalAssistant

        source = inspect.getsource(PersonalAssistant.send_message)

        # The pattern should exist: after actions_taken, cache is cleared
        self.assertIn(
            '_cos_context_cache = None',
            source,
            "send_message() must contain '_cos_context_cache = None' "
            "to clear stale context after action execution"
        )

        # Verify it's conditioned on actions_taken
        # Find the invalidation pattern in context
        lines = source.split('\n')
        found_invalidation = False
        for i, line in enumerate(lines):
            if 'actions_taken' in line and '_cos_context_cache = None' in lines[i + 1] if i + 1 < len(lines) else '':
                found_invalidation = True
                break
            if '_cos_context_cache = None' in line and i > 0 and 'actions_taken' in lines[i - 1]:
                found_invalidation = True
                break

        self.assertTrue(
            found_invalidation,
            "send_message() should invalidate _cos_context_cache "
            "conditionally on actions_taken being non-empty"
        )

    def test_streaming_clears_cache_after_action(self):
        """
        Verify that the streaming send_message_stream path sets
        _cos_context_cache = None after successful action execution.
        """
        import inspect
        from apps.ai.personal_assistant import PersonalAssistant

        source = inspect.getsource(PersonalAssistant.send_message_stream)

        self.assertIn(
            '_cos_context_cache = None',
            source,
            "send_message_stream() must contain '_cos_context_cache = None' "
            "to clear stale context after action execution"
        )
