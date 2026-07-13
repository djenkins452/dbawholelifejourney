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
| Waist | `.waistCircumference` | BodyCompositionEntry(waist) | Send `type:"waist"`, `value`, `unit` ("in"/"cm"); powers Body Intelligence |
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

### One-time historical timestamp recovery (weight / body_fat / lean_body_mass)

Body-composition samples synced before 2026-07-06 were stored at **12:00 PM** (a
server-side noon default that discarded the real sample time — since fixed). The true
sample times were never retained by WLJ (`HealthIngestionRun` logs metadata only; `date`
was reduced to a calendar day on ingest), so they are **not recoverable server-side** —
but they live permanently in Apple Health. The backend now **self-heals** a stored noon
row to the real sample time whenever Apple Health re-sends the sample, matched by the
stable HealthKit UUID `sync_id` (or by date for pre-UUID rows, backfilling the UUID). No
timestamps are fabricated and no duplicate rows are created (verified by
`apps/mobile/tests/test_weight_timestamp.py`).

Repair is a **user-triggered product capability** (no per-repair Xcode change). The user
taps **"Re-import from Apple Health"** on the Weight page → the server records a
`HealthReimportRequest`. The native app fulfils it via the **sync-status directive** it
already polls:

**1. Read the directive** — `GET /api/mobile/health/sync-status/` now returns:

```jsonc
"reimport": {                       // null when nothing is pending
  "request_id": 42,
  "metrics": ["weight", "body_fat", "lean_body_mass"],
  "since": null,                    // ISO date, or null = full history
  "status": "in_progress"
}
```

**2. Fulfil it** — when `reimport` is non-null, run a ONE-TIME full-history query for the
listed metrics and POST each sample to the normal `/health/ingest/` (the server self-heals
noon rows in place by `sync_id`):

```swift
let startDate = reimport.since ?? accountCreationDate   // full history when since == nil
// HKSampleQuery for .bodyMass / .bodyFatPercentage / .leanBodyMass over [startDate, now]
// POST each: date = sample.startDate (ISO8601), sync_id = "weight-\(sample.uuid)"
```

**3. Report completion** — `POST /api/mobile/health/reimport/complete/` with
`{request_id, scanned, created, updated, skipped, failed}`. The Weight page then shows the
outcome. After fulfilling, resume the normal 7-day window.

Truth comes from Apple Health, never a fabricated time. Safe to run repeatedly (a new
request supersedes any pending one; ingest dedups by `sync_id`/date). BMI is date-only by
design (`BodyCompositionEntry.measurement_date`) and is unaffected.

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

## The HealthKit read-authorization trap (why a source can look "enabled" but send nothing)

WLJ requests **read-only** access (`requestAuthorization(toShare: [], read: …)`).
Apple **deliberately never reveals read-authorization status** (privacy):
`authorizationStatus(for:)` reflects only *write/share* permission — which this app
never requests. So the app **cannot know** whether a specific type's *read* was
granted. If the user leaves a per-type toggle off (e.g. **Steps**) in the Health
permission sheet, the corresponding query (`HKStatisticsCollectionQuery` etc.)
returns **zero samples with no error** — nothing is sent, nothing persists, and
the app has no local way to detect it.

**Consequences fixed (2026-07-13):**
- `HealthKitManager.isAuthorized` used to check `.sharingAuthorized` (write) — always
  false for a read-only app, so it under-reported "connected" on relaunch and stopped
  background delivery from re-enabling. It now persists "user completed the auth
  request" (`wlj.healthkit.connected`) — the only honest signal we own.
- The Health Sync page no longer *claims* per-type authorization it cannot verify.

## Health Sync Status — deterministic per-type truth (the platform source)

Because read-authorization is unknowable, the **only** trustworthy signal that a
source is healthy is **whether records actually reached the backend**. That truth
is computed by **`apps/health/services/health_sync_status.py ::
build_health_sync_status(user)`** — the single canonical source for the Health Sync
page *and* any future Health Operations / diagnostic view. It returns, per data type:
last record instant, recent/total counts, status (`healthy` / `idle` / `stale` /
`no_data`), plus account-level `issues`, `newest_data`, `oldest_active_source`, and
a human `last_sync_summary` (imported / no-change / failed).

- Per-type sync results are persisted on each run (`HealthIngestionRun.metric_type_results`,
  populated in `mobile/views.health_ingest`).
- Exposed additively on `GET /api/mobile/health/sync-status/` under `sync_health`.
- The iOS `HealthSyncView` renders entirely from this — answering "Did it sync? What
  synced? What didn't? Is anything broken? What next?". A source that shows
  **"No records received"** (e.g. Steps) is the real, actionable signal → the user
  enables it under Apple Health → Sharing. Add a new tracked type by adding one row
  to `HEALTH_SYNC_TYPES`.

## Steps pipeline glass-box (temporary diagnostic)

To prove *exactly* where Steps disappear (Apple Health → device query → payload →
Django → DB), the sync carries deterministic telemetry:

- **Device** (`HealthKitManager.fetchSteps`) counts **raw step samples**
  (`HKSampleQuery`) alongside the daily-total (`HKStatisticsCollectionQuery`)
  result and records `lastStepsDebug = {raw_samples, built, sent}`, sent to the
  server as `client_debug` in the ingest payload (also `print`ed with tag
  `[STEPS_GLASSBOX]`).
- **Server** stores it (`HealthIngestionRun.client_debug`), logs
  `[STEPS_GLASSBOX]`, and `health_sync_status.steps_pipeline_diagnostics(user)`
  compares device-reported vs. server-received (`metric_type_results`) vs.
  persisted (`StepsEntry`) across the sync session's batches and returns a
  deterministic **verdict + stage**: `healthkit_returned_zero`, `aggregation_zero`,
  `not_received`, `server_rejected`, `not_persisted`, or `healthy`.
- Exposed at `sync_health.diagnostics.steps`; the Health Sync page shows a
  **Steps Diagnostics** section. **Remove this telemetry once the root cause is
  fixed** (it is intentionally temporary).

## Key Files

| File | Purpose |
|------|---------|
| `ios/.../Services/HealthKitManager.swift` | HK authorization, data queries, sync orchestration |
| `ios/.../Models/HealthMetric.swift` | Data model for metrics sent to API |
| `ios/.../Models/HealthSyncStatus.swift` | Decodes the deterministic per-type sync truth |
| `ios/.../Views/HealthSyncView.swift` | Redesigned trust-focused Health Sync page |
| `apps/mobile/views.py` | Ingest endpoint (+ per-type results) & sync-status endpoint |
| `apps/health/services/health_sync_status.py` | **Canonical** per-type Health Sync truth |
| `apps/mobile/models.py` | `HealthIngestionRun` audit + `metric_type_results` |

---

*Last updated: 2026-07-13 (Health Sync redesign: deterministic per-type truth; read-auth trap fix)*
