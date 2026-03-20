"""
Shared Behavior Status Engine — single source of truth for occurrence status.

ALL behavioral domains (medication, workouts, routines) MUST use this function
to determine occurrence status. No domain-specific status logic allowed.

Status vocabulary:
  - completed: log exists, within grace window
  - completed_late: log exists, after grace window
  - upcoming: scheduled time is in the future
  - past_due: scheduled time has passed but within grace window
  - late: scheduled time + grace window has passed, no log
  - missed: (computed in adherence only — absence of log after day ends)
"""

from datetime import datetime, timedelta


def compute_occurrence_status(now, scheduled_datetime, grace_minutes, log=None):
    """
    Deterministic status computation for a single scheduled occurrence.

    Args:
        now: datetime — current time (timezone-aware)
        scheduled_datetime: datetime — when the occurrence was scheduled
        grace_minutes: int — grace period in minutes after scheduled time
        log: dict or None — {completed_at: datetime} if a completion log exists

    Returns:
        str — one of: 'completed', 'completed_late', 'upcoming', 'past_due', 'late'
    """
    grace_end = scheduled_datetime + timedelta(minutes=grace_minutes)

    if log and log.get('completed_at'):
        completed_at = log['completed_at']
        if completed_at <= grace_end:
            return 'completed'
        return 'completed_late'

    # No log — determine current status based on time
    if now < scheduled_datetime:
        return 'upcoming'
    elif now <= grace_end:
        return 'past_due'
    else:
        return 'late'


# ── Adherence scoring weights (strict accountability model) ──
ADHERENCE_WEIGHTS = {
    'completed': 1.0,
    'completed_late': 0.7,
    'rescheduled': 0.0,   # Not yet completed — scores 0 until resolved to completed_late
    'skipped': 0.0,
    'missed': 0.0,
}


def compute_adherence_from_counts(expected, completed, late, skipped, missed):
    """
    Compute adherence score using the strict accountability model.

    Args:
        expected: int — total scheduled occurrences
        completed: int — completed on time
        late: int — completed late (within day but after grace)
        skipped: int — intentionally skipped
        missed: int — not completed at all

    Returns:
        dict with adherence (0-100), on_time_rate (0-100 or None)
    """
    if expected == 0:
        return {'adherence': None, 'on_time_rate': None}

    score_sum = (
        completed * ADHERENCE_WEIGHTS['completed']
        + late * ADHERENCE_WEIGHTS['completed_late']
        + skipped * ADHERENCE_WEIGHTS['skipped']
        + missed * ADHERENCE_WEIGHTS['missed']
    )
    adherence = round((score_sum / expected) * 100, 1)
    adherence = min(adherence, 100.0)

    # On-time rate: of all completions (on-time + late), what % were on time?
    total_completed = completed + late
    if total_completed > 0:
        on_time_rate = round((completed / total_completed) * 100, 1)
    else:
        on_time_rate = None

    return {'adherence': adherence, 'on_time_rate': on_time_rate}


def build_behavior_output(domain, expected, completed, late, skipped, missed):
    """
    Build the standardized behavior output contract for a domain.

    Returns:
        dict matching the behavior score contract
    """
    scores = compute_adherence_from_counts(expected, completed, late, skipped, missed)
    return {
        'domain': domain,
        'adherence': scores['adherence'],
        'on_time_rate': scores['on_time_rate'],
        'expected': expected,
        'completed': completed,
        'late': late,
        'skipped': skipped,
        'missed': missed,
    }
