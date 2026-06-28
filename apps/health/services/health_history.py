"""
HealthHistory — Health's Point-in-Time History provider (Layer 1).

First consumer of the platform History capability (apps.core.truth.history). Each
method resolves the period once and runs ONE grouped query over the canonical model,
then hands the rows to the platform `series_from_rows`. No per-day looping, no
re-implementation of period math or aggregates — Health owns only its queries.

Current Truth (`CurrentHealth`) answers "now / today / last night"; HealthHistory
answers "on <date> / last week / this month / last quarter".
"""
from django.db.models import Sum, Avg

from apps.core.truth.history import series_from_rows
from apps.core.truth.periods import resolve_period


def _today(user):
    from apps.core.utils import get_user_today
    return get_user_today(user)


class HealthHistory:

    @classmethod
    def steps(cls, user, period="last_7_days", *, today=None, start=None, end=None):
        from apps.health.models import StepsEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        rows = (StepsEntry.objects.filter(user=user,
                                          logged_date__range=(p.start, p.end))
                .values("logged_date").annotate(v=Sum("count")).order_by("logged_date"))
        return series_from_rows(
            "health", "steps", p,
            [{"date": r["logged_date"], "value": int(r["v"])} for r in rows],
            unit="steps")

    @classmethod
    def sleep(cls, user, period="last_7_days", *, today=None, start=None, end=None):
        from apps.health.models import SleepEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        rows = (SleepEntry.objects.filter(user=user,
                                          sleep_date__range=(p.start, p.end))
                .values("sleep_date").annotate(v=Avg("asleep_duration_minutes"))
                .order_by("sleep_date"))
        return series_from_rows(
            "health", "sleep", p,
            [{"date": r["sleep_date"], "value": round((r["v"] or 0) / 60.0, 1)}
             for r in rows],
            unit="hours")

    @classmethod
    def weight(cls, user, period="last_month", *, today=None, start=None, end=None):
        from apps.health.models import WeightEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        rows = (WeightEntry.objects.filter(user=user,
                                           recorded_at__date__range=(p.start, p.end))
                .values("recorded_at__date").annotate(v=Avg("value"))
                .order_by("recorded_at__date"))
        return series_from_rows(
            "health", "weight", p,
            [{"date": r["recorded_at__date"], "value": round(float(r["v"]), 1)}
             for r in rows],
            unit="lb")
