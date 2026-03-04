# WLJ Health Intelligence Audit & Dashboard Architecture

**Date:** 2026-03-04
**Author:** Claude Code (Senior Systems Architect)
**Status:** Comprehensive Audit Complete

---

## Table of Contents

1. [Current WLJ Health System Audit](#1-current-wlj-health-system-audit)
2. [Missing Health Signals](#2-missing-health-signals)
3. [External Data Integration Plan](#3-external-data-integration-plan)
4. [Health Data Model Architecture](#4-health-data-model-architecture)
5. [Health Command Center Dashboard](#5-health-command-center-dashboard)
6. [CoS Intelligence Layer](#6-cos-intelligence-layer)
7. [Personalized Health Insights](#7-personalized-health-insights)
8. [Implementation Roadmap](#8-implementation-roadmap)

---

## 1. Current WLJ Health System Audit

### 1.1 Metrics Currently Tracked

WLJ has an **extensive** health data model — 55+ models across 6 apps. Here is the complete inventory:

| Category | Metric | Model | Source(s) | Storage |
|----------|--------|-------|-----------|---------|
| **Weight** | Weight (lb/kg) | `WeightEntry` | Manual, Apple Health | `apps/health/models.py` |
| **Body Comp** | Body fat %, lean mass, muscle mass, bone mass, water %, metabolic age, visceral fat, BMI | `BodyCompositionEntry` | Manual, scale, DEXA, bioimpedance | `apps/health/models.py` |
| **Blood Pressure** | Systolic, diastolic, pulse | `BloodPressureEntry` | Manual, Apple Health | `apps/health/models.py` |
| **Heart Rate** | BPM with context | `HeartRateEntry` | Manual | `apps/health/models.py` |
| **Heart Rate Events** | Irregular rhythm, high/low HR alerts | `HeartRateEventEntry` | Apple Health | `apps/health/models.py` |
| **Blood Oxygen** | SpO2, pulse | `BloodOxygenEntry` | Manual, Apple Health | `apps/health/models.py` |
| **Blood Sugar** | Glucose (mg/dL, mmol/L) with trend arrows | `GlucoseEntry` | Manual, Dexcom CGM, Apple Health | `apps/health/models.py` |
| **Sleep** | Bedtime, wake time, duration, quality, REM/deep/light stages, awake count | `SleepEntry` | Manual, Apple Health, Garmin, Fitbit, Oura, Whoop | `apps/health/models.py` |
| **HRV** | Heart rate variability | `SleepEntry.hrv_value` | Apple Health (sleep-derived) | `apps/health/models.py` |
| **VO2 Max** | Estimated VO2 max | `SleepEntry.vo2_max` | Apple Health | `apps/health/models.py` |
| **Respiratory Rate** | Breaths/min | `SleepEntry.respiratory_rate` | Apple Health | `apps/health/models.py` |
| **Steps** | Count, distance, calories, flights climbed, exercise minutes, stand hours | `StepsEntry` | Manual, Apple Health, Google Fit, Fitbit, Garmin, Samsung | `apps/health/models.py` |
| **Workouts** | Session with exercises, sets, reps, weight, cardio, classes | `WorkoutSession`, `WorkoutExercise`, `ExerciseSet`, `CardioDetails`, `ClassDetails` | Manual, Apple Health | `apps/health/models.py` |
| **Personal Records** | Estimated 1RM via Brzycki formula | `PersonalRecord` | Calculated from `ExerciseSet` | `apps/health/models.py` |
| **Nutrition** | Full macro/micro nutrients per food entry, meal templates | `FoodEntry`, `FoodItem`, `CustomFood`, `DailyNutritionSummary` | Manual, barcode, camera, voice, FatSecret API, OpenFoodFacts | `apps/health/models.py` |
| **Hydration** | Water intake (oz/ml/cups/liters) | `WaterEntry` | Manual, Apple Health | `apps/health/models.py` |
| **Medication** | Adherence, schedule, supply, refills | `Medicine`, `MedicineSchedule`, `MedicineLog` | Manual, CoS voice | `apps/health/models.py` |
| **Fasting** | Windows with type (16:8, 18:6, 20:4, OMAD, etc.) | `FastingWindow` | Manual, CoS voice | `apps/health/models.py` |
| **Glucose (CGM)** | Continuous glucose with trend rates | `GlucoseEntry` + `DexcomCredential` | Dexcom OAuth API | `apps/health/models.py` |
| **Body Temperature** | Temp (°F/°C) with context | `BodyTemperatureEntry` | Manual, Apple Health | `apps/health/models.py` |
| **Caffeine** | mg consumed | `SleepEntry.caffeine_mg` | Apple Health | `apps/health/models.py` |
| **Mindfulness** | Minutes of meditation | `SleepEntry.mindful_minutes` | Apple Health | `apps/health/models.py` |
| **Mobility** | Flexibility, balance, ROM, walking asymmetry, steadiness, speed, step length | `MobilityEntry` | Apple Health | `apps/health/models.py` |
| **Audio Exposure** | Decibel levels, duration | `AudioExposureEntry` | Apple Health | `apps/health/models.py` |
| **Dietary Nutrients** | Individual nutrient daily totals | `DietaryNutrientEntry` | Apple Health | `apps/health/models.py` |
| **Menstrual Cycle** | Flow, symptoms, mood, energy, cervical mucus, basal temp | `Cycle`, `CycleDailyLog`, `CyclePrediction`, `CycleSettings` | Manual | `apps/health/models.py` |
| **Lab Results** | 16+ categories (hematology, chemistry, lipids, thyroid, etc.) | `LabResult`, `LabPanel`, `LabTestCatalog` | PDF import, manual | `apps/medical/models.py` |
| **Medical Providers** | Doctor info, specialty, staff | `MedicalProvider`, `ProviderStaff` | Manual | `apps/medical/models.py` |
| **Health Profile** | Height, birth date, gender, TDEE, BMR, activity level, goals | `HealthProfile` | Manual | `apps/health/models.py` |
| **Transformation** | Protocol, workout plans, schedules | `TransformationProtocol`, `WorkoutPlan`, `WorkoutSchedule` | Manual | `apps/health/models.py` |
| **Nutrition Goals** | Calorie/macro/micro targets | `NutritionGoals` | Manual | `apps/health/models.py` |

### 1.2 Data Sources

| Source | Integration Type | Data Types | Status |
|--------|-----------------|------------|--------|
| **Apple Health / HealthKit** | iOS app → POST `/api/mobile/health/ingest/` | 37+ metric types | **Active** — full sync pipeline |
| **Dexcom CGM** | OAuth 2.0 API | Glucose readings, trends, rates | **Active** — direct API |
| **FatSecret API** | REST API | 1.9M+ food database | **Active** — nutrition lookup |
| **OpenFoodFacts** | REST API | Barcode → nutrition | **Active** — barcode fallback |
| **OpenAI Vision** | API | Food image → nutrition estimates | **Active** — camera scan |
| **Manual Entry** | Web + CoS chat | All metrics | **Active** |
| **PDF Import** | OCR + text extraction | Lab results | **Active** |

### 1.3 Existing Dashboards

| Dashboard | URL | Description |
|-----------|-----|-------------|
| **Main Dashboard** | `/dashboard/` | AI command center with tiles, briefings, intelligence |
| **Transformation** | `/dashboard/transformation/` | Weight progress, body comp, performance charts |
| **Blood Pressure** | `/health/physical/blood-pressure/dashboard/` | Systolic/diastolic trends, AHA categories |
| **Blood Oxygen** | `/health/physical/blood-oxygen/dashboard/` | SpO2 trends and status |
| **Heart Rate** | `/health/physical/heart-rate/dashboard/` | BPM trends with context |
| **HRV** | `/health/physical/hrv/dashboard/` | Heart rate variability trends |
| **VO2 Max** | `/health/physical/vo2-max/dashboard/` | Fitness level trends |
| **Respiratory Rate** | `/health/physical/respiratory-rate/dashboard/` | Breathing rate trends |
| **Body Temperature** | `/health/physical/body-temperature/dashboard/` | Temperature trends |
| **Caffeine** | `/health/physical/caffeine/dashboard/` | Daily caffeine intake |
| **Mindful Minutes** | `/health/physical/mindful-minutes/dashboard/` | Meditation tracking |
| **Activity** | `/health/physical/activity/dashboard/` | Steps/movement trends |
| **Glucose** | `/health/physical/glucose/` | Blood sugar with Dexcom integration |
| **Cycle** | `/health/physical/cycle/` | Menstrual cycle calendar + predictions |
| **Nutrition Stats** | `/health/physical/nutrition/stats/` | Macro/calorie summaries |
| **Fitness Progress** | `/health/physical/fitness/progress/` | Workout stats and PRs |
| **Medicine Adherence** | `/health/physical/medicine/adherence/` | Dose compliance tracking |

**Total: 17 individual dashboards** — but each operates in isolation. There is **no unified Health Command Center** that correlates data across domains.

### 1.4 CoS Health Data Access

The CoS AI currently has access to:

| Data Domain | Access Type | Quality |
|-------------|------------|---------|
| Weight + trend | Dashboard context | **Good** — 6-week trend, goal progress |
| Nutrition (today) | Dashboard context | **Moderate** — calories/goal only, no macros |
| Medicine adherence | Dashboard + briefing | **Good** — weekly %, missed doses |
| Fasting status | Dashboard context | **Good** — active window, hours |
| Workout status | Dashboard + briefing | **Good** — today done, weekly count, PRs |
| Sleep (last night) | Executive briefing | **Minimal** — duration + quality only |
| Steps | Intent logging | **Minimal** — 7-day average, no trend analysis |
| Glucose | Intent logging | **Minimal** — can log, but no trend interpretation |
| Heart rate | Intent logging | **Minimal** — can log, no correlation analysis |
| Body composition | Intent logging | **Basic** — can log, limited trending |
| Lab results | **None** | Not accessible to CoS |
| HRV / VO2 / recovery | **None** | Not in CoS context |
| Cycle data | **None** | Not in CoS context |
| Hydration trends | **None** | Not in CoS context |
| Caffeine/sleep correlation | **None** | Not analyzed |

**Key Finding:** The CoS can LOG most health data but has very limited ability to ANALYZE, CORRELATE, or PREDICT based on that data. It sees today's snapshot, not multi-week patterns.

---

## 2. Missing Health Signals

### 2.1 Signals WLJ Captures But Doesn't Analyze

These are already in the database but have **no cross-domain analytics**:

| Signal | Stored In | Analysis Gap |
|--------|-----------|-------------|
| **Sleep stages** (REM/deep/light) | `SleepEntry` | No quality scoring algorithm, no correlation with workout recovery |
| **HRV trends** | `SleepEntry.hrv_value` | No recovery readiness calculation, no training load correlation |
| **VO2 Max changes** | `SleepEntry.vo2_max` | No fitness trajectory analysis |
| **Resting heart rate** | `HeartRateEntry` (context=resting) | No cardiovascular health trending |
| **Caffeine ↔ sleep correlation** | Both exist | No correlation analysis |
| **Weight ↔ nutrition correlation** | Both exist | No calorie deficit/surplus calculation |
| **Workout volume trends** | `ExerciseSet` | No progressive overload detection |
| **Blood sugar ↔ meal correlation** | Both exist | No post-meal glucose response analysis |
| **Lab result trends** | `LabResult` | Results stored but no longitudinal trend analysis |
| **Medication ↔ vitals correlation** | Both exist | No analysis of BP medication → BP readings |
| **Walking/gait metrics** | `MobilityEntry` | Collected from HealthKit but no analysis |
| **Fasting ↔ glucose correlation** | Both exist | No fasting response analysis |

### 2.2 Signals Not Yet Captured

| Signal | Priority | Why It Matters | Integration Source |
|--------|----------|---------------|-------------------|
| **Recovery score** | **Critical** | Prevents overtraining, optimizes training load | Calculated from HRV + sleep + workout load |
| **Training load** | **Critical** | Prevents plateaus, tracks progressive overload | Calculated from workout volume/intensity over time |
| **Sleep debt** | **High** | Chronic sleep deprivation sabotages fat loss | Calculated from sleep duration vs. target (7-8h) |
| **Metabolic rate estimate** | **High** | Tracks if metabolism is adapting to calorie deficit | Calculated from TDEE, weight change rate, calorie intake |
| **Body recomposition score** | **High** | Muscle gain + fat loss simultaneously | Calculated from body comp + strength PRs |
| **Stress score** | **Medium** | Stress drives cortisol → fat retention | Could derive from HRV, sleep quality, resting HR |
| **Circadian consistency** | **Medium** | Irregular sleep/wake times hurt metabolism | Calculated from bedtime/wake time variance |
| **Hydration adequacy** | **Medium** | Dehydration impairs performance + recovery | Currently tracked but no goal system |
| **Protein timing** | **Medium** | Post-workout protein matters for muscle synthesis | FoodEntry has `logged_time` but no workout proximity analysis |
| **InBody-specific metrics** | **High** | Segmental lean mass, ECW/ICW ratio, phase angle | InBody scanner outputs detailed body comp |

### 2.3 Signals That Matter Most for Weight Loss

Ranked by impact on sustainable fat loss:

1. **Calorie deficit accuracy** — #1 driver. Requires accurate nutrition tracking + TDEE estimation
2. **Sleep quality + duration** — Sleep deprivation increases hunger hormones (ghrelin), decreases leptin
3. **Protein intake** — Preserves lean mass during deficit, increases satiety
4. **Workout consistency** — Maintains metabolic rate, builds/preserves muscle
5. **Blood sugar stability** — Spikes → crashes → cravings → overeating
6. **Stress/cortisol** — Chronic stress promotes visceral fat storage
7. **Recovery** — Overtraining → elevated cortisol → muscle loss → metabolic adaptation
8. **Hydration** — Even mild dehydration impairs fat oxidation and performance
9. **Fasting windows** — Intermittent fasting can improve insulin sensitivity
10. **Progressive overload** — Increasing training stimulus prevents adaptation

---

## 3. External Data Integration Plan

### 3.1 Apple Health / HealthKit

**Status: ALREADY INTEGRATED** — This is WLJ's strongest integration.

**Current Architecture:**
```
Apple Watch → iPhone HealthKit Store → WLJ iOS App → POST /api/mobile/health/ingest/
                                                       ↓
                                               HealthIngestionRun
                                                       ↓
                                            37+ metric type handlers
                                                       ↓
                                           Django models (with sync_id dedup)
```

**37+ data types synced across 7 categories:**
- Activity: steps, calories, distance, flights, exercise minutes, stand hours, workouts
- Body: weight, body fat %, lean body mass
- Sleep: analysis with stages, HRV, VO2 max, respiratory rate, caffeine, mindful minutes
- Heart: resting HR, BP (paired systolic/diastolic), SpO2, body temp, glucose
- Hydration: water intake
- Mobility: walking asymmetry, steadiness, speed, step length, six-min walk, stair speed
- Events: high/low HR alerts, irregular rhythm (AFib)
- Audio: headphone/environmental exposure
- Dietary: calories, protein, carbs, fat, fiber, sugar, sodium, cholesterol

**Improvement needed:** The sync pipeline exists but the CoS and dashboards don't fully leverage the data once it arrives.

### 3.2 InBody Scale

**Status: NOT INTEGRATED**

**Recommended Approach: Manual Import + Future API**

InBody does not provide a public consumer API. Options:

| Approach | Feasibility | Recommendation |
|----------|-------------|----------------|
| **Manual entry via CoS** | **Now** | "Hey CoS, log my InBody results: weight 235, body fat 28.5%, skeletal muscle mass 98.2 lbs" |
| **Photo scan of InBody printout** | **Now** | Use existing OpenAI Vision scan to OCR the InBody results sheet |
| **InBody app → Apple Health → WLJ** | **Now (partial)** | InBody app syncs weight + body fat to Apple Health, which syncs to WLJ. But loses segmental data. |
| **CSV/PDF import pipeline** | **Phase 2** | Build an InBody result sheet parser for detailed body comp data |
| **InBody API (B2B)** | **Future** | InBody offers B2B API for gyms/clinics — not available for individual consumers |

**Recommended data to capture from InBody:**
- Total body weight
- Body fat percentage + pounds
- Skeletal muscle mass (total + segmental: R arm, L arm, trunk, R leg, L leg)
- Body water (total + ECW/ICW ratio)
- Visceral fat level
- Basal metabolic rate
- Phase angle (cell health indicator)
- Body composition history chart

**Action:** The existing `BodyCompositionEntry` model already has fields for most of this. Add `skeletal_muscle_mass_detail` (JSONField) for segmental data, and `phase_angle`, `ecw_icw_ratio` fields.

### 3.3 Dexcom CGM

**Status: ALREADY INTEGRATED** — OAuth 2.0 flow with automatic sync.

**Current Architecture:**
```
Dexcom CGM Sensor → Dexcom App → Dexcom API (OAuth 2.0)
                                       ↓
                              WLJ /health/physical/glucose/dexcom/sync/
                                       ↓
                              GlucoseEntry (value, unit, context, trend, trend_rate)
```

**What works:** Reading sync, trend arrows, rate of change.
**What's missing:** Post-meal glucose response analysis, time-in-range calculation, glucose variability metrics (CV%, standard deviation).

### 3.4 Nutrition Tracking — Barcode Scanning Assessment

**Current system:** Multi-source lookup: Local DB → FatSecret API (1.9M+ foods) → OpenFoodFacts → AI Vision estimation

**Accuracy Assessment:**

| Source | Accuracy | Issue |
|--------|----------|-------|
| FatSecret API | **Good** | 1.9M+ foods, good coverage, generally accurate macros |
| OpenFoodFacts | **Variable** | Community-sourced, some entries incomplete or wrong |
| Barcode scan | **Good** | The scanning works well — the issue is usually the food database behind it |
| AI Vision estimation | **Low** | Vision-based calorie estimation has inherent ±30-50% error |

**Recommendation: Keep barcode scanning, improve the pipeline**

Barcode scanning itself is NOT the problem. The issues are:
1. **Database gaps** — Some products not in FatSecret or OpenFoodFacts
2. **Portion estimation** — Users eat different amounts than the label serving size
3. **Prepared food** — Restaurant meals, home-cooked meals have no barcode

**Better approach — Hybrid tracking system:**

| Method | When to Use | Accuracy |
|--------|------------|----------|
| **Barcode scan** | Packaged foods with labels | **High** — use as-is, data from FatSecret |
| **Meal templates** | Repeated meals (same breakfast, protein shake) | **High** — log once, reuse |
| **Quick macros** | When you know the approximate macros | **High** — user enters protein/carbs/fat/cals |
| **Restaurant lookup** | Eating out at chains | **Medium-High** — many chains publish nutrition |
| **AI photo estimation** | Fallback only | **Low** — flag confidence score |
| **Voice to CoS** | Quick logging | **Medium** — depends on food DB match |

**Key recommendation:** Prioritize making meal template and "copy previous day/meal" features more prominent in the UX. Most people eat 10-15 rotating meals. Once those are logged accurately once, reuse is fast and precise.

---

## 4. Health Data Model Architecture

### 4.1 Current Model Assessment

WLJ's health data model is **surprisingly comprehensive**. Most of the entities needed already exist. The primary gaps are:

1. **No `DailyHealthSummary` aggregate table** — data exists in 15+ tables but nothing pre-computes a daily rollup
2. **No `RecoveryMetrics` model** — HRV, sleep quality, and training load aren't combined into a recovery score
3. **No `HealthScore` model** — no overall health score calculation
4. **Missing InBody-specific fields** on `BodyCompositionEntry`
5. **No `WeeklyHealthReport` model** — weekly summaries computed on-the-fly, not stored

### 4.2 New/Modified Models Needed

#### DailyHealthSummary (NEW — the missing keystone)

This is the **single most important model to add**. It aggregates all daily health data into one row per user per day, enabling fast dashboards and CoS intelligence.

```python
class DailyHealthSummary(UserOwnedModel):
    """Pre-computed daily health rollup for fast dashboard and CoS access."""
    summary_date = models.DateField()

    # Weight & Body Comp (latest reading of day)
    weight_lbs = models.DecimalField(null=True)
    body_fat_pct = models.DecimalField(null=True)
    lean_mass_lbs = models.DecimalField(null=True)

    # Sleep (previous night)
    sleep_duration_minutes = models.PositiveIntegerField(null=True)
    sleep_quality = models.CharField(max_length=20, blank=True)  # excellent/good/fair/poor
    deep_sleep_minutes = models.PositiveIntegerField(null=True)
    rem_sleep_minutes = models.PositiveIntegerField(null=True)
    sleep_efficiency_pct = models.DecimalField(null=True)

    # Activity
    steps = models.PositiveIntegerField(null=True)
    active_calories = models.PositiveIntegerField(null=True)
    exercise_minutes = models.PositiveIntegerField(null=True)
    stand_hours = models.PositiveIntegerField(null=True)
    flights_climbed = models.PositiveIntegerField(null=True)

    # Workouts
    workout_count = models.PositiveSmallIntegerField(default=0)
    workout_duration_minutes = models.PositiveIntegerField(null=True)
    workout_calories = models.PositiveIntegerField(null=True)

    # Nutrition
    calories_consumed = models.PositiveIntegerField(null=True)
    protein_g = models.DecimalField(null=True)
    carbs_g = models.DecimalField(null=True)
    fat_g = models.DecimalField(null=True)
    fiber_g = models.DecimalField(null=True)
    water_oz = models.DecimalField(null=True)
    meals_logged = models.PositiveSmallIntegerField(default=0)

    # Vitals (daily averages or latest)
    resting_hr_bpm = models.PositiveSmallIntegerField(null=True)
    hrv_ms = models.DecimalField(null=True)
    blood_pressure_systolic = models.PositiveSmallIntegerField(null=True)
    blood_pressure_diastolic = models.PositiveSmallIntegerField(null=True)
    spo2_pct = models.DecimalField(null=True)

    # Glucose
    glucose_avg = models.DecimalField(null=True)
    glucose_min = models.DecimalField(null=True)
    glucose_max = models.DecimalField(null=True)
    time_in_range_pct = models.DecimalField(null=True)  # 70-180 mg/dL

    # Medication
    medicine_adherence_pct = models.DecimalField(null=True)
    doses_taken = models.PositiveSmallIntegerField(default=0)
    doses_missed = models.PositiveSmallIntegerField(default=0)

    # Fasting
    fasting_hours = models.DecimalField(null=True)

    # Recovery & Wellness
    recovery_score = models.PositiveSmallIntegerField(null=True)  # 0-100
    stress_indicator = models.CharField(max_length=20, blank=True)  # low/moderate/high

    # Caffeine
    caffeine_mg = models.DecimalField(null=True)

    # Mindfulness
    mindful_minutes = models.PositiveIntegerField(null=True)

    # Metadata
    data_completeness_pct = models.DecimalField(null=True)  # how many domains have data
    last_computed = models.DateTimeField()

    class Meta:
        unique_together = ('user', 'summary_date')
        indexes = [
            models.Index(fields=['user', 'summary_date']),
            models.Index(fields=['user', '-summary_date']),  # for recent queries
        ]
```

**Why this matters:** Instead of querying 15+ tables to answer "How was Danny's health yesterday?", query one row. This enables fast dashboards, efficient CoS context loading, and trend calculations.

#### RecoveryMetrics (NEW)

```python
class RecoveryMetrics(UserOwnedModel):
    """Daily recovery assessment derived from multiple signals."""
    assessment_date = models.DateField()

    # Inputs
    hrv_value = models.DecimalField(null=True)
    hrv_baseline = models.DecimalField(null=True)  # 7-day rolling average
    hrv_deviation_pct = models.DecimalField(null=True)

    resting_hr = models.PositiveSmallIntegerField(null=True)
    resting_hr_baseline = models.PositiveSmallIntegerField(null=True)

    sleep_score = models.PositiveSmallIntegerField(null=True)  # 0-100
    sleep_debt_hours = models.DecimalField(null=True)  # accumulated over 7 days

    training_load_score = models.PositiveSmallIntegerField(null=True)  # 0-100

    # Output
    recovery_score = models.PositiveSmallIntegerField()  # 0-100
    recovery_status = models.CharField(max_length=20)  # excellent/good/fair/poor/critical
    recommendation = models.TextField()  # "Rest day recommended" / "Ready for hard training"

    class Meta:
        unique_together = ('user', 'assessment_date')
```

#### Additions to BodyCompositionEntry (MODIFY)

```python
# Add these fields to existing BodyCompositionEntry:
skeletal_muscle_mass_lbs = models.DecimalField(null=True)  # Total skeletal muscle
segmental_lean = models.JSONField(null=True)  # {"r_arm": 8.2, "l_arm": 8.0, "trunk": 55.1, "r_leg": 22.5, "l_leg": 22.3}
phase_angle = models.DecimalField(null=True)  # Cell health (InBody)
ecw_icw_ratio = models.DecimalField(null=True)  # Extracellular/intracellular water
basal_metabolic_rate = models.PositiveIntegerField(null=True)
```

#### WeeklyHealthReport (NEW)

```python
class WeeklyHealthReport(UserOwnedModel):
    """Weekly pre-computed health analysis for CoS and dashboard."""
    week_start = models.DateField()  # Monday
    week_end = models.DateField()  # Sunday

    # Averages from DailyHealthSummary
    avg_sleep_hours = models.DecimalField(null=True)
    avg_steps = models.PositiveIntegerField(null=True)
    avg_calories = models.PositiveIntegerField(null=True)
    avg_protein_g = models.DecimalField(null=True)
    avg_water_oz = models.DecimalField(null=True)
    avg_resting_hr = models.PositiveSmallIntegerField(null=True)
    avg_hrv = models.DecimalField(null=True)
    avg_recovery_score = models.PositiveSmallIntegerField(null=True)

    # Workout
    workouts_completed = models.PositiveSmallIntegerField(default=0)
    total_workout_minutes = models.PositiveIntegerField(default=0)
    new_prs = models.PositiveSmallIntegerField(default=0)

    # Compliance
    medicine_adherence_pct = models.DecimalField(null=True)
    nutrition_logging_days = models.PositiveSmallIntegerField(default=0)  # out of 7
    sleep_logging_days = models.PositiveSmallIntegerField(default=0)

    # Weight change
    weight_start = models.DecimalField(null=True)
    weight_end = models.DecimalField(null=True)
    weight_change = models.DecimalField(null=True)

    # Trends (vs prior week)
    trend_sleep = models.CharField(max_length=10, blank=True)  # improving/stable/declining
    trend_activity = models.CharField(max_length=10, blank=True)
    trend_nutrition = models.CharField(max_length=10, blank=True)
    trend_recovery = models.CharField(max_length=10, blank=True)
    trend_weight = models.CharField(max_length=10, blank=True)

    # Overall
    health_score = models.PositiveSmallIntegerField(null=True)  # 0-100

    # CoS narrative
    narrative = models.TextField(blank=True)  # AI-generated weekly summary
    top_insights = models.JSONField(default=list)  # top 3 insights
    action_items = models.JSONField(default=list)  # top 3 recommendations

    class Meta:
        unique_together = ('user', 'week_start')
```

### 4.3 Entity Relationships

```
User
  ├── HealthProfile (1:1) — height, age, gender, goals, TDEE, BMR
  ├── DailyHealthSummary (1:many) — one per day, pre-computed rollup
  │     ↑ aggregated from:
  │     ├── WeightEntry
  │     ├── SleepEntry
  │     ├── StepsEntry
  │     ├── WorkoutSession → WorkoutExercise → ExerciseSet / CardioDetails
  │     ├── FoodEntry → DailyNutritionSummary
  │     ├── WaterEntry
  │     ├── HeartRateEntry
  │     ├── BloodPressureEntry
  │     ├── BloodOxygenEntry
  │     ├── GlucoseEntry
  │     ├── MedicineLog
  │     └── FastingWindow
  ├── RecoveryMetrics (1:many) — derived daily recovery score
  ├── WeeklyHealthReport (1:many) — weekly summary + CoS narrative
  ├── BodyCompositionEntry (1:many) — InBody / scale / DEXA data
  ├── InsightResult (1:many) — generated insights
  └── LabResult (1:many) — periodic lab work
```

---

## 5. Health Command Center Dashboard

### 5.1 Design Philosophy

The Health Command Center answers three questions:
1. **Where was Danny?** — Historical trends over weeks/months
2. **Where is he now?** — Today's snapshot across all health domains
3. **Where is he trending?** — Trajectory analysis with forward projections

### 5.2 Dashboard Layout

```
┌──────────────────────────────────────────────────────────────┐
│  HEALTH COMMAND CENTER                    Health Score: 78/100│
│  ─────────────────────────────────────────────────────────── │
│  Recovery: ●●●●○ Good    Sleep Debt: 2.5h    Streak: 12 days │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─── WEIGHT & BODY COMP ──┐  ┌─── SLEEP QUALITY ────────┐  │
│  │ Current: 235.4 lbs      │  │ Last night: 7h 12m       │  │
│  │ Goal: 215 lbs           │  │ Quality: Good             │  │
│  │ Lost: 8.6 lbs (3.5%)    │  │ Deep: 1h 22m | REM: 1h 45│  │
│  │ Body Fat: 28.1%         │  │ Sleep Debt: 2.5h          │  │
│  │ Lean Mass: 169.3 lbs    │  │ 7-day avg: 6h 48m        │  │
│  │ [Chart: 12-week trend]  │  │ [Chart: 14-day stages]    │  │
│  │ ▼ -1.2 lbs/week         │  │ ▼ Bedtime variance: 45min │  │
│  └─────────────────────────┘  └───────────────────────────┘  │
│                                                              │
│  ┌─── WORKOUT CONSISTENCY ─┐  ┌─── ACTIVITY & MOVEMENT ──┐  │
│  │ This week: 4/5 planned  │  │ Today: 8,234 steps       │  │
│  │ Streak: 3 weeks         │  │ Goal: 10,000 (82%)       │  │
│  │ Volume trend: ▲ +5%     │  │ Active cal: 420          │  │
│  │ New PRs (30d): 3        │  │ Exercise min: 45         │  │
│  │ [Chart: 8-week freq]    │  │ [Chart: 14-day steps]    │  │
│  │ Training load: Moderate  │  │ Stand hours: 8/12        │  │
│  └─────────────────────────┘  └───────────────────────────┘  │
│                                                              │
│  ┌─── BLOOD SUGAR ─────────┐  ┌─── NUTRITION ────────────┐  │
│  │ Current: 112 mg/dL →    │  │ Today: 1,450 / 2,200 cal │  │
│  │ Time in range: 87%      │  │ Protein: 95g / 180g      │  │
│  │ Avg (7d): 118 mg/dL     │  │ Tracking streak: 8 days  │  │
│  │ Fasting avg: 98 mg/dL   │  │ [Chart: 7-day macros]    │  │
│  │ [Chart: 24h glucose]    │  │ ⚠ Low protein 3 of 7 days│  │
│  │ CV%: 22% (target <36%)  │  │ Water: 48oz / 64oz       │  │
│  └─────────────────────────┘  └───────────────────────────┘  │
│                                                              │
│  ┌─── RECOVERY & STRESS ───┐  ┌─── MEDICATION ───────────┐  │
│  │ Recovery: 72/100 (Good)  │  │ Adherence: 94% (7d)     │  │
│  │ HRV: 42ms (baseline: 38)│  │ Today: 6/7 doses taken   │  │
│  │ Resting HR: 68 bpm      │  │ Next: Metformin 6:00 PM  │  │
│  │ VO2 Max: 38.2 ml/kg/min │  │ Supply: Lisinopril 12d   │  │
│  │ [Chart: 14-day HRV]     │  │ [Chart: 30-day adherence]│  │
│  │ Recommendation: Train    │  │ ✓ No refills needed      │  │
│  └─────────────────────────┘  └───────────────────────────┘  │
│                                                              │
│  ┌─── CoS INTELLIGENCE ────────────────────────────────────┐ │
│  │ "Your weight loss trend is strong at -1.2 lbs/week.     │ │
│  │  However, your sleep debt is climbing — you averaged     │ │
│  │  6h48m this week vs your 7.5h target. This could slow   │ │
│  │  your fat loss. Priority: get to bed by 10:30 PM."      │ │
│  │                                                          │ │
│  │  Strengths: Workout consistency, medication adherence    │ │
│  │  Watch: Sleep duration, protein intake                   │ │
│  │  Action: Earlier bedtime, add protein to lunch           │ │
│  └──────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

### 5.3 Section Specifications

#### A. Weight & Body Composition

| Metric | Source | Visualization |
|--------|--------|---------------|
| Current weight | Latest `WeightEntry` | Large number with trend arrow |
| Goal weight + progress | `HealthProfile.target_weight_pounds` | Progress bar |
| Weight change rate | Calculated from 14-day linear regression | lbs/week with safety check |
| Body fat % | Latest `BodyCompositionEntry` or `WeightEntry.body_fat_percentage` | Trend line |
| Lean mass | `BodyCompositionEntry.lean_mass_pounds` | Trend line (should stay flat or increase) |
| 12-week chart | `WeightEntry` last 84 days | Line chart with linear trend overlay |

**Auto-insights:**
- "Losing weight too fast (>2 lbs/week) — risk of muscle loss"
- "Body fat declining while lean mass stable — healthy recomposition"
- "Weight plateau detected (14+ days) — consider adjusting calories or training"
- "Goal pace: on track to reach 215 lbs by [date]"

#### B. Sleep Quality

| Metric | Source | Visualization |
|--------|--------|---------------|
| Last night duration | `SleepEntry` | Large number |
| Quality rating | `SleepEntry.quality_rating` | Color-coded badge |
| Sleep stages | `SleepEntry.deep_sleep_minutes`, `.rem_sleep_minutes` | Stacked bar |
| Sleep debt | Calculated: target hours (7.5) - actual, accumulated over 7 days | Number with color |
| 7-day average | Calculated from `SleepEntry` | Number |
| Bedtime variance | Standard deviation of bedtimes over 14 days | Number |
| 14-day chart | `SleepEntry` last 14 days | Stacked area chart (deep/REM/light/awake) |
| Sleep efficiency | `SleepEntry.sleep_efficiency` | Percentage |

**Auto-insights:**
- "Sleep debt climbing — prioritize 8+ hours tonight"
- "Your deep sleep is below average (target: 1.5-2h) — avoid alcohol and caffeine after 2 PM"
- "Bedtime consistency improved — circadian rhythm is stabilizing"
- "Correlation: nights with 7+ hours → better glucose readings next day"

#### C. Workout Consistency

| Metric | Source | Visualization |
|--------|--------|---------------|
| This week completed/planned | `WorkoutSession` + `WorkoutPlan` | Fraction with progress |
| Streak (consecutive weeks meeting goal) | Calculated | Number with flame icon |
| Volume trend | Sum of weight × reps over trailing 4 weeks vs prior 4 weeks | Percentage change |
| New PRs (30 days) | `PersonalRecord` last 30 days | Count |
| Training load | Calculated from volume + cardio + duration | Categorical: light/moderate/hard/overreaching |
| 8-week frequency chart | `WorkoutSession` grouped by week | Bar chart |

**Auto-insights:**
- "Volume increased 5% — progressive overload on track"
- "No chest exercises in 14 days — muscle group imbalance risk"
- "Workouts declining: 5→4→3 sessions in last 3 weeks"
- "New PR on squat! Estimated 1RM: 285 lbs (+10 lbs)"

#### D. Activity & Movement

| Metric | Source | Visualization |
|--------|--------|---------------|
| Today's steps | `StepsEntry` | Large number with goal progress |
| Active calories | `StepsEntry.calories_burned` | Number |
| Exercise minutes | `StepsEntry.exercise_minutes` | Number vs goal |
| Stand hours | `StepsEntry.stand_hours` | Ring or fraction |
| 14-day trend | `StepsEntry` last 14 days | Bar chart |

**Auto-insights:**
- "Below 5,000 steps 3 of last 7 days — increase daily movement"
- "Active calorie burn trending up — consistent with weight loss pace"

#### E. Blood Sugar

| Metric | Source | Visualization |
|--------|--------|---------------|
| Current reading | Latest `GlucoseEntry` with trend arrow | Large number + arrow |
| Time in range (70-180) | Calculated from day's readings | Percentage |
| 7-day average | Calculated | Number |
| Fasting average | `GlucoseEntry` where context=fasting, 7-day | Number |
| Glucose variability (CV%) | Standard deviation / mean × 100 | Percentage (target <36%) |
| 24-hour chart | `GlucoseEntry` last 24h (or Dexcom CGM) | Line chart with range bands |

**Auto-insights:**
- "Post-dinner spikes: avg 165 mg/dL — consider lower carb dinners"
- "Fasting glucose improving: 108→98 over 30 days"
- "Time in range excellent at 87% (target: >70%)"
- "Correlation: workout days have 15% lower avg glucose"

#### F. Nutrition

| Metric | Source | Visualization |
|--------|--------|---------------|
| Today's calories vs goal | `DailyNutritionSummary` + `NutritionGoals` | Progress bar |
| Protein vs goal | `DailyNutritionSummary.total_protein_g` | Progress bar (priority metric) |
| Macro split | Protein/carbs/fat percentages | Donut chart |
| Tracking streak | Consecutive days with logged meals | Number |
| 7-day macro chart | `DailyNutritionSummary` last 7 days | Grouped bar chart |
| Water intake | `WaterEntry` daily total | Progress ring |

**Auto-insights:**
- "Protein below target 3 of 7 days — add protein to lunch or snack"
- "Calorie deficit averaging 450/day — on track for 0.9 lbs/week loss"
- "Logging dropped off on weekends — track Saturday/Sunday meals"
- "Fiber consistently low — add vegetables or a fiber supplement"

#### G. Recovery & Stress

| Metric | Source | Visualization |
|--------|--------|---------------|
| Recovery score | `RecoveryMetrics.recovery_score` | Large gauge (0-100) |
| HRV | `SleepEntry.hrv_value` with baseline comparison | Number + deviation |
| Resting HR | Latest resting `HeartRateEntry` | Number + trend |
| VO2 Max | `SleepEntry.vo2_max` | Number + trend |
| 14-day HRV chart | `SleepEntry.hrv_value` last 14 days | Line chart with baseline band |
| Training recommendation | From recovery status | Text badge |

**Auto-insights:**
- "HRV above baseline — fully recovered, ready for hard training"
- "Resting HR elevated 5 bpm above normal — possible overtraining or illness"
- "VO2 Max improved 1.2 ml/kg/min this month — cardiovascular fitness improving"
- "3 consecutive days with low recovery — recommend a rest day"

#### H. Medication

| Metric | Source | Visualization |
|--------|--------|---------------|
| Weekly adherence | `MedicineLog` last 7 days | Percentage |
| Today's doses | `MedicineLog` today | Taken/total fraction |
| Next dose | `MedicineSchedule` upcoming | Time + medicine name |
| Supply alerts | `Medicine.days_until_empty` | List of low-supply meds |
| 30-day trend | `MedicineLog` adherence by day | Heatmap or bar chart |

**Auto-insights:**
- "Missed evening dose 2x this week — set a reminder for 8 PM"
- "Adherence up from 88% to 94% — great improvement"
- "Lisinopril supply: 12 days remaining — refill soon"

---

## 6. CoS Intelligence Layer

### 6.1 Design Principle

The CoS must not be a **narrator** (repeating dashboard data). It must be an **analyst** that:
- Detects **patterns** humans miss (cross-domain correlations)
- Identifies **risks** before they become problems
- Provides **actionable** recommendations with specific next steps
- Tracks **trajectory** — not just current state, but where things are heading

### 6.2 Data the CoS Needs

```python
# CoS Health Context Builder (enhanced)
def build_cos_health_context(user):
    """Build comprehensive health context for CoS reasoning."""
    today = date.today()

    # Current snapshot
    daily = DailyHealthSummary.objects.filter(user=user, summary_date=today).first()

    # 7-day history
    week = DailyHealthSummary.objects.filter(
        user=user,
        summary_date__gte=today - timedelta(days=7)
    ).order_by('summary_date')

    # 30-day history (for trends)
    month = DailyHealthSummary.objects.filter(
        user=user,
        summary_date__gte=today - timedelta(days=30)
    ).order_by('summary_date')

    # Latest weekly report
    weekly_report = WeeklyHealthReport.objects.filter(
        user=user
    ).order_by('-week_start').first()

    # Recovery status
    recovery = RecoveryMetrics.objects.filter(
        user=user, assessment_date=today
    ).first()

    # Active context
    active_fast = FastingWindow.objects.filter(
        user=user, ended_at__isnull=True
    ).first()

    upcoming_meds = MedicineSchedule.objects.filter(
        medicine__user=user,
        medicine__medicine_status='active',
        scheduled_time__gte=timezone.now().time()
    ).order_by('scheduled_time')[:3]

    return {
        'today': daily,
        'week_history': list(week.values()),
        'month_trends': calculate_trends(month),
        'weekly_report': weekly_report,
        'recovery': recovery,
        'active_fast': active_fast,
        'upcoming_meds': list(upcoming_meds),
    }
```

### 6.3 Pattern Detection Rules

The CoS should watch for these specific patterns:

#### Weight Loss Patterns

| Pattern | Detection Logic | CoS Response |
|---------|----------------|--------------|
| **Plateau** | Weight change < 0.5 lbs over 14+ days | "Weight plateau detected. Consider: refeed day, increase protein, change workout split, or recalculate TDEE" |
| **Too fast** | Weight loss > 2 lbs/week for 2+ weeks | "Losing weight too quickly — risk of muscle loss. Consider increasing calories by 200-300" |
| **Rebound** | Weight trending up after sustained loss | "Weight trending up after 8 weeks of loss. Check: nutrition logging consistency, stress levels, sleep" |
| **Lean mass loss** | Lean mass declining while weight drops | "Lean mass declining — increase protein intake and prioritize strength training" |

#### Sleep-Weight Correlation

| Pattern | Detection Logic | CoS Response |
|---------|----------------|--------------|
| **Sleep debt + slow loss** | Sleep avg < 6.5h AND weight loss slowed | "Sleep debt may be slowing fat loss. Poor sleep increases hunger hormones and reduces metabolic rate" |
| **Irregular bedtime** | Bedtime std dev > 60 minutes | "Irregular sleep schedule detected. Consistent bedtimes improve sleep quality and metabolic health" |
| **Low deep sleep** | Deep sleep < 60 min average | "Deep sleep below target. Avoid alcohol, reduce late-night screen time, consider earlier dinner" |

#### Nutrition Patterns

| Pattern | Detection Logic | CoS Response |
|---------|----------------|--------------|
| **Protein gap** | Protein < 0.7g per lb bodyweight, 3+ days/week | "Protein consistently low. Target: 165g/day minimum for muscle preservation during fat loss" |
| **Weekend tracking drop** | Meals logged Sat/Sun < 50% of weekday average | "Weekend nutrition tracking drops off. This is often where hidden calories accumulate" |
| **Calorie creep** | Average daily calories increasing week-over-week | "Calorie intake trending up: 1,800→1,950→2,100 over 3 weeks" |
| **Post-workout nutrition** | No food entry within 2h of workout completion | "No post-workout meal detected. Consider 30-40g protein within 1 hour of training" |

#### Workout & Recovery Patterns

| Pattern | Detection Logic | CoS Response |
|---------|----------------|--------------|
| **Overtraining risk** | Recovery score < 50 for 3+ consecutive days AND no rest day | "Recovery critically low. Take a rest day — continued training increases injury risk" |
| **Volume stagnation** | Training volume flat for 4+ weeks | "Progressive overload stalled. Consider: increase weight by 2.5%, add a set, or change exercises" |
| **Skipping workouts** | Workout frequency declining 3 weeks in a row | "Workout frequency declining: 5→4→3 sessions. What's blocking consistency?" |
| **Muscle imbalance** | A major muscle group not trained in 14+ days | "Haven't trained legs in 16 days. Balance is important for injury prevention" |

#### Glucose Patterns

| Pattern | Detection Logic | CoS Response |
|---------|----------------|--------------|
| **Rising fasting glucose** | Fasting glucose trending up over 30 days | "Fasting glucose trending up. This may indicate increasing insulin resistance" |
| **Post-meal spikes** | Post-meal readings >180 mg/dL frequently | "Frequent post-meal spikes detected. Consider: smaller carb portions, walking after meals" |
| **Workout benefit** | Glucose avg lower on workout days | "Your glucose averages 15 mg/dL lower on workout days — exercise is helping insulin sensitivity" |

#### Cross-Domain Correlations (the CoS's unique value)

| Correlation | Detection Logic | CoS Response |
|------------|----------------|--------------|
| **Sleep ↔ Glucose** | Poor sleep nights → higher next-day glucose | "Poor sleep last night correlates with higher glucose today. Prioritize sleep tonight" |
| **Stress ↔ Weight** | Low HRV + high resting HR + weight plateau | "Stress indicators elevated alongside weight plateau. Consider: meditation, walks, sleep" |
| **Caffeine ↔ Sleep** | High caffeine days → lower sleep quality | "Caffeine intake of 400mg+ correlates with 30min less deep sleep for you" |
| **Nutrition ↔ Recovery** | Low protein days → lower recovery scores | "Your recovery scores are 15% lower on days with <130g protein" |
| **Workout ↔ Sleep** | Hard workout days → better sleep (or worse, if overtraining) | "Hard training days improve your sleep quality by 12% — good sign of appropriate training load" |
| **Fasting ↔ Glucose** | Longer fasts → lower fasting glucose | "Your fasting windows of 16+ hours correlate with better fasting glucose readings" |

### 6.4 CoS Intelligence Examples

The CoS should be capable of delivering statements like:

> "You're losing weight at a healthy pace of 1.2 lbs/week, but your sleep debt has climbed to 4.5 hours this week. Research shows chronic sleep deprivation can reduce fat loss by up to 55% while increasing muscle loss. Priority action: get to bed by 10:30 PM for the next 3 nights."

> "Your workout consistency improved from 3 to 5 sessions this week — great momentum. However, your nutrition tracking dropped to 3 days logged. The workouts create the stimulus, but the nutrition determines the outcome. Log your meals today."

> "Your weight loss trend is slowing: -1.8 lbs/week in January → -0.6 lbs/week in February. Your calorie intake hasn't changed, suggesting metabolic adaptation. Consider: (1) a 1-week maintenance phase at 2,400 calories, (2) adding 10 minutes of walking daily, or (3) adjusting your deficit to a more moderate 300 calories."

> "Interesting pattern: your blood sugar is 18% lower on days you work out AND eat 150g+ protein. Today you've already worked out. Make sure to hit your protein target — your body responds well to this combination."

### 6.5 Required Calculations

| Calculation | Formula | Module |
|-------------|---------|--------|
| **Weekly weight change** | Linear regression slope of last 14 days × 7 | `health_analytics_service.py` (NEW) |
| **Sleep debt** | Σ(target_hours - actual_hours) for last 7 days, floor at 0 | `health_analytics_service.py` |
| **Bedtime consistency** | Standard deviation of bedtimes (last 14 days) | `health_analytics_service.py` |
| **Recovery score** | Weighted: HRV deviation (40%) + sleep score (30%) + resting HR deviation (15%) + training load factor (15%) | `recovery_service.py` (NEW) |
| **Training load** | Volume × intensity factor, 7-day rolling sum | `fitness_analytics.py` (NEW) |
| **Calorie deficit** | TDEE - avg daily calories (7-day) | `nutrition_analytics.py` (ENHANCE) |
| **Protein adequacy** | avg daily protein / (bodyweight × 0.8) | `nutrition_analytics.py` |
| **Time in range** | (readings between 70-180) / total readings × 100 | `glucose_analytics.py` (NEW) |
| **Glucose CV%** | std_dev / mean × 100 | `glucose_analytics.py` |
| **Medicine adherence** | doses_taken / doses_scheduled × 100 | `medicine_utils.py` (EXISTS) |
| **Health score** | Composite: sleep (20%) + activity (15%) + nutrition (20%) + recovery (15%) + weight trend (10%) + glucose (10%) + adherence (10%) | `health_score_service.py` (NEW) |
| **Data completeness** | domains_with_data_today / total_trackable_domains × 100 | `daily_summary_service.py` (NEW) |

---

## 7. Personalized Health Insights

### 7.1 Weekly Health Score (0-100)

```
Health Score = weighted average of:
  Sleep Score (20%):
    - Duration vs target (0-40 pts)
    - Quality rating (0-20 pts)
    - Consistency/regularity (0-20 pts)
    - Deep sleep adequacy (0-20 pts)

  Activity Score (15%):
    - Steps vs goal (0-40 pts)
    - Exercise minutes (0-30 pts)
    - Stand hours (0-15 pts)
    - Movement consistency (0-15 pts)

  Nutrition Score (20%):
    - Calorie target adherence (0-25 pts)
    - Protein target adherence (0-30 pts)
    - Tracking completeness (0-25 pts)
    - Hydration (0-20 pts)

  Recovery Score (15%):
    - HRV vs baseline (0-40 pts)
    - Resting HR vs baseline (0-30 pts)
    - Sleep quality factor (0-30 pts)

  Weight Trend Score (10%):
    - Direction toward goal (0-50 pts)
    - Rate (healthy range 0.5-1.5 lbs/wk) (0-30 pts)
    - Lean mass preservation (0-20 pts)

  Glucose Score (10%):
    - Time in range (0-40 pts)
    - Fasting average (0-30 pts)
    - Variability (CV%) (0-30 pts)

  Medication Adherence (10%):
    - Weekly adherence % (0-100 pts, direct mapping)
```

### 7.2 Recovery Status

| Score | Status | Visual | Meaning |
|-------|--------|--------|---------|
| 85-100 | Excellent | Green | Ready for hard training |
| 70-84 | Good | Blue | Normal training appropriate |
| 50-69 | Fair | Yellow | Light training recommended |
| 30-49 | Poor | Orange | Active recovery only |
| 0-29 | Critical | Red | Complete rest recommended |

**Calculation:**
```
Recovery = (
    HRV_factor × 0.40 +      # HRV above baseline = good
    Sleep_factor × 0.30 +     # Deep sleep + duration
    HR_factor × 0.15 +        # Resting HR below baseline = good
    Load_factor × 0.15        # Recent training load (inverse)
)

Where:
  HRV_factor = min(100, (current_hrv / baseline_hrv) × 100)
  Sleep_factor = min(100, (deep_sleep_pct × 50 + (duration/target) × 50))
  HR_factor = min(100, max(0, 100 - ((current_rhr - baseline_rhr) × 10)))
  Load_factor = 100 - min(100, (7day_training_load / threshold) × 100)
```

### 7.3 Fat Loss Trajectory

```
Current rate: -X.X lbs/week (14-day linear regression)
Days to goal: remaining_lbs / weekly_rate × 7
Projected date: today + days_to_goal
Confidence: based on tracking consistency and trend stability

Display:
  "At current pace, you'll reach 215 lbs by June 15, 2026"
  "Rate: 1.2 lbs/week (healthy range)"
  "Confidence: High (consistent tracking, stable trend)"
```

### 7.4 Sleep Debt

```
Target: 7.5 hours/night (configurable via HealthProfile)
Daily debt: max(0, target - actual)
Rolling 7-day debt: Σ daily_debt for last 7 days
Status:
  0-2h: "Well rested"
  2-5h: "Mild sleep debt"
  5-10h: "Moderate sleep debt — recovery impacted"
  10h+: "Severe sleep debt — health risk"
```

### 7.5 Workout Momentum

```
Momentum = (current_week_sessions / target_sessions) × streak_multiplier

Where:
  streak_multiplier = 1.0 + (consecutive_weeks_on_target × 0.1), max 2.0

Status:
  Momentum > 1.5: "Building strong momentum" (🔥)
  Momentum 1.0-1.5: "On track" (✓)
  Momentum 0.5-1.0: "Slipping — pick it back up"
  Momentum < 0.5: "Stalled — what's blocking you?"
```

### 7.6 Metabolic Health Trend

```
Composite of:
  - Fasting glucose trend (30-day)
  - HbA1c (if lab results available)
  - Time in range (if CGM data)
  - Insulin resistance proxy: fasting glucose × fasting insulin / 405 (if labs available)
  - Weight trend (metabolic adaptation if loss slows despite consistent deficit)

Status:
  "Improving" — glucose declining, time in range increasing
  "Stable" — no significant change
  "Concerning" — glucose rising, time in range declining
  "Needs attention" — fasting glucose >100 or A1c >5.7
```

---

## 8. Implementation Roadmap

### Step 1 — Foundation: DailyHealthSummary & Analytics Service (Week 1-2)

**Objective:** Create the aggregation layer that everything else depends on.

**Tasks:**
1. **Create `DailyHealthSummary` model** (as designed in Section 4)
   - Files: `apps/health/models.py`, new migration
   - Add unique constraint on (user, summary_date)

2. **Create `apps/health/services/daily_summary_service.py`**
   - `compute_daily_summary(user, date)` — queries all source tables, creates/updates summary
   - `backfill_summaries(user, start_date, end_date)` — one-time backfill of historical data
   - Called: on health data save (signal), nightly cron, and on-demand

3. **Create Django signal handlers** to trigger recomputation
   - On save of any health metric → recompute that day's summary
   - File: `apps/health/signals.py` (add to existing or create)

4. **Create management command:** `python manage.py compute_health_summaries`
   - Backfill historical data and set up nightly recomputation

5. **Create `apps/health/services/health_analytics_service.py`**
   - `calculate_weight_trend(user, days=14)` → slope, rate/week, projection
   - `calculate_sleep_debt(user, days=7)` → accumulated debt hours
   - `calculate_bedtime_consistency(user, days=14)` → std deviation
   - `calculate_calorie_deficit(user, days=7)` → avg deficit/day
   - `calculate_protein_adequacy(user, days=7)` → ratio to target

**Database changes:** 1 new model (DailyHealthSummary), 1 migration

### Step 2 — Recovery & Scoring Services (Week 2-3)

**Objective:** Computed health intelligence that powers the dashboard and CoS.

**Tasks:**
1. **Create `RecoveryMetrics` model** (as designed in Section 4)
   - Files: `apps/health/models.py`, new migration

2. **Create `apps/health/services/recovery_service.py`**
   - `compute_recovery_score(user, date)` → 0-100 with status and recommendation
   - Uses HRV baseline (7-day rolling), sleep score, resting HR, training load

3. **Create `apps/health/services/health_score_service.py`**
   - `compute_weekly_health_score(user, week_start)` → 0-100 composite
   - Sub-scores: sleep, activity, nutrition, recovery, weight, glucose, adherence

4. **Create `apps/health/services/fitness_analytics.py`**
   - `calculate_training_load(user, days=7)` → volume-based load score
   - `calculate_progressive_overload(user, exercise, weeks=4)` → volume trend
   - `detect_muscle_group_gaps(user, days=14)` → missing muscle groups

5. **Create `apps/health/services/glucose_analytics.py`**
   - `calculate_time_in_range(user, days=7)` → percentage
   - `calculate_glucose_variability(user, days=7)` → CV%
   - `calculate_fasting_glucose_trend(user, days=30)` → direction + rate
   - `detect_postmeal_spikes(user, days=7)` → list of spike events

**Database changes:** 1 new model (RecoveryMetrics), 1 migration

### Step 3 — Weekly Health Report (Week 3)

**Objective:** Pre-computed weekly summaries for CoS narrative generation.

**Tasks:**
1. **Create `WeeklyHealthReport` model** (as designed in Section 4)
   - Files: `apps/health/models.py`, new migration

2. **Create `apps/health/services/weekly_report_service.py`**
   - `generate_weekly_report(user, week_start)` → populates all fields
   - `generate_narrative(user, report)` → AI-generated summary using OpenAI
   - `identify_top_insights(user, report)` → top 3 insights
   - `generate_action_items(user, report)` → top 3 recommendations

3. **Create management command:** `python manage.py generate_weekly_reports`
   - Runs Monday morning, generates reports for prior week

4. **Add fields to `BodyCompositionEntry`** for InBody data
   - `skeletal_muscle_mass_lbs`, `segmental_lean` (JSON), `phase_angle`, `ecw_icw_ratio`, `basal_metabolic_rate`

**Database changes:** 1 new model (WeeklyHealthReport), 1 migration, field additions to BodyCompositionEntry

### Step 4 — Health Command Center Dashboard (Week 4-5)

**Objective:** Build the unified dashboard view.

**Tasks:**
1. **Create view:** `apps/health/views_command_center.py`
   - `HealthCommandCenterView` — aggregates all section data
   - URL: `/health/command-center/`

2. **Create template:** `templates/health/command_center.html`
   - 8-section layout as designed in Section 5
   - Chart.js for all visualizations
   - Responsive: mobile-first with grid layout
   - CSP-compliant (nonce-based scripts)

3. **Create API endpoints for dynamic data:**
   - `GET /health/api/command-center/summary/` — today's DailyHealthSummary
   - `GET /health/api/command-center/trends/?days=14` — trend data for charts
   - `GET /health/api/command-center/recovery/` — today's recovery score
   - `GET /health/api/command-center/insights/` — top active insights

4. **Create chart data formatters:**
   - Weight trend chart (12 weeks)
   - Sleep stages chart (14 days, stacked)
   - Workout frequency chart (8 weeks, bar)
   - Steps chart (14 days, bar)
   - Glucose chart (24h or 7d, line with range bands)
   - Macro chart (7 days, grouped bar)
   - HRV chart (14 days, line with baseline band)
   - Adherence chart (30 days, heatmap)

5. **Add navigation:** Link from main dashboard, health landing page, and sidebar

**Database changes:** None (reads from existing models + new summaries)

### Step 5 — CoS Intelligence Enhancement (Week 5-6)

**Objective:** Give the CoS deep health pattern detection capabilities.

**Tasks:**
1. **Enhance `apps/ai/dashboard_ai.py`**
   - Replace individual metric queries with `DailyHealthSummary` reads
   - Add 7-day and 30-day trend data to CoS context
   - Add recovery score and weekly report narrative
   - Add cross-domain correlation data

2. **Create `apps/ai/health_intelligence.py`** (NEW)
   - `detect_weight_patterns(user)` → plateau, too-fast, rebound, lean mass loss
   - `detect_sleep_patterns(user)` → debt, inconsistency, quality decline
   - `detect_nutrition_patterns(user)` → protein gap, weekend drop, calorie creep
   - `detect_workout_patterns(user)` → declining frequency, volume stagnation, imbalance
   - `detect_glucose_patterns(user)` → rising fasting, post-meal spikes
   - `detect_cross_domain_correlations(user)` → sleep↔glucose, stress↔weight, etc.
   - Each returns structured insights the CoS can narrate

3. **Enhance executive briefing** (`apps/ai/executive_briefing.py`)
   - Add recovery status to morning briefing
   - Add weekly report highlights
   - Add top health insight of the day
   - Add upcoming health actions (workout scheduled, low supply meds)

4. **Add health intelligence intents:**
   - `get_health_summary` → "How am I doing?"
   - `get_recovery_status` → "Am I recovered?"
   - `get_weight_trend` → "How's my weight loss going?"
   - `get_sleep_report` → "How's my sleep been?"
   - Register via standard 7-point intent registration checklist

5. **Enhance system prompts** with health reasoning examples

**Database changes:** None (reads from computed models)

### Step 6 — InBody & Advanced Integrations (Week 6-7)

**Objective:** Close remaining data gaps.

**Tasks:**
1. **InBody scan result parser**
   - `apps/health/services/inbody_parser.py`
   - Accepts: photo (OCR via OpenAI Vision), manual entry via CoS, CSV import
   - Outputs: `BodyCompositionEntry` with segmental data

2. **CoS InBody intent**
   - `log_inbody_results(weight, body_fat_pct, skeletal_muscle_mass, ...)`
   - Natural language: "Log my InBody: weight 235, body fat 28.5%, muscle mass 98 lbs"

3. **Post-meal glucose response analysis**
   - Match `GlucoseEntry` (within 30-120 min after meal) to `FoodEntry`
   - Calculate: peak glucose, time to peak, area under curve
   - Identify which meals cause the biggest spikes

4. **Protein timing analysis**
   - Match `FoodEntry.logged_time` to `WorkoutSession.completed_at`
   - Check: was protein consumed within 2h of workout completion?

5. **Caffeine-sleep correlation engine**
   - Match `SleepEntry.caffeine_mg` to that night's sleep quality
   - Build personal caffeine sensitivity profile

**Database changes:** Field additions to BodyCompositionEntry (from Step 3)

### Summary Timeline

| Step | Duration | Dependencies | Key Deliverable |
|------|----------|-------------|-----------------|
| 1. Foundation | Week 1-2 | None | DailyHealthSummary + analytics service |
| 2. Recovery & Scoring | Week 2-3 | Step 1 | Recovery score + health score |
| 3. Weekly Report | Week 3 | Steps 1-2 | AI-generated weekly health report |
| 4. Dashboard | Week 4-5 | Steps 1-3 | Health Command Center UI |
| 5. CoS Intelligence | Week 5-6 | Steps 1-3 | Pattern detection + enhanced briefings |
| 6. Advanced Integrations | Week 6-7 | Steps 1-2 | InBody, glucose response, correlations |

### Database Migration Summary

| Migration | Models Added | Fields Added |
|-----------|-------------|-------------|
| 1 | `DailyHealthSummary` | ~35 fields |
| 2 | `RecoveryMetrics` | ~12 fields |
| 3 | `WeeklyHealthReport` | ~25 fields |
| 4 | — | 5 fields on `BodyCompositionEntry` |

### New Files Summary

| File | Purpose |
|------|---------|
| `apps/health/services/daily_summary_service.py` | Daily health aggregation |
| `apps/health/services/health_analytics_service.py` | Trend calculations |
| `apps/health/services/recovery_service.py` | Recovery scoring |
| `apps/health/services/health_score_service.py` | Weekly health score |
| `apps/health/services/fitness_analytics.py` | Training load, progressive overload |
| `apps/health/services/glucose_analytics.py` | Time-in-range, variability, spikes |
| `apps/health/services/weekly_report_service.py` | Weekly report generation |
| `apps/health/services/inbody_parser.py` | InBody result parsing |
| `apps/health/views_command_center.py` | Health Command Center view |
| `templates/health/command_center.html` | Dashboard template |
| `apps/ai/health_intelligence.py` | CoS pattern detection |
| `apps/health/management/commands/compute_health_summaries.py` | Backfill command |
| `apps/health/management/commands/generate_weekly_reports.py` | Weekly report command |

---

## Conclusion

WLJ's health data collection is **remarkably comprehensive** — 55+ models capturing 37+ HealthKit metric types, Dexcom CGM integration, full nutrition tracking, medication adherence, and detailed fitness logging.

**The gap is not in data capture — it's in data synthesis.**

The system captures extensive health data across 15+ domains but analyzes each in isolation. No single view correlates weight trends with sleep quality, nutrition consistency, workout load, and glucose patterns.

The Health Command Center dashboard + enhanced CoS intelligence layer transforms WLJ from a **health data recorder** into a **personal health intelligence platform** that can answer: "What is actually driving my results, and what should I do differently?"

The implementation follows a bottom-up approach:
1. **Aggregate** (DailyHealthSummary)
2. **Compute** (Recovery, scores, analytics)
3. **Visualize** (Command Center dashboard)
4. **Reason** (CoS intelligence with pattern detection)
5. **Advise** (Actionable, personalized recommendations)

Each step builds on the previous one, with early steps deliverable in 1-2 weeks and the full system operational within 6-7 weeks.
