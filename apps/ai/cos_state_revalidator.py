"""
CoS Mid-Response State Revalidator

Checks if execution truth changed DURING LLM response generation.
If the response references items as pending/not-completed that are
now actually completed, signals that regeneration is needed.

This is a PRECISION PATCH — it does not change architecture, caching,
prompt construction, or LLM call structure.

BEHAVIOR:
- If state changed: caller DISCARDS original response and REGENERATES
- No appended corrections — CoS always speaks from current truth only
- Fail-open: if revalidation fails, original response is kept
"""

import logging

logger = logging.getLogger(__name__)

# Phrases in LLM output that indicate an item is described as NOT completed
_PENDING_PHRASES = [
    "not yet completed",
    "not yet done",
    "hasn't been done",
    "hasn't been completed",
    "hasn't been marked",
    "is not yet",
    "isn't completed",
    "isn't done",
    "still pending",
    "still needs",
    "not completed",
    "not done yet",
    "not marked",
]

# Map from truth keys to the item names the LLM might reference
_TRUTH_ITEMS = {
    "prayer_done": ["prayer"],
    "bible_done": ["bible reading", "bible", "scripture", "devotional"],
    "workout_done": ["workout", "exercise"],
    "journal_done": ["journal", "journal entry", "journaling"],
}


def check_state_changed(response: str, user) -> bool:
    """Check if any item the LLM describes as pending is now actually completed.

    Returns True if the response contains stale state that requires
    regeneration. Returns False if the response is current.

    Fail-open: returns False on any error (no regeneration triggered).
    """
    if not response:
        return False

    try:
        from apps.ai.cos_fact_statements import build_locked_facts

        current_facts = build_locked_facts(user)
        raw = current_facts.get("_raw", {})
    except Exception:
        # Can't validate — assume no change
        return False

    response_lower = response.lower()

    for truth_key, item_names in _TRUTH_ITEMS.items():
        is_done = raw.get(truth_key, False)
        if not is_done:
            continue  # Item isn't completed — no stale-pending possible

        # Check if the response describes this item as pending
        for name in item_names:
            if name not in response_lower:
                continue

            for phrase in _PENDING_PHRASES:
                if phrase in response_lower:
                    logger.info(
                        "[STATE REVALIDATOR] Stale state detected: "
                        "user=%s item=%s is now completed but response "
                        "says pending — regeneration needed",
                        user.id, truth_key,
                    )
                    return True

    return False
