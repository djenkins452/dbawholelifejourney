# ==============================================================================
# File: apps/ai/tests/test_comparison_semantics.py
# Description: Comparison Semantics. Each metric declares HOW it should be compared; the
#   engine asks the domain and executes — it never guesses. Glucose must NOT default to
#   point-vs-point (noisy); it compares against the average and explains why. Steps/
#   calories compare running totals; weight compares the latest weigh-in, not an average.
#   See docs/COMPARISON_SEMANTICS_MATRIX.md.
# ==============================================================================
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.ai.models import AssistantConversation
from apps.ai.chatgpt_cos.lanes import _why_explainer_lane, _referential_lane
from apps.ai.chatgpt_cos import conversation_object as CO

User = get_user_model()


class SemanticsRegistryTests(SimpleTestCase):
    def test_each_metric_declares_its_strategy(self):
        self.assertEqual(CO.comparison_semantics("glucose")["strategy"], "average")
        self.assertEqual(CO.comparison_semantics("steps")["strategy"], "running_total")
        self.assertEqual(CO.comparison_semantics("calories")["strategy"], "running_total")
        self.assertEqual(CO.comparison_semantics("weight")["strategy"], "latest")
        self.assertEqual(CO.comparison_semantics("sleep")["strategy"], "nightly")

    def test_glucose_is_high_confidence_via_average_not_point(self):
        sem = CO.comparison_semantics("glucose")
        self.assertEqual(sem["confidence"], "high")
        self.assertIn("swing", sem["explanation"])           # has a real reason

    def test_unknown_topic_defaults_safely(self):
        self.assertEqual(CO.comparison_semantics("nonexistent")["strategy"], "latest")


class _Ask(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="cmpsem@test.com", password="x")

    def _ask(self, last, q):
        conv = AssistantConversation.objects.create(user=self.user)
        conv.metadata = {"last_answer": last}
        conv.save()
        return (_why_explainer_lane(self.user, q, conv)
                or _referential_lane(self.user, q, conv))


class GlucoseComparisonTests(_Ask):
    LAST = {
        "fact_key": "last_glucose_reading", "topic": "glucose", "timeframe": "today",
        "goal": "compare", "fact": {"value": 160, "unit": "mg/dL"},
        "supporting": {"average": {"key": "average_glucose_yesterday",
                                   "fact": {"value": 142, "unit": "mg/dL"}}},
    }

    def test_glucose_compares_against_average_and_explains(self):
        r = self._ask(self.LAST, "Compared to yesterday.")
        self.assertIsNotNone(r)
        self.assertIn("recent average", r["answer"])           # not point-vs-point
        self.assertIn("142", r["answer"])                      # the average baseline
        self.assertIn("readings", r["answer"].lower())         # the explanation
        self.assertEqual(r["comparison_confidence"], "high")


class StepsComparisonTests(_Ask):
    LAST = {
        "fact_key": "steps_today", "topic": "steps", "timeframe": "today",
        "goal": "compare", "fact": {"value": 4200, "unit": "steps"},
        "supporting": {"prior": {"key": "steps_yesterday",
                                 "fact": {"value": 8123, "unit": "steps"}}},
    }

    def test_steps_compare_running_totals_no_average_detour(self):
        r = self._ask(self.LAST, "Compared to yesterday.")
        self.assertIn("3923", r["answer"])                     # total vs total
        self.assertNotIn("recent average", r["answer"])        # NOT averaged
        self.assertNotIn("compared against your recent average", r["answer"])
