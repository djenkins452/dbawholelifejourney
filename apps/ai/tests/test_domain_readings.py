# ==============================================================================
# File: apps/ai/tests/test_domain_readings.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Model Interface — the intra-day READINGS branch. Verifies the
#   catalog-driven get_readings surface re-fronts DomainTruth.readings with honest
#   statuses, resolves natural windows, and is wired into the tool + capability index.
#   This is the surface that removes the "individual overnight CGM readings are
#   invisible to the CoS" defect class.
# ==============================================================================
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services.domain_readings import (
    get_domain_readings,
    readings_capability_index,
    readings_capable_domains,
)

User = get_user_model()


def _reading(user, value, minutes_before_now):
    from apps.health.models import GlucoseEntry
    return GlucoseEntry.objects.create(
        user=user, value=Decimal(str(value)), unit="mg/dL", context="cgm",
        source="dexcom",
        recorded_at=timezone.now() - timedelta(minutes=minutes_before_now),
    )


class DomainReadingsServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="dr@test.com", password="x")
        # An overnight-ish run of 5-min CGM readings ending ~1h ago, incl. extreme lows.
        vals = [120, 100, 85, 68, 65, 58, 55, 50, 49, 48, 41, 60, 80, 110]
        for i, v in enumerate(vals):
            _reading(cls.user, v, minutes_before_now=60 + (len(vals) - i) * 5)

    # --- capability wiring ---
    def test_glucose_is_readings_capable(self):
        self.assertIn("health", readings_capable_domains())
        self.assertIn("glucose", readings_capability_index()["health"])

    # --- the core deterministic intra-day retrieval ---
    def test_past_12_hours_returns_individual_readings_and_stats(self):
        r = get_domain_readings(self.user, "health", "glucose", window="past 12 hours")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["count"], 14)
        self.assertEqual(r["minimum"], 41.0)
        self.assertEqual(r["unit"], "mg/dL")
        # individual samples with timestamps (not a per-day average)
        self.assertTrue(r["samples"])
        self.assertIn("at", r["samples"][0])
        self.assertEqual(r["granularity"], "reading_window")

    def test_below_70_facts_answer_time_below_range(self):
        r = get_domain_readings(self.user, "health", "glucose", window="past 12 hours")
        # 68,65,58,55,50,49,48,41,60 = 9 readings below 70
        self.assertEqual(r["below_low"], 9)
        # 50,49,48,41 = 4 readings below 54 (severe)
        self.assertEqual(r["urgent_low_count"], 4)
        self.assertIsNotNone(r["below_low_pct"])

    def test_low_excursions_list_the_actual_lows(self):
        r = get_domain_readings(self.user, "health", "glucose", window="past 12 hours")
        worst = [e["value"] for e in r["low_excursions"]]
        self.assertEqual(worst[0], 41.0)          # worst-first
        self.assertIn(48.0, worst)

    def test_explicit_start_end_range(self):
        now = timezone.now()
        r = get_domain_readings(
            self.user, "health", "glucose",
            start=(now - timedelta(hours=12)).isoformat(),
            end=now.isoformat())
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["count"], 14)

    # --- honest statuses (never a guess) ---
    def test_empty_window_is_honest_empty_not_absence_claim(self):
        # a future-free but data-free window: the next-hour has no readings
        now = timezone.now()
        r = get_domain_readings(
            self.user, "health", "glucose",
            start=(now + timedelta(hours=1)).isoformat(),
            end=(now + timedelta(hours=2)).isoformat())
        self.assertEqual(r["status"], "empty")
        self.assertIn("not that the metric is unavailable", r["reason"])

    def test_unparseable_window_is_unsupported_with_guidance(self):
        r = get_domain_readings(self.user, "health", "glucose", window="the vibes")
        self.assertEqual(r["status"], "unsupported")
        self.assertIn("overnight", r["reason"])

    def test_unsupported_metric(self):
        r = get_domain_readings(self.user, "health", "steps", window="today")
        self.assertEqual(r["status"], "unsupported")

    def test_unknown_domain(self):
        r = get_domain_readings(self.user, "nonsense", "glucose", window="today")
        self.assertEqual(r["status"], "unsupported_domain")

    def test_day_phrase_falls_back_to_a_widened_window(self):
        # "today" is a day phrase; the service widens it to a datetime window.
        r = get_domain_readings(self.user, "health", "glucose", window="today")
        self.assertIn(r["status"], ("ready", "empty"))  # depends on wall-clock, both honest


class GetReadingsToolWiringTests(TestCase):
    def test_tool_is_registered_with_reading_domains_enum(self):
        from apps.ai.model_interface.constitution import truth_tools
        names = {t["function"]["name"] for t in truth_tools()}
        self.assertIn("get_readings", names)
        tool = next(t for t in truth_tools()
                    if t["function"]["name"] == "get_readings")
        props = tool["function"]["parameters"]["properties"]
        self.assertIn("window", props)
        self.assertEqual(set(tool["function"]["parameters"]["required"]),
                         {"domain", "metric"})

    def test_capability_index_advertises_truth_readings(self):
        from apps.ai.cos_services.current_context import _capabilities
        caps = _capabilities()
        self.assertIn("truth_readings", caps)
        self.assertIn("glucose", caps["truth_readings"].get("health", []))
        self.assertIn("truth_readings", caps["surface_roles"])
