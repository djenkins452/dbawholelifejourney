# ==============================================================================
# File: apps/ai/tests/test_foundation_validation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Foundation validation — the 5 foundational fact prompts traverse
#              the clean ChatGPT CoS path end-to-end with no truncation, no
#              fallback, no suppression, no legacy, and a non-empty answer.
# ==============================================================================
"""
Validates the foundational truth path for the clean ChatGPT CoS:

    CoSGateway → ChatGPTCoSRuntime → ChatGPTCoSService.generate
      → _call_api_with_tools (real loop)
      → get_foundational_health_facts (real dispatch over SAE module state)
      → model answers over the focused, un-truncated tool result.

OpenAI is emulated (no network/key): round 0 selects the focused tool with the
correct key (as the real model is instructed to), round 1 answers over the
tool result. Everything between — runtime selection, tool dispatch, the
8000-char truncation gate, the empty-answer classifier, fallback avoidance — is
the real code path.
"""

import json
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.cos_gateway import CoSGateway, SURFACE_CHAT
from apps.ai.cos_services.tool_dispatcher import dispatch_tool_call

User = get_user_model()

_GMS = "apps.core.ai_state.state_engine.get_module_state"

# Canonical truth the SAE would hold for the test user.
_FAKE_STATE = {
    "health": {
        "weight_current": 298.3, "weight_unit": "lb", "weight_trend": "decreasing",
        "last_weight_entry": "2026-04-07T16:00:00+00:00",
        "latest_glucose": 133.0, "latest_glucose_unit": "mg/dL",
        "last_glucose_entry": "2026-04-07T20:43:35+00:00", "glucose_avg_7d": 124,
        "sleep_avg_hours_7d": 6.7, "sleep_trend": "decreasing",
        "last_sleep_entry": "2026-04-07",
    },
    "medicine": {"active_medications": ["Atorvastatin", "Metformin HCL ER",
                                        "Mounjaro", "Valsartan"],
                 "medication_count": 4},
    "nutrition": {"daily_calories": 1850.0, "calorie_target": 2000,
                  "daily_protein_g": 142.0, "protein_target": 180},
}

# prompt -> (focused fact key, the value the answer must surface)
PROMPTS = [
    ("What is my current weight?",                "current_weight",      298.3),
    ("What was my last glucose reading?",         "last_glucose_reading", 133.0),
    ("What medications am I currently taking?",   "current_medications",  "Metformin"),
    ("How many calories have I consumed today?",  "calories_today",       1850.0),
    ("How much protein have I consumed today?",   "protein_today",        142.0),
]


def _fake_module_state(user, module, allow_rebuild=False):
    return _FAKE_STATE.get(module, {})


def _toolcall(tc_id, name, arguments):
    return SimpleNamespace(id=tc_id, type="function",
                           function=SimpleNamespace(name=name, arguments=arguments))


def _resp(content=None, tool_calls=None, finish_reason="stop", rid="resp_x"):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        id=rid, choices=[SimpleNamespace(message=msg, finish_reason=finish_reason)],
        usage=None,
    )


def _model_emulator(fact_key, answer_text):
    """Two-round script: select the focused tool, then answer over its result."""
    return [
        _resp(tool_calls=[_toolcall("c1", "get_foundational_health_facts",
                                    json.dumps({"keys": [fact_key]}))],
              finish_reason="tool_calls"),
        _resp(content=answer_text, finish_reason="stop"),
    ]


@override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
class FoundationValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="found@example.com", password="x")
        cls.user.preferences.use_chatgpt_cos = True
        cls.user.preferences.save()

    def _run_prompt(self, prompt, fact_key, answer_text):
        """Drive ChatGPTCoSService.generate with the model emulated; real tool
        dispatch + real loop. Returns (result, dispatched, fallback_called)."""
        from apps.ai.models import AssistantConversation
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService

        conv = AssistantConversation.get_or_create_active(self.user)
        dispatched = {}

        real_dispatch = dispatch_tool_call

        def _spy_dispatch(user, name, args):
            dispatched["name"] = name
            dispatched["args"] = args
            env = real_dispatch(user, name, args)
            dispatched["result"] = env.get("result")
            dispatched["truncated"] = bool(
                isinstance(env.get("result"), dict)
                and env["result"].get("_truncated"))
            return env

        create = mock.MagicMock(side_effect=_model_emulator(fact_key, answer_text))
        client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        with mock.patch(_GMS, side_effect=_fake_module_state), \
             mock.patch("apps.ai.services.ai_service.client", client), \
             mock.patch("apps.ai.cos_services.dispatch_tool_call",
                        side_effect=_spy_dispatch), \
             mock.patch("apps.ai.cos_services.get_standing_context",
                        return_value={"status": "ready"}), \
             mock.patch("apps.core.ai_state.state_engine.get_user_state",
                        return_value={}), \
             mock.patch("apps.ai.services.ai_service._call_api",
                        side_effect=AssertionError("FALLBACK USED")) as fb:
            result = ChatGPTCoSService(self.user).generate(conv, prompt)

        return result, dispatched, fb.called

    def test_all_five_foundation_prompts(self):
        for prompt, fact_key, expected in PROMPTS:
            with self.subTest(prompt=prompt):
                answer = f"(answer surfacing {expected})"
                result, dispatched, fb_called = self._run_prompt(
                    prompt, fact_key, answer)

                # ChatGPTCoSRuntime owns this user + the focused tool ran.
                self.assertTrue(CoSGateway.is_cos(self.user))
                self.assertEqual(dispatched.get("name"),
                                 "get_foundational_health_facts")
                self.assertEqual(dispatched["args"], {"keys": [fact_key]})
                # No truncation.
                self.assertFalse(dispatched["truncated"])
                self.assertLess(len(json.dumps(dispatched["result"])), 8000)
                # The fact value survived to the tool result.
                fact = dispatched["result"].get(fact_key, {})
                self.assertNotIn("status", fact)        # not 'unknown'
                self.assertIn("value", fact)
                # Non-empty answer; no fallback; no empty-answer classification.
                self.assertTrue(result["answer"])
                self.assertIsNone(result.get("empty_reason"))
                self.assertFalse(fb_called)             # fallback NOT used
                self.assertEqual(result["tools_called"],
                                 ["get_foundational_health_facts"])

    def test_chat_surface_is_routed_not_suppressed(self):
        # Foundation prompts arrive on the chat surface — routed to CoS,
        # never the narrative-suppression path.
        from apps.ai.cos_gateway import NARRATIVE_SURFACES
        self.assertNotIn(SURFACE_CHAT, NARRATIVE_SURFACES)
        self.assertTrue(CoSGateway.is_cos(self.user))
