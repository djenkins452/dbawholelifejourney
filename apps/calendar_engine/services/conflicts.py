"""
Conflict Detection Service — Calendar Conflict Policy.

Phase 10: Pre-commit conflict detection for all calendar events.
No silent double-booking — every time overlap requires a user decision
before the event is created or updated.

Two detection layers:
- check_conflicts(): Legacy — checks only is_protected=True events
- detect_all_conflicts(): Phase 10 — checks ALL scheduled events
"""

import logging

from django.utils import timezone as dj_timezone

from apps.calendar_engine.models import CalendarEvent, CalendarOverrideLog

logger = logging.getLogger(__name__)


def _get_user_tz(user):
    """Get user's timezone for local-time display. Falls back to current tz."""
    try:
        from zoneinfo import ZoneInfo
        tz_name = user.preferences.timezone_iana
        if tz_name:
            return ZoneInfo(tz_name)
    except (AttributeError, Exception):
        pass
    return dj_timezone.get_current_timezone()


# ------------------------------------------------------------------ #
# Legacy: protected-event-only conflict check
# ------------------------------------------------------------------ #

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


# ------------------------------------------------------------------ #
# Phase 10: Full conflict detection (ALL scheduled events)
# ------------------------------------------------------------------ #

def detect_all_conflicts(user, start_dt, end_dt, exclude_event_id=None):
    """
    Check ALL scheduled events for time overlap — not just protected ones.

    Overlap formula: existing.start_dt < new.end_dt AND existing.end_dt > new.start_dt
    Only considers non-canceled, non-deleted events.

    Times in the returned dicts are converted to the user's local timezone
    so conflict messages display correctly (not UTC).

    Returns:
        dict with keys:
            has_conflict (bool)
            conflicts (list of dicts with id, title, start_dt, end_dt,
                       is_protected, domain)
    """
    qs = CalendarEvent.objects.filter(
        user=user,
        status=CalendarEvent.STATUS_SCHEDULED,
        start_dt__lt=end_dt,
        end_dt__gt=start_dt,
        deleted_at__isnull=True,
    )
    if exclude_event_id:
        qs = qs.exclude(pk=exclude_event_id)

    user_tz = _get_user_tz(user)

    conflicts = []
    for event in qs:
        # Convert UTC → user timezone for display
        local_start = event.start_dt.astimezone(user_tz)
        local_end = event.end_dt.astimezone(user_tz)
        conflicts.append({
            'id': event.pk,
            'title': event.title,
            'start_dt': local_start.isoformat(),
            'end_dt': local_end.isoformat(),
            'is_protected': event.is_protected,
            'domain': event.domain.name if event.domain else None,
        })

    if not conflicts:
        return {'has_conflict': False, 'conflicts': []}

    return {'has_conflict': True, 'conflicts': conflicts}


def classify_conflict_case(conflicts, new_is_protected):
    """
    Classify the conflict into one of three cases:

    Case A: Existing event is protected, new event is NOT protected.
            → Suggest rescheduling the new event.
    Case B: BOTH existing and new events are protected.
            → User must decide which to move.
    Case C: NEITHER is protected.
            → User can proceed or reschedule.

    Args:
        conflicts: List of conflict dicts from detect_all_conflicts()
        new_is_protected: Whether the proposed new/updated event is protected

    Returns:
        'A', 'B', or 'C'
    """
    any_existing_protected = any(c['is_protected'] for c in conflicts)

    if any_existing_protected and not new_is_protected:
        return 'A'
    elif any_existing_protected and new_is_protected:
        return 'B'
    else:
        return 'C'


def build_conflict_message(case, conflicts, suggested_gaps=None):
    """
    Build a user-facing conflict message with context and suggestions.

    Args:
        case: 'A', 'B', or 'C' from classify_conflict_case()
        conflicts: List of conflict dicts
        suggested_gaps: Optional list of gap dicts from find_gaps_for_day()

    Returns:
        str: Message for the user
    """
    # Format conflicting event titles with times
    from apps.calendar_engine.utils.formatting import friendly_time_range
    conflict_lines = []
    for c in conflicts[:3]:
        start = c.get('start_dt', '')
        end = c.get('end_dt', '')
        # Parse ISO times for display — times should already be in user tz
        # from detect_all_conflicts(), but apply localtime() as safety net.
        try:
            from datetime import datetime as _dt
            s = _dt.fromisoformat(start)
            e = _dt.fromisoformat(end)
            # Safety: if still in UTC, convert to active Django timezone
            if s.tzinfo is not None:
                s = dj_timezone.localtime(s)
            if e.tzinfo is not None:
                e = dj_timezone.localtime(e)
            time_range = friendly_time_range(s, e)
        except (ValueError, TypeError):
            time_range = f"{start} – {end}"

        protected_tag = " (protected)" if c.get('is_protected') else ""
        conflict_lines.append(f"  • {c['title']}{protected_tag}: {time_range}")

    conflict_list = "\n".join(conflict_lines)

    # Build suggestion text
    suggestion_text = ""
    if suggested_gaps:
        alt_lines = []
        for g in suggested_gaps[:3]:
            try:
                from datetime import datetime as _dt
                s = _dt.fromisoformat(g['start_dt']) if isinstance(g['start_dt'], str) else g['start_dt']
                e = _dt.fromisoformat(g['end_dt']) if isinstance(g['end_dt'], str) else g['end_dt']
                # Safety: convert to local timezone if aware
                if hasattr(s, 'tzinfo') and s.tzinfo is not None:
                    s = dj_timezone.localtime(s)
                if hasattr(e, 'tzinfo') and e.tzinfo is not None:
                    e = dj_timezone.localtime(e)
                alt_lines.append(
                    f"  • {friendly_time_range(s, e)} "
                    f"({g['duration_minutes']} min)"
                )
            except (ValueError, TypeError, KeyError):
                pass
        if alt_lines:
            suggestion_text = "\n\nAvailable time slots:\n" + "\n".join(alt_lines)

    if case == 'A':
        return (
            f"⚠️ This overlaps with a protected event:\n{conflict_list}\n\n"
            f"Protected events have priority. Would you like to reschedule "
            f"to a different time, or override the protection?"
            f"{suggestion_text}"
        )
    elif case == 'B':
        return (
            f"⚠️ Two protected events would conflict:\n{conflict_list}\n\n"
            f"Both events are protected. Which one should be moved?"
            f"{suggestion_text}"
        )
    else:  # Case C
        return (
            f"⚠️ This overlaps with an existing event:\n{conflict_list}\n\n"
            f"Would you like to proceed anyway (double-book), "
            f"or reschedule to an open slot?"
            f"{suggestion_text}"
        )
