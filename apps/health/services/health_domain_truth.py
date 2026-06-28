"""
HealthDomainTruth — the canonical interface to Health truth.

A thin facade composing the platform capabilities already built for Health:
Current Truth (`CurrentHealth`), Point-in-Time History (`HealthHistory`,
`WorkoutHistory`), and the SAE snapshot (`state()`). Owns NO new retrieval logic —
every consumer (Beth, dashboards, reports, engines) now has one entry point.
"""
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.health.services.current_health import CurrentHealth
from apps.health.services.health_history import HealthHistory
from apps.health.services.workout_history import WorkoutHistory


@register_domain_truth
class HealthDomainTruth(DomainTruth):
    domain = "health"
    current_metrics = tuple(sorted(CurrentHealth.SUPPORTED))
    history_metrics = ("steps", "sleep", "weight", "workouts")

    _HISTORY = {
        "steps": HealthHistory.steps,
        "sleep": HealthHistory.sleep,
        "weight": HealthHistory.weight,
        "workouts": WorkoutHistory.sessions,
    }

    def current(self, metric):
        return CurrentHealth.get(self.user, metric)

    def history(self, metric, period="last_7_days", **kwargs):
        fn = self._HISTORY.get(metric)
        if fn is None:
            raise KeyError(f"health history unsupported: {metric!r} "
                           f"(have {self.history_metrics})")
        return fn(self.user, period, **kwargs)
