# iOS App Store First-Time Submission Guide

Complete guide for submitting the WLJ iOS app to the App Store for the first time.

---

## Table of Contents

1. [Apple Developer Portal Setup](#apple-developer-portal-setup)
2. [App Store Connect Setup](#app-store-connect-setup)
3. [Xcode Archive & Upload](#xcode-archive--upload)
4. [TestFlight Testing](#testflight-testing)
5. [App Store Submission](#app-store-submission)
6. [Privacy & App Review Answers](#privacy--app-review-answers)
7. [Common Rejections & Prevention](#common-rejections--prevention)

---

## Apple Developer Portal Setup

### Step 1: Create App ID

1. Go to [developer.apple.com/account](https://developer.apple.com/account)
2. Click **Certificates, Identifiers & Profiles**
3. Click **Identifiers** → **+** button
4. Select **App IDs** → Continue
5. Select **App** → Continue
6. Fill in:
   - Description: `Whole Life Journey`
   - Bundle ID: `Explicit` → `com.wholelifejourney.app`
7. Scroll to **Capabilities** and enable:
   - ✅ HealthKit
   - ✅ Push Notifications (for future use)
8. Click **Continue** → **Register**

### Step 2: Create Certificates (if needed)

1. Go to **Certificates** → **+** button
2. For development: Select **Apple Development** → Continue
3. Create CSR:
   - Open Keychain Access on Mac
   - Keychain Access → Certificate Assistant → Request a Certificate from a Certificate Authority
   - Fill in email, select "Saved to disk"
4. Upload CSR file → Continue → Download certificate
5. Double-click certificate to install in Keychain

For distribution:
- Repeat with **Apple Distribution** certificate type

### Step 3: Register Test Device

1. Go to **Devices** → **+** button
2. Select **iOS, iPadOS, tvOS, watchOS, visionOS**
3. Get UDID from iPhone:
   - Connect iPhone to Mac
   - Open Finder → Select iPhone → Click device info text twice
   - UDID appears (40 character string)
4. Enter name and UDID → Continue → Register

### Step 4: Create Provisioning Profiles

**Development Profile:**
1. Go to **Profiles** → **+** button
2. Select **iOS App Development** → Continue
3. Select App ID: `Whole Life Journey` → Continue
4. Select your development certificate → Continue
5. Select your test devices → Continue
6. Name: `WLJ Development` → Generate → Download

**Distribution Profile:**
1. **Profiles** → **+** button
2. Select **App Store Connect** → Continue
3. Select App ID → Continue
4. Select distribution certificate → Continue
5. Name: `WLJ Distribution` → Generate → Download

---

## App Store Connect Setup

### Step 1: Create App

1. Go to [appstoreconnect.apple.com](https://appstoreconnect.apple.com)
2. Click **Apps** → **+** → **New App**
3. Fill in:
   - Platform: ✅ iOS
   - Name: `Whole Life Journey`
   - Primary Language: `English (U.S.)`
   - Bundle ID: Select `com.wholelifejourney.app`
   - SKU: `wlj-ios-app-001`
   - User Access: `Full Access`
4. Click **Create**

### Step 2: App Information

Go to **App Information** in left sidebar:

**Localizable Information:**
- Name: `Whole Life Journey`
- Subtitle: `Personal Wellness Tracker`

**General Information:**
- Category: `Health & Fitness`
- Secondary Category: `Lifestyle` (optional)
- Content Rights: Select "Does not contain..." if you own all content

**Age Rating:** (See detailed answers below)

### Step 3: Pricing and Availability

1. Go to **Pricing and Availability**
2. Price: Select `Free` (or your price tier)
3. Availability: Select countries (start with United States)

### Step 4: App Privacy

Go to **App Privacy**:

1. Click **Get Started**
2. **Data Collection:** Select "Yes, we collect data"
3. Add each data type (see detailed answers below)

---

## Xcode Archive & Upload

### Step 1: Set Version Numbers

1. In Xcode, select WLJWrapper project
2. Select WLJWrapper target → **General** tab
3. Set:
   - Version: `1.0.0`
   - Build: `1`

### Step 2: Select Archive Scheme

1. Product → Scheme → Edit Scheme
2. Select "Release" for Archive build configuration
3. Close

### Step 3: Archive

1. Select **Any iOS Device (arm64)** in device selector
2. Product → Archive (Cmd+Shift+A)
3. Wait for build to complete
4. Archives window opens automatically

### Step 4: Upload to App Store Connect

1. In Archives window, select your archive
2. Click **Distribute App**
3. Select **App Store Connect** → Next
4. Select **Upload** → Next
5. Leave default options checked:
   - ✅ Include bitcode
   - ✅ Upload symbols
   - ✅ Manage Version and Build Number
6. Click **Next** → Automatically manage signing → Next
7. Review and click **Upload**
8. Wait for upload to complete (may take several minutes)

### Step 5: Verify Upload

1. Go to App Store Connect → Your App
2. Click **TestFlight** tab
3. Build should appear (may take 15-30 minutes for processing)

---

## TestFlight Testing

### Internal Testing

1. Go to **TestFlight** → **Internal Testing**
2. Click **+** to add testers (must be App Store Connect users)
3. Once build is processed, testers receive email
4. Testers install TestFlight app and accept invite

### External Testing (Beta)

1. Go to **TestFlight** → **External Testing**
2. Click **+** to create a group
3. Add build to group
4. Submit for Beta App Review (usually 24-48 hours)
5. Once approved, add external testers by email

---

## App Store Submission

### Step 1: Prepare Screenshots

**Required sizes:**

| Device | Size | Required |
|--------|------|----------|
| iPhone 6.9" | 1320 x 2868 | Yes |
| iPhone 6.7" | 1290 x 2796 | Yes |
| iPhone 6.5" | 1284 x 2778 | Yes |
| iPhone 5.5" | 1242 x 2208 | No (but recommended) |
| iPad 12.9" | 2048 x 2732 | Yes (if supporting iPad) |

**Screenshots to capture:**
1. Main dashboard (WebView showing WLJ)
2. Native Settings screen
3. Health Sync screen with HealthKit permissions
4. Health data displayed in WLJ

### Step 2: App Store Listing

Go to your app → **App Store** tab → **Prepare for Submission**:

**Screenshots:** Upload for each device size

**Promotional Text:** (170 chars, can change anytime)
```
Track your wellness journey with HealthKit sync. Monitor steps, weight, sleep, and heart rate all in one place.
```

**Description:** (4000 chars max)
```
Whole Life Journey helps you track and improve every aspect of your wellness - physical health, mental wellbeing, faith, and life goals.

KEY FEATURES:

Health Tracking with Apple Health
- Automatically sync steps, weight, sleep, and heart rate
- View trends and insights from your health data
- No manual data entry required

Comprehensive Wellness Dashboard
- Track nutrition and fasting
- Log workouts and activities
- Monitor glucose with Dexcom integration

Faith & Spirituality
- Daily Bible reading plans
- Prayer tracking and journaling
- Scripture memory tools

Life Management
- Goal setting and tracking
- Task management
- Habit building

AI-Powered Insights
- Personalized coaching
- Pattern recognition
- Actionable recommendations

PRIVACY FOCUSED
- Your data is yours
- Never sold to advertisers
- Secure encryption

Start your whole life journey today.
```

**Keywords:** (100 chars)
```
health,wellness,fitness,steps,weight,sleep,journal,goals,habits,faith,prayer,tracking,HealthKit
```

**Support URL:**
```
https://wholelifejourney.com/help/
```

**Marketing URL:** (optional)
```
https://wholelifejourney.com/
```

### Step 3: Build Selection

1. In **Build** section, click **+**
2. Select your uploaded build
3. Save

### Step 4: Submit for Review

1. Review all sections (green checkmarks)
2. Click **Add for Review**
3. Answer submission questions (see below)
4. Click **Submit to App Review**

---

## Privacy & App Review Answers

### App Privacy (Nutrition Labels)

**Contact Info:**
- ✅ Collected
- Linked to identity: Yes
- Used for: App Functionality

**Health & Fitness:**
- ✅ Collected
- Linked to identity: Yes
- Used for: App Functionality
- **Not** used for: Tracking, Third Party Advertising

**Usage Data:**
- ✅ Collected
- Linked to identity: Yes
- Used for: Analytics, App Functionality

**Identifiers:**
- ✅ Device ID collected
- Linked to identity: Yes
- Used for: App Functionality

**What to select for each:**
- Tracking: **NO**
- Third-party advertising: **NO**
- Developer's advertising: **NO**
- Analytics: Yes (for health/app functionality)
- Product personalization: Yes
- App functionality: Yes

### HealthKit Justification

When asked "How does your app use HealthKit?":

```
Whole Life Journey reads health data from Apple Health to help users track their wellness journey without manual data entry.

Data used:
- Steps: Display daily step counts and trends
- Weight: Track weight changes over time
- Sleep: Monitor sleep duration and quality
- Heart Rate: Track resting heart rate trends

All health data is:
1. Read-only (we never write to HealthKit)
2. Synced only when user explicitly requests
3. Stored securely on our servers with encryption
4. Never shared with third parties
5. Never used for advertising

Users can revoke access at any time through iOS Settings.
```

### WKWebView Defense

If asked about WKWebView usage:

```
While our app uses WKWebView to display the Whole Life Journey web interface, it provides substantial native functionality that cannot be achieved through a website alone:

NATIVE FEATURES:
1. HealthKit Integration - Reads steps, weight, sleep, and heart rate from Apple Health
2. Secure Token Storage - API credentials stored in iOS Keychain (not possible in web)
3. Native Settings Screen - Full SwiftUI interface for health sync configuration
4. Background Sync Support - Infrastructure for future background data sync

The WebView loads only our own domain (wholelifejourney.com) and provides the rich wellness content while native code handles all health data and secure storage.

This architecture allows us to leverage our existing web platform while adding valuable native capabilities that require iOS APIs.
```

### Export Compliance

**Does your app use encryption?**
- Yes (for HTTPS/TLS)

**Does your app qualify for exemption?**
- Yes

**Exemption reason:**
```
The app uses standard HTTPS/TLS encryption for network communication only.
No custom encryption algorithms are implemented.
Qualifies for exemption under 15 CFR 740.17(b).
```

### Sign-In Information (Test Account)

Provide a test account for the reviewer:

```
Email: reviewer@wholelifejourney.com
Password: [Create a test account with this password]
```

**Important:** Create this account before submission with sample health data.

### App Review Notes

```
NATIVE FEATURES DEMONSTRATION:

1. Launch the app
2. Log in with provided credentials
3. Tap the gear icon (bottom right) to open native Settings
4. Navigate to "Health Data Sync"
5. Tap "Authorize HealthKit" to see iOS permission dialog
6. After authorization, tap "Sync Now" to sync health data

The native Settings screen and HealthKit integration demonstrate this app's functionality beyond a simple website wrapper.

HEALTHKIT DATA:
The test account has sample health data. You can also use your own HealthKit data by logging into your personal account.

WEBVIEW DOMAINS:
The app only loads content from wholelifejourney.com. External links open in Safari.
```

### Age Rating Questionnaire

| Question | Answer |
|----------|--------|
| Cartoon or Fantasy Violence | None |
| Realistic Violence | None |
| Prolonged Graphic Violence | None |
| Sexual Content | None |
| Graphic Sexual Content | None |
| Profanity | None |
| Crude Humor | None |
| Alcohol, Tobacco, Drug Use | None |
| Simulated Gambling | None |
| Horror/Fear Themes | None |
| Mature/Suggestive Themes | None |
| Medical Information | **Infrequent/Mild** |
| Unrestricted Web Access | None |

**Result:** Rated 4+ (suitable for all ages)

---

## Common Rejections & Prevention

### 1. "Just a Website" Rejection (Guideline 4.2)

**Prevention:**
- ✅ Native Settings screen (implemented)
- ✅ HealthKit integration (implemented)
- ✅ Keychain storage (implemented)
- ✅ Clear explanation in review notes

### 2. HealthKit Misuse (Guideline 5.1.3)

**Prevention:**
- ✅ Clear usage description in Info.plist
- ✅ Data used only for stated purpose
- ✅ No selling health data to third parties
- ✅ User controls all permissions

### 3. No Account Deletion (Guideline 5.1.1)

**Prevention:**
- Account deletion available at: `https://wholelifejourney.com/user/delete-account/`
- Document in review notes

### 4. Broken Login (Common Issue)

**Prevention:**
- Create test account before submission
- Verify login works on TestFlight build
- Include clear credentials in review notes

### 5. Incomplete Metadata

**Prevention:**
- All screenshots provided
- Description filled out
- Support URL working
- Privacy policy URL working

### 6. Crashes/Bugs

**Prevention:**
- Test thoroughly on TestFlight
- Test on multiple device sizes
- Check Xcode Organizer for crash logs

---

## Post-Submission

### Timeline

- Initial review: 24-48 hours typically
- May take longer for first submission
- You'll receive email when reviewed

### If Rejected

1. Read rejection reason carefully
2. Make required changes
3. Reply in Resolution Center with explanation
4. Resubmit

### After Approval

1. App goes live immediately (or on scheduled date)
2. Monitor ratings and reviews
3. Watch for crash reports in App Store Connect
4. Respond to customer support inquiries

---

## Quick Reference: Required URLs

| URL | Purpose |
|-----|---------|
| https://wholelifejourney.com/help/ | Support URL |
| https://wholelifejourney.com/privacy/ | Privacy Policy |
| https://wholelifejourney.com/terms/ | Terms of Service |
| https://wholelifejourney.com/user/delete-account/ | Account Deletion |
| support@wholelifejourney.com | Support Email |

---

## Files Checklist

Before submission, ensure you have:

- [ ] App icon (1024x1024 PNG, no alpha)
- [ ] Screenshots for all required sizes
- [ ] Test account credentials
- [ ] Build uploaded to App Store Connect
- [ ] All metadata filled in
- [ ] Privacy policy page live
- [ ] Support page live
- [ ] Account deletion flow working
