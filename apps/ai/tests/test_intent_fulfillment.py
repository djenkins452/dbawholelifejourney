# ==============================================================================
# File: apps/ai/tests/test_intent_fulfillment.py
# Description: Intent Fulfillment. A COMPARE goal must produce the COMPARISON itself —
#   differences, overlaps, relative volume — not two raw lists. Verifies objective
#   completion, not literal prompt completion. Numeric compare fulfills via the delta;
#   structured (meals) via derived insights. See docs/INTENT_FULFILLMENT_MATRIX.md.
# ==============================================================================
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.core.utils import get_user_today
from apps.health.models import FoodEntry, StepsEntry
from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.foundational_facts import answer_foundational_fact
from apps.ai.chatgpt_cos.conversation_memory import record_last_answer
from apps.ai.chatgpt_cos.lanes import _why_explainer_lane, _referential_lane
from apps.ai.chatgpt_cos.fulfillment import fulfill_meal_comparison

User = get_user_model()


class MealComparisonFulfillmentTests(SimpleTestCase):
    def test_states_gaps_overlaps_and_volume(self):
        a = {"breakfast": ["Eggs"], "lunch": ["Pizza"], "dinner": ["Pizza", "Salad"]}
        b = {"breakfast": ["Oatmeal"], "dinner": ["Pizza"]}
        out = fulfill_meal_comparison("Yesterday", a, "Today", b)
        self.assertIn("lunch", out.lower())                  # meal-type gap
        self.assertIn("doesn't yet", out)                    # today incomplete
        self.assertIn("Pizza appear", out)                   # shared item
        self.assertIn("heavier", out)                        # relative volume
        self.assertIn("4 items vs 2", out)

    def test_returns_none_when_nothing_to_compare(self):
        self.assertIsNone(fulfill_meal_comparison("Yesterday", {}, "Today", {}))

    def test_equal_volume_is_stated(self):
        a = {"breakfast": ["Eggs"]}
        b = {"breakfast": ["Oatmeal"]}
        out = fulfill_meal_comparison("Yesterday", a, "Today", b)
        self.assertIn("1 items", out)                        # both days equal volume


class _Conv(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="ifc@test.com", password="x")
        self.today = get_user_today(self.user)
        self.yest = self.today - timedelta(days=1)
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _turn(self, q):
        r = (_why_explainer_lane(self.user, q, self.conv)
             or _referential_lane(self.user, q, self.conv)
             or answer_foundational_fact(self.user, q))
        if r:
            record_last_answer(self.conv, r.get("lane", "foundational_facts"), r)
            self.conv.refresh_from_db()
        return r


class MealCompareIntentTests(_Conv):
    def test_compare_returns_comparison_not_two_lists(self):
        for nm, mt, d in [("Eggs", "breakfast", self.yest), ("Pizza", "lunch", self.yest),
                          ("Pizza", "dinner", self.yest), ("Oatmeal", "breakfast", self.today),
                          ("Pizza", "dinner", self.today)]:
            FoodEntry.objects.create(user=self.user, food_name=nm, meal_type=mt,
                                     logged_date=d, serving_size=1, quantity=1)
        self._turn("What did I eat today?")
        self._turn("What about yesterday?")
        ans = self._turn("Compared to today.")["answer"]
        # The comparison IS the answer — it states a difference, not just lists.
        self.assertIn("lunch", ans.lower())
        self.assertIn("both days", ans)
        self.assertNotIn("you've logged:", ans.lower())       # not the raw list format


class NumericCompareIntentTests(_Conv):
    def test_numeric_compare_is_a_delta_not_two_values(self):
        StepsEntry.objects.create(user=self.user, count=4200, logged_date=self.today)
        StepsEntry.objects.create(user=self.user, count=8123, logged_date=self.yest)
        self._turn("How many steps today?")
        ans = self._turn("Compared to yesterday.")["answer"]
        self.assertIn("3923", ans)                            # the delta itself
        self.assertTrue("down" in ans.lower() or "up" in ans.lower())
