# ==============================================================================
# File: apps/core/proactive/nudge_engine.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic health nudge engine — proactive action surfacing
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-24
# ==============================================================================
"""
Deterministic Health Nudge Engine.

Generates proactive nudges based on summary, signals, and coaching state.
Nudges are surfaced WITHOUT the user asking — on dashboard load or periodic
background checks.

Architecture: state → signals → summary → coaching → THIS → UI

Public API:
    generate_health_nudge(summary, signals, coaching, current_dt,
                          last_nudges=None) -> dict | None

Rules:
    - Pure function: no DB queries, no user object, no cache writes, no LLM
    - Reuses existing coaching output — does NOT duplicate logic
    - Respects frequency limits (deduplication)
    - Returns None when no nudge is needed
"""

import logging

logger = logging.getLogger(__name__)

# ── Nudge types ──────────────────────────────────────────────────────────────

NUDGE_MED_OVERDUE = "med_overdue"
NUDGE_SIGNAL_DECLINE = "signal_decline"
NUDGE_REINFORCEMENT = "reinforcement"

# ── Frequency limits (minutes) ──────────────────────────────────────────────

_FREQUENCY_LIMITS = {
    NUDGE_MED_OVERDUE: 60,        # max once per 60 minutes
    NUDGE_SIGNAL_DECLINE: 1440,   # max once per day (1440 min)
    NUDGE_REINFORCEMENT: 1440,    # max once per day
}

# Signal states that trigger a decline nudge
_DECLINE_STATES = frozenset({"declining", "poor", "unstable", "low", "watch"})


def _is_within_frequency(nudge_type, last_nudges, current_dt, signal_key=None):
    """
    Check if a nudge of this type was sent too recently.

    Args:
        nudge_type: one of the NUDGE_* constants
        last_nudges: dict of {nudge_key: ISO timestamp string} or None
        current_dt: current aware datetime
        signal_key: optional signal-specific key for signal nudges

    Returns:
        True if a nudge of this type is within the frequency limit (suppress it)
    """
    if not last_nudges:
        return False

    # Build lookup key
    lookup_key = nudge_type
    if signal_key:
        lookup_key = f"{nudge_type}_{signal_key}"

    last_sent_str = last_nudges.get(lookup_key)
    if not last_sent_str:
        return False

    try:
        from django.utils.dateparse import parse_datetime
        last_sent = parse_datetime(str(last_sent_str))
        if last_sent is None:
            return False
        # Make timezone-aware if needed
        if last_sent.tzinfo is None and current_dt.tzinfo is not None:
            from django.utils.timezone import make_aware
            last_sent = make_aware(last_sent)
        elif last_sent.tzinfo is not None and current_dt.tzinfo is None:
            last_sent = last_sent.replace(tzinfo=None)

        from datetime import timedelta
        limit_minutes = _FREQUENCY_LIMITS.get(nudge_type, 60)
        elapsed = (current_dt - last_sent).total_seconds() / 60
        return elapsed < limit_minutes
    except Exception:
        return False


def _nudge(nudge_type, priority, message, action, nudge_key=None):
    """Build a nudge dict."""
    return {
        "type": "health",
        "nudge_type": nudge_type,
        "nudge_key": nudge_key or nudge_type,
        "priority": priority,
        "message": message,
        "action": action,
    }


def generate_health_nudge(summary, signals, coaching, current_dt,
                           last_nudges=None):
    """
    Generate a proactive health nudge if one is warranted.

    Args:
        summary: dict from build_health_priority_summary()
        signals: list of signal dicts from build_health_signals()
        coaching: dict from build_health_coaching() (with time-awareness applied)
        current_dt: user's current local aware datetime
        last_nudges: dict of {nudge_key: ISO timestamp} for deduplication

    Returns:
        dict with type, nudge_type, priority, message, action — or None
    """
    if not summary or not coaching or not current_dt:
        return None

    signals = signals or []
    last_nudges = last_nudges or {}
    items = summary.get("items", [])
    flags = summary.get("flags", {})

    # ── NUDGE 1: Overdue medications (HIGH, always wins) ──
    if flags.get("has_medication_risk"):
        overdue_items = [i for i in items if i["key"] == "medications_overdue"]
        if overdue_items:
            if not _is_within_frequency(NUDGE_MED_OVERDUE, last_nudges, current_dt):
                return _nudge(
                    NUDGE_MED_OVERDUE,
                    "high",
                    "You have medications overdue",
                    "Take them now",
                )

    # ── NUDGE 2: Declining signal (MEDIUM, max once/day per signal) ──
    # Priority order matches signal priority
    _SIGNAL_PRIORITY = ["med_adherence", "cardio_stability",
                        "activity_momentum", "sleep_recovery"]

    for sig_key in _SIGNAL_PRIORITY:
        sig = next((s for s in signals if s["key"] == sig_key), None)
        if sig is None:
            continue

        state = sig.get("state", "")
        trend = sig.get("trend", "")
        if state not in _DECLINE_STATES and trend not in _DECLINE_STATES:
            continue

        nudge_key = f"{NUDGE_SIGNAL_DECLINE}_{sig_key}"
        if _is_within_frequency(
            NUDGE_SIGNAL_DECLINE, last_nudges, current_dt,
            signal_key=sig_key,
        ):
            continue

        insight = sig.get("insight", "")
        action = coaching.get("action", "")

        return _nudge(
            NUDGE_SIGNAL_DECLINE,
            "medium",
            insight or "A health trend needs attention this week",
            action,
            nudge_key=nudge_key,
        )

    # ── NUDGE 3: Reinforcement (LOW, max once/day) ──
    # Only when everything is stable — encourage consistency
    priority_level = summary.get("priority_level", "low")
    if priority_level == "low" and not flags.get("has_urgent"):
        if not _is_within_frequency(NUDGE_REINFORCEMENT, last_nudges, current_dt):
            action = coaching.get("action", "Stay consistent with your routine today")
            return _nudge(
                NUDGE_REINFORCEMENT,
                "low",
                "Everything is on track",
                action,
            )

    # No nudge needed
    return None
