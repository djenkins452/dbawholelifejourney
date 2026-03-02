"""
PRIE — Meal Intelligence prediction rules.

Predictions:
- GroceryNeedsProjection: Predict when staples will run out
- MealPlanAdherenceProjection: Predict meal plan completion rate
"""

from datetime import timedelta
from decimal import Decimal

from apps.core.ai_predictions.base_prediction_rule import BasePredictionRule
from apps.core.ai_predictions.confidence_engine import confidence_label
from apps.core.ai_predictions.models import build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_registry import register_prediction
from apps.core.time.system_clock import get_current_time


@register_prediction
class GroceryNeedsProjection(BasePredictionRule):
    """Predict when staple pantry items will run out based on consumption patterns."""

    rule_name = "grocery_needs_projection"
    module = "meals"
    prediction_type = "grocery_needs"
    min_confidence_to_store = 0.25

    LOOKBACK_DAYS = 30
    LOW_STOCK_THRESHOLD = Decimal("0.20")  # 20% of last confirmed quantity

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "meals")

    def predict(self, user, event):
        from apps.meals.models import Household, InventoryTransaction, PantryItem

        now = get_current_time()

        # Find households the user belongs to
        household_ids = list(
            Household.objects.filter(
                memberships__user=user
            ).values_list("id", flat=True)
        )
        if not household_ids:
            household_ids = list(
                Household.objects.filter(
                    primary_user=user
                ).values_list("id", flat=True)
            )
        if not household_ids:
            return []

        cutoff = now - timedelta(days=self.LOOKBACK_DAYS)

        # Get pantry items with recent consumption history
        pantry_items = PantryItem.objects.filter(
            household_id__in=household_ids,
            quantity__gt=0,
        ).select_related("ingredient")

        predictions = []

        for item in pantry_items:
            # Calculate consumption rate from inventory transactions
            transactions = InventoryTransaction.objects.filter(
                pantry_item=item,
                created_at__gte=cutoff,
                delta_quantity__lt=0,  # consumption events only
            )

            tx_count = transactions.count()
            if tx_count < 2:
                # Not enough consumption data to project
                continue

            # Total consumed in lookback period
            total_consumed = abs(
                sum(float(tx.delta_quantity) for tx in transactions)
            )
            if total_consumed <= 0:
                continue

            # Average daily consumption
            daily_rate = total_consumed / self.LOOKBACK_DAYS
            if daily_rate <= 0:
                continue

            # Project days until depletion
            current_qty = float(item.quantity)
            days_until_empty = current_qty / daily_rate

            # Confidence based on data quality
            if tx_count >= 10:
                confidence = 0.70
            elif tx_count >= 5:
                confidence = 0.50
            else:
                confidence = 0.35

            predicted_date = (now + timedelta(days=int(days_until_empty))).date()
            conf = confidence_label(confidence)

            pred_type = f"grocery_depletion_{item.ingredient.id}"
            date_str = predicted_date.strftime("%Y-%m-%d")
            dedupe_key = build_prediction_dedupe_key(user.id, pred_type, date_str)

            if days_until_empty <= 3:
                urgency = "needs restocking soon"
            elif days_until_empty <= 7:
                urgency = "will need restocking this week"
            else:
                urgency = f"should last about {int(days_until_empty)} more days"

            explanation = (
                f"{item.ingredient.canonical_name}: based on {tx_count} consumption "
                f"events over {self.LOOKBACK_DAYS} days (avg {daily_rate:.1f}/day), "
                f"current stock of {current_qty:.1f} {item.unit} {urgency}. "
                f"Estimated depletion: {predicted_date.strftime('%B %d, %Y')}. "
                f"Confidence: {conf}."
            )

            predictions.append(
                {
                    "prediction_type": pred_type,
                    "module": "meals",
                    "predicted_value": round(days_until_empty, 1),
                    "predicted_date": now + timedelta(days=int(days_until_empty)),
                    "confidence_score": confidence,
                    "explanation": explanation,
                    "evidence": {
                        "rule": self.rule_name,
                        "ingredient_id": item.ingredient.id,
                        "ingredient_name": item.ingredient.canonical_name,
                        "current_quantity": current_qty,
                        "unit": item.unit,
                        "daily_consumption_rate": round(daily_rate, 3),
                        "transaction_count": tx_count,
                        "lookback_days": self.LOOKBACK_DAYS,
                        "days_until_empty": round(days_until_empty, 1),
                    },
                    "dedupe_key": dedupe_key,
                }
            )

        return predictions


@register_prediction
class MealPlanAdherenceProjection(BasePredictionRule):
    """Predict meal plan completion rate based on historical adherence."""

    rule_name = "meal_plan_adherence"
    module = "meals"
    prediction_type = "meal_plan_adherence"
    min_confidence_to_store = 0.25

    LOOKBACK_DAYS = 60

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "meals")

    def predict(self, user, event):
        from apps.meals.models import Household, MealPlan, MealPlanEntry

        now = get_current_time()
        cutoff = now - timedelta(days=self.LOOKBACK_DAYS)

        # Find households the user belongs to
        household_ids = list(
            Household.objects.filter(
                memberships__user=user
            ).values_list("id", flat=True)
        )
        if not household_ids:
            household_ids = list(
                Household.objects.filter(
                    primary_user=user
                ).values_list("id", flat=True)
            )
        if not household_ids:
            return []

        # Get completed meal plans (end_date in the past)
        past_plans = MealPlan.objects.filter(
            household_id__in=household_ids,
            created_at__gte=cutoff,
            end_date__lt=now.date(),
        )

        plan_count = past_plans.count()
        if plan_count < 1:
            return []

        # Calculate adherence for each past plan
        # Adherence = percentage of planned meals that were actually logged
        adherence_rates = []

        for plan in past_plans:
            total_entries = MealPlanEntry.objects.filter(
                meal_plan=plan
            ).count()

            if total_entries == 0:
                continue

            # Check how many planned meals have corresponding food log entries
            # Use FoodEntry date overlap as a proxy for adherence
            from apps.health.models import FoodEntry

            planned_dates = set(
                MealPlanEntry.objects.filter(
                    meal_plan=plan
                ).values_list("date", flat=True)
            )

            logged_dates = set(
                FoodEntry.objects.filter(
                    user=user,
                    logged_date__gte=plan.start_date,
                    logged_date__lte=plan.end_date,
                    status="active",
                ).values_list("logged_date", flat=True).distinct()
            )

            if planned_dates:
                overlap = len(planned_dates & logged_dates)
                rate = overlap / len(planned_dates)
                adherence_rates.append(rate)

        if not adherence_rates:
            return []

        # Average adherence
        avg_adherence = sum(adherence_rates) / len(adherence_rates)

        # Trend: compare first half vs second half
        if len(adherence_rates) >= 2:
            mid = len(adherence_rates) // 2
            first_half = sum(adherence_rates[:mid]) / max(1, mid)
            second_half = sum(adherence_rates[mid:]) / max(1, len(adherence_rates) - mid)
            trend = second_half - first_half
        else:
            trend = 0.0

        # Projected adherence for next plan
        projected = min(1.0, max(0.0, avg_adherence + (trend * 0.5)))

        # Confidence based on data quantity
        if plan_count >= 6:
            confidence = 0.70
        elif plan_count >= 3:
            confidence = 0.55
        else:
            confidence = 0.35

        conf = confidence_label(confidence)
        predicted_date = now + timedelta(days=7)
        date_str = predicted_date.strftime("%Y-%m-%d")
        dedupe_key = build_prediction_dedupe_key(
            user.id, self.prediction_type, date_str
        )

        if projected >= 0.80:
            outlook = "excellent — you follow through on most planned meals"
        elif projected >= 0.50:
            outlook = "moderate — about half of planned meals get followed"
        else:
            outlook = "low — most planned meals aren't being followed through"

        trend_desc = (
            "improving" if trend > 0.05
            else "declining" if trend < -0.05
            else "stable"
        )

        explanation = (
            f"Based on {plan_count} past meal plans over {self.LOOKBACK_DAYS} days, "
            f"your average meal plan adherence is {avg_adherence:.0%} "
            f"(trend: {trend_desc}). "
            f"Projected completion for your next plan: {projected:.0%} — {outlook}. "
            f"Confidence: {conf}."
        )

        return [
            {
                "prediction_type": self.prediction_type,
                "module": "meals",
                "predicted_value": round(projected, 2),
                "predicted_date": predicted_date,
                "confidence_score": confidence,
                "explanation": explanation,
                "evidence": {
                    "rule": self.rule_name,
                    "plan_count": plan_count,
                    "avg_adherence": round(avg_adherence, 2),
                    "trend": round(trend, 3),
                    "projected_adherence": round(projected, 2),
                    "adherence_rates": [round(r, 2) for r in adherence_rates],
                    "lookback_days": self.LOOKBACK_DAYS,
                    "outlook": outlook,
                },
                "dedupe_key": dedupe_key,
            }
        ]
