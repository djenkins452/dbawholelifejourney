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

Architecture: raw data → canonical state → THIS → UI / (future) CoS

Public API:
    build_health_priority_summary(health_state, medicine_state, current_dt) -> dict

Rules:
    - Pure function: no DB queries, no user object, no cache writes, no LLM
    - Min 2, max 4 items (unless truly fewer signals exist)
    - Freshness-gated: stale metrics are suppressed
    - Message discipline: no "right now" / "so far today" without proof
    - Medication overdue always dominates (forced to index 0)
    - Balanced: includes at least one positive if room and data support it
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
MIN_ITEMS = 2

# ── Headlines ────────────────────────────────────────────────────────────────

_HEADLINES = {
    HIGH: "Health needs attention",
    MEDIUM: "A few things need attention",
    LOW: "Health looks stable",
}

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
                       "Blood pressure looks good", "heart")]

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


def _eval_steps(health_state, current_dt):
    """Evaluate activity. Freshness implicit from 7d window.

    Uses today_steps + current hour to decide "so far today" vs "lately".
    """
    entries = health_state.get("steps_entries_7d", 0)
    if entries == 0:
        return []

    avg = health_state.get("steps_avg_7d")
    if avg is None:
        return []

    # Check for same-day step data
    today_steps = health_state.get("today_steps")
    has_today_context = today_steps is not None and current_dt is not None

    if avg < 3000:
        if has_today_context and today_steps < 3000 and current_dt.hour >= 12:
            msg = "Activity is low so far today"
        else:
            msg = "Activity has been low lately"
        return [_item("activity_low", MEDIUM, "fitness", msg, "shoe")]

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
                       "Blood sugar is outside the healthy range", "drop")]

    # LOW: in range
    if 70 <= mg_dl <= 140:
        return [_item("glucose_normal", LOW, "vitals",
                       "Blood sugar is in a healthy range", "drop")]

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

    # SpO2 >= 95 is normal for nearly everyone — too trivial for a summary slot.
    # Only surface SpO2 when it's actually concerning.
    return []


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


# ── Signal → Summary item conversion ────────────────────────────────────────

# Concern states that qualify a signal for summary inclusion
_CONCERN_STATES = frozenset({"poor", "declining", "unstable", "low", "watch"})

# Signal priority order (lower index = higher priority)
_SIGNAL_PRIORITY = ["med_adherence", "body_composition", "cardio_stability",
                     "metabolic_efficiency", "activity_momentum", "sleep_recovery"]

# Map signal state → summary priority
_SIGNAL_STATE_TO_PRIORITY = {
    "unstable": HIGH,
    "poor": MEDIUM,
    "declining": MEDIUM,
    "watch": MEDIUM,
    "low": MEDIUM,
}


def _select_signal_for_summary(signals, selected_keys):
    """
    Select at most ONE signal to inject into the summary.

    Rules:
        - Signal state must indicate concern (_CONCERN_STATES)
        - Must not duplicate meaning with an existing summary item
        - Priority order: med_adherence > cardio_stability > activity > sleep

    Args:
        signals: list of signal dicts from build_health_signals()
        selected_keys: set of keys already in the summary

    Returns:
        summary item dict, or None
    """
    if not signals:
        return None

    # Map of signal keys that overlap with existing summary item keys
    _SIGNAL_OVERLAPS = {
        "med_adherence": {"medications_overdue", "medication_adherence_low",
                          "medications_on_track"},
        "cardio_stability": {"bp_crisis", "bp_elevated", "bp_normal",
                             "glucose_severe", "glucose_concern", "glucose_normal",
                             "hr_elevated"},
        "activity_momentum": {"activity_low", "activity_on_track"},
        "sleep_recovery": {"sleep_short", "sleep_strong"},
        "body_composition": set(),  # No overlap with existing items
        "metabolic_efficiency": set(),
    }

    # Index signals by key for ordered lookup
    sig_by_key = {s["key"]: s for s in signals}

    for sig_key in _SIGNAL_PRIORITY:
        sig = sig_by_key.get(sig_key)
        if sig is None:
            continue

        # Must be in a concern state
        state = sig.get("state", "")
        trend = sig.get("trend", "")
        if state not in _CONCERN_STATES and trend not in _CONCERN_STATES:
            continue

        # Must not overlap with existing summary items
        overlaps = _SIGNAL_OVERLAPS.get(sig_key, set())
        if overlaps & selected_keys:
            continue

        # Convert to summary item
        # Use the more concerning of state or trend for priority mapping
        effective_state = state if state in _CONCERN_STATES else trend
        priority = _SIGNAL_STATE_TO_PRIORITY.get(effective_state, MEDIUM)

        return _item(
            f"signal_{sig_key}",
            priority,
            "signal",
            sig.get("insight", ""),
            "trend",
        )

    return None


# ── Backfill: neutral items from gap-zone state ─────────────────────────────

def _generate_backfill_items(health_state, medicine_state, current_dt,
                              exclude_keys):
    """
    Generate neutral/gap-zone items for minimum-fill when primary evaluators
    produced too few candidates.

    These cover metrics that exist in state but fell in "acceptable" ranges
    (e.g., sleep 6-7h, steps 3000-7500, BP 120-139). Freshness-gated.

    Returns list of LOW items, ordered by preference: sleep, activity,
    glucose, medications.
    """
    items = []

    # Sleep: 6-7h is acceptable — worth mentioning
    if "sleep_short" not in exclude_keys and "sleep_strong" not in exclude_keys:
        if _is_fresh("last_sleep_entry", health_state, current_dt, "sleep"):
            avg = health_state.get("sleep_avg_duration_7d")
            entries = health_state.get("sleep_entries_7d", 0)
            if avg is not None and entries > 0 and 360 <= avg < 420:
                items.append(_item("sleep_adequate", LOW, "recovery",
                                   "Sleep has been adequate", "moon"))

    # Steps: 3000-7500 is moderate — worth mentioning
    if "activity_low" not in exclude_keys and "activity_on_track" not in exclude_keys:
        avg = health_state.get("steps_avg_7d")
        entries = health_state.get("steps_entries_7d", 0)
        if avg is not None and entries > 0 and 3000 <= avg < 7500:
            items.append(_item("activity_moderate", LOW, "fitness",
                               "Activity has been moderate", "shoe"))

    # BP: 120-139 / 80-89 is elevated but not concerning
    if "bp_normal" not in exclude_keys and "bp_elevated" not in exclude_keys:
        if _is_fresh("last_bp_entry", health_state, current_dt, "bp"):
            sys = health_state.get("bp_systolic")
            dia = health_state.get("bp_diastolic")
            if sys is not None and dia is not None:
                if 120 <= sys < 140 and dia < 90:
                    items.append(_item("bp_acceptable", LOW, "vitals",
                                       "Blood pressure is slightly elevated",
                                       "heart"))

    # Glucose: 140-180 is mildly elevated
    if "glucose_normal" not in exclude_keys and "glucose_concern" not in exclude_keys:
        if _is_fresh("last_glucose_entry", health_state, current_dt, "glucose"):
            value = health_state.get("latest_glucose")
            unit = health_state.get("latest_glucose_unit", "mg/dL")
            if value is not None:
                mg_dl = value * 18.0 if unit == "mmol/L" else value
                if 140 < mg_dl <= 180:
                    items.append(_item("glucose_mildly_elevated", LOW, "vitals",
                                       "Blood sugar is slightly elevated",
                                       "drop"))

    # Medication on track (if not already present)
    if ("medications_on_track" not in exclude_keys
            and "medications_overdue" not in exclude_keys
            and "medication_adherence_low" not in exclude_keys):
        active = medicine_state.get("active_count", 0)
        if active > 0:
            contract = medicine_state.get("_contract", {})
            overdue = contract.get("alerts", {}).get("overdue", [])
            if not overdue:
                expected = medicine_state.get("expected_today", 0)
                taken = medicine_state.get("today_taken", 0)
                if expected > 0 and taken >= expected:
                    items.append(_item("medications_on_track", LOW, "medical",
                                       "Medications are on track", "pill"))

    return items


# ── Main builder ─────────────────────────────────────────────────────────────

def build_health_priority_summary(health_state, medicine_state, current_dt,
                                   signals=None):
    """
    Build deterministic health priority summary from canonical state.

    Args:
        health_state: dict from get_module_state(user, 'health')
        medicine_state: dict from get_module_state(user, 'medicine')
        current_dt: user's current local aware datetime
        signals: optional list of health signal dicts from build_health_signals()

    Returns:
        dict with headline, items (min 2 / max 4), flags, generated_at
    """
    health_state = health_state or {}
    medicine_state = medicine_state or {}
    signals = signals or []

    # Collect all candidate items from evaluators
    candidates = []
    candidates.extend(_eval_medications(medicine_state))
    candidates.extend(_eval_blood_pressure(health_state, current_dt))
    candidates.extend(_eval_sleep(health_state, current_dt))
    candidates.extend(_eval_steps(health_state, current_dt))
    candidates.extend(_eval_glucose(health_state, current_dt))
    candidates.extend(_eval_blood_oxygen(health_state, current_dt))
    candidates.extend(_eval_heart_rate(health_state, current_dt))

    # Sort by priority (HIGH=0, MEDIUM=1, LOW=2)
    candidates.sort(key=lambda x: _PRIORITY_ORDER.get(x["priority"], 99))

    # ── Phase 1: Select with category dedup ──
    seen_categories = {}
    selected = []
    overflow = []  # items skipped by dedup, available for min-fill

    for item in candidates:
        if len(selected) >= MAX_ITEMS:
            break
        cat = item["category"]
        if cat in seen_categories:
            # Allow duplicate category only if both are HIGH
            if item["priority"] == HIGH and seen_categories[cat] == HIGH:
                selected.append(item)
            else:
                overflow.append(item)
            continue
        seen_categories[cat] = item["priority"]
        selected.append(item)

    # ── Phase 2: Enforce medication dominance ──
    # If overdue meds exist, they MUST be item[0] regardless of sort order
    overdue_items = [i for i in selected if i["key"] == "medications_overdue"]
    if overdue_items:
        # Remove from current position, insert at 0
        selected = [i for i in selected if i["key"] != "medications_overdue"]
        selected.insert(0, overdue_items[0])

    # ── Phase 2.5: Inject ONE signal (if concerning + non-duplicate) ──
    if signals and len(selected) < MAX_ITEMS:
        selected_keys = {i["key"] for i in selected}
        signal_item = _select_signal_for_summary(signals, selected_keys)
        if signal_item:
            # Insert after medications (index 1) if meds exist, else at 0
            has_meds = any(i["category"] == "medical" for i in selected)
            insert_idx = 1 if has_meds and len(selected) > 0 else 0
            selected.insert(insert_idx, signal_item)

    # ── Phase 3: Enforce minimum items (2) ──
    # If we have only 1 item, try to fill from overflow (deduped-out items)
    # Only allow overflow items from different categories (preserve dedup)
    if len(selected) < MIN_ITEMS and len(candidates) >= MIN_ITEMS:
        selected_cats = {i["category"] for i in selected}
        for item in overflow:
            if (item["key"] not in {s["key"] for s in selected}
                    and item["category"] not in selected_cats):
                selected.append(item)
                selected_cats.add(item["category"])
                if len(selected) >= MIN_ITEMS:
                    break

    # ── Phase 4: Ensure balance — include a positive if room + data ──
    has_positive = any(i["priority"] == LOW for i in selected)
    if not has_positive and len(selected) < MAX_ITEMS:
        selected_cats = {i["category"] for i in selected}
        low_candidates = [
            c for c in candidates
            if c["priority"] == LOW
            and c["key"] not in {s["key"] for s in selected}
            and c["category"] not in selected_cats
        ]
        if low_candidates:
            selected.append(low_candidates[0])

    # ── Phase 5: Hard minimum backfill ──
    # If still < 2 items after all phases, generate neutral/gap-zone items
    # from available state. These are metrics that exist but fell in
    # "acceptable" ranges that didn't produce a candidate.
    if len(selected) < MIN_ITEMS:
        selected_keys = {i["key"] for i in selected}
        backfill = _generate_backfill_items(health_state, medicine_state,
                                            current_dt, selected_keys)
        for item in backfill:
            selected.append(item)
            if len(selected) >= MIN_ITEMS:
                break

    # Final trim to MAX_ITEMS
    selected = selected[:MAX_ITEMS]

    # ── Derive summary-level priority and headline ──
    if any(i["priority"] == HIGH for i in selected):
        priority_level = HIGH
    elif any(i["priority"] == MEDIUM for i in selected):
        priority_level = MEDIUM
    elif selected:
        priority_level = LOW
    else:
        priority_level = LOW

    headline = _HEADLINES.get(priority_level, _HEADLINES[LOW])

    # ── Build flags ──
    keys = {item["key"] for item in selected}

    flags = {
        "has_urgent": any(i["priority"] == HIGH for i in selected),
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
        "headline": headline,
        "priority_level": priority_level,
        "items": selected,
        "flags": flags,
        "generated_at": current_dt.isoformat() if current_dt else None,
    }
