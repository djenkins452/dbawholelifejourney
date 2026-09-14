# ==============================================================================
# File: apps/core/tests/test_governor_refusal_is_a_decision.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: A cost-governor refusal is never retried and never disguised as empty
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-09-14
# ==============================================================================
"""Production, 2026-09-14. Proactive assistance was ON in the UI and Clara said nothing.

Thirty check-in decision rows that morning, every one `empty`. Not `refused` — `empty`.
The gate WAS refusing (correctly; the operator hold was in place), but `_call_api` caught
`RealLLMCallDenied` as a generic provider error, slept and retried it with exponential
backoff, logged "LLM FAILED", and returned None. `author_checkin` therefore recorded
`empty`, and an intentional hold became indistinguishable from a broken pipeline — which is
exactly the state the product must never be in.

A refusal is a decision, not a failure. No provider is called in this file.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.llm_admission import RealLLMCallDenied

User = get_user_model()


class _RefusingClient:
    """A guarded client whose only behaviour is to refuse."""

    class chat:
        class completions:
            calls = 0

            @classmethod
            def create(cls, **kw):
                cls.calls += 1
                raise RealLLMCallDenied("proactive_ai_disabled")


class CallApiRefusalTests(SimpleTestCase):
    def _service(self):
        from apps.ai.services import AIService
        service = AIService()
        _RefusingClient.chat.completions.calls = 0
        service.client = _RefusingClient()
        service.model = "test"
        return service

    def test_a_refusal_is_not_retried(self):
        service = self._service()
        with mock.patch("apps.ai.services.time.sleep") as sleep:
            out = service._call_api("sys", "user", endpoint="proactive_checkin")
        self.assertIsNone(out)
        self.assertEqual(_RefusingClient.chat.completions.calls, 1,
                         "the governor was asked the same question again")
        sleep.assert_not_called()

    def test_a_refusal_is_not_logged_as_a_provider_failure(self):
        service = self._service()
        with self.assertLogs("apps.ai.services", level="INFO") as logs:
            service._call_api("sys", "user", endpoint="proactive_checkin")
        joined = "\n".join(logs.output)
        self.assertIn("REFUSED BY GOVERNOR", joined)
        self.assertNotIn("LLM FAILED", joined,
                         "a governor decision was logged as a provider outage")

    def test_the_default_contract_is_unchanged_for_existing_callers(self):
        """Seventeen callers expect text-or-None. They still get None."""
        self.assertIsNone(self._service()._call_api("sys", "user"))

    def test_a_caller_that_needs_the_distinction_can_have_it(self):
        with self.assertRaises(RealLLMCallDenied):
            self._service()._call_api("sys", "user", raise_on_refusal=True)

    def test_a_genuine_provider_error_still_retries(self):
        """Removing the refusal from the retry path must not remove retries."""
        from apps.ai.services import AIService

        class _Flaky:
            class chat:
                class completions:
                    calls = 0

                    @classmethod
                    def create(cls, **kw):
                        cls.calls += 1
                        raise RuntimeError("transient")

        service = AIService()
        service.client = _Flaky()
        service.model = "test"
        with mock.patch("apps.ai.services.time.sleep"):
            self.assertIsNone(service._call_api("sys", "user"))
        self.assertGreater(_Flaky.chat.completions.calls, 1)


class CheckinAuditsRefusalTests(TestCase):
    """The audit row must say `refused`, so silence can be read as a hold — not a bug."""

    def setUp(self):
        self.user = User.objects.create_user(email="held@contract.test", password="x")

    LIVE = {"execution_state": {"overdue": [{"title": "x"}], "due_now": [],
                                "coming_up": [], "later": [], "completed": []}}

    def test_a_governor_refusal_is_recorded_as_refused_not_empty(self):
        from apps.ai import checkin_author as ca
        from apps.ai.models import ToolCallLog

        def _refuse(*a, **kw):
            if kw.get("raise_on_refusal"):
                raise RealLLMCallDenied("proactive_ai_disabled")
            return None

        with mock.patch("apps.ai.model_interface.service.ModelInterfaceService"
                        ".build_standing_context", return_value=self.LIVE), \
             mock.patch("apps.ai.services.ai_service._call_api", side_effect=_refuse):
            text = ca.author_checkin(self.user)
        self.assertEqual(text, "")
        row = ToolCallLog.objects.filter(user=self.user, kind="checkin").latest("id")
        self.assertEqual(row.result_status, "refused",
                         "an intentional hold was audited as if the model returned nothing")

    def test_the_author_actually_asks_for_the_distinction(self):
        import inspect

        from apps.ai import checkin_author as ca
        self.assertIn("raise_on_refusal=True", inspect.getsource(ca.author_checkin))


class ProactiveGateIsObservableTests(SimpleTestCase):
    """The flag's value must be readable from the runtime that evaluates it — never
    inferred from whether calls were refused. Both inferences have already been wrong."""

    def test_the_gate_is_declared_in_the_configuration_contract(self):
        from apps.core.config_governance import contract
        spec = contract.by_name().get("WLJ_PROACTIVE_AI_ENABLED")
        self.assertIsNotNone(spec, "the operator hold is invisible to config governance")
        self.assertEqual(spec.classification, contract.CLASS_CONFIG)
        self.assertIn(contract.SERVICE_WORKER, spec.required_services)

    def test_the_probe_reports_the_evaluated_gate(self):
        import inspect

        from apps.admin_console import views
        src = inspect.getsource(views.TruthProbeAPIView)
        self.assertIn("proactive_ai_enabled()", src)
        self.assertIn("proactive_gate", src)
