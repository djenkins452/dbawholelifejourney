# ==============================================================================
# File: apps/ai/tests/test_cos_router_bypass.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Regression — ChatGPT CoS must reach the tool loop, not be
#              pre-empted by the deterministic router (the "same answer" bug)
# ==============================================================================
"""
Root cause (proven): in send_message_stream, the Shared Deterministic Router
(classify_and_route) returns a terminal `_direct_response` for reasoning/
decision/data queries (focus/risk/weight/faith) BEFORE _generate_response_stream
(the ChatGPT tool loop) runs. So enabling the CoS did nothing for those queries —
they were answered by the router (same morning-execution summary every time).

Fix: when evidence_tools_enabled(user) is True, the router's terminal response is
ignored so the message falls through to the tool loop.

These tests drive send_message_stream with the router and the LLM stream mocked:
* CoS OFF -> router terminal answer is used (legacy behavior, unchanged);
* CoS ON  -> router terminal answer is bypassed; the tool-loop stream runs.
"""

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.models import AssistantConversation
from apps.ai.personal_assistant import PersonalAssistant

User = get_user_model()

_ROUTER = "apps.ai.deterministic_router.classify_and_route"
_INFLIGHT = "apps.ai.idempotency.is_in_flight"
_RC1 = "apps.ai.readiness_cache.get_cached_cos_context"
_RC2 = "apps.ai.readiness_cache.get_layered_cos_context"

_ROUTER_ANSWER = "Good morning, Danny. Start with Drink Protein Shake."
_TOOL_ANSWER = "Your biggest risk right now is the 9:00 AM medication block."


def _terminal_route():
    # mimics a terminal deterministic route (e.g. decision/weight/briefing)
    return SimpleNamespace(
        is_terminal=True, response=_ROUTER_ANSWER, skip_intent=True,
        category="data_query", domain="health", route_name="decision_query",
    )


class CoSRouterBypassTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="bypass@example.com", password="x")
        cls.conversation = AssistantConversation.objects.create(user=cls.user)

    def _run(self, message):
        assistant = PersonalAssistant(self.user)
        fake_ai = mock.Mock()
        fake_ai.is_available = True
        with mock.patch(_INFLIGHT, return_value=None), \
             mock.patch(_RC1, return_value={"x": 1}), \
             mock.patch(_RC2, return_value={"x": 1}), \
             mock.patch("apps.ai.personal_assistant.ai_service", fake_ai), \
             mock.patch("apps.ai.personal_assistant.AIService.check_user_consent",
                        return_value=True), \
             mock.patch(_ROUTER, return_value=_terminal_route()), \
             mock.patch.object(PersonalAssistant, "_generate_response_stream",
                               return_value=iter([_TOOL_ANSWER])):
            tokens = []
            for ev in assistant.send_message_stream(message, self.conversation):
                if ev.get("type") == "token":
                    tokens.append(ev.get("content", ""))
        return "".join(tokens)

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
    def test_cos_off_router_answers_legacy_behavior(self):
        # legacy Beth: the deterministic router's terminal answer is used
        self.user.preferences.use_chatgpt_cos = False
        self.user.preferences.save()
        out = self._run("What is my biggest risk right now?")
        self.assertIn(_ROUTER_ANSWER, out)
        self.assertNotIn(_TOOL_ANSWER, out)

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
    def test_cos_on_reaches_tool_loop(self):
        # ChatGPT CoS: router terminal answer is bypassed -> tool loop runs
        self.user.preferences.use_chatgpt_cos = True
        self.user.preferences.save()
        self.user.refresh_from_db()
        out = self._run("What is my biggest risk right now?")
        self.assertIn(_TOOL_ANSWER, out)
        self.assertNotIn(_ROUTER_ANSWER, out)

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
    def test_cos_answer_not_overridden_by_locked_validator(self):
        # The flapping cause: the locked-facts validator replaced the CoS answer
        # with the deterministic morning summary when wording didn't match the
        # locked next-action. With CoS on, that override must NOT happen.
        self.user.preferences.use_chatgpt_cos = True
        self.user.preferences.save()

        assistant = PersonalAssistant(self.user)
        fake_ai = mock.Mock()
        fake_ai.is_available = True
        with mock.patch(_INFLIGHT, return_value=None), \
             mock.patch(_RC1, return_value={"x": 1}), \
             mock.patch(_RC2, return_value={"x": 1}), \
             mock.patch("apps.ai.personal_assistant.ai_service", fake_ai), \
             mock.patch("apps.ai.personal_assistant.AIService.check_user_consent",
                        return_value=True), \
             mock.patch(_ROUTER, return_value=_terminal_route()), \
             mock.patch.object(PersonalAssistant, "_generate_response_stream",
                               return_value=iter([_TOOL_ANSWER])), \
             mock.patch("apps.ai.cos_fact_statements.build_locked_facts",
                        return_value={}), \
             mock.patch("apps.core.ai_governance.validator_gate.validate_response",
                        return_value={"blocked": True, "response": _ROUTER_ANSWER,
                                      "violations": ["x"]}), \
             mock.patch("apps.ai.cos_truth_validator.validate_locked_facts",
                        return_value=(_ROUTER_ANSWER, [{"domain": "medications"}])), \
             mock.patch("apps.ai.cos_truth_validator.log_cos_debug_state"):
            tokens = []
            for ev in assistant.send_message_stream(
                "What is my biggest risk right now?", self.conversation,
            ):
                if ev.get("type") in ("token", "correction"):
                    tokens.append(ev.get("content", ""))
        joined = "".join(tokens)
        # CoS tool answer survives; legacy override did NOT replace it
        self.assertIn(_TOOL_ANSWER, joined)
        self.assertNotIn(_ROUTER_ANSWER, joined)

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
    def test_cos_on_for_each_reported_prompt(self):
        self.user.preferences.use_chatgpt_cos = True
        self.user.preferences.save()
        for prompt in (
            "What should I focus on today?",
            "What is my biggest risk right now?",
            "What is my current weight?",
            "How is my faith life?",
        ):
            out = self._run(prompt)
            self.assertIn(_TOOL_ANSWER, out, msg=f"{prompt!r} did not reach tool loop")
            self.assertNotIn(_ROUTER_ANSWER, out, msg=f"{prompt!r} was router-answered")
