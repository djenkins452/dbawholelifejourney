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

### Fix: RecaptchaService Import Error - Module Restructure

**Issue:** Production deployment failing with `ImportError: cannot import name 'RecaptchaService' from 'apps.users.services'` because both `services.py` file and `services/` directory existed, causing Python to import the directory (package) which didn't export `RecaptchaService`.

**Root Cause:** A `services/` directory was added for `DataExportService` while `services.py` (containing `RecaptchaService`) already existed. Python imports directories over files when both exist.

**Files Modified:**
- `apps/users/services.py` → `apps/users/services/recaptcha.py`: Moved file into package
- `apps/users/services/__init__.py`: Added exports for `RecaptchaService` and `RecaptchaResult`
- `apps/users/services/data_export.py`: Added `from __future__ import annotations` for Python 3.9 compatibility

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

### Fix: Admin Console Test Failures Due to Terms Version and Email Verification

**Issue:** Admin console tests were failing with 302 redirects instead of 200 because:
1. The `AdminTestMixin._accept_terms()` was creating `TermsAcceptance` with version `'1.0'` but `settings.WLJ_SETTINGS['TERMS_VERSION']` is `'1.1'`
2. The tests weren't creating verified `EmailAddress` records required by `ACCOUNT_EMAIL_VERIFICATION = "mandatory"`
3. The project creation tests were missing the `priority` field required by the form

**Files Modified:**
- `apps/admin_console/tests/test_admin_console.py`:
  - Updated `_accept_terms()` to use the current terms version from settings
  - Added `_verify_email()` method to create verified `EmailAddress` records for test users
  - Updated `create_user()` to call `_verify_email()`
  - Added `priority` field to project creation test POST data

**Root Cause:** The terms version was bumped from `'1.0'` to `'1.1'` in settings, but test fixtures weren't updated. Additionally, email verification became mandatory, breaking test user logins.

### Fix: GitHub Actions CI to Use Test Settings

**Issue:** CI tests were failing because GitHub Actions workflow was not using `config.settings_test`, causing static files manifest errors.

**Files Modified:**
- `.github/workflows/test.yml`: Updated test command to use `--settings=config.settings_test`

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
