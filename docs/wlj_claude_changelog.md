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

## 2026-01-20 Changes

### Daily Faith Reminders Scheduled Job (Task 4 from Improvement Backlog)

**New Feature:** Scheduled job to generate in-app and email notifications for prayer and reading plan reminders.

**What's Included:**

1. **New Background Job** (`apps/core/jobs.py`)
   - `generate_faith_reminders()` function calls the management command
   - Logs job start, completion, and any errors

2. **Scheduler Registration** (`config/wsgi.py`)
   - Added Job 7: `generate_faith_reminders` running daily at 6:00 AM UTC (1:00 AM EST)
   - Updated logging to show 7 jobs total, marked SMS jobs as "on hold"

**How It Works:**
- Runs daily at 6 AM UTC
- Creates notifications for prayers with `remind_daily=True` (consolidated per user)
- Creates notifications for active reading plans not yet completed today
- Respects user preferences: `notify_inapp_prayer`, `notify_email_prayer`, `notify_inapp_reading_plan`, `notify_email_reading_plan`
- Email delivery follows user's `email_notification_frequency` setting (immediate or daily_digest)

**Files Modified:**
- `apps/core/jobs.py` - Added generate_faith_reminders function
- `config/wsgi.py` - Added scheduled job, updated job count and logging

---

### Customizable Dashboard (Task 6 from Improvement Backlog)

**New Feature:** User-configurable dashboard with drag-and-drop tile reordering, show/hide toggles, and tile sizing.

**What's Included:**

1. **DashboardConfigService** (`apps/dashboard/services/config_service.py`)
   - 19 configurable tiles with metadata (name, description, icon, module dependency)
   - Methods: get_available_tiles(), get_default_config(), get_visible_tiles()
   - Tile updates: update_tile(), reorder_tiles(), reset_to_defaults()
   - Supports 3 sizes: small, medium, large
   - AI Insights tile marked as mandatory (cannot be hidden)

2. **Dashboard Configuration UI** (`templates/dashboard/configure.html`)
   - Full-page configuration interface
   - Drag-and-drop reordering with visual feedback
   - Checkboxes for show/hide toggles
   - Size selector buttons (S/M/L) per tile
   - Auto-save on changes
   - Reset to defaults button

3. **Setup Banner** (`templates/dashboard/home.html`)
   - Displays for users who haven't customized yet
   - "Customize Now" button links to configure page
   - "Maybe Later" dismisses temporarily
   - Attractive gradient styling

4. **API Endpoints** (`apps/dashboard/urls.py`, `apps/dashboard/views.py`)
   - GET/POST `/dashboard/api/config/` - Full config read/write
   - POST `/dashboard/api/config/reorder/` - Reorder tiles
   - POST `/dashboard/api/config/tile/<id>/` - Update single tile
   - POST `/dashboard/api/setup-banner/dismiss/` - Dismiss banner

5. **Tile Partials** (`templates/dashboard/tiles/`)
   - 19 tile partial templates for modular rendering
   - Each tile supports size classes via `tile-size-{size}`
   - Data attributes for JavaScript interaction

6. **User Preferences** (`apps/users/models.py`)
   - `dashboard_setup_complete` field to track if user completed setup

**Migrations:**
- `apps/users/migrations/0042_dashboard_setup_complete.py` - Setup tracking field
- `apps/core/migrations/0049_configurable_dashboard_release_note.py` - What's New entry

**Teaching Tool Updates:**
- Added "Customize Dashboard" destination

**Configurable Tiles:**
- Quick Stats, Weather, Memory Verse, AI Insights (mandatory)
- Celebrations, Nudges, Weekly Summary, Daily Encouragement
- Current Fast, Cycle Tracking, Quick Actions, Module Cards
- Medicine Schedule, Nutrition Progress, Recent Workouts
- Goal Progress, Upcoming Events, Upcoming Celebrations, Upcoming Bills

**Files Modified:**
- `apps/dashboard/views.py` - Updated ConfigureDashboardView, added API views
- `apps/dashboard/urls.py` - Added configuration API routes
- `templates/dashboard/home.html` - Added setup banner

**New Files:**
- `apps/dashboard/services/__init__.py`
- `apps/dashboard/services/config_service.py`
- `templates/dashboard/configure.html`
- `templates/dashboard/tiles/*.html` (19 tile partials)

---

### In-App Notification System (Task 4 from Improvement Backlog)

**New Feature:** Comprehensive notification system with in-app bell notifications and email digest support.

**What's Included:**

1. **Notification Model** (`apps/core/models.py`)
   - Core model with categories: medicine, task, event, prayer, reading_plan, fasting, significant_event, milestone, finance, journal, system
   - Generic foreign key linking to source objects (ContentType + object_id)
   - Status tracking: is_read, created_at
   - Methods: mark_read(), get_unread_for_user(), mark_all_read(), cleanup_old_notifications()

2. **EmailNotificationTemplate Model** (`apps/admin_console/models.py`)
   - Admin-configurable email templates per category
   - Django template syntax support for subject and body
   - Methods: render_subject(), render_body(), get_template_for_category()

3. **User Preferences** (`apps/users/models.py`)
   - Master toggles: notifications_enabled, email_notifications_enabled
   - Per-category toggles for both in-app and email: notify_inapp_*, notify_email_*
   - email_notification_frequency: immediate or daily_digest
   - notification_reminder_time: single time for reading plan reminders
   - notification_setup_shown: tracks if user saw the one-time notification intro

4. **Notification Service** (`apps/core/services/notification_service.py`)
   - NotificationService class for creating notifications and sending emails
   - Methods: create_notification(), send_immediate_email(), send_daily_digest()
   - Reminder generators: create_prayer_reminders(), create_reading_plan_reminders()
   - Module-aware preference checking (only sends for enabled modules)

5. **Views and URLs** (`apps/core/views.py`, `apps/core/urls.py`)
   - NotificationListView: Full page notification center with pagination
   - API endpoints: unread notifications, mark read, mark all read, count
   - Setup check/dismiss endpoints for one-time intro popup

6. **UI Components**
   - `templates/components/notification_bell.html`: Bell icon with unread badge, dropdown list
   - `templates/core/notifications.html`: Full notification center page
   - `static/js/notifications.js`: JS for bell functionality, auto-refresh every 60 seconds

7. **Email Templates**
   - `templates/core/email/notification_digest.html`: Daily digest email template
   - `apps/admin_console/fixtures/email_notification_templates.json`: Fixture for all category templates

8. **Management Commands**
   - `send_notification_digest`: Sends daily digest emails (intended for 4:45 AM)
   - `generate_daily_reminders`: Creates in-app notifications for prayer/reading plan reminders

9. **Updated Preferences Page** (`templates/users/preferences.html`)
   - In-App Notifications section with master toggle and per-category toggles
   - Email Notifications section with frequency selector and per-category toggles
   - Module-aware: only shows categories for user's enabled modules

**Migrations:**
- `apps/core/migrations/0047_notification_system.py`: Notification model
- `apps/core/migrations/0048_notification_system_release_note.py`: What's New entry
- `apps/admin_console/migrations/0021_notification_system.py`: EmailNotificationTemplate model
- `apps/users/migrations/0041_notification_system.py`: User notification preferences
- `apps/sms/migrations/0003_notification_system.py`: Added milestone category

**Teaching Tool Updates:**
- Added "Notification Center" and "Notification Preferences" destinations

**Test Fixes:**
- `apps/core/tests/test_core_comprehensive.py`: Added required notification fields to preferences test
- `apps/users/tests/test_users.py`: Added required notification fields to preferences POST data

**Files Modified:**
- `apps/core/models.py` - Added Notification model
- `apps/admin_console/models.py` - Added EmailNotificationTemplate model
- `apps/users/models.py` - Added notification preference fields
- `apps/users/forms.py` - Added notification fields to PreferencesForm
- `apps/core/urls.py` - Added notification URL routes
- `apps/core/views.py` - Added notification views
- `templates/components/navigation.html` - Added notification bell include
- `templates/base.html` - Added notifications.js script
- `templates/users/preferences.html` - Added notification preferences sections
- `apps/core/management/commands/load_initial_data.py` - Added email templates fixture

**New Files:**
- `apps/core/services/notification_service.py`
- `templates/components/notification_bell.html`
- `templates/core/notifications.html`
- `static/js/notifications.js`
- `templates/core/email/notification_digest.html`
- `apps/admin_console/fixtures/email_notification_templates.json`
- `apps/core/management/commands/send_notification_digest.py`
- `apps/core/management/commands/generate_daily_reminders.py`
- `apps/help/fixtures/teaching_destinations.json` (updated)

---

### Recurring Transactions Feature (Task 3 from Improvement Backlog)

**New Feature:** Recurring transactions added to the Finance module allowing users to track subscriptions, bills, and regular income automatically.

**What's Included:**

1. **RecurringTransaction Model** (`apps/finance/models.py`)
   - Fields: name, transaction_type (income/expense), amount, account, category, payee, notes
   - Schedule: frequency (daily/weekly/biweekly/monthly/quarterly/yearly/custom), day_of_month, day_of_week, custom_pattern
   - Date range: start_date, end_date, next_due_date
   - Tracking: last_generated_date, total_generated, is_active, is_auto_post
   - Reminders: remind_days_before
   - Properties: signed_amount, is_expense, is_income, recurrence_pattern
   - Methods: calculate_next_due_date, advance_to_next, generate_transaction, get_upcoming_occurrences
   - Uses Life module's RecurrencePattern for consistent pattern handling

2. **RecurringTransactionService** (`apps/finance/services/recurring.py`)
   - get_due_recurring_transactions: Find transactions ready to post
   - process_due_transactions: Batch generate transactions
   - get_upcoming_transactions: Preview upcoming bills/income
   - get_monthly_recurring_summary: Monthly projection
   - skip_occurrence: Skip next instance without posting
   - post_now: Immediate manual posting
   - get_reminders_for_date: Find reminders due today

3. **Views** (`apps/finance/views.py`)
   - RecurringTransactionListView: Filter by active/inactive, shows income/expense sections
   - RecurringTransactionDetailView: Shows upcoming dates, transaction history
   - RecurringTransactionCreateView/UpdateView: CRUD with user-filtered accounts/categories
   - RecurringTransactionDeleteView: Soft delete
   - API endpoints: recurring_post_now, recurring_skip, recurring_toggle_active, api_upcoming_recurring

4. **Templates** (`templates/finance/`)
   - recurring_list.html: Monthly summary, due this week section, income/expense grids
   - recurring_detail.html: Amount card, quick actions, upcoming dates, history
   - recurring_form.html: Dynamic fields based on frequency selection
   - recurring_confirm_delete.html: Confirmation with summary

5. **Dashboard Integration** (`templates/finance/dashboard.html`, `apps/finance/views.py`)
   - "Upcoming Bills & Income" section showing next 14 days
   - Quick action link to recurring management
   - CSS for recurring list styling

6. **Management Command** (`apps/finance/management/commands/process_recurring_transactions.py`)
   - Daily job to auto-post due transactions
   - Supports --dry-run, --user, --date options
   - Processes reminders for upcoming transactions

**Files Modified:**
- apps/finance/models.py - RecurringTransaction model (lines 1647-1954)
- apps/finance/forms.py - RecurringTransactionForm (lines 622-761)
- apps/finance/views.py - CRUD views and API endpoints (lines 1655-1909)
- apps/finance/urls.py - 9 new URL patterns for recurring
- apps/finance/services/recurring.py - Service layer (new file)
- templates/finance/recurring_list.html (new file)
- templates/finance/recurring_detail.html (new file)
- templates/finance/recurring_form.html (new file)
- templates/finance/recurring_confirm_delete.html (new file)
- templates/finance/dashboard.html - Recurring section and quick action
- apps/finance/management/commands/process_recurring_transactions.py (new file)

**Migration:**
- apps/finance/migrations/0015_add_recurring_transaction.py

**Tests:** All 28 finance tests passing

---

### Goal Milestones Feature (Task 2 from Improvement Backlog)

**New Feature:** Goal Progress/Milestones added to the Purpose module allowing users to track incremental progress toward their life goals.

**What's Included:**

1. **GoalMilestone Model** (`apps/purpose/models.py`)
   - Fields: title, description, target_date, completed, completed_date, sort_order
   - ForeignKey to LifeGoal with related_name='milestones'
   - Properties: is_overdue for date-aware urgency
   - Added to LifeGoal: milestone_count, completed_milestone_count, milestone_progress_percent, has_milestones, all_milestones_complete, next_milestone, upcoming_milestones, overdue_milestones

2. **Progress Bar Visuals**
   - Goal list view shows progress bar for goals with milestones
   - Goal detail view shows full milestone section with visual progress
   - Encouragement statistic: "42% more likely to complete" messaging
   - CSS animations for progress fill

3. **Milestone Management**
   - MilestoneCreateView: Add milestones from goal detail page
   - MilestoneToggleView: Toggle completion with celebration trigger
   - MilestoneDeleteView: Remove milestones
   - Admin integration: inline and standalone GoalMilestoneAdmin

4. **Celebration Modal**
   - Auto-triggers when all milestones are completed
   - Confetti animation
   - Prompts user to mark goal as complete
   - Session-based trigger for one-time display

5. **SMS Milestone Reminders** (`apps/sms/scheduler.py`)
   - New CATEGORY_MILESTONE in SMSNotification
   - schedule_milestone_reminders() sends reminders for milestones due today or tomorrow
   - User preference: sms_milestone_reminders (default enabled)

6. **Dashboard Goal Progress Widget** (`templates/dashboard/home.html`)
   - New "Goal Progress" section showing active goals with progress bars
   - Shows next milestone and due dates
   - Links to goal detail pages
   - CSS in `static/css/dashboard.css`

7. **Quarterly Review Dismissible Tile**
   - Appears Jan 1-14, Apr 1-14, Jul 1-14, Oct 1-14
   - Shows previous quarter's stats: goals completed, milestones achieved, goals started
   - Dismissible with X button (stored in UserPreferences.dismissed_quarterly_reviews)
   - API endpoint: dismiss_quarterly_review

8. **AI Integration** (`apps/ai/dashboard_ai.py`, `apps/ai/personal_assistant.py`)
   - _gather_user_data now includes milestone progress, next milestones, overdue count
   - _generate_purpose_priorities shows overdue milestones as highest priority
   - Priority suggestions include specific next milestone context with due dates

9. **Journal-Milestone Cross-Reference**
   - AIService.detect_milestone_completion analyzes journal entries
   - EntryCreateView._check_milestone_completion triggers on save
   - EntryDetailView shows suggestion banner if AI detects potential completion
   - User can confirm with "Yes, mark complete" button

**Files Modified:**
- apps/purpose/models.py - GoalMilestone model, LifeGoal properties
- apps/purpose/admin.py - GoalMilestoneInline, GoalMilestoneAdmin
- apps/purpose/views.py - Milestone CRUD views, GoalDetailView updates
- apps/purpose/urls.py - Milestone URL patterns
- apps/purpose/templates/purpose/goal_list.html - Progress bar
- apps/purpose/templates/purpose/goal_detail.html - Milestones section, celebration modal
- apps/users/models.py - sms_milestone_reminders, dismissed_quarterly_reviews
- apps/sms/models.py - CATEGORY_MILESTONE
- apps/sms/scheduler.py - schedule_milestone_reminders
- apps/dashboard/views.py - _get_purpose_data, _get_quarterly_review, DismissQuarterlyReviewView
- apps/dashboard/urls.py - dismiss_quarterly_review endpoint
- templates/dashboard/home.html - Goal Progress section, Quarterly Review tile
- static/css/dashboard.css - Goal progress and quarterly review styles
- apps/ai/dashboard_ai.py - Milestone data in context gathering
- apps/ai/personal_assistant.py - Milestone-aware priority generation
- apps/ai/services.py - detect_milestone_completion method
- apps/journal/views.py - Milestone detection in EntryCreateView, EntryDetailView
- templates/journal/entry_detail.html - Milestone suggestion banner

**Migrations:**
- apps/purpose/migrations/0004_add_goal_milestones.py
- apps/users/migrations/0040_add_dismissed_quarterly_reviews.py

**Documented for Future:**
- Year in Review feature request (end of year comprehensive review) - see docs/improvement_tasks.md

---

### Sleep Tracking Feature (Task 1 from Improvement Backlog)

**New Feature:** Comprehensive sleep tracking added to the Health module with wearable-ready architecture for future iOS app integration.

**What's Included:**

1. **SleepEntry Model** (`apps/health/models.py`)
   - Full wearable-grade fields: stages (deep, REM, light, awake), heart rate during sleep, efficiency
   - Quality indicators: subjective rating (excellent/good/fair/poor/terrible) and computed score
   - Source tracking for future wearable sync (Apple Health, Google Fit, Fitbit, Garmin, Oura, WHOOP, Samsung Health)
   - sync_id field for deduplication when syncing from wearables
   - Sleep factors (caffeine, alcohol, stress, etc.)

2. **Web Views**
   - SleepListView: Sleep history with stats summary, 30-day chart, sleep composition insights
   - SleepCreateView: Full detailed entry form with all fields
   - SleepQuickCreateView: Quick log form (just hours + quality rating)
   - SleepUpdateView, SleepDeleteView, BulkDeleteSleepView

3. **API Endpoints** (for future native app)
   - `GET/POST /health/api/sleep/` - List entries, create new, bulk sync
   - `GET/PUT/PATCH/DELETE /health/api/sleep/<id>/` - Single entry operations
   - `GET /health/api/sleep/stats/` - Aggregated statistics with trends
   - `GET /health/api/sleep/sync-status/` - Wearable sync status per source
   - Upsert by sync_id to prevent duplicates during wearable sync

4. **AI Integration**
   - Sleep data now included in Health home AI insights
   - Passes avg sleep hours, quality, and count to AI coaching

5. **User Preferences**
   - Added 'sleep' sub-feature toggle to HEALTH_FEATURES in UserPreferences

6. **Tests**
   - 34 tests covering model, views, API endpoints, and serializer
   - Located at `apps/health/tests/test_sleep.py`

**Files Created:**
- `apps/health/views_sleep_api.py` - Sleep API views
- `apps/health/tests/test_sleep.py` - Sleep tests
- `apps/health/migrations/0027_sleepentry_and_more.py` - Database migration
- `templates/health/sleep_list.html` - Sleep history template
- `templates/health/sleep_form.html` - Detailed entry form
- `templates/health/sleep_quick_form.html` - Quick log form

**Files Modified:**
- `apps/health/models.py` - Added SleepEntry model
- `apps/health/forms.py` - Added SleepEntryForm, QuickSleepForm
- `apps/health/views.py` - Added Sleep views and AI data integration
- `apps/health/urls.py` - Added Sleep web and API URLs
- `apps/health/serializers.py` - Added SleepEntrySerializer
- `apps/users/models.py` - Added sleep sub-feature toggle
- `apps/ai/services.py` - Added sleep data to health insights
- `templates/health/home.html` - Added Sleep card to Health dashboard

---

### Completed Reading Plans Moved to Bottom

**Enhancement:** Completed reading plans are now excluded from the Featured Plans section and all other browse sections. They only appear in the "Completed Plans" section at the bottom of the page.

**Behavior:**
- Featured Plans no longer shows plans the user has already completed
- Grouped plans (by source/series) exclude completed plans
- Public/All Plans section excludes completed plans
- Completed Plans section at bottom now shows all completed plans (removed 5 item limit)
- Completed Plans ordered by most recently completed first

**Files Modified:**
- `apps/faith/views.py` - Updated `ReadingPlanListView.get_context_data()` to exclude completed template IDs from featured_plans, grouped_plans, and public_plans

---

### Chat Widget Mobile Viewport Fix

**Bug Fix:** Chat assistant input box was not visible on mobile devices when opening the chat drawer on the reading plan page.

**Root Cause:** The chat drawer used `height: 100vh` which on mobile browsers (iOS Safari, Chrome) includes the space behind the browser chrome (URL bar, bottom navigation). This pushed the input area below the visible viewport.

**Solution:**
- Added CSS `100dvh` (dynamic viewport height) as modern fallback with `100vh` for older browsers
- Added JavaScript viewport height calculator that sets explicit pixel height on mobile/touch devices
- Recalculates height when drawer opens, on resize, and on orientation change

**Files Modified:**
- `templates/components/chat_widget.html` - Added `100dvh` CSS and JavaScript mobile viewport height fix

---

## 2026-01-19 Changes

### Dashboard Weather Widget

**Feature:** Add weather widget to dashboard displaying current conditions and 3-day forecast using Open-Meteo API. Includes prominent alerts for extreme weather conditions.

**Features:**
- Current temperature, condition, humidity, and wind speed
- 3-day forecast with high/low temps and precipitation indicators
- Extreme weather alerts for:
  - Heat warnings (>100°F)
  - Cold alerts (<20°F)
  - High wind warnings (>30 mph)
  - Severe weather (thunderstorms, heavy rain/snow)
- Widget only displays if user has `location_city` set in preferences
- 30-minute cache for weather data, 24-hour cache for geocoding

**Files Created:**
- `apps/dashboard/services/__init__.py`
- `apps/dashboard/services/weather.py` - WeatherService class using Open-Meteo API

**Files Modified:**
- `apps/dashboard/views.py` - Added `_get_weather_data()` method and weather context
- `templates/dashboard/home.html` - Added weather section with alert and normal display modes
- `static/css/dashboard.css` - Added weather widget styles with responsive design

---

### Inline Scripture Expansion in Reading Plans

**Feature:** Add inline scripture expansion to reading plans - clicking scripture references now expands verse text inline instead of navigating away to the Scripture Library.

**Improvements:**
- Click scripture button to expand, click again to collapse
- Fetches scripture via secure Bible API proxy
- Shows loading spinner while fetching
- Formats verse numbers with styling
- Falls back to "Open in Scripture Library" link on error
- Supports all 66 Bible books with comprehensive ID mapping

**UX Benefit:** User never loses their place in the reading plan when looking up verses.

**Files Modified:**
- `templates/faith/reading_plans/progress.html` - Added scripture expansion UI, CSS, and JavaScript

---

## 2026-01-18 Changes

### Fix AdminTask created_by Validation for 404 Reporter

**Bug:** The 404 auto-reporter was failing to create AdminTasks because `'404_reporter'` was not a valid choice in the `created_by` field.

**Root Cause:** The `Report404View` in `apps/core/views.py` was using `created_by='404_reporter'` but this value wasn't in `AdminTask.CREATED_BY_CHOICES`.

**Fix:**
- Added `'404_reporter'` and `'system'` to `CREATED_BY_CHOICES` for both `AdminTask` and `AdminActivityLog`
- Increased `max_length` from 10 to 15 to accommodate longer values

**Migrations:**
- `0020_extend_created_by_max_length` - Alters `created_by` field on both models

**Files Modified:**
- `apps/admin_console/models.py` - Updated CREATED_BY_CHOICES and max_length

**Tasks Resolved:** #338, #339, #340, #341

---

### Reading Plan Source Grouping and Access Control

**Feature:** Added source/series grouping and access control for reading plans to support copyrighted sermon content.

**Model Changes to ReadingPlanTemplate:**
- `source` - Full name of content source (e.g., "Seymour Heights Christian Church")
- `source_abbreviation` - Short display name (e.g., "SHCC")
- `series` - Series name within source (e.g., "Blind Spots")
- `series_order` - Order within series (1 for Week 1, 2 for Week 2, etc.)
- `allowed_emails` - JSON list of emails that can access the plan (empty = public)

**View Changes:**
- `ReadingPlanListView.get_accessible_plans()` - Filters plans by user's email access
- Plans grouped by source and series for organized display
- Public plans (no source) shown separately under "All Reading Plans"

**Template Changes:**
- Source sections with header showing abbreviation and full name
- Series subsections with week badges
- Public plans in separate section
- Responsive styling for mobile

**Migrations:**
- `0012_add_reading_plan_source_series_access` - Adds new fields
- `0013_populate_shcc_reading_plans` - Sets SHCC data on existing Blind Spots plans

**Access Restriction:**
- SHCC Blind Spots plans restricted to dannyjenkins71@gmail.com and heatherjenkins74@gmail.com
- Other users will not see these plans in the list

**Files Modified:**
- `apps/faith/models.py` - Added 5 new fields to ReadingPlanTemplate
- `apps/faith/views.py` - Updated ReadingPlanListView with filtering and grouping
- `templates/faith/reading_plans/list.html` - Grouped display with new CSS
- `apps/faith/fixtures/blind_spots_reading_plan.json` - Added source/series fields
- `apps/faith/fixtures/blind_spots_week1_reading_plan.json` - Added source/series fields

---

### Faith Only Plan - Free Ministry Tier

**Feature:** Added "Faith Only" plan that gives users permanent free access to the Faith module after their 7-day trial expires, as part of Whole Life Journey's ministry.

**Behavior:**
- After trial expires, users see Faith Only option on trial-expired page
- Selecting Faith Only grants permanent free access to all `/faith/` paths
- Faith Only users are blocked from Journal, Health, Life, Purpose, Dashboard
- Dashboard redirects Faith Only users to Faith Home
- Upgrade prompts shown at: Week 1, Month 2, Month 3, then stop forever

**Models Added:**
- `BillingProfile.TIER_FAITH_ONLY` - New pricing tier constant
- `BillingProfile.STATUS_FAITH_ONLY` - New subscription status constant
- `BillingProfile.is_faith_only` - Property to check tier
- `BillingProfile.has_faith_access` - Property to check Faith module access
- `UserPreferences.faith_only_selected_at` - When user selected Faith Only
- `UserPreferences.faith_only_upgrade_week1_shown` / `_shown_at` - Week 1 prompt tracking
- `UserPreferences.faith_only_upgrade_month2_shown` / `_shown_at` - Month 2 prompt tracking
- `UserPreferences.faith_only_upgrade_month3_shown` / `_shown_at` - Month 3 prompt tracking

**Views Added:**
- `select_faith_only` (POST) - Selects Faith Only plan, redirects to Faith Home
- `faith_only_upgrade` - Page shown when Faith Only users try restricted features
- `faith_upgrade_prompt_check` (GET API) - Check if upgrade modal should show
- `faith_upgrade_prompt_dismiss` (POST API) - Record prompt was dismissed

**URLs Added:**
- `/billing/select-faith-only/`
- `/billing/faith-only-upgrade/`
- `/billing/api/faith-upgrade/check/`
- `/billing/api/faith-upgrade/dismiss/`

**Templates Created:**
- `templates/billing/faith_only_upgrade.html` - Upgrade page for restricted features
- `templates/components/faith_only_upgrade_modal.html` - Periodic upgrade prompt modal

**Templates Modified:**
- `templates/billing/trial_expired.html` - Added Faith Only option section
- `templates/faith/home.html` - Included upgrade modal for Faith Only users

**Middleware Modified:**
- `apps/users/middleware.py` - SubscriptionRequiredMiddleware now allows `/faith/` paths for Faith Only users, redirects other paths to faith_only_upgrade

**Dashboard Modified:**
- `apps/dashboard/views.py` - DashboardView.dispatch redirects Faith Only users to Faith Home

**Migrations:**
- `apps/billing/migrations/0006_add_faith_only_tier.py` - Adds TIER_FAITH_ONLY and STATUS_FAITH_ONLY to choices
- `apps/users/migrations/0038_add_faith_only_tracking.py` - Adds upgrade prompt tracking fields

**Tests Added:**
- `apps/billing/tests/test_faith_only.py` - 24 tests covering selection, access control, upgrade prompts

---

### Blind Spots Week 1 Reading Plan - "Opening Your Eyes"

**Feature:** Created 6-day reading plan for Week 1 of the Blind Spots sermon series at Seymour Heights Christian Church.

**Content:**
- Day 1: What You Don't See Can Hurt You (Matthew 7:1-5) - Introduction with self-assessment
- Day 2: The High Capacity for Self-Deception (Jeremiah 17:9-10, Proverbs 16:2)
- Day 3: What Feeds the Blind Spot (Romans 12:3, Galatians 6:3-5) - Dissatisfaction, competition, insecurity
- Day 4: Information vs. Transformation (Romans 12:1-2, James 1:22-25)
- Day 5: The Aroma You Carry (2 Corinthians 2:14-17, Matthew 5:13-16)
- Day 6: The Green Light (John 8:31-32, Psalm 139:23-24) - Surrender and openness to Holy Spirit

**Assessment:** 8-question "Blind Spot Self-Assessment" based on sermon reflection prompts, with 4 score interpretation ranges.

**Files Created:**
- `apps/faith/fixtures/blind_spots_week1_reading_plan.json` - Fixture with template (PK 101), 6 days (PK 1011-1016), and assessment (PK 2)

**Files Modified:**
- `apps/core/management/commands/load_initial_data.py` - Added fixture to FIXTURE_LOADERS

---

### Fix Reading Plan Display Issues

**Fixes:**
1. **Markdown markers in devotional text** - Created migration `0011_update_blind_spots_devotional_text.py` to update database with clean text (no `**` markers)
2. **Line breaks not rendering** - Changed template to use `|linebreaks` filter instead of wrapping in `<p>` tag
3. **Scripture references cut off** - Added `white-space: nowrap` to prevent truncation

**Files Modified:**
- `apps/faith/migrations/0011_update_blind_spots_devotional_text.py` - Data migration to clean up devotional text
- `templates/faith/reading_plans/progress.html` - Template and CSS fixes

---

### Reading Plan Completion Badge on Browse Cards

**Feature:** Added completion badge indicator on the "All Reading Plans" browse grid to show which plans a user has previously completed.

**Files Modified:**
- `apps/faith/views.py` - Added `completed_template_ids` set to context in `ReadingPlanListView`
- `templates/faith/reading_plans/list.html` - Added "Completed" badge and green border on plan cards for completed plans

**Behavior:**
- When browsing "All Reading Plans", cards for plans the user has completed now show a green "Completed" badge
- Cards also have a green border to distinguish them visually
- Users can still click "Learn More" to restart the plan if desired

---

### Reading Plan Assessments - Interactive Self-Assessments

**Feature:** Added interactive assessments to Reading Plans, allowing users to take scored self-assessments with dropdowns and see interpreted results.

**Implementation:**

**Models (`apps/faith/models.py`):**
- `ReadingPlanAssessment` - Stores assessment definition linked to a ReadingPlanDay
  - `questions` (JSONField) - Array of questions with id, text, min_label, mid_label, max_label
  - `score_ranges` (JSONField) - Score interpretation ranges with min, max, label, description
  - `min_score_per_question`, `max_score_per_question` - Scoring configuration
  - `max_possible_score` property and `get_score_interpretation()` method
- `UserAssessmentResponse` - Stores user's responses and calculated score
  - `responses` (JSONField) - Question ID to score mapping
  - `total_score` - Auto-calculated on save
  - `interpretation` property for retrieving result label/description

**Views (`apps/faith/views.py`):**
- Updated `ReadingPlanProgressView` to include assessment data with user responses
- Added `SaveAssessmentResponseView` - AJAX endpoint to save assessment responses

**URLs (`apps/faith/urls.py`):**
- `/faith/reading-plans/progress/<plan_pk>/assessment/<assessment_pk>/save/` - Save assessment response

**Templates (`templates/faith/reading_plans/progress.html`):**
- Added assessment rendering with dropdown selects for each question (1-5 scale)
- JavaScript for collecting responses, calculating score, and displaying results
- CSS for responsive assessment styling (mobile-friendly)
- Saved responses are restored when returning to the page

**Template Tags (`apps/core/templatetags/json_filters.py`):**
- Added `jsonify` filter for safely encoding Python dicts to JSON in data attributes

**Admin (`apps/faith/admin.py`):**
- `ReadingPlanAssessmentAdmin` - Manage assessments with question count display
- `UserAssessmentResponseAdmin` - View user responses with score interpretation

**Fixture (`apps/faith/fixtures/blind_spots_reading_plan.json`):**
- "Surrendering My Blind Spots" - 6-day reading plan based on SHCC sermon
- Day 1 includes Control Freak Assessment with 10 questions
- Score interpretations: Control Freak (40-50), Control Issues (30-39), Live and Let Live (20-29), Very Laid Back (10-19)

**Migration:** `apps/faith/migrations/0010_reading_plan_assessments.py`

**Tests (`apps/faith/tests/test_reading_plans.py`):**
- `ReadingPlanAssessmentModelTest` - Model tests for scoring and interpretation
- `UserAssessmentResponseModelTest` - Tests for auto-calculation and interpretation
- `SaveAssessmentResponseViewTest` - View tests for AJAX save endpoint

**Files Changed:**
- `apps/faith/models.py` - Added ReadingPlanAssessment and UserAssessmentResponse
- `apps/faith/views.py` - Updated progress view, added save assessment view
- `apps/faith/urls.py` - Added assessment save endpoint
- `apps/faith/admin.py` - Added admin for assessment models
- `templates/faith/reading_plans/progress.html` - Assessment UI with JS
- `apps/core/templatetags/json_filters.py` - New jsonify filter
- `apps/faith/fixtures/blind_spots_reading_plan.json` - New fixture
- `apps/faith/tests/test_reading_plans.py` - Assessment tests

---

## 2026-01-17 Changes

### Gmail Integration - Auto-Create Tasks from Email Action Items

**Feature:** Added Gmail integration allowing users to connect their Gmail account and automatically create tasks from action items in their emails.

**Implementation:**

**Models (`apps/life/models.py`):**
- `GmailCredential` - Stores OAuth tokens (encrypted), scan settings, tracking info
- `ProcessedEmail` - Tracks processed email IDs to prevent duplicates
- Added email source fields to `Task` model: `email_source_id`, `email_source_subject`, `email_source_sender`, `email_source_date`

**Services:**
- `apps/life/services/gmail.py` - Gmail OAuth flow, email fetching (primary inbox only, excludes Promotions/Social/Updates)
- `apps/life/services/email_processor.py` - AI-powered action item extraction using OpenAI
- `apps/life/services/gmail_sync.py` - Orchestration for user/all-user scanning

**Views (`apps/life/views.py`):**
- `GmailSettingsView` - Settings page
- `GmailConnectView` - OAuth initiation
- `GmailCallbackView` - OAuth callback
- `GmailDisconnectView` - Remove connection
- `GmailSaveSettingsView` - Save preferences
- `GmailManualScanView` - Manual scan trigger
- `GmailSyncCronView` - External cron endpoint (secured with API key)

**URLs (`apps/life/urls.py`):**
- `/life/gmail/` - Settings page
- `/life/gmail/connect/` - OAuth connect
- `/life/gmail/callback/` - OAuth callback
- `/life/gmail/disconnect/` - Disconnect
- `/life/gmail/settings/` - Save settings
- `/life/gmail/scan/` - Manual scan
- `/life/api/gmail/cron-sync/` - Cron endpoint

**Template:**
- `templates/life/gmail_settings.html` - Settings UI with connection status, scan controls, "How It Works" section

**Settings (`config/settings.py`):**
- `GMAIL_CLIENT_ID` - OAuth client ID
- `GMAIL_CLIENT_SECRET` - OAuth client secret
- `GMAIL_REDIRECT_URI` - OAuth redirect URI
- `GMAIL_SYNC_API_KEY` - API key for cron endpoint

**Security:**
- OAuth tokens encrypted at rest using Fernet AES-256
- Cron endpoint uses constant-time comparison for API key validation
- `gmail.readonly` scope (read-only access)
- CSRF protection via state parameter in OAuth flow

**Migration:**
- `apps/life/migrations/0010_gmail_integration.py`

**Testing:** All 209 life module tests pass.

**Setup Required:**
1. Enable Gmail API in Google Cloud Console
2. Create OAuth 2.0 credentials (same project as Calendar)
3. Add redirect URI: `https://wholelifejourney.com/life/gmail/callback/`
4. Set environment variables: `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_SYNC_API_KEY`
5. Configure external cron service to call `/life/api/gmail/cron-sync/` with API key header

---

### Fix Gap Detector Tests After Water Tracking Feature

**Issue:** 7 gap detector tests were failing in CI after the water/hydration tracking feature was added. The tests were using "hydration" as an example of an **unknown** data type that should trigger gap detection, but now that water/hydration is a supported data type, these tests were incorrect.

**Root Cause:** When water tracking was added, `hydration` was added to `PERSONAL_DATA_KEYWORDS['water']` in `intent_detector.py`. The `extract_potential_keywords()` function correctly filters out known keywords, so "hydration" was no longer being extracted as a "potential new keyword".

**Solution:** Updated 7 tests to use "creatinine" (kidney function marker) instead of "hydration" as the example of an unsupported data type:
- `test_filters_didnt_fragment` - Tests contraction filtering with unknown data type
- `test_filters_something` - Tests conversational word filtering with unknown data type
- `test_extracts_potential_new_keywords` - Tests extraction of unknown data types
- `test_real_data_types_still_extracted` - Tests that legitimate health terms are extracted
- `test_gap_for_new_data_type_request` - Tests gap detection for unrecognized queries
- `test_creatinine_is_legitimate_gap` (renamed from `test_hydration_is_legitimate_gap`)
- `test_creatinine_still_extracted` (renamed from `test_hydration_still_extracted`)

**Files Modified:**
- `assistant/tests/test_gap_detector.py`

**Testing:** All 83 gap detector tests pass. All 736 assistant tests pass.

---

### Prevent AI Hallucination of Real-Time Data (Sports, Stocks, News)

**Issue:** The AI assistant was confidently making up specific sports scores and game information when asked questions like "are there any college football games on with an SEC team?" - providing invented matchups like "Alabama vs. Mississippi State" when it has no access to live sports data.

**Root Cause:** The system prompt told the AI it could "answer ANY question" including "sports scores" but the actual implementation only has real-time data access for weather (via Open-Meteo API). The gap_detector correctly identified these as external data queries, but the AI still generated confident-sounding but fabricated answers.

**Solution:** Updated the Personal Assistant system prompt to:
1. Remove "sports scores" from the list of things it claims to answer
2. Added explicit "CRITICAL: What you DON'T have access to" section listing:
   - Live sports scores, schedules, or game information
   - Stock prices or financial market data
   - Breaking news or current events
3. Added instruction to be honest when asked about these topics
4. Added explicit warning: "NEVER make up specific information you don't have"

**Files Modified:**
- `apps/ai/personal_assistant.py` - Updated PERSONAL_ASSISTANT_BASE_PROMPT

**Testing:** All 61 personal assistant tests pass.

---

### Fix Scripture Reference Links on Reading Plan (Auto-Lookup)

**Issue:** Clicking on scripture references (like "Luke 18:1-8") on the Reading Plan progress page navigated to the Scripture Library page but didn't auto-lookup the passage - users had to manually re-enter the reference.

**Root Cause:** The template was correctly passing `?lookup=Luke%2018%3A1-8` as a URL parameter, but the ScriptureListView didn't process this parameter and the JavaScript didn't look for it to trigger auto-lookup.

**Solution:** Added auto-lookup functionality:

**View (apps/faith/views.py):**
- Added `lookup_reference` to context from query parameter

**Template (templates/faith/scripture_list.html):**
- Added `LOOKUP_REFERENCE` JavaScript constant from template context
- Added `parseScriptureReference()` function to parse references like "Luke 18:1-8" into book, chapter, verses
- Added `autoLookupScripture()` async function to:
  - Wait for Bible API to load translations and books
  - Find and select the matching book
  - Fetch and select the chapter
  - Set verse range if specified
  - Trigger the lookup automatically
- Added DOMContentLoaded handler to auto-lookup if parameter is present

**Tests Fixed:** Updated JavaScript comments to use example references that don't conflict with test assertions.

---

### Add Water/Hydration Tracking Feature

**Feature Request:** User requested water tracking functionality via email intake task.

**Implementation:** Added complete water/hydration tracking to the Health module:

**Model (apps/health/models.py):**
- New `WaterEntry` model with amount, unit (oz/ml/cups/liters), container type, logged_date
- Helper methods: `amount_oz`, `amount_ml` for unit conversion
- Class methods: `get_daily_total()`, `get_daily_goal_progress()` for progress tracking

**Views (apps/health/views.py):**
- `WaterListView` - List water entries with today's progress, weekly stats, and chart
- `WaterCreateView` - Form to log water with quick presets
- `WaterUpdateView` - Edit existing entries
- `WaterDeleteView` - Delete with undo support
- `QuickWaterLogView` - Quick AJAX logging from dashboard

**Templates:**
- `templates/health/water_list.html` - Main water tracking page with progress bar, quick-add buttons, stats
- `templates/health/water_form.html` - Entry form with quick presets (8oz glass, 16oz bottle, etc.)
- Updated `templates/health/home.html` - Added Water card to health dashboard

**URLs (apps/health/urls.py):**
- `/health/water/` - List view
- `/health/water/log/` - Create view
- `/health/water/<pk>/edit/` - Update view
- `/health/water/<pk>/delete/` - Delete view
- `/health/water/quick/` - Quick log endpoint

**AI Integration:**
- `assistant/data_service.py` - Added `get_water_data()` method for assistant queries
- `assistant/intent_detector.py` - Added 'water' keywords for intent detection
- `apps/ai/signals.py` - Added cache invalidation signals for WaterEntry
- `apps/ai/personal_assistant.py` - Added water tracking to feature list

**Navigation:**
- `apps/help/fixtures/teaching_destinations.json` - Added water tracking destination

**Migration:**
- `apps/health/migrations/0026_water_entry.py` - Create WaterEntry table

---

### Fix AI Page Context Awareness (Navigation Override)

**Issue:** When users asked about page content (like "show me the actual scripture NIV"), the AI was incorrectly redirecting them to unrelated features (like habits) instead of using the page context to answer about the scripture they were viewing.

**Root Cause:** The `_try_navigation_response()` function was triggered by "show me the" and other navigation indicators, causing it to search for unrelated destinations instead of using the rich page context (scripture references, reading plan content) that was already being collected.

**Solution:** Updated `_try_navigation_response()` to:
1. Check for page content indicators first ("this scripture", "actual scripture", "NIV", "explain this", etc.)
2. Skip navigation if page_context has rich content and query references that content
3. Pass page_context parameter to enable context-aware decisions

**Files Modified:**
- `apps/ai/personal_assistant.py` - Updated `_try_navigation_response()` with content indicators and page_context parameter

---

### Fix Gap Detector False Positives for Sports and General Knowledge Queries

**Issue:** The gap_detector was flagging queries about external data (sports, general knowledge) as "new data types" to evaluate. Examples: "what college football is on today?", "what horoscope should I read?", "what data do you have on me?"

**Root Cause:** The `is_external_data_query()` function didn't include sports and general knowledge patterns, causing the gap detector to suggest these as new personal data types to track.

**Solution:** Added comprehensive patterns to `is_external_data_query()`:
- Sports: football, basketball, baseball, hockey, soccer, NFL/NBA/MLB/NHL/MLS, college football/basketball, NCAA, game today/tonight, scores, standings, playoffs, championship
- General knowledge: "who is", "who was", "what is on", "what's on"

Also previously added to `CONVERSATIONAL_WORDS`: 'data', 'info', 'information', 'details', 'stats', 'statistics'

And `external_patterns`: 'horoscope', 'zodiac', 'astrology', 'star sign'

**Files Modified:**
- `assistant/gap_detector.py` - Extended external_patterns in is_external_data_query() and CONVERSATIONAL_WORDS

---

### Add Resolution Notes Feature to AdminTask

**Issue:** When tasks were completed, there was no documentation of what was done to resolve them, making it hard to track root causes and preventive actions.

**Solution:** Added two new fields to AdminTask model:
- `resolution_notes` (TextField): Documents what was done to resolve the task
- `completed_at` (DateTimeField): Auto-set when task transitions to 'done'

Updated `transition_status()` method to accept optional `resolution_notes` parameter. Updated the Claude API to accept 'notes' parameter when marking tasks done. Added Resolution section to task edit form with green styling.

**Files Modified:**
- `apps/admin_console/models.py` - Added resolution_notes and completed_at fields to AdminTask
- `apps/admin_console/views.py` - Updated UpdateTaskStatusAPIView to accept 'notes' parameter
- `templates/admin_console/admin_task_form.html` - Added Resolution section UI
- `apps/admin_console/migrations/0022_admintask_completed_at_admintask_resolution_notes.py` - Migration for new fields

---

### Remove Redundant Feature Request Acknowledgment

**Issue:** When users made feature requests, the AI responded with a good acknowledgment, but then the feature_request_service was appending a second redundant acknowledgment paragraph.

**Solution:** Removed the redundant acknowledgment message from feature_request_service since the AI already handles the response naturally.

**Files Modified:**
- `apps/ai/feature_request_service.py` - Removed redundant acknowledgment message

---

### Fix AI Hallucinating Non-Existent Features and Friendly 404 Page

**Issues:**
1. AI assistant was generating broken links to features that don't exist (e.g., "Sleep Tracking" links leading to 404)
2. The 404 error page was bland and didn't help users
3. Bug report acknowledgment message exposed the admin email address

**Solutions:**

1. **AI System Prompt Update:** Updated the personal assistant's feature link list to be comprehensive and added explicit instructions to ONLY use links from the provided list. If users ask about unavailable features (like sleep tracking, water tracking), the AI now explains the feature isn't available yet and suggests using "I wish I could..." to add to the roadmap.

2. **Friendly 404 Page:** Redesigned the 404 page with:
   - Friendly messaging ("Well, that didn't work!")
   - Map emoji for visual interest
   - Clear "Go Back" and "Go to Dashboard" buttons
   - Automatic notification to support team about broken links
   - Creates AdminTask in Bug Reports project for tracking

3. **Email Privacy:** Removed specific email address from bug report acknowledgment message (now just says "our support team")

**Files Modified:**
- `apps/ai/personal_assistant.py` - Updated feature link list and added "do not hallucinate" instructions
- `templates/404.html` - Complete redesign with friendly UX and auto-reporting
- `apps/core/views.py` - Added Report404View API endpoint for broken link tracking
- `apps/core/urls.py` - Added /api/report-404/ URL pattern
- `apps/ai/bug_report_service.py` - Removed email address from acknowledgment message

---

### Clean Up Vision Debug Logging

**Change:** Changed vision logging from `logger.info` to `logger.debug` now that image upload feature is working correctly. This reduces log noise in production.

**Files Modified:**
- `apps/ai/services.py` - Changed vision request/response logging from info to debug level

---

### Fix AI Not Knowing About Image Capabilities

**Issue:** The AI was responding "I can't accept files" and "I can't accept pictures" when users asked about file/image upload, even though the image upload feature was fully implemented in the frontend and backend.

**Root Cause:** The AI's system prompt (`PERSONAL_ASSISTANT_BASE_PROMPT`) was never updated to include information about image capabilities.

**Solution:** Added two sections to the AI system prompt:
1. In the "WHAT CAN YOU DO?" capabilities section, added "Images & Screenshots" capability
2. Added new "## IMAGE CAPABILITIES" section explaining that users can click the + button or paste images

**Files Modified:**
- `apps/ai/personal_assistant.py` - Added image capability documentation to the system prompt

---

### Fix Delete Button and Add Vision Logging

**Issue 1:** The clear conversation (trash) button in the Assistant dashboard wasn't working because clicking it also triggered the sidebar's click handler which called `refreshChatHistory()`, interfering with the delete operation.

**Issue 2:** Need visibility into whether images are actually being sent to OpenAI Vision.

**Solution:**
1. Added `e.stopPropagation()` to the clear button click handler to prevent the sidebar click handler from interfering
2. Added logging to `_call_api()` when sending vision requests to OpenAI

**Files Modified:**
- `templates/ai/assistant_dashboard.html` - Added stopPropagation to clear button handler
- `apps/ai/services.py` - Added logging for vision requests

---

### Fix AI Not Analyzing Attached Images

**Issue:** When users attached images in chat, the AI responded "I can't see the image you've uploaded" even though the image was being sent to OpenAI correctly.

**Root Cause:** The user prompt sent to OpenAI didn't mention that an image was attached. While the OpenAI Vision API received the image, the text prompt didn't acknowledge it, causing the AI to be confused about whether an image was present.

**Solution:** Modified `_generate_response()` to add a note to the prompt when an image is attached: `[The user has attached an image. Please analyze and respond to it along with their message.]`

**Files Modified:**
- `apps/ai/personal_assistant.py` - Added image attachment note to user prompt in `_generate_response()`

---

### Add Image Upload to Assistant Dashboard Chat

**Issue:** The image upload feature was only implemented in the floating chat widget (`chat_widget.html`), but not in the main Assistant dashboard page (`assistant_dashboard.html`). Users on `/assistant/` had no way to attach images.

**Solution:** Added full image upload functionality to the Assistant dashboard chat sidebar:
- Added CSS styles for attachment preview, attach button, and message images
- Added HTML for attach button (+), hidden file input, and preview area
- Added JavaScript for:
  - File selection via button click
  - Image paste from clipboard (Ctrl+V / Cmd+V)
  - Base64 encoding and multipart form upload
  - Preview before sending
  - Display of images in chat history

**Files Modified:**
- `templates/ai/assistant_dashboard.html` - Added complete image upload functionality

---

### Fix Test Failures - Cache Mock and Gap Detection Tests

**Fixed two test failures in CI:**

1. **`test_rate_limit_is_per_user`** (apps/health/tests/test_cycle_export.py)
   - **Issue:** The `@patch('django.core.cache.cache')` decorator patched cache globally, which interfered with the billing signal when creating test users. The `create_billing_profile` signal tried to compare `trial_days > 0` but `trial_days` was a `MagicMock`.
   - **Fix:** Moved user creation BEFORE the cache patch, then used `with patch()` context manager for the actual rate limit testing.

2. **`test_low_severity_queued_for_autonomous`** (assistant/tests/test_views.py)
   - **Issue:** Tests expected gap detection to trigger when `query_by_intent` returned `None`, but the code flow changed - empty data results now trigger a clarification prompt, not gap detection.
   - **Fix:** Changed tests to mock `detect_personal_data_intent` to return `is_personal_query=False`, which correctly triggers the gap detection path.

**Files Modified:**
- `apps/health/tests/test_cycle_export.py` - Fixed `test_rate_limit_is_per_user` cache mocking
- `assistant/tests/test_views.py` - Fixed 4 gap detection tests to use proper intent mocking:
  - `test_low_severity_queued_for_autonomous`
  - `test_medium_severity_sent_to_admin`
  - `test_gap_detection_is_logged`
  - `test_gap_message_returned_to_user`

---

### Development Notice Modal + Bug Report Command + Image Upload in Chat

**Three connected features to help users report issues and communicate better with support:**

#### Part 1: Development Notice Modal
Shows a modal to users 48+ hours after registration reminding them we're in active development and guiding them to the "Fix this:" command for reporting issues.

**Files Created:**
- `templates/components/development_notice_modal.html` - Modal with welcome message and guidance
- `apps/users/migrations/0037_add_development_notice_seen_at.py` - Track when user saw modal

**Files Modified:**
- `apps/users/models.py` - Added `development_notice_seen_at` field to UserPreferences
- `apps/core/views.py` - Added `DevelopmentNoticeCheckView` and `DevelopmentNoticeDismissView` API endpoints
- `apps/core/urls.py` - Added routes for development notice API
- `templates/base.html` - Include development notice modal

#### Part 2: Bug Report "Fix this:" Command
Detects when users type "Fix this:", "Bug:", "Error:", etc. in the AI chat and emails admin with full context.

**Files Created:**
- `apps/ai/bug_report_service.py` - Detects bug reports, creates AdminTask, sends email
- `templates/assistant/emails/bug_report.html` - Email template for bug reports

**Files Modified:**
- `apps/ai/personal_assistant.py` - Integrated bug report detection before feature request detection

#### Part 3: Image Upload in Chat
Users can paste images (Ctrl+V/Cmd+V) or click + to attach images. Images are sent to OpenAI Vision for analysis.

**Files Created:**
- `apps/ai/migrations/0016_add_image_fields_to_assistant_message.py` - Image storage fields

**Files Modified:**
- `apps/ai/models.py` - Added `image_data`, `image_mime_type`, `image_expires_at` fields to AssistantMessage
- `apps/ai/views.py` - Updated `AssistantChatView` to accept multipart/form-data with images
- `apps/ai/views.py` - Updated `ConversationHistoryView` to include image data URLs in response
- `apps/ai/personal_assistant.py` - Updated `send_message()` and `_generate_response()` to handle images
- `apps/ai/services.py` - Updated `_call_api()` to support OpenAI Vision format with image content
- `templates/components/chat_widget.html` - Added image upload button, paste handler, preview area, and image display in chat

**Image Features:**
- Paste images from clipboard directly into chat input
- Click + button to open file picker
- Preview attached image before sending
- Images displayed in chat history (user messages only)
- Images stored as base64 with 72-hour auto-expiration
- 5MB maximum file size
- Supports JPEG, PNG, GIF, WebP formats

---

### Smart Goal Rotation in Today's Priorities

**Issue:** The "Today's Priorities" on the Assistant page always showed the same 2-3 goals repeatedly, based on their sort order. Goals that hadn't been worked on or that the user was neglecting weren't being surfaced.

**Solution:** Implemented smart goal rotation that prioritizes goals based on recent activity:
1. Goals never shown in the last 7 days get highest priority (neglected goals)
2. Goals shown but never completed get next priority (needs attention)
3. Goals partially completed get moderate priority (making some progress)
4. Goals consistently completed get lowest priority (doing well - rotate to others)

This ensures all active goals get attention over time, and goals the user isn't making progress on are surfaced more frequently.

**Files Modified:**
- `apps/ai/personal_assistant.py` - Rewrote `_generate_purpose_priorities()` to score goals by recent activity

**Tests:** All 61 personal_assistant tests pass

---

### Feature Request User Acknowledgment

**Issue:** When users mentioned features that don't exist in the AI Assistant chat (e.g., "I wish I could track my sleep"), the system was detecting and emailing admin but not telling the user their suggestion was received.

**Solution:** Modified the AI response flow to acknowledge feature requests to the user:
- When a feature request is detected and forwarded to admin, the AI now appends: "This feature isn't currently available, but I've sent our support team a notification about your suggestion. Thank you for helping us improve!"
- The email to admin already included user name and email address for follow-up/credit

**Files Modified:**
- `apps/ai/personal_assistant.py` - Capture `_check_feature_request()` return value and append acknowledgment to response when True

**Tests:** All 31 feature_request_service tests pass, all 61 personal_assistant tests pass

---

### Don't Show "What's New" to New Users

**Issue:** When a new user signed up, they were shown the "What's New" modal with all existing release notes. These features aren't "new" to them since they never knew the features were missing - everything is new to them.

**Solution:** Modified the user creation signal to also create a `UserReleaseNoteView` record with `last_viewed_at` set to the current time. This marks all existing release notes as "seen" at signup, so new users will only see release notes added after they signed up.

**Files Modified:**
- `apps/users/signals.py` - Added UserReleaseNoteView creation in `create_user_preferences` signal
- `apps/core/tests/test_core_comprehensive.py` - Updated tests to reflect new behavior

**Result:** New users no longer see the "What's New" modal on first login. They'll only see it when genuinely new features are released after their signup date.

---

### 7-Day Free Trial System

**Issue:** Users could sign up and access all features indefinitely without paying. No trial or subscription requirement existed.

**Solution:** Implemented a 7-day free trial system with subscription gating:

1. **BillingConfiguration** - Added `free_trial_days` field (default: 7) to configure trial duration
2. **BillingProfile** - Added:
   - `trial_ends_at` DateTimeField to track when trial expires
   - `is_in_trial` property to check if currently in trial
   - `trial_expired` property to check if trial has ended
   - `trial_days_remaining` property for days left
   - `has_access` property that checks subscription OR active trial
3. **Signals** - Auto-sets `trial_ends_at` when new users sign up
4. **SubscriptionRequiredMiddleware** - Redirects expired trial users to subscribe page
5. **Trial Expired Page** - Shows subscription options when trial ends

**Exemptions:** Staff users, billing pages, onboarding, terms, help, and API endpoints bypass the trial check.

**Files Modified:**
- `apps/billing/models.py` - Added trial fields and properties
- `apps/billing/signals.py` - Added trial period on user creation
- `apps/users/middleware.py` - Added SubscriptionRequiredMiddleware
- `config/settings.py` - Added middleware to MIDDLEWARE list
- `apps/billing/views.py` - Added trial_expired view
- `apps/billing/urls.py` - Added trial-expired URL route
- `templates/billing/trial_expired.html` - Created trial expired template

**Migration:** `apps/billing/migrations/0005_add_trial_fields.py`

---

### Fix Weather Query Location Extraction Bug

**Issue:** When asking "what is the weather", the system incorrectly extracted "what is the" as the location name, returning error: "I couldn't find the location 'what is the'."

**Root Cause:** The regex pattern `^([a-zA-Z\s,]+?)\s+weather` in `_extract_location()` was matching the question words before "weather".

**Solution:** Added a filter to exclude common question words (what, whats, how, is, the, today, tomorrow, current, my) from being treated as locations.

**Files Modified:**
- `apps/ai/web_search_service.py` - Updated `_extract_location()` to filter out question words

**Result:** "what is the weather" now correctly prompts "What city would you like the weather for?" instead of trying to geocode "what is the".

---

### Allow AI Assistant to Answer Any Question

**Issue:** The AI Assistant was refusing to answer general knowledge questions by saying it was only a wellness assistant and couldn't help.

**Solution:** Added a new "ANSWER ANYTHING (WITHIN REASON)" section to the master prompt that explicitly allows the AI to answer:
- General knowledge and trivia
- Recipes, sports scores, weather
- History, math, advice
- Any helpful question

**The only things it refuses:**
- Rude, vulgar, or hateful content
- Anything illegal or harmful
- Personal attacks

**Files Modified:**
- `apps/ai/personal_assistant.py` - Added "ANSWER ANYTHING" section to `PERSONAL_ASSISTANT_BASE_PROMPT`

**Result:** The AI is now a helpful general-purpose assistant that also specializes in wellness, rather than being limited to only wellness topics.

---

### Always Include Clickable Links When Directing Users

**Issue:** When the AI told users to "go to your Journal entries" or similar, it wasn't including a clickable link. The navigation response system only provided links for explicit navigation queries ("where to find X"), not when the AI naturally suggested going somewhere.

**Solution:** Added a new "ALWAYS INCLUDE LINKS WHEN DIRECTING USERS" section to the master prompt with:
1. Clear instruction that ANY time the AI tells a user to go somewhere, it MUST include a link
2. A reference list of common links (Journal, Weight, Blood Pressure, Goals, Tasks, etc.)
3. Example format: "You can do that by going to **[Feature Name]**. For easy access, [click here](/path/)."

**Files Modified:**
- `apps/ai/personal_assistant.py` - Added link reference section to `PERSONAL_ASSISTANT_BASE_PROMPT`

**Result:** Now when the AI says "go to your Journal" in any context, it will include "[click here](/journal/)" for easy navigation.

---

### Fix Navigation Link Detection for "Where to Find" Queries

**Issue:** When users asked "where to find blood pressure" or similar navigation queries, the AI wasn't returning clickable links to the feature. The navigation response system was only triggering for patterns like "where do I" and "how do I find", but not "where to find".

**Solution:** Expanded the navigation detection patterns in `_try_navigation_response()` to match more natural phrasings:

1. **New navigation indicators added:**
   - `'where to find'`, `'where to log'`, `'where to track'`, `'where to add'`, `'where to record'`
   - `'find my'`, `'find the'`, `'looking for'`

2. **New topic keywords for context resolution:**
   - `'blood pressure'`: ['blood pressure', 'bp', 'systolic', 'diastolic']
   - `'heart rate'`: ['heart rate', 'pulse', 'bpm', 'heartbeat']

**Files Modified:**
- `apps/ai/personal_assistant.py` - Expanded `navigation_indicators` list and `topic_keywords` dict

**Result:** Users asking "where to find blood pressure" will now get a response like: "You can log and monitor your blood pressure readings over time by going to **Health - Blood Pressure**. For easy access, [click here](/health/blood-pressure/)."

---

### Fix "No Data Found" Response and Add Capability Guidance

**Issue:** When no data was found for a query, the AI gave a confusing response: "Can you see your most recent entries in the app? If you can see them there but I can't, please let me know and I'll investigate." This made users feel like they were troubleshooting for the AI.

**Additionally:** When users asked "How can you help me?", the AI gave a generic vague response instead of listing specific capabilities.

**Solution:**
1. Changed the "no data found" message to: "I don't have any [type] entries in your records yet. Would you like to log some? I can help you find where to do that."

2. Added explicit guidance in the prompt for capability questions - now the AI lists specific things it can help with (health data, goals, tasks, faith, journal, navigation) and gives concrete examples.

3. Added friendly names for all new data types (heart_rate → "heart rate", blood_pressure → "blood pressure", etc.)

**Files Modified:**
- `assistant/views.py` - Updated `DATA_NOT_FOUND_CLARIFYING_MESSAGE` and expanded `_get_friendly_data_type_name()`
- `apps/ai/personal_assistant.py` - Added "WHEN ASKED WHAT CAN YOU DO?" section to the prompt

---

### Redesign AI Assistant Master Prompt for Trust & Confidence

**Issue:** The AI Assistant was appearing "lost" and saying "I don't know" too often. Even when data was available, the responses felt like a generic chatbot rather than a knowledgeable partner who knows the user.

**Solution:** Complete rewrite of the master prompt with a new philosophy centered on the "Trust Principle" - the user must trust that the assistant knows their data, remembers context, and gives real answers.

**Key Changes to `apps/ai/personal_assistant.py`:**

1. **New Identity Section** - Defines the assistant as "the user's trusted partner" who KNOWS them, not a generic chatbot

2. **Trust Principle** - Three core behaviors:
   - Know their data: Share confidently when data is available
   - Remember context: Connect ideas naturally across the conversation
   - Give real answers: No deflecting, no "I don't know" when you DO know

3. **Lead with Data** - New instruction: "If you have data about what they're asking, LEAD WITH THE DATA. Don't hedge. Don't add caveats. Just answer."

4. **Explicit Anti-Patterns** - Clear list of what to NEVER do:
   - Say "I don't have that information" when data IS available
   - Deflect to user ("Would you like me to check?")
   - Pad with filler ("That's a great question...")
   - Add uninvited task reminders

5. **Handling Data Questions** - New section with explicit flow:
   - Check if data is in context
   - If YES: Answer directly with specific numbers, dates, trends
   - If NO: Clear acknowledgment that no entries exist yet

6. **Improved Coaching Style Examples** - Each style now includes a concrete example of how to phrase the same information

7. **Gold Standard Check** - New self-evaluation: "Did I sound like someone who knows this person and their data? Or did I sound like a confused chatbot?"

8. **Faith Integration** - Rewritten to be more natural and confident, less preachy

9. **State Assessment Prompt** - Streamlined for clarity

**Files Modified:**
- `apps/ai/personal_assistant.py` (complete prompt rewrite)

**Result:** The AI Assistant should now respond with confidence and specificity when it has data, feel like a knowledgeable friend rather than a confused chatbot, and only admit lack of information when it's genuinely true.

---

### Expand AI Assistant Data Query Capabilities

**Issue:** AI Assistant was saying "I don't know" too often because it couldn't query many data types that users were asking about. The intent detector recognized queries about heart rate, blood pressure, workouts, fasting, and tasks, but there were no query methods to fetch that data.

**Solution:** Added 7 new data query methods and context formatters to enable the AI to respond accurately about more data types.

**New Data Query Methods in `assistant/data_service.py`:**
- `get_heart_rate_data()` - Heart rate entries with average, latest, context
- `get_blood_pressure_data()` - Blood pressure readings with systolic/diastolic averages
- `get_blood_oxygen_data()` - SpO2 measurements
- `get_workout_data()` - Workout sessions with duration stats
- `get_fasting_data()` - Fasting windows with active fast detection
- `get_task_data()` - Task summary with overdue/due today counts

**New Context Formatters in `assistant/context_builder.py`:**
- `_format_heart_rate_data()`
- `_format_blood_pressure_data()`
- `_format_blood_oxygen_data()`
- `_format_workout_data()`
- `_format_fasting_data()`
- `_format_task_data()`
- `_format_user_data()`

**Other Changes:**
- Added `fasting` keywords to `assistant/intent_detector.py`
- Updated `supported_types` in `assistant/views.py` to include all new data types
- Updated `query_map` in `data_service.py` to route to new methods

**Files Modified:**
- `assistant/data_service.py` (added 6 new query methods, updated query_map)
- `assistant/context_builder.py` (added 7 formatting functions)
- `assistant/intent_detector.py` (added fasting keywords)
- `assistant/views.py` (updated supported_types list)

**Result:** AI Assistant can now accurately respond to questions about heart rate, blood pressure, blood oxygen, workouts, fasting, and tasks instead of appearing "lost" and saying it doesn't have that information.

---

### Fix Test Cache Bleeding and Outdated Test APIs

**Bug:** Integration tests were failing due to cache bleeding between test classes and outdated method calls.

**Issues Fixed:**
1. **Cache bleeding:** Test classes inheriting from `CacheClearingTestCase` weren't calling `super().setUp()`, so cache wasn't being cleared between tests
2. **Outdated API calls:** Tests called `HealthMonitor.get_health_report()` which doesn't exist (should be `get_full_status_report()`)
3. **Incorrect unpacking:** Tests tried to unpack `RateLimitResult` as tuple instead of accessing `.allowed` and `.reason` attributes

**Files Modified:**
- `assistant/tests/test_integration.py`
  - Added `super().setUp()` calls to all 11 test classes inheriting from `CacheClearingTestCase`
  - Fixed `get_health_report()` → `get_full_status_report()` (3 occurrences)
  - Fixed `is_within, reason = service.check_rate_limits()` → `result = service.check_rate_limits()`
  - Removed redundant cache imports

**Result:** All 78 integration tests now pass.

---

### Add 'user' Data Type to Personal Assistant

**Feature:** The WLJ Personal Assistant can now access user profile data to personalize responses.

**Implementation:**
- Added 'user' to `SUPPORTED_DATA_TYPES` and `DATA_TYPES_WITH_METHODS` in `assistant/gap_detector.py`
- Added `get_user_data()` method to `PersonalDataService` in `assistant/data_service.py`
- Added 'user' to `query_map` in `query_by_intent()` method

**Data Exposed:**
- User name (first_name, last_name, full name)
- Location (city, country)
- Timezone
- Gender preference

**Files Modified:**
- `assistant/gap_detector.py` - Added 'user' to data type lists
- `assistant/data_service.py` - Added `get_user_data()` method and updated `query_by_intent()`
- `assistant/tests/test_integration.py` - Added 5 tests for user data functionality

**Use Case:** User asks "What's the weather in my city?" → Assistant can now look up user's location from their profile.

---

### Add include_in_progress Parameter to Ready Tasks API

**Bug:** `/run-task` couldn't find tasks after `/next` marked them as `in_progress`, because the API only returned `ready` status tasks.

**Files Modified:**
- `apps/admin_console/views.py` - Added `include_in_progress=true` query param to `ReadyTasksAPIView`
- `.claude/commands/run-task.md` - Updated curl command to use new parameter

**Resolution:** `/run-task` now fetches both `ready` and `in_progress` tasks so it can execute tasks started by `/next`.

---

### Sanitize Email Subject Lines in Confirmation Emails

**Bug:** Confirmation emails failed when original email subjects contained newlines (e.g., `\r\n`).

**Files Modified:**
- `apps/admin_console/email_intake.py` - Strip newlines from subject before sending confirmation

---

### Fix Email Intake IMAP Folder Path

**Bug:** Email intake was looking for folder "Automate" but the actual IMAP path is "INBOX/Automate".

**Root Cause:** PrivateEmail (mail.privateemail.com) uses nested folder structure where folders are children of INBOX, requiring the full path format `INBOX/FolderName`.

**Files Modified:**
- `apps/admin_console/email_intake.py` - Changed folder paths from `Automate` to `INBOX/Automate` and `New Requests` to `INBOX/New Requests`
- `apps/admin_console/management/commands/process_email_tasks.py` - Updated help text

**Resolution:** Now correctly connects to `INBOX/Automate` and moves processed emails to `INBOX/New Requests`.

---

### Add /process-emails Slash Command

**Feature:** Created `/process-emails` slash command to manually trigger the Email Intake Service.

**Files Created:**
- `.claude/commands/process-emails.md` - Slash command definition

**Files Modified:**
- `.claude/commands/README.md` - Added process-emails to command list

**Usage:** Run `/process-emails` to check the "INBOX/Automate" email folder and create AdminTasks from any emails found.

**Note:** To change the cron schedule to hourly, update the Railway dashboard cron service settings.

---

### Add Weather Support to Personal Assistant

**Problem:** When asking the Assistant "what is the weather in Maryville, TN", it replied that it doesn't have access to real-time weather data. ChatGPT can answer this, so our Assistant should too.

**Solution:** Created a web search service that handles weather queries using the Open-Meteo API (free, no API key required). The Assistant now:
1. Detects weather-related questions
2. Extracts location from the question or uses user's saved location
3. Fetches real-time weather data from Open-Meteo
4. Returns current conditions, today's forecast, and tomorrow's forecast

**Files Created:**
- `apps/ai/web_search_service.py` - Web search routing, weather API integration

**Files Modified:**
- `apps/ai/personal_assistant.py` - Added web search check in `_generate_response()`

**Features:**
- Extracts location from query ("weather in Nashville" -> Nashville)
- Falls back to user's saved `location_city` from preferences
- Asks for location if none found
- Shows current temp, conditions, humidity, wind
- Shows today's high/low and precipitation chance
- Shows tomorrow's forecast

---

### Fix: Email Confirmation Template Handles Invalid Keys

**Problem:** Hitting `/accounts/confirm-email/` with an invalid key (like `contact-us` from a bot) caused a `VariableDoesNotExist` error because the template tried to access `confirmation.key` when `confirmation` was `None`.

**Solution:** Updated `templates/account/email_confirm.html` to check if `confirmation` exists before rendering the form. Invalid keys now show a friendly "Invalid confirmation link" message instead of crashing.

**Files Modified:**
- `templates/account/email_confirm.html` - Added `{% if confirmation %}` check

---

## 2026-01-16 Changes

### Improve Assistant Message Tone - More Conversational, Less ChatGPT

**Problem:** The Assistant's state assessment messages sounded corporate and robotic - like ChatGPT, not like a real person talking.

**Solution:** Updated `STATE_ASSESSMENT_PROMPT` to instruct the AI to:
- Write like texting a friend, not a corporate email
- Use contractions and punchy language
- Format as: one conversational opener, then bulleted action items, then a motivating closer
- Avoid bold text, superlatives, and formal language

**Files Modified:**
- `apps/ai/personal_assistant.py` - Rewrote STATE_ASSESSMENT_PROMPT with new voice guidelines

**Example of new tone:**
"Alright partner, here's what needs your attention tonight:
- One task still due today - wrap it up before calling it a night
- Four active life goals haven't seen progress lately - pick one and take a small step
Don't let 'em slip away - take action and keep that momentum rollin'."

---

### Fix: reCAPTCHA Validation No Longer Triggers Error Emails

**Problem:** When a user attempted to sign up with a low reCAPTCHA score (indicating potential bot), the system was raising a `ValidationError` inside `adapter.save_user()`. This caused Django to treat it as an unhandled exception and send an error email to admins, even though the security feature was working correctly.

**Solution:** Moved reCAPTCHA validation from the adapter's `save_user()` method to the form's `clean()` method. Form validation errors are handled cleanly by Django and display a nice error message to the user without triggering error emails.

**Files Modified:**
- `apps/users/forms.py` - Added reCAPTCHA validation in `CustomSignupForm.clean()`
- `apps/users/adapters.py` - Removed blocking logic from `save_user()`, now just logs scores
- `apps/users/views.py` - Added `CustomSignupView` that passes request to form
- `config/urls.py` - Override `/accounts/signup/` to use custom view

**Behavior:**
- Low reCAPTCHA scores still block signup (security maintained)
- Users see "Unable to create account. Please try again later." message
- No error emails sent to admin (this is expected behavior, not an error)
- Security events still logged to `SignupAttempt` model

---

### Email Intake Service for Task Creation

**Summary:** Added automated email-to-task pipeline that polls IMAP for emails and creates AdminTasks.

**Feature:**
- Move any email to the "Automate" folder in admin@wholelifejourney.com
- The `process_email_tasks` management command polls the folder (runs 3x daily on Railway)
- Each email creates an AdminTask with the subject as title, email content as task context
- Sends confirmation email with task ID to the original sender
- Moves processed email to "New Requests" folder

**Implementation:**
1. Created email intake service with IMAP connection, email parsing, and task creation
2. Created management command `process_email_tasks` with --dry-run option
3. Added settings for EMAIL_INTAKE_HOST, EMAIL_INTAKE_PORT, EMAIL_INTAKE_USER, EMAIL_INTAKE_PASSWORD
4. Tasks are created in "Email Intake" project, "Email Requests" phase (phase 999)
5. Full test coverage for parsing, settings validation, and task creation

**Files Created:**
- `apps/admin_console/services/email_intake.py` - IMAP polling and task creation
- `apps/admin_console/services/__init__.py` - Package init
- `apps/admin_console/management/commands/process_email_tasks.py` - Management command
- `apps/admin_console/tests/test_email_intake.py` - Tests (16 tests passing)

**Files Modified:**
- `config/settings.py` - Added EMAIL_INTAKE_* settings

**Environment Variables (added to Railway):**
- `EMAIL_INTAKE_HOST=mail.privateemail.com`
- `EMAIL_INTAKE_PORT=993`
- `EMAIL_INTAKE_USER=admin@wholelifejourney.com`
- `EMAIL_INTAKE_PASSWORD=<password>`

**Railway Scheduled Task Required:**
- Add cron job to run `python manage.py process_email_tasks` at 6am, 12pm, 10pm

---

### Add Attachment Support to Task API

**Summary:** Fixed task attachments not being visible to Claude when working tasks via the API.

**Issue:** The AdminTask model had an `attachment` ImageField, and the form template displayed the file input, but:
1. The attachment field was not included in the form's `fields` list, so uploads weren't being saved
2. The API response didn't include the attachment URL, so Claude couldn't see task screenshots

**Solution:**
1. Added `attachment` to the `fields` list in `AdminTaskCreateView` and `AdminTaskUpdateView`
2. Added `attachment_url` field to the `ReadyTasksAPIView` response (returns full URL or null)
3. Updated `/run-task` command to check for and read attachments

**Files Modified:**
- `apps/admin_console/views.py` - Added attachment to form fields, added attachment_url to API response
- `.claude/commands/run-task.md` - Added step to check for attachment_url

---

### Fix False Positive Gap Detection for Navigation Questions

**Summary:** Fixed a bug where navigation questions like "how do I get to the dashboard" were incorrectly triggering the gap detector to suggest creating a new data type.

**Issue:** When a user asked "how do I get to the dashboard", the AI system incorrectly detected "dashboard" as a potential new data type and triggered an approval task suggesting to create a DashboardEntry model. This was a false positive - the user was asking for navigation help, not asking to store dashboard data.

**Root Cause Analysis:**
1. The intent detector correctly detected `is_personal_query: False` and `data_types: []` since "dashboard" is not in PERSONAL_DATA_KEYWORDS
2. However, the gap detector's `extract_potential_keywords()` function extracted "dashboard" as a potential keyword
3. Combined with personal pronoun "I" in the query, this triggered `GapType.UNKNOWN_DATA_TYPE`
4. The gap detector lacked awareness that UI/navigation terms should be excluded

**Solution:** Added UI/navigation terms to the `CONVERSATIONAL_WORDS` set in `assistant/gap_detector.py`:
- dashboard, page, pages, screen, screens, menu, menus
- settings, preferences, profile, account, navigation, navigate
- button, buttons, link, links, click, clicked, clicking
- tab, tabs, section, sections, sidebar, header, footer
- home, homepage, landing, view, views, display, displays

These terms represent UI elements and navigation concepts that users might ask about but should never be flagged as potential new data types.

**Files Modified:**
- `assistant/gap_detector.py` - Added UI/navigation terms to CONVERSATIONAL_WORDS
- `assistant/tests/test_gap_detector.py` - Added test class `TestUINavigationWordsFiltered` with 4 tests

**Tests Added:**
- `test_dashboard_is_not_data_type` - Verifies "dashboard" is filtered
- `test_settings_is_not_data_type` - Verifies "settings" is filtered
- `test_page_is_not_data_type` - Verifies "page" is filtered
- `test_navigation_question_no_gap` - Integration test verifying navigation questions don't trigger gaps

---

### Improve Password Reset Email Templates to Reduce Spam Detection

**Summary:** Created custom django-allauth email templates for password reset and "unknown account" notifications to reduce spam filter blocking.

**Issue:** An email sent to mark57a@ptd.net was blocked by mx.ptd.net with error "554 5.7.1 Message blocked due to spam content in the message". The email had subject "[Whole Life Journey] Unknown Account" - the default django-allauth template for password reset requests when the email doesn't exist.

**Root Cause Analysis:**
- `ACCOUNT_PREVENT_ENUMERATION = True` setting causes django-allauth to send "unknown account" emails when password reset is requested for non-existent emails
- Default allauth templates have minimal content that can look automated/spammy:
  - Short subject line: "Unknown Account"
  - Brief message body without proper branding
  - Generic phrasing like "you, or someone else" resembles phishing

**Solution:** Created custom email templates with:
- Professional subject lines: "Password Reset Request - Whole Life Journey"
- Proper greeting and clear explanations
- Branded footer with website URL
- "This is an automated message" disclaimer
- Consistent formatting across all password reset emails

**Files Created:**
- `templates/account/email/unknown_account_subject.txt` - Custom subject for unknown account emails
- `templates/account/email/unknown_account_message.txt` - Custom body for unknown account emails
- `templates/account/email/password_reset_key_subject.txt` - Custom subject for password reset emails
- `templates/account/email/password_reset_key_message.txt` - Custom body for password reset emails

**Note:** We cannot guarantee emails won't be spam-filtered (that depends on recipient server settings, SPF/DKIM alignment, sender reputation, etc.), but these changes follow email best practices to reduce false positive spam detection.

---

### Add Delete Functionality for Completed Reading Plans

**Summary:** Added ability to delete completed Bible reading plans from the reading plans listing page.

**Purpose:** Users can now manage their completed reading plan history by removing plans they no longer want to see.

**Implementation:**
- Created `DeleteReadingPlanView` in `apps/faith/views.py` with soft delete support
- Added URL route `reading-plans/progress/<pk>/delete/` in `apps/faith/urls.py`
- Added delete button with trash icon for each completed plan in `templates/faith/reading_plans/list.html`
- Uses JavaScript confirmation dialog via `data-confirm-delete` attribute
- Responsive design: On mobile, only shows icon; on desktop shows "Delete" text

**Security:**
- Only allows deletion of completed plans (plan_status="completed")
- Uses soft delete for data retention (30-day grace period)
- Validates user ownership before deletion
- CSRF protection via form token

**Files Changed:**
- `apps/faith/views.py` - Added DeleteReadingPlanView class
- `apps/faith/urls.py` - Added delete_reading_plan URL pattern
- `templates/faith/reading_plans/list.html` - Added delete button with responsive styling
- `apps/faith/tests/test_reading_plans.py` - Added DeleteReadingPlanViewTest class

---

### Create /close Command for Session Closure

**Summary:** Added a new `/close` slash command to close out coding sessions with a comprehensive review.

**Purpose:** Ensures all documentation, help systems, and tracking are up to date before ending work.

**The /close command performs:**
1. Changelog review - verifies all changes are documented
2. What's New document updates (if user-facing features added)
3. Teaching Tool destinations check (for new pages/features)
4. WLJ Assistant updates check (for new data types)
5. CLAUDE.md review (for new instructions)
6. Git status verification (all committed and pushed)
7. Outstanding tasks report
8. Session summary output

**Files Changed:**
- `.claude/commands/close.md` - New command file
- `.claude/commands/README.md` - Added /close documentation

---

### Reduce False Positives in Gap Detector

**Summary:** Added filters to prevent the gap detector from flagging conversational phrases as potential data types.

**Issue:** The gap detector was incorrectly flagging words like "didn" (from "didn't") and "everything" as potential new data types, generating false "Approval Required" emails.

**Root Cause:** The `extract_potential_keywords()` function in `gap_detector.py` was extracting words too aggressively without filtering out:
- Contraction fragments (didn, wouldn, couldn, etc.)
- Common conversational words (everything, something, nothing, etc.)

**Fix:** Added three new filters to `gap_detector.py`:
1. `CONTRACTION_FRAGMENTS` - Set of 29 words that result from splitting contractions
2. `CONVERSATIONAL_WORDS` - Set of ~200 common words that are never data types (pronouns, verbs, adjectives, discourse markers)
3. Increased minimum word length from 3 to 4 characters

**Files Changed:**
- `assistant/gap_detector.py` - Added CONTRACTION_FRAGMENTS and CONVERSATIONAL_WORDS constants, updated extract_potential_keywords() to filter them
- `assistant/tests/test_gap_detector.py` - Added 3 new test classes with 18 test cases for false positive patterns

**Test Results:** All 56 gap detector tests pass.

---

### Fix Data Visibility Check for Invalid Data Types

**Summary:** Added validation to prevent false "DATA VISIBILITY ISSUE" alerts when the data type is a placeholder like "ambiguous".

**Issue:** When a user's query contained an ambiguous keyword (like "sugar" which could mean blood sugar or dietary sugar), the system set `awaiting_data_type = 'ambiguous'` as a placeholder. If the user then confirmed "yes I can see data", the system tried to look up `get_ambiguous_data` which doesn't exist, triggering a false admin alert.

**Fix:** Added validation at the start of `handle_data_visibility_confirmation()` in `assistant/views.py` to reject placeholder data types ('ambiguous', 'unknown', 'none', empty string) and return a graceful "please ask again" message instead of sending false alerts.

**Files Changed:**
- `assistant/views.py` - Added data type validation

---

### Fix Recurring Task FieldError - is_deleted

**Summary:** Fixed `FieldError: Cannot resolve keyword 'is_deleted'` in recurring task processing.

**Issue:** The `process_recurring_tasks` command was failing with:
```
FieldError: Cannot resolve keyword 'is_deleted' into field.
Choices are: completed_at, created_at, ... deleted_at, ...
```

**Root Cause:** The `recurrence.py` service was using `is_deleted=False` but the Task model uses `deleted_at` field for soft deletes.

**Fix:** Changed `is_deleted=False` to `deleted_at__isnull=True` in `apps/life/services/recurrence.py` line 275.

---

### Fix WLJ Assistant Approval Email Links (Both Systems)

**Summary:** Fixed email links for BOTH approval notification systems - the ImprovementTask gap detection system AND the Feature Request system.

**Issue #1 - ImprovementTask Approval Emails:**
- "[WLJ Assistant] Approval Required" emails had non-functional links
- The approval URL was `/assistant/admin/tasks/<id>/` which doesn't exist
- Users received emails but couldn't click through to review tasks

**Issue #2 - Feature Request Emails:**
- "[WLJ Assistant] Feature Request" emails showed task ID but no clickable link
- Users had to manually navigate to admin console

**Changes:**

1. `assistant/views.py`:
   - Fixed `_send_approval_notification()` to generate proper approval token
   - Build correct URL: `/assistant/admin/approve/<uuid>/<token>/`
   - Uses `SITE_DOMAIN` setting for absolute URL

2. `apps/ai/feature_request_service.py`:
   - Added `task_url` field to `FeatureRequestInfo` dataclass
   - Generate full URL to task edit page after task creation
   - Improved task creation robustness with validation safeguards

3. `templates/assistant/emails/feature_request.html`:
   - Added prominent "Review Task #X" button with clickable link
   - Button styled with indigo background matching app theme

4. `config/settings.py`:
   - Added `SITE_DOMAIN` setting (defaults to https://wholelifejourney.com)

**Result:** Both email systems now have working approval/review links:
- ImprovementTask emails link to `/assistant/admin/approve/<uuid>/<token>/`
- Feature Request emails link to `/admin-console/projects/tasks/<id>/edit/`

---

### Context Aware Help Update - Teaching Tool Expansion

**Summary:** Expanded teaching destinations fixture with 28 new entries to cover all major app features, ensuring users can find any feature via the Teaching Tool.

**Changes:**
- `apps/help/fixtures/teaching_destinations.json`:
  - Added entries 28-55 covering previously missing features:
  - **Scan:** Camera scan (food recognition, barcode)
  - **Finance:** Dashboard, budgets, savings goals
  - **Life/Organize:** Inventory, pets, documents, significant events, maintenance logs
  - **Health:** Blood pressure, heart rate, steps, blood oxygen, medical providers, workout templates, personal records, quick log
  - **Faith:** Daily verse, saved scripture, milestones, study tools
  - **Purpose/Goals:** Annual direction, intentions, reflections
  - **Core:** What's New, journal prompts, SMS history, billing/subscription

- `apps/admin_console/migrations/0018_reset_teaching_destinations_loader.py`:
  - Resets the DataLoadConfig for teaching_destinations so fixture reloads on deploy

**Total destinations:** Increased from 27 to 55

**Auto-reload:** Migration resets the loader, so `load_initial_data` will reload the fixture automatically on next Railway deploy

---

## 2026-01-15 Changes

### Integrate FatSecret Premier Features (Barcode + Image Recognition)

**Summary:** Added FatSecret Premier tier features for barcode scanning and food image recognition, reducing OpenAI API costs.

**Changes:**
- `apps/health/services/fatsecret.py`:
  - Added `lookup_barcode()` method using FatSecret's barcode API
  - Added `recognize_food_image()` method using FatSecret's AI image recognition
  - Updated `_get_access_token()` to support multiple scopes (basic, barcode, image-recognition)
  - Added new API endpoint constants for barcode and image services

- `apps/scan/services/barcode.py`:
  - Added FatSecret as primary barcode lookup source (before Open Food Facts)
  - New lookup order: Local DB → FatSecret → Open Food Facts → OpenAI
  - Added `_lookup_fatsecret()` and `_save_fatsecret_result()` methods

- `apps/scan/services/vision.py`:
  - Added FatSecret food recognition as first attempt for food images
  - OpenAI Vision now used as fallback for non-food items or when FatSecret fails
  - Added `_try_fatsecret_food_recognition()` method
  - Added `fatsecret_available` property

**Benefits:**
- Unlimited API calls (Premier Free tier)
- Better barcode coverage than Open Food Facts
- Faster food image recognition (specialized AI)
- Reduced OpenAI costs (food images handled by FatSecret)

---

### FatSecret Integration Documentation

**Summary:** Complete documentation for FatSecret Premier integration including third-party services doc, What's New entry, and feature documentation.

**Changes:**
- `docs/wlj_third_party_services.md`:
  - Added FatSecret as service #23 with Premier tier details
  - Documented OAuth 2.0 scopes (basic, barcode, image-recognition)
  - Renumbered subsequent services (24-30)

- `apps/core/migrations/0046_fatsecret_integration_release_note.py`:
  - What's New entry: "Improved Food Recognition"
  - Describes barcode scanning and AI food image recognition features

- `docs/wlj_claude_features.md`:
  - Updated Camera Scan section with FatSecret lookup flow
  - Updated Nutrition section with FatSecret integration details
  - Updated key files list

---

### Enable Parallel Task Execution

**Summary:** `/next` now starts ALL tasks at the same phase+priority level, enabling parallel execution.

**Changes:**
- `apps/admin_console/views.py`: `ReadyTasksAPIView` now marks all tasks at top phase+priority as in_progress (not just first one). `auto_started` returns list of IDs instead of single ID.
- `.claude/commands/next.md`: Updated to explain parallel task batching
- `.claude/commands/run-task.md`: Updated to handle multiple in_progress tasks, auto-continue to next batch
- `apps/admin_console/tests/test_admin_console.py`: Updated existing test, added new test for parallel task starting

**Workflow:**
- Phase 1, Priority 1: Tasks A, B → run in parallel
- Phase 1, Priority 2: Task C → runs after A+B complete
- Phase 2, Priority 1: Task D → runs after all Phase 1 complete

---

### Add Behavior Rules to CLAUDE.md

**Summary:** Added explicit behavior rules at top of CLAUDE.md so they're loaded automatically every session.

**Changes:**
- Added "BEHAVIOR RULES" section to CLAUDE.md with permission handling and communication style preferences
- Removed `CLAUDE.local.md` (merged into CLAUDE.md)
- Added `Cheat_Sheet.md` for quick reference

**Why:** User shouldn't have to repeat preferences each session. Rules in CLAUDE.md are auto-loaded.

---

## 2026-01-16 Changes

### Consolidate AI Consent to Single Checkbox

**Summary:** Simplified the AI consent flow during onboarding and in preferences to use a single consent checkbox that covers all AI features including the Personal Assistant.

**Problem:** Users were asked for AI consent multiple times during signup:
1. "AI Data Processing Consent" for general AI features
2. "Personal Assistant Data Consent" for the Personal Assistant

This was confusing and redundant since both consents essentially allow the same data access.

**Solution:**
- Consolidated to a single "Enable AI Features" consent checkbox
- One consent now covers all AI capabilities: insights, coaching, and Personal Assistant
- Personal Assistant toggle remains as a feature toggle (on/off), but no separate consent needed
- Backend automatically syncs `ai_enabled`, `ai_data_consent`, and `personal_assistant_consent` fields

**Files Modified:**
- `templates/users/onboarding_wizard.html`: Simplified AI step to single consent
- `templates/users/preferences.html`: Simplified AI section to single consent
- `apps/users/views.py`: Updated OnboardingWizardView and PreferencesView to handle consolidated consent

**User Experience:**
- Onboarding: One checkbox for AI consent, then optional Personal Assistant toggle
- Preferences: One checkbox for AI consent, then optional Personal Assistant toggle within AI settings

---

### Simplify Task List UX - Circle Toggles, Row Opens Edit

**Summary:** Improved mobile task list interaction - tap circle to complete, tap anywhere else to edit.

**Problem:** Previous task list design required multiple taps and was confusing on mobile.

**Solution:**
- Tapping the circle button now directly toggles task completion
- Tapping anywhere else on the task row opens the edit page
- Removed separate "Edit" link since whole row is clickable
- Added 44px minimum touch target height for accessibility

**Files Modified:**
- `templates/life/task_list.html`: Restructured task item with `.task-row-link` wrapper

---

### Fix Mobile Task List - Checkbox Overlap and Duplicate Recurring Tasks

**Summary:** Fixed two issues on mobile task list: (1) bulk checkbox overlapping with task completion checkbox, (2) recurring tasks creating duplicates when toggled multiple times.

**Problem 1 - Checkbox Overlap:**
- On mobile, the bulk selection checkbox (`.item-checkbox`) was absolutely positioned at top-left of each task item
- This caused it to visually overlap with the task completion circle checkbox
- Made the UI confusing and potentially caused misclicks

**Solution 1:**
- Changed `.item-checkbox` from `position: absolute` to flexbox-based positioning
- Checkbox now flows naturally within the flex container without overlapping

**Problem 2 - Duplicate Recurring Tasks:**
- When a recurring task was marked complete, it created a new task for the next occurrence
- If user toggled the task incomplete and then complete again, another duplicate was created
- This led to many identical tasks piling up (user had 9+ copies of same task)

**Solution 2:**
- Added duplicate check in `RecurrenceService.process_completed_recurring_task()`
- Before creating a new task, checks if a task with same title, due_date, and is_recurring=True already exists
- If existing task found, returns it instead of creating a duplicate

**Files Modified:**
- `templates/life/task_list.html`: Changed `.item-checkbox` CSS positioning (line 562-566)
- `apps/life/services/recurrence.py`: Added duplicate prevention check (lines 268-279)

---

## 2026-01-15 Changes

### Add Cycle Tracking to Navigation and Health Home Page

**Summary:** Made Cycle Tracking discoverable by adding it to the Health navigation menu and Health home page, conditional on user opt-in.

**Problem:** Users could only access Cycle Tracking via direct URL or buried in Preferences. The feature was not visible in the main navigation or Health home page.

**Solution:**
1. Added `cycle_tracking_enabled` to the global context processor so it's available in all templates
2. Added "Cycle Tracking" link to Health dropdown menu (under Vitals column)
3. Added Cycle Tracking card to Health home page with:
   - Current phase display with color indicator
   - Days until next period prediction
   - Daily log count and average cycle length stats
   - Quick access to calendar for logging

**Visibility Rules:**
- Only shown when user has opted into cycle tracking
- Uses existing CycleSettings.cycle_tracking_enabled flag
- Respects is_active (soft delete) status

**Files Modified:**
- `apps/core/context_processors.py`: Added cycle_tracking_enabled to theme_context
- `templates/components/navigation.html`: Added conditional Cycle Tracking link
- `templates/health/home.html`: Added Cycle Tracking card with CSS styles
- `apps/health/views.py`: Added cycle context data to HealthHomeView

---

### Add Cycle Tracking to What's New, Help, and Teaching Tool

**Summary:** Added cycle tracking content to all user-facing documentation systems.

**What's New (Release Notes):**
- Added pk 17: "Menstrual Cycle Tracking" feature announcement
- Published as major feature with release date 2026-01-15

**Teaching Destinations:**
- Added pk 24: "Cycle Tracking" - main cycle dashboard
- Added pk 25: "Log Cycle Day" - daily logging
- Added pk 26: "Cycle Predictions" - AI predictions
- Added pk 27: "Cycle History" - past cycles and statistics

**Help Topics:**
- Added pk 23: "Cycle Tracking: Understand Your Body's Rhythms"
- Context ID: CYCLE_HOME
- Comprehensive help covering phases, logging, predictions, statistics, privacy

**Files Modified:**
- `apps/core/fixtures/release_notes.json`
- `apps/help/fixtures/teaching_destinations.json`
- `apps/help/fixtures/help_topics.json`

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
