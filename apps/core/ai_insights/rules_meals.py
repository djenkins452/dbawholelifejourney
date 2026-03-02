"""
PIE — Meal Intelligence Insight Rules.

Rules:
- MealFrequencyRule: Detect if user isn't meal planning regularly
- PantryWasteRule: Detect pantry items expiring without use
- NutritionGapRule: Detect if recent meals miss protein/fiber targets
"""

from datetime import timedelta
from decimal import Decimal

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import days_since, get_time_window
from apps.core.ai_insights.rule_registry import register


@register
class MealFrequencyRule(BaseInsightRule):
    """Detect if user isn't meal planning regularly."""

    rule_name = "meal_frequency_low"
    module = "meals"
    insight_type = "meal_frequency_low"

    LOOKBACK_DAYS = 30
    MIN_PLANS_EXPECTED = 2  # At least 2 plans in 30 days

    def applies(self, user, event):
        return event.get("module") in ("meals", "all") or (
            event.get("event_type") == "scheduled_check"
        )

    def evaluate(self, user, event):
        from apps.meals.models import Household, MealPlan

        window_start, window_end = get_time_window(days=self.LOOKBACK_DAYS)

        # Find households the user belongs to
        household_ids = list(
            Household.objects.filter(
                memberships__user=user
            ).values_list("id", flat=True)
        )
        if not household_ids:
            # Also check primary_user
            household_ids = list(
                Household.objects.filter(
                    primary_user=user
                ).values_list("id", flat=True)
            )
        if not household_ids:
            return []

        plans = MealPlan.objects.filter(
            household_id__in=household_ids,
            created_at__gte=window_start,
            created_at__lte=window_end,
        )
        plan_count = plans.count()

        if plan_count >= self.MIN_PLANS_EXPECTED:
            return []

        plan_ids = list(plans.values_list("id", flat=True))

        if plan_count == 0:
            message = (
                f"No meal plans created in the last {self.LOOKBACK_DAYS} days. "
                f"Planning meals ahead of time helps with healthier eating, "
                f"reduces food waste, and saves money on groceries."
            )
            confidence = 0.90
        else:
            message = (
                f"Only {plan_count} meal plan created in the last "
                f"{self.LOOKBACK_DAYS} days. Regular weekly meal planning "
                f"helps maintain consistent nutrition and reduces last-minute "
                f"unhealthy choices."
            )
            confidence = 0.80

        return [
            {
                "severity": "info",
                "title": "Meal planning could use more attention",
                "message": message,
                "confidence_score": confidence,
                "explain_why": (
                    f"Rule: {self.rule_name}. {self.LOOKBACK_DAYS}-day window from "
                    f"{window_start.date()} to {window_end.date()}. "
                    f"Found {plan_count} plans (expected >= {self.MIN_PLANS_EXPECTED})."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "window_start": str(window_start.date()),
                    "window_end": str(window_end.date()),
                    "plan_count": plan_count,
                    "expected_minimum": self.MIN_PLANS_EXPECTED,
                    "household_ids": household_ids,
                    "record_ids": plan_ids,
                },
                "dedupe_key": build_dedupe_key(
                    user.id, self.insight_type,
                    window_start.date(), window_end.date(),
                    plan_ids,
                ),
            }
        ]


@register
class PantryWasteRule(BaseInsightRule):
    """Detect pantry items expiring without use."""

    rule_name = "pantry_waste"
    module = "meals"
    insight_type = "pantry_waste"

    EXPIRY_WARNING_DAYS = 3  # Alert when items expire within 3 days

    def applies(self, user, event):
        return event.get("module") in ("meals", "all") or (
            event.get("event_type") == "scheduled_check"
        )

    def evaluate(self, user, event):
        from django.utils import timezone

        from apps.meals.models import Household, PantryItem

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

        today = timezone.now().date()
        warning_date = today + timedelta(days=self.EXPIRY_WARNING_DAYS)

        # Find items expiring soon or already expired, with non-zero quantity
        expiring_items = PantryItem.objects.filter(
            household_id__in=household_ids,
            expiration_date_estimated__isnull=False,
            expiration_date_estimated__lte=warning_date,
            quantity__gt=0,
        ).select_related("ingredient")

        if not expiring_items.exists():
            return []

        expired = []
        expiring_soon = []
        for item in expiring_items:
            if item.expiration_date_estimated < today:
                expired.append(item)
            else:
                expiring_soon.append(item)

        results = []
        window_start, window_end = get_time_window(days=self.EXPIRY_WARNING_DAYS)

        if expired:
            expired_names = [i.ingredient.canonical_name for i in expired[:5]]
            expired_ids = [i.id for i in expired]
            count = len(expired)
            extra = f" (and {count - 5} more)" if count > 5 else ""

            results.append({
                "severity": "warning",
                "title": f"{count} pantry item{'s' if count != 1 else ''} expired",
                "message": (
                    f"These items have passed their estimated expiration: "
                    f"{', '.join(expired_names)}{extra}. "
                    f"Consider removing them to keep your pantry accurate."
                ),
                "confidence_score": 0.85,
                "explain_why": (
                    f"Rule: {self.rule_name}. {count} items with "
                    f"expiration_date_estimated before {today}."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "expired_count": count,
                    "expired_items": expired_names,
                    "record_ids": expired_ids,
                    "check_date": str(today),
                },
                "dedupe_key": build_dedupe_key(
                    user.id, f"{self.insight_type}_expired",
                    window_start.date(), window_end.date(),
                    expired_ids,
                ),
            })

        if expiring_soon:
            expiring_names = [i.ingredient.canonical_name for i in expiring_soon[:5]]
            expiring_ids = [i.id for i in expiring_soon]
            count = len(expiring_soon)
            extra = f" (and {count - 5} more)" if count > 5 else ""

            results.append({
                "severity": "info",
                "title": (
                    f"{count} pantry item{'s' if count != 1 else ''} "
                    f"expiring within {self.EXPIRY_WARNING_DAYS} days"
                ),
                "message": (
                    f"Use these soon before they expire: "
                    f"{', '.join(expiring_names)}{extra}. "
                    f"Try planning meals around these ingredients to reduce waste."
                ),
                "confidence_score": 0.80,
                "explain_why": (
                    f"Rule: {self.rule_name}. {count} items expiring between "
                    f"{today} and {warning_date}."
                ),
                "evidence": {
                    "rule_name": self.rule_name,
                    "expiring_count": count,
                    "expiring_items": expiring_names,
                    "record_ids": expiring_ids,
                    "warning_date": str(warning_date),
                },
                "dedupe_key": build_dedupe_key(
                    user.id, f"{self.insight_type}_expiring",
                    window_start.date(), window_end.date(),
                    expiring_ids,
                ),
            })

        return results


@register
class NutritionGapRule(BaseInsightRule):
    """Detect if recent meals miss protein/fiber targets."""

    rule_name = "nutrition_gap"
    module = "meals"
    insight_type = "nutrition_gap"

    LOOKBACK_DAYS = 7
    DEFAULT_PROTEIN_TARGET = Decimal("50")  # grams per day
    DEFAULT_FIBER_TARGET = Decimal("25")  # grams per day
    THRESHOLD_PCT = Decimal("0.70")  # Below 70% of target triggers insight

    def applies(self, user, event):
        return event.get("module") in ("meals", "health", "all") or (
            event.get("event_type") == "scheduled_check"
        )

    def evaluate(self, user, event):
        from django.db.models import Sum

        from apps.health.models import FoodEntry

        window_start, window_end = get_time_window(days=self.LOOKBACK_DAYS)

        # Get daily nutrition totals for the window
        entries = FoodEntry.objects.filter(
            user=user,
            logged_date__gte=window_start.date(),
            logged_date__lte=window_end.date(),
            status="active",
        )

        entry_count = entries.count()
        if entry_count < 3:
            # Not enough data to draw conclusions
            return []

        totals = entries.aggregate(
            total_protein=Sum("total_protein_g"),
            total_fiber=Sum("total_fiber_g"),
        )

        total_protein = totals["total_protein"] or Decimal("0")
        total_fiber = totals["total_fiber"] or Decimal("0")

        # Calculate per-day averages
        days_with_data = (
            entries.values("logged_date").distinct().count()
        )
        if days_with_data < 1:
            return []

        avg_protein = total_protein / days_with_data
        avg_fiber = total_fiber / days_with_data

        # Check dietary profile for custom targets
        protein_target = self.DEFAULT_PROTEIN_TARGET
        fiber_target = self.DEFAULT_FIBER_TARGET
        try:
            from apps.meals.models import DietaryProfile

            profile = DietaryProfile.objects.filter(
                user=user, status="active"
            ).first()
            if profile and profile.protein_target_daily:
                protein_target = profile.protein_target_daily
        except Exception:
            pass

        results = []
        record_ids = list(entries.values_list("id", flat=True)[:50])

        gaps = []
        if avg_protein < protein_target * self.THRESHOLD_PCT:
            gaps.append("protein")
        if avg_fiber < fiber_target * self.THRESHOLD_PCT:
            gaps.append("fiber")

        if not gaps:
            return []

        gap_details = []
        if "protein" in gaps:
            gap_details.append(
                f"protein ({avg_protein:.0f}g avg vs {protein_target:.0f}g target)"
            )
        if "fiber" in gaps:
            gap_details.append(
                f"fiber ({avg_fiber:.0f}g avg vs {fiber_target:.0f}g target)"
            )

        severity = "warning" if len(gaps) > 1 else "info"

        results.append({
            "severity": severity,
            "title": f"Nutrition gap: low {' and '.join(gaps)}",
            "message": (
                f"Over the last {self.LOOKBACK_DAYS} days ({days_with_data} days "
                f"with logged meals), your daily averages are below target for "
                f"{', '.join(gap_details)}. "
                f"Consider adding protein-rich foods like chicken, eggs, or Greek "
                f"yogurt, and high-fiber options like vegetables, beans, or whole grains."
            ),
            "confidence_score": 0.80,
            "explain_why": (
                f"Rule: {self.rule_name}. {self.LOOKBACK_DAYS}-day window, "
                f"{days_with_data} days with data, {entry_count} food entries. "
                f"Threshold: {self.THRESHOLD_PCT:.0%} of target. "
                f"Avg protein: {avg_protein:.1f}g (target: {protein_target:.0f}g), "
                f"avg fiber: {avg_fiber:.1f}g (target: {fiber_target:.0f}g)."
            ),
            "evidence": {
                "rule_name": self.rule_name,
                "window_start": str(window_start.date()),
                "window_end": str(window_end.date()),
                "days_with_data": days_with_data,
                "entry_count": entry_count,
                "avg_protein_g": float(avg_protein),
                "avg_fiber_g": float(avg_fiber),
                "protein_target_g": float(protein_target),
                "fiber_target_g": float(fiber_target),
                "gaps": gaps,
                "record_ids": record_ids,
            },
            "dedupe_key": build_dedupe_key(
                user.id, self.insight_type,
                window_start.date(), window_end.date(),
                record_ids,
            ),
        })

        return results
