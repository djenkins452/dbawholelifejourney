# ==============================================================================
# File: apps/life/services/routine_cleanup.py
# Description: LEGACY ROUTINE CLEANUP (commit 2 of the single-source-execution
#   initiative). Historically a routine could be born as a Task(is_routine=True,
#   is_recurring=True) — projected to a CalendarEvent — while Beth/dashboard/overdue read
#   the canonical RoutineSchedule (+ RoutineLog). Those two representations drift: a stale
#   twin CalendarEvent disagrees with Beth. This collapses every legacy Task(is_routine)
#   routine ONTO the canonical Routine + RoutineSchedule so existing data obeys the same
#   invariant as new data — ONE definition, ONE writer (RoutineLog), ONE resolved reader
#   (build_today_execution / resolve_routine_occurrences).
#
#   Per routine (matched by user + title, case-insensitive):
#     1. Ensure a canonical RoutineSchedule exists (create Routine + RoutineSchedule from
#        the Task if the routine has no canonical definition yet).
#     2. Stop recurrence + soft-delete the Task series (RecurrenceService.delete_task_series
#        / Task.soft_delete) so it can never regenerate or re-project.
#     3. Cancel the series' projected CalendarEvents (source_type='task') so the stale twin
#        vanishes and the calendar shows the resolved occurrence instead.
#   Idempotent (already-collapsed routines have no active is_routine Task). Never raises
#   per-routine — one bad routine can't abort the batch.
# ==============================================================================
import logging

logger = logging.getLogger(__name__)


def _days_from_recurrence(pattern):
    p = (pattern or 'daily').lower().strip()
    if p in ('every_weekday', 'weekdays'):
        return '0,1,2,3,4'
    if p.startswith('weekly:'):
        names = {'mon': '0', 'tue': '1', 'wed': '2', 'thu': '3',
                 'fri': '4', 'sat': '5', 'sun': '6'}
        days = [names[d.strip()[:3]] for d in p.split(':', 1)[1].split(',')
                if d.strip()[:3] in names]
        return ','.join(days) or '0,1,2,3,4,5,6'
    return '0,1,2,3,4,5,6'


def collapse_dual_defined_routines(user=None):
    """Collapse legacy Task(is_routine) routines onto canonical RoutineSchedule.

    Returns counts: {routines, schedules_created, events_canceled, tasks_retired}."""
    from apps.life.models import Task, Routine, RoutineSchedule
    from apps.life.services.recurrence import RecurrenceService
    try:
        from apps.calendar_engine.models import CalendarEvent
    except Exception:
        CalendarEvent = None

    counts = {'routines': 0, 'schedules_created': 0,
              'events_canceled': 0, 'tasks_retired': 0}

    base = Task.objects.filter(is_routine=True)
    if user is not None:
        base = base.filter(user=user)

    seen = set()
    for rep in base.select_related('user').order_by('user_id', 'title'):
        title = (rep.title or '').strip()
        key = (rep.user_id, title.lower())
        if not title or key in seen:
            continue
        seen.add(key)
        # A routine with no scheduled time never produced a divergent calendar time —
        # leave it alone (nothing to collapse).
        if not rep.scheduled_time:
            continue
        counts['routines'] += 1

        try:
            # 1. Ensure the canonical definition exists.
            sched = RoutineSchedule.objects.filter(
                routine__user=rep.user, name__iexact=title, is_active=True).first()
            if sched is None:
                time_of_day = 'morning'
                try:
                    from apps.core.time_windows import get_window_for_hour
                    w = get_window_for_hour(rep.scheduled_time.hour)
                    time_of_day = w if w != 'other' else 'morning'
                except Exception:
                    pass
                routine = Routine.objects.create(
                    user=rep.user, name=title, description=rep.notes or '',
                    time_of_day=time_of_day, is_active=True)
                RoutineSchedule.objects.create(
                    routine=routine, name=title, scheduled_time=rep.scheduled_time,
                    grace_period_minutes=30,
                    days_of_week=_days_from_recurrence(
                        getattr(rep, 'recurrence_pattern', None)),
                    is_active=True)
                counts['schedules_created'] += 1

            # 2. Collect the series' task pks BEFORE retiring (for calendar cancel),
            #    then stop recurrence + soft-delete the whole series.
            series_pks = [
                str(pk) for pk in Task.all_objects.filter(
                    user=rep.user, title=rep.title, is_routine=True,
                ).values_list('pk', flat=True)
            ]
            if getattr(rep, 'is_recurring', False):
                RecurrenceService.delete_task_series(rep)
            for t in Task.objects.filter(
                    user=rep.user, title=rep.title, is_routine=True):
                t.soft_delete()
            counts['tasks_retired'] += 1

            # 3. Cancel the twin CalendarEvents (runs AFTER retire, so any re-projection
            #    from the soft-delete signal is also cancelled).
            if CalendarEvent is not None and series_pks:
                try:
                    n = CalendarEvent.objects.filter(
                        user=rep.user,
                        source_type=CalendarEvent.SOURCE_TASK,
                        source_id__in=series_pks,
                    ).exclude(status=CalendarEvent.STATUS_CANCELED).update(
                        status=CalendarEvent.STATUS_CANCELED)
                    counts['events_canceled'] += n
                except Exception:
                    logger.warning(
                        "collapse: cancel calendar events failed user=%s title=%r",
                        rep.user_id, title, exc_info=True)
        except Exception:
            logger.warning(
                "collapse: routine collapse failed user=%s title=%r",
                rep.user_id, title, exc_info=True)

    logger.info("collapse_dual_defined_routines: %s", counts)
    return counts
