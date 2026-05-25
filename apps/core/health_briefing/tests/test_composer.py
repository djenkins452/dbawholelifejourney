"""Tests for the C11 composer + explain mode."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.health_briefing.composer import (
    _build_acute_alerts,
    _build_evidence,
    _build_headline,
    _glucose_trends,
    _hash_evidence,
    _insulin_trend_30d,
    _serialize_briefing,
    _trend_from_pair,
    _weight_trend_30d,
    compose_briefing,
)
from apps.core.health_briefing.contract import (
    AcuteSeverity,
    OverallStatus,
    RiskLevel,
    TrendDirection,
)
from apps.core.health_briefing.explain import explain_briefing
from apps.core.health_briefing.models import HealthBriefingSnapshot
from apps.core.health_briefing.ranking import RankingResult
from apps.core.health_briefing.thresholds import get_profile
from apps.users.models import TermsAcceptance

User = get_user_model()


def _make_user(email: str = "composer@test.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ── Pure helper tests (no DB) ───────────────────────────────────────


from django.test import SimpleTestCase  # noqa: E402


class TrendFromPairTests(SimpleTestCase):
    def test_insufficient_when_either_value_none(self):
        t = _trend_from_pair(None, 120, window_days=7)
        self.assertEqual(t.direction, TrendDirection.INSUFFICIENT_DATA)
        self.assertEqual(t.confidence, 0.0)

    def test_flat_when_change_within_threshold(self):
        t = _trend_from_pair(122, 120, window_days=7)  # ~1.6% change
        self.assertEqual(t.direction, TrendDirection.FLAT)

    def test_down_when_recent_lower(self):
        t = _trend_from_pair(120, 140, window_days=7)
        self.assertEqual(t.direction, TrendDirection.DOWN)
        self.assertGreater(t.magnitude, 0)

    def test_up_when_recent_higher(self):
        t = _trend_from_pair(140, 120, window_days=7)
        self.assertEqual(t.direction, TrendDirection.UP)


class GlucoseTrendsTests(SimpleTestCase):
    def test_all_insufficient_when_no_averages(self):
        t7, t30, t90 = _glucose_trends({})
        for t in (t7, t30, t90):
            self.assertEqual(t.direction, TrendDirection.INSUFFICIENT_DATA)

    def test_partial_horizons_yield_partial_trends(self):
        state = {"glucose_avg_7d": 120, "glucose_avg_30d": 140}
        t7, t30, t90 = _glucose_trends(state)
        self.assertEqual(t7.direction, TrendDirection.DOWN)
        # 30d trend needs 30d + 90d.
        self.assertEqual(t30.direction, TrendDirection.INSUFFICIENT_DATA)
        # 90d has no comparison reference in v1.
        self.assertEqual(t90.direction, TrendDirection.INSUFFICIENT_DATA)


class WeightTrendTests(SimpleTestCase):
    def test_down_for_negative_change(self):
        t = _weight_trend_30d({"weight_current": 200, "weight_change_30d": -5})
        self.assertEqual(t.direction, TrendDirection.DOWN)

    def test_flat_for_tiny_change(self):
        t = _weight_trend_30d({"weight_current": 200, "weight_change_30d": -0.5})
        self.assertEqual(t.direction, TrendDirection.FLAT)


class InsulinTrendTests(SimpleTestCase):
    def test_none_when_insulin_observation_absent(self):
        t = _insulin_trend_30d({})
        self.assertIsNone(t)

    def test_down_when_recent_lower_than_30d(self):
        # 30d avg 18u/day; recent 7d total 84u → recent daily 12u.
        t = _insulin_trend_30d({
            "insulin_daily_avg_30d_units": 18.0,
            "insulin_total_7d_units": 84.0,
        })
        self.assertIsNotNone(t)
        self.assertEqual(t.direction, TrendDirection.DOWN)


class AcuteAlertBuilderTests(SimpleTestCase):
    def setUp(self):
        self.profile = get_profile()

    def test_no_alert_when_no_latest_glucose(self):
        self.assertEqual(_build_acute_alerts({}, self.profile), [])

    def test_critical_low_alert(self):
        alerts = _build_acute_alerts(
            {"latest_glucose": 45, "latest_glucose_unit": "mg/dL"},
            self.profile,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].key, "glucose_critical_low")
        self.assertEqual(alerts[0].severity, AcuteSeverity.CRITICAL)

    def test_critical_high_alert(self):
        alerts = _build_acute_alerts(
            {"latest_glucose": 310, "latest_glucose_unit": "mg/dL"},
            self.profile,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].key, "glucose_critical_high")

    def test_mmol_l_conversion_in_acute_check(self):
        # 2.7 mmol/L * 18 = 48.6 mg/dL → critical_low.
        alerts = _build_acute_alerts(
            {"latest_glucose": 2.7, "latest_glucose_unit": "mmol/L"},
            self.profile,
        )
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].key, "glucose_critical_low")

    def test_no_alert_for_normal_value(self):
        alerts = _build_acute_alerts(
            {"latest_glucose": 130, "latest_glucose_unit": "mg/dL"},
            self.profile,
        )
        self.assertEqual(alerts, [])


class EvidenceHashTests(SimpleTestCase):
    def test_deterministic(self):
        a = _hash_evidence({"x": 1, "y": "abc"})
        b = _hash_evidence({"y": "abc", "x": 1})  # different insertion order
        self.assertEqual(a, b)

    def test_changes_with_input(self):
        a = _hash_evidence({"x": 1})
        b = _hash_evidence({"x": 2})
        self.assertNotEqual(a, b)


class HeadlineTests(SimpleTestCase):
    def test_every_status_has_a_template(self):
        for status in OverallStatus:
            r = RankingResult(
                overall_status=status,
                overall_confidence=0.5,
                risk_level=RiskLevel.NONE,
            )
            headline = _build_headline(r, inputs_used_count=10)
            self.assertIsInstance(headline, str)
            self.assertGreater(len(headline), 0)


# ── End-to-end composer tests (require DB) ─────────────────────────


class ComposerIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("integration_composer@test.com")
        cls.now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)

    def _state_patch(self, health=None, medicine=None, medical=None):
        """Return a context manager that stubs get_module_state."""
        def fake_get_state(_user, module):
            return {
                "health": health or {},
                "medicine": medicine or {},
                "medical": medical or {},
            }.get(module, {})
        return patch(
            "apps.core.health_briefing.composer.get_module_state",
            side_effect=fake_get_state,
        )

    def test_empty_state_produces_insufficient_data_briefing(self):
        with self._state_patch():
            briefing = compose_briefing(self.user, now=self.now, persist=False)
        self.assertEqual(briefing.overall_status, OverallStatus.INSUFFICIENT_DATA)
        self.assertTrue(briefing.insufficient_data_flag)
        self.assertEqual(briefing.acute_alerts, [])
        self.assertEqual(briefing.top_positive_drivers, [])

    def test_thriving_state_produces_thriving_briefing(self):
        health = {
            "time_in_range_pct_7d": 85,
            "time_in_range_pct_30d": 82,
            "glucose_avg_7d": 120,
            "glucose_avg_30d": 140,
            "glucose_avg_90d": 145,
            "glucose_variability_level": "stable",
            "weight_current": 200,
            "weight_change_30d": -3,
            "weight_trend": "down",
            "sleep_avg_hours_7d": 7.6,
            "workout_count_7d": 4,
            "steps_avg_7d": 9000,
        }
        medicine = {
            "insulin_total_7d_units": 84.0,
            "insulin_daily_avg_30d_units": 18.0,
            "adherence_7d": 96,
        }
        with self._state_patch(health=health, medicine=medicine):
            briefing = compose_briefing(self.user, now=self.now, persist=False)
        self.assertIn(briefing.overall_status, (
            OverallStatus.THRIVING, OverallStatus.IMPROVING,
        ))
        self.assertGreater(briefing.overall_confidence, 0.5)
        self.assertGreaterEqual(len(briefing.top_positive_drivers), 2)
        self.assertTrue(briefing.positive_recognition_required)

    def test_acute_low_glucose_overrides_thriving_state(self):
        # All other facts look great; latest reading is critical low.
        health = {
            "latest_glucose": 45,
            "latest_glucose_unit": "mg/dL",
            "time_in_range_pct_7d": 85,
            "glucose_avg_7d": 120,
            "glucose_avg_30d": 140,
            "weight_current": 200,
            "weight_change_30d": -3,
        }
        with self._state_patch(health=health):
            briefing = compose_briefing(self.user, now=self.now, persist=False)
        self.assertEqual(briefing.overall_status, OverallStatus.AT_RISK)
        self.assertEqual(briefing.risk_level, RiskLevel.ACUTE)
        self.assertEqual(len(briefing.acute_alerts), 1)
        # Positive recognition explicitly suppressed when AT_RISK.
        self.assertFalse(briefing.positive_recognition_required)

    def test_briefing_id_changes_when_evidence_changes(self):
        # Same user, same now → same briefing_id only if evidence is identical.
        with self._state_patch(health={"glucose_avg_7d": 120}):
            b1 = compose_briefing(self.user, now=self.now, persist=False)
        with self._state_patch(health={"glucose_avg_7d": 130}):
            b2 = compose_briefing(self.user, now=self.now, persist=False)
        self.assertNotEqual(b1.briefing_id, b2.briefing_id)

    def test_persist_writes_snapshot_row(self):
        HealthBriefingSnapshot.objects.filter(user=self.user).delete()
        with self._state_patch(health={"glucose_avg_7d": 130}):
            briefing = compose_briefing(self.user, now=self.now, persist=True)
        self.assertTrue(
            HealthBriefingSnapshot.objects.filter(
                user=self.user, briefing_id=briefing.briefing_id,
            ).exists()
        )

    def test_no_persist_leaves_no_row(self):
        HealthBriefingSnapshot.objects.filter(user=self.user).delete()
        with self._state_patch(health={"glucose_avg_7d": 130}):
            compose_briefing(self.user, now=self.now, persist=False)
        self.assertEqual(
            HealthBriefingSnapshot.objects.filter(user=self.user).count(), 0,
        )


# ── Audit: no raw rows leak into briefing payload ──────────────────


class NoRawRowsAuditTests(TestCase):
    """Critical Phase 0 audit: Beth must never see raw GlucoseEntry /
    LabResult / IntakeLog rows. The briefing carries values, not row
    pointers. This test pins that contract."""

    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("audit@test.com")

    def test_briefing_payload_has_no_orm_objects(self):
        from apps.core.health_briefing.composer import compose_briefing

        with patch(
            "apps.core.health_briefing.composer.get_module_state",
            return_value={
                "glucose_avg_7d": 130, "glucose_avg_30d": 140,
                "latest_glucose": 132, "latest_glucose_unit": "mg/dL",
            },
        ):
            briefing = compose_briefing(self.user, persist=False)
        payload = _serialize_briefing(briefing)

        # The serialized payload must be plain JSON-compatible types.
        import json
        rendered = json.dumps(payload, default=str)
        # If a Django Model leaked in, json.dumps(default=str) would
        # stringify the repr, which contains "<...Model object" — pin
        # that no such string appears.
        self.assertNotIn("Model object", rendered)
        self.assertNotIn("<QuerySet", rendered)


# ── Explain mode ────────────────────────────────────────────────────


class ExplainModeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = _make_user("explain@test.com")
        cls.now = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)

    def test_explain_for_insufficient_state(self):
        with patch(
            "apps.core.health_briefing.composer.get_module_state",
            return_value={},
        ):
            briefing = compose_briefing(self.user, now=self.now, persist=False)
        out = explain_briefing(briefing)
        self.assertIn("HealthBriefing user=", out)
        self.assertIn("insufficient_data", out)
        self.assertIn("Drivers (positive):", out)
        self.assertIn("(none)", out)

    def test_explain_includes_driver_lines(self):
        health = {
            "time_in_range_pct_7d": 85,
            "glucose_avg_7d": 120, "glucose_avg_30d": 140,
            "weight_current": 200, "weight_change_30d": -3,
            "weight_trend": "down",
        }
        with patch(
            "apps.core.health_briefing.composer.get_module_state",
            return_value=health,
        ):
            briefing = compose_briefing(self.user, now=self.now, persist=False)
        out = explain_briefing(briefing)
        # Each driver line starts with "  + " and has a (+N) score
        # token — pins the user's requested explanation format.
        self.assertIn("  + ", out)
        self.assertRegex(out, r"\(\+\d+\)")

    def test_explain_includes_acute_alert_when_present(self):
        with patch(
            "apps.core.health_briefing.composer.get_module_state",
            return_value={
                "latest_glucose": 45, "latest_glucose_unit": "mg/dL",
            },
        ):
            briefing = compose_briefing(self.user, now=self.now, persist=False)
        out = explain_briefing(briefing)
        self.assertIn("Acute alerts:", out)
        self.assertIn("[critical]", out)

    def test_explain_is_deterministic(self):
        health = {
            "time_in_range_pct_7d": 80,
            "glucose_avg_7d": 125, "glucose_avg_30d": 138,
        }
        with patch(
            "apps.core.health_briefing.composer.get_module_state",
            return_value=health,
        ):
            briefing = compose_briefing(self.user, now=self.now, persist=False)
        a = explain_briefing(briefing)
        b = explain_briefing(briefing)
        self.assertEqual(a, b)
