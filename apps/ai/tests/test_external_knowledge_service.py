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


class _Status(Exception):
    """Fake OpenAI-style error carrying an HTTP status_code."""
    def __init__(self, status, message=""):
        super().__init__(message or f"status {status}")
        self.status_code = status


class APITimeoutError(Exception):
    pass


class APIConnectionError(Exception):
    pass


class ClassifyLlmErrorTests(TestCase):
    """The actual exception is mapped to ONE actionable category (status-first)."""

    def test_status_and_class_mapping(self):
        from apps.ai.services import classify_llm_error
        self.assertEqual(classify_llm_error(_Status(401)), "authentication")
        self.assertEqual(classify_llm_error(_Status(403)), "authorization")
        self.assertEqual(classify_llm_error(_Status(429, "Rate limit reached")), "rate_limit")
        self.assertEqual(classify_llm_error(
            _Status(429, "You exceeded your current quota, please check your billing")), "quota")
        self.assertEqual(classify_llm_error(_Status(404, "model not found")), "model")
        self.assertEqual(classify_llm_error(_Status(400, "bad request")), "bad_request")
        self.assertEqual(classify_llm_error(_Status(500, "server error")), "server")
        self.assertEqual(classify_llm_error(APITimeoutError("Request timed out")), "timeout")
        self.assertEqual(classify_llm_error(APIConnectionError("Connection error")), "network")
        self.assertEqual(classify_llm_error(None), "none")


class ProbeExternalKnowledgeTests(TestCase):
    """probe_external_knowledge surfaces the REAL outcome, never collapsed to None."""

    def test_no_client_is_configuration(self):
        from apps.ai.services import AIService
        svc = AIService()
        svc.client = None
        out = svc.probe_external_knowledge()
        self.assertFalse(out["ok"])
        self.assertEqual(out["classification"], "configuration")
        self.assertIn("no/invalid OPENAI_API_KEY", out["message"])

    def test_live_exception_is_captured_not_swallowed(self):
        from types import SimpleNamespace
        from apps.ai.services import AIService
        svc = AIService()
        boom = _Status(429, "You exceeded your current quota")
        svc.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=mock.MagicMock(side_effect=boom))))
        out = svc.probe_external_knowledge()
        self.assertFalse(out["ok"])
        self.assertEqual(out["exception_type"], "_Status")
        self.assertEqual(out["status_code"], 429)
        self.assertEqual(out["classification"], "quota")
        self.assertIn("quota", out["message"].lower())

    def test_call_api_logs_structured_exception(self):
        from types import SimpleNamespace
        from apps.ai.services import AIService
        svc = AIService()
        svc.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=mock.MagicMock(side_effect=_Status(401, "Invalid API key")))))
        with mock.patch("time.sleep"):  # don't actually back off
            with self.assertLogs("apps.ai.services", level="WARNING") as cm:
                result = svc._call_api("s", "u", endpoint="cos_chat")
        self.assertIsNone(result)  # still None to callers …
        blob = "\n".join(cm.output)
        # … but the REAL exception is now visible.
        self.assertIn("class=_Status", blob)
        self.assertIn("status=401", blob)
        self.assertIn("classify=authentication", blob)
        self.assertIn("LLM FAILED", blob)


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

    @override_settings(COS_MODEL="gpt-4o", OPENAI_MODEL="gpt-4o")
    def test_reports_model_alignment(self):
        output = self._run()
        self.assertRegex(output, r"general_lane_model\s+=\s+gpt-4o")
        self.assertRegex(output, r"tool_loop_model\s+=\s+gpt-4o")
        self.assertRegex(output, r"models_aligned\s+=\s+True")
        self.assertIn("use the SAME model (aligned)", output)

    @override_settings(COS_MODEL="cos-good", OPENAI_MODEL="openai-broken")
    def test_aligned_even_when_settings_differ(self):
        # Both CoS paths resolve to COS_MODEL, so they stay aligned regardless of
        # the (legacy) OPENAI_MODEL value — that's exactly what the fix guarantees.
        output = self._run()
        self.assertRegex(output, r"general_lane_model\s+=\s+cos-good")
        self.assertRegex(output, r"tool_loop_model\s+=\s+cos-good")
        self.assertRegex(output, r"models_aligned\s+=\s+True")
