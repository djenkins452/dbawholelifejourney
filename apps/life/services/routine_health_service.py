"""
Routine Health & Drift Signal Service

Evaluates routine health over time and produces signals for Beth and
the dashboard. Reads from existing data — does NOT modify any models.

Signal types:
  - maintenance_overdue: follow_up_days elapsed since last_maintenance_date
  - drift: 3+ of last 5 completions are late, skipped, or missing
  - over_maintenance: maintenance logged more frequently than follow_up_days
  - neglect: bridge-enabled schedule with no activity for extended period

Architecture: service layer only, no new models, no side effects.
"""

import logging
from datetime import timedelta

logger = logging.getLogger(__name__)


def evaluate_routine_health(schedule, user_today):
    """
    Evaluate health signals for a single RoutineSchedule.

    Args:
        schedule: RoutineSchedule instance (with routine relation loaded)
        user_today: date — the user's local date

    Returns:
        list[dict] — signals found (empty if healthy), each with:
            - type: str
            - severity: 'high' | 'medium' | 'low'
            - detail: str (human-readable, for Beth)
            - days: int (optional context)
    """
    signals = []

    # 1. Maintenance overdue
    if schedule.creates_maintenance_log and schedule.follow_up_days:
        overdue_signal = _check_maintenance_overdue(schedule, user_today)
        if overdue_signal:
            signals.append(overdue_signal)

    # 2. Drift (lateness/skip trend)
    drift_signal = _check_drift(schedule, user_today)
    if drift_signal:
        signals.append(drift_signal)

    # 3. Over-maintenance
    if schedule.creates_maintenance_log and schedule.follow_up_days:
        over_signal = _check_over_maintenance(schedule, user_today)
        if over_signal:
            signals.append(over_signal)

    # 4. Neglect
    if schedule.creates_maintenance_log:
        neglect_signal = _check_neglect(schedule, user_today)
        if neglect_signal:
            signals.append(neglect_signal)

    return signals


def evaluate_all_routine_health(user):
    """
    Evaluate health signals for all active routines for a user.

    Returns:
        list[dict] — one entry per schedule that has signals:
            - schedule_id: int
            - schedule_name: str
            - routine_name: str
            - top_signal: dict (highest severity signal)
            - all_signals: list[dict]
    """
    from apps.life.models import RoutineSchedule
    from apps.core.utils import get_user_today

    user_today = get_user_today(user)

    schedules = RoutineSchedule.objects.filter(
        routine__user=user,
        routine__is_active=True,
        is_active=True,
    ).select_related('routine')

    results = []
    _severity_rank = {'high': 0, 'medium': 1, 'low': 2}

    for schedule in schedules:
        signals = evaluate_routine_health(schedule, user_today)
        if signals:
            # Top signal = highest severity
            signals.sort(key=lambda s: _severity_rank.get(s['severity'], 9))
            results.append({
                'schedule_id': schedule.pk,
                'schedule_name': schedule.name,
                'routine_name': schedule.routine.name,
                'top_signal': signals[0],
                'all_signals': signals,
            })

    return results


# ─── Internal signal detectors ───


def _check_maintenance_overdue(schedule, user_today):
    """Check if maintenance is overdue based on follow_up_days."""
    if not schedule.last_maintenance_date or not schedule.follow_up_days:
        return None

    next_due = schedule.last_maintenance_date + timedelta(days=schedule.follow_up_days)
    if user_today > next_due:
        days_overdue = (user_today - next_due).days
        severity = 'high' if days_overdue > 14 else 'medium'
        return {
            'type': 'maintenance_overdue',
            'severity': severity,
            'detail': (
                f"{schedule.name} maintenance is {days_overdue} days overdue"
            ),
            'days': days_overdue,
        }
    return None


def _check_drift(schedule, user_today):
    """Check for completion drift — late/skipped/missing pattern."""
    from apps.life.models import RoutineLog

    # Last 5 logs for this schedule
    recent_logs = list(
        RoutineLog.objects.filter(
            schedule=schedule,
            scheduled_date__lte=user_today,
        ).order_by('-scheduled_date')[:5]
    )

    if len(recent_logs) < 3:
        return None  # Not enough data to detect a pattern

    # Count problematic completions
    problem_count = 0
    for log in recent_logs:
        if log.log_status in ('completed_late', 'skipped'):
            problem_count += 1

    if problem_count >= 3:
        severity = 'high' if problem_count >= 4 else 'medium'
        if all(l.log_status == 'skipped' for l in recent_logs[:3]):
            pattern = 'consistently skipped'
        elif problem_count >= 4:
            pattern = 'frequently late or skipped'
        else:
            pattern = 'slipping — several late completions'
        return {
            'type': 'drift',
            'severity': severity,
            'detail': f"{schedule.name} is {pattern}",
            'days': 0,
        }
    return None


def _check_over_maintenance(schedule, user_today):
    """Check if maintenance is happening too frequently."""
    from apps.life.models import MaintenanceLog

    if not schedule.follow_up_days:
        return None

    # Expected interval
    expected_interval = schedule.follow_up_days
    # Check maintenance logs in the last interval period
    window_start = user_today - timedelta(days=expected_interval)

    log_count = MaintenanceLog.objects.filter(
        user=schedule.routine.user,
        matched_schedule_id=schedule.pk,
        date__gte=window_start,
        date__lte=user_today,
    ).count()

    if log_count >= 2:
        return {
            'type': 'over_maintenance',
            'severity': 'low',
            'detail': (
                f"{schedule.name} was maintained {log_count} times "
                f"in the last {expected_interval} days (expected once)"
            ),
            'days': 0,
        }
    return None


def _check_neglect(schedule, user_today):
    """Check for long periods with no activity at all."""
    from apps.life.models import RoutineLog, MaintenanceLog

    # Only flag neglect for bridge-enabled schedules where we expect
    # periodic maintenance. Use follow_up_days * 2 as the neglect threshold,
    # or 60 days if no follow_up_days.
    threshold_days = (schedule.follow_up_days or 30) * 2
    threshold_date = user_today - timedelta(days=threshold_days)

    # Check for any recent routine completion
    has_recent_completion = RoutineLog.objects.filter(
        schedule=schedule,
        scheduled_date__gte=threshold_date,
        log_status__in=('completed', 'completed_late'),
    ).exists()

    if has_recent_completion:
        return None

    # Check for any recent maintenance log
    has_recent_maintenance = MaintenanceLog.objects.filter(
        user=schedule.routine.user,
        matched_schedule_id=schedule.pk,
        date__gte=threshold_date,
    ).exists()

    if has_recent_maintenance:
        return None

    # Also check last_maintenance_date as a fallback
    if schedule.last_maintenance_date and schedule.last_maintenance_date >= threshold_date:
        return None

    return {
        'type': 'neglect',
        'severity': 'high',
        'detail': (
            f"{schedule.name} has had no activity for {threshold_days}+ days"
        ),
        'days': threshold_days,
    }
