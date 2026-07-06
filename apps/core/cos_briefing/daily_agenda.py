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


def _user_hour(user):
    try:
        from apps.core.utils import get_user_now
        return get_user_now(user).hour
    except Exception:
        return 12


def _value_key(item):
    """Executive-value sort key for a rhythm item — value DESC, chronology only as a
    tiebreaker. A routine_item/supplement never leads just because it's earliest on the
    clock (mirrors interpret()'s priority weighting; kept self-contained in core)."""
    st = (item.get("source_type") or "").lower()
    domain = (item.get("domain") or "").lower()
    if item.get("is_foundational"):
        base = 3
    elif st == "task" or domain in ("calendar", "event", "appointment"):
        base = 2
    else:                                   # routine_item / supplement_dose / med dose
        base = 0
    if (item.get("urgency") or "").lower() == "overdue" and base >= 2:
        base += 1                           # overdue bumps real commitments, not routine
    return (-base, item.get("scheduled_time") or "")


def _top_value_item(items):
    """Highest executive-VALUE incomplete item (not the earliest-scheduled)."""
    incomplete = [i for i in (items or [])
                  if not i.get("completed_today") and (i.get("title") or "").strip()]
    return sorted(incomplete, key=_value_key)[0] if incomplete else None


def _join_titles(titles):
    ts = [t for t in titles if t]
    if not ts:
        return ""
    if len(ts) == 1:
        return ts[0]
    if len(ts) == 2:
        return f"{ts[0]} and {ts[1]}"
    return ", ".join(ts[:-1]) + ", and " + ts[-1]


def _remaining_health_obligations(items):
    """Incomplete same-day HEALTH obligations (prescriptions first, then supplements) —
    what still has to happen tonight before winding down."""
    hl = [i for i in (items or [])
          if not i.get("completed_today") and (i.get("title") or "").strip()
          and (i.get("source_type") or "").lower() in ("medication_dose", "supplement_dose")]
    hl.sort(key=lambda i: 0 if (i.get("source_type") or "").lower() == "medication_dose" else 1)
    return hl


def _domain_done_today(user, domain):
    """True if the user already completed an item in `domain` today (e.g. journaling) —
    so a completed activity is never re-recommended."""
    try:
        from apps.core.cos_briefing.rhythm import build_rhythm_sections
        for sec in ((build_rhythm_sections(user) or {}).get("sections") or []):
            for it in (sec.get("items") or []):
                if it.get("completed_today") and (it.get("domain") or "").lower() == domain.lower():
                    return True
    except Exception:
        logger.warning("daily_agenda: domain-done read failed", exc_info=True)
    return False


def build_daily_agenda(user):
    """Return a deterministic daily agenda string (always non-empty). TIME-AWARE:
    in the evening it pivots to wrap-up / recovery / tomorrow and never tells the
    user to BEGIN a morning activity (Failure #1)."""
    try:
        from apps.core.cos_briefing.rhythm_api import (
            get_current_rhythm_item, get_remaining_rhythm_items,
        )
        remaining = get_remaining_rhythm_items(user) or []
        next_item = get_current_rhythm_item(user)
    except Exception:
        logger.warning("daily_agenda: rhythm api failed", exc_info=True)
        remaining, next_item = [], None

    hour = _user_hour(user)

    # ----- Evening (8 PM onward): finish remaining HEALTH obligations, then wind down.
    # Never bury same-day medication under wind-down; never label today's leftovers as
    # "tomorrow's first priority"; never re-recommend an already-completed activity. ----
    if hour >= 20:
        parts = ["It's getting late, so let's focus on wrapping up the day well."]
        health_left = _remaining_health_obligations(remaining)
        if health_left:
            names = _join_titles([i["title"].strip() for i in health_left])
            lead = "medication" if any(
                (i.get("source_type") or "").lower() == "medication_dose" for i in health_left) else "supplements"
            parts.append(f"Before you wind down, you still have {names} left to take "
                         f"tonight — finish your {lead} first; that outranks anything strategic "
                         "this late.")
        risk = _risk_clause(user)
        if risk:
            parts.append(risk + " Let that go for tonight and reset in the morning.")
        # Wind-down — completion-aware: don't suggest journaling if it's already done today.
        wind = "prepare for tomorrow and protect your sleep"
        if not _domain_done_today(user, "journal"):
            wind = "journal a few lines on how today went, " + wind
        parts.append("Then wind down: " + wind + ".")
        return " ".join(parts)

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

    # 4. Recommended next action — highest executive VALUE, not the next scheduled item.
    best_next = _top_value_item(remaining) or next_item
    if best_next and (best_next.get("title") or "").strip():
        parts.append(f"Your best next step is to begin {best_next['title'].strip()}.")

    return " ".join(parts)
