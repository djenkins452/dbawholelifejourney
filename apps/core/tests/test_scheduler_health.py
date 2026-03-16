"""
Tests for scheduler health check module (Celery Beat liveness).

Validates get_scheduler_status() which derives Beat health from
ISE and SAME heartbeats.
"""
from unittest.mock import patch, MagicMock
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.core.scheduler_health import get_scheduler_status


class SchedulerStatusTests(TestCase):
    """Tests for get_scheduler_status() — heartbeat-based health check."""

    def _make_heartbeat(self, status, drift_seconds=60):
        """Create a mock SchedulerHeartbeat."""
        hb = MagicMock()
        hb.status = status
        hb.last_tick_at = timezone.now() - timedelta(seconds=drift_seconds)
        hb.drift_seconds = drift_seconds
        return hb

    @patch("apps.core.ai_observability.models.SchedulerHeartbeat.get_for_scheduler")
    def test_both_alive_returns_alive(self, mock_get):
        """When both ISE and SAME are ALIVE, overall status is ALIVE."""
        def side_effect(name):
            return self._make_heartbeat("ALIVE", 30)
        mock_get.side_effect = side_effect

        status = get_scheduler_status()
        self.assertEqual(status['status'], 'ALIVE')
        self.assertTrue(status['running'])
        self.assertFalse(status['needs_restart'])
        self.assertEqual(status['ise_status'], 'ALIVE')
        self.assertEqual(status['same_status'], 'ALIVE')

    @patch("apps.core.ai_observability.models.SchedulerHeartbeat.get_for_scheduler")
    def test_one_alive_one_offline_returns_delayed(self, mock_get):
        """When ISE is ALIVE but SAME is OFFLINE, overall is DELAYED."""
        def side_effect(name):
            if name == "ISE":
                return self._make_heartbeat("ALIVE", 30)
            return None  # SAME offline
        mock_get.side_effect = side_effect

        status = get_scheduler_status()
        self.assertEqual(status['status'], 'DELAYED')
        self.assertTrue(status['running'])
        self.assertTrue(status['needs_restart'])

    @patch("apps.core.ai_observability.models.SchedulerHeartbeat.get_for_scheduler")
    def test_both_offline_returns_offline(self, mock_get):
        """When both ISE and SAME are missing, overall is OFFLINE."""
        mock_get.return_value = None

        status = get_scheduler_status()
        self.assertEqual(status['status'], 'OFFLINE')
        self.assertFalse(status['running'])
        self.assertTrue(status['needs_restart'])

    @patch("apps.core.ai_observability.models.SchedulerHeartbeat.get_for_scheduler")
    def test_both_delayed_returns_delayed(self, mock_get):
        """When both heartbeats are DELAYED, overall is DELAYED."""
        def side_effect(name):
            return self._make_heartbeat("DELAYED", 600)
        mock_get.side_effect = side_effect

        status = get_scheduler_status()
        self.assertEqual(status['status'], 'DELAYED')
        self.assertTrue(status['running'])
        self.assertTrue(status['needs_restart'])

    @patch("apps.core.ai_observability.models.SchedulerHeartbeat.get_for_scheduler")
    def test_status_dict_structure(self, mock_get):
        """Status always returns expected keys."""
        mock_get.return_value = None

        status = get_scheduler_status()
        self.assertIn('running', status)
        self.assertIn('status', status)
        self.assertIn('ise_status', status)
        self.assertIn('same_status', status)
        self.assertIn('drift_seconds', status)
        self.assertIn('needs_restart', status)

    @patch("apps.core.ai_observability.models.SchedulerHeartbeat.get_for_scheduler")
    def test_drift_seconds_populated_from_ise(self, mock_get):
        """drift_seconds should come from the ISE heartbeat."""
        def side_effect(name):
            if name == "ISE":
                return self._make_heartbeat("ALIVE", 120)
            return self._make_heartbeat("ALIVE", 30)
        mock_get.side_effect = side_effect

        status = get_scheduler_status()
        self.assertIsNotNone(status['drift_seconds'])
        # Should be approximately 120 seconds (allow small tolerance)
        self.assertAlmostEqual(status['drift_seconds'], 120, delta=5)

    @patch("apps.core.ai_observability.models.SchedulerHeartbeat.get_for_scheduler")
    def test_exception_returns_error_status(self, mock_get):
        """DB errors should not crash — return ERROR status."""
        mock_get.side_effect = Exception("DB connection lost")

        status = get_scheduler_status()
        self.assertEqual(status['status'], 'ERROR')
        self.assertFalse(status['running'])
