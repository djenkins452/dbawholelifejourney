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

## 2026-01-12 Changes

### New: WLJ Transcribe Recordings Project Plan

**Summary:** Created comprehensive project plan for audio transcription and summary feature ("Capture").

**Feature:** Users can record audio in browser or upload audio files, which are transcribed via OpenAI Whisper and summarized by Claude AI into a structured BLUF-format document. Users can save, export to PDF, and email summaries.

**Project Structure:**
- Phase 1: Foundation (3 tasks) - App structure, CaptureEntry model, S3 storage
- Phase 2: Recording UI (4 tasks) - List view, browser recording, file upload, navigation
- Phase 3: Processing Pipeline (5 tasks) - S3 upload, Whisper, AI summarization, Celery
- Phase 4: Review & Save (3 tasks) - Detail view, title editing, category selection
- Phase 5: Export & Sharing (2 tasks) - PDF generation, email sharing
- Phase 6: Retention & Cleanup (3 tasks) - Auto-purge, reminder emails, expired UI
- Phase 7: Polish (4 tasks) - Error handling, filtering, comprehensive testing

**Files Created:**
- `apps/admin_console/fixtures/capture_project.json` - 24 executable tasks in JSON format

**To Load:** `python manage.py load_project_from_json apps/admin_console/fixtures/capture_project.json`

---

## 2026-01-14 Changes

### New: AI Summarization with BLUF Format (Task #248)

**Summary:** Implemented AI summarization service using OpenAI API for structured BLUF-format summaries.

**Files Created:**
- `apps/capture/services/summarization.py` - SummarizationService class with BLUF prompt template
- `apps/capture/tests/test_summarization.py` - 18 comprehensive tests for summarization service

**Files Modified:**
- `apps/capture/services/__init__.py` - Added summarization_service export

**BLUF Summary Sections:**
1. BLUF (Bottom Line Up Front) - 2-3 sentence executive summary
2. Key Points - 3-5 bullet points of important ideas
3. Scripture References - Bible verses mentioned (or "None found")
4. Action Items - Specific actions the listener could take
5. Notable Quotes - 2-3 memorable quotes
6. Detailed Notes - 3-5 paragraph comprehensive summary

**Implementation Details:**
- `SummarizationService` class following existing AI service patterns
- `summarize_transcript(capture_entry)` method calls OpenAI, updates CaptureEntry
- Long transcripts (>100k chars) automatically truncated with indicator
- Temperature 0.3 for consistent, reliable output
- Max 4000 tokens for comprehensive summaries
- Automatic status transitions: summarizing -> ready (success) or failed (error)

**Error Handling:**
- SummarizationError with separate technical/user messages
- Empty transcript detection
- API rate limit handling
- Authentication error detection
- Context length exceeded handling
- Generic error fallback with user-friendly message

**Testing:**
- Service initialization tests (API key, model configuration)
- Success flow with mocked API response
- Error scenarios (no transcript, empty response, API errors)
- Truncation tests for long transcripts
- BLUF prompt validation tests

---

### New: OpenAI Whisper Transcription Service (Task #247)

**Summary:** Implemented transcription service using OpenAI Whisper API with support for large files.

**Files Created:**
- `apps/capture/services/__init__.py` - Package exports for transcription_service
- `apps/capture/services/transcription.py` - TranscriptionService class with Whisper integration
- `apps/capture/tests/test_transcription.py` - 24 comprehensive tests for transcription service

**Implementation Details:**
- `TranscriptionService` class follows existing AIService pattern (singleton, availability check)
- `transcribe_audio(capture_entry)` method downloads audio, calls Whisper, updates CaptureEntry
- Handles Whisper's 25MB file size limit with ffmpeg compression fallback
- User-friendly error messages for all failure scenarios (timeout, auth, rate limit, etc.)
- Automatic status transitions: transcribing -> summarizing (on success) or failed (on error)
- Supports all Whisper audio formats: mp3, wav, webm, m4a, ogg, flac, etc.

**Error Handling:**
- TranscriptionError exception with separate technical and user-friendly messages
- Download timeout handling (120s limit)
- API authentication error detection
- Rate limit error detection with retry guidance
- Empty transcript handling (no speech detected)
- Invalid audio format handling

**Testing:**
- Service initialization tests (API key present/absent)
- Successful transcription flow tests
- Error scenario tests (no URL, timeout, download error, empty transcript)
- API error tests (rate limit, authentication)
- Compression tests (large files trigger compression, small files skip)
- Filename detection from content type and URL

---

### New: Audio Upload to S3 Implementation (Task #246)

**Summary:** Created backend endpoint and logic to upload recorded/uploaded audio to S3 and create CaptureEntry with proper status workflow.

**Files Modified:**
- `apps/capture/views.py` - Added CaptureSubmitView and CaptureStatusView
- `apps/capture/urls.py` - Added 'submit/' and 'status/<uuid:entry_id>/' routes
- `apps/capture/tests/test_views.py` - Added 17 tests for submission flow (61 total)

**New Views:**
- `CaptureSubmitView` - Handles two actions:
  - `get_upload_url`: Generates presigned S3 URL for direct browser upload, creates CaptureEntry with status='uploading' and audio_expires_at set to 7 days
  - `confirm_upload`: Confirms upload completed, updates status to 'transcribing'
  - Mock mode fallback when S3 not configured (for development/testing)
- `CaptureStatusView` - Returns entry status for frontend polling (supports status, error_message, summary, transcript)

**API Endpoints:**
- `POST /capture/submit/` - JSON body with action='get_upload_url' or 'confirm_upload'
- `GET /capture/status/<entry_id>/` - Returns current entry status for polling

**Workflow:**
1. Frontend calls `get_upload_url` -> receives presigned S3 URL + entry_id
2. Frontend uploads directly to S3 using presigned URL
3. Frontend calls `confirm_upload` with entry_id -> status changes to 'transcribing'
4. Frontend polls `status/<entry_id>/` until processing complete

**Verification:** 61 capture tests pass.

---

### Enhancement: Nutrition Meal Subtotals

**Summary:** Added subtotals (calories, protein, carbs, fat) for each meal type on the nutrition home page.

**Files Modified:**
- `apps/health/views.py` - Added meal subtotal calculations in NutritionHomeView
- `templates/health/nutrition/home.html` - Added subtotal display in meal headers with styling

**Features:**
- Each meal section (Breakfast, Lunch, Dinner, Snacks) now shows a subtotal line
- Format: "X cal | P: Xg | C: Xg | F: Xg"
- Subtotals only display when the meal has entries
- Styled in muted text, smaller than the meal title

**Verification:** 94 nutrition tests pass, `python manage.py check` passes.

---

### New: Capture Navigation Integration (Task #245)

**Summary:** Added Capture module to main navigation and dashboard with microphone icon.

**Files Modified:**
- `templates/components/navigation.html` - Added Capture link with microphone SVG icon
- `templates/dashboard/home.html` - Added "Record Audio" quick action and Capture module card
- `apps/core/context_processors.py` - Added `capture_enabled` context variable
- `apps/dashboard/views.py` - Added `capture_enabled` flag and `_get_capture_data()` method
- `apps/users/models.py` - Added `capture_enabled` BooleanField (default=True)
- `apps/capture/tests/test_views.py` - Added 5 navigation tests (44 total)

**Files Created:**
- `apps/users/migrations/0035_capture_enabled.py` - Migration for capture_enabled field

**Features:**
- Capture navigation link with microphone icon (conditionally shown when capture_enabled)
- "Record Audio" quick action card on dashboard
- Capture module card in "Your Modules" section showing recording count
- Context processor provides `capture_enabled` flag from user preferences
- Mobile-responsive layout (follows existing navigation patterns)

**Verification:** 44 capture tests pass, 12 dashboard tests pass.

---

### New: File Upload UI with Validation (Task #244)

**Summary:** Created file upload interface with client and server-side validation for audio files.

**Files Created:**
- `templates/capture/capture_upload.html` - Upload interface with drag-and-drop
- `static/capture/js/uploader.js` - Reusable AudioUploader class module

**Files Modified:**
- `apps/capture/views.py` - Added CaptureUploadView with validation
- `apps/capture/urls.py` - Added 'upload/' route
- `apps/capture/tests/test_views.py` - Added 19 tests for upload view (39 total)
- `templates/capture/capture_list.html` - Added "Upload File" button in header and empty state

**Features:**
- Drag-and-drop file upload zone
- File picker filtered to accepted formats (.mp3, .m4a, .wav, .webm)
- Client-side validation: file type and 60MB max size
- Server-side validation: file type, MIME type, and size
- Upload progress indicator
- Chunked upload support for large files (5MB chunks)
- File preview before upload (name, size)
- Error state with clear messaging and retry option
- Creates CaptureEntry on successful upload

**Validation:**
- Accepted formats: MP3, M4A, WAV, WebM
- Maximum file size: 60MB
- Server validates both file extension and MIME type

**Verification:** 39 tests pass, `python manage.py check` passes.

---

### New: Browser Audio Recording UI (Task #243)

**Summary:** Created mobile-first UI for recording audio directly in the browser using MediaRecorder API.

**Files Created:**
- `templates/capture/capture_record.html` - Recording interface template
- `static/capture/js/recorder.js` - Reusable AudioRecorder class module

**Files Modified:**
- `apps/capture/views.py` - Added CaptureRecordView (TemplateView with LoginRequiredMixin)
- `apps/capture/urls.py` - Added 'record/' route
- `apps/capture/tests/test_views.py` - Added 8 tests for record view (20 total)
- `templates/capture/capture_list.html` - Added "Record Audio" button in header and empty state

**Features:**
- Browser support detection (MediaRecorder API)
- Microphone permission handling with clear denial message and retry
- Recording states: Idle, Recording, Preview, Uploading
- Visual pulse indicator during recording
- Live timer display (MM:SS format)
- Maximum 60-minute recording limit with auto-stop
- Records in webm format for best browser compatibility
- Audio preview with playback controls before saving
- Discard and re-record option
- Placeholder upload progress UI (actual upload in future task)

**Verification:** 20 tests pass, `python manage.py check` passes.

---

## 2026-01-13 Changes

### New: Capture List View and URL Routing (Task #242)

**Summary:** Set up the main capture section with list view showing user's capture entries at `/capture/`.

**Files Created:**
- `apps/capture/views.py` - CaptureListView (ListView with LoginRequiredMixin)
- `apps/capture/tests/test_views.py` - 12 tests for list view
- `templates/capture/capture_list.html` - List template with empty state

**Files Modified:**
- `apps/capture/urls.py` - Added list view route at ''
- `config/urls.py` - Included capture.urls at path 'capture/'

**Features:**
- List view filtered by current user, ordered by -created_at
- Pagination (20 entries per page)
- Empty state with helpful message for first-time users
- Shows entry title, category, subcategory, duration, status, created date
- Status indicators (Ready, Failed, Uploading, Transcribing, Summarizing)
- Context includes total_count and ready_count

**Verification:** 12 tests pass, accessible at `/capture/`.

---

### New: S3 Storage Configuration for Capture Audio (Task #241)

**Summary:** Configured S3-compatible storage for temporary audio file storage with 7-day retention lifecycle policy.

**Settings Added:**
- `CAPTURE_AWS_ACCESS_KEY_ID` - AWS/S3-compatible access key
- `CAPTURE_AWS_SECRET_ACCESS_KEY` - AWS/S3-compatible secret key
- `CAPTURE_AWS_REGION` - AWS region (default: us-east-1)
- `CAPTURE_AUDIO_BUCKET` - S3 bucket name for audio files
- `CAPTURE_S3_ENDPOINT_URL` - Optional custom endpoint for S3-compatible services
- `CAPTURE_AUDIO_RETENTION_DAYS` - Days before auto-deletion (default: 7)
- `CAPTURE_PRESIGNED_URL_EXPIRATION` - URL expiration in seconds (default: 3600)

**Files Created:**
- `apps/capture/storage.py` - S3 presigned URL generation utilities
- `apps/capture/tests/test_storage.py` - 19 tests for storage utilities

**Files Modified:**
- `config/settings.py` - Added S3 configuration section
- `requirements.txt` - Added boto3>=1.34.0
- `docs/wlj_third_party_services.md` - Documented AWS S3 integration with lifecycle policy, IAM policy, and CORS configuration

**Key Functions:**
- `generate_upload_presigned_url()` - Generate presigned URL for browser upload
- `generate_download_presigned_url()` - Generate presigned URL for audio playback
- `delete_audio_file()` - Manual deletion (lifecycle handles auto-cleanup)
- `is_storage_configured()` - Check if S3 is configured

**Verification:** 19 tests pass, `python manage.py check` passes.

---

### New: CaptureEntry Model (Task #240)

**Summary:** Created the CaptureEntry model with all required fields for storing audio recordings, transcripts, and AI-generated summaries.

**Model Fields:**
- `id` (UUID) - Primary key
- `user` (FK) - User who created the capture
- `title` - Optional title for the capture
- `duration_seconds` - Audio recording duration
- `audio_file_url` - S3 signed URL for audio file
- `audio_expires_at` - URL expiration timestamp
- `transcript` - Full Whisper transcription
- `summary` - AI-generated BLUF summary
- `category` - Primary category (faith, organize)
- `subcategory` - Subcategory (sermon, bible_study, devotional, meeting, notes, personal)
- `status` - Processing status (uploading, transcribing, summarizing, ready, failed)
- `error_message` - Error details if processing failed

**Files Created:**
- `apps/capture/migrations/0001_initial.py` - Initial migration

**Files Modified:**
- `apps/capture/models.py` - Added CaptureEntry model
- `apps/capture/admin.py` - Registered CaptureEntryAdmin

**Verification:** Migration applied, `python manage.py check` passes.

---

### New: Capture App Structure (Task #239)

**Summary:** Created the capture Django app with proper app structure for the WLJ Transcribe Recordings feature.

**Files Created:**
- `apps/capture/__init__.py` - App module init
- `apps/capture/apps.py` - CaptureConfig app configuration
- `apps/capture/models.py` - Empty models file (CaptureEntry will be added in next task)
- `apps/capture/views.py` - Empty views file
- `apps/capture/urls.py` - URL configuration with app_name='capture'
- `apps/capture/admin.py` - Admin configuration
- `apps/capture/forms.py` - Forms module
- `apps/capture/tests/__init__.py` - Test package

**Files Modified:**
- `config/settings.py` - Added 'apps.capture' to INSTALLED_APPS

**Verification:** `python manage.py check` passes successfully.

---

### Fix: OAuth Token Decryption Error - Graceful Error Handling

**Summary:** Fixed crash caused by OAuth token decryption failures by adding safe
decryption functions and graceful error handling in views.

**Problem:** When OAuth tokens (Google Calendar, Dexcom) fail to decrypt (due to key
rotation, corruption, or configuration changes), the application would crash with
"OAuth token decryption failed" error instead of gracefully handling the situation.

**Root Cause:** The `decrypt_oauth_token()` function raises `ValueError` on decryption
failure, and this exception was not being caught in the model properties or views that
use the decrypted tokens.

**Fix:**
1. Added `decrypt_oauth_token_safe()` function that returns `(value, success)` tuple
   instead of raising exceptions
2. Updated `GoogleCalendarCredential` and `DexcomCredential` model properties to use
   safe decryption
3. Added `has_decryption_error()` method to both credential models to check validity
4. Added decryption error checks in all views that use OAuth credentials:
   - `GoogleCalendarSettingsView` - Shows error message, prompts re-authorization
   - `GoogleCalendarSaveSettingsView` - Redirects with error message
   - `GoogleCalendarSyncView` - Redirects with error message
   - `GoogleCalendarPushEventView` - Redirects with error message
   - `_sync_google_calendar_if_needed` in DashboardView - Logs warning, skips sync
5. Fixed Dexcom service to use decrypted token properties instead of raw fields
6. Added decryption error check in Dexcom sync service

**Files Modified:**
- `apps/core/encryption.py` - Added `decrypt_oauth_token_safe()` function
- `apps/life/models.py` - Updated GoogleCalendarCredential with safe decryption
- `apps/health/models.py` - Updated DexcomCredential with safe decryption
- `apps/life/views.py` - Added decryption error checks in 4 views
- `apps/dashboard/views.py` - Added decryption error check in auto-sync
- `apps/health/services/dexcom.py` - Use decrypted tokens, add error check

**User Impact:** Users with invalid OAuth tokens will now see a clear error message
asking them to disconnect and reconnect their account, instead of experiencing crashes.

---

### Fix: Visual Glitch on Page Navigation (Chat Drawer Auto-Open)

**Summary:** Fixed "slide to right" visual glitch on every page navigation caused by chat drawer auto-opening then closing.

**Problem:** Users reported a PowerPoint-like slide transition on every page navigation. Initially thought to be FOUC (Flash of Unstyled Content), but investigation revealed the chat drawer was:
1. Persisting its open state in localStorage
2. Auto-opening on every page load via `checkSavedState()`
3. Then immediately closing, causing the slide animation

**Root Cause:** The `checkSavedState()` function in `chat_widget.html` was reading localStorage and calling `openDrawer()` on page load, but something was causing it to close immediately after, creating the visual glitch.

**Solution:**
1. Removed the auto-open feature entirely. Users must now click the chat button to open the drawer on each page.
2. Disabled CSS transition on initial page load by removing the `transition` property from the base `.assistant-drawer` class and only adding it via an `.animate` class when the user first clicks the button.

**Files Modified:**
- `templates/components/chat_widget.html` - Removed `checkSavedState()` function; moved transition to `.animate` class; added animate class on first user interaction

**Also in this session (Critical CSS improvements):**
- `templates/base.html` - Added inline critical CSS for nav/logo sizing
- `templates/account/base.html` - Added inline critical CSS

---

## 2026-01-12 Changes

### Documentation: FOUC Troubleshooting Guide

**Summary:** Documented the Flash of Unstyled Content (FOUC) issue in troubleshooting guide.

**Background:** After extensive testing, confirmed FOUC is an external infrastructure issue
(Railway/Cloudflare), NOT caused by any code changes. Reverted to pre-CISO code and FOUC
still occurred, proving it's unrelated to today's security changes.

**Documented:**
- Symptoms and how to reproduce
- Root cause analysis
- What was already tried (to prevent re-attempting)
- Infrastructure-level suggestions for future investigation

**Files Modified:**
- `docs/wlj_claude_troubleshoot.md` - Added section #9 for FOUC issue

---

### Fix: FOUC (Flash of Unstyled Content) from CSP nonce on styles

**Summary:** Reverted style-src CSP directive to use `'unsafe-inline'` instead of nonces
to fix the flash of unstyled content on page navigation.

**Problem:** The nonce-based style-src directive caused browsers to block inline styles
until the nonce was validated, resulting in a visible flash of unstyled content on
every page load.

**Fix:** Keep nonces for script-src (important for XSS protection) but use `'unsafe-inline'`
for style-src. This is standard practice because:
- Inline styles are lower XSS risk than inline scripts
- Nonce validation on styles causes rendering delays
- The security benefit of nonced styles doesn't justify the UX degradation

**Files Modified:**
- `apps/core/middleware.py` - Changed style-src to use 'unsafe-inline'

---

### Hotfix: Missing logging import in middleware

**Summary:** Fixed deployment crash caused by missing `import logging` statement in
`APIRequestLoggingMiddleware` class.

**Problem:** The `APIRequestLoggingMiddleware.__init__()` method used `logging.getLogger()`
but the `logging` module was not imported at the top of the file, causing a `NameError`
when gunicorn attempted to load the WSGI application.

**Fix:** Added `import logging` to the imports section of `apps/core/middleware.py`.

**Files Modified:**
- `apps/core/middleware.py` - Added missing logging import

---

### Security: API Request Logging with Anomaly Detection (CISO Review Complete)

**Summary:** Implemented comprehensive API request logging infrastructure with real-time
anomaly detection. This completes all 12 security concerns from the CISO review.

**New Components:**

1. **APIRequestLog Model** (`apps/core/models.py`):
   - Stores: request_id, method, path, api_key_name, user, ip_address, user_agent
   - Stores: status_code, response_time_ms, error_message
   - Anomaly fields: is_anomaly, anomaly_reason, anomaly_score
   - Indexed on: request_id, path, api_key_name, ip_address, status_code, created_at, is_anomaly
   - Class methods: `log_request()`, `get_stats_for_ip()`, `detect_anomalies()`, `cleanup_old_logs()`

2. **APIRequestLoggingMiddleware** (`apps/core/middleware.py`):
   - Logs all requests to `/api/*` and `/admin-console/api/*` endpoints
   - Generates UUID request_id for correlation
   - Captures response times and error messages
   - Real-time anomaly detection for:
     - **Burst detection**: >50 requests from same IP in 5 minutes
     - **Auth failure spikes**: >5 auth failures (401/403) from same IP in 5 minutes

3. **Security Event Type** (`apps/core/security_logging.py`):
   - Added `api_anomaly` event type for anomaly alerts
   - Anomalies trigger security event logging with details

4. **Cleanup Command** (`apps/core/management/commands/cleanup_api_logs.py`):
   - Deletes logs older than retention period (default 30 days)
   - `--keep-anomalies` flag retains anomalies for 2x retention
   - `--dry-run` for testing
   - Should be scheduled daily via cron

5. **Configuration** (`config/settings.py`):
   - `WLJ_SETTINGS['API_LOGGING_ENABLED']`: Enable/disable (default: True)
   - `WLJ_SETTINGS['API_LOGGING_PATHS']`: Paths to log (default: ['/api/', '/admin-console/api/'])
   - `WLJ_SETTINGS['API_ANOMALY_DETECTION']`: Enable real-time detection (default: True)
   - `WLJ_SETTINGS['API_LOG_RETENTION_DAYS']`: Log retention (default: 30)

**Migration:** `apps/core/migrations/0044_apirequestlog.py`

**Files Changed:**
- `apps/core/models.py` - Added APIRequestLog model
- `apps/core/middleware.py` - Added APIRequestLoggingMiddleware
- `apps/core/security_logging.py` - Added api_anomaly event type
- `config/settings.py` - Added middleware and WLJ_SETTINGS
- `apps/core/management/commands/cleanup_api_logs.py` - New cleanup command

---

### Security: CSP Nonce Implementation Complete

**Summary:** Added `nonce="{{ csp_nonce }}"` to ALL inline `<script>` and `<style>` tags
across the entire codebase, then re-enabled nonce-based CSP.

**Changes Made:**
- 60 inline `<script>` tags updated with nonce attribute
- 248 inline `<style>` tags updated with nonce attribute
- Re-enabled nonce-based CSP in middleware

**How It Works:**
- Each request gets a unique cryptographic nonce
- CSP header includes `'nonce-{value}'` in script-src and style-src
- Only inline scripts/styles with matching nonce attribute execute
- Injected XSS scripts won't have the nonce and are blocked

**Rollback:** If issues occur, the `csp-nonce-backup` branch contains the
pre-nonce state. Alternatively, set nonce to None in middleware to fall back
to unsafe-inline.

**Files Changed:**
- `apps/core/middleware.py` - Re-enabled nonce-based CSP
- All 200+ template files - Added nonce attributes to inline scripts/styles

---

### CRITICAL Fix: CSP Nonces Breaking Site (Inline Scripts/Styles Blocked)

**Root Cause:** When a CSP nonce is present in the policy, browsers **completely ignore
`'unsafe-inline'`**. This is by design - nonces and unsafe-inline are mutually exclusive.

**Impact:** ALL inline `<script>` and `<style>` tags were blocked, including:
- Navigation component inline styles
- Chat widget inline scripts
- Theme accent color overrides
- Dashboard JavaScript

**The site was completely broken** - CSS wasn't applying, JS wasn't running.

**Temporary Fix:** Disabled nonce-based CSP until all inline scripts/styles had nonce attributes.

**Permanent Fix:** Added nonce attributes to ALL templates (see above).

---

### Fix: CSP Blocking External CDN Scripts (HTMX, Tailwind, Plaid)

**Issue:** The CSP nonce implementation was missing several external CDN domains:
- `unpkg.com` - HTMX library (core interactivity)
- `cdn.tailwindcss.com` - Tailwind CSS for billing pages
- `cdn.plaid.com` - Plaid banking integration

**Files Changed:**
- `apps/core/middleware.py` - Added missing CDN domains to CSP

---

### Security: CISO Review - Admin Override Confirmation (MFA-lite)

**Goal:** Add password confirmation for destructive admin operations to prevent accidental or unauthorized changes.

**Safety First:**
- Normal admin console VIEWING is NOT affected
- Only destructive override operations require confirmation
- Can be disabled via `WLJ_SETTINGS['ADMIN_OVERRIDE_REQUIRE_CONFIRMATION'] = False`
- Django's built-in /admin/ always works
- 30-minute confirmation window (configurable)

**Changes Made:**

1. **AdminOverrideConfirmationMixin** (`apps/admin_console/views.py`):
   - New mixin for admin override operations
   - Checks `admin_override_confirmed_at` session key
   - Returns 403 with `confirmation_required: true` if not confirmed
   - Timeout configurable via `WLJ_SETTINGS['ADMIN_OVERRIDE_TIMEOUT_MINUTES']`

2. **Protected Admin Override APIs**:
   - `ResetPhaseOverrideAPIView` - Now requires confirmation
   - `UnblockTaskOverrideAPIView` - Now requires confirmation
   - `RecheckPhaseOverrideAPIView` - Now requires confirmation

3. **ConfirmPasswordView Update** (`apps/users/views.py`):
   - Now sets both `finance_last_activity` AND `admin_override_confirmed_at`
   - One password confirmation works for both finance and admin operations
   - Smart redirect: staff users go to admin console, others to finance

4. **Configuration Settings** (`config/settings.py`):
   - `ADMIN_OVERRIDE_TIMEOUT_MINUTES`: 30 (default)
   - `ADMIN_OVERRIDE_REQUIRE_CONFIRMATION`: True (set False to disable)

**Recovery If Locked Out:**
1. Django's /admin/ is unaffected
2. Set `ADMIN_OVERRIDE_REQUIRE_CONFIRMATION = False` in settings
3. Or via manage.py shell: clear session data

**Files Modified:**
- `apps/admin_console/views.py` - AdminOverrideConfirmationMixin, updated override views
- `apps/users/views.py` - Updated ConfirmPasswordView
- `config/settings.py` - New WLJ_SETTINGS entries

---

### Security: CISO Review - CSP Nonce-Based XSS Protection (REVERTED)

**Goal:** Implement nonce-based Content Security Policy for stricter XSS protection.

**Changes Made:**

1. **CSP Nonce Middleware** (`apps/core/middleware.py`):
   - Added `generate_csp_nonce()` function using `os.urandom(16)` with base64 encoding
   - New `CSPNonceMiddleware` class generates per-request nonces
   - Nonce stored on `request.csp_nonce` for template access
   - Must run before `ContentSecurityPolicyMiddleware`

2. **Updated CSP Headers** (`apps/core/middleware.py`):
   - `ContentSecurityPolicyMiddleware` now includes `'nonce-{nonce}'` in script-src
   - Also includes nonce in style-src for inline styles
   - `'unsafe-inline'` kept as fallback for legacy compatibility
   - Nonce allows specific inline scripts while blocking injected ones

3. **Context Processor** (`apps/core/context_processors.py`):
   - New `csp_nonce()` context processor
   - Makes `{{ csp_nonce }}` available in all templates
   - Usage: `<script nonce="{{ csp_nonce }}">...</script>`

4. **Settings Configuration** (`config/settings.py`):
   - Added `CSPNonceMiddleware` to MIDDLEWARE (before ContentSecurityPolicyMiddleware)
   - Added `apps.core.context_processors.csp_nonce` to TEMPLATES context_processors

**How It Works:**
- Each request gets a unique 16-byte nonce
- CSP header includes `'nonce-{base64_nonce}'`
- Only `<script>` tags with matching `nonce` attribute execute
- Injected scripts (XSS) won't have valid nonce and are blocked

**Template Migration Notes:**
- Add `nonce="{{ csp_nonce }}"` to inline `<script>` tags
- External scripts from allowed CDNs don't need nonce
- `'unsafe-inline'` fallback ensures gradual migration

**Files Modified:**
- `apps/core/middleware.py` - CSPNonceMiddleware, updated ContentSecurityPolicyMiddleware
- `apps/core/context_processors.py` - csp_nonce context processor
- `config/settings.py` - MIDDLEWARE and TEMPLATES updates

---

### Security: CISO Review - Batch 3 - Policy & Documentation

**Goal:** Complete security hardening with privacy policy updates, activity-based timeout, and security audit documentation.

**Changes Made:**

1. **Activity-Based Timeout for Financial Operations** (`apps/finance/views.py`):
   - New `FinanceSensitiveOperationMixin` class for sensitive financial views
   - Requires re-authentication after 15 minutes of inactivity (configurable)
   - Uses session-based activity tracking
   - Logs timeout events for security monitoring

2. **Password Confirmation View** (`apps/users/views.py`):
   - New `ConfirmPasswordView` for re-authentication flow
   - Secure password verification before sensitive operations
   - Returns user to intended destination after confirmation

3. **GDPR Compliance in Privacy Policy** (`templates/core/privacy.html`):
   - Added "European Users (GDPR)" section
   - Legal basis for processing (contract, consent, legitimate interest, legal obligation)
   - All GDPR rights documented (access, rectification, erasure, restrict, portability, object, withdraw consent)
   - Data transfer safeguards (Standard Contractual Clauses)
   - Supervisory authority rights

4. **CCPA/CPRA Compliance in Privacy Policy** (`templates/core/privacy.html`):
   - Added "California Residents (CCPA/CPRA)" section
   - Categories of personal information collected
   - All CCPA/CPRA rights documented (know, delete, correct, opt-out, limit use, non-discrimination)
   - "Do Not Sell" declaration
   - Sensitive personal information handling
   - Authorized agent provisions
   - Shine the Light compliance

5. **Key Rotation Schedule Documentation** (`docs/key_rotation_schedule.md`):
   - Complete inventory of encryption keys
   - Annual rotation schedule (January)
   - Emergency rotation triggers
   - Step-by-step rotation procedures for each key
   - Verification checklist
   - Audit log template

6. **Annual Security Audit Schedule** (`docs/security_audit_schedule.md`):
   - Quarterly audit calendar
   - Continuous monitoring activities
   - OWASP Top 10 checklist
   - Third-party service audit template
   - GDPR/CCPA/COPPA compliance checklists
   - Incident response procedures

**New Configuration:**
- `WLJ_SETTINGS['FINANCE_ACTIVITY_TIMEOUT_MINUTES']` - Default 15 minutes

**Files Modified/Created:**
- `apps/finance/views.py` - FinanceSensitiveOperationMixin
- `apps/users/views.py` - ConfirmPasswordView
- `apps/users/urls.py` - confirm_password URL
- `templates/users/confirm_password.html` - NEW: Confirmation form
- `templates/core/privacy.html` - GDPR/CCPA sections
- `config/settings.py` - FINANCE_ACTIVITY_TIMEOUT_MINUTES
- `docs/key_rotation_schedule.md` - NEW: Key rotation procedures
- `docs/security_audit_schedule.md` - NEW: Audit schedule

**Remaining Items (Future Work):**
- API request logging with anomaly detection (requires monitoring infrastructure)

---

### Security: CISO Review - Comprehensive Security Hardening

**Goal:** Address all security gaps identified during CISO review to ensure the application meets enterprise security standards.

**Changes Made:**

#### High Priority

1. **Session Timeout Configuration** (`config/settings.py`):
   - Added `SESSION_COOKIE_AGE = 86400` (24 hours)
   - Sessions now expire after 24 hours of inactivity

2. **CSP Enforcement Mode** (`apps/core/middleware.py`):
   - Changed from `Content-Security-Policy-Report-Only` to `Content-Security-Policy`
   - CSP is now actively enforced, not just reporting

3. **Admin API Rate Limiting** (new file: `apps/core/rate_limiting.py`):
   - Created `APIRateLimitMixin` for class-based views
   - Created `rate_limit_api` decorator for function-based views
   - Rate limiting: 60 requests/minute, 500 requests/hour for read APIs
   - Rate limiting: 30 requests/minute, 200 requests/hour for write/override APIs
   - Applied to all admin console API views:
     - `ReadyTasksAPIView`, `UpdateTaskStatusAPIView`
     - `NextTasksAPIView`, `ProjectMetricsAPIView`, `SystemStateAPIView`
     - `SystemIssuesAPIView`, `ResetPhaseOverrideAPIView`
     - `UnblockTaskOverrideAPIView`, `RecheckPhaseOverrideAPIView`
     - `PreflightCheckAPIView`, `SeedPhasesAPIView`

#### Medium Priority

4. **reCAPTCHA Score Enforcement** (`apps/users/adapters.py`):
   - Upgraded from TIER 1 (logging only) to TIER 2 (blocking)
   - Signups with reCAPTCHA score < 0.5 are now blocked
   - Added `_log_blocked_signup()` method for audit logging
   - Security events logged via `log_security_event()`

5. **Bank Token Key Rotation Documentation** (`apps/finance/services/encryption.py`):
   - Added comprehensive KEY ROTATION PROCEDURE in docstring
   - Includes step-by-step rotation instructions
   - Includes rollback procedure
   - Documents when to rotate (compromise, employee departure, annual)

6. **Soft-Delete Cleanup Automation**:
   - New management command: `apps/core/management/commands/cleanup_soft_deletes.py`
   - New background job: `apps/core/jobs.py` - `cleanup_soft_deletes()`
   - Scheduled weekly on Sunday at 3:00 AM UTC via APScheduler
   - Updated `config/wsgi.py` to include the new job
   - Permanently deletes records soft-deleted > 30 days ago
   - Full audit logging of all deletions

#### Low Priority

7. **GDPR Data Export Feature**:
   - New service: `apps/users/services/data_export.py`
   - New views: `DataExportView`, `DataExportDownloadView` (`apps/users/views.py`)
   - New template: `templates/users/data_export.html`
   - New URLs: `/user/data-export/`, `/user/data-export/download/`
   - Supports JSON and CSV (ZIP) export formats
   - Rate limited: 5 exports per hour per user
   - Exports all user-owned data across all modules
   - Excludes sensitive fields (passwords, tokens, keys)

8. **Image Upload MIME Validation** (`apps/admin_console/views.py`):
   - Enhanced `validate_image_file()` function
   - Added magic bytes verification for JPEG, PNG, GIF, ICO, WebP
   - Three-layer validation: extension, Content-Type header, magic bytes
   - PIL verification for actual image content

**Files Modified:**
- `config/settings.py` - Session timeout
- `config/wsgi.py` - Soft-delete cleanup job
- `apps/core/middleware.py` - CSP enforcement
- `apps/core/rate_limiting.py` - NEW: Rate limiting utilities
- `apps/core/jobs.py` - NEW: Background job functions
- `apps/core/management/commands/cleanup_soft_deletes.py` - NEW: Cleanup command
- `apps/users/adapters.py` - reCAPTCHA enforcement
- `apps/users/views.py` - Data export views
- `apps/users/urls.py` - Data export URLs
- `apps/users/services/__init__.py` - NEW: Services module
- `apps/users/services/data_export.py` - NEW: Export service
- `apps/admin_console/views.py` - Rate limiting mixin, image validation
- `apps/finance/services/encryption.py` - Key rotation documentation
- `templates/users/data_export.html` - NEW: Export UI

**Security Controls Added:**
- Session timeout: 24 hours
- CSP: Enforced (no longer report-only)
- API rate limiting: 60/min, 500/hr (standard), 30/min, 200/hr (overrides)
- reCAPTCHA: Score < 0.5 blocks signup
- Soft-delete: Auto-cleanup after 30 days
- GDPR: User data export capability
- Image uploads: Magic bytes + PIL verification

---

### Security: CISO Review - Batch 2 - Sensitive Data Encryption & API Security

**Goal:** Implement critical security controls for OAuth token encryption, secure API key comparison, and admin override audit logging.

**Changes Made:**

#### High Priority (Batch 2)

1. **OAuth Token Encryption for Google Calendar** (`apps/life/models.py`):
   - `GoogleCalendarCredential` now stores encrypted tokens at rest
   - Added `access_token_decrypted`, `refresh_token_decrypted`, `client_secret_decrypted` properties
   - Added `set_access_token()`, `set_refresh_token()`, `set_client_secret()` methods
   - Updated `get_credentials_dict()` to return decrypted values
   - Updated `update_from_credentials()` to encrypt on save

2. **OAuth Token Encryption for Dexcom** (`apps/health/models.py`):
   - `DexcomCredential` now stores encrypted tokens at rest
   - Added `access_token_decrypted`, `refresh_token_decrypted` properties
   - Added `set_access_token()`, `set_refresh_token()` methods
   - Updated `get_credentials_dict()` to return decrypted values
   - Updated `update_from_credentials()` to encrypt on save

3. **OAuth Token Encryption Service** (new file: `apps/core/encryption.py`):
   - `encrypt_oauth_token()` - Encrypt tokens for database storage
   - `decrypt_oauth_token()` - Decrypt tokens for use
   - `get_oauth_fernet()` - Get Fernet instance from settings
   - `generate_oauth_encryption_key()` - Generate new keys
   - Complete KEY ROTATION PROCEDURE documentation
   - Falls back to `UNENCRYPTED:` prefix in dev mode (no key configured)

4. **HMAC-Based API Key Comparison** (`apps/core/rate_limiting.py`):
   - Added `secure_compare_api_key()` function using `hmac.compare_digest`
   - Prevents timing attacks on API key validation
   - Used by Claude API endpoints

5. **Claude API Security Updates** (`apps/admin_console/views.py`):
   - `ReadyTasksAPIView.get()` - Now uses `secure_compare_api_key()`
   - `UpdateTaskStatusAPIView.post()` - Now uses `secure_compare_api_key()`

6. **Admin Override Audit Logging** (`apps/core/security_logging.py`):
   - Added `admin_override` and `data_export` event types
   - New `log_admin_override()` function for audit logging
   - All override actions now notify admins immediately

7. **Admin Override APIs Audit Logging** (`apps/admin_console/views.py`):
   - `ResetPhaseOverrideAPIView` - Logs all phase resets
   - `UnblockTaskOverrideAPIView` - Logs all task unblocks
   - `RecheckPhaseOverrideAPIView` - Logs all phase rechecks

**New Environment Variables:**
- `OAUTH_TOKEN_ENCRYPTION_KEY` - Fernet key for OAuth token encryption
  - Generate with: `from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())`

**Files Modified/Created:**
- `apps/core/encryption.py` - NEW: OAuth token encryption
- `apps/core/rate_limiting.py` - Added secure_compare_api_key()
- `apps/core/security_logging.py` - Added log_admin_override()
- `apps/life/models.py` - GoogleCalendarCredential encryption
- `apps/health/models.py` - DexcomCredential encryption
- `apps/admin_console/views.py` - Secure API key comparison, audit logging
- `config/settings.py` - OAUTH_TOKEN_ENCRYPTION_KEY setting

**Security Controls Added:**
- OAuth tokens: Encrypted at rest (AES-256 via Fernet)
- API key comparison: Constant-time to prevent timing attacks
- Admin overrides: Audited and emailed to admins

---

### Feature: Add Scan Icons Throughout Nutrition Flow

**Goal:** Make barcode/photo scanning accessible from multiple entry points in the nutrition flow, allowing users to quickly scan food items from anywhere in the nutrition section.

**Changes Made:**

1. **Nutrition Home Page** (`templates/health/nutrition/home.html`):
   - Added scan icon (📷) next to "Log Food" button in header
   - Added scan icon next to each meal section's "+ Add" button (Breakfast, Lunch, Dinner, Snacks)
   - Added CSS for `.meal-actions`, `.btn-icon`, and `.btn-icon-sm` classes

2. **Food Entry Form** (`templates/health/nutrition/food_entry_form.html`):
   - Added scan icon next to "What did you eat?" section title
   - Added "Save & Scan 📷" button to form actions (saves entry then redirects to scanner)
   - Added CSS for `.form-section-header` and `.btn-icon-sm` classes

3. **Food Entry View** (`apps/health/views.py`):
   - Added `reverse` import
   - Modified `FoodEntryCreateView.form_valid()` to handle `save_and_scan` button
   - When "Save & Scan" is clicked, saves the entry and redirects to `/scan/?mode=barcode&meal=<meal_type>`

**User Flow:**
- Scan icons link to `/scan/?mode=barcode&meal=<meal_type>`
- After scanning, barcode lookup redirects to food entry form with pre-filled data
- "Save & Scan" button on form saves current entry and immediately opens scanner for next item

**Files Modified:**
- `templates/health/nutrition/home.html`
- `templates/health/nutrition/food_entry_form.html`
- `apps/health/views.py`

**What's New Entry:**
- Migration: `apps/core/migrations/0043_nutrition_scan_icons_release_note.py`
- Title: "Quick Scan: Log Food Faster with Barcode Scanning"

---

### Feature: Auto-Populate Meal Type Based on Scan Time

**Goal:** Automatically determine meal type (breakfast, lunch, dinner, snack) based on the time of day when scanning food, improving the user experience by pre-selecting the correct meal.

**Meal Schedule Logic:**
- Breakfast: 5:00 AM - 10:30 AM
- Lunch: 10:30 AM - 2:30 PM
- Snack: 2:30 PM - 5:00 PM
- Dinner: 5:00 PM - 9:00 PM
- Late Night Snack: 9:00 PM - 5:00 AM

**Changes Made:**

1. **Barcode Lookup** (`apps/scan/views.py`):
   - Added `_get_meal_type_from_time()` helper method to `BarcodeLookupView`
   - If meal type is passed via query param (from meal-specific scan buttons), use that
   - Otherwise, auto-determine meal type based on current time
   - Users can still change the meal type on the food entry form

2. **Vision Scan** (`apps/scan/services/vision.py`):
   - Added `_get_meal_type_from_time()` helper method to `VisionService`
   - If AI doesn't provide a meal type, fall back to time-based determination
   - Previously defaulted to "snack" for all scans

**User Experience:**
- User scans barcode at 7:30 AM → meal type auto-set to "breakfast"
- User scans barcode at 12:00 PM → meal type auto-set to "lunch"
- User clicks scan icon next to "Dinner" section → meal=dinner passed, used instead of time
- User can always change the meal type if the auto-selection is wrong

**Files Modified:**
- `apps/scan/views.py`
- `apps/scan/services/vision.py`

---

### Fix: Billing Templates Missing CSS (Tailwind Not Loaded)

**Problem:** Billing pages (`/billing/plans/`, `/billing/settings/`, etc.) were rendering without CSS styling. The navbar was styled correctly but the page content was unstyled.

**Root Cause:** Billing templates were written using Tailwind CSS utility classes (`max-w-4xl`, `grid`, `md:grid-cols-2`, `rounded-xl`, `shadow-lg`, etc.), but the project uses a custom CSS system (`main.css`, `themes.css`) without Tailwind. The Tailwind classes had no effect.

**Fix:** Added Tailwind CDN script to all billing templates via the `{% block extra_css %}` block. This allows the billing pages to use Tailwind classes while the rest of the app continues using the custom CSS system.

**Files Modified:**
- `templates/billing/select_plan.html`
- `templates/billing/billing_settings.html`
- `templates/billing/checkout_success.html`
- `templates/billing/credit_history.html`
- `templates/billing/payout_preferences.html`
- `templates/billing/submit_suggestion.html`

---

### Fix: BillingProfile Not Found for Existing Users

**Problem:** Users created before the billing system was added did not have BillingProfile records, causing a 500 error when accessing `/billing/plans/`.

**Error:** `User has no billing_profile. RelatedObjectDoesNotExist`

**Fix:** Added `get_or_create_billing_profile()` helper function that creates a BillingProfile on-demand if one doesn't exist for the user. Updated all billing views to use this helper instead of directly accessing `user.billing_profile`.

**Files Modified:**
- `apps/billing/views.py`: Added get_or_create_billing_profile() helper, updated select_plan, checkout_success, billing_settings, payout_preferences, and credit_history views

---

### Billing Configuration - Database-Driven Settings via Django Admin

**Task:** Move billing configuration from hardcoded settings.py to database-managed configuration.

**Problem:** User requested that billing configuration (pricing, rewards, age thresholds) should be managed via Django Admin instead of editing code files. This follows best practices for maintainability.

**Implementation:**

**New Model:**
- `BillingConfiguration`: Singleton model storing all pricing and rewards configuration
  - Business info (name, product)
  - Age thresholds (student_max_age)
  - Pricing tiers (student monthly/annual, adult monthly/annual, founding lifetime)
  - Rewards (referral_bonus, suggestion_reward, founding_quarterly_bonus)
  - Rate limits (suggestions_per_month_limit, referral_qualification_days)
  - Stripe fees (for documentation/margin calculations)
  - Caching via `get_config()` class method (5-minute TTL)
  - `as_dict()` method for template context

**Admin Interface:**
- `BillingConfigurationAdmin` with organized fieldsets
- Singleton pattern - redirects list view to edit form
- Cache invalidation on save
- Add permission only if no config exists
- Delete permission disabled

**Files Modified:**
- `apps/billing/models.py`: Added BillingConfiguration model, updated get_reward_amount()
- `apps/billing/admin.py`: Added BillingConfigurationAdmin
- `apps/billing/services.py`: Updated get_billing_config() and determine_tier_by_age() to read from database
- `apps/billing/context_processors.py`: Updated to use BillingConfiguration.get_config()
- `apps/billing/management/commands/generate_billing_docs.py`: Updated to read from database
- `config/settings.py`: Removed hardcoded BILLING_CONFIG, added reference comment

**Migrations:**
- `0002_add_billing_configuration.py`: Creates BillingConfiguration model
- `0003_populate_initial_billing_config.py`: Data migration with default values

**Admin URL:** `/admin/billing/billingconfiguration/`

---

### Billing & Subscriptions System - Phase 11: Complete Test Suite

**Task:** Create comprehensive test suite for the billing app.

**Implementation:** Added 59 passing tests covering all billing functionality:

**Test Files Created:**
- `apps/billing/tests/__init__.py`
- `apps/billing/tests/test_models.py`: 17 tests for BillingProfile, ReferralReward, FeatureSuggestion, PaymentAuditLog, CreditTransaction
- `apps/billing/tests/test_services.py`: 15 tests for age calculation, tier determination, subscription checks, quarter calculation, StripeService
- `apps/billing/tests/test_views.py`: 16 tests for plan selection, billing settings, referral capture, suggestions, credits, payout preferences
- `apps/billing/tests/test_webhooks.py`: 11 tests for webhook signature verification and event handlers

**Test Coverage:**
- Model CRUD operations and business logic (add_credit, use_credit, mark_implemented, process_rewards)
- Service layer utilities (calculate_age, determine_tier_by_age, is_subscription_active, get_current_quarter)
- StripeService methods with mocked Stripe API calls
- View authentication, authorization, and form handling
- Webhook signature verification and event routing
- Proper handling of terms acceptance and onboarding middleware in tests

**Test Count:** 59 new billing tests, all passing.

---

### Billing & Subscriptions System - Phase 1: Stripe Foundation

**Task:** Implement payment and rewards system with Stripe integration, referral tracking, and account credits.

**Implementation:** Created new `apps/billing` app with full Stripe integration:

**Models Created:**
- `BillingProfile`: User billing info, subscription status, pricing tier, referral code, account credits, payout preferences
- `ReferralReward`: Tracks referral signups and $5 reward distribution
- `ReferralQualification`: 90-day qualification tracking for Founding Member bonuses
- `FoundingMemberPayout`: Quarterly payout records for Founding Members
- `FeatureSuggestion`: User-submitted feature ideas with $5 reward tracking
- `CreditTransaction`: Account credit ledger (referral bonuses, suggestion rewards, applied to invoices)
- `PromoCodeUsage`: Tracks promo code redemptions
- `PaymentAuditLog`: Immutable audit trail for all payment actions

**Views & Endpoints:**
- Plan selection page with age-based tier display (Student $3.99/mo, Adult $7.99/mo)
- Stripe Checkout session creation with promo code and referral support
- Success/cancel pages for checkout flow
- Stripe Customer Portal redirect for subscription management
- Billing settings page with plan details, credits, and referral stats
- Webhook endpoint for Stripe events

**Webhook Handlers:**
- `checkout.session.completed`: Updates user tier and subscription status
- `invoice.paid`: Marks successful payment, processes referral rewards
- `invoice.payment_failed`: Updates status to past_due
- `customer.subscription.updated`: Syncs subscription changes
- `customer.subscription.deleted`: Handles cancellation

**Files Created:**
- `apps/billing/__init__.py`, `apps.py`, `models.py`, `admin.py`
- `apps/billing/services.py`: StripeService class with checkout, portal, webhook handling
- `apps/billing/webhooks.py`: Stripe webhook receiver with signature verification
- `apps/billing/views.py`: Plan selection, checkout, settings views
- `apps/billing/urls.py`: URL routing for billing endpoints
- `apps/billing/signals.py`: Auto-create BillingProfile on User creation
- `apps/billing/migrations/0001_initial.py`: Database migration
- `templates/billing/select_plan.html`: Plan selection UI
- `templates/billing/checkout_success.html`: Success confirmation
- `templates/billing/billing_settings.html`: Subscription management UI

**Files Modified:**
- `requirements.txt`: Added `stripe>=7.0.0` and `dj-stripe>=2.8.0`
- `config/settings.py`: Added `apps.billing` and `djstripe` to INSTALLED_APPS, Stripe configuration
- `config/urls.py`: Added `/billing/` and `/join` URL patterns

**Environment Variables Needed:**
- `STRIPE_PUBLIC_KEY`: Stripe publishable key
- `STRIPE_SECRET_KEY`: Stripe secret key
- `STRIPE_WEBHOOK_SECRET`: Webhook signing secret
- `STRIPE_PRICE_STUDENT_MONTHLY`, `STRIPE_PRICE_STUDENT_ANNUAL`: Student price IDs
- `STRIPE_PRICE_ADULT_MONTHLY`, `STRIPE_PRICE_ADULT_ANNUAL`: Adult price IDs
- `STRIPE_PRICE_FOUNDING`: Founding Member lifetime price ID

**Pricing Tiers:**
- Free: Default tier before subscription
- Student ($3.99/mo or $39/yr): Age 22 and under
- Adult ($7.99/mo or $79/yr): Age 23 and over
- Founding Member ($59 one-time): Lifetime access, quarterly referral bonuses

**Next Steps (Phases 2-12):**
- Phase 2: Auto-assign tier at signup based on age
- Phase 3: Promo code admin interface
- Phase 4: Referral capture at signup
- Phase 5: Founding Member quarterly bonus calculation
- Phase 6: Birthday graduation system (student -> adult)
- Phase 7-12: Email templates, scheduled tasks, testing, go-live

---

### Smart Food Autocomplete with 3-Tier Search

**Task:** Implement intelligent food autocomplete for the nutrition log food form that recognizes partial text, pulls branded items, and auto-fills all nutrition fields.

**Implementation:** Created a 3-tier cascading food search system:
1. **Local Database** - Search user's custom foods and cached FoodItem records
2. **FatSecret API** - External API for restaurant/brand food coverage (5K free calls/day)
3. **AI Estimation** - OpenAI fallback for misspellings and generic foods

**Features:**
- Typeahead autocomplete with 300ms debounce
- Source badges showing where data comes from (Local/FatSecret/AI)
- Keyboard navigation (arrows, enter, escape)
- Auto-fills all nutrition fields on selection (calories, protein, carbs, fat, fiber, sugar, saturated fat)
- AI chat integration - `handle_log_food()` uses same 3-tier search with misspelling correction
- Results cached to local database for future searches
- Data freshness tracking with `last_verified_at` timestamps

**Files Created:**
- `apps/health/services/fatsecret.py`: FatSecret API client with OAuth 2.0 auth and 24hr token caching
- `apps/health/services/ai_nutrition.py`: AI nutrition estimation service with confidence scoring
- `apps/health/services/food_search.py`: 3-tier search orchestrator combining all sources
- `static/js/food-autocomplete.js`: Frontend autocomplete with dropdown and keyboard navigation
- `apps/health/migrations/0020_add_fatsecret_fields_to_fooditem.py`: Adds fatsecret_id and last_verified_at fields

**Files Modified:**
- `apps/health/models.py`: Added `SOURCE_FATSECRET` choice, `fatsecret_id` field (indexed), `last_verified_at` timestamp
- `apps/health/views.py`: Added `FoodSearchAPIView` for autocomplete API endpoint
- `apps/health/urls.py`: Added route `nutrition/api/search/`
- `apps/health/forms.py`: Updated food_name widget with autocomplete attributes
- `templates/health/nutrition/food_entry_form.html`: Added autocomplete CSS and script include
- `apps/ai/action_handlers.py`: Enhanced `handle_log_food()` to use food_search_service with full nutrition data
- `apps/health/tests/test_nutrition.py`: Added `FoodSearchAPITest` class with 12 test cases

**Environment Variables Required:**
- `FATSECRET_CLIENT_ID`: FatSecret API client ID
- `FATSECRET_CLIENT_SECRET`: FatSecret API client secret

**API Endpoint:** `GET /health/nutrition/api/search/?q=<query>&limit=10`

---

### Google Calendar Auto-Sync on Dashboard Load

**Task:** Automatically sync Google Calendar events when dashboard loads so "Coming Up" section shows latest events.

**Implementation:** Added `_sync_google_calendar_if_needed()` method to DashboardView that:
- Checks if user has Google Calendar connected with `auto_sync_enabled=True`
- Refreshes expired OAuth tokens if needed
- Imports events from Google Calendar to LifeEvent table
- Records sync status for debugging
- Fails silently (logs warning) to not break dashboard

Also added missing `refresh_credentials()` method to GoogleCalendarService.

**Files Modified:**
- `apps/dashboard/views.py`: Added `_sync_google_calendar_if_needed()` method, called from `_get_life_data()`
- `apps/life/services/google_calendar.py`: Added `refresh_credentials()` method
- `templates/life/google_calendar_settings.html`: Fixed "Life events" → "events" text

**Result:** Users with Google Calendar connected and auto-sync enabled will see their latest calendar events in the dashboard "Coming Up" section automatically.

---

### What's New Release Note for AI Assistant Improvements

**Task:** Add What's New entry for AI assistant improvements made earlier today.

**Implementation:** Created data migration to add release note for:
- Auto-fetch verse text when saving via assistant (uses Bible API with user's preferred translation)
- Improved intent recognition for faith, journal, and life actions

**Files Created:**
- `apps/core/migrations/0042_ai_assistant_improvements_release_note.py`: Adds "AI Assistant: Smarter Scripture & Action Recognition" release note

---

### COPPA Age Verification Implementation

**Task:** Implement age verification (13+) during registration for COPPA compliance.

**Implementation:** Added date of birth field to User model and custom signup form that blocks registration for users under 13. Updated Terms of Service and Privacy Policy with comprehensive COPPA compliance language.

**Features:**
- `date_of_birth` field added to User model (nullable for existing users)
- Custom `CustomSignupForm` extends django-allauth's SignupForm with age validation
- Blocks registration if user is under 13 years old with clear error message
- Edge case handling: exactly 13 years old today is allowed
- Sanity check: rejects dates claiming age > 120 years
- Clear messaging on signup form: "You must be 13 years or older to use this service"

**Files Modified:**
- `apps/users/models.py`: Added `date_of_birth` DateField to User model
- `apps/users/forms.py`: Added `CustomSignupForm` class with age validation
- `config/settings.py`: Added `ACCOUNT_FORMS` config, bumped `TERMS_VERSION` to 1.1
- `templates/account/signup.html`: Added date of birth input field with messaging
- `templates/core/terms.html`: Added "Age Requirements (COPPA Compliance)" section (Section 4), renumbered subsequent sections, updated to 19 total sections
- `templates/core/privacy.html`: Expanded "Children's Privacy (COPPA Compliance)" section with Age Verification, Discovery of Underage Users, Parental Rights, and Users Aged 13-17 subsections

**Migrations Created:**
- `0034_add_date_of_birth.py`: Adds date_of_birth field to User model

**Terms Version:** Updated from 1.0 to 1.1 (will trigger re-acceptance for existing users)

---

### Exclude Today's Date from "Coming Up" Dashboard Sections

**Issue:** Items scheduled for today were appearing in the "Coming Up" and "Upcoming Celebrations" sections on the dashboard. Semantically, if something is happening today, it's current, not "coming up."

**Solution:** Changed the date filtering logic to exclude today's date:
- For LifeEvent: Changed `start_date__gte=today` to `start_date__gt=today`
- For SignificantEvent: Changed `days_until <= 30` to `0 < days_until <= 30`

**Files Modified:**
- `apps/dashboard/views.py`: Updated `_get_life_data()` method to exclude today from upcoming events

---

### AI save_verse Now Auto-Fetches Verse Text from Bible API

**Issue:** When saving a verse via AI assistant, the verse was saved with an empty text field. Users would see the reference (e.g., "John 3:20") but no actual verse content.

**Solution:** Updated `handle_save_verse()` in `action_handlers.py` to automatically fetch the verse text from the Bible API when text is not provided.

**Implementation:**
- Added `_fetch_verse_text()` helper method to ActionHandler class
- Added `BOOK_ABBREVIATIONS` mapping (66 books) to convert book names to API.Bible format
- Translation mapping for KJV, ESV, NIV, NLT, NKJV, BSB
- Uses user's preferred Bible translation setting
- Response message now includes a preview of the verse text

**Files Modified:**
- `apps/ai/action_handlers.py`: Added verse text fetching from Bible API

---

### Fix AI Assistant save_verse Intent Not Recognized

**Issue:** When users asked the AI assistant to save a Bible verse (e.g., "save John 3:17"), the AI would respond as if it had saved the verse, but the verse never actually appeared in the saved verses list.

**Root Cause:** The intent recognition system's `_build_intent_system_prompt()` method in `intent_service.py` only contained examples for health-related intents (heart rate, blood pressure, weight, etc.). Faith intents like `save_verse`, `log_prayer`, and other non-health actions were not mentioned in the system prompt.

As a result, when OpenAI's function calling received a message like "save John 3:17", it didn't recognize it as a `save_verse` intent because:
1. The system prompt only described health logging scenarios
2. Without clear guidance, the model didn't call the `save_verse` function
3. The system fell back to generating a conversational response (line 1577 in `personal_assistant.py`)
4. The AI generated text that sounded like it had saved the verse, but no function was actually called

**Solution:** Expanded the intent recognition system prompt to include all action categories:
- Faith actions: save_verse, log_prayer, mark_prayer_answered
- Journal actions: create_journal_entry, add_gratitude
- Life/task actions: create_task, complete_task, create_event
- Added explicit examples for each category

**Files Modified:**
- `apps/ai/intent_service.py`: Expanded `_build_intent_system_prompt()` with comprehensive examples for all intent types

---

### Add Journal Emotions Multi-Select Feature

**Task:** Journal emojis options Angry, Sad, Excited, Anxious (can choose more than 1)

**Implementation:** Added a new `Emotion` model that allows users to select multiple emotions per journal entry (instead of the single-select mood dropdown).

**Features:**
- New `Emotion` model with name, slug, emoji, order, and is_active fields
- ManyToMany relationship between `JournalEntry` and `Emotion` for multi-select
- Checkbox-based emotion selector in journal entry form (allows multiple selections)
- Default emotions populated via data migration:
  - Great 😊, Good 🙂, Okay 😐, Low 😔, Difficult 😢
  - Angry 😠, Sad 😢, Excited 🤩, Anxious 😰
  - Grateful 🙏, Hopeful 🌟, Calm 😌, Tired 😴, Energetic ⚡
- Emotions displayed in entry detail view with emoji badges
- Admin interface for managing emotions

**Files Modified:**
- `apps/journal/models.py`: Added `Emotion` model and `emotions` ManyToMany field to `JournalEntry`, added `emotions_display` property
- `apps/journal/forms.py`: Added `emotions` field to `JournalEntryForm` with CheckboxSelectMultiple widget
- `apps/journal/admin.py`: Added `EmotionAdmin` and updated `JournalEntryAdmin` with emotions filter_horizontal
- `templates/journal/entry_form.html`: Added emotion selector UI with checkbox inputs and styling
- `templates/journal/entry_detail.html`: Added emotions display in entry meta section

**Migrations Created:**
- `0005_add_emotions.py`: Creates Emotion model and adds emotions field to JournalEntry
- `0006_populate_emotions.py`: Populates default emotions including Angry, Sad, Excited, Anxious

**Note:** The existing `mood` field is preserved for backward compatibility. Users can now track both overall mood (single-select) and specific emotions (multi-select).

---

### Fix Reading Plans 500 Error (Missing SoftDelete Status Field)

**Issue:** Navigating to `/faith/reading-plans/` caused a 500 error with `psycopg2.errors.UndefinedColumn: column faith_userreadingplan.status does not exist`.

**Root Cause:** The original migration `0006_bible_reading_plans_and_study_tools.py` created `UserReadingPlan` with a `status` field meant for plan progress tracking (active/completed/paused/abandoned). However, `UserReadingPlan` inherits from `UserOwnedModel` → `SoftDeleteModel`, which also expects a `status` field for soft-delete functionality (active/archived/deleted).

Migration `0007_rename_status_to_plan_status.py` renamed the field to avoid the naming conflict, but this left the table with NO `status` column at all. The `SoftDeleteManager.get_queryset()` filters by `status="active"`, causing the error.

**Solution:** Created migration `0008_fix_status_field_restore.py` that adds the soft-delete `status` field back to `UserReadingPlan` with proper choices (active/archived/deleted) and default='active'.

**Files Created:**
- `apps/faith/migrations/0008_fix_status_field_restore.py`: Adds missing status field

**Migration:** `0008_fix_status_field_restore.py` - AddField for status column

**Result:** Reading plans page loads correctly. Both fields now exist: `status` (for soft-delete) and `plan_status` (for reading plan progress).

---

## 2026-01-11 Changes

### Fix Reading Plans List 500 Error (Null Topics Field)

**Issue:** Navigating to `/faith/reading-plans/` caused a 500 error.

**Root Cause:** The `ReadingPlanListView.get_context_data()` method iterates through all active reading plan templates and calls `topics.update(plan.topics)` to build a list of unique topics. If any `ReadingPlanTemplate` had a `None` value for the `topics` JSONField (instead of an empty list), calling `.update(None)` on a set throws a TypeError.

**Solution:** Added a safety check `if plan.topics:` before calling `topics.update()` to handle cases where the field is `None` or empty.

**Files Modified:**
- `apps/faith/views.py`: Line ~1059 - Added null check for `plan.topics` in `ReadingPlanListView.get_context_data()`

**Result:** Reading plans list page now loads correctly even if some templates have null topics.

---

### Fix Fasting Page Context and Title Extraction

**Issue:** On the Fasting page, the assistant context indicator showed CSS code instead of the page title, and the assistant gave wrong fasting data answers.

**Root Cause:** Two issues:
1. The page title extraction was grabbing the entire `.page-title` element including the nested favorite toggle component (which contains inline CSS)
2. The fasting page had no specific context handler, so the assistant didn't see the fasting history data

**Solution:**
1. Fixed title extraction to get only direct text nodes from headings, avoiding nested elements
2. Added dedicated fasting page handler to capture active fast and completed fasts history

**Files Modified:**
- `templates/components/chat_widget.html`:
  - Fixed `getPageContext()` to extract only direct text from headings
  - Added `fasting` content type handler in `extractPageContent()`
  - Added fasting summary in `buildContextSummary()`
- `apps/ai/personal_assistant.py`:
  - Added fasting content type handling with active fast and history display

**Result:** On the Fasting page, the assistant now sees all displayed fast entries (date, duration, type) and can correctly answer questions like "what was my fast on Jan 7th?"

---

### Fix Reading Plan 404 After Completion (Status Field Conflict)

**Issue:** After completing Day 7 of a reading plan (marking it complete), users got a 404 error on the progress page.

**Root Cause:** The `UserReadingPlan` model had a `status` field with values like "active", "completed", "paused", "abandoned". However, it inherits from `UserOwnedModel` which inherits from `SoftDeleteModel`, which also has a `status` field with values "active", "archived", "deleted".

The `SoftDeleteManager` filters `status="active"` by default. When a reading plan was marked complete (status changed to "completed"), the manager filtered it out, causing the 404.

**Solution:** Renamed `UserReadingPlan.status` to `plan_status` to avoid conflict with the soft delete status field.

**Files Modified:**
- `apps/faith/models.py`: Renamed `status` → `plan_status`, updated `STATUS_CHOICES` → `PLAN_STATUS_CHOICES`, updated `mark_complete()` method
- `apps/faith/views.py`: Updated all references to `status` → `plan_status` in queries and saves
- `apps/faith/admin.py`: Updated list_display, list_filter, and admin actions
- `apps/faith/tests/test_reading_plans.py`: Updated test assertions
- `apps/faith/management/commands/reset_reading_plan_progress.py`: Updated field reference
- `templates/faith/reading_plans/progress.html`: Updated template conditions
- `apps/faith/migrations/0007_rename_status_to_plan_status.py`: Migration to rename the field

**Migration:** `0007_rename_status_to_plan_status.py` - Uses `RenameField` operation

---

### Page-Aware Assistant Chat (Context-Aware Responses)

**Feature:** The AI Assistant chat drawer now captures the content of the page you're viewing, allowing you to ask questions like "help me with this scripture" or "explain this entry" without having to specify what you're looking at.

**How it works:**
1. When you open the assistant chat, it captures the current page's content
2. A "Context:" indicator appears below the header showing what page is loaded
3. The AI can now answer questions about "this page", "this scripture", "this entry", etc.

**Supported page types:**
- **Reading Plan Progress:** Captures scriptures, devotional text, reflection prompt, day number
- **Journal Entries:** Captures title, mood, and content
- **Tasks:** Captures title, due date, description
- **Goals:** Captures title and why it matters
- **Prayer Requests:** Captures title and content
- **Health pages:** Captures current weight and workout info

**Files Modified:**
- `templates/components/chat_widget.html`:
  - Added `extractPageContent()` function to capture rich page content by type
  - Added `updateContextIndicator()` function to show current context in UI
  - Added CSS for `.assistant-context-indicator` element
  - Updated `sendMessage()` to use captured page context
  - Changed module names: `/life/` → "Organize", `/purpose/` → "Goals"
- `apps/ai/personal_assistant.py`:
  - Enhanced `_generate_response()` to build rich content descriptions from `page_content`
  - Added handling for reading_plan_progress, journal_entry, task, goal, prayer_request, health content types
  - Added instruction for AI to understand "this page", "this scripture" references

**User Experience:** On a Reading Plan page, you can now say "help me understand this scripture" and the assistant will know which scriptures you're viewing (e.g., Hebrews 12:14-15, Ephesians 4:31-32) and provide relevant explanations.

---

### Fix Journal Book View Not Displaying Content

**Issue:** Journal Book View page showed the book structure but no content (title, date, body were blank).

**Cause:** The view was using `json.dumps()` to serialize entry data, then passing it to Django's `json_script` filter which serializes again. This caused double-encoding, resulting in the JavaScript parsing an escaped string instead of the actual data.

**Solution:** Changed the view to pass raw Python data (`entries_data`) and let the `json_script` template filter handle serialization.

**Files Modified:**
- `apps/journal/views.py` (BookView.get_context_data - changed `entries_json` to `entries_data`)
- `templates/journal/book_view.html` (changed `entries_json` to `entries_data` in json_script)

---

### Fix Navigation Logo and Profile Picture Shrinking

**Issue:** On desktop, the navigation logo (left side) and profile picture/initials (right side) were being shrunk to tiny, unreadable sizes when the nav had many items.

**Cause:** Flexbox was shrinking the logo and user avatar elements to accommodate the navigation links when space was tight.

**Solution:** Added `flex-shrink: 0` and `min-width`/`min-height` constraints to prevent the logo and user elements from being compressed.

**Files Modified:**
- `templates/components/navigation.html` (inline styles for logo, avatar, initials)
- `static/css/main.css` (nav-logo, nav-user, nav-user-initial)

---

### HTMX Modal for Tag Creation During Journal Entry

**Issue:** When typing a journal entry and clicking "+ Create new tag", the browser navigated away to `/journal/tags/create/`. After creating the tag, it redirected to the tag list page - not back to the entry form. This caused users to lose any unsaved journal entry content they had typed.

**Solution:** Implemented an HTMX-powered modal for inline tag creation. The modal opens as an overlay without leaving the page, and after creating a tag, the tag selector is updated in place with the new tag pre-selected.

**Changes:**
1. **New HTMX View** - `apps/journal/views.py`: Added `HTMXTagCreateModalView` class that:
   - Returns the modal form on GET requests
   - Processes tag creation on POST and returns updated tag selector partial

2. **New URL** - `apps/journal/urls.py`: Added `htmx/tag-create/` endpoint

3. **New Template Partials** - `templates/journal/partials/`:
   - `tag_create_modal.html`: Modal dialog with tag name/color form, HTMX-enabled
   - `tag_selector.html`: Tag checkbox list partial, returned after successful tag creation

4. **Updated Entry Form** - `templates/journal/entry_form.html`:
   - Wrapped tag selector in `#tag-selector-container` div for HTMX targeting
   - Changed "+ Create new tag" link to button with HTMX attributes
   - Added `.create-tag-btn` styling to make button look like a link

**Files Modified:**
- `apps/journal/views.py` (added HTMXTagCreateModalView, added render import)
- `apps/journal/urls.py` (added htmx_tag_create URL)
- `templates/journal/entry_form.html` (HTMX button, container div, CSS)

**Files Created:**
- `templates/journal/partials/tag_create_modal.html`
- `templates/journal/partials/tag_selector.html`

**User Experience:** Users can now create tags while typing a journal entry without losing their work. The modal appears as an overlay, and after creating a tag, it's automatically selected in the entry form.

---

### Debug Logging for CI 500 Errors

**Issue:** CI tests failing with 500 errors for `/admin-console/` path. The ERROR logs show the 500 handler being called but no actual exception traceback, making it impossible to diagnose the root cause.

**Changes:**
1. **Enhanced 500 Handler** - `apps/core/views.py`: Modified `custom_500()` to capture and log the full exception traceback using `sys.exc_info()` and `traceback.format_exception()`

2. **AdminDashboardView Debug** - `apps/admin_console/views.py`: Wrapped `get_context_data()` in try/except with `logger.exception()` to capture any errors during context building

**Files Modified:**
- `apps/core/views.py` (custom_500 function)
- `apps/admin_console/views.py` (AdminDashboardView.get_context_data)

**Purpose:** When CI runs again, the logs will show the actual exception and traceback that's causing the 500 errors, allowing us to fix the root cause.

---

### Reading Plan Progress - Notes Not Saving Bug Fix

**Issue:** When users marked a reading plan day as complete, any notes they entered were not being saved to the database. This was because the `mark_complete()` method used `update_fields` that only included `is_completed`, `completed_at`, and `updated_at` - not the `notes` field.

**Changes:**
1. **Bug Fix** - `apps/faith/views.py`: Modified `MarkDayCompleteView.post()` to save notes separately before calling `mark_complete()`
   - Notes are now saved with their own `save(update_fields=["notes", "updated_at"])` call

2. **Regression Tests** - `apps/faith/tests/test_reading_plans.py`: Added comprehensive test suite
   - Critical regression test: `test_mark_day_complete_saves_notes`
   - Model tests for ReadingPlanTemplate, UserReadingPlan, UserReadingProgress
   - View tests for marking progress and viewing plans
   - Data isolation tests to ensure users can only see their own plans

3. **Admin Recovery Actions** - `apps/faith/admin.py`: Added admin actions to help affected users
   - "Reset selected plans to Day 1 (keep notes)" - Full reset preserving any notes
   - "Reset incomplete days only (for bug recovery)" - Only resets days marked complete with empty notes
   - Added progress display column showing completion percentage

**Files Modified:**
- `apps/faith/views.py` (lines 1202-1208)
- `apps/faith/tests/test_reading_plans.py` (new file)
- `apps/faith/admin.py` (UserReadingPlanAdmin)

---

### AI Assistant Update - Responsive Behavior

**Issue:** The AI Assistant was proactively summarizing tasks, overdue items, and outstanding priorities in every response. User wanted the assistant to only provide this information when explicitly asked.

**Changes:**
1. **Dashboard check-in (left side) ALWAYS shows full coaching review**
   - State summary, priorities, nudges, and reflection prompt always shown
   - Tracks `last_opening_shown_date` in conversation metadata for info purposes
   - The `is_first_visit` flag is tracked but doesn't hide content
   - This is the coach actively reviewing your information

2. **Chat (right side) is now interactive and responsive**
   - System prompt updated to prevent unsolicited task summaries
   - Added explicit "NEVER VOLUNTEER THESE UNLESS ASKED" section
   - Chat only provides task info when user explicitly asks (e.g., "what do I have left to do today?")
   - Chat doesn't repeat what's already shown on the left side

3. **Response generation no longer injects state data by default**
   - State context only added when user asks about tasks/priorities
   - Phrase detection for task-related queries triggers state injection
   - Time context removed from default prompts (was too pushy)

4. **Fixed AI Coach selection not being read on change**
   - Added `refresh_from_db()` calls in PersonalAssistant.__init__
   - Also fixed in DashboardAI and TrendTracker classes
   - Ensures latest coaching style is always used across all AI components

5. **Fixed AI assessment not regenerating when coaching style changes**
   - AI assessment was cached in UserStateSnapshot for the day
   - Now stores coaching style in snapshot metadata (`alignment_gaps`)
   - When coaching style changes, forces regeneration of AI assessment
   - Handles legacy snapshots without stored style by regenerating

**Files Modified:**
- `apps/ai/personal_assistant.py` - Updated system prompt, opening message, response generation, refresh_from_db fix, coaching style tracking in snapshot
- `apps/ai/views.py` - Added is_first_visit to opening API response
- `apps/ai/dashboard_ai.py` - Added refresh_from_db for coaching style
- `apps/ai/trend_tracking.py` - Added refresh_from_db for coaching style

---

### Armed Forces Coaching Styles

**Feature:** Added coaching styles for all 6 U.S. military branches, organized under a new "Armed Forces" category.

**New Coaching Styles:**
1. **Army Drill Sergeant** - Intense boot camp accountability
2. **Navy Chief Petty Officer** - Nautical teamwork and navigation metaphors
3. **Marine Gunnery Sergeant** - Semper Fi warrior ethos
4. **Air Force Training Instructor** - Precision and excellence focus
5. **Coast Guard Chief** - Semper Paratus rescue/service mindset
6. **Space Force Guardian** - Innovation and reaching for the stars

**Implementation:**
1. Added `category` field to `CoachingStyle` model for grouping styles
2. Added `get_styles_by_category()` method for grouped retrieval
3. Updated onboarding wizard and preferences templates to display grouped styles
4. Added CSS for category headers (uppercase, muted color, border separator)

**Files Modified:**
- `apps/ai/models.py` - Added category field and grouped retrieval method
- `apps/users/views.py` - Pass grouped styles to templates
- `templates/users/onboarding_wizard.html` - Grouped display with category headers
- `templates/users/preferences.html` - Grouped display with category headers

**Migration:**
- `apps/ai/migrations/0015_add_drill_sergeant_coaching_style.py` - Adds category field and all 6 Armed Forces styles

---

### Add "No Fasting" Option to Fasting Feature

**Issue:** Users who don't practice fasting had no way to indicate this preference. The fasting type dropdown only showed actual fasting schedules (16:8, 18:6, etc.) with no option to opt out.

**Fix:** Added "No Fasting" (`none`) as the first option in fasting type choices:

1. **FastingWindow Model** (`apps/health/models.py`):
   - Added `("none", "No Fasting")` to `FASTING_TYPE_CHOICES`

2. **UserPreferences Model** (`apps/users/models.py`):
   - Added `("none", "No Fasting")` to `FASTING_TYPE_CHOICES`
   - Added description: "You don't practice intermittent fasting. The fasting tracker will not be shown in your dashboard."

3. **FastingWindowForm** (`apps/health/forms.py`):
   - Added `clean_fasting_type()` validation to prevent starting a fast with "none" type
   - Shows user-friendly error if they try to start a fast with "No Fasting" selected

**Files Modified:**
- `apps/health/models.py` - Added "none" choice
- `apps/users/models.py` - Added "none" choice and description
- `apps/health/forms.py` - Added validation

---


### Comprehensive Sub-Feature Toggles Update

**Issue:** Initial sub-feature toggle implementation was missing several features that exist in the navigation (Blood Pressure, Blood Oxygen, Sleep, Steps, Providers, Reading Plans, Study Tools, Milestones, Maintenance, Habit Goals, Prompts).

**Fix:** Expanded all FEATURES constants to include every toggleable sub-feature:

1. **HEALTH_FEATURES** (12 features):
   - weight, heart_rate, blood_pressure, blood_oxygen, glucose
   - medicine, workouts, steps, nutrition, fasting, sleep, providers

2. **FAITH_FEATURES** (8 features):
   - scripture, reading_plans, study_tools, prayers
   - milestones, reflections, memory_verses, devotionals

3. **ORGANIZE_FEATURES** (9 features):
   - tasks, calendar, projects, inventory, pets
   - recipes, maintenance, documents, significant_events

4. **GOALS_FEATURES** (5 features):
   - goals, habit_goals, annual_direction, intentions, reflections

5. **JOURNAL_FEATURES** (4 features):
   - prompts, mood_tracking, tags, ai_reflections

**Navigation Updates** (`templates/components/navigation.html`):
- Fixed Health menu to use proper feature keys (blood_pressure, blood_oxygen, sleep, steps, providers)
- Added maintenance conditional to Organize menu
- Added prompts conditional to Journal menu
- Added habit_goals conditional to Goals menu

**Files Modified:**
- `apps/users/models.py` - Expanded FEATURES constants
- `templates/components/navigation.html` - Added feature conditionals

---

### Sub-Feature Toggles (Customize Features)

**Feature Request:** Users should be able to enable/disable specific features within each module (e.g., turn off Medicine tracking in Health module while keeping Weight tracking). All features default to ON (opt-out model). Disabled features are hidden from navigation/dashboard but data is never deleted.

**Implementation:**

1. **Model Changes** (`apps/users/models.py`):
   - Added 5 JSONField columns for sub-feature storage:
     - `health_features` - Weight, Fasting, Medicine, Workouts, Nutrition, Heart Rate, Glucose
     - `organize_features` - Tasks, Calendar, Projects, Inventory, Pets, Recipes, Documents, Significant Events
     - `goals_features` - Goals, Annual Direction, Intentions, Reflections
     - `faith_features` - Prayers, Scripture, Reading Plans, Study Tools, Milestones, Reflections
     - `journal_features` - Mood Tracking, Tags, AI Reflections
   - Added feature metadata constants (HEALTH_FEATURES, ORGANIZE_FEATURES, etc.) with labels, icons, defaults
   - Added helper methods:
     - `is_feature_enabled(module, feature)` - Check if feature enabled (respects parent module)
     - `get_enabled_features(module)` - List of enabled feature keys
     - `set_feature_enabled(module, feature, enabled)` - Update feature setting
   - Migration: `0032_sub_feature_toggles.py`

2. **API Endpoints** (`apps/users/views.py`, `apps/users/urls.py`):
   - `SubFeatureToggleView` - POST `/user/api/sub-feature-toggle/`
     - Toggle individual feature: `{module, feature, enabled}`
   - `SubFeaturesBulkView` - GET/POST `/user/api/sub-features/`
     - GET: Returns all feature states
     - POST: Bulk update features

3. **Context Processor** (`apps/core/context_processors.py`):
   - Added `features` dict to theme_context with all module feature states
   - Available in templates as `features.health.weight`, `features.organize.tasks`, etc.

4. **Preferences UI** (`templates/users/preferences.html`):
   - Added "Customize Features" accordion section with nested accordions per module
   - Feature toggles displayed in responsive grid with icons and labels
   - Real-time API calls on checkbox change (no page reload needed)
   - Badge shows "All enabled", "All disabled", or "X/Y enabled"
   - CSS: `.feature-toggles-grid`, `.feature-toggle-item`, `.feature-toggle-label`
   - JS: `initFeatureToggles()`, `handleFeatureToggle()`, `updateFeatureCount()`

5. **Navigation Updates** (`templates/components/navigation.html`):
   - Health menu: Vitals items conditional on weight/heart_rate/glucose; Medicine/Fitness/Nutrition columns conditional
   - Organize menu: Calendar, Projects, Tasks, Inventory, Pets, Recipes, Documents, Significant Events conditional
   - Goals menu: Annual Direction, Goals/Habit Goals, Intentions, Reflections conditional
   - Faith menu: Scripture-related items, Prayers, Milestones, Reflections conditional
   - Journal menu: Tags conditional

**Design Decisions:**
- Opt-out model: All features enabled by default
- Data preservation: Disabling a feature hides it, never deletes data
- Parent module respect: Sub-features auto-disabled if parent module disabled
- Real-time updates: No form submission needed for toggles
- UI naming: "Life" displays as "Organize", "Purpose" as "Goals" (apps.py verbose_name)

**Files Modified:**
- `apps/users/models.py` - Added 5 JSON fields, constants, helper methods
- `apps/users/migrations/0032_sub_feature_toggles.py` - New migration
- `apps/users/views.py` - Added 2 API views, updated PreferencesView
- `apps/users/urls.py` - Added 2 URL routes
- `apps/core/context_processors.py` - Added features dict to theme_context
- `templates/users/preferences.html` - Added Customize Features section with CSS/JS
- `templates/components/navigation.html` - Added conditional feature checks

---

### AI Profile Setup Nudge & Guided Builder

**Feature Request:** Users should be reminded to complete their AI Profile for a personalized experience. The nudge should offer help building the profile through guided questions, with options to dismiss or snooze.

**Implementation:**

1. **Model Changes** (`apps/users/models.py`):
   - Added `ai_profile_nudge_dismissed` (BooleanField) - permanent dismissal flag
   - Added `ai_profile_nudge_snoozed_until` (DateTimeField) - snooze until datetime
   - Migration: `0031_ai_profile_nudge_settings.py`

2. **Dashboard Logic** (`apps/dashboard/views.py`):
   - Added `_should_show_ai_profile_nudge()` method
   - Shows nudge when: AI enabled, profile empty/short (<50 chars), not dismissed, snooze expired
   - Added `show_ai_profile_nudge` to context

3. **API Endpoints** (`apps/users/views.py`, `apps/users/urls.py`):
   - `AIProfileNudgeActionView` - POST `/user/api/ai-profile-nudge/`
     - Actions: dismiss (permanent), snooze (3 days), snooze_week (7 days)
   - `AIProfileBuilderView` - POST `/user/api/ai-profile-builder/`
     - Accepts structured answers, generates natural-language profile

4. **Dashboard UI** (`templates/dashboard/home.html`):
   - Nudge card with prominent styling (gradient background, accent border)
   - Three options: "Help Me Set It Up", "I'll Do It Myself", "Don't Show Again"
   - Close button snoozes for 3 days (respects user intent without permanent dismissal)

5. **Profile Builder Modal** (6-step wizard):
   - Step 1: About You (birth year, life stage)
   - Step 2: Family (relationship status, spouse/children info)
   - Step 3: Faith (importance, details)
   - Step 4: Work & Career (type, details)
   - Step 5: Health Focus (multi-select checkboxes)
   - Step 6: Communication & Goals (style, goals, other)
   - All fields optional - users can skip any they prefer not to answer
   - Generates coherent natural-language profile from answers

**Industry Standards Applied:**
- Progressive disclosure (collapsed by default after initial nudge)
- Respect user choice (snooze vs permanent dismiss)
- Low friction (guided wizard as alternative to manual entry)
- Maximum 50 chars threshold for "empty" profile

**Files Modified:**
- `apps/users/models.py` - Added 2 new fields
- `apps/users/migrations/0031_ai_profile_nudge_settings.py` - New migration
- `apps/dashboard/views.py` - Added nudge logic
- `apps/users/views.py` - Added 2 API views
- `apps/users/urls.py` - Added 2 URL routes
- `templates/dashboard/home.html` - Added nudge card, modal, JS, CSS

---

### Preferences Page Accordion Redesign

**Problem:** The preferences page was too long (2294 lines, 62+ settings across 11 flat cards) making it difficult to navigate. Users had to scroll extensively to find specific settings.

**Solution:** Implemented a collapsible accordion pattern following industry standards (iOS Settings, macOS System Preferences, Google Account Settings).

**Changes:**

1. **New Accordion CSS Component** (`static/css/main.css`):
   - Added comprehensive accordion styles with nested accordion support
   - Header with icon, title, subtitle, status badges, and chevron
   - Smooth animations with reduced-motion support
   - Mobile-responsive design

2. **New Accordion JavaScript** (`static/js/accordion.js`):
   - Expand/collapse functionality with click and keyboard support
   - localStorage persistence for expansion state
   - ARIA accessibility attributes
   - Public API: `WLJAccordion.open()`, `.close()`, `.toggle()`, `.expandAll()`, `.collapseAll()`, `.refresh()`

3. **Restructured Preferences Template** (`templates/users/preferences.html`):
   - Reorganized 11 flat cards into 9 collapsible accordion groups
   - Added nested accordions for complex sections (AI, Notifications, Health)
   - Status badges on collapsed headers showing current state
   - "Expand All" / "Collapse All" buttons in page header
   - All accordions collapsed by default for cleaner initial view

**New Organization Structure:**
- 🎨 Appearance (Theme, Accent Color)
- 📦 Modules (6 active + 2 coming soon)
- 🤖 AI & Intelligence (nested: Coaching Style, Personal Profile, Personal Assistant)
- 🌍 Location & Time
- 🔔 Notifications & Communication (nested: In-App, SMS with categories)
- 🔐 Security & Privacy (Biometric login)
- ❤️ Health & Wellness (conditional, nested: Fasting, Weight & Nutrition)
- ✝️ Faith Settings (conditional)
- 🔗 Integrations (Google Calendar)

**User Benefits:**
- Reduced visual overwhelm - users see 9 compact headers instead of 11 full cards
- Quick access via status badges (e.g., "AI: Enabled", "SMS Active")
- Expansion state persists across page refreshes
- Familiar accordion pattern used by all major platforms

**Files Changed:**
- `static/css/main.css` - Added accordion CSS component (~200 lines)
- `static/js/accordion.js` - New file (~220 lines)
- `templates/users/preferences.html` - Full restructure with accordion groups

---

## 2026-01-10 Changes

### Army Drill Sergeant Coaching Persona

**Request:** User wanted a new AI coaching persona styled as an Army Drill Sergeant.

**Changes:**

1. **Coaching Styles Fixture** (`apps/ai/fixtures/coaching_styles.json`):
   - Added new "Army Drill Sergeant" persona (pk: 8, key: drill_sergeant)
   - Icon: 🎖️
   - Style: Tough but invested military drill instructor
   - Uses military expressions: "Drop and give me twenty!", "HOOAH!", "No excuses, recruit!"
   - Tough love approach that builds up, never tears down

**Result:** Users can now select the Army Drill Sergeant coaching style in their preferences for a high-intensity, accountability-focused coaching experience.

**Files Changed:**
- `apps/ai/fixtures/coaching_styles.json` - Added drill_sergeant persona

---

### Context-Aware Assistant Responses

**Request:** User wanted the assistant to know what page they are on so it can provide context-aware feedback.

**Changes:**

1. **AssistantChatView** (`apps/ai/views.py`):
   - Now accepts `page_context` from request body (url, module, page_title)
   - Passes page context through to PersonalAssistant.send_message()

2. **PersonalAssistant.send_message()** (`apps/ai/personal_assistant.py`):
   - Updated signature to accept `page_context` parameter
   - Passes page context to `_generate_response()`

3. **PersonalAssistant._generate_response()** (`apps/ai/personal_assistant.py`):
   - Updated to accept `page_context` parameter
   - Adds PAGE CONTEXT section to AI system prompt when context is provided
   - Provides guidance to AI on how to use page context (Faith, Health, Journal, etc.)

4. **Chat Widget Frontend** (`templates/components/chat_widget.html`):
   - Added `getPageContext()` function to extract URL, module, and page title
   - Module detection for Faith, Health, Journal, Life, Purpose, Assistant, Dashboard
   - Page title extraction from h1, .page-title, or document.title
   - Sends page_context with every chat message

**Result:** When users open the assistant drawer while on a specific page (e.g., Faith), the assistant now knows the context and can provide more relevant, contextual help.

**Files Changed:**
- `apps/ai/views.py` - Accept page_context in chat API
- `apps/ai/personal_assistant.py` - Pass and use page_context in AI prompts
- `templates/components/chat_widget.html` - Send page context with messages

---

### Drawer Persistence Across Page Navigation

**Request:** User wanted the assistant drawer to stay open when navigating between pages.

**Changes:**
- Added localStorage persistence for drawer open state
- Drawer automatically reopens on page load if it was previously open
- State cleared when going to full `/assistant/` page or manually closing

**Files Changed:**
- `templates/components/chat_widget.html` - localStorage persistence logic

---

### Sync on Focus for Chat

**Request:** User wanted chat to sync between drawer and /assistant/ page.

**Changes:**
- Added `visibilitychange` event listener to both interfaces
- When user switches tabs/windows and returns, chat history refreshes
- Only updates DOM if message count changed (avoids flicker)

**Files Changed:**
- `templates/components/chat_widget.html` - Visibility change sync
- `templates/ai/assistant_dashboard.html` - Visibility change sync

---

### Unified Assistant Experience - Slide-out Drawer

**Request:** User wanted a unified assistant experience where:
1. Clicking the floating chat button opens a slide-out drawer (not a popup widget)
2. The drawer uses the same Personal Assistant backend as the `/assistant/` page
3. Conversation history persists across pages and sessions until cleared
4. Users can clear conversation to start fresh

**Changes:**

1. **AssistantConversation Model** (`apps/ai/models.py`):
   - Changed `get_or_create_active()` to persist conversations across days (not daily reset)
   - Added `clear_messages()` method to clear conversation content
   - Added `clear_active_conversation()` class method for clearing via API

2. **New Clear Conversation API** (`apps/ai/views.py`, `apps/ai/urls.py`):
   - Added `ClearConversationView` at `/assistant/api/clear/`
   - POST endpoint to clear all messages and start fresh

3. **New Slide-out Drawer** (`templates/components/chat_widget.html`):
   - Replaced old popup widget with full-height slide-out drawer
   - Loads conversation history from Personal Assistant API on open
   - Features: clear conversation button, open full page button, close button
   - Smooth slide-in animation with overlay backdrop
   - Responsive design (full width on mobile)

4. **Updated Assistant Dashboard** (`templates/ai/assistant_dashboard.html`):
   - Chat sidebar now loads conversation history on page load
   - Added clear conversation button in header
   - Added loading state and empty state UI
   - Both interfaces now share the same conversation

**Files Changed:**
- `apps/ai/models.py` - Updated AssistantConversation model
- `apps/ai/views.py` - Added ClearConversationView
- `apps/ai/urls.py` - Added clear endpoint route
- `templates/components/chat_widget.html` - Complete rewrite as slide-out drawer
- `templates/ai/assistant_dashboard.html` - Load history, clear button, UI updates

**Backup Location:** `backups/assistant_unification_2026-01-10/`

---

### Added "What's New" Link to User Dropdown Menu

**Request:** User requested a direct link to the What's New page in the user dropdown menu.

**Changes:**
- Added "What's New" link after "Preferences" in the user dropdown menu
- Links to existing `core:whats_new_list` route at `/whats-new/`

**Files Changed:**
- `templates/components/navigation.html` - Added nav-user-link for What's New

---

### Task Creation Debugging for Feature Requests

**Issue:** Emails were being sent for feature requests but tasks were not being created in the Admin Console.

**Diagnosis:** Added detailed step-by-step logging to identify the exact failure point.

**Changes:**
1. Added comprehensive logging at each step of task creation:
   - Project lookup/creation
   - Phase 1 lookup/fallback
   - Task object creation
   - Task save operation
2. Fixed Phase 1 lookup to use `.filter().first()` instead of `.get()` for robustness
3. Added fallback to use any existing phase if Phase 1 not found
4. Added fallback to create Phase 1 if no phases exist

**Files Changed:**
- `apps/ai/feature_request_service.py` - Enhanced logging and robust phase lookup

**Monitoring:** After deployment, logs will reveal exactly where task creation is failing.

---

### Feature Request Review: Health Data Export (Task #236)

**Request:** User requested ability to export blood glucose numbers for the last week.

**Decision:** APPROVED

**Rationale:**
- Data ownership: Users should control and export their own health data
- Natural complement to existing import functionality (import_clarity_csv.py)
- GlucoseEntry model already exists with Dexcom CGM integration
- Can be generalized to export multiple health metrics (weight, glucose, fasting, etc.)

**Next Steps:** Implementation task created for health data export feature with:
- CSV export for glucose readings with date range filtering
- Option to include trend data from Dexcom CGM
- Potential to extend to other health metrics (weight, heart rate, etc.)

---

### Phase Filter Dropdown Fix + Phase 999 Cleanup

**Changes:**
1. Fixed phase dropdown in Admin Console to show just phase name instead of "Phase X: Phase X"
2. Created migration to move tasks from Phase 999 to Phase 1
3. Deleted Phase 999 (was used for User Requests, now uses Phase 1)
4. Updated feature request service to create tasks in Phase 1

**Files Changed:**
- `templates/admin_console/admin_task_list.html` - Fixed dropdown label
- `apps/admin_console/models.py` - Fixed `__str__` method
- `apps/admin_console/migrations/0016_cleanup_phase_999.py` - Data migration
- `apps/ai/feature_request_service.py` - Use Phase 1 instead of 999

---

### AI Assistant Feature Request Detection + Auto Task Creation

**Summary:**
Added automatic detection of user feature requests ("I wish", "I want") in the AI Assistant.
When a user expresses a wish or want that the system can't fulfill:
1. Creates an AdminTask in the "New Requests" project (status: backlog)
2. Sends email notification with task ID for easy review

**Admin Workflow:**
- Tasks appear in "New Requests" project with status: backlog
- Review the task in Admin Console
- Mark as "Ready" to approve for implementation
- Mark as "Done" or delete to reject

**Changes Made:**

1. **Feature Request Detection Service**
   - Detects 15+ patterns including "I wish I could", "I want to be able", "can you add",
     "it would be nice if", "there should be a way", etc.
   - Auto-creates AdminTask in "New Requests" project (creates project if needed)
   - Auto-creates "User Requests" phase (phase 999) for organizing requests
   - Sends email notification with task ID to admin
   - Includes rate limiting (24h) to prevent duplicate notifications for similar requests
   - File: `apps/ai/feature_request_service.py`

2. **Integration with Personal Assistant**
   - Added `_check_feature_request()` method to detect feature requests after intent recognition
   - Only triggers when no actionable intent is found (intent_type='no_action')
   - Graceful error handling that doesn't break the chat flow
   - File: `apps/ai/personal_assistant.py`

3. **Email Template**
   - HTML email template extending base_email.html
   - Shows task ID when created, with link to Admin Console workflow
   - Shows user details, detected pattern, message, and conversation context
   - Clear action items based on whether task was created
   - File: `templates/assistant/emails/feature_request.html`

4. **Test Suite**
   - Comprehensive tests for pattern detection
   - Rate limiting tests
   - Email notification tests
   - Edge case handling (empty messages, long messages, special characters)
   - File: `apps/ai/tests/test_feature_request_service.py`

**Files Added:**
- `apps/ai/feature_request_service.py`
- `apps/ai/tests/test_feature_request_service.py`
- `templates/assistant/emails/feature_request.html`

**Files Modified:**
- `apps/ai/personal_assistant.py`

---

## 2026-01-10 Changes (Earlier)

### Production Readiness - Pre-Launch Hardening

**Summary:**
Final production hardening before go-live. Addressed security and reliability concerns from production readiness assessment.

**Changes Made:**

1. **Remove Test SMS from Startup**
   - Removed `send_test_sms` command from nixpacks.toml startup
   - Prevents real SMS being sent on every Railway deploy
   - File: `nixpacks.toml`

2. **Database Connection Pooling**
   - Added `CONN_MAX_AGE=600` (10 minutes) for persistent connections
   - Added `CONN_HEALTH_CHECKS=True` to verify connections before reuse
   - Reduces latency and database connection overhead
   - File: `config/settings.py`

3. **Require PostgreSQL in Production**
   - Added check that raises `ImproperlyConfigured` if `DATABASE_URL` missing in production
   - SQLite now only allowed when `DEBUG=True`
   - Prevents accidental use of SQLite in production (data loss risk)
   - File: `config/settings.py`

4. **CSP Testing Period Extended**
   - Extended CSP report-only testing period to 2026-01-25
   - Allows more time to monitor for CSP violations before enforcement
   - File: `apps/core/middleware.py`

**Files Modified:**
- `nixpacks.toml`
- `config/settings.py`
- `apps/core/middleware.py`

---

### Fix: Missing `logging` import in settings.py

**Problem:** Production deployment failing with `NameError: name 'logging' is not defined` at line 303 in settings.py.

**Cause:** The `JsonFormatter` class inherits from `logging.Formatter`, but `logging` was never imported at module level.

**Fix:** Added `import logging` to the imports at the top of `config/settings.py`.

**Files Modified:**
- `config/settings.py` (line 44)

---

### Production Readiness Improvements

**Summary:**
Added comprehensive production readiness features including error tracking, CI/CD, health monitoring, and improved logging.

**Changes Made:**

1. **Sentry Error Tracking Integration**
   - Added `sentry-sdk` to requirements.txt
   - Configured Sentry in settings.py with Django and logging integrations
   - Performance monitoring with configurable sample rates
   - Release tracking via Railway Git commit SHA
   - Environment tagging (production/staging/development)
   - Files: `config/settings.py`, `requirements.txt`, `.env.example`

2. **Health Check Endpoint**
   - Added `/health/` endpoint for monitoring services
   - Returns JSON with status, database connectivity, and version
   - Used by Railway, uptime monitors, and load balancers
   - Files: `apps/core/views.py`, `apps/core/urls.py`

3. **GitHub Actions CI/CD Workflow**
   - Created `.github/workflows/test.yml`
   - Runs tests on push/PR to main and develop branches
   - Includes Django checks, migration verification, and test coverage
   - Linting job (Black, isort, Flake8)
   - Security checks (Safety, Bandit, Django deploy check)
   - Codecov integration for coverage reporting

4. **Test Coverage Configuration**
   - Added `coverage` to requirements.txt
   - Created `.coveragerc` with comprehensive settings
   - 50% minimum coverage threshold
   - Branch coverage enabled
   - Excludes migrations, tests, admin/apps files

5. **Structured JSON Logging**
   - Added `JsonFormatter` class for production logging
   - Outputs single-line JSON with timestamp, level, logger, message, module, line
   - Added `console_json` handler (production only)
   - Key loggers now output JSON in production for easier parsing
   - Files: `config/settings.py`

6. **Database Backup Verification Procedure**
   - Added section 4.1 to `docs/wlj_backup.md`
   - Step-by-step verification procedure
   - SQL queries for data integrity checks
   - Verification checklist and log template

**Files Created:**
- `.github/workflows/test.yml` - CI/CD workflow
- `.coveragerc` - Coverage configuration

**Files Modified:**
- `config/settings.py` - Sentry, JSON logging
- `apps/core/views.py` - HealthCheckView
- `apps/core/urls.py` - /health/ route
- `requirements.txt` - sentry-sdk, coverage
- `.env.example` - Sentry configuration docs
- `docs/wlj_backup.md` - Verification procedure

**Environment Variables Added:**
- `SENTRY_DSN` - Sentry project DSN
- `SENTRY_TRACES_SAMPLE_RATE` - Performance sampling (default 0.1)
- `SENTRY_PROFILES_SAMPLE_RATE` - Profiling sampling (default 0.1)
- `SENTRY_ENVIRONMENT` - Environment tag (default: production)

---

### Update Organize/Life Calendar to Grid View

**Issue:**
The Organize > Calendar page at `/life/calendar/` was displaying events as a list grouped by date,
not as an actual calendar grid.

**Solution:**
Converted the Life calendar to display as a proper monthly grid view, matching the Journal calendar.

**Files Modified:**
- `apps/life/views.py` - Updated `CalendarView` to generate calendar grid data (weeks/days structure)
- `templates/life/calendar.html` - Complete rewrite with calendar grid layout

**Features:**
- Monthly calendar grid with 7-column layout (Sun-Sat)
- Events displayed as color-coded bars by event type
- Event type legend showing all 8 categories
- Click events to edit them
- Hover tooltip shows event title and time
- Today highlighted with accent circle
- Previous/next month navigation
- "Go to Today" button when viewing other months
- Responsive design (mobile shows colored bars only)
- Google Calendar integration card preserved

---

### Add Journal Calendar View

**Issue:**
The Journal home page had a "Calendar View" link pointing to `?view=calendar` on the entry list,
but the calendar view was never implemented - clicking the link just showed the regular entry list.

**Solution:**
Implemented a full calendar view for journal entries with monthly navigation.

**Files Modified:**
- `apps/journal/views.py` - Added `CalendarView` class with monthly calendar generation
- `apps/journal/urls.py` - Added `/journal/calendar/` route
- `templates/journal/home.html` - Updated Calendar View link to use proper URL
- `templates/journal/entry_list.html` - Added calendar icon to view toggle
- `templates/journal/calendar_view.html` - New template for calendar display

**Features:**
- Monthly calendar grid view showing entries by date
- Entries display with mood emoji and truncated title
- Previous/next month navigation
- "Go to Today" button when viewing other months
- Responsive design (mobile shows mood emojis only)
- View toggle consistent with other journal views (list, calendar, page, book)
- Entry counts for total and current month

---

### Add Steps Tracking Feature to Health Module (Task #233)

**Feature:**
Added daily step count tracking to the Health module with full CRUD functionality.

**StepsEntry Model:**
- `count` - Daily step count (PositiveIntegerField)
- `logged_date` - Date for the steps
- `source` - Manual or synced from wearables (Apple Health, Google Fit, Fitbit, Garmin, Samsung Health)
- `sync_id` - For deduplication when syncing from external sources
- `goal` - Optional daily step goal
- `distance_miles` - Optional distance in miles
- `calories_burned` - Optional calories estimate
- Properties: `goal_percentage`, `goal_reached`, `distance_km`
- UniqueConstraint: One entry per day per source per user

**Views:**
- `StepsListView` - List with stats (7-day avg, total, goals met) and Chart.js bar chart
- `StepsCreateView` - Form with Save & Add Another support
- `StepsUpdateView` - Edit existing entries
- `StepsDeleteView` - Soft delete with undo support
- `BulkDeleteStepsView` - Bulk deletion

**URLs:**
- `/health/steps/` - List view
- `/health/steps/log/` - Create new entry
- `/health/steps/<pk>/edit/` - Edit entry
- `/health/steps/<pk>/delete/` - Delete entry

**Templates:**
- `steps_list.html` - List view with activity chart
- `steps_form.html` - Create/edit form with activity level guide

**Health Home Integration:**
- Added Steps card showing latest entry and 7-day average

**Future Connect API:**
Model designed for iOS/Android app integration via `source` and `sync_id` fields.

**Files modified:**
- `apps/health/models.py` - Added StepsEntry model
- `apps/health/forms.py` - Added StepsEntryForm
- `apps/health/views.py` - Added 5 views for Steps CRUD
- `apps/health/urls.py` - Added 5 URL patterns
- `templates/health/home.html` - Added Steps card
- `templates/health/steps_list.html` - New template
- `templates/health/steps_form.html` - New template
- `apps/health/migrations/0016_add_steps_entry.py` - Migration

---

### Comprehensive Intent Detector Expansion for All WLJ Data Types

**Problem:**
The assistant's intent detector only recognized a limited set of data types (weight, journal, medication, food, mood, sleep, exercise, glucose, blood_pressure, faith, goals). Many user queries about other WLJ data couldn't be understood.

**Solution:**
Performed a comprehensive analysis of all WLJ data models and expanded the intent detector to recognize ~30 data type categories with hundreds of keyword patterns:

**Health Module:**
- `weight` - weight, BMI, body mass, scale readings
- `glucose` - blood sugar, CGM, A1c, insulin
- `blood_pressure` - BP, systolic, diastolic, hypertension
- `heart_rate` - pulse, BPM, HRV, resting heart rate
- `blood_oxygen` - SpO2, oxygen saturation
- `medication` - medications, prescriptions, supplements, vitamins
- `food` - meals, calories, macros, nutrition
- `nutrition_goals` - calorie targets, macro goals
- `workout` - exercise, gym, strength training, lifting
- `cardio` - running, walking, steps, cycling, swimming
- `fitness` - yoga, flexibility, activity level
- `medical_provider` - doctors, specialists, appointments

**Journal Module:**
- `journal` - entries, reflections, gratitude, morning pages

**Faith Module:**
- `faith` - spiritual, devotional, quiet time
- `prayer` - prayer requests, answered prayers
- `scripture` - bible verses, reading
- `reading_plan` - bible reading plans
- `faith_milestone` - salvation, baptism, spiritual milestones

**Life Module (Organize):**
- `task` - tasks, to-dos, action items
- `project` - projects, milestones
- `event` - calendar events, appointments
- `significant_event` - life events, anniversaries
- `pet` - pets, pet care
- `recipe` - recipes, cooking
- `inventory` - household inventory
- `maintenance` - home maintenance, vehicle maintenance
- `document` - important documents, files

**Purpose Module (Goals):**
- `goals` - goals, objectives
- `habit` - habits, streaks, habit tracking
- `intention` - intentions, focus areas
- `reflection` - self-reflection, reviews
- `annual_direction` - yearly direction, annual goals

**Finance Module:**
- `account` - bank accounts, credit cards
- `transaction` - transactions, spending
- `budget` - budgets, spending limits
- `financial_goal` - savings goals, financial targets
- `net_worth` - net worth, assets, liabilities

**Mental/Wellness:**
- `mood` - mood, feelings, emotions, anxiety
- `sleep` - sleep, rest, bedtime, insomnia

Also fixed gap detector to check unsupported query patterns (comparison, correlation, prediction) BEFORE determining no gap exists.

**Files modified:**
- `assistant/intent_detector.py` - Expanded from ~120 to ~500 lines with comprehensive keywords
- `assistant/gap_detector.py` - Reordered logic to check unsupported patterns first
- `assistant/tests/test_intent_detector.py` - Updated tests for new data type structure

---

### Add Clarifying Question for Ambiguous 'sugar' Queries

**Problem:**
When users asked "what's my average sugar the past 7 days", the word "sugar" is ambiguous - it could mean blood sugar (glucose) or dietary sugar (food). Rather than guessing, the assistant should ask for clarification.

**Solution:**
Implemented an ambiguous keyword detection system that:
1. Detects when "sugar" or "sugars" is used without clear context
2. Checks for contextual clues (e.g., "blood sugar" → glucose, "ate sugar" → food)
3. When truly ambiguous, asks a clarifying question before proceeding

The assistant now responds to "what's my average sugar" with:
> When you mention 'sugar', are you referring to:
> • Your **blood sugar** (glucose readings), or
> • The **sugar in your food** (dietary intake)?

Also updated `DATA_TYPES_WITH_METHODS` to include 'glucose', 'faith', 'goals'.

**Files modified:**
- `assistant/intent_detector.py` - Added `AMBIGUOUS_KEYWORDS` dict and detection logic
- `assistant/views.py` - Added handling for ambiguous keywords before data query
- `assistant/gap_detector.py` - Updated DATA_TYPES_WITH_METHODS list

---

### Fix Finance Migration 0012 for SQLite Compatibility

**Problem:**
Migration `apps/finance/migrations/0012_budget_status.py` used PostgreSQL-specific `information_schema.columns` query which doesn't exist in SQLite. This caused tests to fail during database setup.

**Solution:**
Updated `column_exists()` function to detect database vendor and use appropriate query:
- PostgreSQL: Uses `information_schema.columns` with `table_schema = 'public'`
- SQLite: Uses `PRAGMA table_info()` to check column existence

Also updated index creation to handle SQLite's lack of `IF NOT EXISTS` for indexes.

**Files modified:**
- `apps/finance/migrations/0012_budget_status.py` - Added SQLite support to `column_exists()` and `add_status_if_missing()` functions

---

### Track User Who Triggered Gap Detection in Approval Emails

**Problem:**
When the WLJ Assistant sent approval emails for gap-detected tasks (like "Evaluate new data type: 'numbers'"), the email did not show which user triggered the gap or what they typed. This made it impossible to trace the source of the improvement request.

**Solution:**
Added user tracking throughout the gap detection flow:
1. Added `triggered_by_user` ForeignKey field to `ImprovementTaskModel`
2. Updated `_handle_gap_detection()` to accept and store the triggering user
3. Extended `TaskInfo` dataclass with `triggered_by_email`, `triggered_by_name`, and `original_query` fields
4. Updated `_send_approval_notification()` to pass user info to the notification service
5. Updated approval email templates (HTML and plain text) to display:
   - User name and email who triggered the gap
   - Original message that triggered the gap detection

**Files modified:**
- `assistant/models.py` - Added `triggered_by_user` field with FK to User, updated `to_dict()` to include user info
- `assistant/views.py` - Updated `_handle_gap_detection()` signature to accept user, set `triggered_by_user` on task model, updated `_send_approval_notification()` to pass user details to TaskInfo
- `assistant/notifications.py` - Extended `TaskInfo` dataclass with `triggered_by_email`, `triggered_by_name`, `original_query` fields
- `templates/assistant/emails/approval_required.html` - Added "Triggered By" section with user and message info
- `templates/assistant/emails/approval_required.txt` - Added plain text version of triggered by info

**Migration created:**
- `assistant/migrations/0004_add_triggered_by_user.py` - Adds `triggered_by_user` FK field

---

## 2026-01-09 Changes

### Fix Health Dropdown Menu Overflow on Laptops

**Problem:**
The Health mega dropdown menu was positioned with `left: 0`, causing it to overflow off the right edge of the screen on laptop-sized displays.

**Solution:**
Changed the `.nav-mega-menu` positioning to align from the right side instead:
- Added `left: auto` to override the default left positioning
- Added `right: 0` to anchor the menu to the right edge of the Health button

This makes the dropdown expand leftward, keeping all 5 columns (Vitals, Medicine, Fitness, Nutrition, Providers) visible within the viewport.

**Files modified:**
- `static/css/main.css` - Updated `.nav-mega-menu` positioning rules

---

### Update Context-Aware Help with New Module Names (Task #232)

**Changes:**
Updated context-aware help fixtures (help topics) to use new user-facing module names:
- "Life" → "Organize"
- "Purpose" → "Goals"

**Files modified:**
- `apps/help/fixtures/help_topics.json` - Updated multiple topics:
  - DASHBOARD_HOME: Updated profile/goals references
  - GENERAL: Updated navigation table and menu items
  - JOURNAL_HOME: Updated profile & goals references
  - SETTINGS_PREFERENCES: Updated module toggles list
  - LIFE_HOME: Renamed to "Organize: Your Daily Operating Layer"
  - PURPOSE_HOME: Renamed to "Goals: Your North Star"
  - ASSISTANT_HOME: Updated profile & goals references
  - GLUCOSE_DASHBOARD: Updated goals references
- `apps/help/fixtures/help_articles.json` - Updated Priority Ordering references

---

### Update Help Articles with New Module Names (Task #231)

**Changes:**
Updated help article fixtures to use new user-facing module names:
- "Life" → "Organize"
- "Purpose" → "Goals"

**Files modified:**
- `apps/help/fixtures/help_articles.json` - Updated 5 articles:
  - Article 1: Welcome (module list, feature table, getting started)
  - Article 6: Preferences (module toggles list)
  - Article 8: Hidden Features (sub-navigation reference)
  - Article 9: Goals Module (renamed from "Purpose Module")
  - Article 10: Organize Module (renamed from "Life Module")

---

### Fix Finance Budget Status Migration State

**Problem:**
Django was reporting "Your models in app(s): 'finance' have changes that are not yet reflected in a migration".
The Budget model inherits `status` from SoftDeleteModel (via UserOwnedModel), but migration 0012 used
RunPython/SQL to add the column directly. Django's migration state tracker didn't recognize this, so it
kept wanting to add the field again.

**Solution:**
Created migration `0013_sync_budget_status_state.py` using `SeparateDatabaseAndState` to sync Django's
ORM state without modifying the database. This tells Django the field exists without running any SQL.

**Files modified:**
- `apps/finance/migrations/0013_sync_budget_status_state.py` - New state-only migration

---

### Reduce Verbose Startup Logs

**Problem:**
Railway deployment logs showed excessive output on every startup (DataLoadConfig messages,
Twilio/Dexcom/reCAPTCHA configuration prints, workout sync details).

**Solution:**
- Updated management commands to respect verbosity levels (`-v 0` for silent)
- Removed all `print()` statements from `config/settings.py` for service configurations
- Updated `Procfile` to use `-v 0` for all startup commands

**Files modified:**
- `apps/health/management/commands/sync_workout_to_templates.py`
- `apps/core/management/commands/load_initial_data.py`
- `apps/life/management/commands/recalculate_task_priorities.py`
- `apps/admin_console/management/commands/load_project_from_json.py`
- `config/settings.py` - Removed print statements
- `Procfile` - Added `-v 0` to all commands

---

## 2026-01-08 Changes

### Replace 'Life' with 'Organize' and 'Purpose' with 'Goals'

**Task:** Replace every reference of Life and Purpose (Task #230, User Experience Phase 6)

**Problem:**
The module names were inconsistent across the app. Navigation showed "Organize" and "Goals"
but many other places still used the old names "Life" and "Purpose".

**Solution:**
Updated all user-facing display text across the application to use the new terminology.
The underlying app/URL names (life, purpose) remain unchanged.

**Files modified (60 files total):**
- `templates/dashboard/home.html` - Module cards
- `templates/users/preferences.html` - Module toggle labels
- `templates/life/home.html` and 27 other life templates - Breadcrumbs and titles
- `apps/purpose/templates/purpose/home.html` and 20 other purpose templates - Breadcrumbs and titles
- `apps/help/models.py` - MODULE_CHOICES display names
- `apps/help/migrations/0002_add_wlj_assistant_chat_models.py` - Migration choices
- `apps/users/views.py` - Onboarding wizard module definitions
- `apps/life/apps.py` - verbose_name for Django admin
- `apps/purpose/apps.py` - verbose_name for Django admin
- `apps/dashboard/tests/test_dashboard.py` - Test assertions

---

### Search History Suggestions

**Task:** Add Search History Suggestions (Task #229, User Experience Phase 6)

**Problem:**
Users frequently search for the same items (e.g., specific pages, functions) but had to retype
their searches each time. There was no way to quickly access recent searches.

**Solution:**
- Added `search_history` JSONField to UserPreferences model
- Created API endpoints for saving, retrieving, and clearing search history
- Updated command palette to show recent searches when opened or when input is empty
- Implemented localStorage backup for immediate display before API loads

**Features:**
- Recent searches appear at the top of command palette when opened
- Maximum of 10 searches stored (most recent first)
- Clicking a history item fills the search and filters results
- "Clear" button to remove all search history
- History items have clock icon to distinguish from regular commands
- Duplicates are removed (case-insensitive)
- localStorage provides immediate display, synced with server

**Files added:**
- `apps/users/migrations/0030_add_search_history.py` - Migration for search_history field

**Files modified:**
- `apps/users/models.py` - Added search_history JSONField to UserPreferences
- `apps/core/views.py` - Added SearchHistoryGetView, SearchHistorySaveView, SearchHistoryClearView
- `apps/core/urls.py` - Added /api/search-history/ endpoints
- `static/js/command-palette.js` - Added search history UI and localStorage integration

**API endpoints:**
- `GET /api/search-history/` - Get user's search history
- `POST /api/search-history/save/` - Save a search query to history
- `POST /api/search-history/clear/` - Clear all search history

---

### Undo Toast Notifications

**Task:** Add Undo Toast Notifications (Task #227, User Experience Phase 5)

**Problem:**
After deleting items, users had no way to quickly undo the action. The delete operation used
soft-delete, but users couldn't easily restore recently deleted items.

**Solution:**
- Created reusable undo toast notification component with 5-second countdown timer
- Implemented RestoreItemView API endpoint for restoring soft-deleted items
- Added UndoDeleteMixin for delete views to support AJAX responses
- Updated delete views in health app to return JSON for AJAX requests
- Integrated toast system with bulk delete actions

**Features:**
- Toast notification appears at bottom of screen after delete actions
- 5-second countdown timer with visual progress bar
- "Undo" button restores the deleted item instantly
- Smooth animations for showing/hiding toast
- Works with both single item and bulk deletes (single-item undo for bulk)
- Falls back to standard redirect for non-AJAX requests
- Security: whitelist of allowed models, ownership verification

**Files added:**
- `static/js/undo-toast.js` - Undo toast JavaScript component (~340 lines)

**Files modified:**
- `apps/core/views.py` - Added UndoDeleteMixin, RestoreItemView
- `apps/core/urls.py` - Added /api/restore/ endpoint
- `apps/health/views.py` - Updated all delete views to use UndoDeleteMixin
- `static/js/bulk-actions.js` - Integrated undo toast for single-item bulk deletes
- `templates/base.html` - Added undo-toast.js script include

**How to use:**
1. Delete views inherit from UndoDeleteMixin and define item_type, item_name, success_url
2. For AJAX requests, returns JSON with item_id and item_type
3. JavaScript shows toast; clicking Undo calls /api/restore/ to restore item
4. If timer expires, item stays soft-deleted (can be restored from archives later)

---

### Bulk Actions for List Views

**Task:** Add Bulk Actions to List Views (Task #226, User Experience Phase 4)

**Problem:**
Users had to delete or archive items one at a time. For lists with many items (e.g., health
tracking data, journal entries), this was tedious and time-consuming.

**Solution:**
- Added checkbox selection to list views
- Created floating bulk action toolbar that appears when items are selected
- Implemented confirmation modals for destructive actions (delete)
- Added API endpoints for bulk operations with proper authentication

**Features:**
- Select All checkbox in list headers
- Visual highlight on selected rows
- Indeterminate checkbox state when partially selected
- Animated removal of deleted/archived items
- Toast notifications for action feedback
- Support for both card-based (journal) and table-based (health) layouts

**Files added:**
- `static/js/bulk-actions.js` - Bulk actions JavaScript (~585 lines)

**Files modified:**
- `apps/journal/views.py` - Added BulkDeleteEntriesView, BulkArchiveEntriesView
- `apps/journal/urls.py` - Added bulk/delete/, bulk/archive/ routes
- `apps/health/views.py` - Added BulkDeleteWeightView, BulkDeleteHeartRateView, BulkDeleteBloodPressureView
- `apps/health/urls.py` - Added bulk/delete/ routes for weight, heart-rate, blood-pressure
- `templates/journal/entry_list.html` - Added checkboxes and bulk action data attributes
- `templates/health/weight_list.html` - Added checkboxes and bulk action data attributes
- `templates/base.html` - Include bulk-actions.js

---

### Command Palette (Cmd/Ctrl+K)

**Task:** Add Command Palette (Task #225, User Experience Phase 3)

**Problem:**
Users had to navigate through menus or remember multiple keyboard shortcuts to get to different
pages in the app. Power users wanted a faster way to navigate.

**Solution:**
- Created VS Code / Slack-style command palette accessible via Cmd+K (Mac) or Ctrl+K (Windows/Linux)
- Implemented fuzzy search across all navigable pages and quick actions
- Added keyboard navigation (arrow keys, Enter to select, Escape to close)
- Organized commands by category: Navigation, Journal, Faith, Health, Goals, Organize, Finance, Account, Quick Actions

**Features:**
- Fuzzy search matching on titles, categories, and keywords
- Mouse and keyboard navigation support
- Clean styling matching app design system
- Backdrop click or Escape to close
- Footer showing keyboard hints

**Files added:**
- `static/js/command-palette.js` - Main command palette implementation (~600 lines)

**Files modified:**
- `templates/base.html` - Include command palette script
- `static/js/keyboard-shortcuts.js` - Update shortcuts help modal to show Cmd+K

---

### Save & Add Another Button for Forms

**Task:** Add Save & Add Another to Forms (Task #224, User Experience Phase 2)

**Problem:**
Power users who want to create multiple entries (journal entries, weight logs, food entries, etc.)
had to navigate back to the list and then to the create form after each save.

**Solution:**
- Created `SaveAddAnotherMixin` in `apps/core/views.py` for reusable functionality
- Added "Save & Add Another" button to create forms (hidden on edit forms)
- When clicked, saves the entry and redirects back to a fresh form with a success toast

**Files modified:**
- `apps/core/views.py` - Added SaveAddAnotherMixin class
- `apps/journal/views.py` - EntryCreateView now uses the mixin
- `apps/health/views.py` - WeightCreateView, HeartRateCreateView, BloodPressureCreateView, FoodEntryCreateView
- `apps/purpose/views.py` - GoalCreateView
- `templates/journal/entry_form.html` - Added Save & Add Another button
- `templates/health/weight_form.html` - Added Save & Add Another button
- `templates/health/heartrate_form.html` - Added Save & Add Another button
- `templates/health/blood_pressure_form.html` - Added Save & Add Another button
- `templates/health/nutrition/food_entry_form.html` - Added Save & Add Another button
- `apps/purpose/templates/purpose/goal_form.html` - Added Save & Add Another button
- `templates/components/form_actions.html` - New reusable component (optional)

---

### Select All Checkbox for Task List Filters

**Task:** Project Task Page Filters (Task #222)

**Problem:**
The Project, Phase, and Status dropdown filters on the Task List page lacked a convenient way to
select or deselect all options at once. The Phase dropdown was also a single-select element.

**Solution:**
- Converted Phase dropdown from single-select to multi-select checkbox dropdown
- Added a "Select All" checkbox at the top of all three dropdowns (Project, Phase, Status)

**Behavior:**
- When "Select All" is checked, all options in that dropdown become checked
- When "Select All" is unchecked, all options become unchecked
- If any individual option is unchecked, "Select All" automatically unchecks
- If all individual options are checked manually, "Select All" automatically checks
- Default state: all options checked (Select All is checked)

**Files modified:**
- `templates/admin_console/admin_task_list.html`
  - Converted Phase dropdown from single-select to multi-select checkbox dropdown
  - Added `select-all-checkbox` class and HTML structure to all three dropdowns
  - Updated `initCheckboxDropdown()` JavaScript function to handle Select All logic
  - Added CSS for `.select-all-item` and `.dropdown-divider` styling
- `apps/admin_console/views.py`
  - Updated `AdminTaskListView.get_queryset()` to handle multi-select phase filtering
  - Changed `current_phase_filter` to `current_phase_filters` (list) in context

---

### Popup Delete Confirmations in Purpose Module

**Task:** Confirmation Popups (Task #221)

**Problem:**
Delete actions in the Purpose module used separate confirmation pages, requiring navigation
away from the current page. The user preferred consistent popup/dialog confirmations
that stay on the current page.

**Solution:**
Converted all Purpose module delete buttons from `<a>` links to inline `<form>` elements
with `data-confirm-delete` attribute. This triggers a JavaScript confirm dialog that stays
on the page instead of navigating to a separate confirmation page.

**Templates updated:**
- `goal_list.html`, `goal_detail.html`
- `habit_goal_list.html`, `habit_goal_detail.html`
- `direction_list.html`, `direction_detail.html`
- `intention_list.html`, `intention_detail.html`
- `reflection_list.html`, `reflection_detail.html`

**Pattern used:**
```html
<form method="post" action="{% url 'purpose:X_delete' obj.pk %}" class="inline-form" data-confirm-delete="Delete message">
    {% csrf_token %}
    <button type="submit" class="btn ...">Delete</button>
</form>
```

The `data-confirm-delete` attribute is already handled by `static/js/main.js` which shows
a browser confirm dialog before submitting the form.

**Tests:** All 101 purpose module tests pass.

---

### Standardized Button and Text Color Classes

**Task:** Check the entire app for inconsistencies (Task #220)

**Problem:**
Button styles were inconsistently defined across templates. Some templates had inline
`.btn-error` definitions that duplicated functionality and didn't use theme CSS variables.
Text color utilities like `.text-error` and `.text-danger` were defined inline in templates
instead of being centralized.

**Solution:**
Added standardized button and text color classes to `main.css`:

1. **Button variants added:**
   - `.btn-danger-text` - Ghost button with red text for destructive actions
   - `.btn-text` - Link-style button using accent color
   - `.btn-outline` - Transparent with border (alias for btn-secondary)
   - `.btn-error` - Red background button (alias for btn-danger)

2. **Text color utilities added:**
   - `.text-error` - Red text using `--color-error`
   - `.text-danger` - Alias for text-error
   - `.text-success` - Green text using `--color-success`
   - `.text-warning` - Yellow/orange text using `--color-warning`

3. **Removed duplicate inline styles from 18 templates:**
   - Life module: 10 confirm delete templates
   - Admin Console: 8 confirm delete templates

All styles now use CSS custom properties for theme compatibility.

**Text case audit:** All button text (Edit, Delete, Cancel, Save) uses consistent Title Case.

**Files modified:**
- `static/css/main.css` - Added standardized button and text color classes
- `templates/life/*_confirm_delete.html` - Removed inline .btn-error (10 files)
- `templates/admin_console/*_confirm_delete.html` - Removed inline .btn-error (8 files)

---

### Consistent CRUD Buttons in Purpose Module

**Task:** Ability to Delete Goals (Task #219)

**Problem:**
While viewing lists of goals, intentions, directions, and reflections in the Purpose module,
users needed full CRUD capability with consistent UI. Some list views had Edit buttons,
some had no action buttons at all, and Delete was often hidden deep in the detail pages.

**Solution:**
Added consistent Edit and Delete action buttons across all Purpose module list views:

1. **Life Goals List** (`goal_list.html`):
   - Added Delete button next to existing Edit button
   - Delete button styled with red text (`btn-danger-text`)

2. **Intentions List** (`intention_list.html`):
   - Added Delete button next to existing Edit button
   - Wrapped buttons in `.intention-actions` container for proper alignment

3. **Directions List** (`direction_list.html`):
   - Restructured from all-clickable row to row with separate link and actions
   - Added Edit and Delete buttons visible in each row
   - Maintains clickable behavior for the main content area

4. **Reflections List** (`reflection_list.html`):
   - Restructured from all-clickable row to row with separate link and actions
   - Added Edit and Delete buttons visible in each row

All delete buttons use consistent styling:
- Red text color via `.btn-danger-text` class
- Red background tint on hover
- Ghost button style for consistency with Edit buttons

**Files modified:**
- `apps/purpose/templates/purpose/goal_list.html`
- `apps/purpose/templates/purpose/intention_list.html`
- `apps/purpose/templates/purpose/direction_list.html`
- `apps/purpose/templates/purpose/reflection_list.html`

**Tests:** All 101 purpose module tests pass.

### Missing Migrations Created

**Context:** Fresh MacBook setup - discovered model changes without corresponding migrations.

**Migrations created:**

1. **`ai.0014_alter_aiinsight_insight_type_and_more`**
   - Alter field `insight_type` on AIInsight
   - Alter field `prompt_type` on AIPromptConfig

2. **`assistant.0003_rename_assistant_i_status_...`**
   - Rename indexes on ImprovementTaskModel
   - Add fields: `approval_token`, `approval_token_created_at`, `rejected_at`, `rejection_reason`, `rollback_reason`, `rolled_back_at`
   - Alter field `status` on ImprovementTaskModel

3. **`finance.0012_budget_status`**
   - Add field `status` to Budget model

**Files created:**
- `apps/ai/migrations/0014_alter_aiinsight_insight_type_and_more.py`
- `assistant/migrations/0003_rename_assistant_i_status_4b7e8c_idx_assistant_i_status_a738da_idx_and_more.py`
- `apps/finance/migrations/0012_budget_status.py`

---

## 2026-01-07 Changes

### Template Weight/Reps Storage

**Task:** Template Workout Pre-Populate (Task #218)

**Problem:**
The workout template form only stored exercise names and number of sets. There was no way to store
the default weight and reps for each set in the template, which prevented the pre-population
feature from working when creating a workout from a template.

**Solution:**
Updated the template form to allow storing weight/reps per set:

1. **Template Form** (`templates/health/fitness/template_form.html`):
   - Added per-set weight and reps inputs that expand/collapse based on set count
   - JavaScript dynamically adjusts set rows when changing set count
   - Preserves existing values when editing templates

2. **Template Views** (`apps/health/views.py`):
   - Updated `TemplateCreateView` to save `TemplateExerciseSet` records
   - Updated `TemplateUpdateView` to handle set defaults
   - Updated `TemplateDetailView` to prefetch set_defaults for display

3. **Template Detail** (`templates/health/fitness/template_detail.html`):
   - Now displays saved weight/reps for each set
   - Shows "no weights saved" for sets without data

**Files modified:**
- `apps/health/views.py` - TemplateCreateView, TemplateUpdateView, TemplateDetailView
- `templates/health/fitness/template_form.html` - Added set weight/reps inputs
- `templates/health/fitness/template_detail.html` - Display set details
- `apps/health/tests/test_fitness.py` - Added 10 new tests (6 sync tests + 4 form tests)

**Tests:** 74 fitness tests pass (including 10 new template tests)

---

## 2026-01-06 Changes

### Email Deliverability & DNS Configuration

**Session:** Admin login lockout due to email verification

**Problem:**
Admin was locked out because mandatory email verification was enabled but verification emails were not reaching Gmail.

**Solution:**
1. Added DNS records in Cloudflare for email authentication:
   - SPF record: `v=spf1 include:spf.privateemail.com ~all`
   - DKIM record: `default._domainkey` with Namecheap Private Email key
   - DMARC record: `v=DMARC1; p=none; rua=mailto:admin@wholelifejourney.com`
   - MX records: `mx1.privateemail.com` and `mx2.privateemail.com`
2. Updated Django Sites configuration from `example.com` to `wholelifejourney.com`

**Files modified:**
- `config/settings.py` - Temporarily set `ACCOUNT_EMAIL_VERIFICATION = "optional"` (later restored to mandatory)

---

### Admin Email Bypass for Email Verification

**Session:** Prevent future admin lockouts

**Problem:**
If email delivery fails again, admin could be locked out of the application.

**Solution:**
Added admin email bypass in the account adapter. Specified admin emails are always treated as verified, allowing login even when email verification is mandatory.

**Files modified:**
- `apps/users/adapters.py` - Added `ADMIN_BYPASS_EMAILS` set and `is_email_verified()` override
- `config/settings.py` - Restored `ACCOUNT_EMAIL_VERIFICATION = "mandatory"` with comment about admin bypass

---

### Styled Allauth Account Templates

**Session:** Fix ugly default password reset pages

**Problem:**
Password reset confirmation page was showing unstyled default Django allauth template.

**Solution:**
Created custom styled templates that match the application's design with logo, card layout, and consistent styling.

**Files created:**
- `templates/account/password_reset_done.html` - "Check your email" page
- `templates/account/password_reset_from_key.html` - Set new password form
- `templates/account/password_reset_from_key_done.html` - Password changed confirmation
- `templates/account/password_change.html` - Change password form (logged-in users)
- `templates/account/account_inactive.html` - Inactive account message
- `templates/account/signup_closed.html` - Registration closed message
- `templates/account/verified_email_required.html` - Email verification required

**Files modified:**
- `templates/account/base.html` - Updated copyright year to 2026

---

### Security: XSS Protection via json_script

**Session:** Security audit remediation

**Problem:**
Templates were using `{{ data|safe }}` pattern to embed JSON in JavaScript, which could be vulnerable to XSS if user content contained `</script>` tags.

**Solution:**
Replaced with Django's `json_script` template tag which safely escapes special characters.

**Files modified:**
- `templates/journal/book_view.html` - `entries_json`
- `templates/health/weight_list.html` - `chart_data`
- `templates/health/fitness/progress.html` - `progress_data`
- `templates/assistant/admin/analytics.html` - `pie_chart_data`, `line_chart_data`

---

### Security: Plaid Webhook Signature Verification

**Session:** Security audit remediation

**Problem:**
Plaid webhook endpoint was missing signature verification, allowing potential forged webhook attacks.

**Solution:**
Added `verify_plaid_webhook()` function that:
- Verifies the `Plaid-Verification` JWT header
- Checks request body SHA256 hash matches
- Validates timestamp is within 5 minutes
- Skips verification if PLAID_SECRET not configured (sandbox mode)

**Files modified:**
- `apps/finance/views.py` - Added webhook verification function and integrated into `plaid_webhook` view

---

### Security: Admin File Upload Validation

**Session:** Security audit remediation

**Problem:**
Logo and favicon uploads in admin console were stored without validating file content, allowing potential malicious file uploads.

**Solution:**
Added `validate_image_file()` function that:
- Checks file extension against whitelist
- Validates content-type header
- Verifies actual image content using PIL (for non-SVG)
- Enforces file size limits

**Files modified:**
- `apps/admin_console/views.py` - Added validation function and integrated into `SiteConfigView.post()`

---

### Fix workout delete button not working

**Session:** Delete button not work

**Objective:** Fix delete button on /health/fitness/workouts/ page that wasn't functioning.

**Root Cause:**
Two issues found:
1. Quote escaping issue in onclick handler - `default:'this workout'` used single quotes inside a single-quoted JS string
2. Missing button styles - the `.action-btn` CSS class didn't include `background: none; border: none; cursor: pointer;` needed for button elements

**Files modified:**
- `templates/health/fitness/workout_list.html` - Fixed quote escaping and added button styles to .action-btn CSS

---

### Workout Template Defaults - Auto-populate from last workout

**Session:** Workouts

**Objective:**
When a workout template is used and weights/sets are recorded, those values should populate the template so the next time the user uses that template, it reflects the last weights and sets performed. Users can overwrite values.

**Solution:**
1. Created `TemplateExerciseSet` model to store default weight/reps for each set in a template exercise
2. Added `from_template` FK on `WorkoutSession` to track which template a workout was created from
3. Updated `complete_workout_ajax` to sync completed workout data back to template defaults
4. Updated `WorkoutCreateView` and `start_workout_ajax` to set the template relationship
5. Updated workout form template to pre-populate input fields from template defaults using JavaScript
6. Created data migration to populate templates with historical workout data for existing users

**Files created:**
- `apps/health/migrations/0013_workout_template_defaults.py` - Schema migration for new model and FK
- `apps/health/migrations/0014_populate_template_defaults.py` - Data migration for historical workouts

**Files modified:**
- `apps/health/models.py` - Added `TemplateExerciseSet` model and `from_template` FK to `WorkoutSession`
- `apps/health/views.py` - Updated `WorkoutCreateView`, `start_workout_ajax`, `complete_workout_ajax`, added `_sync_workout_to_template`
- `templates/health/fitness/workout_form.html` - Added `templateDefaults` JS variable and `applyTemplateDefaults()` function

**How it works:**
1. User creates a workout from a template
2. `from_template` FK links the workout to the template
3. When workout is completed, `_sync_workout_to_template()` copies all weight/reps from `ExerciseSet` to `TemplateExerciseSet`
4. Next time user starts from that template, the form pre-populates with those default values
5. User can overwrite any values - new values will be saved on next completion

---

## 2026-01-05 Changes

### Add Codebase Metrics Report to Admin Console

**Session:** Codebase Metrics

**Objective:**
Create a comprehensive codebase metrics dashboard in the admin console to display project statistics, file counts, code architecture, and git activity patterns.

**Solution:**
Built a complete metrics service and admin view that gathers and displays:
- Project overview (age, size, apps)
- File statistics (Python, HTML, JS, CSS, Markdown, test files, migrations)
- Code architecture (models, views, routes, classes, functions, test methods)
- Git activity (commits, insertions, deletions, daily activity)
- Today's progress (commits, lines changed, coding window)
- Commit breakdown by type (features, fixes, AI-assisted, refactoring)
- Most productive days
- Commits by day of week
- Peak coding hours

**Files created:**
- `apps/admin_console/metrics_service.py` - Service module with MetricsService class
- `templates/admin_console/codebase_metrics.html` - Dashboard template
- `docs/wlj_codebase_metrics.md` - Feature documentation

**Files modified:**
- `apps/admin_console/views.py` - Added CodebaseMetricsView
- `apps/admin_console/urls.py` - Added route: `/admin-console/codebase-metrics/`
- `templates/admin_console/dashboard.html` - Added link to metrics page
- `apps/admin_console/tests/test_admin_console.py` - Added 20 test cases
- `config/settings.py` - Added django.contrib.humanize to INSTALLED_APPS

**URL:** `/admin-console/codebase-metrics/`

---

### Add Enter Key Submit for Chat with Assistant (Task #193)

**Session:** Chat with your assistant Enter Key

**Objective:**
Allow users to submit chat messages by pressing Enter key instead of clicking the send button.

**Solution:**
Added explicit `keydown` event listener on the chat input in the assistant dashboard:
- Pressing Enter (without Shift) now triggers form submission
- This matches the behavior of the floating chat widget which already had this functionality

**File modified:**
- `templates/ai/assistant_dashboard.html` (lines 806-814)

---

### Add Breadcrumbs to Finance Sub-Pages (Task #192)

**Session:** Breadcrumbs in Finance

**Objective:**
Add consistent breadcrumb navigation to all Finance module sub-pages for improved navigation.

**Solution:**
Added `<nav class="breadcrumb mb-4">` elements to 22 Finance templates following the existing project pattern:

- **Account pages (4):** list, detail, form, delete confirmation
- **Transaction pages (4):** list, detail, form, delete confirmation
- **Budget pages (3):** list, form, delete confirmation
- **Goal pages (4):** list, detail, form, delete confirmation
- **Import pages (3):** list, detail/upload, form
- **Other pages (4):** metrics, categories, transfer, bank connections

**Pattern used:** `Finance → Section → Current Page`

**Files modified:**
- `templates/finance/account_list.html`
- `templates/finance/account_detail.html`
- `templates/finance/account_form.html`
- `templates/finance/account_confirm_delete.html`
- `templates/finance/transaction_list.html`
- `templates/finance/transaction_detail.html`
- `templates/finance/transaction_form.html`
- `templates/finance/transaction_confirm_delete.html`
- `templates/finance/budget_list.html`
- `templates/finance/budget_form.html`
- `templates/finance/budget_confirm_delete.html`
- `templates/finance/goal_list.html`
- `templates/finance/goal_detail.html`
- `templates/finance/goal_form.html`
- `templates/finance/goal_confirm_delete.html`
- `templates/finance/import_list.html`
- `templates/finance/import_detail.html`
- `templates/finance/import_form.html`
- `templates/finance/metrics_dashboard.html`
- `templates/finance/category_list.html`
- `templates/finance/transfer_form.html`
- `templates/finance/bank_connection_list.html`

---

### Fix AI Assistant Not Seeing Blood Glucose Entries (Bug Fix)

**Session:** AI Assistant Blood Glucose Visibility Bug

**Problem:**
User reported that the AI assistant was not seeing blood glucose entries logged via the admin console, despite the entries existing in the database and appearing in the Health section of the app.

**Root Causes Identified:**
1. **Timezone Issue in Date Parser:** The `extract_date_from_message()` function in `assistant/date_parser.py` used naive `datetime.now()` instead of timezone-aware datetime. This caused queries like "show my glucose today" to potentially filter out today's entries when there was a timezone offset between the user's local time and UTC.

2. **Cache Not Invalidated on Bulk Create:** The admin console glucose import (and Clarity CSV import command) used `bulk_create()` which bypasses Django signals. The existing cache invalidation signals only fired on individual `post_save` operations, leaving bulk-imported data cached as stale.

**Solution:**

1. **Fixed timezone awareness in date_parser.py:**
   ```python
   # Before (naive datetime):
   now = reference_date or datetime.now()

   # After (timezone-aware):
   now = reference_date or timezone.localtime(timezone.now())
   ```

2. **Added explicit cache invalidation after bulk_create operations:**
   - `apps/admin_console/views.py` - Added cache invalidation after glucose import
   - `apps/health/management/commands/import_clarity_csv.py` - Added cache invalidation after CSV import

**Files Modified:**
- `assistant/date_parser.py` - Use timezone-aware datetime
- `apps/admin_console/views.py` - Invalidate cache after bulk glucose import
- `apps/health/management/commands/import_clarity_csv.py` - Invalidate cache after CSV import

**Technical Note:**
Django's `bulk_create()` does not trigger `post_save` signals for performance reasons. Any code using `bulk_create()` for health data must explicitly call `invalidate_user_data_cache(user_id, data_type)` after the operation to ensure the AI assistant sees the new data.

---

### Add Clarifying Question Flow for Data Visibility Issues (Enhancement)

**Session:** AI Assistant Self-Diagnosis for Missing Data

**Problem:**
When the AI assistant couldn't find user data (e.g., blood glucose), it would either treat this as a "knowledge gap" (missing feature) or simply not mention it. There was no way for the assistant to distinguish between:
1. User hasn't logged any data (expected)
2. User logged data but the assistant can't see it (bug)

**Solution:**
Added a clarifying question flow that asks users to verify if data exists in the app before escalating:

**New Flow:**
1. User asks about their data (e.g., "show my blood glucose")
2. Assistant queries database and finds nothing
3. Instead of treating as a gap, assistant asks: *"I'm not seeing any blood glucose data in my records. Can you see your most recent blood glucose entries in the app? If you can see them there but I can't, please let me know and I'll investigate."*
4. User responds:
   - **If user says "no":** Assistant responds with guidance on how to log data
   - **If user says "yes" (data exists but assistant can't see it):**
     1. Automatically invalidates cache for that data type
     2. Re-queries to check if cache was the issue
     3. If cache invalidation fixes it: "I found the issue and fixed it! Please ask again."
     4. If still broken: Sends email to admin@wholelifejourney.com with diagnostic details

**Files Modified:**
- `assistant/views.py`:
  - Added `DATA_NOT_FOUND_CLARIFYING_MESSAGE` and `DATA_VISIBILITY_ISSUE_MESSAGE` constants
  - Added `needs_clarification`, `clarifying_question`, `awaiting_data_type` to result dict
  - Modified empty data handling to ask clarifying question instead of treating as gap
  - Added `handle_data_visibility_confirmation()` function
  - Added `_send_data_visibility_alert()` function for admin email
  - Added `_get_friendly_data_type_name()` helper

- `assistant/__init__.py`:
  - Exported `handle_data_visibility_confirmation`

- `apps/ai/personal_assistant.py`:
  - Added `_handle_data_visibility_confirmation()` method to detect yes/no responses
  - Modified `send_message()` to check for pending data visibility confirmations
  - Stores confirmation state in conversation metadata

**User Experience:**
- Users now get asked for clarification instead of getting generic "no data" responses
- If they confirm data should exist, the system tries to self-heal (cache invalidation)
- If self-healing fails, admin is automatically notified via email
- Users receive clear feedback about what's happening and what actions are being taken

**Admin Experience:**
- Receives email alert when user confirms data visibility issue
- Email includes user details, data type, and diagnostic steps to take
- Alerts are only sent when cache invalidation doesn't resolve the issue

---

### Fix Date/Time Defaults on Health Log Forms (Task #191)

**Session:** Date Defaults for Health Metric Forms

**Objective:**
Make date/time fields automatically default to the current date/time when opening health metric log forms.

**Problem:**
The form's `__init__` method was correctly setting `self.initial["recorded_at"]` to the current datetime using `get_local_now_string(user)`, but the templates weren't accessing the initial value correctly for new entries.

**Solution:**
Updated templates to use a conditional that checks for existing value first (for edit mode), then falls back to the initial value from the form (for create mode):

```django
# Before (didn't show default for new entries):
value="{{ form.recorded_at.value|date:'Y-m-d\TH:i'|default:'' }}"

# After (correctly shows current date/time for new entries):
value="{% if form.recorded_at.value %}{{ form.recorded_at.value|date:'Y-m-d\TH:i' }}{% else %}{{ form.initial.recorded_at|default:'' }}{% endif %}"
```

**Files Modified:**
- `templates/health/blood_oxygen_form.html` - Fixed recorded_at default
- `templates/health/blood_pressure_form.html` - Fixed recorded_at default
- `templates/health/weight_form.html` - Fixed recorded_at default

**Note:** `templates/health/heartrate_form.html` already had the correct pattern.

---

### Create System Health Monitor (Task #175)

**Session:** System Health Monitoring Service Implementation

**Objective:**
Build monitoring service that tracks system health and pauses improvements if issues detected.
Part of Personal Assistant Growth project (Phase 8).

**New Files:**
1. `assistant/health_monitor.py` - Core health monitoring module:
   - **Health Thresholds:**
     - `ERROR_RATE_DEGRADED_THRESHOLD = 20%`
     - `ERROR_RATE_CRITICAL_THRESHOLD = 40%`
     - `ROLLBACK_RATE_DEGRADED_THRESHOLD = 15%`
     - `ROLLBACK_RATE_CRITICAL_THRESHOLD = 30%`
     - `CONSECUTIVE_FAILURE_THRESHOLD = 5`
   - **SystemStatus Enum:** HEALTHY, DEGRADED, CRITICAL
   - **HealthCheckResult Dataclass:** Status, reason, metrics
   - **RateMetrics Dataclass:** Calculated rate metrics
   - **HealthMonitor Class:**
     - `check_error_rate()` - Detect task failure rates
     - `check_rollback_rate()` - Detect high rollback rates
     - `check_assistant_response_rate()` - Detect consecutive failures & stuck tasks
     - `get_system_status()` - Combined health check returning HEALTHY/DEGRADED/CRITICAL
     - `handle_status()` - Take action based on status (pause, notify)
     - `run_periodic_check()` - Periodic health check for scheduler
     - `get_cached_status()` / `get_last_check_time()` - Query cached status
     - `get_full_status_report()` - Comprehensive report with recommendations
   - **Convenience Functions:**
     - `run_health_check()`, `get_system_status()`, `get_status_report()`

2. `templates/assistant/admin/health_check.html` - Health check dashboard:
   - Status banner (color-coded: green/yellow/red)
   - Pause/Resume system buttons
   - Metrics grid (error rate, rollback rate, consecutive failures)
   - Recommendations list
   - Threshold configuration reference table

3. `assistant/tests/test_health_monitor.py` - Comprehensive test suite:
   - TestHealthMonitorConstants (5 tests)
   - TestSystemStatusEnum (3 tests)
   - TestHealthCheckResult (2 tests)
   - TestRateMetrics (1 test)
   - TestHealthMonitorRateCalculation (2 tests)
   - TestHealthMonitorErrorRateCheck (3 tests)
   - TestHealthMonitorRollbackRateCheck (3 tests)
   - TestHealthMonitorResponseRateCheck (2 tests)
   - TestHealthMonitorGetSystemStatus (3 tests)
   - TestHealthMonitorHandleStatus (3 tests)
   - TestHealthMonitorPeriodicCheck (1 test)
   - TestHealthMonitorCachedStatus (3 tests)
   - TestHealthMonitorFullStatusReport (2 tests)
   - TestConvenienceFunctions (3 tests)

**Changes to Existing Files:**

1. `assistant/tasks.py`:
   - Import HealthMonitor and run_health_check
   - Added `run_health_check()` function for APScheduler periodic task

2. `assistant/admin_views.py`:
   - Import HealthMonitor and get_status_report
   - Added `system_health_check()` - Manual health check endpoint (GET)
   - Added `system_resume()` - Resume system endpoint (POST)
   - Added `system_pause()` - Pause system endpoint (POST)

3. `assistant/urls.py`:
   - Added `/assistant/admin/health/` - Health check dashboard
   - Added `/assistant/admin/health/resume/` - Resume system
   - Added `/assistant/admin/health/pause/` - Pause system

**Health Status Actions:**
| Status | Error Rate | Rollback Rate | Actions |
|--------|-----------|---------------|---------|
| HEALTHY | <20% | <15% | Normal operation |
| DEGRADED | 20-40% | 15-30% | Pause autonomous, notify admin |
| CRITICAL | >40% | >30% | Pause ALL, urgent admin notification |

**Additional Triggers:**
- 5+ consecutive failures = CRITICAL
- 3+ tasks stuck IN_PROGRESS for 1+ hour = CRITICAL
- 1-2 stuck tasks = DEGRADED

**Files Modified:**
- `assistant/tasks.py`
- `assistant/admin_views.py`
- `assistant/urls.py`
- `docs/wlj_claude_changelog.md`

**Files Created:**
- `assistant/health_monitor.py`
- `templates/assistant/admin/health_check.html`
- `assistant/tests/test_health_monitor.py`

---

### Add Learning Rate Limits and Safety Caps (Task #174)

**Session:** Safety Limits Implementation for Autonomous Execution

**Objective:**
Implement safety limits to prevent runaway self-modification by the autonomous executor system.
Part of Personal Assistant Growth project (Phase 8).

**New Files:**
1. `assistant/safety_limits.py` - Core safety limit module:
   - **Safety Constants:**
     - `MAX_AUTONOMOUS_PER_HOUR = 5`
     - `MAX_AUTONOMOUS_PER_DAY = 20`
     - `MAX_PENDING_TASKS = 50`
     - `MAX_FILE_MODIFICATIONS_PER_FILE_PER_DAY = 3`
     - `ERROR_RATE_THRESHOLD = 30` (percent)
     - `ERROR_RATE_SAMPLE_SIZE = 10`
   - **SafetyLimitOverride Model:** Admin-configurable overrides for all limits
   - **SafetyLimitService Class:**
     - `get_limit_value()` - Get effective limit with override support
     - `is_system_enabled()` - Check if system is paused
     - `pause_system()` / `resume_system()` - System pause controls
     - `check_rate_limits()` - Hourly/daily/pending task limits
     - `check_file_modification_limit()` - Per-file daily limits
     - `record_file_modification()` - Track file modifications
     - `is_system_healthy()` - Error rate monitoring (auto-pauses at 30%)
     - `check_all_limits()` - Combined safety check
     - `_notify_limit_reached()` - Admin notification on limit hit
   - **Convenience Functions:**
     - `check_rate_limits()`, `check_file_modification_limit()`, `is_system_healthy()`

2. `assistant/migrations/0002_safetylimitoverride.py` - Migration for SafetyLimitOverride model

3. `assistant/tests/test_safety_limits.py` - Comprehensive test suite:
   - TestSafetyLimitConstants (6 tests)
   - TestSafetyLimitOverrideModel (5 tests)
   - TestSafetyLimitServiceOverrides (4 tests)
   - TestSafetyLimitServiceSystemEnabled (4 tests)
   - TestSafetyLimitServiceRateLimits (4 tests)
   - TestSafetyLimitServiceFileModification (5 tests)
   - TestSafetyLimitServiceSystemHealth (4 tests)
   - TestSafetyLimitServiceCheckAll (4 tests)
   - TestConvenienceFunctions (3 tests)
   - TestRateLimitResultDataclass (2 tests)
   - TestSystemHealthResultDataclass (2 tests)
   - TestAutonomousExecutorIntegrationWithSafetyLimits (4 tests)

**Changes to Existing Files:**

1. `assistant/executor.py`:
   - Import SafetyLimitService and related functions
   - AutonomousExecutor now accepts `safety_limit_service` parameter
   - Updated docstring to document all safety limits
   - `execute_task()` now includes 9 safety steps:
     1. Check system health (error rate)
     2. Validate task is safe for autonomous execution
     3. Check rate limits (hourly, daily, pending)
     4. Check file modification limits
     5. Legacy rate limit check (backwards compatibility)
     6. Increment rate limit counter
     7. Execute using parent class logic
     8. Record file modification on success
     9. Notify admin

2. `assistant/admin.py`:
   - Import SafetyLimitOverride
   - Added SafetyLimitOverrideAdmin with:
     - List display: limit_name, value, is_active, valid_status, expires_at
     - Fieldsets: Override Settings, Expiration, Documentation, Timestamps
     - `valid_status()` method showing Valid/Expired/Inactive badge

**Safety Features:**
- **Rate Limiting:** Max 5/hour, 20/day autonomous executions
- **Queue Limiting:** Max 50 pending tasks before pausing
- **File Protection:** Max 3 modifications per file per day
- **Health Monitoring:** Auto-pauses if error rate exceeds 30% in last 10 tasks
- **Admin Override:** All limits can be adjusted via Django admin
- **Admin Notifications:** Alerts when any limit is reached
- **Pause/Resume:** Manual system pause capability

**Files Modified:**
- `assistant/executor.py`
- `assistant/admin.py`
- `docs/wlj_claude_changelog.md`

**Files Created:**
- `assistant/safety_limits.py`
- `assistant/migrations/0002_safetylimitoverride.py`
- `assistant/tests/test_safety_limits.py`

---

### Create Improvement Analytics Dashboard (Task #173)

**Session:** Improvement Analytics Dashboard Implementation

**Objective:**
Build simple analytics page showing system learning progress over time.
Part of Personal Assistant Growth project (Phase 8).

**New Files:**
1. `templates/assistant/admin/analytics.html` - Analytics dashboard template:
   - Key stats cards: Total tasks, Success rate, Avg completion time, Completed count
   - Pie chart: Tasks by status (using Chart.js doughnut chart)
   - Line chart: Tasks created over last 30 days
   - Gap types table: Most common gap types with percentages
   - Severity breakdown table: Task distribution by severity
   - Improved files table: Most frequently modified files
   - Recent activity feed: Last 10 task updates with status colors

**View Implementation (admin_views.py):**
- Added `improvement_analytics` view requiring staff login
- Calculates metrics:
  - Task counts by status for pie chart
  - Tasks over time for line chart (last 30 days)
  - Success rate (completed / total attempted)
  - Average completion time (formatted as minutes/hours/days)
  - Most common gap types with percentages
  - Most frequently improved files (parsed from code_template)
  - Recent activity feed with action descriptions
  - Severity breakdown
- Added `_get_task_action_description()` helper function

**URL Route:**
- Added `/assistant/admin/analytics/` route

**Tests Added:**
- TestImprovementAnalytics: 11 tests for analytics view
- Fixed existing test bug (GAP_TYPE_WRONG_INTENT -> GAP_TYPE_UNSUPPORTED_QUERY_PATTERN)

**Files Modified:**
- `assistant/admin_views.py`
- `assistant/urls.py`
- `assistant/tests/test_admin_views.py`

**Files Created:**
- `templates/assistant/admin/analytics.html`

---

### Create Rollback Management Interface (Task #172)

**Session:** Rollback Management Interface Implementation

**Objective:**
Build admin interface to manually trigger rollbacks for any completed improvement.
Part of Personal Assistant Growth project (Phase 7).

**Model Changes:**
- Added `rolled_back_at` DateTimeField to ImprovementTaskModel
- Added `rollback_reason` TextField to ImprovementTaskModel
- Added `rollback()` model method for status transitions
- STATUS_ROLLED_BACK already existed in status choices

**View Changes (admin_views.py):**
- Updated `dashboard_rollback_task` view with:
  - Validation for COMPLETED status
  - Validation for git_commit_before field
  - Required rollback_reason in POST body
  - GitProtectionService.rollback_to_commit() call
  - Admin notification on rollback completion
  - ROLLED_BACK status (not FAILED)
- Fixed STATUS_COLORS to include all statuses
- Fixed SEVERITY_COLORS to match model choices

**Dashboard Template Changes:**
- Added rollback confirmation modal with reason input
- Rollback button only shows if git_commit_before exists
- Added rollback info display in task details (rolled_back_at, rollback_reason)
- Updated commit hash display to show both before/after

**Tests Added:**
- TestDashboardRollbackTask: 8 tests for rollback view
- TestRollbackMethod: 3 tests for model method

**Files Modified:**
- `assistant/models.py`
- `assistant/admin_views.py`
- `templates/assistant/admin/dashboard.html`
- `assistant/tests/test_admin_views.py`

---

### Create Background Task Queue for Execution (Task #171)

**Session:** Background Task Queue Implementation

**Objective:**
Implement async task processing so improvements do not block user requests.
Part of Personal Assistant Growth project (Phase 6).

**Implementation:**
Uses existing django-apscheduler infrastructure (same pattern as SMS scheduler).

**New Files:**
1. `assistant/tasks.py` - Background task functions:
   - `execute_improvement_task()` - Execute single task with timeout/retry
   - `process_approved_tasks()` - Periodic job for approved tasks
   - `process_autonomous_tasks()` - Periodic job for low-severity tasks
   - `monitor_stuck_tasks()` - Monitor tasks stuck > 30 minutes
   - `get_queue_status()` - Get current queue metrics

2. `assistant/management/commands/run_improvement_scheduler.py` - Management command:
   - Processes approved tasks every 5 minutes
   - Processes autonomous tasks every 5 minutes
   - Monitors stuck tasks every 10 minutes
   - Configurable intervals via command-line args

3. `assistant/tests/test_tasks.py` - Comprehensive unit tests

**Updated Files:**
- `assistant/notifications.py` - Added `notify_queue_status()` method

**Configuration:**
- Task timeout: 10 minutes (TASK_TIMEOUT_SECONDS = 600)
- Max retries: 2 (MAX_RETRIES = 2)
- Stuck threshold: 30 minutes (STUCK_TASK_THRESHOLD_MINUTES = 30)
- Default process interval: 5 minutes
- Default monitor interval: 10 minutes

**Usage:**
```bash
python manage.py run_improvement_scheduler
# Or with custom intervals:
python manage.py run_improvement_scheduler --process-interval=10 --monitor-interval=15
```

---

### Fix Circular Import Error (Hotfix)

**Session:** Production 502 Fix

**Issue:**
After Task #170, production server returned 502 error with `AppRegistryNotReady: Apps aren't loaded yet.`
The error occurred because `assistant/__init__.py` imports from `views.py`, which imported
`AutonomousExecutor`, `ImprovementTaskModel`, and notification services at module level.
This chain executed before Django apps were fully loaded.

**Fix:**
Changed `assistant/views.py` to use lazy imports inside the functions that need them:
- `ImprovementTaskModel` imported inside `_handle_gap_detection()`
- `AutonomousExecutor` imported inside `_queue_for_autonomous_execution()`
- `AdminNotificationService`, `TaskInfo` imported inside `_send_approval_notification()`

**Files Modified:**
- `assistant/views.py`

---

### Integrate Gap Detection into Assistant Flow (Task #170)

**Session:** Gap Detection Integration

**Objective:**
Wire gap detection into the main assistant processing to trigger improvement tasks.
Part of Personal Assistant Growth project (Phase 6).

**Changes:**
1. Updated `assistant/views.py`:
   - Added imports for gap_detector, task_generator, executor, models, notifications
   - Added `GAP_DETECTED_MESSAGE` constant for user-facing feedback
   - Updated `process_assistant_message()` to check for gaps at multiple points
   - Added new return keys: `gap_detected`, `gap_message`
   - Added `_handle_gap_detection()` helper function
   - Added `_queue_for_autonomous_execution()` for LOW severity routing
   - Added `_send_approval_notification()` for MEDIUM/HIGH severity routing
   - Comprehensive logging for all gap detection events

2. Updated `assistant/tests/test_views.py`:
   - Added `TestProcessAssistantMessageGapDetection` test class
   - Added `TestGapDetectionTaskRouting` test class
   - Added `TestGapDetectionLogging` test class
   - Added `TestGapDetectionUserMessage` test class

**Integration Flow:**
1. User sends query → intent detection
2. If no data returned → detect_knowledge_gap()
3. If gap detected → generate_improvement_task()
4. Save ImprovementTask to database
5. Route based on severity:
   - LOW: Check is_safe_for_autonomous(), queue or send to admin
   - MEDIUM/HIGH: Send approval notification to admin
6. Return gap_message to user

**Files Modified:**
- `assistant/views.py`
- `assistant/tests/test_views.py`

---

### Create Autonomous Executor for Low-Severity Tasks (Task #169)

**Session:** Autonomous Executor Implementation

**Objective:**
Build a variant executor that runs automatically for low-risk improvements without approval.
Part of Personal Assistant Growth project (Phase 5).

**Changes:**
1. Updated `assistant/executor.py`:
   - Added `AutonomousExecutor` class extending `ImprovementExecutor`
   - Added `ALLOWED_FILES` constant listing safe target files
   - Added `DANGEROUS_PATTERNS` constant with regex patterns to reject
   - Implemented `is_safe_for_autonomous()` method for safety validation
   - Implemented `_extract_target_file()` helper for parsing code templates
   - Implemented `_extract_code_section()` helper for parsing code templates
   - Implemented `_contains_dangerous_patterns()` for pattern matching
   - Implemented rate limiting via Django cache (max 5/hour)
   - Override `execute_task()` to add safety checks before execution
   - Always notifies admin after autonomous execution

2. Updated `assistant/tests/test_executor.py`:
   - Added `TestAutonomousExecutorSafetyValidation` - severity and file validation tests
   - Added `TestAutonomousExecutorDangerousPatterns` - pattern detection tests
   - Added `TestAutonomousExecutorRateLimiting` - rate limit tests with mocked cache
   - Added `TestAutonomousExecutorExecution` - full execution flow tests
   - Added `TestAutonomousExecutorHelperMethods` - helper method unit tests

**Safety Features:**
- Only executes LOW severity tasks
- Only modifies: intent_detector.py, data_service.py, context_builder.py
- Rejects: imports, class definitions, database calls, file I/O, eval/exec
- Rate limited to 5 executions per hour
- Admin notified after every autonomous execution

**Files Modified:**
- `assistant/executor.py`
- `assistant/tests/test_executor.py`

---

### Create Improvement Executor Service (Task #168)

**Session:** Create Improvement Executor Service

**Objective:**
Build the main orchestrator that executes improvement tasks through the full lifecycle with safety guarantees.
Part of Personal Assistant Growth project (Phase 5).

**Changes:**
1. Created `assistant/executor.py`:
   - Added `ExecutionResult` dataclass for execution outcomes
   - Added `ImprovementExecutor` class as main orchestrator
   - Implemented `execute_task()` as the main entry point
   - Step 1: Validates task is APPROVED or NEW for low-severity without approval
   - Step 2: Updates status to IN_PROGRESS
   - Step 3: Creates git snapshot via GitProtectionService
   - Step 4: Applies file modification via SafeFileModifier
   - Step 5: Updates status to TESTING
   - Step 6: Runs tests via MockTestRunner
   - Step 7a/7b: On success - commits changes, updates to COMPLETED, notifies admin
   - Step 8a/8b: On failure - rolls back, updates to ERROR, notifies admin
   - Full try/except wrapper with automatic rollback on exceptions
   - Comprehensive logging throughout execution lifecycle
   - Code template parsing (FILE/TYPE/PATTERN/CODE directives)

2. Created `assistant/tests/test_executor.py`:
   - `TestImprovementExecutorValidation` - task status validation tests
   - `TestImprovementExecutorExecution` - full lifecycle tests with mocks
   - `TestImprovementExecutorModification` - code template parsing tests
   - `TestImprovementExecutorNotifications` - notification handling tests
   - `TestImprovementExecutorIntegration` - TaskInfo creation tests

**Dependencies:**
- Uses ImprovementTaskModel from models.py
- Uses GitProtectionService from git_service.py
- Uses SafeFileModifier from file_modifier.py
- Uses MockTestRunner from test_runner.py
- Uses AdminNotificationService from notifications.py

---

### Create Admin Dashboard View (Task #167)

**Session:** Create Admin Dashboard View

**Objective:**
Build a web-based dashboard for admins to view and manage improvement tasks.
Part of Personal Assistant Growth project (Phase 4).

**Changes:**
1. Updated `assistant/admin_views.py`:
   - Added `STATUS_COLORS` and `SEVERITY_COLORS` mappings
   - Added `improvement_dashboard(request)` - staff-only dashboard view
   - Added `dashboard_approve_task(request, task_id)` - POST endpoint
   - Added `dashboard_reject_task(request, task_id)` - POST endpoint with reason
   - Added `dashboard_rollback_task(request, task_id)` - POST endpoint
   - All dashboard endpoints support both redirect and JSON responses

2. Updated `assistant/urls.py`:
   - Added `/assistant/admin/dashboard/` route
   - Added `/assistant/admin/dashboard/approve/<uuid:task_id>/`
   - Added `/assistant/admin/dashboard/reject/<uuid:task_id>/`
   - Added `/assistant/admin/dashboard/rollback/<uuid:task_id>/`

3. Created `templates/assistant/admin/dashboard.html`:
   - Task list table sorted by created_at descending
   - Status badges with color coding (New=blue, Pending=yellow, etc.)
   - Severity badges with color coding
   - Filter dropdowns for status and severity
   - Expandable task details rows with JavaScript toggle
   - Approve/reject buttons for pending_approval tasks
   - Rollback button for completed tasks
   - AJAX support for all actions with JSON responses
   - Modal dialog for rejection reason input
   - Responsive design with CSS-only styling

4. Updated `assistant/tests/test_admin_views.py`:
   - Added TestImprovementDashboard class with filter tests
   - Added TestDashboardApproveTask class
   - Added TestDashboardRejectTask class
   - Added TestDashboardRollbackTask class

**Files Created:**
- `templates/assistant/admin/dashboard.html` - Dashboard template

**Files Modified:**
- `assistant/admin_views.py` - Added dashboard view and action endpoints
- `assistant/urls.py` - Added dashboard routes
- `assistant/tests/test_admin_views.py` - Added dashboard tests

---

### Create Admin Approval Endpoint (Task #166)

**Session:** Create Admin Approval Endpoint

**Objective:**
Build secure API endpoint for admin to approve or reject improvement tasks.
Part of Personal Assistant Growth project (Phase 4).

**Changes:**
1. Updated `assistant/models.py`:
   - Added `STATUS_REJECTED` to status choices and transitions
   - Added `approval_token` field for secure one-time tokens
   - Added `approval_token_created_at` for 24-hour expiry tracking
   - Added `rejected_at` and `rejection_reason` fields
   - Added `generate_approval_token()` - creates URL-safe tokens
   - Added `is_token_valid(token)` - validates token and expiry
   - Added `clear_approval_token()` - clears token after use
   - Added `approve(user)` and `reject(reason)` helper methods

2. Created `assistant/admin_views.py`:
   - `approve_task(request, task_id, token)` - approves task via link
   - `reject_task(request, task_id, token)` - rejects task with reason
   - Token validation, expiry checking, status validation
   - Returns HTML confirmation/error pages

3. Created `assistant/urls.py`:
   - `/assistant/admin/approve/<uuid:task_id>/<token>/`
   - `/assistant/admin/reject/<uuid:task_id>/<token>/`

4. Created admin response templates:
   - `templates/assistant/admin/approval_success.html`
   - `templates/assistant/admin/approval_error.html`

5. Added comprehensive unit tests in `test_admin_views.py`:
   - Tests for approval/rejection flows
   - Tests for token validation and expiry
   - Tests for error handling

**Files Created:**
- `assistant/admin_views.py` - Admin approval views
- `assistant/urls.py` - URL configuration
- `assistant/tests/test_admin_views.py` - Unit tests
- `templates/assistant/admin/approval_success.html`
- `templates/assistant/admin/approval_error.html`

**Files Modified:**
- `assistant/models.py` - Added approval token fields and methods

---

### Create Admin Notification Service (Task #164)

**Session:** Create Admin Notification Service

**Objective:**
Build email notification service to keep admin informed of all improvement
task activities. Part of Personal Assistant Growth project (Phase 3).

**Changes:**
1. Created `assistant/notifications.py` with `AdminNotificationService` class:
   - `ADMIN_EMAIL` constant (admin@wholelifejourney.com)
   - `TaskInfo` dataclass for task details
   - `notify_task_created()` - notifies when new tasks are created
   - `notify_approval_required()` - notifies when tasks need admin approval
   - `notify_task_completed()` - notifies with summary and git diff
   - `notify_task_error()` - notifies with error details and rollback instructions
   - `notify_auto_improvement()` - notifies for low-severity auto-applied changes
   - `notify_daily_summary()` - sends daily activity summary

2. Created email templates in `templates/assistant/emails/`:
   - `base_email.html` - styled base template with WLJ branding
   - `task_created.html/.txt` - new task notification
   - `approval_required.html/.txt` - approval request with preview link (Phase 4)
   - `task_completed.html/.txt` - completion notification with git diff
   - `task_error.html/.txt` - error notification with rollback instructions
   - `auto_improvement.html/.txt` - auto-applied change notification
   - `daily_summary.html/.txt` - daily activity summary

3. Added comprehensive unit tests in `assistant/tests/test_notifications.py`:
   - Tests use Django mail.outbox for email inspection
   - Tests for all notification methods
   - Tests for email content, subjects, and recipients

**Files Created:**
- `assistant/notifications.py` - Admin notification service
- `assistant/tests/test_notifications.py` - Unit tests
- `templates/assistant/emails/*.html` - HTML email templates (7 files)
- `templates/assistant/emails/*.txt` - Plain text templates (6 files)

---

### Create Mock Test Runner (Task #163)

**Session:** Create Mock Test Runner

**Objective:**
Build a service that generates and executes mock tests to validate
improvements before deployment. Part of Personal Assistant Growth project.

**Changes:**
1. Created `assistant/test_runner.py` with `MockTestRunner` class:
   - `generate_test_file()` - creates test files in auto_generated/ directory
   - `run_single_test()` - executes tests using subprocess with pytest
   - `parse_test_results()` - extracts pass/fail status and error messages
   - `validate_intent_detection()` - tests new keywords are detected correctly
   - `validate_data_query()` - tests data query methods with mock data
   - `cleanup_test_files()` - removes auto-generated tests after run
   - `run_validation_suite()` - runs multiple validation tests in sequence

2. Added `TestResult` dataclass:
   - `passed` boolean, `output` string
   - `errors` list for error messages
   - `duration` float for execution time
   - `test_file` optional path to the test file

3. Created `assistant/tests/auto_generated/` directory for test file storage

4. Created comprehensive integration tests in `assistant/tests/test_test_runner.py`:
   - Tests for file generation, test execution, result parsing
   - Tests for intent detection and data query validation
   - Tests for cleanup and validation suite functionality

**Files Created:**
- `assistant/test_runner.py` - Mock test runner implementation
- `assistant/tests/auto_generated/__init__.py` - Auto-generated tests directory
- `assistant/tests/test_test_runner.py` - Integration tests for test runner

---

### Create Safe File Modifier Service (Task #162)

**Session:** Create Safe File Modifier Service

**Objective:**
Build a service that safely modifies Python files with validation and syntax
checking. Part of Personal Assistant Growth project.

**Changes:**
1. Created `assistant/file_modifier.py` with `SafeFileModifier` class:
   - `ALLOWED_FILES` list: intent_detector.py, data_service.py, context_builder.py, date_parser.py
   - `FORBIDDEN_FILES` list: settings.py, models.py, views.py, urls.py, manage.py
   - `validate_target_file()` - ensures file is in allowed list and exists
   - `backup_file()` - creates .backup copy before modification
   - `restore_from_backup()` - reverts file to backup state
   - `validate_python_syntax()` - uses ast.parse() to validate Python code
   - `insert_code_after_pattern()` - regex-based code insertion
   - `append_to_dict()` - adds entries to dictionary definitions
   - `append_method_to_class()` - adds methods to existing classes using AST
   - `apply_modification()` - main entry point with full validation pipeline

2. Added `ModificationType` enum: APPEND, INSERT_AFTER, REPLACE

3. Added `ModificationResult` dataclass for standardized results:
   - `success` boolean, `message` string
   - Optional `backup_path` and `modified_content` fields

4. Safety features:
   - Automatic backup before any modification
   - Syntax validation before writing changes
   - Automatic rollback on validation failure
   - Restricted file access (allowed/forbidden lists)

5. Created comprehensive unit tests in `assistant/tests/test_file_modifier.py`:
   - Uses tempfile for safe testing with real files
   - Tests validation, backup/restore, syntax checking
   - Tests all modification types and edge cases

**Files Created:**
- `assistant/file_modifier.py` - Safe file modifier implementation
- `assistant/tests/test_file_modifier.py` - Unit tests with temporary files

---

### Create Git Protection Service (Task #161)

**Session:** Create Git Protection Service

**Objective:**
Build a service that creates Git commits before and after changes, enabling
rollback if improvements fail. Part of Personal Assistant Growth project.

**Changes:**
1. Created `assistant/git_service.py` with `GitProtectionService` class:
   - `create_snapshot(task_id)` - captures current commit state before changes
   - `commit_changes(task_id, task_title, files)` - commits improvements with
     standardized message format: `AUTO-IMPROVE {task_title} (Task {task_id})`
   - `rollback_to_commit(commit_hash)` - reverts to a specific commit via
     `git reset --hard`
   - `get_current_commit_hash()` - gets current HEAD reference
   - `get_file_diff(file_path, staged)` - shows unstaged or staged changes
   - `get_commit_diff(commit_hash)` - shows what changed in a specific commit
   - `has_uncommitted_changes()` - safety check before operations

2. Added `GitResult` dataclass for standardized operation results:
   - `success` boolean, `message` string
   - Optional `commit_hash` and `output` fields

3. Safety feature: Refuses to operate if working directory has uncommitted
   changes, preventing accidental commits of unrelated work.

4. Created comprehensive unit tests in `assistant/tests/test_git_service.py`:
   - 20 test methods covering all functionality
   - Uses `unittest.mock` to mock Git commands
   - Tests success cases, failure cases, and edge cases

**Files Created:**
- `assistant/git_service.py` - Git protection service implementation
- `assistant/tests/test_git_service.py` - Unit tests with mock Git commands

---

### Add Soft Delete Consistency Documentation (Task #190)

**Session:** Soft Delete Documentation

**Purpose:**
Document the soft delete handling pattern for the Personal Data Query System to ensure
future data methods follow the same approach and prevent bugs from incorrect filtering.

**Changes:**
1. Added section 7 to `docs/wlj_claude_troubleshoot.md`:
   - Explains SoftDeleteManager automatically filters deleted records
   - Documents that `is_deleted` is a @property, not a database field
   - Shows correct vs incorrect filtering patterns with code examples
   - References `apps/core/models.py` for implementation details

2. Added Soft Delete Pattern documentation to `assistant/data_service.py`:
   - Inline comment block explaining the pattern
   - Correct/wrong usage examples
   - References to related documentation

3. Updated `CLAUDE.md`:
   - Added reference to troubleshoot.md #7 in Key Architecture
   - Added SoftDeleteManager filtering to common issues list

**Files Modified:**
- `docs/wlj_claude_troubleshoot.md` - New section 7 on SoftDeleteManager
- `assistant/data_service.py` - Soft delete pattern in module docstring
- `CLAUDE.md` - References to soft delete documentation

---

### Improve Cache Invalidation Strategy (Task #189)

**Session:** Cache Versioning Strategy

**Problem:**
The existing cache invalidation approach used `cache.delete()` to remove a single
cache key. However, cache keys include date filters, so different date-specific
queries would have different cache keys. This meant invalidation couldn't reliably
clear all cached data for a user/data_type.

**Solution:**
Implemented cache versioning strategy that works with any cache backend:

1. Store a version number per user/data_type combination
2. Include the version in all data cache keys
3. On invalidation, increment the version number

This makes all existing cache keys effectively stale, as new requests will use
the incremented version in their cache key.

**Changes:**
1. Added cache versioning functions:
   - `_get_version_key(user_id, data_type)` - generates version cache key
   - `_get_cache_version(user_id, data_type)` - retrieves current version

2. Updated `_generate_cache_key()`:
   - Now includes version in key format
   - Key format: `personal_data:{user_id}:{data_type}:v{version}:{date}`

3. Updated `invalidate_user_data_cache()`:
   - Now increments version instead of deleting specific keys
   - All existing cached data becomes stale automatically

4. Added `VERSION_CACHE_TTL = 86400` (24 hours) constant

5. Updated all cache-related tests:
   - `TestGenerateCacheKey` - updated for versioned key format
   - `TestInvalidateUserDataCache` - changed to test version increment
   - Added `TestCacheVersioning` - new test class
   - Updated cache miss tests to use pattern matching for versioned keys

**Files Modified:**
- `assistant/data_service.py` - Core cache versioning implementation
- `assistant/tests/test_data_service.py` - Updated tests for versioning

---

### Add Goals Data Service Method (Task #188)

**Session:** Add Goals Data Service Method

**Changes:**
1. Implemented `get_goals_data()` method in `PersonalDataService`:
   - Queries `LifeGoal` model from `apps.purpose.models`
   - Returns goal counts by status (active, paused, completed, released)
   - Returns goal counts by timeframe (year_1, year_2, year_3, ongoing)
   - Calculates completion rate percentage
   - Returns recently completed goals with titles and completion dates
   - Returns domain breakdown with goal counts per life domain
   - Supports `since_date` filtering and caching

2. Integrated goals with Personal Data Query System:
   - Added 'goals' to `query_map` in `query_by_intent()`
   - Added 'goals' to `supported_types` in `views.py`
   - Added `_format_goals_data()` to `context_builder.py`

3. Added cache invalidation for goals data:
   - Updated `invalidate_insights_on_goal_save/delete` signal handlers

4. Added comprehensive unit tests:
   - `TestGetGoalsDataNoEntries` (2 tests)
   - `TestGetGoalsDataWithEntries` (4 tests)
   - `TestGetGoalsDataCaching` (2 tests)
   - `TestQueryByIntentWithGoals` (1 test)
   - Context builder tests for goals formatting (5 tests)

**Files Modified:**
- `assistant/data_service.py` - Added `get_goals_data()` method and query_map entry
- `assistant/views.py` - Added 'goals' to supported_types
- `assistant/context_builder.py` - Added `_format_goals_data()` function
- `apps/ai/signals.py` - Added goals cache invalidation to existing handlers
- `assistant/tests/test_data_service.py` - Added goals data service tests
- `assistant/tests/test_context_builder.py` - Added goals context builder tests

---

### Add Faith Data Service Method (Task #187)

**Session:** Add Faith Data Service Method

**Changes:**
1. Implemented `get_faith_data()` method in `PersonalDataService`:
   - Queries `PrayerRequest` model for prayer request statistics (total, active, answered)
   - Queries `SavedVerse` model for saved Scripture verse counts
   - Queries `FaithMilestone` model for faith milestone counts
   - Queries `UserReadingPlan` model for reading plan progress (active, completed)
   - Supports `since_date` filtering and caching

2. Integrated faith with Personal Data Query System:
   - Added 'faith' to `query_map` in `query_by_intent()`
   - Added 'faith' to `supported_types` in `views.py`
   - Added `_format_faith_data()` to `context_builder.py`

3. Added cache invalidation for faith data:
   - Updated `invalidate_insights_on_prayer_save/delete` signal handlers
   - Added signal handlers for `SavedVerse`, `FaithMilestone`, `UserReadingPlan`

4. Added comprehensive unit tests:
   - `TestGetFaithDataNoEntries` (1 test)
   - `TestGetFaithDataWithPrayerRequests` (3 tests)
   - `TestGetFaithDataWithSavedVerses` (1 test)
   - `TestGetFaithDataWithReadingPlans` (1 test)
   - `TestQueryByIntentWithFaith` (1 test)
   - `TestFaithCacheBehavior` (2 tests)
   - Context builder tests for faith formatting (7 tests)

**Files Modified:**
- `assistant/data_service.py` - Added `get_faith_data()` method and query_map entry
- `assistant/views.py` - Added 'faith' to supported_types
- `assistant/context_builder.py` - Added `_format_faith_data()` and faith section handling
- `apps/ai/signals.py` - Added faith cache invalidation for 4 models
- `assistant/tests/test_data_service.py` - Added faith unit tests (9 tests)
- `assistant/tests/test_context_builder.py` - Added faith formatting tests (7 tests)

**Purpose:** Enable assistant queries about faith activity ("How many prayers have been answered?") with support for prayer tracking, scripture collection, and reading plan progress.

---

### Add Glucose Data Service Method (Task #186)

**Session:** Add Glucose Data Service Method

**Changes:**
1. Implemented `get_glucose_data()` method in `PersonalDataService`:
   - Queries `GlucoseEntry` model for user's blood glucose data
   - Returns count, average, latest value, latest date, unit (mg/dL or mmol/L)
   - Includes recent entries with context and CGM trend information
   - Supports `since_date` filtering and caching

2. Integrated glucose with Personal Data Query System:
   - Added 'glucose' to `query_map` in `query_by_intent()`
   - Added 'glucose' to `supported_types` in `views.py`
   - Added `_format_glucose_data()` to `context_builder.py`

3. Added cache invalidation for glucose data:
   - Updated `invalidate_insights_on_glucose_save` signal handler
   - Updated `invalidate_insights_on_glucose_delete` signal handler

4. Added comprehensive unit tests:
   - `TestGetGlucoseDataNoEntries` (2 tests)
   - `TestGetGlucoseDataWithEntries` (5 tests)
   - `TestGetGlucoseDataFiltering` (1 test)
   - `TestGetGlucoseDataEntries` (2 tests)
   - `TestQueryByIntentWithGlucose` (2 tests)
   - `TestGlucoseCacheBehavior` (2 tests)
   - Context builder tests for glucose formatting

**Files Modified:**
- `assistant/data_service.py` - Added `get_glucose_data()` method and query_map entry
- `assistant/views.py` - Added 'glucose' to supported_types
- `assistant/context_builder.py` - Added `_format_glucose_data()` and glucose section handling
- `apps/ai/signals.py` - Added glucose cache invalidation to existing signal handlers
- `assistant/tests/test_data_service.py` - Added glucose unit tests (14 tests)
- `assistant/tests/test_context_builder.py` - Added glucose formatting tests (7 tests)

**Purpose:** Enable assistant queries about blood glucose data ("What was my average glucose this week?") with support for Dexcom CGM integration.

---

### Add Cache Integration Tests (Task #185)

**Session:** Add Cache Integration Tests

**Changes:**
1. Created `assistant/tests/test_cache_integration.py` with 30 Django TestCase tests:
   - `CacheKeyGenerationTest` (5 tests): Cache key format, uniqueness per user/type/date
   - `CacheHitMissTest` (6 tests): First query cache miss, second query cache hit, data structure
   - `CacheInvalidationTest` (4 tests): Manual invalidation via `invalidate_user_data_cache()`
   - `SignalCacheInvalidationTest` (10 tests): Signal-based invalidation for all models (WeightEntry, JournalEntry, MedicineLog, FoodEntry)
   - `CacheTTLTest` (3 tests): TTL constant verification, cache.set TTL parameter
   - `QueryByIntentCacheTest` (2 tests): Multi-type caching, partial cache hit behavior

**Files Created:**
- `assistant/tests/test_cache_integration.py` - 30 cache integration tests (676 lines)

**Purpose:** Verify caching behavior of the Personal Data Query System with real Django cache framework (locmem cache) using `override_settings`, ensuring cache hits, misses, and signal-based invalidation work correctly.

---

### Add Integration Tests for Personal Data Query System (Task #184)

**Session:** Add Integration Tests for Personal Data Query System

**Changes:**
1. Created `assistant/tests/test_integration.py` with 49 comprehensive tests:
   - `WeightDataIntegrationTest` (7 tests): Weight entry retrieval, averages, date filtering
   - `JournalDataIntegrationTest` (5 tests): Journal entry counts, latest dates, soft delete
   - `MedicationDataIntegrationTest` (6 tests): Medicine logs, consistency calculations
   - `FoodDataIntegrationTest` (5 tests): Food entries, calorie sums, daily averages
   - `MoodDataIntegrationTest` (6 tests): Mood distribution, most common mood, soft delete
   - `SoftDeleteBehaviorIntegrationTest` (3 tests): Soft delete exclusion, archive inclusion
   - `QueryByIntentIntegrationTest` (5 tests): Multi-type queries, unknown type handling
   - `ProcessAssistantMessageIntegrationTest` (8 tests): End-to-end pipeline tests
   - `DateFilteringIntegrationTest` (4 tests): Date filtering for all data types

**Files Created:**
- `assistant/tests/test_integration.py` - 49 integration tests (966 lines)

**Purpose:** Verify the Personal Data Query System works correctly with real Django ORM operations, ensuring soft delete behavior, date filtering, and the full message processing pipeline function as expected.

---

### Integrate Personal Data Query with Help Assistant Chat (Task #183)

**Session:** Integrate Personal Data Query with Help Assistant Chat

**Changes:**
1. Updated `apps/help/services.py`:
   - Added import for `process_assistant_message` from assistant module
   - Added `PERSONAL_DATA_SYSTEM_PROMPT` constant for AI context
   - Added `_try_personal_data_response()` to detect and handle personal data queries
   - Added `_generate_ai_response()` to call OpenAI with personal context
   - Added `_get_coaching_style_instructions()` for style-aware prompts
   - Modified `generate_response()` to check for personal queries first
   - Falls back to help article search if not personal query or AI fails
2. Added comprehensive unit tests in `apps/help/tests/test_services.py`:
   - Test personal query with data generates AI response
   - Test personal query without data returns helpful message
   - Test non-personal queries fall back to article search
   - Test AI failure falls back gracefully
   - Test exception handling
   - Test coaching style instructions

**Files Modified:**
- `apps/help/services.py` - Added personal data query integration
- `apps/help/tests/test_services.py` - Added 10 new test cases

**Purpose:** Connect the assistant module's `process_assistant_message()` to the Help Assistant chat, enabling responses to personal data queries like "What was my weight last week?" with actual user data context.

---

### Integrate Personal Data Query with AI Personal Assistant (Task #182)

**Session:** Integrate Personal Data Query with AI Personal Assistant

**Changes:**
1. Modified `apps/ai/personal_assistant.py`:
   - Added import for `process_assistant_message` from `assistant.views`
   - Updated `_generate_response()` to integrate personal data query detection
   - When users ask about their data (weight, journal, medication, food, mood), the system now automatically injects relevant personal data context into the AI prompt
   - Updated file header timestamp

2. Added unit tests in `apps/ai/tests/test_personal_assistant.py`:
   - Added `PersonalDataQueryIntegrationTests` class with 5 test methods:
     - `test_personal_data_context_injected_for_weight_query` - Verifies weight queries get context
     - `test_no_context_injection_for_non_personal_query` - Verifies non-personal queries work normally
     - `test_personal_query_without_data_uses_base_prompt` - Handles queries when no data exists
     - `test_multiple_data_types_in_query` - Tests compound queries (e.g., mood + journal)
     - `test_existing_features_preserved` - Ensures coaching style features still work

**Files Modified:**
- `apps/ai/personal_assistant.py` - Added personal data query integration
- `apps/ai/tests/test_personal_assistant.py` - Added 5 integration tests

**Purpose:** Enable the AI Personal Assistant to automatically detect when users ask about their personal data and inject that data into the AI context, providing more personalized and data-aware responses.

---

### Add Missing Exports to Assistant Module (Task #181)

**Session:** Add Missing Exports to Assistant Module __init__.py

**Changes:**
1. Updated `assistant/__init__.py`:
   - Added import for `process_assistant_message` from `.views`
   - Added import for `build_personal_context` from `.context_builder`
   - Added import for `invalidate_user_data_cache` from `.data_service`
   - Added all three to `__all__` list

**Files Modified:**
- `assistant/__init__.py` - Added imports and exports

**Purpose:** Make `process_assistant_message`, `build_personal_context`, and `invalidate_user_data_cache` part of the assistant module's public API, enabling easier imports for Phase 2 integration tasks.

---

### Fix is_deleted Filter Bug in Mood Data Query (Task #180)

**Session:** Fix is_deleted Filter Bug in Mood Data Query

**Changes:**
1. Fixed `get_mood_data()` in `assistant/data_service.py`:
   - Removed broken `is_deleted=False` filter (is_deleted is a property, not a field)
   - SoftDeleteManager already excludes deleted records automatically
   - Updated comment to explain SoftDeleteManager handles exclusion
2. Updated corresponding test in `assistant/tests/test_data_service.py`:
   - Changed assertion to verify filter is called with only `user` parameter

**Files Modified:**
- `assistant/data_service.py` - Fixed filter in get_mood_data()
- `assistant/tests/test_data_service.py` - Updated test assertion

**Purpose:** Fix bug where filtering by `is_deleted=False` would fail because `is_deleted` is a property, not a database field. The SoftDeleteManager already handles exclusion of deleted records.

---

### Fix is_deleted Filter Bug in Medication Data Query (Task #179)

**Session:** Fix is_deleted Filter Bug in Medication Data Query

**Changes:**
1. Fixed `get_medication_data()` in `assistant/data_service.py`:
   - Removed broken `is_deleted=False` filter (is_deleted is a property, not a field)
   - SoftDeleteManager already excludes deleted records automatically
   - Updated comment to explain SoftDeleteManager handles exclusion
2. Updated corresponding test in `assistant/tests/test_data_service.py`:
   - Changed assertion to verify filter is called with only `user` parameter

**Files Modified:**
- `assistant/data_service.py` - Fixed filter in get_medication_data()
- `assistant/tests/test_data_service.py` - Updated test assertion

**Purpose:** Fix bug where filtering by `is_deleted=False` would fail because `is_deleted` is a property, not a database field. The SoftDeleteManager already handles exclusion of deleted records.

---

### Fix is_deleted Filter Bug in Journal Data Query (Task #178)

**Session:** Fix is_deleted Filter Bug in Journal Data Query

**Changes:**
1. Fixed `get_journal_data()` in `assistant/data_service.py`:
   - Removed broken `is_deleted=False` filter (is_deleted is a property, not a field)
   - SoftDeleteManager already excludes deleted records automatically
   - Updated comment to explain SoftDeleteManager handles exclusion
2. Updated corresponding test in `assistant/tests/test_data_service.py`:
   - Changed assertion to verify filter is called with only `user` parameter

**Files Modified:**
- `assistant/data_service.py` - Fixed filter in get_journal_data()
- `assistant/tests/test_data_service.py` - Updated test assertion

**Purpose:** Fix bug where filtering by `is_deleted=False` would fail because `is_deleted` is a property, not a database field. The SoftDeleteManager already handles exclusion of deleted records.

---

### Add Task Storage Model (Task #160)

**Session:** Create Task Storage Model

**Changes:**
1. Created `assistant/models.py` with `ImprovementTaskModel`:
   - UUID primary key
   - Fields: title, description (JSON), gap_type, severity, original_query, suggested_fix, code_template, test_template, requires_approval
   - Status field with choices: NEW, PENDING_APPROVAL, APPROVED, IN_PROGRESS, TESTING, COMPLETED, ERROR, ROLLED_BACK
   - Timestamps: created_at, updated_at, approved_at, completed_at
   - User tracking: approved_by (FK to User)
   - Error tracking: error_message
   - Git tracking: git_commit_before, git_commit_after
   - `transition_status()` method with validation for allowed state transitions
   - `to_dict()` method for serialization
   - `create_from_improvement_task()` factory method
2. Created `assistant/apps.py` for Django app configuration
3. Created `assistant/admin.py` with color-coded badges for status/severity/gap_type
4. Created `assistant/migrations/0001_initial.py` migration
5. Added `assistant` to INSTALLED_APPS in config/settings.py

**Files Created:**
- `assistant/models.py` - ImprovementTaskModel with full lifecycle tracking
- `assistant/apps.py` - Django app configuration
- `assistant/admin.py` - Admin interface for manual oversight
- `assistant/migrations/0001_initial.py` - Initial database migration
- `assistant/migrations/__init__.py` - Package init

**Files Modified:**
- `config/settings.py` - Added 'assistant' to INSTALLED_APPS

**Purpose:** Create Django model to persist improvement tasks with full lifecycle tracking, enabling the self-improving assistant to store, manage, and track improvement tasks through their complete workflow.

---

### Add Improvement Task Generator (Task #159)

**Session:** Create Improvement Task Generator

**Changes:**
1. Created `assistant/task_generator.py` with:
   - `ImprovementTask` dataclass with fields: title, description, gap_type, severity, original_query, suggested_fix, code_template, test_requirements, requires_approval, created_at
   - `generate_improvement_task()` function that creates tasks based on gap type
   - `generate_code_template()` that produces code fix templates
   - `generate_test_template()` that produces test code templates
   - Approval logic: `requires_approval=False` for LOW severity, `True` for MEDIUM/HIGH
2. Gap-specific task generation:
   - MISSING_KEYWORDS: Tasks to add keywords to intent_detector.py
   - NO_DATA_METHOD: Tasks to add methods to data_service.py
   - UNSUPPORTED_QUERY_PATTERN: Tasks for date_parser.py or new patterns
   - UNKNOWN_DATA_TYPE: Tasks for model and full implementation
3. Created comprehensive unit tests in `assistant/tests/test_task_generator.py`
4. Updated `assistant/__init__.py` to export new functions and classes

**Files Created:**
- `assistant/task_generator.py` - Task generation module
- `assistant/tests/test_task_generator.py` - Unit tests for task generator

**Files Modified:**
- `assistant/__init__.py` - Added exports for task generator functions

**Purpose:** Build a service that creates structured improvement tasks in the project management system when gaps are detected. Each task includes code templates and test requirements for implementing fixes.

---

### Add Gap Detection Module (Task #158)

**Session:** Create Gap Detection Module

**Changes:**
1. Created `assistant/gap_detector.py` with functions to identify and categorize knowledge gaps:
   - `GapType` enum with values: `UNKNOWN_DATA_TYPE`, `MISSING_KEYWORDS`, `NO_DATA_METHOD`, `UNSUPPORTED_QUERY_PATTERN`
   - `GapSeverity` enum with values: `LOW` (keyword addition), `MEDIUM` (new query method), `HIGH` (application change)
   - `detect_knowledge_gap()` function that analyzes why a query couldn't be answered
   - `extract_potential_keywords()` to identify words that might be new data type indicators
   - `categorize_gap_severity()` returning severity level based on gap type
2. Created comprehensive unit tests in `assistant/tests/test_gap_detector.py`:
   - Tests for all enum values and constants
   - Tests for each gap type detection scenario
   - Tests for keyword extraction logic
   - Integration tests for realistic scenarios
3. Updated `assistant/__init__.py` to export new functions and classes

**Files Created:**
- `assistant/gap_detector.py` - Gap detection module
- `assistant/tests/test_gap_detector.py` - Unit tests for gap detector

**Files Modified:**
- `assistant/__init__.py` - Added exports for gap detector functions

**Purpose:** Build a system that recognizes when the assistant cannot answer a user's personal data question and captures the context for improvement. This enables automatic identification of:
- Missing keywords that should be added to intent detection
- Data types that need query methods in PersonalDataService
- Unsupported query patterns (comparisons, correlations, predictions)
- Unknown data types that may require new models

---

### Add Admin Email Test Functionality (Task #157)

**Session:** Test Admin Email Notification

**Changes:**
1. Created `apps/ai/tests/test_email.py` with unit tests for email configuration:
   - `EmailConfigurationTests`: Tests for email settings existence and validity
   - `EmailDeliveryTests`: Tests for `test_admin_email_delivery()` function using locmem backend
   - `SMTPConfigurationTests`: Tests for SMTP configuration validation
2. Created `apps/ai/management/commands/test_admin_email.py` management command:
   - Sends test email to admin@wholelifejourney.com by default
   - Subject: "WLJ Personal Assistant - Email Test"
   - Body includes timestamp, server name, and environment info
   - Supports `--dry-run` to show config without sending
   - Supports `--recipient` to override target email
   - Displays full SMTP configuration status
3. Verified email configuration in settings.py:
   - Production: SMTP via mail.privateemail.com:587 with TLS
   - Development: Console backend
   - DEFAULT_FROM_EMAIL: admin@wholelifejourney.com

**Files Created:**
- `apps/ai/tests/test_email.py` - Email delivery unit tests
- `apps/ai/management/__init__.py` - Package init
- `apps/ai/management/commands/__init__.py` - Commands package init
- `apps/ai/management/commands/test_admin_email.py` - Management command for email testing

**Usage:**
```bash
# Test in production via Railway console:
python manage.py test_admin_email

# Show configuration only (no email sent):
python manage.py test_admin_email --dry-run

# Send to different recipient:
python manage.py test_admin_email --recipient custom@example.com
```

**Notes:**
- In development (DEBUG=True), emails print to console
- For actual delivery, run on production with SMTP credentials configured
- Existing test command also available: `apps/core/management/commands/test_email.py`

---

### Add Query Result Caching (Task #155)

**Session:** Add Query Result Caching

**Changes:**
1. Added caching to PersonalDataService to reduce database queries:
   - `PERSONAL_DATA_CACHE_TTL` constant set to 300 seconds (5 minutes)
   - `_generate_cache_key()` function generates keys like `personal_data:{user_id}:{data_type}:{date}`
   - `invalidate_user_data_cache()` function clears cache for specific user/data type
2. Wrapped all 5 `get_*_data()` methods with cache check/set:
   - `get_weight_data()` - caches weight query results
   - `get_journal_data()` - caches journal query results
   - `get_medication_data()` - caches medication query results
   - `get_food_data()` - caches food query results
   - `get_mood_data()` - caches mood query results
3. Added cache invalidation signals to `apps/ai/signals.py`:
   - WeightEntry save/delete invalidates 'weight' cache
   - JournalEntry save/delete invalidates 'journal' and 'mood' cache (if entry has mood)
   - MedicineLog save/delete invalidates 'medication' cache
   - FoodEntry save/delete invalidates 'food' cache
4. Added 19 new unit tests for caching behavior:
   - TestGenerateCacheKey (5 tests) - key generation
   - TestInvalidateUserDataCache (2 tests) - cache invalidation
   - TestCacheHitBehavior (4 tests) - returns cached data
   - TestCacheMissBehavior (2 tests) - caches on miss
   - TestCacheTTL (1 test) - verifies TTL value
   - Updated all existing tests with CacheMockMixin

**Files Modified:**
- `assistant/data_service.py` - Added caching to data methods
- `apps/ai/signals.py` - Added cache invalidation signals
- `assistant/tests/test_data_service.py` - Added 19 caching tests (77 total)

---

### Add Intent Detection Tests and Refinement (Task #154)

**Session:** Add Intent Detection Tests and Refinement

**Changes:**
1. Expanded `PERSONAL_DATA_KEYWORDS` with additional keywords for all 11 data types:
   - Weight: bmi, body mass, weight trend, weight history, weight progress, etc.
   - Journal: log, logged, morning pages, evening reflection, journalling, etc.
   - Medication: rx, refill, pharmacy, tablet, capsule, treatment, regimen, etc.
   - Food: macros, micronutrients, kcal, brunch, supper, food intake, etc.
   - Mood: mental state, wellbeing, mental health, mindset, overwhelmed, joyful, etc.
   - Sleep: sleep quality, sleep schedule, sleep pattern, dream, nightmare, etc.
   - Exercise: fitness, swim, bike, yoga, stretching, lifting, marathon, etc.
   - Glucose: insulin, hyperglycemia, hypoglycemia, glucose monitor, etc.
   - Blood Pressure: pulse, heart rate, bpm, resting heart rate, etc.
   - Faith: quiet time, devotion, verse, church, sermon, blessing, etc.
   - Goals: milestone, resolution, challenge, commitment, routine, etc.
2. Added `META_QUESTION_KEYWORDS` list for detecting meta-questions about data existence
3. Added `COMPOUND_CONNECTORS` list for detecting multi-data-type queries
4. Updated `detect_personal_data_intent()` to return two new fields:
   - `is_meta_question`: True when asking about data existence (e.g., "have I logged...")
   - `is_compound_query`: True when asking about multiple data types together
5. Added 38 new unit tests covering:
   - Meta-question keyword validation (3 tests)
   - Compound connector validation (3 tests)
   - Meta-question detection (6 tests)
   - Compound query detection (4 tests)
   - New keyword coverage (14 tests)
   - Updated existing tests for new return fields

**Files Modified:**
- `assistant/intent_detector.py` - Expanded keywords, added meta-question and compound detection
- `assistant/tests/test_intent_detector.py` - Added 38 new tests (82 total)

---

### Update Context Builder for New Data Types (Task #153)

**Session:** Update Context Builder for New Data Types

**Changes:**
1. Added `_format_food_data()` helper function to format food entries
2. Formats total entries, total calories, average daily calories, and latest date
3. Added `_format_mood_data()` helper function to format mood data
4. Formats mood count, most common mood, mood distribution breakdown, and latest mood
5. Updated `build_personal_context()` to call formatters for 'food' and 'mood' data types
6. Added 13 new unit tests for food and mood formatting (28 total in context_builder)

**Files Modified:**
- `assistant/context_builder.py` - Added _format_food_data() and _format_mood_data() functions
- `assistant/tests/test_context_builder.py` - Added food and mood formatting tests (13 new tests)

---

### Add Mood Tracking Data Service Method (Task #152)

**Session:** Add Mood Tracking Data Service Method

**Changes:**
1. Added `get_mood_data()` method to `PersonalDataService` class
2. Queries `JournalEntry` model filtered by user, is_deleted=False, and mood is not empty
3. Filters by `entry_date__gte` when `since_date` is provided
4. Returns None if no entries with mood exist
5. Calculates `mood_distribution` using Count aggregate per mood level
6. Determines `most_common` mood from ordered distribution
7. Returns `latest_mood` and `latest_date` from most recent entry
8. Added `Count` import from django.db.models
9. Updated `query_map` in `query_by_intent()` to include 'mood'
10. Updated `supported_types` in `views.py` to include 'mood'
11. Added 12 new unit tests for mood data querying (63 total in data_service)

**Files Modified:**
- `assistant/data_service.py` - Added get_mood_data() method, Count import, and updated query_map
- `assistant/views.py` - Added 'mood' to supported_types list
- `assistant/tests/test_data_service.py` - Added mood data tests (12 new tests)

---

### Add Food Log Data Service Method (Task #151)

**Session:** Add Food Log Data Service Method

**Changes:**
1. Added `get_food_data()` method to `PersonalDataService` class
2. Queries `FoodEntry` model filtered by user
3. Filters by `logged_date__gte` when `since_date` is provided
4. Returns None if no entries exist
5. Calculates `total_entries`, `total_calories`, and `average_daily_calories`
6. Returns `latest_date` from most recent entry
7. Updated `query_map` in `query_by_intent()` to include 'food'
8. Updated `supported_types` in `views.py` to include 'food'
9. Added 12 new unit tests for food data querying (51 total in data_service)

**Files Modified:**
- `assistant/data_service.py` - Added get_food_data() method and updated query_map
- `assistant/views.py` - Added 'food' to supported_types list
- `assistant/tests/test_data_service.py` - Added food data tests (12 new tests)

---

### Integrate Components into Assistant View (Task #150)

**Session:** Integrate Components into Assistant View

**Changes:**
1. Created new `assistant/views.py` module as main entry point
2. Implemented `process_assistant_message()` function integrating all components
3. Imports and uses `detect_personal_data_intent()` from intent_detector
4. Calls `extract_date_from_message()` when date context is detected
5. Filters data_types to supported types ('weight', 'journal', 'medication')
6. Instantiates `PersonalDataService` with user and calls `query_by_intent()`
7. Calls `build_personal_context()` to format data for AI prompts
8. Appends personal context to base system prompt when data exists
9. Returns dict with system_prompt, is_personal_query, data_types, has_data
10. Added 13 unit tests covering various scenarios

**Files Created:**
- `assistant/views.py` - Main entry point with process_assistant_message() function
- `assistant/tests/test_views.py` - 13 unit tests for integration

---

### Context Builder (Task #149)

**Session:** Create Context Builder

**Changes:**
1. Created new `assistant/context_builder.py` module
2. Implemented `build_personal_context()` function that converts query results to natural language
3. Returns empty string if data_results is None or empty
4. Formats weight data with count, average, and most recent values
5. Formats journal data with count and latest date
6. Formats medication data with consistency percentage and totals
7. Adds closing instruction for AI to use the data
8. Added helper functions: `_format_weight_data()`, `_format_journal_data()`, `_format_medication_data()`, `_format_date()`
9. Added 15 unit tests for various data combinations

**Files Created:**
- `assistant/context_builder.py` - Context builder with build_personal_context() function
- `assistant/tests/test_context_builder.py` - 15 unit tests

---

### Personal Data Service - Master Query Method (Task #148)

**Session:** Create Master Query Method

**Changes:**
1. Added `query_by_intent()` method to `PersonalDataService` class
2. Creates `query_map` dictionary mapping data type strings to method references
3. Loops through `data_types` list and calls corresponding methods
4. Collects results into dict, skipping None responses
5. Returns results dict or None if empty
6. Supports all three data types: 'weight', 'journal', 'medication'
7. Silently skips unknown data types
8. Added 8 integration tests covering multiple data types (39 total tests)

**Files Modified:**
- `assistant/data_service.py` - Added query_by_intent() method with query_map dispatcher
- `assistant/tests/test_data_service.py` - Added query_by_intent tests (8 new tests)

---

### Personal Data Service - Medication Module (Task #147)

**Session:** Create Personal Data Service - Medication Module

**Changes:**
1. Added `get_medication_data()` method to `PersonalDataService` class
2. Queries `MedicineLog` model filtered by user and `is_deleted=False`
3. Filters by `since_date` when provided (using `scheduled_date__gte`)
4. Returns None if no entries exist
5. Calculates `days_logged` using unique dates from logs
6. Calculates `total_days` from since_date or first log to today
7. Calculates `consistency_percent` as (days_logged / total_days) * 100
8. Returns dict with type ('medication'), total_logs, days_logged, total_days, consistency_percent
9. Added 10 new unit tests for medication data querying (31 total)

**Files Modified:**
- `assistant/data_service.py` - Added get_medication_data() method with consistency calculation
- `assistant/tests/test_data_service.py` - Added medication data tests (10 new tests)

---

### Personal Data Service - Journal Module (Task #146)

**Session:** Create Personal Data Service - Journal Module

**Changes:**
1. Added `get_journal_data()` method to `PersonalDataService` class
2. Queries `JournalEntry` model filtered by user and `is_deleted=False`
3. Filters by `since_date` when provided (using `entry_date__gte`)
4. Returns None if no entries exist
5. Returns dict with type ('journal'), count, and latest_date
6. Added 8 new unit tests for journal data querying

**Files Modified:**
- `assistant/data_service.py` - Added get_journal_data() method
- `assistant/tests/test_data_service.py` - Added journal data tests (8 new tests, 21 total)

---

### Personal Data Service - Weight Module (Task #145)

**Session:** Create Personal Data Service - Weight Module

**Changes:**
1. Created `assistant/data_service.py` with `PersonalDataService` class
2. Implemented `get_weight_data()` method that queries `WeightEntry` model
3. Filters by `since_date` when provided
4. Returns None if no entries exist
5. Returns dict with type, count, average, latest, latest_date, unit, and entries
6. Decimal values converted to float for JSON serialization
7. Configurable limit parameter (default 10 entries)

**Files Created/Modified:**
- `assistant/data_service.py` - PersonalDataService class with get_weight_data()
- `assistant/tests/test_data_service.py` - 13 unit tests with mocked models
- `assistant/__init__.py` - Added export for PersonalDataService

---

### Date Parser Utility for Personal Data Query System (Task #144)

**Session:** Create Date Parser Utility

**Changes:**
1. Created `assistant/date_parser.py` with `extract_date_from_message()` function
2. Parses natural language dates into datetime objects
3. Supports relative dates: today, yesterday, this/last week/month/year
4. Handles "past N days/weeks/months" patterns
5. Phrase extraction: since, from, after, starting, beginning
6. Multiple date formats: "December 1st", "12/15", "2024-12-15"
7. Year defaulting when not specified (assumes past year if >7 days in future)
8. Uses python-dateutil for fallback parsing

**Files Created/Modified:**
- `assistant/date_parser.py` - Main date extraction logic
- `assistant/tests/test_date_parser.py` - 47 unit tests
- `assistant/__init__.py` - Added export for extract_date_from_message

---

### Intent Detector Module for Personal Data Query System (Task #143)

**Session:** Create Intent Detector Module

**Changes:**
1. Created new `assistant/` module at project root for Personal Data Query System
2. Implemented `detect_personal_data_intent()` function that classifies user queries
3. Returns dict with `is_personal_query`, `data_types`, and `has_date_context`
4. Supports 11 data types: weight, journal, medication, food, mood, sleep, exercise, glucose, blood_pressure, faith, goals
5. DATE_KEYWORDS list for time-related phrases (since, last, average, this week, etc.)
6. Word-boundary matching to prevent partial word matches
7. Case-insensitive detection with numeric date pattern support

**Files Created:**
- `assistant/__init__.py` - Module exports
- `assistant/intent_detector.py` - Main detection logic with PERSONAL_DATA_KEYWORDS and DATE_KEYWORDS
- `assistant/tests/__init__.py` - Test package
- `assistant/tests/test_intent_detector.py` - 52 unit tests covering various query patterns

---

### Glucose Chart Dynamic Period Selection

**Session:** Blood Glucose Chart Enhancement

**Changes:**
1. Chart now shows data for the selected period (Today, 7, 30, 60, 90 days)
2. Previously chart was static "Last 48 Hours" regardless of period selection
3. For periods > 7 days, data is aggregated to daily averages for readability
4. Chart title updates dynamically to match selected period
5. Tooltips show reading count for averaged data points
6. X-axis labels adapt based on period (time only vs date)
7. Point size adjusts based on data density

**Files Modified:**
- `apps/health/views.py` - Chart data now uses selected period with daily aggregation for longer periods
- `templates/health/glucose/dashboard.html` - Dynamic chart title and improved JS label formatting

---

### Habit Goals Success Rate Fix (Task #141)

**Session:** Habit Goals Success Rate

**Changes:**
1. Fixed Success Rate calculation to use elapsed days instead of total days
2. For a year-long habit goal on day 4 with 3 completions, now correctly shows 75%
3. Added `elapsed_days` property to HabitGoal model
4. Success Rate now refreshes dynamically when logging habits via AJAX
5. Added tests for elapsed_days calculation

**Files Modified:**
- `apps/purpose/models.py` - Added elapsed_days property, updated completion_rate
- `apps/purpose/views.py` - Return stats in AJAX log responses
- `apps/purpose/templates/purpose/habit_goal_detail.html` - Added updateStats() JS function
- `apps/purpose/tests/test_purpose_comprehensive.py` - Added test_elapsed_days_calculation

---

### Dashboard Respects Module Enabled Flags (Task #38)

**Session:** Dashboard Items

**Changes:**
1. Dashboard AI features now respect module enabled flags
2. Quick stats in header only show for enabled modules (journal_enabled, life_enabled, etc.)
3. Celebrations only appear for enabled modules:
   - Journal streak requires journal_enabled
   - Task completions require life_enabled
   - Weight trend requires health_enabled
   - Answered prayers require faith_enabled
   - Medicine/workout celebrations require health_enabled
   - Scan celebrations require ai_enabled
4. Nudges only appear for enabled modules:
   - Journal gap nudge requires journal_enabled
   - Overdue tasks require life_enabled
   - Health nudges (medicine, refill, workout) require health_enabled

**Files Modified:**
- `apps/dashboard/views.py` - Added prefs parameter to _check_for_celebrations(), added module checks
- `templates/dashboard/home.html` - Added journal_enabled/life_enabled checks to quick_stats

---

### Menu Order and Rename Assistant (Task #140)

**Session:** Menu Order

**Changes:**
1. Renamed "My Assistant" to "Assistant" in navigation menu
2. Moved Assistant menu item from end of menu to between Dashboard and Favorites

**Files Modified:**
- `templates/components/navigation.html` - Renamed and repositioned Assistant menu item

---

### Most Used Favorites Menu (Task #139)

**Session:** Favorites Menu / Most Recent → Most Used

**Changes:**
1. Changed Favorites menu "Most Recent" section to "Most Used"
2. Pages are now ranked by visit count instead of recency
3. Added `visit_count` field to PageView model to track page visits
4. Updated `record_view()` to increment visit count on each page view
5. Added `get_most_used_for_user()` method for retrieving pages by frequency
6. Updated context processor and API to return `most_used` instead of `recent`
7. Changed menu icon from clock to bar chart for most used items

**Files Modified:**
- `apps/core/models.py` - Added visit_count field and get_most_used_for_user()
- `apps/core/context_processors.py` - Updated favorites_context() for most_used
- `apps/core/views.py` - Updated FavoritesMenuDataView API response
- `templates/components/navigation.html` - Changed label and icon
- `apps/core/migrations/0037_pageview_visit_count.py` - New migration

---

### Multi-Command Support for AI Assistant

**Session:** AI Assistant Multi-Command

**Changes:**
1. Added support for multiple intents in a single message
2. Users can now say things like "update my oxygen to 95 and my weight to 350" and both will be logged
3. Modified IntentService to recognize multiple tool calls from OpenAI
4. Updated PersonalAssistant.send_message() to execute all detected intents
5. Added `actions_taken` array to API response for multiple actions
6. Updated system prompt to explicitly instruct OpenAI to call multiple functions when appropriate

**Files Modified:**
- `apps/ai/intent_service.py` - Added recognize_intents() method, updated system prompt
- `apps/ai/personal_assistant.py` - Updated send_message() for multi-intent processing
- `apps/ai/views.py` - Updated response format to include actions_taken array

---

### Phase 2 Intent Expansion - All Modules

**Session:** AI Intent Recognition Phase 2

**Changes:**
1. Expanded intent recognition to all modules with input forms
2. Added 21 new intents across Journal, Faith, Purpose, Life, and Fitness modules
3. Created action handlers for all new intents

**New Intents:**
- Journal: create_journal_entry, add_gratitude
- Faith: log_prayer, mark_prayer_answered, save_verse, add_faith_milestone
- Purpose: create_goal, update_goal_progress, set_intention, log_habit
- Life: create_task, complete_task, create_event, add_reminder
- Fitness: log_workout, log_exercise_set, log_cardio

**Files Added:**
- `apps/ai/intents/journal_intents.py` - Journal intent definitions
- `apps/ai/intents/faith_intents.py` - Faith intent definitions
- `apps/ai/intents/purpose_intents.py` - Purpose intent definitions
- `apps/ai/intents/life_intents.py` - Life intent definitions
- `apps/ai/intents/fitness_intents.py` - Fitness intent definitions

**Files Modified:**
- `apps/ai/intents/__init__.py` - Combined all intent tools
- `apps/ai/intent_service.py` - Added routing for all Phase 2 intents
- `apps/ai/action_handlers.py` - Added handlers for all Phase 2 intents

---

### Intent Recognition with Structured Data Extraction

**Session:** AI Assistant Intent Recognition

**Changes:**
1. Added intent recognition using OpenAI function calling (tools API)
2. Users can now say things like "log my heart rate at 60" and the assistant automatically logs it
3. Created IntentService for recognizing user intent and extracting structured data
4. Created ActionHandlers for executing recognized intents by creating model instances
5. Modified PersonalAssistant.send_message() to check for actionable intents first
6. Updated API response format to include action_taken when an action was executed
7. Added assistant_confirm_actions preference for users who want confirmation before logging

**Supported Intents (Phase 1 - Health Data):**
- log_heart_rate: "my heart rate is 60 bpm"
- log_blood_pressure: "BP is 120/80"
- log_weight: "I weigh 175 lbs"
- log_glucose: "blood sugar is 105"
- log_blood_oxygen: "oxygen is 98%"
- log_food: "I ate a banana"
- take_medicine: "took my metformin"
- start_fast: "starting a fast"
- end_fast: "ending my fast"

**Validation:**
- Unusual values trigger confirmation before logging (e.g., "200 BPM is quite high. Were you exercising?")
- Optional assistant_confirm_actions preference for always-confirm mode

**Files Added:**
- `apps/ai/intents/__init__.py` - Intent tool definitions package
- `apps/ai/intents/health_intents.py` - Health-related intent definitions
- `apps/ai/intents/medicine_intents.py` - Medicine intent definitions
- `apps/ai/intents/fasting_intents.py` - Fasting intent definitions
- `apps/ai/intent_service.py` - Intent recognition service
- `apps/ai/action_handlers.py` - Action execution handlers
- `apps/ai/tests/test_intent_service.py` - Comprehensive tests

**Files Modified:**
- `apps/ai/personal_assistant.py` - Integrated intent recognition into send_message()
- `apps/ai/views.py` - Updated AssistantChatView for new response format
- `apps/users/models.py` - Added assistant_confirm_actions preference

**Migration Required:** Yes (for assistant_confirm_actions field)

---

### Favorites Menu (Task #138)

**Session:** Favorites Menu

**Changes:**
1. Added new Favorites dropdown menu between Dashboard and Journal in navigation
2. Created FavoritePage model to store user's favorited pages (max 10)
3. Created PageView model to track recently viewed pages
4. Added floating star toggle button that appears on ALL pages (except home, admin, accounts, api)
5. Favorites menu shows starred pages at top, then fills remaining slots with Most Recent pages
6. Divider and "Most Recent" subheading separates favorites from recent pages
7. Added PageViewTrackingMiddleware to automatically track page views
8. Added favorites_context processor for template data
9. Used explicit hex colors (#f59e0b gold, #9ca3af gray) for star visibility

**Files Added:**
- `apps/core/middleware.py` - PageViewTrackingMiddleware
- `apps/core/migrations/0036_favoritepage_pageview.py` - Migration for new models
- `static/js/favorites.js` - Star toggle JavaScript functionality
- `templates/components/favorite_toggle.html` - Reusable inline star button component
- `templates/components/favorite_floating.html` - Floating star button for all pages

**Files Modified:**
- `apps/core/models.py` - Added FavoritePage and PageView models
- `apps/core/views.py` - Added FavoriteToggleView, FavoriteCheckView, FavoritesMenuDataView
- `apps/core/urls.py` - Added favorites API endpoints
- `apps/core/context_processors.py` - Added favorites_context processor
- `config/settings.py` - Added middleware and context processor
- `templates/components/navigation.html` - Added Favorites dropdown menu
- `templates/base.html` - Include favorites.js and favorite_floating.html

---

## 2026-01-04 Changes

### Today's Verse Refreshes Once Per Day (Task #136)

**Session:** Today's Verse Refresh

**Changes:**
1. Added per-user per-day caching for random verse selection
2. Cache key includes user ID and date so verse changes daily
3. Same verse shows all day on every page refresh
4. First access of new day triggers a new random selection
5. Applied to both FaithHomeView.get_todays_verse and TodaysVerseView

**Files Modified:**
- `apps/faith/views.py` - Added cache import and caching logic to get_todays_verse and TodaysVerseView.get_context_data

---

### Recurring vs One-Time Task Form (Task #134)

**Session:** Task vs. Recurring Task

**Changes:**
1. Form now asks if task is recurring first (moved toggle to top)
2. Recurring tasks show start_date and end_date fields instead of due_date
3. Non-recurring tasks show only due_date (existing behavior)
4. Added start_date and end_date fields to Task model
5. Due date is auto-generated from start_date for recurring tasks
6. RecurrenceService respects end_date when generating next occurrences
7. Next occurrence due date is calculated from previous task's due date

**Files Modified:**
- `apps/life/models.py` - Added start_date, end_date fields and save() override
- `apps/life/views.py` - Added new fields to TaskCreateView and TaskUpdateView
- `apps/life/services/recurrence.py` - Updated to respect end_date and copy dates
- `templates/life/task_form.html` - Reorganized with conditional date fields
- `apps/life/migrations/0007_task_start_date_end_date.py` - New migration

---

### Journal Day Streak Excludes Today (Task #133)

**Session:** Journal Day Streak

**Changes:**
1. Modified journal streak calculation to start from yesterday instead of today
2. The streak now only counts consecutive past days of journaling, not the current day
3. Updated all three streak calculation functions for consistency
4. Updated related tests to reflect the new behavior

**Files Modified:**
- `apps/dashboard/views.py` - Updated `_calculate_journal_streak` to start from yesterday
- `apps/ai/dashboard_ai.py` - Updated `_calculate_journal_streak` to start from yesterday
- `apps/ai/personal_assistant.py` - Updated `_calculate_journal_streak` to start from yesterday
- `apps/dashboard/tests/test_dashboard_comprehensive.py` - Updated streak test cases
- `apps/ai/tests/test_ai_comprehensive.py` - Updated streak test cases

---

### Purpose Home Goals Reorder (Task #132)

**Session:** Goals Order

**Changes:**
1. Reordered tiles: Life Goals, Habit Goals, Change Intentions (was Life Goals, Intentions, then Habit Goals at bottom)
2. Restyled Habit Goals tile to match Life Goals and Change Intentions (same purpose-section class)
3. Added habit goal listing in tile with completion percentage (like Life Goals list)
4. Added 3-column grid layout with responsive breakpoints (3 cols > 1024px, 2 cols > 768px, 1 col mobile)
5. Added `active_habit_goals` to PurposeHomeView context (top 5 active habit goals)
6. Removed old habit-goals-section intro styles

**Files Modified:**
- `apps/purpose/views.py` - Added active_habit_goals to context
- `apps/purpose/templates/purpose/home.html` - Reorganized layout and styling

---

### Mobile Menu Scrolling Fix (Task #131)

**Session:** Menu items no showing

**Changes:**
1. Added `overflow: visible` to `.site-header` to prevent dropdown clipping
2. Changed mobile `.nav-menu` from `position: absolute` to `position: fixed`
3. Used `top: 60px` and `bottom: 0` instead of `max-height` for full viewport scroll
4. Added `overflow-x: hidden` and `overscroll-behavior: contain` for better UX
5. Added extra bottom padding for scroll comfort

**Files Modified:**
- `static/css/main.css` - Updated site-header and mobile nav-menu styles

---

### Habit Goals Completion Rate and CRUD (Task #130)

**Session:** Habit Goals

**Changes:**
1. Changed `completion_rate` property to calculate based on total days (start to end date) instead of only trackable days (up to today)
2. Added Delete button to habit goal list view (alongside View and Edit)
3. Added Delete button to habit goal detail view header

**Files Modified:**
- `apps/purpose/models.py` - Simplified completion_rate calculation
- `apps/purpose/templates/purpose/habit_goal_list.html` - Added Delete button
- `apps/purpose/templates/purpose/habit_goal_detail.html` - Added Delete button

---

### Habit Goal Matrix Box Sizing (Task #129)

**Session:** Matrix Not same size

**Changes:**
1. Removed day numbers from matrix boxes - values no longer visible inside boxes
2. Set fixed 24x24px box size with min/max/flex-shrink constraints
3. Removed mobile responsive sizing override that changed box size on phones
4. Matrix boxes now display at consistent size on all devices

**Files Modified:**
- `apps/purpose/templates/purpose/habit_goal_detail.html` - Updated matrix box template and CSS

---

### Project Priority and Task Ordering (Task #137)

**Session:** Order to work tasks

**Changes:**
1. Added `priority` field (1-10) to AdminProject model with default of 5
2. Updated task fetching API to order by: project priority → phase → task priority → created_at → id
3. Updated project create/update forms to include priority dropdown
4. Updated project list view to display priority column with visual badges
5. Only tasks from projects with status='open' are returned by the ready-tasks API

**Files Modified:**
- `apps/admin_console/models.py` - Added priority field to AdminProject
- `apps/admin_console/views.py` - Updated ReadyTasksAPIView ordering, project forms
- `templates/admin_console/admin_project_list.html` - Added priority column with styling

**Files Created:**
- `apps/admin_console/migrations/0015_add_project_priority.py` - Migration for priority field

---

### Blood Glucose Dashboard Time Period Filter (Task #127)

**Session:** Blood Glucose Dashboard readings with filter

**Changes:**
1. Added time period selector with Today, Last 7/30/60/90 Days options
2. Updated GlucoseDashboardView to filter glucose entries by selected period
3. Updated stats labels to show selected period (Average, Min, Max)
4. Chart title adapts based on period (Today, Last 24 Hours, Last 48 Hours)
5. Period passed via query parameter `?period=X`

**Files Modified:**
- `apps/health/views.py` - Added period handling in GlucoseDashboardView
- `templates/health/glucose/dashboard.html` - Added period selector UI and dynamic labels

---

### Heart Rate Log Default Date/Time (Task #122)

**Session:** Default date/time on heart rate log page

**Changes:**
1. Fixed template to correctly use `form.initial.recorded_at` for new entries
2. Form already had logic to set current user-local time, but template wasn't using it

**Files Modified:**
- `templates/health/heartrate_form.html` - Fixed datetime-local input value template logic

---

### AI Insight on Blood Glucose Dashboard (Task #121)

**Session:** AI Insight added to Blood Glucose Dashboard Page

**Changes:**
1. Added `glucose_insight` prompt type to AIPromptConfig and AIInsight models
2. Created `generate_glucose_insight()` method in AIService
3. Updated GlucoseDashboardView to generate AI insight for users with AI enabled
4. Added AI Insight card to glucose dashboard template with styled UI
5. Created migration 0010 with default glucose_insight prompt configuration

**Files Modified:**
- `apps/ai/models.py` - Added glucose_insight to INSIGHT_TYPES and PROMPT_TYPES
- `apps/ai/services.py` - Added generate_glucose_insight() method
- `apps/health/views.py` - Added AI insight generation to GlucoseDashboardView
- `templates/health/glucose/dashboard.html` - Added AI Insight card with CSS

**Files Created:**
- `apps/ai/migrations/0010_add_glucose_insight_prompt_type.py` - Default prompt config

**Admin Control:**
- Edit AI Insight instructions via Admin Console > AI Prompt Configurations
- Respects user's AI Coaching Style from Preferences

---

### Blood Glucose Page Delete Fix (Task #120)

**Session:** Blood Glucose Page Update

**Changes:**
1. Fixed GlucoseDeleteView redirect to stay on list page when deleting from `/health/glucose/list/`
2. Removed duplicate glucose view definitions (older unused copies at lines 615-702)
3. Consolidated glucose views with Dexcom integration views at end of file

**Files Modified:**
- `apps/health/views.py` - Fixed delete redirect, removed duplicate views

**Note:** Delete functionality already existed in UI. This fix ensures proper redirect behavior.

---

### Admin Console Dashboard - Data Imports Section

**Session:** Add Data Imports tile to Admin Console dashboard

**Changes:**
1. Created "Data Imports" section header on Admin Console dashboard
2. Moved Data Loaders tile under the new section
3. Added Clarity Import tile with glucose graph icon (green accent)

**Files Modified:**
- `templates/admin_console/dashboard.html` - Added Data Imports section and Clarity Import tile

---

### Dexcom Clarity CSV Import (Task #119)

**Session:** Load Clarity File to Whole Life Journey

**Changes:**
1. Created management command `import_clarity_csv` for CLI imports
2. Created admin web UI at `/admin-console/clarity-import/`
3. Supports file upload, user selection, dry-run validation
4. Parses EGV (blood glucose) readings from Clarity CSV exports
5. Deduplicates by timestamp, shows import statistics

**Files Created:**
- `apps/health/management/commands/import_clarity_csv.py` - CLI command
- `templates/admin_console/clarity_import.html` - Web UI template

**Files Modified:**
- `apps/admin_console/views.py` - Added ClarityImportView
- `apps/admin_console/urls.py` - Added clarity-import route

**Usage:**
- Web: Go to Admin Console > Import Clarity Data
- CLI: `python manage.py import_clarity_csv <csv_file> <user_email>`

**Note:** This is a manual import tool. Future Dexcom API integration will enable automatic syncing.

---

### Project Dropdown Multi-Select Checkbox (Task #118)

**Session:** Project Dropdown Box to match Status functionality

**Changes:**
1. Converted Project dropdown from single-select to multi-select checkbox dropdown
2. Moved Project dropdown under Search box to prevent line wrapping
3. Updated view to support multiple project filters via `getlist()`
4. Refactored JavaScript to use generic `initCheckboxDropdown()` function for both Status and Project dropdowns

**Files Modified:**
- `apps/admin_console/views.py` - Changed `get('project')` to `getlist('project')` for multi-select support
- `templates/admin_console/admin_task_list.html` - New checkbox dropdown HTML/CSS/JS for Project filter
- `apps/admin_console/tests/test_admin_console.py` - Added missing `import json` (pre-existing bug fix)

**Why:** User requested Project filter to have same UX as Status filter with multi-select checkboxes.

---

## 2026-01-03 Changes

### One-Time Data Loaders Feature (Consolidated Procfile)

**Session:** Convert Startup Data Loading to One-Time Configuration

**Problem:**
On every Railway deployment, multiple commands ran verbose data loading:
- `load_initial_data` - fixtures and populate commands
- `reload_help_content` - DELETED and reloaded all help content every deploy
- `load_danny_workout_templates` - workout templates
- `load_reading_plans` - Bible reading plans
- `load_phase1_data` - project phases
- `load_project_from_json` - project blueprints (duplicate)

This caused excessive deploy log output and redundant database operations.

**Solution:**
1. Created `DataLoadConfig` model to track which loaders have run
2. Consolidated ALL data loading into `load_initial_data`
3. Simplified Procfile from 8 commands to 4

**New Procfile:**
```
python manage.py migrate --noinput &&
python manage.py load_initial_data &&
python manage.py recalculate_task_priorities &&
python manage.py collectstatic --noinput &&
gunicorn ...
```

**Removed from Procfile:**
- `reload_help_content` (now in load_initial_data, one-time only)
- `load_danny_workout_templates` (now in load_initial_data)
- `load_reading_plans` (now in load_initial_data)
- `load_phase1_data` (now in load_initial_data)
- `load_project_from_json` (duplicate, already in load_initial_data)

**Kept in Procfile:**
- `recalculate_task_priorities` - Must run every deploy (recalculates based on due dates)

**New Model:**
- `DataLoadConfig` in `apps/admin_console/models.py`
- Fields: `loader_name`, `display_name`, `loader_type`, `is_loaded`, `loaded_at`, `loaded_by`
- Methods: `mark_loaded()`, `reset()`, `is_loader_complete()`, `register_loader()`

**Modified Files:**
- `apps/admin_console/models.py` - Added DataLoadConfig model
- `apps/admin_console/migrations/0013_add_dataloadconfig.py` - Migration
- `apps/core/management/commands/load_initial_data.py` - Consolidated all loaders
- `apps/admin_console/views.py` - Added DataLoadConfig management views
- `apps/admin_console/urls.py` - Added dataload routes
- `templates/admin_console/dashboard.html` - Added Data Loaders card
- `templates/admin_console/dataload/list.html` - New admin UI
- `Procfile` - Simplified to 4 commands

**New CLI Options:**
```bash
python manage.py load_initial_data              # Normal (skip completed)
python manage.py load_initial_data --force      # Force reload all
python manage.py load_initial_data --list       # Show loader status
python manage.py load_initial_data --reset <name>  # Reset specific loader
```

**Expected Deploy Output (after first deploy):**
```
Loading initial system data (skipping already loaded)...
  categories: skip
  encouragements: skip
  ...
  load_reading_plans: skip
  load_phase1_data: skip
  load_danny_workout_templates: skip
  ...
Initial data loading complete!
```

**Admin Console Access:**
- Navigate to Admin Console > Data Loaders
- View loader status (loaded/pending)
- Reset individual loaders or all
- Run data load from web UI

**Tests Added:**
- `DataLoadConfigModelTests` - Model functionality tests
- `DataLoadConfigViewTests` - Admin view tests

---

### Budget Status Property Shadowing Fix (ROOT CAUSE)

**Session:** Final Fix for Budget Status FieldError

**Root Cause Identified:**
The `Budget` model had a Python `@property` named `status` that calculated budget health
(on_track/warning/over). This property **shadowed** the inherited `status` database field
from `SoftDeleteModel` (which stores active/archived/deleted state).

When Django's ORM tried to filter by `status='active'`, Python's attribute lookup found
the property first (which returns 'on_track'/'warning'/'over'), not the database field.
This is why migrations adding the column didn't fix the issue - the column existed, but
Python couldn't access it!

**Fix Applied:**
1. Renamed `Budget.status` property to `Budget.health_status`
2. Renamed `Budget.status_color` property to `Budget.health_status_color`
3. Updated all references in views, templates, and tests

**Files Modified:**
- `apps/finance/models.py` - Renamed property from `status` to `health_status`
- `apps/finance/views.py` - Updated references (lines 184, 477-479)
- `templates/finance/budget_list.html` - Updated template references
- `apps/finance/tests/test_finance_comprehensive.py` - Updated test method
- `apps/finance/migrations/0009_fix_budget_status_field.py` - Safety migration

**Important Lesson:**
Never name a property the same as an inherited database field. The property will shadow
the field and make it inaccessible to Django's ORM. Use distinct names like:
- Database field: `status` (for soft-delete state)
- Computed property: `health_status` (for budget health)

---

### CSRF and Budget Status Column Fixes

**Session:** Troubleshooting CSRF and Finance Dashboard Errors

**Issues Found:**

1. **CSRF Verification Failure on Weight Log Form**
   - Error: "Origin checking failed - https://wholelifejourney.com does not match any trusted origins"
   - Root cause: `CSRF_TRUSTED_ORIGINS` was inside `if not DEBUG:` block
   - When DEBUG=True for troubleshooting, CSRF trusted origins weren't applied

2. **Budget Status Column Missing (FieldError on /finance/)**
   - Error: "Cannot resolve keyword 'status' into field"
   - Initial diagnosis: Migrations 0005, 0006 were recorded as applied but column wasn't created
   - ACTUAL root cause: Property shadowing database field (see fix above)

**Fixes Applied:**

1. **CSRF Fix:**
   - Moved `CSRF_TRUSTED_ORIGINS` outside the `if not DEBUG:` block
   - Now applies in both DEBUG=True and DEBUG=False modes

2. **Budget Status Column Fix (Multiple Attempts):**
   - Migration 0006 - Added table_schema='public' to PostgreSQL checks
   - Migration 0007 - Fresh migration with explicit schema checks
   - Migration 0008 - Used PostgreSQL DO blocks with PL/pgSQL
   - Migration 0009 - Safety net after property rename fix
   - **Final fix:** Renamed property to avoid shadowing

**Files Modified:**
- `config/settings.py` - Moved CSRF_TRUSTED_ORIGINS outside DEBUG conditional
- `apps/core/management/commands/load_initial_data.py` - Fixed PostgreSQL schema check
- `apps/finance/migrations/0006_force_budget_status_column.py` - Added table_schema
- `apps/finance/migrations/0007_ensure_budget_status_column.py` - New migration
- `apps/finance/migrations/0008_add_status_via_orm.py` - DO block migration
- `apps/finance/migrations/0009_fix_budget_status_field.py` - Post property-rename safety

**Documentation Added:**
- `CLAUDE.md` - Added "Database Migration State Issues on Railway" section
- Documents the `load_initial_data.py` workaround pattern for failed migrations
- Includes prevention checklist for future migrations

---

### Finance Module under Preferences

**Session:** Enable Finance Module in Preferences

Moved Finance module from "Coming Soon" to "Active Modules" section in preferences.

**Files Modified:**
- `templates/users/preferences.html` - Moved Finance toggle to Active Modules section

### Finance Module Audit & Bug Fix

**Session:** Testing, Validation, and Audit Review

**Issue Found:**
- Budget table missing `status` field in production database
- Caused 500 errors on `/finance/` and `/finance/budgets/` pages
- Root cause: Migration 0001 defined the field, but database state was corrupted

**Fix Applied:**
- Created migration 0005 with conditional logic
- Checks if `status` column exists before adding
- Handles both PostgreSQL and SQLite databases
- Migration is idempotent (safe to run multiple times)

**Files Created/Modified:**
- `apps/finance/migrations/0005_add_missing_budget_status.py` - Conditional migration fix

**Testing Status:**
- Production site now loads correctly
- 22 of 28 finance tests passing
- 6 test errors remain related to test database creation (investigation ongoing)

**Audit Results:**

1. **AI Outputs Validation:**
   - Consent checking implemented (`check_consent()` in ai_insights.py)
   - Data aggregation before AI (no raw transactions sent)
   - Standard disclaimer included in all insights
   - Observational language enforced via system prompt
   - Faith context respected when enabled

2. **Security & Permissions:**
   - All views require `LoginRequiredMixin` or `@login_required`
   - `FinanceUserMixin` filters all querysets by user
   - Audit logging via `FinanceAuditLogger` with IP tracking
   - Sensitive data redaction implemented
   - Rate limiting for AI queries, imports, transfers

3. **Financial Calculations:**
   - Income/expense aggregation using Django ORM (`Sum`, `Count`, `Avg`)
   - Budget spent_amount calculated from related transactions
   - Trend comparison uses same-day-range for fair comparison
   - Savings rate calculation properly handles zero income case

### Finance Security Controls

**Session:** Implement Finance Security Controls

**Task:** WLJ Finance Module - Implement Finance Security Controls

**Objective:**
Protect financial data against unauthorized access and misuse.

**Implementation:**

1. **Security Module Created:**
   - `apps/finance/security.py` - Comprehensive security controls
   - FinanceAuditLogger - Centralized audit logging with redaction
   - FinanceRateLimiter - Rate limiting for sensitive operations
   - FinanceMFAController - MFA hooks for future implementation

2. **Audit Logging:**
   - New `FinanceAuditLog` model for comprehensive audit trail
   - Logs all CRUD operations on accounts, transactions, budgets, goals
   - Logs imports, transfers, AI queries
   - IP address tracking
   - Sensitive data redaction (tokens, account numbers)
   - FinanceAuditMixin for easy view integration

3. **Rate Limiting:**
   - AI queries: 10 per hour
   - Imports: 5 per hour
   - Bank syncs: 10 per hour
   - Transfers: 20 per hour
   - Exports: 10 per hour

4. **Access Controls:**
   - `requires_recent_auth` decorator for sensitive operations
   - `verify_ownership` decorator for resource access
   - `requires_mfa_for_sensitive_ops` decorator (MFA ready)
   - All views require login (LoginRequiredMixin/login_required)

5. **MFA Framework:**
   - FinanceMFAController for future MFA integration
   - Identifies sensitive operations requiring MFA
   - Placeholder verification that logs warnings
   - Ready for TOTP/SMS integration

6. **Encryption (already in place):**
   - Bank tokens encrypted at rest with Fernet (AES-256)
   - Sensitive fields identified in models

**Files Created/Modified:**
- `apps/finance/security.py` (new)
- `apps/finance/models.py` - Added FinanceAuditLog model
- `apps/finance/views.py` - Added FinanceAuditMixin, rate limiting to AI endpoints

**Migration Created:**
- `0004_add_finance_audit_log.py`

---

### AI Spending Insights and Coaching

**Session:** Implement AI Spending Insights and Coaching

**Task:** WLJ Finance Module - Implement AI Spending Insights and Coaching

**Objective:**
Turn financial data into actionable guidance for users with AI-generated insights following the AI Finance Rules.

**Implementation:**

1. **New Service Created:**
   - `apps/finance/services/ai_insights.py` - FinanceAIService class
   - Follows AI Finance Rules (docs/wlj_ai_finance_rules.md)
   - Privacy-first data aggregation (sends summaries, not raw transactions)

2. **Key Features:**
   - `_get_spending_summary()` - Aggregates transaction data for AI
   - `_get_spending_trends()` - Compares current vs previous period
   - `_detect_unusual_spending()` - Pattern deviation detection (>50% from average)
   - `_identify_recurring_transactions()` - Subscription/recurring expense detection
   - `generate_spending_insight()` - Main insight generator with 4-hour caching
   - `generate_budget_alert()` - Budget-specific supportive observations
   - `generate_goal_encouragement()` - Goal progress encouragement
   - `generate_subscription_review()` - Recurring expense review

3. **API Endpoints Added:**
   - `GET /finance/api/insights/spending/` - Spending insights
   - `GET /finance/api/insights/subscriptions/` - Subscription analysis
   - `GET /finance/api/insights/budget/<pk>/` - Budget-specific alerts
   - `GET /finance/api/insights/goal/<pk>/` - Goal encouragement

4. **AI Safety Features:**
   - User consent verification before AI processing
   - Observational language ("It looks like...") vs advice
   - Data aggregation (never sends raw transaction details)
   - All prompts follow AI Finance Rules
   - Disclaimers included in all responses

**Files Created/Modified:**
- `apps/finance/services/ai_insights.py` (new)
- `apps/finance/views.py` - Added AI insight API views
- `apps/finance/urls.py` - Added AI insight routes

---

### Implement Bank Connectivity (Plaid Integration)

**Session:** Implement Bank Connectivity

**Task:** WLJ Finance Module - Implement Bank Connectivity

**Objective:**
Enable users to securely link bank and credit accounts to WLJ via Plaid.

**Implementation:**

1. **New Models Added:**
   - `BankConnection` - Stores Plaid connection info with encrypted tokens
   - `BankIntegrationLog` - Audit trail for all bank integration events
   - Added Plaid fields to `FinancialAccount` (bank_connection, plaid_account_id, is_synced)
   - Added Plaid fields to `Transaction` (plaid_transaction_id, plaid_pending)

2. **Services Created:**
   - `apps/finance/services/encryption.py` - Fernet-based token encryption
   - `apps/finance/services/plaid_service.py` - Plaid API client wrapper
   - `apps/finance/services/sync_service.py` - Transaction sync service

3. **Views and URLs Added:**
   - `BankConnectionListView` - List connected banks
   - `bank_connection_start` - Generate Plaid Link token
   - `bank_connection_complete` - Exchange public token, store encrypted access token
   - `bank_connection_reauth` - Re-authentication flow
   - `bank_connection_disconnect` - Disconnect and revoke token
   - `bank_connection_sync` - Manual sync trigger
   - `plaid_webhook` - Handle Plaid webhooks

4. **Template Created:**
   - `templates/finance/bank_connection_list.html` - Connection management UI

5. **Configuration Added:**
   - Settings: PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ENV, BANK_TOKEN_ENCRYPTION_KEY
   - Updated .env.example with Plaid configuration

6. **Dependencies Added:**
   - `plaid-python>=23.0.0`
   - `cryptography>=42.0.0`

**Files Created/Modified:**
- `apps/finance/models.py` - Added BankConnection, BankIntegrationLog, Plaid fields
- `apps/finance/services/__init__.py` (new)
- `apps/finance/services/encryption.py` (new)
- `apps/finance/services/plaid_service.py` (new)
- `apps/finance/services/sync_service.py` (new)
- `apps/finance/views.py` - Added bank connection views
- `apps/finance/urls.py` - Added bank connection routes
- `templates/finance/bank_connection_list.html` (new)
- `config/settings.py` - Added Plaid configuration
- `.env.example` - Added Plaid environment variables
- `requirements.txt` - Added plaid-python, cryptography

**Migration Created:**
- `0003_add_bank_connection.py`

---

### Bank Integration Architecture

**Session:** Design Bank Integration Architecture

**Task:** WLJ Finance Module - Design Bank Integration Architecture

**Objective:**
Prepare WLJ for secure connections to external financial institutions.

**Documentation Created:** `docs/wlj_bank_integration_architecture.md`

**Key Architecture Decisions:**

1. **Financial Data Aggregator (Section 2)**
   - Selected **Plaid** as primary aggregator
   - Rationale: 12,000+ institutions, OAuth-first, no credential handling
   - Token-based access (WLJ never stores bank passwords)

2. **Token Storage & Encryption (Section 3)**
   - `BankConnection` model with encrypted access tokens
   - Fernet (AES-256) encryption for tokens at rest
   - Token lifecycle handling (permanent tokens, reauth triggers)
   - Secure revocation on disconnect

3. **Sync Schedules & Failure Handling (Section 4)**
   - Initial sync after connection
   - Webhook-driven real-time updates
   - Scheduled sync every 4 hours as fallback
   - Cursor-based incremental sync for efficiency
   - Failure handling: retries, reauth detection, error logging

4. **User Connection/Disconnection Flows (Section 5)**
   - Plaid Link UI handles all bank authentication
   - Token exchange flow documented
   - Re-authentication flow for password/MFA changes
   - Clean disconnection with token revocation

5. **Account Mapping (Section 6)**
   - Plaid accounts map to WLJ FinancialAccount
   - Account type mapping (checking, savings, credit card, etc.)

6. **Security Considerations (Section 7)**
   - Encrypted tokens, never stored credentials
   - Owner-only access control
   - Audit logging via BankIntegrationLog
   - Compliance notes (PCI-DSS, Open Banking, GDPR/CCPA)

7. **Implementation Phases (Section 9)**
   - Phase 1: Foundation (architecture, models, encryption)
   - Phase 2: Core Integration (Plaid client, sync)
   - Phase 3: Reliability (webhooks, error handling)
   - Phase 4: User Experience (UI, status indicators)
   - Phase 5: Operations (monitoring, admin tools)

**Files Created:**
- `docs/wlj_bank_integration_architecture.md` - Complete bank integration architecture

**Environment Variables Required:**
- `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV`
- `BANK_TOKEN_ENCRYPTION_KEY` (Fernet key)
- `PLAID_WEBHOOK_URL`, `PLAID_REDIRECT_URI`

---

### AI Finance Interpretation Rules

**Session:** Define AI Finance Interpretation Rules

**Task:** WLJ Finance Module - Define AI Finance Interpretation Rules

**Objective:**
Establish safe, explainable AI behavior for interpreting financial data.

**Documentation Created:** `docs/wlj_ai_finance_rules.md`

**Key Rules Established:**

1. **Data Access Rules (Section 1)**
   - Allowed: Account names/types, balances, transaction amounts/dates/categories, budgets, goals
   - Prohibited: Account numbers, bank credentials, OAuth tokens, raw import files
   - Preference for aggregated data over raw transaction lists

2. **Allowed AI Outputs (Section 2)**
   - Permitted: Summaries, trends, progress updates, gentle nudges, celebrations, observations
   - Prohibited: Investment advice, tax guidance, debt strategies, credit predictions
   - Language guidelines: "You may want to consider..." not "You should..."

3. **Credential Protection (Section 3)**
   - Absolute prohibition on exposing tokens, credentials, account numbers
   - Data sanitization requirements before AI processing
   - Logging requirements (event only, no sensitive data)

4. **Explainability Requirements (Section 4)**
   - All insights must include data source attribution
   - Timeframe specification required
   - Uncertainty must be acknowledged

5. **User Consent (Section 5)**
   - Consent verification required before AI processing
   - Finance AI can be disabled independently of other AI features

6. **Implementation Checklist (Section 6)**
   - Pre-send validation, response processing, display requirements

**Files Created:**
- `docs/wlj_ai_finance_rules.md` - Complete AI Finance interpretation rules

---

### Transaction File Import Feature

**Session:** Upload Transaction File

**Task:** WLJ Finance Module - Upload Transaction File

**Objective:**
Allow users to manually upload transaction files exported from their financial institutions.

**Implementation:**

1. **New Model: `TransactionImport`**
   - Tracks uploaded files with full audit trail
   - Records: who uploaded, when, file details, processing status
   - Tracks: rows total, imported, skipped (duplicates), failed
   - Status workflow: pending -> processing -> completed/failed/partial
   - Linked to transactions via `import_record` foreign key

2. **Import Service: `apps/finance/import_service.py`**
   - `TransactionImportService` class for parsing files
   - Supports multiple formats:
     - **CSV**: Auto-detects column mappings (date, amount, debit/credit, description, payee, etc.)
     - **OFX/QFX**: Parses Open Financial Exchange format
     - **QIF**: Parses Quicken Interchange Format
   - Handles multiple date formats (MM/DD/YYYY, YYYY-MM-DD, etc.)
   - Parses various amount formats (negative, parentheses, CR/DR suffixes)
   - Duplicate detection based on date/amount/description

3. **Form: `TransactionImportForm`**
   - File upload with validation (supports .csv, .ofx, .qfx, .qif)
   - Account selection for target account
   - Optional notes field
   - Max file size: 10MB

4. **Views:**
   - `import_upload_view`: File upload and processing
   - `ImportListView`: Import history with pagination
   - `ImportDetailView`: Details and imported transactions

5. **Templates:**
   - `import_form.html`: Drag-and-drop upload interface
   - `import_list.html`: Import history table
   - `import_detail.html`: Audit details and transaction list

6. **URL Routes:**
   - `/finance/import/` - Upload form
   - `/finance/import/history/` - Import history
   - `/finance/import/<pk>/` - Import details

**Files Changed:**
- `apps/finance/models.py` - Added TransactionImport model, import_record FK on Transaction
- `apps/finance/import_service.py` - New file for parsing logic
- `apps/finance/forms.py` - Added TransactionImportForm
- `apps/finance/views.py` - Added import views
- `apps/finance/urls.py` - Added import routes
- `templates/finance/import_form.html` - New
- `templates/finance/import_list.html` - New
- `templates/finance/import_detail.html` - New
- `apps/finance/migrations/0002_add_transaction_import.py` - New migration

**Migration:** `0002_add_transaction_import` - Creates TransactionImport model and adds import_record field

**Supported File Formats:**
| Format | Extension | Column Detection |
|--------|-----------|------------------|
| CSV    | .csv      | Auto-detects common column names |
| OFX    | .ofx      | Standard OFX/SGML parsing |
| QFX    | .qfx      | Same as OFX (Quicken variant) |
| QIF    | .qif      | Quicken Interchange Format |

---

## 2026-01-02 Changes

### CRITICAL: Timezone IANA Format Fix

**Session:** Encryption of Data (task was actually timezone fix)

**Issue:**
Dashboard and AI Assistant returning 500 error with message:
`time zone "US/Eastern" not recognized`

**Root Cause:**
PostgreSQL requires IANA timezone names (e.g., 'America/New_York') and does not recognize legacy US/* format (e.g., 'US/Eastern'). The `TimezoneMiddleware` added earlier in the day was activating the user's timezone using Django's `timezone.activate()`, which then passed the timezone to PostgreSQL for date/time operations.

**Solution:**
1. Updated `TIMEZONE_CHOICES` in UserPreferences model to use IANA format
2. Added `TIMEZONE_LEGACY_MAP` dict for converting legacy values
3. Added `timezone_iana` property to UserPreferences for safe access
4. Updated `TimezoneMiddleware` to use `timezone_iana` property
5. Updated all code using `preferences.timezone` directly:
   - `apps/core/utils.py` (get_user_today, get_user_now)
   - `apps/dashboard/views.py`
   - `apps/health/views.py`, `forms.py`, `models.py`
   - `apps/sms/views.py`
6. Created data migration `0024_convert_legacy_timezones.py` to convert existing legacy values
7. Updated onboarding form with IANA timezone choices
8. Fixed test assertions to use new IANA format

**New Timezone Choices:**
- America/New_York (Eastern Time)
- America/Chicago (Central Time)
- America/Denver (Mountain Time)
- America/Los_Angeles (Pacific Time)
- America/Anchorage (Alaska Time)
- Pacific/Honolulu (Hawaii Time)
- UTC

**Files Changed:**
- `apps/users/models.py` - TIMEZONE_CHOICES, TIMEZONE_LEGACY_MAP, timezone_iana property
- `apps/users/middleware.py` - TimezoneMiddleware
- `apps/users/forms.py` - onboarding form
- `apps/core/utils.py` - get_user_today, get_user_now
- `apps/dashboard/views.py`
- `apps/health/views.py`, `forms.py`, `models.py`
- `apps/sms/views.py`
- `apps/users/migrations/0024_convert_legacy_timezones.py` (new)
- `apps/users/tests/test_onboarding_wizard.py`

**Migration:** `0024_convert_legacy_timezones` - Converts US/Eastern, US/Central, US/Mountain, US/Pacific to IANA equivalents

---

### Run Task Mode Execution Contract

**Session:** Define Run Task execution behavior

**Task:** WLJ Executable Work Orchestration System - Phase 1

**Objective:**
Ensure Claude executes tasks deterministically and never guesses or infers missing information.

**Implementation:**

Added comprehensive "RUN TASK MODE (MANDATORY EXECUTION CONTRACT)" section to CLAUDE.md:

1. **Core Principle:** No Guessing, No Inference
   - Claude must execute tasks deterministically
   - Never guess missing information
   - Never infer unstated requirements
   - Fail with specific error rather than proceeding with assumptions

2. **Step 1: Load CLAUDE.md First (MANDATORY)**
   - Non-negotiable requirement before any task execution
   - Ensures project context is always loaded

3. **Step 2: Validate Task Structure**
   - Verify all four required fields: objective, inputs, actions, output
   - Halt execution on validation failure

4. **Step 3: Gather Inputs**
   - Process each input in the inputs array
   - Halt if any input cannot be gathered

5. **Step 4: Execute Actions In Order**
   - Execute each action exactly as written
   - Sequential execution (no reordering)
   - No actions skipped, added, or modified
   - Stop immediately on any action failure

6. **Step 5: Verify Output**
   - Confirm output criteria is met before marking complete

7. **Step 6: Mark Complete (Only On Success)**
   - Only mark task done if all steps succeeded
   - Task remains in_progress on any failure

**Additional Sections:**
- Failure Modes table with specific responses
- Example Execution Flow diagram
- "What Run Task Mode Does NOT Do" list
- Integration with Task API documentation

**Files Changed:**
- `CLAUDE.md` - Added 160+ lines of Run Task Mode documentation

---

### Nightly Task Priority Scheduler Fix

**Issue:** Tasks due "today" were not automatically moving from "Soon" to "Now" priority overnight.

**Root Causes:**
1. **Missing --preload flag:** The gunicorn command was missing `--preload`, causing APScheduler to start in worker processes instead of the master process. When workers are recycled, the scheduler dies with them.

2. **Wrong scheduler time:** The scheduler was running at 00:05 UTC, which is 7:05 PM EST the previous evening. This meant tasks that should be "Now" on the current day weren't updated until the next day.

**Solution:**
1. Added `--preload` flag to gunicorn in both Procfile and railway.json
   - Scheduler now starts once in master process before forking workers
   - Survives worker recycling

2. Changed scheduler time from 00:05 UTC to 06:00 UTC (01:00 EST)
   - Ensures tasks update at the right time for US Eastern timezone
   - Tasks due "today" correctly show as "now" priority

3. Improved logging throughout
   - Clear startup logs confirm scheduler is running
   - Job execution logs include UTC timestamps

**Files Modified:**
- `Procfile` - Added --preload flag
- `railway.json` - Added --preload flag and recalculate_task_priorities command
- `config/wsgi.py` - Better startup logging
- `apps/life/jobs.py` - Added execution timestamps

---

### Habit Goal Matrix Sizing Implementation (Phase 2)

**Session:** Implement Optimized Habit Matrix Sizing Logic

**Task:** Phase 2 of "WLJ Goals & Habit Matrix System Upgrade" project

**Objective:**
Create a habit matrix that minimizes unused space while preserving a clean, readable grid using an optimized rectangular layout algorithm.

**Implementation:**

1. **New Models (apps/purpose/models.py):**
   - `HabitGoal` - Short-term habit goals with daily tracking
     - Required fields: name, purpose, start_date, end_date, habit_required
     - Matrix sizing properties: total_days, matrix_rows, matrix_columns, total_boxes, disabled_boxes
     - Matrix data generation: get_matrix_data(), get_matrix_as_rows()
     - Statistics: completed_days, completion_rate, current_streak
   - `HabitEntry` - Daily habit completion entries
     - One entry per goal per calendar day (unique_together constraint)
     - Validation: date within goal range, no future dates

2. **Matrix Sizing Algorithm:**
   ```python
   total_days = (end_date - start_date).days + 1  # Inclusive
   rows = floor(sqrt(total_days))
   columns = ceil(total_days / rows)
   total_boxes = rows × columns
   disabled_boxes = total_boxes - total_days
   ```

3. **Box States:**
   - `completed` - Habit entry exists with completed=True
   - `missed` - Past date, no completed entry
   - `today` - Current date
   - `future` - Future date (not interactable)
   - `disabled` - Grid alignment box (no date)

4. **Files Changed:**
   - `apps/purpose/models.py` - Added HabitGoal and HabitEntry models
   - `apps/purpose/migrations/0003_add_habit_goal_and_entry.py` - New migration
   - `apps/purpose/tests/test_purpose_comprehensive.py` - 23 new tests

5. **Tests Added (23 total):**
   - HabitGoalModelTest: Model creation, validation, matrix sizing (30/45/100/7/1 days), matrix data generation, statistics
   - HabitEntryModelTest: Creation, uniqueness, date validation, backfilling

**Example Matrix Calculations:**
- 30-day goal: 5×6 grid (30 boxes, 0 disabled)
- 45-day goal: 6×8 grid (48 boxes, 3 disabled)
- 100-day goal: 10×10 grid (100 boxes, 0 disabled)

---

### Claude Code Ready Tasks API ("What's Next?" Protocol)

**Session:** Admin Console - Task Orchestration Enhancement

**Objective:**
Enable Claude Code to automatically discover and execute Ready tasks when the user asks "What's Next?" without requiring screenshots or manual task lookups.

**Implementation:**

1. **New API Endpoint:**
   - `GET /admin-console/api/claude/ready-tasks/`
   - Returns all tasks with `status='ready'`, ordered by priority
   - Authenticated via `X-Claude-API-Key` header
   - Returns full executable task description for AI execution

2. **Files Changed:**
   - `config/settings.py` - Added `CLAUDE_API_KEY` environment variable
   - `apps/admin_console/views.py` - Added `ReadyTasksAPIView` class
   - `apps/admin_console/urls.py` - Added URL route for API endpoint
   - `CLAUDE.md` - Added "What's Next?" Protocol section

3. **API Response Format:**
   ```json
   {
       "count": 1,
       "tasks": [{
           "id": 123,
           "title": "Task title",
           "phase": "Phase 1: Name",
           "priority": 1,
           "project": "Project Name",
           "description": {
               "objective": "...",
               "inputs": ["..."],
               "actions": ["..."],
               "output": "..."
           },
           "created_at": "2026-01-02T00:00:00Z"
       }]
   }
   ```

4. **Authentication:**
   - API key stored in `CLAUDE_API_KEY` environment variable
   - Passed via `X-Claude-API-Key` HTTP header
   - Returns 401 if key missing/invalid, 500 if not configured

5. **Tests Added:**
   - 8 new tests in `apps/admin_console/tests/test_admin_console.py`
   - `ReadyTasksAPITests` class covering:
     - API key validation (missing, invalid, valid)
     - Only ready tasks returned
     - Executable task structure in response
     - Limit parameter
     - Priority ordering
     - 500 error when key not configured

**Usage:**
When user says "What's Next?", Claude Code will:
1. WebFetch the API endpoint with API key
2. Parse the ready tasks from response
3. Execute the highest priority task per Executable Task Standard

**Deployment Note:**
You must set `CLAUDE_API_KEY` environment variable in Railway before the endpoint will work.

---

## 2026-01-01 Changes

### Phase 17.5: WLJ Executable Task Standard (MAJOR FEATURE)

**Session:** Admin Tasks - Phase 17 Configurable Task Fields (continued)

**Objective:**
Make all AdminTask objects machine-readable and executable by AI by enforcing a structured JSON description format.

**Implementation:**

1. **Model Changes (`apps/admin_console/models.py`):**
   - Changed `AdminTask.description` from TextField to JSONField
   - Added `validate_executable_task_description()` validator
   - Added `ExecutableTaskValidationError` exception class
   - Added `save()` method override with validation enforcement
   - Added `clean()` method for model-level validation
   - Legacy string descriptions are allowed during migration (logs warning)

2. **Required Description Structure:**
   ```json
   {
       "objective": "What the task should accomplish",
       "inputs": ["Required context or resources"],
       "actions": ["Step 1", "Step 2", "At least one required"],
       "output": "Expected deliverable or result"
   }
   ```

3. **Validation Rules:**
   - All four fields are mandatory
   - `objective` must be non-empty string
   - `inputs` must be array of strings (can be empty)
   - `actions` must have at least one non-empty string
   - `output` must be non-empty string

4. **Form Updates:**
   - `templates/admin_console/task_intake.html` - New executable task fields UI
   - `templates/admin_console/admin_task_form.html` - Updated with JSON fields
   - `apps/admin_console/views.py` - TaskIntakeView, AdminTaskCreateView, AdminTaskUpdateView updated to parse form fields into JSON

5. **Migrations:**
   - `0010_convert_description_to_json.py` - Data migration to convert existing text to JSON
   - `0011_alter_admintask_description.py` - Schema migration to change field type

6. **Documentation:**
   - Added "WLJ EXECUTABLE TASK STANDARD (MANDATORY)" section to CLAUDE.md
   - Defines Run Task mode behavior for AI execution

**Test Impact:**
- All 178 admin_console tests pass
- Legacy string descriptions allowed during migration period

---

### Nightly Task Priority Recalculation (NEW FEATURE)

**Session:** Prayer Request Fix

**Problem:**
Task priorities (Now/Soon/Someday) are calculated based on due dates, but they only updated when a task was saved. If a task was set to "Soon" because it was due in 5 days, it would remain "Soon" forever unless edited - even after the due date arrived.

**Solution:**
Added a nightly scheduled job that automatically recalculates task priorities for all incomplete tasks based on their due dates:
- **Now**: Due today or overdue
- **Soon**: Due within 7 days
- **Someday**: Due more than 7 days away or no due date

**New Files:**
- `apps/life/management/commands/recalculate_task_priorities.py` - Management command to recalculate priorities
- `apps/life/jobs.py` - APScheduler job functions for life module

**Modified Files:**
- `config/wsgi.py` - Added two new nightly jobs:
  - `recalculate_task_priorities` at 12:05 AM
  - `process_recurring_tasks` at 12:10 AM (existing command, now scheduled)
- `apps/life/tests/test_life_comprehensive.py` - Added 7 tests for the new command

**Scheduler Jobs:**
The background scheduler now runs 4 jobs:
1. SMS: Daily scheduling at midnight
2. SMS: Send pending every 5 minutes
3. Life: Recalculate task priorities at 12:05 AM
4. Life: Process recurring tasks at 12:10 AM

**Note:** Task priorities also recalculate immediately when a task is saved (due date changed), so the nightly job only catches time-based transitions.

---

### Remove "Your First" Button Text Across All Templates (UI FIX)

**Session:** Prayer Request Fix

**Problem:**
Multiple buttons and links throughout the app said things like "Add your first prayer request", "Log your first weight", "Create your first tag", etc. even when the user already had existing items. The text implied it was the user's first when it may not be.

**Solution:**
Changed all button/link text to remove "your first" phrasing, making them accurate regardless of whether the user has existing items.

**Files Modified (13 instances fixed):**
- `templates/faith/home.html`:
  - "Add your first prayer request" → "Add a prayer request"
  - "Write your first reflection" → "Write a reflection"
  - "Add your first milestone" → "Add a milestone"
- `templates/health/home.html`:
  - "Log your first weight" → "Log weight"
  - "Log your first reading" → "Log a reading" (heart rate)
  - "Log your first reading" → "Log a reading" (blood pressure)
  - "Log your first reading" → "Log a reading" (blood oxygen)
  - "Add your first medicine" → "Add a medicine"
  - "Log your first workout" → "Log a workout"
- `templates/health/fasting_list.html`:
  - "Start your first fast" → "Start a fast" (text and button)
- `templates/health/medicine/medicine_list.html`:
  - "adding your first medicine" → "adding a medicine"
- `templates/journal/tag_list.html`:
  - "Create your first tag" → "Create a tag" (text and button)
- `templates/journal/entry_form.html`:
  - "Create your first tag" → "Create a tag"
- `templates/admin_console/theme_list.html`:
  - "Create your first theme" → "Create a theme"

---

### Admin Project Tasks - Phase 17 Configurable Task Fields (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 17 Configurable Task Fields

**Description:**
Made task intake fields fully configurable via admin-defined database tables instead of hardcoded enums. Admins can now create, edit, and manage task field options (status, priority, category, effort) through the admin console.

**New Models:**
- `AdminTaskStatusConfig` - Configurable status options (backlog, ready, in_progress, blocked, done)
  - Fields: name, display_name, execution_allowed, terminal, order, active
- `AdminTaskPriorityConfig` - Configurable priority levels (1-5)
  - Fields: value (integer), label, order, active
- `AdminTaskCategoryConfig` - Configurable categories (feature, bug, infra, content, business)
  - Fields: name, display_name, order, active
- `AdminTaskEffortConfig` - Configurable effort levels (S, M, L)
  - Fields: value, label, order, active

**AdminTask Model Changes:**
- Added ForeignKey fields: `status_config`, `priority_config`, `category_config`, `effort_config`
- Legacy fields retained for backward compatibility during migration
- Helper methods: `get_status_display_value()`, `get_priority_display_value()`, etc.

**New Routes (Admin Config Management):**
- `GET /admin-console/projects/config/` - Config dashboard
- Status: `/config/status/`, `/config/status/new/`, `/config/status/<pk>/edit/`, `/config/status/<pk>/delete/`
- Priority: `/config/priority/`, `/config/priority/new/`, `/config/priority/<pk>/edit/`, `/config/priority/<pk>/delete/`
- Category: `/config/category/`, `/config/category/new/`, `/config/category/<pk>/edit/`, `/config/category/<pk>/delete/`
- Effort: `/config/effort/`, `/config/effort/new/`, `/config/effort/<pk>/edit/`, `/config/effort/<pk>/delete/`

**Task Intake Form Updates:**
- Dropdowns now populated from active config tables
- Only active config values appear in dropdowns
- Form creates tasks with both config ForeignKeys and legacy field values for backward compatibility

**Safety Rules (Deletion Protection):**
- Config items in use by tasks cannot be deleted (raises `DeletionProtectedError`)
- Inactive config items cannot be assigned to new tasks
- All existing tasks linked to config records via data migration

**Migrations:**
- `0008_phase17_configurable_task_fields.py` - Creates config models, adds FK fields to AdminTask
- `0009_populate_task_configs.py` - Data migration to populate config tables and link existing tasks

**Modified Files:**
- `apps/admin_console/models.py` - Added 4 config models, updated AdminTask
- `apps/admin_console/views.py` - Added TaskConfigDashboardView and CRUD views for all config types
- `apps/admin_console/urls.py` - Added 17 new URL patterns for config management
- `templates/admin_console/task_intake.html` - Updated to use config dropdowns
- `templates/admin_console/config/` - New directory with 13 templates:
  - `config_dashboard.html`,
  - `status_list.html`, `status_form.html`, `status_confirm_delete.html`
  - `priority_list.html`, `priority_form.html`, `priority_confirm_delete.html`
  - `category_list.html`, `category_form.html`, `category_confirm_delete.html`
  - `effort_list.html`, `effort_form.html`, `effort_confirm_delete.html`

**Tests:** All 178 admin_console tests pass.

---

### Admin Project Tasks - Phase 16 Projects Introduction (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 16 Projects Introduction

**Description:**
Introduced Projects as a first-class object to organize admin tasks. Each task must now belong to a project. Projects can be marked as complete when all their tasks are done.

**New Model:**
- `AdminProject` - Groups related tasks together
  - Fields: id, name, description, status (open/complete), created_at, updated_at
  - Status: 'open' or 'complete'
  - Deletion protection: Cannot delete a project that has tasks

**New Routes:**
- `GET /admin-console/projects/` - Project list page
- `GET /admin-console/projects/<id>/` - Project detail page

**AdminTask Changes:**
- Added required `project` ForeignKey to AdminProject
- All existing tasks assigned to default "General" project via migration
- Task transitions to 'done' now check if project should be completed

**Project Completion Logic:**
- `check_and_complete_project(project)` - Checks if all tasks are done and marks project complete
- `on_task_done_check_project(task)` - Called when task transitions to 'done'
- Creates AdminActivityLog entry when project is completed

**Safety Rules:**
- Project must exist for every task (enforced at DB level)
- Tasks cannot exist without a project
- Deleting projects with tasks raises `DeletionProtectedError`
- No data loss during migration (existing tasks get "General" project)

**Modified Files:**
- `apps/admin_console/models.py` - Added AdminProject model, project FK to AdminTask
- `apps/admin_console/services.py` - Added project completion functions
- `apps/admin_console/views.py` - Added AdminProjectListView, AdminProjectDetailView
- `apps/admin_console/urls.py` - Added project routes
- `apps/admin_console/migrations/0007_add_admin_project.py` - Migration for AdminProject
- `templates/admin_console/admin_project_list.html` - Project list template
- `templates/admin_console/admin_project_detail.html` - Project detail template
- `apps/admin_console/tests/test_admin_console.py` - Updated tests with project field

---

### Admin Project Tasks - Phase 15 Operator Runbook (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 15 Operator Runbook (Contextual Help)

**Description:**
Added an Operator Runbook that appears as contextual help when the user is working in Projects. The runbook is a read-only reference document that explains how to operate the Projects system.

**New Route:**
- `GET /admin-console/projects/help/` - Projects Operator Runbook page

**Contextual Help Integration:**
- When user is on any Projects page (`/admin-console/projects/*`), the Help modal shows a "Projects Operator Runbook" button
- When user is outside Projects, the button is hidden
- Context-awareness implemented via JavaScript URL path detection

**Runbook Content (5 Sections):**
1. **What the Projects System Is** - Purpose of Projects, Phases, and Tasks; why tasks must be entered intentionally
2. **Daily Operating Workflow** - 6-step workflow from Task Intake to reviewing execution results
3. **Task Status Meanings** - Definitions for backlog, ready, in_progress, blocked, done
4. **When Execution Stops** - Explains 4 stop conditions and their resolutions
5. **Golden Rules** - 5 operating principles (database is truth, Claude never invents work, one task at a time, humans control readiness, safety stops are expected)

**Safety Rules:**
- Admin-only access (returns 403 for non-staff users via AdminRequiredMixin)
- Read-only content (no forms, no data modification)
- Does not log activity
- Does not auto-open

**Modified Files:**
- `apps/admin_console/urls.py` - Added projects_runbook route
- `apps/admin_console/views.py` - Added ProjectsRunbookView
- `templates/admin_console/projects_runbook.html` - New runbook template
- `templates/components/help_modal.html` - Added contextual links section with Projects Runbook
- `static/css/help.css` - Added styles for contextual links

---

### Admin Project Tasks - Phase 13 Inline Editing & Priority (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 13 Inline Editing & Priority

**Description:**
Improved admin productivity by allowing quick inline task updates directly from the Task List page. Adds inline dropdowns for status and priority changes that save immediately without needing to navigate to edit pages.

**New API Endpoints:**
- `PATCH /admin-console/api/projects/tasks/<id>/inline-status/` - Inline status updates
- `PATCH /admin-console/api/projects/tasks/<id>/inline-priority/` - Inline priority updates

**Inline Status Edit:**
- Allows changing status via dropdown directly in the Task List
- Only allows transitions between `backlog` and `ready`
- Does NOT allow setting `in_progress`, `blocked`, or `done` via inline edit
- Tasks in other statuses show read-only badge (not dropdown)
- Changes save immediately on selection
- Creates activity log entry for each change

**Inline Priority Edit:**
- Allows changing priority (1-5) via dropdown directly in the Task List
- Works on tasks in any status
- Changes save immediately on selection
- Creates activity log entry for each change
- Priority dropdown shows color-coded styling matching priority level

**Ordering Helpers:**
- Default ordering: priority ASC, created_at ASC (most urgent first)
- Displayed in page subtitle

**Quick Filters:**
- Added quick filter buttons below main filter bar
- "Ready Only" - Shows only tasks with status=ready
- "Backlog Only" - Shows only tasks with status=backlog
- Active filter is highlighted

**Safety Rules:**
- Admin-only (returns 403 for non-staff users)
- No background jobs
- No execution hooks
- No auto-advancement of phases or status

**Modified Files:**
- `apps/admin_console/views.py` - Added InlineStatusUpdateAPIView, InlinePriorityUpdateAPIView
- `apps/admin_console/urls.py` - Added 2 new API routes
- `templates/admin_console/admin_task_list.html` - Added inline dropdowns, quick filters, updated JS/CSS
- `apps/admin_console/tests/test_admin_console.py` - Added 19 new tests for inline editing

**Test Count:** 19 new tests (InlineStatusUpdateAPITest: 9, InlinePriorityUpdateAPITest: 10)

---

### Admin Project Tasks - Phase 12 Task Intake & Controls (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 12 Task Intake & Controls

**Description:**
Added a clean, intentional admin-console interface for human task management. This phase provides admin-only pages for creating and managing project tasks without any automation or execution logic.

**New Routes:**
- `GET/POST /admin-console/projects/intake/` - Task Intake page
- `GET /admin-console/projects/tasks/` - Task List page (enhanced with filtering)
- `POST /api/projects/tasks/<id>/mark-ready/` - Mark Ready toggle API

**Task Intake Page:**
New `TaskIntakeView` provides a form for admins to create tasks:
- Required fields: title, description, phase
- Priority: 1-5 (default 3)
- Status: backlog or ready (default backlog)
- Optional: category, effort
- created_by is ALWAYS set to "human" (enforced server-side)
- Validates phase is selected (cannot create task without phase)
- Redirects to task list after successful creation

**Task List Page:**
Enhanced `AdminTaskListView` with:
- Display columns: title, phase number, status, priority, created_by, created_at
- Order by: priority ASC, created_at ASC
- Filterable by: phase, status
- Read-only list with Mark Ready controls
- Shows truncated task descriptions

**Human Controls:**
1. "Mark Ready" toggle button on backlog tasks
   - Requires explicit click
   - Changes status from backlog to ready
   - Logs activity as created_by="human"
   - No bulk actions (one task at a time)

2. Soft guardrail warning
   - Displays warning when 5+ tasks are marked "ready"
   - Shows on both Task Intake and Task List pages
   - Does NOT block saving (warning only)
   - Updates dynamically when using Mark Ready toggle

**Navigation:**
Added "Projects" section to admin console dashboard with links to:
- Task Intake
- Task List
- Project Status (existing)

**Safety Rules:**
- Non-admin users receive 403 Forbidden
- Cannot create task without selecting a phase
- Cannot auto-assign tasks to future phases
- No execution logic triggered from UI
- No Phase 11 integration from this interface

**Modified Files:**
- `apps/admin_console/urls.py` - Added 2 new routes
- `apps/admin_console/views.py` - Added TaskIntakeView, MarkReadyAPIView, enhanced AdminTaskListView
- `templates/admin_console/task_intake.html` - New template
- `templates/admin_console/admin_task_list.html` - Enhanced with filtering and Mark Ready controls
- `templates/admin_console/dashboard.html` - Added Projects section

**Tests:** All 156 admin_console tests pass.

---

### Admin Project Tasks - Phase 11.1 Preflight Guard & Phase Seeding (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 11.1 Preflight Guard & Phase Seeding

**Description:**
Added preflight execution guard and safe phase seeding for production. Ensures Phase 11 execution can only run when valid phase and task data exists.

**Preflight Guard:**
New `preflight_execution_check()` function verifies:
1. At least one AdminProjectPhase exists
2. Exactly one phase has status = "in_progress"
3. At least one AdminTask exists for the active phase

Returns structured `PreflightResult` with success flag and error messages:
- Does NOT raise exceptions
- Does NOT modify data
- Returns clear error messages for each check failure

**Phase Seeding:**
New `seed_admin_project_phases(created_by)` service function:
- If AdminProjectPhase table is empty: Creates phases 1-11
- Phase 1 set to "in_progress", all others to "not_started"
- Uses minimal names ("Phase 1", "Phase 2", etc.)
- Idempotent: safe to run multiple times
- Logs AdminActivityLog entry when seeding occurs (if tasks exist)

New management command `seed_admin_project_phases`:
- Suitable for production use
- Added to Procfile for Railway deployment

**New API Endpoints:**
- `GET /api/admin/project/preflight/` - Run preflight execution check (read-only)
- `POST /api/admin/project/seed-phases/` - Seed phases 1-11 if empty

**Safety Rules:**
- Never seeds AdminTask data (only phases)
- Never overwrites or resets existing phase data
- Never assumes development environment
- Preflight is mandatory before Phase 11 execution

**Modified Files:**
- `apps/admin_console/services.py` - Added PreflightResult, preflight_execution_check, seed_admin_project_phases
- `apps/admin_console/views.py` - Added PreflightCheckAPIView, SeedPhasesAPIView
- `apps/admin_console/api_urls.py` - Added 2 new API routes
- `apps/admin_console/management/commands/seed_admin_project_phases.py` - New management command
- `apps/admin_console/tests/test_admin_console.py` - Added 20+ tests for new functionality

**Tests:** All 130 admin_console tests pass.

---

### Admin Project Tasks - Phase 10 Hardening & Fail-Safes (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 10 Hardening & Fail-Safes

**Description:**
Added minimal safeguards so the project system cannot get stuck or corrupted. This phase adds detection of stuck states, admin override actions, and guardrails to prevent data corruption.

**Stuck State Detection:**
New `detect_system_issues()` function detects:
- A) No active phase exists (critical)
- B) More than one phase is marked "in_progress" (critical)
- C) A phase is "in_progress" but has zero tasks AND no next phase unlocked (warning)
- D) A task is "in_progress" longer than 24 hours (warning)

**Admin Override Actions:**
Three new service functions for admin-only recovery actions:
1. `reset_active_phase(phase_id, created_by)` - Force exactly one phase to in_progress
2. `force_unblock_task(task_id, reason, created_by)` - Move task from blocked to ready (requires reason)
3. `recheck_phase_completion(phase_id, created_by)` - Re-run phase completion check safely

**New API Endpoints:**
- `GET /api/admin/project/system-issues/` - Detect system issues (read-only)
- `POST /api/admin/project/override/reset-phase/` - Reset active phase
- `POST /api/admin/project/override/unblock-task/` - Force-unblock a task (requires reason)
- `POST /api/admin/project/override/recheck-phase/` - Re-run phase completion check

**Guardrails:**
1. `DeletionProtectedError` exception for protected resources
2. `AdminProjectPhase.delete()` prevents deletion if tasks exist for the phase
3. `AdminTask.delete()` prevents deletion if activity logs exist for the task
4. Invalid status transitions rejected with 400 error (existing behavior, now enforced in API)

**Activity Logging:**
All override/recovery actions are logged with `[ADMIN OVERRIDE]` prefix:
- Phase reset: "[ADMIN OVERRIDE] Active phase reset to Phase X..."
- Task unblock: "[ADMIN OVERRIDE] Task force-unblocked from 'blocked' to 'ready'..."
- Phase recheck: "[ADMIN OVERRIDE] Phase completion recheck initiated..."

**Modified Files:**
- `apps/admin_console/models.py` - Added DeletionProtectedError, delete() guardrails
- `apps/admin_console/services.py` - Added detect_system_issues, reset/unblock/recheck functions
- `apps/admin_console/views.py` - Added 4 new API views, updated delete views
- `apps/admin_console/api_urls.py` - Added 4 new API routes

**Tests:** All 129 admin_console tests pass.

---

### Admin Project Tasks - Phase 8 Phase Auto-Unlock (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 8 Phase Auto-Unlock

**Description:**
Added minimal logic so phases automatically complete and unlock based on task status. When all tasks in a phase are marked as done, the phase is marked complete and the next phase is automatically unlocked.

**Phase Completion Rule:**
A phase is considered COMPLETE when:
- All AdminTask records for that phase have status = "done"
- OR no tasks exist for that phase
- Blocked tasks do NOT count as complete (phase won't complete with blocked tasks)

**New Service Functions (in `services.py`):**
1. `is_phase_complete(phase)` - Check if a phase meets completion criteria
2. `get_next_phase(phase)` - Get the next phase by ascending phase_number
3. `unlock_next_phase(completed_phase, created_by)` - Unlock the next phase
4. `check_and_complete_phase(phase, created_by)` - Main function that checks and completes phase
5. `on_task_done(task, created_by)` - Handler called when task transitions to done

**Integration Point:**
- Phase completion logic is called ONLY when a task status transitions to "done"
- Integrated into `AdminTask.transition_status()` method
- Does NOT run on reads or page loads

**Safety Rules:**
- Never auto-complete a phase with blocked tasks
- Never skip phase numbers
- Never unlock future phases early (only unlocks immediate next phase)
- If no next phase exists, stops quietly

**Activity Logging:**
- Phase completion: "Phase X ('Name') completed. All tasks in phase are done."
- Phase unlock: "Phase X ('Name') unlocked. Previous phase Y ('Name') completed."

**Modified Files:**
- `apps/admin_console/models.py` - Added on_task_done call in transition_status method
- `apps/admin_console/services.py` - Added 5 new service functions for phase auto-unlock
- `apps/admin_console/tests/test_admin_console.py` - Added 25 new tests

**Tests:** 25 new tests for Phase 8 functionality:
- IsPhaseCompleteTests (6 tests): no tasks, all done, various incomplete states
- GetNextPhaseTests (3 tests): next phase, last phase, non-consecutive numbers
- UnlockNextPhaseTests (4 tests): sets status, no next, already started, activity log
- CheckAndCompletePhaseTests (5 tests): completion, blocked tasks, unlock next, already complete, activity log
- OnTaskDoneTests (2 tests): triggers check, does not complete with remaining
- TransitionStatusPhaseAutoUnlockTests (5 tests): full workflow, blocked prevention, multiple phases

---

### Admin Project Tasks - Phase 5 Blocker Task Creation (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 5 Blocker Task Creation

**Description:**
Added minimal logic to capture blockers as tasks instead of stopping progress. When a task encounters a blocker (missing config, required credentials, manual setup needed, or business decision required), a blocker task is created and the original task is marked as blocked.

**Blocker Definition:**
A blocker exists ONLY when one or more of the following is true:
- Required configuration or environment variable is missing
- An external account, credential, or API key is required
- A manual setup step must be completed by a human
- A business rule or decision is required to proceed

**Model Changes:**
- Added `blocking_task` ForeignKey field to AdminTask model
  - Self-referential relationship (`'self'`)
  - `on_delete=SET_NULL` (blocked task persists if blocker is deleted)
  - `null=True, blank=True` (optional field)
  - `related_name='blocks'` for reverse lookup (blocker.blocks returns all blocked tasks)

**New Service Functions (in `services.py`):**
1. `create_blocker_task(blocked_task, title, description, category, effort, created_by)`
   - Creates a new AdminTask with category='infra' or 'business'
   - Sets priority equal to or higher than the blocked task
   - Creates status='ready' blocker task
   - Updates original task to status='blocked' with blocking_task reference
   - Creates AdminActivityLog entries for BOTH tasks
   - Returns tuple: (blocker_task, blocked_task, blocker_log, blocked_log)

2. `get_blocked_tasks(phase=None)` - Query all tasks with status='blocked'
3. `get_blocker_tasks(phase=None)` - Query all tasks that are blocking other tasks
4. `is_valid_blocker_reason(reason)` - Validate blocker reason

**Blocker Task Requirements:**
- **title:** Short, action-oriented description
- **description:** Must include what was being worked on, what caused the block, what is required to unblock
- **category:** 'infra' or 'business' only (not feature, bug, or content)
- **priority:** Equal to or higher than blocked task
- **status:** 'ready' (so it appears in next tasks)
- **effort:** 'S' or 'M' only
- **created_by:** 'claude' or 'human'
- **phase:** Same phase as blocked task

**Activity Logging:**
Both the blocker task and blocked task get AdminActivityLog entries:
1. Blocker task log: "Blocker task created. Blocking task: '[title]' (ID: X). Reason: [description]"
2. Blocked task log: "Task blocked. Blocker task created: '[title]' (ID: X). Reason: [description]"

**New Files:**
- `apps/admin_console/migrations/0006_add_blocking_task.py` - Migration for blocking_task field

**Modified Files:**
- `apps/admin_console/models.py` - Added blocking_task ForeignKey field
- `apps/admin_console/services.py` - Added blocker task creation and query functions
- `apps/admin_console/tests/test_admin_console.py` - Added 17 new tests

**Tests:** 17 new tests for Phase 5 functionality:
- BlockerTaskCreationTest (9 tests): creation, priority, task updates, activity logs, validation
- BlockerTaskQueryTests (4 tests): get_blocked_tasks, get_blocker_tasks with filters
- BlockerModelFieldTests (4 tests): nullable, settable, SET_NULL on delete, reverse relationship

---

### Admin Project Tasks - Phase 4 Task Execution (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 4 Task Execution

**Description:**
Added minimal logic to allow controlled task execution using status updates only. This includes status transition validation, validation rules for phase awareness and blocked reasons, and an admin-only API endpoint for updating task status.

**Status Transition Rules:**
- `backlog` → `ready`
- `ready` → `in_progress`
- `in_progress` → `done` | `blocked`
- `blocked` → `ready`
- `done` → (terminal, no transitions allowed)

**Validation Rules:**
1. A task can only move to `in_progress` if it belongs to the active phase (phase.status = 'in_progress')
2. A task cannot move to `done` unless it was `in_progress`
3. A blocked task must include a reason

**New API Endpoint:**
- `PATCH /api/admin/project/tasks/<id>/status/` - Update task status
  - Admin-only (returns 403 for non-staff users)
  - Request body: `{"status": "in_progress", "reason": "optional, required for blocked"}`
  - Returns: Updated task JSON with activity log entry
  - Error responses: 400 (validation error), 403 (not admin), 404 (task not found)

**Activity Logging:**
Every status change creates an AdminActivityLog entry with:
- Task reference
- Previous status → New status
- Reason (if provided)
- created_by (human or claude)

**Model Changes:**
- Added `TaskStatusTransitionError` exception class
- Added `ALLOWED_TRANSITIONS` constant mapping valid transitions
- Added `blocked_reason` field to AdminTask model
- Added `is_valid_transition()` class method
- Added `validate_status_transition()` instance method
- Added `transition_status()` instance method with validation and logging

**New Files:**
- `apps/admin_console/migrations/0005_add_blocked_reason.py` - Migration for blocked_reason field

**Modified Files:**
- `apps/admin_console/models.py` - Added transition validation, blocked_reason field, logging
- `apps/admin_console/views.py` - Added TaskStatusUpdateAPIView, ActivePhaseAPIView
- `apps/admin_console/urls.py` - Added task status API route
- `apps/admin_console/tests/test_admin_console.py` - Added 31 new tests

**Tests:** 31 tests for Phase 4 functionality (TaskStatusTransitionModelTest + TaskStatusUpdateAPITest), all passing.

---

### Admin Project Tasks - Phase 3 Task Selection (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 3 Task Selection

**Description:**
Added minimal logic to list the next tasks for the active project phase. This includes a helper function and an admin-only API endpoint.

**New Features:**

1. **get_next_tasks(limit=5) Helper Function**
   - Reads the active phase (status='in_progress')
   - Queries AdminTask where phase=active and status IN ('ready', 'backlog')
   - Orders by priority ASC, then created_at ASC
   - Returns up to `limit` tasks

2. **GET /api/admin/project/next-tasks/ API Endpoint**
   - Admin-only (returns 403 for non-staff users)
   - Query params: `limit` (optional, default 5)
   - Returns JSON array of task objects with: id, title, priority, status, phase_number
   - Returns empty list if no active phase or no matching tasks

**Safety Rules Implemented:**
- Does NOT return tasks from future phases (only from active phase)
- Does NOT return tasks with status='done'
- Returns empty list when no tasks exist

**New Files:**
- `apps/admin_console/services.py` - Service functions (get_active_phase, get_next_tasks)
- `apps/admin_console/api_urls.py` - API URL routes

**Modified Files:**
- `apps/admin_console/views.py` - Added NextTasksAPIView
- `config/urls.py` - Added /api/admin/project/ route
- `apps/admin_console/tests/test_admin_console.py` - Added 11 tests for NextTasksAPITest

**Tests:** 11 new tests for NextTasksAPITest, all passing.

---

### Admin Project Tasks - Phase 1 Infrastructure (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 1 Infrastructure

**Description:**
Created a simple admin-only project task system for internal project management. This is infrastructure only - no automation, AI, or business rules.

**New Models:**

1. **AdminProjectPhase**
   - `phase_number` (IntegerField, unique)
   - `name` (CharField, max_length=100)
   - `objective` (TextField)
   - `status` (CharField, choices: not_started, in_progress, complete)
   - `created_at`, `updated_at` (auto timestamps)

2. **AdminTask**
   - `title` (CharField, max_length=200)
   - `description` (TextField)
   - `category` (CharField, choices: feature, bug, infra, content, business)
   - `priority` (IntegerField, default=3)
   - `status` (CharField, choices: backlog, ready, in_progress, blocked, done)
   - `effort` (CharField, choices: S, M, L)
   - `phase` (ForeignKey to AdminProjectPhase)
   - `created_by` (CharField, choices: human, claude)
   - `created_at`, `updated_at` (auto timestamps)

3. **AdminActivityLog**
   - `task` (ForeignKey to AdminTask)
   - `action` (TextField)
   - `created_by` (CharField, choices: human, claude)
   - `created_at` (auto timestamp)

**New URL Patterns:**
- `/admin-console/projects/phases/` - Phase list
- `/admin-console/projects/phases/new/` - Create phase
- `/admin-console/projects/phases/<pk>/edit/` - Edit phase
- `/admin-console/projects/phases/<pk>/delete/` - Delete phase
- `/admin-console/projects/tasks/` - Task list
- `/admin-console/projects/tasks/new/` - Create task
- `/admin-console/projects/tasks/<pk>/edit/` - Edit task
- `/admin-console/projects/tasks/<pk>/delete/` - Delete task
- `/admin-console/projects/activity/` - Activity log list
- `/admin-console/projects/activity/new/` - Create log
- `/admin-console/projects/activity/<pk>/edit/` - Edit log
- `/admin-console/projects/activity/<pk>/delete/` - Delete log

**New Files:**
- `apps/admin_console/migrations/0004_admin_project_tasks.py`
- `apps/admin_console/management/commands/load_phase1_data.py`
- `templates/admin_console/project_phase_list.html`
- `templates/admin_console/project_phase_form.html`
- `templates/admin_console/project_phase_confirm_delete.html`
- `templates/admin_console/admin_task_list.html`
- `templates/admin_console/admin_task_form.html`
- `templates/admin_console/admin_task_confirm_delete.html`
- `templates/admin_console/activity_log_list.html`
- `templates/admin_console/activity_log_form.html`
- `templates/admin_console/activity_log_confirm_delete.html`

**Modified Files:**
- `apps/admin_console/models.py` - Added 3 new models
- `apps/admin_console/views.py` - Added 12 new views
- `apps/admin_console/urls.py` - Added 12 new URL patterns
- `Procfile` - Added `load_phase1_data` command

**Seed Data Created:**
- Phase 1: "Core Project Infrastructure" (status: in_progress)

**Tests:** All admin_console tests pass.

---

### Project Manager App Removal (CLEANUP)

**Session:** Update Project Manager App

**Description:**
Removed the ClaudeTask project management feature due to persistent Railway deployment issues preventing the task loading commands from running. The feature was causing confusion and wasn't functioning as expected on Railway due to Nixpacks caching problems.

**Components Removed:**

1. **ClaudeTask Model**
   - Deleted the entire ClaudeTask model from `apps/admin_console/models.py`
   - Created migration `0003_delete_claudetask.py` to drop the database table

2. **Admin Registration**
   - Removed ClaudeTaskAdmin from `apps/admin_console/admin.py`

3. **Management Commands**
   - Deleted `apps/admin_console/management/commands/task_status.py`
   - Deleted `apps/admin_console/management/commands/load_bible_app_task.py`

4. **Deployment Configuration**
   - Removed `load_bible_app_task` from Procfile startup chain
   - Removed `load_bible_app_task` from nixpacks.toml start command

5. **Documentation**
   - Removed all PM/ClaudeTask references from CLAUDE.md
   - Deleted `docs/wlj_claude_tasks.md`
   - Removed "Claude as Project Manager" workflow documentation

**Files Deleted:**
- `apps/admin_console/management/commands/task_status.py`
- `apps/admin_console/management/commands/load_bible_app_task.py`
- `docs/wlj_claude_tasks.md`

**Files Modified:**
- `apps/admin_console/models.py` - Cleared (no models)
- `apps/admin_console/admin.py` - Cleared (no registrations)
- `CLAUDE.md` - Removed all PM references
- `Procfile` - Removed load_bible_app_task
- `nixpacks.toml` - Removed load_bible_app_task

**Migration Created:**
- `apps/admin_console/migrations/0003_delete_claudetask.py`

**Reason for Removal:**
Railway's Nixpacks builder was aggressively caching the old start command configuration, preventing new management commands from running on deploy. After multiple failed deployment attempts, the decision was made to completely remove the feature rather than continue troubleshooting Railway caching issues.

---

### Bible Reading Plans & Study Tools (NEW FEATURE - Phase 1)

**Session:** Bible App Updates

**Description:**
Major enhancement to the Faith module adding Bible reading plans and study tools to help users build consistent Scripture engagement habits.

**New Features:**

1. **Bible Reading Plans**
   - ReadingPlanTemplate model for system-defined plans
   - ReadingPlanDay model for daily readings within a plan
   - UserReadingPlan model for tracking user progress
   - UserReadingProgress model for daily completion tracking
   - Pre-loaded plans: Forgiveness (7 days), Prayer (7 days), Peace in Troubled Times (7 days), Marriage (7 days), Gospel of John (21 days), Psalms of Comfort (5 days)
   - Progress tracking with percentage complete
   - Pause/Resume/Abandon functionality
   - Topic-based filtering

2. **Bible Study Tools**
   - BibleHighlight model - color-coded verse highlighting (yellow, green, blue, pink, purple, orange)
   - BibleBookmark model - save locations to return to
   - BibleStudyNote model - in-depth study notes with tagging
   - Study Tools dashboard showing all tools in one place
   - Filtering by color, book, or tag

**New Files:**
- `apps/faith/migrations/0006_bible_reading_plans_and_study_tools.py`
- `apps/faith/management/commands/load_reading_plans.py`
- `templates/faith/reading_plans/list.html`
- `templates/faith/reading_plans/detail.html`
- `templates/faith/reading_plans/progress.html`
- `templates/faith/study_tools/home.html`
- `templates/faith/study_tools/highlight_list.html`
- `templates/faith/study_tools/highlight_form.html`
- `templates/faith/study_tools/bookmark_list.html`
- `templates/faith/study_tools/bookmark_form.html`
- `templates/faith/study_tools/note_list.html`
- `templates/faith/study_tools/note_form.html`
- `templates/faith/study_tools/note_detail.html`

**Modified Files:**
- `apps/faith/models.py` - Added 7 new models
- `apps/faith/forms.py` - Added forms for reading plans and study tools
- `apps/faith/views.py` - Added 20+ new views
- `apps/faith/urls.py` - Added URL patterns for reading plans and study tools
- `apps/faith/admin.py` - Added admin registrations for new models

**URL Patterns Added:**
- `/faith/reading-plans/` - Browse reading plans
- `/faith/reading-plans/<slug>/` - View plan details
- `/faith/reading-plans/<slug>/start/` - Start a plan
- `/faith/reading-plans/progress/<pk>/` - View progress
- `/faith/reading-plans/progress/<pk>/day/<pk>/complete/` - Mark day complete
- `/faith/study-tools/` - Study tools dashboard
- `/faith/study-tools/highlights/` - View highlights
- `/faith/study-tools/bookmarks/` - View bookmarks
- `/faith/study-tools/notes/` - View study notes

**Tests:**
- All 1395 tests pass including 100 faith tests

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
