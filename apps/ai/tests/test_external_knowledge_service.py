# ==============================================================================
# File: apps/ai/tests/test_external_knowledge_service.py
# Description: The "external knowledge service" is OpenAI (AIService._call_api).
#   General/educational answers REQUIRE it (no offline KB by design). These tests
#   pin the designed degradation (service down → graceful message, no crash) AND
#   that once OpenAI is reachable, general medication education answers — proving
#   the only missing piece in production is a configured/valid OPENAI_API_KEY.
# ==============================================================================
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.chatgpt_cos.lanes import general_answer

User = get_user_model()

_CALL_API = "apps.ai.services.ai_service._call_api"
_GEN_Q = "What is Metformin commonly used for?"


class ExternalKnowledgeAvailabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="eks@example.com", password="x")

    def test_service_unavailable_when_client_is_none(self):
        from apps.ai.services import AIService
        svc = AIService()
        svc.client = None
        self.assertFalse(svc.is_available)
        # With no client, _call_api short-circuits to None (the 'no API key' path).
        self.assertIsNone(svc._call_api("s", "u", endpoint="cos_chat"))

    def test_general_lane_unavailable_message_when_service_down(self):
        # _call_api returns None (service down) → the designed graceful degradation.
        with mock.patch(_CALL_API, return_value=None):
            out = general_answer(self.user, _GEN_Q)
        self.assertIsNotNone(out, f"{_GEN_Q!r} must route to the general lane")
        low = out["answer"].lower()
        self.assertIn("temporarily unavailable", low)
        # Never leaks personal-domain language during an outage.
        for leak in ("your goal", "your health", "your weight"):
            self.assertNotIn(leak, low)

    def test_general_lane_answers_when_service_up(self):
        # Once OpenAI is reachable, the SAME question is answered from general
        # knowledge — proving the only missing piece is a valid OPENAI_API_KEY.
        educational = ("Metformin is commonly used to help lower blood sugar in "
                       "people with type 2 diabetes.")
        with mock.patch(_CALL_API, return_value=educational):
            out = general_answer(self.user, _GEN_Q)
        self.assertEqual(out["answer"], educational)
        self.assertNotIn("temporarily unavailable", out["answer"].lower())


class DiagnosticCommandTests(TestCase):
    def _run(self):
        out = StringIO()
        call_command("diagnose_external_knowledge", stdout=out)
        return out.getvalue()

    @override_settings(OPENAI_API_KEY=None)
    def test_reports_missing_key_as_root_cause(self):
        output = self._run()
        self.assertIn("api_key_configured", output)
        self.assertIn("OPENAI_API_KEY is not set", output)
        self.assertIn("ENVIRONMENT issue", output)

    @override_settings(OPENAI_API_KEY="sk-test")
    def test_reports_configured_when_client_available(self):
        with mock.patch("apps.ai.services.AIService.is_available",
                        new_callable=mock.PropertyMock, return_value=True):
            output = self._run()
        self.assertRegex(output, r"client_initialized\s+=\s+True")
        self.assertIn("Configured and client initialized", output)
