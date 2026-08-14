# ==============================================================================
# File: apps/ai/tests/test_domain_change_point.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Model Interface — the CHANGE-POINT branch. Verifies the catalog-driven
#   get_change_point surface composes canonical Weight history, detects a supported trend
#   shift (and honestly reports none), gives honest statuses, and is wired into the tool +
#   capability index + Question Catalog. Closes health.weight.trend_change_point (Phase 3c).
# ==============================================================================
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services.domain_change_point import (
    change_point_capability_index,
    change_point_capable_domains,
    get_domain_change_point,
)

User = get_user_model()


class DomainChangePointServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cp@test.com", password="x")

    def _weigh(self, days_ago, value):
        from apps.health.models import WeightEntry
        at = timezone.now() - timedelta(days=days_ago)
        return WeightEntry.objects.create(
            user=self.user, value=Decimal(str(round(value, 1))), unit="lb",
            recorded_at=at)

    def _fill(self, values_recent_first):
        """values_recent_first[i] is the weight i days ago (so index 0 = today)."""
        for days_ago, v in enumerate(values_recent_first):
            self._weigh(days_ago, v)

    # --- capability wiring ---
    def test_weight_is_change_point_capable(self):
        self.assertIn("health", change_point_capable_domains())
        self.assertIn("weight", change_point_capability_index()["health"])

    # --- supported change ---
    def test_detects_a_clear_trend_change(self):
        # Oldest→newest: 20 days flat-ish (280), then 20 days falling to ~270. Build
        # recent-first (today=lowest). A clear kink ~20 days ago.
        older_flat = [280 + (0.2 if i % 2 else -0.2) for i in range(20)]      # days 39..20
        recent_fall = [280 - 0.5 * (i + 1) for i in range(20)]               # days 19..0
        # recent-first = reverse of chronological
        chrono = older_flat + recent_fall
        self._fill(list(reversed(chrono)))
        r = get_domain_change_point(self.user, "health", "weight", period="last 90 days")
        self.assertEqual(r["status"], "ready")
        self.assertTrue(r["supported"])
        self.assertIn("change_date", r)
        self.assertIn("residual_reduction", r)
        self.assertEqual(r["granularity"], "change_point")
        self.assertEqual(r["unit"], "lb")
        # pre segment ~flat, post segment falling.
        self.assertEqual(r["post_change"]["direction"], "falling")

    # --- honest "no change" ---
    def test_steady_trend_reports_no_supported_change(self):
        chrono = [280 - 0.3 * i + (0.15 if i % 2 else -0.15) for i in range(30)]
        self._fill(list(reversed(chrono)))
        r = get_domain_change_point(self.user, "health", "weight", period="last 90 days")
        self.assertEqual(r["status"], "ready")
        self.assertFalse(r["supported"])
        self.assertIn("reason", r)
        self.assertIn("overall", r)               # still gives the single-trend direction

    # --- honest statuses ---
    def test_insufficient_history_reports_unsupported_change(self):
        self._fill([280, 279.5, 279, 278.5])      # 4 points < min_observations
        r = get_domain_change_point(self.user, "health", "weight", period="last 90 days")
        # 'ready' envelope, but not a supported change (honest insufficient reason).
        self.assertEqual(r["status"], "ready")
        self.assertFalse(r["supported"])
        self.assertIn("at least", r["reason"])

    def test_no_weight_data_is_empty(self):
        r = get_domain_change_point(self.user, "health", "weight", period="last 90 days")
        self.assertEqual(r["status"], "empty")

    def test_unsupported_metric(self):
        r = get_domain_change_point(self.user, "health", "not_a_metric",
                                    period="last 90 days")
        self.assertEqual(r["status"], "unsupported")

    def test_unsupported_domain(self):
        r = get_domain_change_point(self.user, "not_a_domain", "weight")
        self.assertEqual(r["status"], "unsupported_domain")

    def test_unresolvable_period(self):
        self._fill([280 - 0.3 * i for i in range(15)])
        r = get_domain_change_point(self.user, "health", "weight", period="qwerty")
        self.assertEqual(r["status"], "unsupported")

    def test_deterministic(self):
        chrono = [280 - (0.1 if i < 15 else 0.6) * i for i in range(30)]
        self._fill(list(reversed(chrono)))
        a = get_domain_change_point(self.user, "health", "weight", period="last 90 days")
        b = get_domain_change_point(self.user, "health", "weight", period="last 90 days")
        self.assertEqual(a.get("change_date"), b.get("change_date"))
        self.assertEqual(a.get("supported"), b.get("supported"))
