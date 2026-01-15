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
