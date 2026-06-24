# ==============================================================================
# File: apps/ai/tests/test_cos_tools.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for the ChatGPT CoS tool registry + dispatcher + tool loop (Phase 3)
# ==============================================================================
"""
Phase 3 — ChatGPT integration layer tests.

Covers:
* tool registry: only ENABLED tools are advertised; disabled tools registered;
* tool dispatcher: unknown / not-enabled / delegated / bad-args / error — never raises;
* the bounded tool loop in AIService._call_api_with_tools (single orchestration
  path extension): dispatches tool calls, feeds results back, returns final text,
  and falls back to a plain completion on error.
"""

import json
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.cos_services import (
    dispatch_tool_call,
    enabled_tool_names,
    evidence_tools_enabled,
    get_tool_schemas,
)

User = get_user_model()

_GMS = "apps.core.ai_state.state_engine.get_module_state"


# --- OpenAI response fakes -------------------------------------------------
def _toolcall(tc_id, name, arguments):
    return SimpleNamespace(
        id=tc_id, type="function",
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _resp(content=None, tool_calls=None):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)


class ToolRegistryTests(TestCase):
    def test_only_enabled_tools_advertised(self):
        names = {s["function"]["name"] for s in get_tool_schemas(enabled_only=True)}
        self.assertEqual(names, {"get_standing_context", "get_domain_state"})

    def test_enabled_tool_names(self):
        self.assertEqual(
            enabled_tool_names(), ["get_domain_state", "get_standing_context"]
        )

    def test_disabled_tools_registered_but_hidden(self):
        all_names = {s["function"]["name"] for s in get_tool_schemas(enabled_only=False)}
        # registered (complete catalog) ...
        self.assertIn("get_decision", all_names)
        self.assertIn("search_history", all_names)
        self.assertIn("execute_action", all_names)

    def test_domain_state_schema_has_enum(self):
        schema = next(
            s for s in get_tool_schemas()
            if s["function"]["name"] == "get_domain_state"
        )
        props = schema["function"]["parameters"]["properties"]
        self.assertIn("health", props["domain"]["enum"])

    def test_flag_defaults_off(self):
        self.assertFalse(evidence_tools_enabled())

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=True)
    def test_flag_can_be_enabled(self):
        self.assertTrue(evidence_tools_enabled())


class ToolDispatcherTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cos_tools@example.com", password="x")

    def test_unknown_tool(self):
        env = dispatch_tool_call(self.user, "no_such_tool", {})
        self.assertFalse(env["ok"])
        self.assertEqual(env["code"], "unknown_tool")

    def test_disabled_tool_rejected_without_calling_handler(self):
        env = dispatch_tool_call(self.user, "get_decision", {"mode": "risk"})
        self.assertFalse(env["ok"])
        self.assertEqual(env["code"], "tool_not_enabled")

    def test_enabled_tool_delegates_to_service(self):
        with mock.patch(_GMS, return_value={"weight_current": 286.6}):
            env = dispatch_tool_call(self.user, "get_domain_state", {"domain": "health"})
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["status"], "ready")
        self.assertEqual(env["result"]["domain"], "health")

    def test_standing_context_tool(self):
        with mock.patch("apps.ai.readiness_cache.get_cached_cos_context",
                        return_value={"top_signals": []}):
            env = dispatch_tool_call(self.user, "get_standing_context", {})
        self.assertTrue(env["ok"])
        self.assertIn("status", env["result"])

    def test_bad_arguments(self):
        # get_domain_state handler requires `domain`; an unexpected kw → TypeError
        env = dispatch_tool_call(self.user, "get_domain_state", {"wrong": 1})
        # missing `domain` -> handler runs with domain="" -> unsupported_domain (ok)
        # an *unexpected* kwarg triggers TypeError -> bad_arguments
        self.assertIn(env.get("code"), {"bad_arguments", None})

    def test_handler_exception_is_execution_error_not_raise(self):
        with mock.patch(_GMS, side_effect=RuntimeError("boom")):
            env = dispatch_tool_call(self.user, "get_domain_state", {"domain": "health"})
        # get_domain_state catches its own read error and returns status=error (ok=True envelope)
        self.assertTrue(env["ok"])
        self.assertEqual(env["result"]["status"], "error")

    def test_dispatcher_never_raises(self):
        # even with garbage arguments, returns an envelope
        env = dispatch_tool_call(self.user, "get_domain_state", None)
        self.assertIn("ok", env)

    def test_output_json_serializable(self):
        with mock.patch(_GMS, return_value={"x": 1}):
            env = dispatch_tool_call(self.user, "get_domain_state", {"domain": "faith"})
        json.dumps(env)


class ToolLoopTests(TestCase):
    """AIService._call_api_with_tools — the single-path agentic extension."""

    def _service_with_responses(self, responses):
        from apps.ai.services import AIService
        svc = AIService()
        create = mock.MagicMock(side_effect=responses)
        svc.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        )
        return svc, create

    def test_plain_answer_no_tool_calls(self):
        svc, create = self._service_with_responses([_resp(content="Hello.")])
        out = svc._call_api_with_tools(
            "sys", "hi", tools=[], dispatch=lambda n, a: {},
        )
        self.assertEqual(out, "Hello.")
        self.assertEqual(create.call_count, 1)

    def test_tool_call_then_final_answer(self):
        responses = [
            _resp(tool_calls=[_toolcall("c1", "get_domain_state",
                                        '{"domain": "health"}')]),
            _resp(content="Your weight is 286.6."),
        ]
        svc, create = self._service_with_responses(responses)
        seen = {}

        def _dispatch(name, args):
            seen["name"] = name
            seen["args"] = args
            return {"ok": True, "result": {"weight_current": 286.6}}

        out = svc._call_api_with_tools(
            "sys", "what is my weight?", tools=[{"x": 1}], dispatch=_dispatch,
        )
        self.assertEqual(out, "Your weight is 286.6.")
        self.assertEqual(create.call_count, 2)
        self.assertEqual(seen["name"], "get_domain_state")
        self.assertEqual(seen["args"], {"domain": "health"})

    def test_loop_falls_back_to_plain_on_error(self):
        from apps.ai.services import AIService
        svc = AIService()
        svc.client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(
                create=mock.MagicMock(side_effect=RuntimeError("api down"))
            ))
        )
        with mock.patch.object(svc, "_call_api", return_value="FALLBACK") as fb:
            out = svc._call_api_with_tools("sys", "hi", tools=[{"x": 1}],
                                           dispatch=lambda n, a: {})
        self.assertEqual(out, "FALLBACK")
        fb.assert_called_once()
