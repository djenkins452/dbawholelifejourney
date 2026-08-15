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
    def hrv(cls, user, period="last_month", *, today=None, start=None, end=None):
        """Per-night Heart Rate Variability (HRV **SDNN, milliseconds**) — the canonical
        overnight HRV series from `SleepEntry.hrv_value` (as recorded by the wearable). One
        value per sleep_date (Avg over any multi-source rows), NULLs excluded so a night with
        no HRV reading is ABSENT, never a fabricated 0 (missing HRV ≠ zero recovery). Unit is
        always 'ms'; the model interprets whether higher/lower HRV means better recovery."""
        from apps.health.models import SleepEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        rows = (SleepEntry.objects.filter(user=user,
                                          sleep_date__range=(p.start, p.end),
                                          hrv_value__isnull=False)
                .values("sleep_date").annotate(v=Avg("hrv_value"))
                .order_by("sleep_date"))
        return series_from_rows(
            "health", "hrv", p,
            [{"date": r["sleep_date"], "value": round(float(r["v"]), 1)} for r in rows],
            unit="ms")

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

    @classmethod
    def glucose(cls, user, period="last_7_days", *, today=None, start=None, end=None):
        """Per-day AVERAGE glucose in canonical mg/dL — "my glucose trend this week".
        CORRECTNESS: readings may be stored in mg/dL OR mmol/L; each is normalized to
        mg/dL via GlucoseEntry.value_in_mg_dl (the canonical converter) BEFORE averaging,
        so mixed-unit rows are never blindly averaged. The series unit is always mg/dL."""
        from collections import defaultdict
        from apps.health.models import GlucoseEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        by_day = defaultdict(list)
        for e in (GlucoseEntry.objects.filter(
                    user=user, recorded_at__date__range=(p.start, p.end))
                  .only("value", "unit", "recorded_at")):
            by_day[e.recorded_at.date()].append(e.value_in_mg_dl)
        rows = [{"date": d, "value": round(sum(vals) / len(vals), 1)}
                for d, vals in sorted(by_day.items())]
        return series_from_rows("health", "glucose", p, rows, unit="mg/dL")

    # Blood pressure is two numbers; a HistorySeries point is one value, so systolic
    # and diastolic are separate metrics (the model narrates them together as "126/83
    # → 120/79"). Closes the measured BP-trend gap (2026-07-18) — there was NO BP
    # query authority at all; SAE held only the single latest reading.
    @classmethod
    def _bp_series(cls, user, field, metric, period, today, start, end):
        from apps.health.models import BloodPressureEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        rows = (BloodPressureEntry.objects.filter(
                    user=user, recorded_at__date__range=(p.start, p.end))
                .values("recorded_at__date").annotate(v=Avg(field))
                .order_by("recorded_at__date"))
        return series_from_rows(
            "health", metric, p,
            [{"date": r["recorded_at__date"], "value": round(float(r["v"]), 1)}
             for r in rows],
            unit=("bpm" if field == "pulse" else "mmHg"))

    @classmethod
    def bp_systolic(cls, user, period="last_month", *, today=None, start=None, end=None):
        return cls._bp_series(user, "systolic", "bp_systolic", period, today, start, end)

    @classmethod
    def bp_diastolic(cls, user, period="last_month", *, today=None, start=None, end=None):
        return cls._bp_series(user, "diastolic", "bp_diastolic", period, today, start, end)

    @classmethod
    def bp_pulse(cls, user, period="last_month", *, today=None, start=None, end=None):
        """Per-day resting pulse (bpm) captured alongside BP — `BloodPressureEntry.pulse`
        was stored but had no accessor (gap)."""
        return cls._bp_series(user, "pulse", "bp_pulse", period, today, start, end)

    @classmethod
    def heart_rate(cls, user, period="last_month", *, today=None, start=None, end=None):
        """Per-day AVERAGE heart rate (bpm) over HeartRateEntry.recorded_at — "how has my
        resting heart rate trended". Closes the HR truth gap (model existed, no series)."""
        from apps.health.models import HeartRateEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        rows = (HeartRateEntry.objects.filter(
                    user=user, recorded_at__date__range=(p.start, p.end))
                .values("recorded_at__date").annotate(v=Avg("bpm"))
                .order_by("recorded_at__date"))
        return series_from_rows(
            "health", "heart_rate", p,
            [{"date": r["recorded_at__date"], "value": round(float(r["v"]), 1)}
             for r in rows],
            unit="bpm")

    @classmethod
    def resting_heart_rate(cls, user, period="last_month", *, today=None,
                           start=None, end=None):
        """Per-day average RESTING heart rate (context='resting') — the clinically
        meaningful baseline trend, isolated from active/workout readings."""
        from apps.health.models import HeartRateEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        rows = (HeartRateEntry.objects.filter(
                    user=user, context="resting",
                    recorded_at__date__range=(p.start, p.end))
                .values("recorded_at__date").annotate(v=Avg("bpm"))
                .order_by("recorded_at__date"))
        return series_from_rows(
            "health", "resting_heart_rate", p,
            [{"date": r["recorded_at__date"], "value": round(float(r["v"]), 1)}
             for r in rows],
            unit="bpm")

    @classmethod
    def water(cls, user, period="last_7_days", *, today=None, start=None, end=None):
        """Per-day TOTAL hydration in oz over WaterEntry.logged_date. Uses raw amount_oz
        (not the beverage coefficient) summed per day — "am I drinking enough water"."""
        from collections import defaultdict
        from apps.health.models import WaterEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        by_day = defaultdict(float)
        for e in (WaterEntry.objects.filter(
                    user=user, logged_date__range=(p.start, p.end))
                  .only("amount", "unit", "logged_date")):
            by_day[e.logged_date] += e.amount_oz
        rows = [{"date": d, "value": round(v, 1)} for d, v in sorted(by_day.items())]
        return series_from_rows("health", "water", p, rows, unit="oz")

    @classmethod
    def spo2(cls, user, period="last_month", *, today=None, start=None, end=None):
        """Per-day AVERAGE blood-oxygen saturation (%) over BloodOxygenEntry."""
        from apps.health.models import BloodOxygenEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        rows = (BloodOxygenEntry.objects.filter(
                    user=user, recorded_at__date__range=(p.start, p.end))
                .values("recorded_at__date").annotate(v=Avg("spo2"))
                .order_by("recorded_at__date"))
        return series_from_rows(
            "health", "spo2", p,
            [{"date": r["recorded_at__date"], "value": round(float(r["v"]), 1)}
             for r in rows],
            unit="%")

    @classmethod
    def body_temperature(cls, user, period="last_month", *, today=None,
                         start=None, end=None):
        """Per-day AVERAGE body temperature in °F over BodyTemperatureEntry. Normalizes
        mixed C/F rows via temperature_fahrenheit BEFORE averaging (never blindly mixed)."""
        from collections import defaultdict
        from apps.health.models import BodyTemperatureEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        by_day = defaultdict(list)
        for e in (BodyTemperatureEntry.objects.filter(
                    user=user, recorded_at__date__range=(p.start, p.end))
                  .only("temperature", "unit", "recorded_at")):
            by_day[e.recorded_at.date()].append(e.temperature_fahrenheit)
        rows = [{"date": d, "value": round(sum(v) / len(v), 1)}
                for d, v in sorted(by_day.items())]
        return series_from_rows("health", "body_temperature", p, rows, unit="°F")

    @classmethod
    def body_measurement(cls, user, metric, period="last_month", *,
                         today=None, start=None, end=None):
        """Per-day AVERAGE of a single body-composition metric (waist, body_fat_pct,
        lean_mass, …) over `BodyCompositionEntry.measurement_date` — answers "how has
        my waist changed over time". `BodyMeasurementSession` data existed but had no
        point-in-time/series accessor (measured gap, 2026-07-18); this is it. Unit
        varies per metric, so the point value is the number and unit stays None."""
        from apps.health.models import BodyCompositionEntry
        p = resolve_period(period, today or _today(user), start=start, end=end)
        rows = (BodyCompositionEntry.objects.filter(
                    user=user, metric_name=metric,
                    measurement_date__range=(p.start, p.end))
                .values("measurement_date").annotate(v=Avg("value"))
                .order_by("measurement_date"))
        return series_from_rows(
            "health", metric, p,
            [{"date": r["measurement_date"], "value": round(float(r["v"]), 1)}
             for r in rows])
