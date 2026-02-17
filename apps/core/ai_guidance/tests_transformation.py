"""
PGE Transformation Guidance Rule Tests.

All 4 rules tested with SAE state dict + mock PIE insights + mock PRIE predictions.
Validates cognitive pipeline: PGE consumes SAE + PIE + PRIE outputs.
"""

from unittest.mock import MagicMock, PropertyMock

from django.conf import settings
from django.test import TestCase

from apps.core.ai_guidance.guidance_rules_transformation import (
    FastingOptimizationRule,
    ProteinAdjustmentRule,
    TransformationCoachingRule,
    WorkoutFrequencyAdjustmentRule,
)
from apps.users.models import TermsAcceptance, User


def _create_test_user(email="pge_transform@example.com"):
    user = User.objects.create_user(email=email, password="testpass123")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


def _mock_empty_qs():
    """Create a mock queryset that returns empty on filter/exclude."""
    qs = MagicMock()
    qs.filter.return_value = qs
    qs.exclude.return_value = qs
    qs.exists.return_value = False
    qs.__iter__ = MagicMock(return_value=iter([]))
    qs.__getitem__ = MagicMock(return_value=[])
    return qs


def _mock_prediction(pred_type="transformation_success_90d", value=0.35,
                     confidence=0.7, evidence=None, pred_id=1):
    pred = MagicMock()
    pred.prediction_type = pred_type
    pred.predicted_value = value
    pred.confidence_score = confidence
    pred.evidence = evidence or {"outlook": "at risk"}
    pred.id = pred_id
    pred.status = "active"
    return pred


def _mock_insight(insight_type="protein_deficit", severity="warning",
                  confidence=0.82, evidence=None, title="", message="", insight_id=1):
    insight = MagicMock()
    insight.insight_type = insight_type
    insight.severity = severity
    insight.confidence_score = confidence
    insight.evidence = evidence or {"deficit_g": 30}
    insight.title = title or f"Mock {insight_type}"
    insight.message = message or "Mock insight message"
    insight.id = insight_id
    insight.status = "active"
    return insight


# ── TransformationCoachingRule ─────────────────────────────────


class TestTransformationCoachingRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("pge_coaching@example.com")
        self.rule = TransformationCoachingRule()

    def test_no_guidance_without_transformation_score(self):
        state = {"transformation": {}}
        insights = _mock_empty_qs()
        predictions = _mock_empty_qs()

        results = self.rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 0)

    def test_guidance_from_low_prie_prediction(self):
        """PGE uses PRIE prediction for coaching guidance."""
        state = {"transformation": {"transformation_score": 35, "momentum_score": 40}}

        insights = _mock_empty_qs()

        pred = _mock_prediction(value=0.35, evidence={"outlook": "at risk"})
        pred_qs = MagicMock()
        pred_qs.filter.return_value = pred_qs
        pred_qs.__iter__ = MagicMock(return_value=iter([pred]))
        pred_qs.__getitem__ = MagicMock(side_effect=lambda s: [pred][s] if isinstance(s, slice) else pred)

        results = self.rule.evaluate(self.user, state, insights, pred_qs)
        # Should produce guidance from PRIE prediction
        has_prie_guidance = any(r.get("source") == "prie_prediction" for r in results)
        self.assertTrue(has_prie_guidance or len(results) > 0)

    def test_guidance_for_weak_areas_from_sae(self):
        """PGE uses SAE state to identify weak areas."""
        state = {
            "transformation": {
                "transformation_score": 45,
                "momentum_score": 40,
                "nutrition_score": 30,
                "workout_score": 35,
                "recovery_score": 20,
                "fasting_score": 50,
            }
        }
        insights = _mock_empty_qs()
        predictions = _mock_empty_qs()

        results = self.rule.evaluate(self.user, state, insights, predictions)
        # Should identify weak areas from SAE state
        has_sae_guidance = any(r.get("source") == "sae_state" for r in results)
        self.assertTrue(has_sae_guidance, f"Expected SAE-sourced guidance, got: {results}")

    def test_guidance_priority(self):
        state = {
            "transformation": {
                "transformation_score": 45,
                "momentum_score": 40,
                "nutrition_score": 30,
                "workout_score": 35,
            }
        }
        insights = _mock_empty_qs()
        predictions = _mock_empty_qs()

        results = self.rule.evaluate(self.user, state, insights, predictions)
        for r in results:
            self.assertIn("priority", r)
            self.assertGreaterEqual(r["priority"], 1)
            self.assertLessEqual(r["priority"], 5)


# ── ProteinAdjustmentRule ──────────────────────────────────────


class TestProteinAdjustmentRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("pge_protein@example.com")
        self.rule = ProteinAdjustmentRule()

    def test_no_guidance_without_protein_insights(self):
        state = {"nutrition": {"rolling_7d_protein_avg": 120, "protein_target": 150}}
        insights = _mock_empty_qs()
        predictions = _mock_empty_qs()

        results = self.rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 0)

    def test_guidance_from_pie_protein_deficit(self):
        """PGE uses PIE protein deficit insight for guidance."""
        state = {
            "nutrition": {
                "rolling_7d_protein_avg": 90,
                "protein_target": 150,
                "protein_compliance_pct": 60,
            }
        }

        insight = _mock_insight(
            insight_type="protein_deficit",
            evidence={"deficit_g": 60, "compliance_pct": 60},
        )
        insight_qs = MagicMock()
        insight_qs.filter.return_value = insight_qs
        insight_qs.exclude.return_value = insight_qs
        insight_qs.exists.return_value = True
        insight_qs.__iter__ = MagicMock(return_value=iter([insight]))
        insight_qs.__getitem__ = MagicMock(
            side_effect=lambda s: [insight][s] if isinstance(s, slice) else insight
        )

        predictions = _mock_empty_qs()
        results = self.rule.evaluate(self.user, state, insight_qs, predictions)

        has_pie_guidance = any(r.get("source") == "pie_insight" for r in results)
        self.assertTrue(has_pie_guidance, f"Expected PIE-sourced guidance, got: {results}")

    def test_guidance_has_required_fields(self):
        state = {"nutrition": {"rolling_7d_protein_avg": 90, "protein_target": 150}}

        insight = _mock_insight(insight_type="protein_deficit", evidence={"deficit_g": 60})
        insight_qs = MagicMock()
        insight_qs.filter.return_value = insight_qs
        insight_qs.exclude.return_value = insight_qs
        insight_qs.exists.return_value = True
        insight_qs.__iter__ = MagicMock(return_value=iter([insight]))
        insight_qs.__getitem__ = MagicMock(
            side_effect=lambda s: [insight][s] if isinstance(s, slice) else insight
        )

        predictions = _mock_empty_qs()
        results = self.rule.evaluate(self.user, state, insight_qs, predictions)

        for r in results:
            self.assertIn("title", r)
            self.assertIn("message", r)
            self.assertIn("priority", r)
            self.assertIn("guidance_type", r)
            self.assertIn("dedupe_key", r)


# ── WorkoutFrequencyAdjustmentRule ─────────────────────────────


class TestWorkoutFrequencyAdjustmentRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("pge_workout@example.com")
        self.rule = WorkoutFrequencyAdjustmentRule()

    def test_no_guidance_empty_state(self):
        state = {"fitness": {}}
        insights = _mock_empty_qs()
        predictions = _mock_empty_qs()

        results = self.rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 0)

    def test_rest_day_guidance_high_frequency(self):
        """PGE recommends rest when SAE shows high workout frequency."""
        state = {"fitness": {"workouts_7d": 6, "workouts_30d": 20}}
        insights = _mock_empty_qs()
        predictions = _mock_empty_qs()

        results = self.rule.evaluate(self.user, state, insights, predictions)
        has_rest_guidance = any("rest" in r.get("title", "").lower() for r in results)
        self.assertTrue(has_rest_guidance, f"Expected rest guidance, got: {results}")

    def test_guidance_from_pie_plateau_insight(self):
        """PGE uses PIE strength plateau insight for guidance."""
        state = {"fitness": {"workouts_7d": 4, "workouts_30d": 16}}

        insight = _mock_insight(
            insight_type="strength_plateau",
            evidence={"workouts_30d": 16, "prs_30d": 0},
        )
        insight_qs = MagicMock()
        insight_qs.filter.return_value = insight_qs
        insight_qs.exclude.return_value = insight_qs
        insight_qs.__iter__ = MagicMock(return_value=iter([insight]))
        insight_qs.__getitem__ = MagicMock(
            side_effect=lambda s: [insight][s] if isinstance(s, slice) else insight
        )

        predictions = _mock_empty_qs()
        results = self.rule.evaluate(self.user, state, insight_qs, predictions)

        has_pie_guidance = any(r.get("source") == "pie_insight" for r in results)
        self.assertTrue(has_pie_guidance, f"Expected PIE-sourced guidance, got: {results}")


# ── FastingOptimizationRule ────────────────────────────────────


class TestFastingOptimizationRule(TestCase):
    def setUp(self):
        self.user = _create_test_user("pge_fasting@example.com")
        self.rule = FastingOptimizationRule()

    def test_no_guidance_empty_state(self):
        state = {"fasting": {}}
        insights = _mock_empty_qs()
        predictions = _mock_empty_qs()

        results = self.rule.evaluate(self.user, state, insights, predictions)
        self.assertEqual(len(results), 0)

    def test_extend_fasting_guidance_short_duration(self):
        """PGE recommends extending when SAE shows short fasting windows."""
        state = {
            "fasting": {
                "rolling_7d_avg_fast_duration": 12,
                "fasts_7d": 5,
                "fasting_compliance_score": 70,
            }
        }
        insights = _mock_empty_qs()
        predictions = _mock_empty_qs()

        results = self.rule.evaluate(self.user, state, insights, predictions)
        has_extend_guidance = any(
            "extend" in r.get("title", "").lower() for r in results
        )
        self.assertTrue(has_extend_guidance, f"Expected extend guidance, got: {results}")

    def test_no_extend_guidance_adequate_duration(self):
        """Don't suggest extending if fasts are already 16+ hours."""
        state = {
            "fasting": {
                "rolling_7d_avg_fast_duration": 17,
                "fasts_7d": 5,
            }
        }
        insights = _mock_empty_qs()
        predictions = _mock_empty_qs()

        results = self.rule.evaluate(self.user, state, insights, predictions)
        has_extend_guidance = any(
            "extend" in r.get("title", "").lower() for r in results
        )
        self.assertFalse(has_extend_guidance)
