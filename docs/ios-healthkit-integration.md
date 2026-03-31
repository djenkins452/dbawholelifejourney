# HealthKit Integration Guide

Technical documentation for the WLJ iOS HealthKit integration.

## Overview

The WLJ iOS app reads health data from Apple Health and syncs it to the Django backend. This provides users with automatic tracking without manual data entry. The integration currently covers **38+ HealthKit data types** across 7 categories.

## Data Types Synced

### Activity & Movement

| Type | HealthKit Identifier | WLJ Model | Notes |
|------|---------------------|-----------|-------|
| Steps | `.stepCount` | StepsEntry | Daily totals |
| Active Calories | `.activeEnergyBurned` | StepsEntry.calories_burned | Daily totals |
| Resting Calories | `.basalEnergyBurned` | StepsEntry.resting_calories | Daily totals |
| Distance | `.distanceWalkingRunning` | StepsEntry.distance_miles | Daily totals |
| Flights Climbed | `.flightsClimbed` | StepsEntry.flights_climbed | Daily totals |
| Exercise Minutes | `.appleExerciseTime` | StepsEntry.exercise_minutes | Daily totals |
| Stand Hours | `.appleStandTime` | StepsEntry.stand_hours | Daily totals |
| Workouts | `.workoutType()` | WorkoutSession | Individual sessions (40+ types) |

### Body Measurements

| Type | HealthKit Identifier | WLJ Model | Notes |
|------|---------------------|-----------|-------|
| Weight | `.bodyMass` | WeightEntry | Most recent per day |
| Body Fat % | `.bodyFatPercentage` | WeightEntry.body_fat_percentage + BodyCompositionEntry | Most recent per day |
| Lean Body Mass | `.leanBodyMass` | WeightEntry.lean_body_mass + BodyCompositionEntry | In pounds |
| BMI | `.bodyMassIndex` | BodyCompositionEntry(bmi) | Most recent per day |
| Fat Mass | *computed* | BodyCompositionEntry(fat_mass) | weight × body_fat_pct / 100 |
| BMR | `.basalEnergyBurned` | BodyCompositionEntry(bmr) | Mirrored from StepsEntry.resting_calories |

### Sleep & Recovery

| Type | HealthKit Identifier | WLJ Model | Notes |
|------|---------------------|-----------|-------|
| Sleep Analysis | `.sleepAnalysis` | SleepEntry | Sessions with stages (deep/REM/light/awake) |
| HRV | `.heartRateVariabilitySDNN` | SleepEntry.hrv_value | Daily average (ms) |
| VO2 Max | `.vo2Max` | SleepEntry.vo2_max | Most recent per day (mL/kg/min) |
| Respiratory Rate | `.respiratoryRate` | SleepEntry.respiratory_rate | Daily average |
| Caffeine | `.dietaryCaffeine` | SleepEntry.caffeine_mg | Daily total |
| Mindful Minutes | `.mindfulSession` | SleepEntry.mindful_minutes | Daily total |

### Heart & Vitals

| Type | HealthKit Identifier | WLJ Model | Notes |
|------|---------------------|-----------|-------|
| Resting Heart Rate | `.restingHeartRate` | SleepEntry (HR fields) | Most recent per day |
| Blood Pressure (Systolic) | `.bloodPressureSystolic` | BloodPressureEntry | Matched with diastolic (±60s) |
| Blood Pressure (Diastolic) | `.bloodPressureDiastolic` | BloodPressureEntry | Matched with systolic (±60s) |
| Blood Oxygen (SpO2) | `.oxygenSaturation` | BloodOxygenEntry | Individual readings |
| Body Temperature | `.bodyTemperature` | BodyTemperatureEntry | Individual readings (°F) |
| Blood Glucose | `.bloodGlucose` | GlucoseEntry | High-volume CGM optimized |

### Hydration

| Type | HealthKit Identifier | WLJ Model | Notes |
|------|---------------------|-----------|-------|
| Water Intake | `.dietaryWater` | WaterEntry | Daily totals (fl oz) |

### Mobility & Gait (NEW)

| Type | HealthKit Identifier | WLJ Model | Notes |
|------|---------------------|-----------|-------|
| Walking Asymmetry | `.walkingAsymmetryPercentage` | MobilityEntry | Daily average (%) |
| Walking Steadiness | `.appleWalkingSteadiness` | MobilityEntry | Classification + score (iOS 15+) |
| Walking Speed | `.walkingSpeed` | MobilityEntry | Daily average (mph) |
| Step Length | `.walkingStepLength` | MobilityEntry | Daily average (inches) |
| Double Support Time | `.walkingDoubleSupportPercentage` | MobilityEntry | Balance indicator (%) |
| Stair Ascent Speed | `.stairAscentSpeed` | MobilityEntry | Flights per minute |
| Stair Descent Speed | `.stairDescentSpeed` | MobilityEntry | Flights per minute |
| Six Min Walk Distance | `.sixMinuteWalkTestDistance` | MobilityEntry | Estimated (meters) |

### Heart Rate Events (NEW)

| Type | HealthKit Identifier | WLJ Model | Notes |
|------|---------------------|-----------|-------|
| High Heart Rate Alert | `.highHeartRateEvent` | HeartRateEventEntry | Event-based, not daily |
| Low Heart Rate Alert | `.lowHeartRateEvent` | HeartRateEventEntry | Event-based, not daily |
| Irregular Rhythm (AFib) | `.irregularHeartRhythmEvent` | HeartRateEventEntry | Event-based, not daily |

### Audio Exposure (NEW)

| Type | HealthKit Identifier | WLJ Model | Notes |
|------|---------------------|-----------|-------|
| Headphone Audio Level | `.headphoneAudioExposure` | AudioExposureEntry | Daily avg (dB) + duration |
| Environmental Audio | `.environmentalAudioExposure` | AudioExposureEntry | Daily average (dB) |

### Dietary Nutrients (NEW)

| Type | HealthKit Identifier | WLJ Model | Notes |
|------|---------------------|-----------|-------|
| Calories | `.dietaryEnergyConsumed` | DietaryNutrientEntry | Daily total (kcal) |
| Protein | `.dietaryProtein` | DietaryNutrientEntry | Daily total (g) |
| Carbohydrates | `.dietaryCarbohydrates` | DietaryNutrientEntry | Daily total (g) |
| Fat | `.dietaryFatTotal` | DietaryNutrientEntry | Daily total (g) |
| Fiber | `.dietaryFiber` | DietaryNutrientEntry | Daily total (g) |
| Sugar | `.dietarySugar` | DietaryNutrientEntry | Daily total (g) |
| Sodium | `.dietarySodium` | DietaryNutrientEntry | Daily total (mg) |
| Cholesterol | `.dietaryCholesterol` | DietaryNutrientEntry | Daily total (mg) |
| Saturated Fat | `.dietaryFatSaturated` | DietaryNutrientEntry | Daily total (g) |
| Potassium | `.dietaryPotassium` | DietaryNutrientEntry | Daily total (mg) |
| Calcium | `.dietaryCalcium` | DietaryNutrientEntry | Daily total (mg) |
| Iron | `.dietaryIron` | DietaryNutrientEntry | Daily total (mg) |
| Vitamin D | `.dietaryVitaminD` | DietaryNutrientEntry | Daily total (mcg) |

## Authorization Flow

### 1. Request Permission

```swift
// In HealthKitManager.swift
func requestAuthorization() async throws {
    try await healthStore.requestAuthorization(
        toShare: [],  // We only read, never write
        read: readTypes
    )
}
```

### 2. Check Status

```swift
var isAuthorized: Bool {
    let status = healthStore.authorizationStatus(for: stepType)
    return status == .sharingAuthorized
}
```

### 3. User Sees iOS Permission Sheet

iOS shows native permission dialog. User can:
- Allow all types
- Allow some types
- Deny all

**Important:** We cannot programmatically check which specific types were authorized. iOS returns `.sharingDenied` for both "denied" and "not yet asked".

## Data Query Strategy

### Date Range

By default, we query the last 7 days:

```swift
let endDate = Date()
let startDate = calendar.date(byAdding: .day, value: -7, to: endDate)!
```

### Query Patterns

- **Daily aggregates** (steps, calories, water, nutrients): `HKStatisticsCollectionQuery` with `.cumulativeSum`
- **Individual samples** (weight, SpO2, glucose): `HKSampleQuery` — most recent per day or all readings
- **Event-based** (HR events, sleep stages): `HKSampleQuery` — all events in range
- **Mobility averages** (gait, speed, asymmetry): `HKSampleQuery` — averaged per day

### Deduplication

Each metric includes a `sync_id` to prevent duplicates:
- Steps: `steps-{date}` (one per day)
- Weight: `weight-{uuid}` (HealthKit sample UUID)
- Sleep: `sleep-{date}` (one per night)
- Heart Rate: `hr-{date}` (one per day)
- Glucose: `glucose-{uuid}` (per reading, pre-fetched sync_id cache for CGM)
- Mobility: `walkasym-{date}`, `walkspeed-{date}`, etc. (one per day)
- HR Events: `{event_type}-{timestamp}` (per event)
- Audio: `headphone-{date}`, `envaud-{date}` (one per day)
- Nutrients: `nutrients-{date}` (one per day)

Django uses `sync_id` to update existing records instead of creating duplicates.

### High-Volume Optimization (Blood Glucose)

CGM data (Dexcom) generates ~2000+ readings per week. The ingest endpoint pre-fetches all existing sync_ids in one query to avoid N+1 DB lookups:

```python
existing_glucose_sync_ids = set(
    GlucoseEntry.objects.filter(
        user=user, sync_id__in=glucose_sync_ids,
    ).values_list("sync_id", flat=True)
)
```

## API Payload Format

```json
{
    "client_timestamp": "2024-01-15T10:30:00Z",
    "metrics": [
        {
            "type": "steps",
            "date": "2024-01-15",
            "value": 8500,
            "source": "apple_health",
            "sync_id": "steps-2024-01-15"
        },
        {
            "type": "walking_speed",
            "date": "2024-01-15",
            "walking_speed_value": 3.2,
            "source": "apple_health",
            "sync_id": "walkspeed-2024-01-15"
        },
        {
            "type": "high_heart_rate_event",
            "date": "2024-01-15",
            "recorded_at": "2024-01-15T14:30:00Z",
            "heart_rate_value": 150,
            "source": "apple_health",
            "sync_id": "high_heart_rate_event-1705329000"
        },
        {
            "type": "dietary_nutrients",
            "date": "2024-01-15",
            "calories": 2100,
            "protein_g": 120,
            "carbohydrates_g": 250,
            "fat_g": 70,
            "source": "apple_health",
            "sync_id": "nutrients-2024-01-15"
        }
    ]
}
```

**Limits:**
- Payload size: 1 MB max
- Metrics per request: 5,000 max
- Batching: iOS client sends up to 500 metrics per request, auto-splits for larger syncs

## Django Models (New in v2)

### MobilityEntry
One record per date. All mobility/gait fields are nullable — only populated fields are stored. Strong predictors of overall health decline, injury risk, and neurological conditions.

### HeartRateEventEntry
Event-based (not daily). Each record = one Apple Watch alert. Clinically significant: AFib detection, abnormal HR thresholds.

### AudioExposureEntry
One record per date. Headphone + environmental audio levels. WHO guidelines: sustained >80 dB causes hearing damage.

### DietaryNutrientEntry
One record per date. Captures macros/micros from food-logging apps (MyFitnessPal, Cronometer, etc.) that sync through Apple Health. Separate from WLJ's own nutrition tracking.

## Error Handling

All queries use async/await with proper error propagation. Individual type failures don't block other types from syncing.

## Privacy Considerations

1. **Read-only access**: We never write to HealthKit
2. **User controls all permissions**: Can be revoked in iOS Settings
3. **Data stays on device** until user explicitly syncs
4. **Secure transmission**: HTTPS only, Bearer token auth
5. **Audit logging**: All ingestion runs logged server-side with HealthIngestionRun

## Key Files

| File | Purpose |
|------|---------|
| `ios/.../Services/HealthKitManager.swift` | HK authorization, data queries, sync orchestration |
| `ios/.../Models/HealthMetric.swift` | Data model for metrics sent to API |
| `apps/mobile/views.py` | Ingest endpoint + 37 metric handlers |
| `apps/health/models.py` | Django models (StepsEntry, MobilityEntry, etc.) |
| `apps/mobile/models.py` | HealthIngestionRun audit model |

---

*Last updated: 2026-02-21*
