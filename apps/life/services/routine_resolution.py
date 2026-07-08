# ==============================================================================
# File: apps/life/services/routine_resolution.py
# Description: RESOLVED ROUTINE OCCURRENCES for a date range — the single date-aware
#   resolution of a routine's occurrences from the ONE authoritative definition
#   (RoutineSchedule) + its one-day exceptions (RoutineLog). Every date's effective time
#   is `RoutineLog.rescheduled_time` (if a same-day reschedule exists) else the
#   RoutineSchedule template time. This is the multi-day sibling of
#   build_today_execution's today-only routine read: both resolve from the SAME source,
#   so the calendar (which needs a whole visible range) can never disagree with Beth
#   about a routine's time. Read-only, deterministic, never raises for the caller.
# ==============================================================================
import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


def resolve_routine_occurrences(user, start_date, end_date):
    """Resolve every routine occurrence between start_date and end_date (inclusive).

    Returns a list of dicts: {schedule_id, name, date, time, status, rescheduled}.
    `time` is the EFFECTIVE occurrence time (rescheduled override or template time).
    'skipped' occurrences are omitted; 'completed' are marked. Never raises."""
    try:
        from apps.life.models import RoutineSchedule, RoutineLog
    except Exception:
        return []
    if start_date is None or end_date is None or end_date < start_date:
        return []
    try:
        schedules = list(
            RoutineSchedule.objects.filter(
                routine__user=user, routine__is_active=True, is_active=True,
            ).select_related('routine'))
    except Exception:
        logger.warning("resolve_routine_occurrences: schedule query failed", exc_info=True)
        return []
    if not schedules:
        return []

    sched_ids = [s.id for s in schedules]
    logs = {}
    try:
        for log in RoutineLog.objects.filter(
                schedule_id__in=sched_ids,
                scheduled_date__range=(start_date, end_date)):
            logs[(log.schedule_id, log.scheduled_date)] = log
    except Exception:
        logger.warning("resolve_routine_occurrences: log query failed", exc_info=True)

    out = []
    day = start_date
    while day <= end_date:
        weekday = day.weekday()
        for s in schedules:
            # Applicability: a specific-date schedule fires only on that date; otherwise
            # the weekly day-of-week mask governs.
            if s.specific_date:
                if s.specific_date != day:
                    continue
            elif not s.applies_to_day(weekday):
                continue

            log = logs.get((s.id, day))
            status, eff_time, rescheduled = 'pending', s.scheduled_time, None
            if log is not None:
                st = log.log_status
                if st in ('completed', 'completed_late'):
                    status = 'completed'
                elif st == 'skipped':
                    continue  # user removed this occurrence for the day — don't surface
                elif st == 'rescheduled':
                    status = 'rescheduled'
                    rescheduled = log.rescheduled_time
                    eff_time = log.rescheduled_time or s.scheduled_time
            if eff_time is None:
                continue
            out.append({
                'schedule_id': s.id,
                'name': s.name,
                'date': day,
                'time': eff_time,
                'status': status,
                'rescheduled': rescheduled,
            })
        day += timedelta(days=1)
    return out
