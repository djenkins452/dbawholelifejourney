"""
Deterministic task classifier for the WLJ recovery contract.

Inputs an ExecutionItem dict (as produced by today_execution._task_to_item /
_collect_routine_items / _collect_medication_items) and returns:

    (task_class: str, grace_minutes: int | None, is_reset_action: bool)

Resolution order — first match wins:

    1. Explicit registry override by (source_type, source_id)
    2. Activity-type rule (faith bible/journal/workout, hygiene, etc.)
    3. Domain + intake/priority rule (medication windows, supplements)
    4. Source-type fallback (medication_dose / routine_item / task)
    5. Schedule fallback (scheduled vs. unscheduled)
    6. Safe default — FLEXIBLE

PURE module: no DB, no settings lookup at runtime, no LLM.

`is_reset_action` is set ONLY by registry/activity-type/domain rules —
never inferred from titles. Title-token matching is forbidden.
"""

from .constants import (
    GRACE_HARD_EXPIRED_MIN,
    GRACE_REST_OF_DAY,
    GRACE_WINDOWED_DEFAULT_MIN,
)

# ── Class enum (string constants for JSON serializability) ──────────
HARD_EXPIRED = "HARD_EXPIRED"
WINDOWED = "WINDOWED"
SOFT_EXPIRED = "SOFT_EXPIRED"
FLEXIBLE = "FLEXIBLE"

ALL_CLASSES = (HARD_EXPIRED, WINDOWED, SOFT_EXPIRED, FLEXIBLE)


# ── Activity-type rules ─────────────────────────────────────────────
# Routine items expose `activity_type` from apps.life.models. These map
# to a class deterministically. Reset flag is set on items whose value
# as a "reset" comes from their nature (hydration, hygiene, brief
# spiritual pause), not from their title.
_ACTIVITY_TYPE_RULES = {
    # Faith activities are still useful any time of day. A brief
    # spiritual pause counts as a reset; bible/journal/workout do not.
    "bible":   (SOFT_EXPIRED, GRACE_REST_OF_DAY, False),
    "faith":   (SOFT_EXPIRED, GRACE_REST_OF_DAY, True),
    "journal": (SOFT_EXPIRED, GRACE_REST_OF_DAY, False),
    "workout": (SOFT_EXPIRED, GRACE_REST_OF_DAY, False),
    # Stabilizing reset activities (hydration / hygiene / short walk).
    # Set is_reset_action=True so RecoveryState can pick them as the
    # stabilize lever without title matching.
    "hydration": (SOFT_EXPIRED, GRACE_REST_OF_DAY, True),
    "hygiene":   (SOFT_EXPIRED, GRACE_REST_OF_DAY, True),
    "movement":  (SOFT_EXPIRED, GRACE_REST_OF_DAY, True),
    "pause":     (SOFT_EXPIRED, GRACE_REST_OF_DAY, True),
    # Time-bound external commitments — service/appointment/meeting/
    # class. Once the scheduled window passes there is no value in
    # surfacing them as actionable. Authoritative signal is a dedicated
    # activity_type tag, not a title.
    "event":       (HARD_EXPIRED, GRACE_HARD_EXPIRED_MIN, False),
    "service":     (HARD_EXPIRED, GRACE_HARD_EXPIRED_MIN, False),
    "appointment": (HARD_EXPIRED, GRACE_HARD_EXPIRED_MIN, False),
    "meeting":     (HARD_EXPIRED, GRACE_HARD_EXPIRED_MIN, False),
    "class":       (HARD_EXPIRED, GRACE_HARD_EXPIRED_MIN, False),
    # Time-bound nutrition anchors (morning shake, weigh-in, measurement)
    # — meaningful inside their window only.
    "nutrition_anchor": (WINDOWED, GRACE_WINDOWED_DEFAULT_MIN, False),
    "weigh_in":         (WINDOWED, GRACE_WINDOWED_DEFAULT_MIN, False),
    "measurement":      (WINDOWED, GRACE_WINDOWED_DEFAULT_MIN, False),
}


# ── Domain + source-type rules ──────────────────────────────────────
# Medication doses are window-based: critical meds get a tight grace,
# optimization supplements get a longer grace. Reset flag never set.
def _classify_medication(item):
    priority = (item.get("priority") or "").lower()
    if priority == "optimization":
        # Optimization-priority supplements: longer grace.
        return (WINDOWED, 120, False)
    # Critical medications and unspecified default to the standard grace.
    return (WINDOWED, 60, False)


# ── Explicit registry override hook ─────────────────────────────────
# Empty in v1 — extension point for per-(source_type, source_id) pins
# without changing code. Populate from a future admin surface or a
# fixture if needed.
_EXPLICIT_REGISTRY = {}


def _registry_lookup(item):
    key = (item.get("source_type"), item.get("source_id"))
    return _EXPLICIT_REGISTRY.get(key)


# ── Public API ──────────────────────────────────────────────────────
def classify(item):
    """Classify an ExecutionItem dict.

    Returns:
        tuple: (task_class, grace_minutes, is_reset_action)
        - task_class is one of HARD_EXPIRED / WINDOWED / SOFT_EXPIRED /
          FLEXIBLE.
        - grace_minutes is an int (minutes after scheduled time during
          which the item is still meaningful) OR None for "rest of day".
        - is_reset_action is True only when the activity is a stabilizing
          reset (hydration, hygiene, brief spiritual pause) — derived
          deterministically, never from title text.
    """
    # 1. Explicit registry override
    pinned = _registry_lookup(item)
    if pinned is not None:
        return pinned

    source_type = (item.get("source_type") or "").lower()
    domain = (item.get("domain") or "").lower()
    activity_type = (item.get("activity_type") or "").lower()
    intake_type = (item.get("intake_type") or "").lower()

    # 2. Activity-type rule (routine items with a known activity_type)
    if activity_type and activity_type in _ACTIVITY_TYPE_RULES:
        return _ACTIVITY_TYPE_RULES[activity_type]

    # 3. Domain + intake/priority rule (medication / supplement windows)
    if source_type in ("medication_dose", "supplement_dose"):
        return _classify_medication(item)
    if intake_type in ("medication", "supplement"):
        return _classify_medication(item)

    # 4. Source-type fallbacks
    if source_type == "routine_item":
        # Routine items without a recognized activity_type are still
        # useful any time of day (e.g., chores, charge watch, cleanup).
        # Not resets — those are explicitly tagged via activity_type.
        return (SOFT_EXPIRED, GRACE_REST_OF_DAY, False)

    if source_type == "task":
        # 5. Schedule fallback: a scheduled task is SOFT_EXPIRED
        # (meaningful all day); an unscheduled task is FLEXIBLE.
        if item.get("scheduled_time"):
            return (SOFT_EXPIRED, GRACE_REST_OF_DAY, False)
        return (FLEXIBLE, GRACE_REST_OF_DAY, False)

    # 6. Safe default
    return (FLEXIBLE, GRACE_REST_OF_DAY, False)


def annotate(item):
    """In-place mutator: write task_class / recovery_grace_minutes /
    is_reset_action onto the ExecutionItem dict and return it.

    Idempotent — re-annotating an already-annotated item produces the
    same values.
    """
    cls, grace, is_reset = classify(item)
    item["task_class"] = cls
    item["recovery_grace_minutes"] = grace
    item["is_reset_action"] = is_reset
    return item
