# ==============================================================================
# File: docs/wlj_claude_features.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Detailed feature documentation for reference when needed
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-28
# Last Updated: 2025-12-31
# ==============================================================================

# WLJ Feature Documentation

This file contains detailed documentation for major features.
Reference this file when working on specific features.
For core project context, see `CLAUDE.md` (project root).

---

## Table of Contents
1. [Navigation System](#navigation-system)
2. [Onboarding Wizard](#onboarding-wizard)
3. [Context-Aware Help System](#context-aware-help-system)
4. [What's New Feature](#whats-new-feature)
5. [Dashboard AI Personal Assistant](#dashboard-ai-personal-assistant)
6. [Nutrition/Food Tracking](#nutritionfood-tracking)
7. [Weight & Nutrition Goals](#weight--nutrition-goals)
8. [Medicine Tracking](#medicine-tracking)
9. [Vitals Tracking](#vitals-tracking)
10. [Medical Providers](#medical-providers)
11. [Camera Scan Feature](#camera-scan-feature)
12. [Biometric Login](#biometric-login)
13. [Dashboard Tile Shortcuts](#dashboard-tile-shortcuts)
14. [SMS Text Notifications](#sms-text-notifications)
15. [Task Management](#task-management)
16. [Memory Verse](#memory-verse)
17. [Significant Events](#significant-events)

---

## Navigation System

### Overview
The main navigation features a cascading dropdown menu system that allows users to jump directly to any page without visiting the module home first.

### Desktop Behavior
- Hover over menu items to reveal dropdown menus
- Dropdowns appear with smooth fade-in animation
- Clicking a dropdown item navigates to that page
- Clicking outside closes all dropdowns
- ESC key closes all open menus

### Mobile Behavior
- Tap on menu items to toggle dropdown visibility
- Dropdowns expand in-place as accordion menus
- Chevron rotates to indicate open/closed state
- Works well with touch devices

### Menu Structure

| Module | Type | Items |
|--------|------|-------|
| Dashboard | Direct link | Home only |
| Journal | Dropdown | Home, New Entry, All Entries, Book View, Prompts, Tags |
| Faith | Dropdown | Home, Today's Verse, Saved Scripture, Prayers, Milestones, Reflections |
| Health | Mega menu | 5 columns: Vitals, Medicine, Fitness, Nutrition, Providers |
| Life | Two-column | Home, Calendar, Projects, Tasks, Inventory, Pets, Recipes, Maintenance, Documents, Significant Events |
| Purpose | Dropdown | Home, Annual Direction, Goals, Intentions, Reflections |
| Assistant | Direct link | Dashboard only |

### Health Mega Menu Columns
- **Vitals:** Health Home, Weight, Heart Rate, Blood Pressure, Glucose, Blood Oxygen
- **Medicine:** Today's Medicines, All Medicines, History, Adherence
- **Fitness:** Fitness Home, Workouts, Templates, Personal Records
- **Nutrition:** Nutrition Home, Food History, Statistics, Goals
- **Providers:** Medical Providers, Fasting

### Key Files
- `templates/components/navigation.html` - Navigation template with dropdown structure
- `static/css/main.css` - Dropdown and mega menu styles (lines 532-756)
- `static/js/main.js` - Dropdown toggle logic, click handlers, keyboard support

### CSS Classes
| Class | Purpose |
|-------|---------|
| `.nav-dropdown` | Container for menu item with dropdown |
| `.nav-dropdown-toggle` | Button that triggers dropdown |
| `.nav-dropdown-menu` | The dropdown panel |
| `.nav-dropdown-item` | Link within dropdown |
| `.nav-mega-menu` | Multi-column dropdown variant |
| `.nav-mega-columns` | Flexbox container for columns |
| `.nav-mega-column` | Single column within mega menu |
| `.nav-mega-heading` | Column header text |

### JavaScript Functions
- `toggleNavDropdown(dropdown)` - Toggle a specific dropdown's visibility
- `closeAllNavDropdowns()` - Close all open dropdowns
- Click handlers for outside clicks
- ESC key handler in accessibility section

### Accessibility Features
- Full ARIA support (`aria-expanded`, `aria-haspopup`)
- Keyboard navigation (ESC closes all menus)
- Focus-visible outlines
- Screen reader compatible structure

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
| AI | `/user/onboarding/step/ai/` | `ai_enabled`, `ai_data_consent`, `ai_coaching_style`, `personal_assistant_enabled`, `personal_assistant_consent` |
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
4. **Next login** → Only shows notes with `release_date` after last dismissal

### Popup Cadence
The popup shows when there are unseen release notes. "Unseen" is determined by:
- Notes where `release_date > last_seen_date` (notes from days after dismissal), OR
- Notes where `release_date = last_seen_date AND created_at > last_viewed_at` (notes added same day but after dismissal)

**Note:** The popup uses `release_date` (the logical feature release date) rather than `created_at` (when the DB record was created). This ensures notes added via data migrations display correctly, since their `release_date` represents when the feature was actually deployed.

### User Preference
Users can disable the popup via Preferences → Notifications → "Show What's New popup" checkbox.

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
A task-focused personal assistant that helps users get things done and stay aligned with their goals. This is NOT a chatbot or cheerleader - it focuses on ACTION and what needs attention.

### Core Philosophy
- **Action-focused** - Surfaces what needs attention, not what's been accomplished
- **Faith-first prioritization** (for users with faith enabled): Faith → Purpose → Long-term goals → Commitments → Maintenance → Optional
- **Direct and helpful** - Provides clear next steps without excessive praise
- **Positive feedback on dashboard** - Celebrations belong on the main dashboard, not the assistant
- **Personalized reflection prompts** for journaling

### What It Does
1. **Daily State Assessment** - Focuses on gaps and action items (overdue tasks, journal gaps, medicine adherence issues)
2. **Priority Generation** - Creates daily priorities following strict ordering based on what matters most
   - Completed priorities are preserved when refreshing (won't be deleted/regenerated)
   - Shows brief positive feedback when priorities are completed
   - Tracks completion history for analytics via `DailyPriority.get_completion_stats()`
3. **Trend Analysis** - Weekly/monthly analysis of patterns and progress
4. **Drift Detection** - Identifies when behavior drifts from stated intentions
5. **Reflection Prompts** - Generates personalized journaling prompts based on context
6. **Action Items** - Surfaces things that need attention today with direct action links
7. **Conversational Interface** - Answers questions about priorities and how to tackle goals

### What It Is NOT
- NOT a cheerleader or motivational speaker
- NOT focused on celebrating accomplishments (that's the dashboard's job)
- Does NOT use excessive praise or superlatives
- Does NOT lecture or moralize
- Does NOT claim to know what's best for the user

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

### Prerequisites (Personal Assistant Module)
The Personal Assistant is a separate module that requires:

1. **AI Features Enabled** (`ai_enabled = True`)
2. **AI Data Consent** (`ai_data_consent = True`)
3. **Personal Assistant Enabled** (`personal_assistant_enabled = True`)
4. **Personal Assistant Consent** (`personal_assistant_consent = True`)

### AI Caching Strategy (Optimized 2025-12-31)

Multiple levels of caching reduce API costs and improve performance:

| Layer | What's Cached | TTL | Invalidation |
|-------|--------------|-----|--------------|
| **System Prompt** | Base + coaching style + faith context | 1 hour | On CoachingStyle or AIPromptConfig save |
| **Coaching Styles** | Active coaching styles list | 1 hour | On CoachingStyle save |
| **Prompt Configs** | AIPromptConfig per type | 1 hour | On AIPromptConfig save |
| **Daily Insight** | Generated dashboard message | End of day | On coaching style change |
| **Weekly Summary** | Journal week summary | 24 hours | On coaching style change |
| **User State Snapshot** | Daily user state | 1 day | force_refresh=True |
| **Instance User Data** | Per-request data gathering | Per-instance | New DashboardAI instance |

**Key Files:**
- `apps/ai/services.py` - System prompt caching with `cache.set()`
- `apps/ai/dashboard_ai.py` - Instance-level caching with `get_user_data()` / `get_reflection_data()`
- `apps/ai/models.py` - `invalidate_system_prompt_cache()` helper

**Cache Keys:**
- `system_prompt_{coaching_style}_{faith_enabled}` - Cached system prompts
- `coaching_styles_all` - All active coaching styles
- `coaching_style_{key}` - Individual style by key
- `ai_prompt_config_{prompt_type}` - Prompt configs by type

For full assessment, see: `docs/wlj_ai_assessment.md`

This separation allows users to:
- Enable general AI features (insights, camera scan) without the Personal Assistant
- Enable the Personal Assistant only if AI features are already enabled
- Provide separate consent for the Assistant's deeper data access

### Personal Assistant Module Fields (`UserPreferences`)
| Field | Type | Description |
|-------|------|-------------|
| `personal_assistant_enabled` | Boolean | Enable Personal Assistant module |
| `personal_assistant_consent` | Boolean | Consent for deeper data access |
| `personal_assistant_consent_date` | DateTime | When consent was given |

### Where Configured
- **Onboarding Wizard** - AI step includes Personal Assistant toggle + consent
- **Preferences Page** - Personal Assistant section under AI Features
- **Navigation** - Assistant link only shown when fully enabled and consented

### Access Control (`AssistantMixin.check_personal_assistant_enabled()`)
All Personal Assistant API endpoints check for full access:
1. AI Features enabled
2. AI Data Consent given
3. Personal Assistant module enabled
4. Personal Assistant consent given

Faith features only shown if `faith_enabled = True`

### Key Files
- `apps/ai/models.py` - 6 new models for Dashboard AI
- `apps/ai/personal_assistant.py` - Core service
- `apps/ai/trend_tracking.py` - Trend analysis
- `apps/ai/dashboard_ai.py` - Dashboard AI insights and context gathering
- `apps/ai/services.py` - Core AI service for OpenAI API calls
- `apps/ai/views.py` - 16 API endpoints
- `apps/ai/urls.py` - URL configuration
- `templates/ai/assistant_dashboard.html` - Full-page UI

### Comprehensive AI Context (as of 2025-12-31)

The AI receives a complete picture of the user's life to generate personalized insights:

**Purpose Module Data:**
| Data | Source | Description |
|------|--------|-------------|
| Word of Year | `AnnualDirection` | User's single-word focus for the year |
| Annual Theme | `AnnualDirection` | Expanded theme description |
| Anchor Scripture | `AnnualDirection` | Scripture verse supporting the theme |
| Active Intentions | `ChangeIntention` | Identity-based behavior changes |
| Life Goals | `LifeGoal` | Goals with domain names and "why it matters" |

**Faith Module Data:**
| Data | Source | Description |
|------|--------|-------------|
| Active Prayers | `PrayerRequest` | Count of unanswered prayers |
| Answered Prayers | `PrayerRequest` | Count answered in last 30 days |
| Memory Verse | `SavedVerse` | Currently memorizing Scripture |
| Scripture Study | `SavedVerse` | Recent verses user is studying |
| Faith Milestones | `FaithMilestone` | Spiritual journey marker count |

**Life Module Data:**
| Data | Source | Description |
|------|--------|-------------|
| Tasks Today | `Task` | Due today, not completed |
| Overdue Tasks | `Task` | Past due, needs attention |
| Active Projects | `Project` | Status = 'active' |
| Priority Projects | `Project` | Priority = 'now' with progress % |
| Events Today | `LifeEvent` | Calendar events for today |

**Health Module Data:**
| Data | Source | Description |
|------|--------|-------------|
| Weight Trend | `WeightEntry` | up/down/stable based on last 5 entries |
| Current Weight | `WeightEntry` | Most recent weight in lbs |
| Weight Goal | `UserPreferences` | Target weight and remaining lbs |
| Fasting Status | `FastingWindow` | Active fast with hours elapsed |
| Calories Today | `DailyNutritionSummary` | Consumed vs remaining |
| Workouts Week | `WorkoutSession` | Count in last 7 days |
| Days Since Workout | `WorkoutSession` | Gap since last workout |
| Personal Records | `PersonalRecord` | PRs in last 30 days |
| Medicine Adherence | `MedicineLog` | Percentage this week |
| Refills Needed | `Medicine` | Below refill threshold |

**Journal Data:**
| Data | Source | Description |
|------|--------|-------------|
| Entries This Week | `JournalEntry` | Count in last 7 days |
| Last Journal Date | `JournalEntry` | Most recent entry date |
| Journal Streak | Calculated | Consecutive days journaling |

### How Context Is Used

The AI builds context into the prompt:
```
Based on this user's comprehensive life data:
- Word of the Year: 'FOCUS'
- Annual Theme: Being intentional about time and energy
- Goal (Health): Lose 20 pounds
- 3 tasks due today
- Weight trending down recently
- Memorizing: John 3:16
...

Generate a personalized, meaningful message for their dashboard.
Consider their Word of the Year, goals, and current progress.
```

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
- **Quick Edit/Delete**: Edit and Delete buttons on nutrition home for each entry
- **All Nutritional Fields Optional**: Can log food without knowing exact macros

### Camera Scan Integration
Food entries can be pre-filled from camera scans. See [Camera Scan Feature](#camera-scan-feature) for details.

### Tests
`apps/health/tests/test_nutrition.py` - 81 tests

---

## Weight & Nutrition Goals

### Overview
Personal weight and nutrition goal tracking with progress display on the dashboard. Users can set a target weight (with optional deadline) and daily macro targets, then track their progress over time.

### Setting Goals (Preferences Page)
Access via **Settings → Preferences → Weight & Nutrition Goals** (only visible when Health module is enabled).

**Weight Goal:**
- Target Weight - Your goal weight (e.g., 180)
- Unit - Pounds (lb) or Kilograms (kg)
- Target Date - Optional deadline for reaching your goal

**Nutrition Goals:**
- Daily Calorie Goal - Target daily caloric intake (e.g., 2000)
- Macro Split - Percentage of calories from each macro:
  - Protein % (e.g., 30%)
  - Carbs % (e.g., 40%)
  - Fat % (e.g., 30%)
  - Must total 100%
- Preset Buttons - Balanced, High Protein, Low Carb, Keto

### Dashboard Progress Display

**Health Tile:**
- Shows current weight and progress bar toward goal
- Displays "X.X lb to go" or "X.X kg to go"
- When goal reached: "Goal reached!"

**Today's Nutrition Section:**
- Calorie summary: consumed / goal with remaining
- Macro progress bars for Protein, Carbs, Fat
- Shows current grams vs target grams

### Progress Calculation Logic

**Weight Progress:**
- Compares current weight to goal weight
- Uses first weight entry as starting point
- Calculates percentage progress
- Determines if user needs to lose or gain

**Nutrition Progress:**
- Aggregates today's food entries
- Converts macro percentages to gram targets:
  - Protein: `(calories × percent) / 4` (4 cal/g)
  - Carbs: `(calories × percent) / 4` (4 cal/g)
  - Fat: `(calories × percent) / 9` (9 cal/g)
- Calculates progress percentage for each macro

### Model Fields (UserPreferences)
```python
# Weight Goals
weight_goal = DecimalField(max_digits=5, decimal_places=1, null=True)
weight_goal_unit = CharField(choices=[("lb", "Pounds"), ("kg", "Kilograms")], default="lb")
weight_goal_target_date = DateField(null=True)

# Nutrition Goals
daily_calorie_goal = PositiveIntegerField(null=True)
protein_percentage = PositiveSmallIntegerField(null=True)
carbs_percentage = PositiveSmallIntegerField(null=True)
fat_percentage = PositiveSmallIntegerField(null=True)
```

### Key Methods (UserPreferences)
- `has_weight_goal` - Property: True if weight_goal is set
- `has_nutrition_goals` - Property: True if daily_calorie_goal is set
- `macro_percentages_valid` - Property: True if macros sum to 100%
- `get_weight_progress()` - Returns dict with progress info
- `get_nutrition_progress(date)` - Returns dict with today's nutrition progress

### Key Files
- `apps/users/models.py` - Goal fields and progress methods
- `apps/users/forms.py` - Goal fields with validation
- `templates/users/preferences.html` - Goals section in preferences
- `apps/dashboard/views.py` - Progress data for dashboard
- `templates/dashboard/home.html` - Health tile and nutrition section
- `static/css/dashboard.css` - Progress bar styles

### Validation
- Macro percentages must sum to 100% (enforced in form)
- All fields are optional (goals are opt-in)
- Weight goal unit affects how progress is calculated

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
- Refill alerts with request tracking
- Pause/resume without losing history

### Refill Request Status (Added 2025-12-29)
Users can mark a medicine as "refill requested" to track that they've already called in/submitted a refill:

1. When supply is low, medicine detail page shows "Request Refill" button
2. Clicking it sets `refill_requested=True` and `refill_requested_at` timestamp
3. Dashboard shows "Refill Requested" status instead of "needs refill"
4. When refill arrives, user clicks "Refill Received" to clear the status

**Fields on Medicine model:**
- `refill_requested` (Boolean, default False)
- `refill_requested_at` (DateTime, nullable)

**Methods:**
- `medicine.request_refill()` - Sets refill as requested
- `medicine.clear_refill_request()` - Clears after refill received
- `medicine.refill_status` - Returns 'requested', 'needed', or None

### Models
- `Medicine` - The medication itself (includes refill_requested fields)
- `MedicineSchedule` - When to take it (days, times)
- `MedicineLog` - Individual dose records (taken, missed, skipped)

### Dashboard Integration
- Today's Medicine Schedule with status badges
- Medicine adherence rate in AI insights
- Refill alerts as nudges (differentiates "needs refill" vs "refill requested")

### Timezone Handling (Fixed 2025-12-30)
The `taken_at` time on medicine logs is now displayed in the user's configured timezone. This fixes an issue where medicines taken on time appeared as "Taken Late" because the UTC time was being shown instead of local time.

### Tests
`apps/health/tests/test_medicine.py` - 86 tests

---

## Vitals Tracking

### Overview
Track blood pressure and blood oxygen (SpO2) readings with automatic categorization.

### Blood Pressure Tracking (Added 2025-12-29)
Records systolic and diastolic pressure with context.

**Model: `BloodPressureEntry`**
- `systolic` - Top number (mmHg)
- `diastolic` - Bottom number (mmHg)
- `pulse` - Optional pulse reading
- `context` - When measured (resting, morning, evening, post_exercise, stressed, relaxed, other)
- `arm` - Which arm (left, right)
- `position` - Body position (sitting, standing, lying)
- `recorded_at` - Timestamp
- `notes` - Optional notes

**Categorization (AHA Guidelines):**
- Normal: <120/<80
- Elevated: 120-129/<80
- High Stage 1: 130-139/80-89
- High Stage 2: ≥140/≥90
- Crisis: ≥180/≥120

**URLs:**
- `/health/blood-pressure/` - List view
- `/health/blood-pressure/log/` - Create
- `/health/blood-pressure/<pk>/edit/` - Update
- `/health/blood-pressure/<pk>/delete/` - Delete

### Blood Oxygen Tracking (Added 2025-12-29)
Records SpO2 saturation percentage with context.

**Model: `BloodOxygenEntry`**
- `spo2` - Oxygen saturation percentage
- `pulse` - Optional pulse reading
- `context` - When measured (resting, morning, active, post_exercise, sleeping, illness, other)
- `measurement_method` - Device type (finger, wrist, ear, other)
- `recorded_at` - Timestamp
- `notes` - Optional notes

**Categorization:**
- Normal: ≥95%
- Low: 90-94%
- Concerning: 85-89%
- Critical: <85%

**URLs:**
- `/health/blood-oxygen/` - List view
- `/health/blood-oxygen/log/` - Create
- `/health/blood-oxygen/<pk>/edit/` - Update
- `/health/blood-oxygen/<pk>/delete/` - Delete

### Health Home Integration
Both vitals appear as cards on the Health home page (`/health/`) with:
- Latest reading
- Category badge (color-coded)
- Average stats
- Links to full history

---

## Medical Providers

### Overview
Store contact information for doctors, clinics, and other healthcare providers with AI-assisted lookup and staff tracking.

### Key Features
- **Provider Contact Management** - Store comprehensive contact info for any healthcare provider
- **AI-Powered Lookup** - Enter name/location, AI finds contact details
- **Staff Tracking** - Add PAs, nurses, and other supporting staff
- **Primary Care Flag** - Mark your main doctor for quick access
- **Patient Portal Storage** - Store portal URLs and usernames

### Models

**`MedicalProvider`** - Healthcare provider contact information
| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField | Provider or practice name |
| `specialty` | CharField | 27 specialty choices (primary_care, cardiology, dentist, etc.) |
| `credentials` | CharField | MD, DO, DDS, PA-C, etc. |
| `phone`, `phone_alt`, `fax` | CharField | Contact numbers |
| `email`, `website` | EmailField, URLField | Online contact |
| `address_line1`, `address_line2`, `city`, `state`, `postal_code`, `country` | CharFields | Full address |
| `portal_url`, `portal_username` | URLField, CharField | Patient portal access |
| `npi_number` | CharField | National Provider Identifier |
| `accepts_insurance`, `insurance_notes` | Boolean, TextField | Insurance info |
| `is_primary` | Boolean | Mark as primary care provider |
| `notes` | TextField | Personal notes |
| `ai_lookup_completed`, `ai_lookup_at` | Boolean, DateTime | AI lookup tracking |

**`ProviderStaff`** - Supporting staff members
| Field | Type | Description |
|-------|------|-------------|
| `provider` | ForeignKey | Parent provider (CASCADE delete) |
| `name` | CharField | Staff member name |
| `role` | CharField | 12 role choices (physician_assistant, registered_nurse, etc.) |
| `title` | CharField | Job title |
| `phone_extension`, `direct_phone` | CharField | Contact numbers |
| `email` | EmailField | Direct email |
| `notes` | TextField | Notes |

### URL Routes (`/health/providers/`)

| Route | View | Description |
|-------|------|-------------|
| `/providers/` | `MedicalProviderListView` | List all providers |
| `/providers/add/` | `MedicalProviderCreateView` | Add provider with AI lookup |
| `/providers/<pk>/` | `MedicalProviderDetailView` | Provider detail with staff |
| `/providers/<pk>/edit/` | `MedicalProviderUpdateView` | Edit provider |
| `/providers/<pk>/delete/` | `MedicalProviderDeleteView` | Delete provider |
| `/providers/ai-lookup/` | `ProviderAILookupView` | AI lookup API endpoint |
| `/providers/<pk>/staff/add/` | `ProviderStaffCreateView` | Add staff member |
| `/providers/staff/<pk>/edit/` | `ProviderStaffUpdateView` | Edit staff |
| `/providers/staff/<pk>/delete/` | `ProviderStaffDeleteView` | Delete staff |

### AI Provider Lookup

When adding a new provider, users can use AI to auto-fill contact information:

1. Enter provider name (e.g., "Dr. John Smith" or "Cleveland Clinic")
2. Optionally enter city and state for better results
3. Click "Search with AI"
4. AI searches for the provider and returns:
   - Phone, fax numbers
   - Address (street, city, state, ZIP)
   - Website URL
   - Specialty and credentials
   - NPI number if known
5. Form fields are auto-populated with results
6. User reviews and saves

**Technical Details:**
- Uses OpenAI GPT-4o-mini model
- AJAX POST to `/health/providers/ai-lookup/`
- Returns JSON response
- `ai_lookup_completed` flag tracks which providers used AI

### Health Home Integration

The Health module home page (`/health/`) includes a "My Providers" card showing:
- Total provider count
- Primary care provider name (if set)
- Quick links to view/add providers

### Key Files
- `apps/health/models.py` - MedicalProvider, ProviderStaff models
- `apps/health/forms.py` - MedicalProviderForm, ProviderStaffForm
- `apps/health/views.py` - 9 provider-related views
- `apps/health/urls.py` - URL patterns
- `apps/health/admin.py` - Admin registration with inlines
- `templates/health/providers/` - 4 templates (list, detail, form, staff_form)
- `templates/health/home.html` - Providers card

### Tests
`apps/health/tests/test_medical_providers.py` - 35 tests covering:
- Model creation and properties
- View CRUD operations
- Staff management
- User isolation (security)
- AI lookup endpoint
- Form validation
- Health home integration

---

## Camera Scan Feature

### Overview
OpenAI Vision API integration for scanning items and routing to appropriate modules.
Now includes dedicated barcode scanning mode for quick food product lookup.

### Scan Modes

#### 1. Vision Mode (AI Recognition)
Uses OpenAI Vision API to identify items in photos.

**Categories Detected:**
- food, medicine, supplement, receipt, document
- workout equipment, barcode, inventory_item
- recipe, pet, maintenance

**Features:**
- Browser camera capture (getUserMedia)
- File upload fallback
- Multi-format support (JPEG, PNG, WebP)
- Contextual action suggestions
- Privacy-first (no permanent image storage)
- Rate limiting
- Magic bytes validation

#### 2. Barcode Mode (Added 2025-12-31)
Dedicated mode for scanning food product barcodes.

**Features:**
- Native BarcodeDetector API (Chrome/Edge mobile)
- Real-time barcode detection from camera feed
- Supports UPC-A, UPC-E, EAN-13, EAN-8, Code 128, Code 39
- Vibration feedback on detection
- Manual capture fallback for browsers without BarcodeDetector

**Lookup Flow:**
1. Scan barcode → Extract barcode string
2. Check local FoodItem database first
3. If not found, use OpenAI to lookup product (with AI consent)
4. Display product name, brand, and key nutrition info
5. Pre-fill food entry form with all details
6. Save AI-found products to database for future lookups

**Entry Source Tracking:**
- `entry_source = 'barcode'` set automatically
- Barcode value passed to food entry form

### Food Recognition (Vision Mode)

When food is detected, the system:

1. **For Packaged/Branded Foods** (protein bars, snacks, drinks):
   - Identifies brand name and full product name
   - Looks up ACTUAL nutritional data from AI knowledge base
   - Returns accurate calories, protein, carbs, fat, fiber, sugar, saturated fat
   - Includes standard serving size from nutrition label

2. **For Home-Cooked/Restaurant Food**:
   - Estimates portion size visually
   - Uses common nutritional data for identified foods
   - Considers typical preparation methods visible

3. **Data Pre-filled to Form**:
   - Food Name (product name or description)
   - Brand (for packaged foods)
   - All macros (calories, protein, carbs, fat)
   - Fiber, sugar, saturated fat
   - Serving size and unit
   - Meal type (breakfast, lunch, dinner, snack)
   - Notes (description)

4. **Entry Source Tracking**:
   - `entry_source = 'camera'` set automatically
   - `source=ai_camera` added to URL for tracking

### Architecture
See `docs/wlj_camera_scan_architecture.md` for full details.

### Key Files
- `apps/scan/views.py` - ScanHomeView, ScanAnalyzeView, BarcodeLookupView
- `apps/scan/services/vision.py` - OpenAI Vision integration, `_build_actions()`
- `apps/scan/services/barcode.py` - Barcode lookup service (database + AI)
- `apps/health/views.py` - FoodEntryCreateView (accepts prefill params)
- `apps/health/models.py` - FoodItem (has barcode field), FoodEntry (SOURCE_BARCODE)
- `templates/scan/scan_page.html` - Camera UI with mode toggle

### URL Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/scan/` | GET | Scan home page with camera interface |
| `/scan/analyze/` | POST | Submit image for AI analysis |
| `/scan/barcode/` | POST | Look up barcode and return nutrition info |
| `/scan/consent/` | POST | Record user consent for scanning |
| `/scan/history/` | GET | View scan history |

### Tests
`apps/scan/tests/` - 100+ tests including:
- Vision analysis tests
- Barcode lookup view tests
- Barcode service tests
- Security and isolation tests

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

## Dashboard Tile Shortcuts

### Overview
The quick stat tiles at the top of the dashboard are clickable, providing direct navigation to their respective detail pages.

### Clickable Tiles
| Tile | Icon | Links To |
|------|------|----------|
| Journal Streak | 🔥 | `/journal/entries/` (Journal Entry List) |
| Tasks Today | ✓ | `/life/tasks/` (Task List) |
| Active Prayers | 🙏 | `/faith/prayers/` (Prayer List) |
| Medicine Doses | 💊 | `/health/medicine/` (Medicine Tracker) |
| Workouts This Week | 💪 | `/health/fitness/workouts/` (Workout List) |

### UI/UX
- Tiles display a lift effect and shadow on hover
- Border highlights with accent color on hover
- Cursor changes to pointer to indicate clickability
- Updated tooltips include "Click to..." guidance

### Key Files
- `templates/dashboard/home.html` - Quick stat tiles as anchor links
- `static/css/dashboard.css` - `.quick-stat-link` hover/active styles

---

## Task List with Search

### Overview
The Task List page allows users to view all tasks with powerful filtering and search capabilities.

### Features
1. **Full-Text Search** - Search across task titles, notes, and project names
2. **Filtering** - Filter by completion status (Active/Completed/All) and priority (Now/Soon/Someday)
3. **Task Counts** - See how many tasks in each category
4. **Combined Search + Filters** - Search preserves filter selections

### Search Behavior
- Searches task `title`, `notes`, and `project.title` fields
- Case-insensitive matching
- Search query persists across filter changes
- Clear button to reset search

### URL Parameters
| Parameter | Values | Description |
|-----------|--------|-------------|
| `q` | string | Search query |
| `show` | active, completed, all | Filter by completion status |
| `priority` | now, soon, someday | Filter by priority |

### Example URLs
- `/life/tasks/` - All active tasks
- `/life/tasks/?q=groceries` - Search for "groceries" in active tasks
- `/life/tasks/?show=all&priority=now` - All "now" priority tasks
- `/life/tasks/?show=completed&q=work` - Completed tasks containing "work"

### Key Files
- `apps/life/views.py` - TaskListView with search/filter logic
- `templates/life/task_list.html` - Task list UI with search bar

---

## SMS Text Notifications

### Overview
First-class SMS notification system using Twilio. Users can receive text message reminders for medicine doses, task due dates, calendar events, and more. Replies with shortcuts (D=Done, R=Remind, N=Skip) allow quick status updates directly from text messages.

### Prerequisites
1. **Twilio Account** - Sign up at twilio.com
2. **Twilio Phone Number** - Purchase a number (~$1.15/month)
3. **Twilio Verify Service** - For phone verification
4. **Environment Variables** - See configuration below

### User Flow
1. **Verify Phone** - User enters phone in Preferences, receives 6-digit code, enters code
2. **Enable SMS** - Toggle SMS notifications on
3. **Give Consent** - Accept SMS terms and consent
4. **Select Categories** - Choose which reminders to receive
5. **Set Quiet Hours** - Configure times when no SMS will be sent
6. **Receive Reminders** - Get texts at scheduled times
7. **Reply to Log** - Reply D/R/N to log status directly

### Notification Categories
| Category | Description | Example Message |
|----------|-------------|-----------------|
| Medicine | Scheduled medication reminders | "WLJ: Time for Metformin 500mg. Reply D=Done, R=5min, N=Skip" |
| Medicine Refill | Low supply alerts | "WLJ: Low supply: Metformin (3 days left). Time to refill!" |
| Task | Task due date reminders | "WLJ: Due today: Buy groceries. Reply D=Done, R=1hr, N=Not today" |
| Event | Calendar event reminders (30 min before) | "WLJ: In 30 min: Doctor appt at 2:30 PM" |
| Prayer | Daily prayer reminders | "WLJ: Good morning! Take a moment for prayer today." |
| Fasting | Fasting window reminders | "WLJ: Eating window opens at 12:00 PM. Keep going!" |
| Significant Event | Birthdays, anniversaries, milestones | "WLJ: Mom's Birthday is tomorrow! Gift ideas: Books" |

### Reply Codes
| Code | Meaning | Action |
|------|---------|--------|
| D, d, done, yes, taken | Done | Mark medicine taken / task complete |
| R, R5, R10, R30 | Remind | Schedule new reminder in X minutes |
| N, n, no, skip | Skip | Mark skipped / dismiss for today |

### Models (`apps/sms/models.py`)
| Model | Description |
|-------|-------------|
| `SMSNotification` | Scheduled/sent SMS with delivery status |
| `SMSResponse` | Incoming SMS replies with parsed actions |

### UserPreferences Fields
```python
# Phone verification
phone_number = CharField  # E.164 format: +1XXXXXXXXXX
phone_verified = BooleanField
phone_verified_at = DateTimeField

# Master toggles
sms_enabled = BooleanField
sms_consent = BooleanField
sms_consent_date = DateTimeField

# Category toggles
sms_medicine_reminders = BooleanField
sms_medicine_refill_alerts = BooleanField
sms_task_reminders = BooleanField
sms_event_reminders = BooleanField
sms_prayer_reminders = BooleanField
sms_fasting_reminders = BooleanField
sms_significant_event_reminders = BooleanField

# Quiet hours
sms_quiet_hours_enabled = BooleanField
sms_quiet_start = TimeField  # Default: 22:00
sms_quiet_end = TimeField    # Default: 07:00
```

### URL Routes (`/sms/`)
| Route | View | Description |
|-------|------|-------------|
| `/sms/api/verify/send/` | `SendVerificationView` | Send verification code |
| `/sms/api/verify/check/` | `CheckVerificationView` | Verify code |
| `/sms/api/phone/remove/` | `RemovePhoneView` | Remove phone & disable SMS |
| `/sms/api/status/` | `sms_status` | Get SMS configuration status |
| `/sms/api/trigger/send/` | `TriggerSendView` | Protected: Send pending SMS |
| `/sms/api/trigger/schedule/` | `TriggerScheduleView` | Protected: Schedule SMS |
| `/sms/webhook/incoming/` | `TwilioIncomingWebhookView` | Twilio incoming webhook |
| `/sms/webhook/status/` | `TwilioStatusWebhookView` | Twilio delivery status |
| `/sms/history/` | `sms_history` | User SMS history page |

### Management Commands
```bash
# Schedule reminders for all users (run daily)
python manage.py schedule_sms_reminders

# Send pending notifications (run every 5 min)
python manage.py send_pending_sms

# Dry run (preview without sending)
python manage.py send_pending_sms --dry-run
python manage.py schedule_sms_reminders --dry-run

# Schedule for specific user
python manage.py schedule_sms_reminders --user=email@example.com
```

### External Cron Setup (Railway)
Since Railway has no cron, use external trigger with protected endpoints:

1. Set `SMS_TRIGGER_TOKEN` environment variable
2. Call endpoints with `X-Trigger-Token` header:
   ```bash
   # Every 5 minutes
   curl -X POST https://yourapp.railway.app/sms/api/trigger/send/ \
        -H "X-Trigger-Token: your-secret-token"

   # Daily at midnight
   curl -X POST https://yourapp.railway.app/sms/api/trigger/schedule/ \
        -H "X-Trigger-Token: your-secret-token"
   ```

3. Use cron-job.org, GitHub Actions, or similar for scheduling

### Configuration (Environment Variables)
```bash
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
TWILIO_VERIFY_SERVICE_SID=VAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_TEST_MODE=True  # Set to False in production
SMS_TRIGGER_TOKEN=your-random-secret-token
```

### Twilio Console Setup
1. **Create Verify Service**: Console → Verify → Create Service
2. **Configure Webhooks**: Console → Phone Numbers → Your Number → Messaging
   - Incoming: `https://yourapp.railway.app/sms/webhook/incoming/`
   - Status: `https://yourapp.railway.app/sms/webhook/status/`

### Key Files
- `apps/sms/models.py` - SMSNotification, SMSResponse
- `apps/sms/services.py` - TwilioService, SMSNotificationService
- `apps/sms/scheduler.py` - SMSScheduler for all categories
- `apps/sms/views.py` - Webhooks, verification, history
- `apps/sms/urls.py` - URL patterns
- `apps/users/models.py` - SMS preference fields
- `templates/sms/history.html` - SMS history page
- `templates/users/preferences.html` - SMS section in preferences

### Tests
`apps/sms/tests/test_sms_comprehensive.py` - ~50 tests covering:
- Model creation and status transitions
- Reply parsing (D/R/N)
- TwilioService (test mode)
- Notification scheduling
- Webhook handling
- View functionality
- Integration flows

### Cost Estimates
| Item | Cost |
|------|------|
| Phone Number | ~$1.15/month |
| Outbound SMS | ~$0.0079/message |
| Inbound SMS | ~$0.0079/message |
| Verify (phone verification) | ~$0.05/verification |

**Example:** 1 user, 3 medicine reminders/day = ~$0.71/month + $1.15 number = ~$1.86/month

---

## Task Management

### Overview
The Task Management feature allows users to track personal tasks with intelligent priority-based organization. Tasks can be associated with projects, have due dates, effort estimates, and support recurrence patterns.

### Key Features

#### Task List (`/life/tasks/`)
- **Priority Groups**: Tasks auto-organized into Now/Soon/Someday based on due date
- **Search**: Full-text search across task titles and notes
- **Filters**: Filter by status (Active/Completed/All) and priority
- **Quick Toggle**: Complete tasks with single click, undo available
- **Project Association**: Link tasks to projects

#### Task Search (Added 2025-12-31)
Search functionality for finding tasks quickly:
- **Search Bar**: Located at top of task list page
- **Search Fields**: Searches both title and notes
- **Case Insensitive**: Finds matches regardless of case
- **Filter Compatible**: Search works with existing show/priority filters
- **Preserves Context**: Search query preserved when changing filters
- **Result Count**: Shows "Found X tasks matching..."
- **Clear Button**: Quick reset to show all tasks

**URL Pattern:** `/life/tasks/?q=<search_term>`

**Combined Example:** `/life/tasks/?q=meeting&show=active&priority=now`

#### Priority System
Priorities are auto-calculated based on due date:
| Priority | Criteria |
|----------|----------|
| Now | Due today or overdue |
| Soon | Due within 7 days |
| Someday | Due 7+ days away or no due date |

#### Effort Estimation
| Level | Duration |
|-------|----------|
| Quick | < 15 minutes |
| Small | < 1 hour |
| Medium | 1-3 hours |
| Large | Half day+ |

#### Recurrence Patterns
Tasks can recur with patterns:
- Daily, Weekly, Biweekly, Monthly, Yearly
- Every weekday
- Custom: weekly:mon,wed,fri
- Custom: monthly:15 (15th of each month)

When a recurring task is completed, the next occurrence is automatically created.

### Task Model Fields
| Field | Type | Description |
|-------|------|-------------|
| title | CharField(300) | Task description |
| notes | TextField | Additional details |
| project | ForeignKey | Optional project association |
| priority | CharField | now/soon/someday (auto-calculated) |
| effort | CharField | quick/small/medium/large |
| due_date | DateField | When task is due |
| is_completed | BooleanField | Completion status |
| completed_at | DateTimeField | When completed |
| is_recurring | BooleanField | Whether task repeats |
| recurrence_pattern | CharField | Pattern like 'daily', 'weekly' |

### URL Routes
| URL | View | Description |
|-----|------|-------------|
| `/life/tasks/` | TaskListView | Task list with search/filters |
| `/life/tasks/new/` | TaskCreateView | Create new task |
| `/life/tasks/<id>/edit/` | TaskUpdateView | Edit task |
| `/life/tasks/<id>/delete/` | TaskDeleteView | Delete task |
| `/life/tasks/<id>/toggle/` | TaskToggleView | Toggle completion |

### Key Files
- `apps/life/models.py` - Task model with priority calculation
- `apps/life/views.py` - Task views including search functionality
- `apps/life/services/recurrence.py` - Recurrence pattern parsing
- `templates/life/task_list.html` - Task list UI with search bar
- `templates/life/task_form.html` - Task create/edit form
- `apps/life/tests/test_views.py` - Task view tests including search tests

### Testing
Located in `apps/life/tests/test_views.py` - TaskViewTest class with tests for:
- List loading and filtering
- Task creation and editing
- Toggle completion (complete/undo)
- Project pre-selection
- Search by title and notes
- Search with filters
- User isolation

---

## Memory Verse

### Overview
Users can designate one of their saved Scripture verses as a "Memory Verse" to display prominently at the top of their Dashboard. This feature supports Scripture memorization as a spiritual discipline.

### How It Works
1. User saves Scripture verses to their personal library (Faith → Scripture)
2. User clicks the "Memorize" button on any saved verse
3. The verse is marked as the Memory Verse (only one at a time)
4. The verse appears at the top of the Dashboard (when Faith module is enabled)
5. User can toggle off or switch to a different verse at any time

### Model Changes
`SavedVerse` model in `apps/faith/models.py`:
```python
is_memory_verse = BooleanField(
    default=False,
    help_text="Mark this verse as a memory verse to display on the dashboard"
)
```

### Business Logic
- Only one verse can be the memory verse at a time per user
- Setting a new memory verse automatically clears the previous one
- Memory verse only displays on dashboard when Faith module is enabled

### URL Routes
| URL | View | Description |
|-----|------|-------------|
| `/faith/scripture/<id>/memory-verse/` | ToggleMemoryVerseView | Toggle memory verse status |

### Dashboard Display
When a user has a memory verse set and Faith is enabled:
- Appears immediately after the header, before AI insights
- Features a star icon badge with "Memory Verse" label
- Shows the Scripture text in italics
- Displays the reference attribution
- Link to Scripture Library for management

### UI Components
**Scripture List (`templates/faith/scripture_list.html`)**:
- "Memorize" / "Memorizing" toggle button with star icon
- Visual badge on memory verse cards
- Highlighted border and background

**Dashboard (`templates/dashboard/home.html`)**:
- Memory verse section with styled card
- Gradient background with accent color
- Link to Scripture Library

### CSS Styles
- `static/css/dashboard.css` - Memory verse section styles
- `templates/faith/scripture_list.html` - Inline styles for verse cards

### Key Files
- `apps/faith/models.py` - SavedVerse.is_memory_verse field
- `apps/faith/views.py` - ToggleMemoryVerseView
- `apps/faith/urls.py` - Route for toggle endpoint
- `apps/dashboard/views.py` - _get_faith_data fetches memory verse
- `templates/dashboard/home.html` - Memory verse display section
- `templates/faith/scripture_list.html` - Toggle button and badge

### Testing
10 tests in `apps/faith/tests/test_saved_verses.py`:
- `MemoryVerseTest` - 7 tests for toggle functionality
- `MemoryVerseOnDashboardTest` - 3 tests for dashboard display

### Migration
`apps/faith/migrations/0005_add_memory_verse_field.py` - Adds is_memory_verse field

---

## Significant Events

### Overview
Track and get SMS reminders for significant personal dates like birthdays, anniversaries, memorials, and milestones. Events automatically recur annually and can send SMS reminders at configurable intervals before the date.

### Event Types
| Type | Icon | Description |
|------|------|-------------|
| Birthday | 🎂 | Someone's birthday |
| Anniversary | 💍 | Wedding, relationship, or work anniversaries |
| Memorial | 🕯️ | Remembering someone who passed |
| Milestone | 🏆 | Achievement or personal milestone |
| Holiday | 🎉 | Personal or family holidays |
| Other | 📅 | Custom event type |

### Smart Date Features
- **Annual recurrence** - Events automatically calculate their next occurrence each year
- **Years calculation** - Shows "10th Anniversary", "25th Birthday", etc.
- **Feb 29 handling** - Leap year dates gracefully fall back to Feb 28
- **Days countdown** - "Today!", "Tomorrow", "In 3 days", etc.

### SMS Reminders
| Setting | Options |
|---------|---------|
| Reminder intervals | 14 days, 7 days, 3 days, 1 day, day-of |
| Custom message | e.g., "Gift ideas: Books, flowers" |
| Time | Sent at 9 AM user's timezone |

**SMS Message Format:**
```
WLJ: Mom's Birthday is tomorrow! Gift ideas: Books, flowers
WLJ: 25th Anniversary with Jane is in 7 days!
WLJ: Dad's Memorial is today. 🕯️
```

### Model Fields (`apps/life/models.py`)
```python
class SignificantEvent(UserOwnedModel):
    title = CharField(max_length=200)
    description = TextField(blank=True)
    event_type = CharField(choices=[
        'birthday', 'anniversary', 'memorial',
        'milestone', 'holiday', 'other'
    ])
    event_date = DateField  # The date (year used for age calculation)
    original_year = PositiveIntegerField(null=True)  # For "Xth" display
    person_name = CharField(max_length=200, blank=True)

    # SMS settings
    sms_reminder_enabled = BooleanField
    reminder_days = JSONField  # e.g., [14, 7, 3, 1, 0]
    custom_message = TextField(blank=True)
```

### Key Methods
- `get_next_occurrence(from_date)` - Next occurrence of this event
- `get_years_count()` - Years since original_year
- `days_until_next()` - Days until next occurrence (0 = today)
- `get_display_date()` - Human-friendly: "Tomorrow", "In 3 days", "Jan 15"
- `get_years_display()` - Ordinal: "10th", "25th"

### URL Routes (`/life/significant-events/`)
| Route | View | Description |
|-------|------|-------------|
| `/life/significant-events/` | List | All events sorted by days until |
| `/life/significant-events/new/` | Create | Add new event |
| `/life/significant-events/<id>/` | Detail | Event details with countdown |
| `/life/significant-events/<id>/edit/` | Update | Edit event |
| `/life/significant-events/<id>/delete/` | Delete | Remove event |

### Dashboard Integration
- **"Upcoming Celebrations" card** - Shows next 5 events within 30 days
- Events highlighted based on proximity: "Today!" (green), "Soon" (yellow)
- Years badge displayed (e.g., "10th")

### User Preferences
- `sms_significant_event_reminders` - Toggle in preferences to enable/disable SMS for this category
- Default: enabled (when SMS is configured)

### Key Files
- `apps/life/models.py` - SignificantEvent model
- `apps/life/forms.py` - SignificantEventForm with checkbox reminder days
- `apps/life/views.py` - CRUD views
- `apps/life/urls.py` - URL patterns
- `apps/sms/scheduler.py` - `schedule_significant_event_reminders()`
- `apps/dashboard/views.py` - `_get_life_data()` includes significant events
- `templates/life/significant_event_*.html` - UI templates
- `static/css/dashboard.css` - Celebrations section styles

---

*Last updated: 2025-12-31*
