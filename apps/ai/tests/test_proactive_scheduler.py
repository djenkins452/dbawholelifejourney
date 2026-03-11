# ==============================================================================
# File: apps/ai/tests/test_proactive_scheduler.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for the Proactive Guidance Scheduler (PGS)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-11
# ==============================================================================
"""
Proactive Guidance Scheduler (PGS) Tests

Tests cover:
1. ISE runner: no users → zeros, disabled user skipped, per-user error caught
2. Window dispatch: correct generators for hours 8/11/14/19/3
3. Weekend: midday_alignment NOT called on weekends
4. Feature flags: health_enabled=False → medicine/workout/pattern skipped
5. New generators: dedup, empty data = skip
6. Registry: run_proactive_guidance in SCHEDULED_TASKS and TASK_ENGINE_MAP
"""

from datetime import datetime, date, timedelta
from unittest.mock import patch, MagicMock, PropertyMock

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.ai.models import AssistantConversation, AssistantMessage

User = get_user_model()


class PGSTestMixin:
    """Common setup for PGS tests."""

    def create_user(self, email='pgs@example.com', password='testpass123'):
        user = User.objects.create_user(email=email, password=password)
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


class TestRunnerBasics(PGSTestMixin, TestCase):
    """Test the ISE runner function basics."""

    @patch('apps.ai.proactive_checkins._get_proactive_users')
    @patch('apps.ai.proactive_checkins.trace_context', create=True)
    def test_no_users_returns_zeros(self, mock_trace, mock_users):
        """No eligible users → all-zero metrics."""
        from apps.ai.proactive_checkins import run_proactive_guidance_scheduler
        mock_users.return_value = User.objects.none()
        # Patch trace_context at the import location inside the function
        with patch('apps.core.ai_observability.trace.trace_context') as tc:
            tc.return_value.__enter__ = MagicMock()
            tc.return_value.__exit__ = MagicMock(return_value=False)
            result = run_proactive_guidance_scheduler()

        self.assertEqual(result['users_processed'], 0)
        self.assertEqual(result['check_ins_attempted'], 0)
        self.assertEqual(result['errors'], 0)

    @patch('apps.ai.proactive_checkins._dispatch_for_window')
    @patch('apps.core.utils.get_user_now')
    def test_quiet_hours_skipped(self, mock_now, mock_dispatch):
        """Users in quiet hours (hour < 7 or >= 22) are skipped."""
        from apps.ai.proactive_checkins import run_proactive_guidance_scheduler

        user = self.create_user()
        # 3 AM — quiet hours
        mock_dt = MagicMock()
        mock_dt.hour = 3
        mock_dt.weekday.return_value = 1  # Tuesday
        mock_now.return_value = mock_dt

        with patch('apps.ai.proactive_checkins._get_proactive_users', return_value=[user]):
            with patch('apps.core.ai_observability.trace.trace_context') as tc:
                tc.return_value.__enter__ = MagicMock()
                tc.return_value.__exit__ = MagicMock(return_value=False)
                result = run_proactive_guidance_scheduler()

        self.assertEqual(result['users_processed'], 0)
        mock_dispatch.assert_not_called()

    @patch('apps.ai.proactive_checkins._dispatch_for_window', side_effect=Exception("boom"))
    @patch('apps.core.utils.get_user_now')
    def test_per_user_error_caught(self, mock_now, mock_dispatch):
        """Per-user errors are caught; loop continues."""
        from apps.ai.proactive_checkins import run_proactive_guidance_scheduler

        user = self.create_user()
        mock_dt = MagicMock()
        mock_dt.hour = 10
        mock_dt.weekday.return_value = 1
        mock_now.return_value = mock_dt

        with patch('apps.ai.proactive_checkins._get_proactive_users', return_value=[user]):
            with patch('apps.core.ai_observability.trace.trace_context') as tc:
                tc.return_value.__enter__ = MagicMock()
                tc.return_value.__exit__ = MagicMock(return_value=False)
                result = run_proactive_guidance_scheduler()

        self.assertEqual(result['errors'], 1)
        self.assertEqual(result['users_processed'], 0)


class TestWindowDispatch(PGSTestMixin, TestCase):
    """Test _dispatch_for_window routes to correct generators."""

    def setUp(self):
        self.user = self.create_user()
        self.prefs = self.user.preferences

    @patch('apps.ai.proactive_checkins.generate_birthday_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_faith_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_medicine_check_ins_for_user')
    def test_morning_window(self, mock_med, mock_faith, mock_bday):
        """Hour 8 → medicine + birthday + faith generators."""
        from apps.ai.proactive_checkins import _dispatch_for_window

        self.prefs.faith_enabled = True
        self.prefs.save()

        count = _dispatch_for_window(self.user, self.prefs, 8, is_weekend=False)

        mock_med.assert_called_once_with(self.user)
        mock_bday.assert_called_once_with(self.user)
        mock_faith.assert_called_once_with(self.user)
        self.assertGreaterEqual(count, 3)

    @patch('apps.ai.proactive_checkins.generate_midday_alignment_for_user')
    @patch('apps.ai.proactive_checkins.generate_nn_skip_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_overdue_task_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_daily_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_medicine_check_ins_for_user')
    def test_midday_window(self, mock_med, mock_daily, mock_overdue, mock_nn, mock_midday):
        """Hour 11 → medicine + workout + overdue + nn_skip + midday_alignment."""
        from apps.ai.proactive_checkins import _dispatch_for_window

        count = _dispatch_for_window(self.user, self.prefs, 11, is_weekend=False)

        mock_med.assert_called_once_with(self.user)
        mock_daily.assert_called_once_with(self.user, 'workout')
        mock_overdue.assert_called_once_with(self.user)
        mock_nn.assert_called_once_with(self.user)
        mock_midday.assert_called_once_with(self.user)

    @patch('apps.ai.proactive_checkins.generate_afternoon_momentum_for_user')
    @patch('apps.ai.proactive_checkins.generate_finance_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_journal_intelligence_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_pattern_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_goal_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_medicine_check_ins_for_user')
    def test_afternoon_window(
        self, mock_med, mock_goal, mock_pattern, mock_journal, mock_finance, mock_momentum,
    ):
        """Hour 14 → medicine + goal + afternoon_momentum (weekday)."""
        from apps.ai.proactive_checkins import _dispatch_for_window

        count = _dispatch_for_window(self.user, self.prefs, 14, is_weekend=False)

        mock_med.assert_called_once_with(self.user)
        mock_goal.assert_called_once_with(self.user)
        mock_momentum.assert_called_once_with(self.user)

    @patch('apps.ai.proactive_checkins.generate_evening_wrap_for_user')
    @patch('apps.ai.proactive_checkins.generate_relationship_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_busy_day_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_daily_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_medicine_check_ins_for_user')
    def test_evening_window(self, mock_med, mock_daily, mock_busy, mock_rel, mock_wrap):
        """Hour 19 → medicine + journal + busy_day + relationship + evening_wrap."""
        from apps.ai.proactive_checkins import _dispatch_for_window

        count = _dispatch_for_window(self.user, self.prefs, 19, is_weekend=False)

        mock_med.assert_called_once_with(self.user)
        mock_daily.assert_called_once_with(self.user, 'journal')
        mock_busy.assert_called_once_with(self.user)
        mock_rel.assert_called_once_with(self.user)
        mock_wrap.assert_called_once_with(self.user)


class TestWeekendBehavior(PGSTestMixin, TestCase):
    """Test weekend-specific dispatch behavior."""

    def setUp(self):
        self.user = self.create_user()
        self.prefs = self.user.preferences

    @patch('apps.ai.proactive_checkins.generate_midday_alignment_for_user')
    @patch('apps.ai.proactive_checkins.generate_nn_skip_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_overdue_task_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_daily_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_medicine_check_ins_for_user')
    def test_midday_weekend_no_alignment(self, mock_med, mock_daily, mock_overdue, mock_nn, mock_midday):
        """Weekend midday: midday_alignment NOT called, others still called."""
        from apps.ai.proactive_checkins import _dispatch_for_window

        _dispatch_for_window(self.user, self.prefs, 11, is_weekend=True)

        mock_midday.assert_not_called()
        mock_overdue.assert_called_once()
        mock_nn.assert_called_once()

    @patch('apps.ai.proactive_checkins.generate_afternoon_momentum_for_user')
    @patch('apps.ai.proactive_checkins.generate_finance_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_journal_intelligence_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_pattern_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_goal_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_medicine_check_ins_for_user')
    def test_afternoon_weekend_no_momentum(
        self, mock_med, mock_goal, mock_pattern, mock_journal, mock_finance, mock_momentum,
    ):
        """Weekend afternoon: afternoon_momentum NOT called."""
        from apps.ai.proactive_checkins import _dispatch_for_window

        _dispatch_for_window(self.user, self.prefs, 14, is_weekend=True)

        mock_momentum.assert_not_called()
        mock_goal.assert_called_once()


class TestFeatureFlags(PGSTestMixin, TestCase):
    """Test feature flag gating."""

    def setUp(self):
        self.user = self.create_user()
        self.prefs = self.user.preferences

    @patch('apps.ai.proactive_checkins.generate_afternoon_momentum_for_user')
    @patch('apps.ai.proactive_checkins.generate_finance_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_journal_intelligence_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_pattern_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_goal_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_midday_alignment_for_user')
    @patch('apps.ai.proactive_checkins.generate_nn_skip_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_overdue_task_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_daily_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_medicine_check_ins_for_user')
    def test_health_disabled_skips_health_generators(
        self, mock_med, mock_daily, mock_overdue, mock_nn, mock_midday,
        mock_goal, mock_pattern, mock_journal_intel, mock_finance, mock_momentum,
    ):
        """health_enabled=False → medicine, workout, pattern skipped."""
        from apps.ai.proactive_checkins import _dispatch_for_window

        self.prefs.health_enabled = False
        self.prefs.save()

        # Midday window: medicine + workout should be skipped
        _dispatch_for_window(self.user, self.prefs, 11, is_weekend=False)
        mock_med.assert_not_called()
        mock_daily.assert_not_called()

        # Afternoon window: pattern should be skipped
        mock_med.reset_mock()
        _dispatch_for_window(self.user, self.prefs, 14, is_weekend=False)
        mock_pattern.assert_not_called()

    @patch('apps.ai.proactive_checkins.generate_faith_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_birthday_check_ins_for_user')
    @patch('apps.ai.proactive_checkins.generate_medicine_check_ins_for_user')
    def test_faith_disabled_skips_faith(self, mock_med, mock_bday, mock_faith):
        """faith_enabled=False → faith generator skipped in morning."""
        from apps.ai.proactive_checkins import _dispatch_for_window

        self.prefs.faith_enabled = False
        self.prefs.save()

        _dispatch_for_window(self.user, self.prefs, 8, is_weekend=False)
        mock_faith.assert_not_called()
        mock_bday.assert_called_once()  # birthday not gated by faith


class TestNewGenerators(PGSTestMixin, TestCase):
    """Test the three new daily rhythm generators."""

    def setUp(self):
        self.user = self.create_user()
        self.conv = AssistantConversation.objects.create(user=self.user)

    @patch('apps.core.utils.get_user_now')
    @patch('apps.core.utils.get_user_today')
    def test_midday_alignment_creates_message(self, mock_today, mock_now):
        """Midday alignment creates a proactive message with task counts."""
        from apps.ai.proactive_checkins import generate_midday_alignment_for_user
        from apps.life.models import Task

        today = date.today()
        mock_today.return_value = today
        mock_now.return_value = timezone.now()

        # Create tasks
        Task.objects.create(
            user=self.user, title='Done', due_date=today,
            completion_status='completed', completed_at=timezone.now(),
        )
        Task.objects.create(
            user=self.user, title='Pending', due_date=today,
            completion_status='pending',
        )

        with patch.object(
            type(self.user.preferences), 'assistant_proactive_checkins',
            new_callable=PropertyMock, return_value=True
        ):
            generate_midday_alignment_for_user(self.user)

        msg = AssistantMessage.objects.filter(
            conversation__user=self.user,
            is_proactive=True,
            metadata__check_in_type='midday_alignment',
        ).first()

        self.assertIsNotNone(msg)
        self.assertIn('1 done', msg.content)
        self.assertIn('1 remaining', msg.content)

    @patch('apps.core.utils.get_user_today')
    def test_midday_alignment_dedup(self, mock_today):
        """Second call on same day does nothing."""
        from apps.ai.proactive_checkins import generate_midday_alignment_for_user

        today = date.today()
        mock_today.return_value = today

        # Pre-create a message for today
        AssistantMessage.objects.create(
            conversation=self.conv,
            content='Already sent',
            is_proactive=True,
            metadata={'check_in_type': 'midday_alignment'},
        )

        with patch.object(
            type(self.user.preferences), 'assistant_proactive_checkins',
            new_callable=PropertyMock, return_value=True
        ):
            generate_midday_alignment_for_user(self.user)

        count = AssistantMessage.objects.filter(
            conversation__user=self.user,
            is_proactive=True,
            metadata__check_in_type='midday_alignment',
        ).count()
        self.assertEqual(count, 1)

    @patch('apps.core.utils.get_user_today')
    def test_midday_alignment_empty_data_skips(self, mock_today):
        """No tasks today → no message created."""
        from apps.ai.proactive_checkins import generate_midday_alignment_for_user

        mock_today.return_value = date.today()

        with patch.object(
            type(self.user.preferences), 'assistant_proactive_checkins',
            new_callable=PropertyMock, return_value=True
        ):
            generate_midday_alignment_for_user(self.user)

        self.assertFalse(
            AssistantMessage.objects.filter(
                conversation__user=self.user,
                is_proactive=True,
                metadata__check_in_type='midday_alignment',
            ).exists()
        )

    @patch('apps.core.utils.get_user_today')
    def test_afternoon_momentum_single_nn(self, mock_today):
        """Single non-negotiable pending → shows task title."""
        from apps.ai.proactive_checkins import generate_afternoon_momentum_for_user
        from apps.life.models import Task

        today = date.today()
        mock_today.return_value = today

        Task.objects.create(
            user=self.user, title='Bible Study', due_date=today,
            completion_status='pending', commitment_level='non_negotiable',
        )

        with patch.object(
            type(self.user.preferences), 'assistant_proactive_checkins',
            new_callable=PropertyMock, return_value=True
        ):
            generate_afternoon_momentum_for_user(self.user)

        msg = AssistantMessage.objects.filter(
            conversation__user=self.user,
            is_proactive=True,
            metadata__check_in_type='afternoon_momentum',
        ).first()

        self.assertIsNotNone(msg)
        self.assertIn('Bible Study', msg.content)

    @patch('apps.core.utils.get_user_today')
    def test_evening_wrap_shows_counts(self, mock_today):
        """Evening wrap shows completed, missed, and tomorrow counts."""
        from apps.ai.proactive_checkins import generate_evening_wrap_for_user
        from apps.life.models import Task

        today = date.today()
        tomorrow = today + timedelta(days=1)
        mock_today.return_value = today

        Task.objects.create(
            user=self.user, title='Done1', due_date=today,
            completion_status='completed', completed_at=timezone.now(),
        )
        Task.objects.create(
            user=self.user, title='Done2', due_date=today,
            completion_status='completed', completed_at=timezone.now(),
        )
        Task.objects.create(
            user=self.user, title='Missed', due_date=today,
            completion_status='pending',
        )
        Task.objects.create(
            user=self.user, title='Tomorrow', due_date=tomorrow,
            completion_status='pending',
        )

        with patch.object(
            type(self.user.preferences), 'assistant_proactive_checkins',
            new_callable=PropertyMock, return_value=True
        ):
            generate_evening_wrap_for_user(self.user)

        msg = AssistantMessage.objects.filter(
            conversation__user=self.user,
            is_proactive=True,
            metadata__check_in_type='evening_wrap',
        ).first()

        self.assertIsNotNone(msg)
        self.assertIn('2 tasks completed', msg.content)
        self.assertIn('1 still open', msg.content)
        self.assertIn('1 item tomorrow', msg.content)


class TestRegistration(TestCase):
    """Test PGS is properly registered in ISE and engine runtime."""

    def test_in_scheduled_tasks(self):
        """run_proactive_guidance appears in SCHEDULED_TASKS."""
        from apps.core.ai_scheduler.scheduler_registry import SCHEDULED_TASKS

        self.assertIn('run_proactive_guidance', SCHEDULED_TASKS)
        self.assertEqual(
            SCHEDULED_TASKS['run_proactive_guidance']['interval_seconds'],
            900,
        )

    def test_in_task_engine_map(self):
        """run_proactive_guidance maps to PGS engine code."""
        from apps.core.engine_runtime import TASK_ENGINE_MAP

        self.assertIn('run_proactive_guidance', TASK_ENGINE_MAP)
        self.assertEqual(TASK_ENGINE_MAP['run_proactive_guidance'], 'PGS')

    def test_in_engine_phase_map(self):
        """PGS is in Phase 2 (Execution)."""
        from apps.core.engine_runtime import ENGINE_PHASE_MAP

        self.assertIn('PGS', ENGINE_PHASE_MAP)
        self.assertEqual(ENGINE_PHASE_MAP['PGS'], 2)

    def test_function_path_importable(self):
        """The function_path is importable."""
        from apps.core.ai_scheduler.scheduler_registry import get_task_function

        fn = get_task_function('run_proactive_guidance')
        self.assertIsNotNone(fn)
        self.assertEqual(fn.__name__, 'run_proactive_guidance_scheduler')
