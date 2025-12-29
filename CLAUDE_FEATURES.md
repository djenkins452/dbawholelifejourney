# CLAUDE_FEATURES.md
# ==============================================================================
# File: CLAUDE_FEATURES.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Detailed feature documentation for reference when needed
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-28
# Last Updated: 2025-12-29
# ==============================================================================

# Feature Documentation

This file contains detailed documentation for major features.
Reference this file when working on specific features.
For core project context, see `CLAUDE.md`.

---

## Table of Contents
1. [Onboarding Wizard](#onboarding-wizard)
2. [Context-Aware Help System](#context-aware-help-system)
3. [What's New Feature](#whats-new-feature)
4. [Dashboard AI Personal Assistant](#dashboard-ai-personal-assistant)
5. [Nutrition/Food Tracking](#nutritionfood-tracking)
6. [Medicine Tracking](#medicine-tracking)
7. [Camera Scan Feature](#camera-scan-feature)
8. [Biometric Login](#biometric-login)

---

## Onboarding Wizard

### Overview
New users are guided through a 6-step onboarding wizard before accessing the app. The wizard collects preferences and personalizes the experience.

### Flow
1. **User signs up** → `UserPreferences` created with `has_completed_onboarding = False`
2. **User accepts terms** → Redirected to onboarding wizard
3. **Middleware enforces** → Until `has_completed_onboarding = True`, user is redirected to wizard
4. **User completes wizard** → Flag set to `True`, user proceeds to dashboard

### Steps (6 total)
| Step | URL | Saves |
|------|-----|-------|
| Welcome | `/user/onboarding/start/` | Nothing |
| Theme | `/user/onboarding/step/theme/` | `theme` |
| Modules | `/user/onboarding/step/modules/` | Module toggles |
| AI | `/user/onboarding/step/ai/` | `ai_enabled`, `ai_coaching_style` |
| Location | `/user/onboarding/step/location/` | `timezone`, `location_city`, `location_country` |
| Complete | `/user/onboarding/step/complete/` | `has_completed_onboarding = True` |

### Key Files
- `apps/users/views.py` - `OnboardingWizardView`, `ONBOARDING_STEPS` configuration
- `apps/users/middleware.py` - `TermsAcceptanceMiddleware` enforces onboarding
- `templates/users/onboarding_wizard.html` - Wizard UI template
- `apps/users/tests/test_onboarding_wizard.py` - Comprehensive tests (30+ tests)

### Testing the Wizard
- **New user**: Sign up → Accept terms → Wizard starts
- **Reset existing user**: Set `has_completed_onboarding = False` in Django Admin
- **Direct access**: Visit `/user/onboarding/start/` while logged in

### URL Note
The users app is mounted at `/user/` (singular), not `/users/`.

---

## Context-Aware Help System

### Overview
The application has a "?" help icon that provides context-aware help. This is authoritative user guidance with exact, step-by-step instructions.

### Core Principle: HELP_CONTEXT_ID
Every page declares a stable identifier. The help system uses this to show the exact relevant documentation.

**How it works:**
1. User clicks "?" icon
2. System reads the page's `HELP_CONTEXT_ID`
3. Looks up that ID in the help index
4. Opens the exact matching help section

### HELP_CONTEXT_ID Naming Convention
Format: `{APP}_{SCREEN}` or `{APP}_{ENTITY}_{ACTION}`

Examples:
- `DASHBOARD_HOME`
- `HEALTH_ROOT`
- `HEALTH_WORKOUT_CREATE`
- `JOURNAL_ENTRY_LIST`
- `SETTINGS_PREFERENCES`

### Implementation Details
Each page exposes its context via:
- Django template variable: `{% with help_context_id="HEALTH_ROOT" %}`
- HTML data attribute: `data-help-context="HEALTH_ROOT"`
- JavaScript variable: `window.HELP_CONTEXT_ID = "HEALTH_ROOT"`

### Documentation File Structure
```
docs/
├── help/
│   ├── index.json          # Maps HELP_CONTEXT_ID → file + HELP_ID
│   ├── dashboard.md        # Dashboard help content
│   ├── health.md           # Health app help content
│   └── ...
```

### Help Entry Format
```markdown
## [HELP_ID: health-log-workout]
**Title:** How to Log a Workout
**Context:** HEALTH_WORKOUT_CREATE screen
**Description:** Record your exercise activities.

### Steps
1. Click "Health" in the left navigation menu.
2. Click the "Log Workout" button.
3. Select a workout type from the dropdown.
4. Enter the duration in minutes.
5. Click "Save" to record your workout.
```

### Writing Rules
1. Start each step with an action verb (Click, Enter, Select)
2. Reference exact UI labels in quotes
3. Be exact—a chatbot will read these verbatim
4. No vague text, no summaries

---

## What's New Feature

### Overview
Informs users of new features and updates since their last visit via a popup modal.

### How It Works
1. **User logs in** → JavaScript calls `/api/whats-new/check/`
2. **API returns unseen notes** → If `has_unseen: true`, modal displays
3. **User dismisses modal** → POST to `/api/whats-new/dismiss/`
4. **Next login** → Only shows notes created after last dismissal

### Models (`apps/core/models.py`)
| Model | Description |
|-------|-------------|
| `ReleaseNote` | Entry (title, description, type, release_date, is_major) |
| `UserReleaseNoteView` | Tracks when user last dismissed popup |

### Entry Types
| Type | Icon | Use For |
|------|------|---------|
| `feature` | ✨ | New functionality |
| `fix` | 🔧 | Bug fixes |
| `enhancement` | 🚀 | Improvements |
| `security` | 🔒 | Security updates |

### URL Routes
| Route | View | Description |
|-------|------|-------------|
| `/whats-new/` | `WhatsNewListView` | Full page view |
| `/api/whats-new/check/` | `WhatsNewCheckView` | JSON API - returns unseen |
| `/api/whats-new/dismiss/` | `WhatsNewDismissView` | JSON API - marks seen |

### Adding a Release Note (Django Admin)
1. Navigate to Django Admin → Core → Release Notes
2. Click "Add Release Note"
3. Fill in: Title, Description, Entry Type, Release Date
4. Set `is_published = True`

### Key Files
- `apps/core/models.py` - ReleaseNote, UserReleaseNoteView
- `apps/core/views.py` - WhatsNewCheckView, WhatsNewDismissView, WhatsNewListView
- `templates/components/whats_new_modal.html` - Popup modal
- `static/js/whats_new.js` - Client-side logic

---

## Dashboard AI Personal Assistant

### Overview
A comprehensive personal life assistant that helps users live the life they said they want to live. This is NOT a chatbot - it anchors all guidance to user's stated Purpose, Goals, intentions, and commitments.

### Core Philosophy
- **Faith-first prioritization** (for users with faith enabled): Faith → Purpose → Long-term goals → Commitments → Maintenance → Optional
- **Honors user's journey** - doesn't lecture or give unsolicited advice
- **Celebrates wins** and progress
- **Gentle accountability** - nudges without nagging
- **Personalized reflection prompts** for journaling

### What It Does
1. **Daily State Assessment** - Evaluates user's current state across all dimensions (journal, tasks, goals, faith, health)
2. **Priority Generation** - Creates daily priorities following strict ordering based on what matters most to the user
3. **Trend Analysis** - Weekly/monthly analysis of patterns and progress
4. **Drift Detection** - Identifies when behavior drifts from stated intentions
5. **Reflection Prompts** - Generates personalized journaling prompts based on context
6. **Celebration** - Recognizes completed goals, maintained streaks, answered prayers
7. **Conversational Interface** - Answers questions about user's own journey and data

### What It Is NOT
- NOT a generic chatbot
- Does NOT give unsolicited advice
- Does NOT lecture or moralize
- Does NOT claim to know what's best for the user
- Does NOT suggest what user "should" want

### Models (`apps/ai/models.py`)
| Model | Description |
|-------|-------------|
| `AssistantConversation` | Conversation session with session type (daily_checkin, reflection, planning, etc.) |
| `AssistantMessage` | Individual message with role (user, assistant, system) |
| `UserStateSnapshot` | Daily snapshot of user state across all dimensions |
| `DailyPriority` | AI-suggested priority with source tracking |
| `TrendAnalysis` | Weekly/monthly trend analysis with patterns |
| `ReflectionPromptQueue` | Personalized reflection prompts |

### URL Routes (`/assistant/`)
| Route | View | Description |
|-------|------|-------------|
| `/assistant/` | `AssistantDashboardView` | Full-page assistant UI |
| `/assistant/api/opening/` | `AssistantOpeningView` | Daily check-in message |
| `/assistant/api/chat/` | `AssistantChatView` | Send/receive messages |
| `/assistant/api/history/` | `ConversationHistoryView` | Get conversation history |
| `/assistant/api/feedback/` | `MessageFeedbackView` | Submit message feedback |
| `/assistant/api/priorities/` | `DailyPrioritiesView` | Get/refresh priorities |
| `/assistant/api/priorities/<id>/complete/` | `PriorityCompleteView` | Mark priority complete |
| `/assistant/api/priorities/<id>/dismiss/` | `PriorityDismissView` | Dismiss priority |
| `/assistant/api/state/` | `StateAssessmentView` | Get current state |
| `/assistant/api/analysis/weekly/` | `WeeklyAnalysisView` | Weekly trends |
| `/assistant/api/analysis/monthly/` | `MonthlyAnalysisView` | Monthly trends |
| `/assistant/api/analysis/drift/` | `DriftDetectionView` | Drift from intentions |
| `/assistant/api/analysis/goals/` | `GoalProgressView` | Goal progress report |
| `/assistant/api/reflection/` | `ReflectionPromptView` | Get reflection prompt |
| `/assistant/api/reflection/used/` | `ReflectionPromptUsedView` | Mark prompt used |

### Key Services
- `apps/ai/personal_assistant.py` - Core personal assistant logic (~800 lines)
  - State assessment across all dimensions
  - Priority generation with faith-first ordering
  - Opening message generation
  - Conversation management with context

- `apps/ai/trend_tracking.py` - Trend analysis service (~400 lines)
  - Weekly/monthly analysis generation
  - Pattern detection in user behavior
  - Drift detection from stated intentions
  - Goal progress reporting

### Prerequisites
- User must have AI enabled in Preferences (`ai_enabled = True`)
- User must have AI data consent (`ai_data_consent = True`)
- Faith features only shown if `faith_enabled = True`

### Key Files
- `apps/ai/models.py` - 6 new models for Dashboard AI
- `apps/ai/personal_assistant.py` - Core service
- `apps/ai/trend_tracking.py` - Trend analysis
- `apps/ai/views.py` - 16 API endpoints
- `apps/ai/urls.py` - URL configuration
- `templates/ai/assistant_dashboard.html` - Full-page UI

### Tests
`apps/ai/tests/test_personal_assistant.py` - 45 tests

---

## Nutrition/Food Tracking

### Overview
Log food consumption, track macros, set nutrition goals, view daily/historical stats.

### Models (`apps/health/models.py`)
| Model | Description |
|-------|-------------|
| `FoodItem` | Global food library (USDA, barcode, AI) |
| `CustomFood` | User-created foods/recipes |
| `FoodEntry` | Individual food log entry |
| `DailyNutritionSummary` | Aggregated daily totals |
| `NutritionGoals` | User's calorie/macro targets |

### URL Routes (`/health/nutrition/`)
| Route | View | Description |
|-------|------|-------------|
| `/nutrition/` | `NutritionHomeView` | Daily dashboard |
| `/nutrition/add/` | `FoodEntryCreateView` | Full food entry form |
| `/nutrition/quick-add/` | `QuickAddFoodView` | Simplified logging |
| `/nutrition/history/` | `FoodHistoryView` | Historical log |
| `/nutrition/stats/` | `NutritionStatsView` | Trends |
| `/nutrition/goals/` | `NutritionGoalsView` | Set goals |
| `/nutrition/foods/` | `CustomFoodListView` | User's custom foods |

### Key Features
- **Meal Types**: Breakfast, Lunch, Dinner, Snack
- **Entry Sources**: Manual, Barcode, Camera, Voice, Quick Add
- **Location Context**: Home, Restaurant, Work, Travel, Other
- **Eating Pace**: Rushed, Normal, Slow/Mindful
- **Hunger/Fullness Tracking**: 1-5 scale
- **Net Carbs**: Auto-calculated (carbs - fiber)
- **Macro Percentages**: Auto-calculated in DailyNutritionSummary

### Tests
`apps/health/tests/test_nutrition.py` - 80 tests

---

## Medicine Tracking

### Overview
Daily tracker, adherence stats, PRN support, refill tracking, dashboard integration.

### Key Features
- Medicine Master List (name, dose, frequency, schedules, doctor, pharmacy)
- Daily Tracker with one-tap check-off
- Missed/Overdue detection with configurable grace period
- History & Adherence views
- Quick Look for screenshots
- Refill alerts
- Pause/resume without losing history

### Models
- `Medicine` - The medication itself
- `MedicineSchedule` - When to take it (days, times)
- `MedicineLog` - Individual dose records (taken, missed, skipped)

### Dashboard Integration
- Today's Medicine Schedule with status badges
- Medicine adherence rate in AI insights
- Refill alerts as nudges

### Tests
`apps/health/tests/test_medicine.py` - 77 tests

---

## Camera Scan Feature

### Overview
OpenAI Vision API integration for scanning items and routing to appropriate modules.

### Categories Detected
- food, medicine, supplement, receipt, document
- workout equipment, barcode, inventory_item
- recipe, pet, maintenance

### Key Features
- Browser camera capture (getUserMedia)
- File upload fallback
- Multi-format support (JPEG, PNG, WebP)
- Contextual action suggestions
- Privacy-first (no permanent image storage)
- Rate limiting
- Magic bytes validation

### Architecture
See `docs/CAMERA_SCAN_ARCHITECTURE.md` for full details.

### Key Files
- `apps/scan/views.py` - CameraScanView
- `apps/scan/services/vision.py` - OpenAI Vision integration
- `templates/scan/camera.html` - Camera UI
- `static/js/camera.js` - Camera JavaScript

### Tests
`apps/scan/tests/` - 70 tests

---

## Biometric Login

### Overview
WebAuthn-based biometric login for mobile devices (Face ID, Touch ID, Windows Hello).

### Models
`WebAuthnCredential` - Stores device credentials (credential_id, public_key, sign_count, device_name)

### Views
| View | Description |
|------|-------------|
| `BiometricCheckView` | Login page checks if biometric available |
| `BiometricCredentialsView` | List user's registered devices |
| `BiometricRegisterBeginView` | Start device registration |
| `BiometricRegisterCompleteView` | Complete device registration |
| `BiometricLoginBeginView` | Start passwordless auth |
| `BiometricLoginCompleteView` | Complete passwordless auth |
| `BiometricDeleteCredentialView` | Remove a device |

### User Preference
`biometric_login_enabled` in UserPreferences - toggle in Security section of Preferences page.

### Key Files
- `apps/users/models.py` - WebAuthnCredential
- `apps/users/views.py` - 6 biometric views
- `templates/account/login.html` - "Use Face ID / Touch ID" button
- `static/js/biometric.js` - WebAuthn API handling

### Tests
32 tests in `apps/users/tests/`

---

*Last updated: 2025-12-29*
