# iOS Wrapper Setup Guide

Complete guide to set up, build, and run the WLJ iOS app.

## Prerequisites

- Mac with macOS 13+ (Ventura or later)
- Xcode 15+ installed from Mac App Store
- Apple Developer account (already have)
- Physical iPhone for testing HealthKit (simulator doesn't support HealthKit)

## Project Structure

```
ios/WLJWrapper/
├── WLJWrapper.xcodeproj/          # Xcode project file
├── WLJWrapper/
│   ├── App/
│   │   └── WLJWrapperApp.swift    # App entry point
│   ├── Views/
│   │   ├── ContentView.swift      # Main view container
│   │   ├── MainWebView.swift      # WKWebView wrapper
│   │   ├── SettingsView.swift     # Native settings screen
│   │   └── HealthSyncView.swift   # Health sync controls
│   ├── Services/
│   │   ├── KeychainManager.swift  # Secure token storage
│   │   ├── APIClient.swift        # HTTP client for backend
│   │   └── HealthKitManager.swift # HealthKit queries
│   ├── Models/
│   │   └── HealthMetric.swift     # Health data models
│   ├── Resources/
│   │   ├── Assets.xcassets/       # App icons, colors
│   │   └── Info.plist             # App configuration
│   └── WLJWrapper.entitlements    # HealthKit entitlements
```

## Step 1: Open Project in Xcode

1. Open Finder and navigate to the `ios/WLJWrapper/` folder
2. Double-click `WLJWrapper.xcodeproj` to open in Xcode
3. Wait for Xcode to index the project (may take a minute)

## Step 2: Configure Signing

1. In Xcode, select the **WLJWrapper** project in the left sidebar
2. Select the **WLJWrapper** target
3. Go to **Signing & Capabilities** tab
4. Check "Automatically manage signing"
5. Select your Team from the dropdown
   - If not listed, add your Apple Developer account: Xcode → Settings → Accounts → Add
6. Bundle Identifier should be: `com.wholelifejourney.app`
   - If taken, change to something unique like `com.yourname.wholelifejourney`

## Step 3: Add HealthKit Capability

Xcode should already have this configured, but verify:

1. In **Signing & Capabilities** tab
2. Check that "HealthKit" capability is listed
3. If not, click **+ Capability** and add "HealthKit"

## Step 4: Register Device for Testing

To test on a physical iPhone:

1. Connect your iPhone via USB
2. On iPhone: Settings → Privacy & Security → Developer Mode → Enable
3. Trust the computer when prompted
4. In Xcode, select your iPhone from the device dropdown (top of window)

## Step 5: Build and Run

1. Select your iPhone in the device selector
2. Press **Cmd+R** or click the Play button
3. Wait for build to complete
4. App will install and launch on iPhone

### First Run

1. App opens with WLJ web view
2. Log in to your WLJ account
3. Tap the gear icon (bottom right) to open native Settings
4. Go to **Health Data Sync** → **Authorize HealthKit**
5. Grant permissions in the iOS Health prompt
6. Tap **Sync Now** to sync health data

## Troubleshooting

### "Unable to install WLJWrapper"

- Ensure Developer Mode is enabled on iPhone
- Try: Product → Clean Build Folder (Cmd+Shift+K) then rebuild

### "Signing certificate not found"

- Open Keychain Access and delete any expired Apple certificates
- In Xcode: Preferences → Accounts → Download Manual Profiles

### HealthKit "not available"

- HealthKit only works on physical devices, not simulators
- Ensure you're testing on a real iPhone

### WebView shows blank

- Check your internet connection
- Verify wholelifejourney.com is accessible in Safari
- Check Xcode console for errors

### "Code signing error"

1. Xcode → Preferences → Accounts
2. Select your team → Manage Certificates
3. Click + → Apple Development
4. Try building again

## Running Without Developer Account

For testing only (not for App Store):

1. Use your personal Apple ID in Xcode
2. Apps expire after 7 days
3. Re-install when expired by building again

## Debug Mode

In debug builds, you can inspect the WebView:

1. Run the app from Xcode
2. In Safari on Mac: Develop → [Your iPhone] → wholelifejourney.com
3. Use Safari's Web Inspector to debug

Enable Safari developer menu:
- Safari → Preferences → Advanced → "Show Develop menu in menu bar"

## Architecture Notes

### WKWebView Security

- Only allows navigation to `wholelifejourney.com` domains
- All other links open in Safari
- HTTPS enforced (no HTTP)
- Session cookies persist between launches

### Token Flow

1. User logs in via WebView
2. Web calls JS bridge: `window.wljNative.requestExchangeCode()`
3. Django returns one-time code
4. iOS exchanges code for API token
5. Token stored in Keychain (never UserDefaults)
6. All API calls use Bearer token auth

### HealthKit Data

Data synced (last 7 days):
- Steps (daily totals)
- Weight (most recent per day)
- Sleep (sessions with stages)
- Heart rate (resting)

Sync is manual by default. User triggers via Settings screen.
