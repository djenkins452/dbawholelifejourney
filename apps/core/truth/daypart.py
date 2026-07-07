# ==============================================================================
# File: apps/core/truth/daypart.py
# Capability: EXECUTIVE STANCE — the canonical situational grounding of the day.
#
# A Chief of Staff does not speak the same way at every hour. In the morning she
# PLANS the day; at midday she drives EXECUTION; in the evening she helps LAND the
# day; at night she CLOSES IT OUT — reflection and rest, never a fresh plan. The
# same question — "How am I doing today?" — demands a different POSTURE at 8am than
# at 10pm. A human CoS knows this without being told; Beth must too.
#
# Before this module the codebase computed "part of day" in three independent places
# (response_coherence.part_of_day for wording, executive_brief._rhythm_split for the
# agenda tail, reasoning/stages for nutrition) — each with a different bucketing and
# NONE carrying an executive STANCE. So a bedtime "How am I doing?" produced a morning
# planning narrative welded to a bedtime wind-down tail: internally incoherent.
#
# This is the ONE deterministic source of truth for the day's execution phase AND the
# executive stance it implies. Every narrative composer (the deterministic executive
# brief, the LLM reasoner) consults it so Beth's posture always matches the clock.
# Wording-level coherence (greeting/"this morning" re-grounding) remains the job of
# response_coherence; this module governs the higher-order STANCE, not the phrasing.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)

# ── Execution phases of the day (by the user's LOCAL hour) ───────────────────
MORNING = "morning"        # start of day
MIDDAY = "midday"          # the working middle
EVENING = "evening"        # the day is winding down
NIGHT = "night"            # the day is over

# ── Executive stances (what posture Beth holds) ──────────────────────────────
PLAN = "plan"              # orient the day, set focus
EXECUTE = "execute"        # drive momentum, what still needs doing
WIND_DOWN = "wind_down"    # help land the day, ease off
CLOSE_OUT = "close_out"    # the day is done — reflect and rest, never re-plan

# Phase → stance. One phase, one stance; no consumer re-derives this mapping.
_PHASE_STANCE = {
    MORNING: PLAN,
    MIDDAY: EXECUTE,
    EVENING: WIND_DOWN,
    NIGHT: CLOSE_OUT,
}

# The governing POSTURE directive handed to any narrator (deterministic or LLM). It
# tells the composer what conversation to have — and, as importantly, what NOT to say
# at this hour. This is the text that stops a bedtime answer from planning the day.
_POSTURE = {
    PLAN: (
        "It is the START of the user's day. Orient them to what matters today and "
        "help them set focus. Do NOT talk about winding down, resting, or closing "
        "out the day — the day is just beginning."
    ),
    EXECUTE: (
        "It is the MIDDLE of the user's working day. Focus on momentum and what "
        "still needs to get done, with the time that's left. Do NOT open the day as "
        "if it were morning, and do NOT close it out as if it were over."
    ),
    WIND_DOWN: (
        "It is the EVENING and the day is winding down. Help the user land the day — "
        "name only what still genuinely matters tonight — and begin easing off. Do "
        "NOT plan a fresh day, and do NOT tell them to catch up on what didn't happen."
    ),
    CLOSE_OUT: (
        "It is NIGHT — the user's day is effectively over. Reflect on how the day "
        "went, acknowledge what they did, and help them rest. NEVER plan the day, "
        "tell them what to focus on today, tell them not to fall behind, or frame the "
        "day as still in progress — the day is already closing. Keep it short and calm."
    ),
}


def _hour(user, now=None):
    """The user's current LOCAL hour (0–23). Never raises."""
    if now is None:
        from apps.core.utils import get_user_now
        now = get_user_now(user)
    return now.hour


def phase_of_day(user, now=None):
    """The user's current execution PHASE — the single source of truth.

    Buckets (local hour): 4–11 morning · 11–17 midday · 17–21 evening · else night
    (21–04). Night deliberately wraps midnight so the small hours read as the END of
    the prior day, not the start of a new one.
    """
    h = _hour(user, now)
    if 4 <= h < 11:
        return MORNING
    if 11 <= h < 17:
        return MIDDAY
    if 17 <= h < 21:
        return EVENING
    return NIGHT


def executive_stance(user, now=None):
    """The executive STANCE implied by the current phase (plan/execute/wind_down/
    close_out). What posture Beth should hold right now."""
    return _PHASE_STANCE[phase_of_day(user, now)]


def posture_directive(stance):
    """The governing instruction for a narrator holding `stance` — what conversation
    to have and, crucially, what NOT to say at this hour."""
    return _POSTURE.get(stance, "")


def resolve(user, now=None):
    """The canonical situational read, in one call. Returns a plain dict so it can be
    dropped straight into working memory or an ExecutiveSignals field with no import
    coupling. Never raises — on failure it degrades to a neutral EXECUTE stance so a
    narrator always has a coherent posture.

    {
      "phase":   "morning"|"midday"|"evening"|"night",
      "stance":  "plan"|"execute"|"wind_down"|"close_out",
      "hour":    int,                # user-local hour
      "is_close_out": bool,          # convenience: the day is over
      "posture": str,                # the governing directive for the narrator
    }
    """
    try:
        h = _hour(user, now)
        phase = phase_of_day(user, now)
        stance = _PHASE_STANCE[phase]
        return {
            "phase": phase,
            "stance": stance,
            "hour": h,
            "is_close_out": stance == CLOSE_OUT,
            "posture": _POSTURE[stance],
        }
    except Exception:
        logger.warning("daypart.resolve failed; defaulting to execute", exc_info=True)
        return {
            "phase": MIDDAY, "stance": EXECUTE, "hour": None,
            "is_close_out": False, "posture": _POSTURE[EXECUTE],
        }
