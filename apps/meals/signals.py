# ==============================================================================
# File: apps/meals/signals.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Write-boundary enrichment for the canonical Recipe (Foundation 2).
# ==============================================================================
"""Meal Intelligence signals.

Recipe enrichment at the write boundary (architecture P3): whenever a Recipe is
saved with free-text ingredients, (re)build its structured RecipeIngredient rows so
recipe nutrition / inventory-gap / scoring operate on real data. Request-path-safe —
the signal only ENQUEUES; the worker parses + matches + writes (never inline).
"""
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


@receiver(post_save, sender="meals.Recipe", dispatch_uid="meals_enrich_recipe_on_save")
def enrich_recipe_on_save(sender, instance, **kwargs):
    """On any Recipe write with ingredients text, enqueue structured-ingredient
    enrichment. Fire-and-forget via safe_enqueue (never blocks the request path)."""
    if not (getattr(instance, "ingredients", "") or "").strip():
        return
    from apps.core.celery_utils import safe_enqueue
    from apps.meals.tasks import enrich_recipe_ingredients

    safe_enqueue(enrich_recipe_ingredients, instance.pk)
