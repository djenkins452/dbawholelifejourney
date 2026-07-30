"""Record-level composers for the raw health metric models (steps / glucose / blood
pressure / weight). The scalar-current and history-series surfaces stay as-is; these
entities expose EVERY stored user field of each record (context, notes, source, device,
activity-ring metrics, attached body composition) that the collapsed number surfaces
dropped. Additive; reuses existing models only."""
from datetime import timedelta

from apps.core.truth.entity import CompleteEntity
from apps.core.truth.freshness import CURRENT


def _f(v):
    return float(v) if v is not None else None


def _recent(model, user, date_field, days=30, cap=30):
    from apps.core.utils import get_user_today
    cutoff = get_user_today(user) - timedelta(days=days)
    flt = {"user": user, f"{date_field}__date__gte": cutoff} if date_field.endswith("_at") \
        else {"user": user, f"{date_field}__gte": cutoff}
    return model.objects.filter(**flt).order_by(f"-{date_field}")[:cap]


class StepsEntities:
    @staticmethod
    def describe(user):
        from apps.health.models import StepsEntry
        out = []
        for e in _recent(StepsEntry, user, "logged_date"):
            out.append(CompleteEntity(
                kind="steps", identity=f"Steps — {e.logged_date.isoformat()}",
                definition={"date": e.logged_date.isoformat(), "source": e.source or None},
                status="logged",
                performance={"steps": e.count, "goal": e.goal,
                             "distance_miles": _f(e.distance_miles),
                             "calories_burned": _f(e.calories_burned),
                             "resting_calories": _f(e.resting_calories),
                             "flights_climbed": e.flights_climbed,
                             "exercise_minutes": e.exercise_minutes,
                             "stand_hours": e.stand_hours},
                extensions={"notes": e.notes} if e.notes else {},
                freshness=CURRENT))
        return out


class GlucoseEntities:
    @staticmethod
    def describe(user):
        from apps.health.models import GlucoseEntry
        out = []
        for e in _recent(GlucoseEntry, user, "recorded_at"):
            out.append(CompleteEntity(
                kind="glucose", identity=f"Glucose — {e.recorded_at.isoformat()}",
                definition={"recorded_at": e.recorded_at.isoformat(),
                            "context": e.context or None, "source": e.source or None,
                            "display_device": e.display_device or None},
                status="logged",
                # value in the READING's own unit + the canonical mg/dL (never mislabeled).
                performance={"value": _f(e.value), "unit": e.unit,
                             "value_mg_dl": e.value_in_mg_dl,
                             "trend": e.trend or None, "trend_rate": _f(e.trend_rate)},
                extensions={"notes": e.notes} if e.notes else {},
                freshness=CURRENT))
        return out


class BloodPressureEntities:
    @staticmethod
    def describe(user):
        from apps.health.models import BloodPressureEntry
        out = []
        for e in _recent(BloodPressureEntry, user, "recorded_at"):
            out.append(CompleteEntity(
                kind="blood_pressure", identity=f"BP — {e.recorded_at.isoformat()}",
                definition={"recorded_at": e.recorded_at.isoformat(),
                            "context": e.context or None, "arm": e.arm or None,
                            "position": e.position or None, "source": e.source or None},
                status="logged",
                performance={"systolic": e.systolic, "diastolic": e.diastolic,
                             "pulse": e.pulse},
                extensions={"notes": e.notes} if e.notes else {},
                freshness=CURRENT))
        return out


class HeartRateEntities:
    @staticmethod
    def describe(user):
        from apps.health.models import HeartRateEntry
        out = []
        for e in _recent(HeartRateEntry, user, "recorded_at"):
            out.append(CompleteEntity(
                kind="heart_rate", identity=f"Heart rate — {e.recorded_at.isoformat()}",
                definition={"recorded_at": e.recorded_at.isoformat(),
                            "context": e.context or None, "source": e.source or None},
                status="logged",
                performance={"bpm": e.bpm},
                extensions={"notes": e.notes} if e.notes else {},
                freshness=CURRENT))
        return out


class WaterEntities:
    @staticmethod
    def describe(user):
        from apps.health.models import WaterEntry
        out = []
        for e in _recent(WaterEntry, user, "logged_date"):
            out.append(CompleteEntity(
                kind="water", identity=f"Water — {e.logged_date.isoformat()}",
                definition={"date": e.logged_date.isoformat(),
                            "drink_type": getattr(e, "drink_type", None),
                            "source": getattr(e, "source", None)},
                status="logged",
                performance={"amount": _f(e.amount), "unit": e.unit,
                             "amount_oz": e.amount_oz},
                extensions={"notes": e.notes} if getattr(e, "notes", "") else {},
                freshness=CURRENT))
        return out


class SpO2Entities:
    @staticmethod
    def describe(user):
        from apps.health.models import BloodOxygenEntry
        out = []
        for e in _recent(BloodOxygenEntry, user, "recorded_at"):
            out.append(CompleteEntity(
                kind="spo2", identity=f"SpO2 — {e.recorded_at.isoformat()}",
                definition={"recorded_at": e.recorded_at.isoformat(),
                            "context": e.context or None,
                            "measurement_method": e.measurement_method or None,
                            "source": e.source or None},
                status="logged",
                performance={"spo2": e.spo2, "pulse": e.pulse},
                extensions={"notes": e.notes} if e.notes else {},
                freshness=CURRENT))
        return out


class TemperatureEntities:
    @staticmethod
    def describe(user):
        from apps.health.models import BodyTemperatureEntry
        out = []
        for e in _recent(BodyTemperatureEntry, user, "recorded_at"):
            out.append(CompleteEntity(
                kind="body_temperature",
                identity=f"Temperature — {e.recorded_at.isoformat()}",
                definition={"recorded_at": e.recorded_at.isoformat(),
                            "context": e.context or None, "source": e.source or None},
                status="logged",
                performance={"temperature": _f(e.temperature), "unit": e.unit,
                             "temperature_f": e.temperature_fahrenheit},
                extensions={"notes": e.notes} if e.notes else {},
                freshness=CURRENT))
        return out


class WeightEntities:
    @staticmethod
    def describe(user):
        from apps.health.models import WeightEntry
        out = []
        for e in _recent(WeightEntry, user, "recorded_at"):
            out.append(CompleteEntity(
                kind="weight", identity=f"Weight — {e.recorded_at.isoformat()}",
                definition={"recorded_at": e.recorded_at.isoformat(),
                            "unit": e.unit, "source": e.source or None},
                status="logged",
                performance={"weight": _f(e.value),
                             "body_fat_percentage": _f(e.body_fat_percentage),
                             "lean_body_mass": _f(e.lean_body_mass)},
                extensions={"notes": e.notes} if e.notes else {},
                freshness=CURRENT))
        return out
