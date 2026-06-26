# ==============================================================================
# File: apps/core/cos_briefing/daily_agenda.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deterministic Daily Agenda synthesis from canonical engines (P24).
# ==============================================================================
"""
build_daily_agenda(user) — a deterministic, Chief-of-Staff-voiced daily agenda.

Synthesized ONLY from canonical engines — NO new truth, NO independent
re-computation (P24), NO OpenAI:
  * Rhythm API (schedule / upcoming / next)          -> upcoming items, next step
  * get_next_action (Focus Right Now / urgency)      -> highest priority
  * build_rhythm_sections totals (overdue / at_risk)  -> conflicts / risks
  * build_executive_summary (trajectory)              -> on-track status

Beth speaks as if she already knows — never "your dashboard", never "go look",
never "ask me again". WLJ owns truth; Beth owns synthesis.
"""

import logging

logger = logging.getLogger(__name__)


def _fmt_time(hhmm):
    try:
        from apps.core.cos_briefing.rhythm import _format_time_12h
        return _format_time_12h(hhmm) or hhmm
    except Exception:
        return hhmm


def _fmt_upcoming(items):
    """'Prayer Time at 5:30 AM, then Workout, then Lunch.'"""
    parts = []
    for i, it in enumerate(items):
        title = (it.get("title") or "").strip()
        if not title:
            continue
        t = it.get("scheduled_time")
        if i == 0 and t:
            parts.append(f"{title} at {_fmt_time(t)}")
        else:
            parts.append(title)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return parts[0] + "".join(", then " + p for p in parts[1:])


def _focus_now_title(user):
    """Highest priority = the canonical Focus-Right-Now (urgency selector)."""
    try:
        from apps.core.execution.execution_state import build_execution_state
        from apps.core.execution.selectors import get_next_action
        decision = get_next_action(build_execution_state(user)) or {}
        return ((decision.get("primary_action") or {}).get("title") or "").strip() or None
    except Exception:
        logger.warning("daily_agenda: focus_now failed", exc_info=True)
        return None


def _risk_clause(user):
    """Conflicts / overdue / at-risk from the canonical rhythm totals."""
    try:
        from apps.core.cos_briefing.rhythm import build_rhythm_sections
        totals = (build_rhythm_sections(user) or {}).get("totals") or {}
        overdue = int(totals.get("overdue") or 0)
        at_risk = int(totals.get("at_risk") or 0)
    except Exception:
        return None
    if not overdue and not at_risk:
        return "You're on track — nothing overdue or at risk."
    bits = []
    if overdue:
        bits.append(f"{overdue} overdue")
    if at_risk:
        bits.append(f"{at_risk} at risk")
    return "Watch out: you have " + " and ".join(bits) + " right now."


def build_daily_agenda(user):
    """Return a deterministic daily agenda string (always non-empty)."""
    try:
        from apps.core.cos_briefing.rhythm_api import (
            get_current_rhythm_item, get_remaining_rhythm_items,
        )
        remaining = get_remaining_rhythm_items(user) or []
        next_item = get_current_rhythm_item(user)
    except Exception:
        logger.warning("daily_agenda: rhythm api failed", exc_info=True)
        remaining, next_item = [], None

    parts = []

    # 1. Upcoming scheduled items.
    upcoming = _fmt_upcoming(remaining[:3])
    if upcoming:
        parts.append(f"Coming up today you have {upcoming}.")
    else:
        parts.append("You're all caught up on today's rhythm — nothing scheduled is left.")

    # 2. Highest priority (Focus Right Now / urgency).
    focus = _focus_now_title(user)
    if focus:
        parts.append(f"Your highest priority is {focus}.")

    # 3. Conflicts / overdue / risks.
    risk = _risk_clause(user)
    if risk:
        parts.append(risk)

    # 4. Recommended next action (next scheduled rhythm item).
    if next_item and (next_item.get("title") or "").strip():
        parts.append(f"Your best next step is to begin {next_item['title'].strip()}.")

    return " ".join(parts)
