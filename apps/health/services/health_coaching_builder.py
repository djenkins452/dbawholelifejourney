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
coaching directive for Beth (CoS). No LLM reasoning. Pure function.

Architecture: summary + signals → THIS → CoS system prompt

Public API:
    build_health_coaching(summary, signals) -> dict | None

Rules:
    - Pure function: no DB, no user object, no cache, no LLM
    - Exactly ONE primary action
    - Medications always override everything else
    - Never references missing data
    - Never gives medical advice beyond simple behavior
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
        "reason": "Sleep has been short lately — even 30 extra minutes makes a difference",
    },
    "medication_adherence_low": {
        "action": "Set a reminder for your next dose",
        "reason": "Medication consistency has been slipping — a reminder can help",
    },
    "hr_elevated": {
        "action": "Take a few minutes to rest and breathe slowly",
        "reason": "Your resting heart rate is elevated — slow breathing can help bring it down",
    },
    "activity_low": {
        "action": "Take a 10-minute walk",
        "reason": "Activity has been low — a short walk gets momentum back",
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
        "reason": "Sleep has been strong — that's powering everything else",
    },
    "medications_on_track": {
        "action": "Stay consistent with your routine",
        "reason": "Medications are on track — nice work keeping up",
    },
    "activity_on_track": {
        "action": "Keep up your activity level",
        "reason": "You've been moving well — consistency is key",
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
        "reason": "Activity has been moderate — a little more movement helps",
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
            "reason": "Medication adherence has been declining — a consistent reminder helps",
        },
        "declining": {
            "action": "Set a daily medication reminder",
            "reason": "Medication adherence has been slipping this week",
        },
    },
    "sleep_recovery": {
        "poor": {
            "action": "Prioritize an earlier bedtime tonight",
            "reason": "Sleep recovery has been poor — even 30 extra minutes helps",
        },
        "declining": {
            "action": "Aim for an earlier bedtime tonight",
            "reason": "Sleep quality has been declining this week",
        },
    },
    "activity_momentum": {
        "low": {
            "action": "Take a 10-minute walk",
            "reason": "Activity levels are trending down — this gets momentum back",
        },
        "declining": {
            "action": "Take a 10-minute walk",
            "reason": "Activity has been dropping — a short walk reverses the trend",
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


def build_health_coaching(summary, signals=None):
    """
    Build a single actionable coaching directive from summary + signals.

    Args:
        summary: dict from build_health_priority_summary()
        signals: optional list of signal dicts from build_health_signals()

    Returns:
        dict with action, reason, priority_level, source_key
        or None if no summary data
    """
    if not summary or not summary.get("items"):
        return None

    signals = signals or []
    items = summary["items"]
    priority_level = summary.get("priority_level", "low")

    # ── Step 1: Use the highest-priority summary item for the action ──
    # Items are already ordered by priority (medications first if overdue)
    primary = items[0]
    key = primary["key"]

    # Check for signal-based items (key starts with "signal_")
    if key.startswith("signal_"):
        sig_key = key.replace("signal_", "")
        sig_actions = _SIGNAL_ACTIONS.get(sig_key, {})
        # Find the matching signal to get its state
        matching_sig = next(
            (s for s in signals if s["key"] == sig_key), None
        )
        if matching_sig:
            state = matching_sig.get("state", "")
            trend = matching_sig.get("trend", "")
            # Try state first, then trend
            action_data = sig_actions.get(state) or sig_actions.get(trend)
            if action_data:
                return {
                    "action": action_data["action"],
                    "reason": action_data["reason"],
                    "priority_level": priority_level,
                    "source_key": key,
                }

    # ── Step 2: Use template for known summary item keys ──
    action_data = _ACTIONS.get(key)
    if action_data:
        return {
            "action": action_data["action"],
            "reason": action_data["reason"],
            "priority_level": priority_level,
            "source_key": key,
        }

    # ── Step 3: Fallback — use the summary message as context ──
    # This handles any future items not yet in _ACTIONS
    if primary.get("priority") == "high":
        return {
            "action": "Address the most urgent item first",
            "reason": primary.get("message", ""),
            "priority_level": priority_level,
            "source_key": key,
        }

    return {
        "action": "Stay consistent with your routine",
        "reason": "Everything is trending in a good direction — keep it steady",
        "priority_level": priority_level,
        "source_key": key,
    }
