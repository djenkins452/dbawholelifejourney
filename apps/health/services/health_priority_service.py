# ==============================================================================
# File: apps/health/services/health_priority_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic health priority summary — no DB, no LLM, pure function
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-24
# ==============================================================================
"""
Deterministic Health Priority Summary.

Converts canonical health + medicine state into a short ordered summary
of what matters right now. Sits between canonical state and UI.

Architecture: raw data → canonical state → THIS → UI / (future) Beth

Public API:
    build_health_priority_summary(health_state, medicine_state, current_dt) -> dict

Rules:
    - Pure function: no DB queries, no user object, no cache writes, no LLM
    - Max 4 items, ordered by importance
    - Freshness-gated: stale metrics are suppressed
    - Message discipline: no "right now" without freshness proof
"""

from datetime import datetime, timedelta

import logging

logger = logging.getLogger(__name__)

# ── Priority levels ──────────────────────────────────────────────────────────

HIGH = "high"
MEDIUM = "medium"
LOW = "low"

_PRIORITY_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2}

MAX_ITEMS = 4

# ── Freshness thresholds ────────────────────────────────────────────────────

_FRESHNESS = {
    "bp": timedelta(days=7),
    "sleep": timedelta(days=3),
    "heart_rate": timedelta(days=7),
    "glucose": timedelta(days=7),
    "blood_oxygen": timedelta(days=7),
}


def _parse_ts(iso_str):
    """Parse an ISO timestamp or date string. Returns datetime or None."""
    if not iso_str:
        return None
    try:
        # Full datetime
        if "T" in str(iso_str):
            from django.utils.dateparse import parse_datetime
            return parse_datetime(str(iso_str))
        # Date-only
        from django.utils.dateparse import parse_date
        d = parse_date(str(iso_str))
        if d:
            from django.utils.timezone import make_aware
            return make_aware(datetime(d.year, d.month, d.day, 23, 59, 59))
    except Exception:
        pass
    return None


def _is_fresh(ts_key, health_state, current_dt, metric_name):
    """Check if a metric is fresh enough to include."""
    max_age = _FRESHNESS.get(metric_name)
    if max_age is None:
        return True  # No freshness rule = always include

    ts = _parse_ts(health_state.get(ts_key))
    if ts is None:
        return False  # No timestamp = cannot prove freshness

    # Make both tz-aware or both naive for comparison
    if ts.tzinfo is None and current_dt.tzinfo is not None:
        from django.utils.timezone import make_aware
        ts = make_aware(ts)
    elif ts.tzinfo is not None and current_dt.tzinfo is None:
        ts = ts.replace(tzinfo=None)

    return (current_dt - ts) <= max_age


def _item(key, priority, category, message, icon):
    return {
        "key": key,
        "priority": priority,
        "category": category,
        "message": message,
        "icon": icon,
    }


# ── Item evaluators ─────────────────────────────────────────────────────────

def _eval_medications(medicine_state):
    """Evaluate medication status. Always current (today's schedule)."""
    items = []
    contract = medicine_state.get("_contract", {})
    overdue = contract.get("alerts", {}).get("overdue", [])
    active_count = medicine_state.get("active_count", 0)

    if not active_count:
        return items

    if overdue:
        n = len(overdue)
        s = "s" if n != 1 else ""
        items.append(_item(
            "medications_overdue", HIGH, "medical",
            f"{n} medication{s} overdue", "pill",
        ))
        return items  # Don't also show adherence if overdue

    adherence = medicine_state.get("adherence_7d")
    if adherence is not None and adherence < 70:
        items.append(_item(
            "medication_adherence_low", MEDIUM, "medical",
            "Medication adherence is low", "pill",
        ))
        return items

    # Reassurance: all taken, none overdue
    expected = medicine_state.get("expected_today", 0)
    taken = medicine_state.get("today_taken", 0)
    if expected > 0 and taken >= expected:
        items.append(_item(
            "medications_on_track", LOW, "medical",
            "Medications are on track", "pill",
        ))

    return items


def _eval_blood_pressure(health_state, current_dt):
    """Evaluate blood pressure. Freshness-gated."""
    if not _is_fresh("last_bp_entry", health_state, current_dt, "bp"):
        return []

    sys = health_state.get("bp_systolic")
    dia = health_state.get("bp_diastolic")
    if sys is None or dia is None:
        return []

    # HIGH: hypertensive crisis (AHA)
    if sys >= 180 or dia >= 120:
        return [_item("bp_crisis", HIGH, "vitals",
                       "Blood pressure is very high", "heart")]

    # MEDIUM: Stage 2 hypertension
    if sys >= 140 or dia >= 90:
        return [_item("bp_elevated", MEDIUM, "vitals",
                       "Blood pressure is elevated", "heart")]

    # LOW: normal
    if sys < 120 and dia < 80:
        return [_item("bp_normal", LOW, "vitals",
                       "Blood pressure is normal", "heart")]

    # Elevated (120-139 / 80-89) — no item (not concerning enough, not reassuring)
    return []


def _eval_sleep(health_state, current_dt):
    """Evaluate sleep. Freshness-gated."""
    if not _is_fresh("last_sleep_entry", health_state, current_dt, "sleep"):
        return []

    avg = health_state.get("sleep_avg_duration_7d")
    if avg is None:
        return []

    if avg < 360:  # < 6 hours
        return [_item("sleep_short", MEDIUM, "recovery",
                       "Sleep has been short lately", "moon")]

    if avg >= 420:  # >= 7 hours
        return [_item("sleep_strong", LOW, "recovery",
                       "Sleep has been strong", "moon")]

    return []  # 6-7 hours — acceptable, no item


def _eval_steps(health_state):
    """Evaluate activity. Freshness implicit from 7d window."""
    entries = health_state.get("steps_entries_7d", 0)
    if entries == 0:
        return []

    avg = health_state.get("steps_avg_7d")
    if avg is None:
        return []

    if avg < 3000:
        return [_item("activity_low", MEDIUM, "fitness",
                       "Activity has been low lately", "shoe")]

    if avg >= 7500:
        return [_item("activity_on_track", LOW, "fitness",
                       "Activity is on track", "shoe")]

    return []  # 3000-7500 — moderate, no item


def _eval_glucose(health_state, current_dt):
    """Evaluate glucose. Freshness-gated."""
    if not _is_fresh("last_glucose_entry", health_state, current_dt, "glucose"):
        return []

    value = health_state.get("latest_glucose")
    unit = health_state.get("latest_glucose_unit", "mg/dL")
    if value is None:
        return []

    # Convert to mg/dL for threshold comparison
    mg_dl = value
    if unit == "mmol/L":
        mg_dl = value * 18.0

    # HIGH: severe
    if mg_dl < 54 or mg_dl > 250:
        return [_item("glucose_severe", HIGH, "vitals",
                       "Blood sugar needs attention", "drop")]

    # MEDIUM: moderate concern
    if mg_dl < 70 or mg_dl > 180:
        return [_item("glucose_concern", MEDIUM, "vitals",
                       "Blood sugar is outside normal range", "drop")]

    # LOW: in range
    if 70 <= mg_dl <= 140:
        return [_item("glucose_normal", LOW, "vitals",
                       "Blood sugar is in range", "drop")]

    return []  # 140-180 — slightly elevated, no item


def _eval_blood_oxygen(health_state, current_dt):
    """Evaluate SpO2. Freshness-gated."""
    if not _is_fresh("last_blood_oxygen_entry", health_state, current_dt, "blood_oxygen"):
        return []

    spo2 = health_state.get("latest_blood_oxygen")
    if spo2 is None:
        return []

    if spo2 < 90:
        return [_item("spo2_low", HIGH, "vitals",
                       "Blood oxygen is low", "lungs")]

    if spo2 >= 95:
        return [_item("spo2_normal", LOW, "vitals",
                       "Blood oxygen is normal", "lungs")]

    return []  # 90-95 — borderline, no item


def _eval_heart_rate(health_state, current_dt):
    """Evaluate resting heart rate. Freshness-gated."""
    if not _is_fresh("last_heart_rate_entry", health_state, current_dt, "heart_rate"):
        return []

    hr = health_state.get("latest_heart_rate")
    if hr is None:
        return []

    if hr > 100:
        return [_item("hr_elevated", MEDIUM, "vitals",
                       "Resting heart rate is elevated", "heart")]

    return []  # Normal HR is not interesting enough for a summary slot


# ── Main builder ─────────────────────────────────────────────────────────────

def build_health_priority_summary(health_state, medicine_state, current_dt):
    """
    Build deterministic health priority summary from canonical state.

    Args:
        health_state: dict from get_module_state(user, 'health')
        medicine_state: dict from get_module_state(user, 'medicine')
        current_dt: user's current local aware datetime

    Returns:
        dict with items (max 4), flags, generated_at
    """
    health_state = health_state or {}
    medicine_state = medicine_state or {}

    # Collect all candidate items
    candidates = []
    candidates.extend(_eval_medications(medicine_state))
    candidates.extend(_eval_blood_pressure(health_state, current_dt))
    candidates.extend(_eval_sleep(health_state, current_dt))
    candidates.extend(_eval_steps(health_state))
    candidates.extend(_eval_glucose(health_state, current_dt))
    candidates.extend(_eval_blood_oxygen(health_state, current_dt))
    candidates.extend(_eval_heart_rate(health_state, current_dt))

    # Sort by priority (HIGH=0, MEDIUM=1, LOW=2)
    candidates.sort(key=lambda x: _PRIORITY_ORDER.get(x["priority"], 99))

    # Deduplicate categories (keep first per category, unless both HIGH)
    seen_categories = {}
    selected = []
    for item in candidates:
        cat = item["category"]
        if cat in seen_categories:
            # Allow duplicate category only if both are HIGH
            if item["priority"] == HIGH and seen_categories[cat] == HIGH:
                selected.append(item)
                if len(selected) >= MAX_ITEMS:
                    break
            continue
        seen_categories[cat] = item["priority"]
        selected.append(item)
        if len(selected) >= MAX_ITEMS:
            break

    # Build flags from selected items
    priorities = {item["priority"] for item in selected}
    categories = {item["category"] for item in selected}
    keys = {item["key"] for item in selected}

    flags = {
        "has_urgent": HIGH in priorities,
        "has_medication_risk": any(
            k in keys for k in ("medications_overdue", "medication_adherence_low")
        ),
        "has_recovery_concern": any(
            item["priority"] in (HIGH, MEDIUM) and item["category"] == "recovery"
            for item in selected
        ),
        "has_positive": any(
            item["priority"] == LOW for item in selected
        ),
    }

    return {
        "items": selected,
        "flags": flags,
        "generated_at": current_dt.isoformat() if current_dt else None,
    }
