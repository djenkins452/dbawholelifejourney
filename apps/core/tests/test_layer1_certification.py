# ==============================================================================
# File: apps/core/tests/test_layer1_certification.py
# Description: LAYER 1 CERTIFICATION GATE (Canonical Truth). The authoritative,
#   permanent proof that the Layer 1 foundation is intact. Exercises every Layer 1
#   platform capability end-to-end and checks the certification manifest is
#   consistent. Once GREEN, Layer 1 is frozen — this gate must never regress, and
#   every future layer's release gate re-runs it. No OpenAI.
# ==============================================================================
from datetime import date, timedelta
from importlib import import_module

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.truth import certification as CERT
from apps.core.truth import freshness as F
from apps.core.truth.current import CurrentTruth
from apps.core.truth.domain import get_domain_truth, registered_domains
from apps.core.truth.history import series_from_rows
from apps.core.truth.periods import resolve_period
from apps.core.utils import get_user_today
from apps.health.models import StepsEntry, SleepEntry, WorkoutSession

User = get_user_model()


class Layer1ManifestTests(SimpleTestCase):
    def test_layer1_declares_its_capabilities(self):
        self.assertEqual(CERT.LAYER_1["name"], "Canonical Truth")
        for cap in ("Per-Day Truth", "Freshness", "Confidence", "Stability",
                    "Current Truth Objects", "Point-in-Time History",
                    "Domain Truth Objects", "Deterministic Provider Registry",
                    "Truth Catalog"):
            self.assertIn(cap, CERT.LAYER_1["capabilities"])

    def test_platform_modules_all_import(self):
        for mod in CERT.LAYER_1["platform_modules"]:
            import_module(mod)        # raises if a Layer 1 module went missing

    def test_certification_modules_union_includes_layer1(self):
        mods = CERT.certification_modules(1)
        self.assertIn("apps.core.tests.test_layer1_certification", mods)
        self.assertEqual(len(mods), len(set(mods)))   # de-duplicated


class Layer1CapabilityGateTests(TestCase):
    """One end-to-end assertion per capability — the spine of the foundation."""

    def setUp(self):
        self.user = User.objects.create_user(email="cert@test.com", password="x")
        self.today = get_user_today(self.user)
        self.yest = self.today - timedelta(days=1)

    def test_freshness_capability(self):
        self.assertEqual(
            F.classify_period_freshness(has_data=True, requested_date=self.today,
                                        data_date=self.today, today=self.today,
                                        is_cumulative=True), F.PARTIAL)

    def test_confidence_capability(self):
        from apps.core.truth import confidence as C
        self.assertEqual(C.confidence_from_freshness(F.CURRENT), C.HIGH)
        self.assertEqual(C.confidence_from_coverage(1, 7), C.LOW)
        self.assertEqual(C.combine(C.HIGH, C.LOW), C.LOW)

    def test_stability_capability(self):
        from apps.core.truth import stability as S
        a = CurrentTruth.found("health", "steps_yesterday", 8123, F.CURRENT)
        b = CurrentTruth.found("health", "steps_yesterday", 8123, F.STALE)
        self.assertEqual(S.truth_signature(a), S.truth_signature(b))  # data-stable
        res = S.verify_stable(lambda: CurrentTruth.found("d", "m", 1, F.CURRENT))
        self.assertTrue(res["stable"])

    def test_period_resolution_capability(self):
        p = resolve_period("yesterday", date(2026, 6, 17))
        self.assertEqual((p.start, p.end), (date(2026, 6, 16), date(2026, 6, 16)))

    def test_history_series_capability(self):
        s = series_from_rows("d", "m",
                             resolve_period("last_7_days", self.today),
                             [{"date": self.yest, "value": 10},
                              {"date": self.today, "value": 30}])
        self.assertEqual(s.total(), 40)
        self.assertEqual(s.average(), 20)

    def test_current_truth_object_capability(self):
        ct = CurrentTruth.found("health", "steps_yesterday", 8123, F.CURRENT)
        self.assertEqual(ct.to_fact_dict()["value"], 8123)

    def test_per_day_truth_capability(self):
        from apps.health.services.daily_health_queries import DailyHealthQueries
        StepsEntry.objects.create(user=self.user, count=8123, logged_date=self.yest)
        self.assertEqual(DailyHealthQueries.steps_on(self.user, self.yest)["value"], 8123)

    def test_domain_truth_object_capability(self):
        StepsEntry.objects.create(user=self.user, count=4200, logged_date=self.today)
        WorkoutSession.objects.create(user=self.user, duration_minutes=30,
                                      date=self.today)
        truth = get_domain_truth(self.user, "health")
        self.assertEqual(truth.current("steps_today").value, 4200)
        self.assertEqual(truth.history("workouts", "last_7_days", today=self.today).total(), 1)
        self.assertIn("health", registered_domains())
        self.assertIn("finance", registered_domains())

    def test_truth_catalog_capability(self):
        from apps.core.truth import catalog as CAT
        self.assertTrue(CAT.can_answer("health", "steps_today", "current"))
        self.assertTrue(CAT.can_answer("health", "steps", "history"))
        self.assertGreater(CAT.catalog_summary()["total_answerable"], 0)

    def test_deterministic_provider_registry_capability(self):
        import apps.ai.chatgpt_cos.foundational_facts  # noqa: F401 (registers providers)
        from apps.ai.chatgpt_cos.fact_registry import registered_sources
        for s in ("get_foundational_goal_facts", "get_foundational_execution_facts",
                  "get_foundational_health_facts"):
            self.assertIn(s, registered_sources())

    def test_beth_retrieves_per_day_truth_through_the_stack(self):
        # End-to-end: classify -> registry -> domain truth -> current -> phrasing.
        from apps.ai.chatgpt_cos.foundational_facts import (
            classify_foundational_fact, format_fact_sentence,
        )
        from apps.ai.cos_services.health_facts import get_foundational_health_facts
        SleepEntry.objects.create(
            user=self.user, sleep_date=self.yest, bedtime=timezone.now(),
            wake_time=timezone.now() + timedelta(hours=7),
            total_duration_minutes=432, asleep_duration_minutes=432)
        key = classify_foundational_fact("How did I sleep last night?")
        self.assertEqual(key, "sleep_last_night")
        fact = get_foundational_health_facts(self.user, [key])[key]
        self.assertIn("7.2", format_fact_sentence(key, fact))
