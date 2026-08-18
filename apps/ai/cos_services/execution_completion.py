# =============================================================================
# File: apps/ai/cos_services/execution_completion.py
# Purpose: CoS action surface for the Execution Completion router (Blocker #14,
#   Layer 2). Resolves the day (a natural phrase, default yesterday) and records
#   the item's completion ON THE ACTUAL DATE via the core router, which reuses the
#   existing per-domain writes. Owns no completion logic of its own. Never raises.
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


def complete_execution_item(user, kind=None, title=None, day=None, content=None,
                            source_type=None, source_id=None, undo=False) -> dict:
    """Canonical model-facing completion verb for execution items.

    TWO entry shapes, one authority:

      * IDENTITY-FIRST (preferred) — `source_type` + `source_id` straight from execution
        truth / Current Context. Identity establishes the EXACT occurrence, so there is
        no title rediscovery and NO default-day inference: `day` defaults to TODAY,
        because a current action is today's occurrence. This is the path for
        "Mark Shower complete" while Shower is the visible current action.

      * LEGACY kind + title — retained UNCHANGED for the retrospective
        `get_execution_review` reconciliation flow, including its `day` default of
        YESTERDAY. Do not collapse the two defaults: they answer different questions
        ("what am I doing now" vs "what did I already do yesterday").
    """
    if source_type and source_id is not None:
        # `title` (when the model supplies it) is the REQUESTED TARGET — used only to
        # verify the identity points at what the user asked for. It never selects.
        return _complete_by_identity(user, source_type, source_id, day,
                                     requested_target=title, undo=bool(undo))
    return _complete_by_title(user, kind or "", title or "", day=day, content=content)


def _complete_by_identity(user, source_type, source_id, day=None,
                          requested_target=None, undo=False) -> dict:
    """Identity path — the occurrence is already known. Defaults to TODAY."""
    from apps.core.execution.execution_completion import (
        complete_by_identity, reverse_by_identity,
    )
    today = _user_today(user)
    target = today
    if day:
        try:
            from apps.core.truth.periods import resolve_date_expression
            p = resolve_date_expression(day, today)
            if p is not None:
                target = p.start
        except Exception:
            logger.warning("execution_completion: date resolve failed for %r", day,
                           exc_info=True)
    try:
        fn = reverse_by_identity if undo else complete_by_identity
        out = fn(user, source_type, source_id, target,
                 requested_target=requested_target)
    except Exception:
        logger.warning("execution_completion: identity record failed", exc_info=True)
        return {"status": "error", "source_type": source_type, "source_id": source_id,
                "message": "That completion could not be recorded; nothing was changed."}
    out["day"] = target.isoformat()
    out["source_type"] = source_type
    out["source_id"] = source_id
    return out


def _complete_by_title(user, kind, title, day=None, content=None) -> dict:
    """Record completion of an execution item on the day it actually happened. `day` is a
    natural phrase ('yesterday', a date); defaults to yesterday. `content` carries the text
    for content kinds (journal). Delegates to the core router (reuse of existing writes).
    Never raises."""
    today = _user_today(user)
    target = today - timedelta(days=1)  # default: yesterday (the reconciliation case)
    if day:
        try:
            from apps.core.truth.periods import resolve_date_expression
            p = resolve_date_expression(day, today)
            if p is not None:
                target = p.start
        except Exception:
            logger.warning("execution_completion: date resolve failed for %r", day, exc_info=True)
    try:
        from apps.core.execution.execution_completion import complete_execution_item as _record
        out = _record(user, kind, title, target, content=content)
    except Exception:
        logger.warning("execution_completion: record failed", exc_info=True)
        return {"status": "error", "kind": kind, "title": title,
                "message": "That completion could not be recorded; nothing was changed."}
    out["day"] = target.isoformat()
    return out
