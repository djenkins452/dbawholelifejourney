# ==============================================================================
# File: apps/ai/tests/test_customer_conversation_replay.py
# Description: WHOLE-CONVERSATION regression. Replays the entire real customer
#   conversation as one flow through the deterministic path (with the phrasing LLM
#   forced off, so we assert the deterministic floor). The conversation must succeed
#   end-to-end with NO trust-breaking response. Future regressions add whole
#   conversations here, not just isolated prompts.
# ==============================================================================
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.foundational_facts import (
    classify_foundational_fact, answer_foundational_fact,
)
from apps.ai.chatgpt_cos.lanes import _why_explainer_lane
from apps.ai.chatgpt_cos.conversation_memory import record_last_answer
from apps.core.utils import get_user_today
from apps.health.models import FoodEntry

User = get_user_model()

# Things a Chief of Staff must NEVER say.
_TRUST_BREAKERS = ("good range", "in a good range", "healthy range", "meal entry",
                   "food entry", "sae", "i couldn't pull that together",
                   "latest meal logged")
_GMS = "apps.core.ai_state.state_engine.get_module_state"
_CALL_API = "apps.ai.services.ai_service._call_api"


class CustomerConversationReplayTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="replay@test.com", password="x")
        self.today = get_user_today(self.user)
        self.conv = AssistantConversation.objects.create(user=self.user)
        FoodEntry.objects.create(user=self.user, food_name="Oatmeal", meal_type="breakfast",
                                 logged_date=self.today - timedelta(days=1),
                                 serving_size=1, quantity=1)

    def _turn(self, question, health_state=None):
        """One deterministic turn: classify -> answer -> record memory. Returns answer."""
        key = classify_foundational_fact(question)
        self.assertIsNotNone(key, f"unrouted: {question}")
        with mock.patch(_CALL_API, return_value=None):       # force deterministic floor
            if health_state is not None:
                with mock.patch(_GMS, return_value=health_state):
                    res = answer_foundational_fact(self.user, question)
            else:
                res = answer_foundational_fact(self.user, question)
        self.assertIsNotNone(res, f"no answer: {question}")
        record_last_answer(self.conv, "foundational_facts", res)
        self.conv.refresh_from_db()
        return res["answer"]

    def _assert_clean(self, answer):
        low = answer.lower()
        for bad in _TRUST_BREAKERS:
            self.assertNotIn(bad, low, f"trust-breaking phrase {bad!r} in: {answer}")

    def test_full_conversation_succeeds_naturally(self):
        # 1) Dangerous glucose — must surface danger, never reassure.
        glu = self._turn("What was my last glucose reading?",
                         health_state={"latest_glucose": 43, "latest_glucose_unit": "mg/dL",
                                       "last_glucose_entry": (timezone.now() - timedelta(hours=2)).isoformat()})
        self._assert_clean(glu)
        self.assertIn("43", glu)
        self.assertIn("very low", glu.lower())

        # 2) Follow-up — answered from MEMORY, deterministically, citing the fact.
        why = _why_explainer_lane(self.user, "Why do you say that?", self.conv)
        self.assertIsNotNone(why, "follow-up lost context")
        self.assertEqual(why["fast_path"], "conversation_memory")
        self.assertIn("43", why["answer"])
        self._assert_clean(why["answer"])

        # 3) Real meals yesterday — actual food, not a storage concept.
        meals = self._turn("What did I eat yesterday?")
        self._assert_clean(meals)
        self.assertIn("Oatmeal", meals)

        # 4) A future-timestamp glucose must never report the impossible time / crash.
        future = self._turn("What's my latest glucose?",
                            health_state={"latest_glucose": 95, "latest_glucose_unit": "mg/dL",
                                          "last_glucose_entry": (timezone.now() + timedelta(hours=1)).isoformat()})
        self._assert_clean(future)
        self.assertIn("95", future)

    def test_followup_after_a_non_factual_turn_still_has_context(self):
        record_last_answer(self.conv, "personal_reasoning",
                           {"answer": "You're averaging 6.2 hours of sleep, a bit short."})
        self.conv.refresh_from_db()
        why = _why_explainer_lane(self.user, "Why do you say that?", self.conv)
        self.assertIsNotNone(why)
        self.assertIn("6.2", why["answer"])
