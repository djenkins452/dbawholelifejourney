# =============================================================================
# File: apps/core/execution/guided_review.py
# Purpose: The GUIDED execution-review queue — the deterministic "what item is
#   next to reconcile?" truth for a one-at-a-time review. It owns ZERO truth: the
#   queue is DERIVED live from the Execution Review projection (build_execution_review)
#   every call, so a just-recorded completion is reflected immediately and nothing is
#   duplicated. The conversation-scoped CURSOR (which items were already presented)
#   lives in conversation_state, not here. Read-only; never raises. (Blocker #15.)
# =============================================================================
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def item_key(item) -> str:
    """Stable identity of a review item within a day — (kind, title). This is the SAME
    identity complete_execution_item consumes (kind + title + day); no new id scheme."""
    return f"{(item or {}).get('kind', '')}::{(item or {}).get('title', '')}"


def incomplete_items(user, target_date) -> list:
    """The still-incomplete execution items for `target_date`, in the review's own order —
    DERIVED live from the Execution Review projection (never a stored/duplicated queue)."""
    try:
        from apps.core.execution.execution_review import build_execution_review
        review = build_execution_review(user, target_date)
    except Exception:
        logger.warning("guided_review: review build failed", exc_info=True)
        return []
    return [it for it in (review.get("items") or []) if not it.get("completed")]


def next_incomplete(user, target_date, asked_keys) -> dict | None:
    """The first incomplete item for the day whose key is NOT already in `asked_keys`
    (so a skipped/answered item is never re-presented). None when the day is reconciled
    or every remaining item has already been presented."""
    asked = set(asked_keys or [])
    for it in incomplete_items(user, target_date):
        if item_key(it) not in asked:
            return it
    return None
