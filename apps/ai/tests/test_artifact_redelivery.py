"""
Tests for Artifacts-as-Truth Milestone B2 — re-delivery of visual content.

When the user retrieves a previously-uploaded IMAGE or VIDEO, WLJ must give the
model the actual pixels/frames to RE-PERCEIVE (not just metadata). PDF/audio ride
as text (extracted_text) and need no re-delivery.
"""
import base64
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import TestCase, override_settings

from apps.ai.multimodal import (
    artifact_ids_from_entity_envelope,
    perceive_images_for_artifacts,
)
from apps.capture.models import MultimodalArtifact

User = get_user_model()

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40


class EnvelopeExtractionTests(TestCase):
    def test_single_entity(self):
        raw = {"status": "ready", "entity": {"definition": {"artifact_id": 7}}}
        self.assertEqual(artifact_ids_from_entity_envelope(raw), [7])

    def test_entity_list(self):
        raw = {"entities": [
            {"definition": {"artifact_id": 1}},
            {"definition": {"artifact_id": 2}},
            {"definition": {}},  # no id → skipped
        ]}
        self.assertEqual(artifact_ids_from_entity_envelope(raw), [1, 2])

    def test_garbage(self):
        self.assertEqual(artifact_ids_from_entity_envelope(None), [])
        self.assertEqual(artifact_ids_from_entity_envelope({"status": "empty"}), [])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="wlj-redeliver-"))
class PerceiveImagesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="r@ex.com", password="x")

    def test_image_bytes_reloaded_from_storage(self):
        name = default_storage.save("multimodal/x/pic.png", ContentFile(PNG))
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="a" * 64, content_type="image/png", kind="image",
            storage_ref=name, storage_status=MultimodalArtifact.STORAGE_STORED,
        )
        out = perceive_images_for_artifacts(self.user, [art.id])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][1], "image/png")
        self.assertEqual(base64.b64decode(out[0][0]), PNG)

    def test_unstored_image_skipped(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="b" * 64, content_type="image/png", kind="image",
            storage_status=MultimodalArtifact.STORAGE_PENDING,
        )
        self.assertEqual(perceive_images_for_artifacts(self.user, [art.id]), [])

    def test_video_frames_delivered(self):
        frames = [{"t": 0.5, "b64": base64.b64encode(b"f0").decode()},
                  {"t": 2.5, "b64": base64.b64encode(b"f1").decode()}]
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="c" * 64, content_type="video/mp4", kind="video",
            perception_status=MultimodalArtifact.PERCEPTION_DONE, frames=frames,
        )
        out = perceive_images_for_artifacts(self.user, [art.id])
        self.assertEqual(len(out), 2)
        self.assertTrue(all(m == "image/jpeg" for _, m in out))

    def test_pdf_yields_no_visual_bytes(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="d" * 64, content_type="application/pdf",
            kind="document", perception_status=MultimodalArtifact.PERCEPTION_DONE,
            extracted_text="text is enough",
        )
        self.assertEqual(perceive_images_for_artifacts(self.user, [art.id]), [])

    def test_owner_scoped(self):
        other = User.objects.create_user(email="o@ex.com", password="x")
        name = default_storage.save("multimodal/y/secret.png", ContentFile(PNG))
        art = MultimodalArtifact.objects.create(
            user=other, sha256="e" * 64, content_type="image/png", kind="image",
            storage_ref=name, storage_status=MultimodalArtifact.STORAGE_STORED,
        )
        self.assertEqual(perceive_images_for_artifacts(self.user, [art.id]), [])

    def test_bounded(self):
        frames = [{"t": float(i), "b64": "x"} for i in range(20)]
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="f" * 64, content_type="video/mp4", kind="video",
            perception_status=MultimodalArtifact.PERCEPTION_DONE, frames=frames,
        )
        self.assertEqual(len(perceive_images_for_artifacts(self.user, [art.id], max_total=6)), 6)
