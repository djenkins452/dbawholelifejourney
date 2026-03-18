"""
Tests for the deterministic health coaching layer with severity scoring.

The coaching engine is a pure function inside HealthTrendAnalyzer._build_coaching.
It scores every health domain (0-100), selects the highest-severity constraint,
and produces parameterized actions using actual values. No LLM calls. No DB writes.

Covers:
1. Per-domain severity scoring correctness
2. Severity-based constraint selection (highest wins)
3. Reinforcement mode when all scores below threshold
4. Parameterized actions with real values
5. Debug structure
6. Edge cases (ties, missing data)
7. Integration: coaching flows through to CoS context
"""
from django.test import TestCase

from apps.health.services.trend_analyzer import HealthTrendAnalyzer


# ── Severity Scoring Correctness ────────────────────────────────────


class TestSleepScoring(TestCase):
    """Sleep severity scoring based on rolling_7d.sleep_hours."""

    def test_severe_deficit(self):
        sev, reason, params = HealthTrendAnalyzer._score_sleep(
            {"sleep_hours": 5.2}, [],
        )
        self.assertGreaterEqual(sev, 80)
        self.assertIn("5.2", reason)
        self.assertGreater(params["gap_min"], 0)

    def test_moderate_deficit(self):
        sev, reason, params = HealthTrendAnalyzer._score_sleep(
            {"sleep_hours": 6.3}, [],
        )
        self.assertGreaterEqual(sev, 40)
        self.assertLess(sev, 80)

    def test_adequate_sleep(self):
        sev, _, _ = HealthTrendAnalyzer._score_sleep(
            {"sleep_hours": 7.5}, [],
        )
        self.assertEqual(sev, 0)

    def test_no_sleep_data(self):
        sev, _, _ = HealthTrendAnalyzer._score_sleep({}, [])
        self.assertEqual(sev, 0)

    def test_gap_minutes_calculated(self):
        _, _, params = HealthTrendAnalyzer._score_sleep(
            {"sleep_hours": 6.0}, [],
        )
        self.assertEqual(params["gap_min"], 60)


class TestProteinScoring(TestCase):
    """Protein severity scoring based on rolling_7d protein ratio."""

    def test_critically_low_protein(self):
        sev, reason, params = HealthTrendAnalyzer._score_protein(
            {"protein_ratio": 0.4, "protein_target_g": 180, "protein_consumed_g": 72},
            [],
        )
        self.assertGreaterEqual(sev, 70)
        self.assertGreater(params["gap_g"], 0)

    def test_moderate_protein_gap(self):
        sev, _, params = HealthTrendAnalyzer._score_protein(
            {"protein_ratio": 0.65, "protein_target_g": 180, "protein_consumed_g": 117},
            [],
        )
        self.assertGreaterEqual(sev, 30)
        self.assertLess(sev, 75)

    def test_adequate_protein(self):
        sev, _, _ = HealthTrendAnalyzer._score_protein(
            {"protein_ratio": 0.92, "protein_target_g": 180, "protein_consumed_g": 166},
            [],
        )
        self.assertEqual(sev, 0)


class TestActivityScoring(TestCase):
    """Activity severity scoring based on rolling_7d.steps."""

    def test_very_low_steps(self):
        sev, reason, params = HealthTrendAnalyzer._score_activity(
            {"steps": 2500}, [],
        )
        self.assertGreaterEqual(sev, 60)
        self.assertGreater(params["step_gap"], 0)

    def test_low_steps(self):
        sev, _, _ = HealthTrendAnalyzer._score_activity(
            {"steps": 4000}, [],
        )
        self.assertGreaterEqual(sev, 40)

    def test_adequate_steps(self):
        sev, _, _ = HealthTrendAnalyzer._score_activity(
            {"steps": 9000}, [],
        )
        self.assertEqual(sev, 0)


class TestGlucoseScoring(TestCase):
    """Glucose severity scoring."""

    def test_elevated_glucose(self):
        sev, _, _ = HealthTrendAnalyzer._score_glucose(
            {"glucose_avg": 150}, [],
        )
        self.assertGreaterEqual(sev, 70)

    def test_above_optimal(self):
        sev, _, _ = HealthTrendAnalyzer._score_glucose(
            {"glucose_avg": 125},
            [{"domain": "glucose", "severity": "warning", "message": "rising"}],
        )
        self.assertGreaterEqual(sev, 40)

    def test_normal_glucose(self):
        sev, _, _ = HealthTrendAnalyzer._score_glucose(
            {"glucose_avg": 95}, [],
        )
        self.assertEqual(sev, 0)


class TestWorkoutScoring(TestCase):
    """Workout severity scoring."""

    def test_no_workouts(self):
        sev, _, _ = HealthTrendAnalyzer._score_workout(
            {"workout_days": 0, "total_days": 7}, [],
        )
        self.assertGreaterEqual(sev, 60)

    def test_low_workouts(self):
        sev, _, _ = HealthTrendAnalyzer._score_workout(
            {"workout_days": 1, "total_days": 7}, [],
        )
        self.assertGreaterEqual(sev, 30)

    def test_adequate_workouts(self):
        sev, _, _ = HealthTrendAnalyzer._score_workout(
            {"workout_days": 4, "total_days": 7}, [],
        )
        self.assertEqual(sev, 0)


class TestNutritionScoring(TestCase):
    """Nutrition tracking severity scoring."""

    def test_very_low_tracking(self):
        sev, _, _ = HealthTrendAnalyzer._score_nutrition(
            {"nutrition_logged_days": 1, "total_days": 7}, [],
        )
        self.assertGreaterEqual(sev, 40)

    def test_adequate_tracking(self):
        sev, _, _ = HealthTrendAnalyzer._score_nutrition(
            {"nutrition_logged_days": 6, "total_days": 7}, [],
        )
        self.assertEqual(sev, 0)


class TestMedicationScoring(TestCase):
    """Medication severity scoring (flag-based)."""

    def test_medication_warning_scores_high(self):
        sev, _, _ = HealthTrendAnalyzer._score_medication(
            {},
            [{"domain": "medication", "severity": "warning", "message": "Low adherence 60%"}],
        )
        self.assertGreaterEqual(sev, 60)

    def test_no_medication_flag(self):
        sev, _, _ = HealthTrendAnalyzer._score_medication({}, [])
        self.assertEqual(sev, 0)


# ── Constraint Selection (Severity-Based) ───────────────────────────


class TestSeverityBasedSelection(TestCase):
    """Highest severity wins, regardless of domain order."""

    def test_sleep_deficit_beats_low_steps_by_severity(self):
        """Sleep at 5.5h (severity ~90) beats steps at 4000 (severity ~50)."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={"sleep_hours": 5.5, "steps": 4000},
        )
        self.assertEqual(coaching["primary_constraint"], "sleep")

    def test_worse_protein_beats_mild_sleep(self):
        """Protein at 40% (severity ~75) beats sleep at 6.8h (severity ~40)."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={
                "sleep_hours": 6.8,
                "protein_ratio": 0.4,
                "protein_target_g": 180,
                "protein_consumed_g": 72,
            },
        )
        self.assertEqual(coaching["primary_constraint"], "protein")

    def test_glucose_beats_sleep_when_more_severe(self):
        """Glucose at 150 (severity ~80) beats sleep at 6.5h (severity ~60)."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={"sleep_hours": 6.5, "glucose_avg": 150},
        )
        self.assertEqual(coaching["primary_constraint"], "glucose")

    def test_medication_warning_beats_moderate_sleep(self):
        """Medication warning (severity 70) beats mild sleep deficit (severity 40)."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[
                {"domain": "medication", "severity": "warning", "message": "Low adherence"},
            ],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={"sleep_hours": 6.8},
        )
        self.assertEqual(coaching["primary_constraint"], "medication")


class TestReinforcementMode(TestCase):
    """When all severities < 25, coaching enters reinforcement mode."""

    def test_all_good_reinforcement(self):
        """Good sleep, good steps, no flags → reinforcement."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=["Healthy weight loss pace (1.2 lbs/week)"],
            trends={},
            rolling_7d={"sleep_hours": 7.5, "steps": 10000},
        )
        self.assertIsNone(coaching["primary_constraint"])
        self.assertIsNone(coaching["primary_action"])
        self.assertEqual(coaching["reinforcement"], "Healthy weight loss pace (1.2 lbs/week)")

    def test_no_data_reinforcement(self):
        """No data at all → reinforcement mode with tracking message."""
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={},
        )
        self.assertIsNone(coaching["primary_constraint"])
        self.assertIn("tracking", coaching["insight"].lower())

    def test_debug_shows_reinforcement_mode(self):
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=["Good sleep"],
            trends={},
            rolling_7d={"sleep_hours": 7.5},
        )
        self.assertEqual(coaching["_debug"]["mode"], "reinforcement")


# ── Parameterized Actions ───────────────────────────────────────────


class TestParameterizedActions(TestCase):
    """Actions use actual values from rolling_7d."""

    def test_sleep_action_includes_gap(self):
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={"sleep_hours": 6.0},
        )
        self.assertEqual(coaching["primary_constraint"], "sleep")
        # Gap is 60 minutes (7.0 - 6.0 = 1h = 60min)
        self.assertIn("60", coaching["primary_action"])

    def test_protein_action_includes_gap_grams(self):
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={
                "protein_ratio": 0.6,
                "protein_target_g": 180,
                "protein_consumed_g": 108,
            },
        )
        self.assertEqual(coaching["primary_constraint"], "protein")
        # Gap is 180-108 = 72g
        self.assertIn("72", coaching["primary_action"])

    def test_activity_action_includes_step_gap(self):
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={"steps": 4000},
        )
        self.assertEqual(coaching["primary_constraint"], "activity")
        # Gap is 7500-4000 = 3500
        self.assertIn("3,500", coaching["primary_action"])


# ── Debug Structure ─────────────────────────────────────────────────


class TestDebugStructure(TestCase):
    """Coaching output includes _debug dict for diagnostics."""

    def test_constraint_debug_has_all_fields(self):
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={"sleep_hours": 5.5, "steps": 4000},
        )
        debug = coaching["_debug"]
        self.assertEqual(debug["mode"], "constraint")
        self.assertIn("selected", debug)
        self.assertIn("selected_severity", debug)
        self.assertIn("domain_severities", debug)
        self.assertIn("all_reasons", debug)
        self.assertIsInstance(debug["domain_severities"], dict)
        # Both sleep and activity should show in severities
        self.assertIn("sleep", debug["domain_severities"])
        self.assertIn("activity", debug["domain_severities"])

    def test_reinforcement_debug(self):
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={},
        )
        debug = coaching["_debug"]
        self.assertEqual(debug["mode"], "reinforcement")


# ── Output Structure ────────────────────────────────────────────────


class TestOutputStructure(TestCase):
    """Coaching output has all required fields and correct types."""

    def test_constraint_output_has_all_fields(self):
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=["Strong workout frequency"],
            trends={},
            rolling_7d={"sleep_hours": 5.5},
        )
        for key in ["primary_constraint", "insight", "primary_action",
                     "secondary_action", "reinforcement", "supporting_signals", "_debug"]:
            self.assertIn(key, coaching, f"Missing key: {key}")

        self.assertIsInstance(coaching["primary_constraint"], str)
        self.assertIsInstance(coaching["insight"], str)
        self.assertIsInstance(coaching["primary_action"], str)
        self.assertIsInstance(coaching["supporting_signals"], list)
        self.assertIsInstance(coaching["_debug"], dict)

    def test_supporting_signals_excludes_primary(self):
        coaching = HealthTrendAnalyzer._build_coaching(
            risk_flags=[],
            weaknesses=[],
            strengths=[],
            trends={},
            rolling_7d={
                "sleep_hours": 5.5,  # severity ~75
                "steps": 2500,       # severity ~70
            },
        )
        self.assertEqual(coaching["primary_constraint"], "sleep")
        self.assertNotIn("sleep", coaching["supporting_signals"])
        self.assertIn("activity", coaching["supporting_signals"])

    def test_every_domain_has_insight_template(self):
        for domain, _ in HealthTrendAnalyzer._DOMAIN_SCORERS:
            self.assertIn(
                domain, HealthTrendAnalyzer._CONSTRAINT_INSIGHTS,
                f"Domain '{domain}' has a scorer but no insight template",
            )

    def test_every_domain_produces_actions(self):
        """_actions_for_domain returns a tuple for every known domain."""
        for domain, _ in HealthTrendAnalyzer._DOMAIN_SCORERS:
            actions = HealthTrendAnalyzer._actions_for_domain(domain, {})
            self.assertIsInstance(actions, tuple)
            self.assertEqual(len(actions), 2)
            self.assertIsInstance(actions[0], str)


# ── Integration ─────────────────────────────────────────────────────


class TestCoachingIntegration(TestCase):
    """Coaching output flows through HealthTrendAnalyzer.analyze()."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.conf import settings
        from apps.users.models import TermsAcceptance

        User = get_user_model()
        self.user = User.objects.create_user(
            email="coach@example.com", password="testpass123",
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_analyze_returns_coaching_with_debug(self):
        from django.utils import timezone

        result = HealthTrendAnalyzer.analyze(self.user, timezone.localdate())
        self.assertIn("coaching", result)
        coaching = result["coaching"]
        self.assertIn("primary_constraint", coaching)
        self.assertIn("_debug", coaching)

    def test_top_recommendation_matches_coaching_insight(self):
        from django.utils import timezone

        result = HealthTrendAnalyzer.analyze(self.user, timezone.localdate())
        coaching = result["coaching"]
        self.assertEqual(result["top_recommendation"], coaching["insight"])
