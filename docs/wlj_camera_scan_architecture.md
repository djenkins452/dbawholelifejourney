# ==============================================================================
# File: docs/wlj_camera_scan_architecture.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Camera scan feature architecture and security design
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-28
# Last Updated: 2025-12-30
# ==============================================================================

# WLJ Camera Scan Feature - Architecture & Security Design

## Overview

The Camera Scan feature allows WLJ users to capture images using their device camera (or upload from gallery), send them to OpenAI Vision API for identification, and receive contextual suggestions for actions within WLJ modules.

**Privacy-First Design**: Images are processed in-memory and discarded immediately after analysis unless the user explicitly opts to save them.

---

## A) Architecture & Flow

### User Flow (UI States)

```
1. IDLE STATE
   └── User sees "Scan" button in navigation or Quick Actions

2. CONSENT STATE
   └── First-time: Modal explains what happens to their image
   └── User acknowledges: "I understand. Images are processed by AI and not stored."

3. CAMERA STATE
   ├── Camera preview (getUserMedia)
   ├── [Capture] button - takes snapshot
   ├── [Upload] button - fallback for file picker
   └── [Cancel] - returns to previous page

4. PREVIEW STATE
   ├── Shows captured/uploaded image
   ├── [Analyze] - sends to backend
   ├── [Retake] - returns to camera
   └── [Cancel] - discards and exits

5. LOADING STATE
   └── "Analyzing your image..." with spinner
   └── Timeout after 30 seconds with retry option

6. RESULTS STATE
   ├── Shows identified category + confidence
   ├── Shows detected items
   ├── Shows "What would you like to do?" options
   ├── Each option links to appropriate WLJ module
   └── [Scan Another] - returns to camera state

7. ERROR STATE
   ├── User-friendly error message
   ├── [Try Again] - returns to camera
   └── [Cancel] - exits
```

### System Flow Diagram

```
┌──────────────────┐
│   BROWSER        │
│  (JavaScript)    │
└────────┬─────────┘
         │ 1. Camera capture (getUserMedia)
         │ 2. Client-side compression (canvas)
         │ 3. Base64 encode
         │ 4. POST to /scan/analyze/
         ▼
┌──────────────────┐
│   WLJ BACKEND    │
│  (Django View)   │
├──────────────────┤
│ - Auth check     │
│ - CSRF verify    │
│ - Rate limit     │
│ - File validate  │
│   (type, size)   │
│ - Consent check  │
└────────┬─────────┘
         │ 5. Call Vision Service
         ▼
┌──────────────────┐
│ VISION SERVICE   │
│ (services/       │
│  vision.py)      │
├──────────────────┤
│ - Build prompt   │
│ - Call OpenAI    │
│ - Parse response │
│ - Map to actions │
└────────┬─────────┘
         │ 6. OpenAI API call
         ▼
┌──────────────────┐
│   OPENAI API     │
│ (Vision Model)   │
└────────┬─────────┘
         │ 7. JSON response
         ▼
┌──────────────────┐
│   WLJ BACKEND    │
├──────────────────┤
│ - Log request ID │
│ - Build actions  │
│ - Discard image  │
└────────┬─────────┘
         │ 8. JSON response
         ▼
┌──────────────────┐
│   BROWSER        │
│ (Display results)│
└──────────────────┘
```

### Data Handling Rules

| Data Type | Sent to OpenAI | Stored in DB | Logged |
|-----------|----------------|--------------|--------|
| Raw image | Yes (base64) | NO (never by default) | NO |
| Request ID (UUID) | No | YES (ScanLog) | YES |
| Category result | No | YES (ScanLog) | YES |
| Confidence score | No | YES (ScanLog) | YES |
| Detected items | No | YES (ScanLog) | YES |
| User action taken | No | YES (ScanLog) | YES |
| Errors | No | NO | YES (anonymized) |
| Timestamps | No | YES | YES |

---

## B) Security Controls

### 1. Authentication & Authorization
- **LoginRequiredMixin**: All scan views require authenticated user
- **User-scoped data**: All ScanLog entries are tied to request.user
- **AI consent check**: Must have `ai_data_consent=True` in preferences

### 2. CSRF Protection
- Django's built-in CSRF middleware
- All POST requests require valid CSRF token
- AJAX requests include `X-CSRFToken` header

### 3. Rate Limiting
- **Per-user limit**: 30 scans per hour (configurable)
- **Per-IP limit**: 60 scans per hour (shared devices)
- Uses Django cache backend for tracking
- Returns 429 Too Many Requests with retry-after header

### 4. Input Validation
- **MIME type check**: Only `image/jpeg`, `image/png`, `image/webp`
- **File size limit**: Max 10MB (configurable via `SCAN_MAX_IMAGE_MB`)
- **Magic bytes verification**: Checks actual file content, not just extension
- **Reject executables**: No .exe, .php, .js embedded in images

### 5. Image Processing Safety
- Images processed in-memory only
- No filesystem writes (except temp if required by OpenAI library)
- Immediate garbage collection after response
- No image data in server logs

### 6. API Key Security
- OpenAI key from environment variable only
- Never exposed to frontend
- Server-side calls only

### 7. Error Handling
- Never expose internal errors to user
- Correlation IDs for debugging
- Sanitized error messages

---

## C) Environment Variables

```env
# Required
OPENAI_API_KEY=sk-...

# Optional (with defaults)
OPENAI_VISION_MODEL=gpt-4o           # Vision-capable model
SCAN_MAX_IMAGE_MB=10                  # Max upload size
SCAN_RATE_LIMIT_PER_HOUR=30          # Per-user limit
SCAN_RATE_LIMIT_IP_PER_HOUR=60       # Per-IP limit
SCAN_REQUEST_TIMEOUT_SECONDS=30      # OpenAI timeout
```

---

## D) Response Schema (Strict JSON)

```json
{
  "request_id": "uuid-v4-string",
  "top_category": "food|medicine|receipt|document|workout_equipment|supplement|barcode|unknown",
  "confidence": 0.0-1.0,
  "items": [
    {
      "label": "string",
      "details": {
        "key": "value"
      },
      "confidence": 0.0-1.0
    }
  ],
  "safety_notes": ["string"],
  "next_best_actions": [
    {
      "module": "Health.FoodLog|Health.Medicine|Finance.Expense|Journal|Goals|Unknown",
      "question": "string (e.g., 'Log this meal in your Food Log?')",
      "actions": [
        {
          "id": "action_id",
          "label": "string",
          "url": "/health/food/add/?prefill=...",
          "payload_template": {}
        }
      ]
    }
  ]
}
```

---

## E) Decision Mapping

| Category | WLJ Module | Question | Actions |
|----------|------------|----------|---------|
| food | Health.FoodLog | "Log this meal/snack?" | Log meal, Add calories, Skip |
| medicine | Health.Medicine | "Add to your medicines?" | Add medicine, Set reminder, Skip |
| supplement | Health.Medicine | "Add to supplements?" | Add supplement, Set reminder, Skip |
| receipt | Journal | "Save this receipt?" | Add journal note, Skip |
| document | Journal | "Save this document?" | Add to journal, Skip |
| workout_equipment | Health.Fitness | "Log a workout?" | Start workout, Skip |
| barcode | Varies | "What is this product?" | Lookup, Skip |
| unknown | - | "What is this?" | Try again, Upload clearer photo, Skip |

---

## F) Security Checklist (Pre-Production)

### Must Have
- [ ] HTTPS enforced (SECURE_SSL_REDIRECT=True)
- [ ] CSRF protection active
- [ ] Rate limiting configured
- [ ] File size limits enforced
- [ ] MIME type validation
- [ ] Magic bytes verification
- [ ] No raw images in logs
- [ ] AI consent check before processing
- [ ] Request timeout configured
- [ ] Error messages sanitized

### Should Have
- [ ] Content-Security-Policy header for camera
- [ ] Permissions-Policy header for camera access
- [ ] Audit logging for scan requests
- [ ] Abuse detection (unusual patterns)

### Nice to Have
- [ ] Image blur detection (reject blurry images)
- [ ] Duplicate detection (same image within X minutes)
- [ ] Cost monitoring dashboard

---

## G) Why Each Control Matters

| Control | Attack Prevented | Real-World Example |
|---------|-----------------|-------------------|
| Auth required | Unauthorized access | Attacker scanning to find account info |
| Rate limiting | Cost abuse, DoS | Bot making thousands of API calls |
| File size limit | Resource exhaustion | 1GB image crashing server |
| MIME validation | Malicious upload | PHP shell disguised as image |
| Magic bytes check | Bypass attempts | Changed extension from .exe to .jpg |
| CSRF token | Cross-site request forgery | Malicious site triggering scans |
| AI consent | Privacy compliance | Legal liability for data processing |
| No image storage | Data breach risk | Stolen DB exposing personal photos |
| Timeout | Resource hanging | Slow API locking up workers |
| Sanitized errors | Information disclosure | Stack traces revealing code paths |

---

## H) File Structure

```
apps/scan/
├── __init__.py
├── apps.py
├── models.py              # ScanLog model
├── views.py               # Scan views
├── urls.py                # URL patterns
├── forms.py               # Validation forms
├── services/
│   ├── __init__.py
│   └── vision.py          # OpenAI Vision service
├── tests/
│   ├── __init__.py
│   ├── test_views.py      # View tests
│   ├── test_vision.py     # Service tests
│   └── test_security.py   # Security tests
└── templates/scan/        # (in main templates dir)
    ├── scan_page.html     # Main scan UI
    └── partials/
        └── results.html   # Results partial

static/js/
└── scan.js                # Camera capture logic
```

---

*Document Version: 1.0*
*Created: 2025-12-28*
*Author: Claude Code for WLJ*
