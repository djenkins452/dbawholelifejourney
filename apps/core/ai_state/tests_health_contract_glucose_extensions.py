"""
HEALTH_CONTRACT glucose extensions (Phase 1A · C5) — regression coverage.

These tests pin two things:

1. The new metabolic-intelligence keys exist with safe defaults and are
   populated by build_health_state when real data is present, without
   disturbing any pre-existing HEALTH_CONTRACT key.

2. The Bible Journey workstream's additions to build_faith_state (the
   ``state["journey"]`` block) remain intact. C5 only edits
   build_health_state and HEALTH_CONTRACT; it must not regress the
   parallel faith_state work that landed concurrently.

Both assertions exist to satisfy the Wave 2 guardrail: shared SAE
infrastructure must stay additive across both workstreams.
"""

from __future__ import annotations

import inspect
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from apps.core.ai_state import state_builder
from apps.core.ai_state.state_builder import (
    HEALTH_CONTRACT,
    _validate_health_contract,
    build_faith_state,
    build_health_state,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


def _make_user(email: str = "c5_state@test.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ── New contract keys: shape + defaults ─────────────────────────────


class HealthContractKeysExistTests(SimpleTestCase):
    """The five new C5 keys are present with None defaults."""

    NEW_KEYS = (
        "glucose_avg_30d",
        "glucose_avg_90d",
        "time_in_range_pct_7d",
        "time_in_range_pct_30d",
        "overnight_avg_glucose",
    )

    def test_all_new_keys_in_contract(self):
        for key in self.NEW_KEYS:
            self.assertIn(key, HEALTH_CONTRACT, f"missing new C5 key: {key}")

    def test_all_new_keys_default_to_none(self):
        for key in self.NEW_KEYS:
            self.assertIsNone(
                HEALTH_CONTRACT[key],
                f"C5 key {key} should default to None",
            )

    def test_validate_fills_missing_new_keys_with_defaults(self):
        state = {}
        out = _validate_health_contract(state)
        for key in self.NEW_KEYS:
            self.assertIn(key, out)
            self.assertIsNone(out[key])


class ExistingContractKeysPreservedTests(SimpleTestCase):
    """C5 must not remove or alter any pre-existing HEALTH_CONTRACT key."""

    EXISTING_KEYS = (
        "sleep_status", "sleep_status_reason", "sleep_last_night_hours",
        "sleep_last_night_quality", "sleep_avg_hours_7d",
        "weight_status", "weight_status_reason", "weight_current",
        "weight_unit", "weight_trend", "weight_change_30d",
        "bp_status", "bp_status_reason", "bp_reading", "bp_category",
        "hr_status", "hr_status_reason", "hr_context",
        "latest_heart_rate", "heart_rate_avg_7d",
        "spo2_status", "spo2_status_reason", "spo2_context",
        "latest_blood_oxygen", "blood_oxygen_avg_7d",
        "glucose_status", "glucose_status_reason", "glucose_context",
        "latest_glucose", "latest_glucose_unit", "glucose_avg_7d",
        "steps_status", "steps_status_reason",
        "water_status", "water_status_reason",
    )

    def test_every_existing_key_still_present(self):
        for key in self.EXISTING_KEYS:
            self.assertIn(
                key, HEALTH_CONTRACT,
                f"pre-C5 key {key!r} was removed — additive violation",
            )

    def test_no_existing_key_default_changed_to_unexpected(self):
        # Spot-check a few defaults that have specific semantic meaning.
        self.assertEqual(HEALTH_CONTRACT["weight_unit"], "lb")
        self.assertEqual(HEALTH_CONTRACT["weight_trend"], "insufficient_data")
        for status_key in (
            "sleep_status", "weight_status", "bp_status", "hr_status",
            "spo2_status", "glucose_status", "steps_status", "water_status",
        ):
            self.assertEqual(HEALTH_CONTRACT[status_key], "no_data")


# ── Builder behavior ────────────────────────────────────────────────


class BuildHealthStateGlucoseExtensionsTests(TestCase):
    """build_health_state populates the new keys when data is present
    and falls back to safe defaults when it isn't."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("builder@test.com")

    def test_empty_user_returns_none_for_new_keys(self):
        state = build_health_state(self.user)
        for key in (
            "glucose_avg_30d", "glucose_avg_90d",
            "time_in_range_pct_7d", "time_in_range_pct_30d",
            "overnight_avg_glucose",
        ):
            self.assertIn(key, state)
            self.assertIsNone(state[key], f"{key} should be None for empty user")

    def test_glucose_avg_30d_and_90d_computed_when_data_present(self):
        from apps.health.models import GlucoseEntry

        now = datetime.now(timezone.utc)
        # Three readings in the last 30 days, all 130.
        for days_ago in (1, 10, 25):
            GlucoseEntry.objects.create(
                user=self.user,
                value=Decimal("130"),
                unit="mg/dL",
                recorded_at=now - timedelta(days=days_ago),
            )
        # Two older readings (60 and 80 days ago) at 160 — should affect
        # 90d but not 30d.
        for days_ago, val in ((60, 160), (80, 160)):
            GlucoseEntry.objects.create(
                user=self.user,
                value=Decimal(val),
                unit="mg/dL",
                recorded_at=now - timedelta(days=days_ago),
            )
        state = build_health_state(self.user)
        self.assertEqual(state["glucose_avg_30d"], 130)
        # 90d average pulls in all five readings: (130*3 + 160*2)/5 = 142.
        self.assertEqual(state["glucose_avg_90d"], 142)

    def test_tir_averages_from_daily_summaries(self):
        from apps.health.models import DailyHealthSummary

        today = date.today()
        # Three days in last 7: TIR 90, 80, 70 → avg 80.
        for offset, tir in ((1, 90), (3, 80), (5, 70)):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=today - timedelta(days=offset),
                time_in_range_pct=Decimal(tir),
            )
        # Two older days in 30d window: 60, 60 → mixed avg.
        for offset, tir in ((15, 60), (20, 60)):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=today - timedelta(days=offset),
                time_in_range_pct=Decimal(tir),
            )
        state = build_health_state(self.user)
        # 7d average: (90+80+70)/3 = 80.0
        self.assertEqual(state["time_in_range_pct_7d"], 80.0)
        # 30d average: (90+80+70+60+60)/5 = 72.0
        self.assertEqual(state["time_in_range_pct_30d"], 72.0)

    def test_existing_glucose_keys_still_populated(self):
        """Existing glucose_avg_7d and latest_glucose must keep working."""
        from apps.health.models import GlucoseEntry

        now = datetime.now(timezone.utc)
        GlucoseEntry.objects.create(
            user=self.user,
            value=Decimal("128"),
            unit="mg/dL",
            recorded_at=now - timedelta(hours=1),
        )
        state = build_health_state(self.user)
        self.assertEqual(state["glucose_avg_7d"], 128)
        self.assertEqual(state["latest_glucose"], 128.0)
        self.assertEqual(state["latest_glucose_unit"], "mg/dL")


# ── Bible Journey shared-state guardrail ────────────────────────────


class FaithStateJourneyIntegrationPreservedTests(SimpleTestCase):
    """C5 must not regress Bible Journey's faith-state additions.

    These tests inspect the source of build_faith_state rather than
    executing it, so they pass without requiring the journey database
    schema. They prove the integration code is still wired up.
    """

    def test_build_faith_state_still_defined(self):
        self.assertTrue(callable(build_faith_state))

    def test_build_faith_state_imports_journey_state(self):
        source = inspect.getsource(build_faith_state)
        self.assertIn(
            "from apps.faith.journey.state import build_journey_state",
            source,
            "Bible Journey import was removed from build_faith_state — "
            "regression of parallel workstream",
        )

    def test_build_faith_state_assigns_journey_key(self):
        source = inspect.getsource(build_faith_state)
        self.assertIn(
            'state["journey"] = build_journey_state(user)',
            source,
            "Bible Journey state[\"journey\"] assignment was removed",
        )

    def test_build_faith_state_journey_is_import_error_safe(self):
        # The journey wrap is guarded by except ImportError so missing
        # journey app doesn't break faith state. Pin that guard exists.
        source = inspect.getsource(build_faith_state)
        self.assertIn("except ImportError", source)

    def test_state_builder_module_constants_unchanged(self):
        # Pin the module-level constants Bible Journey or other workstreams
        # may depend on. VALID_STATUS_VALUES is read by validators.
        self.assertEqual(
            state_builder.VALID_STATUS_VALUES,
            frozenset({"excellent", "good", "fair", "poor", "no_data"}),
        )
