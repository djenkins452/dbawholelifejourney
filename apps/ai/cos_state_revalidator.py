"""
CoS Mid-Response State Revalidator

Checks if execution truth changed DURING LLM response generation.
If the response references items as pending/not-completed that are
now actually completed (or vice versa), appends a correction.

This is a PRECISION PATCH — it does not change architecture, caching,
prompt construction, or LLM call structure. It runs once, right before
the response is saved, and either returns the response unchanged or
appends a factual correction line.

RULES:
- Never blocks the response
- Never modifies the LLM's original text (only appends)
- Only corrects completion status mismatches
- Uses the same data source as Today Engine (execution truth)
- Fail-open: if revalidation fails, return original response
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


def revalidate_response(response: str, user) -> str:
    """Check if any item the LLM describes as pending is now completed.

    If a mismatch is found, appends a correction line.
    Returns the original response if no corrections needed.
    """
    if not response:
        return response

    try:
        from apps.ai.cos_fact_statements import build_locked_facts

        current_facts = build_locked_facts(user)
        raw = current_facts.get("_raw", {})
    except Exception:
        # Can't validate — return original
        return response

    response_lower = response.lower()
    corrections = []

    for truth_key, item_names in _TRUTH_ITEMS.items():
        is_done = raw.get(truth_key, False)
        if not is_done:
            continue  # Item isn't completed — no possible stale-pending error

        # Check if the response describes this item as pending
        for name in item_names:
            if name not in response_lower:
                continue

            # Check if any pending phrase appears near the item name
            for phrase in _PENDING_PHRASES:
                if phrase in response_lower and name in response_lower:
                    # The response says this item is pending, but truth says done
                    display_name = name.title()
                    corrections.append(display_name)
                    break
            if corrections and corrections[-1] == name.title():
                break  # Already found a correction for this truth key

    if not corrections:
        return response

    # Deduplicate
    corrections = list(dict.fromkeys(corrections))

    # Append correction — factual, no coaching
    correction_text = ", ".join(corrections)
    note = f"\n\n(Update: {correction_text} has been completed since this response was generated.)"

    logger.info(
        "[STATE REVALIDATOR] Appended correction for user=%s: %s",
        user.id, corrections,
    )

    return response + note
