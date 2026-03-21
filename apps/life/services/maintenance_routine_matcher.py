"""
Maintenance → Routine Matching Service

Passive intelligence layer that finds likely RoutineSchedule matches
for a MaintenanceLog entry. Score-based heuristics (v1) — no ML.

All matches are suggestions requiring user confirmation.
No automatic updates. No FK between systems.
"""

import logging

logger = logging.getLogger(__name__)

# Minimum score threshold to include a match in results
MATCH_THRESHOLD = 70
MAX_RESULTS = 3


def _title_similarity_score(maintenance_title, schedule_name):
    """
    Simple word-overlap similarity between two strings.

    Returns 0-100 score based on percentage of words in common.
    """
    if not maintenance_title or not schedule_name:
        return 0

    words_a = set(maintenance_title.lower().split())
    words_b = set(schedule_name.lower().split())

    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'of', 'for', 'to', 'in', 'on', 'at'}
    words_a -= stop_words
    words_b -= stop_words

    if not words_a or not words_b:
        return 0

    overlap = words_a & words_b
    if not overlap:
        # Check for substring containment (e.g., "oil change" in "Oil Change Service")
        a_lower = maintenance_title.lower()
        b_lower = schedule_name.lower()
        if a_lower in b_lower or b_lower in a_lower:
            return 60
        return 0

    # Jaccard-style similarity, scaled to 0-100
    union = words_a | words_b
    return int(len(overlap) / len(union) * 100)


def find_matching_routines(maintenance_log, user):
    """
    Find RoutineSchedules that likely correspond to a MaintenanceLog.

    Only searches schedules with creates_maintenance_log=True.

    Args:
        maintenance_log: MaintenanceLog instance (just saved)
        user: Django User instance

    Returns:
        list[dict] — top matches above threshold, each with:
            - schedule_id: int
            - schedule_name: str
            - routine_name: str
            - score: int (0-100)
            - reason: str (human-readable explanation)
    """
    try:
        from apps.life.models import RoutineSchedule

        # Only match against bridge-enabled schedules for this user
        candidates = RoutineSchedule.objects.filter(
            routine__user=user,
            routine__is_active=True,
            is_active=True,
            creates_maintenance_log=True,
        ).select_related('routine')

        if not candidates.exists():
            return []

        results = []
        log_title = maintenance_log.title or ''
        log_type = maintenance_log.log_type or ''
        log_area = (maintenance_log.area or '').strip().lower()

        for schedule in candidates:
            score = 0
            reasons = []

            # Area match: +40 points (case-insensitive)
            sched_area = (schedule.maintenance_area or '').strip().lower()
            if log_area and sched_area and log_area == sched_area:
                score += 40
                reasons.append('area')
            elif log_area and sched_area and (
                log_area in sched_area or sched_area in log_area
            ):
                score += 25
                reasons.append('area (partial)')

            # Type match: +30 points
            sched_type = (schedule.maintenance_type or '').strip().lower()
            if log_type and sched_type and log_type == sched_type:
                score += 30
                reasons.append('type')

            # Title similarity: +30 points
            sched_title = schedule.default_maintenance_title or schedule.name
            title_score = _title_similarity_score(log_title, sched_title)
            title_points = int(title_score * 0.3)  # Scale to max 30
            if title_points > 0:
                score += title_points
                reasons.append('title')

            if score >= MATCH_THRESHOLD:
                results.append({
                    'schedule_id': schedule.pk,
                    'schedule_name': schedule.name,
                    'routine_name': schedule.routine.name,
                    'score': min(score, 100),
                    'reason': 'Matched on ' + ' + '.join(reasons),
                })

        # Sort by score descending, cap at MAX_RESULTS
        results.sort(key=lambda r: r['score'], reverse=True)
        return results[:MAX_RESULTS]

    except Exception:
        logger.warning("Maintenance routine matcher failed", exc_info=True)
        return []
