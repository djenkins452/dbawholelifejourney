"""
Medication acquisition pipeline (Sprint 3).

The permanent acquisition architecture for Medication Intelligence: every
acquisition method — bottle image, pharmacy label/PDF, medication list, provider
export, FHIR, pharmacy API, manual entry — converges into ONE staging object
(``MedicationScanDraft``) and resolves through ONE confirmation path into the
canonical ``Intake`` + ``MedicationEvent`` ledger.

Invariants:
  - Nothing enters canonical state without confirmation (Canon: OCR is never truth).
  - Confirmation reuses the single history writer (``record_medication_change``)
    and the canonical Intake create path — NO direct ad-hoc model writes.
  - Duplicate detection runs BEFORE any canonical write — never silently duplicate.
"""

from django.db import transaction
from django.utils import timezone

from apps.health.medication_confidence import (
    compute_field_confidences,
    compute_overall_confidence,
)


# ── Acquisition (3B / 3G / 3H) ────────────────────────────────────────────────

def create_draft(user, source, extracted_values, *, intake_type=None,
                 extraction_confidences=None, evidence=None,
                 user_edited_fields=None):
    """Create a pending MedicationScanDraft from any acquisition method.

    Computes per-field + overall confidence and attaches the evidence envelope.
    Does NOT touch Intake. Returns the draft (status=pending_review).
    """
    from apps.health.models import Intake, MedicationScanDraft

    extracted_values = {
        k: v for k, v in (extracted_values or {}).items() if v not in (None, "", [])
    }
    intake_type = intake_type or Intake.INTAKE_TYPE_MEDICATION

    field_conf = compute_field_confidences(
        extracted_values, source,
        extraction_confidences=extraction_confidences,
        user_edited_fields=user_edited_fields,
    )
    overall = compute_overall_confidence(field_conf)

    draft = MedicationScanDraft.objects.create(
        user=user,
        source=source,
        intake_type=intake_type,
        extracted_values=extracted_values,
        field_confidences=field_conf,
        overall_confidence=overall,
        evidence=_evidence_envelope(source, evidence),
        review_status=MedicationScanDraft.REVIEW_PENDING,
    )
    return draft


def create_draft_from_scan(user, category, items, *, scan_confidence=None,
                           evidence=None):
    """Bridge the existing Scan/Vision pipeline into the acquisition pipeline
    (Sprint 3.5). Maps a Vision medicine/supplement extraction into a
    MedicationScanDraft — Vision NEVER writes canonical state; like every other
    source it produces a reviewable draft. Returns the draft, or None if there
    is nothing usable to stage.
    """
    from apps.health.models import Intake

    if not items:
        return None
    item = items[0] or {}
    details = item.get("details", {}) or {}
    name = (item.get("label") or details.get("name") or "").strip()
    if not name:
        return None

    extracted = {
        "name": name,
        "dose": details.get("dosage", ""),
        "sig": details.get("directions", ""),
        "quantity": details.get("quantity", ""),
        "purpose": details.get("purpose", ""),
        "provider": details.get("prescriber") or details.get("provider", ""),
        "pharmacy": details.get("pharmacy", ""),
        "refills": details.get("refills", ""),
        "expiration": details.get("expiration") or details.get("expiration_date", ""),
        "ndc": details.get("ndc", ""),
    }
    intake_type = (
        Intake.INTAKE_TYPE_SUPPLEMENT if category == "supplement"
        else Intake.INTAKE_TYPE_MEDICATION
    )
    # Vision gives one overall scan confidence; apply it to each read field as the
    # extraction confidence (the per-field confidence then flows through the engine).
    extraction_conf = None
    if scan_confidence is not None:
        extraction_conf = {
            k: scan_confidence for k, v in extracted.items() if v not in (None, "")
        }
    scan_evidence = (evidence or []) + [{
        "source_type": "vision",
        "summary": f"Scanned ({category})",
        "confidence": scan_confidence,
    }]
    return create_draft(
        user, "bottle_image", extracted, intake_type=intake_type,
        extraction_confidences=extraction_conf, evidence=scan_evidence,
    )


def create_manual_draft(user, values, *, intake_type=None):
    """Manual entry is a first-class acquisition method (Sprint 3G).

    The user entered it intentionally → every provided field is treated as
    user-edited (high confidence). Still goes through the same review/confirm
    workflow (one pipeline for everything).
    """
    return create_draft(
        user, "manual", values, intake_type=intake_type,
        user_edited_fields=list((values or {}).keys()),
        evidence=[{"source_type": "user_entry", "summary": "Entered manually"}],
    )


def _evidence_envelope(source, evidence):
    """Standardized evidence envelope (Canon §6 convention: evidence supports
    truth, it is not truth). Always records the acquisition source + timestamp."""
    env = list(evidence or [])
    env.append({
        "source_type": "acquisition",
        "summary": f"Acquired via {source}",
        "captured_at": timezone.now().isoformat(),
    })
    return env


# ── Duplicate detection (3E) ──────────────────────────────────────────────────

def detect_duplicates(user, draft):
    """Find existing active Intakes that this draft may duplicate.

    Runs BEFORE any canonical write. Returns a list of candidate dicts:
    {intake_id, name, match_type, dose_differs, existing_dose, new_dose}.
    match_type ∈ {exact, same_name_diff_dose, ndc}.
    """
    from apps.health.models import Intake

    values = draft.extracted_values or {}
    name = (values.get("name") or "").strip().lower()
    ndc = (values.get("ndc") or "").strip()
    new_dose = (values.get("dose") or "").strip().lower()
    if not name and not ndc:
        return []

    candidates = Intake.objects.filter(user=user, intake_status=Intake.STATUS_ACTIVE)
    matches = []
    for intake in candidates:
        existing_name = (intake.name or "").strip().lower()
        existing_dose = (intake.dose or "").strip().lower()
        match_type = None
        if ndc and getattr(intake, "ndc_code", None) and intake.ndc_code.strip() == ndc:
            match_type = "ndc"
        elif name and existing_name == name:
            match_type = "exact" if existing_dose == new_dose else "same_name_diff_dose"
        if match_type:
            matches.append({
                "intake_id": intake.id,
                "name": intake.name,
                "match_type": match_type,
                "dose_differs": bool(new_dose and existing_dose != new_dose),
                "existing_dose": intake.dose,
                "new_dose": values.get("dose"),
            })
    return matches


# ── Confirmation (3F) ─────────────────────────────────────────────────────────

# extracted_values key → Intake field (only fields that exist on Intake today).
_INTAKE_FIELD_MAP = {
    "name": "name",
    "dose": "dose",
    "purpose": "purpose",
    "sig": "instructions",
    "provider": "prescribing_doctor",
    "pharmacy": "pharmacy",
    "rx_number": "rx_number",
}


def _valid_frequency(value):
    from apps.health.models import Intake
    valid = {c[0] for c in Intake.FREQUENCY_CHOICES}
    if value in valid:
        return value
    if value and "need" in str(value).lower():
        return "as_needed"
    return None


@transaction.atomic
def confirm_draft(draft, action, *, target_intake=None, edits=None, reason=None,
                  source_label=None):
    """Resolve a draft into canonical state through the ONE write path.

    action:
      - create      → create a new Intake (post_save fires the 'started' event).
      - update      → update target_intake; record dose/provider/etc. change events.
      - discontinue → target_intake.complete() (→ 'discontinued' event).
      - replace     → discontinue target_intake + create a new Intake.
      - ignore      → reject the draft; no canonical write.

    ``edits`` (field→value) are applied first and treated as user confirmation
    (highest evidence): they update extracted_values and lift confidence to ~1.0.
    Returns the resulting Intake (or None for ignore).
    """
    from apps.health.models import Intake, MedicationScanDraft

    if edits:
        draft.extracted_values = {**(draft.extracted_values or {}), **{
            k: v for k, v in edits.items() if v not in (None, "")
        }}
        draft.field_confidences = compute_field_confidences(
            draft.extracted_values, draft.source,
            user_edited_fields=list(edits.keys()),
        )

    result = None
    if action == MedicationScanDraft.ACTION_CREATE:
        result = _create_intake_from_draft(draft)
    elif action == MedicationScanDraft.ACTION_UPDATE:
        result = _apply_update(draft, target_intake, reason=reason)
    elif action == MedicationScanDraft.ACTION_DISCONTINUE:
        if target_intake is not None:
            target_intake.complete()
        result = target_intake
    elif action == MedicationScanDraft.ACTION_REPLACE:
        if target_intake is not None:
            target_intake.complete()
        result = _create_intake_from_draft(draft)
    elif action == MedicationScanDraft.ACTION_IGNORE:
        draft.review_status = MedicationScanDraft.REVIEW_REJECTED
        draft.confirmation_action = action
        draft.reviewed_at = timezone.now()
        draft.save(update_fields=["review_status", "confirmation_action",
                                  "reviewed_at", "updated_at"])
        return None
    else:
        raise ValueError(f"Unknown confirmation action: {action}")

    # Mark the draft confirmed (user confirmation = strongest evidence → conf ~1.0).
    draft.review_status = MedicationScanDraft.REVIEW_CONFIRMED
    draft.confirmation_action = action
    draft.created_intake = result
    draft.confirmed_at = timezone.now()
    draft.reviewed_at = timezone.now()
    draft.overall_confidence = compute_overall_confidence(
        draft.field_confidences, user_confirmed=True,
    )
    draft.save(update_fields=[
        "review_status", "confirmation_action", "created_intake",
        "confirmed_at", "reviewed_at", "overall_confidence", "updated_at",
    ])
    return result


def _create_intake_from_draft(draft):
    """Create a canonical Intake from the draft's confirmed values. The Intake
    post_save signal appends the canonical 'started' MedicationEvent — so this
    reuses the one history writer rather than writing events directly."""
    from apps.core.utils import get_user_today
    from apps.health.models import Intake

    values = draft.extracted_values or {}
    kwargs = {"user": draft.user, "intake_type": draft.intake_type}
    for key, field in _INTAKE_FIELD_MAP.items():
        if values.get(key) not in (None, ""):
            kwargs[field] = values[key]
    freq = _valid_frequency(values.get("frequency"))
    if freq:
        kwargs["frequency"] = freq
    kwargs.setdefault("name", values.get("name") or "Unnamed medication")
    # start_date is required; confirmation date is the canonical "tracking start".
    kwargs.setdefault("start_date", get_user_today(draft.user))
    return Intake.objects.create(**kwargs)


def _apply_update(draft, target_intake, *, reason=None):
    """Apply the draft's values to an existing Intake and record a MedicationEvent
    per significant change via the single history writer."""
    from apps.health.medication_events import record_medication_change
    from apps.health.models import Intake, MedicationEvent

    if target_intake is None:
        return _create_intake_from_draft(draft)

    values = draft.extracted_values or {}
    changed = {}
    # Dose change → its own canonical event.
    new_dose = values.get("dose")
    if new_dose not in (None, "") and new_dose != target_intake.dose:
        prev = target_intake.dose
        target_intake.dose = new_dose
        changed["dose"] = (prev, new_dose)
    # Provider / pharmacy free-text updates.
    for key, field in (("provider", "prescribing_doctor"), ("pharmacy", "pharmacy")):
        nv = values.get(key)
        if nv not in (None, "") and nv != getattr(target_intake, field):
            changed[field] = (getattr(target_intake, field), nv)
            setattr(target_intake, field, nv)
    freq = _valid_frequency(values.get("frequency"))
    if freq and freq != target_intake.frequency:
        changed["frequency"] = (target_intake.frequency, freq)
        target_intake.frequency = freq

    if changed:
        target_intake.save()
        _reason = reason or MedicationEvent.REASON_UNKNOWN
        if "dose" in changed:
            record_medication_change(
                target_intake, MedicationEvent.EVENT_DOSE_CHANGED,
                previous_value={"dose": changed["dose"][0]},
                new_value={"dose": changed["dose"][1]},
                reason=_reason, source=MedicationEvent.SOURCE_COS_CONFIRMED,
            )
        if "frequency" in changed:
            record_medication_change(
                target_intake, MedicationEvent.EVENT_FREQUENCY_CHANGED,
                previous_value={"frequency": changed["frequency"][0]},
                new_value={"frequency": changed["frequency"][1]},
                reason=_reason, source=MedicationEvent.SOURCE_COS_CONFIRMED,
            )
        if "prescribing_doctor" in changed:
            record_medication_change(
                target_intake, MedicationEvent.EVENT_PROVIDER_CHANGED,
                new_value={"provider": changed["prescribing_doctor"][1]},
                reason=_reason, source=MedicationEvent.SOURCE_COS_CONFIRMED,
            )
    return target_intake
