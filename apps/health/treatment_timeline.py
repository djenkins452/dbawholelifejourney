"""
Canonical Treatment Timeline service (Sprint 4).

The single source for a user's deterministic, evidence-first medication treatment
history. It turns the append-only ``MedicationEvent`` ledger (Sprint 2A) plus
confirmed acquisitions into ordered canonical timeline entries, and aligns them
with other domains' events (Sprint 4C) WITHOUT correlating or inferring anything.

Rules (Medication Intelligence Canon / Sprint 4 guardrails):
  - Deterministic only — no LLM, no predictions, no clinical conclusions, no
    cross-domain correlation. The timeline ORDERS events; it never explains cause.
  - Evidence-first — every entry references the canonical record it came from
    ("why is this here?"), never raw OCR.
  - Reusable canonical data — entries are plain dicts, not UI structures.
"""

import re
from datetime import datetime, time

from django.utils import timezone


# Canonical timeline entry kinds (medication domain).
KIND_TRACKING_BEGAN = "tracking_began"
KIND_STARTED = "started"
KIND_STOPPED = "discontinued"
KIND_PAUSED = "paused"
KIND_RESUMED = "resumed"
KIND_DOSE_INCREASED = "dose_increased"
KIND_DOSE_DECREASED = "dose_decreased"
KIND_DOSE_CHANGED = "dose_changed"
KIND_FREQUENCY_CHANGED = "frequency_changed"
KIND_PROVIDER_CHANGED = "provider_changed"
KIND_PHARMACY_CHANGED = "pharmacy_changed"
KIND_REFILL = "refill"
KIND_ACQUISITION_CONFIRMED = "acquisition_confirmed"


def _numeric(value):
    """Leading number in a dose string ('20mg' → 20.0), or None."""
    if value in (None, ""):
        return None
    m = re.search(r"\d+(\.\d+)?", str(value))
    return float(m.group()) if m else None


def _classify_dose_change(event):
    """Refine a dose_changed event into increased/decreased when both doses are
    numerically comparable; otherwise leave it a generic change. Deterministic."""
    prev = _numeric((event.previous_value or {}).get("dose"))
    new = _numeric((event.new_value or {}).get("dose"))
    if prev is not None and new is not None:
        if new > prev:
            return KIND_DOSE_INCREASED
        if new < prev:
            return KIND_DOSE_DECREASED
    return KIND_DOSE_CHANGED


def _event_title(kind, name, event):
    """Deterministic, factual entry title — never coaching, never inferred."""
    pv = (event.previous_value or {}).get("dose")
    nv = (event.new_value or {}).get("dose")
    titles = {
        KIND_TRACKING_BEGAN: f"Started tracking {name}",
        KIND_STARTED: f"Started {name}",
        KIND_STOPPED: f"Stopped {name}",
        KIND_PAUSED: f"Paused {name}",
        KIND_RESUMED: f"Resumed {name}",
        KIND_DOSE_INCREASED: f"{name} dose increased",
        KIND_DOSE_DECREASED: f"{name} dose decreased",
        KIND_DOSE_CHANGED: f"{name} dose changed",
        KIND_FREQUENCY_CHANGED: f"{name} frequency changed",
        KIND_PROVIDER_CHANGED: f"{name} provider changed",
        KIND_PHARMACY_CHANGED: f"{name} pharmacy changed",
        KIND_REFILL: f"{name} refilled",
    }
    return titles.get(kind, f"{name} {kind}")


def _entry_from_medication_event(event):
    name = event.intake.name
    kind = event.event_type
    if kind == "dose_changed":
        kind = _classify_dose_change(event)
    detail = ""
    pv = (event.previous_value or {}).get("dose")
    nv = (event.new_value or {}).get("dose")
    if pv and nv:
        detail = f"{pv} → {nv}"
    elif event.reason_detail:
        detail = event.reason_detail
    ts = event.created_at or timezone.make_aware(
        datetime.combine(event.effective_date, time())
    )
    return {
        "timestamp": ts.isoformat(),
        "date": event.effective_date.isoformat(),
        "domain": "medication",
        "kind": kind,
        "title": _event_title(kind, name, event),
        "detail": detail,
        "intake_id": event.intake_id,
        "intake_name": name,
        "reason": event.get_reason_display(),
        # 4F — evidence-first: every entry says why it's here.
        "evidence": {
            "type": "MedicationEvent",
            "id": event.id,
            "summary": f"{event.get_event_type_display()} recorded {event.effective_date}",
        },
    }


def _entry_from_confirmed_draft(draft):
    name = (draft.extracted_values or {}).get("name") or (
        draft.created_intake.name if draft.created_intake_id else "medication"
    )
    ts = draft.confirmed_at or draft.created_at
    return {
        "timestamp": ts.isoformat(),
        "date": (draft.confirmed_at or draft.created_at).date().isoformat(),
        "domain": "medication",
        "kind": KIND_ACQUISITION_CONFIRMED,
        "title": f"Confirmed {name}",
        "detail": f"via {draft.get_source_display()}",
        "intake_id": draft.created_intake_id,
        "intake_name": name,
        "reason": "Acquisition confirmed",
        "evidence": {
            "type": "MedicationScanDraft",
            "id": draft.id,
            "summary": f"Acquired via {draft.source}, confidence "
                       f"{round((draft.overall_confidence or 0) * 100)}%",
        },
    }


def build_medication_timeline(user, *, intake=None, include_acquisitions=True,
                              newest_first=False):
    """Canonical medication treatment history — the single source.

    Args:
        intake: limit to one Intake (else all of the user's).
        include_acquisitions: include 'acquisition_confirmed' entries from
            confirmed MedicationScanDrafts.
        newest_first: order most-recent-first (default chronological/ascending).

    Returns a list of canonical timeline entry dicts (see module docstring).
    """
    from apps.health.models import MedicationEvent, MedicationScanDraft

    events = MedicationEvent.objects.filter(user=user).select_related("intake")
    if intake is not None:
        events = events.filter(intake=intake)
    entries = [_entry_from_medication_event(e) for e in events]

    if include_acquisitions:
        drafts = MedicationScanDraft.objects.filter(
            user=user, review_status=MedicationScanDraft.REVIEW_CONFIRMED,
        ).select_related("created_intake")
        if intake is not None:
            drafts = drafts.filter(created_intake=intake)
        entries.extend(_entry_from_confirmed_draft(d) for d in drafts)

    entries.sort(key=lambda e: e["timestamp"], reverse=newest_first)
    return entries


# ── Deterministic treatment summaries (Sprint 4B) ─────────────────────────────

def _days_between(start_date, end_date):
    if not start_date or not end_date:
        return None
    return (end_date - start_date).days


def build_treatment_summary(user, *, intake=None):
    """Deterministic treatment summaries (NO coaching, NO inference).

    Overall (intake=None): treatment duration, total dose changes, recent-change
    count, adherence, and a factual treatment-momentum label.
    Per-intake: start/duration, current-dose duration, dose-change count, provider
    history, prescription status, longest stable period, adherence.
    """
    from datetime import timedelta

    from apps.core.utils import get_user_today
    from apps.health.medicine_utils import calculate_medicine_adherence_rate
    from apps.health.models import Intake, MedicationEvent, Prescription

    today = get_user_today(user)

    if intake is not None:
        events = list(
            MedicationEvent.objects.filter(user=user, intake=intake)
            .order_by("effective_date", "created_at")
        )
        start_date = intake.start_date
        dose_changes = [e for e in events if e.event_type == "dose_changed"]
        # Current dose since the last dose change (or the start).
        last_dose_event = dose_changes[-1] if dose_changes else None
        current_dose_since = (
            last_dose_event.effective_date if last_dose_event else start_date
        )
        # Provider history: providers seen across change events + current.
        provider_history = []
        for e in events:
            nv = (e.new_value or {}).get("provider")
            if nv and nv not in provider_history:
                provider_history.append(nv)
        if intake.provider_id and intake.provider.name not in provider_history:
            provider_history.append(intake.provider.name)
        elif intake.prescribing_doctor and intake.prescribing_doctor not in provider_history:
            provider_history.append(intake.prescribing_doctor)
        # Longest stable period = largest gap (days) between consecutive events.
        change_dates = [start_date] + [e.effective_date for e in events] + [today]
        change_dates = sorted(d for d in change_dates if d)
        longest_stable = max(
            ((b - a).days for a, b in zip(change_dates, change_dates[1:])),
            default=0,
        )
        # Current prescription status.
        rx = (
            Prescription.objects.filter(user=user, intake=intake)
            .order_by("-written_date", "-created_at").first()
        )
        rx_status = None
        if rx:
            rx_status = {
                "rx_number": rx.rx_number,
                "refills_remaining": rx.refills_remaining,
                "expiration_date": rx.expiration_date.isoformat() if rx.expiration_date else None,
            }
        return {
            "intake_id": intake.id,
            "name": intake.name,
            "started_date": start_date.isoformat() if start_date else None,
            "treatment_duration_days": _days_between(start_date, today),
            "current_dose": intake.dose,
            "current_dose_since": current_dose_since.isoformat() if current_dose_since else None,
            "current_dose_duration_days": _days_between(current_dose_since, today),
            "dose_change_count": len(dose_changes),
            "provider_history": provider_history,
            "longest_stable_period_days": longest_stable,
            "prescription_status": rx_status,
            "adherence_30d": calculate_medicine_adherence_rate(user, days=30),
        }

    # ── Overall summary ──
    active = Intake.objects.filter(user=user, intake_status=Intake.STATUS_ACTIVE)
    earliest = (
        MedicationEvent.objects.filter(user=user)
        .order_by("effective_date").values_list("effective_date", flat=True).first()
    )
    cutoff = today - timedelta(days=90)
    recent_changes = MedicationEvent.objects.filter(
        user=user, effective_date__gte=cutoff,
    ).exclude(event_type="tracking_began").count()
    total_dose_changes = MedicationEvent.objects.filter(
        user=user, event_type="dose_changed",
    ).count()
    # Factual momentum label by recent-change frequency (NOT advice).
    if recent_changes == 0:
        momentum = "stable"
    elif recent_changes <= 2:
        momentum = "adjusting"
    else:
        momentum = "actively_changing"

    return {
        "treatment_started_date": earliest.isoformat() if earliest else None,
        "treatment_duration_days": _days_between(earliest, today),
        "active_medication_count": active.filter(intake_type=Intake.INTAKE_TYPE_MEDICATION).count(),
        "active_supplement_count": active.filter(intake_type=Intake.INTAKE_TYPE_SUPPLEMENT).count(),
        "total_dose_changes": total_dose_changes,
        "recent_change_count_90d": recent_changes,
        "treatment_momentum": momentum,
        "adherence_30d": calculate_medicine_adherence_rate(user, days=30),
    }
