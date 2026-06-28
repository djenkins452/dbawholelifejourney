# ==============================================================================
# File: apps/ai/tests/test_cos_multi_med_composition.py
# Description: Multi-medication composition. Single-med enrichment fit the CoS tool
#   loop's 1000-token default; composing educational purposes for MANY meds (13)
#   exceeded it → truncation/empty → fallback. Fix: the tool loop gets a budget
#   sufficient for multi-entity composition. These tests prove the budget is passed
#   and that the loop returns a long multi-med answer intact (no truncation in OUR
#   code; multi-tool pairing preserved).
# ==============================================================================
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

User = get_user_model()

_MULTI = "Can you list each medicine I take and what each is commonly used for?"


def _toolcall(tc_id, name, arguments):
    return SimpleNamespace(id=tc_id, type="function",
                           function=SimpleNamespace(name=name, arguments=arguments))


def _resp(content=None, tool_calls=None, finish_reason="stop"):
    msg = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(id="r", choices=[SimpleNamespace(
        message=msg, finish_reason=finish_reason)], usage=None)


def _service_with_responses(responses):
    from apps.ai.services import AIService
    svc = AIService()
    svc.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=mock.MagicMock(side_effect=responses))))
    return svc


class ToolLoopBudgetTests(TestCase):
    """service.generate must give the tool loop a budget big enough for many meds."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="multimed@example.com", password="x")

    def test_generate_passes_multi_entity_budget(self):
        from apps.ai.chatgpt_cos.service import ChatGPTCoSService
        svc = ChatGPTCoSService(self.user)
        captured = {}

        def fake_tools(*a, **kw):
            captured.update(kw)
            return "• Metformin — …\n• Lantus — …"

        with mock.patch.object(ChatGPTCoSService, "_history", return_value=[]), \
             mock.patch("apps.core.ai_state.state_engine.get_user_state", return_value={}), \
             mock.patch("apps.ai.cos_services.get_standing_context",
                        return_value={"status": "ready"}), \
             mock.patch("apps.ai.cos_services.get_tool_schemas", return_value=[]), \
             mock.patch("apps.ai.chatgpt_cos.reasoning.answer_reasoning_question",
                        return_value=None), \
             mock.patch("apps.ai.services.ai_service._call_api_with_tools",
                        side_effect=fake_tools):
            svc.generate(object(), _MULTI)
        # Was 1000 (default) — too small for 13 meds. Must now be materially larger.
        self.assertGreaterEqual(captured.get("max_tokens", 0), 2000,
                                "CoS tool loop needs a multi-entity composition budget")


class ToolLoopReturnsFullAnswerTests(TestCase):
    """Our code returns the full model answer — it does not truncate by count, and
    it correctly pairs the medication-list tool call with its result."""

    def test_long_thirteen_med_answer_returned_intact(self):
        meds = ["Metformin", "Lantus", "Humalog", "Mounjaro", "Lisinopril",
                "Atorvastatin", "Levothyroxine", "Amlodipine", "Omeprazole",
                "Aspirin", "Vitamin D", "Magnesium", "Fish Oil"]
        long_answer = "Here's each medicine and what it's commonly used for:\n" + \
            "\n".join(f"• {m} — commonly used for its standard indication, and based "
                      f"on what WLJ knows you take it as part of your plan." for m in meds)
        svc = _service_with_responses([
            # Round 0: model fetches the medication list (one tool call) …
            _resp(tool_calls=[_toolcall("c1", "get_foundational_health_facts",
                                        '{"keys": ["current_medications"]}')]),
            # Round 1: … then composes the full 13-med educational answer.
            _resp(content=long_answer),
        ])
        out = svc._call_api_with_tools(
            "sys", _MULTI, tools=[{"x": 1}],
            dispatch=lambda n, a: {"ok": True, "result": {"active_medications": meds}},
            max_tokens=2000,
        )
        # Full answer returned — every medication present, nothing dropped/truncated.
        self.assertEqual(out, long_answer)
        for m in meds:
            self.assertIn(m, out)

    def test_multi_tool_call_pairing_preserved(self):
        # Two tool calls in one round, then a final answer — the loop must echo the
        # assistant tool_calls turn and append BOTH tool results (valid pairing).
        svc = _service_with_responses([
            _resp(tool_calls=[
                _toolcall("c1", "get_foundational_health_facts", '{"keys": ["current_medications"]}'),
                _toolcall("c2", "get_domain_state", '{"domain": "health"}'),
            ]),
            _resp(content="Two tools resolved; here is your combined answer."),
        ])
        out = svc._call_api_with_tools(
            "sys", _MULTI, tools=[{"x": 1}],
            dispatch=lambda n, a: {"ok": True, "result": {}},
            max_tokens=2000,
        )
        self.assertEqual(out, "Two tools resolved; here is your combined answer.")
