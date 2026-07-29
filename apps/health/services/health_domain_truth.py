"""
HealthDomainTruth — the canonical interface to Health truth.

A thin facade composing the platform capabilities already built for Health:
Current Truth (`CurrentHealth`), Point-in-Time History (`HealthHistory`,
`WorkoutHistory`), and the SAE snapshot (`state()`). Owns NO new retrieval logic —
every consumer (Beth, dashboards, reports, engines) now has one entry point.
"""
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.health.models import BODY_COMPOSITION_METRIC_CHOICES
from apps.health.services.current_health import CurrentHealth
from apps.health.services.health_history import HealthHistory
from apps.health.services.workout_history import WorkoutHistory

# Body-composition metrics are data-driven from the model's own choice list (single
# source of truth — the trendable set can never drift from what the model can store).
# Each is a per-day series over BodyCompositionEntry (see HealthHistory.body_measurement).
_BODY_METRICS = tuple(k for k, _ in BODY_COMPOSITION_METRIC_CHOICES)


@register_domain_truth
class HealthDomainTruth(DomainTruth):
    domain = "health"
    current_metrics = tuple(sorted(CurrentHealth.SUPPORTED))
    history_metrics = (("steps", "sleep", "weight", "workouts",
                        "glucose", "bp_systolic", "bp_diastolic", "bp_pulse")
                       + _BODY_METRICS)
    # Intra-day reading windows (individual timestamped samples + excursions over an
    # arbitrary datetime Window) — the shape for HIGH-FREQUENCY streams. Glucose (CGM)
    # is the first adopter; heart rate / SpO2 / blood pressure add a spec + one line
    # here as their models gain sub-day accessors. See readings() below.
    reading_metrics = ("glucose",)
    entity_types = ("workout", "sleep", "body_measurement",
                    "steps", "glucose", "blood_pressure", "weight")

    # Analyzable subjects — each composes the domain's EXISTING history()/describe()
    # surfaces into one evidence bundle (see DomainTruth.analysis_subjects). Subjects
    # with an entity_type also carry record-level detail (exercises/sets/reps/weights).
    analysis_subjects = {
        "workouts": {"history_metric": "workouts", "entity_type": "workout"},
        "weight":   {"history_metric": "weight"},
        "sleep":    {"history_metric": "sleep"},
        "steps":    {"history_metric": "steps"},
        "glucose":  {"history_metric": "glucose"},
    }

    _HISTORY = {
        "steps": HealthHistory.steps,
        "sleep": HealthHistory.sleep,
        "weight": HealthHistory.weight,
        "workouts": WorkoutHistory.sessions,
        "glucose": HealthHistory.glucose,
        "bp_systolic": HealthHistory.bp_systolic,
        "bp_diastolic": HealthHistory.bp_diastolic,
        "bp_pulse": HealthHistory.bp_pulse,
    }

    _READINGS = {
        # metric -> callable(user, window) -> ReadingSeries dict
        "glucose": "apps.health.services.glucose_readings.glucose_reading_window",
    }

    def current(self, metric):
        return CurrentHealth.get(self.user, metric)

    def readings(self, metric, window):
        """Intra-day reading window for a high-frequency metric. Delegates to the
        domain's single reading-window producer (no new retrieval logic here)."""
        target = self._READINGS.get(metric)
        if target is None:
            raise KeyError(f"health readings unsupported: {metric!r} "
                           f"(have {self.reading_metrics})")
        from importlib import import_module
        mod_path, fn_name = target.rsplit(".", 1)
        fn = getattr(import_module(mod_path), fn_name)
        return fn(self.user, window)

    def history(self, metric, period="last_7_days", **kwargs):
        if metric in _BODY_METRICS:
            return HealthHistory.body_measurement(self.user, metric, period, **kwargs)
        fn = self._HISTORY.get(metric)
        if fn is None:
            raise KeyError(f"health history unsupported: {metric!r} "
                           f"(have {self.history_metrics})")
        return fn(self.user, period, **kwargs)

    # -- Entity Completeness Contract (record-level truth) --------------------
    # Delegates to the canonical WorkoutQueries authority (no new retrieval logic).
    def describe(self, entity_type="workout"):
        """Record-level health truth. entity_type ∈ workout | sleep. Workouts →
        exercises/sets/reps/weight/PRs; sleep → stages/efficiency/quality/HRV
        (all stored on SleepEntry, previously unreachable)."""
        if entity_type == "sleep":
            from apps.health.services import sleep_queries
            return sleep_queries.describe(self.user)
        if entity_type == "body_measurement":
            from apps.health.services.body_measurement_queries import BodyMeasurementQueries
            return BodyMeasurementQueries.describe(self.user)
        if entity_type in ("steps", "glucose", "blood_pressure", "weight"):
            from apps.health.services import health_entities as HE
            return {"steps": HE.StepsEntities, "glucose": HE.GlucoseEntities,
                    "blood_pressure": HE.BloodPressureEntities,
                    "weight": HE.WeightEntities}[entity_type].describe(self.user)
        if entity_type not in (None, "workout"):
            raise KeyError(f"health domain cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.health.services.workout_queries import WorkoutQueries
        return WorkoutQueries.describe(self.user)

    def describe_one(self, name):
        """Resolve a named health record across ALL entity types. A workout by name/type/
        exercise first (the natural "my squat session"), then any other health record whose
        identity matches — so weight/BP/glucose/steps/sleep/body_measurement are reachable
        by name/identity too (previously only workouts were, a SUBSET gap)."""
        from apps.health.services.workout_queries import WorkoutQueries
        w = WorkoutQueries.describe_one(self.user, name)
        if w is not None:
            return w
        return self._entity_by_identity(
            name, ("weight", "blood_pressure", "glucose", "steps",
                   "body_measurement", "sleep"))
