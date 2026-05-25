"""Tests for the C10 ranking module."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.core.health_briefing.contract import (
    AcuteAlert,
    AcuteSeverity,
    OverallStatus,
    RiskLevel,
)
from apps.core.health_briefing.interpreted_facts import (
    VERDICT_ADEQUATE,
    VERDICT_DECREASING,
    VERDICT_IMPROVING,
    VERDICT_INSUFFICIENT_DATA,
    VERDICT_POOR,
    VERDICT_STABLE,
    VERDICT_STRONG,
    VERDICT_TIGHT,
    FactVerdict,
)
from apps.core.health_briefing.ranking import (
    HIGH_NET_RISK_MAX,
    IMPROVING_NET_MIN,
    MIXED_NET_MIN,
    MODERATE_NEGATIVE_FACT_MIN,
    STABLE_NET_MIN,
    THRIVING_NET_MIN,
    rank_facts,
)


def _fact(key, *, contribution, verdict=VERDICT_STABLE, confidence=0.7):
    return FactVerdict(
        key=key,
        label=key.replace("_", " ").title(),
        verdict=verdict,
        confidence=confidence,
        contribution=contribution,
        why=f"{key} reason",
    )


def _insufficient(key):
    return FactVerdict(
        key=key, label=key, verdict=VERDICT_INSUFFICIENT_DATA,
        confidence=0.0, contribution=0, why="missing",
    )


def _acute(key="glucose_critical_low", severity=AcuteSeverity.CRITICAL):
    return AcuteAlert(
        key=key, label="Critical low glucose",
        severity=severity, why="Reading 48 mg/dL", evidence_ref="",
    )


# ── Insufficient data path ──────────────────────────────────────────


class InsufficientDataTests(SimpleTestCase):
    def test_no_verdicts_and_no_acute_returns_insufficient(self):
        result = rank_facts([])
        self.assertEqual(result.overall_status, OverallStatus.INSUFFICIENT_DATA)
        self.assertEqual(result.overall_confidence, 0.0)
        self.assertEqual(result.risk_level, RiskLevel.NONE)
        self.assertTrue(result.insufficient_data_flag)
        self.assertEqual(result.top_positive_drivers, [])
        self.assertEqual(result.watch_items, [])

    def test_all_insufficient_verdicts_returns_insufficient(self):
        result = rank_facts(
            [_insufficient("glycemic_control"), _insufficient("weight_trajectory")]
        )
        self.assertEqual(result.overall_status, OverallStatus.INSUFFICIENT_DATA)
        self.assertTrue(result.insufficient_data_flag)


# ── Headline classification ─────────────────────────────────────────


class HeadlineClassificationTests(SimpleTestCase):
    def test_thriving_when_net_very_positive(self):
        verdicts = [
            _fact("glycemic_control", contribution=18, verdict=VERDICT_TIGHT),
            _fact("insulin_dependence", contribution=15, verdict=VERDICT_DECREASING),
            _fact("weight_trajectory", contribution=12, verdict=VERDICT_IMPROVING),
        ]
        result = rank_facts(verdicts)
        self.assertEqual(result.overall_status, OverallStatus.THRIVING)
        self.assertEqual(result.risk_level, RiskLevel.NONE)

    def test_improving_when_net_moderately_positive(self):
        verdicts = [
            _fact("glycemic_control", contribution=10, verdict=VERDICT_ADEQUATE),
            _fact("weight_trajectory", contribution=5, verdict=VERDICT_IMPROVING),
        ]
        result = rank_facts(verdicts)
        self.assertEqual(result.overall_status, OverallStatus.IMPROVING)

    def test_stable_when_net_near_zero_and_no_decline(self):
        verdicts = [
            _fact("glycemic_control", contribution=5, verdict=VERDICT_ADEQUATE),
            _fact("weight_trajectory", contribution=0, verdict=VERDICT_STABLE),
        ]
        result = rank_facts(verdicts)
        self.assertEqual(result.overall_status, OverallStatus.STABLE)

    def test_mixed_when_stable_but_with_decline(self):
        # Net within stable band but a negative fact exists → tilt MIXED.
        verdicts = [
            _fact("glycemic_control", contribution=10, verdict=VERDICT_ADEQUATE),
            _fact("weight_trajectory", contribution=-6, verdict=VERDICT_POOR),
        ]
        result = rank_facts(verdicts)
        self.assertEqual(result.overall_status, OverallStatus.MIXED)

    def test_mixed_when_net_modestly_negative(self):
        verdicts = [
            _fact("glycemic_control", contribution=-12, verdict=VERDICT_POOR),
            _fact("weight_trajectory", contribution=-8, verdict=VERDICT_POOR),
        ]
        result = rank_facts(verdicts)
        self.assertEqual(result.overall_status, OverallStatus.MIXED)

    def test_declining_when_net_very_negative(self):
        verdicts = [
            _fact("glycemic_control", contribution=-20, verdict=VERDICT_POOR),
            _fact("adherence", contribution=-18, verdict=VERDICT_POOR),
        ]
        result = rank_facts(verdicts)
        self.assertEqual(result.overall_status, OverallStatus.DECLINING)


# ── Acute alert behavior ────────────────────────────────────────────


class AcuteAlertBehaviorTests(SimpleTestCase):
    def test_acute_alert_overrides_thriving_headline(self):
        verdicts = [
            _fact("glycemic_control", contribution=20, verdict=VERDICT_TIGHT),
            _fact("weight_trajectory", contribution=15, verdict=VERDICT_IMPROVING),
        ]
        result = rank_facts(verdicts, acute_alerts=[_acute()])
        self.assertEqual(result.overall_status, OverallStatus.AT_RISK)
        self.assertEqual(result.risk_level, RiskLevel.ACUTE)
        self.assertEqual(len(result.acute_alerts), 1)

    def test_acute_alert_appears_in_why_before_facts(self):
        verdicts = [
            _fact("weight_trajectory", contribution=12, verdict=VERDICT_IMPROVING),
        ]
        result = rank_facts(verdicts, acute_alerts=[_acute()])
        self.assertTrue(result.why[0].startswith("ACUTE: "))


# ── Drivers and watch items ─────────────────────────────────────────


class DriversAndWatchItemsTests(SimpleTestCase):
    def test_top_positive_drivers_sorted_descending(self):
        verdicts = [
            _fact("a", contribution=5),
            _fact("b", contribution=18),
            _fact("c", contribution=10),
            _fact("d", contribution=3),
        ]
        result = rank_facts(verdicts)
        scores = [d.score for d in result.top_positive_drivers]
        self.assertEqual(scores, [18.0, 10.0, 5.0])  # max 3, descending

    def test_watch_items_sorted_by_severity(self):
        verdicts = [
            _fact("a", contribution=-3, verdict=VERDICT_POOR),
            _fact("b", contribution=-18, verdict=VERDICT_POOR),
            _fact("c", contribution=-10, verdict=VERDICT_POOR),
            _fact("d", contribution=-1, verdict=VERDICT_POOR),
        ]
        result = rank_facts(verdicts)
        scores = [d.score for d in result.watch_items]
        self.assertEqual(scores, [-18.0, -10.0, -3.0])  # max 3, most-negative first

    def test_neutral_facts_excluded_from_both_lists(self):
        verdicts = [
            _fact("a", contribution=0, verdict=VERDICT_STABLE),
            _fact("b", contribution=12, verdict=VERDICT_IMPROVING),
            _fact("c", contribution=-5, verdict=VERDICT_POOR),
        ]
        result = rank_facts(verdicts)
        self.assertEqual(len(result.top_positive_drivers), 1)
        self.assertEqual(len(result.watch_items), 1)


# ── Positive recognition ────────────────────────────────────────────


class PositiveRecognitionTests(SimpleTestCase):
    def test_required_when_improving_with_qualifying_positive(self):
        verdicts = [
            _fact("a", contribution=12, verdict=VERDICT_IMPROVING, confidence=0.8),
        ]
        result = rank_facts(verdicts)
        self.assertTrue(result.positive_recognition_required)

    def test_not_required_when_status_at_risk(self):
        verdicts = [
            _fact("a", contribution=15, verdict=VERDICT_IMPROVING, confidence=0.8),
        ]
        result = rank_facts(verdicts, acute_alerts=[_acute()])
        # At-risk skips positive recognition — acute coverage wins.
        self.assertFalse(result.positive_recognition_required)

    def test_not_required_when_positive_below_floor(self):
        verdicts = [
            _fact("a", contribution=10, verdict=VERDICT_IMPROVING, confidence=0.3),
        ]
        result = rank_facts(verdicts)
        # Net is improving, but the only positive driver is below
        # narration_floor (0.5). No recognition required.
        self.assertFalse(result.positive_recognition_required)

    def test_required_when_mixed_with_positive_above_floor(self):
        verdicts = [
            _fact("a", contribution=12, verdict=VERDICT_IMPROVING, confidence=0.8),
            _fact("b", contribution=-15, verdict=VERDICT_POOR, confidence=0.8),
        ]
        result = rank_facts(verdicts)
        # Net is at MIXED, but the positive driver is qualifying.
        # Composer must surface it alongside the watch item.
        self.assertEqual(result.overall_status, OverallStatus.MIXED)
        self.assertTrue(result.positive_recognition_required)


# ── Risk classification ─────────────────────────────────────────────


class RiskLevelTests(SimpleTestCase):
    def test_none_when_all_positive(self):
        verdicts = [
            _fact("a", contribution=12, verdict=VERDICT_IMPROVING),
            _fact("b", contribution=8, verdict=VERDICT_ADEQUATE),
        ]
        result = rank_facts(verdicts)
        self.assertEqual(result.risk_level, RiskLevel.NONE)

    def test_low_when_modest_negative(self):
        verdicts = [
            _fact("a", contribution=10, verdict=VERDICT_IMPROVING),
            _fact("b", contribution=-5, verdict=VERDICT_POOR),
        ]
        result = rank_facts(verdicts)
        self.assertEqual(result.risk_level, RiskLevel.LOW)

    def test_moderate_when_one_severe_negative_fact(self):
        verdicts = [
            _fact("a", contribution=10, verdict=VERDICT_IMPROVING),
            _fact("b", contribution=-15, verdict=VERDICT_POOR),
        ]
        result = rank_facts(verdicts)
        self.assertEqual(result.risk_level, RiskLevel.MODERATE)

    def test_high_when_net_very_negative(self):
        verdicts = [
            _fact("a", contribution=-20, verdict=VERDICT_POOR),
            _fact("b", contribution=-15, verdict=VERDICT_POOR),
        ]
        result = rank_facts(verdicts)
        self.assertEqual(result.risk_level, RiskLevel.HIGH)

    def test_acute_when_acute_alert_present(self):
        verdicts = [_fact("a", contribution=5, verdict=VERDICT_ADEQUATE)]
        result = rank_facts(verdicts, acute_alerts=[_acute()])
        self.assertEqual(result.risk_level, RiskLevel.ACUTE)


# ── Confidence weighting ────────────────────────────────────────────


class ConfidenceWeightingTests(SimpleTestCase):
    def test_high_contribution_facts_pull_confidence(self):
        # A high-confidence (+20) fact and a low-confidence neutral
        # fact should produce a confidence weighted toward the strong fact.
        verdicts = [
            _fact("a", contribution=20, confidence=0.9, verdict=VERDICT_IMPROVING),
            _fact("b", contribution=0, confidence=0.2, verdict=VERDICT_STABLE),
        ]
        result = rank_facts(verdicts)
        # Weighted: (0.9 * 21 + 0.2 * 1) / 22 ≈ 0.86
        self.assertGreater(result.overall_confidence, 0.8)

    def test_zero_when_no_sufficient_verdicts(self):
        result = rank_facts([_insufficient("x")])
        self.assertEqual(result.overall_confidence, 0.0)


# ── Why bullets ─────────────────────────────────────────────────────


class WhyBulletTests(SimpleTestCase):
    def test_why_capped_at_max(self):
        verdicts = [
            _fact(f"f{i}", contribution=10 + i, verdict=VERDICT_IMPROVING)
            for i in range(10)
        ]
        result = rank_facts(verdicts)
        self.assertLessEqual(len(result.why), 5)

    def test_why_ordered_by_absolute_contribution(self):
        verdicts = [
            _fact("a", contribution=5),
            _fact("b", contribution=-18, verdict=VERDICT_POOR),
            _fact("c", contribution=12, verdict=VERDICT_IMPROVING),
        ]
        result = rank_facts(verdicts)
        # Largest |contribution| first.
        self.assertIn("(-18)", result.why[0])
        self.assertIn("(+12)", result.why[1])
        self.assertIn("(+5)", result.why[2])


# ── Determinism ─────────────────────────────────────────────────────


class DeterminismTests(SimpleTestCase):
    def test_same_inputs_produce_same_result(self):
        verdicts = [
            _fact("glycemic_control", contribution=15, verdict=VERDICT_TIGHT),
            _fact("weight_trajectory", contribution=8, verdict=VERDICT_IMPROVING),
            _fact("adherence", contribution=-10, verdict=VERDICT_POOR),
        ]
        a = rank_facts(verdicts)
        b = rank_facts(verdicts)
        self.assertEqual(a.overall_status, b.overall_status)
        self.assertEqual(a.overall_confidence, b.overall_confidence)
        self.assertEqual(a.risk_level, b.risk_level)
        self.assertEqual(
            [d.key for d in a.top_positive_drivers],
            [d.key for d in b.top_positive_drivers],
        )
        self.assertEqual(a.why, b.why)

    def test_input_order_does_not_affect_output(self):
        verdicts_a = [
            _fact("z", contribution=10),
            _fact("a", contribution=10),
        ]
        verdicts_b = [
            _fact("a", contribution=10),
            _fact("z", contribution=10),
        ]
        a = rank_facts(verdicts_a)
        b = rank_facts(verdicts_b)
        self.assertEqual(
            [d.key for d in a.top_positive_drivers],
            [d.key for d in b.top_positive_drivers],
        )
