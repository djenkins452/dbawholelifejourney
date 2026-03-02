"""
PGE — Meal Intelligence Guidance Rules.

Rules that evaluate SAE state, PIE insights, and PRIE predictions
to produce meal-specific guidance candidates.

Rules:
- DinnerSuggestionGuidance: Suggest dinner when no plan exists
- PantryAlertGuidance: Alert about expiring pantry items
- MealPlanReminderGuidance: Remind to create weekly plan
"""

import logging

from apps.core.ai_guidance.guidance_registry import register_guidance
from apps.core.ai_guidance.guidance_rules import BaseGuidanceRule
from apps.core.ai_guidance.models import build_guidance_dedupe_key

logger = logging.getLogger(__name__)


@register_guidance
class DinnerSuggestionGuidance(BaseGuidanceRule):
    """Suggest dinner when no plan exists for today."""

    rule_name = "dinner_suggestion"
    module = "meals"

    def evaluate(self, user, state, insights, predictions):
        results = []

        meals_state = state.get("meals", {})
        today_plan = meals_state.get("today_meal_plan")
        has_dinner_planned = meals_state.get("has_dinner_planned", False)

        # If there's already a dinner plan, no guidance needed
        if has_dinner_planned:
            return results

        # Check PIE insights for nutrition gaps to make smarter suggestions
        nutrition_insights = insights.filter(
            insight_type="nutrition_gap",
        ).exclude(status="dismissed")

        gaps = []
        for insight in nutrition_insights[:1]:
            evidence = insight.evidence or {}
            gaps = evidence.get("gaps", [])

        # Check PRIE for pantry items running low (could suggest meals using them)
        grocery_predictions = predictions.filter(
            prediction_type__startswith="grocery_depletion_",
            status="active",
        )
        expiring_ingredients = []
        for pred in grocery_predictions[:3]:
            evidence = pred.evidence or {}
            days_left = evidence.get("days_until_empty", 999)
            if days_left <= 3:
                name = evidence.get("ingredient_name", "")
                if name:
                    expiring_ingredients.append(name)

        # Build contextual suggestion
        if gaps and expiring_ingredients:
            message = (
                f"No dinner planned for today. You have {', '.join(expiring_ingredients)} "
                f"that should be used soon, and your recent meals have been low in "
                f"{' and '.join(gaps)}. Try a {gaps[0]}-rich recipe using "
                f"{expiring_ingredients[0]}."
            )
            priority = 2
            source = "pie_insight"
        elif expiring_ingredients:
            message = (
                f"No dinner planned for today. Consider making something with "
                f"{', '.join(expiring_ingredients)} — these items need to be used soon."
            )
            priority = 3
            source = "prie_prediction"
        elif gaps:
            message = (
                f"No dinner planned for today. Your recent meals have been low in "
                f"{' and '.join(gaps)}. Focus on a {gaps[0]}-rich dinner tonight."
            )
            priority = 3
            source = "pie_insight"
        else:
            message = (
                "No dinner planned for today. Planning meals ahead of time "
                "helps with healthier eating and reduces food waste. "
                "Check your recipes for inspiration."
            )
            priority = 4
            source = "sae_state"

        results.append({
            "title": "Plan tonight's dinner",
            "message": message,
            "priority": priority,
            "guidance_type": self.rule_name,
            "source": source,
            "module": self.module,
            "evidence": {
                "has_dinner_planned": has_dinner_planned,
                "nutrition_gaps": gaps,
                "expiring_ingredients": expiring_ingredients,
            },
            "dedupe_key": build_guidance_dedupe_key(
                user.id, "dinner_suggest"
            ),
        })

        return results


@register_guidance
class PantryAlertGuidance(BaseGuidanceRule):
    """Alert about expiring pantry items with actionable suggestions."""

    rule_name = "pantry_alert"
    module = "meals"

    def evaluate(self, user, state, insights, predictions):
        results = []

        # Check PIE insights for pantry waste
        pantry_insights = insights.filter(
            insight_type__startswith="pantry_waste",
        ).exclude(status="dismissed")

        for insight in pantry_insights[:1]:
            evidence = insight.evidence or {}
            items = evidence.get("expired_items") or evidence.get("expiring_items", [])
            count = evidence.get("expired_count") or evidence.get("expiring_count", 0)

            if not items:
                continue

            if "expired" in insight.insight_type or evidence.get("expired_count"):
                results.append({
                    "title": f"Remove {count} expired pantry item{'s' if count != 1 else ''}",
                    "message": (
                        f"Your pantry has expired items: {', '.join(items[:3])}. "
                        f"Remove these to keep your inventory accurate and make room "
                        f"for fresh ingredients on your next grocery trip."
                    ),
                    "priority": 2,
                    "guidance_type": self.rule_name,
                    "source": "pie_insight",
                    "module": self.module,
                    "confidence_score": insight.confidence_score,
                    "evidence": insight.evidence,
                    "dedupe_key": build_guidance_dedupe_key(
                        user.id, "pantry_expired", str(insight.id)
                    ),
                })
            else:
                results.append({
                    "title": f"Use {', '.join(items[:2])} before they expire",
                    "message": (
                        f"{count} item{'s are' if count != 1 else ' is'} expiring soon: "
                        f"{', '.join(items[:3])}. Plan a meal around these ingredients "
                        f"to avoid waste."
                    ),
                    "priority": 3,
                    "guidance_type": self.rule_name,
                    "source": "pie_insight",
                    "module": self.module,
                    "confidence_score": insight.confidence_score,
                    "evidence": insight.evidence,
                    "dedupe_key": build_guidance_dedupe_key(
                        user.id, "pantry_expiring", str(insight.id)
                    ),
                })

        # Also check PRIE grocery depletion predictions for low-stock alerts
        depletion_predictions = predictions.filter(
            prediction_type__startswith="grocery_depletion_",
            status="active",
        )
        urgent_items = []
        for pred in depletion_predictions:
            evidence = pred.evidence or {}
            days_left = evidence.get("days_until_empty", 999)
            if days_left <= 3:
                name = evidence.get("ingredient_name", "")
                if name:
                    urgent_items.append(name)

        if urgent_items and not pantry_insights.exists():
            results.append({
                "title": f"Running low on {', '.join(urgent_items[:2])}",
                "message": (
                    f"Based on your usage patterns, you'll run out of "
                    f"{', '.join(urgent_items[:3])} within a few days. "
                    f"Add these to your next grocery run."
                ),
                "priority": 3,
                "guidance_type": self.rule_name,
                "source": "prie_prediction",
                "module": self.module,
                "evidence": {
                    "urgent_items": urgent_items,
                },
                "dedupe_key": build_guidance_dedupe_key(
                    user.id, "pantry_low_stock"
                ),
            })

        return results


@register_guidance
class MealPlanReminderGuidance(BaseGuidanceRule):
    """Remind user to create a weekly meal plan."""

    rule_name = "meal_plan_reminder"
    module = "meals"

    def evaluate(self, user, state, insights, predictions):
        results = []

        meals_state = state.get("meals", {})
        has_current_plan = meals_state.get("has_current_meal_plan", False)
        last_plan_age_days = meals_state.get("days_since_last_plan")

        # If user has a current plan, no reminder needed
        if has_current_plan:
            return results

        # Check PIE insights for meal frequency
        frequency_insights = insights.filter(
            insight_type="meal_frequency_low",
        ).exclude(status="dismissed")

        # Check PRIE for adherence prediction
        adherence_predictions = predictions.filter(
            prediction_type="meal_plan_adherence",
            status="active",
        )

        adherence = None
        outlook = None
        for pred in adherence_predictions[:1]:
            adherence = pred.predicted_value
            outlook = (pred.evidence or {}).get("outlook", "")

        # Determine message priority and content
        if frequency_insights.exists() and adherence is not None and adherence < 0.5:
            # Both low frequency and low adherence
            message = (
                f"You haven't created a meal plan recently, and past plans "
                f"had about {adherence:.0%} follow-through. Start with a "
                f"simpler 3-day plan focused on dinners only — smaller plans "
                f"are easier to stick with."
            )
            priority = 2
            source = "pie_insight"
            confidence = frequency_insights.first().confidence_score
        elif frequency_insights.exists():
            insight = frequency_insights.first()
            message = (
                "It's been a while since your last meal plan. Weekly meal "
                "planning helps reduce food waste, save money, and maintain "
                "better nutrition. Even a quick plan for the next few dinners "
                "makes a difference."
            )
            priority = 3
            source = "pie_insight"
            confidence = insight.confidence_score
        elif last_plan_age_days and last_plan_age_days > 14:
            message = (
                f"Your last meal plan was {last_plan_age_days} days ago. "
                f"Creating a new weekly plan helps you stay on track with "
                f"nutrition goals and make the most of what's in your pantry."
            )
            priority = 4
            source = "sae_state"
            confidence = None
        else:
            # No strong signal — skip
            return results

        result = {
            "title": "Time for a new meal plan",
            "message": message,
            "priority": priority,
            "guidance_type": self.rule_name,
            "source": source,
            "module": self.module,
            "evidence": {
                "has_current_plan": has_current_plan,
                "days_since_last_plan": last_plan_age_days,
                "adherence_prediction": float(adherence) if adherence else None,
                "adherence_outlook": outlook,
            },
            "dedupe_key": build_guidance_dedupe_key(
                user.id, "meal_plan_remind"
            ),
        }

        if confidence is not None:
            result["confidence_score"] = confidence

        results.append(result)

        return results
