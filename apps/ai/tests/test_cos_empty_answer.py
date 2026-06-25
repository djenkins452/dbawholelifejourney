# ==============================================================================
# File: apps/ai/tests/test_cos_empty_answer.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Proves WHY _call_api_with_tools can return empty, and that the
#              clean CoS path never silently degrades to "couldn't compose".
# ==============================================================================
"""
Empty-answer diagnostics for the clean ChatGPT CoS path.

Loop level (AIService._call_api_with_tools):
  Case 1 — tool call -> tool result -> final content  => answer_len > 0.
  Case 2 — tool call -> tool result -> EMPTY content   => "" + COS_TOOL_LOOP_EMPTY_FINAL.
  Case 3 — OpenAI raises -> fallback _call_api None     => None + COS_TOOL_LOOP_FALLBACK
                                                          + COS_PLAIN_FALLBACK_RESULT answer_len=0.

Service level (ChatGPTCoSService.generate): empty answers are classified
(model_empty_after_tools vs openai_fallback_empty), never silently empty.
"""

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()

_SVC_LOG = "apps.ai.services"


def _toolcall(tc_id, name, arguments):
    return SimpleNamespace(id=tc_id, type="function",
                           function=SimpleNamespace(name=name, arguments=arguments))


def _resp(content=None, tool_calls=None, finish_reason="stop", rid="resp_x"):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        id=rid, choices=[SimpleNamespace(message=msg, finish_reason=finish_reason)],
        usage=None,
    )


def _service_with_responses(responses):
    from apps.ai.services import AIService
    svc = AIService()
    create = mock.MagicMock(side_effect=responses)
    svc.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    return svc, create


class ToolLoopEmptyAnswerTests(TestCase):
    # Case 1 — healthy: tool call -> result -> final content.
    def test_case1_tool_then_final_content_nonempty(self):
        responses = [
            _resp(tool_calls=[_toolcall("c1", "get_foundational_health_facts",
                                        '{"keys": ["current_weight"]}')]),
            _resp(content="Your current weight is 285.9 lb."),
        ]
        svc, create = _service_with_responses(responses)
        with self.assertLogs(_SVC_LOG, level="WARNING") as cm:
            out = svc._call_api_with_tools(
                "sys", "what is my weight?", tools=[{"x": 1}],
                dispatch=lambda n, a: {"ok": True, "result": {"current_weight": 285.9}},
            )
        self.assertTrue(len(out) > 0)
        self.assertEqual(out, "Your current weight is 285.9 lb.")
        self.assertEqual(create.call_count, 2)
        # per-response telemetry present
        self.assertTrue(any("COS_TOOL_LOOP_RESPONSE" in m for m in cm.output))
        self.assertFalse(any("COS_TOOL_LOOP_EMPTY_FINAL" in m for m in cm.output))

    # Case 2 — model returns empty content on the answering round.
    def test_case2_empty_final_content_logs_and_returns_empty(self):
        responses = [
            _resp(tool_calls=[_toolcall("c1", "get_foundational_health_facts",
                                        '{"keys": ["current_weight"]}')]),
            _resp(content=""),  # empty final answer
        ]
        svc, _ = _service_with_responses(responses)
        with self.assertLogs(_SVC_LOG, level="WARNING") as cm:
            out = svc._call_api_with_tools(
                "sys", "what is my weight?", tools=[{"x": 1}],
                dispatch=lambda n, a: {"ok": True, "result": {"current_weight": 285.9}},
            )
        self.assertEqual(out, "")  # empty string, NOT None
        empty = [m for m in cm.output if "COS_TOOL_LOOP_EMPTY_FINAL" in m]
        self.assertTrue(empty)
        self.assertIn("last_tool_names=get_foundational_health_facts", empty[0])

    # Case 3 — OpenAI raises; fallback _call_api returns None.
    def test_case3_exception_then_fallback_none(self):
        from apps.ai.services import AIService
        svc = AIService()
        svc.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=mock.MagicMock(side_effect=RuntimeError("api down")))))
        with mock.patch.object(svc, "_call_api", return_value=None) as fb:
            with self.assertLogs(_SVC_LOG, level="WARNING") as cm:
                out = svc._call_api_with_tools(
                    "sys", "hi", tools=[{"x": 1}], dispatch=lambda n, a: {})
        self.assertIsNone(out)  # None, NOT ""
        fb.assert_called_once()
        self.assertTrue(any("COS_TOOL_LOOP_FALLBACK" in m and "RuntimeError" in m
                            for m in cm.output))
        self.assertTrue(any("COS_PLAIN_FALLBACK_RESULT answer_len=0" in m
                            for m in cm.output))


class GenerateEmptyReasonTests(TestCase):
    """ChatGPTCoSService.generate classifies empty answers; never silent."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cos_empty@example.com",
                                             password="x")

    def _generate_with_loop_return(self, loop_return):
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService
        svc = ChatGPTCoSService(self.user)
        with mock.patch.object(ChatGPTCoSService, "_history", return_value=[]), \
             mock.patch.object(ChatGPTCoSService, "_system_prompt", return_value="sys"), \
             mock.patch("apps.core.ai_state.state_engine.get_user_state",
                        return_value={}), \
             mock.patch("apps.ai.cos_services.get_standing_context",
                        return_value={"status": "ready"}), \
             mock.patch("apps.ai.cos_services.get_tool_schemas", return_value=[]), \
             mock.patch("apps.ai.chatgpt_cos.reasoning.answer_reasoning_question",
                        return_value=None), \
             mock.patch("apps.ai.services.ai_service._call_api_with_tools",
                        return_value=loop_return):
            # Non-foundational prompt so generate() exercises the tool loop
            # (foundational fact prompts take the deterministic fast path).
            return svc.generate(object(), "how am I doing overall?")

    def test_model_empty_after_tools(self):
        result = self._generate_with_loop_return("")
        self.assertEqual(result["answer"], "")
        self.assertEqual(result["empty_reason"], "model_empty_after_tools")

    def test_openai_fallback_empty(self):
        result = self._generate_with_loop_return(None)
        self.assertEqual(result["answer"], "")
        self.assertEqual(result["empty_reason"], "openai_fallback_empty")

    def test_nonempty_answer_has_no_empty_reason(self):
        result = self._generate_with_loop_return("Your weight is 285.9 lb.")
        self.assertEqual(result["answer"], "Your weight is 285.9 lb.")
        self.assertIsNone(result["empty_reason"])
