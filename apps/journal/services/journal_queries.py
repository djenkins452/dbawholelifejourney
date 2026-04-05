# ==============================================================================
# File: apps/journal/services/journal_queries.py
# Description: Canonical journal query service. All consumers (execution truth,
#              SAE state builder, CoS context, views) MUST use these methods
#              instead of ad-hoc JournalEntry QuerySets.
# Created: 2026-04-05
# ==============================================================================
"""
Canonical journal queries.

Every method returns a QuerySet (not evaluated) so callers can chain
additional filters, slice, or aggregate as needed.

COMPLETION RULE:
  A journal entry exists = the user journaled that day.
  There is no "started but not finished" state for journal entries.
"""

from apps.journal.models import JournalEntry


class JournalQueries:
    """Canonical, deterministic journal queries. No instance state."""

    @classmethod
    def on_date(cls, user, target_date):
        """Entries on a specific date."""
        return JournalEntry.objects.filter(user=user, entry_date=target_date)

    @classmethod
    def has_entry_on(cls, user, target_date):
        """Boolean: did user journal on this date?"""
        return cls.on_date(user, target_date).exists()

    @classmethod
    def recent(cls, user, days=30):
        """Entries in the last N days, ordered by date desc."""
        from datetime import timedelta

        from django.utils import timezone
        cutoff = timezone.now() - timedelta(days=days)
        return JournalEntry.objects.filter(
            user=user, entry_date__gte=cutoff.date(),
        ).order_by('-entry_date')

    @classmethod
    def with_mood(cls, user, days=7):
        """Entries with mood data in the last N days, ordered by date asc."""
        from datetime import timedelta

        from django.utils import timezone
        cutoff = timezone.now() - timedelta(days=days)
        return JournalEntry.objects.filter(
            user=user,
            entry_date__gte=cutoff.date(),
            mood__isnull=False,
        ).exclude(mood='').order_by('entry_date')

    @classmethod
    def last_entry(cls, user):
        """Most recent journal entry (or None)."""
        return JournalEntry.objects.filter(user=user).order_by('-entry_date').first()
