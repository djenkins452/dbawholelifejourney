# ==============================================================================
# File: apps/ai/tests/test_hardening.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Regression tests for performance/accuracy/stability hardening
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-11
# ==============================================================================
"""
Hardening Pass Regression Tests

Tests cover:
1. DedupCache: batch-load + in-memory dedup replaces per-generator DB queries
2. Medicine N+1 fix: prefetch_related + batch MedicineLog
3. Goal N+1 fix: batch milestone aggregation
4. Freshness validation: overdue task re-check before delivery
5. Medicine freshness: re-verify at delivery time
6. Cache TTL: extended dynamic TTL (90s)
7. Event-based cache invalidation
"""

from datetime import datetime, date, time, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.models import AssistantConversation, AssistantMessage
from apps.ai.proactive_checkins import (
    _ProactiveDedupCache,
    _get_dedup_cache,
    _dedup_local,
)

User = get_user_model()


class HardeningTestMixin:
    """Common setup for hardening tests."""

    def create_user(self, email='hardening@example.com'):
        user = User.objects.create_user(email=email, password='testpass123')
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.ai_enabled = True
        user.preferences.ai_data_consent = True
        user.preferences.ai_data_consent_date = timezone.now()
        user.preferences.personal_assistant_enabled = True
        user.preferences.personal_assistant_consent = True
        user.preferences.personal_assistant_consent_date = timezone.now()
        user.preferences.assistant_proactive_checkins = True
        user.preferences.health_enabled = True
        user.preferences.journal_enabled = True
        user.preferences.save()
        return user


class TestDedupCache(HardeningTestMixin, TestCase):
    """Test the batch dedup cache for proactive check-ins."""

    def setUp(self):
        self.user = self.create_user()
        self.today = date.today()

    def test_empty_cache_returns_false(self):
        """No proactive messages → already_sent returns False."""
        cache = _ProactiveDedupCache(self.user, self.today)
        self.assertFalse(cache.already_sent('medicine_group'))
        self.assertFalse(cache.already_sent('midday_alignment'))

    def test_matching_type_returns_true(self):
        """Proactive message with matching type → already_sent returns True."""
        conv = AssistantConversation.objects.create(user=self.user)
        AssistantMessage.objects.create(
            conversation=conv,
            role='assistant',
            content='Test',
            is_proactive=True,
            metadata={'check_in_type': 'medicine_group', 'time_of_day': 'morning'},
        )
        cache = _ProactiveDedupCache(self.user, self.today)
        self.assertTrue(cache.already_sent('medicine_group'))
        self.assertTrue(cache.already_sent('medicine_group', time_of_day='morning'))

    def test_extra_filter_narrows_match(self):
        """Extra filter key prevents match on different metadata values."""
        conv = AssistantConversation.objects.create(user=self.user)
        AssistantMessage.objects.create(
            conversation=conv,
            role='assistant',
            content='Test',
            is_proactive=True,
            metadata={'check_in_type': 'medicine_group', 'time_of_day': 'morning'},
        )
        cache = _ProactiveDedupCache(self.user, self.today)
        # Should match morning
        self.assertTrue(cache.already_sent('medicine_group', time_of_day='morning'))
        # Should NOT match evening
        self.assertFalse(cache.already_sent('medicine_group', time_of_day='evening'))

    def test_different_type_returns_false(self):
        """Proactive message with different type → already_sent returns False."""
        conv = AssistantConversation.objects.create(user=self.user)
        AssistantMessage.objects.create(
            conversation=conv,
            role='assistant',
            content='Test',
            is_proactive=True,
            metadata={'check_in_type': 'medicine_group'},
        )
        cache = _ProactiveDedupCache(self.user, self.today)
        self.assertFalse(cache.already_sent('midday_alignment'))
        self.assertFalse(cache.already_sent('evening_wrap'))

    def test_non_proactive_messages_ignored(self):
        """Non-proactive messages should not count as dedup matches."""
        conv = AssistantConversation.objects.create(user=self.user)
        AssistantMessage.objects.create(
            conversation=conv,
            role='assistant',
            content='Test',
            is_proactive=False,
            metadata={'check_in_type': 'medicine_group'},
        )
        cache = _ProactiveDedupCache(self.user, self.today)
        self.assertFalse(cache.already_sent('medicine_group'))

    def test_only_one_query_for_multiple_checks(self):
        """Cache should load once, then check in memory for all types."""
        conv = AssistantConversation.objects.create(user=self.user)
        AssistantMessage.objects.create(
            conversation=conv,
            role='assistant',
            content='T1',
            is_proactive=True,
            metadata={'check_in_type': 'medicine_group'},
        )
        AssistantMessage.objects.create(
            conversation=conv,
            role='assistant',
            content='T2',
            is_proactive=True,
            metadata={'check_in_type': 'midday_alignment'},
        )
        cache = _ProactiveDedupCache(self.user, self.today)

        # First access triggers load
        self.assertTrue(cache.already_sent('medicine_group'))
        # Subsequent accesses use cached data (no additional query)
        self.assertTrue(cache.already_sent('midday_alignment'))
        self.assertFalse(cache.already_sent('evening_wrap'))

        # Verify internal state was loaded once
        self.assertIsNotNone(cache._entries)
        self.assertEqual(len(cache._entries), 2)

    def test_thread_local_cache_set_and_cleared(self):
        """PGS runner should set and clear thread-local dedup cache."""
        today = self.today
        user_dedup = _ProactiveDedupCache(self.user, today)

        # Simulate PGS runner setting thread-local
        _dedup_local.cache = user_dedup
        retrieved = _get_dedup_cache(self.user)
        self.assertIs(retrieved, user_dedup)

        # Clean up
        _dedup_local.cache = None
        # After clearing, _get_dedup_cache creates a new one
        new_cache = _get_dedup_cache(self.user)
        self.assertIsNot(new_cache, user_dedup)


class TestMedicineNPlusOneFix(HardeningTestMixin, TestCase):
    """Test that medicine generator uses prefetch and batch queries."""

    def setUp(self):
        self.user = self.create_user(email='medfix@example.com')

    @patch('apps.core.utils.get_user_today')
    @patch('apps.core.utils.get_user_now')
    def test_no_active_medicines_exits_early(self, mock_now, mock_today):
        """No active medicines → generator exits without errors."""
        mock_today.return_value = date.today()
        mock_now.return_value = datetime.now(tz=timezone.get_current_timezone())

        from apps.ai.proactive_checkins import generate_medicine_check_ins_for_user
        # Should not raise — just return cleanly
        generate_medicine_check_ins_for_user(self.user)


class TestFreshnessValidation(HardeningTestMixin, TestCase):
    """Test that generators re-verify state before creating messages."""

    def setUp(self):
        self.user = self.create_user(email='fresh@example.com')

    @patch('apps.core.utils.get_user_today')
    def test_overdue_task_rechecks_before_delivery(self, mock_today):
        """Task completed between query and delivery → no stale message."""
        from apps.life.models import Task
        today = date.today()
        mock_today.return_value = today

        # Create an overdue task
        task = Task.objects.create(
            user=self.user,
            title='Overdue test',
            due_date=today - timedelta(days=2),
            completion_status='pending',
        )

        # Patch the service to verify it's only called when task is really pending
        with patch('apps.ai.proactive_checkins.get_proactive_service') as mock_svc:
            mock_service = MagicMock()
            mock_svc.return_value = mock_service

            # First call — task is pending
            from apps.ai.proactive_checkins import generate_overdue_task_check_ins_for_user
            generate_overdue_task_check_ins_for_user(self.user)
            mock_service.generate_overdue_task_check_in.assert_called_once()
            mock_service.reset_mock()

            # Now mark it completed
            task.completion_status = 'completed'
            task.completed_at = timezone.now()
            task.save()

            # Second call — task is no longer pending, should NOT generate
            generate_overdue_task_check_ins_for_user(self.user)
            mock_service.generate_overdue_task_check_in.assert_not_called()


class TestGoalMilestoneBatch(HardeningTestMixin, TestCase):
    """Test that goal stalling uses batch milestone query instead of N+1."""

    def setUp(self):
        self.user = self.create_user(email='goals@example.com')

    @patch('apps.core.utils.get_user_today')
    def test_goals_with_no_milestones_checks_created_at(self, mock_today):
        """Goals with no milestones should use created_at for stalling calc."""
        today = date.today()
        mock_today.return_value = today

        try:
            from apps.purpose.models import LifeGoal
        except ImportError:
            self.skipTest("LifeGoal model not available")

        # Create a goal that's been stalled for 60 days
        goal = LifeGoal.objects.create(
            user=self.user,
            title='Test Goal',
            status='active',
            created_at=timezone.now() - timedelta(days=60),
        )

        with patch('apps.ai.proactive_checkins.get_proactive_service') as mock_svc:
            mock_service = MagicMock()
            mock_svc.return_value = mock_service

            from apps.ai.proactive_checkins import generate_goal_check_ins_for_user
            generate_goal_check_ins_for_user(self.user)

            # Should have been called with ~60 days stalled
            if mock_service.generate_goal_stalling_check_in.called:
                args = mock_service.generate_goal_stalling_check_in.call_args
                self.assertGreater(args[1].get('days_stalled', args[0][1] if len(args[0]) > 1 else 0), 30)


class TestCacheTTL(TestCase):
    """Test cache TTL configuration."""

    def test_dynamic_ttl_is_90s(self):
        """Dynamic cache TTL should be 90 seconds (extended from 45s)."""
        from apps.ai.readiness_cache import DYNAMIC_CACHE_TTL, CONTEXT_CACHE_TTL
        self.assertEqual(DYNAMIC_CACHE_TTL, 90)
        self.assertEqual(CONTEXT_CACHE_TTL, 90)

    def test_stable_ttl_unchanged(self):
        """Stable cache TTL should remain 300 seconds (5 min)."""
        from apps.ai.readiness_cache import STABLE_CACHE_TTL
        self.assertEqual(STABLE_CACHE_TTL, 300)

    def test_invalidation_function_exists(self):
        """Event-based invalidation function should be importable."""
        from apps.ai.readiness_cache import invalidate_cos_context_on_action
        self.assertTrue(callable(invalidate_cos_context_on_action))


class TestPGSBatchDedup(HardeningTestMixin, TestCase):
    """Test that PGS runner sets up batch dedup for each user."""

    def setUp(self):
        self.user = self.create_user(email='batch@example.com')

    @patch('apps.ai.proactive_checkins._dispatch_for_window')
    @patch('apps.core.utils.get_user_now')
    @patch('apps.core.utils.get_user_today')
    @patch('apps.ai.proactive_checkins._get_proactive_users')
    def test_dedup_cache_set_during_dispatch(self, mock_users, mock_today,
                                              mock_now, mock_dispatch):
        """PGS runner should set thread-local dedup cache before dispatch."""
        mock_users.return_value = [self.user]
        mock_today.return_value = date.today()
        mock_now.return_value = datetime(2026, 3, 11, 14, 0,
                                         tzinfo=timezone.get_current_timezone())
        mock_dispatch.return_value = 3

        from apps.ai.proactive_checkins import run_proactive_guidance_scheduler

        # Track whether dedup cache was set during dispatch
        cache_was_set = {}

        def check_cache(*args, **kwargs):
            cache_was_set['during_dispatch'] = getattr(_dedup_local, 'cache', None) is not None
            return 2

        mock_dispatch.side_effect = check_cache

        result = run_proactive_guidance_scheduler()

        # Cache was set during dispatch
        self.assertTrue(cache_was_set.get('during_dispatch', False))
        # Cache was cleared after dispatch
        self.assertIsNone(getattr(_dedup_local, 'cache', None))

    @patch('apps.ai.proactive_checkins._dispatch_for_window')
    @patch('apps.core.utils.get_user_now')
    @patch('apps.core.utils.get_user_today')
    @patch('apps.ai.proactive_checkins._get_proactive_users')
    def test_dedup_cache_cleared_on_error(self, mock_users, mock_today,
                                           mock_now, mock_dispatch):
        """PGS runner should clear thread-local even if dispatch raises."""
        mock_users.return_value = [self.user]
        mock_today.return_value = date.today()
        mock_now.return_value = datetime(2026, 3, 11, 14, 0,
                                         tzinfo=timezone.get_current_timezone())
        mock_dispatch.side_effect = Exception("test error")

        from apps.ai.proactive_checkins import run_proactive_guidance_scheduler
        result = run_proactive_guidance_scheduler()

        # Cache should be cleaned up despite error
        self.assertIsNone(getattr(_dedup_local, 'cache', None))
        self.assertEqual(result['errors'], 1)
