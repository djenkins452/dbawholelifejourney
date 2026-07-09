# ==============================================================================
# File: apps/ai/tests/test_model_interface_runtime.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Slice 7 — the model-interface runtime, end-to-end validation.
# ==============================================================================
"""
Validation suite for the model-interface runtime (docs/WLJ_MODEL_INTERFACE_DESIGN.md).

The OpenAI client is mocked to EMIT tool calls, so the real tool loop drives the real
dispatch (truth-envelope wrapping + audit + stateful action confirmation). Covers the
required Slice-7 validation scenarios.
"""

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.ai.model_interface.constitution import CONSTITUTION
from apps.ai.model_interface.service import ModelInterfaceService
from apps.ai.models import ToolCallLog

User = get_user_model()


# -- OpenAI response fixtures (mirror the existing tool-loop test pattern) -----
def _toolcall(tc_id, name, arguments):
    return SimpleNamespace(id=tc_id, type="function",
                           function=SimpleNamespace(name=name, arguments=arguments))


def _resp(content=None, tool_calls=None, finish_reason="stop"):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(id="r", choices=[SimpleNamespace(
        message=msg, finish_reason=finish_reason)], usage=None)


def _ai_with(responses):
    from apps.ai.services import AIService
    svc = AIService()
    svc.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=mock.MagicMock(side_effect=responses))))
    return svc


def _prefs(user, **fields):
    from apps.users.models import UserPreferences
    p = (UserPreferences.objects.filter(user=user).first()
         or UserPreferences.objects.create(user=user))
    for k, v in fields.items():
        setattr(p, k, v)
    p.save()
    # Bust the cached reverse one-to-one so `user.preferences` re-reads the saved row.
    try:
        del user._state.fields_cache["preferences"]
    except (AttributeError, KeyError):
        pass
    return p


class StandingContextTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="mi_ctx@example.com", password="x")
        _prefs(cls.user, cos_display_name="Beth", default_relationship="best_friend",
               cos_response_style="strategic")

    def test_ai_relationship_and_current_context_are_in_the_standing_context(self):
        mi = ModelInterfaceService(self.user)
        ctx = mi.build_standing_context()
        rel = ctx["ai_relationship"]
        self.assertEqual(rel["assistant"]["display_name"], "Beth")           # name
        self.assertEqual(rel["assistant"]["default_relationship"], "best_friend")
        self.assertIn("detail_level", rel["communication"])                  # comms
        self.assertIn("clock", ctx["current_context"])                       # current ctx
        self.assertIn("answerable_domains", ctx["current_context"]["capabilities"])

    def test_constitution_carries_the_fabrication_rule(self):
        mi = ModelInterfaceService(self.user)
        sp = mi._system_prompt(mi.build_standing_context())
        self.assertIn("never", CONSTITUTION.lower())
        self.assertIn("fabrication is forbidden", sp.lower())
        self.assertIn("derive conclusions", sp.lower())

    def test_sandbox_does_not_push_broad_personal_truth(self):
        # Only AI Relationship + Current Context baseline are pushed; deep personal
        # truth is pull-only. With no signals, the safety/priority section is pending
        # (no health data pushed), and there is no journal/finance/relationship payload.
        mi = ModelInterfaceService(self.user)
        ctx = mi.build_standing_context()
        # Only two pillars are pushed; deep personal truth is pull-only.
        self.assertEqual(set(ctx.keys()), {"ai_relationship", "current_context"})
        # No personal domain STATE is pushed: priority + day-continuity are pending
        # (no health/other data), and Current Context carries no domain payloads.
        cc = ctx["current_context"]
        self.assertEqual(cc["priority"]["status"], "pending")
        self.assertEqual(cc["day_continuity"]["status"], "pending")
        self.assertNotIn("state", cc)          # no pushed domain state
        # The capability index lists domain NAMES only (what you can ask), not values.
        self.assertTrue(all(isinstance(d, str)
                            for d in cc["capabilities"]["answerable_domains"]))


class TruthToolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="mi_truth@example.com", password="x")
        _prefs(cls.user)

    def setUp(self):
        cache.clear()

    def _generate_with_tool(self, tool_name, arguments, patch_target, patch_return):
        responses = [
            _resp(tool_calls=[_toolcall("c1", tool_name, arguments)]),
            _resp(content="Here is what I found."),
        ]
        mi = ModelInterfaceService(self.user, ai_service=_ai_with(responses))
        with mock.patch(patch_target, return_value=patch_return):
            result = mi.generate(SimpleNamespace(id=1), "tell me", request_id="t1")
        return result

    def test_get_domain_state_returns_envelope_and_is_audited(self):
        self._generate_with_tool(
            "get_domain_state", '{"domain": "health"}',
            "apps.ai.model_interface.service.get_domain_state",
            {"status": "ok", "state": {"weight": 182}})
        row = ToolCallLog.objects.get(user=self.user, turn_id="t1",
                                      tool_name="get_domain_state")
        self.assertEqual(row.kind, "truth")
        self.assertEqual(row.result_status, "ok")
        self.assertIn("freshness", row.result_digest)   # truth-envelope metadata

    def test_search_history_is_audited_truth(self):
        self._generate_with_tool(
            "search_history", '{"query": "vacation"}',
            "apps.ai.model_interface.service.search_history",
            {"status": "ok", "results": [{"title": "Trip"}]})
        self.assertTrue(ToolCallLog.objects.filter(
            user=self.user, tool_name="search_history", kind="truth").exists())

    def test_foundational_health_facts_is_audited_truth(self):
        self._generate_with_tool(
            "get_foundational_health_facts", '{"keys": ["current_medications"]}',
            "apps.ai.model_interface.service.get_foundational_health_facts",
            {"status": "ok", "current_medications": ["Metformin"]})
        self.assertTrue(ToolCallLog.objects.filter(
            user=self.user, tool_name="get_foundational_health_facts",
            kind="truth").exists())

    def test_unavailable_data_is_handled_honestly(self):
        # An unsupported domain maps to insufficient_evidence — never a fabricated value.
        self._generate_with_tool(
            "get_domain_state", '{"domain": "nonexistent"}',
            "apps.ai.model_interface.service.get_domain_state",
            {"status": "unsupported_domain"})
        row = ToolCallLog.objects.get(user=self.user, tool_name="get_domain_state")
        self.assertEqual(row.result_status, "insufficient_evidence")

    def test_response_is_audited(self):
        self._generate_with_tool(
            "get_domain_state", '{"domain": "health"}',
            "apps.ai.model_interface.service.get_domain_state",
            {"status": "ok"})
        self.assertTrue(ToolCallLog.objects.filter(
            user=self.user, turn_id="t1", kind="response").exists())


class StatefulActionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="mi_act@example.com", password="x")
        _prefs(cls.user)

    def setUp(self):
        cache.clear()

    @staticmethod
    def _fake_execute(user, action, params):
        if params.get("confirmed"):
            return {"status": "success", "action": action, "message": "Moved to 9 PM."}
        return {"status": "confirmation_required", "action": action,
                "message": "needs confirmation"}

    def test_request_creates_pending_then_confirm_executes_stored_action(self):
        exec_target = "apps.ai.cos_services.action_execution.execute_action"
        with mock.patch(exec_target, side_effect=self._fake_execute):
            # Turn 1: model requests the action → confirmation_required, WLJ stores it.
            mi1 = ModelInterfaceService(self.user, ai_service=_ai_with([
                _resp(tool_calls=[_toolcall(
                    "c1", "request_action",
                    '{"action": "mutate_task", "params": {"id": 5, "time": "21:00"}}')]),
                _resp(content="Want me to move it to 9 PM?"),
            ]))
            mi1.generate(SimpleNamespace(id=1), "move my task", request_id="t1")

            from apps.ai.intent_service import IntentService
            pending = IntentService().get_pending_confirmation(self.user)
            self.assertIsNotNone(pending)                 # held server-side
            self.assertEqual(pending["intent_type"], "mutate_task")

            # Turn 2: user says yes → model resolves; WLJ executes the STORED action.
            mi2 = ModelInterfaceService(self.user, ai_service=_ai_with([
                _resp(tool_calls=[_toolcall("c2", "resolve_pending_action",
                                            '{"confirm": true}')]),
                _resp(content="Done — moved it to 9 PM."),
            ]))
            mi2.generate(SimpleNamespace(id=1), "yes", request_id="t2")

        self.assertIsNone(IntentService().get_pending_confirmation(self.user))  # cleared
        # Audit shows the action request and the executed action.
        self.assertTrue(ToolCallLog.objects.filter(
            user=self.user, kind="action", turn_id="t1").exists())
        self.assertTrue(ToolCallLog.objects.filter(
            user=self.user, kind="action", turn_id="t2").exists())


class RuntimeResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="mi_res@example.com", password="x")

    def _runtime_name(self):
        from apps.ai.cos_gateway.gateway import CoSGateway
        return CoSGateway.resolve_runtime(self.user).name

    def test_flag_on_selects_model_interface(self):
        _prefs(self.user, use_model_interface=True, use_chatgpt_cos=True)
        self.assertEqual(self._runtime_name(), "model_interface")  # precedence

    def test_flag_off_returns_existing_behavior(self):
        _prefs(self.user, use_model_interface=False, use_chatgpt_cos=False)
        self.assertEqual(self._runtime_name(), "legacy_beth")
        _prefs(self.user, use_model_interface=False, use_chatgpt_cos=True)
        self.assertEqual(self._runtime_name(), "chatgpt_cos")


class RuntimeIOTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="mi_io@example.com", password="x")
        _prefs(cls.user, use_model_interface=True)

    def test_non_streaming_persists_and_returns_answer(self):
        from apps.ai.cos_gateway.runtime import ModelInterfaceRuntime
        from apps.ai.models import AssistantMessage
        with mock.patch.object(ModelInterfaceService, "generate",
                               return_value={"answer": "Hello there.", "tools_called": []}):
            resp = ModelInterfaceRuntime().respond(
                user=self.user, surface="chat", message="hi", stream=False)
        self.assertEqual(resp.runtime, "model_interface")
        self.assertEqual(resp.text, "Hello there.")
        conv_id = resp.meta["conversation_id"]
        roles = list(AssistantMessage.objects.filter(
            conversation_id=conv_id).values_list("role", flat=True))
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_streaming_parity_writes_terminal_answer_to_bus(self):
        from apps.ai import chat_stream_bus as bus
        from apps.ai.model_interface.tasks import run_model_interface_generation
        from apps.ai.models import AssistantConversation
        conv = AssistantConversation.get_or_create_active(self.user)
        job_id = "job-parity-1"
        bus.write(job_id, bus.new_snapshot(self.user.id, conv.id))
        with mock.patch.object(ModelInterfaceService, "generate",
                               return_value={"answer": "Streamed answer.",
                                             "tools_called": []}):
            run_model_interface_generation.apply(
                args=[self.user.id, conv.id, "hi", None, job_id])
        snap = bus.read(job_id)
        self.assertEqual(snap["status"], "done")            # terminal — relay won't hang
        self.assertEqual(snap["text"], "Streamed answer.")  # same answer as non-streaming
