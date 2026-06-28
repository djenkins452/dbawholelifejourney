"""
Daily Health Queries — canonical PER-DAY health truth (Layer 1, Batch 1).

"Retrieve, never derive." Each method returns the value FOR A SPECIFIC DAY read
straight from the canonical model, or {status: 'no_data'} when that day has no
entry. It NEVER substitutes a 7-day average for a requested day (the Layer-1
defect class this closes: SAE only had averages, so "steps yesterday" / "sleep
last night" could not be answered as a real value — Architecture Laws 0/1/4).

Single source of truth (F4): UserOwnedModel `.objects` already filters
status='active'. Returns a small fact dict the foundational-fact layer renders.
"""
from datetime import timedelta

from django.db.models import Avg, Sum


def _no_data(metric, target_date):
    return {"status": "no_data", "metric": metric,
            "for_date": target_date.isoformat() if target_date else None}


class DailyHealthQueries:
    """Deterministic per-day health facts. All dates are user-local `date` objects."""

    # ----- Steps (StepsEntry.count by logged_date) --------------------------
    @classmethod
    def steps_on(cls, user, target_date):
        from apps.health.models import StepsEntry
        qs = StepsEntry.objects.filter(user=user, logged_date=target_date)
        total = qs.aggregate(s=Sum("count"))["s"]
        if total is None:
            return _no_data("steps", target_date)
        last = qs.order_by("-recorded_at").first()
        return {"status": "ok", "value": int(total), "unit": "steps",
                "for_date": target_date.isoformat(),
                "recorded_at": last.recorded_at.isoformat() if last else None}

    # ----- Sleep (SleepEntry, by sleep_date; "last night" = most recent) ----
    @classmethod
    def latest_sleep(cls, user):
        from apps.health.models import SleepEntry
        e = (SleepEntry.objects.filter(user=user)
             .order_by("-sleep_date", "-id").first())
        if not e:
            return _no_data("sleep", None)
        mins = e.asleep_duration_minutes or e.total_duration_minutes or 0
        return {"status": "ok", "value": round(mins / 60.0, 1), "unit": "hours",
                "for_date": e.sleep_date.isoformat()}

    @classmethod
    def sleep_on(cls, user, night_date):
        from apps.health.models import SleepEntry
        e = (SleepEntry.objects.filter(user=user, sleep_date=night_date)
             .order_by("-asleep_duration_minutes", "-id").first())
        if not e:
            return _no_data("sleep", night_date)
        mins = e.asleep_duration_minutes or e.total_duration_minutes or 0
        return {"status": "ok", "value": round(mins / 60.0, 1), "unit": "hours",
                "for_date": night_date.isoformat()}

    # ----- Weight (sparse — most recent ON OR BEFORE the date; 'as_of') -----
    @classmethod
    def weight_on(cls, user, target_date):
        from apps.health.models import WeightEntry
        e = (WeightEntry.objects.filter(user=user, recorded_at__date__lte=target_date)
             .order_by("-recorded_at").first())
        if not e:
            return _no_data("weight", target_date)
        as_of = e.recorded_at.date()
        return {"status": "ok", "value": float(e.value), "unit": e.unit,
                "for_date": target_date.isoformat(), "as_of": as_of.isoformat(),
                "exact": as_of == target_date}

    # ----- Glucose (GlucoseEntry.value avg on a date) -----------------------
    @classmethod
    def glucose_on(cls, user, target_date):
        from apps.health.models import GlucoseEntry
        qs = GlucoseEntry.objects.filter(user=user, recorded_at__date=target_date)
        avg = qs.aggregate(a=Avg("value"))["a"]
        if avg is None:
            return _no_data("glucose", target_date)
        return {"status": "ok", "value": round(float(avg)), "unit": "mg/dL",
                "for_date": target_date.isoformat(), "count": qs.count()}

    # ----- Calories (DailyNutritionSummary, fallback FoodEntry sum) ---------
    @classmethod
    def calories_on(cls, user, target_date):
        from apps.health.models import DailyNutritionSummary, FoodEntry
        s = DailyNutritionSummary.objects.filter(
            user=user, summary_date=target_date).first()
        if s and s.total_calories:
            return {"status": "ok", "value": int(s.total_calories), "unit": "kcal",
                    "for_date": target_date.isoformat()}
        total = (FoodEntry.objects.filter(user=user, logged_date=target_date)
                 .aggregate(s=Sum("total_calories"))["s"])
        if total:
            return {"status": "ok", "value": int(total), "unit": "kcal",
                    "for_date": target_date.isoformat()}
        return _no_data("calories", target_date)

    # ----- Date helpers ------------------------------------------------------
    @staticmethod
    def today(user):
        from apps.core.utils import get_user_today
        return get_user_today(user)

    @classmethod
    def yesterday(cls, user):
        return cls.today(user) - timedelta(days=1)
