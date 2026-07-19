"""
Tests for Phase 1.3 Milestone 3 — Video perception.

Video = DUAL deterministic decode: sampled FRAMES (ffmpeg → delivered to the
model's image path) + the AUDIO-TRACK transcript (the ONE shared transcription
capability). Only the perception stage differs from PDF/audio. ffmpeg + Whisper
are mocked (neither is available/keyed in tests).
"""
import base64
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.multimodal import frames_for_attachments
from apps.ai.perception import is_perceivable, perceive
from apps.ai.tasks import perceive_artifact
from apps.capture.models import MultimodalArtifact

User = get_user_model()

_FRAMES = "apps.ai.perception._extract_frames"
_TRANSCRIBE = "apps.capture.services.transcription.transcription_service.transcribe_bytes"

_FAKE_FRAMES = [
    {"t": 0.5, "b64": base64.b64encode(b"frame0").decode()},
    {"t": 2.5, "b64": base64.b64encode(b"frame1").decode()},
]


class VideoPerceiveTests(TestCase):
    def test_video_types_perceivable(self):
        self.assertTrue(is_perceivable("video/mp4"))
        self.assertTrue(is_perceivable("video/quicktime"))

    def test_frames_plus_transcript(self):
        with patch(_FRAMES, return_value=_FAKE_FRAMES), \
             patch(_TRANSCRIBE, return_value="Alright team, ship it Friday."):
            r = perceive("video/mp4", b"video-bytes")
        self.assertEqual(r["status"], "done")
        self.assertEqual(len(r["frames"]), 2)
        self.assertEqual(r["page_count"], 2)
        self.assertIn("representative frames", r["text"])
        self.assertIn("0.5s, 2.5s", r["text"])            # timeline references
        self.assertIn("ship it Friday", r["text"])        # audio transcript

    def test_frames_only_silent_video(self):
        with patch(_FRAMES, return_value=_FAKE_FRAMES), patch(_TRANSCRIBE, return_value=""):
            r = perceive("video/quicktime", b"x")
        self.assertEqual(r["status"], "done")
        self.assertEqual(len(r["frames"]), 2)
        self.assertNotIn("Audio transcript", r["text"])

    def test_transcript_only_no_frames(self):
        with patch(_FRAMES, return_value=[]), patch(_TRANSCRIBE, return_value="meeting words"):
            r = perceive("video/mp4", b"x")
        self.assertEqual(r["status"], "done")
        self.assertEqual(r["frames"], [])
        self.assertIn("meeting words", r["text"])

    def test_nothing_extractable_unsupported(self):
        with patch(_FRAMES, return_value=[]), patch(_TRANSCRIBE, return_value=""):
            r = perceive("video/mp4", b"x")
        self.assertEqual(r["status"], "unsupported")

    def test_frame_extraction_failure_still_ok_via_transcript(self):
        with patch(_FRAMES, side_effect=RuntimeError("no ffmpeg")), \
             patch(_TRANSCRIBE, return_value="spoken content"):
            r = perceive("video/mp4", b"x")
        self.assertEqual(r["status"], "done")
        self.assertIn("spoken content", r["text"])


class VideoTaskAndDeliveryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="v@ex.com", password="x")

    def test_task_persists_frames(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="a" * 64, content_type="video/mp4", kind="video",
            perception_status=MultimodalArtifact.PERCEPTION_PENDING,
        )
        with patch(_FRAMES, return_value=_FAKE_FRAMES), patch(_TRANSCRIBE, return_value="hi"):
            result = perceive_artifact(art.id, base64.b64encode(b"video").decode())
        self.assertEqual(result["result"], "done")
        self.assertEqual(result["frames"], 2)
        art.refresh_from_db()
        self.assertEqual(len(art.frames), 2)
        self.assertTrue(art.has_perception)

    def test_frames_for_attachments_delivers_images(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="b" * 64, content_type="video/mp4", kind="video",
            perception_status=MultimodalArtifact.PERCEPTION_DONE, frames=_FAKE_FRAMES,
        )
        out = frames_for_attachments(self.user, [art.id])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0][1], "image/jpeg")
        self.assertEqual(out[0][0], _FAKE_FRAMES[0]["b64"])

    def test_frames_for_attachments_owner_scoped_and_bounded(self):
        other = User.objects.create_user(email="o@ex.com", password="x")
        mine = MultimodalArtifact.objects.create(
            user=self.user, sha256="c" * 64, content_type="video/mp4", kind="video",
            perception_status=MultimodalArtifact.PERCEPTION_DONE,
            frames=[{"t": float(i), "b64": "f"} for i in range(30)],
        )
        MultimodalArtifact.objects.create(
            user=other, sha256="d" * 64, content_type="video/mp4", kind="video",
            perception_status=MultimodalArtifact.PERCEPTION_DONE, frames=_FAKE_FRAMES,
        )
        out = frames_for_attachments(self.user, [mine.id], max_total=16)
        self.assertEqual(len(out), 16)   # bounded
        # A non-video artifact yields no frames.
        img = MultimodalArtifact.objects.create(
            user=self.user, sha256="e" * 64, content_type="image/png", kind="image",
        )
        self.assertEqual(frames_for_attachments(self.user, [img.id]), [])
