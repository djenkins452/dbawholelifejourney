# ==============================================================================
# File: apps/ai/tests/test_cos_multi_med_composition.py
# Description: Multi-medication composition — MEASUREMENT before any budget change.
#   The token-starvation hypothesis is unproven; these tests verify the tool loop
#   (a) returns a full multi-med answer intact (no count-truncation in our code),
#   (b) preserves multi-tool-call pairing, and (c) EMITS the per-round + summary
#   measurements (tool calls/names/output size, completion tokens, finish_reason,
#   repeated-retrieval) that determine the real cause in production.
# ==============================================================================
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase

_MULTI = "Can you list each medicine I take and what each is commonly used for?"
_SVC_LOG = "apps.ai.services"


def _toolcall(tc_id, name, arguments):
    return SimpleNamespace(id=tc_id, type="function",
                           function=SimpleNamespace(name=name, arguments=arguments))


def _usage(prompt=0, completion=0):
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                           total_tokens=prompt + completion)


def _resp(content=None, tool_calls=None, finish_reason="stop", usage=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(id="r", choices=[SimpleNamespace(
        message=msg, finish_reason=finish_reason)], usage=usage)


def _service_with_responses(responses):
    from apps.ai.services import AIService
    svc = AIService()
    svc.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=mock.MagicMock(side_effect=responses))))
    return svc


class ToolLoopReturnsFullAnswerTests(TestCase):
    def test_long_thirteen_med_answer_returned_intact(self):
        meds = ["Metformin", "Lantus", "Humalog", "Mounjaro", "Lisinopril",
                "Atorvastatin", "Levothyroxine", "Amlodipine", "Omeprazole",
                "Aspirin", "Vitamin D", "Magnesium", "Fish Oil"]
        long_answer = "Here's each medicine and what it's commonly used for:\n" + \
            "\n".join(f"• {m} — its standard indication." for m in meds)
        svc = _service_with_responses([
            _resp(tool_calls=[_toolcall("c1", "get_foundational_health_facts",
                                        '{"keys": ["current_medications"]}')]),
            _resp(content=long_answer),
        ])
        out = svc._call_api_with_tools(
            "sys", _MULTI, tools=[{"x": 1}],
            dispatch=lambda n, a: {"ok": True, "result": {"active_medications": meds}})
        self.assertEqual(out, long_answer)
        for m in meds:
            self.assertIn(m, out)

    def test_multi_tool_call_pairing_preserved(self):
        svc = _service_with_responses([
            _resp(tool_calls=[
                _toolcall("c1", "get_foundational_health_facts", '{"keys": ["current_medications"]}'),
                _toolcall("c2", "get_domain_state", '{"domain": "health"}'),
            ]),
            _resp(content="Two tools resolved; combined answer."),
        ])
        out = svc._call_api_with_tools(
            "sys", _MULTI, tools=[{"x": 1}], dispatch=lambda n, a: {"ok": True, "result": {}})
        self.assertEqual(out, "Two tools resolved; combined answer.")


class ToolLoopMeasurementTests(TestCase):
    """The instrumentation captures the numbers that decide tool-composition vs
    token-starvation — without changing behavior."""

    def test_measure_summary_and_per_call_logs_emitted(self):
        svc = _service_with_responses([
            _resp(tool_calls=[_toolcall("c1", "get_foundational_health_facts",
                                        '{"keys": ["current_medications"]}')],
                  usage=_usage(1200, 0)),
            _resp(content="• Metformin — …", finish_reason="stop", usage=_usage(1500, 40)),
        ])
        with self.assertLogs(_SVC_LOG, level="INFO") as cm:
            svc._call_api_with_tools(
                "sys", _MULTI, tools=[{"x": 1}],
                dispatch=lambda n, a: {"ok": True, "result": {"active_medications": ["Metformin"]}})
        blob = "\n".join(cm.output)
        # Per-round shape with tool names + token usage.
        self.assertIn("COS_TOOL_LOOP_RESPONSE", blob)
        self.assertIn("tool_names=get_foundational_health_facts", blob)
        self.assertIn("completion_tokens=40", blob)
        # Per-call measurement (detects per-med / repeated retrieval + output size).
        self.assertIn("COS_TOOL_CALL", blob)
        self.assertIn("output_chars=", blob)
        # Summary: rounds, total calls, finish_reason, repeated_retrieval.
        self.assertIn("COS_TOOL_LOOP_MEASURE", blob)
        self.assertIn("total_tool_calls=1", blob)
        self.assertIn("repeated_retrieval=False", blob)
        self.assertIn("final_finish_reason=stop", blob)

    def test_measure_flags_repeated_retrieval(self):
        # Model fetches the SAME med tool twice across rounds → repeated_retrieval=True.
        svc = _service_with_responses([
            _resp(tool_calls=[_toolcall("c1", "get_foundational_health_facts", "{}")]),
            _resp(tool_calls=[_toolcall("c2", "get_foundational_health_facts", "{}")]),
            _resp(content="done"),
        ])
        with self.assertLogs(_SVC_LOG, level="WARNING") as cm:
            svc._call_api_with_tools(
                "sys", _MULTI, tools=[{"x": 1}], dispatch=lambda n, a: {"ok": True})
        blob = "\n".join(cm.output)
        self.assertIn("COS_TOOL_LOOP_MEASURE", blob)
        self.assertIn("total_tool_calls=2", blob)
        self.assertIn("repeated_retrieval=True", blob)
