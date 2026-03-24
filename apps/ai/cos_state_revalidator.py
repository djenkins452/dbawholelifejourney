"""
CoS Mid-Response State Revalidator — Context Comparison

Detects if execution truth changed DURING LLM response generation by
comparing pre-generation and post-generation state snapshots.

NO LLM text parsing. NO appended corrections. Pure system state comparison.

If state changed → caller discards original response and regenerates.

RULES:
- Detection is based ONLY on execution truth snapshot comparison
- Never inspects, parses, or evaluates LLM response text
- Fail-open: if snapshot capture fails, no regeneration triggered
- Lightweight: captures only completion booleans + counts
"""

import logging

logger = logging.getLogger(__name__)


def capture_state_snapshot(user) -> dict:
    """Capture a lightweight snapshot of current execution truth.

    Returns a dict of completion booleans and counts that can be
    compared with == to detect any state change.

    Returns None if capture fails (fail-open).
    """
    try:
        from apps.ai.cos_fact_statements import build_locked_facts

        facts = build_locked_facts(user)
        raw = facts.get("_raw", {})

        # Extract only the completion-relevant fields
        return {
            "prayer_done": raw.get("prayer_done", False),
            "bible_done": raw.get("bible_done", False),
            "workout_done": raw.get("workout_done", False),
            "journal_done": raw.get("journal_done", False),
            "routine_done": raw.get("routine_done", 0),
            "routine_total": raw.get("routine_total", 0),
            "tasks_done": raw.get("tasks_done", 0),
            "meds_taken": raw.get("meds_taken", 0),
            "meds_expected": raw.get("meds_expected", 0),
            "meds_skipped": raw.get("meds_skipped", 0),
            "meds_all_taken": raw.get("meds_all_taken", True),
        }
    except Exception:
        logger.warning(
            "[STATE REVALIDATOR] Failed to capture snapshot for user=%s",
            user.id, exc_info=True,
        )
        return None


def has_state_changed(before: dict, after: dict) -> bool:
    """Compare two state snapshots to detect any change.

    Returns True if any completion status differs.
    Returns False if snapshots are identical or either is None.
    """
    if before is None or after is None:
        return False

    changed = before != after

    if changed:
        # Log what changed for observability
        diffs = [
            k for k in before
            if before.get(k) != after.get(k)
        ]
        logger.info(
            "[STATE REVALIDATOR] State changed: %s", diffs,
        )

    return changed
