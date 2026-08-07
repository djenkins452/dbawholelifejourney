# ==============================================================================
# File: apps/faith/services/faith_queries.py
# Description: Canonical faith domain query service. All consumers (execution
#              truth, SAE state builder, CoS context, views) MUST use these
#              methods instead of ad-hoc PrayerRequest/UserReadingPlan QuerySets.
# Created: 2026-04-05
# ==============================================================================
"""
Canonical faith queries.

Every method returns a QuerySet (not evaluated) so callers can chain
additional filters, slice, or aggregate as needed.

COMPLETION RULES:
  Bible reading completed = UserReadingProgress with is_completed=True
  Prayer completed = faith-module Task with completion_status='completed'
  These may also be satisfied by routine bridges (see execution_truth_engine).
"""

from django.db.models import Q

from apps.faith.models import PrayerRequest, UserReadingPlan, UserReadingProgress


class FaithQueries:
    """Canonical, deterministic faith queries. No instance state."""

    # ── Reading Plans ────────────────────────────────────────────

    @classmethod
    def active_reading_plans(cls, user):
        """Active Bible reading plans."""
        return UserReadingPlan.objects.filter(
            user=user, plan_status='active',
        ).exclude(status='deleted')

    @classmethod
    def has_active_plan(cls, user):
        """Boolean: does user have an active reading plan?"""
        return cls.active_reading_plans(user).exists()

    @classmethod
    def reading_completed_on(cls, user, target_date):
        """Reading progress satisfying a specific CALENDAR day.

        Occurrence-scoped: keyed on ``reading_date`` (the day the reading
        belongs to), NOT ``completed_at`` (when the click happened) — so a
        reading read Aug 6 but checked off Aug 7 counts for Aug 6. Legacy rows
        whose ``reading_date`` is null (pre-migration 0025) fall back to
        ``completed_at``'s date so history never silently drops.
        """
        active_plans = cls.active_reading_plans(user)
        return UserReadingProgress.objects.filter(
            user_plan__in=active_plans,
            is_completed=True,
        ).filter(
            Q(reading_date=target_date)
            | Q(reading_date__isnull=True, completed_at__date=target_date)
        )

    @classmethod
    def has_reading_on(cls, user, target_date):
        """Boolean: did user complete reading on this date?"""
        return cls.reading_completed_on(user, target_date).exists()

    @classmethod
    def last_reading(cls, user):
        """Most recent completed reading progress entry (or None)."""
        return UserReadingProgress.objects.filter(
            user_plan__user=user, is_completed=True,
        ).order_by('-completed_at').first()

    @classmethod
    def reading_completion_dates(cls, user, limit=60):
        """Distinct PLAN reading-occurrence dates in reverse order.

        Occurrence-scoped on ``reading_date`` (the day each reading belongs to)
        with a ``completed_at`` fallback for any un-backfilled legacy row, so
        streaks and days-since reflect the day read — not the day clicked.
        Plan-only. For canonical faith history (days-since / streak) use
        ``bible_completion_dates`` instead — it also folds in the
        routine→faith bridge so it cannot diverge from execution truth.
        """
        from django.db.models.functions import Coalesce, TruncDate

        rows = (
            UserReadingProgress.objects.filter(
                user_plan__user=user, is_completed=True,
            )
            .annotate(occ_date=Coalesce('reading_date', TruncDate('completed_at')))
            .filter(occ_date__isnull=False)
            .values_list('occ_date', flat=True)
            .distinct().order_by('-occ_date')
        )
        return list(rows[:limit])

    @classmethod
    def _routine_bible_completed_on(cls, user, target_date):
        """True if a routine→faith-bridge Bible item was completed on a date."""
        try:
            from apps.core.execution.execution_truth_engine import (
                FAITH_BIBLE_NAMES,
            )
            from apps.life.models import RoutineLog
            names = RoutineLog.objects.filter(
                user=user, scheduled_date=target_date,
                log_status__in=[
                    RoutineLog.STATUS_COMPLETED, RoutineLog.STATUS_COMPLETED_LATE],
            ).values_list('schedule__name', flat=True)
            return any(
                n and n.strip().lower() in FAITH_BIBLE_NAMES for n in names)
        except Exception:
            return False

    @classmethod
    def is_bible_complete_on(cls, user, target_date):
        """CANONICAL per-date Bible-reading completion across BOTH sources
        (reading plan + routine→faith bridge). Every consumer that needs
        "was Bible reading done on date X?" must use this so they cannot
        diverge from execution truth / the dashboard (trust contract 2026-06-16)."""
        return (
            cls.has_reading_on(user, target_date)
            or cls._routine_bible_completed_on(user, target_date)
        )

    @classmethod
    def bible_completion_dates(cls, user, limit=90):
        """THE single canonical set of dates Bible reading was completed.

        Unions BOTH canonical sources that execution_truth_engine counts:
          1. reading-plan progress (UserReadingProgress.is_completed)
          2. the routine→faith bridge — a completed routine item named like
             "Bible Reading" (FAITH_BIBLE_NAMES)

        This exists so faith history metrics (days-since, streak) derive from
        the SAME truth as the dashboard / adherence / routine engine and can
        never diverge (the "22 days since scripture while reading daily via a
        routine" trust bug, 2026-06-16). Returns dates newest-first. Never
        raises (routine source is best-effort).
        """
        from datetime import timedelta

        from django.utils import timezone

        dates = set(cls.reading_completion_dates(user, limit=limit))
        try:
            from apps.core.execution.execution_truth_engine import (
                FAITH_BIBLE_NAMES,
            )
            from apps.life.models import RoutineLog

            cutoff = timezone.now().date() - timedelta(days=limit)
            rows = RoutineLog.objects.filter(
                user=user,
                scheduled_date__gte=cutoff,
                log_status__in=[
                    RoutineLog.STATUS_COMPLETED,
                    RoutineLog.STATUS_COMPLETED_LATE,
                ],
            ).values_list('schedule__name', 'scheduled_date')
            for name, d in rows:
                if d and name and name.strip().lower() in FAITH_BIBLE_NAMES:
                    dates.add(d)
        except Exception:
            pass  # routine bridge best-effort; plan dates still returned
        return sorted((d for d in dates if d), reverse=True)[:limit]

    # ── Prayer Requests ──────────────────────────────────────────

    @classmethod
    def unanswered_prayers(cls, user):
        """Active, unanswered prayer requests."""
        return PrayerRequest.objects.filter(user=user, is_answered=False)

    @classmethod
    def answered_prayers(cls, user):
        """Answered prayer requests."""
        return PrayerRequest.objects.filter(user=user, is_answered=True)

    @classmethod
    def urgent_prayers(cls, user):
        """Unanswered prayer requests marked as urgent."""
        return cls.unanswered_prayers(user).filter(priority='urgent')

    # ── Entity Completeness Law (prayer records for the Model Interface) ──────────
    # describe / describe_one return CompleteEntity objects so the Chief of Staff can
    # answer "what have I been praying about" from a SINGLE deterministic retrieval,
    # grounded in FAITH truth only. Surface behind FaithDomainTruth.describe("prayer").
    _DESCRIBE_LIMIT = 20

    @classmethod
    def describe(cls, user, *, limit=None):
        """Recent prayer requests, each a CompleteEntity (newest-first)."""
        qs = (PrayerRequest.objects.filter(user=user)
              .order_by("-created_at")[: (limit or cls._DESCRIBE_LIMIT)])
        return [cls._prayer_to_entity(p) for p in qs]

    @classmethod
    def describe_one(cls, user, name):
        """The prayer matching `name`, or None. A chronological phrase ("my most recent /
        latest / last prayer") resolves to the single NEWEST prayer — the single-object
        retrieval that previously had no path (prod: "tell me about my most recent prayer"
        fell through to a keyword search and returned "no prayers in the last 7 days").
        Mirrors the nutrition 'last meal' precedent; reuses describe()[0], no new query."""
        name = (name or "").strip()
        if not name:
            return None
        low = name.lower()
        if "prayer" in low and any(k in low for k in ("most recent", "latest", "last",
                                                      "newest")):
            recent = cls.describe(user, limit=1)
            return recent[0] if recent else None
        p = (PrayerRequest.objects.filter(user=user, title__icontains=name)
             .order_by("-created_at").first())
        return cls._prayer_to_entity(p) if p else None

    @classmethod
    def _prayer_to_entity(cls, p):
        """One PrayerRequest → CompleteEntity."""
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="prayer",
            identity=(p.title or "").strip() or "Prayer request",
            definition={
                "title": p.title,
                "priority": p.priority,
                "is_personal": p.is_personal,
                "person_or_situation": (p.person_or_situation or None),
                "request": p.description_plain or "",
                "created": p.created_at.date() if p.created_at else None,
                "created_via": getattr(p, "created_via", None),
            },
            status=("answered" if p.is_answered else "unanswered"),
            plan={"remind_daily": getattr(p, "remind_daily", None)},
            standing={
                "answered_at": (p.answered_at.date() if p.answered_at else None),
                "answer_notes": (p.answer_notes_plain or None) if p.is_answered else None,
            },
            freshness=F.CURRENT,
        )

    # A completed plan older than this is no longer "current/recent study" and must not
    # surface as a current theme in the Analysis surface (prod: "themes lately" referenced
    # long-completed plans like Journey Through Matthew, started/completed months ago).
    _RECENT_STUDY_DAYS = 120

    @classmethod
    def describe_plans(cls, user, *, limit=10):
        """CURRENT / RECENT Bible reading plans as CompleteEntity objects — "what I'm studying
        (and recently studied)". This composer ALSO feeds the faith Analysis surface, so its
        window is the domain's definition of "recent study":

          * ABANDONED plans are excluded (not study truth).
          * ACTIVE and PAUSED plans are always in-progress → always included.
          * COMPLETED plans are included only if finished within the last _RECENT_STUDY_DAYS
            (by completed_at, falling back to started_at) — a plan completed months ago is not
            a CURRENT theme; it stays retrievable BY NAME via describe_plan_one and as history
            via history('reading'), just not as "what I'm studying/exploring lately."

        Ordered active/paused first, then most-recent. Non-fatal on any date edge case."""
        from datetime import timedelta

        from django.db.models import Q
        from django.utils import timezone

        cutoff = timezone.now() - timedelta(days=cls._RECENT_STUDY_DAYS)
        qs = (UserReadingPlan.objects.filter(user=user)
              .exclude(plan_status="abandoned")
              .filter(
                  Q(plan_status__in=("active", "paused"))
                  | Q(completed_at__gte=cutoff)
                  | (Q(plan_status="completed") & Q(completed_at__isnull=True)
                     & Q(started_at__gte=cutoff)))
              .select_related("template")
              # active/paused (in-progress) ahead of completed, then most-recent.
              .order_by("plan_status", "-started_at")[:limit])
        # plan_status order: 'active' < 'completed' < 'paused' alphabetically is not the
        # intent — sort in Python so in-progress leads deterministically.
        rows = sorted(qs, key=lambda p: (0 if p.plan_status in ("active", "paused") else 1,
                                         -(p.started_at.timestamp() if p.started_at else 0)))
        return [cls._plan_to_entity(pl) for pl in rows]

    @classmethod
    def describe_plan_one(cls, user, name):
        """The reading plan whose template title matches `name`, as a CompleteEntity, or
        None. Lets the Chief of Staff retrieve a NAMED Bible plan ("tell me about my
        Journey Through John plan") — previously describe_one resolved prayers only, so a
        named reading-plan lookup returned nothing (a Truth Layer gap)."""
        name = (name or "").strip()
        if not name:
            return None
        pl = (UserReadingPlan.objects.filter(user=user, template__title__icontains=name)
              .select_related("template").order_by("-started_at").first())
        return cls._plan_to_entity(pl) if pl else None

    @classmethod
    def _plan_to_entity(cls, pl):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        tmpl = pl.template
        ctx = {}
        try:
            ctx = pl.get_context_summary() or {}
        except Exception:
            ctx = {}
        return CompleteEntity(
            kind="reading_plan",
            identity=(getattr(tmpl, "title", None) or getattr(tmpl, "name", None)
                      or "Reading plan"),
            definition={"title": getattr(tmpl, "title", None) or getattr(tmpl, "name", None),
                        "category": getattr(tmpl, "category", None),
                        "duration_days": getattr(tmpl, "duration_days", None)},
            status=getattr(pl, "plan_status", None),
            plan={"current_day": getattr(pl, "current_day", None),
                  "reminder_time": (pl.reminder_time.strftime("%-I:%M %p")
                                    if getattr(pl, "reminder_time", None) else None),
                  "started": pl.started_at.date().isoformat() if pl.started_at else None},
            standing={"progress_percentage": getattr(pl, "progress_percentage", None),
                      "days_completed": getattr(pl, "days_completed", None),
                      "is_complete": getattr(pl, "is_complete", None),
                      "completed_at": (pl.completed_at.date().isoformat()
                                       if pl.completed_at else None)},
            extensions={"current_reading": ctx.get("content", ""),
                        "reflections": cls._plan_reflections(pl)},
            freshness=F.CURRENT,
        )

    @classmethod
    def _plan_reflections(cls, pl):
        """Per-day reading reflection notes (UserReadingProgress.notes) — was orphaned."""
        try:
            from apps.faith.models import UserReadingProgress
            rows = (UserReadingProgress.objects.filter(user_plan=pl)
                    .exclude(notes="").order_by("-completed_at")[:30])
            return [{"completed_at": (r.completed_at.date().isoformat()
                                      if r.completed_at else None),
                     "notes": r.notes} for r in rows if (r.notes or "").strip()]
        except Exception:
            return []

    # ── Faith Milestones / Saved Verses / Study Tools (entity surfaces) ───────────
    # Additive CompleteEntity composers for the user-owned faith records that had NO
    # get_entity surface (Faith cert Step 2, Finding E). Exposure only — each reads the
    # canonical model directly and composes a CompleteEntity; no new store, no reasoning.

    @classmethod
    def describe_milestones(cls, user, *, limit=25):
        """Faith-journey milestones (salvation, baptism, …) newest-first, each a
        CompleteEntity — 'tell me about my baptism', 'my faith milestones'."""
        from apps.faith.models import FaithMilestone
        qs = FaithMilestone.objects.filter(user=user).order_by("-date")[:limit]
        return [cls._milestone_to_entity(m) for m in qs]

    @classmethod
    def _milestone_to_entity(cls, m):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="faith_milestone",
            identity=(m.title or "").strip() or m.get_milestone_type_display(),
            definition={
                "type": m.get_milestone_type_display(),
                "date": m.date.isoformat() if m.date else None,
                "scripture_reference": (m.scripture_reference or None),
                "description": (m.description_plain or ""),
            },
            status="recorded",
            freshness=F.CURRENT,
        )

    @classmethod
    def describe_saved_verses(cls, user, *, limit=50):
        """The user's saved Scripture verses (memory verses first), each a CompleteEntity —
        'what are my memory verses', 'the verses I've saved'."""
        from apps.faith.models import SavedVerse
        qs = (SavedVerse.objects.filter(user=user)
              .order_by("-is_memory_verse", "book_order", "chapter", "verse_start")[:limit])
        return [cls._verse_to_entity(v) for v in qs]

    @classmethod
    def _verse_to_entity(cls, v):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="saved_verse",
            identity=v.reference,
            definition={
                "reference": v.reference,
                "text": v.text,
                "translation": v.translation,
                "themes": (v.themes or []),
                "notes": (v.notes or ""),
            },
            status=("memory_verse" if v.is_memory_verse else "saved"),
            freshness=F.CURRENT,
        )

    @classmethod
    def describe_study_notes(cls, user, *, limit=30):
        """Bible study notes newest-first, each a CompleteEntity — 'my notes on Romans 8'."""
        from apps.faith.models import BibleStudyNote
        qs = BibleStudyNote.objects.filter(user=user).order_by("-created_at")[:limit]
        return [cls._note_to_entity(n) for n in qs]

    @classmethod
    def _note_to_entity(cls, n):
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        return CompleteEntity(
            kind="bible_study_note",
            identity=(n.title or "").strip() or f"Note on {n.reference}",
            definition={
                "reference": n.reference,
                "translation": n.translation,
                "note": (n.content_plain or ""),
                "tags": (n.tags or []),
                "created": n.created_at.date().isoformat() if n.created_at else None,
            },
            status="recorded",
            freshness=F.CURRENT,
        )

    @classmethod
    def describe_highlights(cls, user, *, limit=50):
        """Highlighted passages, each a CompleteEntity — 'passages I highlighted'."""
        from apps.faith.models import BibleHighlight
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        qs = (BibleHighlight.objects.filter(user=user)
              .order_by("book_order", "chapter", "verse_start")[:limit])
        return [CompleteEntity(
            kind="bible_highlight",
            identity=h.reference,
            definition={"reference": h.reference, "text": h.text,
                        "color": h.color, "translation": h.translation},
            status="highlighted",
            freshness=F.CURRENT,
        ) for h in qs]

    @classmethod
    def describe_bookmarks(cls, user, *, limit=50):
        """Bookmarked Bible locations, each a CompleteEntity — 'my bookmarks'."""
        from apps.faith.models import BibleBookmark
        from apps.core.truth import freshness as F
        from apps.core.truth.entity import CompleteEntity
        qs = BibleBookmark.objects.filter(user=user).order_by("-created_at")[:limit]
        return [CompleteEntity(
            kind="bible_bookmark",
            identity=(b.title or "").strip() or b.reference,
            definition={"reference": b.reference, "translation": b.translation,
                        "notes": (b.notes or "")},
            status="bookmarked",
            freshness=F.CURRENT,
        ) for b in qs]

    # ── Point-in-Time History (per-day Bible reading) ─────────────────────────────
    # Sourced from the CANONICAL unified completion set (plan + routine bridge) — the
    # same source reading_streak / days_since_reading use — so it can never diverge
    # from the dashboard. Surface behind FaithDomainTruth.history("reading").
    HISTORY_METRICS = ("reading",)

    @classmethod
    def reading_series(cls, user, period="last_7_days", *,
                       today=None, start=None, end=None):
        """Per-day Bible-reading completion (1 = read) over a resolved period."""
        from apps.core.truth.history import series_from_rows
        from apps.core.truth.periods import resolve_period
        if today is None:
            from apps.core.utils import get_user_today
            today = get_user_today(user)
        p = resolve_period(period, today, start=start, end=end)
        span_days = (p.end - p.start).days + 1
        done = set(cls.bible_completion_dates(user, limit=max(span_days, 90)))
        rows = [{"date": d, "value": 1} for d in done if p.start <= d <= p.end]
        return series_from_rows("faith", "reading", p, rows, unit="days")

    # ── Faith Tasks ──────────────────────────────────────────────

    @classmethod
    def faith_task_completed_on(cls, user, target_date):
        """Faith-module tasks completed on a specific date."""
        from apps.life.models import Task
        return Task.objects.filter(
            user=user,
            module='faith',
            completion_status='completed',
            completed_at__date=target_date,
        )

    @classmethod
    def has_faith_task_completed_on(cls, user, target_date):
        """Boolean: did user complete a faith task on this date?"""
        return cls.faith_task_completed_on(user, target_date).exists()
