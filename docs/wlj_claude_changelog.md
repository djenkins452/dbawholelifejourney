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

## 2026-01-14 Changes

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
