# ==============================================================================
# File: docs/wlj_claude_changelog.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Historical record of fixes, migrations, and changes
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-28
# Last Updated: 2025-12-31 (Improved Help System, Task Search)
# ==============================================================================

# WLJ Change History

This file contains the historical record of all fixes, migrations, and significant changes.
For active development context, see `CLAUDE.md` (project root).

---

## 2025-12-31 Changes

### Task Search Feature

Added the ability to search tasks by title and notes content. Users can now quickly find specific tasks from their task list.

**Features:**
- Search box at the top of the task list page
- Searches both task title and notes fields
- Case-insensitive search
- Works with existing filters (Show: Active/Completed/All, Priority: Now/Soon/Someday)
- Preserves search query when changing filters
- Shows result count ("Found X tasks matching...")
- Clear search button to reset search
- Context-aware empty state (different message for no results vs no tasks)

**Files Modified:**
- `apps/life/views.py` - Added search query filtering with Q objects to `TaskListView.get_queryset()`
- `apps/life/views.py` - Added `search_query` to template context
- `templates/life/task_list.html` - Added search bar UI with input, clear button, and search button
- `templates/life/task_list.html` - Added CSS styles for search bar components
- `templates/life/task_list.html` - Updated filter links to preserve search query
- `templates/life/task_list.html` - Added empty state for search with no results

**Tests Added (9 new tests):**
- `test_task_search_by_title` - Search filters tasks by title
- `test_task_search_by_notes` - Search filters tasks by notes content
- `test_task_search_case_insensitive` - Search is case-insensitive
- `test_task_search_with_filters` - Search works with show/priority filters
- `test_task_search_empty_query_returns_all` - Empty search returns all tasks
- `test_task_search_no_results` - No matches shows empty state
- `test_task_search_query_preserved_in_context` - Search query in template context
- `test_task_search_shows_result_count` - Shows count of matching tasks
- `test_task_search_other_user_tasks_not_visible` - User isolation maintained

**URL:** `/life/tasks/?q=<search_term>`

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
- `different_files.txt`
- `template_diffs.txt`
- `phase2_diff_..txt`
- `docs/intro_transcript.md`

---

### Migration Merge: Core App Conflict Resolution

Fixed conflicting migrations in the core app that caused Django startup failures.

**Issue:**
- Two migrations (`0017_personal_assistant_module_release_note` and `0018_add_assistant_focus_release_note`) both depended on the same parent migration, creating a "diamond" conflict.
- Railway deployment was repeatedly failing with: `CommandError: Conflicting migrations detected; multiple leaf nodes in the migration graph`

**Fix:**
- Created merge migration `0019_merge_20251230_0556.py` using `python manage.py makemigrations --merge`

**Files Created:**
- `apps/core/migrations/0019_merge_20251230_0556.py` - Merge migration

---

## 2025-12-29 Changes

### Personal Assistant Module

Made the Personal Assistant a selectable module with its own consent, separate from general AI Features.

**Purpose:**
- Users can enable general AI features (insights, camera scan) without the Personal Assistant
- Personal Assistant requires explicit opt-in and separate consent
- Deeper data access requires explicit consent for privacy

**New Model Fields (`UserPreferences`):**
- `personal_assistant_enabled` - Enable Personal Assistant module (BooleanField, default False)
- `personal_assistant_consent` - Consent for deeper data access (BooleanField, default False)
- `personal_assistant_consent_date` - When consent was given (DateTimeField, nullable)

**Migration:**
- `apps/users/migrations/0020_add_personal_assistant_module.py`
- `apps/core/migrations/0017_personal_assistant_module_release_note.py`

**Files Modified:**
1. `apps/users/models.py` - Added 3 new fields to UserPreferences
2. `apps/users/forms.py` - Added fields to PreferencesForm
3. `apps/users/views.py` - Updated OnboardingWizardView and PreferencesView
4. `apps/core/context_processors.py` - Added personal_assistant_enabled and personal_assistant_consent
5. `apps/ai/views.py` - Added `check_personal_assistant_enabled()` to AssistantMixin
6. `templates/users/preferences.html` - Added Personal Assistant section with toggles
7. `templates/users/onboarding_wizard.html` - Added Personal Assistant to AI step
8. `templates/ai/assistant_dashboard.html` - Updated status banner messages
9. `templates/components/navigation.html` - Updated nav item conditional
10. `apps/ai/tests/test_personal_assistant.py` - Added access control tests

**UI Changes:**
- **Preferences Page**: Personal Assistant section under AI Features with:
  - Module toggle (requires AI Features enabled)
  - Consent toggle (requires module enabled)
  - Info box showing what the Assistant does
- **Onboarding Wizard**: AI step now includes:
  - AI Data Consent toggle
  - Personal Assistant toggle (visible when AI + consent enabled)
  - Personal Assistant consent toggle
- **Navigation**: Assistant link only visible when fully enabled and consented
- **Assistant Dashboard**: Shows specific messages for each missing requirement

**Access Control:**
All Personal Assistant API endpoints now check for:
1. AI Features enabled (`ai_enabled`)
2. AI Data Consent (`ai_data_consent`)
3. Personal Assistant enabled (`personal_assistant_enabled`)
4. Personal Assistant consent (`personal_assistant_consent`)

---

### AI Assistant - Task-Focused Not Cheerleading

Updated the AI Personal Assistant to focus on what needs to be done rather than celebrating what's been accomplished. Positive feedback/celebrations now belong on the main dashboard, while the Assistant focuses on ACTION.

**Changes Made:**

1. **System Prompts Updated** (`apps/ai/personal_assistant.py`)
   - Updated `PERSONAL_ASSISTANT_SYSTEM_PROMPT` to be action-focused, not cheerleading
   - Changed tone instructions: "Direct and helpful" instead of "Calm, Wise, Supportive"
   - Added explicit instructions to NOT be a cheerleader or use excessive praise
   - Focus on gaps and opportunities, not accomplishments

2. **State Assessment Prompt Updated**
   - Updated `STATE_ASSESSMENT_PROMPT` to focus on what needs attention
   - Reduced from 150 to 100 words max response
   - Explicit DO NOT instructions for praise and superlatives
   - Focus on actionable gaps and clear next steps

3. **Assessment Generation Updated**
   - `_generate_ai_assessment()` now prioritizes gaps and action items
   - Overdue tasks and due-today tasks are highlighted first
   - Journal gaps, medicine adherence issues surfaced
   - Celebrations array kept minimal (for dashboard use only)

4. **Opening Message Updated**
   - `get_opening_message()` now returns empty celebrations array
   - Focus shifted to nudges (renamed conceptually to "action items")
   - Greeting remains, but assessment focuses on what needs attention

5. **Nudges Enhanced**
   - `_build_nudges()` now prioritizes overdue tasks first
   - Added tasks due today as action item
   - Added medicine adherence gap detection
   - Increased max nudges from 2 to 3

6. **Dashboard Template Updated** (`templates/ai/assistant_dashboard.html`)
   - Removed Celebrations card entirely
   - Renamed "Today's Focus" to "Needs Attention"
   - Updated welcome chat message to be task-focused
   - Simplified insights row to single action items card

**Philosophy:**
- The **Dashboard** is where positive feedback and celebrations belong
- The **Assistant** is for getting things done and staying on track
- Direct, helpful, efficient communication without excessive praise

**Files Modified:**
- `apps/ai/personal_assistant.py` - Prompts, assessment, opening message, nudges
- `templates/ai/assistant_dashboard.html` - Removed celebrations, simplified UI

**Test Status:** All 44 personal assistant tests passing, 57 dashboard tests passing

---

### Silence django-axes Warning (axes.W003)

Silenced the `axes.W003` warning that was appearing on every Django startup/deployment.

**Background:**
- The warning recommended adding `axes.backends.AxesStandaloneBackend` to `AUTHENTICATION_BACKENDS`
- However, this backend requires a `request` parameter when authenticating
- Django's test client `client.login()` doesn't pass a request, which breaks many tests
- Rate limiting still works via `AxesMiddleware`, so the warning is benign

**Solution:**
- Added `SILENCED_SYSTEM_CHECKS = ["axes.W003"]` to settings
- Updated comment in `AUTHENTICATION_BACKENDS` explaining the intentional design
- Rate limiting continues to work via middleware

**Files Modified:**
- `config/settings.py` - Added `SILENCED_SYSTEM_CHECKS`, updated `AUTHENTICATION_BACKENDS` comment

**Test Status:** All 40 user authentication tests passing

---

### Medicine Tile Timezone Bug Fix

Fixed a bug where the Medicines tile on the Health page was incorrectly showing doses as "overdue" because it was using UTC time instead of the user's configured timezone.

**Problem:**
- The `HealthHomeView.get_context_data()` method was calculating overdue doses by comparing `timezone.now()` (UTC) against the scheduled time
- The code stripped the timezone info from UTC time but kept the UTC value, then compared it against a naive datetime constructed from the user's local date/time
- For users in EST (UTC-5), a dose scheduled for 5:00 PM would show as overdue at 12:00 PM local time (5:00 PM UTC)

**Solution:**
- Updated the overdue calculation to convert `timezone.now()` to the user's local timezone before comparison
- Uses `user.preferences.timezone` to get the user's configured timezone
- Falls back to UTC if timezone is not set or invalid
- Now matches the pattern already used in `MedicineListView._is_overdue()` method

**Files Modified:**
- `apps/health/views.py` - Fixed `HealthHomeView.get_context_data()` medicine overdue calculation (lines 191-211)

**Test Status:** All health and medicine tests passing (85 medicine tests, 16 health tests)

---

### Health Page Fitness Tile Summary Metrics

Added summary metrics to the Fitness tile on the Health page, making it consistent with all other health tiles that display summary statistics.

**New Fitness Tile Features:**
- **Workouts This Week** - Number of workout sessions logged since Monday
- **Workouts This Month** - Number of workout sessions logged this month
- **Duration This Week** - Total minutes of workouts with recorded duration
- **Last Workout Date** - When the most recent workout was logged

**Before:** The Fitness tile only showed static text "Track your workouts, cardio, and strength training" with no actual data.

**After:** The tile now shows:
- `X workouts this week` | `Y this month` (stats layout)
- `Z min this week` (if duration data exists)
- `Last workout: Dec 29` (date of most recent workout)
- Falls back to "No workouts logged yet" with a prompt to log the first workout

**Files Modified:**
- `apps/health/views.py` - Added workout summary context data to `HealthHomeView.get_context_data()`:
  - `latest_workout` - Most recent WorkoutSession
  - `total_workouts` - Total count of workouts
  - `workouts_this_week` - Workouts since Monday
  - `workouts_this_month` - Workouts since 1st of month
  - `fitness_duration_this_week` - Sum of duration_minutes this week
- `templates/health/home.html` - Updated Fitness card template to display metrics like other tiles
  - Added `.fitness-stats` CSS styles matching other stat tiles

**Test Status:** All health view tests passing

---

### Medical Providers Feature

Added a complete medical providers contact management system to the Health module.

**New Features:**
- **Medical Provider Tracking** - Store contact information for doctors, clinics, specialists
  - 27 specialty types (Primary Care, Cardiology, Dentist, etc.)
  - Full contact info: phone, fax, email, website
  - Address with Google Maps link
  - Patient portal URL and username storage
  - NPI number tracking
  - Insurance acceptance notes
  - Mark primary care provider
- **AI-Powered Provider Lookup**
  - Enter provider name and location
  - AI searches for contact information
  - Auto-populates form fields with results
  - Uses OpenAI GPT-4o-mini for lookups
- **Provider Staff Management**
  - Add supporting staff (PA, Nurse, MA, etc.) to each provider
  - 12 role types
  - Direct contact info or phone extension
  - Linked to parent provider
- **Health Module Integration**
  - New "My Providers" card on Health home page
  - Shows provider count and primary care provider
  - Quick access to add/view providers

**New Models:**
- `MedicalProvider` - Healthcare provider contact information
  - Inherits from `UserOwnedModel` (soft delete, user ownership)
  - 27+ fields for comprehensive contact storage
  - AI lookup tracking fields
- `ProviderStaff` - Supporting staff members
  - ForeignKey to MedicalProvider (cascade delete)
  - 12 role choices

**New Views:**
- `MedicalProviderListView` - List user's providers
- `MedicalProviderDetailView` - Provider details with staff
- `MedicalProviderCreateView` - Add new provider with AI lookup
- `MedicalProviderUpdateView` - Edit provider
- `MedicalProviderDeleteView` - Soft delete provider
- `ProviderAILookupView` - AJAX endpoint for AI lookup
- `ProviderStaffCreateView` - Add staff to provider
- `ProviderStaffUpdateView` - Edit staff member
- `ProviderStaffDeleteView` - Remove staff

**New URLs:**
- `/health/providers/` - List providers
- `/health/providers/add/` - Add provider
- `/health/providers/<pk>/` - Provider detail
- `/health/providers/<pk>/edit/` - Edit provider
- `/health/providers/<pk>/delete/` - Delete provider
- `/health/providers/ai-lookup/` - AI lookup API
- `/health/providers/<pk>/staff/add/` - Add staff
- `/health/providers/staff/<pk>/edit/` - Edit staff
- `/health/providers/staff/<pk>/delete/` - Delete staff

**New Templates:**
- `templates/health/providers/provider_list.html`
- `templates/health/providers/provider_detail.html`
- `templates/health/providers/provider_form.html`
- `templates/health/providers/staff_form.html`

**Files Modified:**
- `apps/health/models.py` - Added MedicalProvider and ProviderStaff models
- `apps/health/forms.py` - Added MedicalProviderForm and ProviderStaffForm
- `apps/health/views.py` - Added 9 new views + HealthHomeView provider context
- `apps/health/urls.py` - Added 9 new URL patterns
- `apps/health/admin.py` - Registered new models with inlines
- `templates/health/home.html` - Added providers card with styles

**New Migration:**
- `apps/health/migrations/0010_add_medical_providers.py`

**Tests (35 new tests):**
- `test_medical_providers.py` - Comprehensive test coverage
  - Model tests (creation, properties, string repr)
  - View tests (list, detail, create, update, delete)
  - Staff tests (create, update, delete)
  - User isolation tests (security)
  - AI lookup endpoint tests
  - Form validation tests
  - Health home integration tests

---

### Remove Chat History Display on Assistant Page

Removed the display of previous chat history when loading the Assistant page.

**Problem:**
- When users visited the Assistant page, previous conversation messages were being loaded and displayed
- This created unnecessary clutter with short truncated message previews
- Users wanted a clean slate each time they visit the Assistant

**Solution:**
- Modified `AssistantDashboardView.get_context_data()` to not pass previous messages to the template
- The conversation session is still maintained in the database for AI context
- Chat now starts fresh with just the welcome message on each page visit

**Files Modified:**
- `apps/ai/views.py` - Changed to pass empty messages list instead of conversation history

**Test Status:** All 43 PersonalAssistant tests passing

---

### Dashboard Tile Shortcut Links

Made the quick stat tiles at the top of the dashboard clickable, providing direct navigation to their respective detail pages.

**Clickable Tiles:**
- **Journal Streak (🔥)** - Now links to Journal Entries list (`/journal/entries/`)
- **Tasks Today (✓)** - Now links to Task List (`/life/tasks/`)
- **Active Prayers (🙏)** - Now links to Prayer List (`/faith/prayers/`)
- **Medicine Doses (💊)** - Now links to Medicine Tracker (`/health/medicine/`)
- **Workouts This Week (💪)** - Now links to Workout List (`/health/fitness/workouts/`)

**UI Improvements:**
- Tiles now have hover effects (lift, border highlight, shadow)
- Cursor changes to pointer on hover
- Active/click state provides tactile feedback
- Updated tooltips to indicate clickability

**Files Modified:**
- `templates/dashboard/home.html` - Changed `<div>` tiles to `<a>` links with appropriate URLs
- `static/css/dashboard.css` - Added `.quick-stat-link` styles for hover/active states

**Test Status:** All 56 dashboard tests passing

---

### Dashboard End Fast Button Fix

Fixed the "End Fast" button on the dashboard that was returning an HTTP 405 error.

**Problem:**
- The End Fast button on the dashboard was using an `<a href>` anchor tag which sends a GET request
- The `EndFastView` only accepts POST requests for safety (prevents CSRF attacks and accidental clicks from URL sharing)
- Clicking "End Fast" resulted in HTTP 405 Method Not Allowed error

**Solution:**
- Changed the End Fast button from an anchor tag to a proper POST form with CSRF token
- Added `onsubmit` confirmation dialog (same UX as before with `onclick`)
- Matches the implementation used in `fasting_list.html` and `health/home.html`

**Files Modified:**
- `templates/dashboard/home.html` - Changed End Fast button to POST form with CSRF token

---

### Weight and Nutrition Goals Feature

Added personal weight and nutrition goal tracking with progress display on the dashboard.

**New Features:**
- **Weight Goal** - Set a target weight and optional target date in Preferences
  - Supports both pounds (lb) and kilograms (kg)
  - Progress bar shows how close you are to your goal
  - Dashboard Health tile shows remaining weight to goal
- **Nutrition Goals** - Set daily caloric intake and macro percentages
  - Daily calorie goal (custom amount)
  - Macro split: Protein, Carbs, Fat percentages (must total 100%)
  - Preset macros: Balanced, High Protein, Low Carb, Keto
  - Calculates target grams from percentages automatically
- **Dashboard Progress Display**
  - Health tile shows weight progress bar with remaining to goal
  - New "Today's Nutrition" section shows:
    - Calories consumed vs goal
    - Macro progress bars (protein/carbs/fat)
    - Current vs target grams for each macro

**Model Changes (UserPreferences):**
- `weight_goal` - Target weight (DecimalField)
- `weight_goal_unit` - Unit (lb/kg)
- `weight_goal_target_date` - Optional target date
- `daily_calorie_goal` - Daily calorie target
- `protein_percentage` - Target protein % (0-100)
- `carbs_percentage` - Target carbs % (0-100)
- `fat_percentage` - Target fat % (0-100)

**New Methods (UserPreferences):**
- `has_weight_goal` - Property checking if weight goal is set
- `has_nutrition_goals` - Property checking if nutrition goals are set
- `macro_percentages_valid` - Property checking if macros sum to 100%
- `get_weight_progress()` - Calculates weight progress toward goal
- `get_nutrition_progress(date)` - Calculates nutrition progress for a date

**Files Modified:**
- `apps/users/models.py` - Added goal fields and progress methods
- `apps/users/forms.py` - Added goal fields with validation
- `templates/users/preferences.html` - New "Weight & Nutrition Goals" section
- `apps/dashboard/views.py` - Added goal progress to health data
- `templates/dashboard/home.html` - Health tile progress bar, nutrition section
- `static/css/dashboard.css` - Styles for goal progress indicators

**New Migration:**
- `apps/users/migrations/0019_add_weight_nutrition_goals.py`

**Test Status:** All 485 users/dashboard/health tests passing

---

### Medicine Refill Status Display and Overdue Dose Timezone Fix

Fixed two issues with the medicine tracking system:

**1. Refill Status Display Improvements:**
- Added separate green "Refill Requested" alert when medicines have pending refill requests
- Both "needs refill" and "refill requested" alerts now show clickable medicine name links
- Users can now easily see which specific medicine needs attention and click to manage it

**2. Overdue Dose Timezone Bug:**
- Fixed timezone comparison bug in `_is_overdue()` method
- Was comparing UTC time (from `timezone.now()`) against local scheduled time (naive datetime)
- For users in EST (UTC-5), this caused doses to show as "overdue" hours early
- Now properly converts current time to user's local timezone before comparison

**Files Modified:**
- `apps/health/views.py` - Fixed `_is_overdue()` timezone handling, added `refill_requested_medicines` context
- `templates/health/medicine/home.html` - Added refill requested alert, medicine name links, new CSS styles

---

### Blood Pressure & Blood Oxygen Tests Added

Added comprehensive tests for the new Blood Pressure and Blood Oxygen tracking features.

**New Tests (52 tests added):**
- `BloodPressureModelTest` - 14 tests for model creation, categorization, properties
- `BloodOxygenModelTest` - 10 tests for model creation, categorization, properties
- `BloodPressureViewTest` - 7 tests for list, create, update, delete views
- `BloodOxygenViewTest` - 7 tests for list, create, update, delete views
- `BloodVitalsDataIsolationTest` - 4 tests ensuring users can only see their own data

**Test Coverage:**
- Model creation and string representation
- Category classification (Normal, Elevated, High Stage 1/2, Crisis for BP; Normal, Low, Concerning, Critical for SpO2)
- Optional fields (pulse, context, arm, position, measurement method)
- View loading and form submission
- Data isolation between users

**Files Modified:**
- `apps/health/tests/test_health_comprehensive.py` - Added 52 new tests

**Test Status:** 97 health comprehensive tests, 346 total health tests, 1302 total tests, all passing

---

### Python 3.14 Autoreload Compatibility Issue

**Issue:** Django's autoreload mechanism fails on Python 3.14 due to changes in Python's import system. The error occurs in Django's autoreload subprocess when it tries to re-import apps.

**Root Cause:** Python 3.14 (released October 2025) has significant changes to its import system (`_find_and_load_unlocked` in `<frozen importlib._bootstrap>`). Django 5.2's autoreload subprocess spawns a child process that re-imports the entire Django application, and this fails on Python 3.14.

**Current Workaround:** Run the development server without autoreload:
```bash
python manage.py runserver --noreload
```

**Attempted Fix:** Added `django-watchfiles` (conditionally loaded in DEBUG mode only) which provides WatchfilesReloader instead of StatReloader. While WatchfilesReloader is more efficient, the underlying Python 3.14 import issue still affects the subprocess.

**Files Modified:**
- `config/settings.py` - Conditionally adds `django_watchfiles` when DEBUG=True and package is available
- `requirements.txt` - Added `django-watchfiles>=1.4.0` (development only)

**Production Impact:** None - production uses Gunicorn, not runserver

**Note:** This is likely a Django/Python 3.14 compatibility issue that will be resolved in future Django releases. For now, use `--noreload` flag.

---

### What's New Popup Fix and Release Notes Update

Fixed the "What's New" popup not appearing after updates and added release notes for December 29 features.

**Issue:** The What's New popup was comparing `created_at` (when the database record was created) instead of `release_date` (the logical feature release date). Since release notes are often created via data migrations at deployment time, all notes created in the same deployment had the same `created_at`, causing notes to not show if the user had already dismissed the popup.

**Fix:** Updated `ReleaseNote.get_unseen_for_user()` to use a combined query:
- Show notes where `release_date > last_seen_date` (notes from future days), OR
- Show notes where `release_date = last_seen_date AND created_at > last_viewed_at` (notes created same day but after viewing)

**New Release Notes Added (Migration 0011):**
- Blood Pressure & Blood Oxygen Tracking (major feature)
- Medicine Refill Request Tracking (enhancement)
- Default Fasting Type Preference (enhancement)
- Dashboard Fasting Widget (enhancement)
- Timezone-Aware Date Defaults (fix)

**Files Modified:**
- `apps/core/models.py` - Updated `get_unseen_for_user()` method
- `apps/core/tests/test_core_comprehensive.py` - Fixed tests for required `default_fasting_type` field
- `apps/ai/tests/test_ai_comprehensive.py` - Fixed test for required `default_fasting_type` field

**New Migration:**
- `apps/core/migrations/0011_december_29_release_notes.py`

**Test Status:** All 1250 tests passing

---

### Live Workout Tracking with Done Button and Rest Timer

Added real-time workout tracking with per-set saving and a rest timer between sets. This prevents data loss from unsaved forms during long workout sessions.

**Features:**
- **Done Button per Set** - Each resistance exercise set has a "Done" button that immediately saves to the database
- **Cardio Done Button** - Cardio exercises also have a Done button to save duration/distance/intensity
- **Rest Timer** - A countdown timer (0:00 to 1:10) appears after completing a set, helping track rest periods
  - Timer turns yellow/warning at 60 seconds
  - Auto-stops at 1 minute 10 seconds (70 seconds)
- **Visual Feedback** - Saved sets show green checkmark and "Saved" status
- **Status Banner** - Shows "Workout in progress - sets save automatically" with count of saved sets
- **Resume Support** - If you reload the page or come back later, in-progress workouts can be resumed

**New AJAX Endpoints:**
- `POST /health/fitness/api/start-workout/` - Creates new or resumes existing workout session
- `POST /health/fitness/api/save-set/` - Saves individual set (weight, reps)
- `POST /health/fitness/api/save-cardio/` - Saves cardio details (duration, distance, intensity)
- `POST /health/fitness/api/complete-workout/` - Marks workout as completed, calculates duration
- `GET /health/fitness/api/workout-state/<id>/` - Gets current state of in-progress workout

**How It Works:**
1. When you start a new workout (or add first exercise), a WorkoutSession is created with `started_at` timestamp
2. Clicking "Done" on a set immediately saves to database via AJAX (no form submission needed)
3. The rest timer starts automatically after each set is saved
4. When you click "Finish Workout", the session is marked complete and duration is calculated
5. If you have an in-progress workout from today, it resumes automatically

**Files Modified:**
- `apps/health/views.py` - Added 5 new AJAX view functions
- `apps/health/urls.py` - Added 5 new URL routes
- `templates/health/fitness/workout_form.html` - Complete rewrite with Done buttons, rest timer, and AJAX JavaScript
- `templates/health/fitness/partials/exercise_row.html` - Added Done buttons to server-rendered exercise rows
- `apps/health/tests/test_fitness.py` - Added 10 new tests for AJAX endpoints

**Test Status:** 63 fitness tests passing (53 original + 10 new AJAX tests), 305 total health tests passing

---

### Default Entry Dates with User Time Zone
Added user timezone-aware default dates to all entry forms throughout the application. Previously, some forms defaulted to UTC or had no default at all. Now all date/datetime entry forms default to the user's local date based on their configured timezone.

**Forms Updated:**
- **Journal App** - `JournalEntryForm.entry_date` now defaults to user's local date
- **Faith App** - `FaithMilestoneForm.date` now defaults to user's local date
- **Health App** - `MedicineForm.start_date` now uses user's local date instead of UTC
- **Life App** - Multiple views updated:
  - `ProjectCreateView` - `start_date` defaults to user's local date
  - `EventCreateView` - `start_date` and `end_date` default to user's local date
  - `PetRecordCreateView` - `date` defaults to user's local date
  - `MaintenanceLogCreateView` - `date` defaults to user's local date
  - `DocumentCreateView` - `document_date` defaults to user's local date

**How It Works:**
- Uses `get_user_today(user)` from `apps.core.utils` which gets the current date in the user's configured timezone
- User can still override the default date if needed
- Properly handles timezone conversion using the user's preferences

**Files Modified:**
- `apps/journal/forms.py` - Added import and default for `entry_date`
- `apps/faith/forms.py` - Added `__init__` method with user parameter and default for `date`
- `apps/faith/views.py` - Added `get_form_kwargs` to pass user to `FaithMilestoneForm`
- `apps/health/forms.py` - Updated `MedicineForm` to use `get_user_today(user)`
- `apps/life/views.py` - Added `get_initial` methods with user timezone defaults to multiple views

**Test Status:** All 1250 tests passing

---

### Medical Updates - Blood Pressure, Blood Oxygen, and Medicine Refill Tracking

Added two new health metrics (Blood Pressure and Blood Oxygen tracking) and a medicine refill request status feature.

**Blood Pressure Tracking:**
- New `BloodPressureEntry` model with systolic, diastolic, pulse, context, arm, and position fields
- Automatic categorization according to AHA guidelines (Normal, Elevated, High Stage 1, High Stage 2, Hypertensive Crisis)
- CRUD views: list, create, update, delete
- Integrated into Health home page with latest reading and averages

**Blood Oxygen (SpO2) Tracking:**
- New `BloodOxygenEntry` model with SpO2 percentage, pulse, context, and measurement method fields
- Automatic categorization (Normal ≥95%, Low 90-94%, Concerning 85-89%, Critical <85%)
- CRUD views: list, create, update, delete
- Integrated into Health home page with latest reading and averages

**Medicine Refill Request Status:**
- New `refill_requested` and `refill_requested_at` fields on Medicine model
- "Request Refill" button when supply is low
- "Refill Received" button to clear request status
- Dashboard shows "Refill Requested" status instead of "needs refill" when request is pending
- Updated dashboard nudges to differentiate between "needs refill" and "refill requested" medicines

**Files Created:**
- `templates/health/blood_pressure_list.html`
- `templates/health/blood_pressure_form.html`
- `templates/health/blood_oxygen_list.html`
- `templates/health/blood_oxygen_form.html`
- `apps/health/migrations/0009_add_blood_pressure_oxygen_and_refill_tracking.py`

**Files Modified:**
- `apps/health/models.py` - Added BloodPressureEntry, BloodOxygenEntry models; added refill_requested fields to Medicine
- `apps/health/forms.py` - Added BloodPressureEntryForm, BloodOxygenEntryForm
- `apps/health/views.py` - Added views for BP, SpO2, and refill request/clear
- `apps/health/urls.py` - Added URL routes for new features
- `apps/dashboard/views.py` - Updated nudges for refill_requested status
- `templates/dashboard/home.html` - Added refill_requested nudge type
- `templates/health/home.html` - Added Blood Pressure and Blood Oxygen cards
- `templates/health/medicine/medicine_detail.html` - Added refill request/clear buttons and status display

**Test Status:** All 1250 tests passing

---

### Default Fasting Type Preference
Added user preference for selecting a default fasting type that pre-populates when starting a new fast.

**Features:**
- New `default_fasting_type` field in UserPreferences model
- 7 fasting types with detailed descriptions (16:8, 18:6, 20:4, OMAD, 24h, 36h, Custom)
- Health Settings section in Preferences page for configuring default fasting type
- Interactive fasting type cards with descriptions - click to select
- Start Fast form now pre-selects user's preferred fasting type
- Improved Start Fast form with visual fasting guide and descriptions

**Files Modified:**
- `apps/users/models.py` - Added `FASTING_TYPE_CHOICES`, `FASTING_TYPE_DESCRIPTIONS`, and `default_fasting_type` field
- `apps/users/forms.py` - Added `default_fasting_type` to PreferencesForm
- `apps/health/views.py` - Updated StartFastView with `get_initial()` and `get_context_data()` methods
- `templates/users/preferences.html` - Added Health Settings section with fasting type selector
- `templates/health/fasting_form.html` - Enhanced with fasting type descriptions and interactive cards
- `apps/users/tests/test_users.py` - Updated test to include new field

**New Migration:**
- `0018_add_default_fasting_type.py`

**Test Status:** All 470 tests passing

---

### Dashboard Current Fast Widget
Added a prominent widget on the dashboard showing the current active fast with a real-time updating timer.

**Features:**
- Real-time updating timer showing hours:minutes:seconds since fast started
- Progress bar toward target hours (when target is set)
- Fast type display (16:8, 18:6, OMAD, etc.)
- Quick action buttons to End Fast or View Details
- Green-themed styling to match health/fasting theme
- Responsive design for mobile devices

**Files Modified:**
- `templates/dashboard/home.html` - Added current fast widget section with JavaScript timer
- `static/css/dashboard.css` - Added `.current-fast-section`, `.fast-card`, `.fast-timer`, and related styles

**Technical Details:**
- Widget only displays when `health_enabled` and `user_data.active_fast` exist
- JavaScript reads `data-started` attribute (ISO format) to calculate elapsed time
- Timer updates every second using `setInterval`
- Progress bar updates dynamically toward target hours
- End Fast button uses confirmation dialog

**Test Status:** All 350 dashboard/health tests passing

---

### Fixed Food Log Delete HTTP 405 Error
Fixed the delete button on the nutrition home page that was causing HTTP 405 (Method Not Allowed) errors.

**Problem:**
- Delete buttons were implemented as anchor tags (`<a href="...">`) that sent GET requests
- The `FoodEntryDeleteView` only accepts POST requests for safety
- Clicking delete would result in HTTP 405 error

**Solution:**
- Changed all delete buttons in breakfast, lunch, dinner, and snacks sections from anchor tags to proper POST forms with CSRF tokens
- Added `.inline-form` CSS class to style the inline form element
- Updated `.food-actions` CSS to align items properly

**Files Modified:**
- `templates/health/nutrition/home.html` - Changed delete links to POST forms (4 locations)

---

### Assistant Priorities - Completion Tracking & Positive Feedback
Fixed issues with the Dashboard AI assistant's "Today's Priorities" feature to properly track completions and provide positive reinforcement.

**Issues Fixed:**
1. **Refresh button was resetting completion status** - When clicking "Refresh", previously completed priorities were being deleted and regenerated. Now completed priorities are preserved across refreshes.
2. **No positive feedback for completions** - Added encouraging toast notifications when users complete a priority, with messages tailored to the priority type (faith, purpose, commitment, health, personal).
3. **Added completion statistics** - New `get_completion_stats()` method on DailyPriority model for analytics tracking.

**How it Works Now:**
- Completed priorities persist and won't be regenerated on refresh
- New priorities are generated to fill remaining slots (max 5 total)
- Duplicate priorities (same title) are avoided
- Type-specific positive feedback messages appear when completing priorities
- Completion history is preserved for analytics (completion rate, daily breakdown, type breakdown)

**Files Modified:**
- `apps/ai/personal_assistant.py` - Updated `generate_daily_priorities()` to preserve completed priorities on refresh
- `apps/ai/views.py` - Added feedback messages to `PriorityCompleteView` with type-specific encouragement
- `apps/ai/models.py` - Added `get_completion_stats()` classmethod for analytics
- `templates/ai/assistant_dashboard.html` - Added completion feedback toast notification with CSS styling

**Test Status:** All 1261 tests passing (including 142 AI tests)

---

### Fasting Edit Feature
Added ability to edit completed fasts to correct start/end times.

**Files Modified:**
- `templates/health/fasting_list.html` - Added Edit button to completed fasts in history
- `apps/health/forms.py` - Updated `FastingWindowForm` to convert UTC times to user's local timezone when editing
- `templates/health/fasting_form.html` - Fixed end time field to use proper timezone-aware initial values

**Functionality:**
- Users can now edit any completed fast from the fasting history list
- Start time and end time fields display in user's local timezone
- Times are correctly converted back to UTC when saved

---

### Delete Button Added to Nutrition Food Entries
Added a Delete button next to the Edit button on the nutrition home page for easier food entry management.

**Note:** Initial implementation used anchor tags which caused HTTP 405 errors. See "Fixed Food Log Delete HTTP 405 Error" above for the fix.

**Changes:**
- Added Delete link with confirmation prompt for all meal sections (Breakfast, Lunch, Dinner, Snacks)
- Added CSS styling for `.text-danger` class and `.food-actions` layout

**Files Modified:**
- `templates/health/nutrition/home.html` - Added delete buttons and styling

---

### Enhanced Food Recognition for Packaged/Branded Foods
Enhanced the camera scan feature to recognize branded/packaged foods and look up actual nutritional data.

**Changes:**
- Updated vision prompt with examples for packaged foods (e.g., Aloha protein bars)
- AI now looks up actual nutritional data from its knowledge base for recognized brands
- Added brand field extraction and URL parameter passing
- Made all nutritional fields optional in `FoodEntryForm` (calories, protein, carbs, fat, etc.)
- Added `default=0` to `total_calories` field in FoodEntry model

**Files Modified:**
- `apps/scan/services/vision.py` - Enhanced prompt with branded food examples, updated `_build_actions`
- `apps/health/forms.py` - Made nutritional fields optional
- `apps/health/models.py` - Added default=0 to total_calories

**New Migration:**
- `0008_make_total_calories_default_zero.py`

---

### Food Recognition from Camera Scan (Initial Implementation)
Enhanced the camera scan feature to recognize food and extract detailed nutritional information.

**Changes:**
- Updated vision service prompt to request detailed nutritional estimates (calories, protein, carbs, fat, fiber, sugar, saturated fat, serving size/unit, meal type)
- Changed food scan routing from journal entry to nutrition log form (`health:food_entry_create`)
- Added URL parameter prefilling for all nutritional fields in `FoodEntryCreateView`
- Set `entry_source` to 'camera' when coming from AI scan
- Added `from_camera` context variable for potential UI customization

**Files Modified:**
- `apps/scan/services/vision.py` - Enhanced food example in prompt, updated `_build_actions` for food
- `apps/health/views.py` - Updated `FoodEntryCreateView.get_initial()` and `form_valid()`
- `apps/scan/tests/test_vision.py` - Updated test for new module name
- `apps/health/tests/test_nutrition.py` - Added 2 new tests for camera prefill

**Flow:**
1. User takes picture of food
2. AI recognizes food and estimates nutritional values (or looks up branded food data)
3. User clicks "Log to Nutrition"
4. Food entry form opens with all fields pre-filled (name, brand, calories, macros, serving info)
5. User confirms or adjusts values and saves

---

### Added Comprehensive Fitness CRUD Tests
Added comprehensive test suite for fitness module covering workouts and workout templates CRUD operations.

**New Test File:** `apps/health/tests/test_fitness.py` (52 tests)

**Test Coverage:**
- Exercise model tests (resistance and cardio)
- WorkoutSession model tests (creation, properties, ordering)
- WorkoutTemplate model tests (creation, exercise count)
- Workout CRUD view tests (list, create, detail, update, delete, copy)
- Template CRUD view tests (list, create, detail, update, delete, use)
- Data isolation tests (users can only see/modify their own data)
- Cardio exercise handling tests
- Fitness home view tests
- Personal records tracking tests
- Edge cases and validation tests

**Existing Fitness CRUD Verified:**
The fitness module already had full CRUD functionality implemented:
- Workouts: Create, Read (list/detail), Update, Delete
- Templates: Create, Read (list/detail), Update, Delete
- Delete buttons available on workout_detail.html and template_detail.html
- Copy workout feature implemented
- Use template feature (redirects to create with template prefilled)

**Health Module Total Tests:** 292 tests (all passing)

---

### Workout Templates Data Load
Created a one-time data loading command to import 10 workout templates for dannyjenkins71@gmail.com based on a 4-week workout program (Week 1&3 and Week 2&4 variations).

**New Files:**
- `apps/health/management/commands/load_danny_workout_templates.py`

**Creates:**
- 20 additional exercises (Box Squat, KB Lunges, Ab Crunch Machine, etc.)
- 10 workout templates (5 for Week 1&3, 5 for Week 2&4)
  - Monday Strength, Tuesday Cardio, Wednesday Strength, Thursday Cardio, Friday Strength

**Procfile updated** to run command on deploy (idempotent - safe to run multiple times)

**CLAUDE.md updated** with "One-Time Data Loading Pattern" documentation for Railway deployments (no shell access)

---

### Dashboard AI Personal Assistant
Implemented comprehensive Dashboard AI Personal Assistant feature. This is NOT a chatbot - it's a personal life assistant that helps users live the life they said they want to live, anchoring all guidance to user's stated Purpose, Goals, intentions, and commitments.

**Core Philosophy:**
- Faith-first prioritization (for users with faith enabled): Faith → Purpose → Long-term goals → Commitments → Maintenance → Optional
- Honors user's journey - doesn't lecture or give unsolicited advice
- Celebrates wins and progress
- Provides gentle accountability nudges
- Generates personalized reflection prompts

**New Models (6 models):**
- `AssistantConversation` - Conversation sessions with session types (daily_checkin, reflection, planning, etc.)
- `AssistantMessage` - Individual messages with roles (user, assistant, system)
- `UserStateSnapshot` - Daily snapshots of user state across all dimensions
- `DailyPriority` - AI-suggested daily priorities with source tracking
- `TrendAnalysis` - Weekly/monthly trend analysis with pattern detection
- `ReflectionPromptQueue` - Personalized reflection prompts based on user context

**New Services:**
- `apps/ai/personal_assistant.py` (~800 lines)
  - State assessment across all dimensions (journal, tasks, goals, faith, health)
  - Priority generation following strict ordering
  - Reflection prompt generation
  - Opening message/daily check-in
  - Conversation management with context

- `apps/ai/trend_tracking.py` (~400 lines)
  - Weekly/monthly analysis generation
  - Pattern detection in user behavior
  - Drift detection from stated intentions
  - Goal progress reporting

**API Endpoints (16 endpoints):**
- `GET /assistant/` - Full-page assistant dashboard
- `GET /assistant/api/opening/` - Opening message/daily check-in
- `POST /assistant/api/chat/` - Send message to assistant
- `GET /assistant/api/history/` - Get conversation history
- `POST /assistant/api/feedback/` - Submit message feedback
- `GET /assistant/api/priorities/` - Get/regenerate daily priorities
- `POST /assistant/api/priorities/<id>/complete/` - Mark priority complete
- `POST /assistant/api/priorities/<id>/dismiss/` - Dismiss priority
- `GET /assistant/api/state/` - Get current state assessment
- `GET /assistant/api/analysis/weekly/` - Weekly trend analysis
- `GET /assistant/api/analysis/monthly/` - Monthly trend analysis
- `GET /assistant/api/analysis/drift/` - Drift detection
- `GET /assistant/api/analysis/goals/` - Goal progress report
- `GET /assistant/api/reflection/` - Get reflection prompt
- `POST /assistant/api/reflection/used/` - Mark prompt as used

**UI Components:**
- Full-page assistant dashboard (`templates/ai/assistant_dashboard.html`)
- Daily check-in card with state summary
- Priority list with complete/dismiss actions
- Celebrations and nudges display
- Chat sidebar with conversation history
- HTMX-powered dynamic updates

**Tests:** 45 comprehensive tests covering models, services, APIs, authentication, and edge cases.

**Files:**
- `apps/ai/models.py` - Extended with 6 new models
- `apps/ai/personal_assistant.py` - Core personal assistant service
- `apps/ai/trend_tracking.py` - Trend analysis service
- `apps/ai/views.py` - Completely rewritten with 16 API endpoints
- `apps/ai/urls.py` - New URL configuration
- `config/urls.py` - Added AI assistant route
- `templates/ai/assistant_dashboard.html` - Full-page UI
- `apps/ai/migrations/0007_dashboard_ai_personal_assistant.py` - Database migration
- `apps/ai/tests/test_personal_assistant.py` - Comprehensive test suite

**Migration:** `0007_dashboard_ai_personal_assistant` creates all new tables with proper indexes and constraints.

**Backup Tag:** `pre-dashboard-ai-20251229-091948` created before implementation.

---

### Fix Medicine Tracker Dashboard Link 404
Fixed incorrect URL in dashboard nudge for medicine tracker. The "Open Tracker" action link was pointing to `/health/medicine/tracker/` which doesn't exist, causing a 404 error.

**Fix:** Changed action_url from `/health/medicine/tracker/` to `/health/medicine/` in the pending medicine doses nudge.

**File:** `apps/dashboard/views.py:748`

---

## 2025-12-28 Changes

### Timezone Fix for Task Priorities
Fixed critical bug where task priority calculation (Now/Soon/Someday) was using UTC timezone instead of the user's configured timezone. This caused tasks to show incorrect priorities for users in different timezones.

**Fixed properties/methods:**
- `Task.calculate_priority()`: Now uses `get_user_today(self.user)` to calculate priority based on user's timezone
- `Task.is_overdue`: Uses user's timezone
- `Project.is_overdue`: Uses user's timezone
- `LifeEvent.is_past/is_today`: Uses user's timezone
- `Pet.age`: Uses user's timezone
- `Document.is_expiring_soon/is_expired`: Uses user's timezone
- `Medicine.complete()`: Uses user's timezone for end_date
- `NutritionGoals.is_active/save()`: Uses user's timezone

**Files:** `apps/life/models.py`, `apps/health/models.py`

---

### AI Personal Profile
Added personal AI profile feature to Preferences. Users can enter details about themselves (age, family, health conditions, interests, goals, etc.) that the AI uses to personalize dashboard insights and coaching messages.

**Features:**
- New `ai_profile` TextField in UserPreferences model (max 2000 chars)
- Personal AI Profile section in Preferences page (shown when AI enabled + data consent given)
- Content moderation via `apps/ai/profile_moderation.py` - blocks prompt injection attempts, harmful content, and sanitizes input
- Integration with AIService's system prompts - profile wrapped in bounded context with safety guidelines

**Security measures:** regex-based prompt injection detection (16 patterns), harmful content filtering, PII warnings (email, SSN patterns), control character removal, prompt delimiter escaping. Industry best practice: profile passed as bounded user-provided context, never treated as system instructions.

**Files:** `apps/users/models.py`, `apps/users/migrations/0016_add_ai_profile.py`, `apps/ai/profile_moderation.py`, `apps/ai/services.py`, `apps/ai/dashboard_ai.py`, `templates/users/preferences.html`, `apps/ai/tests/test_ai_comprehensive.py` (24 tests).

---

### Profile Picture Save Fix
Fixed bug where profile picture (avatar) was not being saved for some users (reported by heatherjenkins74@gmail).

**Issues identified:**
1. The ProfileForm used `FileInput` widget which doesn't preserve existing files when form is resubmitted without a new file - existing avatars were being cleared on any profile update. Fixed by adding logic in `save()` method to restore `self.instance.avatar` when no new file is uploaded.
2. The `clean_avatar()` method's content_type validation could reject valid images from iPhone (HEIC/HEIF) or browsers that send `application/octet-stream`. Added support for `image/heic`, `image/heif`, `image/webp`, and `application/octet-stream` content types.

**Files:** `apps/users/forms.py` (ProfileForm.clean_avatar, ProfileForm.save), `apps/users/tests/test_users_comprehensive.py` (6 new tests).

---

### AI Camera Medicine Purpose Auto-Fetch
When scanning a medicine bottle with AI Camera, the OpenAI Vision API now automatically looks up the common medical purpose of the medication (e.g., "blood pressure control", "pain relief", "cholesterol management") and includes it in the action URL. The medicine create form reads this purpose parameter and pre-populates the purpose field.

**Files:** `apps/scan/services/vision.py`, `apps/health/tests/test_medicine.py`, `apps/scan/tests/test_vision.py` (6 new tests).

---

### AI Camera Medicine Form Prefill Fix
Fixed bug where AI Camera scanned medicine data was not populating the medicine add form.

**Fixes:**
1. Added `get_initial()` method to `MedicineCreateView` to read query parameters (name, dose, directions, quantity, purpose)
2. Updated vision service `_build_actions()` to include all extracted fields in the URL

**Files:** `apps/health/views.py`, `apps/scan/services/vision.py` (11 new tests).

---

### Task List Sorting & Single-Click Fix
Fixed two task list issues:
1. Task sorting now correctly orders by Now, Soon, Someday instead of alphabetical
2. Fixed task checkbox requiring double-click to complete

**Files:** `apps/life/views.py`, `templates/life/task_list.html`.

---

### Mobile Menu Toggle Contrast Fix
Fixed issue where the hamburger menu button lost contrast on dark-header themes (Faith, Sports, Nature, Outdoors).

**Files:** `static/css/themes.css`.

---

### Task Completion Popup & Auto-Priority
1. Task completion popup - green checkmark appears for 3 seconds when completing a task
2. Auto-priority based on due date: Now = due today/overdue, Soon = within 7 days, Someday = 7+ days

**Files:** `apps/life/models.py`, `apps/life/views.py`, `templates/life/task_form.html`, `templates/life/task_list.html` (6 new tests).

---

### Biometric/Face ID Login
Added WebAuthn-based biometric login for mobile devices (Face ID, Touch ID, Windows Hello).

**Models:** `WebAuthnCredential` stores device credentials.
**Views:** BiometricCheckView, BiometricCredentialsView, BiometricRegisterBeginView/CompleteView, BiometricLoginBeginView/CompleteView, BiometricDeleteCredentialView.

**Files:** `apps/users/models.py`, `apps/users/views.py`, `apps/users/urls.py`, `templates/users/preferences.html`, `templates/account/login.html`, `static/js/biometric.js` (32 new tests).

---

### What's New Feature
Added "What's New" popup system to inform users of new features since their last visit.

**Models:** `ReleaseNote`, `UserReleaseNoteView`.
**Views:** WhatsNewCheckView, WhatsNewDismissView, WhatsNewListView.

**Files:** `apps/core/models.py`, `apps/core/views.py`, `templates/components/whats_new_modal.html`, `templates/core/whats_new_list.html`, `static/js/whats_new.js` (23 new tests).

---

### Scan Image Auto-Attachment to Inventory
Scanned images are now automatically saved to inventory items created via AI Camera.

**Files:** Multiple scan/inventory files (3 new tests).

---

### Expanded Camera Scan Module Support
Extended AI Camera to recognize: inventory_item, recipe, pet, maintenance categories.

**Files:** Vision service, Life module views (7 new tests).

---

### Dashboard and AI Integration for Medicine, Workout, Scan
Dashboard now shows: Today's Medicine Schedule, Recent Workouts, Quick Stats. AI integration updated for medicine adherence, workout tracking, scan activity.

---

### Food/Nutrition Tracking
Added comprehensive Nutrition section with food logging, macro tracking, daily summaries, and nutrition goals.

**Models:** FoodItem, CustomFood, FoodEntry, DailyNutritionSummary, NutritionGoals.

---

### AI Camera Source Tracking
Added `created_via` field on `UserOwnedModel` base class. Entries from AI Camera marked as `ai_camera`.

**Files:** Multiple files (16 new tests).

---

### Medicine Schedule Fixes
Fixed critical bug where medicine schedules weren't appearing in Today's Schedule. Added "Daily" button, day-of-week indicators, Activate button.

---

### Camera Scan Feature
Added comprehensive Camera Scan feature with OpenAI Vision API integration. See `docs/CAMERA_SCAN_ARCHITECTURE.md`.

**Files:** Multiple scan app files (70 new tests).

---

### Medicine Tracking Section
Added Medicine section to Health module with daily tracker, adherence stats, PRN support, refill tracking (77 new tests).

---

### CSO Security Review & Fixes
Comprehensive security review with 21 findings. See `SECURITY_REVIEW_REPORT.md`.

**Critical fixes:**
- C-2: Bible API key removed from frontend
- C-3: AI data consent field added
- H-3: Rate limiting via django-axes
- H-4: Django admin moved to configurable path
- M-1: SameSite cookie attribute configured

---

### Django-allauth Deprecation Warnings Fix
Updated settings.py to use new django-allauth settings format.

---

### Backup and Disaster Recovery Playbook
Added comprehensive BACKUP.md document.

---

### Edit/Delete Saved Scripture Verses
Added ability to edit and delete saved Scripture verses from the Scripture Library.

---

### Test Suite Onboarding Fixes
Fixed 185+ test failures caused by onboarding middleware. All test setups now call `_complete_onboarding()`.

---

### User-Specific Saved Verses
Fixed bug where saved Scripture verses were shared across all users. Created `SavedVerse` model with user ownership.

---

### Project Add Task Default
When adding a task from within a project, the project dropdown auto-selects that project.

---

### Dev Environment Dependency Check
Added `check_dependencies.py` script.

---

### Task Undo Link
Added "Undo" link next to completed tasks.

---

### Journal Prompts Migration
Data migration (`0003_load_journal_prompts.py`) to load 20 journal prompts.

---

### ChatGPT Journal Import
Management command (`import_chatgpt_journal`) for one-time data migration from ChatGPT JSON exports.

**Usage:**
```bash
python manage.py import_chatgpt_journal export.json --dry-run
python manage.py import_chatgpt_journal export.json --user=email@example.com
```

**Expected JSON Format:**
```json
[
  {
    "date": "2025-12-03",
    "faith": "Faith content or null",
    "health": "Health content or null",
    "family": "Family content or null",
    "work": "Work content or null",
    "reflection_summary": "Summary text"
  }
]
```

---

### Step-by-Step Onboarding Wizard
New 6-step wizard for new users (Welcome, Theme, Modules, AI Coaching, Location, Complete).

---

### Database-Driven AI Prompts
AIPromptConfig model allows admin control of all AI prompt types (10 types).

---

### Database-Driven Coaching Styles
CoachingStyle model with 7 styles, editable via Django admin.

---

## Earlier Changes (Pre-2025-12-28)

- Django admin improvements: "Back to Admin Console" link, fixed capitalization
- Life dashboard: Quick Access tiles show counts
- Test history: Dev-only "Run Tests" button
- Fitness tracking: Comprehensive fitness tracking feature
- Google Calendar: Added API dependencies
- Preferences page: Dynamic coaching style rendering
- Fixture loading: Fixed to use fixture names without app prefix
- Login page CSS: Fixed auth_content block
- Timezone display: Fasting list uses timezone tag
- Faith module default: Changed to default=True
- Speech-to-text: Set continuous: false
- Superuser creation: Only creates if user doesn't exist
- Footer logo: Increased size to 200px
- Custom domain: Added wholelifejourney.com support
- Media files: Fixed serving in production

---

## Security Audit Details (2025-12-28)

### Current Health Score: 8.5/10

### CRITICAL Issues (Fixed)
1. **Open Redirect Vulnerability** - Created `is_safe_redirect_url()` and `get_safe_redirect_url()` utilities in `apps/core/utils.py`. Fixed 3 vulnerable locations.
2. **Hardcoded API Key** - Removed hardcoded Bible API key from `config/settings.py`.

### HIGH Priority Issues (Fixed)
1. **Bare except clauses (10+ locations)** - Replaced with specific exception types
2. **XSS Risk in HTMX Response** - Added `django.utils.html.escape()` to `RandomPromptView`
3. **Unsafe Client IP Extraction** - Added validation to `get_client_ip()`
4. **Missing Custom Error Pages** - Created `templates/404.html` and `templates/500.html`
5. **Console-Only Logging** - Added persistent logging with RotatingFileHandler

### Audit Checklist
```bash
# Check for bare except clauses
grep -rn "except:" apps/ --include="*.py" | grep -v "except Exception"

# Check for |safe filter usage
grep -rn "|safe" templates/

# Check for hardcoded emails
grep -rn "@.*\.com" apps/ --include="*.py" | grep -v test

# Run full test suite
python run_tests.py
```

### Remaining Issues (Medium/Low)
- Error dashboard widget
- Health check endpoint
- Input validation improvements
- Large file splitting (views.py files over 500 lines)

---

*Last updated: 2025-12-28*
