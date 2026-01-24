# HealthKit Integration Guide

Technical documentation for the WLJ iOS HealthKit integration.

## Overview

The WLJ iOS app reads health data from Apple Health and syncs it to the Django backend. This provides users with automatic tracking without manual data entry.

## Data Types Synced

| Type | HealthKit Identifier | WLJ Model | Notes |
|------|---------------------|-----------|-------|
| Steps | `HKQuantityType.stepCount` | StepsEntry | Daily totals |
| Weight | `HKQuantityType.bodyMass` | WeightEntry | Most recent per day |
| Sleep | `HKCategoryType.sleepAnalysis` | SleepEntry | Sessions with stages |
| Heart Rate | `HKQuantityType.restingHeartRate` | SleepEntry (HR fields) | Resting HR only |

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

### Deduplication

Each metric includes a `sync_id` to prevent duplicates:
- Steps: `steps-{date}` (one per day)
- Weight: `weight-{uuid}` (HealthKit sample UUID)
- Sleep: `sleep-{date}` (one per night)
- Heart Rate: `hr-{date}` (one per day)

Django uses `sync_id` to update existing records instead of creating duplicates.

## Steps Query

Uses `HKStatisticsCollectionQuery` for daily totals:

```swift
let query = HKStatisticsCollectionQuery(
    quantityType: stepType,
    quantitySamplePredicate: predicate,
    options: .cumulativeSum,
    anchorDate: startOfDay,
    intervalComponents: DateComponents(day: 1)
)
```

This automatically sums steps from all sources (iPhone, Apple Watch, etc.).

## Weight Query

Uses `HKSampleQuery` to get individual measurements:

```swift
let query = HKSampleQuery(
    sampleType: weightType,
    predicate: predicate,
    limit: HKObjectQueryNoLimit,
    sortDescriptors: [sortByDate]
)
```

We take only the most recent measurement per day.

## Sleep Query

Sleep data is complex because HealthKit stores individual sleep stages:

```swift
// HKCategoryValueSleepAnalysis values:
// - awake: Time awake during sleep session
// - asleepREM: REM sleep
// - asleepCore: Light/Core sleep
// - asleepDeep: Deep sleep
// - inBed: In bed but not necessarily asleep
```

We aggregate stages into a single session per night, tracking:
- Total duration
- Deep sleep minutes
- REM sleep minutes
- Light sleep minutes
- Awake minutes
- Bedtime (earliest sample start)
- Wake time (latest sample end)

## Heart Rate Query

We query `restingHeartRate` which Apple Watch calculates:

```swift
let query = HKSampleQuery(
    sampleType: restingHRType,
    predicate: predicate,
    limit: HKObjectQueryNoLimit,
    sortDescriptors: [sortByDate]
)
```

Resting HR is updated once per day by Apple Watch.

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
            "type": "weight",
            "date": "2024-01-15",
            "value": 175.5,
            "unit": "lb",
            "source": "apple_health",
            "sync_id": "weight-ABC123-UUID"
        },
        {
            "type": "sleep",
            "date": "2024-01-15",
            "total_minutes": 480,
            "deep_minutes": 90,
            "rem_minutes": 120,
            "light_minutes": 240,
            "awake_minutes": 30,
            "bedtime": "2024-01-14T23:00:00Z",
            "wake_time": "2024-01-15T07:00:00Z",
            "source": "apple_health",
            "sync_id": "sleep-2024-01-15"
        },
        {
            "type": "heart_rate",
            "date": "2024-01-15",
            "resting_hr": 62,
            "source": "apple_health",
            "sync_id": "hr-2024-01-15"
        }
    ]
}
```

## Error Handling

### Authorization Denied

```swift
if case HealthKitError.notAvailable = error {
    // Show alert: "HealthKit not available on this device"
}
```

### Query Failures

All queries use async/await with proper error propagation:

```swift
do {
    let steps = try await fetchSteps(from: startDate, to: endDate)
} catch {
    // Log error but continue with other data types
}
```

### Network Errors

API client handles:
- 401: Token expired, prompt re-login
- 413: Payload too large (shouldn't happen with 7-day window)
- Network errors: Show retry option

## Testing

### Simulator Limitations

HealthKit is **not available** in the iOS Simulator. You must test on a physical device.

### Test Data

To add test data:
1. Open Apple Health app on iPhone
2. Browse → Steps → Add Data
3. Enter test values
4. Run sync in WLJ app

### Debug Logging

In development builds, all HealthKit operations log to Xcode console:

```swift
#if DEBUG
print("Fetched \(steps.count) step entries")
#endif
```

## Privacy Considerations

1. **Read-only access**: We never write to HealthKit
2. **User controls all permissions**: Can be revoked in iOS Settings
3. **Data stays on device** until user explicitly syncs
4. **Secure transmission**: HTTPS only, Bearer token auth
5. **Audit logging**: All ingestion runs logged server-side

## Future Enhancements

### Background Sync (Scaffolded)

The app includes placeholder for `BGAppRefreshTask`:

```swift
// In Info.plist:
// UIBackgroundModes = ["fetch"]

// Future implementation:
// - Register background task in app delegate
// - Request background refresh time from system
// - Sync when woken up in background
```

### Additional Data Types

Easy to add new types:
1. Add `HKQuantityType` to `readTypes`
2. Implement fetch function
3. Create `HealthMetric` initializer
4. Add handler in Django views

Candidates:
- Active calories
- Workout sessions
- Blood pressure
- Blood glucose (already have Dexcom integration)
