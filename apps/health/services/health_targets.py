# ==============================================================================
# File: apps/health/services/health_targets.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Canonical TARGET providers for the reusable adherence capability.
#              Registers (domain, metric) -> user's stored target/limit. Read-only.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Target providers for nutrition macros and step goal.

Each reads the CANONICAL stored target (NutritionGoals is the target authority — the
same row get_foundational_health_facts and personal_truth derive from) and returns a
`Target`. Registered at app-ready (HealthConfig.ready imports this module). Adding a new
adherence metric = add one provider here; the reusable adherence surface + capability
index pick it up automatically (no per-metric plumbing).
"""
from apps.core.truth.targets import Target, register_target

_NG_SOURCE = "health.NutritionGoals"


def _active_goals(user):
    # Reuse the ONE canonical active-goals resolver (no parallel query).
    from apps.ai.cos_services.personal_truth import _active_nutrition_goals
    return _active_nutrition_goals(user)


def _macro_target(user, attr, unit, kind="target"):
    g = _active_goals(user)
    if g is None:
        return None
    v = getattr(g, attr, None)
    if v is None:
        return None
    return Target(value=float(v), unit=unit, kind=kind, basis="daily",
                  source=_NG_SOURCE)


# ── Nutrition macros (domain "nutrition") ──────────────────────────────────
@register_target("nutrition", "calories")
def _calories(user):
    return _macro_target(user, "daily_calorie_target", "kcal")


@register_target("nutrition", "protein")
def _protein(user):
    return _macro_target(user, "daily_protein_target_g", "g")


@register_target("nutrition", "carbs")
def _carbs(user):
    return _macro_target(user, "daily_carb_target_g", "g")


@register_target("nutrition", "fat")
def _fat(user):
    return _macro_target(user, "daily_fat_target_g", "g")


@register_target("nutrition", "fiber")
def _fiber(user):
    return _macro_target(user, "daily_fiber_target_g", "g")


@register_target("nutrition", "sugar")
def _sugar(user):
    # A LIMIT (stay under), not a reach-target — kind drives the model's interpretation.
    return _macro_target(user, "daily_sugar_limit_g", "g", kind="limit")


@register_target("nutrition", "sodium")
def _sodium(user):
    return _macro_target(user, "daily_sodium_limit_mg", "mg", kind="limit")


# ── Water (domain "health") ────────────────────────────────────────────────
@register_target("health", "water")
def _water(user):
    """Daily hydration target in oz. Uses the app's canonical default (64 oz) that
    WaterEntry.get_daily_goal_progress already applies — NOT an invented number; it is
    the established product default the water page renders against."""
    return Target(value=64.0, unit="oz", kind="target", basis="daily",
                  source="WaterEntry.get_daily_goal_progress(default)")


# ── Steps (domain "health") ────────────────────────────────────────────────
@register_target("health", "steps")
def _steps(user):
    """The user's daily step goal — from their most recent StepsEntry.goal (the value
    the Steps page renders). None when no goal has ever been recorded."""
    from apps.health.models import StepsEntry
    row = (StepsEntry.objects.filter(user=user, goal__isnull=False)
           .order_by("-logged_date").values_list("goal", flat=True).first())
    if not row:
        return None
    return Target(value=float(row), unit="steps", kind="target", basis="daily",
                  source="health.StepsEntry.goal")
