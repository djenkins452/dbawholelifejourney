"""
Routine domain adapter — evaluates Routine/RoutineSchedule/RoutineLog
into canonical ComplianceEvent rows.

Important: Routine items that map to other domains (workout, journal, faith)
are tagged with a reason_detail['cross_domain'] field for dedupe visibility.
They still count in the routine bucket unless explicitly linked.
"""

import logging
from datetime import timedelta

from apps.dashboard_v2.compliance.constants import (
    ACTUAL_COMPLETED,
    ACTUAL_COMPLETED_LATE,
    ACTUAL_NONE,
    ACTUAL_RESCHEDULED,
    ACTUAL_SKIPPED,
    BUCKET_ROUTINE,
    DOMAIN_ROUTINE,
    FINAL_COMPLETED,
    FINAL_COMPLETED_LATE,
    FINAL_MISSED,
    FINAL_RESCHEDULED,
    FINAL_SKIPPED,
    REASON_AFTER_GRACE,
    REASON_ASSERTED_ON_TIME,
    REASON_EXPLICIT_SKIP,
    REASON_NO_LOG,
    REASON_ON_TIME,
    REASON_RESCHEDULED,
    SOURCE_ROUTINE_LOG,
    SOURCE_ROUTINE_SCHEDULE,
)

logger = logging.getLogger(__name__)


def evaluate_routine(user, start_date, end_date):
    """
    Produce ComplianceEvent dicts for routine domain.

    One event per expected routine item per day.
    """
    try:
        from apps.life.models import Routine, RoutineLog

        active_routines = Routine.objects.filter(
            user=user, is_active=True, status="active",
        ).prefetch_related("items")

        if not active_routines.exists():
            return []

        # Gather all active schedule items
        all_items = []
        for routine in active_routines:
            for item in routine.items.filter(is_active=True):
                all_items.append((routine, item))

        if not all_items:
            return []

        # Build log lookup: (schedule_id, date) → log
        schedule_ids = [item.id for _, item in all_items]
        logs = RoutineLog.objects.filter(
            user=user,
            schedule_id__in=schedule_ids,
            scheduled_date__gte=start_date,
            scheduled_date__lte=end_date,
        )
        log_map = {}
        for log in logs:
            key = (log.schedule_id, log.scheduled_date)
            log_map[key] = log

        events = []
        day = start_date
        while day <= end_date:
            day_of_week = day.weekday()
            for routine, item in all_items:
                applies = False
                if item.specific_date:
                    applies = item.specific_date == day
                else:
                    applies = item.applies_to_day(day_of_week)

                if not applies:
                    continue

                key = (item.id, day)
                log = log_map.get(key)

                time_label = ""
                if item.scheduled_time:
                    time_label = f" ({item.scheduled_time.strftime('%I:%M %p').lstrip('0')})"

                label = f"{item.name}{time_label}"

                event = _build_routine_event(user, day, routine, item, label, log)
                events.append(event)

            day += timedelta(days=1)

        return events
    except Exception:
        logger.error("Routine compliance adapter failed", exc_info=True)
        return []


def _build_routine_event(user, day, routine, schedule_item, label, log):
    """Build a single ComplianceEvent dict for one routine item."""
    base = {
        "user": user,
        "event_date": day,
        "domain": DOMAIN_ROUTINE,
        "scoring_bucket": BUCKET_ROUTINE,
        "item_type": "RoutineSchedule",
        "item_id": schedule_item.id,
        "item_label": label,
        "expected_at": schedule_item.scheduled_time,
        "expected": True,
        "source_system": SOURCE_ROUTINE_LOG if log else SOURCE_ROUTINE_SCHEDULE,
        "reason_detail": {
            "routine_name": routine.name,
            "time_of_day": routine.time_of_day if hasattr(routine, "time_of_day") else None,
        },
    }

    if log:
        if log.log_status == "completed":
            base.update({
                "actual_status": ACTUAL_COMPLETED,
                "final_status": FINAL_COMPLETED,
                "reason_code": REASON_ON_TIME,
            })
        elif log.log_status == "completed_late":
            if getattr(log, "completed_as_scheduled", False):
                base.update({
                    "actual_status": ACTUAL_COMPLETED,
                    "final_status": FINAL_COMPLETED,
                    "reason_code": REASON_ASSERTED_ON_TIME,
                })
            else:
                base.update({
                    "actual_status": ACTUAL_COMPLETED_LATE,
                    "final_status": FINAL_COMPLETED_LATE,
                    "reason_code": REASON_AFTER_GRACE,
                    "reason_detail": {
                        **base["reason_detail"],
                        "grace_minutes": schedule_item.grace_period_minutes,
                    },
                })
        elif log.log_status == "skipped":
            base.update({
                "actual_status": ACTUAL_SKIPPED,
                "final_status": FINAL_SKIPPED,
                "reason_code": REASON_EXPLICIT_SKIP,
            })
        elif log.log_status == "rescheduled":
            base.update({
                "actual_status": ACTUAL_RESCHEDULED,
                "final_status": FINAL_RESCHEDULED,
                "reason_code": REASON_RESCHEDULED,
                "reason_detail": {
                    **base["reason_detail"],
                    "reschedule_count": getattr(log, "reschedule_count", 0),
                },
            })
    else:
        base.update({
            "actual_status": ACTUAL_NONE,
            "final_status": FINAL_MISSED,
            "reason_code": REASON_NO_LOG,
        })

    return base
