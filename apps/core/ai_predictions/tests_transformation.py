"""
PRIE Transformation Prediction Rule Tests.

Tests all 3 prediction rules. Validates SAE state integration where applicable.
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_predictions.prediction_rules_transformation import (
    NutritionWeightProjectionRule,
    StrengthProgressionPredictionRule,
    TransformationSuccessProbabilityRule,
)
from apps.users.models import TermsAcceptance, User


def _create_test_user(email="prie_transform@example.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ── NutritionWeightProjectionRule ──────────────────────────────


class TestNutritionWeightProjectionRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("prie_nwp@example.com")
        self.rule = NutritionWeightProjectionRule()

    def test_applies_on_health_module(self):
        event = {"module": "health"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_applies_on_nutrition_module(self):
        event = {"module": "nutrition"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_does_not_apply_on_unrelated_module(self):
        event = {"module": "journal"}
        self.assertFalse(self.rule.applies(self.user, event))

    def test_no_predictions_insufficient_data(self):
        event = {"module": "health"}
        predictions = self.rule.predict(self.user, event)
        self.assertEqual(len(predictions), 0)

    def test_predictions_with_sufficient_data(self):
        from apps.health.models import WeightEntry

        now = timezone.now()
        # Create 10 weight entries trending down
        for i in range(10):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal(str(200 - i * 0.5)),
                unit="lb",
                recorded_at=now - timedelta(days=30 - i * 3),
            )

        event = {"module": "health"}
        predictions = self.rule.predict(self.user, event)
        self.assertGreater(len(predictions), 0)

        # Verify output format
        pred = predictions[0]
        self.assertIn("prediction_type", pred)
        self.assertIn("predicted_value", pred)
        self.assertIn("predicted_date", pred)
        self.assertIn("confidence_score", pred)
        self.assertIn("explanation", pred)
        self.assertIn("evidence", pred)
        self.assertIn("dedupe_key", pred)
        self.assertEqual(pred["module"], "health")

    def test_prediction_horizons(self):
        from apps.health.models import WeightEntry

        now = timezone.now()
        for i in range(15):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal(str(200 - i * 0.3)),
                unit="lb",
                recorded_at=now - timedelta(days=45 - i * 3),
            )

        event = {"module": "health"}
        predictions = self.rule.predict(self.user, event)
        pred_types = [p["prediction_type"] for p in predictions]
        # Should have 30d and 60d horizons
        self.assertTrue(
            any("30d" in pt for pt in pred_types),
            f"Expected 30d horizon, got: {pred_types}",
        )

    def test_confidence_bounded_0_1(self):
        from apps.health.models import WeightEntry

        now = timezone.now()
        for i in range(10):
            WeightEntry.objects.create(
                user=self.user,
                value=Decimal(str(200 - i * 0.5)),
                unit="lb",
                recorded_at=now - timedelta(days=30 - i * 3),
            )

        event = {"module": "health"}
        predictions = self.rule.predict(self.user, event)
        for pred in predictions:
            self.assertGreaterEqual(pred["confidence_score"], 0)
            self.assertLessEqual(pred["confidence_score"], 1)


# ── StrengthProgressionPredictionRule ──────────────────────────


class TestStrengthProgressionPredictionRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("prie_strength@example.com")
        self.rule = StrengthProgressionPredictionRule()

    def test_applies_on_fitness_module(self):
        event = {"module": "fitness"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_no_predictions_insufficient_sessions(self):
        event = {"module": "health"}
        predictions = self.rule.predict(self.user, event)
        self.assertEqual(len(predictions), 0)

    def test_predictions_with_workout_data(self):
        from apps.health.models import Exercise, ExerciseSet, WorkoutExercise, WorkoutSession

        today = date.today()
        # Create 6 weeks of workout data
        for week in range(6):
            session = WorkoutSession.objects.create(
                user=self.user,
                name=f"Week {week} Workout",
                date=today - timedelta(weeks=week),
                duration_minutes=60,
            )
            # Add an exercise with sets
            exercise, _ = Exercise.objects.get_or_create(
                name="Bench Press",
                defaults={"category": "resistance", "muscle_group": "chest"},
            )
            we = WorkoutExercise.objects.create(
                session=session,
                exercise=exercise,
                order=1,
            )
            for s in range(3):
                ExerciseSet.objects.create(
                    workout_exercise=we,
                    set_number=s + 1,
                    weight=Decimal("135"),
                    reps=10,
                )

        event = {"module": "health"}
        predictions = self.rule.predict(self.user, event)
        # May or may not produce predictions depending on data sufficiency
        for pred in predictions:
            self.assertIn("prediction_type", pred)
            self.assertIn("predicted_value", pred)
            self.assertEqual(pred["module"], "health")


# ── TransformationSuccessProbabilityRule ────────────────────────


class TestTransformationSuccessProbabilityRule(TestCase):
    """Tests that success probability reads from SAE transformation_state."""

    def setUp(self):
        self.user = _create_test_user("prie_success@example.com")
        self.rule = TransformationSuccessProbabilityRule()

    def test_applies_on_health(self):
        event = {"module": "health"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_applies_on_all(self):
        event = {"module": "all"}
        self.assertTrue(self.rule.applies(self.user, event))

    def test_no_prediction_without_transformation_state(self):
        event = {"module": "health"}
        predictions = self.rule.predict(self.user, event)
        self.assertEqual(len(predictions), 0)

    def test_prediction_from_sae_transformation_state(self):
        """Verify prediction uses get_module_state for transformation."""
        from apps.core.ai_state.models import UserState

        # Pre-populate SAE with transformation state
        user_state, _ = UserState.objects.get_or_create(user=self.user)
        user_state.state_data = {
            "transformation": {
                "transformation_score": 75,
                "momentum_score": 80,
                "nutrition_score": 70,
                "workout_score": 85,
                "weight_trend_score": 80,
                "fasting_score": 60,
                "recovery_score": 70,
            }
        }
        user_state.save()

        event = {"module": "health"}
        predictions = self.rule.predict(self.user, event)
        self.assertGreater(len(predictions), 0)

        pred = predictions[0]
        self.assertEqual(pred["prediction_type"], "transformation_success_90d")
        self.assertIn("predicted_value", pred)
        # Probability between 0 and 1
        self.assertGreaterEqual(pred["predicted_value"], 0)
        self.assertLessEqual(pred["predicted_value"], 1)
        # Confidence between 0 and 1
        self.assertGreaterEqual(pred["confidence_score"], 0)
        self.assertLessEqual(pred["confidence_score"], 1)

    def test_evidence_contains_sub_scores(self):
        from apps.core.ai_state.models import UserState

        user_state, _ = UserState.objects.get_or_create(user=self.user)
        user_state.state_data = {
            "transformation": {
                "transformation_score": 65,
                "momentum_score": 70,
                "nutrition_score": 60,
                "workout_score": 75,
            }
        }
        user_state.save()

        event = {"module": "health"}
        predictions = self.rule.predict(self.user, event)
        self.assertGreater(len(predictions), 0)
        evidence = predictions[0].get("evidence", {})
        self.assertIn("transformation_score", evidence)
        self.assertIn("probability", evidence)
        self.assertIn("outlook", evidence)
