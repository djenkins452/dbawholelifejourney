"""
EXACT-IDENTITY RECORD CORRECTION (M4).

WHY THIS EXISTS (production 2026-08-27). The CoS created an erroneous weight record and
then could not reverse it: `complete_execution_item(source_type='weight', source_id=None)`
returned *"No completion write is wired for '' yet."* Having created truth it could not
correct, it then offered to "fix" the bad value by **substituting an unrelated historical
weight** (275.1 lb, a real reading from nine days earlier). Both halves were wrong.

GOVERNING INVARIANT:

    A corrective action must target an EXACT canonical record identity. If the target or
    the replacement truth is unknown, WLJ must not guess.

The model may CHOOSE which record to act on through ordinary deterministic retrieval —
that is reasoning, and it is the model's. EXECUTION binds to the identity, never to a
name, a value, a description, or "the most recent one".

DELIBERATELY NOT A GENERIC DELETE. Only record types registered here can be corrected,
each naming its own model and its own deterministic description. There is no
`delete(table, id)` capability, and adding a type is an explicit, reviewable act.

REMOVAL IS SOFT-DELETE — the domain's own canonical mechanism (`UserOwnedModel.
soft_delete()`, which sets `status='deleted'`, stamps `deleted_at`, and invalidates the
CoS/SAE caches). WLJ never hard-deletes a user's record from a conversation.

NO REPLACEMENT TRUTH. This module removes a record. It does not, and must not, write a
"corrected" value: a value nobody supplied is a value nobody verified.
"""
import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

OK = "ok"
NOT_FOUND = "not_found"
ALREADY_REMOVED = "already_removed"
UNSUPPORTED = "unsupported_record_type"
AMBIGUOUS = "ambiguous_target"


@dataclass(frozen=True)
class RecordSpec:
    """One correctable record type. The domain owns its model and its description."""
    key: str
    label: str
    app_label: str
    model_name: str
    describe: Callable          # (record) -> deterministic one-line description


def _describe_weight(e):
    from django.utils import timezone
    when = timezone.localtime(e.recorded_at)
    note = (e.notes or "").strip()
    base = f"{e.value} {e.unit} recorded {when.strftime('%b %d, %Y at %-I:%M %p')}"
    return f"{base} — note: {note[:60]}" if note else base


def _describe_food(e):
    bits = [f"{e.food_name}"]
    if e.meal_type:
        bits.append(str(e.meal_type))
    if e.total_calories:
        bits.append(f"{e.total_calories} cal")
    return f"{' — '.join(bits)} on {e.logged_date.isoformat()}"


# The ONLY correctable record types. Each addition is deliberate, never a generic
# capability: weight is the proven production need, and food is included because the
# same write path now creates it (M3) and a user who can log a meal must be able to
# remove one they logged by mistake. Both are `UserOwnedModel`s with the domain's own
# `soft_delete()`, so nothing new is invented to support them.
RECORD_TYPES = {
    "weight": RecordSpec(key="weight", label="weight entry",
                         app_label="health", model_name="WeightEntry",
                         describe=_describe_weight),
    "food": RecordSpec(key="food", label="food entry",
                       app_label="health", model_name="FoodEntry",
                       describe=_describe_food),
}


def spec_for(record_type):
    return RECORD_TYPES.get((record_type or "").strip().lower())


def _model(spec):
    from django.apps import apps
    return apps.get_model(spec.app_label, spec.model_name)


def _fetch(user, spec, record_id):
    """Ownership-scoped fetch by EXACT primary key, including already-removed rows so a
    repeat can be reported idempotently rather than as a mysterious miss."""
    M = _model(spec)
    return M.all_objects.filter(user=user, pk=record_id).first() if hasattr(
        M, "all_objects") else M.objects.filter(user=user, pk=record_id).first()


def describe_target(user, record_type, record_id):
    """The deterministic CURRENT state of the exact record, for the confirmation.

    The user authorizes the removal of a record they can SEE, described from the stored
    row — not from the model's recollection of it.
    """
    spec = spec_for(record_type)
    if spec is None:
        return {"status": UNSUPPORTED, "record_type": record_type,
                "message": f"I can't correct '{record_type}' records."}
    if record_id in (None, "", 0):
        # Fail closed: no identity means no target. Never "the most recent one".
        return {"status": AMBIGUOUS, "record_type": record_type,
                "message": (f"I need the exact {spec.label} to remove — I won't guess "
                            "which one you mean.")}
    rec = _fetch(user, spec, record_id)
    if rec is None:
        return {"status": NOT_FOUND, "record_type": record_type,
                "record_id": record_id,
                "message": f"I couldn't find that {spec.label}."}
    removed = getattr(rec, "status", "active") == "deleted"
    return {"status": ALREADY_REMOVED if removed else OK,
            "record_type": spec.key, "record_id": rec.pk,
            "label": spec.label, "description": spec.describe(rec),
            "message": f"{spec.label}: {spec.describe(rec)}"}


def remove_record(user, record_type, record_id):
    """Remove EXACTLY the identified record. Idempotent; never guesses; never replaces.

    Returns a deterministic result carrying the identity acted on, so the audit row can
    establish old record → action → result.
    """
    target = describe_target(user, record_type, record_id)
    if target["status"] in (UNSUPPORTED, AMBIGUOUS, NOT_FOUND):
        return {**target, "removed": False}
    if target["status"] == ALREADY_REMOVED:
        # A retry after a completed removal is a no-op that reports the truth.
        return {**target, "status": ALREADY_REMOVED, "removed": False,
                "message": f"That {target['label']} was already removed."}

    spec = spec_for(record_type)
    rec = _fetch(user, spec, record_id)
    try:
        rec.soft_delete()          # the domain's own canonical removal
    except Exception:
        logger.warning("record_correction: soft_delete failed type=%s id=%s",
                       record_type, record_id, exc_info=True)
        return {**target, "status": "error", "removed": False,
                "message": f"I couldn't remove that {spec.label}."}
    return {"status": OK, "removed": True, "record_type": spec.key,
            "record_id": rec.pk, "label": spec.label,
            "description": target["description"],
            "message": f"Removed that {spec.label} — {target['description']}."}
