# ==============================================================================
# File: apps/life/services/task_coaching_builder.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic task coaching + time-awareness + nudges
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-24
# ==============================================================================
"""
Deterministic Task Coaching, Time-Awareness, and Proactive Nudging.

Combines Phases 3-5 of the Task intelligence system:
    - build_task_coaching() — single action from summary + signals
    - apply_task_time_awareness() — adjust phrasing for time/schedule
    - generate_task_nudge() — proactive nudge when warranted

Architecture: state → signals → summary → coaching → time-aware → nudges

Rules:
    - Pure functions: no DB, no user object, no cache writes, no LLM
    - ONE action per coaching response
    - Overdue always dominates
    - Never recommends completed work
    - Safety fallback: always returns valid coaching
"""

import logging

logger = logging.getLogger(__name__)


# ── Coaching action templates ────────────────────────────────────────────────

_ACTIONS = {
    # HIGH
    "tasks_overdue": {
        "action": "Start with your overdue tasks",
        "reason": "Getting these done clears the backlog and reduces pressure",
    },
    "foundational_overdue": {
        "action": "Handle your foundational tasks first",
        "reason": "These are your non-negotiables — they need attention",
    },
    "next_task_overdue": {
        "action": "Start your overdue task now",
        "reason": "This is past due — clearing it is the top priority",
    },

    # MEDIUM
    "next_task": {
        "action": "Start your next task",
        "reason": "This is the most actionable item right now",
    },
    "tasks_due_soon": {
        "action": "Focus on what's due soon",
        "reason": "You have tasks coming up — getting ahead feels good",
    },
    "tasks_due_today": {
        "action": "Work through today's tasks",
        "reason": "Steady progress keeps you on track",
    },

    # LOW (reinforcement)
    "momentum_high": {
        "action": "Keep up the pace",
        "reason": "You're making great progress today — keep it going",
    },
    "momentum_moderate": {
        "action": "Keep working through your list",
        "reason": "Good progress so far — keep building on it",
    },
    "tasks_clear": {
        "action": "Stay consistent with your routine today",
        "reason": "No pressing tasks — a good time to plan ahead",
    },
    "tasks_tomorrow": {
        "action": "Preview tomorrow's tasks",
        "reason": "Getting a head start makes tomorrow easier",
    },
}

# Signal-based actions
_SIGNAL_ACTIONS = {
    "task_momentum": {
        "low": {
            "action": "Start one small task to build momentum",
            "reason": "No tasks completed yet today — starting small gets things moving",
        },
    },
    "task_pressure": {
        "high": {
            "action": "Tackle your most important task first",
            "reason": "Task pressure is high — focus on what matters most",
        },
    },
    "task_slippage": {
        "slipping": {
            "action": "Reprioritize your task list",
            "reason": "Tasks are falling behind — a quick reprioritization helps",
        },
    },
}

_SAFETY_FALLBACK = {
    "action": "Stay consistent with your routine today",
    "reason": "Everything is manageable — keep working through your list",
    "priority_level": "low",
    "source_key": "_fallback",
}


def build_task_coaching(summary, signals=None):
    """
    Build a single actionable task coaching directive.

    Args:
        summary: dict from build_task_priority_summary()
        signals: optional list of signal dicts from build_task_signals()

    Returns:
        dict with action, reason, priority_level, source_key (always valid)
    """
    if not summary or not summary.get("items"):
        return dict(_SAFETY_FALLBACK)

    signals = signals or []
    items = summary["items"]
    priority_level = summary.get("priority_level", "low")

    # Personalize next_task action with title
    next_up_title = None
    for item in items:
        if item["key"] in ("next_task", "next_task_overdue"):
            msg = item.get("message", "")
            if msg.startswith("Next: "):
                next_up_title = msg.replace("Next: ", "").split(" at ")[0].split(" (")[0]
            break

    # Try each item in priority order
    for item in items:
        key = item["key"]

        # Check signal-based items
        if key.startswith("signal_"):
            sig_key = key.replace("signal_", "")
            sig_actions = _SIGNAL_ACTIONS.get(sig_key, {})
            matching_sig = next(
                (s for s in signals if s["key"] == sig_key), None
            )
            if matching_sig:
                state = matching_sig.get("state", "")
                action_data = sig_actions.get(state)
                if action_data:
                    return {
                        "action": action_data["action"],
                        "reason": action_data["reason"],
                        "priority_level": priority_level,
                        "source_key": key,
                    }

        # Template-based actions
        action_data = _ACTIONS.get(key)
        if action_data:
            action = action_data["action"]
            reason = action_data["reason"]

            # Personalize with task title
            if key == "next_task" and next_up_title:
                action = f"Start your next task: {next_up_title}"

            return {
                "action": action,
                "reason": reason,
                "priority_level": priority_level,
                "source_key": key,
            }

    # Safety fallback
    return {
        "action": "Stay consistent with your routine today",
        "reason": "Everything is manageable — keep working through your list",
        "priority_level": priority_level,
        "source_key": items[0]["key"] if items else "_fallback",
    }


# ── Time-Aware Coaching Adjustment ──────────────────────────────────────────

_NEVER_DELAY_KEYS = frozenset({
    "tasks_overdue",
    "foundational_overdue",
    "next_task_overdue",
})

_REINFORCEMENT_KEYS = frozenset({
    "momentum_high",
    "momentum_moderate",
    "tasks_clear",
    "tasks_tomorrow",
})


def _minutes_until_next(next_event_time_str, current_dt):
    """Parse a next-event time string and return minutes until it."""
    if not next_event_time_str:
        return None
    try:
        from django.utils.dateparse import parse_datetime
        dt = parse_datetime(str(next_event_time_str))
        if dt is None:
            return None
        if dt.tzinfo is None and current_dt.tzinfo is not None:
            from django.utils.timezone import make_aware
            dt = make_aware(dt)
        elif dt.tzinfo is not None and current_dt.tzinfo is None:
            dt = dt.replace(tzinfo=None)
        diff = (dt - current_dt).total_seconds() / 60
        return diff if diff >= 0 else None
    except Exception:
        return None


def apply_task_time_awareness(coaching, current_dt, next_event_time=None):
    """
    Adjust task coaching wording based on time of day and schedule proximity.

    Args:
        coaching: dict from build_task_coaching()
        current_dt: user's current local aware datetime
        next_event_time: ISO string of next calendar event (or None)

    Returns:
        coaching dict with adjusted wording
    """
    if not coaching or not current_dt:
        return coaching

    source_key = coaching.get("source_key", "")
    action = coaching.get("action", "")
    priority = coaching.get("priority_level", "low")

    # Never delay overdue
    if source_key in _NEVER_DELAY_KEYS:
        if "now" not in action.lower():
            coaching["action"] = action.rstrip(".") + " now"
        return coaching

    hour = current_dt.hour
    minutes_until = _minutes_until_next(next_event_time, current_dt)

    # Evening softening
    if hour >= 17 and source_key not in _REINFORCEMENT_KEYS:
        if not any(w in action.lower() for w in ("evening", "tonight", "tomorrow")):
            coaching["action"] = action.rstrip(".") + " this evening"
            return coaching

    # Busy soon — defer
    if minutes_until is not None and minutes_until < 30:
        if source_key not in _REINFORCEMENT_KEYS:
            if "now" in action.lower():
                coaching["action"] = action.replace(
                    " now", " after your next task finishes"
                )
            elif not any(w in action.lower() for w in ("after", "when", "evening")):
                coaching["action"] = (
                    action.rstrip(".") + " after your next task finishes"
                )
            return coaching

    # Free window — add "now"
    if minutes_until is None or minutes_until >= 60:
        if source_key not in _REINFORCEMENT_KEYS and priority != "low":
            if "now" not in action.lower() and not any(
                w in action.lower() for w in ("after", "when", "evening", "tonight")
            ):
                coaching["action"] = action.rstrip(".") + " now"
                return coaching

    # Reinforcement — add "today"
    if source_key in _REINFORCEMENT_KEYS or priority == "low":
        if "today" not in action.lower() and "tonight" not in action.lower():
            coaching["action"] = action.rstrip(".") + " today"

    return coaching


# ── Proactive Nudge Engine ──────────────────────────────────────────────────

NUDGE_TASK_OVERDUE = "task_overdue"
NUDGE_TASK_PRESSURE = "task_pressure"
NUDGE_TASK_MOMENTUM = "task_momentum"
NUDGE_TASK_REINFORCEMENT = "task_reinforcement"

_NUDGE_FREQUENCY = {
    NUDGE_TASK_OVERDUE: 60,       # max once/hour
    NUDGE_TASK_PRESSURE: 1440,    # max once/day
    NUDGE_TASK_MOMENTUM: 1440,    # max once/day
    NUDGE_TASK_REINFORCEMENT: 1440,  # max once/day
}


def _is_within_frequency(nudge_type, last_nudges, current_dt):
    """Check if a nudge was sent too recently."""
    if not last_nudges:
        return False
    last_sent_str = last_nudges.get(nudge_type)
    if not last_sent_str:
        return False
    try:
        from django.utils.dateparse import parse_datetime
        last_sent = parse_datetime(str(last_sent_str))
        if last_sent is None:
            return False
        if last_sent.tzinfo is None and current_dt.tzinfo is not None:
            from django.utils.timezone import make_aware
            last_sent = make_aware(last_sent)
        elif last_sent.tzinfo is not None and current_dt.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=None)
        limit = _NUDGE_FREQUENCY.get(nudge_type, 60)
        elapsed = (current_dt - last_sent).total_seconds() / 60
        return elapsed < limit
    except Exception:
        return False


def generate_task_nudge(summary, signals, coaching, current_dt,
                         last_nudges=None):
    """
    Generate a proactive task nudge if warranted.

    Args:
        summary: dict from build_task_priority_summary()
        signals: list from build_task_signals()
        coaching: dict from build_task_coaching()
        current_dt: user's current local aware datetime
        last_nudges: dict of {nudge_type: ISO timestamp}

    Returns:
        dict with type, nudge_type, priority, message, action — or None
    """
    if not summary or not coaching or not current_dt:
        return None

    signals = signals or []
    last_nudges = last_nudges or {}
    flags = summary.get("flags", {})

    # NUDGE 1: Overdue tasks (HIGH)
    if flags.get("has_overdue"):
        if not _is_within_frequency(NUDGE_TASK_OVERDUE, last_nudges, current_dt):
            overdue_count = 0
            for item in summary.get("items", []):
                if item["key"] == "tasks_overdue":
                    # Extract count from message
                    msg = item.get("message", "")
                    try:
                        overdue_count = int(msg.split()[0])
                    except (ValueError, IndexError):
                        overdue_count = 1
                    break
            s = "s" if overdue_count != 1 else ""
            return {
                "type": "tasks",
                "nudge_type": NUDGE_TASK_OVERDUE,
                "nudge_key": NUDGE_TASK_OVERDUE,
                "priority": "high",
                "message": f"You have {overdue_count} overdue task{s}",
                "action": "Start with the most important one now",
            }

    # NUDGE 2: High pressure signal
    pressure_sig = next((s for s in signals if s["key"] == "task_pressure"), None)
    if pressure_sig and pressure_sig.get("state") == "high":
        if not _is_within_frequency(NUDGE_TASK_PRESSURE, last_nudges, current_dt):
            return {
                "type": "tasks",
                "nudge_type": NUDGE_TASK_PRESSURE,
                "nudge_key": NUDGE_TASK_PRESSURE,
                "priority": "medium",
                "message": pressure_sig.get("insight", "Task pressure is high"),
                "action": coaching.get("action", "Focus on your most important task"),
            }

    # NUDGE 3: Low momentum
    momentum_sig = next((s for s in signals if s["key"] == "task_momentum"), None)
    if momentum_sig and momentum_sig.get("state") == "low":
        if not _is_within_frequency(NUDGE_TASK_MOMENTUM, last_nudges, current_dt):
            return {
                "type": "tasks",
                "nudge_type": NUDGE_TASK_MOMENTUM,
                "nudge_key": NUDGE_TASK_MOMENTUM,
                "priority": "medium",
                "message": "No tasks completed yet today",
                "action": "Start one small task to build momentum",
            }

    # NUDGE 4: Reinforcement (stable day)
    priority_level = summary.get("priority_level", "low")
    if priority_level == "low" and not flags.get("has_overdue"):
        momentum = next((s for s in signals if s["key"] == "task_momentum"), None)
        if momentum and momentum.get("state") in ("strong", "moderate"):
            if not _is_within_frequency(
                NUDGE_TASK_REINFORCEMENT, last_nudges, current_dt
            ):
                return {
                    "type": "tasks",
                    "nudge_type": NUDGE_TASK_REINFORCEMENT,
                    "nudge_key": NUDGE_TASK_REINFORCEMENT,
                    "priority": "low",
                    "message": "You're making good progress today",
                    "action": coaching.get("action", "Keep it up"),
                }

    return None
