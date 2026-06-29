# ==============================================================================
# File: apps/ai/tests/test_conversation_goal.py
# Description: Conversational Goal Tracking. The Conversation Object stores not just the
#   topic but the GOAL (review → compare → trend → investigate). The topic stays stable;
#   the goal evolves. Production failure: meals today→yesterday→"compared to today"
#   returned today's meals instead of COMPARING them — the objective was lost.
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
from apps.ai.chatgpt_cos import conversation_object as CO

User = get_user_model()


class GoalEvolutionTests(SimpleTestCase):
    def test_fresh_topic_is_review(self):
        self.assertEqual(CO.evolve_goal(None, "meals", "today"), CO.GOAL_REVIEW)

    def test_new_timeframe_same_topic_becomes_compare(self):
        prev = {"topic": "meals", "timeframe": "today", "goal": "review"}
        self.assertEqual(CO.evolve_goal(prev, "meals", "yesterday"), CO.GOAL_COMPARE)

    def test_topic_change_resets_to_review(self):
        prev = {"topic": "meals", "timeframe": "today", "goal": "compare"}
        self.assertEqual(CO.evolve_goal(prev, "steps", "today"), CO.GOAL_REVIEW)

    def test_explicit_hint_wins(self):
        prev = {"topic": "glucose", "timeframe": "today", "goal": "compare"}
        self.assertEqual(CO.evolve_goal(prev, "glucose", "today", explicit="trend"),
                         CO.GOAL_TREND)


class _ConvBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cgoal@test.com", password="x")
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

    def _goal(self):
        return self.conv.metadata["last_answer"].get("goal")


class MealsComparisonGoalTests(_ConvBase):
    def setUp(self):
        super().setUp()
        FoodEntry.objects.create(user=self.user, food_name="Oatmeal", meal_type="breakfast",
                                 logged_date=self.today, serving_size=1, quantity=1)
        FoodEntry.objects.create(user=self.user, food_name="Eggs", meal_type="breakfast",
                                 logged_date=self.yest, serving_size=1, quantity=1)

    def test_compared_to_today_returns_side_by_side_not_just_today(self):
        # The exact production failure.
        self._turn("What did I eat today?")
        self.assertEqual(self._goal(), "review")
        self._turn("What about yesterday?")
        self.assertEqual(self._goal(), "compare")             # objective emerged
        self._turn("What about the day before yesterday?")
        self.assertEqual(self._goal(), "compare")             # objective persists
        r = self._turn("Compared to today.")
        # The COMPARISON itself — names what differed, not a repeat of today's list.
        self.assertIn("differed", r["answer"].lower())
        self.assertIn("Eggs", r["answer"])
        self.assertIn("Oatmeal", r["answer"])
        self.assertNotIn("you've logged:", r["answer"].lower())
        self.assertEqual(self._goal(), "compare")


class StepsGoalProgressionTests(_ConvBase):
    def setUp(self):
        super().setUp()
        StepsEntry.objects.create(user=self.user, count=4200, logged_date=self.today)
        StepsEntry.objects.create(user=self.user, count=8123, logged_date=self.yest)

    def test_review_then_compare(self):
        self._turn("How many steps today?")
        self.assertEqual(self._goal(), "review")
        r = self._turn("Compared to yesterday.")
        self.assertIn("3923", r["answer"])
        self.assertEqual(self._goal(), "compare")

    def test_new_subject_resets_goal(self):
        # After a steps comparison, asking a fresh meals question resets the objective.
        FoodEntry.objects.create(user=self.user, food_name="Oatmeal", meal_type="breakfast",
                                 logged_date=self.today, serving_size=1, quantity=1)
        self._turn("How many steps today?")
        self._turn("Compared to yesterday.")
        self.assertEqual(self._goal(), "compare")
        self._turn("What did I eat today?")
        self.assertEqual(self.conv.metadata["last_answer"]["topic"], "meals")
        self.assertEqual(self._goal(), "review")              # intentional direction change
