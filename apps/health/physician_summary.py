"""
Physician Summary service (Sprint 8) — Physician Mode.

Assembles a patient-owned, physician-ready medication & treatment summary ENTIRELY
from existing canonical/deterministic layers. It performs NO clinical
interpretation, generates NO observations, and makes NO recommendations — it
organizes what WLJ deterministically knows so the user can have a better
conversation with their physician.

Sources (canonical only — no raw re-query where a canonical surface exists, no
duplicate calculation):
  - Intake current state + structured Prescription/Pharmacy/MedicalProvider fields
  - MedicationEvent ledger (via treatment_timeline)
  - treatment summary + timeline services (Sprint 4)
  - adherence utilities (medicine_utils)
  - approved narration objects (Sprint 7) — already safety-classified
"""

# User-friendly evidence labels (Sprint 8F) — never raw OCR / implementation detail.
EVIDENCE_LABELS = {
    "MedicationEvent": "Medication timeline event",
    "MedicationScanDraft": "Confirmed medication record",
    "WeightEntry": "Weight entry",
    "GlucoseEntry": "Glucose entry",
    "LabResult": "Lab result",
    "WorkoutSession": "Workout record",
    "adherence": "Adherence calculation",
    "glucose_avg": "Glucose average",
    "workout_count": "Workout count",
    "user_entry": "Manual entry",
    "vision": "Confirmed scan",
    "acquisition": "Acquisition record",
}

# Deterministic discussion-item phrasing per observation type (Sprint 8B §8).
# Discussion PROMPTS only — never advice, never dose-change suggestions.
DISCUSSION_TEMPLATES = {
    "treatment_recently_changed": "Discuss the recent medication changes.",
    "multiple_dose_increases": "Discuss the recent dose increases.",
    "multiple_dose_reductions": "Discuss the recent dose reductions.",
    "weight_after_treatment_change": "Discuss weight changes observed around treatment changes.",
    "glucose_after_treatment_change": "Discuss glucose changes observed around treatment changes.",
    "exercise_during_treatment": "Mention recent activity changes during treatment.",
    "adherence_declining": "Discuss recent adherence.",
    "recent_provider_change": "Confirm the current prescriber.",
    "recent_refill_pattern": "Review recent refill activity.",
}

NOT_RECORDED = "Not recorded"


def evidence_label(ev):
    if not isinstance(ev, dict):
        return "Source"
    return EVIDENCE_LABELS.get(ev.get("type"), "Source")


def _med_entry(intake):
    """Deterministic per-medication summary row from canonical fields."""
    rx = (
        intake.prescriptions.order_by("-written_date", "-created_at").first()
    )
    draft = (
        intake.acquisition_drafts.filter(review_status="confirmed")
        .order_by("-confirmed_at").first()
    )
    extracted = (draft.extracted_values or {}) if draft else {}
    route_form = " ".join(
        x for x in (extracted.get("dosage_form", ""), extracted.get("route", "")) if x
    ).strip()

    provider = (
        intake.provider.name if intake.provider_id
        else (intake.prescribing_doctor or "")
    )
    pharmacy = (
        intake.pharmacy_ref.name if intake.pharmacy_ref_id
        else (intake.pharmacy or "")
    )
    refill_status = NOT_RECORDED
    rx_number = (rx.rx_number if rx and rx.rx_number else (intake.rx_number or "")) or NOT_RECORDED
    if rx and rx.refills_remaining is not None:
        refill_status = f"{rx.refills_remaining} refill(s) remaining"
        if rx.expiration_date:
            refill_status += f", expires {rx.expiration_date.isoformat()}"
    elif intake.needs_refill:
        refill_status = "Running low (refill suggested)"

    return {
        "name": intake.name,
        "dose": intake.dose or NOT_RECORDED,
        "frequency": (intake.get_frequency_display() if intake.frequency else NOT_RECORDED),
        "route_form": route_form or NOT_RECORDED,
        "purpose": intake.purpose or NOT_RECORDED,
        "provider": provider or NOT_RECORDED,
        "pharmacy": pharmacy or NOT_RECORDED,
        "rx_number": rx_number,
        "refill_status": refill_status,
        "monitoring": intake.monitoring_requirements or "",
        "acquisition_confidence": (
            round((draft.overall_confidence or 0) * 100) if draft and draft.overall_confidence else None
        ),
    }


def build_physician_summary(user):
    """Assemble the full deterministic physician summary (Sprint 8A/8B)."""
    from apps.core.utils import get_user_today
    from apps.health.medicine_utils import calculate_medicine_adherence_rate
    from apps.health.models import Intake
    from apps.health.treatment_timeline import (
        build_medication_timeline,
        build_treatment_summary,
    )

    today = get_user_today(user)

    active = (
        Intake.objects.filter(user=user, intake_status=Intake.STATUS_ACTIVE)
        .select_related("provider", "pharmacy_ref")
        .prefetch_related("prescriptions", "acquisition_drafts")
        .order_by("name")
    )
    def _safe_entry(m):
        try:
            return _med_entry(m)
        except Exception:  # one bad row must not sink the whole summary (9C)
            import logging
            logging.getLogger(__name__).warning(
                "physician summary: med entry failed for intake %s", m.pk, exc_info=True)
            return None

    medications = [
        e for e in (_safe_entry(m) for m in active
                    if m.intake_type == Intake.INTAKE_TYPE_MEDICATION) if e
    ]
    supplements = [
        e for e in (_safe_entry(m) for m in active
                    if m.intake_type == Intake.INTAKE_TYPE_SUPPLEMENT) if e
    ]

    # Recent changes — from the MedicationEvent ledger (no fabrication).
    timeline = build_medication_timeline(user, include_acquisitions=False, newest_first=True)
    recent_changes = [
        {
            "date": e["date"],
            "medicine": e["intake_name"],
            "change": e["title"],
            "detail": e["detail"],
            "evidence_label": evidence_label(e.get("evidence", {})),
        }
        for e in timeline
        if e["kind"] not in ("tracking_began", "started")
    ][:15]

    # Timeline highlights — high-value events (skip refills/acquisition noise).
    highlights = [
        {"date": e["date"], "title": e["title"], "detail": e["detail"]}
        for e in timeline
        if e["kind"] in (
            "started", "discontinued", "dose_increased", "dose_decreased",
            "provider_changed",
        )
    ][:10]

    summary = build_treatment_summary(user)

    # Adherence — canonical utilities only (no duplicate math). Medication = PRESCRIPTION
    # ONLY (trust contract 2026-06-30); supplements are reported separately.
    adherence = {
        "medication_7d": calculate_medicine_adherence_rate(user, days=7, classification="prescription"),
        "medication_30d": calculate_medicine_adherence_rate(user, days=30, classification="prescription"),
        "supplement_30d": calculate_medicine_adherence_rate(user, days=30, classification="supplement"),
    }

    # What we've noticed + discussion items — APPROVED narrations only (Sprint 7),
    # read from the shared cached bundle (Sprint 9A — no recomputation).
    from apps.health.observations.bundle import get_observation_bundle
    narrations = get_observation_bundle(user)["narrations"]
    observations = [
        {
            "summary": n["summary"],
            "physician_discussion": n["physician_discussion"],
            "evidence_labels": sorted({evidence_label(ev) for ev in n.get("evidence", [])}),
        }
        for n in narrations
    ]
    # Deterministic discussion items (dedup by phrasing). Physician-flagged first.
    seen = set()
    discussion_items = []
    for n in sorted(narrations, key=lambda x: (not x["physician_discussion"], -x["priority_score"])):
        template = DISCUSSION_TEMPLATES.get(n["observation_type"])
        if template and template not in seen:
            seen.add(template)
            discussion_items.append(template)

    # Evidence source notes — the set of friendly source labels in this summary.
    source_labels = sorted({
        evidence_label(ev) for n in narrations for ev in n.get("evidence", [])
    } | {c["evidence_label"] for c in recent_changes})

    return {
        "header": {
            "user_name": (user.get_full_name() or user.email),
            "generated_date": today.isoformat(),
            "summary_period_days": summary.get("treatment_duration_days"),
            "disclaimer": (
                "Patient-owned summary of self-tracked information to support your "
                "conversation. Not a medical record and not medical advice."
            ),
        },
        "medications": medications,
        "supplements": supplements,
        "recent_changes": recent_changes,
        "adherence": adherence,
        "timeline_highlights": highlights,
        "observations": observations,
        "discussion_items": discussion_items,
        "source_notes": source_labels,
        "treatment_summary": summary,
        "is_empty": not (medications or supplements),
    }
