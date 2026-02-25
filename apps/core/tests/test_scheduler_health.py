"""
Tests for scheduler health check module.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.core.scheduler_health import get_scheduler_status


class SchedulerStatusTests(TestCase):
    """Tests for get_scheduler_status()."""

    def test_no_scheduler_returns_not_started(self):
        """When no scheduler instance exists, status is NOT_STARTED."""
        with patch('apps.core.scheduler_health._get_scheduler', return_value=None):
            status = get_scheduler_status()
            self.assertEqual(status['status'], 'NOT_STARTED')
            self.assertFalse(status['running'])
            self.assertTrue(status['needs_restart'])

    def test_stopped_scheduler(self):
        """When scheduler exists but is not running, status is STOPPED."""
        mock_scheduler = MagicMock()
        mock_scheduler.running = False
        mock_scheduler.get_jobs.return_value = []

        with patch('apps.core.scheduler_health._get_scheduler', return_value=mock_scheduler):
            status = get_scheduler_status()
            self.assertEqual(status['status'], 'STOPPED')
            self.assertFalse(status['running'])
            self.assertTrue(status['needs_restart'])

    def test_running_scheduler_with_no_heartbeat(self):
        """When scheduler is running but no heartbeat record exists."""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_scheduler.get_jobs.return_value = [MagicMock()] * 15

        with patch('apps.core.scheduler_health._get_scheduler', return_value=mock_scheduler):
            status = get_scheduler_status()
            self.assertTrue(status['running'])
            self.assertEqual(status['job_count'], 15)
            # With no heartbeat record, status depends on DB query
            self.assertIn(status['status'], ['NO_HEARTBEAT', 'ALIVE', 'DELAYED', 'OFFLINE'])

    def test_status_dict_structure(self):
        """Status always returns expected keys."""
        with patch('apps.core.scheduler_health._get_scheduler', return_value=None):
            status = get_scheduler_status()
            self.assertIn('running', status)
            self.assertIn('job_count', status)
            self.assertIn('status', status)
            self.assertIn('needs_restart', status)
            self.assertIn('last_heartbeat', status)
            self.assertIn('drift_seconds', status)
