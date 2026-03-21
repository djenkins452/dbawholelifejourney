"""
Routine Signal → Action Service

Converts routine health signals into prioritized, actionable
recommendations. Answers "what should the user do?" not "what's
happening?"

Architecture: service layer only, no models, no side effects.
Reads from routine_health_service output and returns ranked actions.
"""

import logging

logger = logging.getLogger(__name__)

# Priority ranking (lower = higher priority)
_PRIORITY_RANK = {'high': 0, 'medium': 1, 'low': 2}

# Signal type → action mapping
_SIGNAL_ACTIONS = {
    'maintenance_overdue': {
        'action': 'perform_maintenance',
        'priority': 'high',
        'verb': 'Handle',
        'suffix': 'today',
    },
    'neglect': {
        'action': 'reset_routine',
        'priority': 'high',
        'verb': 'Address',
        'suffix': '— this needs attention',
    },
    'drift': {
        'action': 'stabilize_routine',
        'priority': 'medium',
        'verb': 'Get back on track with',
        'suffix': '',
    },
    'over_maintenance': {
        'action': 'slow_down',
        'priority': 'low',
        'verb': 'You may be overdoing',
        'suffix': '— check the schedule',
    },
}

# Maximum actions to return (keep focused, not overwhelming)
MAX_ACTIONS = 3


def generate_routine_actions(routine_signals):
    """
    Convert routine health signals into prioritized action recommendations.

    Args:
        routine_signals: list[dict] — output from evaluate_all_routine_health()
            Each entry has: schedule_id, schedule_name, routine_name,
            top_signal, all_signals

    Returns:
        list[dict] — up to MAX_ACTIONS items, sorted by priority + severity:
            - schedule_id: int
            - schedule_name: str
            - priority: 'high' | 'medium' | 'low'
            - action: str (action type key)
            - message: str (human-readable, for Beth)
    """
    if not routine_signals:
        return []

    actions = []

    for rs in routine_signals:
        signal = rs['top_signal']
        signal_type = signal.get('type', '')
        action_template = _SIGNAL_ACTIONS.get(signal_type)

        if not action_template:
            continue

        # Build human-readable message
        name = rs['schedule_name']
        days = signal.get('days', 0)

        if signal_type == 'maintenance_overdue' and days:
            message = f"{name} is {days} days overdue — handle today"
        elif signal_type == 'neglect':
            message = f"{name} needs attention — no activity recently"
        elif signal_type == 'drift':
            message = f"{name} is slipping — get back on track"
        elif signal_type == 'over_maintenance':
            message = f"You may be overdoing {name} — check the schedule"
        else:
            message = f"{action_template['verb']} {name} {action_template['suffix']}".strip()

        actions.append({
            'schedule_id': rs['schedule_id'],
            'schedule_name': name,
            'priority': action_template['priority'],
            'action': action_template['action'],
            'message': message,
            'severity_days': days,
        })

    # Sort: priority rank first, then by days overdue (descending)
    actions.sort(key=lambda a: (
        _PRIORITY_RANK.get(a['priority'], 9),
        -(a.get('severity_days') or 0),
    ))

    return actions[:MAX_ACTIONS]


def get_routine_actions_for_user(user):
    """
    Full pipeline: evaluate signals → generate actions for a user.

    Args:
        user: Django User instance

    Returns:
        list[dict] — up to MAX_ACTIONS prioritized recommendations
    """
    from apps.life.services.routine_health_service import evaluate_all_routine_health

    signals = evaluate_all_routine_health(user)
    return generate_routine_actions(signals)
