"""
Metric Registry — canonical keys for user metrics.

This registry is the single source of truth for *which* metric keys
AI-facing code is allowed to read. It does not compute anything.
It maps a canonical key (e.g. "health.glucose_avg_7d") to the SAE
state path that already provides the value, plus metadata used for
observability.

Rules
-----
* Adding a new key here requires that a SAE state builder in
  apps.core.ai_state.state_builder already writes that path. The
  orphan test in tests/test_metric_registry.py guards this.
* If a metric has no canonical source, do NOT add it here. Surface
  the gap instead so SAE is extended rather than the metric being
  re-derived inside the AI layer.
* Never add raw model aggregations. The purity test blocks them in
  AI-facing code, which is where this registry is consumed.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class MetricDefinition:
    key: str
    state_path: str
    domain: str
    window: str
    description: str
    unit: Optional[str] = None


_REGISTRY_LIST: List[MetricDefinition] = [
    # ── Glucose ────────────────────────────────────────────────
    MetricDefinition(
        "health.glucose_avg_7d", "health.glucose_avg_7d", "health",
        "7d_rolling", "7-day rolling average blood glucose", "mg/dL",
    ),
    MetricDefinition(
        "health.latest_glucose", "health.latest_glucose", "health",
        "latest", "Most recent blood glucose reading value", "mg/dL",
    ),
    MetricDefinition(
        "health.latest_glucose_unit", "health.latest_glucose_unit", "health",
        "latest", "Unit of most recent glucose reading", None,
    ),
    MetricDefinition(
        "health.glucose_variability_level", "health.glucose_variability_level", "health",
        "daily", "Canonical glucose variability level", None,
    ),

    # ── Weight ─────────────────────────────────────────────────
    MetricDefinition(
        "health.weight_current", "health.weight_current", "health",
        "latest", "Most recent weight value", "lb/kg",
    ),
    MetricDefinition(
        "health.weight_unit", "health.weight_unit", "health",
        "latest", "Unit of most recent weight reading", None,
    ),
    MetricDefinition(
        "health.weight_change_30d", "health.weight_change_30d", "health",
        "30d_delta", "30-day change in weight", "lb/kg",
    ),
    MetricDefinition(
        "health.weight_trend", "health.weight_trend", "health",
        "30d_delta", "30-day weight trend classification", None,
    ),
    MetricDefinition(
        "health.last_weight_entry", "health.last_weight_entry", "health",
        "latest", "Timestamp of last weight entry (presence signal)", None,
    ),

    # ── Sleep ──────────────────────────────────────────────────
    MetricDefinition(
        "health.sleep_avg_hours_7d", "health.sleep_avg_hours_7d", "health",
        "7d_rolling", "7-day average sleep duration", "hours",
    ),
    MetricDefinition(
        "health.sleep_last_night_hours", "health.sleep_last_night_hours", "health",
        "latest", "Hours slept most recent night", "hours",
    ),
    MetricDefinition(
        "health.sleep_entries_7d", "health.sleep_entries_7d", "health",
        "7d_rolling", "Number of sleep entries in last 7 days", "count",
    ),
    MetricDefinition(
        "health.last_sleep_entry", "health.last_sleep_entry", "health",
        "latest", "Timestamp of last sleep entry (presence signal)", None,
    ),

    # ── Nutrition ─────────────────────────────────────────────
    MetricDefinition(
        "nutrition.daily_calories", "nutrition.daily_calories", "nutrition",
        "daily", "Calories consumed today", "kcal",
    ),
    MetricDefinition(
        "nutrition.rolling_7d_calories_avg", "nutrition.rolling_7d_calories_avg", "nutrition",
        "7d_rolling", "7-day rolling average daily calories", "kcal",
    ),
    MetricDefinition(
        "nutrition.food_entries_today", "nutrition.food_entries_today", "nutrition",
        "daily", "Food entries logged today", "count",
    ),
    MetricDefinition(
        "nutrition.food_entries_7d", "nutrition.food_entries_7d", "nutrition",
        "7d_rolling", "Food entries logged in last 7 days", "count",
    ),
    MetricDefinition(
        "health.last_food_entry", "health.last_food_entry", "health",
        "latest", "Date of last food entry (presence signal)", None,
    ),

    # ── Steps ──────────────────────────────────────────────────
    MetricDefinition(
        "health.steps_avg_7d", "health.steps_avg_7d", "health",
        "7d_rolling", "7-day rolling average daily steps", "steps",
    ),
    MetricDefinition(
        "health.steps_entries_7d", "health.steps_entries_7d", "health",
        "7d_rolling", "Days with step entries in last 7 days", "count",
    ),

    # ── Water ──────────────────────────────────────────────────
    MetricDefinition(
        "health.water_today_oz", "health.water_today_oz", "health",
        "daily", "Water intake today", "oz",
    ),
    MetricDefinition(
        "health.water_avg_oz_7d", "health.water_avg_oz_7d", "health",
        "7d_rolling", "7-day rolling average daily water intake", "oz",
    ),
    MetricDefinition(
        "health.water_today_pct", "health.water_today_pct", "health",
        "daily", "Percentage of daily water goal achieved today", "%",
    ),

    # ── Fitness / Workouts ─────────────────────────────────────
    MetricDefinition(
        "fitness.workout_minutes_7d", "fitness.workout_minutes_7d", "fitness",
        "7d_rolling", "Total workout minutes in last 7 days", "minutes",
    ),
    MetricDefinition(
        "fitness.workouts_7d", "fitness.workouts_7d", "fitness",
        "7d_rolling", "Completed workouts in last 7 days", "count",
    ),
    MetricDefinition(
        "fitness.workouts_30d", "fitness.workouts_30d", "fitness",
        "30d_rolling", "Completed workouts in last 30 days", "count",
    ),
    MetricDefinition(
        "fitness.last_workout_date", "fitness.last_workout_date", "fitness",
        "latest", "Date of most recent workout (presence signal)", None,
    ),

    # ── Journal ────────────────────────────────────────────────
    MetricDefinition(
        "journal.entries_7d", "journal.entries_7d", "journal",
        "7d_rolling", "Journal entries in last 7 days", "count",
    ),
    MetricDefinition(
        "journal.entries_30d", "journal.entries_30d", "journal",
        "30d_rolling", "Journal entries in last 30 days", "count",
    ),
    MetricDefinition(
        "journal.days_since_entry", "journal.days_since_entry", "journal",
        "latest", "Days since most recent journal entry", "days",
    ),
    MetricDefinition(
        "journal.last_entry", "journal.last_entry", "journal",
        "latest", "Date of most recent journal entry (presence signal)", None,
    ),

    # ── Mood (lives on journal module) ────────────────────────
    MetricDefinition(
        "journal.mood_avg_7d", "journal.mood_avg_7d", "journal",
        "7d_rolling", "7-day average mood score", None,
    ),
    MetricDefinition(
        "journal.mood_trend", "journal.mood_trend", "journal",
        "7d_rolling", "Mood trend classification", None,
    ),
    MetricDefinition(
        "journal.mood_distribution", "journal.mood_distribution", "journal",
        "7d_rolling", "Mood distribution counts over last 7 days", None,
    ),
    MetricDefinition(
        "journal.last_mood", "journal.last_mood", "journal",
        "latest", "Most recent recorded mood", None,
    ),

    # ── Medication ────────────────────────────────────────────
    MetricDefinition(
        "health.medication_status", "health.medication_status", "health",
        "daily", "Canonical daily medication adherence status", None,
    ),
    MetricDefinition(
        "health.medication_status_reason", "health.medication_status_reason", "health",
        "daily", "Human-readable reason for medication status", None,
    ),

    # ── BP (presence only, no canonical 7d average yet) ───────
    MetricDefinition(
        "health.bp_systolic", "health.bp_systolic", "health",
        "latest", "Most recent systolic BP value", "mmHg",
    ),
    MetricDefinition(
        "health.bp_diastolic", "health.bp_diastolic", "health",
        "latest", "Most recent diastolic BP value", "mmHg",
    ),
    MetricDefinition(
        "health.last_bp_entry", "health.last_bp_entry", "health",
        "latest", "Timestamp of last BP entry (presence signal)", None,
    ),

    # ── Goals (presence check for CoS data snapshot) ──────────
    MetricDefinition(
        "goals.active_goal_count", "goals.active_goal_count", "goals",
        "latest", "Number of active life goals", "count",
    ),
    MetricDefinition(
        "goals.completion_rate", "goals.completion_rate", "goals",
        "latest", "Milestone completion rate across active goals", "%",
    ),
]


METRIC_REGISTRY: Dict[str, MetricDefinition] = {d.key: d for d in _REGISTRY_LIST}


def is_canonical(key: str) -> bool:
    """True if the metric key is registered as canonical."""
    return key in METRIC_REGISTRY


def get_definition(key: str) -> Optional[MetricDefinition]:
    """Return the MetricDefinition for a key, or None."""
    return METRIC_REGISTRY.get(key)


def all_keys() -> List[str]:
    """Return every registered metric key."""
    return list(METRIC_REGISTRY.keys())
