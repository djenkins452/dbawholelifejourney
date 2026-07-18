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
        """Reading progress entries completed on a specific date."""
        active_plans = cls.active_reading_plans(user)
        return UserReadingProgress.objects.filter(
            user_plan__in=active_plans,
            is_completed=True,
            completed_at__date=target_date,
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
        """Distinct PLAN completion dates in reverse order.

        Plan-only. For canonical faith history (days-since / streak) use
        ``bible_completion_dates`` instead — it also folds in the
        routine→faith bridge so it cannot diverge from execution truth.
        """
        return list(
            UserReadingProgress.objects.filter(
                user_plan__user=user, is_completed=True,
                completed_at__isnull=False,
            ).values_list(
                'completed_at__date', flat=True,
            ).distinct().order_by('-completed_at__date')[:limit]
        )

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
        """Most recent prayer whose title matches `name`, or None."""
        name = (name or "").strip()
        if not name:
            return None
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

    @classmethod
    def describe_plans(cls, user, *, limit=10):
        """Active/recent Bible reading plans as CompleteEntity objects — exposes the
        UserReadingPlan/Progress study truth that had no entity surface."""
        qs = (UserReadingPlan.objects.filter(user=user)
              .select_related("template").order_by("-started_at")[:limit])
        return [cls._plan_to_entity(pl) for pl in qs]

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
                  "started": pl.started_at.date().isoformat() if pl.started_at else None},
            standing={"progress_percentage": getattr(pl, "progress_percentage", None),
                      "days_completed": getattr(pl, "days_completed", None),
                      "is_complete": getattr(pl, "is_complete", None),
                      "completed_at": (pl.completed_at.date().isoformat()
                                       if pl.completed_at else None)},
            extensions={"current_reading": ctx.get("content", "")},
            freshness=F.CURRENT,
        )

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
