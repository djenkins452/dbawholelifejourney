# Third-Party Services Documentation
# ==============================================================================
# File: THIRD_PARTY_SERVICES.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Comprehensive inventory of all third-party services, APIs, and
#              external integrations used in this application.
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-28
# Last Updated: 2025-12-28
# ==============================================================================
# IMPORTANT: This file must be updated whenever a new third-party service is
# added, removed, or modified. See CLAUDE.md for maintenance instructions.
# ==============================================================================

## Overview

This document catalogs all external services, APIs, and third-party integrations used by the Whole Life Journey application. Each entry includes:
- Service name and provider
- Integration type (API, SDK, CDN, etc.)
- Pricing model (Free/Paid/Usage-based)
- Configuration details
- Key files referencing the service

---

## AI & Language Models

### 1. OpenAI API
| Attribute | Value |
|-----------|-------|
| **Provider** | OpenAI |
| **Type** | REST API |
| **Pricing** | Paid (usage-based) |
| **Status** | Active |

**Purpose:**
- AI coaching and personalized dashboard insights
- Journal entry analysis and reflections
- Goal progress feedback
- Prayer encouragement with Scripture references
- Health tracking encouragement
- AI Camera image analysis (Vision API)

**Configuration (Environment Variables):**
- `OPENAI_API_KEY` - API authentication key
- `OPENAI_MODEL` - Default model (gpt-4o-mini)
- `OPENAI_VISION_MODEL` - Vision model (gpt-4o)

**Key Files:**
- `config/settings.py` (lines 49-57)
- `apps/ai/services.py` - AIService class
- `apps/scan/services/vision.py` - Vision API integration
- `apps/ai/models.py` - AIPromptConfig, CoachingStyle, AIInsight, AIUsageLog
- `apps/ai/dashboard_ai.py` - Dashboard AI integration

**User Consent:**
- Explicit opt-in required via `ai_data_consent` field in UserPreferences

---

## Cloud Storage & Media

### 2. Cloudinary
| Attribute | Value |
|-----------|-------|
| **Provider** | Cloudinary |
| **Type** | SDK & API |
| **Pricing** | Free tier available; paid for higher usage |
| **Status** | Active |

**Purpose:**
- User profile avatars
- Media file storage for user uploads
- Photo storage for inventory items
- Medicine schedule images
- AI Camera scanned images

**Configuration (Environment Variables):**
- `CLOUDINARY_CLOUD_NAME`
- `CLOUDINARY_API_KEY`
- `CLOUDINARY_API_SECRET`

**Key Files:**
- `config/settings.py` (lines 233-261)
- `requirements.txt` (cloudinary>=1.40.0, django-cloudinary-storage>=0.3.0)
- `apps/users/models.py` - User.avatar field
- `apps/health/models.py` - InventoryPhoto model

**Fallback:** Local filesystem if Cloudinary not configured

---

## Scripture & Bible APIs

### 3. API.Bible
| Attribute | Value |
|-----------|-------|
| **Provider** | American Bible Society |
| **Type** | REST API |
| **Pricing** | Free tier available |
| **Status** | Active |

**Purpose:**
- Scripture verse lookups for Faith module
- Bible translation support (default: ESV)
- Verse references and content retrieval

**Configuration (Environment Variables):**
- `BIBLE_API_KEY` - API authentication key

**Key Files:**
- `config/settings.py` (line 509)
- `apps/faith/views.py` - Scripture API views
- `apps/users/models.py` - default_bible_translation field
- `apps/faith/models.py` - ScriptureVerse, SavedVerse models

**Security:**
- Server-side proxy only (API key not exposed to frontend)
- Security Fix C-2 from CSO review

---

## Email Services

### 4. Resend
| Attribute | Value |
|-----------|-------|
| **Provider** | Resend |
| **Type** | REST API |
| **Pricing** | Free tier available; paid for volume |
| **Status** | Active (production only) |

**Purpose:**
- Password reset emails
- Email verification
- Notification emails
- Transactional communications

**Configuration (Environment Variables):**
- `RESEND_API_KEY` - API authentication key
- `DEFAULT_FROM_EMAIL` - Sender address (default: noreply@wholelifejourney.com)

**Key Files:**
- `config/settings.py` (lines 401-409)
- `apps/core/email_backends.py` - ResendEmailBackend class
- `requirements.txt` (resend>=2.4.0)

**Note:** Only active when DEBUG=False

---

## Calendar Integration

### 5. Google Calendar API
| Attribute | Value |
|-----------|-------|
| **Provider** | Google |
| **Type** | REST API with OAuth 2.0 |
| **Pricing** | Free |
| **Status** | Active |

**Purpose:**
- Sync Life module tasks/events to user's Google Calendar
- OAuth 2.0 authentication for secure credential storage
- Event creation and retrieval
- Multi-calendar support

**Configuration (Environment Variables):**
- `GOOGLE_CALENDAR_CLIENT_ID`
- `GOOGLE_CALENDAR_CLIENT_SECRET`
- `GOOGLE_CALENDAR_REDIRECT_URI`

**OAuth Scopes:**
- `https://www.googleapis.com/auth/calendar`

**Key Files:**
- `config/settings.py` (lines 526-533)
- `apps/life/services/google_calendar.py` - Service implementation
- `apps/life/models.py` - GoogleCalendarCredential model
- `requirements.txt` (google-auth>=2.0.0, google-auth-oauthlib>=1.0.0, google-api-python-client>=2.0.0)

---

## Authentication & Security

### 6. WebAuthn (Web Authentication API)
| Attribute | Value |
|-----------|-------|
| **Provider** | W3C Standard (native browser API) |
| **Type** | Browser API |
| **Pricing** | Free |
| **Status** | Active |

**Purpose:**
- Face ID login (iOS)
- Touch ID login (macOS)
- Windows Hello support
- Passwordless authentication via biometrics

**Requirements:**
- HTTPS required (except localhost)
- Browser support: Chrome 67+, Firefox 60+, Safari 13+, Edge 79+

**Key Files:**
- `static/js/biometric.js` - WebAuthn implementation
- `apps/users/views.py` - Biometric views (BiometricCheckView, etc.)
- `apps/users/models.py` - WebAuthnCredential model
- `templates/account/login.html` - Face ID/Touch ID button
- `templates/users/preferences.html` - Credentials management

---

## JavaScript Libraries (CDN)

### 7. HTMX
| Attribute | Value |
|-----------|-------|
| **Provider** | HTMX (Open Source) |
| **Type** | CDN |
| **Pricing** | Free (Open Source - BSD) |
| **Status** | Active |

**Purpose:**
- Dynamic page updates without full reloads
- AJAX requests for forms and partial updates
- Real-time interactions with Django backend

**CDN URL:** `https://unpkg.com/htmx.org@1.9.10`

**Key Files:**
- `templates/base.html` (line 21)
- `requirements.txt` (django-htmx>=1.19.0)
- `config/settings.py` - INSTALLED_APPS, MIDDLEWARE

---

### 8. Chart.js
| Attribute | Value |
|-----------|-------|
| **Provider** | Chart.js (Open Source) |
| **Type** | CDN |
| **Pricing** | Free (Open Source - MIT) |
| **Status** | Active |

**Purpose:**
- Fitness/health progress charts
- Weight tracking visualizations
- Nutrition analytics charts

**CDN URL:** `https://cdn.jsdelivr.net/npm/chart.js`

**Key Files:**
- `templates/health/fitness/progress.html`

---

## Django Packages (Open Source)

### 9. Django-allauth
| Attribute | Value |
|-----------|-------|
| **Type** | Python Package |
| **Pricing** | Free (Open Source) |
| **Status** | Active |

**Purpose:**
- User registration and login
- Email-based authentication
- Password reset flows
- Social authentication support (configured but inactive)

**Key Files:**
- `config/settings.py` (lines 366-393)
- `requirements.txt` (django-allauth>=65.0.0)
- `apps/users/middleware.py` - TermsAcceptanceMiddleware
- `templates/account/` - Auth templates

---

### 10. Django-Axes
| Attribute | Value |
|-----------|-------|
| **Type** | Python Package |
| **Pricing** | Free (Open Source) |
| **Status** | Active |

**Purpose:**
- Rate limiting on login attempts
- Brute force protection
- Lockout after 5 failed attempts (1 hour)

**Configuration:**
- `AXES_FAILURE_LIMIT` = 5
- `AXES_COOLOFF_TIME` = 1 hour
- `AXES_LOCKOUT_PARAMETERS` = ["ip_address", "username"]

**Key Files:**
- `config/settings.py` (lines 443-451)
- `requirements.txt` (django-axes>=6.0.0)

---

### 11. WhiteNoise
| Attribute | Value |
|-----------|-------|
| **Type** | Python Package |
| **Pricing** | Free (Open Source) |
| **Status** | Active |

**Purpose:**
- Static files serving (CSS, JS, images)
- Compression and caching
- Production-ready without external CDN

**Key Files:**
- `config/settings.py` (lines 218-226)
- `requirements.txt` (whitenoise>=6.7.0)

---

### 12. Crispy Forms & Crispy Tailwind
| Attribute | Value |
|-----------|-------|
| **Type** | Python Packages |
| **Pricing** | Free (Open Source) |
| **Status** | Active |

**Purpose:**
- Form rendering with TailwindCSS styling
- Reusable form templates
- Better form UX

**Key Files:**
- `config/settings.py` (lines 396-398)
- `requirements.txt` (django-crispy-forms>=2.3, crispy-tailwind>=1.0.3)

---

### 13. Pillow
| Attribute | Value |
|-----------|-------|
| **Type** | Python Package |
| **Pricing** | Free (Open Source) |
| **Status** | Active |

**Purpose:**
- Image processing and validation
- Profile picture handling
- HEIC/HEIF format support
- Thumbnail generation

**Key Files:**
- `requirements.txt` (pillow>=10.4.0)
- `apps/users/forms.py` - ProfileForm image handling
- `apps/health/models.py` - InventoryPhoto model

---

### 14. Markdown
| Attribute | Value |
|-----------|-------|
| **Type** | Python Package |
| **Pricing** | Free (Open Source) |
| **Status** | Active |

**Purpose:**
- Help system documentation rendering
- Markdown to HTML conversion

**Key Files:**
- `requirements.txt` (markdown>=3.7)
- `apps/help/services.py` - Markdown content handling

---

## Database & Infrastructure

### 15. PostgreSQL
| Attribute | Value |
|-----------|-------|
| **Provider** | PostgreSQL (via Railway) |
| **Type** | Relational Database |
| **Pricing** | Free (Open Source); Railway charges for hosting |
| **Status** | Active (Production) |

**Purpose:**
- Primary production database
- All user data, entries, preferences
- Automatic backups via Railway

**Configuration:**
- `DATABASE_URL` environment variable
- Development uses SQLite locally

**Key Files:**
- `config/settings.py` (lines 159-175)
- `Procfile` - Migration on deploy

---

### 16. Gunicorn
| Attribute | Value |
|-----------|-------|
| **Type** | Python Package |
| **Pricing** | Free (Open Source) |
| **Status** | Active |

**Purpose:**
- WSGI application server
- Production Django server
- Handles concurrent requests

**Key Files:**
- `Procfile` (gunicorn config.wsgi --log-file -)
- `config/wsgi.py`
- `requirements.txt` (gunicorn>=23.0.0)

---

## Hosting & Deployment

### 17. Railway
| Attribute | Value |
|-----------|-------|
| **Provider** | Railway |
| **Type** | Platform as a Service (PaaS) |
| **Pricing** | Paid (usage-based) |
| **Status** | Active |

**Purpose:**
- Production application hosting
- PostgreSQL database hosting
- Environment variable management
- Auto-deploy from GitHub

**Key Files:**
- `Procfile` - Deployment commands
- Environment variables for all secrets

---

### 18. GitHub
| Attribute | Value |
|-----------|-------|
| **Provider** | GitHub |
| **Type** | Source Control & CI/CD |
| **Pricing** | Free for public repos; paid for private teams |
| **Status** | Active |

**Purpose:**
- Code repository and version control
- Auto-deployment trigger to Railway
- Issue tracking

**Repository:** djenkins452/dbawholelifejourney

---

## Location Services

### 19. Zippopotam.us API
| Attribute | Value |
|-----------|-------|
| **Provider** | Zippopotam.us |
| **Type** | REST API |
| **Pricing** | Free |
| **Status** | Deprecated/Unused |

**Purpose:**
- ZIP code to city/state lookup (historical)

**API URL:** `https://api.zippopotam.us/us/{zip}`

**Key Files:**
- Referenced in old backup files only

---

## SMS Notifications

### 20. Twilio
| Attribute | Value |
|-----------|-------|
| **Provider** | Twilio |
| **Type** | REST API & SDK |
| **Pricing** | Paid (usage-based) |
| **Status** | Active |

**Purpose:**
- SMS text message notifications for reminders
- Medicine dose reminders with reply shortcuts (D=Done, R=Remind, N=Skip)
- Task due date reminders
- Calendar event reminders
- Phone number verification via Twilio Verify

**Configuration (Environment Variables):**
- `TWILIO_ACCOUNT_SID` - Twilio account SID
- `TWILIO_AUTH_TOKEN` - Twilio auth token
- `TWILIO_PHONE_NUMBER` - Sender phone number (E.164 format: +1XXXXXXXXXX)
- `TWILIO_VERIFY_SERVICE_SID` - Twilio Verify service SID for phone verification
- `TWILIO_TEST_MODE` - Set to true for development (logs instead of sending)
- `SMS_TRIGGER_TOKEN` - Secret token for external cron trigger endpoints

**Key Files:**
- `config/settings.py` (lines 556-577)
- `apps/sms/services.py` - TwilioService, SMSNotificationService
- `apps/sms/scheduler.py` - SMSScheduler
- `apps/sms/views.py` - Webhooks and verification views
- `apps/sms/models.py` - SMSNotification, SMSResponse models
- `apps/users/models.py` - SMS preference fields in UserPreferences
- `requirements.txt` (twilio>=9.0.0)

**User Consent:**
- Explicit opt-in required via phone verification and `sms_consent` field
- Users can reply STOP to unsubscribe (Twilio handles this)

**Webhook URLs (configure in Twilio Console):**
- Incoming SMS: `/sms/webhook/incoming/`
- Delivery Status: `/sms/webhook/status/`

**Cost Estimates:**
- Phone Number: ~$1.15/month
- Outbound SMS: ~$0.0079/message
- Inbound SMS: ~$0.0079/message
- Twilio Verify: ~$0.05/verification

---

## Services NOT Currently Used

The following services are NOT integrated but may be considered for future use:

| Service | Purpose | Status |
|---------|---------|--------|
| Stripe | Payment processing | Not integrated |
| Sentry | Error tracking | Not integrated (uses local logging) |
| Google Analytics | User analytics | Not integrated |
| Mixpanel | Product analytics | Not integrated |
| Firebase | Push notifications | Not integrated |
| AWS S3 | Alternative storage | Not integrated (uses Cloudinary) |

---

## Summary Table

| # | Service | Type | Pricing | Status |
|---|---------|------|---------|--------|
| 1 | OpenAI | AI API | Paid (usage) | Active |
| 2 | Cloudinary | Media Storage | Free tier | Active |
| 3 | API.Bible | Scripture API | Free tier | Active |
| 4 | Resend | Email API | Free tier | Active (prod) |
| 5 | Google Calendar | Calendar API | Free | Active |
| 6 | WebAuthn | Browser API | Free | Active |
| 7 | HTMX | CDN Library | Free (OSS) | Active |
| 8 | Chart.js | CDN Library | Free (OSS) | Active |
| 9 | Django-allauth | Package | Free (OSS) | Active |
| 10 | Django-Axes | Package | Free (OSS) | Active |
| 11 | WhiteNoise | Package | Free (OSS) | Active |
| 12 | Crispy Forms | Package | Free (OSS) | Active |
| 13 | Pillow | Package | Free (OSS) | Active |
| 14 | Markdown | Package | Free (OSS) | Active |
| 15 | PostgreSQL | Database | Free (OSS) | Active |
| 16 | Gunicorn | Server | Free (OSS) | Active |
| 17 | Railway | PaaS | Paid (usage) | Active |
| 18 | GitHub | Source Control | Free | Active |
| 19 | Zippopotam.us | Location API | Free | Deprecated |
| 20 | Twilio | SMS API | Paid (usage) | Active |

---

## Maintenance Notes

**When adding a new third-party service:**
1. Add an entry to this document with all required fields
2. Update the Summary Table
3. Document all environment variables needed
4. List all files that reference the service
5. Update CLAUDE.md if the service affects development workflow

**When removing a service:**
1. Mark as "Deprecated" or "Removed" in this document
2. Remove from Summary Table or update status
3. Clean up any unused environment variables
4. Remove package from requirements.txt if applicable

---

*Last Updated: 2025-12-30*
