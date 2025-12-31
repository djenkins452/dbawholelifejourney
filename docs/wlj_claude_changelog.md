# ==============================================================================
# File: docs/wlj_claude_changelog.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Historical record of fixes, migrations, and changes
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-28
# Last Updated: 2025-12-31 (AI Caching Optimizations, Cascading Menu, Memory Verse, SMS Preferences fix)
# ==============================================================================

# WLJ Change History

This file contains the historical record of all fixes, migrations, and significant changes.
For active development context, see `CLAUDE.md` (project root).

---

## 2025-12-31 Changes

### AI Caching Optimizations

Performed comprehensive AI usage assessment and implemented caching optimizations to reduce API costs and improve performance without sacrificing features.

**Assessment Report Created:**
- `docs/wlj_ai_assessment.md` - Complete analysis of AI architecture and API call patterns

**Optimizations Implemented:**

1. **System Prompt Caching** (`apps/ai/services.py`)
   - System prompts now cached by coaching style + faith enabled combination
   - Cache key: `system_prompt_{coaching_style}_{faith_enabled}`
   - TTL: 1 hour
   - Reduces redundant prompt building on every API call

2. **Instance-Level User Data Caching** (`apps/ai/dashboard_ai.py`)
   - Added `get_user_data()` method with per-instance caching
   - Added `get_reflection_data()` method with per-instance caching
   - Prevents redundant database queries when multiple methods call `_gather_user_data()`

3. **Cache Invalidation on Config Changes** (`apps/ai/models.py`)
   - Added `invalidate_system_prompt_cache()` helper function
   - CoachingStyle.save() now invalidates system prompt cache
   - AIPromptConfig.save() now invalidates system prompt cache
   - Ensures cached prompts are refreshed when admin changes AI configuration

**Files Modified:**
- `apps/ai/services.py` - Added system prompt caching, updated header
- `apps/ai/dashboard_ai.py` - Added instance-level user data caching, updated header
- `apps/ai/models.py` - Added cache invalidation on save, updated header

**Test Fix:**
- `apps/ai/tests/test_ai_comprehensive.py` - Added required SMS quiet hours fields to PreferencesForm test

**Estimated Impact:**
- ~25% reduction in API costs through better caching
- Reduced database queries per request
- Faster response times for dashboard and personal assistant

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
  - Nutrition: Nutrition Home, Food History, Statistics, Goals
  - Providers: Medical Providers, Fasting
- Life - Two-column: Home, Calendar, Projects, Tasks, Inventory, Pets, Recipes, Maintenance, Documents
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

*Last updated: 2025-12-31*
