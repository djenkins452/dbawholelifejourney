# ==============================================================================
# File: apps/ai/tests/test_referential_resolution.py
# Description: Referential Conversation Resolution. Once a topic is established, a bare
#   reference ("what about yesterday?", "compared to today") resolves against the active
#   frame (topic + timeframe) — same subject, new timeframe/comparison — with no restated
#   subject, no topic drift, no generic coaching. Origin: production conversation where
#   "What about yesterday?" failed and "Compared to today." drifted to sleep coaching.
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
from apps.ai.chatgpt_cos.referential import _classify_reference

User = get_user_model()


class ReferenceClassifierTests(SimpleTestCase):
    def test_timeframe_references(self):
        self.assertEqual(_classify_reference("what about yesterday"), ("timeframe", "yesterday"))
        self.assertEqual(_classify_reference("how about today"), ("timeframe", "today"))
        self.assertEqual(_classify_reference("what about last week"), ("timeframe", "last_week"))

    def test_comparison_references(self):
        self.assertEqual(_classify_reference("compared to today"), ("compare", "today"))
        self.assertEqual(_classify_reference("compared to my average"), ("compare", "average"))
        self.assertEqual(_classify_reference("how does that compare"), ("compare", None))

    def test_non_reference_returns_none(self):
        self.assertIsNone(_classify_reference("what's my weight"))
        self.assertIsNone(_classify_reference("tell me a joke"))


class ReferentialConversationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="refconv@test.com", password="x")
        self.today = get_user_today(self.user)
        self.yest = self.today - timedelta(days=1)
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _turn(self, q):
        """Production routing order: why_explainer → referential → foundational."""
        r = (_why_explainer_lane(self.user, q, self.conv)
             or _referential_lane(self.user, q, self.conv)
             or answer_foundational_fact(self.user, q))
        if r:
            record_last_answer(self.conv, r.get("lane", "foundational_facts"), r)
            self.conv.refresh_from_db()
        return r

    def _frame(self):
        return self.conv.metadata["last_answer"].get("topic")

    def test_meals_what_about_yesterday_repoints_without_restating(self):
        FoodEntry.objects.create(user=self.user, food_name="Oatmeal", meal_type="breakfast",
                                 logged_date=self.today, serving_size=1, quantity=1)
        FoodEntry.objects.create(user=self.user, food_name="Eggs", meal_type="breakfast",
                                 logged_date=self.yest, serving_size=1, quantity=1)
        self._turn("What did I eat today?")
        self.assertEqual(self._frame(), "meals")
        # "What about yesterday?" — same topic, new timeframe, no restated subject.
        r = self._turn("What about yesterday?")
        self.assertEqual(r["fast_path"], "referential_resolution")
        self.assertIn("Eggs", r["answer"])
        self.assertEqual(self._frame(), "meals")           # still on meals, not drifted
        # "Compared to today." — stays on the meals topic (never sleep coaching).
        r = self._turn("Compared to today.")
        self.assertIn("Oatmeal", r["answer"])
        self.assertEqual(self._frame(), "meals")

    def test_steps_comparison_resolves_numerically(self):
        StepsEntry.objects.create(user=self.user, count=4200, logged_date=self.today)
        StepsEntry.objects.create(user=self.user, count=8123, logged_date=self.yest)
        self._turn("How many steps today?")
        self.assertEqual(self._frame(), "steps")
        r = self._turn("What about yesterday?")
        self.assertIn("8123", r["answer"])
        r = self._turn("Compared to today.")
        self.assertEqual(r["fast_path"], "referential_resolution")
        self.assertIn("3,923", r["answer"])                 # numeric delta, on-topic

    def test_new_full_question_is_not_hijacked_by_stale_frame(self):
        # After a meals topic, "How many steps today?" is a NEW subject — the word
        # "today" must NOT re-point it to the stale meals topic.
        FoodEntry.objects.create(user=self.user, food_name="Oatmeal", meal_type="breakfast",
                                 logged_date=self.today, serving_size=1, quantity=1)
        StepsEntry.objects.create(user=self.user, count=4200, logged_date=self.today)
        self._turn("What did I eat today?")
        r = self._turn("How many steps today?")
        self.assertEqual(r["fact_key"], "steps_today")     # new subject answered
        self.assertEqual(self._frame(), "steps")
        self.assertIn("4200", r["answer"])

    def test_reference_with_no_active_topic_declines(self):
        fresh = AssistantConversation.objects.create(user=self.user)
        self.assertIsNone(_referential_lane(self.user, "What about yesterday?", fresh))
