# ==============================================================================
# File: apps/ai/deterministic_health_summary.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Fast deterministic health summary — skips LLM for metric queries
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-11
# ==============================================================================
"""
Deterministic Health Summary — sub-second health status responses.

When a user asks a health-focused check-in question like "how have I been
doing overall?" or "how's my health?", the full CoS pipeline spends 15-30s
building context across ALL domains, calling the embedding API for semantic
memory, and then asking gpt-4o to restate 4 pre-computed numbers.

This module short-circuits that entire path by:
1. Detecting health-focused check-in messages (lexical, no LLM)
2. Reading pre-computed metrics from SAE state (single cached DB hit)
3. Formatting a warm, conversational response deterministically

Total latency: ~200ms instead of ~15-30s.

Public API:
    is_health_summary_query(message: str) -> bool
    build_health_summary_response(user) -> str | None
"""

import logging

logger = logging.getLogger(__name__)

# =========================================================================
# Health Summary Query Detection (lexical — no LLM)
# =========================================================================

# Health-domain keywords that distinguish "how am I doing with health?"
# from "how am I doing with my tasks?"
_HEALTH_KEYWORDS = frozenset({
    'health', 'weight', 'workout', 'workouts', 'exercise',
    'sleep', 'glucose', 'blood sugar', 'fitness', 'vitals',
    'body', 'nutrition', 'diet', 'calories', 'protein',
    'steps', 'heart rate', 'blood pressure', 'fasting',
    'medication', 'meds', 'medicine',
})

# Check-in intent phrases — user is asking for a status summary
_SUMMARY_INTENT_PHRASES = frozenset({
    'how have i been doing',
    'how am i doing',
    "how's my health",
    'how is my health',
    'my health',
    'health summary',
    'health status',
    'health update',
    'health check',
    'health overview',
    'how have i been',
    'my progress',
    'my fitness',
    'how am i progressing',
    'overall health',
    'health report',
    'wellness update',
    'wellness summary',
    'give me my health',
    'give me my stats',
    'my stats',
    'my numbers',
    'my metrics',
    'how are my numbers',
    'how are my stats',
    'how are my metrics',
    'where do i stand with my health',
    'health snapshot',
})


def is_health_summary_query(message: str) -> bool:
    """
    Detect if a message is a health-focused summary query that can be
    answered deterministically without an LLM call.

    Must match BOTH conditions:
    1. Contains a summary intent phrase (asking for status/overview)
    2. Contains a health keyword OR the intent phrase itself is health-specific

    This intentionally has a narrow match to avoid false positives.
    If it doesn't match, the message falls through to the normal LLM path.

    Args:
        message: User's raw message text.

    Returns:
        True if this is a health summary query.
    """
    if not message:
        return False

    msg_lower = message.lower()

    # Check for health-specific intent phrases (these are inherently health-scoped)
    _health_specific_intents = {
        "how's my health", 'how is my health', 'health summary',
        'health status', 'health update', 'health check', 'health overview',
        'health report', 'wellness update', 'wellness summary',
        'give me my health', 'give me my stats', 'my stats', 'my numbers',
        'my metrics', 'how are my numbers', 'how are my stats',
        'how are my metrics', 'where do i stand with my health',
        'health snapshot', 'my fitness',
    }
    if any(phrase in msg_lower for phrase in _health_specific_intents):
        return True

    # Check for general summary intent + health keyword
    _general_intents = {
        'how have i been doing', 'how am i doing', 'how have i been',
        'my progress', 'how am i progressing', 'overall',
    }
    has_summary_intent = any(phrase in msg_lower for phrase in _general_intents)
    has_health_keyword = any(kw in msg_lower for kw in _HEALTH_KEYWORDS)

    return has_summary_intent and has_health_keyword


# =========================================================================
# Deterministic Response Builder
# =========================================================================

def build_health_summary_response(user) -> str:
    """
    Build a complete health summary response from pre-computed SAE state.

    Reads from the SAE state cache (single DB hit, already loaded during
    CoS context build). Returns a warm, formatted response covering all
    available health metrics.

    Args:
        user: Django User instance.

    Returns:
        str — formatted health summary response, or None if insufficient data.
    """
    try:
        from apps.core.ai_state.state_engine import (
            get_module_state,
            get_state_value,
        )

        health = get_module_state(user, 'health') or {}
        fitness = get_module_state(user, 'fitness') or {}

        # Phase 5: explicit reader gate. If the health builder returned
        # {"enabled": False}, the dict is technically truthy (one key)
        # so the legacy `if not health and not fitness` check would let
        # it through and produce a summary full of "None" sections.
        # Bail cleanly with a friendly message instead.
        if health.get('enabled') is False:
            return (
                "Health tracking is turned off right now, so I don't have "
                "a summary to show. Flip it back on in Settings if you'd "
                "like one."
            )

        # Bail if we have no health data at all
        if not health and not fitness:
            return None

        sections = []

        # ── Weight ──────────────────────────────────────────────
        weight = health.get('weight_current')
        if weight is not None:
            unit = health.get('weight_unit', 'lb')
            unit_label = 'lbs' if unit == 'lb' else 'kg'
            trend = health.get('weight_trend', '')
            trend_str = ''
            if trend == 'decreasing':
                trend_str = ' (trending down)'
            elif trend == 'increasing':
                trend_str = ' (trending up)'
            elif trend == 'stable':
                trend_str = ' (stable)'
            sections.append(f"**Weight:** {weight:.1f} {unit_label}{trend_str}")

            # Weight goal context
            goal = health.get('weight_goal')
            if goal is not None:
                remaining = health.get('weight_goal_remaining')
                on_track = health.get('weight_goal_on_track')
                goal_unit = health.get('weight_goal_unit', 'lb')
                goal_label = 'lbs' if goal_unit == 'lb' else 'kg'
                if remaining is not None:
                    track_str = 'on track' if on_track else 'behind pace'
                    sections.append(
                        f"**Goal:** {goal:.0f} {goal_label} "
                        f"({abs(remaining):.1f} {goal_label} to go, {track_str})"
                    )

        # ── Workouts ────────────────────────────────────────────
        workouts_7d = fitness.get('workouts_7d', 0)
        if workouts_7d > 0:
            session_word = 'session' if workouts_7d == 1 else 'sessions'
            workout_str = f"**Workouts:** {workouts_7d} {session_word} this week"
            minutes = fitness.get('workout_minutes_7d')
            if minutes:
                workout_str += f" ({minutes} min total)"
            sections.append(workout_str)

        # ── Sleep ───────────────────────────────────────────────
        sleep_min = health.get('sleep_avg_duration_7d')
        if sleep_min is not None:
            sleep_hrs = round(float(sleep_min) / 60, 1)
            trend = health.get('sleep_trend', '')
            trend_str = ''
            if trend and trend != 'insufficient_data':
                trend_str = f' ({trend})'
            sections.append(f"**Sleep:** {sleep_hrs} hrs average{trend_str}")

        # ── Steps ───────────────────────────────────────────────
        steps = health.get('steps_avg_7d')
        if steps is not None:
            sections.append(f"**Steps:** {int(steps):,}/day average")

        # ── Glucose ─────────────────────────────────────────────
        glucose = health.get('glucose_avg_7d')
        if glucose is not None:
            sections.append(f"**Glucose:** {int(glucose)} mg/dL average")

        # ── Heart Rate ──────────────────────────────────────────
        hr = health.get('heart_rate_avg_7d')
        if hr is not None:
            sections.append(f"**Heart Rate:** {int(hr)} bpm average")

        # ── Blood Pressure ──────────────────────────────────────
        bp_sys = health.get('bp_systolic')
        bp_dia = health.get('bp_diastolic')
        if bp_sys and bp_dia:
            sections.append(f"**Blood Pressure:** {bp_sys}/{bp_dia}")

        # ── Blood Oxygen ────────────────────────────────────────
        spo2 = health.get('blood_oxygen_avg_7d')
        if spo2 is not None:
            sections.append(f"**Blood Oxygen:** {spo2:.1f}%")

        # ── Medication Adherence ────────────────────────────────
        try:
            from apps.core.ai_state.state_engine import get_module_state as _gms
            # Phase 4: the correct state module is `medicine` (not
            # `medication`) and the correct key is `adherence_7d` (not
            # `adherence_pct_7d`). Before the fix this block was dead —
            # it always got {} from the wrong module and the medication
            # adherence line never appeared in the deterministic summary.
            med_state = _gms(user, 'medicine') or {}
            adherence = med_state.get('adherence_7d')
            if adherence is not None:
                sections.append(f"**Medication Adherence:** {adherence:.0f}%")
        except Exception:
            pass

        if not sections:
            return None

        # ── Assemble response ───────────────────────────────────
        # Build a warm, brief response that sounds like the CoS
        header = "Here's your health snapshot for the past week:"
        metrics = '\n'.join(sections)

        # Add a brief encouragement based on data
        encouragement = _pick_encouragement(health, fitness)

        response = f"{header}\n\n{metrics}"
        if encouragement:
            response += f"\n\n{encouragement}"

        return response

    except Exception as e:
        logger.warning(
            "Deterministic health summary failed for user=%s: %s",
            getattr(user, 'id', '?'), e, exc_info=True,
        )
        return None


def _pick_encouragement(health: dict, fitness: dict) -> str:
    """Pick a brief, data-driven encouragement line."""
    weight_trend = health.get('weight_trend')
    workouts = fitness.get('workouts_7d', 0)
    sleep_min = health.get('sleep_avg_duration_7d')

    if weight_trend == 'decreasing' and workouts >= 3:
        return "You're putting in the work and it's showing. Keep it up."
    elif workouts >= 5:
        return "Impressive workout consistency this week."
    elif weight_trend == 'decreasing':
        return "The weight trend is heading the right direction."
    elif sleep_min and float(sleep_min) >= 420:  # 7+ hours
        return "Good sleep foundation this week."
    elif workouts >= 3:
        return "Solid week of training."

    return "Want me to dig deeper into any of these areas?"
