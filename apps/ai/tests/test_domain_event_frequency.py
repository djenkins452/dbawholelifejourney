# ==============================================================================
# File: apps/ai/tests/test_domain_event_frequency.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Model Interface — the EVENT-FREQUENCY branch. Verifies the catalog-driven
#   get_event_frequency surface counts a named event across recurring windows, carries the
#   reused frequency trend, gives honest statuses, and is wired into the tool + capability
#   index + Question Catalog. This is the surface that closes the "are my overnight lows
#   getting MORE FREQUENT" gap (Phase 3b).
# ==============================================================================
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_event_frequency import (
    event_frequency_capability_index,
    event_frequency_capable_domains,
    get_domain_event_frequency,
)

User = get_user_model()


class DomainEventFrequencyServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="ef@test.com", password="x")

    def _night(self, value, days_ago, hour=2):
        from apps.core.utils import get_user_now
        from apps.health.models import GlucoseEntry
        now = get_user_now(self.user)
        at = (now - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0,
                                                      microsecond=0)
        return GlucoseEntry.objects.create(
            user=self.user, value=Decimal(str(value)), unit="mg/dL", context="cgm",
            source="dexcom", recorded_at=at)

    # --- capability wiring ---
    def test_glucose_is_event_frequency_capable(self):
        self.assertIn("health", event_frequency_capable_domains())
        self.assertIn("glucose", event_frequency_capability_index()["health"])

    # --- the core deterministic frequency retrieval ---
    def test_overnight_lows_counted_per_night_with_trend(self):
        # Rising overnight lows: night -5 one low, -3 two lows, -1 three lows.
        self._night(120, 5, 1); self._night(65, 5, 2)                      # 1 low
        self._night(60, 3, 1); self._night(50, 3, 3)                      # 2 lows
        self._night(68, 1, 1); self._night(66, 1, 2); self._night(48, 1, 4)  # 3 lows
        r = get_domain_event_frequency(self.user, "health", "glucose",
                                       event="low", window="night", period="last_7_days")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["event"], "low")
        self.assertEqual(r["total_events"], 6)
        self.assertEqual(r["windows_with_data"], 3)
        self.assertEqual(r["change"]["direction"], "rising")
        self.assertEqual(r["granularity"], "event_frequency")

    def test_severe_lows_use_urgent_event(self):
        self._night(50, 3, 2)                       # urgent low (<54)
        self._night(60, 1, 2); self._night(48, 1, 3)   # one urgent low (48)
        r = get_domain_event_frequency(self.user, "health", "glucose",
                                       event="urgent_low", window="night",
                                       period="last_7_days")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["total_events"], 2)

    def test_by_hour_answers_time_of_night(self):
        self._night(50, 3, 3); self._night(48, 1, 3)   # both at 03:00
        r = get_domain_event_frequency(self.user, "health", "glucose",
                                       event="low", window="night", period="last_7_days")
        self.assertEqual(r["by_hour"]["peak_hour"], 3)

    # --- honest statuses (never a guess) ---
    def test_no_data_is_honest_empty_not_zero_events(self):
        r = get_domain_event_frequency(self.user, "health", "glucose",
                                       event="low", window="night", period="last_7_days")
        self.assertEqual(r["status"], "empty")
        self.assertIn("not that there were no events", r["reason"])

    def test_unknown_event_is_unsupported(self):
        r = get_domain_event_frequency(self.user, "health", "glucose", event="meltdown")
        self.assertEqual(r["status"], "unsupported")
        self.assertIn("low", r["supported_events"])

    def test_unknown_window_kind_is_unsupported(self):
        r = get_domain_event_frequency(self.user, "health", "glucose", window="whenever")
        self.assertEqual(r["status"], "unsupported")
        self.assertIn("night", r["supported_windows"])

    def test_unsupported_metric(self):
        r = get_domain_event_frequency(self.user, "health", "steps")
        self.assertEqual(r["status"], "unsupported")

    def test_unknown_domain(self):
        r = get_domain_event_frequency(self.user, "nonsense", "glucose")
        self.assertEqual(r["status"], "unsupported_domain")

    def test_unresolvable_period_is_unsupported(self):
        r = get_domain_event_frequency(self.user, "health", "glucose",
                                       period="the good old days")
        self.assertEqual(r["status"], "unsupported")


class GetEventFrequencyToolWiringTests(TestCase):
    def test_tool_is_registered_with_event_frequency_domains_enum(self):
        from apps.ai.model_interface.constitution import truth_tools
        tools = truth_tools()
        names = {t["function"]["name"] for t in tools}
        self.assertIn("get_event_frequency", names)
        tool = next(t for t in tools if t["function"]["name"] == "get_event_frequency")
        props = tool["function"]["parameters"]["properties"]
        self.assertEqual(set(tool["function"]["parameters"]["required"]),
                         {"domain", "metric"})
        self.assertIn("event", props)
        self.assertIn("window", props)
        self.assertIn("low", props["event"]["enum"])
        self.assertIn("night", props["window"]["enum"])

    def test_capability_index_advertises_truth_event_frequency(self):
        from apps.ai.cos_services.current_context import _capabilities
        caps = _capabilities()
        self.assertIn("truth_event_frequency", caps)
        self.assertIn("glucose", caps["truth_event_frequency"].get("health", []))
        self.assertIn("truth_event_frequency", caps["surface_roles"])
