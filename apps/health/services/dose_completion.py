# ==============================================================================
# File: apps/health/services/dose_completion.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The ONE deterministic authority for completing a scheduled dose
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-08-18
# ==============================================================================
"""Canonical dose completion — shared by the Dashboard control AND the Chief of Staff.

WHY THIS EXISTS: this logic previously lived INLINE in
`apps/dashboard_v2/views.py :: IntakeLogAction.post`, so the visible UI button and the
CoS had no shared authority to converge on. The 2026-08-18 "Mark Shower complete"
incident exposed the class: WLJ surfaces `medication_dose` / `supplement_dose` as
executable, but no domain-owned service existed for anything except the view to call.

Behaviour is a faithful extraction of the view's logic — occurrence-scoped
`scheduled_date`, `mark_taken()` for late/on-time classification, supply adjustment, and
the domain event. Medications and supplements share ONE authority because they share one
underlying model (`IntakeSchedule`/`IntakeLog`); the only difference is which `Intake`
row the schedule points at.
"""

import logging

logger = logging.getLogger(__name__)


def is_dose_complete(user, schedule, target_date) -> bool:
    """True when this exact occurrence is already logged as taken/late."""
    from apps.health.models import IntakeLog
    return IntakeLog.objects.filter(
        user=user, intake=schedule.intake, schedule=schedule,
        scheduled_date=target_date, log_status__in=["taken", "late"],
    ).exists()


def complete_dose(user, schedule, target_date, *, source=None):
    """Mark ONE scheduled dose occurrence taken. Idempotent; never raises for the
    already-taken case.

    Returns a structured result:
        {"status": "recorded"|"already_complete"|"not_applicable", "log_id": int|None,
         "title": str, "scheduled_date": iso}
    """
    from apps.core.events.domain_events import EventTypes, safe_emit_event
    from apps.health.models import IntakeLog

    medicine = schedule.intake
    title = getattr(medicine, "name", "") or "Dose"

    # Occurrence validity — the schedule must actually apply to that weekday.
    try:
        applies = schedule.applies_to_day(target_date.weekday())
    except Exception:  # pragma: no cover - defensive
        applies = True
    if not applies:
        return {"status": "not_applicable", "log_id": None, "title": title,
                "scheduled_date": target_date.isoformat()}

    if is_dose_complete(user, schedule, target_date):
        return {"status": "already_complete", "log_id": None, "title": title,
                "scheduled_date": target_date.isoformat()}

    log, _created = IntakeLog.objects.get_or_create(
        user=user, intake=medicine, schedule=schedule, scheduled_date=target_date,
        defaults={
            "scheduled_time": schedule.scheduled_time,
            "is_prn_dose": False,
            "source": source or IntakeLog.SOURCE_UI_PER_ITEM,
        },
    )
    # mark_taken handles late/on-time classification via the grace period.
    log.mark_taken(source=source or IntakeLog.SOURCE_UI_PER_ITEM)

    if medicine.current_supply is not None and medicine.current_supply > 0:
        medicine.current_supply -= 1
        medicine.save(update_fields=["current_supply", "updated_at"])

    safe_emit_event(EventTypes.HEALTH_MEDICATION_TAKEN, user, {
        "log_id": log.id, "medicine_name": medicine.name,
        "source": "dose_completion_service",
    })
    return {"status": "recorded", "log_id": log.id, "title": title,
            "scheduled_date": target_date.isoformat()}


def undo_dose(user, schedule, target_date):
    """Reverse a logged dose (the Dashboard toggle's 'undo' half). Restores supply."""
    from apps.health.models import IntakeLog
    existing = IntakeLog.objects.filter(
        user=user, intake=schedule.intake, schedule=schedule,
        scheduled_date=target_date, log_status__in=["taken", "late"],
    ).first()
    if not existing:
        return {"status": "not_logged"}
    existing.delete()
    medicine = schedule.intake
    if medicine.current_supply is not None:
        medicine.current_supply += 1
        medicine.save(update_fields=["current_supply", "updated_at"])
    return {"status": "undone"}
