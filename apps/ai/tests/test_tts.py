"""
Tests for Text-to-Speech (TTS) Service & API Endpoint.

Project: Whole Life Journey
Path: apps/ai/tests/test_tts.py
"""

import json
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, RequestFactory

User = get_user_model()


class CleanTextForSpeechTests(TestCase):
    """Tests for markdown/emoji cleanup before TTS."""

    def test_strips_bold(self):
        from apps.ai.tts_service import clean_text_for_speech
        self.assertEqual(clean_text_for_speech("This is **bold** text"), "This is bold text")

    def test_strips_italic(self):
        from apps.ai.tts_service import clean_text_for_speech
        self.assertEqual(clean_text_for_speech("This is *italic* text"), "This is italic text")

    def test_strips_headers(self):
        from apps.ai.tts_service import clean_text_for_speech
        result = clean_text_for_speech("## My Header\nSome text")
        self.assertNotIn("##", result)
        self.assertIn("My Header", result)

    def test_strips_bullet_points(self):
        from apps.ai.tts_service import clean_text_for_speech
        result = clean_text_for_speech("- Item one\n- Item two")
        self.assertNotIn("-", result)
        self.assertIn("Item one", result)

    def test_strips_markdown_links(self):
        from apps.ai.tts_service import clean_text_for_speech
        result = clean_text_for_speech("Visit [Google](https://google.com) today")
        self.assertIn("Google", result)
        self.assertNotIn("https://", result)

    def test_empty_string(self):
        from apps.ai.tts_service import clean_text_for_speech
        self.assertEqual(clean_text_for_speech(""), "")
        self.assertEqual(clean_text_for_speech(None), "")

    def test_collapses_whitespace(self):
        from apps.ai.tts_service import clean_text_for_speech
        result = clean_text_for_speech("Hello   world")
        self.assertEqual(result, "Hello world")


class GenerateSpeechTests(TestCase):
    """Tests for the core generate_speech function."""

    def test_empty_text_returns_none(self):
        from apps.ai.tts_service import generate_speech
        self.assertIsNone(generate_speech(""))
        self.assertIsNone(generate_speech("   "))
        self.assertIsNone(generate_speech(None))

    @patch("openai.OpenAI")
    def test_calls_openai_tts(self, mock_openai_cls):
        from apps.ai.tts_service import generate_speech

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = b"fake-mp3-bytes"
        mock_client.audio.speech.create.return_value = mock_response

        result = generate_speech("Hello world")

        self.assertEqual(result, b"fake-mp3-bytes")
        mock_client.audio.speech.create.assert_called_once()
        call_kwargs = mock_client.audio.speech.create.call_args[1]
        self.assertEqual(call_kwargs["model"], "tts-1")
        self.assertEqual(call_kwargs["voice"], "nova")
        self.assertEqual(call_kwargs["input"], "Hello world")
        self.assertEqual(call_kwargs["response_format"], "mp3")

    @patch("openai.OpenAI")
    def test_custom_voice(self, mock_openai_cls):
        from apps.ai.tts_service import generate_speech

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = b"audio"
        mock_client.audio.speech.create.return_value = mock_response

        generate_speech("Hello", voice="echo")
        call_kwargs = mock_client.audio.speech.create.call_args[1]
        self.assertEqual(call_kwargs["voice"], "echo")

    @patch("openai.OpenAI")
    def test_invalid_voice_falls_back_to_default(self, mock_openai_cls):
        from apps.ai.tts_service import generate_speech

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = b"audio"
        mock_client.audio.speech.create.return_value = mock_response

        generate_speech("Hello", voice="nonexistent_voice")
        call_kwargs = mock_client.audio.speech.create.call_args[1]
        self.assertEqual(call_kwargs["voice"], "nova")

    @patch("openai.OpenAI")
    def test_speed_clamped(self, mock_openai_cls):
        from apps.ai.tts_service import generate_speech

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = b"audio"
        mock_client.audio.speech.create.return_value = mock_response

        generate_speech("Hello", speed=10.0)
        call_kwargs = mock_client.audio.speech.create.call_args[1]
        self.assertEqual(call_kwargs["speed"], 4.0)

        generate_speech("Hello", speed=0.01)
        call_kwargs = mock_client.audio.speech.create.call_args[1]
        self.assertEqual(call_kwargs["speed"], 0.25)

    @patch("openai.OpenAI")
    def test_truncates_long_text(self, mock_openai_cls):
        from apps.ai.tts_service import generate_speech, MAX_INPUT_LENGTH

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.content = b"audio"
        mock_client.audio.speech.create.return_value = mock_response

        long_text = "x" * 5000
        generate_speech(long_text)
        call_kwargs = mock_client.audio.speech.create.call_args[1]
        self.assertEqual(len(call_kwargs["input"]), MAX_INPUT_LENGTH)

    @patch("openai.OpenAI")
    def test_returns_none_on_api_failure(self, mock_openai_cls):
        from apps.ai.tts_service import generate_speech

        mock_openai_cls.side_effect = Exception("API down")
        result = generate_speech("Hello")
        self.assertIsNone(result)


class GenerateSpeechBase64Tests(TestCase):
    """Tests for base64 wrapper."""

    @patch("apps.ai.tts_service.generate_speech")
    def test_returns_base64_string(self, mock_gen):
        from apps.ai.tts_service import generate_speech_base64
        import base64

        mock_gen.return_value = b"fake-audio"
        result = generate_speech_base64("Hello")
        self.assertIsNotNone(result)
        # Verify it's valid base64
        decoded = base64.b64decode(result)
        self.assertEqual(decoded, b"fake-audio")

    @patch("apps.ai.tts_service.generate_speech")
    def test_returns_none_on_failure(self, mock_gen):
        from apps.ai.tts_service import generate_speech_base64

        mock_gen.return_value = None
        result = generate_speech_base64("Hello")
        self.assertIsNone(result)


class AudioDataUrlTests(TestCase):
    """Tests for data URL builder."""

    def test_builds_correct_data_url(self):
        from apps.ai.tts_service import get_audio_data_url

        result = get_audio_data_url("abc123")
        self.assertEqual(result, "data:audio/mpeg;base64,abc123")


class VoiceChoicesTests(TestCase):
    """Tests for voice constants."""

    def test_default_voice_in_choices(self):
        from apps.ai.tts_service import DEFAULT_VOICE, VOICE_CHOICES
        self.assertIn(DEFAULT_VOICE, VOICE_CHOICES)

    def test_six_voices_available(self):
        from apps.ai.tts_service import VOICE_CHOICES
        self.assertEqual(len(VOICE_CHOICES), 6)


class TextToSpeechViewTests(TestCase):
    """Tests for the TTS API endpoint."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="ttsuser@test.com",
            password="testpass123",
        )
        # Satisfy TermsAcceptance & onboarding middleware
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.get_or_create(
            user=self.user,
            defaults={
                'terms_version': settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
            },
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.client.force_login(self.user)
        self.url = "/assistant/api/tts/"

    def test_requires_auth(self):
        self.client.logout()
        response = self.client.post(
            self.url,
            data=json.dumps({"text": "Hello"}),
            content_type="application/json",
        )
        # LoginRequiredMixin redirects to login
        self.assertIn(response.status_code, [302, 403])

    def test_rejects_get(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 405)

    def test_rejects_invalid_json(self):
        response = self.client.post(
            self.url,
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_rejects_empty_text(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"text": ""}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("required", response.json()["error"].lower())

    def test_rejects_missing_text(self):
        response = self.client.post(
            self.url,
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_invalid_voice(self):
        response = self.client.post(
            self.url,
            data=json.dumps({"text": "Hello", "voice": "invalid_voice"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid voice", response.json()["error"])

    @patch("apps.ai.tts_service.generate_speech_base64")
    def test_success_returns_audio(self, mock_gen):
        mock_gen.return_value = "dGVzdA=="  # base64 of "test"

        response = self.client.post(
            self.url,
            data=json.dumps({"text": "Hello world"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["audio"], "dGVzdA==")
        self.assertEqual(data["content_type"], "audio/mpeg")

    @patch("apps.ai.tts_service.generate_speech_base64")
    def test_returns_502_on_generation_failure(self, mock_gen):
        mock_gen.return_value = None

        response = self.client.post(
            self.url,
            data=json.dumps({"text": "Hello world"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 502)
        self.assertIn("failed", response.json()["error"].lower())

    @patch("apps.ai.tts_service.generate_speech_base64")
    def test_passes_voice_and_speed(self, mock_gen):
        mock_gen.return_value = "audio=="

        self.client.post(
            self.url,
            data=json.dumps({"text": "Hello", "voice": "echo", "speed": 1.5}),
            content_type="application/json",
        )
        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        self.assertEqual(kwargs.get("voice"), "echo")
        self.assertEqual(kwargs.get("speed"), 1.5)

    @patch("apps.ai.tts_service.generate_speech_base64")
    def test_cleans_markdown_before_speech(self, mock_gen):
        mock_gen.return_value = "audio=="

        response = self.client.post(
            self.url,
            data=json.dumps({"text": "This is **bold** text"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(mock_gen.called, "generate_speech_base64 was not called")
        # The cleaned text (no bold markers) should be passed
        call_args = mock_gen.call_args[0]
        self.assertNotIn("**", call_args[0])
        self.assertIn("bold", call_args[0])
