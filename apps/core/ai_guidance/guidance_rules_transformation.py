"""
PGE — Transformation Guidance Rules.

Rules that evaluate SAE state, PIE insights, and PRIE predictions
to produce transformation-specific guidance candidates.

Rules:
- TransformationCoachingRule: Overall transformation coaching
- ProteinAdjustmentRule: Protein intake adjustment recommendations
- WorkoutFrequencyAdjustmentRule: Workout frequency recommendations
- FastingOptimizationRule: Fasting schedule optimization
"""

import logging

from apps.core.ai_guidance.guidance_registry import register_guidance
from apps.core.ai_guidance.guidance_rules import BaseGuidanceRule
from apps.core.ai_guidance.models import build_guidance_dedupe_key

logger = logging.getLogger(__name__)


@register_guidance
class TransformationCoachingRule(BaseGuidanceRule):
    """Surface overall transformation coaching based on composite scores."""

    rule_name = "transformation_coaching"
    module = "health"

    def evaluate(self, user, state, insights, predictions):
        results = []

        transformation = state.get("transformation", {})
        score = transformation.get("transformation_score")

        if score is None:
            return results

        # Check PRIE transformation predictions
        transform_predictions = predictions.filter(
            prediction_type="transformation_success_90d",
            status="active",
        )
        for pred in transform_predictions[:1]:
            probability = pred.predicted_value
            outlook = (pred.evidence or {}).get("outlook", "unknown")

            if probability is not None and probability < 0.4:
                results.append({
                    "title": "Your transformation needs attention",
                    "message": (
                        f"Your 90-day transformation success probability is {probability:.0%} "
                        f"(outlook: {outlook}). Focus on consistency — hit your protein target, "
                        f"complete your scheduled workouts, and maintain your sleep. "
                        f"Small daily wins compound into big results."
                    ),
                    "priority": 2,
                    "guidance_type": self.rule_name,
                    "source": "prie_prediction",
                    "module": self.module,
                    "confidence_score": pred.confidence_score,
                    "evidence": pred.evidence,
                    "dedupe_key": build_guidance_dedupe_key(
                        user.id, "transform_coaching_low", str(pred.id)
                    ),
                })
            elif probability is not None and probability >= 0.7:
                results.append({
                    "title": "Transformation on track!",
                    "message": (
                        f"Your 90-day success probability is {probability:.0%}. "
                        f"You're maintaining strong consistency. Current score: {score}/100. "
                        f"Keep doing what you're doing!"
                    ),
                    "priority": 4,
                    "guidance_type": self.rule_name,
                    "source": "prie_prediction",
                    "module": self.module,
                    "confidence_score": pred.confidence_score,
                    "evidence": pred.evidence,
                    "dedupe_key": build_guidance_dedupe_key(
                        user.id, "transform_coaching_high", str(pred.id)
                    ),
                })

        # SAE state-based guidance for missing domains
        momentum = transformation.get("momentum_score", 0)
        if score > 0 and momentum < 60:
            # Identify weak areas
            weak_areas = []
            if transformation.get("nutrition_score", 0) < 40:
                weak_areas.append("nutrition tracking")
            if transformation.get("workout_score", 0) < 40:
                weak_areas.append("workout consistency")
            if transformation.get("recovery_score", 0) < 40:
                weak_areas.append("sleep/recovery")
            if transformation.get("fasting_score", 0) < 40:
                weak_areas.append("fasting consistency")

            if weak_areas:
                results.append({
                    "title": f"Focus areas: {', '.join(weak_areas[:2])}",
                    "message": (
                        f"Your transformation momentum is {momentum}/100. "
                        f"Improving in {', '.join(weak_areas)} would have the biggest "
                        f"impact on your progress."
                    ),
                    "priority": 3,
                    "guidance_type": self.rule_name,
                    "source": "sae_state",
                    "module": self.module,
                    "evidence": {
                        "transformation_score": score,
                        "momentum_score": momentum,
                        "weak_areas": weak_areas,
                    },
                    "dedupe_key": build_guidance_dedupe_key(
                        user.id, "transform_focus", str(momentum)
                    ),
                })

        return results


@register_guidance
class ProteinAdjustmentRule(BaseGuidanceRule):
    """Surface protein intake adjustment recommendations."""

    rule_name = "protein_adjustment"
    module = "health"

    def evaluate(self, user, state, insights, predictions):
        results = []

        nutrition = state.get("nutrition", {})
        protein_compliance = nutrition.get("protein_compliance_pct")
        protein_target = nutrition.get("protein_target")
        rolling_protein = nutrition.get("rolling_7d_protein_avg")

        # Check PIE protein deficit insights
        protein_insights = insights.filter(
            insight_type="protein_deficit",
        ).exclude(status="dismissed")

        for insight in protein_insights[:1]:
            deficit_g = (insight.evidence or {}).get("deficit_g", 0)
            results.append({
                "title": "Increase your protein intake",
                "message": (
                    f"You're averaging {rolling_protein:.0f}g protein/day, "
                    f"which is {deficit_g:.0f}g below your target. Try adding a "
                    f"protein shake, Greek yogurt, or lean meat to close this gap. "
                    f"Protein is critical for muscle preservation during transformation."
                ),
                "priority": 2,
                "guidance_type": self.rule_name,
                "source": "pie_insight",
                "module": self.module,
                "confidence_score": insight.confidence_score,
                "evidence": insight.evidence,
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "protein_adjust", str(insight.id)
                ),
            })

        # SAE-based: protein over target (rare but possible)
        if protein_compliance and protein_compliance > 150 and not protein_insights.exists():
            results.append({
                "title": "Protein intake well above target",
                "message": (
                    f"You're consuming {protein_compliance:.0f}% of your protein target. "
                    f"While adequate protein is important, excessive intake beyond your "
                    f"needs doesn't provide additional muscle-building benefits."
                ),
                "priority": 5,
                "guidance_type": self.rule_name,
                "source": "sae_state",
                "module": self.module,
                "evidence": {
                    "protein_compliance_pct": protein_compliance,
                    "protein_target": protein_target,
                    "rolling_7d_avg": rolling_protein,
                },
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "protein_over"
                ),
            })

        return results


@register_guidance
class WorkoutFrequencyAdjustmentRule(BaseGuidanceRule):
    """Surface workout frequency adjustment recommendations."""

    rule_name = "workout_frequency_adjustment"
    module = "health"

    def evaluate(self, user, state, insights, predictions):
        results = []

        fitness = state.get("fitness", {})
        workouts_7d = fitness.get("workouts_7d", 0)
        workouts_30d = fitness.get("workouts_30d", 0)
        last_workout = fitness.get("last_workout_date")

        # Check PIE workout consistency insights
        workout_insights = insights.filter(
            insight_type__in=("workout_consistency", "strength_plateau"),
        ).exclude(status="dismissed")

        for insight in workout_insights[:1]:
            if insight.insight_type == "strength_plateau":
                results.append({
                    "title": "Consider adjusting your program",
                    "message": (
                        "You've been training consistently but haven't set new PRs. "
                        "Try increasing weight by 5%, adding an extra set, or "
                        "switching to a different exercise variation to break "
                        "through the plateau."
                    ),
                    "priority": 3,
                    "guidance_type": self.rule_name,
                    "source": "pie_insight",
                    "module": self.module,
                    "confidence_score": insight.confidence_score,
                    "evidence": insight.evidence,
                    "dedupe_key": build_guidance_dedupe_key(
                        user.id, "workout_plateau", str(insight.id)
                    ),
                })
            else:
                results.append({
                    "title": insight.title,
                    "message": insight.message,
                    "priority": 3,
                    "guidance_type": self.rule_name,
                    "source": "pie_insight",
                    "module": self.module,
                    "confidence_score": insight.confidence_score,
                    "evidence": insight.evidence,
                    "dedupe_key": build_guidance_dedupe_key(
                        user.id, "workout_freq", str(insight.id)
                    ),
                })

        # SAE-based: recommend rest day if high frequency
        if workouts_7d >= 6:
            results.append({
                "title": "Consider a rest day",
                "message": (
                    f"You've logged {workouts_7d} workouts this week. "
                    f"Recovery is when muscle growth happens. Make sure you're "
                    f"getting at least one full rest day per week."
                ),
                "priority": 4,
                "guidance_type": self.rule_name,
                "source": "sae_state",
                "module": self.module,
                "evidence": {
                    "workouts_7d": workouts_7d,
                    "workouts_30d": workouts_30d,
                },
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "workout_rest"
                ),
            })

        return results


@register_guidance
class FastingOptimizationRule(BaseGuidanceRule):
    """Surface fasting schedule optimization recommendations."""

    rule_name = "fasting_optimization"
    module = "health"

    def evaluate(self, user, state, insights, predictions):
        results = []

        fasting = state.get("fasting", {})
        fasts_7d = fasting.get("fasts_7d", 0)
        compliance = fasting.get("fasting_compliance_score")
        avg_duration = fasting.get("rolling_7d_avg_fast_duration")

        # Check PIE fasting insights
        fasting_insights = insights.filter(
            insight_type__startswith="fasting_consistency",
        ).exclude(status="dismissed")

        for insight in fasting_insights[:1]:
            if insight.severity == "positive":
                # Don't generate guidance for positive fasting insights —
                # let PositiveReinforcementRule handle those
                continue

            results.append({
                "title": "Get back to your fasting routine",
                "message": (
                    "Your fasting consistency has dropped. Start with a "
                    "comfortable fasting window (like 16:8) and build from there. "
                    "Consistency matters more than duration."
                ),
                "priority": 3,
                "guidance_type": self.rule_name,
                "source": "pie_insight",
                "module": self.module,
                "confidence_score": insight.confidence_score,
                "evidence": insight.evidence,
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "fasting_opt", str(insight.id)
                ),
            })

        # SAE-based: short average fasts
        if avg_duration and avg_duration < 14 and fasts_7d > 0 and not fasting_insights.exists():
            results.append({
                "title": "Consider extending your fasting window",
                "message": (
                    f"Your average fasting duration is {avg_duration:.1f} hours. "
                    f"Many benefits of intermittent fasting increase with "
                    f"slightly longer windows (16-18 hours). Gradually extend "
                    f"by 30-60 minutes per week."
                ),
                "priority": 4,
                "guidance_type": self.rule_name,
                "source": "sae_state",
                "module": self.module,
                "evidence": {
                    "avg_fast_duration": avg_duration,
                    "fasts_7d": fasts_7d,
                    "compliance_score": compliance,
                },
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "fasting_extend"
                ),
            })

        return results
