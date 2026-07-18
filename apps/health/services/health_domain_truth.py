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
                        "glucose", "bp_systolic", "bp_diastolic") + _BODY_METRICS)
    entity_types = ("workout",)

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
    }

    def current(self, metric):
        return CurrentHealth.get(self.user, metric)

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
        """Recent completed workouts as CompleteEntity objects — answers "what
        exercises did I do", "did I do calf raises", "my sets/weight/volume",
        "summarize my workout". entity_type ∈ workout."""
        if entity_type not in (None, "workout"):
            raise KeyError(f"health domain cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.health.services.workout_queries import WorkoutQueries
        return WorkoutQueries.describe(self.user)

    def describe_one(self, name):
        """The most recent completed workout matching `name` (or activity type), or None."""
        from apps.health.services.workout_queries import WorkoutQueries
        return WorkoutQueries.describe_one(self.user, name)
