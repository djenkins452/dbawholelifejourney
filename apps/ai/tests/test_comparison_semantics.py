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


class GlucoseTargetVsSemanticsTests(_Ask):
    """Comparison TARGET (user's request) is honored first; Comparison SEMANTICS (the
    average) is offered AFTER — additive, never substitutive."""

    LAST = {
        "fact_key": "last_glucose_reading", "topic": "glucose", "timeframe": "today",
        "goal": "compare", "fact": {"value": 160, "unit": "mg/dL"},
        "supporting": {"average": {"key": "average_glucose_yesterday",
                                   "fact": {"value": 142, "unit": "mg/dL"}}},
    }

    def setUp(self):
        super().setUp()
        from datetime import timedelta, datetime, time
        from django.utils import timezone
        from apps.core.utils import get_user_today
        from apps.health.models import GlucoseEntry
        # Anchor at yesterday NOON (date-boundary-safe — a now-minus-26h seed lands
        # outside the day window when the suite runs near midnight).
        y = get_user_today(self.user) - timedelta(days=1)
        GlucoseEntry.objects.create(user=self.user, value=105, unit="mg/dL",
                                    recorded_at=timezone.make_aware(datetime.combine(y, time(12, 0))))

    def test_honors_yesterday_first_then_offers_average(self):
        r = self._ask(self.LAST, "Compared to yesterday.")
        a = r["answer"]
        # 1) the user's explicit target is answered FIRST — not replaced.
        self.assertIn("from yesterday", a)
        self.assertIn("105", a)
        # 2) the average is offered AFTERWARD — additive.
        self.assertIn("recent average", a)
        self.assertIn("142", a)
        self.assertLess(a.index("yesterday"), a.index("recent average"))   # sequence
        self.assertEqual(r["comparison_confidence"], "high")

    def test_explicit_average_target_is_not_doubled(self):
        # User asked FOR the average → answer it; don't append a redundant recommendation.
        a = self._ask(self.LAST, "Compared to my average.")["answer"]
        self.assertIn("recent average", a)
        self.assertNotIn("more meaningful", a)

    def test_missing_target_is_not_silently_substituted(self):
        # No yesterday reading → say so explicitly, then offer the average. Never pretend
        # the average was the requested comparison.
        from apps.health.models import GlucoseEntry
        GlucoseEntry.objects.all().delete()
        a = self._ask(self.LAST, "Compared to yesterday.")["answer"]
        self.assertIn("don't have", a.lower())
        self.assertIn("recent average", a)


class GlucoseAverageSurvivesRepointTests(TestCase):
    """Production regression: the recent average must survive a re-point to yesterday so
    a later "compared to my average" still resolves, and glucose_yesterday must render
    through the presentation layer (not the raw 'Glucose yesterday: 105' default)."""

    def setUp(self):
        from datetime import timedelta, datetime, time
        from django.utils import timezone
        from apps.core.utils import get_user_today
        from apps.health.models import GlucoseEntry
        self.user = User.objects.create_user(email="grepoint@test.com", password="x")
        today = get_user_today(self.user)

        def at_noon(d):  # date-boundary-safe anchor
            return timezone.make_aware(datetime.combine(d, time(12, 0)))
        GlucoseEntry.objects.create(user=self.user, value=160, unit="mg/dL",
                                    recorded_at=timezone.now())
        GlucoseEntry.objects.create(user=self.user, value=105, unit="mg/dL",
                                    recorded_at=at_noon(today - timedelta(days=1)))
        for d in range(2, 7):
            GlucoseEntry.objects.create(user=self.user, value=140, unit="mg/dL",
                                        recorded_at=at_noon(today - timedelta(days=d)))
        # Establish the SAE snapshot precondition the request path READS but never
        # rebuilds (Phase-3 request-path safety). Production guarantees a warm
        # snapshot via the background worker; the test must establish it explicitly
        # so the certified reasoning (comparison anchor + average resolution) is
        # exercised deterministically, not left to an incidental eager rebuild whose
        # timing makes the gate order-dependent.
        from apps.core.ai_state.state_engine import rebuild_user_state
        rebuild_user_state(self.user)
        from apps.ai.models import AssistantConversation
        self.conv = AssistantConversation.objects.create(user=self.user)

    def _turn(self, q):
        from apps.ai.chatgpt_cos.foundational_facts import answer_foundational_fact
        from apps.ai.chatgpt_cos.conversation_memory import record_last_answer
        r = (_why_explainer_lane(self.user, q, self.conv)
             or _referential_lane(self.user, q, self.conv)
             or answer_foundational_fact(self.user, q))
        if r:
            record_last_answer(self.conv, r.get("lane", "foundational_facts"), r)
            self.conv.refresh_from_db()
        return r

    def test_full_production_conversation(self):
        self._turn("What is my BG?")
        yest = self._turn("What about yesterday?")["answer"]
        self.assertIn("Yesterday your glucose was", yest)        # presentation, not default
        self.assertNotIn("Glucose yesterday:", yest)
        self.assertIn("average", self.conv.metadata["last_answer"]["supporting"])  # kept
        self._turn("Compared to today.")                          # comparison turn
        self.assertIn("average", self.conv.metadata["last_answer"]["supporting"])  # still kept
        avg = self._turn("Compared to my average.")["answer"]
        self.assertNotIn("don't have", avg.lower())               # the bug is gone
        self.assertIn("recent average", avg)


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
