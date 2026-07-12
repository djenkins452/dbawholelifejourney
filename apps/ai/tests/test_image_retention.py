# ==============================================================================
# File: apps/ai/tests/test_image_retention.py
# Project: Whole Life Journey
# Description: Tests for the expired chat-image cleanup task (OPS-8b gap closure)
# ==============================================================================
"""Scoped tests for ``apps.ai.image_retention.purge_expired_images``.

Covers: expired-message byte purge (row kept), expired-attachment delete,
non-expired preservation, idempotency, already-purged no-op, and end-to-end
agreement with the OPS-8b ``media_persistence`` monitor's expired counter.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.image_retention import purge_expired_images
from apps.ai.models import AssistantConversation, AssistantMessage, MessageImage

User = get_user_model()


def _user(email="img-cleanup@test.com"):
    return User.objects.create_user(email=email, password="x")


class PurgeExpiredImagesTests(TestCase):
    def setUp(self):
        self.user = _user()
        self.convo = AssistantConversation.objects.create(user=self.user)
        self.now = timezone.now()

    def _message(self, *, expires_delta, data="AAAA", mime="image/png"):
        return AssistantMessage.objects.create(
            conversation=self.convo, role="user", content="x",
            image_data=data, image_mime_type=mime,
            image_expires_at=self.now + expires_delta,
        )

    # ---- AssistantMessage: purge bytes, keep the conversation turn ----------

    def test_expired_message_bytes_purged_row_kept(self):
        msg = self._message(expires_delta=-timedelta(hours=1))
        result = purge_expired_images(self.now)

        self.assertEqual(result["messages_purged"], 1)
        msg.refresh_from_db()
        # Row still exists (conversation history), bytes gone.
        self.assertEqual(msg.image_data, "")
        self.assertEqual(msg.image_mime_type, "")
        self.assertIsNone(msg.image_expires_at)
        self.assertEqual(msg.content, "x")

    def test_non_expired_message_untouched(self):
        msg = self._message(expires_delta=timedelta(hours=1))
        result = purge_expired_images(self.now)

        self.assertEqual(result["messages_purged"], 0)
        msg.refresh_from_db()
        self.assertEqual(msg.image_data, "AAAA")
        self.assertIsNotNone(msg.image_expires_at)

    def test_already_purged_message_is_noop(self):
        # Expired timestamp but bytes already cleared → must NOT be re-counted.
        AssistantMessage.objects.create(
            conversation=self.convo, role="user", content="x",
            image_data="", image_mime_type="",
            image_expires_at=self.now - timedelta(hours=5),
        )
        result = purge_expired_images(self.now)
        self.assertEqual(result["messages_purged"], 0)

    # ---- MessageImage: delete the expired attachment row --------------------

    def test_expired_attachment_deleted(self):
        parent = self._message(expires_delta=timedelta(hours=1))  # parent not expired
        MessageImage.objects.create(
            message=parent, image_data="BBBB", image_mime_type="image/png",
            image_expires_at=self.now - timedelta(hours=2), order=0,
        )
        result = purge_expired_images(self.now)

        self.assertEqual(result["images_deleted"], 1)
        self.assertFalse(MessageImage.objects.exists())
        # Parent message untouched.
        parent.refresh_from_db()
        self.assertEqual(parent.image_data, "AAAA")

    def test_non_expired_attachment_kept(self):
        parent = self._message(expires_delta=timedelta(hours=1))
        MessageImage.objects.create(
            message=parent, image_data="BBBB", image_mime_type="image/png",
            image_expires_at=self.now + timedelta(hours=2), order=0,
        )
        result = purge_expired_images(self.now)
        self.assertEqual(result["images_deleted"], 0)
        self.assertEqual(MessageImage.objects.count(), 1)

    # ---- Idempotency + shape ------------------------------------------------

    def test_idempotent_second_run_is_noop(self):
        self._message(expires_delta=-timedelta(hours=1))
        parent = self._message(expires_delta=timedelta(hours=1))
        MessageImage.objects.create(
            message=parent, image_data="BBBB", image_mime_type="image/png",
            image_expires_at=self.now - timedelta(hours=2), order=0,
        )

        first = purge_expired_images(self.now)
        self.assertEqual(first["messages_purged"], 1)
        self.assertEqual(first["images_deleted"], 1)

        second = purge_expired_images(self.now)
        self.assertEqual(second["messages_purged"], 0)
        self.assertEqual(second["images_deleted"], 0)

    def test_result_shape(self):
        result = purge_expired_images(self.now)
        self.assertEqual(
            set(result), {"messages_purged", "images_deleted", "cutoff"}
        )
        self.assertEqual(result["cutoff"], self.now.isoformat())

    # ---- End-to-end agreement with the OPS-8b monitor -----------------------

    def test_monitor_expired_count_drops_to_zero_after_purge(self):
        from apps.core.ai_observability import media_persistence_monitor as mpm

        self._message(expires_delta=-timedelta(hours=1))
        parent = self._message(expires_delta=timedelta(hours=1))
        MessageImage.objects.create(
            message=parent, image_data="BBBB", image_mime_type="image/png",
            image_expires_at=self.now - timedelta(hours=2), order=0,
        )

        before = mpm._image_retention_health(self.now)
        self.assertEqual(before["expired_unpurged"], 2)

        purge_expired_images(self.now)

        after = mpm._image_retention_health(self.now)
        self.assertEqual(after["expired_unpurged"], 0)
        self.assertEqual(after["status"], "HEALTHY")
