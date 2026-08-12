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

    def test_executive_lead_exposes_the_fact_and_delegates_the_judgment(self):
        # EXECUTIVE LEAD RESPONSIBILITY CORRECTION (2026-08-12): the lead must EXPOSE the
        # deterministic current_action FACT (I.3) and DELEGATE to the model whether it answers
        # the user's question (I.4) — NOT classify intent via phrase-list buckets nor command
        # "you ALREADY KNOW the answer — LEAD with the item above" (which collapsed action-worded
        # questions like "what should I focus on right now?" onto current_action, even overriding
        # an established conversational subject).
        mi = ModelInterfaceService(self.user)
        ctx = {"current_action": {
            "reason": "foundational; prioritized now",
            "message": "Work on WLJ",
            "primary_action": {"title": "Work on WLJ"}}}
        lead = mi._executive_lead(ctx)
        low = lead.lower()
        self.assertIn("Work on WLJ", lead)                       # the FACT is surfaced
        self.assertIn("deterministic fact", low)                 # framed as fact, not answer
        self.assertIn("you decide", low)                         # judgment delegated to the model
        # the over-steer imperative is GONE
        self.assertNotIn("you already know the answer", low)
        # a broader question is one input, not the answer (over-steer stays fixed)
        self.assertIn("one input", low)
        self.assertIn("do not collapse", low)
        # conversation precedence: an established subject is not overridden by current_action
        self.assertIn("does not override", low)
        # the ONE preserved deterministic protection: never hand the job back
        self.assertIn("pick an area", low)
        self.assertIn("name their own tasks", low)
        # NO phrase-list intent classifier remains (the four bucket headers are gone)
        self.assertNotIn("• execution", low)
        self.assertNotIn("• completeness", low)
        # wired into the system prompt; empty current_action → no lead (WLJ never invents one)
        sp = mi._system_prompt({**mi.build_standing_context(), **ctx})
        self.assertIn("WHAT MATTERS RIGHT NOW", sp)
        self.assertEqual(mi._executive_lead({"current_action": {}}), "")

    def test_overall_rollup_is_not_anchored_as_a_narrow_active_subject(self):
        # An "overall" roll-up (a whole-domain/multi-domain assessment) is arbitrary after a
        # broad synthesis (last-retrieval-wins). It must NOT be asserted as THE active subject
        # ("the analysis 'overall'"); the conversational reference rule carries the referent.
        mi = ModelInterfaceService(self.user)
        lead = mi._conversation_state_lead({"conversation_state": {"active_subject": {
            "kind": "analysis", "ref": "goals.overall", "label": "overall",
            "metric": "overall", "domain": "goals", "turns_ago": 1}}})
        self.assertEqual(lead, "")  # nothing pending/guided + overall dropped → no lead

    def test_analysis_subject_reretrieval_uses_get_analysis_not_artifacts(self):
        # A specific get_analysis subject (weight) must be re-fetched with get_analysis — the
        # old branch told the model to use get_entity(domain='artifacts'), which is incoherent
        # for an analysis subject and was the secondary continuity bug.
        mi = ModelInterfaceService(self.user)
        lead = mi._conversation_state_lead({"conversation_state": {"active_subject": {
            "kind": "analysis", "ref": "health.weight", "label": "weight",
            "metric": "weight", "domain": "health", "turns_ago": 1}}})
        self.assertIn("get_analysis(domain='health'", lead)
        self.assertNotIn("get_entity (domain='artifacts')", lead)

    def test_artifact_subject_still_uses_get_entity_artifacts(self):
        # An uploaded artifact subject is still correctly re-perceived via get_entity(artifacts).
        mi = ModelInterfaceService(self.user)
        lead = mi._conversation_state_lead({"conversation_state": {"active_subject": {
            "kind": "artifact", "ref": "art-123", "label": "scan.pdf", "turns_ago": 1}}})
        self.assertIn("get_entity (domain='artifacts')", lead)

    def test_checkin_and_chat_surface_the_same_current_action_no_contradiction(self):
        # Blocker #4: the proactive check-in claims a high-priority action; the chat must be
        # able to name the SAME one — they cannot contradict ("I can't see your to-do list")
        # because BOTH the check-in author and the chat build from `current_action` in the ONE
        # standing envelope. Guard: the same current_action appears in BOTH system prompts.
        import apps.ai.checkin_author as ca
        mi = ModelInterfaceService(self.user)
        envelope = {"current_action": {"message": "Work on WLJ",
                                       "primary_action": {"title": "Work on WLJ"}}}
        checkin_prompt = ca._system_prompt(envelope, "end_of_day")
        self.assertIn("Work on WLJ", checkin_prompt)   # the check-in can CLAIM it
        chat_prompt = mi._system_prompt({**mi.build_standing_context(), **envelope})
        self.assertIn("Work on WLJ", chat_prompt)      # the chat can NAME it (no "I can't see")

    def test_first_internal_question_is_what_kind_of_help(self):
        # CoS v2.0: the model's FIRST internal question is "what kind of help is this person
        # asking me for?" (not "what did they ask / which domain"), and — when WLJ holds the
        # truth — retrieve what they've actually been doing BEFORE answering. Model-side; WLJ
        # never classifies the ask. Lives at the top of the identity (first-read salience).
        c = CONSTITUTION.lower()
        self.assertIn("your first internal question", c)
        self.assertIn("what kind of help is this person actually asking me for", c)
        self.assertIn("wlj never classifies the ask", c)
        # generic advice is the fallback only when WLJ lacks the truth
        self.assertIn("are the fallback", c)
        # a person is retrievable truth; retrieve — don't assume you know, don't defer
        self.assertIn("a person is retrievable truth", c)
        self.assertIn("your very next move is to retrieve", c)
        self.assertIn("do not say 'let's consider what we know", c)
        # the identity question sits BEFORE the wlj-ownership split (first-read placement)
        self.assertLess(c.index("your first internal question"),
                        c.index("you are the user's personal assistant"))

    def test_investigate_trigger_covers_improvement_intent(self):
        # Blocker #13A: an open-ended personal-improvement INTENT ("I need to plan my nutrition
        # better") must trigger investigate-first, not generic advice — when WLJ already holds
        # that area's truth. The trigger scope must name this class, not only problem/slip/'what
        # should I do'.
        c = CONSTITUTION.lower()
        self.assertIn("i need to plan my nutrition better", c)     # the exact class example
        self.assertIn("get control of", c)                          # improvement-intent verbs
        self.assertIn("never answered with generic advice first", c)
        self.assertIn("retrieve that truth first", c)

    def test_constitution_carries_the_fabrication_rule(self):
        mi = ModelInterfaceService(self.user)
        sp = mi._system_prompt(mi.build_standing_context())
        self.assertIn("never", CONSTITUTION.lower())
        self.assertIn("fabrication is forbidden", sp.lower())
        self.assertIn("derive conclusions", sp.lower())

    def test_standing_context_assembles_the_owned_interfaces(self):
        # The envelope assembles owned truth interfaces; it owns none. Read-only sections:
        # AI Relationship, Deterministic Understanding, Personal Truth (durable stored user
        # facts), Current Context, plus the Mission Link facts (`missions`) and the enriched
        # `current_action` (execution truth).
        mi = ModelInterfaceService(self.user)
        ctx = mi.build_standing_context()
        self.assertEqual(set(ctx.keys()),
                         {"ai_relationship", "deterministic_understanding",
                          "personal_truth", "current_context", "missions",
                          "execution_state", "current_action"})
        # Current Context is the FAST tier only — no understanding leaks into it.
        cc = ctx["current_context"]
        self.assertEqual(set(cc.keys()),
                         {"schema_version", "clock", "day_significance",
                          "current_screen", "capabilities"})
        for banned in ("priority", "day_continuity", "state", "patterns"):
            self.assertNotIn(banned, cc)

    def test_deterministic_understanding_is_projected_when_warm(self):
        # Understanding is CACHE-FIRST from its own owner. Cold → pending; warm → the
        # already-computed assessment is surfaced for the model to reason FROM.
        from apps.ai.model_interface import understanding
        from django.core.cache import cache
        cache.delete(understanding._key(self.user.id))
        ctx = ModelInterfaceService(self.user).build_standing_context()
        self.assertEqual(ctx["deterministic_understanding"]["status"], "pending")

        cache.set(understanding._key(self.user.id), {
            "schema_version": "1.0", "status": "ok",
            "executive": {"primary_challenge": "workload", "biggest_risk": "overdue",
                          "workload": "overloaded"},
            "patterns": [{"text": "Overtraining Risk"}],
        }, 60)
        du = ModelInterfaceService(self.user).build_standing_context()["deterministic_understanding"]
        self.assertEqual(du["status"], "ok")
        self.assertEqual(du["executive"]["primary_challenge"], "workload")
        self.assertEqual(du["patterns"][0]["text"], "Overtraining Risk")

    def test_current_screen_is_exposed_in_context(self):
        # Location (WHERE) flows through the standing context; a declared reference (WHAT)
        # resolves to canonical truth server-side (proven in test_current_context_baseline).
        page = {"url": "/faith/journey/today/", "module": "Faith",
                "page_title": "Today's Reading"}
        cc = ModelInterfaceService(self.user).build_standing_context(
            page_context=page)["current_context"]
        self.assertEqual(cc["current_screen"]["status"], "present")
        self.assertEqual(cc["current_screen"]["location"]["module"], "Faith")
        self.assertIsNone(cc["current_screen"]["focus"])

    def test_read_only_omits_action_tools_write_exposes_named_intents(self):
        from apps.ai.model_interface.constitution import all_tools
        ro = {t["function"]["name"] for t in all_tools(writes_enabled=False)}
        rw = {t["function"]["name"] for t in all_tools(writes_enabled=True)}
        # read-only: NO action tools at all
        for n in ("mutate_task", "create_task", "complete_task", "resolve_pending_action"):
            self.assertNotIn(n, ro)
        # write: the curated NAMED intent tools + the confirmation resolver
        self.assertIn("mutate_task", rw)
        self.assertIn("create_task", rw)
        self.assertIn("complete_task", rw)
        self.assertIn("resolve_pending_action", rw)
        # the generic request_action tool is RETIRED (Option B)
        self.assertNotIn("request_action", rw)
        # mutate_task carries the REAL handler params (no invented interface)
        mt = next(t for t in all_tools(writes_enabled=True)
                  if t["function"]["name"] == "mutate_task")
        self.assertEqual(set(mt["function"]["parameters"]["required"]),
                         {"action", "task_query"})
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
        # The digest now records the truth ACTUALLY RETURNED (status/value/provenance)
        # under `evidence`, not just the request — see audit.truth_digest.
        self.assertIn("freshness", row.result_digest["evidence"])

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
            # Turn 1: model calls the NAMED tool with real handler params → bound confirm.
            mi1 = ModelInterfaceService(self.user, ai_service=_ai_with([
                _resp(tool_calls=[_toolcall(
                    "c1", "mutate_task",
                    '{"action": "update", "task_query": "dishes", '
                    '"new_scheduled_time": "21:00"}')]),
                _resp(content="Want me to move it to 9 PM?"),
            ]))
            mi1.generate(SimpleNamespace(id=1), "move my task", request_id="t1",
                         observer=_obs, writes_enabled=True)

            # The named tool routed through the pipeline and returned a bound confirmation.
            cid = None
            for name, res in captured:
                if name == "mutate_task":
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

    def test_proactive_checkin_stays_in_history(self):
        # Blocker 3: the CoS INITIATES the conversation with an end-of-day check-in
        # (persisted as a proactive `nudge`, shown to the user in chat). When the user
        # replies, the model MUST still see that opening turn — otherwise the CoS behaves
        # as though the conversation it just started never happened. The history the model
        # receives must equal the conversation the user saw, regardless of message_type.
        from apps.ai.cos_gateway.runtime import ModelInterfaceRuntime
        from apps.ai.models import AssistantConversation, AssistantMessage
        conv = AssistantConversation.get_or_create_active(self.user)
        AssistantMessage.objects.create(
            conversation=conv, role="assistant",
            content="It's the end of the day. Focus on completing the high-priority "
                    "action that's due.",
            message_type="nudge", is_proactive=True)
        seen = {}
        def _capture(self_svc, conversation, message, **kw):
            seen["history"] = kw.get("conversation_history")
            return {"answer": "ok", "tools_called": []}
        with mock.patch.object(ModelInterfaceService, "generate", new=_capture):
            ModelInterfaceRuntime().respond(user=self.user, surface="chat",
                                            conversation=conv,
                                            message="What's left for me to do?",
                                            stream=False)
        hist = seen["history"]
        self.assertEqual(len(hist), 1)
        self.assertEqual(hist[0]["role"], "assistant")
        self.assertIn("high-priority action", hist[0]["content"])

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
