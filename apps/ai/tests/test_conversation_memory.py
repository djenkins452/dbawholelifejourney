# ==============================================================================
# File: apps/ai/tests/test_conversation_memory.py
# Description: Deterministic Conversation Memory. "Why do you say that?" is answered
#   from the STORED last answer + supporting fact, with NO LLM reconstruction. Origin:
#   real Beth conversation (lost context on a follow-up).
# ==============================================================================
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.conversation_memory import (
    record_last_answer, get_last_answer, compose_why,
)
from apps.ai.chatgpt_cos.lanes import _why_explainer_lane

User = get_user_model()


class ConversationMemoryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="mem@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _glucose_turn(self):
        return {"answer": "Your last glucose reading was 43 mg/dL (Very Low).",
                "fact_key": "last_glucose_reading",
                "basis": "Your last glucose reading was 43 mg/dL (Very Low).",
                "fact": {"value": 43, "unit": "mg/dL",
                         "interpretation": {"display": "Very Low", "concern": True,
                                            "advice": "This is a dangerously low reading."}}}

    def test_record_and_read_roundtrip(self):
        record_last_answer(self.conv, "foundational_facts", self._glucose_turn())
        self.conv.refresh_from_db()
        last = get_last_answer(self.conv)
        self.assertEqual(last["fact"]["value"], 43)
        self.assertEqual(last["lane"], "foundational_facts")

    def test_why_explainer_is_deterministic_and_cites_the_fact(self):
        record_last_answer(self.conv, "foundational_facts", self._glucose_turn())
        self.conv.refresh_from_db()
        out = _why_explainer_lane(self.user, "Why do you say that?", self.conv)
        self.assertIsNotNone(out)
        self.assertEqual(out["fast_path"], "conversation_memory")   # NO LLM
        ans = out["answer"].lower()
        self.assertIn("43", ans)
        self.assertIn("very low", ans)
        self.assertIn("dangerously low", ans)

    def test_no_prior_answer_declines(self):
        self.assertIsNone(_why_explainer_lane(self.user, "Why do you say that?", self.conv))

    def test_why_explainer_does_not_overwrite_the_basis(self):
        record_last_answer(self.conv, "foundational_facts", self._glucose_turn())
        # A why-explainer result must NOT replace the stored basis (so repeats work).
        record_last_answer(self.conv, "why_explainer", {"answer": "Because ..."})
        self.conv.refresh_from_db()
        self.assertEqual(get_last_answer(self.conv)["fact_key"], "last_glucose_reading")

    def test_compose_why_without_a_fact_uses_prior_text(self):
        why = compose_why({"answer": "You're averaging 6.2 hours of sleep.", "fact": {}})
        self.assertIn("6.2", why)

    def test_at_what_time_followup_reads_timestamp_from_same_fact(self):
        # CUSTOMER BLOCKER: "What is my glucose?" then "At what time?" must retrieve the
        # timestamp from the SAME stored fact — deterministically, no LLM.
        turn = {"answer": "Your last glucose reading was 112 mg/dL.",
                "fact_key": "last_glucose_reading",
                "fact": {"value": 112, "unit": "mg/dL",
                         "recorded_at": "2026-06-28T14:05:00+00:00"}}
        record_last_answer(self.conv, "foundational_facts", turn)
        self.conv.refresh_from_db()
        out = _why_explainer_lane(self.user, "At what time?", self.conv)
        self.assertIsNotNone(out)
        self.assertEqual(out["fast_path"], "conversation_memory")
        ans = out["answer"].lower()
        self.assertIn("recorded on", ans)
        self.assertIn("/2026", ans)            # MM/DD/YYYY, user-rendered

    def test_when_followup_after_future_timestamp_reports_the_warning(self):
        turn = {"answer": "Your last glucose reading was 95 mg/dL.",
                "fact_key": "last_glucose_reading",
                "fact": {"value": 95, "temporal_warning":
                         "That timestamp appears to be in the future, which shouldn't be possible."}}
        record_last_answer(self.conv, "foundational_facts", turn)
        self.conv.refresh_from_db()
        out = _why_explainer_lane(self.user, "At what time?", self.conv)
        self.assertIn("future", out["answer"].lower())
