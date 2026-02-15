"""
PGE -- Guidance Rules.

Structured rules that evaluate SAE state, PIE insights, and PRIE predictions
to produce guidance candidates. Rules are modular and extensible.

Each rule must implement:
    - rule_name: str
    - evaluate(user, state, insights, predictions) -> list[dict]

Returned dicts must contain:
    title, message, priority, guidance_type, source, module,
    confidence_score (if predictive), evidence, dedupe_key
"""

import logging

from apps.core.ai_guidance.guidance_registry import register_guidance
from apps.core.ai_guidance.models import build_guidance_dedupe_key

logger = logging.getLogger(__name__)


class BaseGuidanceRule:
    """Base class for guidance rules."""

    rule_name = ""
    module = ""

    def evaluate(self, user, state, insights, predictions):
        """
        Evaluate this rule and return guidance candidates.

        Args:
            user: Django user instance.
            state: Dict from SAE get_user_state().
            insights: QuerySet of recent Insight objects.
            predictions: QuerySet of recent Prediction objects.

        Returns:
            List of guidance candidate dicts.
        """
        raise NotImplementedError


@register_guidance
class GoalRiskRule(BaseGuidanceRule):
    """Surface guidance when a goal is at risk of missing its deadline."""

    rule_name = "goal_risk"
    module = "goals"

    def evaluate(self, user, state, insights, predictions):
        results = []
        goal_state = state.get("goals", {})

        # Check for overdue goals
        overdue = goal_state.get("overdue_goal_count", 0)
        if overdue > 0:
            results.append({
                "title": f"You have {overdue} overdue goal{'s' if overdue > 1 else ''}",
                "message": (
                    f"{overdue} goal{'s are' if overdue > 1 else ' is'} past the target date. "
                    "Consider updating the deadline or marking progress."
                ),
                "priority": 2,
                "guidance_type": self.rule_name,
                "source": "sae_state",
                "module": self.module,
                "evidence": {"overdue_count": overdue},
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "goal_overdue", str(overdue)
                ),
            })

        # Check PRIE predictions for goals behind schedule
        goal_predictions = predictions.filter(
            module="goals", status="active"
        )
        for pred in goal_predictions:
            evidence = pred.evidence or {}
            if evidence.get("behind_schedule"):
                results.append({
                    "title": "You are projected to miss your goal deadline",
                    "message": pred.explanation,
                    "priority": 2,
                    "guidance_type": self.rule_name,
                    "source": "prie_prediction",
                    "module": self.module,
                    "confidence_score": pred.confidence_score,
                    "evidence": pred.evidence,
                    "dedupe_key": build_guidance_dedupe_key(
                        user.id, "goal_risk_pred", str(pred.id)
                    ),
                })

        return results


@register_guidance
class HabitInactivityRule(BaseGuidanceRule):
    """Surface guidance when habits show inactivity."""

    rule_name = "habit_inactivity"
    module = "habits"

    def evaluate(self, user, state, insights, predictions):
        results = []

        # Check PIE insights for broken streaks
        habit_insights = insights.filter(
            module="habits", severity="warning"
        ).exclude(status="dismissed")

        for insight in habit_insights[:2]:  # Limit to avoid flooding
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
                    user.id, "habit_warning", str(insight.id)
                ),
            })

        return results


@register_guidance
class HealthTrendRule(BaseGuidanceRule):
    """Surface guidance for health trends (positive and negative)."""

    rule_name = "health_trend"
    module = "health"

    def evaluate(self, user, state, insights, predictions):
        results = []

        # Check PIE insights for health trends
        health_insights = insights.filter(module="health").exclude(
            status="dismissed"
        )

        for insight in health_insights[:3]:
            priority = 3
            if insight.severity == "warning":
                priority = 2
            elif insight.severity == "positive":
                priority = 4

            results.append({
                "title": insight.title,
                "message": insight.message,
                "priority": priority,
                "guidance_type": self.rule_name,
                "source": "pie_insight",
                "module": self.module,
                "confidence_score": insight.confidence_score,
                "evidence": insight.evidence,
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "health_trend", str(insight.id)
                ),
            })

        # Check PRIE predictions for health projections
        health_predictions = predictions.filter(
            module="health", status="active"
        )
        for pred in health_predictions[:2]:
            results.append({
                "title": f"Health projection: {pred.prediction_type}",
                "message": pred.explanation,
                "priority": 3,
                "guidance_type": self.rule_name,
                "source": "prie_prediction",
                "module": self.module,
                "confidence_score": pred.confidence_score,
                "evidence": pred.evidence,
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "health_pred", str(pred.id)
                ),
            })

        return results


@register_guidance
class JournalInactivityRule(BaseGuidanceRule):
    """Surface guidance when journaling drops off."""

    rule_name = "journal_inactivity"
    module = "journal"

    def evaluate(self, user, state, insights, predictions):
        results = []

        journal_state = state.get("journal", {})
        entry_count_30d = journal_state.get("entry_count_30d", 0)

        # Check if user was journaling but stopped
        journal_insights = insights.filter(
            module="journal", insight_type="journal_drop_off"
        ).exclude(status="dismissed")

        for insight in journal_insights[:1]:
            results.append({
                "title": insight.title,
                "message": insight.message,
                "priority": 4,
                "guidance_type": self.rule_name,
                "source": "pie_insight",
                "module": self.module,
                "confidence_score": insight.confidence_score,
                "evidence": insight.evidence,
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "journal_inactivity", str(insight.id)
                ),
            })

        # If no entries in 30 days and no insight, use SAE state
        if entry_count_30d == 0 and not journal_insights.exists():
            results.append({
                "title": "You haven't journaled recently",
                "message": "No journal entries in the past 30 days. "
                           "Journaling can help with reflection and mindfulness.",
                "priority": 5,
                "guidance_type": self.rule_name,
                "source": "sae_state",
                "module": self.module,
                "evidence": {"entry_count_30d": 0},
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "journal_zero_30d"
                ),
            })

        return results


@register_guidance
class PositiveReinforcementRule(BaseGuidanceRule):
    """Surface positive reinforcement for good trends."""

    rule_name = "positive_reinforcement"
    module = ""

    def evaluate(self, user, state, insights, predictions):
        results = []

        # Find positive insights across all modules
        positive_insights = insights.filter(
            severity="positive"
        ).exclude(status="dismissed")[:2]

        for insight in positive_insights:
            results.append({
                "title": insight.title,
                "message": insight.message,
                "priority": 4,
                "guidance_type": self.rule_name,
                "source": "pie_insight",
                "module": insight.module,
                "confidence_score": insight.confidence_score,
                "evidence": insight.evidence,
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "positive", str(insight.id)
                ),
            })

        return results
