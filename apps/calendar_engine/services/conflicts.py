"""
Conflict Detection Service — Habit Protection Layer.

Detects overlaps with protected events when moving/editing calendar events.
"""

from apps.calendar_engine.models import CalendarEvent, CalendarOverrideLog


def check_conflicts(user, start_dt, end_dt, exclude_event_id=None):
    """
    Check if the proposed time range overlaps with any protected events.

    Returns:
        dict with keys:
            conflict (bool)
            conflict_message (str)
            conflicting_events (list of dicts)
    """
    qs = CalendarEvent.objects.filter(
        user=user,
        is_protected=True,
        status=CalendarEvent.STATUS_SCHEDULED,
        start_dt__lt=end_dt,
        end_dt__gt=start_dt,
    )
    if exclude_event_id:
        qs = qs.exclude(pk=exclude_event_id)

    # Also expand recurring protected events
    conflicts = []
    for event in qs:
        conflicts.append({
            'id': event.pk,
            'title': event.title,
            'start_dt': event.start_dt.isoformat(),
            'end_dt': event.end_dt.isoformat(),
            'domain': event.domain.name if event.domain else None,
        })

    # Check recurring protected events that might also overlap
    recurring_protected = CalendarEvent.objects.filter(
        user=user,
        is_protected=True,
        status=CalendarEvent.STATUS_SCHEDULED,
    ).exclude(pk__in=[c['id'] for c in conflicts])

    if exclude_event_id:
        recurring_protected = recurring_protected.exclude(pk=exclude_event_id)

    for event in recurring_protected:
        if hasattr(event, 'recurrence'):
            occurrences = event.recurrence.get_occurrences(start_dt, end_dt)
            for occ_start, occ_end in occurrences:
                if occ_start < end_dt and occ_end > start_dt:
                    conflicts.append({
                        'id': event.pk,
                        'title': event.title,
                        'start_dt': occ_start.isoformat(),
                        'end_dt': occ_end.isoformat(),
                        'domain': event.domain.name if event.domain else None,
                        'is_occurrence': True,
                    })
                    break  # One conflict per series is enough

    if not conflicts:
        return {'conflict': False, 'conflict_message': '', 'conflicting_events': []}

    titles = ', '.join(c['title'] for c in conflicts[:3])
    message = f"This conflicts with protected time: {titles}. Continue?"

    return {
        'conflict': True,
        'conflict_message': message,
        'conflicting_events': conflicts,
    }


def log_override(user, event, overridden_event, reason=''):
    """Log that a user chose to override a protected-event conflict."""
    return CalendarOverrideLog.objects.create(
        user=user,
        event=event,
        overridden_event=overridden_event,
        reason=reason,
    )
