# =============================================================================
# File: apps/core/execution/execution_review.py
# Purpose: EXECUTION REVIEW — a deterministic PROJECTION (owns ZERO truth) that
#   answers ONE question: "What represented the user's INTENDED execution for a
#   given day?" It composes the EXISTING execution truth authorities (Tasks, Faith,
#   Health/medication, Workout, Journal, scheduled routines) into one review, the
#   way a dashboard presents truth from many domains through one purpose-built view.
#   It never owns, computes, or duplicates truth — it only assembles it.
#
#   Blocker #14 (Layer 1): the CoS was reducing "yesterday's items" to Tasks because
#   there was no single reachable surface for a day's intended execution. This is that
#   surface. Read-only; never raises.
# =============================================================================
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# Routine names already represented under the Faith domain (prayer / bible), so we do
# not list them twice. Matched case-insensitively as a substring.
_FAITH_ROUTINE_WORDS = ("pray", "bible", "scripture", "devotion")


def _item(kind, title, completed, *, detail="", source=""):
    return {
        "kind": kind,
        "title": title,
        "completed": bool(completed),
        "status": "complete" if completed else "incomplete",
        "detail": detail,
        "source": source,
    }


def build_execution_review(user, target_date) -> dict:
    """Compose everything the user INTENDED to execute on `target_date` into one list.

    Returns ``{status, date, items:[{kind,title,completed,status,detail,source}], summary}``.
    A PROJECTION over existing truth (``get_execution_truth`` + ``TaskQueries``); owns no
    truth of its own. Never raises."""
    items = []
    try:
        from apps.core.execution.execution_truth_engine import get_execution_truth
        truth = get_execution_truth(user, target_date)
    except Exception:
        logger.warning("execution_review: execution truth read failed", exc_info=True)
        truth = {}

    domains = truth.get("domains") or {}

    # --- Faith: Prayer Time + Bible Reading (completion already bridged in `truth`) ------
    faith = domains.get("faith") or {}
    if faith.get("prayer_expected"):
        items.append(_item("prayer", "Prayer Time", faith.get("prayer_completed"),
                           source=faith.get("prayer_source") or ""))
    if faith.get("bible_expected"):
        items.append(_item("bible_reading", "Bible Reading",
                           faith.get("bible_reading_completed"),
                           source=faith.get("bible_source") or ""))

    # --- Workout / Journal (domain summaries) -------------------------------------------
    workout = domains.get("workout") or {}
    if workout.get("expected"):
        items.append(_item("workout", "Workout", workout.get("completed")))
    journal = domains.get("journal") or {}
    if journal.get("expected"):
        items.append(_item("journal", "Journal", journal.get("completed")))

    # --- Medications / Supplements (group level for the review) --------------------------
    meds = truth.get("medications") or {}
    if (meds.get("expected") or 0) > 0:
        items.append(_item("medications", "Medications", meds.get("all_taken"),
                           detail=f"{meds.get('taken', 0)} of {meds.get('expected', 0)} taken"))

    # --- Scheduled routines (each), minus those already listed under Faith ---------------
    routines = (truth.get("routines") or {}).get("items") or {}
    for name, r in routines.items():
        low = (name or "").lower()
        if any(w in low for w in _FAITH_ROUTINE_WORDS):
            continue  # already represented as Prayer Time / Bible Reading
        r = r or {}
        r_total = r.get("total") or 0
        detail = f"{r.get('completed', 0)} of {r_total}" if r_total else ""
        items.append(_item("routine", name, r.get("fully_complete"), detail=detail))

    # --- Tasks with due_date == target_date (occurrence-scoped completion) ---------------
    try:
        from apps.life.services.task_queries import TaskQueries
        for t in TaskQueries.completed_due_on(user, target_date):
            items.append(_item("task", getattr(t, "title", "Task"), True))
        for t in TaskQueries.due_today(user, as_of=target_date):
            items.append(_item("task", getattr(t, "title", "Task"), False))
    except Exception:
        logger.warning("execution_review: task read failed", exc_info=True)

    total = len(items)
    completed = sum(1 for it in items if it["completed"])
    date_iso = target_date.isoformat() if hasattr(target_date, "isoformat") else str(target_date)
    return {
        "status": "ready" if items else "empty",
        "date": date_iso,
        "items": items,
        "summary": {"intended": total, "completed": completed,
                    "remaining": total - completed, "fully_reconciled": total == completed},
        "note": ("Deterministic PROJECTION of what the user INTENDED to execute this day — "
                 "composed from existing truth (tasks, faith, medication, workout, journal, "
                 "routines). This surface owns no truth; it only assembles it. This is the "
                 "COMPLETE set for the day — do not go discover domains individually."),
    }
