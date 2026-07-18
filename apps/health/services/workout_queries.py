# ==============================================================================
# File: apps/health/services/workout_queries.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Canonical workout query service. All consumers (execution truth,
#              SAE state builder, CoS context, views, analytics) MUST use these
#              methods instead of ad-hoc WorkoutSession QuerySets. This
#              eliminates the .exists() vs completed_at mismatch that caused
#              CoS to report in-progress workouts as "completed".
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-04-04
# ==============================================================================
"""
Canonical workout queries.

Every method returns a QuerySet (not evaluated) so callers can chain
additional filters, slice, or aggregate as needed. The SoftDeleteManager
on WorkoutSession.objects already filters status='active', but we add an
explicit .exclude(status='deleted') for safety since some call sites
previously relied on it.

COMPLETION RULE:
  A workout is "completed" when completed_at is not null.
  A started-but-not-finished session is NOT completed.
  This matches the Health UI (views.py:467) and SAE fitness builder
  (state_builder.py build_fitness_state 7d/30d counts).

Usage:
    from apps.health.services.workout_queries import WorkoutQueries

    qs  = WorkoutQueries.completed_on(user, today)        # completed sessions
    ok  = WorkoutQueries.is_completed_on(user, today)     # bool
    qs  = WorkoutQueries.completed_in_range(user, s, e)   # for analytics
    qs  = WorkoutQueries.on_date(user, today)             # all (incl in-progress)
"""

from datetime import date

from django.db.models import Q

from apps.health.models import WorkoutSession


# A workout is "completed" when ANY of these are true:
#   1. completed_at is set (explicitly finished via UI or import)
#   2. It has at least one exercise logged (structured workout with content)
#   3. It has duration_minutes set (activity workout logged with duration)
#
# A session that was merely started (started_at set, no exercises, no
# duration, no completed_at) is NOT completed — it's in-progress.
_COMPLETED_Q = (
    Q(completed_at__isnull=False)
    | Q(workout_exercises__isnull=False)
    | Q(duration_minutes__isnull=False)
)


class WorkoutQueries:
    """Canonical, deterministic workout queries. No instance state."""

    @classmethod
    def completed_on(cls, user, target_date):
        """
        Completed workout sessions on a specific date.

        A workout is "completed" when:
          - completed_at is set (explicitly finished), OR
          - it has exercises logged (structured workout with content), OR
          - it has duration_minutes (activity/import with duration)

        A session that was merely started with no content is NOT completed.
        """
        return WorkoutSession.objects.filter(
            _COMPLETED_Q,
            user=user,
            date=target_date,
        ).exclude(status='deleted').distinct()

    @classmethod
    def is_completed_on(cls, user, target_date):
        """Boolean: did the user complete any workout on this date?"""
        return cls.completed_on(user, target_date).exists()

    @classmethod
    def on_date(cls, user, target_date):
        """
        All non-deleted sessions on a date (regardless of completion).

        Use this when you need to know "has the user started anything?"
        e.g., suppressing workout check-in prompts or protein-day detection
        where a started session is enough.
        """
        return WorkoutSession.objects.filter(
            user=user,
            date=target_date,
        ).exclude(status='deleted')

    @classmethod
    def completed_in_range(cls, user, start_date, end_date):
        """
        Completed sessions in a date range (inclusive).

        Use for frequency/trend counting — only completed sessions should
        count toward goals like "3x/week".
        """
        return WorkoutSession.objects.filter(
            _COMPLETED_Q,
            user=user,
            date__gte=start_date,
            date__lte=end_date,
        ).exclude(status='deleted').distinct()

    @classmethod
    def in_range(cls, user, start_date, end_date):
        """
        All non-deleted sessions in a date range (regardless of completion).

        Use for listing/display where in-progress sessions should appear.
        """
        return WorkoutSession.objects.filter(
            user=user,
            date__gte=start_date,
            date__lte=end_date,
        ).exclude(status='deleted')

    # ── Entity Completeness (record-level truth) ─────────────────────────────
    # Workouts participate in the platform Entity surface (DomainTruth.describe /
    # get_entity) exactly like Medication: a completed workout describes itself
    # across the CompleteEntity dimensions from a SINGLE deterministic retrieval,
    # so the CoS answers "what exercises did I do", "did I do calf raises", "what
    # weight", "my sets", "my volume", "summarize my workout" from truth WLJ owns
    # — with no workout-specific tool. Per-set volume/movement reuse the canonical
    # ExerciseSet.volume / .movement_work properties (no re-derived calculation).
    _DESCRIBE_DAYS = 30       # recent window that covers "yesterday" / "this week" / "last workout"
    _DESCRIBE_LIMIT = 20      # cap the payload — most-recent-first (bounded truth package)

    @classmethod
    def _describe_qs(cls, user, start_date, end_date):
        """Completed sessions in range, newest-first, with the exercise + set graph
        prefetched so `_to_entity` runs with no per-row query (N+1-free)."""
        return (
            cls.completed_in_range(user, start_date, end_date)
            .select_related("from_template")
            .prefetch_related("workout_exercises__exercise", "workout_exercises__sets")
            .order_by("-date", "-completed_at", "-created_at")
        )

    @classmethod
    def describe(cls, user, *, since_days=None, limit=None):
        """Recent completed workouts, each a `CompleteEntity` (bounded, newest-first).

        Workouts are historical, so "describe all entities of this type" is bounded to
        a recent window (`_DESCRIBE_DAYS`) and a count cap (`_DESCRIBE_LIMIT`) to keep
        the truth package small. The model reasons over the returned entities to resolve
        "yesterday" / "my last workout" / "did I do X" — WLJ owns the facts, the model
        picks among them.
        """
        from datetime import timedelta
        from apps.core.utils import get_user_today
        today = get_user_today(user)
        days = cls._DESCRIBE_DAYS if since_days is None else since_days
        cap = cls._DESCRIBE_LIMIT if limit is None else limit
        sessions = list(cls._describe_qs(user, today - timedelta(days=days), today)[:cap])
        return [cls._to_entity(s) for s in sessions]

    @classmethod
    def describe_one(cls, user, name):
        """The most recent completed workout whose name or activity type matches `name`
        (case-insensitive), as a `CompleteEntity`, or None."""
        from datetime import timedelta
        from apps.core.utils import get_user_today
        n = (name or "").strip()
        if not n:
            return None
        today = get_user_today(user)
        session = (
            cls._describe_qs(user, today - timedelta(days=365), today)
            .filter(Q(name__icontains=n) | Q(workout_type__icontains=n))
            .first()
        )
        return cls._to_entity(session) if session else None

    @classmethod
    def _to_entity(cls, session):
        """One completed WorkoutSession → a CompleteEntity across the contract dimensions.
        Reads only prefetched relations (no `.filter()` on the prefetch — that bypasses
        the cache) and reuses the canonical per-set volume/movement calculations."""
        from apps.core.truth.entity import CompleteEntity
        exercises, detail = [], []
        strength_load = 0.0
        movement_reps = 0
        resistance_sets = 0
        for we in session.workout_exercises.all():             # prefetched
            ex = we.exercise
            is_resistance = (ex.category == "resistance")
            exercises.append({"name": ex.name, "category": ex.category})
            set_rows, ex_volume = [], 0.0
            for s in we.sets.all():                             # prefetched (ordered by set_number)
                s.workout_exercise = we                         # prime cache → reuse s.volume, no query
                vol, mw = s.volume, s.movement_work
                set_rows.append({
                    "set": s.set_number,
                    "weight_lb": float(s.weight) if s.weight is not None else None,
                    "reps": s.reps,
                    "volume_lb": round(vol, 1) if vol is not None else None,
                    "is_warmup": s.is_warmup,
                    "is_pr": s.is_pr,
                })
                if is_resistance and not s.is_warmup:
                    resistance_sets += 1
                    if vol is not None:
                        ex_volume += vol
                        strength_load += vol
                    if mw is not None:
                        movement_reps += mw
            detail.append({
                "name": ex.name, "category": ex.category, "order": we.order,
                "total_volume_lb": round(ex_volume, 1), "sets": set_rows,
            })

        title = (session.name or session.workout_type or "Workout").strip()
        template = session.from_template if session.from_template_id else None
        return CompleteEntity(
            kind="workout",
            identity=f"{title} — {session.date.isoformat()}",
            definition={
                "date": session.date.isoformat(),
                "started_at": (session.started_at.isoformat()
                               if getattr(session, "started_at", None) else None),
                "source": getattr(session, "source", None) or None,
                "mode": session.session_mode,                   # structured | activity
                "workout_type": session.workout_type or "",
                "notes": session.notes or "",                  # stored note, was dropped
                "exercise_count": len(exercises),
                "exercises": exercises,                         # names → "did I do calf raises?"
            },
            status="completed",
            plan={"from_template": getattr(template, "name", None)},
            standing={},                                        # a logged workout is settled history
            performance={
                "total_sets": resistance_sets,
                "strength_load_lb": round(strength_load, 1),
                "movement_work_reps": movement_reps,
                "duration_minutes": session.duration_minutes,
                "calories_burned": session.calories_burned,
                "distance_miles": (float(session.distance_miles)
                                   if session.distance_miles is not None else None),
                "avg_heart_rate": session.avg_heart_rate,
                "intensity": session.intensity or "",
            },
            extensions={"exercise_detail": detail} if detail else {},
        )
