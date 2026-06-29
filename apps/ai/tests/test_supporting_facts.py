# ==============================================================================
# File: apps/ai/tests/test_supporting_facts.py
# Description: Conversation-object completeness — a PRIMARY fact carries the SUPPORTING
#   facts a natural follow-up needs (the meals behind a calorie total), gathered once
#   and read from the active topic. "What did I eat?" after "how many calories?" is
#   answered from memory — no new retrieval, no LLM. Generalized, not nutrition-special.
# ==============================================================================
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.utils import get_user_today
from apps.health.models import FoodEntry
from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.foundational_facts import answer_foundational_fact
from apps.ai.chatgpt_cos.conversation_memory import (
    record_last_answer, compose_supporting,
)
from apps.ai.chatgpt_cos.lanes import _why_explainer_lane
from apps.ai.chatgpt_cos.supporting_facts import gather_supporting

User = get_user_model()
_GMS = "apps.core.ai_state.state_engine.get_module_state"
_CALL = "apps.ai.services.ai_service._call_api"


class SupportingFactsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="sup@test.com", password="x")
        self.today = get_user_today(self.user)
        FoodEntry.objects.create(user=self.user, food_name="Oatmeal", meal_type="breakfast",
                                 logged_date=self.today, serving_size=1, quantity=1,
                                 total_calories=200)
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _ask_calories(self):
        with mock.patch(_CALL, return_value=None), \
             mock.patch(_GMS, return_value={"daily_calories": 200}):
            r = answer_foundational_fact(self.user, "How many calories have I had today?")
        record_last_answer(self.conv, "foundational_facts", r)
        self.conv.refresh_from_db()
        return r

    def test_calorie_answer_carries_supporting_meals_and_protein(self):
        r = self._ask_calories()
        self.assertIn("200", r["answer"])
        self.assertIn("meals", r["supporting"])
        self.assertIn("protein", r["supporting"])

    def test_what_did_i_eat_answers_from_supporting_no_new_retrieval(self):
        self._ask_calories()
        for q in ("What did I eat?", "What were they?"):
            out = _why_explainer_lane(self.user, q, self.conv)
            self.assertIsNotNone(out, q)
            self.assertEqual(out["fast_path"], "conversation_memory")   # from memory
            self.assertIn("Oatmeal", out["answer"])
            self.assertIn("breakfast", out["answer"].lower())

    def test_standalone_meal_question_declines_to_normal_routing(self):
        # No active calorie topic → the follow-up lane must decline so the question
        # routes normally (not hijack every "what did I eat").
        fresh = AssistantConversation.objects.create(user=self.user)
        self.assertIsNone(_why_explainer_lane(self.user, "What did I eat?", fresh))

    def test_capability_is_generalized_registry_driven(self):
        # calories_yesterday declares meals_yesterday support — not a calories-today
        # special case. Any fact may register supporting facts.
        FoodEntry.objects.create(user=self.user, food_name="Eggs", meal_type="breakfast",
                                 logged_date=self.today - timedelta(days=1),
                                 serving_size=1, quantity=1, total_calories=150)
        sup = gather_supporting(self.user, "calories_yesterday")
        self.assertIn("meals", sup)
        self.assertEqual(sup["meals"]["key"], "meals_yesterday")
        # compose_supporting renders it deterministically
        ans = compose_supporting({"supporting": sup}, self.user, "meals")
        self.assertIn("Eggs", ans)

    def test_no_supporting_facts_for_an_unrelated_fact(self):
        self.assertEqual(gather_supporting(self.user, "current_weight"), {})
