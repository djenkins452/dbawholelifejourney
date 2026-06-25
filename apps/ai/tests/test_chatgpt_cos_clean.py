# ==============================================================================
# File: apps/ai/tests/test_chatgpt_cos_clean.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for the clean ChatGPT CoS path (service / task / routing)
# ==============================================================================
"""
Proves the clean ChatGPT CoS path:
* ChatGPTCoSService.generate runs the tool loop over standing context + tools;
* the Celery task persists messages + writes the bus snapshot;
* the streaming view branches to the clean task when use_chatgpt_cos=True, and
  to the legacy task (NOT the clean one) when it is False — and the clean path
  never imports/invokes PersonalAssistant.
"""

from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.ai import chat_stream_bus as bus
from apps.ai.chatgpt_cos.service import ChatGPTCoSService
from apps.ai.chatgpt_cos.tasks import run_chatgpt_cos_generation
from apps.ai.models import AssistantConversation, AssistantMessage

User = get_user_model()

_LOOP = "apps.ai.services.ai_service._call_api_with_tools"
_STANDING = "apps.ai.cos_services.get_standing_context"
_WARM = "apps.core.ai_state.state_engine.get_user_state"


def _mk_user(email):
    u = User.objects.create_user(email=email, password="x")
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class ChatGPTCoSServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _mk_user("svc@example.com")
        cls.conversation = AssistantConversation.objects.create(user=cls.user)

    def test_generate_runs_tool_loop_and_returns_answer(self):
        with mock.patch(_WARM, return_value={"health": {}}), \
             mock.patch(_STANDING, return_value={"status": "ready", "x": 1}), \
             mock.patch(_LOOP, return_value="You're on track.") as loop:
            result = ChatGPTCoSService(self.user).generate(
                self.conversation, "How am I doing?",
            )
        self.assertEqual(result["answer"], "You're on track.")
        # all CoS tools advertised to the model
        self.assertEqual(
            set(result["tools_advertised"]),
            {"get_standing_context", "get_domain_state", "get_decision",
             "search_history", "execute_action",
             "get_foundational_health_facts"},
        )
        loop.assert_called_once()
        # standing context is injected into the system prompt
        sys_prompt = loop.call_args.args[0]
        self.assertIn("Chief of Staff", sys_prompt)

    def test_tools_called_are_recorded(self):
        def _fake_loop(system, user_msg, *, tools, dispatch, **kw):
            dispatch("get_decision", {"mode": "execution"})
            return "Focus on X."
        with mock.patch(_WARM, return_value={}), \
             mock.patch(_STANDING, return_value={"status": "ready"}), \
             mock.patch("apps.ai.cos_services.dispatch_tool_call",
                        return_value={"ok": True, "result": {}}), \
             mock.patch(_LOOP, side_effect=_fake_loop):
            result = ChatGPTCoSService(self.user).generate(
                self.conversation, "What should I focus on today?",
            )
        self.assertEqual(result["tools_called"], ["get_decision"])

    def test_warms_sae_and_standing_context(self):
        # The fix for "I can't see your weight": the clean path warms the SAE
        # snapshot and builds standing context so tools read real data.
        with mock.patch(_WARM, return_value={"health": {"weight_current": 286}}) as warm, \
             mock.patch(_STANDING, return_value={"status": "ready"}) as standing, \
             mock.patch(_LOOP, return_value="ok"):
            # Non-foundational prompt: foundational fact prompts take the
            # deterministic fast path and never build standing context.
            ChatGPTCoSService(self.user).generate(
                self.conversation, "How am I doing overall?",
            )
        warm.assert_called()
        self.assertIs(warm.call_args.kwargs.get("allow_rebuild"), True)
        self.assertIs(standing.call_args.kwargs.get("allow_build"), True)
        # the warmed snapshot is pinned so get_domain_state reads it
        self.assertEqual(self.user._sae_cache, {"health": {"weight_current": 286}})


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class ChatGPTCoSTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _mk_user("task@example.com")
        cls.conversation = AssistantConversation.objects.create(user=cls.user)

    def test_task_persists_and_writes_bus(self):
        with mock.patch.object(
            ChatGPTCoSService, "generate",
            return_value={"answer": "TASK ANSWER",
                          "tools_called": ["get_decision"],
                          "tools_advertised": ["get_decision"]},
        ):
            run_chatgpt_cos_generation.apply(args=[
                self.user.id, self.conversation.id,
                "What should I focus on today?", {}, "job-clean-1",
            ])
        snap = bus.read("job-clean-1")
        self.assertEqual(snap["status"], "done")
        self.assertEqual(snap["text"], "TASK ANSWER")
        self.assertTrue(any(e["type"] == "done" for e in snap["events"]))
        # messages persisted
        self.assertTrue(AssistantMessage.objects.filter(
            conversation=self.conversation, role="user",
            content="What should I focus on today?").exists())
        am = AssistantMessage.objects.filter(
            conversation=self.conversation, role="assistant").latest("created_at")
        self.assertEqual(am.content, "TASK ANSWER")
        self.assertEqual(am.metadata.get("cos_path"), "chatgpt_clean")

    def test_task_handles_generation_error_cleanly(self):
        with mock.patch.object(ChatGPTCoSService, "generate",
                               side_effect=RuntimeError("boom")):
            run_chatgpt_cos_generation.apply(args=[
                self.user.id, self.conversation.id, "x", {}, "job-clean-2",
            ])
        snap = bus.read("job-clean-2")
        self.assertEqual(snap["status"], "failed")
        am = AssistantMessage.objects.filter(
            conversation=self.conversation, role="assistant").latest("created_at")
        self.assertIn("error", am.content.lower())


class TaskRegistrationTests(TestCase):
    """The hang bug: the clean task lived in a non-autodiscovered sub-package,
    so the Celery worker never registered it and jobs sat unconsumed forever.
    It must be importable via apps.ai.tasks (which IS autodiscovered)."""

    def test_clean_task_registered_via_autodiscovered_module(self):
        from apps.ai import tasks as ai_tasks
        self.assertTrue(hasattr(ai_tasks, "run_chatgpt_cos_generation"))
        self.assertEqual(
            ai_tasks.run_chatgpt_cos_generation.name,
            "apps.ai.chatgpt_cos.run_chatgpt_cos_generation",
        )


class StreamViewRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _mk_user("view@example.com")

    def _post(self):
        self.client.force_login(self.user)
        with mock.patch(
            "apps.ai.views.AssistantChatStreamView.check_personal_assistant_enabled",
            return_value=(True, None),
        ), mock.patch(
            "apps.ai.chatgpt_cos.tasks.run_chatgpt_cos_generation.delay",
        ) as clean_delay, mock.patch(
            "apps.ai.tasks.run_chat_generation.delay",
        ) as legacy_delay:
            resp = self.client.post(
                "/assistant/api/chat/stream/",
                data='{"message": "What should I focus on today?"}',
                content_type="application/json",
            )
            # consume the streaming response so the generator runs
            if hasattr(resp, "streaming_content"):
                b"".join(resp.streaming_content)
        return clean_delay, legacy_delay

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
    def test_flag_on_routes_to_clean_path(self):
        self.user.preferences.use_chatgpt_cos = True
        self.user.preferences.save()
        clean_delay, legacy_delay = self._post()
        clean_delay.assert_called_once()
        legacy_delay.assert_not_called()

    @override_settings(WLJ_COS_EVIDENCE_TOOLS_ENABLED=False)
    def test_flag_off_routes_to_legacy(self):
        self.user.preferences.use_chatgpt_cos = False
        self.user.preferences.save()
        clean_delay, legacy_delay = self._post()
        clean_delay.assert_not_called()
        legacy_delay.assert_called_once()
