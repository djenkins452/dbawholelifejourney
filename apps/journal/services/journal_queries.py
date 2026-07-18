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

    # ── Point-in-Time History (per-day mood) ──────────────────────────────────────
    # Mood is a categorical CharField; scores mirror the SAE's mood mapping
    # (state_builder mood_avg_7d) so the windowed average matches the current-truth
    # narration. Surface behind JournalDomainTruth.history("mood") — answers "how has
    # my mood changed recently" from JOURNAL truth only. One grouped query.
    _MOOD_SCORES = {"great": 5, "good": 4, "okay": 3, "low": 2, "difficult": 1}
    HISTORY_METRICS = ("mood",)

    @classmethod
    def mood_series(cls, user, period="last_7_days", *,
                    today=None, start=None, end=None):
        """Per-day AVERAGE mood (1-5) over a resolved period as a HistorySeries."""
        from django.db.models import Avg, Case, IntegerField, Value, When
        from apps.core.truth.history import series_from_rows
        from apps.core.truth.periods import resolve_period
        if today is None:
            from apps.core.utils import get_user_today
            today = get_user_today(user)
        p = resolve_period(period, today, start=start, end=end)
        score = Case(
            *[When(mood=k, then=Value(v)) for k, v in cls._MOOD_SCORES.items()],
            output_field=IntegerField(),
        )
        rows = (JournalEntry.objects
                .filter(user=user, mood__isnull=False,
                        entry_date__range=(p.start, p.end))
                .exclude(mood="")
                .values("entry_date").annotate(v=Avg(score))
                .order_by("entry_date"))
        return series_from_rows(
            "journal", "mood", p,
            [{"date": r["entry_date"], "value": round(float(r["v"]), 1)}
             for r in rows],
            unit="score")

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
    def describe(cls, user, *, since_days=30, limit=None,
                 period=None, start=None, end=None):
        """Journal entries, each a `CompleteEntity`. Deterministic scoping: a `period`
        (or start/end) returns the FULL set for that window ('what have I written this
        week/month') from JOURNAL truth only; unscoped stays a recent bounded browse."""
        if period or start or end:
            from apps.core.truth.periods import resolve_period
            from apps.core.utils import get_user_today
            p = resolve_period(period or "custom", get_user_today(user),
                               start=start, end=end)
            qs = (JournalEntry.objects.filter(
                    user=user, entry_date__range=(p.start, p.end))
                  .prefetch_related("emotions", "tags", "categories")
                  .order_by("-entry_date"))
            return [cls._to_entity(e) for e in qs]
        qs = (cls.recent(user, days=since_days)
              .prefetch_related("emotions", "tags", "categories")
              [: (limit or cls._DESCRIBE_LIMIT)])
        return [cls._to_entity(e) for e in qs]

    @classmethod
    def theme_counts(cls, user, period="this_month", *, today=None,
                     start=None, end=None):
        """Deterministic tag + emotion frequency over a window — answers 'what topics
        have I written about' and 'what concerns have I repeated' (repeated = count>1),
        grounded in JOURNAL truth only. Returns {'tags': {name: n}, 'emotions': {name: n}}."""
        from apps.core.truth.periods import resolve_period
        if today is None:
            from apps.core.utils import get_user_today
            today = get_user_today(user)
        p = resolve_period(period, today, start=start, end=end)
        entries = (JournalEntry.objects
                   .filter(user=user, entry_date__range=(p.start, p.end))
                   .prefetch_related("tags", "emotions"))
        tags, emotions = {}, {}
        for e in entries:
            for t in e.tags.all():
                tags[t.name] = tags.get(t.name, 0) + 1
            for em in e.emotions.all():
                emotions[em.name] = emotions.get(em.name, 0) + 1
        srt = lambda d: dict(sorted(d.items(), key=lambda kv: -kv[1]))
        return {"tags": srt(tags), "emotions": srt(emotions),
                "repeated": [k for k, v in {**tags, **emotions}.items() if v > 1]}

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
        # Prompt that inspired the entry (FK → JournalPrompt, nullable — guard on _id).
        prompt = None
        if getattr(e, "prompt_id", None):
            prompt = {"text": e.prompt.text,
                      "scripture_reference": (e.prompt.scripture_reference or None),
                      "is_faith_specific": e.prompt.is_faith_specific}
        # NLP behavioral signals extracted from this entry (the app's AI-derived journal
        # truth; reverse FK, may be empty) + cross-module links out of the entry.
        signals = [{"type": s.signal_type, "domain": s.domain,
                    "confidence": round(s.confidence, 2), "text": s.extracted_text}
                   for s in e.signals.all()]
        links = [{"target": lk.target_type, "target_id": lk.target_id,
                  "link_type": lk.link_type} for lk in e.outgoing_links.all()]
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
                "prompt": prompt,               # inspiration source
                "created_via": e.created_via,   # manual vs routine vs ai_camera
            },
            status="written",
            freshness=F.CURRENT,
            extensions={"content": e.body_plain or "",
                        **({"signals": signals} if signals else {}),
                        **({"links": links} if links else {})},
        )
