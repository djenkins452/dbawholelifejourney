"""
Medication domain adapter — evaluates Medicine/MedicineSchedule/MedicineLog
into canonical ComplianceEvent rows.
"""

import logging

from apps.dashboard_v2.compliance.constants import (
    ACTUAL_COMPLETED,
    ACTUAL_COMPLETED_LATE,
    ACTUAL_NONE,
    ACTUAL_SKIPPED,
    BUCKET_MEDICATION,
    DOMAIN_MEDICATION,
    FINAL_COMPLETED,
    FINAL_COMPLETED_LATE,
    FINAL_MISSED,
    FINAL_NOT_EXPECTED,
    FINAL_SKIPPED,
    REASON_AFTER_GRACE,
    REASON_EXPLICIT_MISSED,
    REASON_EXPLICIT_SKIP,
    REASON_INACTIVE_SCHEDULE,
    REASON_NO_LOG,
    REASON_ON_TIME,
    SOURCE_MEDICINE_LOG,
    SOURCE_MEDICINE_SCHEDULE,
)

logger = logging.getLogger(__name__)


def evaluate_medication(user, start_date, end_date):
    """
    Produce ComplianceEvent dicts for medication domain.

    One event per expected dose (medicine + schedule + date).
    """
    try:
        from apps.health.models import Intake, IntakeLog
        from apps.health.medicine_utils import get_expected_dose_entries

        active_medicines = list(
            Intake.objects.filter(
                user=user,
                intake_status=Intake.STATUS_ACTIVE,
            ).prefetch_related("schedules")
        )

        if not active_medicines:
            return []

        # Build lookup of logs: (medicine_id, schedule_id, date) → log
        logs = IntakeLog.objects.filter(
            user=user,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
        ).select_related("intake", "schedule")

        log_map = {}
        for log in logs:
            key = (log.intake_id, log.schedule_id, log.scheduled_date)
            log_map[key] = log

        # Object lookups so we can decorate each canonical expected-dose entry.
        med_by_id = {m.id: m for m in active_medicines}
        sched_by_id = {
            s.id: s
            for m in active_medicines
            for s in m.schedules.all()
            if s.is_active
        }

        # D5 / Canon §5 — single expected-dose author. Enumerate expected doses
        # via the ONE canonical helper (passing our already-fetched active
        # medicines to avoid a duplicate query) instead of re-walking schedules
        # here. This applies the future-dose-today fairness rule, so a dose
        # scheduled later today is no longer emitted as a MISSED compliance event
        # before it is due.
        events = []
        for med_id, sched_id, day in get_expected_dose_entries(
            user, start_date, end_date, active_medicines=active_medicines
        ):
            medicine = med_by_id.get(med_id)
            schedule = sched_by_id.get(sched_id)
            if medicine is None or schedule is None:
                continue
            log = log_map.get((med_id, sched_id, day))
            events.append(_build_dose_event(user, day, medicine, schedule, log))

        return events
    except Exception:
        logger.error("Medication compliance adapter failed", exc_info=True)
        return []


def _build_dose_event(user, day, medicine, schedule, log):
    """Build a single ComplianceEvent dict for one dose."""
    label = f"{medicine.name}"
    if schedule.scheduled_time:
        label += f" ({schedule.scheduled_time.strftime('%I:%M %p').lstrip('0')})"

    base = {
        "user": user,
        "event_date": day,
        "domain": DOMAIN_MEDICATION,
        "scoring_bucket": BUCKET_MEDICATION,
        "item_type": "MedicineSchedule",
        "item_id": schedule.id,
        "item_label": label,
        "expected_at": schedule.scheduled_time,
        "expected": True,
        "source_system": SOURCE_MEDICINE_LOG if log else SOURCE_MEDICINE_SCHEDULE,
        "intake_type": medicine.intake_type,
        "priority": medicine.priority,
    }

    if log:
        if log.log_status == "taken":
            base.update({
                "actual_status": ACTUAL_COMPLETED,
                "final_status": FINAL_COMPLETED,
                "reason_code": REASON_ON_TIME,
                "reason_detail": {"log_id": log.id},
            })
        elif log.log_status == "late":
            base.update({
                "actual_status": ACTUAL_COMPLETED_LATE,
                "final_status": FINAL_COMPLETED_LATE,
                "reason_code": REASON_AFTER_GRACE,
                "reason_detail": {
                    "log_id": log.id,
                    "grace_minutes": medicine.grace_period_minutes,
                },
            })
        elif log.log_status == "skipped":
            base.update({
                "actual_status": ACTUAL_SKIPPED,
                "final_status": FINAL_SKIPPED,
                "reason_code": REASON_EXPLICIT_SKIP,
                "reason_detail": {"log_id": log.id},
            })
        elif log.log_status == "missed":
            base.update({
                "actual_status": ACTUAL_NONE,
                "final_status": FINAL_MISSED,
                "reason_code": REASON_EXPLICIT_MISSED,
                "reason_detail": {"log_id": log.id},
            })
    else:
        # No log at all — unlogged = missed
        base.update({
            "actual_status": ACTUAL_NONE,
            "final_status": FINAL_MISSED,
            "reason_code": REASON_NO_LOG,
            "reason_detail": {},
        })

    return base
