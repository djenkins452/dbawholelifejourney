"""
Tests for Phase 1.3 Milestone 2 — Audio perception.

WLJ transcribes deterministically via the ONE shared transcription capability
(Capture's Whisper integration); the model reasons over the transcript. Whisper
is mocked (no API key in tests).
"""
import base64
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.perception import _AUDIO_FILENAMES, is_perceivable, perceive
from apps.ai.tasks import perceive_artifact
from apps.capture.models import MultimodalArtifact
from apps.capture.services.transcription import TranscriptionError

User = get_user_model()

_TRANSCRIBE = "apps.capture.services.transcription.transcription_service.transcribe_bytes"


class AudioPerceiveTests(TestCase):
    def test_audio_types_perceivable(self):
        for ct in ("audio/mpeg", "audio/mp4", "audio/wav", "audio/aac"):
            self.assertTrue(is_perceivable(ct), ct)

    def test_transcribes_audio(self):
        with patch(_TRANSCRIBE, return_value="  Remember to call the pharmacy.  ") as m:
            result = perceive("audio/mpeg", b"fake-audio")
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["text"], "Remember to call the pharmacy.")
        # Correct Whisper filename/extension was passed for the format.
        m.assert_called_once()
        self.assertEqual(m.call_args[0][1], _AUDIO_FILENAMES["audio/mpeg"])

    def test_m4a_and_aac_filenames(self):
        with patch(_TRANSCRIBE, return_value="hi") as m:
            perceive("audio/mp4", b"x")
            self.assertEqual(m.call_args[0][1], "audio.m4a")
        with patch(_TRANSCRIBE, return_value="hi") as m:
            perceive("audio/aac", b"x")
            self.assertEqual(m.call_args[0][1], "audio.aac")

    def test_empty_transcript_unsupported(self):
        with patch(_TRANSCRIBE, return_value="   "):
            result = perceive("audio/wav", b"x")
        self.assertEqual(result["status"], "unsupported")

    def test_transcription_error_fails_gracefully(self):
        with patch(_TRANSCRIBE, side_effect=TranscriptionError("boom", "temporarily unavailable")):
            result = perceive("audio/mpeg", b"x")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["text"], "")


class AudioPerceiveTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="aud@ex.com", password="x")

    def test_task_stores_transcript(self):
        art = MultimodalArtifact.objects.create(
            user=self.user, sha256="a" * 64, content_type="audio/mpeg", kind="audio",
            perception_status=MultimodalArtifact.PERCEPTION_PENDING,
        )
        with patch(_TRANSCRIBE, return_value="Action item: send the report Friday."):
            result = perceive_artifact(art.id, base64.b64encode(b"audio-bytes").decode())
        self.assertEqual(result["result"], "done")
        art.refresh_from_db()
        self.assertTrue(art.has_perception)
        self.assertIn("send the report Friday", art.extracted_text)


class TranscribeBytesConvergenceTests(TestCase):
    """The one shared capability: routing (direct vs convert) is correct, and
    Capture's own path reuses it."""

    def _service(self):
        from apps.capture.services.transcription import transcription_service
        transcription_service.client = object()  # force is_available True
        return transcription_service

    def test_direct_format_skips_conversion(self):
        svc = self._service()
        with patch.object(svc, "_call_whisper_api", return_value="ok") as whisper, \
             patch.object(svc, "_compress_audio") as compress:
            out = svc.transcribe_bytes(b"small", "audio.mp3")
        self.assertEqual(out, "ok")
        compress.assert_not_called()   # mp3 is Whisper-native, small → no ffmpeg

    def test_non_whisper_format_converts(self):
        svc = self._service()
        with patch.object(svc, "_call_whisper_api", return_value="ok") as whisper, \
             patch.object(svc, "_compress_audio", return_value=(b"mp3", "audio.mp3")) as compress:
            svc.transcribe_bytes(b"aacdata", "audio.aac")
        compress.assert_called_once()  # AAC isn't Whisper-native → convert via ffmpeg
