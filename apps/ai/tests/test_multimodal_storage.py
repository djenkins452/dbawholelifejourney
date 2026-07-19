"""
Tests for durable artifact storage (P0.6): background persistence + integrity.

Verifies the request-path/worker split:
  - ingest_uploads records the artifact + provenance and QUEUES durable storage
    (which runs eagerly in tests), never blocking on I/O.
  - the persist task verifies sha256 integrity, writes to durable storage, and
    records storage_ref / byte_size / storage_status.
  - failure and idempotency paths behave correctly.
"""
import base64
import hashlib
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings

from apps.ai.multimodal import ingest_uploads
from apps.ai.tasks import persist_artifact_bytes
from apps.capture.models import MultimodalArtifact

User = get_user_model()

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PNG_B64 = base64.b64encode(PNG).decode("utf-8")
PNG_SHA = hashlib.sha256(PNG).hexdigest()

_TMP_MEDIA = tempfile.mkdtemp(prefix="wlj-media-test-")


@override_settings(MEDIA_ROOT=_TMP_MEDIA)
class MultimodalStorageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="artifact@example.com", password="x",
        )

    def test_ingest_queues_and_persists_durably(self):
        images, attachments = ingest_uploads(
            self.user, images_list=[(PNG_B64, "image/png")],
        )
        # Perception payload is returned; artifact provenance recorded.
        self.assertEqual(len(images), 1)
        self.assertEqual(len(attachments), 1)

        art = MultimodalArtifact.objects.get(id=attachments[0]["artifact_id"])
        # Ran eagerly in tests → durably stored with integrity metadata.
        self.assertEqual(art.storage_status, MultimodalArtifact.STORAGE_STORED)
        self.assertTrue(art.is_durably_stored)
        self.assertTrue(art.storage_ref)
        self.assertEqual(art.byte_size, len(PNG))
        self.assertEqual(art.sha256, PNG_SHA)
        # The original bytes are actually retrievable from durable storage.
        with default_storage.open(art.storage_ref, "rb") as fh:
            self.assertEqual(fh.read(), PNG)

    def test_integrity_mismatch_marks_failed(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256=PNG_SHA, content_type="image/png",
        )
        # Feed bytes that do NOT match the recorded hash.
        other = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x11" * 64).decode("utf-8")
        result = persist_artifact_bytes(art.id, other)
        self.assertEqual(result["result"], "integrity_mismatch")
        art.refresh_from_db()
        self.assertEqual(art.storage_status, MultimodalArtifact.STORAGE_FAILED)
        self.assertFalse(art.is_durably_stored)

    def test_idempotent_when_already_stored(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256=PNG_SHA, content_type="image/png",
            storage_ref="multimodal/x/y.png",
            storage_status=MultimodalArtifact.STORAGE_STORED,
        )
        result = persist_artifact_bytes(art.id, PNG_B64)
        self.assertEqual(result["result"], "already_stored")

    def test_empty_bytes_skipped(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="", content_type="image/png",
        )
        result = persist_artifact_bytes(art.id, "")
        self.assertEqual(result["result"], "no_bytes")
        art.refresh_from_db()
        self.assertEqual(art.storage_status, MultimodalArtifact.STORAGE_SKIPPED)

    def test_reupload_same_content_is_idempotent(self):
        ingest_uploads(self.user, images_list=[(PNG_B64, "image/png")])
        ingest_uploads(self.user, images_list=[(PNG_B64, "image/png")])
        # Artifact-level dedup: one artifact for identical content.
        self.assertEqual(
            MultimodalArtifact.objects.filter(user=self.user).count(), 1,
        )
