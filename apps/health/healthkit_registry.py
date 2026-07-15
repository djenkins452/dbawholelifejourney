"""THE canonical HealthKit registry — the single authority for every HealthKit type
WLJ ingests.

One row per WLJ metric. Each row is the single source of truth for:
  * HealthKit identity — ``hk_identifier`` (Apple's string) + ``hk_swift_reads`` (the
    Swift enum cases the iOS app must authorize) + ``kind`` (quantity/category/…),
  * WLJ metric — ``key`` (the ``type`` the iOS app sends and the ingest handler routes on),
  * ``unit`` + ``fetch_strategy`` (how the sample is read/aggregated),
  * storage destination — ``model_path`` + ``presence_filter`` (+ shared-model discriminator),
  * telemetry — ``date_field`` / ``stale_after_days`` / ``core`` (freshness/health),
  * ``category`` + display metadata (``label`` / ``subtitle``) for the Health Sync UI.

This eliminates the duplicated lists that previously drifted (ingest handlers, telemetry
registry, iOS authorization). Agreement is enforced in CI by
``apps/health/tests/test_health_sync_registry_contract.py``:
  * every ingest handler key ↔ a registry row (and vice versa),
  * every registry row resolves against its real model,
  * every registry ``hk_swift_reads`` identifier is authorized in the iOS
    ``HealthKitManager.swift`` (Django → Swift drift is impossible).

Add a HealthKit type by adding ONE row here, then: the matching ingest handler
(``apps.mobile.views.HEALTH_METRIC_HANDLERS``) and the iOS producer + authorization.
The contract test tells you if you missed one.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------- #
# Categories — the grouping the Health Sync UI renders (ordered).             #
# --------------------------------------------------------------------------- #
CATEGORY_ORDER: list[tuple[str, str]] = [
    ("activity", "Activity"),
    ("heart_vitals", "Heart & Vitals"),
    ("respiratory", "Respiratory"),
    ("sleep", "Sleep & Recovery"),
    ("body", "Body Measurements"),
    ("mobility", "Mobility"),
    ("nutrition", "Nutrition"),
    ("hearing", "Hearing"),
    ("mental", "Mental Wellbeing"),
    ("workouts", "Workouts"),
    ("other", "Other"),
]
CATEGORY_LABELS = dict(CATEGORY_ORDER)

# Fetch strategies (documentation of how the iOS producer reads the sample):
#   cumulative_sum  — HKStatisticsQuery cumulative sum per day (steps, energy, distance…)
#   discrete_latest — most recent sample (weight, height, VO₂ max…)
#   discrete_avg    — daily average of discrete samples (HR, HRV, SpO₂…)
#   discrete_all    — every sample (glucose CGM, temperature…)
#   category        — HKCategorySample (sleep, mindful, HR events…)
#   correlation     — HKCorrelation (blood pressure = systolic+diastolic)
#   composite       — one payload carrying several quantities (dietary nutrients)
#   workout         — HKWorkout sessions


@dataclass(frozen=True)
class HealthKitType:
    """One canonical HealthKit type. Telemetry fields come first (they project 1:1
    onto the Health Sync status); HealthKit-identity + display metadata follow."""
    # ── WLJ metric + storage + telemetry ──
    key: str                       # the metric `type` the iOS app sends / ingest routes on
    label: str                     # display name
    model_path: str                # "apps.health.models.StepsEntry"
    date_field: str                # field to order by / read the record instant from
    unit: str = ""
    presence_filter: dict = field(default_factory=dict)  # distinguishes types sharing a model
    stale_after_days: Optional[int] = None  # None = irregular by nature (never "stale")
    core: bool = False             # phone-native, universally expected → surface as an issue if absent
    category: str = "other"
    telemetry: bool = True         # surfaced in Health Sync status?

    # ── HealthKit identity ──
    hk_identifier: str = ""        # Apple's identifier string, e.g. "HKQuantityTypeIdentifierStepCount"
    hk_swift_reads: tuple = ()     # Swift enum cases the iOS app must authorize, e.g. (".stepCount",)
    kind: str = "quantity"         # quantity | category | correlation | workout | composite
    fetch_strategy: str = "discrete_latest"
    authorized: bool = True        # part of the iOS read-authorization set?

    # ── Display metadata (Health Sync UI) ──
    subtitle: str = ""

    def get_model(self):
        from django.apps import apps as django_apps
        model_name = self.model_path.rsplit(".", 1)[1]
        return django_apps.get_model("health", model_name)


def _t(**kw) -> HealthKitType:
    return HealthKitType(**kw)


# --------------------------------------------------------------------------- #
# THE registry.                                                               #
# --------------------------------------------------------------------------- #
HEALTHKIT_TYPES: list[HealthKitType] = [
    # ═══ Activity ═══════════════════════════════════════════════════════════ #
    _t(key="steps", label="Steps", model_path="apps.health.models.StepsEntry",
       date_field="logged_date", unit="steps", presence_filter={"count__gt": 0},
       stale_after_days=2, core=True, category="activity",
       hk_identifier="HKQuantityTypeIdentifierStepCount", hk_swift_reads=(".stepCount",),
       fetch_strategy="cumulative_sum", subtitle="Daily step count"),
    _t(key="active_calories", label="Active Calories", model_path="apps.health.models.StepsEntry",
       date_field="logged_date", unit="kcal", presence_filter={"calories_burned__gt": 0},
       stale_after_days=2, category="activity",
       hk_identifier="HKQuantityTypeIdentifierActiveEnergyBurned", hk_swift_reads=(".activeEnergyBurned",),
       fetch_strategy="cumulative_sum", subtitle="Calories burned from activity"),
    _t(key="resting_calories", label="Resting Calories", model_path="apps.health.models.StepsEntry",
       date_field="logged_date", unit="kcal", presence_filter={"resting_calories__gt": 0},
       stale_after_days=2, category="activity",
       hk_identifier="HKQuantityTypeIdentifierBasalEnergyBurned", hk_swift_reads=(".basalEnergyBurned",),
       fetch_strategy="cumulative_sum", subtitle="Basal metabolic rate"),
    _t(key="distance", label="Distance", model_path="apps.health.models.StepsEntry",
       date_field="logged_date", unit="mi", presence_filter={"distance_miles__gt": 0},
       stale_after_days=2, category="activity",
       hk_identifier="HKQuantityTypeIdentifierDistanceWalkingRunning", hk_swift_reads=(".distanceWalkingRunning",),
       fetch_strategy="cumulative_sum", subtitle="Walking and running distance"),
    _t(key="flights_climbed", label="Flights Climbed", model_path="apps.health.models.StepsEntry",
       date_field="logged_date", unit="flights", presence_filter={"flights_climbed__gt": 0},
       stale_after_days=2, category="activity",
       hk_identifier="HKQuantityTypeIdentifierFlightsClimbed", hk_swift_reads=(".flightsClimbed",),
       fetch_strategy="cumulative_sum", subtitle="Stairs climbed"),
    _t(key="exercise_minutes", label="Exercise Minutes", model_path="apps.health.models.StepsEntry",
       date_field="logged_date", unit="min", presence_filter={"exercise_minutes__gt": 0},
       stale_after_days=2, category="activity",
       hk_identifier="HKQuantityTypeIdentifierAppleExerciseTime", hk_swift_reads=(".appleExerciseTime",),
       fetch_strategy="cumulative_sum", subtitle="Active exercise time"),
    _t(key="stand_hours", label="Stand Hours", model_path="apps.health.models.StepsEntry",
       date_field="logged_date", unit="hours", presence_filter={"stand_hours__gt": 0},
       stale_after_days=2, category="activity",
       hk_identifier="HKQuantityTypeIdentifierAppleStandTime", hk_swift_reads=(".appleStandTime",),
       fetch_strategy="cumulative_sum", subtitle="Hours with standing"),

    # ═══ Heart & Vitals ═════════════════════════════════════════════════════ #
    _t(key="heart_rate", label="Heart Rate", model_path="apps.health.models.HeartRateEntry",
       date_field="recorded_at", unit="bpm", stale_after_days=2, category="heart_vitals",
       hk_identifier="HKQuantityTypeIdentifierHeartRate", hk_swift_reads=(".heartRate", ".restingHeartRate"),
       fetch_strategy="discrete_avg", subtitle="Resting and average heart rate"),
    _t(key="hrv", label="Heart Rate Variability", model_path="apps.health.models.SleepEntry",
       date_field="sleep_date", unit="ms", presence_filter={"hrv_value__isnull": False},
       stale_after_days=3, category="heart_vitals",
       hk_identifier="HKQuantityTypeIdentifierHeartRateVariabilitySDNN", hk_swift_reads=(".heartRateVariabilitySDNN",),
       fetch_strategy="discrete_avg", subtitle="HRV in milliseconds"),
    _t(key="vo2_max", label="VO₂ Max", model_path="apps.health.models.SleepEntry",
       date_field="sleep_date", unit="mL/kg/min", presence_filter={"vo2_max__isnull": False},
       stale_after_days=None, category="heart_vitals",
       hk_identifier="HKQuantityTypeIdentifierVO2Max", hk_swift_reads=(".vo2Max",),
       fetch_strategy="discrete_latest", subtitle="Cardio fitness level"),
    _t(key="blood_pressure", label="Blood Pressure", model_path="apps.health.models.BloodPressureEntry",
       date_field="recorded_at", unit="mmHg", stale_after_days=None, category="heart_vitals",
       hk_identifier="HKCorrelationTypeIdentifierBloodPressure",
       hk_swift_reads=(".bloodPressureSystolic", ".bloodPressureDiastolic"),
       kind="correlation", fetch_strategy="correlation", subtitle="Systolic and diastolic"),
    _t(key="blood_oxygen", label="Blood Oxygen", model_path="apps.health.models.BloodOxygenEntry",
       date_field="recorded_at", unit="%", stale_after_days=3, category="heart_vitals",
       hk_identifier="HKQuantityTypeIdentifierOxygenSaturation", hk_swift_reads=(".oxygenSaturation",),
       fetch_strategy="discrete_avg", subtitle="SpO₂ from Apple Watch"),
    _t(key="blood_glucose", label="Blood Glucose", model_path="apps.health.models.GlucoseEntry",
       date_field="recorded_at", unit="mg/dL", stale_after_days=2, category="heart_vitals",
       hk_identifier="HKQuantityTypeIdentifierBloodGlucose", hk_swift_reads=(".bloodGlucose",),
       fetch_strategy="discrete_all", subtitle="CGM readings from Dexcom"),
    _t(key="body_temperature", label="Body Temperature", model_path="apps.health.models.BodyTemperatureEntry",
       date_field="recorded_at", unit="°F", stale_after_days=None, category="heart_vitals",
       hk_identifier="HKQuantityTypeIdentifierBodyTemperature", hk_swift_reads=(".bodyTemperature",),
       fetch_strategy="discrete_all", subtitle="Temperature readings"),
    _t(key="high_heart_rate_event", label="High Heart Rate Events",
       model_path="apps.health.models.HeartRateEventEntry", date_field="recorded_at", unit="events",
       presence_filter={"event_type": "high_hr"}, stale_after_days=None, category="heart_vitals",
       hk_identifier="HKCategoryTypeIdentifierHighHeartRateEvent", hk_swift_reads=(".highHeartRateEvent",),
       kind="category", fetch_strategy="category", subtitle="High heart rate notifications"),
    _t(key="low_heart_rate_event", label="Low Heart Rate Events",
       model_path="apps.health.models.HeartRateEventEntry", date_field="recorded_at", unit="events",
       presence_filter={"event_type": "low_hr"}, stale_after_days=None, category="heart_vitals",
       hk_identifier="HKCategoryTypeIdentifierLowHeartRateEvent", hk_swift_reads=(".lowHeartRateEvent",),
       kind="category", fetch_strategy="category", subtitle="Low heart rate notifications"),
    _t(key="irregular_rhythm_event", label="Irregular Rhythm Events",
       model_path="apps.health.models.HeartRateEventEntry", date_field="recorded_at", unit="events",
       presence_filter={"event_type": "irregular_rhythm"}, stale_after_days=None, category="heart_vitals",
       hk_identifier="HKCategoryTypeIdentifierIrregularHeartRhythmEvent", hk_swift_reads=(".irregularHeartRhythmEvent",),
       kind="category", fetch_strategy="category", subtitle="Irregular rhythm notifications"),

    # ═══ Respiratory ════════════════════════════════════════════════════════ #
    _t(key="respiratory_rate", label="Respiratory Rate", model_path="apps.health.models.SleepEntry",
       date_field="sleep_date", unit="breaths/min", presence_filter={"respiratory_rate__isnull": False},
       stale_after_days=3, category="respiratory",
       hk_identifier="HKQuantityTypeIdentifierRespiratoryRate", hk_swift_reads=(".respiratoryRate",),
       fetch_strategy="discrete_avg", subtitle="Breaths per minute"),

    # ═══ Sleep & Recovery ═══════════════════════════════════════════════════ #
    _t(key="sleep", label="Sleep", model_path="apps.health.models.SleepEntry",
       date_field="sleep_date", unit="nights", stale_after_days=2, category="sleep",
       hk_identifier="HKCategoryTypeIdentifierSleepAnalysis", hk_swift_reads=(".sleepAnalysis",),
       kind="category", fetch_strategy="category", subtitle="Sleep analysis and stages"),

    # ═══ Body Measurements ══════════════════════════════════════════════════ #
    _t(key="weight", label="Weight", model_path="apps.health.models.WeightEntry",
       date_field="recorded_at", unit="lbs", stale_after_days=None, category="body",
       hk_identifier="HKQuantityTypeIdentifierBodyMass", hk_swift_reads=(".bodyMass",),
       fetch_strategy="discrete_latest", subtitle="Body weight measurements"),
    _t(key="body_fat", label="Body Fat", model_path="apps.health.models.WeightEntry",
       date_field="recorded_at", unit="%", presence_filter={"body_fat_percentage__isnull": False},
       stale_after_days=None, category="body",
       hk_identifier="HKQuantityTypeIdentifierBodyFatPercentage", hk_swift_reads=(".bodyFatPercentage",),
       fetch_strategy="discrete_latest", subtitle="Body fat percentage"),
    _t(key="lean_body_mass", label="Lean Body Mass", model_path="apps.health.models.WeightEntry",
       date_field="recorded_at", unit="lbs", presence_filter={"lean_body_mass__isnull": False},
       stale_after_days=None, category="body",
       hk_identifier="HKQuantityTypeIdentifierLeanBodyMass", hk_swift_reads=(".leanBodyMass",),
       fetch_strategy="discrete_latest", subtitle="Muscle and non-fat mass"),
    _t(key="bmi", label="Body Mass Index", model_path="apps.health.models.BodyCompositionEntry",
       date_field="measurement_date", unit="", presence_filter={"metric_name": "bmi"},
       stale_after_days=None, category="body",
       hk_identifier="HKQuantityTypeIdentifierBodyMassIndex", hk_swift_reads=(".bodyMassIndex",),
       fetch_strategy="discrete_latest", subtitle="Body mass index"),
    _t(key="waist", label="Waist Circumference", model_path="apps.health.models.BodyCompositionEntry",
       date_field="measurement_date", unit="in", presence_filter={"metric_name": "waist"},
       stale_after_days=None, category="body",
       hk_identifier="HKQuantityTypeIdentifierWaistCircumference", hk_swift_reads=(".waistCircumference",),
       fetch_strategy="discrete_latest", subtitle="Waist circumference"),
    _t(key="height", label="Height", model_path="apps.health.models.BodyCompositionEntry",
       date_field="measurement_date", unit="in", presence_filter={"metric_name": "height"},
       stale_after_days=None, category="body",
       hk_identifier="HKQuantityTypeIdentifierHeight", hk_swift_reads=(".height",),
       fetch_strategy="discrete_latest", subtitle="Height for BMI / BSA"),

    # ═══ Mobility ═══════════════════════════════════════════════════════════ #
    _t(key="walking_speed", label="Walking Speed", model_path="apps.health.models.MobilityEntry",
       date_field="metric_date", unit="mph", presence_filter={"walking_speed__isnull": False},
       stale_after_days=None, category="mobility",
       hk_identifier="HKQuantityTypeIdentifierWalkingSpeed", hk_swift_reads=(".walkingSpeed",),
       fetch_strategy="discrete_avg", subtitle="Average walking speed"),
    _t(key="step_length", label="Step Length", model_path="apps.health.models.MobilityEntry",
       date_field="metric_date", unit="in", presence_filter={"step_length__isnull": False},
       stale_after_days=None, category="mobility",
       hk_identifier="HKQuantityTypeIdentifierWalkingStepLength", hk_swift_reads=(".walkingStepLength",),
       fetch_strategy="discrete_avg", subtitle="Average step length"),
    _t(key="walking_asymmetry", label="Walking Asymmetry", model_path="apps.health.models.MobilityEntry",
       date_field="metric_date", unit="%", presence_filter={"walking_asymmetry__isnull": False},
       stale_after_days=None, category="mobility",
       hk_identifier="HKQuantityTypeIdentifierWalkingAsymmetryPercentage",
       hk_swift_reads=(".walkingAsymmetryPercentage",),
       fetch_strategy="discrete_avg", subtitle="Left/right step imbalance"),
    _t(key="double_support_time", label="Double Support Time", model_path="apps.health.models.MobilityEntry",
       date_field="metric_date", unit="%", presence_filter={"double_support_time__isnull": False},
       stale_after_days=None, category="mobility",
       hk_identifier="HKQuantityTypeIdentifierWalkingDoubleSupportPercentage",
       hk_swift_reads=(".walkingDoubleSupportPercentage",),
       fetch_strategy="discrete_avg", subtitle="Balance indicator"),
    _t(key="walking_steadiness", label="Walking Steadiness", model_path="apps.health.models.MobilityEntry",
       date_field="metric_date", unit="", presence_filter={"walking_steadiness__gt": ""},
       stale_after_days=None, category="mobility",
       hk_identifier="HKQuantityTypeIdentifierAppleWalkingSteadiness", hk_swift_reads=(".appleWalkingSteadiness",),
       fetch_strategy="discrete_latest", subtitle="Fall-risk classification"),
    _t(key="stair_ascent_speed", label="Stair Ascent Speed", model_path="apps.health.models.MobilityEntry",
       date_field="metric_date", unit="ft/s", presence_filter={"stair_ascent_speed__isnull": False},
       stale_after_days=None, category="mobility",
       hk_identifier="HKQuantityTypeIdentifierStairAscentSpeed", hk_swift_reads=(".stairAscentSpeed",),
       fetch_strategy="discrete_avg", subtitle="Stair ascent speed"),
    _t(key="stair_descent_speed", label="Stair Descent Speed", model_path="apps.health.models.MobilityEntry",
       date_field="metric_date", unit="ft/s", presence_filter={"stair_descent_speed__isnull": False},
       stale_after_days=None, category="mobility",
       hk_identifier="HKQuantityTypeIdentifierStairDescentSpeed", hk_swift_reads=(".stairDescentSpeed",),
       fetch_strategy="discrete_avg", subtitle="Stair descent speed"),
    _t(key="six_min_walk", label="Six-Minute Walk", model_path="apps.health.models.MobilityEntry",
       date_field="metric_date", unit="m", presence_filter={"six_min_walk_distance__isnull": False},
       stale_after_days=None, category="mobility",
       hk_identifier="HKQuantityTypeIdentifierSixMinuteWalkTestDistance",
       hk_swift_reads=(".sixMinuteWalkTestDistance",),
       fetch_strategy="discrete_latest", subtitle="Six-minute walk distance"),

    # ═══ Nutrition ══════════════════════════════════════════════════════════ #
    _t(key="water", label="Water", model_path="apps.health.models.WaterEntry",
       date_field="logged_date", unit="fl oz", stale_after_days=None, category="nutrition",
       hk_identifier="HKQuantityTypeIdentifierDietaryWater", hk_swift_reads=(".dietaryWater",),
       fetch_strategy="cumulative_sum", subtitle="Daily hydration"),
    _t(key="caffeine", label="Caffeine", model_path="apps.health.models.SleepEntry",
       date_field="sleep_date", unit="mg", presence_filter={"caffeine_mg__isnull": False},
       stale_after_days=None, category="nutrition",
       hk_identifier="HKQuantityTypeIdentifierDietaryCaffeine", hk_swift_reads=(".dietaryCaffeine",),
       fetch_strategy="cumulative_sum", subtitle="Daily caffeine intake"),
    _t(key="dietary_nutrients", label="Nutrition (Macros & Micros)",
       model_path="apps.health.models.DietaryNutrientEntry", date_field="metric_date", unit="",
       stale_after_days=None, category="nutrition",
       hk_identifier="HKQuantityTypeIdentifierDietaryEnergyConsumed",
       hk_swift_reads=(".dietaryEnergyConsumed", ".dietaryProtein", ".dietaryCarbohydrates",
                       ".dietaryFatTotal", ".dietaryFiber", ".dietarySugar", ".dietarySodium",
                       ".dietaryCholesterol", ".dietaryFatSaturated", ".dietaryPotassium",
                       ".dietaryCalcium", ".dietaryIron", ".dietaryVitaminD"),
       kind="composite", fetch_strategy="composite", subtitle="Macros and micronutrients"),

    # ═══ Hearing ════════════════════════════════════════════════════════════ #
    _t(key="headphone_audio", label="Headphone Audio", model_path="apps.health.models.AudioExposureEntry",
       date_field="metric_date", unit="dB", presence_filter={"headphone_level_db__isnull": False},
       stale_after_days=None, category="hearing",
       hk_identifier="HKQuantityTypeIdentifierHeadphoneAudioExposure", hk_swift_reads=(".headphoneAudioExposure",),
       fetch_strategy="discrete_avg", subtitle="Headphone audio levels"),
    _t(key="environmental_audio", label="Environmental Audio", model_path="apps.health.models.AudioExposureEntry",
       date_field="metric_date", unit="dB", presence_filter={"environmental_level_db__isnull": False},
       stale_after_days=None, category="hearing",
       hk_identifier="HKQuantityTypeIdentifierEnvironmentalAudioExposure",
       hk_swift_reads=(".environmentalAudioExposure",),
       fetch_strategy="discrete_avg", subtitle="Environmental sound levels"),

    # ═══ Mental Wellbeing ═══════════════════════════════════════════════════ #
    _t(key="mindful_minutes", label="Mindful Minutes", model_path="apps.health.models.SleepEntry",
       date_field="sleep_date", unit="min", presence_filter={"mindful_minutes__isnull": False},
       stale_after_days=None, category="mental",
       hk_identifier="HKCategoryTypeIdentifierMindfulSession", hk_swift_reads=(".mindfulSession",),
       kind="category", fetch_strategy="category", subtitle="Meditation and mindfulness"),

    # ═══ Workouts ═══════════════════════════════════════════════════════════ #
    _t(key="workout", label="Workouts", model_path="apps.health.models.WorkoutSession",
       date_field="date", unit="workouts", stale_after_days=None, category="workouts",
       hk_identifier="HKWorkoutTypeIdentifier", hk_swift_reads=(), kind="workout",
       fetch_strategy="workout", subtitle="Workout sessions"),
]

HEALTHKIT_TYPES_BY_KEY = {t.key: t for t in HEALTHKIT_TYPES}

# Every Swift enum case the iOS app must authorize (for the Django→Swift contract).
AUTHORIZED_SWIFT_READS = {
    r for t in HEALTHKIT_TYPES if t.authorized for r in t.hk_swift_reads
}
