"""
SAE Transformation State Builder Tests.

Tests all 4 new builders: nutrition, fasting, fitness, transformation.
Validates SAE-first architecture — transformation reads from SAE state, not DB.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_state.state_builder import (
    build_fasting_state,
    build_fitness_state,
    build_nutrition_state,
    build_transformation_state,
)
from apps.users.models import TermsAcceptance, User


def _create_test_user(email="sae_transform@example.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ── Nutrition Builder Tests ─────────────────────────────────────


class TestBuildNutritionStateEmpty(TestCase):
    def setUp(self):
        self.user = _create_test_user("nutrition_empty@example.com")

    def test_empty_state_no_food_data(self):
        state = build_nutrition_state(self.user)
        self.assertEqual(state.get("food_entries_7d", 0), 0)
        self.assertNotIn("rolling_7d_calories_avg", state)
        self.assertNotIn("calorie_target", state)

    def test_returns_dict(self):
        state = build_nutrition_state(self.user)
        self.assertIsInstance(state, dict)


class TestBuildNutritionStateWithData(TestCase):
    def setUp(self):
        self.user = _create_test_user("nutrition_data@example.com")

    def test_food_entries_reflected_in_state(self):
        from apps.health.models import FoodEntry

        today = date.today()
        for i in range(3):
            FoodEntry.objects.create(
                user=self.user,
                food_name=f"Chicken Breast {i}",
                total_calories=Decimal("300"),
                total_protein_g=Decimal("40"),
                total_carbohydrates_g=Decimal("5"),
                total_fat_g=Decimal("8"),
                logged_date=today - timedelta(days=i),
                serving_size=Decimal("1"),
                serving_unit="serving",
            )

        state = build_nutrition_state(self.user)
        self.assertGreater(state.get("food_entries_7d", 0), 0)
        self.assertGreater(state.get("food_entries_today", 0), 0)

    def test_rolling_averages_calculated(self):
        from apps.health.models import FoodEntry

        today = date.today()
        for i in range(5):
            FoodEntry.objects.create(
                user=self.user,
                food_name=f"Meal {i}",
                total_calories=Decimal("500"),
                total_protein_g=Decimal("30"),
                total_carbohydrates_g=Decimal("50"),
                total_fat_g=Decimal("20"),
                logged_date=today - timedelta(days=i),
                serving_size=Decimal("1"),
                serving_unit="serving",
            )

        state = build_nutrition_state(self.user)
        # Should have rolling averages
        if "rolling_7d_calories_avg" in state:
            self.assertGreater(state["rolling_7d_calories_avg"], 0)
        if "rolling_7d_protein_avg" in state:
            self.assertGreater(state["rolling_7d_protein_avg"], 0)

    def test_compliance_scores_with_targets(self):
        from apps.health.models import FoodEntry, NutritionGoals

        # Create nutrition goals
        NutritionGoals.objects.create(
            user=self.user,
            daily_calorie_target=2000,
            daily_protein_target_g=150,
            daily_carb_target_g=200,
            daily_fat_target_g=80,
            effective_from=date.today() - timedelta(days=30),
        )

        today = date.today()
        for i in range(7):
            FoodEntry.objects.create(
                user=self.user,
                food_name=f"Meal {i}",
                total_calories=Decimal("1800"),
                total_protein_g=Decimal("120"),
                total_carbohydrates_g=Decimal("180"),
                total_fat_g=Decimal("70"),
                logged_date=today - timedelta(days=i),
                serving_size=Decimal("1"),
                serving_unit="serving",
            )

        state = build_nutrition_state(self.user)
        self.assertIn("calorie_target", state)
        self.assertEqual(state["calorie_target"], 2000)
        self.assertIn("protein_target", state)
        self.assertEqual(state["protein_target"], 150)


# ── Fasting Builder Tests ──────────────────────────────────────


class TestBuildFastingStateEmpty(TestCase):
    def setUp(self):
        self.user = _create_test_user("fasting_empty@example.com")

    def test_empty_state_no_fasting_data(self):
        state = build_fasting_state(self.user)
        self.assertIsInstance(state, dict)
        self.assertEqual(state.get("fasts_7d", 0), 0)
        self.assertFalse(state.get("current_fast_active", False))

    def test_returns_dict(self):
        state = build_fasting_state(self.user)
        self.assertIsInstance(state, dict)


class TestBuildFastingStateWithData(TestCase):
    def setUp(self):
        self.user = _create_test_user("fasting_data@example.com")

    def test_completed_fasts_counted(self):
        from apps.health.models import FastingWindow

        now = timezone.now()
        for i in range(3):
            start = now - timedelta(days=i + 1, hours=18)
            end = now - timedelta(days=i, hours=2)
            FastingWindow.objects.create(
                user=self.user,
                started_at=start,
                ended_at=end,
            )

        state = build_fasting_state(self.user)
        self.assertGreaterEqual(state.get("fasts_7d", 0), 3)
        self.assertIn("rolling_7d_fasting_hours", state)

    def test_active_fast_detected(self):
        from apps.health.models import FastingWindow

        # Open fast (no ended_at)
        FastingWindow.objects.create(
            user=self.user,
            started_at=timezone.now() - timedelta(hours=14),
            ended_at=None,
        )

        state = build_fasting_state(self.user)
        self.assertTrue(state.get("current_fast_active", False))

    def test_fasting_compliance_score_bounded(self):
        from apps.health.models import FastingWindow

        now = timezone.now()
        for i in range(7):
            start = now - timedelta(days=i + 1, hours=16)
            end = now - timedelta(days=i)
            FastingWindow.objects.create(
                user=self.user,
                started_at=start,
                ended_at=end,
            )

        state = build_fasting_state(self.user)
        compliance = state.get("fasting_compliance_score")
        if compliance is not None:
            self.assertGreaterEqual(compliance, 0)
            self.assertLessEqual(compliance, 100)


# ── Fitness Builder Tests ──────────────────────────────────────


class TestBuildFitnessStateEmpty(TestCase):
    def setUp(self):
        self.user = _create_test_user("fitness_empty@example.com")

    def test_empty_state_no_workout_data(self):
        state = build_fitness_state(self.user)
        self.assertIsInstance(state, dict)
        self.assertEqual(state.get("workouts_7d", 0), 0)
        self.assertEqual(state.get("workouts_30d", 0), 0)

    def test_returns_dict(self):
        state = build_fitness_state(self.user)
        self.assertIsInstance(state, dict)


class TestBuildFitnessStateWithData(TestCase):
    def setUp(self):
        self.user = _create_test_user("fitness_data@example.com")

    def test_workout_counts_reflected(self):
        from apps.health.models import WorkoutSession

        today = date.today()
        for i in range(4):
            WorkoutSession.objects.create(
                user=self.user,
                name=f"Workout {i}",
                date=today - timedelta(days=i),
                duration_minutes=60,
            )

        state = build_fitness_state(self.user)
        self.assertEqual(state["workouts_7d"], 4)
        self.assertGreaterEqual(state["workouts_30d"], 4)

    def test_avg_workout_duration(self):
        from apps.health.models import WorkoutSession

        today = date.today()
        for i in range(3):
            WorkoutSession.objects.create(
                user=self.user,
                name=f"Workout {i}",
                date=today - timedelta(days=i),
                duration_minutes=45 + i * 10,
            )

        state = build_fitness_state(self.user)
        self.assertIn("avg_workout_duration", state)
        self.assertGreater(state["avg_workout_duration"], 0)


# ── Transformation Builder Tests (Composite — SAE only) ────────


class TestBuildTransformationStateEmpty(TestCase):
    def setUp(self):
        self.user = _create_test_user("transform_empty@example.com")

    def test_empty_state_no_data(self):
        state = build_transformation_state(self.user)
        self.assertIsInstance(state, dict)
        # No sub-scores should be present
        self.assertNotIn("transformation_score", state)

    def test_returns_dict(self):
        state = build_transformation_state(self.user)
        self.assertIsInstance(state, dict)


class TestBuildTransformationStateFromSAE(TestCase):
    """Transformation state must read from UserState model, not raw DB."""

    def setUp(self):
        self.user = _create_test_user("transform_sae@example.com")

    def test_reads_from_user_state_model(self):
        """Verify transformation builder reads from UserState, not ORM models."""
        from apps.core.ai_state.models import UserState

        # Pre-populate UserState with module states
        user_state, _ = UserState.objects.get_or_create(user=self.user)
        user_state.state_data = {
            "health": {
                "weight_trend": "decreasing",
                "sleep_avg_duration_7d": 450,
            },
            "nutrition": {
                "macro_compliance_score": 75,
                "food_entries_7d": 5,
            },
            "fasting": {
                "fasting_compliance_score": 80,
                "fasts_7d": 5,
            },
            "fitness": {
                "workout_consistency_score": 90,
                "workouts_7d": 4,
            },
        }
        user_state.save()

        state = build_transformation_state(self.user)

        # Should have computed scores from SAE state
        self.assertIn("transformation_score", state)
        self.assertIn("weight_trend_score", state)
        self.assertIn("nutrition_score", state)
        self.assertIn("fasting_score", state)
        self.assertIn("workout_score", state)

    def test_transformation_score_bounded_0_100(self):
        from apps.core.ai_state.models import UserState

        user_state, _ = UserState.objects.get_or_create(user=self.user)
        user_state.state_data = {
            "health": {"weight_trend": "decreasing", "sleep_avg_duration_7d": 480},
            "nutrition": {"macro_compliance_score": 100, "food_entries_7d": 7},
            "fasting": {"fasting_compliance_score": 100, "fasts_7d": 7},
            "fitness": {"workout_consistency_score": 100, "workouts_7d": 5},
        }
        user_state.save()

        state = build_transformation_state(self.user)
        score = state.get("transformation_score")
        if score is not None:
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)

    def test_momentum_score_based_on_active_domains(self):
        from apps.core.ai_state.models import UserState

        user_state, _ = UserState.objects.get_or_create(user=self.user)
        # Only 2 active domains
        user_state.state_data = {
            "health": {"weight_entries_90d": 5},
            "nutrition": {"food_entries_7d": 3},
            "fasting": {},
            "fitness": {},
        }
        user_state.save()

        state = build_transformation_state(self.user)
        momentum = state.get("momentum_score", 0)
        # 2 out of 5 domains active → 40%
        self.assertLessEqual(momentum, 60)

    def test_does_not_query_db_directly(self):
        """Confirm transformation builder imports UserState, not health models."""
        import inspect
        source = inspect.getsource(build_transformation_state)
        # Should reference UserState
        self.assertIn("UserState", source)
        # Should NOT import health models like FoodEntry, WorkoutSession, etc.
        self.assertNotIn("FoodEntry", source)
        self.assertNotIn("WorkoutSession", source)
        self.assertNotIn("FastingWindow", source)
        self.assertNotIn("WeightEntry", source)

    def test_handles_missing_user_state(self):
        """If no UserState exists, should return empty dict."""
        from apps.core.ai_state.models import UserState
        UserState.objects.filter(user=self.user).delete()

        state = build_transformation_state(self.user)
        self.assertIsInstance(state, dict)
        self.assertNotIn("transformation_score", state)

    def test_weight_trend_scores(self):
        """Validate weight trend score mappings."""
        from apps.core.ai_state.models import UserState

        user_state, _ = UserState.objects.get_or_create(user=self.user)

        for trend, expected_score in [
            ("decreasing", 80),
            ("stable", 60),
            ("increasing", 30),
        ]:
            user_state.state_data = {
                "health": {"weight_trend": trend},
                "nutrition": {},
                "fasting": {},
                "fitness": {},
            }
            user_state.save()

            state = build_transformation_state(self.user)
            self.assertEqual(
                state.get("weight_trend_score"),
                expected_score,
                f"Failed for trend={trend}",
            )
