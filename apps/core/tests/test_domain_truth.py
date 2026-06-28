# ==============================================================================
# File: apps/core/tests/test_domain_truth.py
# Description: Platform capability — Domain Truth Objects (apps.core.truth.domain).
#   One canonical per-domain interface composing Current Truth + History + the SAE
#   snapshot. Tests the facade + registry, Health (current+history+state) and Finance
#   (current+state) consuming the SAME interface. No OpenAI.
# ==============================================================================
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.truth.domain import get_domain_truth, registered_domains
from apps.core.truth.history import HistorySeries
from apps.core.truth.current import CurrentTruth
from apps.core.utils import get_user_today
from apps.health.models import StepsEntry, WorkoutSession

User = get_user_model()


class DomainTruthRegistryTests(TestCase):
    def test_known_domains_register(self):
        self.assertIn("health", registered_domains())
        self.assertIn("finance", registered_domains())

    def test_unknown_domain_raises(self):
        with self.assertRaises(KeyError):
            get_domain_truth(User.objects.create_user(email="u@test.com", password="x"),
                             "nope")


class HealthDomainTruthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="hdt@test.com", password="x")
        self.today = get_user_today(self.user)
        self.truth = get_domain_truth(self.user, "health")

    def test_one_interface_for_current_and_history(self):
        StepsEntry.objects.create(user=self.user, count=8123,
                                  logged_date=self.today - timedelta(days=1))
        WorkoutSession.objects.create(user=self.user, duration_minutes=30,
                                      date=self.today - timedelta(days=2))
        cur = self.truth.current("steps_yesterday")
        self.assertIsInstance(cur, CurrentTruth)
        self.assertEqual(cur.value, 8123)

        hist = self.truth.history("steps", "last_7_days", today=self.today)
        self.assertIsInstance(hist, HistorySeries)
        self.assertEqual(hist.total(), 8123)

        workouts = self.truth.history("workouts", "last_7_days", today=self.today)
        self.assertEqual(workouts.total(), 1)

    def test_state_reads_sae_snapshot(self):
        with mock.patch("apps.core.ai_state.state_engine.get_module_state",
                        return_value={"weight_current": 285}) as gms:
            self.assertEqual(self.truth.state()["weight_current"], 285)
        gms.assert_called_once()

    def test_supports_introspection(self):
        s = self.truth.supports()
        self.assertIn("steps", s["history"])
        self.assertIn("sleep_last_night", s["current"])


class FinanceDomainTruthTests(TestCase):
    """Second domain behind the SAME interface."""

    def setUp(self):
        self.user = User.objects.create_user(email="fdt@test.com", password="x")
        self.truth = get_domain_truth(self.user, "finance")

    def test_current_net_worth_via_interface(self):
        state = {"_contract": {"summary": {"net_worth": 42000.0}}}
        with mock.patch("apps.core.ai_state.state_engine.get_module_state",
                        return_value=state):
            cur = self.truth.current("net_worth")
        self.assertIsInstance(cur, CurrentTruth)
        self.assertEqual(cur.value, 42000.0)
        self.assertEqual(cur.domain, "finance")


class BethConsumesDomainTruthTests(TestCase):
    """Beth's foundational fast-path now retrieves via the canonical interface."""

    def setUp(self):
        self.user = User.objects.create_user(email="beth@test.com", password="x")
        self.today = get_user_today(self.user)

    def test_day_fact_goes_through_domain_truth(self):
        from apps.ai.cos_services.health_facts import get_foundational_health_facts
        StepsEntry.objects.create(user=self.user, count=4200, logged_date=self.today)
        fact = get_foundational_health_facts(self.user, ["steps_today"])["steps_today"]
        self.assertEqual(fact["value"], 4200)
        self.assertEqual(fact["source"], "DailyHealthQueries")
