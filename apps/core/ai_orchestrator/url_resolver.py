"""
Dynamic URL Resolver — Centralized URL resolution for CoS actions and navigation.

Maps intent types, modules, and entities to Django URL paths so CoS can:
1. Embed "View details" links in action responses
2. Direct users to relevant pages in conversation
3. Generate action buttons with navigation targets

Project: Whole Life Journey
Path: apps/core/ai_orchestrator/url_resolver.py
"""

import logging
from typing import Dict, List, Optional

from django.urls import reverse, NoReverseMatch

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intent → Post-Action URL Mapping
# ---------------------------------------------------------------------------
# After an action completes, where should the user go to see the result?
# Format: intent_type → (url_name, label, needs_pk)

INTENT_URL_MAP: Dict[str, dict] = {
    # Health
    "log_weight": {"url": "/health/weight/", "label": "View weight trends"},
    "log_heart_rate": {"url": "/health/heart-rate/", "label": "View heart rate"},
    "log_blood_pressure": {"url": "/health/blood-pressure/", "label": "View blood pressure"},
    "log_glucose": {"url": "/health/glucose/", "label": "View glucose"},
    "log_blood_oxygen": {"url": "/health/blood-oxygen/", "label": "View blood oxygen"},
    "log_food": {"url": "/health/nutrition/", "label": "View nutrition log"},
    "log_sleep": {"url": "/health/sleep/", "label": "View sleep tracker"},
    "log_water": {"url": "/health/hydration/", "label": "View hydration"},
    "log_steps": {"url": "/health/steps/", "label": "View step tracker"},
    "log_body_measurement": {"url": "/health/body-measurements/", "label": "View measurements"},
    # Medicine
    "take_medicine": {"url": "/medical/medicines/", "label": "View medicines"},
    # Fasting
    "start_fast": {"url": "/health/fasting/", "label": "View fasting tracker"},
    "end_fast": {"url": "/health/fasting/", "label": "View fasting tracker"},
    # Journal
    "create_journal_entry": {"url": "/journal/", "label": "View journal"},
    "add_gratitude": {"url": "/journal/", "label": "View journal"},
    # Faith
    "log_prayer": {"url": "/faith/prayer/", "label": "View prayer journal"},
    "mark_prayer_answered": {"url": "/faith/prayer/", "label": "View prayer journal"},
    "save_verse": {"url": "/faith/verses/", "label": "View saved verses"},
    "add_faith_milestone": {"url": "/faith/milestones/", "label": "View milestones"},
    # Purpose
    "create_goal": {"url": "/purpose/goals/", "label": "View goals"},
    "update_goal_progress": {"url": "/purpose/goals/", "label": "View goals"},
    "set_intention": {"url": "/purpose/goals/", "label": "View intentions"},
    "log_habit": {"url": "/purpose/habits/", "label": "View habits"},
    # Life
    "create_task": {"url": "/life/tasks/", "label": "View tasks"},
    "create_routine_task": {"url": "/life/tasks/", "label": "View tasks"},
    "complete_task": {"url": "/life/tasks/", "label": "View tasks"},
    "create_event": {"url": "/calendar/", "label": "View calendar"},
    "add_reminder": {"url": "/calendar/", "label": "View calendar"},
    "read_calendar_events": {"url": "/calendar/", "label": "View calendar"},
    "mutate_calendar_event": {"url": "/calendar/", "label": "View calendar"},
    # Fitness
    "log_workout": {"url": "/health/fitness/", "label": "View workouts"},
    "log_exercise_set": {"url": "/health/fitness/", "label": "View workouts"},
    "log_cardio": {"url": "/health/fitness/", "label": "View workouts"},
    # Transformation
    "log_transformation_protocol": {"url": "/health/transformation/", "label": "View transformation"},
    "log_shopping_item": {"url": "/health/transformation/shopping/", "label": "View shopping list"},
    "complete_shopping_item": {"url": "/health/transformation/shopping/", "label": "View shopping list"},
    # Finance
    "log_transaction": {"url": "/finance/", "label": "View finances"},
    "check_budget": {"url": "/finance/budgets/", "label": "View budgets"},
    # Settings
    "set_cos_name": {"url": "/assistant/cos/settings/", "label": "CoS settings"},
}


# ---------------------------------------------------------------------------
# Module → Landing Page URL Mapping
# ---------------------------------------------------------------------------
# For when CoS needs to direct users to a module's main page.

MODULE_URL_MAP: Dict[str, dict] = {
    "health": {"url": "/health/", "label": "Health Dashboard"},
    "journal": {"url": "/journal/", "label": "Journal"},
    "faith": {"url": "/faith/", "label": "Faith Dashboard"},
    "purpose": {"url": "/purpose/", "label": "Purpose & Goals"},
    "life": {"url": "/life/", "label": "Life Management"},
    "fitness": {"url": "/health/fitness/", "label": "Fitness Tracker"},
    "finance": {"url": "/finance/", "label": "Finance"},
    "medical": {"url": "/medical/", "label": "Medical"},
    "calendar": {"url": "/calendar/", "label": "Calendar"},
    "dashboard": {"url": "/dashboard/", "label": "Dashboard"},
    "assistant": {"url": "/assistant/", "label": "Chief of Staff"},
    "settings": {"url": "/user/preferences/", "label": "Settings"},
    "billing": {"url": "/billing/", "label": "Subscription"},
    "transformation": {"url": "/health/transformation/", "label": "Transformation"},
}


# ---------------------------------------------------------------------------
# Navigable Pages for CoS Awareness
# ---------------------------------------------------------------------------
# Pages that CoS can reference in conversation. Ordered by frequency of use.

NAVIGABLE_PAGES: List[dict] = [
    {"url": "/dashboard/", "name": "Dashboard", "keywords": "home, overview, summary"},
    {"url": "/health/weight/", "name": "Weight Tracking", "keywords": "weight, scale, pounds"},
    {"url": "/health/nutrition/", "name": "Nutrition Log", "keywords": "food, calories, macros, meals"},
    {"url": "/health/sleep/", "name": "Sleep Tracker", "keywords": "sleep, rest, bedtime"},
    {"url": "/health/hydration/", "name": "Hydration", "keywords": "water, hydration, drinking"},
    {"url": "/health/steps/", "name": "Step Tracker", "keywords": "steps, walking, activity"},
    {"url": "/health/fitness/", "name": "Fitness", "keywords": "workout, exercise, gym, lifting"},
    {"url": "/health/fasting/", "name": "Fasting Tracker", "keywords": "fasting, fast, intermittent"},
    {"url": "/health/heart-rate/", "name": "Heart Rate", "keywords": "heart rate, pulse, bpm"},
    {"url": "/health/blood-pressure/", "name": "Blood Pressure", "keywords": "blood pressure, bp"},
    {"url": "/health/glucose/", "name": "Glucose", "keywords": "glucose, blood sugar"},
    {"url": "/health/body-measurements/", "name": "Body Measurements", "keywords": "measurements, waist, chest"},
    {"url": "/health/transformation/", "name": "Transformation", "keywords": "transformation, protocol, body"},
    {"url": "/journal/", "name": "Journal", "keywords": "journal, diary, writing, entry"},
    {"url": "/faith/", "name": "Faith Dashboard", "keywords": "faith, spiritual"},
    {"url": "/faith/prayer/", "name": "Prayer Journal", "keywords": "prayer, prayers, praying"},
    {"url": "/faith/bible-reading/", "name": "Bible Reading", "keywords": "bible, reading, scripture"},
    {"url": "/faith/verses/", "name": "Saved Verses", "keywords": "verses, scripture, bible verse"},
    {"url": "/purpose/goals/", "name": "Goals", "keywords": "goals, objectives, targets"},
    {"url": "/purpose/habits/", "name": "Habits", "keywords": "habits, routines, streak"},
    {"url": "/life/tasks/", "name": "Tasks", "keywords": "tasks, to-do, checklist"},
    {"url": "/life/recipes/", "name": "Recipes", "keywords": "recipes, cooking, recipe book"},
    {"url": "/life/recipes/bulk/", "name": "Bulk Import Recipes", "keywords": "bulk import, upload recipes, scan recipes"},
    {"url": "/calendar/", "name": "Calendar", "keywords": "calendar, schedule, events, appointments"},
    {"url": "/medical/medicines/", "name": "Medicines", "keywords": "medicine, medication, prescription"},
    {"url": "/finance/", "name": "Finance", "keywords": "finance, money, spending, budget"},
    {"url": "/finance/budgets/", "name": "Budgets", "keywords": "budget, budgets, spending limits"},
    {"url": "/user/preferences/", "name": "Settings", "keywords": "settings, preferences, profile"},
    {"url": "/assistant/cos/settings/", "name": "CoS Settings", "keywords": "cos, chief of staff, assistant settings"},
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def resolve_intent_url(intent_type: str) -> Optional[dict]:
    """
    Get the post-action URL for an intent type.

    Args:
        intent_type: The action intent (e.g., 'log_weight').

    Returns:
        Dict with 'url' and 'label', or None if no mapping exists.
    """
    return INTENT_URL_MAP.get(intent_type)


def resolve_module_url(module: str) -> Optional[dict]:
    """
    Get the landing page URL for a module.

    Args:
        module: Module name (e.g., 'health', 'journal').

    Returns:
        Dict with 'url' and 'label', or None if no mapping exists.
    """
    return MODULE_URL_MAP.get(module)


def resolve_entity_url(entity_type: str, entity_id: int = None) -> Optional[str]:
    """
    Get the URL for a specific entity detail page.

    Args:
        entity_type: Type of entity (e.g., 'goal', 'journal_entry', 'event').
        entity_id: Primary key of the entity.

    Returns:
        URL string, or None if no mapping exists.
    """
    # Entity-type → URL pattern mapping with optional PK
    entity_patterns = {
        "goal": "/purpose/goals/{pk}/",
        "journal_entry": "/journal/{pk}/",
        "event": "/calendar/",
        "task": "/life/tasks/",
        "prayer": "/faith/prayer/",
        "habit": "/purpose/habits/",
    }

    pattern = entity_patterns.get(entity_type)
    if not pattern:
        return None

    if entity_id and "{pk}" in pattern:
        return pattern.replace("{pk}", str(entity_id))

    # Return the list view if no PK
    return pattern.replace("{pk}/", "")


def get_navigable_pages() -> List[dict]:
    """
    Get all navigable pages for CoS awareness injection.

    Returns:
        List of dicts with url, name, keywords.
    """
    return NAVIGABLE_PAGES


def build_action_url_metadata(intent_type: str, created_object: dict = None) -> Optional[dict]:
    """
    Build URL metadata for an action result.

    Checks for both the intent-level URL and any entity-specific URL
    from the created_object.

    Args:
        intent_type: The intent that was executed.
        created_object: Dict with created object details (may contain 'id', 'type').

    Returns:
        Dict with 'url', 'label', and optionally 'detail_url', or None.
    """
    result = resolve_intent_url(intent_type)
    if not result:
        return None

    metadata = dict(result)  # Copy to avoid mutating the registry

    # If a specific object was created, try to add a detail URL
    if created_object:
        entity_type = created_object.get("type") or created_object.get("entity_type")
        entity_id = created_object.get("id") or created_object.get("pk")
        if entity_type and entity_id:
            detail_url = resolve_entity_url(entity_type, entity_id)
            if detail_url:
                metadata["detail_url"] = detail_url

    return metadata
