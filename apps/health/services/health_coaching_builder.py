# ==============================================================================
# File: apps/health/services/health_coaching_builder.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic health coaching — summary + signals → single action
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-24
# ==============================================================================
"""
Deterministic Health Coaching Builder.

Converts health priority summary + signals into a single actionable
coaching directive for CoS. No LLM reasoning. Pure function.

Architecture: summary + signals → THIS → time-awareness → CoS system prompt

Public API:
    build_health_coaching(summary, signals) -> dict | None
    apply_time_awareness(coaching, current_dt, next_event_time) -> dict | None

Rules:
    - Pure function: no DB, no user object, no cache, no LLM
    - Exactly ONE primary action
    - Medications always override everything else
    - Never references missing data
    - Never gives medical advice beyond simple behavior
    - Never recommends something already completed
    - Signal language: always "this week" for 7-day patterns
"""

import logging

logger = logging.getLogger(__name__)


# ── Action templates keyed by summary item key ──────────────────────────────

_ACTIONS = {
    # HIGH priority
    "medications_overdue": {
        "action": "Take your medications now",
        "reason": "These are already past due — getting back on track matters most right now",
    },
    "bp_crisis": {
        "action": "Sit down, rest, and check your blood pressure again in a few minutes",
        "reason": "Your blood pressure is running very high — take it easy and monitor",
    },
    "glucose_severe": {
        "action": "Check your blood sugar and follow your care plan",
        "reason": "Your blood sugar reading needs attention right away",
    },
    "spo2_low": {
        "action": "Rest and take slow, deep breaths",
        "reason": "Your blood oxygen is lower than usual — slow breathing helps",
    },

    # MEDIUM priority
    "bp_elevated": {
        "action": "Take a few minutes to slow down and reset",
        "reason": "Your blood pressure is running a bit high — lowering stress helps",
    },
    "sleep_short": {
        "action": "Aim for an earlier bedtime tonight",
        "reason": "Sleep has been short this week — even 30 extra minutes makes a difference",
    },
    "medication_adherence_low": {
        "action": "Set a reminder for your next dose",
        "reason": "Medication consistency has been slipping this week — a reminder can help",
    },
    "hr_elevated": {
        "action": "Take a few minutes to rest and breathe slowly",
        "reason": "Your resting heart rate is elevated — slow breathing can help bring it down",
    },
    "activity_low": {
        "action": "Take a 10-minute walk",
        "reason": "Activity has been low this week — a short walk gets momentum back",
    },
    "glucose_concern": {
        "action": "Watch your carb intake at your next meal",
        "reason": "Your blood sugar has been running outside the ideal range",
    },

    # LOW priority (reinforcement)
    "bp_normal": {
        "action": "Stay consistent with your routine",
        "reason": "Blood pressure looks good — keep doing what you're doing",
    },
    "sleep_strong": {
        "action": "Stay consistent with your routine",
        "reason": "Sleep has been strong this week — that's powering everything else",
    },
    "medications_on_track": {
        "action": "Stay consistent with your routine",
        "reason": "Medications are on track — nice work keeping up",
    },
    "activity_on_track": {
        "action": "Keep up your activity level",
        "reason": "You've been moving well this week — consistency is key",
    },
    "glucose_normal": {
        "action": "Stay consistent with your routine",
        "reason": "Blood sugar is in a healthy range — keep it steady",
    },

    # Backfill items
    "sleep_adequate": {
        "action": "Try to get a little more sleep tonight",
        "reason": "Sleep has been adequate but there's room to improve",
    },
    "activity_moderate": {
        "action": "Add a short walk to your day",
        "reason": "Activity has been moderate this week — a little more movement helps",
    },
    "bp_acceptable": {
        "action": "Stay active and manage stress",
        "reason": "Blood pressure is slightly elevated — staying active helps",
    },
}

# ── Signal-based actions (when no matching summary item action) ─────────────

_SIGNAL_ACTIONS = {
    "med_adherence": {
        "poor": {
            "action": "Set a daily medication reminder",
            "reason": "Medication adherence has been declining this week — a consistent reminder helps",
        },
        "declining": {
            "action": "Set a daily medication reminder",
            "reason": "Medication adherence has been slipping this week",
        },
    },
    "sleep_recovery": {
        "poor": {
            "action": "Prioritize an earlier bedtime tonight",
            "reason": "Sleep recovery has been poor this week — even 30 extra minutes helps",
        },
        "declining": {
            "action": "Aim for an earlier bedtime tonight",
            "reason": "Sleep quality has been declining this week",
        },
    },
    "activity_momentum": {
        "low": {
            "action": "Take a 10-minute walk",
            "reason": "Activity levels have been trending down this week — this gets momentum back",
        },
        "declining": {
            "action": "Take a 10-minute walk",
            "reason": "Activity has been dropping this week — a short walk reverses the trend",
        },
    },
    "cardio_stability": {
        "unstable": {
            "action": "Rest and follow up with your care team",
            "reason": "Multiple vital signs need attention",
        },
        "watch": {
            "action": "Take a few minutes to rest and check your vitals again",
            "reason": "One of your vital signs is outside the normal range",
        },
    },
}

# ── Safety fallback ─────────────────────────────────────────────────────────

_SAFETY_FALLBACK = {
    "action": "Stay consistent with your routine today",
    "reason": "Everything is trending in a good direction — keep it steady",
    "priority_level": "low",
    "source_key": "_fallback",
}


# ── Action eligibility: keys that require incomplete state ──────────────────

# Maps source_key → the summary item key that proves the action is still needed.
# If the key isn't in the summary items, the action is ineligible.
_ELIGIBILITY_REQUIRES_ITEM = {
    "medications_overdue": "medications_overdue",
    "medication_adherence_low": "medication_adherence_low",
}


def _is_action_eligible(key, summary_items):
    """
    Check if an action is still valid (not already completed).

    The summary already reflects current state. If a key requires an item
    to be present in the summary (e.g., overdue meds), and it's NOT there,
    the action is stale/completed.
    """
    required_key = _ELIGIBILITY_REQUIRES_ITEM.get(key)
    if required_key is None:
        return True  # No eligibility check for this key
    return any(item["key"] == required_key for item in summary_items)


def build_health_coaching(summary, signals=None):
    """
    Build a single actionable coaching directive from summary + signals.

    Args:
        summary: dict from build_health_priority_summary()
        signals: optional list of signal dicts from build_health_signals()

    Returns:
        dict with action, reason, priority_level, source_key
        Always returns a valid dict (never None when summary has items).
    """
    if not summary or not summary.get("items"):
        return dict(_SAFETY_FALLBACK)

    signals = signals or []
    items = summary["items"]
    priority_level = summary.get("priority_level", "low")

    # Try each item in order until we find an eligible one
    for item in items:
        key = item["key"]

        # FIX 1: Skip ineligible actions (already completed)
        if not _is_action_eligible(key, items):
            continue

        # Check for signal-based items (key starts with "signal_")
        if key.startswith("signal_"):
            sig_key = key.replace("signal_", "")
            sig_actions = _SIGNAL_ACTIONS.get(sig_key, {})
            matching_sig = next(
                (s for s in signals if s["key"] == sig_key), None
            )
            if matching_sig:
                state = matching_sig.get("state", "")
                trend = matching_sig.get("trend", "")
                action_data = sig_actions.get(state) or sig_actions.get(trend)
                if action_data:
                    return {
                        "action": action_data["action"],
                        "reason": action_data["reason"],
                        "priority_level": priority_level,
                        "source_key": key,
                    }

        # Use template for known summary item keys
        action_data = _ACTIONS.get(key)
        if action_data:
            return {
                "action": action_data["action"],
                "reason": action_data["reason"],
                "priority_level": priority_level,
                "source_key": key,
            }

        # Unknown key fallback (per-item)
        if item.get("priority") == "high":
            return {
                "action": "Address the most urgent item first",
                "reason": item.get("message", ""),
                "priority_level": priority_level,
                "source_key": key,
            }

    # FIX 4: Safety fallback — system NEVER returns empty coaching
    return {
        "action": "Stay consistent with your routine today",
        "reason": "Everything is trending in a good direction — keep it steady",
        "priority_level": priority_level,
        "source_key": items[0]["key"] if items else "_fallback",
    }


# ── Time-Aware Coaching Adjustment ──────────────────────────────────────────

# Keys whose actions are NEVER softened or delayed
_NEVER_DELAY_KEYS = frozenset({
    "medications_overdue",
    "bp_crisis",
    "glucose_severe",
    "spo2_low",
})

# Keys whose actions are activity-based (eligible for evening softening)
_ACTIVITY_KEYS = frozenset({
    "activity_low",
    "signal_activity_momentum",
})

# Keys whose actions are stable/reinforcement (eligible for "today" suffix)
_REINFORCEMENT_KEYS = frozenset({
    "bp_normal",
    "sleep_strong",
    "medications_on_track",
    "activity_on_track",
    "glucose_normal",
})


def _get_time_block(hour):
    """Classify hour into time block."""
    if hour < 12:
        return "morning"
    elif hour < 17:
        return "afternoon"
    return "evening"


def _minutes_until_next(next_event_time_str, current_dt):
    """
    Parse a next-event time string and return minutes until it.
    Returns None if unparseable or not today.
    """
    if not next_event_time_str:
        return None
    try:
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(str(next_event_time_str))
        if dt is None:
            return None
        # Make timezone-aware if needed
        if dt.tzinfo is None and current_dt.tzinfo is not None:
            from django.utils.timezone import make_aware
            dt = make_aware(dt)
        elif dt.tzinfo is not None and current_dt.tzinfo is None:
            dt = dt.replace(tzinfo=None)
        diff = (dt - current_dt).total_seconds() / 60
        if diff < 0:
            return None  # Already past
        return diff
    except Exception:
        return None


def apply_time_awareness(coaching, current_dt, next_event_time=None):
    """
    Adjust coaching wording based on time of day and schedule proximity.

    This is a POST-PROCESSING step. It does NOT change the action itself,
    only adjusts phrasing for time-awareness.

    Args:
        coaching: dict from build_health_coaching() (or None)
        current_dt: user's current local aware datetime
        next_event_time: ISO string of next calendar/routine event (or None)

    Returns:
        coaching dict with adjusted wording (same shape, modified in place)
    """
    if not coaching or not current_dt:
        return coaching

    source_key = coaching.get("source_key", "")
    action = coaching.get("action", "")
    priority = coaching.get("priority_level", "low")

    # ── RULE 3: Never delay critical actions ──
    if source_key in _NEVER_DELAY_KEYS:
        # Ensure "now" is present for overdue meds
        if source_key == "medications_overdue" and "now" not in action.lower():
            coaching["action"] = action.rstrip(".") + " now"
        return coaching

    hour = current_dt.hour
    time_block = _get_time_block(hour)
    minutes_until = _minutes_until_next(next_event_time, current_dt)

    # ── RULE 4: Evening softening for activity actions ──
    if time_block == "evening" and source_key in _ACTIVITY_KEYS:
        lower = action.lower()
        if "walk" in lower:
            coaching["action"] = "Take a short walk this evening"
            return coaching
        if "movement" in lower or "active" in lower:
            coaching["action"] = "Light movement this evening"
            return coaching

    # ── RULE 2: Busy soon — shift to "after your next task finishes" ──
    if minutes_until is not None and minutes_until < 30:
        if source_key not in _REINFORCEMENT_KEYS:
            if "now" in action.lower():
                coaching["action"] = action.replace(
                    " now", " after your next task finishes"
                )
            elif not any(
                w in action.lower()
                for w in ("after", "when", "tonight", "evening")
            ):
                coaching["action"] = (
                    action.rstrip(".") + " after your next task finishes"
                )
            return coaching

    # ── RULE 1: Free window — add "now" for actionable items ──
    if minutes_until is None or minutes_until >= 60:
        if source_key not in _REINFORCEMENT_KEYS and priority != "low":
            if "now" not in action.lower() and not any(
                w in action.lower()
                for w in ("after", "when", "tonight", "evening")
            ):
                coaching["action"] = action.rstrip(".") + " now"
                return coaching

    # ── RULE 5: Stable day — add "today" for reinforcement ──
    if source_key in _REINFORCEMENT_KEYS or priority == "low":
        if "today" not in action.lower() and "tonight" not in action.lower():
            coaching["action"] = action.rstrip(".") + " today"

    return coaching
