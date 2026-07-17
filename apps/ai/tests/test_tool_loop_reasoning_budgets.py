# ==============================================================================
# File: apps/ai/tests/test_tool_loop_reasoning_budgets.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Regression tests for the Model Interface deep-reasoning runtime fix
#   (scopes #1 + #2). The deep path (competing hypotheses × cross-domain evidence)
#   outgrew the shared 3-round / 1000-token tool-loop limits and emptied on the
#   forced final round, surfacing "…the model returned an empty response after tool
#   execution." Two structural corrections:
#     #1 endpoint-specific bounded budgets (model_interface = 7 rounds / 3500 tokens),
#        other endpoints unchanged;
#     #2 an empty forced-final answer NEVER escapes — one bounded, evidence-grounded
#        synthesis retry (no tools, keeps the accumulated evidence), then the plain
#        fallback only if that also fails.
#   All exercised with a scripted fake OpenAI client — no real model, deterministic.
# ==============================================================================
import json
from types import SimpleNamespace

from django.test import TestCase

from apps.ai.services import AIService, resolve_tool_loop_budgets


# --- scriptable fake OpenAI client -------------------------------------------
def _resp(content=None, tool_calls=None, finish_reason="stop",
          prompt_tokens=1200, completion_tokens=0):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=msg, finish_reason=finish_reason)
    usage = SimpleNamespace(prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens)
    return SimpleNamespace(choices=[choice], usage=usage, id="resp_fake")


def _toolcall(name, args="{}", _id="tc1"):
    return SimpleNamespace(id=_id, type="function",
                           function=SimpleNamespace(name=name, arguments=args))


class _FakeClient:
    """Returns scripted responses in order; repeats the last once exhausted."""
    def __init__(self, script):
        self._script = list(script)
        self.calls = []  # captured kwargs per create() call

        def _create(**kwargs):
            self.calls.append(kwargs)
            idx = len(self.calls) - 1
            item = self._script[idx] if idx < len(self._script) else self._script[-1]
            if isinstance(item, Exception):
                raise item
            return item

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=_create))


_TOOLS = [{"type": "function",
           "function": {"name": "get_analysis",
                        "parameters": {"type": "object", "properties": {}}}}]


def _svc(script):
    svc = AIService()
    svc.client = _FakeClient(script)
    svc.model = "gpt-test"
    return svc


def _run(svc, prompt="Analyze my workout trends", *, endpoint="model_interface",
         dispatch=None, **kw):
    dispatch = dispatch or (lambda n, a: {"ok": True, "tool": n, "evidence": [1, 2, 3]})
    return svc._call_api_with_tools(
        "SYSTEM", prompt, tools=_TOOLS, dispatch=dispatch, endpoint=endpoint,
        skip_current_context=True, **kw)


# =============================================================================
class BudgetResolutionTests(TestCase):
    def test_model_interface_gets_its_own_budgets(self):
        tokens, rounds = resolve_tool_loop_budgets("model_interface")
        self.assertEqual((tokens, rounds), (3500, 7))
        self.assertGreaterEqual(rounds, 6)
        self.assertLessEqual(rounds, 8)
        self.assertGreaterEqual(tokens, 3000)
        self.assertLessEqual(tokens, 4000)

    def test_other_endpoints_retain_the_existing_defaults(self):
        for ep in ("cos_chat", "cos_briefing", "general", "intent_recognition", ""):
            self.assertEqual(resolve_tool_loop_budgets(ep), (1000, 3))

    def test_explicit_caller_values_always_win(self):
        self.assertEqual(
            resolve_tool_loop_budgets("model_interface", max_tool_rounds=2,
                                      max_tokens=500),
            (500, 2))


class DeepReasoningRoundsTests(TestCase):
    def test_more_than_three_tool_rounds_return_a_nonempty_answer(self):
        # Four tool-calling rounds (0-3) then a prose answer on round 4 — impossible
        # under the old 3-round cap (round 3 would be forced-answer), fine at 7.
        script = [
            _resp(tool_calls=[_toolcall("get_analysis")], finish_reason="tool_calls"),
            _resp(tool_calls=[_toolcall("get_history")], finish_reason="tool_calls"),
            _resp(tool_calls=[_toolcall("get_entity")], finish_reason="tool_calls"),
            _resp(tool_calls=[_toolcall("get_domain_state")], finish_reason="tool_calls"),
            _resp(content="Executive briefing answer.", finish_reason="stop"),
        ]
        svc = _svc(script)
        out = _run(svc)
        self.assertEqual(out, "Executive briefing answer.")
        self.assertEqual(len(svc.client.calls), 5)   # 5 rounds (0-4) — past the old cap
        # rounds 0-3 offered tools; the answering round did not
        self.assertIn("tools", svc.client.calls[0])
        self.assertIn("tools", svc.client.calls[3])


class SynthesisRetryTests(TestCase):
    def _empty_final_script(self, synth_content):
        # round 0 = tool call; round 1 (last, max_tool_rounds=1) = EMPTY forced answer;
        # call 2 = synthesis retry.
        return [
            _resp(tool_calls=[_toolcall("get_analysis",
                                        '{"domain":"health","subject":"workouts"}')],
                  finish_reason="tool_calls"),
            _resp(content=None, finish_reason="stop"),
            _resp(content=synth_content, finish_reason="stop"),
        ]

    def test_empty_forced_final_triggers_synthesis_and_uses_its_answer(self):
        svc = _svc(self._empty_final_script("Grounded synthesis answer."))
        disp = lambda n, a: {"ok": True, "evidence": "WORKOUT_EVIDENCE_XYZ"}
        out = _run(svc, "Why has my weight loss slowed?", dispatch=disp,
                   max_tool_rounds=1)
        self.assertEqual(out, "Grounded synthesis answer.")
        self.assertEqual(len(svc.client.calls), 3)   # round0, forced-final, synthesis

    def test_synthesis_retry_offers_no_tools_and_keeps_the_evidence(self):
        svc = _svc(self._empty_final_script("Answer from evidence."))
        disp = lambda n, a: {"ok": True, "evidence": "WORKOUT_EVIDENCE_XYZ"}
        _run(svc, dispatch=disp, max_tool_rounds=1)
        synth_kwargs = svc.client.calls[2]
        self.assertNotIn("tools", synth_kwargs)          # no tools offered
        blob = json.dumps(synth_kwargs["messages"])
        self.assertIn("WORKOUT_EVIDENCE_XYZ", blob)      # accumulated evidence retained
        # explicit "answer from what was gathered / do not request tools" instruction
        last = synth_kwargs["messages"][-1]
        self.assertEqual(last["role"], "user")
        self.assertIn("evidence already gathered", last["content"])
        self.assertIn("do NOT request any more tools", last["content"])

    def test_second_empty_falls_back_to_plain_completion(self):
        # forced-final empty AND synthesis empty → the existing plain fallback runs.
        svc = _svc(self._empty_final_script(None))
        svc._call_api = lambda *a, **k: "PLAIN_FALLBACK_ANSWER"
        out = _run(svc, dispatch=lambda n, a: {"ok": True}, max_tool_rounds=1)
        self.assertEqual(out, "PLAIN_FALLBACK_ANSWER")

    def test_no_empty_string_can_escape_the_tool_loop(self):
        # Even when both the forced final and the synthesis retry are empty, the loop
        # never returns "" — it hands off to the fallback (here, a real answer).
        svc = _svc(self._empty_final_script(""))
        svc._call_api = lambda *a, **k: "RECOVERED"
        out = _run(svc, dispatch=lambda n, a: {"ok": True}, max_tool_rounds=1)
        self.assertTrue(out)
        self.assertNotEqual(out, "")


class OtherRuntimesUnchangedTests(TestCase):
    """The non-empty guarantee is scoped to the Model Interface ON PURPOSE: the
    ChatGPT-CoS path INTENTIONALLY surfaces an empty final as a suppressed diagnostic
    state (reason=openai_fallback_empty). Changing that would silently alter a different
    live runtime — so cos_chat keeps the legacy empty-return contract."""

    def test_cos_chat_empty_final_still_returns_empty_no_synthesis(self):
        script = [
            _resp(tool_calls=[_toolcall("get_domain_state")], finish_reason="tool_calls"),
            _resp(content=None, finish_reason="stop"),   # forced-final EMPTY
        ]
        svc = _svc(script)
        out = _run(svc, endpoint="cos_chat", dispatch=lambda n, a: {"ok": True},
                   max_tool_rounds=1)
        self.assertEqual(out, "")                    # legacy contract preserved
        self.assertEqual(len(svc.client.calls), 2)   # NO synthesis retry was attempted

    def test_synthesis_guarantee_is_scoped_to_model_interface(self):
        from apps.ai.services import TOOL_LOOP_SYNTHESIS_ENDPOINTS
        self.assertIn("model_interface", TOOL_LOOP_SYNTHESIS_ENDPOINTS)
        self.assertNotIn("cos_chat", TOOL_LOOP_SYNTHESIS_ENDPOINTS)


class ProductionEquivalentTests(TestCase):
    """The two deepest acceptance prompts, driven through a many-round investigation
    that empties on the forced final round — each must still return a nonempty,
    evidence-grounded answer via the synthesis retry (never the empty-response error)."""

    PROMPTS = ["Analyze my workout trends.",
               "Why has my weight loss slowed down recently?"]

    def test_deep_prompts_never_return_the_empty_response_error(self):
        for prompt in self.PROMPTS:
            with self.subTest(prompt=prompt):
                # 3 cross-domain tool rounds, then an empty forced-final, then synthesis.
                script = [
                    _resp(tool_calls=[_toolcall("get_analysis")],
                          finish_reason="tool_calls"),
                    _resp(tool_calls=[_toolcall("get_history")],
                          finish_reason="tool_calls"),
                    _resp(tool_calls=[_toolcall("get_domain_state")],
                          finish_reason="tool_calls"),
                    _resp(content=None, finish_reason="stop"),   # forced-final EMPTY
                    _resp(content="Here is what the evidence shows…",
                          finish_reason="stop"),                 # synthesis retry
                ]
                svc = _svc(script)
                out = svc._call_api_with_tools(
                    "SYSTEM", prompt, tools=_TOOLS,
                    dispatch=lambda n, a: {"ok": True, "evidence": "E"},
                    endpoint="model_interface", skip_current_context=True,
                    max_tool_rounds=3)
                self.assertTrue(out)
                self.assertNotIn("empty response after tool execution", out)
                self.assertEqual(out, "Here is what the evidence shows…")
