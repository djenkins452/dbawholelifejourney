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
        # No personal DOMAIN state (journal/finance/etc.) is pushed — Current Context
        # carries only the minimal baseline (clock, priority policy, continuity,
        # capability index). Priority/clinical-safety IS the intentional safety baseline.
        cc = ctx["current_context"]
        self.assertEqual(set(cc.keys()),
                         {"schema_version", "clock", "priority", "day_continuity",
                          "capabilities"})
        self.assertNotIn("state", cc)          # no pushed domain state payloads
        # The capability index lists domain NAMES only (what you can ask), not values.
        self.assertTrue(all(isinstance(d, str)
                            for d in cc["capabilities"]["answerable_domains"]))

    def test_current_context_priority_from_standing_context(self):
        # Acceptance (Blocker 3): Current Context REUSES StandingContextService. When it is
        # warm, the baseline surfaces the deterministic priority (not pending).
        ready = {
            "status": "ready",
            "executive_read": "Highest priority right now: 5 prescription doses are overdue.",
            "recommended_focus": "Take the overdue doses first.",
            "critical_signals": [{"domain": "health", "type": "past_due",
                                  "title": "Metformin overdue"}],
        }
        with mock.patch(
            "apps.ai.cos_services.standing_context.get_standing_context",
            return_value=ready,
        ):
            cc = ModelInterfaceService(self.user).build_standing_context()["current_context"]
        self.assertEqual(cc["priority"]["status"], "ok")
        self.assertIn("overdue", cc["priority"]["priority_action"]["text"])
        self.assertEqual(len(cc["priority"]["clinical_safety"]), 1)

    def test_read_only_omits_action_tools_write_includes_them(self):
        from apps.ai.model_interface.constitution import all_tools
        ro = {t["function"]["name"] for t in all_tools(writes_enabled=False)}
        rw = {t["function"]["name"] for t in all_tools(writes_enabled=True)}
        self.assertNotIn("request_action", ro)
        self.assertNotIn("resolve_pending_action", ro)
        self.assertIn("request_action", rw)
        # truth tools present in both
        self.assertIn("get_domain_state", ro)

    def test_writes_enabled_reads_the_flag(self):
        _prefs(self.user, use_model_interface_writes=True)
        self.assertTrue(ModelInterfaceService(self.user)._writes_enabled())
        _prefs(self.user, use_model_interface_writes=False)
        self.assertFalse(ModelInterfaceService(self.user)._writes_enabled())


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

    def test_request_binds_confirmation_then_confirm_by_id_executes(self):
        import json as _json
        exec_target = "apps.ai.cos_services.action_interface.execute_action"
        captured = []

        def _obs(name, args, result):
            captured.append((name, result))

        with mock.patch(exec_target, side_effect=self._fake_execute):
            # Turn 1: model requests the action (write mode) → bound confirmation.
            mi1 = ModelInterfaceService(self.user, ai_service=_ai_with([
                _resp(tool_calls=[_toolcall(
                    "c1", "request_action",
                    '{"action": "mutate_task", "params": {"id": 5, "time": "21:00"}}')]),
                _resp(content="Want me to move it to 9 PM?"),
            ]))
            mi1.generate(SimpleNamespace(id=1), "move my task", request_id="t1",
                         observer=_obs, writes_enabled=True)

            # The model interface returned a bound confirmation id.
            cid = None
            for name, res in captured:
                if name == "request_action":
                    cid = (res.get("confirmation") or {}).get("confirmation_id")
            self.assertTrue(cid)

            # Turn 2: model resolves the SPECIFIC confirmation by id.
            mi2 = ModelInterfaceService(self.user, ai_service=_ai_with([
                _resp(tool_calls=[_toolcall("c2", "resolve_pending_action",
                                            _json.dumps({"confirmation_id": cid,
                                                         "confirm": True}))]),
                _resp(content="Done — moved it to 9 PM."),
            ]))
            mi2.generate(SimpleNamespace(id=1), "yes", request_id="t2",
                         writes_enabled=True)

        from apps.ai.model_interface import confirmation
        self.assertIsNone(confirmation.get(self.user, cid))  # consumed
        # Audit shows the action request (t1) and the executed action (t2, status ok).
        self.assertTrue(ToolCallLog.objects.filter(
            user=self.user, kind="action", turn_id="t1").exists())
        self.assertTrue(ToolCallLog.objects.filter(
            user=self.user, kind="action", turn_id="t2", result_status="ok").exists())


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

    def test_conversation_history_is_loaded_and_passed(self):
        # Blocker 2: prior turns are loaded from the existing AssistantMessage store and
        # passed to the model — and the CURRENT user message is not duplicated into it.
        from apps.ai.cos_gateway.runtime import ModelInterfaceRuntime
        from apps.ai.models import AssistantConversation, AssistantMessage
        conv = AssistantConversation.get_or_create_active(self.user)
        AssistantMessage.objects.create(conversation=conv, role="user",
                                        content="earlier question", message_type="text")
        AssistantMessage.objects.create(conversation=conv, role="assistant",
                                        content="earlier answer", message_type="text")
        seen = {}
        def _capture(self_svc, conversation, message, **kw):
            seen["history"] = kw.get("conversation_history")
            return {"answer": "ok", "tools_called": []}
        with mock.patch.object(ModelInterfaceService, "generate", new=_capture):
            ModelInterfaceRuntime().respond(user=self.user, surface="chat",
                                            conversation=conv, message="new question",
                                            stream=False)
        hist = seen["history"]
        self.assertEqual(hist, [{"role": "user", "content": "earlier question"},
                                {"role": "assistant", "content": "earlier answer"}])
        # the current turn ("new question") must NOT be in the passed history
        self.assertNotIn("new question", [h["content"] for h in hist])

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
