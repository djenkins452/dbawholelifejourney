"""
PRIE — Tests for the Predictive Intelligence Engine.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytz
from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.core.ai_predictions.confidence_engine import (
    compute_confidence,
    confidence_label,
)
from apps.core.ai_predictions.models import Prediction, build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_engine import (
    _upsert_prediction,
    generate_predictions,
)
from apps.core.ai_predictions.projection_math import (
    calculate_rate_of_change,
    linear_regression,
    project_value,
)
from apps.core.ai_predictions.trajectory_engine import calculate_linear_projection
from apps.users.models import TermsAcceptance, User


def _create_test_user(email="predtest@test.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


# ─── Projection Math Tests ──────────────────────────────────


class LinearRegressionTests(TestCase):
    def test_perfect_linear(self):
        """Perfect linear data should give R²=1.0."""
        x = [0, 1, 2, 3, 4]
        y = [10, 12, 14, 16, 18]
        slope, intercept, r_sq = linear_regression(x, y)
        self.assertAlmostEqual(slope, 2.0, places=5)
        self.assertAlmostEqual(intercept, 10.0, places=5)
        self.assertAlmostEqual(r_sq, 1.0, places=5)

    def test_constant_values(self):
        """All same values → slope 0, R²=1.0."""
        x = [0, 1, 2, 3]
        y = [5, 5, 5, 5]
        slope, intercept, r_sq = linear_regression(x, y)
        self.assertAlmostEqual(slope, 0.0)
        self.assertAlmostEqual(intercept, 5.0)
        self.assertAlmostEqual(r_sq, 1.0)

    def test_single_point(self):
        """One data point → slope=0."""
        slope, intercept, r_sq = linear_regression([0], [10])
        self.assertEqual(slope, 0.0)
        self.assertEqual(intercept, 10.0)

    def test_two_points(self):
        """Two points → perfect fit."""
        slope, intercept, r_sq = linear_regression([0, 10], [100, 150])
        self.assertAlmostEqual(slope, 5.0)
        self.assertAlmostEqual(intercept, 100.0)
        self.assertAlmostEqual(r_sq, 1.0)

    def test_noisy_data(self):
        """Noisy data should give R² < 1."""
        x = [0, 1, 2, 3, 4, 5]
        y = [10, 15, 12, 18, 14, 20]
        slope, intercept, r_sq = linear_regression(x, y)
        self.assertGreater(slope, 0)
        self.assertLess(r_sq, 1.0)
        self.assertGreater(r_sq, 0.0)

    def test_project_value(self):
        """Project value at a target x."""
        val = project_value(2.0, 10.0, 5.0)
        self.assertAlmostEqual(val, 20.0)


class RateOfChangeTests(TestCase):
    def test_stable(self):
        result = calculate_rate_of_change(0.005, "lbs")
        self.assertIn("stable", result)

    def test_increasing(self):
        result = calculate_rate_of_change(0.5, "lbs")
        self.assertIn("increasing", result)

    def test_decreasing(self):
        result = calculate_rate_of_change(-0.2, "lbs")
        self.assertIn("decreasing", result)


# ─── Trajectory Engine Tests ─────────────────────────────────


class TrajectoryEngineTests(TestCase):
    def test_linear_projection_basic(self):
        """Basic linear projection with perfect data."""
        now = timezone.now()
        data_points = [
            (now - timedelta(days=10), 250.0),
            (now - timedelta(days=5), 255.0),
            (now, 260.0),
        ]
        result = calculate_linear_projection(data_points, 30, "lbs")
        self.assertIsNotNone(result)
        self.assertGreater(result.predicted_value, 260.0)
        self.assertGreater(result.confidence_score, 0.0)
        self.assertEqual(result.data_point_count, 3)

    def test_insufficient_data(self):
        """One data point should return None."""
        now = timezone.now()
        result = calculate_linear_projection([(now, 250.0)], 30, "lbs")
        self.assertIsNone(result)

    def test_decreasing_trend(self):
        """Decreasing values project lower."""
        now = timezone.now()
        data_points = [
            (now - timedelta(days=20), 260.0),
            (now - timedelta(days=10), 255.0),
            (now, 250.0),
        ]
        result = calculate_linear_projection(data_points, 30, "lbs")
        self.assertIsNotNone(result)
        self.assertLess(result.predicted_value, 250.0)

    def test_flat_trend(self):
        """Flat values project same value."""
        now = timezone.now()
        data_points = [
            (now - timedelta(days=20), 200.0),
            (now - timedelta(days=10), 200.0),
            (now, 200.0),
        ]
        result = calculate_linear_projection(data_points, 30, "lbs")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.predicted_value, 200.0, places=0)

    def test_many_points_higher_confidence(self):
        """More data points should yield higher confidence."""
        now = timezone.now()
        few_points = [
            (now - timedelta(days=5), 250.0),
            (now, 255.0),
        ]
        many_points = [
            (now - timedelta(days=i), 250.0 + i * 0.5)
            for i in range(20, -1, -1)
        ]
        result_few = calculate_linear_projection(few_points, 30, "lbs")
        result_many = calculate_linear_projection(many_points, 30, "lbs")
        self.assertGreater(result_many.confidence_score, result_few.confidence_score)


# ─── Confidence Engine Tests ─────────────────────────────────


class ConfidenceEngineTests(TestCase):
    def test_high_confidence(self):
        """Many points, high R², good history, short projection."""
        score = compute_confidence(
            data_point_count=25, r_squared=0.95,
            days_of_history=90, days_forward=30,
        )
        self.assertGreaterEqual(score, 0.75)

    def test_low_confidence(self):
        """Few points, low R², far projection."""
        score = compute_confidence(
            data_point_count=2, r_squared=0.2,
            days_of_history=5, days_forward=120,
        )
        self.assertLess(score, 0.40)

    def test_medium_confidence(self):
        """Moderate data quality."""
        score = compute_confidence(
            data_point_count=8, r_squared=0.7,
            days_of_history=30, days_forward=30,
        )
        self.assertGreater(score, 0.40)
        self.assertLess(score, 0.85)

    def test_confidence_label_high(self):
        self.assertEqual(confidence_label(0.80), "high")

    def test_confidence_label_medium(self):
        self.assertEqual(confidence_label(0.55), "medium")

    def test_confidence_label_low(self):
        self.assertEqual(confidence_label(0.35), "low")

    def test_confidence_label_very_low(self):
        self.assertEqual(confidence_label(0.15), "very low")


# ─── Model Tests ─────────────────────────────────────────────


class PredictionModelTests(TestCase):
    def test_create_prediction(self):
        user = _create_test_user()
        pred = Prediction.objects.create(
            user=user,
            prediction_type="weight_30d",
            module="health",
            predicted_value=275.5,
            predicted_date=timezone.now() + timedelta(days=30),
            confidence_score=0.72,
            explanation="Test prediction",
            evidence={"test": True},
            dedupe_key="test-key-123",
        )
        self.assertEqual(pred.status, "active")
        self.assertEqual(pred.predicted_value, 275.5)
        self.assertIn("275.5", str(pred))

    def test_dedupe_key_generation(self):
        key1 = build_prediction_dedupe_key(1, "weight_30d", "2026-03-15")
        key2 = build_prediction_dedupe_key(1, "weight_30d", "2026-03-15")
        key3 = build_prediction_dedupe_key(1, "weight_60d", "2026-03-15")
        self.assertEqual(key1, key2)
        self.assertNotEqual(key1, key3)
        self.assertEqual(len(key1), 64)


# ─── Prediction Engine Tests ────────────────────────────────


class PredictionEngineTests(TestCase):
    def test_upsert_creates_new(self):
        user = _create_test_user()
        pred_data = {
            "prediction_type": "weight_30d",
            "module": "health",
            "predicted_value": 270.0,
            "predicted_date": timezone.now() + timedelta(days=30),
            "confidence_score": 0.65,
            "explanation": "Test",
            "evidence": {},
            "dedupe_key": "test-upsert-1",
        }
        pred = _upsert_prediction(user, pred_data)
        self.assertIsNotNone(pred)
        self.assertEqual(pred.status, "active")

    def test_upsert_supersedes_old(self):
        user = _create_test_user()
        pred_data = {
            "prediction_type": "weight_30d",
            "module": "health",
            "predicted_value": 270.0,
            "predicted_date": timezone.now() + timedelta(days=30),
            "confidence_score": 0.65,
            "explanation": "First prediction",
            "evidence": {},
            "dedupe_key": "test-supersede-1",
        }
        first = _upsert_prediction(user, pred_data)
        self.assertEqual(first.status, "active")

        pred_data["predicted_value"] = 268.0
        pred_data["explanation"] = "Updated prediction"
        second = _upsert_prediction(user, pred_data)

        first.refresh_from_db()
        self.assertEqual(first.status, "superseded")
        self.assertEqual(second.status, "active")
        self.assertEqual(second.predicted_value, 268.0)


# ─── Weight Projection Rule Tests ───────────────────────────


class WeightProjectionRuleTests(TestCase):
    def test_weight_projection_sufficient_data(self):
        """Weight projection with enough data points."""
        user = _create_test_user()
        from apps.health.models import WeightEntry

        now = timezone.now()
        # Create 10 weight entries over 30 days, trending up
        for i in range(10):
            WeightEntry.objects.create(
                user=user,
                value=250 + i * 0.5,
                recorded_at=now - timedelta(days=30 - i * 3),
            )

        # Import and run the rule
        from apps.core.ai_predictions.prediction_rules_health import (
            WeightProjectionRule,
        )

        rule = WeightProjectionRule()
        event = {"module": "health"}
        self.assertTrue(rule.applies(user, event))

        predictions = rule.predict(user, event)
        self.assertGreater(len(predictions), 0)

        # Should have predictions for 30, 60, 90 days
        pred_types = [p["prediction_type"] for p in predictions]
        self.assertIn("weight_30d", pred_types)
        self.assertIn("weight_60d", pred_types)
        self.assertIn("weight_90d", pred_types)

        # All should have required fields
        for pred in predictions:
            self.assertIn("predicted_value", pred)
            self.assertIn("confidence_score", pred)
            self.assertIn("explanation", pred)
            self.assertIn("evidence", pred)
            self.assertIn("dedupe_key", pred)
            self.assertGreater(pred["predicted_value"], 250)

    def test_weight_projection_insufficient_data(self):
        """Weight projection with too few data points returns nothing."""
        user = _create_test_user()
        from apps.health.models import WeightEntry

        WeightEntry.objects.create(
            user=user, value=250, recorded_at=timezone.now(),
        )

        from apps.core.ai_predictions.prediction_rules_health import (
            WeightProjectionRule,
        )

        rule = WeightProjectionRule()
        predictions = rule.predict(user, {"module": "health"})
        self.assertEqual(len(predictions), 0)


# ─── Habit Continuation Rule Tests ──────────────────────────


class HabitContinuationRuleTests(TestCase):
    def test_habit_continuation_active_habit(self):
        """Habit continuation prediction for active habit with entries."""
        user = _create_test_user()
        from apps.purpose.models import HabitGoal, HabitEntry

        now = timezone.now()
        habit = HabitGoal.objects.create(
            user=user,
            name="Test Habit",
            purpose="Testing",
            start_date=(now - timedelta(days=30)).date(),
            end_date=(now + timedelta(days=60)).date(),
            measurement_type="binary",
            frequency_type="daily",
        )

        # Create 20 completed entries over 28 days
        for i in range(20):
            HabitEntry.objects.create(
                goal=habit,
                date=(now - timedelta(days=i)).date(),
                completed=True,
            )

        from apps.core.ai_predictions.prediction_rules_habits import (
            HabitContinuationRule,
        )

        rule = HabitContinuationRule()
        event = {"module": "habits"}
        self.assertTrue(rule.applies(user, event))

        predictions = rule.predict(user, event)
        self.assertEqual(len(predictions), 1)

        pred = predictions[0]
        self.assertGreater(pred["predicted_value"], 0.5)  # High continuation
        self.assertIn("continuation", pred["explanation"].lower())

    def test_habit_continuation_insufficient_data(self):
        """Habit with too few entries returns no prediction."""
        user = _create_test_user()
        from apps.purpose.models import HabitGoal, HabitEntry

        now = timezone.now()
        habit = HabitGoal.objects.create(
            user=user,
            name="New Habit",
            purpose="Testing",
            start_date=(now - timedelta(days=2)).date(),
            end_date=(now + timedelta(days=60)).date(),
            measurement_type="binary",
            frequency_type="daily",
        )
        # No entries at all — below minimum of 1
        from apps.core.ai_predictions.prediction_rules_habits import (
            HabitContinuationRule,
        )

        rule = HabitContinuationRule()
        predictions = rule.predict(user, {"module": "habits"})
        self.assertEqual(len(predictions), 0)


# ─── Integration Tests ──────────────────────────────────────


class PredictionIntegrationTests(TestCase):
    def test_generate_predictions_with_data(self):
        """generate_predictions should create predictions when data exists."""
        user = _create_test_user()
        from apps.health.models import WeightEntry

        now = timezone.now()
        for i in range(10):
            WeightEntry.objects.create(
                user=user,
                value=250 + i * 0.5,
                recorded_at=now - timedelta(days=30 - i * 3),
            )

        # Import rule modules to register them
        import apps.core.ai_predictions.prediction_rules_health  # noqa: F401

        predictions = generate_predictions(user, module="health")
        self.assertGreater(len(predictions), 0)

        # All stored as Prediction objects
        stored = Prediction.objects.filter(user=user, status="active")
        self.assertGreater(stored.count(), 0)

    def test_generate_predictions_no_data(self):
        """generate_predictions with no data should return empty."""
        user = _create_test_user("nodata@test.com")

        import apps.core.ai_predictions.prediction_rules_health  # noqa: F401

        predictions = generate_predictions(user, module="health")
        self.assertEqual(len(predictions), 0)


# ─── Registry Tests ─────────────────────────────────────────


class PredictionRegistryTests(TestCase):
    def test_rules_registered(self):
        """All rule modules should register their rules."""
        # Import all rule modules
        import apps.core.ai_predictions.prediction_rules_health  # noqa: F401
        import apps.core.ai_predictions.prediction_rules_bodycomp  # noqa: F401
        import apps.core.ai_predictions.prediction_rules_goals  # noqa: F401
        import apps.core.ai_predictions.prediction_rules_habits  # noqa: F401
        import apps.core.ai_predictions.prediction_rules_labs  # noqa: F401

        from apps.core.ai_predictions.prediction_registry import (
            get_prediction_rules,
        )

        rules = get_prediction_rules()
        rule_names = [r.rule_name for r in rules]
        self.assertIn("weight_projection", rule_names)
        self.assertIn("body_fat_projection", rule_names)
        self.assertIn("lean_mass_projection", rule_names)
        self.assertIn("goal_completion_date", rule_names)
        self.assertIn("habit_continuation", rule_names)
        self.assertIn("lab_marker_trend", rule_names)
