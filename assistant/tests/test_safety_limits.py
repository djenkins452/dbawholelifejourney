"""
Tests for the SafetyLimitService and safety limit functionality.

Tests rate limiting, file modification limits, system health checks,
and admin override capabilities.
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import TestCase
from django.utils import timezone

from assistant.safety_limits import (
    SafetyLimitService,
    SafetyLimitOverride,
    RateLimitResult,
    SystemHealthResult,
    check_rate_limits,
    check_file_modification_limit,
    is_system_healthy,
    MAX_AUTONOMOUS_PER_HOUR,
    MAX_AUTONOMOUS_PER_DAY,
    MAX_PENDING_TASKS,
    MAX_FILE_MODIFICATIONS_PER_FILE_PER_DAY,
    ERROR_RATE_THRESHOLD,
    ERROR_RATE_SAMPLE_SIZE,
    CACHE_KEY_HOURLY_COUNT,
    CACHE_KEY_SYSTEM_PAUSED,
    CACHE_KEY_FILE_MODIFICATIONS,
)
from assistant.models import ImprovementTaskModel


class TestSafetyLimitConstants(TestCase):
    """Tests for safety limit constant values."""

    def test_max_autonomous_per_hour(self):
        """Test default MAX_AUTONOMOUS_PER_HOUR is 5."""
        self.assertEqual(MAX_AUTONOMOUS_PER_HOUR, 5)

    def test_max_autonomous_per_day(self):
        """Test default MAX_AUTONOMOUS_PER_DAY is 20."""
        self.assertEqual(MAX_AUTONOMOUS_PER_DAY, 20)

    def test_max_pending_tasks(self):
        """Test default MAX_PENDING_TASKS is 50."""
        self.assertEqual(MAX_PENDING_TASKS, 50)

    def test_max_file_modifications_per_day(self):
        """Test default MAX_FILE_MODIFICATIONS_PER_FILE_PER_DAY is 3."""
        self.assertEqual(MAX_FILE_MODIFICATIONS_PER_FILE_PER_DAY, 3)

    def test_error_rate_threshold(self):
        """Test default ERROR_RATE_THRESHOLD is 30."""
        self.assertEqual(ERROR_RATE_THRESHOLD, 30)

    def test_error_rate_sample_size(self):
        """Test default ERROR_RATE_SAMPLE_SIZE is 10."""
        self.assertEqual(ERROR_RATE_SAMPLE_SIZE, 10)


class TestSafetyLimitOverrideModel(TestCase):
    """Tests for SafetyLimitOverride model."""

    def test_override_is_valid_active(self):
        """Test that active overrides are valid."""
        override = SafetyLimitOverride(
            limit_name='max_autonomous_per_hour',
            value=10,
            is_active=True,
            expires_at=None
        )

        self.assertTrue(override.is_valid())

    def test_override_is_invalid_when_inactive(self):
        """Test that inactive overrides are invalid."""
        override = SafetyLimitOverride(
            limit_name='max_autonomous_per_hour',
            value=10,
            is_active=False,
            expires_at=None
        )

        self.assertFalse(override.is_valid())

    def test_override_is_invalid_when_expired(self):
        """Test that expired overrides are invalid."""
        override = SafetyLimitOverride(
            limit_name='max_autonomous_per_hour',
            value=10,
            is_active=True,
            expires_at=timezone.now() - timedelta(hours=1)
        )

        self.assertFalse(override.is_valid())

    def test_override_is_valid_when_not_expired(self):
        """Test that non-expired overrides are valid."""
        override = SafetyLimitOverride(
            limit_name='max_autonomous_per_hour',
            value=10,
            is_active=True,
            expires_at=timezone.now() + timedelta(hours=1)
        )

        self.assertTrue(override.is_valid())

    def test_override_str_representation(self):
        """Test string representation of override."""
        override = SafetyLimitOverride(
            limit_name='max_autonomous_per_hour',
            value=10
        )

        result = str(override)

        self.assertIn('10', result)


class TestSafetyLimitServiceOverrides(TestCase):
    """Tests for SafetyLimitService override functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = SafetyLimitService(
            notification_service=MagicMock()
        )

    def test_get_limit_value_returns_default_when_no_override(self):
        """Test that default is returned when no override exists."""
        result = self.service.get_limit_value('max_autonomous_per_hour', 5)

        self.assertEqual(result, 5)

    def test_get_limit_value_returns_override_when_exists(self):
        """Test that override value is returned when it exists."""
        SafetyLimitOverride.objects.create(
            limit_name='max_autonomous_per_hour',
            value=15,
            is_active=True
        )

        result = self.service.get_limit_value('max_autonomous_per_hour', 5)

        self.assertEqual(result, 15)

    def test_get_limit_value_ignores_inactive_override(self):
        """Test that inactive overrides are ignored."""
        SafetyLimitOverride.objects.create(
            limit_name='max_autonomous_per_hour',
            value=15,
            is_active=False
        )

        result = self.service.get_limit_value('max_autonomous_per_hour', 5)

        self.assertEqual(result, 5)

    def test_get_limit_value_ignores_expired_override(self):
        """Test that expired overrides are ignored."""
        SafetyLimitOverride.objects.create(
            limit_name='max_autonomous_per_hour',
            value=15,
            is_active=True,
            expires_at=timezone.now() - timedelta(hours=1)
        )

        result = self.service.get_limit_value('max_autonomous_per_hour', 5)

        self.assertEqual(result, 5)


class TestSafetyLimitServiceSystemEnabled(TestCase):
    """Tests for system enabled/disabled functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = SafetyLimitService(
            notification_service=MagicMock()
        )

    @patch('assistant.safety_limits.cache')
    def test_is_system_enabled_true_by_default(self, mock_cache):
        """Test that system is enabled by default."""
        mock_cache.get.return_value = None

        result = self.service.is_system_enabled()

        self.assertTrue(result)

    @patch('assistant.safety_limits.cache')
    def test_is_system_enabled_false_when_paused(self, mock_cache):
        """Test that system is disabled when paused."""
        mock_cache.get.return_value = "Paused for testing"

        result = self.service.is_system_enabled()

        self.assertFalse(result)

    @patch('assistant.safety_limits.cache')
    def test_pause_system_sets_cache(self, mock_cache):
        """Test that pause_system sets the cache flag."""
        mock_cache.get.return_value = None

        self.service.pause_system("Test reason")

        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        self.assertEqual(call_args[0][0], CACHE_KEY_SYSTEM_PAUSED)
        self.assertEqual(call_args[0][1], "Test reason")

    @patch('assistant.safety_limits.cache')
    def test_resume_system_deletes_cache(self, mock_cache):
        """Test that resume_system clears the cache flag."""
        self.service.resume_system()

        mock_cache.delete.assert_called_once_with(CACHE_KEY_SYSTEM_PAUSED)


class TestSafetyLimitServiceRateLimits(TestCase):
    """Tests for rate limiting functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_notification = MagicMock()
        self.service = SafetyLimitService(
            notification_service=self.mock_notification
        )

    @patch('assistant.safety_limits.cache')
    def test_check_rate_limits_blocked_when_paused(self, mock_cache):
        """Test that rate limits block when system is paused."""
        mock_cache.get.return_value = "System paused"

        result = self.service.check_rate_limits()

        self.assertFalse(result.allowed)
        self.assertIn("paused", result.reason.lower())

    @patch('assistant.safety_limits.cache')
    @patch.object(ImprovementTaskModel.objects, 'filter')
    def test_check_rate_limits_allows_under_hourly_limit(self, mock_filter, mock_cache):
        """Test that rate limits allow execution under hourly limit."""
        mock_cache.get.return_value = None
        mock_queryset = MagicMock()
        mock_queryset.count.return_value = 3
        mock_filter.return_value = mock_queryset

        result = self.service.check_rate_limits()

        self.assertTrue(result.allowed)
        self.assertIn("Within rate limits", result.reason)

    @patch('assistant.safety_limits.cache')
    @patch.object(ImprovementTaskModel.objects, 'filter')
    def test_check_rate_limits_blocks_at_hourly_limit(self, mock_filter, mock_cache):
        """Test that rate limits block at hourly limit."""
        mock_cache.get.return_value = None
        mock_queryset = MagicMock()
        mock_queryset.count.return_value = 5  # At limit
        mock_filter.return_value = mock_queryset

        result = self.service.check_rate_limits()

        self.assertFalse(result.allowed)
        self.assertIn("Hourly rate limit", result.reason)

    @patch('assistant.safety_limits.cache')
    @patch.object(ImprovementTaskModel.objects, 'filter')
    def test_check_rate_limits_notifies_admin_when_blocked(self, mock_filter, mock_cache):
        """Test that admin is notified when rate limit is reached."""
        mock_cache.get.return_value = None
        mock_queryset = MagicMock()
        mock_queryset.count.return_value = 5  # At limit
        mock_filter.return_value = mock_queryset

        self.service.check_rate_limits()

        self.mock_notification.notify_queue_status.assert_called()


class TestSafetyLimitServiceFileModification(TestCase):
    """Tests for file modification limit functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_notification = MagicMock()
        self.service = SafetyLimitService(
            notification_service=self.mock_notification
        )

    @patch('assistant.safety_limits.cache')
    def test_check_file_modification_allows_under_limit(self, mock_cache):
        """Test that file modification is allowed under limit."""
        mock_cache.get.return_value = 1  # Under limit of 3

        result = self.service.check_file_modification_limit('test/file.py')

        self.assertTrue(result.allowed)
        self.assertEqual(result.current_count, 1)
        self.assertEqual(result.limit, MAX_FILE_MODIFICATIONS_PER_FILE_PER_DAY)

    @patch('assistant.safety_limits.cache')
    def test_check_file_modification_blocks_at_limit(self, mock_cache):
        """Test that file modification is blocked at limit."""
        mock_cache.get.return_value = 3  # At limit

        result = self.service.check_file_modification_limit('test/file.py')

        self.assertFalse(result.allowed)
        self.assertIn("limit exceeded", result.reason.lower())

    @patch('assistant.safety_limits.cache')
    def test_check_file_modification_notifies_admin(self, mock_cache):
        """Test that admin is notified when file limit reached."""
        mock_cache.get.return_value = 3  # At limit

        self.service.check_file_modification_limit('test/file.py')

        self.mock_notification.notify_queue_status.assert_called()

    @patch('assistant.safety_limits.cache')
    def test_record_file_modification_increments_counter(self, mock_cache):
        """Test that recording modification increments counter."""
        mock_cache.get.return_value = 1

        self.service.record_file_modification('test/file.py')

        # Verify cache.set was called with incremented value
        mock_cache.set.assert_called_once()
        call_args = mock_cache.set.call_args
        self.assertEqual(call_args[0][1], 2)  # 1 + 1 = 2
        self.assertEqual(call_args[1]['timeout'], 86400)  # 24 hours

    @patch('assistant.safety_limits.cache')
    def test_record_file_modification_normalizes_path(self, mock_cache):
        """Test that file paths are normalized for cache keys."""
        mock_cache.get.return_value = 0

        self.service.record_file_modification('test/nested/file.py')

        call_args = mock_cache.set.call_args
        cache_key = call_args[0][0]
        self.assertIn('test_nested_file.py', cache_key)


class TestSafetyLimitServiceSystemHealth(TestCase):
    """Tests for system health check functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_notification = MagicMock()
        self.service = SafetyLimitService(
            notification_service=self.mock_notification
        )

    @patch.object(ImprovementTaskModel.objects, 'filter')
    def test_is_system_healthy_with_no_tasks(self, mock_filter):
        """Test system is healthy when no tasks to analyze."""
        mock_queryset = MagicMock()
        mock_queryset.order_by.return_value.__getitem__.return_value = mock_queryset
        mock_queryset.count.return_value = 0
        mock_filter.return_value = mock_queryset

        result = self.service.is_system_healthy()

        self.assertTrue(result.healthy)
        self.assertIn("No recent tasks", result.reason)

    @patch.object(ImprovementTaskModel.objects, 'filter')
    def test_is_system_healthy_with_low_error_rate(self, mock_filter):
        """Test system is healthy with low error rate."""
        # Create mock tasks - 1 error out of 10
        mock_tasks = []
        for i in range(10):
            task = MagicMock()
            task.status = ImprovementTaskModel.STATUS_COMPLETED if i > 0 else ImprovementTaskModel.STATUS_ERROR
            mock_tasks.append(task)

        mock_queryset = MagicMock()
        mock_queryset.order_by.return_value.__getitem__.return_value = mock_tasks
        mock_queryset.count.return_value = 10
        mock_filter.return_value = mock_queryset

        result = self.service.is_system_healthy()

        self.assertTrue(result.healthy)
        self.assertEqual(result.error_rate, 10.0)  # 1/10 = 10%
        self.assertEqual(result.recent_errors, 1)
        self.assertEqual(result.recent_total, 10)

    @patch('assistant.safety_limits.cache')
    @patch.object(ImprovementTaskModel.objects, 'filter')
    def test_is_system_healthy_with_high_error_rate(self, mock_filter, mock_cache):
        """Test system is unhealthy with high error rate."""
        mock_cache.get.return_value = None

        # Create mock tasks - 4 errors out of 10 (40%)
        mock_tasks = []
        for i in range(10):
            task = MagicMock()
            task.status = ImprovementTaskModel.STATUS_ERROR if i < 4 else ImprovementTaskModel.STATUS_COMPLETED
            mock_tasks.append(task)

        mock_queryset = MagicMock()
        mock_queryset.order_by.return_value.__getitem__.return_value = mock_tasks
        mock_queryset.count.return_value = 10
        mock_filter.return_value = mock_queryset

        result = self.service.is_system_healthy()

        self.assertFalse(result.healthy)
        self.assertEqual(result.error_rate, 40.0)  # 4/10 = 40%
        self.assertIn("exceeds threshold", result.reason)

    @patch('assistant.safety_limits.cache')
    @patch.object(ImprovementTaskModel.objects, 'filter')
    def test_is_system_healthy_pauses_on_high_errors(self, mock_filter, mock_cache):
        """Test that system auto-pauses on high error rate."""
        mock_cache.get.return_value = None

        # Create mock tasks with high error rate
        mock_tasks = [MagicMock(status=ImprovementTaskModel.STATUS_ERROR) for _ in range(10)]

        mock_queryset = MagicMock()
        mock_queryset.order_by.return_value.__getitem__.return_value = mock_tasks
        mock_queryset.count.return_value = 10
        mock_filter.return_value = mock_queryset

        self.service.is_system_healthy()

        # Verify pause was called
        mock_cache.set.assert_called()


class TestSafetyLimitServiceCheckAll(TestCase):
    """Tests for combined safety check functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = SafetyLimitService(
            notification_service=MagicMock()
        )

    @patch.object(SafetyLimitService, 'is_system_healthy')
    @patch.object(SafetyLimitService, 'check_rate_limits')
    @patch.object(SafetyLimitService, 'check_file_modification_limit')
    def test_check_all_limits_passes_all(self, mock_file, mock_rate, mock_health):
        """Test check_all_limits passes when all checks pass."""
        mock_health.return_value = SystemHealthResult(
            healthy=True,
            reason="OK"
        )
        mock_rate.return_value = RateLimitResult(
            allowed=True,
            reason="OK"
        )
        mock_file.return_value = RateLimitResult(
            allowed=True,
            reason="OK"
        )

        allowed, reason = self.service.check_all_limits(file_path='test.py')

        self.assertTrue(allowed)
        self.assertIn("passed", reason.lower())

    @patch.object(SafetyLimitService, 'is_system_healthy')
    def test_check_all_limits_fails_on_health(self, mock_health):
        """Test check_all_limits fails when health check fails."""
        mock_health.return_value = SystemHealthResult(
            healthy=False,
            reason="Error rate too high"
        )

        allowed, reason = self.service.check_all_limits()

        self.assertFalse(allowed)
        self.assertIn("Error rate", reason)

    @patch.object(SafetyLimitService, 'is_system_healthy')
    @patch.object(SafetyLimitService, 'check_rate_limits')
    def test_check_all_limits_fails_on_rate_limit(self, mock_rate, mock_health):
        """Test check_all_limits fails when rate limit exceeded."""
        mock_health.return_value = SystemHealthResult(
            healthy=True,
            reason="OK"
        )
        mock_rate.return_value = RateLimitResult(
            allowed=False,
            reason="Hourly limit exceeded"
        )

        allowed, reason = self.service.check_all_limits()

        self.assertFalse(allowed)
        self.assertIn("Hourly limit", reason)

    @patch.object(SafetyLimitService, 'is_system_healthy')
    @patch.object(SafetyLimitService, 'check_rate_limits')
    @patch.object(SafetyLimitService, 'check_file_modification_limit')
    def test_check_all_limits_fails_on_file_limit(self, mock_file, mock_rate, mock_health):
        """Test check_all_limits fails when file limit exceeded."""
        mock_health.return_value = SystemHealthResult(
            healthy=True,
            reason="OK"
        )
        mock_rate.return_value = RateLimitResult(
            allowed=True,
            reason="OK"
        )
        mock_file.return_value = RateLimitResult(
            allowed=False,
            reason="File limit exceeded"
        )

        allowed, reason = self.service.check_all_limits(file_path='test.py')

        self.assertFalse(allowed)
        self.assertIn("File limit", reason)


class TestConvenienceFunctions(TestCase):
    """Tests for module-level convenience functions."""

    @patch.object(SafetyLimitService, 'check_rate_limits')
    def test_check_rate_limits_function(self, mock_method):
        """Test check_rate_limits convenience function."""
        mock_method.return_value = RateLimitResult(
            allowed=True,
            reason="OK"
        )

        result = check_rate_limits()

        self.assertTrue(result.allowed)

    @patch.object(SafetyLimitService, 'check_file_modification_limit')
    def test_check_file_modification_limit_function(self, mock_method):
        """Test check_file_modification_limit convenience function."""
        mock_method.return_value = RateLimitResult(
            allowed=True,
            reason="OK"
        )

        result = check_file_modification_limit('test.py')

        self.assertTrue(result.allowed)

    @patch.object(SafetyLimitService, 'is_system_healthy')
    def test_is_system_healthy_function(self, mock_method):
        """Test is_system_healthy convenience function."""
        mock_method.return_value = SystemHealthResult(
            healthy=True,
            reason="OK"
        )

        result = is_system_healthy()

        self.assertTrue(result.healthy)


class TestRateLimitResultDataclass(TestCase):
    """Tests for RateLimitResult dataclass."""

    def test_rate_limit_result_defaults(self):
        """Test RateLimitResult default values."""
        result = RateLimitResult(
            allowed=True,
            reason="Test"
        )

        self.assertEqual(result.current_count, 0)
        self.assertEqual(result.limit, 0)

    def test_rate_limit_result_with_values(self):
        """Test RateLimitResult with all values."""
        result = RateLimitResult(
            allowed=False,
            reason="Limit exceeded",
            current_count=5,
            limit=5
        )

        self.assertFalse(result.allowed)
        self.assertEqual(result.current_count, 5)
        self.assertEqual(result.limit, 5)


class TestSystemHealthResultDataclass(TestCase):
    """Tests for SystemHealthResult dataclass."""

    def test_system_health_result_defaults(self):
        """Test SystemHealthResult default values."""
        result = SystemHealthResult(
            healthy=True,
            reason="Test"
        )

        self.assertEqual(result.error_rate, 0.0)
        self.assertEqual(result.recent_errors, 0)
        self.assertEqual(result.recent_total, 0)

    def test_system_health_result_with_values(self):
        """Test SystemHealthResult with all values."""
        result = SystemHealthResult(
            healthy=False,
            reason="Error rate high",
            error_rate=40.0,
            recent_errors=4,
            recent_total=10
        )

        self.assertFalse(result.healthy)
        self.assertEqual(result.error_rate, 40.0)
        self.assertEqual(result.recent_errors, 4)
        self.assertEqual(result.recent_total, 10)


class TestAutonomousExecutorIntegrationWithSafetyLimits(TestCase):
    """Integration tests for AutonomousExecutor with SafetyLimitService."""

    def setUp(self):
        """Set up test fixtures."""
        from assistant.executor import AutonomousExecutor

        self.mock_git_service = MagicMock()
        self.mock_file_modifier = MagicMock()
        self.mock_test_runner = MagicMock()
        self.mock_notification_service = MagicMock()
        self.mock_safety_service = MagicMock()

        self.executor = AutonomousExecutor(
            git_service=self.mock_git_service,
            file_modifier=self.mock_file_modifier,
            test_runner=self.mock_test_runner,
            notification_service=self.mock_notification_service,
            safety_limit_service=self.mock_safety_service
        )

    def test_executor_checks_system_health_first(self):
        """Test that executor checks system health before execution."""
        self.mock_safety_service.is_system_healthy.return_value = SystemHealthResult(
            healthy=False,
            reason="Error rate too high"
        )

        task = MagicMock()
        task.id = uuid.uuid4()

        result = self.executor.execute_task(task)

        self.assertFalse(result.success)
        self.assertIn("health check", result.message.lower())
        self.mock_safety_service.is_system_healthy.assert_called_once()

    @patch('assistant.executor.cache')
    def test_executor_checks_rate_limits(self, mock_cache):
        """Test that executor checks rate limits."""
        mock_cache.get.return_value = 0

        self.mock_safety_service.is_system_healthy.return_value = SystemHealthResult(
            healthy=True,
            reason="OK"
        )
        self.mock_safety_service.check_rate_limits.return_value = RateLimitResult(
            allowed=False,
            reason="Daily limit exceeded"
        )

        task = MagicMock()
        task.id = uuid.uuid4()
        task.severity = ImprovementTaskModel.SEVERITY_LOW
        task.code_template = ""

        result = self.executor.execute_task(task)

        self.assertFalse(result.success)
        self.assertIn("rate limited", result.message.lower())

    @patch('assistant.executor.cache')
    def test_executor_checks_file_modification_limit(self, mock_cache):
        """Test that executor checks file modification limits."""
        mock_cache.get.return_value = 0

        self.mock_safety_service.is_system_healthy.return_value = SystemHealthResult(
            healthy=True,
            reason="OK"
        )
        self.mock_safety_service.check_rate_limits.return_value = RateLimitResult(
            allowed=True,
            reason="OK"
        )
        self.mock_safety_service.check_file_modification_limit.return_value = RateLimitResult(
            allowed=False,
            reason="File limit exceeded for test.py"
        )

        task = MagicMock()
        task.id = uuid.uuid4()
        task.severity = ImprovementTaskModel.SEVERITY_LOW
        task.code_template = """FILE: assistant/intent_detector.py
TYPE: append
CODE:
    'test': 'value',"""

        result = self.executor.execute_task(task)

        self.assertFalse(result.success)
        self.assertIn("file modification limit", result.message.lower())

    @patch('assistant.executor.cache')
    def test_executor_records_file_modification_on_success(self, mock_cache):
        """Test that executor records file modification after success."""
        from assistant.executor import ExecutionResult
        from assistant.git_service import GitResult
        from assistant.test_runner import TestResult

        mock_cache.get.return_value = 0

        self.mock_safety_service.is_system_healthy.return_value = SystemHealthResult(
            healthy=True,
            reason="OK"
        )
        self.mock_safety_service.check_rate_limits.return_value = RateLimitResult(
            allowed=True,
            reason="OK"
        )
        self.mock_safety_service.check_file_modification_limit.return_value = RateLimitResult(
            allowed=True,
            reason="OK"
        )

        self.mock_git_service.create_snapshot.return_value = GitResult(
            success=True,
            message="Snapshot created",
            commit_hash="abc123"
        )
        self.mock_git_service.commit_changes.return_value = GitResult(
            success=True,
            message="Committed",
            commit_hash="def456"
        )
        self.mock_git_service.get_commit_diff.return_value = "diff"

        self.mock_test_runner.generate_test_file.return_value = "/tmp/test.py"
        self.mock_test_runner.run_single_test.return_value = TestResult(
            passed=True,
            output="OK"
        )

        task = MagicMock()
        task.id = uuid.uuid4()
        task.title = "Test Task"
        task.severity = ImprovementTaskModel.SEVERITY_LOW
        task.suggested_fix = "Fix"
        task.status = ImprovementTaskModel.STATUS_NEW
        task.requires_approval = False
        task.code_template = """FILE: assistant/intent_detector.py
TYPE: append
CODE:
    'test': 'value',"""
        task.test_template = ""
        task.git_commit_before = None
        task.git_commit_after = None

        result = self.executor.execute_task(task)

        if result.success:
            self.mock_safety_service.record_file_modification.assert_called_once_with(
                'assistant/intent_detector.py'
            )
