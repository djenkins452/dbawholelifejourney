"""Tests for the HealthBriefing v1 contract."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

from django.test import SimpleTestCase

from apps.core.health_briefing.contract import (
    COMPOSER_VERSION,
    DEFAULT_TTL_SECONDS,
    MAX_DRIVERS,
    MAX_WATCH_ITEMS,
    MAX_WHY_BULLETS,
    SCHEMA_VERSION,
    AcuteAlert,
    AcuteSeverity,
    ComposedOver,
    Driver,
    HealthBriefing,
    OverallStatus,
    RiskLevel,
    Trend,
    TrendDirection,
    compute_briefing_id,
)


def _ts(year: int = 2026, month: int = 5, day: int = 24, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)


def _trend(
    direction: TrendDirection = TrendDirection.FLAT,
    magnitude: int = 0,
    confidence: float = 0.5,
    window_days: int = 7,
) -> Trend:
    return Trend(
        direction=direction,
        magnitude=magnitude,
        confidence=confidence,
        window_days=window_days,
    )


def _minimal_briefing(**overrides) -> HealthBriefing:
    defaults = dict(
        briefing_id="abc123",
        user_id=1,
        generated_at_utc=_ts(),
        composer_version=COMPOSER_VERSION,
        composed_over=ComposedOver(start_utc=_ts(day=20), end_utc=_ts(day=24)),
        ttl_seconds=DEFAULT_TTL_SECONDS,
        overall_status=OverallStatus.STABLE,
        overall_confidence=0.7,
        risk_level=RiskLevel.NONE,
        headline_summary="Metabolic profile stable over the last month.",
        glucose_trend_7d=_trend(window_days=7),
        glucose_trend_30d=_trend(window_days=30),
        glucose_trend_90d=_trend(window_days=90),
        weight_trend_30d=_trend(window_days=30),
        insulin_trend_30d=None,
    )
    defaults.update(overrides)
    return HealthBriefing(**defaults)


class VersionConstantsTests(SimpleTestCase):
    def test_schema_version_is_one(self):
        self.assertEqual(SCHEMA_VERSION, 1)

    def test_composer_version_is_semver_string(self):
        self.assertIsInstance(COMPOSER_VERSION, str)
        self.assertEqual(COMPOSER_VERSION.count("."), 2)

    def test_default_ttl_matches_locked_default(self):
        self.assertEqual(DEFAULT_TTL_SECONDS, 1800)

    def test_caps_are_locked(self):
        self.assertEqual(MAX_DRIVERS, 3)
        self.assertEqual(MAX_WATCH_ITEMS, 3)
        self.assertEqual(MAX_WHY_BULLETS, 5)


class EnumTests(SimpleTestCase):
    def test_overall_status_values(self):
        values = {s.value for s in OverallStatus}
        self.assertEqual(
            values,
            {
                "thriving",
                "improving",
                "stable",
                "mixed",
                "declining",
                "at_risk",
                "insufficient_data",
            },
        )

    def test_risk_level_values(self):
        values = {r.value for r in RiskLevel}
        self.assertEqual(values, {"none", "low", "moderate", "high", "acute"})

    def test_trend_direction_values(self):
        values = {d.value for d in TrendDirection}
        self.assertEqual(values, {"up", "down", "flat", "insufficient_data"})

    def test_acute_severity_values(self):
        values = {s.value for s in AcuteSeverity}
        self.assertEqual(values, {"high", "critical"})

    def test_enums_serialize_as_strings(self):
        self.assertEqual(OverallStatus.IMPROVING, "improving")
        self.assertEqual(RiskLevel.ACUTE, "acute")


class TrendValidationTests(SimpleTestCase):
    def test_valid_trend_constructs(self):
        t = _trend(direction=TrendDirection.UP, magnitude=42, confidence=0.8)
        self.assertEqual(t.direction, TrendDirection.UP)
        self.assertEqual(t.magnitude, 42)

    def test_magnitude_below_zero_rejected(self):
        with self.assertRaises(ValueError):
            _trend(magnitude=-1)

    def test_magnitude_above_hundred_rejected(self):
        with self.assertRaises(ValueError):
            _trend(magnitude=101)

    def test_confidence_below_zero_rejected(self):
        with self.assertRaises(ValueError):
            _trend(confidence=-0.1)

    def test_confidence_above_one_rejected(self):
        with self.assertRaises(ValueError):
            _trend(confidence=1.01)

    def test_window_days_must_be_positive(self):
        with self.assertRaises(ValueError):
            _trend(window_days=0)


class HealthBriefingValidationTests(SimpleTestCase):
    def test_minimal_briefing_constructs(self):
        b = _minimal_briefing()
        self.assertEqual(b.overall_status, OverallStatus.STABLE)
        self.assertEqual(b.acute_alerts, [])
        self.assertEqual(b.top_positive_drivers, [])
        self.assertIsNone(b.insulin_trend_30d)

    def test_briefing_is_frozen(self):
        b = _minimal_briefing()
        with self.assertRaises(FrozenInstanceError):
            b.overall_status = OverallStatus.DECLINING  # type: ignore[misc]

    def test_overall_confidence_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            _minimal_briefing(overall_confidence=1.5)

    def test_ttl_must_be_positive(self):
        with self.assertRaises(ValueError):
            _minimal_briefing(ttl_seconds=0)

    def test_too_many_drivers_rejected(self):
        drivers = [
            Driver(key=f"k{i}", label=f"L{i}", score=1.0, why="w") for i in range(4)
        ]
        with self.assertRaises(ValueError):
            _minimal_briefing(top_positive_drivers=drivers)

    def test_too_many_watch_items_rejected(self):
        items = [
            Driver(key=f"k{i}", label=f"L{i}", score=1.0, why="w") for i in range(4)
        ]
        with self.assertRaises(ValueError):
            _minimal_briefing(watch_items=items)

    def test_too_many_why_bullets_rejected(self):
        with self.assertRaises(ValueError):
            _minimal_briefing(why=[f"reason {i}" for i in range(6)])

    def test_insufficient_data_flag_requires_matching_status(self):
        with self.assertRaises(ValueError):
            _minimal_briefing(insufficient_data_flag=True)

    def test_insufficient_data_flag_consistent_with_status(self):
        b = _minimal_briefing(
            insufficient_data_flag=True,
            overall_status=OverallStatus.INSUFFICIENT_DATA,
        )
        self.assertTrue(b.insufficient_data_flag)

    def test_acute_alert_evidence_ref_must_resolve(self):
        alert = AcuteAlert(
            key="glucose_critical_low",
            label="Critical low glucose",
            severity=AcuteSeverity.CRITICAL,
            why="Reading 48 mg/dL at 14:02",
            evidence_ref="latest_glucose",
        )
        with self.assertRaises(ValueError):
            _minimal_briefing(acute_alerts=[alert])

    def test_acute_alert_with_resolved_evidence_ref_ok(self):
        alert = AcuteAlert(
            key="glucose_critical_low",
            label="Critical low glucose",
            severity=AcuteSeverity.CRITICAL,
            why="Reading 48 mg/dL at 14:02",
            evidence_ref="latest_glucose",
        )
        b = _minimal_briefing(
            acute_alerts=[alert],
            inputs_used={"latest_glucose": 48},
        )
        self.assertEqual(len(b.acute_alerts), 1)

    def test_acute_alert_with_empty_evidence_ref_skips_check(self):
        alert = AcuteAlert(
            key="general",
            label="General",
            severity=AcuteSeverity.HIGH,
            why="Generalized concern",
            evidence_ref="",
        )
        b = _minimal_briefing(acute_alerts=[alert])
        self.assertEqual(len(b.acute_alerts), 1)


class BriefingIdTests(SimpleTestCase):
    def test_id_is_sha256_hex(self):
        bid = compute_briefing_id(1, _ts(), COMPOSER_VERSION, "h")
        self.assertEqual(len(bid), 64)
        int(bid, 16)  # hex parseable

    def test_id_deterministic_for_same_inputs(self):
        a = compute_briefing_id(1, _ts(), COMPOSER_VERSION, "h")
        b = compute_briefing_id(1, _ts(), COMPOSER_VERSION, "h")
        self.assertEqual(a, b)

    def test_id_changes_with_user(self):
        a = compute_briefing_id(1, _ts(), COMPOSER_VERSION, "h")
        b = compute_briefing_id(2, _ts(), COMPOSER_VERSION, "h")
        self.assertNotEqual(a, b)

    def test_id_changes_with_timestamp(self):
        a = compute_briefing_id(1, _ts(hour=12), COMPOSER_VERSION, "h")
        b = compute_briefing_id(1, _ts(hour=13), COMPOSER_VERSION, "h")
        self.assertNotEqual(a, b)

    def test_id_changes_with_composer_version(self):
        a = compute_briefing_id(1, _ts(), "1.0.0", "h")
        b = compute_briefing_id(1, _ts(), "1.0.1", "h")
        self.assertNotEqual(a, b)

    def test_id_changes_with_evidence_hash(self):
        a = compute_briefing_id(1, _ts(), COMPOSER_VERSION, "h1")
        b = compute_briefing_id(1, _ts(), COMPOSER_VERSION, "h2")
        self.assertNotEqual(a, b)
