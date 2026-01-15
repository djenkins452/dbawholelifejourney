# ==============================================================================
# File: docs/wlj_claude_changelog.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Historical record of fixes, migrations, and changes
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-12-28
# Last Updated: 2026-01-12 (CISO Security Review - Comprehensive Security Hardening)
# ==============================================================================

# WLJ Change History

This file contains the historical record of all fixes, migrations, and significant changes.
For active development context, see `CLAUDE.md` (project root).

---

## 2026-01-15 Changes

### Add Cycle Section to Dashboard (Phase 7)

**Summary:** Integrated cycle tracking into the main WLJ dashboard for users with cycle tracking enabled.

**Features:**
- Conditional cycle widget on dashboard (only shows if user has cycle_tracking_enabled=True)
- Displays current cycle day and phase name with color indicator
- Quick period toggle buttons ("Period started" / "Period ended")
- HTMX-powered toggle that updates without page reload
- "Log Details" link to cycle dashboard for full logging
- Period status indicator when logged

**Backend Changes:**
- `apps/dashboard/views.py`: Added cycle tracking data to `_get_health_data()`
  - Imports CycleSettings, Cycle, CycleDailyLog
  - Gathers phase info, current cycle, today's log
  - Returns `cycle_tracking_enabled` and `cycle_data` context
- `apps/health/views_cycle.py`: Added `CyclePeriodToggleView` for HTMX toggle
  - Handles "start" action: creates daily log with flow level, starts new cycle if needed
  - Handles "end" action: marks period as ended, updates cycle period_end_date
  - Returns HTML fragment for HTMX replacement

**Files Created:**
- `templates/health/cycle/includes/period_toggle_status.html`

**Files Modified:**
- `templates/dashboard/home.html` - Added cycle tracking section
- `apps/dashboard/views.py` - Added cycle data gathering
- `apps/health/views_cycle.py` - Added CyclePeriodToggleView
- `apps/health/urls.py` - Added cycle_period_toggle URL
- `static/css/dashboard.css` - Added cycle widget styles

---

### Create Symptom/Mood Trend Charts Component (Phase 6)

**Summary:** Created interactive chart components for visualizing symptom and mood patterns across menstrual cycles.

**Template:** `templates/health/cycle/includes/trend_charts.html`

**Features:**
- Symptom frequency horizontal bar chart showing top 8 symptoms
- Mood distribution stacked bar chart by cycle phase (menstrual, follicular, ovulation, luteal)
- Configurable date range selection (1, 3, 6 months) with HTMX refresh
- Chart.js integration with dynamic loading
- Colorblind-accessible Wong palette variant colors
- Mobile-responsive chart sizing (max-height constraints)
- Accessible data tables as `<details>` elements for screen readers
- Graceful degradation with `<noscript>` fallback showing text summary
- Empty states with helpful messages when no data available

**Technical Notes:**
- Uses CDN-loaded Chart.js 4.4.1
- Data passed via Django template context and rendered as JSON
- Wong palette colors for colorblind accessibility:
  - Blue: #0072B2, Orange: #E69F00, Green: #009E73
  - Yellow: #F0E442, Sky Blue: #56B4E9, Vermillion: #D55E00
  - Purple: #CC79A7

**Files Created:** `templates/health/cycle/includes/trend_charts.html`

---

### Update Cycle Tracking Opt-In Status Display (Phase 6)

**Summary:** Updated the cycle tracking opt-in page to show status when already enabled and provide disable functionality.

**Features Added:**
- Status display when cycle tracking is already enabled
- "Enabled based on your profile" message when auto-enabled from gender signal
- Disable button with confirmation modal dialog
- Inclusive message: "Anyone can use this feature regardless of gender"
- Link to preferences page to update gender settings
- Modal with cancel/confirm actions for disabling
- Proper JavaScript handling for modal open/close/escape key
- API integration with opt-out endpoint

**View Updates:**
- `CycleOptInPageView`: Added context for `is_enabled`, `was_auto_enabled`, and `user_gender`

**Files Modified:**
- `templates/health/cycle/opt_in.html` - Added status section, disable modal, inclusive message, CSS styles, and JavaScript handlers
- `apps/health/views_cycle.py` - Updated `CycleOptInPageView` to pass auto-enable context

---

### Create Cycle Dashboard Page (Phase 6)

**Summary:** Created the main cycle tracking dashboard as the central hub for the feature.

**Template:** `templates/health/cycle/dashboard.html`

**Features:**
- Cycle summary card displayed prominently at top (via include)
- Recent 7 days of logs list with:
  - Flow level badges (color-coded)
  - Mood emoji display
  - Symptom count
  - Energy level indicator
  - Edit button for each log
  - Today's log highlighted
- Quick actions grid:
  - Log Today (opens modal)
  - Calendar (placeholder link)
  - Statistics (links to API endpoint)
- Floating Action Button (FAB) for quick log entry
- Modal with daily log form component
- Empty state for new users with:
  - Feature benefits list
  - "Get Started" button linking to opt-in page
- Mobile-responsive layout

**Views Added:**
- `CycleDashboardView`: Loads cycle data and recent logs for dashboard
- `CycleOptInPageView`: Renders opt-in page, redirects if already enabled

**URLs Added:**
- `/health/cycle/` -> `cycle_dashboard`
- `/health/cycle/opt-in/` -> `cycle_opt_in_page`

**Files Created:** `templates/health/cycle/dashboard.html`
**Files Modified:** `apps/health/views_cycle.py`, `apps/health/urls.py`

---

### Create Cycle Summary Card Component (Phase 6)

**Summary:** Created component showing current cycle status at a glance.

**Template:** `templates/health/cycle/includes/summary_card.html`

**Features:**
- Large prominent cycle day display (2.5rem font, gradient background)
- Color-coded phase indicator with dot matching phase:
  - Menstrual (red #E53935)
  - Follicular (orange #FFB300)
  - Ovulation (green #43A047)
  - Luteal (blue #1E88E5)
- Prediction countdown with multiple states:
  - Period late: warning message with reassurance
  - Period expected today: alert styling
  - Period coming soon (1-3 days): warning styling
  - Period upcoming (4+ days): standard countdown with date
  - No prediction: encouraging message to log more cycles
- Empty state for no active cycle with helpful message
- HTMX refresh: `hx-trigger="daily-log-saved from:body"`
- Mobile-responsive: stacks vertically on mobile, side-by-side on desktop

**Files Created:** `templates/health/cycle/includes/summary_card.html`

---

### Create Daily Log Form Component (Phase 6)

**Summary:** Created reusable form component for daily cycle logging with mobile-first design.

**Template:** `templates/health/cycle/includes/daily_log_form.html`

**Features:**
- Flow level selector with large tap-friendly buttons (64px min-height):
  - Color-coded indicators: none (gray), spotting (yellow), light (pink), medium (red), heavy (dark red)
- Symptoms as multi-select emoji chips:
  - Cramps, headache, fatigue, bloating, tenderness, acne, backache, nausea, cravings, insomnia
- Mood selector with emoji buttons in 4x2 grid:
  - Happy, calm, energetic, tired, sad, irritable, anxious, emotional
- Energy level as 1-5 button group with descriptive labels
- Optional expandable fields via `<details>` element:
  - Cervical mucus type (dry, sticky, creamy, watery, egg white)
  - Basal body temperature input
  - Notes textarea
- JavaScript form submission:
  - Builds JSON payload from button selections
  - Posts to /health/cycle/api/daily-logs/
  - Shows success animation on save
  - Dispatches 'daily-log-saved' custom event for dashboard refresh
- Mobile-responsive with 44px+ touch targets
- ARIA labels for accessibility

**Files Created:** `templates/health/cycle/includes/daily_log_form.html`

---

### Create Cycle Tracking Opt-In Page (Phase 6)

**Summary:** Created the opt-in template for cycle tracking with privacy-focused messaging.

**Template:** `templates/health/cycle/opt_in.html`

**Features:**
- Gentle, non-clinical language explaining feature benefits
- Clear explanation of data collected:
  - Period days (flow level, start/end dates)
  - Mood and energy tracking
  - Physical symptoms (cramps, headache, fatigue, etc.)
  - Predictions (after enough cycles logged)
- Privacy assurances section:
  - Data never shared with anyone
  - Stored securely with encryption
  - Easy one-click deletion
  - No advertising or third-party data sales
- Link to privacy policy
- Mobile-responsive design with 44px+ touch targets
- Single "Enable Cycle Tracking" button
- JavaScript handles API call to /health/cycle/api/opt-in/
- Redirects to health home on success

**Files Created:** `templates/health/cycle/opt_in.html`

---

### Create CycleStatisticsService (Phase 5)

**Summary:** Created service for calculating cycle statistics and correlations.

**Service:** `CycleStatisticsService` in `apps/health/services/cycle_statistics.py`

**Methods:**
- `get_average_cycle_length(num_cycles, months)`: Average with min/max/std_dev
- `get_average_period_length(num_cycles, months)`: Average with min/max
- `get_symptom_frequency(months)`: Symptom occurrence counts and percentages
- `get_mood_by_cycle_phase(months)`: Correlate moods with phases
- `get_cycle_regularity_score(num_cycles)`: 0-100 score based on std deviation
- `get_trends(num_cycles)`: Detect cycle lengthening/shortening using linear regression
- `get_summary()`: Comprehensive summary of all statistics

**Features:**
- Configurable analysis period (by cycle count or months)
- Regularity ratings: excellent (std<=2), good (std<=4), fair (std<=6), irregular
- Trend detection using linear regression slope
- Mood-by-phase correlation with dominant mood identification
- Symptom frequency with display names and percentages

**Files Created:** `apps/health/services/cycle_statistics.py`
**Files Modified:** `apps/health/services/__init__.py`

---

### Create CyclePredictionService (Phase 5)

**Summary:** Created service for predicting next period and fertile window using weighted moving averages.

**Service:** `CyclePredictionService` in `apps/health/services/cycle_prediction.py`

**Methods:**
- `generate_prediction(save=True)`: Generate new prediction from historical data
- `can_generate_prediction()`: Check if prediction is possible (min 3 cycles)
- `get_latest_prediction()`: Get most recent prediction
- `get_prediction_accuracy_stats()`: Calculate accuracy metrics from past predictions

**Features:**
- Weighted moving average: recent cycles weighted higher (3x, 2.5x, 2x, etc.)
- Uses last 3-6 completed cycles for prediction
- Confidence scores based on cycle regularity (standard deviation)
- Fertile window calculation adjusted for user's cycle length
- Returns None if fewer than 3 completed cycles
- Algorithm version tracking (v1.0-wma)

**Confidence Levels:**
- High: 80%+ (std dev <= 2 days)
- Medium: 60-79% (std dev 3-4 days)
- Low: 40-59% (std dev 5-6 days)
- Very Low: <40% (std dev 7+ days)

**Files Created:** `apps/health/services/cycle_prediction.py`
**Files Modified:** `apps/health/services/__init__.py`

---

### Create cycle phase calculator (Phase 5)

**Summary:** Created service function to calculate current cycle phase based on cycle day.

**Service:** `cycle_phase.py` in `apps/health/services/`

**Functions:**
- `get_current_phase(user, reference_date)`: Returns current phase info or None
- `get_phase_by_day(cycle_day, cycle_length)`: Get phase for specific cycle day
- `get_all_phases(cycle_length)`: Get all phase boundaries for a cycle length

**Phases Defined:**
- Menstrual (days 1-5): Red, bleeding phase
- Follicular (days 6-13): Orange, pre-ovulation
- Ovulation (days 14-16): Green, peak fertility
- Luteal (days 17-28): Blue, post-ovulation

**Features:**
- Proportionally adjusts phase lengths for non-28-day cycles
- Returns phase name, display_name, description, day_in_phase, total_phase_days
- Includes color codes (hex and name) for UI display
- Returns None if user not in active cycle or tracking disabled
- Handles extended luteal phase gracefully

**Files Created:** `apps/health/services/cycle_phase.py`
**Files Modified:** `apps/health/services/__init__.py`

---

### Create CycleDataExportService (Phase 5)

**Summary:** Created service for exporting cycle tracking data in JSON and CSV formats.

**Service:** `CycleDataExportService` in `apps/health/services/cycle_export.py`

**Methods:**
- `export_to_json()`: Full JSON export with settings, daily logs, cycles, predictions
- `export_to_json_string()`: JSON export as string
- `export_to_csv()`: CSV export for spreadsheets (daily_logs, cycles, or predictions)
- `get_export_size_estimate()`: Estimate export size and check pagination needs

**Features:**
- ISO 8601 date formatting throughout
- File size limits with pagination support (1000 daily logs, 100 cycles, 50 predictions max)
- No user PII in export metadata
- Flattened CSV structure for spreadsheet compatibility
- Symptoms list converted to comma-separated string in CSV
- Export version tracking for data compatibility

**Files Created:** `apps/health/services/cycle_export.py`
**Files Modified:** `apps/health/services/__init__.py`

---

### Create CycleDetectionService (Phase 5)

**Summary:** Created service for automatic period detection from daily logs.

**Service:** `CycleDetectionService` in `apps/health/services/cycle_detection.py`

**Methods:**
- `process_daily_log()`: Main entry point, analyzes a log and updates cycles
- `_check_period_start()`: Detects if flow indicates new period start
- `_check_period_end()`: Detects period end after 2+ no-flow days
- `_create_new_cycle()`: Creates new Cycle, closes previous
- `_update_period_end()`: Sets period_end_date on current cycle
- `recalculate_cycles()`: Rebuilds all cycles from logs (admin utility)

**Features:**
- Automatically detects period start when flow changes from none to light/medium/heavy
- Detects period end after 2+ consecutive days of no flow
- Handles spotting intelligently (doesn't trigger new period)
- Creates new Cycle when period starts, closes previous cycle
- Updates period_end_date when period ends
- Connected to DailyLog post_save signal in apps.py

**Files Created:** `apps/health/services/cycle_detection.py`
**Files Modified:** `apps/health/services/__init__.py`, `apps/health/apps.py`, `apps/health/views_cycle.py`

---

### Create CyclePredictionViewSet (Phase 4)

**Summary:** Created ViewSet for cycle predictions with regenerate capability.

**Views:**
- `CyclePredictionViewSet`: ViewSet for predictions
  - `list`: List all predictions with pagination
  - `retrieve`: Get single prediction by ID
  - `current`: Get latest active prediction with days until period and status
  - `regenerate`: Generate new prediction from cycle data (POST)

**Features:**
- Minimum 3 completed cycles required for predictions
- Regenerate calculates predictions based on average cycle/period length
- Confidence score based on data consistency (std deviation)
- Fertile window predictions when enabled in user settings
- Algorithm version tracking (v1.0-basic)
- Status messages: overdue, today, soon, upcoming

**Endpoints Added:**
- `/health/cycle/api/predictions/` - List predictions
- `/health/cycle/api/predictions/<id>/` - Retrieve prediction
- `/health/cycle/api/predictions/current/` - Get current prediction
- `/health/cycle/api/predictions/regenerate/` - Generate new prediction

**Files Modified:** `apps/health/views_cycle.py`, `apps/health/urls.py`

---

### Add URL Routing for Cycle API (Phase 4)

**Summary:** Configured URL routing for all cycle tracking API endpoints.

**Endpoints Added:**
- `/health/cycle/api/daily-logs/` - List/create daily logs
- `/health/cycle/api/daily-logs/<id>/` - Retrieve/update/delete daily logs
- `/health/cycle/api/cycles/` - List cycles
- `/health/cycle/api/cycles/<id>/` - Retrieve cycle
- `/health/cycle/api/cycles/current/` - Get current ongoing cycle
- `/health/cycle/api/cycles/statistics/` - Get cycle statistics and trends

**Documentation:**
- Added comprehensive API documentation comments in urls.py
- Placeholder routes commented for predictions endpoint (to be implemented)

**Files Modified:** `apps/health/urls.py`

---

### Create CycleDailyLogViewSet (Phase 4)

**Summary:** Created full CRUD ViewSet for daily cycle logging with validation.

**Views:**
- `CycleDailyLogViewSet`: Full CRUD ViewSet for daily logs
  - `list`: List all daily logs with pagination (30/page default, max 100)
  - `retrieve`: Get single daily log by ID
  - `create`: Create new daily log (validates future dates, checks for duplicates)
  - `update/partial_update`: Update existing log
  - `destroy`: Soft delete a log

**Features:**
- Date range filtering via start_date and end_date query params
- Validates log_date is not in the future
- Prevents duplicate logs for same date (returns error with suggestion to use PUT)
- Period detection service hook (placeholder for future implementation)
- Uses CycleTrackingEnabledMixin to return 404 if tracking not enabled

**Files Modified:** `apps/health/views_cycle.py`

---

### Create CycleViewSet (Phase 4)

**Summary:** Created read-only API view for cycle history with statistics endpoint.

**Views:**
- `CycleViewSet`: Read-only ViewSet for cycle history
  - `list`: List all cycles with pagination (10/page default, max 50)
  - `retrieve`: Get single cycle by ID with daily logs
  - `current_cycle`: Get the ongoing cycle with days_since_start
  - `statistics`: Get cycle averages, trends, and regularity score

**Features:**
- Date range filtering via start_date and end_date query params
- Pagination with page and page_size params
- Optional include_logs param for nested daily logs in list
- Statistics include: average/min/max cycle length, regularity score (0-100), trend analysis (lengthening/shortening/stable), recent cycles summary

**Files Modified:** `apps/health/views_cycle.py`

---

### Create CycleSettingsViewSet (Phase 4)

**Summary:** Created API views for managing cycle tracking settings with opt-in/out control.

**Views:**
- `CycleSettingsViewSet`: GET/PUT/PATCH for settings retrieval and update
- `CycleOptInView`: POST to enable cycle tracking (creates or reactivates settings)
- `CycleOptOutView`: POST to disable tracking (optional data deletion with confirmation)
- `CycleSettingsCheckView`: GET quick status check for UI feature toggles

**Mixins:**
- `CycleTrackingEnabledMixin`: Returns 403 if cycle tracking not enabled

**URL Patterns:**
- `/health/cycle/api/settings/` - Settings CRUD
- `/health/cycle/api/opt-in/` - Enable tracking
- `/health/cycle/api/opt-out/` - Disable tracking
- `/health/cycle/api/check/` - Quick status check

**Files Created:** `apps/health/views_cycle.py`
**Files Modified:** `apps/health/urls.py`

---

### Create Serializers for Cycle Models (Phase 4)

**Summary:** Created serializers module for all cycle tracking models.

**Serializers:**
- `CycleSettingsSerializer`: User preferences with cycle/period length validation
- `CycleDailyLogSerializer`: Daily logs with symptom list and mood choice validation
- `CycleSerializer`: Cycles with nested daily logs support (read-only)
- `CyclePredictionSerializer`: Predictions with confidence formatting

**Features:**
- DRF-like interface (`.data`, `.is_valid()`, `.save()`)
- Consistent date format (YYYY-MM-DD)
- Validation messages for invalid symptom/mood choices
- Computed properties included in serialization

**Note:** Uses Django core (no DRF dependency) but follows DRF patterns for easy migration.

**Files Created:** `apps/health/serializers.py`

---

### Admin Filters and Actions for Cycle Tracking (Phase 3)

**Summary:** Added custom admin filters and bulk export action for cycle data management.

**Custom Filters:**
- `AverageCycleLengthFilter`: Filter by short/normal/long cycle lengths
- `LastLogDateFilter`: Filter daily logs by today/week/month/older
- `CycleDateRangeFilter`: Filter cycles by current/3months/6months/year

**Bulk Action:**
- `export_cycle_data_for_support`: Export selected cycles as CSV for support review

**Files Modified:** `apps/health/admin.py`

---

### Register Cycle Models in Admin (Phase 3)

**Summary:** Added Django admin configuration for all cycle tracking models.

**Admin Classes:**
- `CycleSettingsAdmin`: list_display for user, tracking enabled, cycle/period lengths
- `CycleDailyLogAdmin`: list_display for user, log_date, flow_level, mood; date_hierarchy
- `CycleAdmin`: list_display for user, cycle_number, dates, lengths; cycle_length_display method
- `CyclePredictionAdmin`: list_display for user, prediction dates, confidence, is_verified method

**All models have:**
- `search_fields = ["user__email"]` for user search
- `raw_id_fields = ["user"]` for performance
- Appropriate `list_filter` options

**Files Modified:** `apps/health/admin.py`

---

### Create CyclePrediction Model (Phase 2)

**Summary:** Created CyclePrediction model for storing AI-generated cycle predictions.

**Model Fields:**
- `predicted_period_start`, `predicted_period_end`: Expected period dates
- `predicted_fertile_window_start`, `predicted_fertile_window_end`: Expected fertile window (nullable)
- `prediction_confidence`: DecimalField (0.00 to 1.00)
- `prediction_algorithm_version`: Version string for traceability
- `generated_at`: When prediction was created
- `actual_period_start`: Filled when period actually starts (for accuracy tracking)

**Class Methods:**
- `get_active_prediction(user)`: Returns most recent unverified prediction

**Properties:**
- `accuracy`: Days difference between predicted and actual (+ = late, - = early)
- `is_verified`: True if actual_period_start is set
- `accuracy_percentage`: 100% minus 10% per day off

**Migration:** `0025_add_cycleprediction_model.py`

---

### Auto-enable Cycle Tracking for Female Users (Phase 2)

**Summary:** Created signal handler to auto-enable cycle tracking when a user sets their gender to female.

**Signal Behavior:**
- When gender is set to 'female', auto-create CycleSettings with `cycle_tracking_enabled=True`
- If CycleSettings already exists, respect existing settings (don't override)
- Changing gender FROM female does NOT delete existing CycleSettings
- For male/prefer_not_to_say/None, do NOT auto-create CycleSettings

**Files Modified:**
- `apps/users/signals.py`: Added `auto_enable_cycle_tracking_for_female` signal handler
- `apps/users/tests/test_signals.py`: Created with 5 tests for signal behavior

---

### Verify Cycle Model Migrations (Phase 2)

**Summary:** Verified all cycle tracking model migrations are complete.

**Migration Files:**
- `0022_add_cyclesettings_model.py`: CycleSettings model
- `0023_add_cycledailylog_model.py`: CycleDailyLog model
- `0024_add_cycle_model.py`: Cycle model

All migrations were created during individual model tasks. No additional migration work needed.

---

### Create Cycle Model (Phase 2)

**Summary:** Created Cycle model for tracking complete menstrual cycles.

**Model Fields:**
- `cycle_number`: Auto-incremented per user ("Cycle #5")
- `start_date`: First day of period
- `end_date`: Day before next period (nullable)
- `period_end_date`: Last day of bleeding (nullable)
- `is_predicted`: True if AI-predicted
- `notes`: User observations

**Properties:**
- `cycle_length`: Days in full cycle
- `period_length`: Days of period
- `is_complete`, `is_ongoing`: Status checks

**Auto-numbering:** cycle_number auto-assigned on save, incrementing per user.

**Files Modified:**
- `apps/health/models.py`: Added Cycle model
- `apps/health/migrations/0024_add_cycle_model.py`: New migration

---

### Create CycleDailyLog Model (Phase 2)

**Summary:** Created CycleDailyLog model for recording daily menstrual cycle data.

**Model Fields:**
- `log_date`: Date of entry (unique per user)
- `flow_level`: Flow intensity from FLOW_LEVEL_CHOICES
- `symptoms`: JSONField for multi-select symptom list
- `mood`: Emotional state from CYCLE_MOOD_CHOICES
- `energy_level`: 1-5 scale (optional)
- `cervical_mucus`: Fertility indicator (optional) - added CERVICAL_MUCUS_CHOICES
- `basal_temp`: Body temperature (optional)
- `notes`: Free-form observations

**Properties:**
- `is_period_day`: True if any flow (not 'none')
- `symptom_display_list`: Human-readable names
- `flow_emoji`, `mood_emoji`: UI display

**Constraints:**
- `unique_cycle_log_per_user_per_day`: One entry per user per day
- Indexed on user + log_date

**Files Modified:**
- `apps/health/models.py`: Added CycleDailyLog model and CERVICAL_MUCUS_CHOICES
- `apps/health/migrations/0023_add_cycledailylog_model.py`: New migration

---

### Add Cycle Tracking Choice Definitions (Phase 2)

**Summary:** Defined standard choice constants for cycle tracking symptoms, moods, and flow levels.

**Constants Added:**
- `CYCLE_SYMPTOM_CHOICES`: 10 physical symptoms (cramps, headache, fatigue, bloating, breast_tenderness, acne, backache, nausea, food_cravings, insomnia)
- `CYCLE_MOOD_CHOICES`: 8 emotional states (happy, sad, irritable, anxious, calm, energetic, tired, emotional)
- `FLOW_LEVEL_CHOICES`: 5 flow intensities (none, spotting, light, medium, heavy)
- Emoji mappings for all choices (CYCLE_SYMPTOM_EMOJIS, CYCLE_MOOD_EMOJIS, FLOW_LEVEL_EMOJIS)

**Files Modified:**
- `apps/health/models.py`: Added choice constants after CycleSettings model

**Note:** These choices differ from journal MOOD_CHOICES (great/good/okay/low/difficult) as they're designed for physical/emotional tracking during menstrual cycles.

---

### Create CycleSettings Model (Phase 2)

**Summary:** Created CycleSettings model for menstrual cycle tracking preferences.

**Model Structure:**
- Extends SoftDeleteModel with OneToOne relationship to User
- `cycle_tracking_enabled`: Master toggle (default False)
- `average_cycle_length`: Days in typical cycle (default 28)
- `average_period_length`: Days in typical period (default 5)
- `notifications_enabled`: Send prediction reminders (default True)
- `fertile_window_tracking_enabled`: Track fertile window (default False)
- `last_period_start_date`: Most recent period start (nullable)

**Properties:**
- `is_enabled`: Quick check combining is_active and cycle_tracking_enabled

**Files Modified:**
- `apps/health/models.py`: Added CycleSettings model
- `apps/health/migrations/0022_add_cyclesettings_model.py`: New migration

**Purpose:** Foundation model for WLJ Cycle Tracking Module Phase 2.

---

### Add Gender Field to UserPreferences Model

**Summary:** Added a gender field to the UserPreferences model to support personalized health features like cycle tracking.

**Changes:**
- Added `GENDER_CHOICES` constant with three options: male, female, prefer_not_to_say
- Added `gender` CharField to UserPreferences with:
  - `blank=True, null=True` for existing users
  - `help_text` explaining usage for personalized health features

**Files Modified:**
- `apps/users/models.py`: Added GENDER_CHOICES and gender field
- `apps/users/migrations/0036_add_gender_to_userpreferences.py`: New migration

**Purpose:** Enables conditional enabling of cycle tracking features for users who identify as female (part of WLJ Cycle Tracking Module).

---

### Add Gender Selection to Onboarding Wizard

**Summary:** Added a new "About You" step to the onboarding wizard flow for gender selection.

**Features:**
- Large tap-friendly radio buttons (44px+ touch targets) for mobile
- Three options: Male, Female, Prefer not to say
- Skip option to proceed without selecting
- Friendly explanation about health feature personalization
- Responsive CSS for mobile devices

**Files Modified:**
- `apps/users/views.py`: Added gender step to ONBOARDING_STEPS, get_context_data, and post handler
- `templates/users/onboarding_wizard.html`: Added gender step HTML and CSS (188 lines)
- `apps/users/tests/test_onboarding_wizard.py`: Updated expected step order

**Purpose:** Part of WLJ Cycle Tracking Module - allows users to optionally select gender during onboarding to enable personalized health features.

---

### Add Gender Selection to Preferences Page

**Summary:** Added a "Personal Information" section to the preferences page with a gender dropdown.

**Features:**
- Dropdown with options: Male, Female, Prefer not to say (plus empty option)
- Pre-populated with current UserPreferences value
- Privacy note explaining how gender data is used
- Uses existing form submission (Save Changes button)

**Files Modified:**
- `apps/users/forms.py`: Added gender field to PreferencesForm fields and widgets
- `templates/users/preferences.html`: Added Personal Information accordion section

**Purpose:** Part of WLJ Cycle Tracking Module - allows users to update their gender selection at any time from settings.

---

### Data Migration Strategy for Existing Users (Gender Field)

**Summary:** Implemented migration strategy for existing users where gender field will be null.

**Implementation:**
- Migration 0036 already sets `null=True, blank=True` so existing users get `gender=None`
- Added nudge banner in preferences that shows when gender is not set
- Documented null gender handling in model comments
- UI gracefully handles null: shows "Not set" badge, prompts user to set if desired

**Files Modified:**
- `apps/users/models.py`: Added documentation comments for null handling
- `templates/users/preferences.html`: Added nudge banner for users without gender set

**Usage Note:** Code checking gender must handle None gracefully. For cycle tracking: `if prefs.gender == 'female'`

---

### Fix Audio Email - Optional Message Field Causing Error

**Summary:** Fixed bug where sending an audio capture email with a blank message body would fail with an AttributeError.

**Problem:** When a user left the optional "Personal Message" field empty in the email modal, JavaScript would send `message: null` in the JSON body. The Python backend's `.strip()` call would fail because `NoneType` has no `.strip()` attribute:
```python
message = data.get('message', '').strip()  # Fails if value is None (not missing)
```

**Root Cause:** `data.get('message', '')` returns the default `''` only when the key is missing. When the key exists with value `None`, it returns `None`, and `None.strip()` raises AttributeError.

**Solution:** Changed the extraction logic to handle both missing keys and explicit null values:
```python
message = (data.get('message') or '').strip()
```

This uses `or ''` to convert any falsy value (None, empty string, missing key) to an empty string before calling `.strip()`.

**Files Modified:**
- `apps/capture/views.py`: Fixed line 1015-1016 to handle null values for recipient_email and message
- `apps/capture/tests/test_email.py`: Added `test_email_with_null_message` test case

---

## 2026-01-14 Changes

### Fix Assistant Chat Mobile Responsiveness

**Summary:** Fixed the assistant chat drawer layout on iPhone - messages were being cut off on the left side due to insufficient mobile CSS adjustments.

**Problem:** On narrow iPhone screens, the chat bubbles appeared cut off because:
1. Container padding was 20px on mobile (too wide)
2. Message max-width of 85% didn't account for reduced mobile space
3. No mobile-specific adjustments for font size, button sizes, or input area

**Solution:** Added comprehensive mobile breakpoint styles (max-width: 480px):
- Reduced messages container padding from 20px to 12px
- Increased message max-width from 85% to 90%
- Set input font-size to 16px (prevents iOS auto-zoom on focus)
- Reduced header padding and hide subtitle text on mobile
- Smaller send button and input area padding
- Adjusted empty state and clear dialog positioning

**Files Modified:**
- `templates/components/chat_widget.html`: Extended @media (max-width: 480px) with mobile-optimized styles

---

### Comprehensive Mobile Responsiveness Fixes

**Summary:** Added @media queries to 18 templates across all modules to improve mobile responsiveness on phones.

**Problem:** Audit revealed ~67 user-facing templates had inline CSS styles but lacked mobile breakpoints, causing layout issues on narrow screens.

**Solution:** Added mobile CSS (max-width: 640px) breakpoints to high-priority templates:

**Journal (5 files):**
- `entry_form.html`: Stack form actions, adjust emotion buttons
- `prompt_list.html`: Single column grid, scrollable filters
- `tag_list.html`: Stack tag items vertically
- `tag_form.html`: Stack color picker and form actions
- `partials/tag_create_modal.html`: Responsive modal for mobile

**Faith (5 files):**
- `home.html`: Single column faith grid, stack card headers
- `prayer_list.html`: Stack page header and prayer actions
- `reflections.html`: Stack entry headers
- `milestone_list.html`: Adjust timeline for mobile
- `todays_verse.html`: Scale down text and stack buttons

**Health (4 files):**
- `medicine/medicine_list.html`: Stack headers, scrollable tabs
- `nutrition/quick_add.html`: Single column form, full-width buttons
- `providers/provider_list.html`: Stack provider cards
- `fitness/progress.html`: Single column stats, scrollable tables

**Life (2 files):**
- `home.html`: Single column grid, stack stats, 2-col quick links
- `project_list.html`: Single column grid, stack filters

**Users (2 files):**
- `theme_selection.html`: Single column theme cards
- `onboarding.html`: Scaled down icons and text for mobile

**Also Added:** Responsive Design requirements section to CLAUDE.md for future development.

---

### Add ffmpeg for 60-Minute Audio Support & Download Button

**Summary:** Added ffmpeg to Railway deployment to enable compression of large audio files, and added a download button to the error state so users can save their recording locally when processing fails.

**Problem:**
1. 16-minute and longer recordings were failing with "audio file is too large" because ffmpeg wasn't installed on Railway
2. When processing failed, users had no way to save their recording to their device

**Solution:**
1. Added ffmpeg to nixpacks.toml so it's installed during Railway deployment
2. Added "Download Recording to Device" button on the error screen
3. Improved error messages to be more helpful

**Files Modified:**
- `nixpacks.toml`: Added `[phases.setup]` with `nixPkgs = ["ffmpeg"]`
- `templates/capture/capture_record.html`: Added download button container and updated showError() to create download link
- `apps/capture/services/transcription.py`: Improved error messages for compression failures

**Behavior:**
- Recording failures now show a prominent "Download Recording to Device" button
- Users can save their recording locally and upload it later via the Upload page
- With ffmpeg now available, 60-minute recordings can be compressed to meet Whisper's 25MB limit

---

### CRITICAL: Prevent Audio Recording Loss on Upload Failure

**Summary:** Fixed critical bug where audio recordings were permanently lost when upload failed (e.g., 502 timeout). Users can now retry failed uploads without losing their recording, and recordings are automatically recovered if the page is refreshed.

**Problem:** When a user recorded a long sermon/meeting and hit a 502 error during upload:
1. The "Try Again" button called `discardRecording()` which destroyed the audio blob
2. No backup storage existed - audio was only in JavaScript memory
3. Gunicorn's 30-second default timeout caused 502 errors on long uploads
4. The recording was permanently lost - unacceptable for irreplaceable content like sermons

**Solution:**
1. **IndexedDB Backup:** Audio blob is now saved to IndexedDB immediately after recording stops
2. **Preserved Retry:** "Try Again" now preserves the audio and returns to preview state for retry
3. **Page Reload Recovery:** On page load, checks for saved recordings and restores them automatically
4. **Increased Timeout:** Gunicorn timeout increased from 30s to 300s (5 minutes) for long uploads
5. **Auto-Cleanup:** IndexedDB backup is cleared after successful upload or explicit discard

**Files Modified:**
- `templates/capture/capture_record.html`:
  - Added IndexedDB helper functions (openDatabase, saveRecordingToIndexedDB, loadRecordingFromIndexedDB, clearRecordingFromIndexedDB)
  - Modified mediaRecorder.onstop to backup audio immediately
  - Modified resetForRetry() to preserve audio and restore from IndexedDB if needed
  - Added checkForSavedRecording() to restore on page load
  - Modified discard button to clear IndexedDB backup
  - Modified successful upload to clear IndexedDB backup
- `Procfile`:
  - Added `--timeout 300` to Gunicorn command

**Behavior:**
- Recording stops → Audio backed up to IndexedDB
- Upload fails → "Try Again" returns to preview with audio intact
- Page refreshed → Recording automatically restored (if within 24 hours)
- User discards → IndexedDB backup cleared
- Upload succeeds → IndexedDB backup cleared

---

### Fix PDF Document Viewing in Organize/Documents

**Summary:** Fixed "Failed to load PDF document" error when viewing uploaded PDFs in the Documents section. PDFs now display correctly in the iframe preview.

**Problem:** PDFs uploaded via Cloudinary's `MediaCloudinaryStorage` were being treated as image resources, but PDFs require "raw" resource type for proper serving. The direct Cloudinary URL was failing to load in the browser iframe.

**Solution:**
1. Created `get_document_storage()` function that returns `RawMediaCloudinaryStorage` for proper PDF/raw file handling
2. Updated Document model's `file` field to use the new storage function
3. Added `DocumentViewInlineView` that serves files inline with correct Content-Type headers
4. Updated document detail template to use the new inline view URL instead of direct Cloudinary URL

**Files Modified:**
- `apps/life/models.py` - Added `get_document_storage()` function, updated Document.file field storage
- `apps/life/views.py` - Added `DocumentViewInlineView` for inline PDF viewing
- `apps/life/urls.py` - Added URL pattern `documents/<pk>/view/` for inline viewing
- `templates/life/document_detail.html` - Changed iframe src to use `document_view_inline` URL

**Technical Details:**
- New documents will be stored using `RawMediaCloudinaryStorage` which uses Cloudinary's "raw" resource type
- The inline view serves files through Django with proper Content-Type headers (application/pdf for PDFs)
- X-Frame-Options is set to SAMEORIGIN to allow iframe embedding
- Existing documents may need to be re-uploaded if they were stored with wrong resource type

---

### Fix X-Frame-Options for PDF Inline Viewing

**Summary:** Fixed "refused to connect" error when viewing PDFs in iframe due to X-Frame-Options being set to 'deny'.

**Problem:** Two issues were preventing PDF viewing:
1. Django's `XFrameOptionsMiddleware` was setting `X-Frame-Options: DENY` globally
2. The view was returning 500 errors when trying to open Cloudinary files

**Solution:**
1. Added `@xframe_options_sameorigin` decorator to `DocumentViewInlineView` to allow same-origin iframe embedding
2. Added proper error handling with fallback to redirect to file URL if direct streaming fails
3. Added logging for troubleshooting file access issues

**Files Modified:**
- `apps/life/views.py` - Added decorator and error handling to `DocumentViewInlineView`

---

### Add File Replacement Option in Document Edit Mode

**Summary:** Added ability to replace the attached file when editing a document without having to delete the entire entry and start over.

**Problem:** Users could only view the current file when editing a document, with no way to replace it. If a wrong file was uploaded, the only option was to delete the entire document and recreate it.

**Solution:**
1. Added "Replace File" button in document edit form that reveals a file upload area
2. Updated `DocumentUpdateView` to include `file` field (optional) and handle file replacement
3. Old files are automatically deleted from storage when replaced

**Files Modified:**
- `templates/life/document_form.html` - Added replace file UI with toggle button and upload area
- `apps/life/views.py` - Updated `DocumentUpdateView` to handle optional file replacement

**UI Features:**
- Current file info displayed with "Replace File" button
- Clicking "Replace File" shows the file upload area
- "Cancel" button to abort replacement and keep current file
- Old file is automatically cleaned up from storage when replaced

---

### Add Pending Model Migrations

**Summary:** Created migrations for model field changes that were detected by CI checks.

**Migrations Added:**
- `apps/health/migrations/0021_alter_dexcomcredential_access_token_and_more.py` - Updated Dexcom credential token fields with encrypted storage help text
- `apps/life/migrations/0008_alter_googlecalendarcredential_access_token_and_more.py` - Updated Google Calendar credential fields with encrypted storage help text
- `apps/finance/migrations/0014_alter_financialaccount_account_type.py` - Updated account_type field with grouped choices (Assets/Liabilities)

**Reason:** CI was failing on `makemigrations --check` because model field definitions had changed but migrations were not committed.

---

### Polish AI Summary Rendering

**Summary:** Fixed AI-generated summaries to display with professional formatting instead of raw markdown syntax. Summaries now render with proper headers, bold text, and bullet lists in the web view, Word document exports, and emails.

**Problem:** AI summaries were displaying raw markdown (e.g., `## BLUF`, `**bold**`, `- bullet`) as literal text instead of being properly formatted, making them look unprofessional and unsuitable for email sharing.

**Solution:**
- Created `render_summary` template filter to convert markdown to styled HTML
- Updated DOCX generator to properly parse markdown and apply Word formatting
- Added comprehensive CSS styling for summary sections

**Files Added:**
- `apps/capture/templatetags/__init__.py` - Package init
- `apps/capture/templatetags/capture_filters.py` - Template filters for summary rendering
- `apps/capture/tests/test_templatetags.py` - 11 tests for template filters

**Files Modified:**
- `templates/capture/capture_detail.html` - Use `render_summary` filter, improved CSS
- `apps/capture/services/docx_generator.py` - Added `_parse_markdown_to_docx()` function

**Rendering Features:**
- `## Section Headers` become styled blue headers with underlines
- `**Bold text**` becomes proper bold formatting
- `- Bullet lists` become proper HTML/Word lists
- Paragraphs properly spaced and styled

---

### Add Capture to Help System

**Summary:** Added comprehensive help system support for the Capture module, including Teaching Tool destinations and a full help topic.

**Teaching Tool Destinations Added (3):**
- `capture-list` (pk 21): Audio Capture list view - keywords: capture, audio, recordings, transcripts, summaries, voice notes, sermon notes, meeting notes
- `capture-record` (pk 22): Record Audio page - keywords: record, record audio, voice recording, microphone, record sermon, record meeting, voice memo
- `capture-upload` (pk 23): Upload Audio page - keywords: upload, upload audio, audio file, mp3, wav, upload recording, import audio

**Help Topic Added:**
- `capture-overview` (pk 22): "Capture: Record, Transcribe, and Summarize Audio" - comprehensive help covering:
  - Recording and uploading audio
  - Categories and subcategories (Faith: Sermon, Bible Study, etc. | Organize: Meeting, Lecture, etc.)
  - What users get (transcript, summary, playback)
  - Filtering and searching recordings
  - Processing status and retry functionality
  - Audio storage and retention
  - Tips for best results
  - How to enable/disable the module

**Files Modified:**
- `apps/help/fixtures/teaching_destinations.json` - Added 3 new destinations
- `apps/help/fixtures/help_topics.json` - Added Capture help topic

---

### Move Capture to Module System

**Summary:** Moved Capture from a permanent menu item to a toggleable module like other features (Health, Journal, etc.). Users can now enable/disable Capture in their preferences.

**Changes:**
- `templates/components/navigation.html`: Moved Capture menu item from between Assistant and Favorites to between Favorites and Journal
- `templates/users/preferences.html`: Added Capture toggle to Active Modules section
- `apps/users/forms.py`: Added `capture_enabled` to UserPreferencesForm fields and widgets
- JavaScript updated to include capture_enabled in module count

**Behavior:**
- When enabled: Shows in menu (between Favorites and Journal), shows on dashboard (microphone quick action + module tile)
- When disabled: Hidden from menu and dashboard
- Default: Enabled (True)

---

### Error Handling and Retry UI for Capture (Task 262)

**Summary:** Implemented user-friendly error states and retry functionality for the Capture feature.

**Error Handling:**
- Added error type detection on CaptureEntry model (mic denied, upload failed, transcription failed, summarization failed, timeout, unknown)
- Created user-friendly error messages with helpful suggestions for each error type
- Updated detail page to show specific error titles and suggestions instead of generic "Processing Failed"
- Added error styling with distinct visual treatment for failed entries

**Retry Functionality:**
- Added `CaptureRetryView` endpoint to re-trigger processing for failed entries
- Retry button only shown for retryable errors (upload, transcription, summarization failures)
- Non-retryable errors (mic denied, timeout) show appropriate messaging
- JavaScript handles retry polling and page reload on success

**Email Notification:**
- Added `send_processing_complete_email` function for delayed processing completion
- Created email template `templates/capture/email/processing_complete.html`
- Added `completion_email_sent_at` field to track notification status
- Email automatically sent when retried processing completes

**Tests Added:**
- `test_error_handling.py` - 29 tests covering:
  - Error type detection (7 tests)
  - User-friendly error messages (4 tests)
  - Retry eligibility (4 tests)
  - Retry view functionality (6 tests)
  - Detail page error display (4 tests)
  - Processing complete email (3 tests)
  - Status API error response (1 test)

**Files Modified:**
- `apps/capture/models.py` - Added error type constants, methods, and completion_email_sent_at field
- `apps/capture/views.py` - Added CaptureRetryView, error_info in context
- `apps/capture/urls.py` - Added retry endpoint
- `apps/capture/tasks.py` - Integrated completion email notification
- `apps/capture/services/email.py` - Added send_processing_complete_email
- `templates/capture/capture_detail.html` - Enhanced error UI and retry button
- `apps/capture/tests/test_email.py` - Updated tests for docx (was PDF)
- `apps/capture/tests/test_integration.py` - Updated expected error messages

---

### Add Filtering and Search to Capture List

**Summary:** Added category/subcategory filtering and title/summary search to the Audio Capture list view. Users can now easily find recordings by filtering by Faith/Organize categories and their subcategories, or by searching for keywords in titles and summaries.

**Features:**
- Category filter dropdown (Faith, Organize, All)
- Subcategory filter dropdown (dynamically updates based on selected category)
- Search box that searches both title and summary content
- Combined filtering and search support
- Active filter indicator showing filtered results count
- Clear Filters button when filters are active
- Filters preserved in pagination links for bookmarking
- Empty state shows different message when filters return no results

**Changes:**
- `apps/capture/views.py`:
  - Updated `CaptureListView.get_queryset()` to filter by category, subcategory, and search query
  - Updated `CaptureListView.get_context_data()` to include filter choices and active filter values
- `templates/capture/capture_list.html`:
  - Added filters bar with category/subcategory dropdowns and search box
  - Added filter summary showing active filters
  - Updated pagination links to preserve filter params
  - Updated empty state for filtered vs. unfiltered
  - Added JavaScript for filter dropdown interactions
- `apps/capture/tests/test_views.py`:
  - Added 15 new tests for filtering and search functionality

---

### Add Cloudinary Audio Storage Support

**Summary:** Added Cloudinary as the audio storage backend for the Capture feature. This uses the existing Cloudinary credentials already configured for image storage, eliminating the need for a separate S3 bucket.

**How it works:**
1. When recording/uploading audio, the frontend sends audio to the server
2. Server uploads to Cloudinary using the video resource type (handles audio)
3. Cloudinary returns a permanent URL for playback
4. Audio files are tagged for 7-day retention tracking

**Changes:**
- Created `apps/capture/cloudinary_storage.py` - Cloudinary upload/delete functions
- Updated `apps/capture/views.py` - Added `CaptureCloudinaryUploadView`, modified submit flow to detect Cloudinary
- Updated `apps/capture/urls.py` - Added cloudinary-upload endpoint
- Updated `templates/capture/capture_record.html` - Handle Cloudinary upload mode
- Updated `templates/capture/capture_upload.html` - Handle Cloudinary upload mode

**Storage Priority:**
1. Cloudinary (if configured) - uses existing credentials
2. S3 (if configured) - requires separate bucket setup
3. Mock mode (no storage) - for development only

---

### Add Play/Download Actions to Capture List

**Summary:** Added action buttons to the Audio Capture list view so users can play and download audio directly without navigating to the detail page.

**Changes:**
- Added play button (opens modal with audio player)
- Added download button (direct download link)
- Existing delete button remains
- Audio modal includes playback controls and close button
- Icons use consistent styling with other action buttons

**Files Modified:**
- `templates/capture/capture_list.html` - Added action icons column, audio modal, and JavaScript
