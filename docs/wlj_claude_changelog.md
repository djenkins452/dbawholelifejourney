# ==============================================================================
# File: docs/wlj_claude_changelog.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Historical record of fixes, migrations, and changes
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-28
# Last Updated: 2026-01-01 (ClaudeTask Admin Interface)
# ==============================================================================

# WLJ Change History

This file contains the historical record of all fixes, migrations, and significant changes.
For active development context, see `CLAUDE.md` (project root).

---

## 2026-01-01 Changes

### ClaudeTask Admin Interface (NEW FEATURE)

**Session:** New App Ideas/Fixes

**Description:**
Created a Django Admin interface for managing Claude Code tasks. Danny can now add, edit, and manage tasks through the web admin instead of editing markdown files.

**Features:**
- **ClaudeTask Model** with fields for title, description, status, priority, category, phases
- **10 Task Categories:** Bug, Feature, Enhancement, Idea, Refactor, Maintenance, Cleanup, Security, Performance, Documentation
- **Source Tracking:** Tasks marked as "User" (added by Danny) or "Claude" (discovered during session)
- **Color-coded badges** for status (blue=new, yellow=in progress, green=complete, red=blocked)
- **Priority badges** (HIGH=red, MEDIUM=yellow, LOW=green)
- **Multi-phase support** for complex features (Claude does one phase at a time)
- **Bulk actions** to mark tasks as New/In Progress/Complete/Blocked
- **Auto-assigned task numbers** (TASK-001, TASK-002, etc.)

**Admin URL:** `/admin/admin_console/claudetask/`

**Files Created:**
- `apps/admin_console/migrations/0001_create_claudetask.py`

**Files Modified:**
- `apps/admin_console/models.py` - ClaudeTask model
- `apps/admin_console/admin.py` - ClaudeTaskAdmin with badges and actions
- `CLAUDE.md` - Updated PM workflow, added auto-allow tools instructions
- `docs/wlj_claude_changelog.md` - This entry

---

### Delete Food Entries from History Page (ENHANCEMENT)

**Session:** Delete Food History

**Feature:**
Added the ability to delete food entries directly from the Food History page without navigating to the detail page first.

**Changes Made:**
1. Added inline delete button with confirmation dialog to each food entry row in history
2. Added CSS styles for inline-form and text-danger classes to match nutrition home styling
3. Delete uses existing soft-delete pattern via `FoodEntryDeleteView`

**Files Modified:**
- `templates/health/nutrition/history.html` - Added delete form and styles

**Migration:**
- `apps/core/migrations/0033_food_history_delete_release_note.py` - What's New entry

**Tests:** All 82 nutrition tests and 101 health comprehensive tests pass.

---

### Claude as Project Manager (ENHANCEMENT)

**Session:** New App Ideas/Fixes

**Description:**
Enhanced the task queue system so Claude acts as a full Project Manager. Just start a session and Claude automatically:
1. Reads the task queue
2. Gives a status summary (active, pending, blocked)
3. Shows top priority items ready to work
4. Asks what you want to tackle
5. Executes work, updates docs, and deploys

**Features:**
- **Quick Commands:** "What's the status?", "Do the next task", "Add task: [description]"
- **Multi-Phase Tasks:** Claude completes one phase at a time, then asks if you want to continue or save for next session
- **Automatic Updates:** Claude updates task status, moves completed tasks to archive, and commits changes
- **Session Tracking:** Session log records what was worked on and outcomes

**Files Modified:**
- `docs/wlj_claude_tasks.md` - Complete rewrite with PM workflow, quick commands, status summary section
- `CLAUDE.md` - Updated session instructions with PM workflow, quick command table
- `docs/wlj_claude_changelog.md` - This entry

---

### Google Calendar OAuth Redirect URI Fix (BUG FIX)

**Session:** Google Calendar Error

**Problem:**
When trying to connect Google Calendar from production, users received "Access blocked: This app's request is invalid" with error 400: redirect_uri_mismatch.

**Root Cause:**
The `GOOGLE_CALENDAR_REDIRECT_URI` setting had an empty default for production, requiring the environment variable to be set. When not set, the redirect URI sent to Google was empty or didn't match the authorized URI in Google Cloud Console.

**Solution:**
1. Added production default redirect URI: `https://wholelifejourney.com/life/calendar/google/callback/`
2. Added diagnostic logging for redirect URI configuration
3. Follows same pattern as Dexcom OAuth fix (uses env var with sensible default)

**Files Modified:**
- `config/settings.py` - Added production default for GOOGLE_CALENDAR_REDIRECT_URI
- `apps/life/services/google_calendar.py` - Added logging for OAuth configuration

**Required Action:**
User must add `https://wholelifejourney.com/life/calendar/google/callback/` as an authorized redirect URI in Google Cloud Console under:
APIs & Services → Credentials → OAuth 2.0 Client IDs → (your client) → Authorized redirect URIs

---

### Dexcom OAuth v3 Upgrade and Debugging (BUG FIX)

**Session:** Dexcom Fix

**Problem:**
Dexcom OAuth connection was failing with blank screen after user consent. User could log in to Dexcom but after granting permission, the callback resulted in no redirect or error.

**Root Cause:**
1. OAuth endpoints were using v2 paths (`/v2/oauth2/login`, `/v2/oauth2/token`) instead of v3
2. Authorization URL query parameters were not properly URL-encoded
3. Insufficient logging made it impossible to diagnose issues

**Solution:**
1. Updated OAuth endpoints to v3 (`/v3/oauth2/login`, `/v3/oauth2/token`)
2. Added `urllib.parse.urlencode()` for proper URL encoding of query parameters
3. Added comprehensive logging throughout the OAuth flow:
   - Callback receipt with user info and GET parameters
   - Code presence, state comparison, and stored state validation
   - Token exchange URL, redirect_uri, and response status
   - Full error response body for troubleshooting
   - Stack traces for exception handling

**Files Modified:**
- `apps/health/services/dexcom.py` - v3 endpoints, URL encoding, logging
- `apps/health/views.py` - Detailed logging in DexcomCallbackView

---

## 2025-12-31 Changes

### Dexcom CGM Integration (NEW FEATURE)

**Session:** Journal Book View (continued)

Added full Dexcom Continuous Glucose Monitor integration to automatically sync blood glucose data.

**Features Added:**
1. **OAuth 2.0 Authentication**
   - Secure connection to Dexcom account via OAuth flow
   - Token storage and automatic refresh
   - Connect/disconnect UI on glucose dashboard

2. **Glucose Data Sync**
   - Automatic import of EGV (Estimated Glucose Values)
   - Trend arrows showing glucose direction (rising/falling)
   - Trend rate in mg/dL/min
   - Manual sync trigger with day range selection
   - Duplicate detection to prevent re-importing same readings

3. **New Glucose Dashboard**
   - Current reading with large display and trend arrow
   - Time in Range calculation (70-180 mg/dL)
   - Low/high event counts
   - 24-hour chart with color-coded points
   - Stats: average, min, max for past 7 days
   - Recent readings list with source indicators

4. **Extended GlucoseEntry Model**
   - New fields: source, dexcom_record_id, trend, trend_rate, display_device
   - New context choice: "cgm" for CGM readings
   - Status display (Very Low, Low, In Range, High, Very High)

5. **DexcomCredential Model**
   - OAuth token storage (access_token, refresh_token, token_expiry)
   - Sync settings (enabled, days_to_sync)
   - Sync status tracking (last_sync, status, count)

**Files Created:**
- `apps/health/services/__init__.py`
- `apps/health/services/dexcom.py` - DexcomService, DexcomSyncService
- `templates/health/glucose/dashboard.html`
- `templates/health/glucose/form.html`
- `templates/health/glucose/list.html`

**Files Modified:**
- `apps/health/models.py` - Added DexcomCredential, extended GlucoseEntry
- `apps/health/views.py` - Added Dexcom views, GlucoseDashboardView
- `apps/health/urls.py` - Added Dexcom and glucose dashboard routes
- `apps/health/admin.py` - Added DexcomCredentialAdmin, updated GlucoseEntryAdmin
- `config/settings.py` - Added Dexcom configuration settings
- `docs/wlj_third_party_services.md` - Added Dexcom service documentation

**Migration:**
- `apps/health/migrations/0012_dexcom_cgm_integration.py`

**Environment Variables Required:**
- `DEXCOM_CLIENT_ID` - From Dexcom Developer Portal
- `DEXCOM_CLIENT_SECRET` - From Dexcom Developer Portal
- `DEXCOM_REDIRECT_URI` - OAuth callback URL
- `DEXCOM_USE_SANDBOX` - Set to true for sandbox mode (development)

**Setup Instructions:**
1. Register app at https://developer.dexcom.com/
2. Create an application with Redirect URI pointing to `/health/glucose/dexcom/callback/`
3. Set environment variables in Railway
4. Users can connect from Health > Blood Glucose dashboard

---

### Delete Button Contrast Fix (BUG FIX)

**Session:** Significant Events

**Problem:**
The Delete button on the Significant Event detail page had red text on a red background, making the text invisible. The button only showed white text on hover, which is poor accessibility.

**Root Cause:**
The template used `class="btn btn-ghost btn-danger"` where:
- `btn-ghost` sets `background-color: transparent`
- The inline CSS `.btn-danger` set `color: var(--color-error)` (red text)
- Result: red text on transparent button that appears red due to hover styles

**Solution:**
1. Removed `btn-ghost` class from the delete button
2. Updated inline CSS `.btn-danger` to use:
   - `background-color: var(--color-error)` (red background)
   - `color: white` (white text for contrast)
   - Proper hover state with darker red background

**Files Modified:**
- `templates/life/significant_event_detail.html`:
  - Line 34: Changed from `class="btn btn-ghost btn-danger"` to `class="btn btn-danger"`
  - Lines 336-344: Updated `.btn-danger` CSS to have red background with white text
- `templates/life/pet_detail.html`:
  - Line 54: Changed from `class="btn btn-ghost btn-danger"` to `class="btn btn-danger"`
  - (Already had correct `.btn-danger` CSS styling)

**No migrations required** - CSS/template changes only.

---

### Journal Book View Fix (BUG FIX)

**Session:** Journal Book View

**Problem:**
The Journal Book View feature was not working. When users navigated to `/journal/book-view/`, the JavaScript would fail because the `entries_json` context variable was being passed as a Python list directly into the JavaScript code instead of being properly serialized as JSON.

**Root Cause:**
In `apps/journal/views.py`, the `BookView.get_context_data()` method was passing a Python list to the template:
```python
context["entries_json"] = [...]  # Python list with None/True/False
```

When this was rendered in the template with `{{ entries_json|safe }}`, it produced invalid JavaScript because:
- Python `None` was output instead of JavaScript `null`
- Python `True/False` was output instead of JavaScript `true/false`
- Python string quotes and escaping differ from JSON

**Solution:**
1. Added `import json` at the top of `apps/journal/views.py`
2. Changed the context assignment to properly serialize to JSON:
   ```python
   context["entries_json"] = json.dumps(entries_data)
   ```

**Files Modified:**
- `apps/journal/views.py`:
  - Added `import json` (line 33)
  - Changed `entries_json` to use `json.dumps()` for proper JSON serialization (line 163)

**Testing:**
- All 11 journal view tests pass
- Book view test (`test_book_view_loads`) passes

---

### Weight Loss Calculation and Progress Graph (NEW FEATURE)

**Session:** Weight Loss and Graph

Added total weight loss calculation and an interactive progress chart to the Weight History page.

**Features Added:**
1. **Total Weight Change Calculation**
   - Shows how much weight lost/gained from first entry to latest entry
   - Displayed in stats bar with color coding (green for loss, orange for gain)
   - Shows starting weight, current weight, and total change

2. **Weight Progress Chart**
   - Interactive line chart showing weight over time (up to 100 entries)
   - Uses Chart.js for smooth, responsive visualization
   - Hover tooltips show exact weight and date
   - Chart displays journey summary with date range and total change

3. **Enhanced Stats Bar**
   - New "Total Change" stat added to existing Latest/Low/High/Avg bar
   - Highlighted with accent border for visibility

**Layout:**
- Stats bar (Latest, Low, High, Avg, Total Change)
- Weight Progress Chart (new)
- Weight History table (existing)

**Files Modified:**
- `apps/health/views.py` - WeightListView: Added weight_change, first_entry, first_weight, latest_weight_lb, and chart_data to context
- `templates/health/weight_list.html` - Added Total Change stat, chart container with Chart.js, and responsive styles

**Tests Added (4 new tests):**
- `test_weight_list_has_weight_loss_calculation` - Verifies weight change calculation
- `test_weight_list_has_chart_data` - Verifies chart data structure
- `test_weight_list_single_entry_no_change` - No weight_change with single entry

**Test Count:** 1395 tests (was 1392, +3 new tests)

**No migrations required** - View/template changes only.

---

### Data Encryption Roadmap (DOCUMENTATION)

Added comprehensive data encryption analysis and roadmap to security documentation.

**Session:** Encryption of Data

**Analysis Completed:**
- Reviewed current data storage (all sensitive fields stored as plaintext)
- Evaluated three encryption approaches:
  - Option A: Full encryption (breaks search)
  - Option B: Selective encryption (recommended for pre-launch)
  - Option C: Full encryption + search index (complex, for post-launch if needed)
- Assessed impact on AI features (Dashboard AI, Personal Assistant, trend tracking)
- Documented performance implications and trade-offs

**Key Findings:**
- AI features will NOT break with encryption (data decrypted before sending to OpenAI)
- Journal/task search WILL break with encryption (can't search encrypted fields)
- Option B (selective encryption) provides best balance for pre-launch

**Decision:** Defer encryption implementation during development phase to reduce complexity. Implement Option B (selective encryption) before public launch.

**Files Modified:**
- `docs/wlj_security_review.md` - Added Appendix D: Data Encryption Roadmap
  - Documents current state, options evaluated, implementation phases
  - Key management requirements
  - AI feature compatibility analysis
  - Decision rationale

**Security Certifications Discussed:**
- SSL Certificate (already in place via Railway)
- Privacy Policy and Terms of Service
- Penetration testing (recommended pre-launch)
- SOC 2 / ISO 27001 / HIPAA (enterprise-level, not needed yet)

---

### SMS Error 21212 - Phone Number Validation Fix (FIX)

**Problem Solved:**
Twilio Error 21212 "Invalid 'From' number" was occurring when sending SMS because the `TWILIO_PHONE_NUMBER` environment variable wasn't properly validated or normalized to E.164 format.

**Error from Twilio Console:**
- Error Code: 21212
- Message: "The 'From' parameter you supplied was not a valid phone number, Alphanumeric Sender ID or approved WhatsApp Sender."

**Root Cause:**
The `TWILIO_PHONE_NUMBER` could be set incorrectly (missing +, wrong format, extra characters) without validation, causing Twilio to reject SMS sends.

**Solution:**
1. Added `_normalize_phone_number()` method to TwilioService that:
   - Removes formatting characters (spaces, dashes, parentheses, dots)
   - Adds +1 prefix for 10-digit US numbers
   - Adds + prefix for 11-digit numbers starting with 1
   - Validates against E.164 regex pattern (`^\+[1-9]\d{1,14}$`)
   - Returns empty string for invalid numbers
2. Phone number normalization happens at service initialization AND for destination numbers
3. Added detailed error logging showing actual From/To values when errors occur
4. Added specific error messages for common Twilio errors (21212, 21211)
5. Added configuration validation that logs clear errors if TWILIO_PHONE_NUMBER is invalid

**Files Modified:**
- `apps/sms/services.py`:
  - Added `E164_PATTERN` regex constant
  - Added `_normalize_phone_number()` method
  - Updated `__init__()` to validate/normalize the phone number at startup
  - Updated `send_sms()` with detailed error messages and normalization
- `apps/sms/tests/test_sms_comprehensive.py`:
  - Added `TwilioServicePhoneNormalizationTests` class (6 new tests)
  - Tests: E.164 format, 10-digit US, 11-digit US, formatting removal, invalid handling

**Test Count:** 46 SMS tests (was 40, added 6 phone normalization tests)

**Action Required for Railway:**
Verify `TWILIO_PHONE_NUMBER` environment variable is set correctly:
- Must be in E.164 format: `+1XXXXXXXXXX` (e.g., `+12025551234`)
- Or 10-digit format: `2025551234` (will be auto-converted)
- Check in Twilio Console that this number is assigned to your account

---

### SMS History Timezone Fix (FIX)

**Problem Solved:**
SMS notification times in `/sms/history/` were displayed in UTC instead of the user's timezone.

**Solution:**
- Added Django timezone template tag to convert times to user's local timezone
- Updated date grouping to use local timezone (so notifications appear under correct day)
- Added `user_timezone` to view context

**Files Modified:**
- `templates/sms/history.html` - Added `{% load tz %}` and timezone conversion
- `apps/sms/views.py` - Added pytz timezone conversion for date grouping and context

---

### SMS History Link on Preferences (Enhancement)

Added a "View History" button to the SMS Notifications section on the Preferences page for easy access to `/sms/history/`.

**Files Modified:**
- `templates/users/preferences.html` - Added link and CSS for card-title-row

---

### Embedded SMS Scheduler in Web Process (FIX)

**Problem Solved:**
SMS scheduler was configured to run as a separate worker process, but Railway doesn't auto-create worker processes from Procfile - only web and database services are created by default.

**Solution:**
Embedded the APScheduler background jobs directly in the WSGI application. The scheduler starts when Gunicorn loads the application using the `--preload` flag.

**Key Implementation Details:**
1. **Embedded in WSGI:** Scheduler starts in `config/wsgi.py` rather than as separate worker
2. **Single Instance:** Uses `SMS_SCHEDULER_STARTED` environment variable to prevent duplicate schedulers when Gunicorn forks workers
3. **Textual References:** Jobs use textual references (`'apps.sms.jobs:schedule_daily_reminders'`) instead of function objects to avoid APScheduler serialization issues
4. **MemoryJobStore:** Uses in-memory job store (not DjangoJobStore) because jobs are re-registered on each startup anyway

**New File Created:**
- `apps/sms/jobs.py` - Importable job functions for APScheduler:
  - `schedule_daily_reminders()` - Called at midnight to create SMSNotification records
  - `send_pending_sms()` - Called every 5 minutes to send due notifications

**Files Modified:**
- `config/wsgi.py` - Added `start_scheduler()` function that initializes APScheduler with two jobs
- `Procfile` - Added `--preload` flag to Gunicorn command to ensure scheduler starts once before forking

**Error Fixed:**
- `SerializationError: This Job cannot be serialized since the reference to its callable could not be determined`
- Solution: Created standalone functions in `apps/sms/jobs.py` and used textual references

**Deployment Status:**
- Railway logs confirm: "SMS scheduler started successfully"
- Initial send check runs on startup: "Sent 0 SMS, 0 failed, 0 skipped"

---

### Real-Time SMS Scheduling on Save (NEW)

**Problem Solved:**
If you created a medicine schedule at 2pm for 8pm tonight, the SMS reminder wouldn't be scheduled until the next midnight batch job ran.

**Solution:**
Added Django signals that trigger SMS scheduling immediately when you save:
- Medicines and MedicineSchedules → Schedules SMS for any doses due today
- Tasks → Schedules SMS reminder at 9 AM if due today
- Events (LifeEvent) → Schedules SMS 30 minutes before event time

**New File:**
- `apps/sms/signals.py` - Django post_save signal handlers for real-time scheduling

**Files Modified:**
- `apps/sms/apps.py` - Registers signals in `ready()` method

**Test Count:** 1394 tests (+2 new signal tests)

---

### Universal Barcode Scanner Integration (MAJOR FEATURE)

Extended the barcode scanner to work throughout the app, enabling users to scan product barcodes to auto-populate forms. This significantly reduces data entry when adding inventory items or medicines.

**Example Use Case:**
User scans a DeWalt drill barcode → System looks up product in external databases → Returns product name, brand, model, category → Pre-fills Inventory form → User just reviews and submits.

**New Files Created:**
- `apps/scan/services/product_lookup.py` - Product lookup service for electronics, tools, household items
  - Uses UPC Item DB API (free tier) for product lookups
  - OpenAI fallback for unknown products
  - Returns: product_name, brand, category, model_number, description, msrp
  - 24-hour caching to minimize API calls

- `apps/scan/services/medicine_lookup.py` - Medicine lookup service for OTC drugs and supplements
  - Uses RxNav API (NIH, free) for drug name lookups
  - Uses FDA OpenData API (free) for NDC code lookups
  - OpenAI fallback for unknown medicines
  - Returns: medicine_name, generic_name, brand_name, dosage_form, strength, purpose

**Files Modified:**
- `apps/scan/services/__init__.py` - Export new services
- `apps/scan/urls.py` - Added `/barcode/product/` and `/barcode/medicine/` endpoints
- `apps/scan/views.py` - Added `ProductLookupView` and `MedicineLookupView` classes
- `apps/life/views.py` - Updated `InventoryCreateView` with barcode scan support and additional pre-fill fields
- `apps/health/views.py` - Updated `MedicineCreateView` with barcode scan support and context data
- `templates/life/inventory_form.html` - Added barcode scanner UI with camera integration
- `templates/health/medicine/medicine_form.html` - Added barcode scanner UI with camera integration

**New API Endpoints:**
- `POST /scan/barcode/product/` - Look up product barcode, returns inventory pre-fill URL
- `POST /scan/barcode/medicine/` - Look up medicine barcode, returns medicine pre-fill URL

**External APIs Used (All FREE):**
- UPC Item DB - Product database for electronics, tools, appliances
- RxNav API (NIH) - Drug database for medication lookups
- FDA OpenData - Official NDC drug database
- OpenAI (fallback) - For products not in external databases

**Features:**
- Native browser barcode detection using `BarcodeDetector` API
- Manual barcode entry fallback for unsupported browsers
- Real-time camera preview with scanning target overlay
- Haptic feedback on successful barcode detection
- Pre-fill redirect to appropriate form with all fields populated
- Source tracking (`created_via` = barcode_scan) for analytics

**No migrations required** - No database schema changes.

---

### Nutrition Breadcrumbs (Enhancement)

Added breadcrumb navigation to all nutrition pages for improved UX and navigation consistency.

**Files Modified (9 templates):**
- `templates/health/nutrition/home.html` - Health > Nutrition
- `templates/health/nutrition/food_entry_form.html` - Health > Nutrition > Log Food/Edit Entry
- `templates/health/nutrition/food_entry_detail.html` - Health > Nutrition > [Food Name]
- `templates/health/nutrition/history.html` - Health > Nutrition > History
- `templates/health/nutrition/goals.html` - Health > Nutrition > Goals
- `templates/health/nutrition/stats.html` - Health > Nutrition > Stats
- `templates/health/nutrition/quick_add.html` - Health > Nutrition > Quick Add
- `templates/health/nutrition/custom_food_list.html` - Health > Nutrition > My Foods
- `templates/health/nutrition/custom_food_form.html` - Health > Nutrition > My Foods > Create/Edit

**No migrations required** - Template-only changes.

---

### APScheduler for Automatic SMS Notification Scheduling (NEW)

**Problem Solved:**
SMS medicine reminders were not being sent because the notification system required external cron jobs to trigger scheduling and sending - but no scheduler was actually running on Railway.

**Solution:**
Integrated `django-apscheduler` to run background jobs automatically as part of the Django application. Added a worker process that:
1. **Schedules SMS reminders daily at midnight** - Creates SMSNotification records for all users with SMS enabled
2. **Sends pending SMS every 5 minutes** - Finds notifications due and sends via Twilio
3. **Cleans up old job logs weekly** - Prevents database bloat

**New Dependencies:**
- `django-apscheduler>=0.6.2` - APScheduler with Django database job store

**New Files Created:**
- `apps/sms/management/commands/run_sms_scheduler.py` - Management command to run the scheduler
  - Uses `BackgroundScheduler` with `DjangoJobStore` for persistence
  - Configurable schedule hour and send interval via command arguments
  - Runs initial send check on startup
  - Handles graceful shutdown on SIGINT

**Files Modified:**
- `requirements.txt` - Added django-apscheduler
- `config/settings.py` - Added `django_apscheduler` to INSTALLED_APPS, APScheduler configuration
- `Procfile` - Added `worker: python manage.py run_sms_scheduler`

**Deployment:**
Railway will automatically detect the worker process in Procfile and run it alongside the web process. No external cron configuration needed.

**Test Count:** 1392 tests (unchanged)

---

### Medicine Log Edit Feature (NEW)

Added the ability to edit the "taken at" time of medicine log entries. This allows users to correct the time when they actually took a dose - important when they took medicine on time but forgot to log it immediately.

**Problem Solved:**
- User takes medicine at 8:00 AM on schedule
- Forgets to tap "Take" until 9:30 AM
- Medicine is marked as "Taken Late" even though it was on time
- Now users can edit the log to correct the actual taken time

**New Files Created:**
- `templates/health/medicine/log_edit.html` - Edit form template with medicine info display

**Files Modified:**
- `apps/health/forms.py` - Added `MedicineLogEditForm` class
  - Allows editing `taken_at` datetime and `notes`
  - Converts times between user timezone and UTC
  - Recalculates Taken/Taken Late status on save based on new time
- `apps/health/views.py` - Added `MedicineLogEditView` class
  - UpdateView for editing MedicineLog entries
  - User can only edit their own logs (data isolation)
  - Imports `MedicineLogEditForm`
- `apps/health/urls.py` - Added route `/medicine/log/<int:pk>/edit/`
- `templates/health/medicine/home.html` - Added "Edit" link for taken doses
- `templates/health/medicine/history.html` - Added "Edit" link for each log entry
  - Updated CSS grid to accommodate new actions column
  - Added user_timezone to context for time display

**Tests Added (12 new tests):**
- `test_log_edit_view_requires_login` - Authentication required
- `test_log_edit_view_loads` - Page loads correctly
- `test_log_edit_shows_medicine_info` - Displays medicine name and dose
- `test_log_edit_can_update_taken_at` - Can change the time
- `test_log_edit_recalculates_status_to_taken` - Late → Taken when corrected
- `test_log_edit_recalculates_status_to_late` - Taken → Late if time changed
- `test_log_edit_can_add_notes` - Notes field works
- `test_log_edit_redirects_to_next_url` - Respects ?next= parameter
- `test_log_edit_default_redirect_to_history` - Default redirect
- `test_user_cannot_edit_other_users_log` - Data isolation (404)
- `test_log_edit_shows_current_status` - Displays status badge
- `test_history_page_shows_edit_link` - Edit link appears in history
- `test_medicine_home_shows_edit_link_for_taken_doses` - Edit link on home page

**Test Count:** 1381 tests (was 1368, +13 tests)

**No migrations required** - Uses existing MedicineLog fields.

---

### Barcode Scanner Feature (NEW)

Added dedicated barcode scanning mode to the Camera Scan feature for quick food product lookup.

**New Files Created:**
- `apps/scan/services/barcode.py` - Barcode lookup service with database and AI fallback

**Files Modified:**
- `apps/scan/views.py` - Added BarcodeLookupView for barcode API endpoint
- `apps/scan/urls.py` - Added `/scan/barcode/` URL route
- `apps/scan/services/__init__.py` - Exported barcode_service
- `apps/health/views.py` - FoodEntryCreateView now handles barcode source
- `templates/scan/scan_page.html` - Added mode toggle, barcode overlay, and barcode result states

**Test Files Modified:**
- `apps/scan/tests/test_views.py` - Added BarcodeLookupViewTests and BarcodeServiceTests
- `apps/scan/tests/test_security.py` - Fixed user isolation test assertion

**Features:**
1. **Mode Toggle UI**
   - Toggle between Vision mode and Barcode mode at top of scan page
   - Different camera overlay for each mode

2. **Barcode Detection** (Updated: ZXing Library)
   - Uses @zxing/browser library for cross-browser barcode detection
   - CDN: `https://cdn.jsdelivr.net/npm/@zxing/browser@0.1.5/umd/zxing-browser.min.js`
   - Works on all browsers including Safari/iOS (previously Quagga2 was unreliable)
   - Supports UPC-A, UPC-E, EAN-13, EAN-8, Code 128, Code 39
   - Real-time auto-detection from camera feed without button press
   - Vibration feedback on barcode detection

3. **Barcode Lookup Service** (Updated: Open Food Facts API)
   - **Lookup order:** Local DB → Open Food Facts → OpenAI fallback
   - **Open Food Facts:** Free, open-source database with 4M+ products worldwide
   - API: `https://world.openfoodfacts.org/api/v2/product/{barcode}.json`
   - Caches Open Food Facts results to local database for faster future lookups
   - Returns structured BarcodeResult with all nutritional data

4. **Food Entry Integration**
   - Pre-fills food entry form with all nutritional data
   - Sets `entry_source = 'barcode'` automatically
   - Passes barcode value in URL for reference

5. **Result Display**
   - Shows product name, brand, and key nutrition (calories, protein, carbs, fat)
   - "Log to Nutrition" button pre-fills food entry form
   - "Scan Another" to continue scanning

**No migrations required** - Uses existing FoodItem.barcode field and FoodEntry.SOURCE_BARCODE.

---

### File Cleanup & Test Fixes

Fixed 6 failing tests and added temp files to .gitignore for cleaner repository.

**Changes Made:**

1. **Added temp/test output files to .gitignore**
   - `nul` - Windows null device file that can accidentally be created
   - `test_errors.txt` - Test runner error output
   - `test_summary.txt` - Test runner summary output
   - `test_output.txt` - General test output

2. **Fixed Preferences Form Tests**
   - Added missing required fields: `weight_goal_unit`, `sms_quiet_start`, `sms_quiet_end`
   - Corrected `weight_goal_unit` value from 'lbs' to 'lb' (matching model choices)
   - Tests affected: `apps.users.tests.test_users.PreferencesViewTest`

3. **Fixed What's New Preference Tests**
   - Same form field fixes as preferences tests
   - Tests affected: `apps.core.tests.test_core_comprehensive.WhatsNewPreferenceTest`

4. **Fixed Blood Oxygen Data Isolation Test**
   - Changed test strategy: instead of checking if '94' appears in HTML (which matched unrelated content like navigation elements), now verifies entry count in context
   - More robust test that confirms data isolation without false positives
   - Tests affected: `apps.health.tests.test_health_comprehensive.BloodVitalsDataIsolationTest`

5. **Fixed Task Search Tests**
   - Updated assertions to match actual template text
   - Template shows "X results for" not "Found X tasks matching"
   - Tests affected: `apps.life.tests.test_views.TaskViewTest`

**Files Modified:**
- `.gitignore` - Added temp file patterns
- `apps/core/tests/test_core_comprehensive.py` - Fixed What's New preference tests
- `apps/health/tests/test_health_comprehensive.py` - Fixed blood oxygen data isolation test
- `apps/life/tests/test_views.py` - Fixed task search result assertions
- `apps/users/tests/test_users.py` - Fixed preferences form test

**Test Count:** 1379 tests passing (no change in total)

---

### Menu Navigation Reorganization

Updated the Health and Life module navigation menus for better organization.

**Changes Made:**

1. **Moved Fasting from Providers to Nutrition**
   - Fasting is logically related to nutrition tracking, not medical providers
   - Nutrition menu now includes: Nutrition Home, Food History, Statistics, Goals, Fasting
   - Providers menu now contains only: Medical Providers

2. **Added Significant Events to Life Menu**
   - Significant Events (birthdays, anniversaries, etc.) was missing from navigation
   - Now accessible under Life menu alongside Documents

**Files Modified:**
- `templates/components/navigation.html` - Updated Health mega-menu and Life dropdown menu

**No migrations required** - Template-only change.

---

### AI Span: Comprehensive AI Context Enhancement

Enhanced OpenAI integration to read and apply ALL relevant user data when generating Dashboard AI insights and Personal Assistant responses. The AI now has a complete picture of the user's life journey.

**New Data Sent to OpenAI:**

**Purpose Module:**
- Word of the Year and annual theme
- Anchor Scripture (if set)
- Active change intentions (identity-based shifts)
- Life goals with domain names and importance
- Goal details including "why it matters"

**Faith Module:**
- Active prayer count
- Recently answered prayers (shows God's faithfulness)
- Memory verse (if user has one set)
- Recently saved Scripture references (what user is studying)
- Faith milestones count

**Life Module:**
- Tasks due today and overdue counts
- Active projects with progress percentages
- Priority projects (marked as "Now")
- Today's calendar events count

**Health Module:**
- Current weight and weight goal progress
- Weight remaining to goal and direction (lose/gain/maintain)
- Active fasting status with hours fasted
- Today's calorie intake vs goal
- Calories remaining for the day
- Workout count and days since last workout
- Personal records achieved this month
- Medicine adherence rate with quality indicator
- Medicines needing refill

**Files Modified:**
- `apps/ai/dashboard_ai.py` - Enhanced `_gather_user_data()` with comprehensive context
  - Added Purpose module data gathering (Word of Year, goals, intentions)
  - Added enhanced Faith data (memory verse, Scripture study, answered prayers)
  - Added Life module data (projects, events, tasks due)
  - Added Health nutrition data (calories, weight goals)
  - Organized code with clear section headers
- `apps/ai/services.py` - Updated `generate_daily_insight()` to use new data
  - Added sections for Annual Direction & Purpose
  - Added Task & Project Status context
  - Added enhanced Faith Context
  - Added comprehensive Health Status
  - Improved prompt to reference Word of Year and goals

**Impact:**
- AI insights now deeply personalized to user's stated purpose
- Dashboard messages reference user's Word of the Year when appropriate
- AI can encourage progress on specific goals by name
- Health insights include weight goal progress and nutrition tracking
- Faith-aware insights include Scripture study and prayer activity

**No migrations required** - This is a code-only enhancement to AI prompt construction.

---

### Cascading Menu Navigation System

Implemented an industry-standard cascading dropdown menu system for the main navigation. Users can now hover (desktop) or tap (mobile) on module names to reveal dropdown menus with direct links to all sub-pages within each module.

**Key Features:**
- **Desktop:** Hover-triggered dropdown menus with smooth CSS transitions
- **Mobile:** Tap-to-toggle accordion-style menus that work well on touch devices
- **Mega Menu:** Health module features a multi-column mega menu with organized sections (Vitals, Medicine, Fitness, Nutrition, Providers)
- **Two-column Layout:** Life and other larger modules use a two-column dropdown for easier scanning
- **Accessibility:** Full ARIA support, keyboard navigation (ESC closes all menus), focus management
- **Visual Polish:** Icons for each menu item, dividers between sections, chevron rotation on expand

**Menu Structure:**
- Dashboard - Direct link (no dropdown)
- Journal - Home, New Entry, All Entries, Book View, Prompts, Tags
- Faith - Home, Today's Verse, Saved Scripture, Prayers, Milestones, Reflections
- Health - Mega menu with 5 columns:
  - Vitals: Health Home, Weight, Heart Rate, Blood Pressure, Glucose, Blood Oxygen
  - Medicine: Today's Medicines, All Medicines, History, Adherence
  - Fitness: Fitness Home, Workouts, Templates, Personal Records
  - Nutrition: Nutrition Home, Food History, Statistics, Goals, Fasting
  - Providers: Medical Providers
- Life - Two-column: Home, Calendar, Projects, Tasks, Inventory, Pets, Recipes, Maintenance, Documents, Significant Events
- Purpose - Home, Annual Direction, Goals, Intentions, Reflections
- Assistant - Direct link (no dropdown)

**Files Modified:**
- `templates/components/navigation.html` - Complete rewrite with dropdown structure
- `static/css/main.css` - Added 180+ lines for dropdown/mega menu styles
- `static/js/main.js` - Added dropdown toggle functions, click-outside handlers, ESC key support

**Migrations:**
- `apps/core/migrations/0023_merge_20251231_0658.py` - Merge migration for prior conflicts
- `apps/core/migrations/0024_add_cascading_menu_release_note.py` - What's New entry

**What's New Entry Added:**
- Title: "Enhanced Navigation with Cascading Menus"
- Type: Feature

---

### Memory Verse Feature

Added the ability to mark a saved Scripture verse as a "Memory Verse" to display prominently at the top of the Dashboard.

**Features:**
- Toggle button on saved verses to mark/unmark as memory verse
- Only one memory verse allowed per user at a time
- Memory verse displays at top of Dashboard (when Faith module enabled)
- Visual badge and highlight on memory verse in Scripture Library
- Star icon and styled card on Dashboard

**Files Modified:**
- `apps/faith/models.py` - Added `is_memory_verse` field to SavedVerse model
- `apps/faith/views.py` - Added `ToggleMemoryVerseView` class
- `apps/faith/urls.py` - Added route for toggle endpoint
- `apps/dashboard/views.py` - `_get_faith_data()` now fetches memory verse
- `templates/dashboard/home.html` - Added Memory Verse section after header
- `templates/faith/scripture_list.html` - Added Memorize button and badge to verse cards
- `static/css/dashboard.css` - Added Memory Verse section styles

**Migration:**
- `apps/faith/migrations/0005_add_memory_verse_field.py`

**Tests Added (10 new tests):**
- `test_default_is_not_memory_verse` - New verses aren't memory verses
- `test_toggle_to_memory_verse` - Can set as memory verse
- `test_toggle_off_memory_verse` - Can unset memory verse
- `test_only_one_memory_verse_at_a_time` - New one clears previous
- `test_cannot_toggle_other_users_verse` - User isolation
- `test_memory_verse_shows_badge_in_list` - Badge displays correctly
- `test_toggle_requires_post` - GET method not allowed
- `test_dashboard_shows_memory_verse_when_set` - Dashboard displays verse
- `test_dashboard_no_memory_verse_section_when_not_set` - Hidden when none
- `test_dashboard_no_memory_verse_when_faith_disabled` - Hidden when Faith off

---

### Fix SMS Preferences Not Saving

Fixed bug where changes to SMS notification settings in Preferences would not save.

**Issue:**
- SMS notification toggles (enabled, consent, category preferences, quiet hours) were displayed in the preferences form but were not bound to the Django form
- The template used `user.preferences.sms_*` instead of `form.sms_*.value`, which meant the fields weren't part of the form submission
- The `PreferencesForm` class did not include SMS fields in its `fields` list

**Fix:**
1. Added all 11 SMS fields to `PreferencesForm.Meta.fields`:
   - `sms_enabled`, `sms_consent`
   - `sms_medicine_reminders`, `sms_medicine_refill_alerts`
   - `sms_task_reminders`, `sms_event_reminders`
   - `sms_prayer_reminders`, `sms_fasting_reminders`
   - `sms_quiet_hours_enabled`, `sms_quiet_start`, `sms_quiet_end`

2. Added corresponding widget definitions for all SMS fields

3. Updated template to use `form.sms_*.value` instead of `user.preferences.sms_*`

4. Added SMS consent date handling in `PreferencesView.form_valid()`

**Files Modified:**
- `apps/users/forms.py` - Added SMS fields and widgets to PreferencesForm
- `apps/users/views.py` - Added SMS consent date handling
- `templates/users/preferences.html` - Updated SMS section to use form fields

---

### Task List with Search Feature

Added ability to search within tasks and improved task list display with counts.

**Features Added:**
- Full-text search across task title, notes, and project name
- Search preserves existing filters (show, priority)
- Task counts displayed on filter buttons (Active/Completed/All)
- Clear search button when search is active
- Search results count display

**Implementation:**
1. Updated `TaskListView` in `apps/life/views.py`:
   - Added search query handling with Django Q objects
   - Searches across title, notes, and project__title
   - Added `search_query` to context
   - Added `total_active_count`, `total_completed_count`, `total_all_count` to context

2. Updated `templates/life/task_list.html`:
   - Added search bar with search icon and clear button
   - Search results info display
   - Updated filter links to preserve search query
   - Added task counts to filter buttons
   - Added CSS styles for search bar

**Files Modified:**
- `apps/life/views.py` - Enhanced TaskListView with search and counts
- `templates/life/task_list.html` - Added search UI and updated filter links

---

### Improved Help System - "Why Use This Feature"

Completely rewrote the in-app help system to provide more valuable, decision-enabling content. The previous help content explained *how* to use features, but the new content explains *why* users should use each feature and how it all connects.

**New Content Structure:**
Each help topic now includes:
1. **"Why This Feature?"** - Value proposition explaining the reason to use it
2. **"How It Powers Your Dashboard"** - Connection to AI insights and dashboard
3. **"How to Use It"** - Step-by-step instructions
4. **"Tips for Success"** - Best practices
5. **"Related Features"** - Cross-module connections showing how everything integrates

**Help Topics Added/Rewritten (20 total):**
- DASHBOARD_HOME - "Your Dashboard: The Heart of Your Journey"
- GENERAL - "Navigating Your Whole Life Journey"
- JOURNAL_HOME - "Journal: The Foundation of Self-Awareness"
- HEALTH_HOME - "Health: Track What You Can Measure"
- FAITH_HOME - "Faith: Nurture Your Spiritual Journey"
- SETTINGS_PREFERENCES - "Preferences: Make It Yours"
- LIFE_HOME - "Life: Your Daily Operating Layer"
- PURPOSE_HOME - "Purpose: Your North Star"
- NUTRITION_HOME - "Nutrition: Fuel Your Body Intentionally" (NEW)
- HEALTH_MEDICINE_HOME - "Medicine Tracking: Never Miss a Dose" (NEW)
- SCAN_HOME - "Camera Scan: AI-Powered Quick Entry" (NEW)
- ASSISTANT_HOME - "Personal Assistant: Your AI-Powered Guide" (NEW)
- SMS_SETTINGS - "SMS Notifications: Reminders Where You'll See Them" (NEW)
- HEALTH_VITALS - "Vitals: Monitor Your Cardiovascular Health" (NEW)
- HEALTH_PROVIDERS - "Medical Providers: Your Healthcare Contacts" (NEW)

**Help Articles Added/Rewritten (15 total):**
- Welcome to Whole Life Journey
- Understanding Your Dashboard
- Journaling for Self-Awareness
- Health Tracking Overview
- Faith Module: Tracking Your Spiritual Journey
- Customizing Your Preferences
- AI Coaching Styles Explained
- Why Can't I See Certain Features?
- Goals and the Purpose Module
- Tasks, Projects, and the Life Module
- Medicine Tracking and Adherence (NEW)
- Camera Scan: Quick AI-Powered Entry (NEW)
- The Personal Assistant (NEW)
- SMS Notifications Setup (NEW)
- Nutrition and Food Tracking (NEW)

**New Management Command:**
- `reload_help_content` - Clears and reloads help content from fixtures
  - Options: `--dry-run`, `--topics-only`, `--articles-only`
  - Added to Procfile for automatic deployment

**Files Created:**
- `apps/help/management/__init__.py`
- `apps/help/management/commands/__init__.py`
- `apps/help/management/commands/reload_help_content.py`
- `apps/core/migrations/0022_improved_help_system_release_note.py`

**Files Modified:**
- `apps/help/fixtures/help_topics.json` - Complete rewrite (13→20 topics)
- `apps/help/fixtures/help_articles.json` - Complete rewrite (10→15 articles)
- `Procfile` - Added `reload_help_content` command

**Test Status:** All 68 help app tests passing

---

## 2025-12-30 Changes

### SMS Text Notifications Feature

Added first-class SMS notification capabilities using Twilio. Users can receive text message reminders for medicine doses, tasks, events, and more. Replies with shortcuts (D=Done, R=Remind, N=Skip) allow quick status updates directly from text messages.

**New App: `apps/sms/`**
- `models.py` - SMSNotification, SMSResponse models for tracking sent/scheduled SMS and user replies
- `services.py` - TwilioService (Twilio API integration), SMSNotificationService (scheduling, sending, reply processing)
- `scheduler.py` - SMSScheduler for scheduling medicine, task, event, prayer, and fasting reminders
- `views.py` - Phone verification, Twilio webhooks, SMS history page, protected trigger endpoints
- `urls.py` - URL patterns for all SMS endpoints
- `admin.py` - Admin registration with status badges and filters

**New User Preference Fields (15 fields):**
- Phone: `phone_number`, `phone_verified`, `phone_verified_at`
- Master toggles: `sms_enabled`, `sms_consent`, `sms_consent_date`
- Categories: `sms_medicine_reminders`, `sms_medicine_refill_alerts`, `sms_task_reminders`, `sms_event_reminders`, `sms_prayer_reminders`, `sms_fasting_reminders`
- Quiet hours: `sms_quiet_hours_enabled`, `sms_quiet_start`, `sms_quiet_end`

**Management Commands:**
- `send_pending_sms` - Send all pending SMS notifications (run every 5 min)
- `schedule_sms_reminders` - Schedule SMS for all users (run daily)

**URL Routes (10 endpoints):**
- `/sms/api/verify/send/` - Send phone verification code
- `/sms/api/verify/check/` - Verify phone with code
- `/sms/api/phone/remove/` - Remove phone and disable SMS
- `/sms/api/status/` - Get SMS configuration status
- `/sms/api/trigger/send/` - Protected: Send pending SMS
- `/sms/api/trigger/schedule/` - Protected: Schedule SMS
- `/sms/webhook/incoming/` - Twilio incoming SMS webhook
- `/sms/webhook/status/` - Twilio delivery status webhook
- `/sms/history/` - User SMS history page

**Notification Categories:**
- Medicine dose reminders
- Medicine refill alerts
- Task due date reminders
- Calendar event reminders (30 min before)
- Daily prayer reminders
- Fasting window reminders

**Reply Codes:**
- D/done/yes/taken → Mark medicine taken / task complete
- R/R5/R10/R30 → Schedule new reminder in X minutes
- N/no/skip → Mark skipped / dismiss for today

**New Files:**
- `apps/sms/__init__.py`, `apps.py`, `models.py`, `admin.py`
- `apps/sms/services.py`, `scheduler.py`, `views.py`, `urls.py`
- `apps/sms/management/commands/send_pending_sms.py`
- `apps/sms/management/commands/schedule_sms_reminders.py`
- `apps/sms/tests/test_sms_comprehensive.py` (~50 tests)
- `templates/sms/history.html` - SMS history page

**Modified Files:**
- `apps/users/models.py` - Added 15 SMS preference fields
- `templates/users/preferences.html` - Added SMS section with verification, toggles, quiet hours
- `config/settings.py` - Added Twilio settings and 'apps.sms' to INSTALLED_APPS
- `config/urls.py` - Added SMS URL include
- `requirements.txt` - Added `twilio>=9.0.0`
- `THIRD_PARTY_SERVICES.md` - Added Twilio documentation
- `CLAUDE_FEATURES.md` - Added SMS Text Notifications section

**Migrations:**
- `apps/users/migrations/0021_sms_notifications.py` - User preference fields
- `apps/sms/migrations/0001_sms_notifications.py` - SMS models

**Configuration (Environment Variables):**
- `TWILIO_ACCOUNT_SID` - Twilio account SID
- `TWILIO_AUTH_TOKEN` - Twilio auth token
- `TWILIO_PHONE_NUMBER` - Sender phone number (E.164)
- `TWILIO_VERIFY_SERVICE_SID` - Twilio Verify service SID
- `TWILIO_TEST_MODE` - Test mode (logs instead of sending)
- `SMS_TRIGGER_TOKEN` - Secret token for protected endpoints

**Test Mode:**
- When `TWILIO_TEST_MODE=True`, SMS are logged instead of sent
- Verification code `123456` is accepted in test mode

**Cost Estimates:**
- Phone Number: ~$1.15/month
- Outbound/Inbound SMS: ~$0.0079/message
- Phone verification: ~$0.05/verification

---

### Fix Medicine "Taken Late" Status When Taken Early

Fixed bug where medicines taken BEFORE the scheduled time were incorrectly marked as "Taken Late".

**Issue:**
- When a user in America/New_York (EST, UTC-5) took medicine at 8:24 AM local time with a 9:00 AM schedule, it was incorrectly marked "Taken Late"
- The root cause: the `mark_taken()` method was comparing UTC time (stored in database) against a naive local time
- Example: 8:24 AM EST = 1:24 PM UTC. When stripped of timezone, "1:24 PM" > "10:00 AM" (schedule + grace), so marked as late

**Fix:**
Updated three methods in `MedicineLog` model to properly convert times to user's timezone before comparison:

1. `mark_taken()` - Now converts `taken_at` (UTC) to user's local timezone before comparing with scheduled time
2. `was_on_time` property - Same timezone-aware comparison
3. `minutes_late` property - Same timezone-aware comparison

**Technical Details:**
- Uses `pytz.timezone(self.user.preferences.timezone)` to get user's timezone
- Converts `taken_at.astimezone(user_tz)` for UTC → local conversion
- Creates `scheduled_local = user_tz.localize(scheduled_dt)` for proper timezone-aware scheduled time
- Compares both timezone-aware datetimes correctly

**Files Modified:**
- `apps/health/models.py` - Updated `mark_taken()`, `was_on_time`, and `minutes_late` in `MedicineLog` class

**Related:** This is a companion fix to the earlier "Taken At" display fix. The display fix showed the correct time in the UI, but this fix ensures the status (Taken/Taken Late) is also correctly calculated.

---

### Medicine "Taken At" Time Now Displays in User's Timezone

Fixed medicine history showing "Taken Late" incorrectly because the `taken_at` time was being displayed in UTC instead of the user's configured timezone.

**Issue:**
- The `taken_at` field on MedicineLog is a DateTimeField stored in UTC
- When displayed in templates, Django's `time` filter was showing UTC time
- For users in America/New_York (EST/EDT, UTC-5), a medicine taken at 9:24 AM local time was showing as "1:24 PM" (UTC)
- This caused medicines taken on time to appear as "Taken Late"

**Fix:**
1. Added `user_timezone` to the theme context processor so templates can access the user's timezone
2. Used Django's `{% timezone %}` template tag to convert `taken_at` datetimes to user's local time
3. Updated both `medicine_detail.html` and `history.html` templates

**Files Modified:**
- `apps/core/context_processors.py` - Added `user_timezone` to template context
- `templates/health/medicine/medicine_detail.html` - Added `{% load tz %}` and wrapped `taken_at` in timezone tag
- `templates/health/medicine/history.html` - Added `{% load tz %}` and wrapped `taken_at` in timezone tag

**Technical Details:**
- The `scheduled_time` fields are stored as TimeField (no timezone), so they don't need conversion - they represent the desired local schedule time
- Only `taken_at` (DateTimeField stored in UTC) needed the timezone conversion

**Test Results:** 86 medicine tests pass

---

### Documentation Reorganization

Reorganized all project documentation files into a clean, consistent structure in the `docs/` directory.

**Changes Made:**
- Created `docs/` subdirectory for all project documentation
- Renamed all documentation files to follow consistent naming convention: `wlj_<category>_<descriptor>.md`
- Updated `CLAUDE.md` to reference new file locations
- Added `docs/README.md` as documentation index
- Deleted temporary artifact files (test_summary.txt, test_errors.txt, etc.)

**New Naming Convention:**
| Old Name | New Name |
|----------|----------|
| `CLAUDE_CHANGELOG.md` | `docs/wlj_claude_changelog.md` |
| `CLAUDE_FEATURES.md` | `docs/wlj_claude_features.md` |
| `CLAUDE_BEACON.md` | `docs/wlj_claude_beacon.md` |
| `BACKUP.md` | `docs/wlj_backup.md` |
| `BACKUP_REPORT.md` | `docs/wlj_backup_report.md` |
| `SECURITY_REVIEW_REPORT.md` | `docs/wlj_security_review.md` |
| `SYSTEM_AUDIT_REPORT.md` | `docs/wlj_system_audit.md` |
| `SYSTEM_REVIEW.md` | `docs/wlj_system_review.md` |
| `THIRD_PARTY_SERVICES.md` | `docs/wlj_third_party_services.md` |
| `docs/CAMERA_SCAN_ARCHITECTURE.md` | `docs/wlj_camera_scan_architecture.md` |

**Naming Convention Rules:**
- All files start with `wlj_` prefix
- Categories: `claude_*`, `backup_*`, `security_*`, `system_*`, `third_party_*`, `camera_*`
- Use lowercase with underscores
- Example: `wlj_claude_changelog.md`

**Files Kept at Root:**
- `CLAUDE.md` - Remains at root for Claude Code discovery
- `README.md` - Standard project README

**Temporary Files Deleted:**
- `test_summary.txt`
- `test_errors.txt`
- `app_diffs.txt`

---

*Last updated: 2026-01-01*
