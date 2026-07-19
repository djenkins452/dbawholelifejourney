"""
Tests for the artifact-storage-lifecycle health block (OPS-8b extension, P0.7).

Verifies the durable-storage pipeline health signal: failed writes and
stuck-pending artifacts escalate status; a clean pipeline reads HEALTHY.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.capture.models import MultimodalArtifact
from apps.core.ai_observability.media_persistence_monitor import (
    _artifact_storage_health,
    get_media_persistence_telemetry,
)

User = get_user_model()


class ArtifactStorageMonitorTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="mon@example.com", password="x")
        self.now = timezone.now()

    def _mk(self, sha, storage_status, created_delta=timedelta()):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256=sha, content_type="image/png",
            storage_status=storage_status,
        )
        if created_delta:
            MultimodalArtifact.objects.filter(id=art.id).update(
                created_at=self.now - created_delta,
            )
        return art

    def test_healthy_when_all_stored(self):
        self._mk("a" * 64, MultimodalArtifact.STORAGE_STORED)
        self._mk("b" * 64, MultimodalArtifact.STORAGE_STORED)
        health = _artifact_storage_health(self.now)
        self.assertEqual(health["status"], "HEALTHY")
        self.assertEqual(health["failed_24h"], 0)
        self.assertEqual(health["stuck_pending"], 0)

    def test_failed_writes_warn(self):
        for i in range(3):
            self._mk(str(i) * 64, MultimodalArtifact.STORAGE_FAILED)
        health = _artifact_storage_health(self.now)
        self.assertEqual(health["status"], "WARNING")
        self.assertEqual(health["failed_24h"], 3)

    def test_stuck_pending_warns(self):
        # A pending artifact older than the stuck window = worker stalled.
        self._mk("c" * 64, MultimodalArtifact.STORAGE_PENDING,
                 created_delta=timedelta(minutes=30))
        health = _artifact_storage_health(self.now)
        self.assertEqual(health["status"], "WARNING")
        self.assertEqual(health["stuck_pending"], 1)

    def test_fresh_pending_is_not_stuck(self):
        self._mk("d" * 64, MultimodalArtifact.STORAGE_PENDING)  # just created
        health = _artifact_storage_health(self.now)
        self.assertEqual(health["stuck_pending"], 0)
        self.assertEqual(health["status"], "HEALTHY")

    def test_telemetry_includes_artifact_storage_block(self):
        self._mk("e" * 64, MultimodalArtifact.STORAGE_STORED)
        telem = get_media_persistence_telemetry(self.now)
        self.assertIn("artifact_storage", telem)
        self.assertEqual(telem["artifact_storage"]["status"], "HEALTHY")
