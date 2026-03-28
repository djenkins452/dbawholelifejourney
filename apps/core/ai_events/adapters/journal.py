# ==============================================================================
# File: apps/core/ai_events/adapters/journal.py
# Project: Whole Life Journey
# Description: Journal event adapter
# Created: 2026-03-28
# ==============================================================================
"""Journal Event Adapter. Reads JournalEntry directly."""

import logging
from datetime import date
from apps.core.ai_events.event_record import EventRecord

logger = logging.getLogger(__name__)
MAX_LOOKBACK_DAYS = 30


def get_events(user, start_date, end_date):
    _enforce_bounds(start_date, end_date)
    from apps.journal.models import JournalEntry
    entries = JournalEntry.objects.filter(
        user=user, entry_date__gte=start_date, entry_date__lte=end_date,
    ).order_by('entry_date')
    return [_to_event(e) for e in entries]


def get_latest(user, count=1):
    from apps.journal.models import JournalEntry
    return [_to_event(e) for e in JournalEntry.objects.filter(user=user).order_by('-entry_date')[:count]]


def get_day_events(user, target_date):
    return get_events(user, target_date, target_date)


def _to_event(entry):
    from django.utils import timezone as tz
    mood = entry.mood or ''
    title = entry.title or 'Journal Entry'
    label = title
    if mood:
        label += f" (mood: {mood})"

    timestamp = tz.make_aware(
        tz.datetime.combine(entry.entry_date, tz.datetime.min.time()),
        tz.get_default_timezone(),
    )
    if hasattr(entry, 'created_at') and entry.created_at:
        timestamp = entry.created_at

    return EventRecord(
        domain='journal', event_type='journal_entry', timestamp=timestamp,
        label=label, status='logged',
        detail={
            'title': entry.title or '', 'mood': mood,
            'word_count': entry.word_count or 0,
            'date': str(entry.entry_date),
        },
        source_model='JournalEntry', source_id=entry.pk,
    )


def _enforce_bounds(s, e):
    if e < s: raise ValueError("end_date must be >= start_date")
    if (e - s).days > MAX_LOOKBACK_DAYS: raise ValueError(f"Exceeds {MAX_LOOKBACK_DAYS} days")
