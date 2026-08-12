# =============================================================================
# File: apps/ai/cos_services/guided_review.py
# Purpose: CoS surface for the GUIDED, one-at-a-time execution review (Blocker #15).
#   It advances a deterministic review workflow and returns the ONE item now awaiting
#   the user's answer — persisting that pending question in conversation_state so the
#   NEXT turn's short reply ("yes"/"no"/"partially"/"skip"/"stop") has an authoritative
#   referent to bind to (the exact state the stateless review was missing).
#
#   Owns no truth: the queue is re-derived each call from the Execution Review projection
#   (guided_review.next_incomplete → build_execution_review); recording happens through the
#   existing complete_execution_item router. WLJ owns the deterministic cursor + which item
#   is current; the model owns the language (asking, and interpreting the reply). Never raises.
# =============================================================================
import logging
from datetime import date as _date, timedelta

logger = logging.getLogger(__name__)


def _user_today(user):
    try:
        from apps.core.utils import get_user_today
        return get_user_today(user) or _date.today()
    except Exception:
        return _date.today()


def _resolve_day(user, day):
    today = _user_today(user)
    target = today - timedelta(days=1)  # default: yesterday (the reconciliation case)
    if day:
        try:
            from apps.core.truth.periods import resolve_date_expression
            p = resolve_date_expression(day, today)
            if p is not None:
                target = p.start
        except Exception:
            logger.warning("guided_review: date resolve failed for %r", day, exc_info=True)
    return today, target


def next_review_item(user, conversation, day=None, stop=False) -> dict:
    """Advance the guided execution review and return the next item awaiting an answer.

    * ``stop=True`` ends the review (clears the pending question).
    * Otherwise: pick the next still-incomplete item for the day that has NOT already been
      presented this session, PERSIST it as the pending question (so the next short reply
      binds to it), and return it. When nothing remains, the day is reconciled and the
      session is cleared. Never raises."""
    from apps.ai.model_interface import conversation_state as _cs
    today, target = _resolve_day(user, day)
    day_iso = target.isoformat()
    relative = ("yesterday" if target == today - timedelta(days=1)
                else "today" if target == today else day_iso)

    if stop:
        _cs.clear_guided_review(conversation)
        return {"status": "stopped", "day": day_iso, "relative": relative}

    # Load the session cursor (the keys already presented) — only if it's for THIS day.
    session = {}
    try:
        cs = _cs.read(conversation) or {}
        gr = cs.get("guided_review") or {}
        if gr.get("day") == day_iso:
            session = gr
    except Exception:
        session = {}
    asked = list(session.get("asked") or [])

    try:
        from apps.core.execution.guided_review import next_incomplete, item_key, incomplete_items
        remaining_before = len(incomplete_items(user, target))
        item = next_incomplete(user, target, asked)
    except Exception:
        logger.warning("guided_review: next item failed", exc_info=True)
        return {"status": "error", "day": day_iso,
                "message": "The review could not be advanced right now."}

    if item is None:
        _cs.clear_guided_review(conversation)
        return {"status": "reconciled", "day": day_iso, "relative": relative,
                "message": f"Every item for {relative} is reconciled."}

    key = item_key(item)
    asked.append(key)
    current = {"kind": item.get("kind", ""), "title": item.get("title", ""),
               "detail": item.get("detail", ""), "source": item.get("source", ""),
               "completion_state": item.get("detail", "") or "incomplete"}
    _cs.set_guided_review(conversation, {"day": day_iso, "relative": relative,
                                         "asked": asked, "current": current})
    return {"status": "question", "day": day_iso, "relative": relative,
            "item": current, "remaining": remaining_before}
