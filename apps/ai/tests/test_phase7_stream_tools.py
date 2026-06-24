# ==============================================================================
# File: apps/ai/tests/test_phase7_stream_tools.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Phase 7 — CoS tool loop runs in the streaming/background path
# ==============================================================================
"""
Phase 7 — the ChatGPT CoS evidence-tool loop must run in the persistent /
background generation path (run_chat_generation -> send_message_stream ->
_generate_response_stream), so it survives navigation.

These tests drive _generate_response_stream directly with the context build and
OpenAI client mocked, and assert:
* flag OFF -> the existing token-streaming path (_call_api_stream) is used (unchanged);
* flag ON  -> the bounded tool loop (_call_api_with_tools) is used, and its final
  synthesized answer is yielded as a single chunk through the same generator the
  background task owns.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai.models import AssistantConversation, AssistantMessage
from apps.ai.personal_assistant import PersonalAssistant

User = get_user_model()

_CTX = {
    "system_prompt": "sys",
    "user_prompt": "How am I doing?",
    "max_tokens": 800,
    "temperature": 0.7,
    "conversation_history": [],
    "briefing_built": False,
    "cos_context": {},
}


class Phase7StreamingToolLoopTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="p7@example.com", password="x")
        cls.conversation = AssistantConversation.objects.create(user=cls.user)

    def _drive(self):
        assistant = PersonalAssistant(self.user)
        am = AssistantMessage.objects.create(
            conversation=self.conversation, role="assistant", content="",
        )
        # Stub the deferred-warming background thread (it writes UserState async,
        # which would FK-violate after the test transaction rolls back).
        with mock.patch.object(PersonalAssistant, "_run_deferred_context",
                               return_value=None):
            chunks = list(assistant._generate_response_stream(
                "How am I doing?", self.conversation, assistant_message=am,
            ))
        am.refresh_from_db()
        return chunks, am

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
    def test_flag_off_uses_streaming_path(self):
        with mock.patch.object(PersonalAssistant, "_build_fast_context",
                               return_value=dict(_CTX)), \
             mock.patch("apps.ai.services.ai_service._call_api_stream",
                        return_value=iter(["Doing ", "well."])) as stream_fn, \
             mock.patch("apps.ai.services.ai_service._call_api_with_tools") as tools_fn:
            chunks, am = self._drive()
        self.assertEqual("".join(chunks), "Doing well.")
        stream_fn.assert_called_once()
        tools_fn.assert_not_called()
        self.assertEqual(am.content, "Doing well.")

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=True)
    def test_flag_on_uses_tool_loop_in_stream(self):
        with mock.patch.object(PersonalAssistant, "_build_fast_context",
                               return_value=dict(_CTX)), \
             mock.patch("apps.ai.services.ai_service._call_api_stream") as stream_fn, \
             mock.patch("apps.ai.services.ai_service._call_api_with_tools",
                        return_value="You're on track.") as tools_fn:
            chunks, am = self._drive()
        # Tool loop ran (in the generator the background task owns) and its final
        # synthesized answer was delivered as one chunk.
        self.assertEqual("".join(chunks), "You're on track.")
        tools_fn.assert_called_once()
        stream_fn.assert_not_called()
        self.assertEqual(am.content, "You're on track.")

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=True)
    def test_flag_on_passes_tools_and_dispatch(self):
        with mock.patch.object(PersonalAssistant, "_build_fast_context",
                               return_value=dict(_CTX)), \
             mock.patch("apps.ai.services.ai_service._call_api_with_tools",
                        return_value="ok") as tools_fn:
            self._drive()
        kwargs = tools_fn.call_args.kwargs
        # tools advertised + a callable dispatch were passed
        self.assertTrue(kwargs.get("tools"))
        self.assertTrue(callable(kwargs.get("dispatch")))
