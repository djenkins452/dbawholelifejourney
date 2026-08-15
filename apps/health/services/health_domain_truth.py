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
    history_metrics = (("steps", "sleep", "weight", "workouts", "training_volume",
                        "glucose", "bp_systolic", "bp_diastolic", "bp_pulse",
                        "heart_rate", "resting_heart_rate", "hrv", "water", "spo2",
                        "body_temperature")
                       + _BODY_METRICS)
    # Intra-day reading windows (individual timestamped samples + excursions + hour-of-day
    # distribution over an arbitrary datetime Window) — the shape for HIGH-FREQUENCY
    # streams. Glucose (CGM) was first; heart rate / blood pressure / SpO2 / temperature
    # now adopt the same platform producer. See readings() below.
    reading_metrics = ("glucose", "heart_rate", "blood_pressure", "spo2",
                       "body_temperature")
    # Event-frequency metrics (how often a named event — a low, a high — happens across
    # recurring windows: "are my overnight lows getting more frequent"). Glucose is the
    # first adopter (CGM lows/highs); the other reading metrics adopt the same platform
    # producer as their episode thresholds are declared. See event_frequency() below.
    event_frequency_metrics = ("glucose",)
    # Consistency/regularity metrics (how much a repeated observation VARIES around its
    # normal pattern: "how consistent has my sleep schedule been"). Sleep is the first
    # adopter (bedtime/wake circular regularity + duration spread); meal/med/exercise
    # timing adopt the same platform producer later. See consistency() below.
    consistency_metrics = ("sleep",)
    entity_types = ("workout", "sleep", "body_measurement",
                    "steps", "glucose", "blood_pressure", "weight",
                    "heart_rate", "water", "spo2", "body_temperature",
                    "personal_record")

    # Analyzable subjects — each composes the domain's EXISTING history()/describe()
    # surfaces into one evidence bundle (see DomainTruth.analysis_subjects). Subjects
    # with an entity_type also carry record-level detail (exercises/sets/reps/weights).
    analysis_subjects = {
        "workouts": {"history_metric": "workouts", "entity_type": "workout"},
        "weight":   {"history_metric": "weight"},
        "sleep":    {"history_metric": "sleep"},
        "steps":    {"history_metric": "steps"},
        "glucose":  {"history_metric": "glucose"},
        # Blood pressure was history+entity but analysis-blind — the analytical question
        # ("how's my blood pressure trending / is it improving") had no evidence bundle.
        # Compose over the systolic series (the headline) + the BP record detail; the
        # model narrates systolic/diastolic together from the records.
        "blood_pressure": {"history_metric": "bp_systolic", "entity_type": "blood_pressure"},
        "bp":             {"history_metric": "bp_systolic", "entity_type": "blood_pressure"},
        # Body composition — waist is the headline anthropometric trend; body_measurement
        # records carry the rest. Closes the analysis-blind gap for "how's my body
        # composition trending".
        "body_composition": {"history_metric": "waist", "entity_type": "body_measurement"},
        "waist":            {"history_metric": "waist", "entity_type": "body_measurement"},
        "body_fat":         {"history_metric": "body_fat_pct",
                             "entity_type": "body_measurement"},
        # Vitals — models existed but were analysis-blind (and history-blind). Each
        # composes its new per-day series + record detail.
        "heart_rate":       {"history_metric": "resting_heart_rate",
                             "entity_type": "heart_rate"},
        "resting_heart_rate": {"history_metric": "resting_heart_rate",
                               "entity_type": "heart_rate"},
        # Training VOLUME (lb lifted/day) — the strength-progression trend, composed over the
        # canonical per-day volume series + the workout record detail. "is my volume
        # increasing / how's my lifting trending".
        "training_volume":  {"history_metric": "training_volume",
                             "entity_type": "workout"},
        "volume":           {"history_metric": "training_volume",
                             "entity_type": "workout"},
        "lifting":          {"history_metric": "training_volume",
                             "entity_type": "workout"},
        # Personal records / strength bests — an ENTITY-only analysis subject (PRs are a set
        # of records, not a per-day series). "what are my PRs / most weight I've lifted /
        # best bench". Exposes the canonical PersonalRecord (+ Brzycki e1RM); WLJ never
        # judges "getting stronger" — the model reasons over the records.
        "personal_records": {"entity_type": "personal_record"},
        "prs":              {"entity_type": "personal_record"},
        "strength":         {"entity_type": "personal_record"},
        # HRV (overnight SDNN, ms) — the deterministic recovery-relevant trend. WLJ exposes
        # the HRV facts (current/history/trend/comparison inherited); the model interprets
        # "recovery". NOT a WLJ recovery verdict (the legacy DailyHealthSummary.recovery_score
        # is a heuristic I.4 classification and is deliberately NOT exposed here).
        "hrv":                {"history_metric": "hrv"},
        "heart_rate_variability": {"history_metric": "hrv"},
        "recovery":           {"history_metric": "hrv"},
        "water":            {"history_metric": "water", "entity_type": "water"},
        "hydration":        {"history_metric": "water", "entity_type": "water"},
        "spo2":             {"history_metric": "spo2", "entity_type": "spo2"},
        "blood_oxygen":     {"history_metric": "spo2", "entity_type": "spo2"},
        "body_temperature": {"history_metric": "body_temperature",
                             "entity_type": "body_temperature"},
        "temperature":      {"history_metric": "body_temperature",
                             "entity_type": "body_temperature"},
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
        "heart_rate": HealthHistory.heart_rate,
        "resting_heart_rate": HealthHistory.resting_heart_rate,
        "water": HealthHistory.water,
        "spo2": HealthHistory.spo2,
        "body_temperature": HealthHistory.body_temperature,
        "hrv": HealthHistory.hrv,
        "training_volume": WorkoutHistory.volume,
    }

    _EVENT_FREQUENCY = {
        # metric -> dotted path to callable(user, event, windows) -> EventFrequencySeries dict
        "glucose": "apps.health.services.glucose_readings.glucose_event_frequency",
    }

    _CONSISTENCY = {
        # metric -> dotted path to callable(user, start, end, period_label) -> consistency dict
        "sleep": "apps.health.services.sleep_queries.sleep_consistency",
    }

    _READINGS = {
        # metric -> dotted path to callable(user, window) -> ReadingSeries dict
        "glucose": "apps.health.services.glucose_readings.glucose_reading_window",
        "heart_rate": "apps.health.services.vitals_readings.heart_rate_reading_window",
        "blood_pressure": "apps.health.services.vitals_readings.blood_pressure_reading_window",
        "spo2": "apps.health.services.vitals_readings.spo2_reading_window",
        "body_temperature": "apps.health.services.vitals_readings.body_temperature_reading_window",
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

    def event_frequency(self, metric, event, windows):
        """Event-frequency series for a metric ("are my lows getting more frequent").
        Delegates to the domain's single event-frequency producer (no new retrieval
        logic here); the caller resolves the recurring windows."""
        target = self._EVENT_FREQUENCY.get(metric)
        if target is None:
            raise KeyError(f"health event_frequency unsupported: {metric!r} "
                           f"(have {self.event_frequency_metrics})")
        from importlib import import_module
        mod_path, fn_name = target.rsplit(".", 1)
        fn = getattr(import_module(mod_path), fn_name)
        return fn(self.user, event, windows)

    def consistency(self, metric, start_date, end_date, period_label=""):
        """Schedule-consistency (regularity) for a metric ("how consistent has my sleep
        schedule been"). Delegates to the domain's single consistency producer (no new
        retrieval logic here); the caller resolves the (start, end) period."""
        target = self._CONSISTENCY.get(metric)
        if target is None:
            raise KeyError(f"health consistency unsupported: {metric!r} "
                           f"(have {self.consistency_metrics})")
        from importlib import import_module
        mod_path, fn_name = target.rsplit(".", 1)
        fn = getattr(import_module(mod_path), fn_name)
        return fn(self.user, start_date, end_date, period_label=period_label)

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
    def describe(self, entity_type="workout", filters=None):
        """Record-level health truth. entity_type ∈ workout | sleep | steps | vitals…
        Workouts → exercises/sets/reps/weight/PRs; sleep → stages/efficiency/quality/HRV.
        `filters` (optional start/end) scopes the workout entity to a period for the
        ranked-entity surface; other entity types ignore it (uniform describe contract)."""
        if entity_type == "sleep":
            from apps.health.services import sleep_queries
            return sleep_queries.describe(self.user)
        if entity_type == "body_measurement":
            from apps.health.services.body_measurement_queries import BodyMeasurementQueries
            return BodyMeasurementQueries.describe(self.user)
        if entity_type == "personal_record":
            from apps.health.services.pr_queries import PersonalRecordQueries
            f = filters or {}
            return PersonalRecordQueries.describe(self.user, start=f.get("start"),
                                                  end=f.get("end"))
        if entity_type in ("steps", "glucose", "blood_pressure", "weight",
                            "heart_rate", "water", "spo2", "body_temperature"):
            from apps.health.services import health_entities as HE
            return {"steps": HE.StepsEntities, "glucose": HE.GlucoseEntities,
                    "blood_pressure": HE.BloodPressureEntities,
                    "weight": HE.WeightEntities, "heart_rate": HE.HeartRateEntities,
                    "water": HE.WaterEntities, "spo2": HE.SpO2Entities,
                    "body_temperature": HE.TemperatureEntities}[entity_type].describe(self.user)
        if entity_type not in (None, "workout"):
            raise KeyError(f"health domain cannot describe {entity_type!r} "
                           f"(have {self.entity_types})")
        from apps.health.services.workout_queries import WorkoutQueries
        # `filters` (start/end) lets the ranked-entity surface scope workouts to a period —
        # e.g. "which workouts had the most volume this month". Unscoped = the recent window.
        f = filters or {}
        return WorkoutQueries.describe(self.user, start=f.get("start"), end=f.get("end"))

    def describe_one(self, name):
        """Resolve a named health record across ALL entity types. A workout by name/type/
        exercise first (the natural "my squat session"), then any other health record whose
        identity matches — so weight/BP/glucose/steps/sleep/body_measurement are reachable
        by name/identity too (previously only workouts were, a SUBSET gap)."""
        from apps.health.services.workout_queries import WorkoutQueries
        w = WorkoutQueries.describe_one(self.user, name)
        if w is not None:
            return w
        from apps.health.services.pr_queries import PersonalRecordQueries
        pr = PersonalRecordQueries.describe_one(self.user, name)   # "my bench PR"
        if pr is not None:
            return pr
        return self._entity_by_identity(
            name, ("weight", "blood_pressure", "glucose", "steps",
                   "body_measurement", "sleep"))
