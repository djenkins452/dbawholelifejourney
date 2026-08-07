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


def complete_execution_item(user, kind, title, day=None) -> dict:
    """Record completion of an execution item on the day it actually happened. `day` is a
    natural phrase ('yesterday', a date); defaults to yesterday. Delegates to the core
    router (reuse of existing writes). Never raises."""
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
        out = _record(user, kind, title, target)
    except Exception:
        logger.warning("execution_completion: record failed", exc_info=True)
        return {"status": "error", "kind": kind, "title": title,
                "message": "That completion could not be recorded; nothing was changed."}
    out["day"] = target.isoformat()
    return out
