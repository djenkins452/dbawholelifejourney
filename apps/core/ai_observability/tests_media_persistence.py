"""
OPS-8b — Media & capture persistence health tests.

Exercises the capture-pipeline health (CaptureEntry/PendingCapture), the
expired-image "missing cleaner" signal (AssistantMessage), and the storage-config
facts against the real test DB. Deterministic; each block degrades gracefully.
"""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.capture.models import CaptureEntry, PendingCapture
from apps.core.ai_observability import media_persistence_monitor as mpm

User = get_user_model()


def _user(email):
    return User.objects.create(email=email)


def _capture(user, status, updated_delta=timedelta(0), error_message=""):
    e = CaptureEntry.objects.create(user=user, status=status, error_message=error_message)
    if updated_delta:
        CaptureEntry.objects.filter(pk=e.pk).update(updated_at=timezone.now() + updated_delta)
    return e


class CaptureHealthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = _user("cap@test.com")

    def test_healthy_when_ready(self):
        _capture(self.user, CaptureEntry.STATUS_READY)
        r = mpm._capture_health(timezone.now())
        self.assertEqual(r["status"], "HEALTHY")
        self.assertEqual(r["failed_24h"], 0)
        self.assertEqual(r["by_status_24h"].get("ready"), 1)

    def test_failed_counted_with_top_error(self):
        for _ in range(3):
            _capture(self.user, CaptureEntry.STATUS_FAILED,
                     error_message="Upload failed: network error")
        r = mpm._capture_health(timezone.now())
        self.assertEqual(r["failed_24h"], 3)
        self.assertEqual(r["status"], "WARNING")
        self.assertIsNotNone(r["top_error_type"])

    def test_stuck_capture_detected(self):
        # In-progress but updated_at is old → stuck.
        _capture(self.user, CaptureEntry.STATUS_TRANSCRIBING,
                 updated_delta=timedelta(seconds=-(mpm.STUCK_CAPTURE_S + 60)))
        r = mpm._capture_health(timezone.now())
        self.assertEqual(r["stuck"], 1)
        self.assertEqual(r["status"], "WARNING")

    def test_many_stuck_is_critical(self):
        for _ in range(3):
            _capture(self.user, CaptureEntry.STATUS_UPLOADING,
                     updated_delta=timedelta(seconds=-(mpm.STUCK_CAPTURE_S + 60)))
        r = mpm._capture_health(timezone.now())
        self.assertEqual(r["status"], "CRITICAL")

    def test_pending_abandoned_flagged(self):
        PendingCapture.objects.create(
            user=self.user, client_id="c1", status=PendingCapture.STATUS_ABANDONED,
        )
        r = mpm._capture_health(timezone.now())
        self.assertEqual(r["pending_abandoned_24h"], 1)
        self.assertEqual(r["status"], "WARNING")


class ImageRetentionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_zero_expired_is_healthy(self):
        r = mpm._image_retention_health(timezone.now())
        self.assertEqual(r["status"], "HEALTHY")
        self.assertEqual(r["expired_unpurged"], 0)
        self.assertIn("no cleanup task", r["note"])

    def test_expired_unpurged_counted(self):
        from apps.ai.models import AssistantConversation, AssistantMessage
        user = _user("img@test.com")
        now = timezone.now()
        convo = AssistantConversation.objects.create(user=user)
        # An expired image row that still carries its base64 bytes → never purged.
        AssistantMessage.objects.create(
            conversation=convo, role="user", content="x",
            image_data="AAAA", image_expires_at=now - timedelta(hours=1),
        )
        r = mpm._image_retention_health(now)
        self.assertEqual(r["expired_unpurged"], 1)


class TelemetrySectionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_section_shape_and_storage_facts(self):
        r = mpm.get_media_persistence_telemetry()
        for key in ("status", "capture", "image_retention", "storage_config", "measured_at"):
            self.assertIn(key, r)
        sc = r["storage_config"]
        self.assertIn("cloudinary_configured", sc)
        self.assertIn("capture_s3_configured", sc)

    def test_cache_guard(self):
        mpm.get_media_persistence_telemetry()
        with mock.patch.object(mpm, "_capture_health") as m:
            mpm.get_media_persistence_telemetry()
            m.assert_not_called()
