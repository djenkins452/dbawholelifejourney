"""
Proactive Routine Planning Service

Identifies upcoming routines and suggests early action BEFORE signals
trigger. Answers "what can I get ahead of?" — not "what am I behind on."

Architecture: service layer only, no models, no DB writes.
Reads existing RoutineSchedule data (last_maintenance_date, follow_up_days).

Suppressed when urgent actions already exist (overdue/neglect).
"""

import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# How far ahead to look for upcoming maintenance
_LOOKAHEAD_MIN_DAYS = 3
_LOOKAHEAD_MAX_DAYS = 10

# Max suggestions to return (keep it light)
MAX_SUGGESTIONS = 2


def generate_proactive_suggestions(user):
    """
    Scan active routines for upcoming maintenance opportunities.

    Returns:
        list[dict] — up to MAX_SUGGESTIONS proactive items, each with:
            - schedule_id: int
            - schedule_name: str
            - type: 'upcoming' | 'load_balance'
            - priority: 'medium' | 'low'
            - message: str (CoS-ready)
            - days_until_due: int
        Returns empty list if urgent actions exist (suppression rule).
    """
    from apps.life.models import RoutineSchedule
    from apps.life.services.routine_action_service import get_routine_actions_for_user
    from apps.core.utils import get_user_today

    user_today = get_user_today(user)

    # Suppression check: if HIGH priority actions exist, don't add noise
    urgent_actions = get_routine_actions_for_user(user)
    has_urgent = any(a['priority'] == 'high' for a in urgent_actions)
    if has_urgent:
        return []

    # Find bridge-enabled schedules with follow_up_days
    schedules = RoutineSchedule.objects.filter(
        routine__user=user,
        routine__is_active=True,
        is_active=True,
        creates_maintenance_log=True,
        follow_up_days__isnull=False,
    ).select_related('routine')

    upcoming = []
    for schedule in schedules:
        if not schedule.last_maintenance_date or not schedule.follow_up_days:
            continue

        next_due = schedule.last_maintenance_date + timedelta(
            days=schedule.follow_up_days
        )
        days_until = (next_due - user_today).days

        # Only suggest items within the lookahead window
        if _LOOKAHEAD_MIN_DAYS <= days_until <= _LOOKAHEAD_MAX_DAYS:
            upcoming.append({
                'schedule_id': schedule.pk,
                'schedule_name': schedule.name,
                'type': 'upcoming',
                'priority': 'medium' if days_until <= 5 else 'low',
                'message': (
                    f"{schedule.name} is due in {days_until} days "
                    f"— consider handling it early"
                ),
                'days_until_due': days_until,
            })

    # Sort by soonest due first
    upcoming.sort(key=lambda s: s['days_until_due'])

    # Load balancing: if 3+ items due in the same week, add a note
    suggestions = upcoming[:MAX_SUGGESTIONS]
    if len(upcoming) >= 3:
        names = ', '.join(u['schedule_name'] for u in upcoming[:3])
        suggestions.append({
            'schedule_id': None,
            'schedule_name': '',
            'type': 'load_balance',
            'priority': 'low',
            'message': (
                f"Several maintenance items due soon ({names}) "
                f"— spread them out if you can"
            ),
            'days_until_due': 0,
        })

    return suggestions[:MAX_SUGGESTIONS]
