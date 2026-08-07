# =============================================================================
# File: apps/ai/cos_services/execution_review.py
# Purpose: CoS read surface for the Execution Review PROJECTION. Resolves the day
#   (a natural phrase like "yesterday") and returns the deterministic review of
#   everything the user INTENDED to execute that day. Owns ZERO truth — it delegates
#   to apps.core.execution.execution_review.build_execution_review, a projection over
#   existing truth authorities. Read-only; never raises. (Blocker #14, Layer 1.)
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


def get_execution_review(user, day=None) -> dict:
    """Return the deterministic review of everything the user INTENDED to execute on a day
    (tasks, faith/prayer/bible, medication, workout, journal, scheduled routines) with each
    item's completion state — ONE composed surface, not per-domain discovery.

    `day` is a natural date phrase ("yesterday", "today", "Monday", a date). Defaults to
    yesterday (the reconciliation case). A projection over existing truth; owns nothing.
    Never raises."""
    today = _user_today(user)
    target = today - timedelta(days=1)  # default: yesterday
    resolved_from = "default:yesterday"
    if day:
        try:
            from apps.core.truth.periods import resolve_date_expression
            p = resolve_date_expression(day, today)
            if p is not None:
                target = p.start
                resolved_from = day
            else:
                resolved_from = f"unresolved:{day}->default"
        except Exception:
            logger.warning("execution_review: date resolve failed for %r", day, exc_info=True)

    try:
        from apps.core.execution.execution_review import build_execution_review
        out = build_execution_review(user, target)
    except Exception:
        logger.warning("execution_review: build failed", exc_info=True)
        return {"status": "error", "reason": "Execution review could not be composed."}

    out["requested_day"] = day
    out["resolved_from"] = resolved_from
    out["relative"] = ("yesterday" if target == today - timedelta(days=1)
                       else "today" if target == today else out.get("date"))
    return out
