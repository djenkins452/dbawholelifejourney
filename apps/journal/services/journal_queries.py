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

    # ── Entity Completeness Law (record-level truth for the Model Interface) ──────
    # `describe` / `describe_one` return `CompleteEntity` objects so the Chief of Staff
    # can answer "what did I write about yesterday?", "what was my MOOD yesterday?",
    # "what emotions/tags?" from a SINGLE deterministic retrieval — mood/emotions are
    # FIELDS on JournalEntry (journal content, not a separate domain). This is the
    # surface behind JournalDomainTruth.describe(). Exposing it stops journal/mood
    # questions from falling through to a cross-domain search that surfaces unrelated
    # health metrics (the "journal → walking speed / audio exposure" defect, 2026-07-17).
    # Mirrors WorkoutQueries.describe; reuses the canonical queries above, no new store.
    _DESCRIBE_LIMIT = 10

    @classmethod
    def describe(cls, user, *, since_days=30, limit=None):
        """Recent journal entries, each a `CompleteEntity` (bounded, newest-first)."""
        qs = (cls.recent(user, days=since_days)
              .prefetch_related("emotions", "tags", "categories")
              [: (limit or cls._DESCRIBE_LIMIT)])
        return [cls._to_entity(e) for e in qs]

    @classmethod
    def describe_one(cls, user, name):
        """The most recent journal entry matching `name` (a YYYY-MM-DD / ISO date, or a
        title substring), as a `CompleteEntity`, or None."""
        name = (name or "").strip()
        if not name:
            return None
        base = JournalEntry.objects.filter(user=user).order_by('-entry_date')
        entry = None
        try:
            from apps.health.services.health_dates import parse_health_date
            entry = base.filter(entry_date=parse_health_date(name)).first()
        except ValueError:
            entry = None
        if entry is None:
            entry = base.filter(title__icontains=name).first()
        return cls._to_entity(entry) if entry else None

    @classmethod
    def _to_entity(cls, e):
        """One JournalEntry → a CompleteEntity. The narrative body lives in
        `extensions.content` as the plain-text shadow (never raw sanitized HTML —
        the RTE/Visual-Truth contract)."""
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity

        title = (e.title or "").strip() or "Journal entry"
        # emotions / tags / categories are ManyToMany → render their names.
        _names = lambda mgr: sorted(mgr.values_list("name", flat=True))
        return CompleteEntity(
            kind="journal_entry",
            identity=f"{title} — {e.entry_date}",
            definition={
                "date": e.entry_date,
                "title": title,
                "mood": (e.mood or None),
                "emotions": _names(e.emotions),
                "categories": _names(e.categories),
                "tags": _names(e.tags),
                "word_count": e.word_count,
            },
            status="written",
            freshness=F.CURRENT,
            extensions={"content": e.body_plain or ""},
        )
