# ==============================================================================
# File: apps/ai/tests/test_trust_capabilities.py
# Description: Trust Sprint #1. Capabilities that eliminate production trust failures:
#   TF4 topic-aware meta ("is that an average?"), TF5 conversational patterns
#   ("what changed?", "anything else?"), TF1 deep-timeline stays on-topic (no drift),
#   TF3 presentation consistency (no internal key leaks). Classified by customer trust,
#   not by code. See docs/TRUST_FAILURE_INVENTORY.md.
# ==============================================================================
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.lanes import _why_explainer_lane, _referential_lane
from apps.ai.chatgpt_cos.foundational_facts import format_fact_sentence

User = get_user_model()

_GLUCOSE_OBJECT = {
    "fact_key": "last_glucose_reading", "topic": "glucose", "timeframe": "today",
    "fact": {"value": 160, "unit": "mg/dL", "recorded_at": "2026-06-29T08:00:00"},
    "supporting": {"average": {"key": "average_glucose_yesterday",
                               "fact": {"value": 142, "unit": "mg/dL"}}},
    "answer": "Your last glucose reading was 160 mg/dL.",
}


class TopicAwareMetaTests(TestCase):
    """TF4 — meta-questions resolve against the active object, never a clarifying Q."""

    def setUp(self):
        self.user = User.objects.create_user(email="meta@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)
        self.conv.metadata = {"last_answer": dict(_GLUCOSE_OBJECT)}
        self.conv.save()

    def _ask(self, q):
        r = _why_explainer_lane(self.user, q, self.conv) or _referential_lane(self.user, q, self.conv)
        return (r or {}).get("answer")

    def test_is_that_an_average_knows_it_is_a_single_reading(self):
        ans = self._ask("Is that an average?")
        self.assertIsNotNone(ans)
        self.assertIn("single reading", ans.lower())
        self.assertIn("142", ans)               # offers the average — anticipates next Q

    def test_is_that_an_average_says_yes_for_an_average_fact(self):
        self.conv.metadata = {"last_answer": {
            "fact_key": "average_sleep_7d", "topic": "sleep",
            "fact": {"value": 6.7, "unit": "hours"}, "supporting": {}}}
        self.conv.save()
        self.assertIn("average", (self._ask("Is that an average?") or "").lower())

    def test_what_changed_gives_the_comparison(self):
        ans = self._ask("What changed?")
        self.assertIn("18", ans)                 # 160 vs 142 average
        self.assertIn("up", ans.lower())

    def test_anything_else_surfaces_supporting_without_leaking_keys(self):
        ans = self._ask("Anything else?")
        self.assertIn("142", ans)
        self.assertNotIn("average_glucose_yesterday", ans)   # TF3: no internal name
        self.assertNotIn("_", ans)


class DeepTimelineStaysOnTopicTests(TestCase):
    """TF1 — deep-timeline references are recognized and stay ON-TOPIC (no drift) even
    though real N-day/N-month retrieval is the next sprint."""

    def setUp(self):
        self.user = User.objects.create_user(email="tl@test.com", password="x")
        self.conv = AssistantConversation.objects.create(user=self.user)
        self.conv.metadata = {"last_answer": dict(_GLUCOSE_OBJECT)}
        self.conv.save()

    def test_day_before_yesterday_stays_on_glucose(self):
        r = _referential_lane(self.user, "Day before yesterday?", self.conv)
        self.assertIsNotNone(r)                  # claimed, not dropped to a drifting lane
        self.assertIn("glucose", r["answer"].lower())

    def test_last_month_stays_on_topic(self):
        r = _referential_lane(self.user, "Compared to last month?", self.conv)
        self.assertIsNotNone(r)
        self.assertIn("glucose", r["answer"].lower())


class PresentationConsistencyGuardTests(SimpleTestCase):
    """TF3 — no deterministic answer may leak a raw snake_case key or internal name."""

    def test_unmapped_key_humanizes_never_leaks_snake_case(self):
        s = format_fact_sentence("some_internal_metric", {"value": 5, "unit": "x"})
        self.assertNotIn("some_internal_metric", s)
        self.assertNotIn("_", s)

    def test_glucose_average_renders_cleanly(self):
        s = format_fact_sentence("average_glucose_yesterday", {"value": 142, "unit": "mg/dL"})
        self.assertNotIn("_", s)
        self.assertIn("142", s)
        self.assertIn("average", s.lower())
