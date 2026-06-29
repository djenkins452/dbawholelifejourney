# ==============================================================================
# File: apps/ai/tests/test_calorie_questions.py
# Description: Defect class — calorie questions must answer with a calorie TOTAL
#   (a number), not a meal list and never "you haven't logged anything". Meal
#   questions remain a separate intent. Origin: Deep run #55 (truth_calories,
#   det_calories gate_value failures). No OpenAI (deterministic facts).
# ==============================================================================
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.utils import get_user_today
from apps.health.models import FoodEntry
from apps.ai.chatgpt_cos.foundational_facts import (
    classify_foundational_fact, format_fact_sentence,
)
from apps.ai.cos_services.health_facts import get_foundational_health_facts
from apps.ai.cos_services.execution_facts import get_foundational_execution_facts

User = get_user_model()
_GMS = "apps.core.ai_state.state_engine.get_module_state"


class CalorieQuestionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cal@test.com", password="x")
        self.today = get_user_today(self.user)
        self.yest = self.today - timedelta(days=1)

    def test_calorie_questions_route_to_calorie_totals_not_meals(self):
        self.assertEqual(classify_foundational_fact("How many calories have I eaten today?"),
                         "calories_today")
        self.assertEqual(classify_foundational_fact("How many calories did I eat yesterday?"),
                         "calories_yesterday")

    def test_today_with_no_food_returns_zero_calories(self):
        # No nutrition snapshot at all → still a numeric 0, never "haven't logged".
        with mock.patch(_GMS, return_value={}):
            f = get_foundational_health_facts(self.user, ["calories_today"])["calories_today"]
        self.assertEqual(f["value"], 0)
        ans = format_fact_sentence("calories_today", f)
        self.assertIn("0 calories", ans)
        self.assertNotIn("haven't", ans.lower())

    def test_yesterday_with_foods_returns_total_calories(self):
        for cal in (210, 320):
            FoodEntry.objects.create(user=self.user, food_name="x", meal_type="lunch",
                                     logged_date=self.yest, serving_size=1, quantity=1,
                                     total_calories=cal)
        f = get_foundational_health_facts(self.user, ["calories_yesterday"])["calories_yesterday"]
        self.assertEqual(f["value"], 530)
        self.assertEqual(format_fact_sentence("calories_yesterday", f),
                         "Yesterday you logged 530 calories.")

    def test_meal_question_still_returns_meal_list(self):
        FoodEntry.objects.create(user=self.user, food_name="Eggs", meal_type="breakfast",
                                 logged_date=self.yest, serving_size=1, quantity=1,
                                 total_calories=210)
        key = classify_foundational_fact("What did I eat yesterday?")
        self.assertEqual(key, "meals_yesterday")          # different intent
        ans = format_fact_sentence(key, get_foundational_execution_facts(self.user, [key])[key])
        self.assertIn("breakfast — Eggs", ans)
        self.assertNotIn("calorie", ans.lower())          # meals, not a calorie total

    def test_no_internal_field_leak_in_calorie_answers(self):
        with mock.patch(_GMS, return_value={"daily_calories": 1850}):
            f = get_foundational_health_facts(self.user, ["calories_today"])["calories_today"]
        ans = format_fact_sentence("calories_today", f).lower()
        for leak in ("sae", "daily_calories", "module", "field", "nutrition state"):
            self.assertNotIn(leak, ans)
