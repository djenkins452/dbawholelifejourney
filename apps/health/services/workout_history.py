"""
WorkoutHistory — Fitness's Point-in-Time History provider (Layer 1).

Second consumer of the platform History capability, demonstrating reuse with near-zero
new code: it runs the EXISTING canonical contract `WorkoutQueries.completed_in_range`
over a platform-resolved `Period` and hands the rows to the same `series_from_rows`.
One grouped query; the platform owns period math + aggregates.

`.sessions(...).total()` = total workouts in the period; `.count()` = days trained.
"""
from django.db.models import Count

from apps.core.truth.history import series_from_rows
from apps.core.truth.periods import resolve_period


class WorkoutHistory:

    @classmethod
    def sessions(cls, user, period="last_week", *, today=None, start=None, end=None):
        from apps.core.utils import get_user_today
        from apps.health.services.workout_queries import WorkoutQueries
        p = resolve_period(period, today or get_user_today(user), start=start, end=end)
        # distinct=True is REQUIRED: completed_in_range's _COMPLETED_Q LEFT-JOINs
        # workout_exercises, so a plain Count("id") counts (session × exercise) rows —
        # a 4-session week of 7-exercise workouts would report 28 "sessions". The base
        # .distinct() does not survive .values().annotate(), so we must count distinct ids.
        rows = (WorkoutQueries.completed_in_range(user, p.start, p.end)
                .values("date").annotate(v=Count("id", distinct=True)).order_by("date"))
        return series_from_rows(
            "fitness", "workouts", p,
            [{"date": r["date"], "value": int(r["v"])} for r in rows],
            unit="sessions")
