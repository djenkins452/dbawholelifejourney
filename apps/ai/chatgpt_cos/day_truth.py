# ==============================================================================
# File: apps/ai/chatgpt_cos/day_truth.py
# Capability: DETERMINISTIC DAY-TRUTH ACCESSORS for recommendations.
#
# Before Beth recommends a day-action (a workout, "focus on protein"), she MUST read
# what is actually planned/known from deterministic providers — never infer it from a
# health GOAL. Production failure: Beth recommended "strength training" (inferred from
# a muscle-loss goal risk) on a day whose ACTUAL scheduled workout was Cardio at 6pm.
#
# This module is a thin, read-only projection over EXISTING deterministic providers
# (the rhythm/execution pipeline sourced from WorkoutSchedule → CalendarEvent, and the
# dietary profile). WLJ owns the truth; this just exposes it in the shape the CoS
# recommendation path needs. No new intelligence, no new source of truth.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)


def _title_type(title):
    """"Workout: Cardio" → "cardio"; "Bike Ride" → "bike ride". The modality the user
    actually has planned, never one inferred from a goal."""
    t = (title or "").strip()
    if ":" in t:
        t = t.split(":", 1)[1].strip()
    return t.lower()


def todays_planned_workout(user):
    """The user's ACTUAL planned workout for today from the deterministic rhythm/
    execution pipeline (WorkoutSchedule → CalendarEvent projection), or None when
    nothing is scheduled. Read-only; never raises.

    Returns {"title", "type", "time", "completed"} — e.g.
    {"title": "Workout: Cardio", "type": "cardio", "time": "6:00 PM", "completed": False}.
    """
    try:
        from apps.core.cos_briefing.rhythm_api import get_remaining_rhythm_items
        items = get_remaining_rhythm_items(user) or []
    except Exception:
        logger.warning("day_truth: rhythm items failed", exc_info=True)
        return None
    for it in items:
        if not isinstance(it, dict):
            continue
        domain = (it.get("domain") or "").lower()
        title = (it.get("title") or "").strip()
        if domain == "workout" or title.lower().startswith("workout"):
            raw = it.get("scheduled_time") or ""
            return {
                "title": title,
                "type": _title_type(title),
                "time": _fmt_time(raw),
                "completed": bool(it.get("completed_today")),
            }
    return None


def _fmt_time(raw):
    """"18:00" → "6:00 PM". Empty/unparseable → ""."""
    raw = (raw or "").strip()
    if not raw:
        return ""
    try:
        from apps.core.cos_briefing.daily_agenda import _fmt_time as _f
        return _f(raw)
    except Exception:
        return raw


def protein_options(user):
    """Two or three CONCRETE, dietary-appropriate high-protein foods to make "focus on
    protein" actionable. Grounded in the user's deterministic DietaryProfile when
    present (vegetarian / diabetes-sensitive), else a sensible default. Read-only,
    never raises — returns a short human phrase like "eggs, Greek yogurt, or a protein
    shake"."""
    flags, diabetes = set(), False
    try:
        from apps.meals.models import DietaryProfile
        prof = DietaryProfile.objects.filter(user=user).first()
        if prof:
            flags = {str(f).lower() for f in (prof.dietary_flags or [])}
            diabetes = bool(prof.diabetes_sensitive)
    except Exception:
        logger.warning("day_truth: dietary profile read failed", exc_info=True)

    if "vegan" in flags:
        opts = ["tofu", "lentils", "a plant protein shake", "edamame"]
    elif flags & {"vegetarian", "pescatarian"}:
        opts = ["Greek yogurt", "eggs", "cottage cheese", "a protein shake"]
    else:
        opts = ["eggs", "Greek yogurt", "grilled chicken", "a protein shake"]
    if diabetes and "vegan" not in flags:
        # Favor lower-carb, protein-dense picks first for a diabetes-sensitive profile.
        opts = ["eggs", "cottage cheese", "grilled chicken", "Greek yogurt"]
    picks = opts[:3]
    return ", ".join(picks[:-1]) + ", or " + picks[-1]
