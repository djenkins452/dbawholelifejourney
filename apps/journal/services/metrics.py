"""
Journal Metrics Service — Canonical journal domain metrics.

This is the single canonical source for journal metrics consumed by:
- PersonalAssistant._get_journal_state()
- Executive Briefing journal context
- Proactive check-in generators
- Any future journal-metric consumer

Architecture: Reads from SAE (Layer 3) as primary source, with direct
queries for computed fields that SAE doesn't track (streaks, totals,
recent entries).
"""

import logging
from datetime import timedelta

from django.db.models import Count

logger = logging.getLogger(__name__)


def get_journal_metrics(user) -> dict:
    """Return canonical journal metrics for a user.

    Combines SAE state (entry_frequency, mood_distribution, days_since_entry)
    with direct queries for fields SAE doesn't compute (journal_total,
    journal_streak, recent_entries).

    Returns dict with keys matching PA's _get_journal_state() contract:
        journal_total, journal_week, journal_month, journal_streak,
        dominant_mood, recent_entries, last_journal_date.
    """
    from apps.core.utils import get_user_today
    from apps.journal.models import JournalEntry

    today = get_user_today(user)
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # ── SAE state (primary source for aggregate metrics) ──
    sae_journal = _get_sae_journal(user)

    # ── Direct queries for fields SAE doesn't track ──
    entries = JournalEntry.objects.filter(user=user)

    # Totals
    journal_total = entries.count()
    journal_week = entries.filter(entry_date__gte=week_ago).count()
    journal_month = entries.filter(entry_date__gte=month_ago).count()

    # Streak (consecutive days, excluding today)
    streak = calculate_journal_streak(user, today)

    # Dominant mood (from SAE if available, else direct query)
    dominant_mood = ''
    mood_dist = sae_journal.get('mood_distribution', {})
    if mood_dist:
        dominant_mood = max(mood_dist, key=mood_dist.get, default='')
    else:
        moods = (
            entries.filter(entry_date__gte=week_ago)
            .exclude(mood='')
            .values('mood')
            .annotate(count=Count('mood'))
            .order_by('-count')
        )
        if moods:
            dominant_mood = moods[0]['mood']

    # Recent entries for AI context
    recent = list(entries.order_by('-entry_date')[:5].values(
        'title', 'entry_date', 'mood', 'body',
    ))

    last_date = entries.order_by('-entry_date').values_list(
        'entry_date', flat=True,
    ).first()

    return {
        'journal_total': journal_total,
        'journal_week': journal_week,
        'journal_month': journal_month,
        'journal_streak': streak,
        'dominant_mood': dominant_mood,
        'recent_entries': recent,
        'last_journal_date': last_date,
    }


def calculate_journal_streak(user, today) -> int:
    """Calculate consecutive days of journaling (excludes today).

    This is the SINGLE canonical streak calculation. All consumers should
    call this instead of reimplementing streak logic.
    """
    from apps.journal.models import JournalEntry

    entries = (
        JournalEntry.objects.filter(user=user)
        .order_by('-entry_date')
        .values_list('entry_date', flat=True)
        .distinct()[:60]
    )

    if not entries:
        return 0

    streak = 0
    expected = today - timedelta(days=1)

    for entry_date in entries:
        if entry_date == expected:
            streak += 1
            expected -= timedelta(days=1)
        elif entry_date < expected:
            break

    return streak


def _get_sae_journal(user) -> dict:
    """Read journal state from SAE. Returns empty dict if unavailable."""
    try:
        from apps.core.ai_state.models import UserState
        sae = UserState.objects.filter(user=user).first()
        if sae and sae.state_data:
            return sae.state_data.get('journal', {})
    except Exception:
        logger.warning("JOURNAL_SERVICE SAE read failed for user=%s", user.id, exc_info=True)
    return {}
