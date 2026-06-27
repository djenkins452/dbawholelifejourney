"""
Medication history — the single write authority for the MedicationEvent ledger.

Medication Intelligence Canon §5/§6.1 + Design Assurance C10b: history has exactly
ONE writer. Every treatment change (started, paused, resumed, discontinued, dose/
frequency/provider/pharmacy changed, refill) is appended here as an immutable
``MedicationEvent``. ``Intake`` remains the canonical current-state projection;
this ledger is the canonical history. Do NOT create MedicationEvent rows directly
elsewhere — call ``record_medication_change``.
"""

from django.utils import timezone


def record_medication_change(
    intake,
    event_type,
    *,
    previous_value=None,
    new_value=None,
    reason=None,
    reason_detail="",
    provider=None,
    source=None,
    effective_date=None,
):
    """Append one immutable MedicationEvent for ``intake``.

    Args:
        intake: the Intake whose treatment changed.
        event_type: one of ``MedicationEvent.EVENT_*``.
        previous_value / new_value: JSON-safe snapshots of the changed attribute(s).
        reason: one of ``MedicationEvent.REASON_*`` (defaults to UNKNOWN — we never
            assume a clinical reason the user did not give).
        reason_detail: free-text detail (e.g., a paused reason).
        provider: optional MedicalProvider associated with the change.
        source: one of ``MedicationEvent.SOURCE_*`` (defaults to LIFECYCLE).
        effective_date: user-local date the change took effect (defaults to today).

    Returns:
        the created MedicationEvent.
    """
    from apps.core.utils import get_user_today
    from apps.health.models import MedicationEvent

    if reason is None:
        reason = MedicationEvent.REASON_UNKNOWN
    if source is None:
        source = MedicationEvent.SOURCE_LIFECYCLE
    if effective_date is None:
        effective_date = (
            get_user_today(intake.user) if intake.user_id else timezone.now().date()
        )

    return MedicationEvent.objects.create(
        user=intake.user,
        intake=intake,
        event_type=event_type,
        effective_date=effective_date,
        previous_value=previous_value,
        new_value=new_value,
        reason=reason,
        reason_detail=reason_detail or "",
        provider=provider,
        source=source,
    )


def get_medication_timeline(intake):
    """Return the deterministic, newest-first treatment timeline for an Intake.

    This is the canonical timeline read (Sprint 2D foundation): the immutable
    MedicationEvent ledger ordered for display. No fabrication — it contains only
    events that were actually recorded, beginning with the honest ``tracking_began``
    (or ``started``) marker.
    """
    return list(intake.events.all())  # Meta.ordering = -effective_date, -created_at
