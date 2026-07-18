# ==============================================================================
# File: apps/health/services/nutrition_summary.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Canonical deterministic nutrition day-summary composer.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Single deterministic composer for a day's nutrition summary.

ONE source feeds BOTH the Nutrition Home page render AND the `health.nutrition`
Current Context page-summary provider — so the screen and the assistant can never
present different totals or progress (the exact page-vs-assistant drift class the
Current Context contract exists to eliminate).

Facts only: totals, targets, and progress *numbers*. No verdicts ("on track") —
the model decides what the numbers mean. Reuses the canonical `NutritionQueries`
daily-total authority and the `NutritionGoals` target store; it never re-derives a
total or re-reads raw `FoodEntry` rows.
"""
from decimal import Decimal


def build_nutrition_summary(user, *, target_date=None):
    """Deterministic nutrition facts for one day.

    Returns a dict:
        {
          "date": date,
          "entry_count": int,
          "has_entries": bool,
          "totals": {calories, protein_g, carbs_g, fat_g, fiber_g, sugar_g}  # Decimals
          "goals": NutritionGoals | None,     # the model instance (for template use)
          "targets": {calories, protein_g, carbs_g, fat_g} | None,  # plain numbers
          "progress": {calories, protein_g, carbs_g, fat_g}         # int % or absent key
        }
    """
    from apps.core.utils import get_user_today
    from apps.health.models import NutritionGoals
    from apps.health.services.nutrition_queries import NutritionQueries

    target_date = target_date or get_user_today(user)

    totals = NutritionQueries.get_daily_totals(user, target_date)
    entry_count = NutritionQueries.entries_on_date(user, target_date).count()

    goals = NutritionGoals.objects.filter(
        user=user, effective_until__isnull=True,
    ).first()

    def _pct(current, target):
        if not target:
            return None
        return min(100, int(float(current or Decimal("0")) / float(target) * 100))

    targets = None
    progress = {}
    if goals:
        targets = {
            "calories": goals.daily_calorie_target,
            "protein_g": goals.daily_protein_target_g,
            "carbs_g": goals.daily_carb_target_g,
            "fat_g": goals.daily_fat_target_g,
        }
        for key, target_val in (
            ("calories", goals.daily_calorie_target),
            ("protein_g", goals.daily_protein_target_g),
            ("carbs_g", goals.daily_carb_target_g),
            ("fat_g", goals.daily_fat_target_g),
        ):
            pct = _pct(totals[key], target_val)
            if pct is not None:
                progress[key] = pct

    return {
        "date": target_date,
        "entry_count": entry_count,
        "has_entries": entry_count > 0,
        "totals": totals,
        "goals": goals,
        "targets": targets,
        "progress": progress,
    }


def build_nutrition_progress(user, *, target_date=None):
    """Dashboard-tile-shaped nutrition progress, derived from the SAME canonical
    summary (build_nutrition_summary → NutritionQueries + NutritionGoals). Returns
    None when the user has no calorie target set (the tile hides) — this replaced
    UserPreferences.get_nutrition_progress so nutrition targets live in ONE store.

    Shape (unchanged from the retired producer, minus the dropped goal_percent):
        {
          "date": date,
          "calories": {current, goal, remaining, progress_percent},
          "protein"|"carbs"|"fat": {current_g, goal_g, progress_percent},
        }
    """
    s = build_nutrition_summary(user, target_date=target_date)
    targets = s["targets"]
    if not targets or not targets.get("calories"):
        return None

    totals = s["totals"]
    progress = s["progress"]

    def _macro(key):
        return {
            "current_g": round(float(totals[key]), 1),
            "goal_g": targets.get(key),
            "progress_percent": progress.get(key),
        }

    cal_current = round(float(totals["calories"]))
    cal_goal = targets["calories"]
    return {
        "date": s["date"],
        "calories": {
            "current": cal_current,
            "goal": cal_goal,
            "remaining": cal_goal - cal_current,
            "progress_percent": progress.get("calories"),
        },
        "protein": _macro("protein_g"),
        "carbs": _macro("carbs_g"),
        "fat": _macro("fat_g"),
    }
