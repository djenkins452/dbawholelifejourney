"""
Advanced Intelligence Services for Meal Intelligence

Implements:
- EmotionalContextOverlay: mood-aware meal suggestions
- DecisionFatigueMode: simplified choices when overwhelmed
- FaithCalendarIntegration: Lenten/fasting awareness
- FinanceOverlay: budget-aware recommendations
- PredictiveGroceryCycle: predict shopping needs
- ProactiveNudgeScheduler: max 2 nudges/day
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# Emotional Context Overlay
# =============================================================================

@dataclass
class EmotionalContext:
    """Emotional context from journal/mood data."""
    mood: str  # happy, stressed, tired, sad, neutral
    energy_level: str  # high, medium, low
    suggestion_type: str  # comfort, healthy, quick, indulgent, balanced


def get_emotional_overlay(user) -> EmotionalContext:
    """
    Derive meal suggestion style from recent journal mood data.
    Uses the last 3 journal entries to detect emotional patterns.
    """
    try:
        from apps.journal.models import JournalEntry
        recent = JournalEntry.objects.filter(
            user=user,
        ).order_by("-created_at")[:3]

        moods = []
        for entry in recent:
            # Journal entries may have mood_tags or mood field
            if hasattr(entry, "mood_tags") and entry.mood_tags:
                moods.extend(entry.mood_tags if isinstance(entry.mood_tags, list) else [])

        if not moods:
            return EmotionalContext(
                mood="neutral", energy_level="medium", suggestion_type="balanced",
            )

        # Map moods to suggestion type
        mood_lower = [m.lower() for m in moods]
        if any(m in mood_lower for m in ["stressed", "anxious", "overwhelmed"]):
            return EmotionalContext(
                mood="stressed", energy_level="low", suggestion_type="comfort",
            )
        elif any(m in mood_lower for m in ["tired", "exhausted", "drained"]):
            return EmotionalContext(
                mood="tired", energy_level="low", suggestion_type="quick",
            )
        elif any(m in mood_lower for m in ["happy", "excited", "energetic"]):
            return EmotionalContext(
                mood="happy", energy_level="high", suggestion_type="healthy",
            )
        elif any(m in mood_lower for m in ["sad", "down", "depressed"]):
            return EmotionalContext(
                mood="sad", energy_level="low", suggestion_type="comfort",
            )

        return EmotionalContext(
            mood="neutral", energy_level="medium", suggestion_type="balanced",
        )
    except Exception:
        return EmotionalContext(
            mood="neutral", energy_level="medium", suggestion_type="balanced",
        )


# =============================================================================
# Decision Fatigue Mode
# =============================================================================

def get_decision_fatigue_recommendations(
    scored_recipes: list,
    emotional_context: EmotionalContext,
    max_choices: int = 3,
) -> list:
    """
    When user is overwhelmed, simplify to max 3 choices with clear labels.

    Returns simplified recommendations with one-line explanations.
    """
    if not scored_recipes:
        return []

    # Select based on emotional context
    if emotional_context.suggestion_type == "quick":
        # Prioritize by prep time
        quick = [s for s in scored_recipes if (s.prep_time_minutes or 999) <= 30]
        if quick:
            scored_recipes = quick

    elif emotional_context.suggestion_type == "comfort":
        # Prioritize favorites
        favorites = [s for s in scored_recipes if hasattr(s, 'is_favorite')]
        if favorites:
            scored_recipes = favorites

    # Return top N with simplified labels
    choices = scored_recipes[:max_choices]
    simplified = []
    labels = ["Best match", "Runner up", "Quick option"]

    for i, score in enumerate(choices):
        label = labels[i] if i < len(labels) else f"Option {i + 1}"
        simplified.append({
            "label": label,
            "recipe_id": score.recipe_id,
            "recipe_title": score.recipe_title,
            "score": float(score.total_score),
            "one_liner": score.explanation[:80] if score.explanation else "",
            "prep_time": score.prep_time_minutes,
        })

    return simplified


# =============================================================================
# Faith Calendar Integration
# =============================================================================

@dataclass
class FaithCalendarConstraint:
    """Dietary constraints from faith calendar."""
    is_fasting_day: bool
    constraint_type: str  # "none", "no_meat", "vegan", "reduced"
    reason: str


def get_faith_calendar_constraint(user, target_date: date) -> FaithCalendarConstraint:
    """
    Check if a date has faith-based dietary constraints.

    Checks user's faith calendar for fasting days, Lent, etc.
    """
    try:
        from apps.faith.models import FastingDay

        fasting = FastingDay.objects.filter(
            user=user,
            date=target_date,
        ).first()

        if fasting:
            return FaithCalendarConstraint(
                is_fasting_day=True,
                constraint_type=getattr(fasting, "fast_type", "reduced"),
                reason=getattr(fasting, "reason", "Faith calendar fasting day"),
            )
    except Exception:
        pass

    return FaithCalendarConstraint(
        is_fasting_day=False,
        constraint_type="none",
        reason="",
    )


# =============================================================================
# Finance Overlay
# =============================================================================

@dataclass
class BudgetContext:
    """Budget context for meal planning."""
    weekly_food_budget: Optional[Decimal]
    spent_this_week: Decimal
    remaining: Optional[Decimal]
    budget_pressure: str  # "low", "medium", "high"


def get_budget_context(household) -> BudgetContext:
    """
    Get budget context from recent receipt data.
    """
    from apps.meals.models import Receipt

    # Get receipts from last 7 days
    week_ago = timezone.now().date() - timedelta(days=7)
    recent_receipts = Receipt.objects.filter(
        household=household,
        receipt_date__gte=week_ago,
    )

    spent = sum(
        r.total for r in recent_receipts
        if r.total is not None
    )
    spent = Decimal(str(spent)) if spent else Decimal("0")

    # Default budget — could be pulled from finance settings in future
    weekly_budget = Decimal("150")  # Default, override from user settings
    remaining = weekly_budget - spent

    if remaining > weekly_budget * Decimal("0.5"):
        pressure = "low"
    elif remaining > Decimal("0"):
        pressure = "medium"
    else:
        pressure = "high"

    return BudgetContext(
        weekly_food_budget=weekly_budget,
        spent_this_week=spent,
        remaining=remaining,
        budget_pressure=pressure,
    )


# =============================================================================
# Proactive Nudge Scheduler
# =============================================================================

MAX_NUDGES_PER_DAY = 2

@dataclass
class MealNudge:
    """A proactive meal-related nudge."""
    nudge_type: str  # "plan_dinner", "use_expiring", "grocery_reminder"
    title: str
    message: str
    confidence: Decimal
    priority: int  # 1=highest


def get_todays_nudges(user, household) -> list[MealNudge]:
    """
    Generate up to MAX_NUDGES_PER_DAY proactive nudges.

    Nudge types (in priority order):
    1. Use expiring ingredients
    2. Plan tonight's dinner
    3. Grocery trip reminder
    """
    from apps.meals.services.inventory_gap import find_pantry_expiring_soon

    nudges = []
    today = timezone.now().date()

    # 1. Expiring ingredients
    expiring = find_pantry_expiring_soon(household, days=2)
    if expiring.exists():
        names = [item.ingredient.canonical_name for item in expiring[:3]]
        nudges.append(MealNudge(
            nudge_type="use_expiring",
            title="Items expiring soon",
            message=f"Use these soon: {', '.join(names)}",
            confidence=Decimal("0.90"),
            priority=1,
        ))

    # 2. Plan dinner if no plan exists for today
    from apps.meals.models import MealPlanEntry
    has_dinner = MealPlanEntry.objects.filter(
        meal_plan__household=household,
        date=today,
        meal_type="dinner",
    ).exists()

    if not has_dinner:
        nudges.append(MealNudge(
            nudge_type="plan_dinner",
            title="What's for dinner?",
            message="No dinner planned for tonight. Want a suggestion?",
            confidence=Decimal("0.85"),
            priority=2,
        ))

    # 3. Grocery reminder based on cycle
    days_since_trip = _days_since_last_grocery(household)
    if days_since_trip is not None and days_since_trip >= household.grocery_cycle_days - 1:
        nudges.append(MealNudge(
            nudge_type="grocery_reminder",
            title="Grocery trip due",
            message=f"It's been {days_since_trip} days since your last grocery trip",
            confidence=Decimal("0.75"),
            priority=3,
        ))

    # Sort by priority, limit to max
    nudges.sort(key=lambda n: n.priority)
    return nudges[:MAX_NUDGES_PER_DAY]


def _days_since_last_grocery(household) -> Optional[int]:
    """Calculate days since last grocery receipt."""
    from apps.meals.models import Receipt

    latest = Receipt.objects.filter(
        household=household,
        receipt_date__isnull=False,
    ).order_by("-receipt_date").first()

    if latest and latest.receipt_date:
        return (timezone.now().date() - latest.receipt_date).days
    return None
