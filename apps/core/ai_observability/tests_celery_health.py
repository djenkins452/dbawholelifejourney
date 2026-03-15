"""
Tests for Celery execution layer health observability.

Tests the celery_health module, Ops Wall tile rendering, and
the celery_health key in the OpsStreamView polling payload.

Path: apps/core/ai_observability/tests_celery_health.py
"""
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.users.models import User, TermsAcceptance


class CeleryHealthClassificationTests(TestCase):
    """Test health status classification logic."""

    def test_healthy_status(self):
        """All metrics nominal → HEALTHY."""
        from apps.core.ai_observability.celery_health import _classify_status
        self.assertEqual(_classify_status(2, 5, 0, True), "HEALTHY")

    def test_degraded_single_worker(self):
        """Only 1 worker → DEGRADED."""
        from apps.core.ai_observability.celery_health import _classify_status
        self.assertEqual(_classify_status(1, 0, 0, True), "DEGRADED")

    def test_degraded_queue_rising(self):
        """Queue depth 25 (above warn threshold) → DEGRADED."""
        from apps.core.ai_observability.celery_health import _classify_status
        self.assertEqual(_classify_status(2, 25, 0, True), "DEGRADED")

    def test_degraded_moderate_failures(self):
        """5 failures in 1h (at warn threshold) → DEGRADED."""
        from apps.core.ai_observability.celery_health import _classify_status
        self.assertEqual(_classify_status(2, 0, 5, True), "DEGRADED")

    def test_critical_queue_depth(self):
        """Queue depth 60 (above critical) → CRITICAL."""
        from apps.core.ai_observability.celery_health import _classify_status
        self.assertEqual(_classify_status(2, 60, 0, True), "CRITICAL")

    def test_critical_many_failures(self):
        """15 failures in 1h → CRITICAL."""
        from apps.core.ai_observability.celery_health import _classify_status
        self.assertEqual(_classify_status(2, 0, 15, True), "CRITICAL")

    def test_down_no_workers(self):
        """Zero workers → DOWN."""
        from apps.core.ai_observability.celery_health import _classify_status
        self.assertEqual(_classify_status(0, 0, 0, True), "DOWN")

    def test_down_broker_unreachable(self):
        """Broker unreachable → DOWN regardless of other metrics."""
        from apps.core.ai_observability.celery_health import _classify_status
        self.assertEqual(_classify_status(2, 5, 0, False), "DOWN")


class CeleryHealthCollectorTests(TestCase):
    """Test the get_celery_health() collector function."""

    @patch("apps.core.ai_observability.celery_health._get_celery_app")
    @patch("apps.core.ai_observability.celery_health._get_queue_depth")
    @patch("apps.core.ai_observability.celery_health._get_worker_stats")
    @patch("apps.core.ai_observability.celery_health._get_failed_task_count_1h")
    def test_healthy_response_structure(self, mock_failed, mock_workers, mock_queue, mock_app):
        """Full health check returns all expected keys."""
        from apps.core.ai_observability.celery_health import get_celery_health

        mock_app.return_value = MagicMock()
        mock_queue.return_value = 3
        mock_workers.return_value = {
            "workers": [
                {"name": "celery@worker1", "status": "online", "active_tasks": 1,
                 "reserved_tasks": 0, "processed": 42, "concurrency": 2},
            ],
            "active_tasks": 1,
            "reserved_tasks": 0,
        }
        mock_failed.return_value = 0

        result = get_celery_health()

        # All keys present
        for key in ("status", "worker_count", "workers", "queue_depth",
                     "active_tasks", "reserved_tasks", "failed_1h", "broker_connected"):
            self.assertIn(key, result, f"Missing key: {key}")

        self.assertEqual(result["status"], "DEGRADED")  # 1 worker < 2
        self.assertEqual(result["worker_count"], 1)
        self.assertEqual(result["queue_depth"], 3)
        self.assertTrue(result["broker_connected"])

    @patch("apps.core.ai_observability.celery_health._get_celery_app")
    def test_no_celery_app(self, mock_app):
        """Returns DOWN when Celery app can't be imported."""
        from apps.core.ai_observability.celery_health import get_celery_health

        mock_app.return_value = None
        result = get_celery_health()

        self.assertEqual(result["status"], "DOWN")
        self.assertFalse(result["broker_connected"])

    @patch("apps.core.ai_observability.celery_health._get_celery_app")
    @patch("apps.core.ai_observability.celery_health._get_queue_depth")
    @patch("apps.core.ai_observability.celery_health._get_worker_stats")
    @patch("apps.core.ai_observability.celery_health._get_failed_task_count_1h")
    def test_workers_unreachable(self, mock_failed, mock_workers, mock_queue, mock_app):
        """Workers unreachable but broker connected → DOWN (0 workers)."""
        from apps.core.ai_observability.celery_health import get_celery_health

        mock_app.return_value = MagicMock()
        mock_queue.return_value = 10
        mock_workers.return_value = None  # Workers unreachable
        mock_failed.return_value = 0

        result = get_celery_health()
        self.assertEqual(result["status"], "DOWN")
        self.assertEqual(result["worker_count"], 0)
        self.assertTrue(result["broker_connected"])


class CeleryHealthViewTests(TestCase):
    """Test Celery health data appears in Ops Wall."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="opsstaff@test.com", password="testpass123"
        )
        self.user.is_staff = True
        self.user.save()
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client.login(email="opsstaff@test.com", password="testpass123")
        session = self.client.session
        session["mfa_verified"] = True
        session["mfa_verified_at"] = timezone.now().isoformat()
        session.save()

    def test_ops_wall_has_celery_tile(self):
        """Ops Wall HTML includes the Celery Workers tile."""
        resp = self.client.get("/admin-console/ops/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("celeryHealthTile", content)
        self.assertIn("celeryWorkerCount", content)
        self.assertIn("celeryQueueDepth", content)
        self.assertIn("Execution Layer", content)

    @patch("apps.core.ai_observability.ops_views._get_celery_health")
    def test_ops_stream_includes_celery_health(self, mock_celery):
        """OpsStreamView polling includes celery_health key."""
        mock_celery.return_value = {
            "status": "HEALTHY",
            "worker_count": 2,
            "workers": [],
            "queue_depth": 0,
            "active_tasks": 0,
            "reserved_tasks": 0,
            "failed_1h": 0,
            "broker_connected": True,
        }
        resp = self.client.get("/admin-console/ops/stream/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("celery_health", data)
        self.assertEqual(data["celery_health"]["status"], "HEALTHY")
