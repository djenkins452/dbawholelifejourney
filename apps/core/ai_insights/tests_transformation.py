"""
PIE Transformation Insight Rule Tests.

All 7 rules tested with SAE state dict input via event["user_state"].
Tests validate pipeline behavior: applies() + evaluate() with state, not raw ORM.
"""

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_insights.rules_transformation import (
    CarbGlucoseCorrelationRule,
    FastingConsistencyRule,
    NutritionCalorieTrendRule,
    ProteinDeficitRule,
    StrengthPlateauRule,
    TransformationMomentumRule,
    WorkoutConsistencyRule,
)
from apps.users.models import TermsAcceptance, User


def _create_test_user(email="pie_transform@example.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ── NutritionCalorieTrendRule ──────────────────────────────────


class TestNutritionCalorieTrendRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("pie_cal@example.com")
        self.rule = NutritionCalorieTrendRule()

    def test_applies_on_health_module(self):
        event = {"module": "health", "action": "log_food"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_applies_on_nutrition_module(self):
        event = {"module": "nutrition", "action": "log_food"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_applies_on_scheduled_check(self):
        event = {"event_type": "scheduled_check"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_triggers_when_calories_over_target(self):
        event = {
            "module": "health",
            "user_state": {
                "nutrition": {
                    "rolling_7d_calories_avg": 3000,
                    "calorie_target": 2000,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "warning")
        self.assertIn("confidence_score", insights[0])
        self.assertIn("dedupe_key", insights[0])
        self.assertIn("evidence", insights[0])

    def test_no_trigger_within_range(self):
        event = {
            "module": "health",
            "user_state": {
                "nutrition": {
                    "rolling_7d_calories_avg": 2100,
                    "calorie_target": 2000,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)

    def test_no_trigger_missing_data(self):
        event = {"module": "health", "user_state": {"nutrition": {}}}
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)


# ── ProteinDeficitRule ──────────────────────────────────────────


class TestProteinDeficitRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("pie_protein@example.com")
        self.rule = ProteinDeficitRule()

    def test_applies_on_health_module(self):
        event = {"module": "health"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_triggers_on_low_protein(self):
        event = {
            "module": "nutrition",
            "user_state": {
                "nutrition": {
                    "rolling_7d_protein_avg": 90,
                    "protein_target": 150,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "warning")
        self.assertIn("confidence_score", insights[0])

    def test_no_trigger_adequate_protein(self):
        event = {
            "module": "nutrition",
            "user_state": {
                "nutrition": {
                    "rolling_7d_protein_avg": 140,
                    "protein_target": 150,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)

    def test_no_trigger_no_target(self):
        event = {
            "module": "nutrition",
            "user_state": {
                "nutrition": {"rolling_7d_protein_avg": 90}
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)


# ── CarbGlucoseCorrelationRule ──────────────────────────────────


class TestCarbGlucoseCorrelationRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("pie_carb_glucose@example.com")
        self.rule = CarbGlucoseCorrelationRule()

    def test_applies_on_health(self):
        event = {"module": "health"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_no_trigger_without_high_carbs(self):
        event = {
            "module": "health",
            "user_state": {
                "nutrition": {"daily_carbs_g": 180, "carb_target": 200},
                "health": {},
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)

    def test_no_trigger_missing_carb_data(self):
        event = {"module": "health", "user_state": {"nutrition": {}, "health": {}}}
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)


# ── FastingConsistencyRule ──────────────────────────────────────


class TestFastingConsistencyRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("pie_fasting@example.com")
        self.rule = FastingConsistencyRule()

    def test_applies_on_fast_action(self):
        event = {"module": "health", "action": "end_fast"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_triggers_positive_high_compliance(self):
        event = {
            "module": "health",
            "action": "end_fast",
            "user_state": {
                "fasting": {
                    "fasts_7d": 5,
                    "fasting_compliance_score": 90,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "positive")

    def test_triggers_info_no_fasts_with_history(self):
        """User who has fasted before but 0 fasts this week gets info nudge."""
        event = {
            "module": "health",
            "action": "scheduled_check",
            "event_type": "scheduled_check",
            "user_state": {
                "fasting": {
                    "fasts_7d": 0,
                    "fasting_compliance_score": 0,
                    "last_fast_end": "2026-02-10T08:00:00Z",
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "info")

    def test_no_trigger_no_fasting_history(self):
        event = {
            "module": "health",
            "action": "end_fast",
            "user_state": {
                "fasting": {"fasts_7d": 0, "fasting_compliance_score": None}
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)


# ── WorkoutConsistencyRule ─────────────────────────────────────


class TestWorkoutConsistencyRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("pie_workout@example.com")
        self.rule = WorkoutConsistencyRule()

    def test_applies_on_fitness(self):
        event = {"module": "fitness"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_triggers_positive_strong_week(self):
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_7d": 4,
                    "workouts_30d": 12,
                    "workout_consistency_score": 120,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "positive")

    def test_triggers_warning_no_workouts(self):
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_7d": 0,
                    "workouts_30d": 12,
                    "workout_consistency_score": 0,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "warning")

    def test_no_trigger_no_history(self):
        event = {
            "module": "health",
            "user_state": {
                "fitness": {"workouts_7d": 0, "workouts_30d": 0}
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)


# ── StrengthPlateauRule ────────────────────────────────────────


class TestStrengthPlateauRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("pie_plateau@example.com")
        self.rule = StrengthPlateauRule()

    def test_applies_on_health(self):
        event = {"module": "health"}
        self.assertTrue(self.rule.applies(self.user, event))

    # ── Global fallback tests (no exercise_progress in state) ──

    def test_triggers_plateau_detected(self):
        """Global fallback: fires when 0 PRs and no exercise_progress."""
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_30d": 12,
                    "prs_30d": 0,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "info")
        self.assertIn("plateau", insights[0]["title"].lower())

    def test_no_trigger_has_prs(self):
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_30d": 12,
                    "prs_30d": 3,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)

    def test_no_trigger_insufficient_workouts(self):
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_30d": 3,
                    "prs_30d": 0,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)

    # ── Exercise-specific plateau tests ──

    def _make_event(self, exercise_progress):
        return {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_30d": 12,
                    "prs_30d": 0,
                    "exercise_progress": exercise_progress,
                }
            },
        }

    def test_one_exercise_plateau_one_improving(self):
        """Insight should fire and name only the plateauing exercise."""
        progress = [
            {"exercise": "Bench Press", "sessions_30d": 6, "sets_30d": 18,
             "prs_30d": 0, "best_e1rm": 208, "recent_e1rm": 208,
             "prior_e1rm": 208, "trend": "flat", "status": "plateau"},
            {"exercise": "Squat", "sessions_30d": 5, "sets_30d": 15,
             "prs_30d": 2, "best_e1rm": 300, "recent_e1rm": 300,
             "prior_e1rm": 285, "trend": "up", "status": "improving"},
        ]
        insights = self.rule.evaluate(self.user, self._make_event(progress))
        self.assertEqual(len(insights), 1)
        msg = insights[0]["message"].lower()
        self.assertIn("bench press", msg)
        self.assertIn("squat", msg)
        self.assertIn("progressing", msg)

    def test_all_exercises_improving_no_insight(self):
        """No insight when all exercises are improving."""
        progress = [
            {"exercise": "Bench Press", "sessions_30d": 6, "sets_30d": 18,
             "prs_30d": 2, "best_e1rm": 220, "recent_e1rm": 220,
             "prior_e1rm": 208, "trend": "up", "status": "improving"},
            {"exercise": "Squat", "sessions_30d": 5, "sets_30d": 15,
             "prs_30d": 1, "best_e1rm": 300, "recent_e1rm": 300,
             "prior_e1rm": 285, "trend": "up", "status": "improving"},
        ]
        insights = self.rule.evaluate(self.user, self._make_event(progress))
        self.assertEqual(len(insights), 0)

    def test_all_exercises_plateau(self):
        """Insight should name all plateauing exercises."""
        progress = [
            {"exercise": "Bench Press", "sessions_30d": 6, "sets_30d": 18,
             "prs_30d": 0, "best_e1rm": 208, "recent_e1rm": 208,
             "prior_e1rm": 208, "trend": "flat", "status": "plateau"},
            {"exercise": "Overhead Press", "sessions_30d": 4, "sets_30d": 12,
             "prs_30d": 0, "best_e1rm": 130, "recent_e1rm": 130,
             "prior_e1rm": 130, "trend": "flat", "status": "plateau"},
        ]
        insights = self.rule.evaluate(self.user, self._make_event(progress))
        self.assertEqual(len(insights), 1)
        msg = insights[0]["message"].lower()
        self.assertIn("bench press", msg)
        self.assertIn("overhead press", msg)

    def test_regressing_exercise_triggers_insight(self):
        """Regressing exercises should also trigger the insight."""
        progress = [
            {"exercise": "Bench Press", "sessions_30d": 6, "sets_30d": 18,
             "prs_30d": 0, "best_e1rm": 208, "recent_e1rm": 195,
             "prior_e1rm": 208, "trend": "down", "status": "regressing"},
        ]
        insights = self.rule.evaluate(self.user, self._make_event(progress))
        self.assertEqual(len(insights), 1)
        msg = insights[0]["message"].lower()
        self.assertIn("bench press", msg)

    def test_empty_exercise_progress_no_insight(self):
        """Empty exercise_progress list means no exercises meet threshold."""
        insights = self.rule.evaluate(self.user, self._make_event([]))
        self.assertEqual(len(insights), 0)

    def test_only_new_exercises_no_insight(self):
        """Exercises with status='new' should not trigger plateau."""
        progress = [
            {"exercise": "Romanian Deadlift", "sessions_30d": 2, "sets_30d": 6,
             "prs_30d": 1, "best_e1rm": 200, "recent_e1rm": 200,
             "prior_e1rm": None, "trend": "new", "status": "new"},
        ]
        insights = self.rule.evaluate(self.user, self._make_event(progress))
        self.assertEqual(len(insights), 0)

    def test_evidence_includes_exercise_progress(self):
        """Evidence should contain the full exercise_progress data."""
        progress = [
            {"exercise": "Bench Press", "sessions_30d": 6, "sets_30d": 18,
             "prs_30d": 0, "best_e1rm": 208, "recent_e1rm": 208,
             "prior_e1rm": 208, "trend": "flat", "status": "plateau"},
        ]
        insights = self.rule.evaluate(self.user, self._make_event(progress))
        self.assertEqual(len(insights), 1)
        evidence = insights[0]["evidence"]
        self.assertIn("exercise_progress", evidence)
        self.assertEqual(evidence["plateauing"], ["Bench Press"])
        self.assertEqual(evidence["improving"], [])

    def test_title_says_exercise_plateau(self):
        """Title should say 'Exercise plateau' not generic 'Strength plateau'."""
        progress = [
            {"exercise": "Squat", "sessions_30d": 6, "sets_30d": 18,
             "prs_30d": 0, "best_e1rm": 300, "recent_e1rm": 300,
             "prior_e1rm": 300, "trend": "flat", "status": "plateau"},
        ]
        insights = self.rule.evaluate(self.user, self._make_event(progress))
        self.assertEqual(insights[0]["title"], "Exercise plateau detected")


# ── TransformationMomentumRule ─────────────────────────────────


class TestTransformationMomentumRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("pie_momentum@example.com")
        self.rule = TransformationMomentumRule()

    def test_applies_on_health(self):
        event = {"module": "health"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_applies_on_scheduled_check(self):
        event = {"event_type": "scheduled_check"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_triggers_positive_high_score(self):
        event = {
            "module": "health",
            "user_state": {
                "transformation": {
                    "transformation_score": 80,
                    "momentum_score": 85,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "positive")
        self.assertIn("confidence_score", insights[0])

    def test_triggers_warning_low_score(self):
        event = {
            "module": "health",
            "user_state": {
                "transformation": {
                    "transformation_score": 30,
                    "momentum_score": 40,
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 1)
        self.assertEqual(insights[0]["severity"], "warning")

    def test_no_trigger_no_score(self):
        event = {
            "module": "health",
            "user_state": {"transformation": {}},
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)
