# ==============================================================================
# File: apps/ai/tests/test_active_subject.py
# Description: Active Subject tracking. The Conversation Object tracks Topic + Goal +
#   Active Subject (which object owns the conversation). Comparisons anchor on the Active
#   Subject and must NOT move it; only a primary question or an explicit refocus ("what
#   about yesterday?" / "compared to today") moves it. Production bug: "compared to my
#   average" anchored on yesterday instead of the current reading under discussion.
# ==============================================================================
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.lanes import _referential_lane
from apps.ai.chatgpt_cos import referential as R

User = get_user_model()


class AnchorDoesNotDriftTests(TestCase):
    """A comparison anchors on the Active Subject — never on whatever was last answered."""

    def setUp(self):
        self.user = User.objects.create_user(email="anchor@test.com", password="x")

    def _ask(self, last, q):
        conv = AssistantConversation.objects.create(user=self.user)
        conv.metadata = {"last_answer": last}
        conv.save()
        return _referential_lane(self.user, q, conv)

    def test_compared_to_average_anchors_on_active_subject_not_last_answer(self):
        # The frame: we were focused on the CURRENT reading (160), even though the last
        # answer shown was yesterday (105). "Compared to my average" must use 160.
        last = {
            "fact_key": "glucose_yesterday", "topic": "glucose", "timeframe": "yesterday",
            "goal": "compare", "fact": {"value": 105, "unit": "mg/dL"},
            "active_subject": {"fact_key": "last_glucose_reading",
                               "fact": {"value": 160, "unit": "mg/dL"}},
            "supporting": {"average": {"key": "average_glucose_yesterday",
                                       "fact": {"value": 138, "unit": "mg/dL"}}},
        }
        ans = self._ask(last, "Compared to my average.")["answer"]
        self.assertIn("160", ans)                  # anchored on the current reading
        self.assertIn("138", ans)                  # vs the average
        self.assertNotIn("105", ans)               # NOT anchored on yesterday

    def test_compare_to_average_does_not_move_the_active_subject(self):
        last = {
            "fact_key": "last_glucose_reading", "topic": "glucose", "timeframe": "today",
            "goal": "compare", "fact": {"value": 160, "unit": "mg/dL"},
            "active_subject": {"fact_key": "last_glucose_reading",
                               "fact": {"value": 160, "unit": "mg/dL"}},
            "supporting": {"average": {"key": "average_glucose_yesterday",
                                       "fact": {"value": 138, "unit": "mg/dL"}}},
        }
        r = self._ask(last, "Compared to my average.")
        # A pure comparison carries no active_subject change (record carries it forward).
        self.assertNotIn("active_subject", r)


class RepointAndRecenterTests(TestCase):
    """Explicit refocus moves the anchor; "compared to today" re-centers it on current."""

    def setUp(self):
        from datetime import timedelta
        from apps.core.utils import get_user_today
        from apps.health.models import StepsEntry
        self.user = User.objects.create_user(email="recenter@test.com", password="x")
        today = get_user_today(self.user)
        StepsEntry.objects.create(user=self.user, count=4200, logged_date=today)
        StepsEntry.objects.create(user=self.user, count=8123, logged_date=today - timedelta(days=1))
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _turn(self, q):
        from apps.ai.chatgpt_cos.foundational_facts import answer_foundational_fact
        from apps.ai.chatgpt_cos.conversation_memory import record_last_answer
        from apps.ai.chatgpt_cos.lanes import _why_explainer_lane
        r = (_why_explainer_lane(self.user, q, self.conv)
             or _referential_lane(self.user, q, self.conv)
             or answer_foundational_fact(self.user, q))
        if r:
            record_last_answer(self.conv, r.get("lane", "foundational_facts"), r)
            self.conv.refresh_from_db()
        return r

    def _subject(self):
        return (self.conv.metadata["last_answer"].get("active_subject") or {}).get("fact_key")

    def test_repoint_moves_then_compared_to_today_recenters(self):
        self._turn("How many steps today?")
        self.assertEqual(self._subject(), "steps_today")            # primary
        self._turn("What about yesterday?")
        self.assertEqual(self._subject(), "steps_yesterday")        # explicit refocus moves it
        self._turn("Compared to today.")
        self.assertEqual(self._subject(), "steps_today")            # re-centered on current
