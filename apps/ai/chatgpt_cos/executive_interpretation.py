# ==============================================================================
# File: apps/ai/chatgpt_cos/executive_interpretation.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Executive Interpretation Engine (P33). A DETERMINISTIC judgment layer
#   that converts raw deterministic facts into EXECUTIVE SIGNALS *before* they reach
#   the Conversation Planner / Executive Brief Composer. It is NOT a planner, engine,
#   composer, or prioritizer — it reuses existing deterministic providers (TaskQueries
#   horizons, health/goals SAE state, executive_summary) and INTERPRETS them like a
#   Chief of Staff would: workload is today's commitments + overdue (NOT total pending
#   count); a strategic backlog is never an overload conclusion. Output: ExecutiveSignals.
# ==============================================================================
import logging
from dataclasses import dataclass, asdict, field

logger = logging.getLogger(__name__)


@dataclass
class ExecutiveSignals:
    workload: str = "light"            # light|manageable|full|heavy|overloaded
    workload_summary: str = ""         # narration: "1 due today; 21 open are backlog"
    today_count: int = 0
    overdue_count: int = 0
    soon_count: int = 0                # due within 7 days (near-term)
    backlog_count: int = 0            # no due date — strategic/someday
    total_pending: int = 0
    cognitive_load: str = "low"        # low|moderate|high
    recovery_needed: bool = False
    health_read: str = "stable"        # improving|stable|declining
    biggest_risk: str = ""
    highest_leverage: str = ""
    strategic_focus: str = ""
    intervention_required: bool = False
    confidence: str = "medium"         # low|medium|high
    headline: str = ""                 # the one-line executive thesis

    def to_dict(self):
        return asdict(self)


def _text(item):
    if not item:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return (item.get("message") or item.get("title") or item.get("phrase")
                or item.get("concern") or "").strip()
    return str(item).strip()


# ── Existing deterministic providers (reused; never duplicated) ────────────
def _task_horizons(user):
    """Task counts BY HORIZON via the canonical TaskQueries — the executive unit,
    not a single 'pending' lump. Defensive: any failure yields zeros."""
    out = {"today": 0, "overdue": 0, "soon": 0, "backlog": 0, "total": 0}
    try:
        from datetime import timedelta
        from apps.life.services.task_queries import TaskQueries
        from apps.core.utils import get_user_now
        now = get_user_now(user)
        out["today"] = TaskQueries.due_today(user).count()
        out["overdue"] = TaskQueries.overdue(user).count()
        out["soon"] = TaskQueries.due_within(user, now + timedelta(days=7)).count()
        out["backlog"] = TaskQueries.no_due_date(user).count()
        out["total"] = TaskQueries.pending(user).count()
    except Exception:
        logger.warning("interpretation: task horizons failed", exc_info=True)
    return out


def _exec_summary(user):
    try:
        from apps.core.cos_briefing.executive_summary import build_executive_summary
        es = build_executive_summary(user)
        return es if isinstance(es, dict) else {}
    except Exception:
        logger.warning("interpretation: exec summary failed", exc_info=True)
        return {}


def _health_read(user):
    out = {"recovery_needed": False, "read": "stable", "note": ""}
    try:
        from apps.ai.cos_services import get_domain_state
        h = (get_domain_state(user, "health").get("state") or {})
        sleep = h.get("sleep_last_night_hours") or h.get("sleep_avg_hours_7d")
        if isinstance(sleep, (int, float)) and 0 < sleep < 6.5:
            out["recovery_needed"] = True
            out["note"] = "sleep is short"
        trend = (h.get("weight_trend") or "").lower()
        if "down" in trend or "improv" in trend:
            out["read"] = "improving"
    except Exception:
        logger.warning("interpretation: health read failed", exc_info=True)
    return out


def _strategic_focus(user):
    try:
        from apps.ai.cos_services import get_domain_state
        st = (get_domain_state(user, "purpose").get("state") or {})
        m = st.get("mission")
        if isinstance(m, dict):
            return m.get("title") or ""
    except Exception:
        pass
    return ""


# ── Interpretation (the JUDGMENT — workload from horizon, not count) ───────
def _interpret_workload(tw):
    """Workload = what actually demands attention TODAY (due today + overdue) — NOT
    the total pending count. A strategic/someday backlog is not today's workload."""
    active = tw["today"] + tw["overdue"]
    if active == 0:
        wl = "light"
    elif active <= 3:
        wl = "manageable"
    elif active <= 6:
        wl = "full"
    elif active <= 10:
        wl = "heavy"
    else:
        wl = "overloaded"
    strategic = max(0, tw["total"] - active)
    parts = []
    if tw["today"]:
        parts.append(f"{tw['today']} due today")
    if tw["overdue"]:
        parts.append(f"{tw['overdue']} overdue")
    if not parts:
        parts.append("nothing due today")
    summary = "; ".join(parts)
    if strategic > 0:
        summary += (f"; the other {strategic} open item"
                    f"{'s are' if strategic != 1 else ' is'} upcoming or longer-term "
                    "backlog, not today's load")
    return wl, summary


def _cognitive_load(tw, health):
    active = tw["today"] + tw["overdue"]
    if health["recovery_needed"] and active >= 3:
        return "high"
    if active <= 2:
        return "low"
    if active <= 6:
        return "moderate"
    return "high"


def _headline(workload, recovery, has_backlog):
    if workload in ("light", "manageable") and has_backlog:
        base = f"Today's workload is {workload} despite a healthy strategic backlog"
    elif workload in ("heavy", "overloaded"):
        base = f"Today is a {workload} day — guard your focus"
    elif workload in ("light", "manageable"):
        base = f"Today's workload is {workload}"
    else:
        base = f"Today is a {workload} day"
    if recovery:
        base += ("; recovery is today's limiting factor, so protect your energy "
                 "before pushing performance")
    return base + "."


def interpret(user):
    """Produce ExecutiveSignals from existing deterministic facts. Deterministic,
    request-path-safe, degrades gracefully."""
    tw = _task_horizons(user)
    es = _exec_summary(user)
    health = _health_read(user)

    workload, wsummary = _interpret_workload(tw)
    has_backlog = (tw["total"] - (tw["today"] + tw["overdue"])) >= 3
    recovery = health["recovery_needed"]

    biggest_risk = _text(es.get("biggest_risk"))
    if not biggest_risk and recovery:
        biggest_risk = "sleep debt is the main thing to watch"

    recs = es.get("recommendations") or []
    highest_leverage = next((_text(x) for x in recs if _text(x)), "")
    if not highest_leverage and recovery:
        highest_leverage = "protecting your sleep and energy today"

    strategic = _strategic_focus(user)
    # Intervention is a JUDGMENT, not a count: only real risk warrants it, never a
    # large-but-harmless backlog.
    intervention = (tw["overdue"] >= 5 or workload == "overloaded"
                    or bool(es.get("biggest_risk")))
    confidence = "high" if (tw["total"] or es) else "low"

    return ExecutiveSignals(
        workload=workload, workload_summary=wsummary,
        today_count=tw["today"], overdue_count=tw["overdue"], soon_count=tw["soon"],
        backlog_count=tw["backlog"], total_pending=tw["total"],
        cognitive_load=_cognitive_load(tw, health), recovery_needed=recovery,
        health_read=health["read"], biggest_risk=biggest_risk,
        highest_leverage=highest_leverage, strategic_focus=strategic,
        intervention_required=intervention, confidence=confidence,
        headline=_headline(workload, recovery, has_backlog))
