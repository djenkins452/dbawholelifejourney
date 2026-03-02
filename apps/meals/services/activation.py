"""
Whole Life Journey - Meal Activation Service

Project: Whole Life Journey
Path: apps/meals/services/activation.py
Purpose: Progressive Intelligence Activation — enforces minimum data thresholds

Ensures no low-quality dinner suggestions or broken first impressions.
Blocks scoring engine execution until minimum threshold is met:
- PantryItem count >= 5
- Recipe count >= 3
"""

import logging
from dataclasses import dataclass

from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

PANTRY_REQUIRED = 5
RECIPE_REQUIRED = 3

CACHE_TTL = 300  # 5 minutes


@dataclass
class ActivationStatus:
    """Structured activation state."""

    pantry_count: int
    recipe_count: int
    pantry_required: int
    recipe_required: int
    is_ready: bool
    activated_at: object = None  # datetime or None

    @property
    def pantry_pct(self):
        return min(100, int(self.pantry_count / self.pantry_required * 100))

    @property
    def recipe_pct(self):
        return min(100, int(self.recipe_count / self.recipe_required * 100))

    @property
    def missing(self):
        """Return list of missing requirement descriptions."""
        result = []
        if self.pantry_count < self.pantry_required:
            result.append(
                f"Add {self.pantry_required - self.pantry_count} more pantry item(s) "
                f"({self.pantry_count}/{self.pantry_required})"
            )
        if self.recipe_count < self.recipe_required:
            result.append(
                f"Add {self.recipe_required - self.recipe_count} more recipe(s) "
                f"({self.recipe_count}/{self.recipe_required})"
            )
        return result


def get_activation_status(user, household) -> ActivationStatus:
    """
    Check if meal intelligence meets minimum activation threshold.

    Cached per-user for performance. Returns ActivationStatus with
    counts, thresholds, and readiness flag.
    """
    cache_key = f"meal_activation_{user.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    from apps.life.models import Recipe

    from apps.meals.models import PantryItem

    pantry_count = PantryItem.objects.filter(
        household=household, quantity__gt=0
    ).count()
    recipe_count = Recipe.objects.filter(user=user).count()

    is_ready = pantry_count >= PANTRY_REQUIRED and recipe_count >= RECIPE_REQUIRED

    # Check / set activation timestamp
    activated_at = household.meals_activated_at
    if is_ready and not activated_at:
        household.meals_activated_at = timezone.now()
        household.save(update_fields=["meals_activated_at"])
        activated_at = household.meals_activated_at
        logger.info(
            "Meal intelligence activated for household %s (user %s)",
            household.id,
            user.id,
        )

    status = ActivationStatus(
        pantry_count=pantry_count,
        recipe_count=recipe_count,
        pantry_required=PANTRY_REQUIRED,
        recipe_required=RECIPE_REQUIRED,
        is_ready=is_ready,
        activated_at=activated_at,
    )

    cache.set(cache_key, status, CACHE_TTL)
    return status


def invalidate_activation_cache(user_id):
    """Invalidate activation cache when pantry or recipes change."""
    cache.delete(f"meal_activation_{user_id}")
