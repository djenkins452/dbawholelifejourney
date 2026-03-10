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


# ── StrengthPlateauRule Auto-Resolution Tests ────────────────


class TestStrengthPlateauAutoResolution(TestCase):
    """Verify that plateau insights are dismissed when exercises improve."""

    def setUp(self):
        from apps.core.ai_insights.models import Insight
        self.user = _create_test_user("pie_resolve@example.com")
        self.rule = StrengthPlateauRule()
        # Pre-create an active plateau insight
        self.plateau_insight = Insight.objects.create(
            user=self.user,
            module="health",
            insight_type="strength_plateau",
            severity="info",
            title="Exercise plateau detected",
            message="Your bench press appears to be plateauing.",
            confidence_score=0.75,
            explain_why="Rule: strength_plateau",
            evidence={"rule_name": "strength_plateau"},
            status="new",
            dedupe_key="test_plateau_dedupe_001",
        )

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

    def test_all_improving_resolves_plateau_insight(self):
        """When all exercises are improving, old plateau insight is dismissed."""
        from apps.core.ai_insights.models import Insight
        progress = [
            {"exercise": "Bench Press", "sessions_30d": 6, "sets_30d": 18,
             "prs_30d": 2, "best_e1rm": 220, "recent_e1rm": 220,
             "prior_e1rm": 208, "trend": "up", "status": "improving"},
        ]
        insights = self.rule.evaluate(self.user, self._make_event(progress))
        self.assertEqual(len(insights), 0)
        self.plateau_insight.refresh_from_db()
        self.assertEqual(self.plateau_insight.status, "dismissed")

    def test_empty_progress_resolves_plateau_insight(self):
        """Empty exercise list (no exercises meet threshold) also resolves."""
        from apps.core.ai_insights.models import Insight
        insights = self.rule.evaluate(self.user, self._make_event([]))
        self.assertEqual(len(insights), 0)
        self.plateau_insight.refresh_from_db()
        self.assertEqual(self.plateau_insight.status, "dismissed")

    def test_plateau_still_active_keeps_insight(self):
        """Plateau insight is NOT dismissed when plateau still exists."""
        progress = [
            {"exercise": "Bench Press", "sessions_30d": 6, "sets_30d": 18,
             "prs_30d": 0, "best_e1rm": 208, "recent_e1rm": 208,
             "prior_e1rm": 208, "trend": "flat", "status": "plateau"},
        ]
        insights = self.rule.evaluate(self.user, self._make_event(progress))
        self.assertEqual(len(insights), 1)
        self.plateau_insight.refresh_from_db()
        # The existing insight is updated via dedupe, NOT dismissed
        self.assertIn(self.plateau_insight.status, ["new", "read"])

    def test_dismissed_insight_not_re_dismissed(self):
        """Already dismissed insights should not be affected."""
        from apps.core.ai_insights.models import Insight
        self.plateau_insight.status = "dismissed"
        self.plateau_insight.save()
        progress = [
            {"exercise": "Bench Press", "sessions_30d": 6, "sets_30d": 18,
             "prs_30d": 2, "best_e1rm": 220, "recent_e1rm": 220,
             "prior_e1rm": 208, "trend": "up", "status": "improving"},
        ]
        self.rule.evaluate(self.user, self._make_event(progress))
        self.plateau_insight.refresh_from_db()
        self.assertEqual(self.plateau_insight.status, "dismissed")

    def test_global_fallback_resolves_on_prs(self):
        """Global fallback path: PRs found → resolve stale insight."""
        from apps.core.ai_insights.models import Insight
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_30d": 12,
                    "prs_30d": 3,
                    # No exercise_progress → triggers global fallback
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)
        self.plateau_insight.refresh_from_db()
        self.assertEqual(self.plateau_insight.status, "dismissed")

    def test_global_fallback_resolves_on_increasing_trend(self):
        """Global fallback path: increasing trend → resolve stale insight."""
        from apps.core.ai_insights.models import Insight
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_30d": 12,
                    "prs_30d": 0,
                    "strength_trend_score": "increasing",
                }
            },
        }
        insights = self.rule.evaluate(self.user, event)
        self.assertEqual(len(insights), 0)
        self.plateau_insight.refresh_from_db()
        self.assertEqual(self.plateau_insight.status, "dismissed")

    def test_does_not_resolve_other_insight_types(self):
        """Resolution only targets strength_plateau, not other types."""
        from apps.core.ai_insights.models import Insight
        other_insight = Insight.objects.create(
            user=self.user,
            module="health",
            insight_type="weight_trend_up",
            severity="info",
            title="Weight trend up",
            message="Your weight is trending up.",
            confidence_score=0.80,
            explain_why="Rule: weight_trend_up",
            evidence={},
            status="new",
            dedupe_key="test_other_dedupe_001",
        )
        progress = [
            {"exercise": "Bench Press", "sessions_30d": 6, "sets_30d": 18,
             "prs_30d": 2, "best_e1rm": 220, "recent_e1rm": 220,
             "prior_e1rm": 208, "trend": "up", "status": "improving"},
        ]
        self.rule.evaluate(self.user, self._make_event(progress))
        other_insight.refresh_from_db()
        self.assertEqual(other_insight.status, "new")  # Untouched


# ── CoS Freshness Window Tests ──────────────────────────────


class TestCoSInsightFreshnessWindow(TestCase):
    """Verify CoS only surfaces insights within the freshness window."""

    def setUp(self):
        from apps.core.ai_insights.models import Insight
        self.user = _create_test_user("cos_fresh@example.com")
        now = timezone.now()
        # Recent insight (within 72h)
        self.recent = Insight.objects.create(
            user=self.user, module="health",
            insight_type="strength_plateau", severity="info",
            title="Recent plateau", message="Recent",
            confidence_score=0.75, explain_why="test",
            evidence={}, status="new", dedupe_key="cos_fresh_recent",
        )
        # Old insight (4 days ago — outside 72h window)
        self.stale = Insight.objects.create(
            user=self.user, module="health",
            insight_type="strength_plateau", severity="info",
            title="Old plateau", message="Stale",
            confidence_score=0.75, explain_why="test",
            evidence={}, status="new", dedupe_key="cos_fresh_stale",
        )
        from apps.core.ai_insights.models import Insight as I
        I.objects.filter(pk=self.stale.pk).update(
            created_at=now - timezone.timedelta(days=4),
        )

    def test_fresh_insights_included(self):
        from apps.core.ai_orchestrator.cos_context import _build_intelligence_signals
        signals = _build_intelligence_signals(self.user)
        titles = [i['title'] for i in signals.get('active_insights', [])]
        self.assertIn("Recent plateau", titles)

    def test_stale_insights_excluded(self):
        from apps.core.ai_orchestrator.cos_context import _build_intelligence_signals
        signals = _build_intelligence_signals(self.user)
        titles = [i['title'] for i in signals.get('active_insights', [])]
        self.assertNotIn("Old plateau", titles)


# ── Exercise Progress Weight-Progression Tests ───────────────


class TestExerciseProgressWeightProgression(TestCase):
    """Verify _build_exercise_progress uses raw weight as secondary signal."""

    def setUp(self):
        self.user = _create_test_user("progress_weight@example.com")

    def test_weight_increase_overrides_flat_e1rm(self):
        """If e1RM is flat but raw weight went up 5+ lbs, status should be improving."""
        from apps.core.ai_state.state_builder import _build_exercise_progress
        from apps.core.time.system_clock import get_current_time
        from apps.health.models import (
            Exercise, ExerciseSet, WorkoutExercise, WorkoutSession,
        )

        now = get_current_time()
        cutoff_30d = now - timezone.timedelta(days=30)

        ex = Exercise.objects.create(
            name="Test Bench Press", category="resistance",
        )

        # Prior period (15-30 days ago): 135 lbs × 8 reps → e1RM ≈ 171
        prior_session = WorkoutSession.objects.create(
            user=self.user, date=(now - timezone.timedelta(days=20)).date(),
            name="Workout A", status="active",
        )
        prior_we = WorkoutExercise.objects.create(
            session=prior_session, exercise=ex, order=1,
        )
        for i in range(1, 5):  # 4 sets to meet threshold
            ExerciseSet.objects.create(
                workout_exercise=prior_we, set_number=i,
                weight=135, reps=8, is_warmup=False,
            )

        # Recent period (last 14 days): 145 lbs × 5 reps → e1RM ≈ 163
        # Weight went UP by 10 lbs, but e1RM went DOWN slightly.
        # The raw weight increase should override the flat/down e1RM.
        recent_session = WorkoutSession.objects.create(
            user=self.user, date=(now - timezone.timedelta(days=3)).date(),
            name="Workout B", status="active",
        )
        recent_we = WorkoutExercise.objects.create(
            session=recent_session, exercise=ex, order=1,
        )
        for i in range(1, 5):  # 4 sets
            ExerciseSet.objects.create(
                workout_exercise=recent_we, set_number=i,
                weight=145, reps=5, is_warmup=False,
            )

        progress = _build_exercise_progress(self.user, cutoff_30d)
        self.assertEqual(len(progress), 1)
        entry = progress[0]
        self.assertEqual(entry["exercise"], "Test Bench Press")
        # Should be "improving" due to 10 lb weight increase, not "plateau"
        self.assertEqual(entry["status"], "improving")
        self.assertEqual(entry["trend"], "up")

    def test_small_weight_change_stays_plateau(self):
        """Tiny weight change (<3% and <5 lbs) should NOT override plateau."""
        from apps.core.ai_state.state_builder import _build_exercise_progress
        from apps.core.time.system_clock import get_current_time
        from apps.health.models import (
            Exercise, ExerciseSet, PersonalRecord,
            WorkoutExercise, WorkoutSession,
        )

        now = get_current_time()
        cutoff_30d = now - timezone.timedelta(days=30)

        ex = Exercise.objects.create(
            name="Test OHP", category="resistance",
        )

        # Prior: 100 lbs × 8 reps → e1RM ≈ 126.9
        prior = WorkoutSession.objects.create(
            user=self.user, date=(now - timezone.timedelta(days=20)).date(),
            name="W1", status="active",
        )
        prior_we = WorkoutExercise.objects.create(
            session=prior, exercise=ex, order=1,
        )
        for i in range(1, 5):
            ExerciseSet.objects.create(
                workout_exercise=prior_we, set_number=i,
                weight=100, reps=8, is_warmup=False,
            )

        # Recent: 102 lbs × 7 reps → e1RM ≈ 122.4 (slightly lower)
        # Weight only went up 2 lbs (2%, below 3% threshold)
        recent = WorkoutSession.objects.create(
            user=self.user, date=(now - timezone.timedelta(days=3)).date(),
            name="W2", status="active",
        )
        recent_we = WorkoutExercise.objects.create(
            session=recent, exercise=ex, order=1,
        )
        for i in range(1, 5):
            ExerciseSet.objects.create(
                workout_exercise=recent_we, set_number=i,
                weight=102, reps=7, is_warmup=False,
            )

        # Clear auto-created PRs so prs_30d doesn't override status
        PersonalRecord.objects.filter(user=self.user, exercise=ex).delete()

        progress = _build_exercise_progress(self.user, cutoff_30d)
        self.assertEqual(len(progress), 1)
        entry = progress[0]
        # e1RM went down slightly and weight change is negligible → should stay plateau
        self.assertIn(entry["status"], ["plateau", "regressing"])
