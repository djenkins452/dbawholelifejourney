# ==============================================================================
# File: apps/core/execution/dashboard_day_summary.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: THE single deterministic Dashboard Day Summary — facts only, read from
#              the request-path-safe SAE execution snapshot. One builder; every consumer
#              (dashboard page + Current Context provider) reads from it.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# ==============================================================================
"""Deterministic Dashboard Day Summary (facts only).

The Dashboard workspace's canonical Current Context summary. It projects the day's
execution into a compact facts-only shape the conversational model reasons over — WLJ
never renders a verdict ("behind"/"on track"); it exposes numbers and titles only.

REQUEST-PATH SAFE — the single most important property. It reads the **already-cached**
execution contract via the SAE snapshot (`get_module_state(user, 'execution',
allow_rebuild=False)`), NEVER the live `build_execution_state`/`build_today_execution`
(too expensive for Current Context resolution). If the snapshot is not yet warm it
returns `status="pending"` — it NEVER falls back to a live rebuild.

Single authority / no drift: `build_today_execution` (the one execution contract producer)
is what the SAE caches AND what the dashboard's own render is built on, so the page and
this summary are rooted in the SAME truth. This module adds NO new execution calculation,
NO new execution authority, NO new cache — it exposes existing cached truth.

Cache architecture it depends on (owned elsewhere, reused here):
  • ownership   : SAE (UserState snapshot; module key "execution").
  • producer    : build_today_execution (single execution contract authority).
  • refresh     : SAE background cycle + incremental state_updater.
  • invalidation: task/routine writes drop wlj:user_state:<id>:execution (e.g.
                  apps/life/services/routine_helpers.py).
  • runtime cost: one cached dict read (allow_rebuild=False) — no queries on miss.
"""

import logging

logger = logging.getLogger(__name__)


def _status_of(item):
    """An item's effective schedule status (facts): prefer time_status, else status."""
    return (item.get("time_status") or item.get("status") or "").strip().lower()


def build_dashboard_day_summary(user):
    """Return deterministic facts for the Dashboard workspace (facts only, never raises).

    Shape:
        {
          "status": "ready" | "pending",   # pending = SAE snapshot not warm yet
          "total": int,                    # commitments surfaced for today
          "completed": int,
          "remaining": int,
          "overdue": int,
          "upcoming": int,
          "tasks_completed_today": int,
          "by_type": {source_type: count, ...},
          "next_item": {"title": str, "time": str} | None,  # earliest not-done, timed
        }
    """
    try:
        from apps.core.ai_state.state_engine import get_module_state

        # Request-path-safe: read the SAE snapshot ONLY. Never rebuild here.
        state = get_module_state(user, "execution", allow_rebuild=False) or {}
        items = state.get("items") or []
        summaries = state.get("summaries") or {}

        if not state:
            # Snapshot not warm — honest pending state, never a live rebuild.
            return {"status": "pending", "total": 0, "completed": 0, "remaining": 0,
                    "overdue": 0, "upcoming": 0, "tasks_completed_today": 0,
                    "by_type": {}, "next_item": None}

        total = len(items)
        completed = sum(1 for i in items if i.get("completed_today"))
        overdue = sum(1 for i in items
                      if not i.get("completed_today") and _status_of(i) == "overdue")
        upcoming = sum(1 for i in items
                       if not i.get("completed_today") and _status_of(i) == "upcoming")

        by_type = {}
        for i in items:
            st = i.get("source_type") or "other"
            by_type[st] = by_type.get(st, 0) + 1

        # Earliest not-yet-completed item that carries a scheduled time (facts only —
        # NOT a prioritized "what to do now"; that stays with build_execution_state).
        timed = [i for i in items
                 if not i.get("completed_today") and (i.get("scheduled_time"))]
        timed.sort(key=lambda i: str(i.get("scheduled_time")))
        next_item = None
        if timed:
            nxt = timed[0]
            next_item = {"title": nxt.get("title") or "", "time": nxt.get("scheduled_time")}

        return {
            "status": "ready",
            "total": total,
            "completed": completed,
            "remaining": max(0, total - completed),
            "overdue": overdue,
            "upcoming": upcoming,
            "tasks_completed_today": summaries.get("tasks_completed_today", 0),
            "by_type": by_type,
            "next_item": next_item,
        }
    except Exception:  # pragma: no cover - defensive; a summary must never hard-fail
        logger.warning("build_dashboard_day_summary failed user=%s",
                       getattr(user, "id", None), exc_info=True)
        return {"status": "pending", "total": 0, "completed": 0, "remaining": 0,
                "overdue": 0, "upcoming": 0, "tasks_completed_today": 0,
                "by_type": {}, "next_item": None}
