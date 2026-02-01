"""
Tests for the HealthMonitor system health monitoring service.

Tests health check functionality, rate calculations, status determination,
and automatic actions based on health status.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from assistant.health_monitor import (
    HealthMonitor,
    HealthCheckResult,
    RateMetrics,
    SystemStatus,
    get_system_status,
    get_status_report,
    run_health_check,
    ERROR_RATE_DEGRADED_THRESHOLD,
    ERROR_RATE_CRITICAL_THRESHOLD,
    ROLLBACK_RATE_DEGRADED_THRESHOLD,
    ROLLBACK_RATE_CRITICAL_THRESHOLD,
    CONSECUTIVE_FAILURE_THRESHOLD,
    CACHE_KEY_HEALTH_STATUS,
    CACHE_KEY_LAST_HEALTH_CHECK,
)
from assistant.models import ImprovementTaskModel


class TestHealthMonitorConstants(TestCase):
    """Tests for health monitor constant values."""

    def test_error_rate_degraded_threshold(self):
        """Test default ERROR_RATE_DEGRADED_THRESHOLD is 20."""
        self.assertEqual(ERROR_RATE_DEGRADED_THRESHOLD, 20)

    def test_error_rate_critical_threshold(self):
        """Test default ERROR_RATE_CRITICAL_THRESHOLD is 40."""
        self.assertEqual(ERROR_RATE_CRITICAL_THRESHOLD, 40)

    def test_rollback_rate_degraded_threshold(self):
        """Test default ROLLBACK_RATE_DEGRADED_THRESHOLD is 15."""
        self.assertEqual(ROLLBACK_RATE_DEGRADED_THRESHOLD, 15)

    def test_rollback_rate_critical_threshold(self):
        """Test default ROLLBACK_RATE_CRITICAL_THRESHOLD is 30."""
        self.assertEqual(ROLLBACK_RATE_CRITICAL_THRESHOLD, 30)

    def test_consecutive_failure_threshold(self):
        """Test default CONSECUTIVE_FAILURE_THRESHOLD is 5."""
        self.assertEqual(CONSECUTIVE_FAILURE_THRESHOLD, 5)


class TestSystemStatusEnum(TestCase):
    """Tests for SystemStatus enum."""

    def test_healthy_status(self):
        """Test HEALTHY status value."""
        self.assertEqual(SystemStatus.HEALTHY.value, 'healthy')

    def test_degraded_status(self):
        """Test DEGRADED status value."""
        self.assertEqual(SystemStatus.DEGRADED.value, 'degraded')

    def test_critical_status(self):
        """Test CRITICAL status value."""
        self.assertEqual(SystemStatus.CRITICAL.value, 'critical')


class TestHealthCheckResult(TestCase):
    """Tests for HealthCheckResult dataclass."""

    def test_default_values(self):
        """Test default values for HealthCheckResult."""
        result = HealthCheckResult(
            status=SystemStatus.HEALTHY,
            reason="Test"
        )

        self.assertEqual(result.error_rate, 0.0)
        self.assertEqual(result.rollback_rate, 0.0)
        self.assertEqual(result.consecutive_failures, 0)
        self.assertIsNone(result.details)

    def test_with_all_values(self):
        """Test HealthCheckResult with all values."""
        result = HealthCheckResult(
            status=SystemStatus.DEGRADED,
            reason="Test reason",
            error_rate=25.0,
            rollback_rate=10.0,
            consecutive_failures=3,
            details={'key': 'value'}
        )

        self.assertEqual(result.status, SystemStatus.DEGRADED)
        self.assertEqual(result.error_rate, 25.0)
        self.assertEqual(result.rollback_rate, 10.0)
        self.assertEqual(result.consecutive_failures, 3)
        self.assertEqual(result.details, {'key': 'value'})


class TestRateMetrics(TestCase):
    """Tests for RateMetrics dataclass."""

    def test_rate_metrics_creation(self):
        """Test RateMetrics creation."""
        metrics = RateMetrics(
            total_count=100,
            error_count=20,
            rollback_count=5,
            completed_count=75,
            error_rate=20.0,
            rollback_rate=6.25,
            consecutive_failures=2
        )

        self.assertEqual(metrics.total_count, 100)
        self.assertEqual(metrics.error_count, 20)
        self.assertEqual(metrics.rollback_count, 5)
        self.assertEqual(metrics.completed_count, 75)
        self.assertEqual(metrics.error_rate, 20.0)
        self.assertEqual(metrics.rollback_rate, 6.25)
        self.assertEqual(metrics.consecutive_failures, 2)


class TestHealthMonitorRateCalculation(TestCase):
    """Tests for HealthMonitor rate calculation methods."""

    def setUp(self):
        """Set up test fixtures."""
        self.monitor = HealthMonitor(
            notification_service=MagicMock(),
            safety_limit_service=MagicMock()
        )

    @patch.object(ImprovementTaskModel.objects, 'filter')
    def test_get_rate_metrics_no_tasks(self, mock_filter):
        """Test rate metrics with no tasks."""
        mock_queryset = MagicMock()
        mock_queryset.order_by.return_value = mock_queryset
        mock_queryset.count.return_value = 0
        mock_filter.return_value = mock_queryset

        metrics = self.monitor._get_rate_metrics()

        self.assertEqual(metrics.total_count, 0)
        self.assertEqual(metrics.error_rate, 0.0)
        self.assertEqual(metrics.rollback_rate, 0.0)

    @patch.object(ImprovementTaskModel.objects, 'filter')
    def test_get_rate_metrics_with_errors(self, mock_filter):
        """Test rate metrics calculation with some errors."""
        # Create mock querysets that return proper int values for count()
        mock_error_qs = MagicMock()
        mock_error_qs.count.return_value = 3

        mock_rollback_qs = MagicMock()
        mock_rollback_qs.count.return_value = 1

        mock_completed_qs = MagicMock()
        mock_completed_qs.count.return_value = 6

        # The recent_tasks queryset - it needs to support chained .filter().count()
        mock_recent_tasks = MagicMock()
        mock_recent_tasks.count.return_value = 10

        def recent_filter_side_effect(**kwargs):
            status = kwargs.get('status')
            if status == ImprovementTaskModel.STATUS_ERROR:
                return mock_error_qs
            elif status == ImprovementTaskModel.STATUS_ROLLED_BACK:
                return mock_rollback_qs
            elif status == ImprovementTaskModel.STATUS_COMPLETED:
                return mock_completed_qs
            return MagicMock(count=MagicMock(return_value=0))

        mock_recent_tasks.filter.side_effect = recent_filter_side_effect

        # The initial filter returns a queryset with order_by
        mock_initial_qs = MagicMock()
        mock_initial_qs.order_by.return_value = mock_recent_tasks

        mock_filter.return_value = mock_initial_qs

        # Patch _count_consecutive_failures to return 0
        with patch.object(self.monitor, '_count_consecutive_failures', return_value=0):
            metrics = self.monitor._get_rate_metrics()

        self.assertEqual(metrics.total_count, 10)
        self.assertEqual(metrics.error_count, 3)
        self.assertEqual(metrics.rollback_count, 1)
        self.assertEqual(metrics.completed_count, 6)


class TestHealthMonitorErrorRateCheck(TestCase):
    """Tests for error rate checking functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.monitor = HealthMonitor(
            notification_service=MagicMock(),
            safety_limit_service=MagicMock()
        )

    def test_check_error_rate_healthy(self):
        """Test error rate check when healthy."""
        with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
            mock_metrics.return_value = RateMetrics(
                total_count=100,
                error_count=10,
                rollback_count=0,
                completed_count=90,
                error_rate=10.0,
                rollback_rate=0.0,
                consecutive_failures=0
            )

            result = self.monitor.check_error_rate()

            self.assertEqual(result.status, SystemStatus.HEALTHY)
            self.assertIn("OK", result.reason)

    def test_check_error_rate_degraded(self):
        """Test error rate check when degraded (20-40%)."""
        with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
            mock_metrics.return_value = RateMetrics(
                total_count=100,
                error_count=25,
                rollback_count=0,
                completed_count=75,
                error_rate=25.0,
                rollback_rate=0.0,
                consecutive_failures=0
            )

            result = self.monitor.check_error_rate()

            self.assertEqual(result.status, SystemStatus.DEGRADED)
            self.assertIn("Elevated", result.reason)

    def test_check_error_rate_critical(self):
        """Test error rate check when critical (>40%)."""
        with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
            mock_metrics.return_value = RateMetrics(
                total_count=100,
                error_count=45,
                rollback_count=0,
                completed_count=55,
                error_rate=45.0,
                rollback_rate=0.0,
                consecutive_failures=0
            )

            result = self.monitor.check_error_rate()

            self.assertEqual(result.status, SystemStatus.CRITICAL)
            self.assertIn("Critical", result.reason)


class TestHealthMonitorRollbackRateCheck(TestCase):
    """Tests for rollback rate checking functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.monitor = HealthMonitor(
            notification_service=MagicMock(),
            safety_limit_service=MagicMock()
        )

    def test_check_rollback_rate_healthy(self):
        """Test rollback rate check when healthy."""
        with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
            mock_metrics.return_value = RateMetrics(
                total_count=100,
                error_count=0,
                rollback_count=5,
                completed_count=95,
                error_rate=0.0,
                rollback_rate=5.0,
                consecutive_failures=0
            )

            result = self.monitor.check_rollback_rate()

            self.assertEqual(result.status, SystemStatus.HEALTHY)
            self.assertIn("OK", result.reason)

    def test_check_rollback_rate_degraded(self):
        """Test rollback rate check when degraded (15-30%)."""
        with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
            mock_metrics.return_value = RateMetrics(
                total_count=100,
                error_count=0,
                rollback_count=20,
                completed_count=80,
                error_rate=0.0,
                rollback_rate=20.0,
                consecutive_failures=0
            )

            result = self.monitor.check_rollback_rate()

            self.assertEqual(result.status, SystemStatus.DEGRADED)
            self.assertIn("Elevated", result.reason)

    def test_check_rollback_rate_critical(self):
        """Test rollback rate check when critical (>30%)."""
        with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
            mock_metrics.return_value = RateMetrics(
                total_count=100,
                error_count=0,
                rollback_count=35,
                completed_count=65,
                error_rate=0.0,
                rollback_rate=35.0,
                consecutive_failures=0
            )

            result = self.monitor.check_rollback_rate()

            self.assertEqual(result.status, SystemStatus.CRITICAL)
            self.assertIn("Critical", result.reason)


class TestHealthMonitorResponseRateCheck(TestCase):
    """Tests for assistant response rate checking functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.monitor = HealthMonitor(
            notification_service=MagicMock(),
            safety_limit_service=MagicMock()
        )

    def test_check_response_rate_healthy(self):
        """Test response rate check when healthy."""
        with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
            mock_metrics.return_value = RateMetrics(
                total_count=100,
                error_count=5,
                rollback_count=2,
                completed_count=93,
                error_rate=5.0,
                rollback_rate=2.0,
                consecutive_failures=0
            )

            with patch.object(ImprovementTaskModel.objects, 'filter') as mock_filter:
                mock_queryset = MagicMock()
                mock_queryset.count.return_value = 0
                mock_filter.return_value = mock_queryset

                result = self.monitor.check_assistant_response_rate()

                self.assertEqual(result.status, SystemStatus.HEALTHY)

    def test_check_response_rate_critical_consecutive_failures(self):
        """Test response rate critical with many consecutive failures."""
        with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
            mock_metrics.return_value = RateMetrics(
                total_count=100,
                error_count=20,
                rollback_count=0,
                completed_count=80,
                error_rate=20.0,
                rollback_rate=0.0,
                consecutive_failures=6  # Over threshold
            )

            with patch.object(ImprovementTaskModel.objects, 'filter') as mock_filter:
                mock_queryset = MagicMock()
                mock_queryset.count.return_value = 0
                mock_filter.return_value = mock_queryset

                result = self.monitor.check_assistant_response_rate()

                self.assertEqual(result.status, SystemStatus.CRITICAL)
                self.assertIn("consecutive", result.reason.lower())


class TestHealthMonitorGetSystemStatus(TestCase):
    """Tests for overall system status determination."""

    def setUp(self):
        """Set up test fixtures."""
        self.monitor = HealthMonitor(
            notification_service=MagicMock(),
            safety_limit_service=MagicMock()
        )

    @patch('assistant.health_monitor.cache')
    def test_get_system_status_all_healthy(self, mock_cache):
        """Test system status when all checks are healthy."""
        mock_cache.set = MagicMock()

        with patch.object(self.monitor, 'check_error_rate') as mock_error:
            with patch.object(self.monitor, 'check_rollback_rate') as mock_rollback:
                with patch.object(self.monitor, 'check_assistant_response_rate') as mock_response:
                    with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
                        mock_error.return_value = HealthCheckResult(
                            status=SystemStatus.HEALTHY,
                            reason="OK"
                        )
                        mock_rollback.return_value = HealthCheckResult(
                            status=SystemStatus.HEALTHY,
                            reason="OK"
                        )
                        mock_response.return_value = HealthCheckResult(
                            status=SystemStatus.HEALTHY,
                            reason="OK"
                        )
                        mock_metrics.return_value = RateMetrics(
                            total_count=100,
                            error_count=5,
                            rollback_count=2,
                            completed_count=93,
                            error_rate=5.0,
                            rollback_rate=2.0,
                            consecutive_failures=0
                        )

                        result = self.monitor.get_system_status()

                        self.assertEqual(result.status, SystemStatus.HEALTHY)
                        self.assertIn("passed", result.reason.lower())

    @patch('assistant.health_monitor.cache')
    def test_get_system_status_one_degraded(self, mock_cache):
        """Test system status when one check is degraded."""
        mock_cache.set = MagicMock()

        with patch.object(self.monitor, 'check_error_rate') as mock_error:
            with patch.object(self.monitor, 'check_rollback_rate') as mock_rollback:
                with patch.object(self.monitor, 'check_assistant_response_rate') as mock_response:
                    with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
                        mock_error.return_value = HealthCheckResult(
                            status=SystemStatus.DEGRADED,
                            reason="Elevated error rate"
                        )
                        mock_rollback.return_value = HealthCheckResult(
                            status=SystemStatus.HEALTHY,
                            reason="OK"
                        )
                        mock_response.return_value = HealthCheckResult(
                            status=SystemStatus.HEALTHY,
                            reason="OK"
                        )
                        mock_metrics.return_value = RateMetrics(
                            total_count=100,
                            error_count=25,
                            rollback_count=2,
                            completed_count=73,
                            error_rate=25.0,
                            rollback_rate=2.0,
                            consecutive_failures=0
                        )

                        result = self.monitor.get_system_status()

                        self.assertEqual(result.status, SystemStatus.DEGRADED)
                        self.assertIn("DEGRADED", result.reason)

    @patch('assistant.health_monitor.cache')
    def test_get_system_status_critical_overrides_degraded(self, mock_cache):
        """Test that critical status overrides degraded."""
        mock_cache.set = MagicMock()

        with patch.object(self.monitor, 'check_error_rate') as mock_error:
            with patch.object(self.monitor, 'check_rollback_rate') as mock_rollback:
                with patch.object(self.monitor, 'check_assistant_response_rate') as mock_response:
                    with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
                        mock_error.return_value = HealthCheckResult(
                            status=SystemStatus.DEGRADED,
                            reason="Elevated error rate"
                        )
                        mock_rollback.return_value = HealthCheckResult(
                            status=SystemStatus.CRITICAL,
                            reason="Critical rollback rate"
                        )
                        mock_response.return_value = HealthCheckResult(
                            status=SystemStatus.HEALTHY,
                            reason="OK"
                        )
                        mock_metrics.return_value = RateMetrics(
                            total_count=100,
                            error_count=25,
                            rollback_count=40,
                            completed_count=35,
                            error_rate=25.0,
                            rollback_rate=53.0,
                            consecutive_failures=0
                        )

                        result = self.monitor.get_system_status()

                        self.assertEqual(result.status, SystemStatus.CRITICAL)
                        self.assertIn("CRITICAL", result.reason)


class TestHealthMonitorHandleStatus(TestCase):
    """Tests for status handling actions."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_notification = MagicMock()
        self.mock_safety = MagicMock()
        self.monitor = HealthMonitor(
            notification_service=self.mock_notification,
            safety_limit_service=self.mock_safety
        )

    def test_handle_healthy_status(self):
        """Test handling healthy status (no action)."""
        result = HealthCheckResult(
            status=SystemStatus.HEALTHY,
            reason="All healthy"
        )

        actions = self.monitor.handle_status(result)

        self.assertEqual(actions['status'], 'healthy')
        self.assertFalse(actions['notifications_sent'])
        self.mock_safety.pause_system.assert_not_called()

    def test_handle_degraded_status(self):
        """Test handling degraded status (pause and notify)."""
        result = HealthCheckResult(
            status=SystemStatus.DEGRADED,
            reason="Elevated error rate",
            error_rate=25.0
        )

        actions = self.monitor.handle_status(result)

        self.assertEqual(actions['status'], 'degraded')
        self.assertTrue(actions['notifications_sent'])
        self.mock_safety.pause_system.assert_called_once()
        self.assertIn("DEGRADED", self.mock_safety.pause_system.call_args[1]['reason'])

    def test_handle_critical_status(self):
        """Test handling critical status (pause and urgent notify)."""
        result = HealthCheckResult(
            status=SystemStatus.CRITICAL,
            reason="Critical error rate",
            error_rate=50.0
        )

        actions = self.monitor.handle_status(result)

        self.assertEqual(actions['status'], 'critical')
        self.assertTrue(actions['notifications_sent'])
        self.mock_safety.pause_system.assert_called_once()
        self.assertIn("CRITICAL", self.mock_safety.pause_system.call_args[1]['reason'])


class TestHealthMonitorPeriodicCheck(TestCase):
    """Tests for periodic health check functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.monitor = HealthMonitor(
            notification_service=MagicMock(),
            safety_limit_service=MagicMock()
        )

    def test_run_periodic_check_returns_dict(self):
        """Test that run_periodic_check returns expected structure."""
        with patch.object(self.monitor, 'get_system_status') as mock_status:
            with patch.object(self.monitor, 'handle_status') as mock_handle:
                mock_status.return_value = HealthCheckResult(
                    status=SystemStatus.HEALTHY,
                    reason="OK",
                    error_rate=5.0,
                    rollback_rate=2.0,
                    consecutive_failures=0
                )
                mock_handle.return_value = {
                    'status': 'healthy',
                    'actions': [],
                    'notifications_sent': False
                }

                result = self.monitor.run_periodic_check()

                self.assertIn('timestamp', result)
                self.assertIn('status', result)
                self.assertIn('reason', result)
                self.assertIn('error_rate', result)
                self.assertIn('rollback_rate', result)
                self.assertIn('consecutive_failures', result)
                self.assertIn('actions', result)


class TestHealthMonitorCachedStatus(TestCase):
    """Tests for cached status functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.monitor = HealthMonitor(
            notification_service=MagicMock(),
            safety_limit_service=MagicMock()
        )

    @patch('assistant.health_monitor.cache')
    def test_get_cached_status(self, mock_cache):
        """Test getting cached status."""
        mock_cache.get.return_value = 'healthy'

        status = self.monitor.get_cached_status()

        self.assertEqual(status, 'healthy')
        mock_cache.get.assert_called_with(CACHE_KEY_HEALTH_STATUS)

    @patch('assistant.health_monitor.cache')
    def test_get_cached_status_none(self, mock_cache):
        """Test getting cached status when not set."""
        mock_cache.get.return_value = None

        status = self.monitor.get_cached_status()

        self.assertIsNone(status)

    @patch('assistant.health_monitor.cache')
    def test_get_last_check_time(self, mock_cache):
        """Test getting last check time."""
        mock_cache.get.return_value = '2026-01-05T12:00:00'

        time = self.monitor.get_last_check_time()

        self.assertEqual(time, '2026-01-05T12:00:00')
        mock_cache.get.assert_called_with(CACHE_KEY_LAST_HEALTH_CHECK)


class TestHealthMonitorFullStatusReport(TestCase):
    """Tests for full status report functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.monitor = HealthMonitor(
            notification_service=MagicMock(),
            safety_limit_service=MagicMock()
        )

    @patch('assistant.health_monitor.cache')
    def test_get_full_status_report_healthy(self, mock_cache):
        """Test full status report when healthy."""
        mock_cache.get.return_value = None
        mock_cache.set = MagicMock()

        with patch.object(self.monitor, 'get_system_status') as mock_status:
            with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
                mock_status.return_value = HealthCheckResult(
                    status=SystemStatus.HEALTHY,
                    reason="OK",
                    error_rate=5.0,
                    rollback_rate=2.0,
                    consecutive_failures=0,
                    details={}
                )
                mock_metrics.return_value = RateMetrics(
                    total_count=100,
                    error_count=5,
                    rollback_count=2,
                    completed_count=93,
                    error_rate=5.0,
                    rollback_rate=2.0,
                    consecutive_failures=0
                )

                report = self.monitor.get_full_status_report()

                self.assertEqual(report['status'], 'healthy')
                self.assertEqual(report['status_display'], 'HEALTHY')
                self.assertIn('metrics', report)
                self.assertIn('thresholds', report)
                self.assertEqual(len(report['recommendations']), 0)

    @patch('assistant.health_monitor.cache')
    def test_get_full_status_report_critical(self, mock_cache):
        """Test full status report when critical includes recommendations."""
        mock_cache.get.return_value = None
        mock_cache.set = MagicMock()

        with patch.object(self.monitor, 'get_system_status') as mock_status:
            with patch.object(self.monitor, '_get_rate_metrics') as mock_metrics:
                mock_status.return_value = HealthCheckResult(
                    status=SystemStatus.CRITICAL,
                    reason="Critical error rate",
                    error_rate=50.0,
                    rollback_rate=10.0,
                    consecutive_failures=2,
                    details={}
                )
                mock_metrics.return_value = RateMetrics(
                    total_count=100,
                    error_count=50,
                    rollback_count=10,
                    completed_count=40,
                    error_rate=50.0,
                    rollback_rate=20.0,
                    consecutive_failures=2
                )

                report = self.monitor.get_full_status_report()

                self.assertEqual(report['status'], 'critical')
                self.assertEqual(report['status_display'], 'CRITICAL')
                self.assertGreater(len(report['recommendations']), 0)


class TestConvenienceFunctions(TestCase):
    """Tests for module-level convenience functions."""

    @patch.object(HealthMonitor, 'get_system_status')
    def test_get_system_status_function(self, mock_method):
        """Test get_system_status convenience function."""
        mock_method.return_value = HealthCheckResult(
            status=SystemStatus.HEALTHY,
            reason="OK"
        )

        result = get_system_status()

        self.assertEqual(result.status, SystemStatus.HEALTHY)

    @patch.object(HealthMonitor, 'get_full_status_report')
    def test_get_status_report_function(self, mock_method):
        """Test get_status_report convenience function."""
        mock_method.return_value = {'status': 'healthy'}

        result = get_status_report()

        self.assertEqual(result['status'], 'healthy')

    @patch.object(HealthMonitor, 'run_periodic_check')
    def test_run_health_check_function(self, mock_method):
        """Test run_health_check convenience function."""
        mock_method.return_value = {
            'status': 'healthy',
            'timestamp': '2026-01-05T12:00:00'
        }

        result = run_health_check()

        self.assertEqual(result['status'], 'healthy')
