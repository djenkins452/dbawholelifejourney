"""Tests for the Layer 4 interpreted-fact functions."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.core.health_briefing.interpreted_facts import (
    ALL_FACTS,
    FactVerdict,
    VERDICT_ADEQUATE,
    VERDICT_DECLINING,
    VERDICT_DECREASING,
    VERDICT_IMPROVING,
    VERDICT_INCREASING,
    VERDICT_INSUFFICIENT_DATA,
    VERDICT_LOOSE,
    VERDICT_POOR,
    VERDICT_STABLE,
    VERDICT_STRONG,
    VERDICT_TIGHT,
    VERDICT_UNCONTROLLED,
    adherence_state,
    compute_all_facts,
    exercise_response_state,
    glycemic_control_state,
    glycemic_trajectory,
    insulin_dependence_state,
    sleep_recovery_state,
    weight_trajectory_state,
)


# ── FactVerdict shape ────────────────────────────────────────────────


class FactVerdictTests(SimpleTestCase):
    def test_is_sufficient_true_for_real_verdict(self):
        v = FactVerdict(
            key="x", label="X", verdict=VERDICT_STABLE,
            confidence=0.5, contribution=0, why="ok",
        )
        self.assertTrue(v.is_sufficient)

    def test_is_sufficient_false_for_insufficient_data(self):
        v = FactVerdict(
            key="x", label="X", verdict=VERDICT_INSUFFICIENT_DATA,
            confidence=0.0, contribution=0, why="missing",
        )
        self.assertFalse(v.is_sufficient)


# ── glycemic_control_state ───────────────────────────────────────────


class GlycemicControlTests(SimpleTestCase):
    def test_insufficient_when_no_tir_or_avg(self):
        v = glycemic_control_state({})
        self.assertEqual(v.verdict, VERDICT_INSUFFICIENT_DATA)
        self.assertEqual(v.contribution, 0)
        self.assertEqual(v.confidence, 0.0)

    def test_tight_at_high_tir(self):
        v = glycemic_control_state({"time_in_range_pct_7d": 85})
        self.assertEqual(v.verdict, VERDICT_TIGHT)
        self.assertGreater(v.contribution, 0)

    def test_adequate_at_mid_tir(self):
        v = glycemic_control_state({"time_in_range_pct_7d": 72})
        self.assertEqual(v.verdict, VERDICT_ADEQUATE)
        self.assertGreater(v.contribution, 0)

    def test_loose_at_low_tir(self):
        v = glycemic_control_state({"time_in_range_pct_7d": 55})
        self.assertEqual(v.verdict, VERDICT_LOOSE)
        self.assertLess(v.contribution, 0)

    def test_uncontrolled_at_very_low_tir(self):
        v = glycemic_control_state({"time_in_range_pct_7d": 35})
        self.assertEqual(v.verdict, VERDICT_UNCONTROLLED)
        self.assertLess(v.contribution, 0)

    def test_high_variability_dampens_score(self):
        baseline = glycemic_control_state({"time_in_range_pct_7d": 85})
        variable = glycemic_control_state({
            "time_in_range_pct_7d": 85,
            "glucose_variability_level": "high",
        })
        self.assertEqual(variable.contribution, baseline.contribution - 5)

    def test_falls_back_to_avg_when_tir_missing(self):
        v = glycemic_control_state({"glucose_avg_7d": 135})
        self.assertEqual(v.verdict, VERDICT_ADEQUATE)

    def test_confidence_caps_at_single_source_cap(self):
        v = glycemic_control_state({
            "time_in_range_pct_7d": 85,
            "time_in_range_pct_30d": 82,
            "glucose_variability_level": "stable",
        })
        # Should not exceed the registry single-source cap.
        self.assertLessEqual(v.confidence, 0.75)


# ── glycemic_trajectory ──────────────────────────────────────────────


class GlycemicTrajectoryTests(SimpleTestCase):
    def test_insufficient_with_no_history(self):
        v = glycemic_trajectory({})
        self.assertEqual(v.verdict, VERDICT_INSUFFICIENT_DATA)

    def test_insufficient_with_only_one_window(self):
        v = glycemic_trajectory({"glucose_avg_7d": 120})
        self.assertEqual(v.verdict, VERDICT_INSUFFICIENT_DATA)

    def test_improving_when_7d_below_30d(self):
        v = glycemic_trajectory({
            "glucose_avg_7d": 120,
            "glucose_avg_30d": 140,
            "glucose_avg_90d": 145,
        })
        self.assertEqual(v.verdict, VERDICT_IMPROVING)
        self.assertGreater(v.contribution, 0)

    def test_declining_when_7d_above_30d(self):
        v = glycemic_trajectory({
            "glucose_avg_7d": 150,
            "glucose_avg_30d": 135,
            "glucose_avg_90d": 130,
        })
        self.assertEqual(v.verdict, VERDICT_DECLINING)
        self.assertLess(v.contribution, 0)

    def test_stable_when_changes_small(self):
        v = glycemic_trajectory({
            "glucose_avg_7d": 130,
            "glucose_avg_30d": 132,
            "glucose_avg_90d": 134,
        })
        self.assertEqual(v.verdict, VERDICT_STABLE)
        self.assertLess(abs(v.contribution), 8)

    def test_contribution_clipped_at_25(self):
        v = glycemic_trajectory({
            "glucose_avg_7d": 90,
            "glucose_avg_30d": 200,
            "glucose_avg_90d": 220,
        })
        self.assertEqual(v.contribution, 25)


# ── insulin_dependence_state ─────────────────────────────────────────


class InsulinDependenceTests(SimpleTestCase):
    def test_insufficient_when_no_insulin(self):
        v = insulin_dependence_state({})
        self.assertEqual(v.verdict, VERDICT_INSUFFICIENT_DATA)
        self.assertEqual(v.contribution, 0)
        self.assertIn("No insulin", v.why)

    def test_stable_when_only_one_window(self):
        v = insulin_dependence_state({"insulin_total_7d_units": 100})
        self.assertEqual(v.verdict, VERDICT_STABLE)
        self.assertEqual(v.contribution, 0)

    def test_decreasing_when_recent_lower_than_30d_avg(self):
        # 30d avg 18u/day. Recent 7d total 84u → recent daily 12u.
        # Delta = 6u/day = 33% decrease.
        v = insulin_dependence_state({
            "insulin_daily_avg_30d_units": 18.0,
            "insulin_total_7d_units": 84.0,
        })
        self.assertEqual(v.verdict, VERDICT_DECREASING)
        self.assertGreater(v.contribution, 0)

    def test_increasing_when_recent_higher_than_30d_avg(self):
        v = insulin_dependence_state({
            "insulin_daily_avg_30d_units": 10.0,
            "insulin_total_7d_units": 112.0,  # 16/day, 60% higher
        })
        self.assertEqual(v.verdict, VERDICT_INCREASING)
        self.assertLess(v.contribution, 0)

    def test_stable_when_change_small(self):
        v = insulin_dependence_state({
            "insulin_daily_avg_30d_units": 18.0,
            "insulin_total_7d_units": 125.0,  # ~17.86/day, ~1% change
        })
        self.assertEqual(v.verdict, VERDICT_STABLE)


# ── weight_trajectory_state ──────────────────────────────────────────


class WeightTrajectoryTests(SimpleTestCase):
    def test_insufficient_with_no_history(self):
        v = weight_trajectory_state({})
        self.assertEqual(v.verdict, VERDICT_INSUFFICIENT_DATA)

    def test_improving_when_change_negative(self):
        v = weight_trajectory_state({
            "weight_trend": "down",
            "weight_change_30d": -5.0,
        })
        self.assertEqual(v.verdict, VERDICT_IMPROVING)
        self.assertGreater(v.contribution, 0)

    def test_declining_when_change_positive(self):
        v = weight_trajectory_state({
            "weight_trend": "up",
            "weight_change_30d": 4.0,
        })
        self.assertEqual(v.verdict, VERDICT_DECLINING)
        self.assertLess(v.contribution, 0)

    def test_stable_when_change_small(self):
        v = weight_trajectory_state({
            "weight_trend": "stable",
            "weight_change_30d": -0.3,
        })
        self.assertEqual(v.verdict, VERDICT_STABLE)


# ── exercise_response_state ──────────────────────────────────────────


class ExerciseResponseTests(SimpleTestCase):
    def test_insufficient_with_no_data(self):
        v = exercise_response_state({})
        self.assertEqual(v.verdict, VERDICT_INSUFFICIENT_DATA)

    def test_strong_with_high_workouts(self):
        v = exercise_response_state({"workout_count_7d": 5, "steps_avg_7d": 10000})
        self.assertEqual(v.verdict, VERDICT_STRONG)
        self.assertGreater(v.contribution, 0)

    def test_poor_with_zero_workouts(self):
        v = exercise_response_state({"workout_count_7d": 0, "steps_avg_7d": 3000})
        self.assertEqual(v.verdict, VERDICT_POOR)
        self.assertLess(v.contribution, 0)


# ── sleep_recovery_state ─────────────────────────────────────────────


class SleepRecoveryTests(SimpleTestCase):
    def test_insufficient_with_no_data(self):
        v = sleep_recovery_state({})
        self.assertEqual(v.verdict, VERDICT_INSUFFICIENT_DATA)

    def test_strong_at_high_sleep(self):
        v = sleep_recovery_state({"sleep_avg_hours_7d": 8.0})
        self.assertEqual(v.verdict, VERDICT_STRONG)

    def test_adequate_at_mid_sleep(self):
        v = sleep_recovery_state({"sleep_avg_hours_7d": 7.0})
        self.assertEqual(v.verdict, VERDICT_ADEQUATE)

    def test_poor_at_low_sleep(self):
        v = sleep_recovery_state({"sleep_avg_hours_7d": 5.0})
        self.assertEqual(v.verdict, VERDICT_POOR)
        self.assertLess(v.contribution, 0)


# ── adherence_state ──────────────────────────────────────────────────


class AdherenceTests(SimpleTestCase):
    def test_insufficient_when_no_rate(self):
        v = adherence_state({})
        self.assertEqual(v.verdict, VERDICT_INSUFFICIENT_DATA)

    def test_strong_at_high_rate(self):
        v = adherence_state({"adherence_7d": 98})
        self.assertEqual(v.verdict, VERDICT_STRONG)
        self.assertGreater(v.contribution, 10)

    def test_poor_at_low_rate(self):
        v = adherence_state({"adherence_7d": 50})
        self.assertEqual(v.verdict, VERDICT_POOR)
        self.assertLess(v.contribution, 0)

    def test_reads_from_contract_summary_fallback(self):
        state = {"_contract": {"summary": {"adherence_7d": 92}}}
        v = adherence_state(state)
        self.assertEqual(v.verdict, VERDICT_ADEQUATE)


# ── Registry / compute_all_facts ────────────────────────────────────


class ComputeAllFactsTests(SimpleTestCase):
    def test_registry_includes_all_seven_facts(self):
        self.assertEqual(len(ALL_FACTS), 7)
        for key in (
            "glycemic_control", "glycemic_trajectory", "insulin_dependence",
            "weight_trajectory", "exercise_response", "sleep_recovery",
            "adherence",
        ):
            self.assertIn(key, ALL_FACTS)

    def test_returns_seven_verdicts_in_stable_order(self):
        verdicts = compute_all_facts({}, {})
        self.assertEqual(len(verdicts), 7)
        keys = [v.key for v in verdicts]
        self.assertEqual(keys, list(ALL_FACTS))

    def test_all_insufficient_when_no_data(self):
        verdicts = compute_all_facts({}, {})
        for v in verdicts:
            self.assertEqual(v.verdict, VERDICT_INSUFFICIENT_DATA)
            self.assertEqual(v.contribution, 0)

    def test_mixed_state_produces_mixed_verdicts(self):
        health = {
            "time_in_range_pct_7d": 85,
            "glucose_avg_7d": 120,
            "glucose_avg_30d": 140,
            "weight_trend": "down",
            "weight_change_30d": -3,
            "sleep_avg_hours_7d": 7.5,
            "workout_count_7d": 4,
        }
        medicine = {
            "insulin_total_7d_units": 84.0,
            "insulin_daily_avg_30d_units": 18.0,
            "adherence_7d": 95,
        }
        verdicts = compute_all_facts(health, medicine)
        verdict_map = {v.key: v for v in verdicts}
        self.assertEqual(verdict_map["glycemic_control"].verdict, VERDICT_TIGHT)
        self.assertEqual(verdict_map["glycemic_trajectory"].verdict, VERDICT_IMPROVING)
        self.assertEqual(verdict_map["insulin_dependence"].verdict, VERDICT_DECREASING)
        self.assertEqual(verdict_map["weight_trajectory"].verdict, VERDICT_IMPROVING)
        # Every verdict should have a positive contribution for this user.
        for v in verdicts:
            self.assertGreater(v.contribution, 0, f"{v.key}: {v.contribution}")
