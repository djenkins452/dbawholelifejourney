# iOS App Reference (Claude Code)

**Location:** `ios/WLJWrapper/`

Native iOS wrapper that loads WLJ in a WKWebView with HealthKit integration for App Store approval.

## Key Components

- `WLJWrapper.xcodeproj` - Xcode project (open to build/run)
- `WLJWrapper/Views/MainWebView.swift` - WKWebView with domain allowlist + JS bridge
- `WLJWrapper/Views/SettingsView.swift` - Native settings (required for App Store)
- `WLJWrapper/Views/HealthSyncView.swift` - HealthKit authorization + sync
- `WLJWrapper/Services/HealthKitManager.swift` - HealthKit queries (steps, weight, sleep, HR)
- `WLJWrapper/Services/KeychainManager.swift` - Secure token storage
- `WLJWrapper/Services/APIClient.swift` - HTTP client for mobile API

## Django Backend: `apps/mobile/`

- Bearer token authentication (not session-based)
- Token exchange flow: web session → one-time code → API token
- Health data ingestion endpoint with audit logging
- Device registration and management

## Mobile API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /api/mobile/generate-code/` | Get one-time exchange code (from web session) |
| `POST /api/mobile/token/exchange/` | Exchange code for Bearer token |
| `POST /api/mobile/health/ingest/` | Submit HealthKit data |
| `GET /api/mobile/health/sync-status/` | Check last sync status |
| `POST /api/mobile/push/register/` | Register APNs push token for device |
| `POST /api/mobile/push/unregister/` | Unregister push token for device |

**Token Authentication:**
```
Authorization: Bearer <token>
```
All mobile API endpoints require Bearer token auth (added via `MobileAuthenticationMiddleware`).

## HealthKit Data Synced (23 types)

- Steps, Active Calories, Distance, Resting Calories, Flights Climbed, Exercise Minutes, Stand Hours → `StepsEntry`
- Weight, Body Fat %, Lean Body Mass → `WeightEntry`
- Sleep, Heart Rate, Respiratory Rate, HRV, VO2 Max, Caffeine, Mindful Minutes → `SleepEntry`
- Blood Glucose → `BloodGlucoseReading`
- Blood Oxygen → stored as note
- Water Intake → `WaterEntry`
- Workouts → `WorkoutSession`
- Blood Pressure → `BloodPressureEntry`
- Body Temperature → `BodyTemperatureEntry`

## Testing iOS Locally

1. Open `ios/WLJWrapper/WLJWrapper.xcodeproj` in Xcode
2. Configure signing (your Apple Developer team)
3. Connect iPhone, enable Developer Mode
4. Build and run (Cmd+R)

## App Store Submission

See `docs/ios-app-store-submission.md` for complete guide including:
- Apple Developer Portal setup
- Privacy nutrition label answers
- HealthKit justification text
- WKWebView defense (why it's not "just a website")
