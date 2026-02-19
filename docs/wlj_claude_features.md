# ==============================================================================
# File: docs/wlj_claude_features.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Detailed feature documentation for reference when needed
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-12-28
# Last Updated: 2026-02-19
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
18. [Bible Reading Plans & Study Tools](#bible-reading-plans--study-tools)
19. [Capture (Audio Recording & Transcription)](#capture-audio-recording--transcription)
20. [Cycle Tracking](#cycle-tracking)
21. [Goal Engine: Measurement-Driven Habits](#goal-engine-measurement-driven-habits) *(Jan 2026)*
22. [Body Composition & Health Profile](#body-composition--health-profile) *(Jan 2026)*
23. [Health Insight Engine](#health-insight-engine) *(Jan 2026)*
24. [Medical Lab Ingestion UI](#medical-lab-ingestion-ui) *(Jan 2026)*
25. [AI Assistant Intelligence Layer](#ai-assistant-intelligence-layer) *(Jan-Feb 2026)*
26. [Quick Links (External Links)](#quick-links-external-links) *(Feb 2026)*
27. [User Activity Pattern Tracking](#user-activity-pattern-tracking) *(Jan 2026)*
28. [Brain Training (Cognitive Health)](#brain-training-cognitive-health) *(Jan 2026)*
29. [Dashboard Performance & Caching](#dashboard-performance--caching) *(Jan 2026)*
30. [Medicine Adherence Calculation](#medicine-adherence-calculation) *(Jan 2026)*
31. [Chief of Staff — Personal Operating System](#chief-of-staff--personal-operating-system) *(Feb 2026)*
32. [Voice Conversation Mode](#voice-conversation-mode) *(Feb 2026)*
33. [Finance Module](#finance-module) *(Feb 2026)*
34. [Nutrition Log Upgrade](#nutrition-log-upgrade) *(Feb 2026)*
35. [Intelligence Engine Stack](#intelligence-engine-stack) *(Jan-Feb 2026)*
36. [Body Transformation Protocol](#body-transformation-protocol) *(Feb 2026)*
37. [Admin Guide](#admin-guide) *(Feb 2026)*
38. [Workout Plans & Training Splits](#workout-plans--training-splits) *(Feb 2026)*
39. [Additional Jan-Feb 2026 Enhancements](#additional-jan-feb-2026-enhancements)

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
| Organize | Two-column | Home, Calendar, Projects, Tasks, Inventory, Pets, Recipes, Maintenance, Documents, Significant Events |
| Goals | Dropdown | Home, Annual Direction, Life Goals, Intentions, Reflections |
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
- **Faith-first prioritization** (for users with faith enabled): Faith → Goals → Long-term goals → Commitments → Maintenance → Optional
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

**Goals Module Data:**
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

**Organize Module Data:**
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
| `FoodItem` | Global food library (FatSecret, barcode scans, AI) |
| `CustomFood` | User-created foods/recipes |
| `FoodEntry` | Individual food log entry |
| `DailyNutritionSummary` | Aggregated daily totals |
| `NutritionGoals` | User's calorie/macro targets |

### Food Search Data Sources
Food search uses a 3-tier priority system (fastest/cheapest first):
1. **Local Database** - User's custom foods + cached FoodItem entries
2. **FatSecret API** - 1.9M+ foods including restaurant menus (Premier tier)
3. **OpenAI AI** - Estimation for unknown foods (fallback only)

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
- **Edit Taken Time** (Added 2025-12-31) - Correct the time when you actually took a dose

### Edit Medicine Log (Added 2025-12-31)
Allows users to correct the "taken at" time on medicine log entries:

**Problem Solved:**
- User takes medicine at 8:00 AM (on time)
- Forgets to tap "Take" until 9:30 AM
- System marks it as "Taken Late"
- Now user can edit the log to set the correct time

**How It Works:**
1. On Medicine Home page, taken doses show an "Edit" link
2. On History page, each log entry has an "Edit" link
3. Edit page shows medicine info, scheduled time, and current status
4. User enters the actual taken time using datetime picker
5. System recalculates "Taken" vs "Taken Late" status based on new time

**URL:** `/health/medicine/log/<pk>/edit/`

**Form Fields:**
- `taken_at` - DateTime picker (user's timezone, converted to/from UTC)
- `notes` - Optional notes field

**Technical Details:**
- `MedicineLogEditForm` handles timezone conversion
- Status recalculated on save using medicine's grace_period_minutes
- User can only edit their own logs (404 for others)

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
`apps/health/tests/test_medicine.py` - 98 tests (12 new tests for log edit feature)

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
AI-powered image recognition for scanning items and routing to appropriate modules.
Uses FatSecret AI for food images (faster, specialized) and OpenAI Vision for non-food items.
Includes multiple barcode scanning modes for quick product lookup across different forms.

### Scan Modes

#### 1. Vision Mode (AI Recognition)
Uses FatSecret AI for food images, OpenAI Vision for non-food items.

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

#### 2. Food Barcode Mode
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
3. Query FatSecret API (1.9M+ products, Premier tier)
4. Fallback: Query Open Food Facts API (4M+ products)
5. Last resort: Use OpenAI to lookup product (with AI consent)
6. Display product name, brand, and key nutrition info
7. Pre-fill food entry form with all details
8. Save results to database for future lookups

**Entry Source Tracking:**
- `entry_source = 'barcode'` set automatically
- Barcode value passed to food entry form

#### 3. Product Barcode Mode (Added 2025-12-31)
Scan product barcodes to auto-fill inventory forms.

**Use Cases:**
- Electronics (phones, tablets, laptops)
- Tools (DeWalt drills, Makita equipment)
- Household appliances
- General retail products

**Lookup Flow:**
1. Scan barcode on Inventory form
2. Query UPC Item DB API (free tier)
3. If not found, use OpenAI fallback
4. Pre-fill: product_name, brand, category, model_number, description, msrp

**API Endpoint:** `POST /scan/barcode/product/`

#### 4. Medicine Barcode Mode (Added 2025-12-31)
Scan OTC medicine barcodes to auto-fill medicine forms.

**Use Cases:**
- Over-the-counter drugs (Tylenol, Advil, etc.)
- Vitamins and supplements
- Any product with NDC code

**Lookup Flow:**
1. Scan barcode on Medicine form
2. Query FDA OpenData for NDC lookup
3. Query RxNav API for drug details
4. If not found, use OpenAI fallback
5. Pre-fill: medicine_name, dosage, form, purpose, manufacturer

**API Endpoint:** `POST /scan/barcode/medicine/`

### Form Integration

**Forms with Barcode Scanning:**
| Form | Module | Barcode Type | Lookup Service |
|------|--------|--------------|----------------|
| Food Entry | Health | UPC/EAN | FatSecret → Open Food Facts → AI |
| Inventory | Organize | UPC/EAN | UPC Item DB + AI |
| Medicine | Health | UPC/NDC | FDA + RxNav + AI |

**Scanner UI Features:**
- "Scan Barcode" button on each form
- Camera modal with live preview
- Target overlay for barcode positioning
- Real-time detection feedback
- Manual entry fallback for unsupported browsers
- Success message showing scanned barcode

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
- `apps/scan/views.py` - ScanHomeView, ScanAnalyzeView, BarcodeLookupView, ProductLookupView, MedicineLookupView
- `apps/scan/services/vision.py` - FatSecret + OpenAI Vision integration, `_build_actions()`
- `apps/scan/services/barcode.py` - Food barcode lookup (FatSecret → Open Food Facts → AI)
- `apps/health/services/fatsecret.py` - FatSecret API client (search, barcode, image recognition)
- `apps/scan/services/product_lookup.py` - Product barcode lookup service (UPC Item DB + AI)
- `apps/scan/services/medicine_lookup.py` - Medicine barcode lookup service (FDA + RxNav + AI)
- `apps/health/views.py` - FoodEntryCreateView, MedicineCreateView (accepts prefill params)
- `apps/life/views.py` - InventoryCreateView (accepts prefill params)
- `apps/health/models.py` - FoodItem (has barcode field), FoodEntry (SOURCE_BARCODE)
- `templates/scan/scan_page.html` - Camera UI with mode toggle
- `templates/life/inventory_form.html` - Inventory form with barcode scanner
- `templates/health/medicine/medicine_form.html` - Medicine form with barcode scanner

### URL Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/scan/` | GET | Scan home page with camera interface |
| `/scan/analyze/` | POST | Submit image for AI analysis |
| `/scan/barcode/` | POST | Look up food barcode and return nutrition info |
| `/scan/barcode/product/` | POST | Look up product barcode for inventory |
| `/scan/barcode/medicine/` | POST | Look up medicine barcode for medicine form |
| `/scan/consent/` | POST | Record user consent for scanning |
| `/scan/history/` | GET | View scan history |

### Tests
`apps/scan/tests/` - 106 tests including:
- Vision analysis tests
- Barcode lookup view tests
- Barcode service tests
- Product lookup tests
- Medicine lookup tests
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

### Automatic Scheduling (Embedded Scheduler)
The SMS scheduler runs automatically within the web process - no external cron required.

**How It Works:**
1. **Embedded in WSGI**: Scheduler starts when Gunicorn loads via `--preload` flag
2. **Two Background Jobs**:
   - `schedule_daily_reminders` - Runs at midnight to create SMS records for the day
   - `send_pending_sms` - Runs every 5 minutes to send due notifications
3. **Real-Time Signals**: Creating/editing medicines, tasks, or events immediately schedules SMS for today

**Key Files:**
- `config/wsgi.py` - Starts APScheduler with background jobs
- `apps/sms/jobs.py` - Job functions (`schedule_daily_reminders`, `send_pending_sms`)
- `apps/sms/signals.py` - Django post_save signals for real-time scheduling
- `apps/sms/apps.py` - Registers signals in `ready()` method

**Technical Details:**
- Uses `BackgroundScheduler` with `MemoryJobStore` (not DjangoJobStore)
- Jobs re-register on each startup with `replace_existing=True`
- Uses textual references (`'apps.sms.jobs:send_pending_sms'`) to avoid serialization issues
- Single-instance protection via `SMS_SCHEDULER_STARTED` environment variable

### Real-Time Scheduling (Signals)
When users save models, SMS is scheduled immediately (no wait for nightly batch):

| Model | Trigger | SMS Scheduled |
|-------|---------|---------------|
| Medicine | Save with active schedule | SMS for any doses due today |
| MedicineSchedule | Save active schedule | SMS for this dose if today |
| Task | Save with today's due date | SMS at 9 AM |
| LifeEvent | Save event happening today | SMS 30 minutes before event |

**Conditions for Real-Time Scheduling:**
- User has SMS enabled and verified phone
- User has given SMS consent
- Relevant category toggle is enabled (e.g., `sms_medicine_reminders`)
- The reminder time is in the future

### Legacy: External Cron (Optional)
Protected endpoints still exist for external triggering if needed:

```bash
# Trigger pending SMS send
curl -X POST https://yourapp.railway.app/sms/api/trigger/send/ \
     -H "X-Trigger-Token: $SMS_TRIGGER_TOKEN"

# Trigger daily scheduling
curl -X POST https://yourapp.railway.app/sms/api/trigger/schedule/ \
     -H "X-Trigger-Token: $SMS_TRIGGER_TOKEN"
```

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
- `apps/sms/services.py` - TwilioService (with phone normalization), SMSNotificationService
- `apps/sms/scheduler.py` - SMSScheduler for all categories
- `apps/sms/jobs.py` - Importable job functions for APScheduler
- `apps/sms/signals.py` - Django signals for real-time scheduling
- `apps/sms/views.py` - Webhooks, verification, history
- `apps/sms/urls.py` - URL patterns
- `apps/sms/apps.py` - App config with signal registration
- `config/wsgi.py` - Embedded scheduler startup
- `apps/users/models.py` - SMS preference fields
- `templates/sms/history.html` - SMS history page
- `templates/users/preferences.html` - SMS section in preferences

### Phone Number Normalization
TwilioService automatically normalizes phone numbers to E.164 format:
- Removes formatting: `(555) 123-4567` → `+15551234567`
- Adds +1 prefix: `5551234567` → `+15551234567`
- Validates: Numbers must match E.164 pattern `^\+[1-9]\d{1,14}$`
- Invalid numbers are rejected with clear error messages

**Common Error Fix (21212):** If you see "Invalid 'From' number" error, check that `TWILIO_PHONE_NUMBER` is set correctly in Railway environment variables.

### Tests
`apps/sms/tests/test_sms_comprehensive.py` - 46 tests covering:
- Model creation and status transitions
- Reply parsing (D/R/N)
- TwilioService (test mode)
- Phone number normalization
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

## Bible Reading Plans & Study Tools

### Overview
The Bible Reading Plans and Study Tools feature enhances the Faith module to help users build consistent Scripture engagement habits. Users can follow structured reading plans and use tools like highlighting, bookmarking, and note-taking while studying the Bible.

### Bible Reading Plans

#### Available Plans (Pre-loaded)
| Plan | Days | Category | Topics |
|------|------|----------|--------|
| Finding Forgiveness | 7 | Topical | forgiveness, healing, grace, relationships |
| Learning to Pray | 7 | Topical | prayer, faith, spiritual growth |
| Peace in Troubled Times | 7 | Topical | peace, anxiety, stress, trust |
| Building a Godly Marriage | 7 | Topical | marriage, love, relationships, family |
| Journey Through John | 21 | Book Study | Jesus, Gospel, faith, salvation |
| Psalms of Comfort | 5 | Devotional | comfort, peace, hope, trust |

#### Models
```python
ReadingPlanTemplate  # System-defined reading plans
ReadingPlanDay       # Daily readings within a plan
UserReadingPlan      # User's progress on a plan
UserReadingProgress  # Daily completion tracking
```

#### Plan Template Fields
- `title` - Plan name
- `slug` - URL-friendly identifier
- `description` - Plan overview
- `category` - topical, book, chronological, devotional
- `difficulty` - beginner, intermediate, advanced
- `duration_days` - Total days
- `topics` - JSON list of topics
- `is_featured` - Show prominently
- `is_active` - Available to users

#### User Progress Tracking
- Start a plan → Creates UserReadingPlan + progress entries for all days
- Mark day complete → Records completion time and notes
- Progress percentage calculated automatically
- Plan automatically marked complete when all days done
- Pause/Resume/Abandon functionality

### Bible Study Tools

#### BibleHighlight Model
Color-coded verse highlighting with 6 colors:
- Yellow, Green, Blue, Pink, Purple, Orange

Fields: reference, text, translation, book_name, book_order, chapter, verse_start, verse_end, color

#### BibleBookmark Model
Save locations to easily return to later.

Fields: reference, translation, book_name, book_order, chapter, verse, title, notes

#### BibleStudyNote Model
In-depth study notes attached to Scripture passages.

Fields: reference, translation, book_name, book_order, chapter, verse_start, verse_end, title, content, tags (JSON)

### URL Routes

#### Reading Plans (`/faith/reading-plans/`)
| Route | View | Description |
|-------|------|-------------|
| `/faith/reading-plans/` | List | Browse plans, view active/completed |
| `/faith/reading-plans/<slug>/` | Detail | View plan details, start option |
| `/faith/reading-plans/<slug>/start/` | Start | Begin a plan |
| `/faith/reading-plans/progress/<pk>/` | Progress | Current reading, overall progress |
| `/faith/reading-plans/progress/<pk>/day/<pk>/complete/` | Complete | Mark day done |
| `/faith/reading-plans/progress/<pk>/pause/` | Pause | Pause plan |
| `/faith/reading-plans/progress/<pk>/resume/` | Resume | Resume plan |
| `/faith/reading-plans/progress/<pk>/abandon/` | Abandon | Remove from active |

#### Study Tools (`/faith/study-tools/`)
| Route | View | Description |
|-------|------|-------------|
| `/faith/study-tools/` | Home | Dashboard with all tools |
| `/faith/study-tools/highlights/` | List | All highlights, filter by color/book |
| `/faith/study-tools/highlights/new/` | Create | Add highlight |
| `/faith/study-tools/highlights/<pk>/delete/` | Delete | Remove highlight |
| `/faith/study-tools/bookmarks/` | List | All bookmarks |
| `/faith/study-tools/bookmarks/new/` | Create | Add bookmark |
| `/faith/study-tools/bookmarks/<pk>/delete/` | Delete | Remove bookmark |
| `/faith/study-tools/notes/` | List | All notes, filter by tag/book |
| `/faith/study-tools/notes/new/` | Create | Add study note |
| `/faith/study-tools/notes/<pk>/` | Detail | View note |
| `/faith/study-tools/notes/<pk>/edit/` | Update | Edit note |
| `/faith/study-tools/notes/<pk>/delete/` | Delete | Remove note |

### Key Files
- `apps/faith/models.py` - All models (ReadingPlanTemplate, ReadingPlanDay, UserReadingPlan, UserReadingProgress, BibleHighlight, BibleBookmark, BibleStudyNote)
- `apps/faith/forms.py` - Forms for reading plans and study tools
- `apps/faith/views.py` - All view classes
- `apps/faith/urls.py` - URL patterns
- `apps/faith/admin.py` - Admin registrations with inlines
- `apps/faith/management/commands/load_reading_plans.py` - Initial data loader
- `templates/faith/reading_plans/` - Reading plan templates
- `templates/faith/study_tools/` - Study tools templates

### Management Command
```bash
python manage.py load_reading_plans
```
Loads initial reading plan templates. Idempotent - safe to run multiple times.

### Future Phases (Planned)
- Phase 2: Prayer prompts before Bible study
- Phase 3: Background worship music with voice narration
- Phase 4: Interactive Q&A / AI-powered faith questions
- Phase 5: Bible character profiles, topical verse collections
- Phase 6: AR guided experiences, interactive timelines

---

## Capture (Audio Recording & Transcription)

### Overview
The Capture feature allows users to record or upload audio recordings, which are then automatically transcribed using OpenAI Whisper and summarized using GPT. Recordings are stored temporarily in AWS S3 with a 7-day retention policy, while transcripts and summaries are preserved permanently.

### Key Features
- **Audio Recording** - Browser-based recording using MediaRecorder API (up to 60 minutes)
- **Audio Upload** - Upload existing audio files (MP3, M4A, WAV, WebM up to 60MB)
- **Speech-to-Text** - Automatic transcription via OpenAI Whisper API
- **AI Summarization** - BLUF-style summary with category detection
- **Category Classification** - Auto-detection of Faith/Organize categories with subcategories
- **PDF/DOCX Export** - Download summary and transcript as formatted documents
- **Audio Expiration** - 7-day retention with email reminders before expiration
- **Status Polling** - Real-time progress updates during processing

### Processing Pipeline
1. **Upload** (`STATUS_UPLOADING`) - User records/uploads audio, file sent to S3
2. **Transcription** (`STATUS_TRANSCRIBING`) - Audio transcribed via Whisper API
3. **Summarization** (`STATUS_SUMMARIZING`) - Transcript summarized with category detection
4. **Ready** (`STATUS_READY`) - Entry complete, available for viewing/export
5. **Failed** (`STATUS_FAILED`) - Error occurred, message stored for user

### Categories & Subcategories
| Category | Subcategories |
|----------|---------------|
| Faith | Sermon, Bible Study, Devotional |
| Organize | Meeting, Notes, Personal |

### Models (`apps/capture/models.py`)
**CaptureEntry** - Main model for audio recordings
| Field | Type | Description |
|-------|------|-------------|
| `id` | UUIDField | Unique identifier (primary key) |
| `user` | ForeignKey | Owner of the recording |
| `title` | CharField(255) | Recording title (can be auto-generated) |
| `duration_seconds` | PositiveIntegerField | Recording duration in seconds |
| `audio_file_url` | URLField(500) | S3 presigned URL for audio |
| `audio_expires_at` | DateTimeField | When S3 URL expires (7 days) |
| `transcript` | TextField | Full Whisper transcription |
| `summary` | TextField | AI-generated BLUF summary |
| `category` | CharField(20) | faith, organize |
| `subcategory` | CharField(20) | sermon, bible_study, meeting, etc. |
| `status` | CharField(20) | uploading, transcribing, summarizing, ready, failed |
| `error_message` | TextField | Error details if processing failed |
| `reminder_sent_at` | DateTimeField | When expiration reminder was sent |

### URL Routes (`/capture/`)
| Route | View | Description |
|-------|------|-------------|
| `/capture/` | `CaptureListView` | List all user's recordings |
| `/capture/record/` | `CaptureRecordView` | Browser-based recording interface |
| `/capture/upload/` | `CaptureUploadView` | File upload interface |
| `/capture/submit/` | `CaptureSubmitView` | API for presigned URLs & upload confirmation |
| `/capture/<pk>/` | `CaptureDetailView` | View recording details |
| `/capture/<pk>/status/` | `CaptureStatusView` | Poll processing status (JSON) |
| `/capture/<pk>/update-title/` | `CaptureUpdateTitleView` | Update entry title (AJAX) |
| `/capture/<pk>/delete/` | `CaptureDeleteView` | Delete recording |
| `/capture/<pk>/download/pdf/` | `CaptureDownloadPDFView` | Download as PDF |
| `/capture/<pk>/download/docx/` | `CaptureDownloadDocxView` | Download as Word Document |

### Submit API Actions
The `/capture/submit/` endpoint handles multiple actions via JSON POST:

| Action | Parameters | Response |
|--------|------------|----------|
| `get_upload_url` | content_type, title, duration_seconds | upload_url, entry_id, mock_mode |
| `confirm_upload` | entry_id | success, status (triggers transcription) |

### Status Polling Response
```json
{
    "status": "transcribing",
    "status_message": "Transcribing",
    "status_description": "Converting speech to text...",
    "progress": 50,
    "title": "My Recording"
}
```

When status is `ready`:
```json
{
    "status": "ready",
    "status_message": "Ready",
    "status_description": "Your recording is ready!",
    "progress": 100,
    "redirect_url": "/capture/<uuid>/",
    "summary": "BLUF: Key points...",
    "category": "faith",
    "subcategory": "sermon"
}
```

### Services

#### Transcription (`apps/capture/services/transcription.py`)
Uses OpenAI Whisper API for speech-to-text conversion.
- Supports multiple audio formats
- Returns full transcript text
- Handles API errors with retry logic

#### Summarization (`apps/capture/services/summarization.py`)
Uses OpenAI GPT for BLUF-style summarization.
- Generates concise summary from transcript
- Auto-detects category and subcategory
- Returns JSON with summary, category, subcategory

#### PDF Generation (`apps/capture/services/pdf.py`)
Uses WeasyPrint to generate PDF documents.
- `generate_pdf(entry)` - Renders entry to PDF bytes
- `get_pdf_filename(entry)` - Generates safe filename

#### DOCX Generation (`apps/capture/services/docx_generator.py`)
Uses python-docx to generate Word documents.
- `generate_docx(entry)` - Renders entry to DOCX bytes
- `get_docx_filename(entry)` - Generates safe filename

#### Email Notification (`apps/capture/services/email.py`)
Sends email when recording is ready.
- Includes summary preview
- Link to view full recording

#### Expiration Reminder (`apps/capture/services/expiration_reminder.py`)
Sends email reminder before audio expires.
- Triggered 2 days before expiration
- Only for entries with audio still available

### Storage (`apps/capture/storage.py`)
AWS S3 integration for audio file storage.

| Function | Description |
|----------|-------------|
| `is_storage_configured()` | Check if S3 credentials are set |
| `generate_upload_presigned_url(user_id, content_type, filename)` | Generate S3 upload URL |
| `generate_download_presigned_url(key, expiration_seconds)` | Generate S3 download URL |

**S3 Key Format:** `captures/{user_id}/{uuid}.{extension}`

### Background Jobs (`apps/capture/jobs.py`)
| Job | Description |
|-----|-------------|
| `send_expiration_reminders` | Find entries expiring in 1-2 days, send reminder emails |

### Configuration (Environment Variables)
```bash
# AWS S3 Storage
CAPTURE_AUDIO_BUCKET=your-bucket-name
CAPTURE_AWS_ACCESS_KEY_ID=your-access-key
CAPTURE_AWS_SECRET_ACCESS_KEY=your-secret-key
CAPTURE_AWS_REGION=us-east-1
CAPTURE_S3_ENDPOINT_URL=  # Optional, for S3-compatible services

# Retention
CAPTURE_AUDIO_RETENTION_DAYS=7
CAPTURE_PRESIGNED_URL_EXPIRATION=3600

# OpenAI (shared with other AI features)
OPENAI_API_KEY=your-openai-key
```

### User Preferences
| Field | Type | Description |
|-------|------|-------------|
| `capture_enabled` | BooleanField | Enable Capture module for user |

### Dashboard Integration
When `capture_enabled = True`:
- "Capture" link appears in navigation menu
- "Record Audio" quick action on dashboard
- Capture module card shows recording count

### Accepted Audio Formats
| Extension | MIME Type | Notes |
|-----------|-----------|-------|
| .mp3 | audio/mpeg, audio/mp3 | Most common format |
| .m4a | audio/mp4 | iOS recordings |
| .wav | audio/wav | Uncompressed |
| .webm | audio/webm | Browser recordings |

### Limits
| Limit | Value |
|-------|-------|
| Max Duration | 60 minutes |
| Max File Size | 60 MB |
| Audio Retention | 7 days |
| Title Length | 200 characters (update), 255 (model) |

### Key Files
- `apps/capture/models.py` - CaptureEntry model
- `apps/capture/views.py` - All capture views
- `apps/capture/storage.py` - S3 presigned URL utilities
- `apps/capture/services/transcription.py` - OpenAI Whisper integration
- `apps/capture/services/summarization.py` - OpenAI GPT summarization
- `apps/capture/services/pdf.py` - PDF generation
- `apps/capture/services/docx_generator.py` - DOCX generation
- `apps/capture/services/email.py` - Email notifications
- `apps/capture/services/expiration_reminder.py` - Expiration reminders
- `apps/capture/jobs.py` - Background jobs
- `apps/capture/tasks.py` - Celery tasks (if using Celery)
- `templates/capture/` - All capture templates

### Tests
- `apps/capture/tests/test_models.py` - Model unit tests
- `apps/capture/tests/test_views.py` - View tests (extensive)
- `apps/capture/tests/test_storage.py` - S3 storage tests with mocked boto3
- `apps/capture/tests/test_transcription.py` - Transcription service tests
- `apps/capture/tests/test_summarization.py` - Summarization service tests
- `apps/capture/tests/test_email.py` - Email service tests
- `apps/capture/tests/test_pdf.py` - PDF generation tests
- `apps/capture/tests/test_tasks.py` - Background task tests
- `apps/capture/tests/test_expiration_reminder.py` - Expiration reminder tests
- `apps/capture/tests/test_integration.py` - End-to-end flow tests
- `apps/capture/tests/test_edge_cases.py` - Edge case and limit tests

---

## Cycle Tracking

### Overview
Privacy-first menstrual cycle tracking feature that allows users to log daily symptoms, track period patterns, and receive predictions for upcoming cycles. The feature includes automatic cycle detection, phase calculation, calendar visualization, and comprehensive data export capabilities.

### Key Features
- **Daily Logging** - Track flow level, symptoms, mood, energy, and optional fertility indicators
- **Automatic Cycle Detection** - Service detects period start/end from flow patterns
- **Phase Calculator** - Calculates current menstrual phase (menstrual, follicular, ovulation, luteal)
- **Cycle Predictions** - Predicts next period based on historical patterns (requires 3+ cycles)
- **Calendar View** - Visual monthly calendar with color-coded period days and predictions
- **Data Export** - Export data in JSON or CSV format with rate limiting
- **Opt-In Privacy** - Explicit opt-in required; data can be completely deleted

### Data Models

#### CycleSettings
OneToOne settings model for user preferences.

| Field | Type | Description |
|-------|------|-------------|
| `user` | OneToOne | User these settings belong to |
| `cycle_tracking_enabled` | Boolean | Master toggle for cycle tracking |
| `average_cycle_length` | SmallInt | Typical cycle length (default 28, range 15-60) |
| `average_period_length` | SmallInt | Typical period length (default 5, range 1-14) |
| `notifications_enabled` | Boolean | Send period prediction reminders |
| `fertile_window_tracking_enabled` | Boolean | Track and show fertile window |
| `last_period_start_date` | Date | Most recent period start (for predictions) |

**Key Property:** `is_enabled` - Returns True only if record is active AND `cycle_tracking_enabled=True`

#### CycleDailyLog
Daily health data entry (one per user per day).

| Field | Type | Description |
|-------|------|-------------|
| `user` | ForeignKey | Owner of this log |
| `log_date` | Date | Date of this entry |
| `flow_level` | Choice | none, spotting, light, medium, heavy |
| `symptoms` | JSON | List of symptom keys (cramps, headache, etc.) |
| `mood` | Choice | happy, calm, anxious, irritable, sad, energetic, tired, neutral |
| `energy_level` | SmallInt | 1-10 scale |
| `cervical_mucus` | Choice | Optional fertility tracking |
| `basal_temp` | Decimal | Optional BBT (95-105°F range) |
| `notes` | Text | Free-form notes |

**Symptom Choices:** cramps, headache, fatigue, bloating, breast_tenderness, acne, backache, nausea, food_cravings, insomnia

**Key Property:** `is_period_day` - True if flow_level is not "none"

#### Cycle
Complete menstrual cycle record (auto-numbered per user).

| Field | Type | Description |
|-------|------|-------------|
| `user` | ForeignKey | Owner of this cycle |
| `cycle_number` | Int | Auto-incremented per user |
| `start_date` | Date | First day of period |
| `end_date` | Date | Day before next period starts (nullable) |
| `period_end_date` | Date | Last day of bleeding (nullable) |
| `is_predicted` | Boolean | True if AI-predicted (not user-confirmed) |
| `notes` | Text | User notes |

**Key Properties:**
- `cycle_length` - Days between start and end (or None if ongoing)
- `period_length` - Days between start and period_end
- `is_complete` / `is_ongoing` - Status checks

#### CyclePrediction
AI-generated predictions for upcoming periods.

| Field | Type | Description |
|-------|------|-------------|
| `user` | ForeignKey | Owner |
| `predicted_period_start` | Date | Expected period start |
| `predicted_period_end` | Date | Expected period end |
| `predicted_fertile_window_start` | Date | Fertile window start (optional) |
| `predicted_fertile_window_end` | Date | Fertile window end (optional) |
| `prediction_confidence` | Decimal | 0.00-1.00 confidence score |
| `prediction_algorithm_version` | Char | Version string (e.g., "v1.0-basic") |
| `generated_at` | DateTime | When prediction was created |
| `actual_period_start` | Date | Filled when verified (for accuracy tracking) |

**Class Method:** `get_active_prediction(user)` - Returns most recent unverified prediction

### URL Routes

#### Page Views (`/health/cycle/`)
| Route | View | Description |
|-------|------|-------------|
| `/health/cycle/` | `CycleDashboardView` | Main dashboard with summary |
| `/health/cycle/opt-in/` | `CycleOptInPageView` | Privacy info and enable/disable |
| `/health/cycle/settings/` | `CycleSettingsPageView` | Configure cycle preferences |
| `/health/cycle/calendar/` | `CycleCalendarView` | Monthly calendar visualization |
| `/health/cycle/data/` | `CycleDataManagementView` | Export/delete data |

#### API Endpoints (`/health/api/cycle/`)
| Route | Method | View | Description |
|-------|--------|------|-------------|
| `/api/cycle/settings/` | GET | `CycleSettingsViewSet` | Get current settings |
| `/api/cycle/settings/` | PUT/PATCH | `CycleSettingsViewSet` | Update settings |
| `/api/cycle/opt_in/` | POST | `CycleOptInView` | Enable cycle tracking |
| `/api/cycle/opt_out/` | POST | `CycleOptOutView` | Disable (optionally delete) |
| `/api/cycle/check/` | GET | `CycleSettingsCheckView` | Quick enabled status check |
| `/api/cycle/logs/` | GET | `CycleDailyLogViewSet` | List daily logs (paginated) |
| `/api/cycle/logs/` | POST | `CycleDailyLogViewSet` | Create new log |
| `/api/cycle/logs/<id>/` | GET/PUT/PATCH | `CycleDailyLogViewSet` | Retrieve/update log |
| `/api/cycle/logs/<id>/` | DELETE | `CycleDailyLogViewSet` | Soft delete log |
| `/api/cycle/cycles/` | GET | `CycleViewSet` | List cycles (paginated) |
| `/api/cycle/cycles/<id>/` | GET | `CycleViewSet` | Retrieve single cycle |
| `/api/cycle/cycles/current/` | GET | `CycleViewSet` | Get ongoing cycle |
| `/api/cycle/cycles/statistics/` | GET | `CycleViewSet` | Get averages and trends |
| `/api/cycle/predictions/` | GET | `CyclePredictionViewSet` | List predictions |
| `/api/cycle/predictions/<id>/` | GET | `CyclePredictionViewSet` | Retrieve prediction |
| `/api/cycle/predictions/current/` | GET | `CyclePredictionViewSet` | Get active prediction |
| `/api/cycle/predictions/regenerate/` | POST | `CyclePredictionViewSet` | Generate new prediction |
| `/api/cycle/export/` | GET | `CycleExportAPIView` | Export data (JSON/CSV) |
| `/api/cycle/delete-all/` | POST | `CycleDeleteAllAPIView` | Delete all data |

#### Form Endpoints (HTML responses)
| Route | Method | View | Description |
|-------|--------|------|-------------|
| `/api/cycle/day-modal/` | GET | `CycleDayModalView` | Day detail modal HTML |
| `/api/cycle/period-toggle/` | POST | `CyclePeriodToggleView` | Quick start/end period |
| `/api/cycle/export-json/` | POST | `CycleExportJSONView` | Download JSON file |
| `/api/cycle/export-csv/` | POST | `CycleExportCSVView` | Download CSV file |

### Service Layer

#### CycleDetectionService (`apps/health/services/cycle_detection.py`)
Automatically detects period boundaries from daily log flow patterns.

**Key Methods:**
- `process_daily_log(log)` - Main entry point after log save
- `_check_period_start(date)` - Detects new period start
- `_check_period_end(date)` - Detects period end (2+ no-flow days)
- `_create_new_cycle(date)` - Creates Cycle and closes previous
- `recalculate_cycles()` - Rebuilds all cycles from logs

**Detection Logic:**
- Period starts when flow changes from none/spotting to light/medium/heavy
- Period ends after 2+ consecutive days of no flow
- Spotting doesn't count as period start/end
- Previous cycle is automatically closed when new one begins

#### CyclePhaseService (`apps/health/services/cycle_phase.py`)
Calculates current menstrual phase with proportional adjustment for non-28-day cycles.

**Phases (Standard 28-day):**
| Phase | Days | Color | Description |
|-------|------|-------|-------------|
| Menstrual | 1-5 | Red | Period bleeding |
| Follicular | 6-13 | Orange | Pre-ovulation |
| Ovulation | 14-16 | Green | Peak fertility |
| Luteal | 17-28 | Blue | Post-ovulation |

**Key Functions:**
- `get_current_phase(user, date)` - Returns phase info dict
- `get_phase_by_day(day, cycle_length)` - Phase for specific day
- `get_all_phases(cycle_length)` - All phases with boundaries

#### CycleDataExportService (`apps/health/services/cycle_export.py`)
Exports user data in JSON and CSV formats.

**Key Methods:**
- `export_to_json()` - Full data as dict
- `export_to_json_string()` - JSON string with formatting
- `export_to_csv(data_type)` - CSV for daily_logs/cycles/predictions
- `get_export_size_estimate()` - Record counts and size estimates

**Limits:**
- Max 1000 daily logs per export
- Max 100 cycles per export
- Max 50 predictions per export
- Rate limited: 5 exports per hour per user

### Privacy & Security

#### Opt-In Model
- Cycle tracking requires explicit opt-in
- `CycleTrackingEnabledMixin` enforces access control on all API views
- Users can disable tracking while preserving data
- Full data deletion with confirmation text ("DELETE ALL MY CYCLE DATA")

#### Data Isolation
- All models use `UserOwnedModel` base class
- API views filter by `request.user`
- Soft delete preserves data for 30 days
- Hard delete option for permanent removal

#### Export Security
- Rate limiting: 5 exports/hour prevents abuse
- No PII in export metadata
- Audit logging for data deletion (`log_security_event`)
- Confirmation required for destructive operations

### API Response Examples

**GET /api/cycle/settings/**
```json
{
  "id": 1,
  "cycle_tracking_enabled": true,
  "average_cycle_length": 28,
  "average_period_length": 5,
  "notifications_enabled": true,
  "fertile_window_tracking_enabled": false,
  "last_period_start_date": "2026-01-01",
  "is_enabled": true
}
```

**POST /api/cycle/logs/**
```json
{
  "log_date": "2026-01-15",
  "flow_level": "medium",
  "symptoms": ["cramps", "fatigue"],
  "mood": "tired",
  "energy_level": 3,
  "notes": "First day of period"
}
```

**GET /api/cycle/predictions/current/**
```json
{
  "id": 5,
  "predicted_period_start": "2026-01-28",
  "predicted_period_end": "2026-02-02",
  "predicted_fertile_window_start": "2026-01-19",
  "predicted_fertile_window_end": "2026-01-21",
  "prediction_confidence": 0.75,
  "confidence_display": "75%",
  "days_until_period": 13,
  "status": "upcoming",
  "status_message": "Period expected in 13 days"
}
```

**GET /api/cycle/cycles/statistics/**
```json
{
  "cycle_count": 6,
  "completed_cycles": 6,
  "cycle_length": {
    "average": 28.5,
    "min": 26,
    "max": 31,
    "standard_deviation": 1.8
  },
  "period_length": {
    "average": 5.2,
    "min": 4,
    "max": 6
  },
  "regularity_score": 74,
  "trend": {
    "direction": "stable",
    "recent_average": 28.3,
    "older_average": 28.7
  }
}
```

### Integration with Daily Check-In

The cycle tracking feature integrates with the dashboard's daily summary:
- Current cycle phase displayed when applicable
- Days until next predicted period shown
- Quick log actions available from dashboard
- Today's log status visible in health section

### Key Files
- `apps/health/models.py` - CycleSettings, CycleDailyLog, Cycle, CyclePrediction
- `apps/health/serializers.py` - All cycle serializers
- `apps/health/views_cycle.py` - All cycle views (1700+ lines)
- `apps/health/services/cycle_detection.py` - Period detection service
- `apps/health/services/cycle_phase.py` - Phase calculator
- `apps/health/services/cycle_export.py` - Data export service
- `templates/health/cycle/` - Dashboard, calendar, settings, opt-in templates
- `templates/health/cycle/includes/` - Form partials, modals

### Tests
- `apps/health/tests/test_cycle_models.py` - Model tests
- `apps/health/tests/test_cycle_services.py` - Service layer tests (48 tests)
- `apps/health/tests/test_cycle_api.py` - API endpoint tests (77 tests)
- `apps/health/tests/test_cycle_views.py` - Template/view tests (51 tests)

**Total: 250+ cycle-related tests**

---

---

## Goal Engine: Measurement-Driven Habits

### Overview
The Goal Engine extends HabitGoal from simple binary tracking to four measurement types, with streaks, analytics, rule-based recommendations, and interactive logging widgets.

### Measurement Types
| Type | Widget | Example |
|------|--------|---------|
| **Binary** | Checkbox / "I Did It" button | "Did I exercise today?" |
| **Duration** | Timer widget (start/stop/pause) | "How long did I meditate?" |
| **Count** | Counter widget (+/- buttons) | "How many glasses of water?" |
| **Target** | Target input with unit dropdown | "How many pages did I read?" |

### Key Features
- **Habit streaks** - Current streak, longest streak, streak recovery (1 missed day grace)
- **Analytics service** - Completion rate, averages, trend direction, best day of week
- **Rule-based recommendations** - System suggests when to increase difficulty
- **Clickable matrix** - Click any day in the matrix to log; shift+click for date ranges
- **Custom calendar** - Full month view, color-coded days, click to log, shift/ctrl multi-select
- **Undo toast** - 8-second countdown with "Undo" button after logging
- **Quick Log** - Available for ALL goal types (not just binary)
- **Retroactive logging** - "I Did It Today" button with date picker
- **Upgrade banner** - Binary goals show dismissible prompt to upgrade to measurement types
- **18 unit options** - minutes, hours, pages, reps, miles, km, oz, cups, mg, etc.

### Key Files
- `apps/purpose/models.py` - HabitGoal (measurement_type, target_value, unit), HabitLog (value, session_number)
- `apps/purpose/services/streak.py` - Streak calculation with grace period
- `apps/purpose/services/analytics.py` - Completion rate, trends, best day
- `apps/purpose/services/recommendation.py` - Rule-based difficulty suggestions
- `apps/purpose/views.py` - 7 new endpoints including HabitLogDatesView, HabitUnlogDatesView
- `apps/purpose/templates/purpose/habit_goal_detail.html` - Matrix, calendar, timer, counter widgets
- `apps/purpose/templates/purpose/habit_goal_form.html` - Native date pickers, unit dropdown

### Tests
- `apps/purpose/tests/test_goal_engine.py` - 55 tests covering models, services, views

---

## Body Composition & Health Profile

### Overview
Separates body composition metrics from Labs/Vitals into a dedicated domain. Health Profile stores user-specific context (height, activity level, weight goal) used by the Insight Engine.

### Body Composition Metrics
- Body fat percentage
- Lean body mass
- Waist circumference
- Hip circumference
- BMI (calculated)
- Custom metrics via flexible storage

### Health Profile
- Height (stored for BMI calculations)
- Activity level (sedentary, lightly active, active, very active)
- Weight goal (moved from Preferences - with backward-compatible delegation)
- Used by Insight Engine for personalized health insights

### Key Files
- `apps/health/models.py` - BodyCompositionEntry, HealthProfile
- `apps/health/views_body_composition.py` - CRUD views
- `apps/health/views.py` - Health Profile form, ClearWeightGoalView
- `apps/health/forms.py` - Body composition and health profile forms
- `apps/health/migrations/0040_body_composition_health_profile_insights.py`
- `apps/health/migrations/0041_add_weight_goal_to_health_profile.py`
- `apps/health/migrations/0042_migrate_weight_goal_data.py`

### Tests
- 59 tests covering models, views, forms, services

---

## Health Insight Engine

### Overview
Cross-domain health analysis engine that reads data from Labs, Vitals, Body Composition, Weight, Sleep, and Steps to generate personalized health insights with confidence scoring.

### Architecture
```
Labs ──┐
Vitals ──┤
Body Comp ──┤──→ health_data.py (service layer) ──→ insight_engine.py ──→ InsightResult
Weight ──┤
Sleep ──┤
Steps ──┘
```

### InsightResult Model
- `insight_type` - Category of insight (trend, correlation, alert)
- `confidence_score` - How confident the system is (0-1)
- `related_domains` - Which health domains contributed
- `content` - The insight text
- Persisted to database for history tracking

### Key Files
- `apps/health/services/health_data.py` - Unified health data service layer
- `apps/health/services/insight_engine.py` - Cross-domain analysis logic
- `apps/health/views_insights.py` - Insight display views
- `apps/health/models.py` - InsightResult model

---

## Medical Lab Ingestion UI

### Overview
Complete user-facing UI for uploading PDF lab results, viewing parsed results, trending over time, and lab test education. Builds on the medical module backend (apps/medical/).

### User Flow
1. **Upload** - Upload PDF lab report via form
2. **Parse** - System extracts lab results using `lab_parser.py`
3. **Review** - Import detail page shows all extracted results with abnormal highlighting
4. **View** - Labs Summary page with filterable results, abnormal result badges
5. **Trend** - Individual test trend charts with colored range zones
6. **Learn** - Education panels on result detail pages

### Lab Test Education
- 57 system-seeded lab tests with structured content
- What each test measures
- Common associations for low/high values
- Factors that influence results
- Typical panels where the test appears
- Model: `LabEducationContent`

### Safety Features
- Rejects lab results with missing dates (won't fabricate dates)
- Flags estimated dates with amber warnings
- Page-break handling in parser (looks ahead 4 lines past breaks)
- Duplicate detection prevents re-importing same PDF
- Soft-delete support for imports and documents

### Trend Charts
- Colored background zones (green in-range, light red above, light blue below)
- Color-coded data points
- Dashed boundary lines for reference ranges
- Value labels on data points
- Range fallback to catalog defaults when per-result ranges missing

### Key Files
- `apps/medical/views.py` - 8 view classes (Upload, ImportDetail, LabsSummary, ResultDetail, TestTrend, DocumentRename, DocumentDelete, ImportDelete)
- `apps/medical/services/lab_parser.py` - PDF parsing with 7+ date formats
- `apps/medical/services/importer.py` - Import orchestration
- `apps/medical/services/duplicate_detector.py` - Duplicate PDF detection
- `apps/medical/models.py` - LabEducationContent, date_estimated field
- `templates/medical/` - 7 template files
- `apps/medical/migrations/0003-0005` - Education content, date_estimated

### Tests
- 41 comprehensive tests covering upload, parse, view, trend, education

---

## AI Assistant Intelligence Layer

### Overview
Major overhaul of the AI personal assistant adding proactive check-ins, conversational intelligence, quick reply system, and a "Master Prompt" philosophy.

### Master Prompt Philosophy
The assistant is an **attentive, calm, factual, efficient right-hand assistant**. NOT a cheerleader, therapist, or medical advisor.

### Proactive Check-ins
- System initiates relevant check-ins based on user patterns
- InteractionThrottler: max 3/hour, no repeats within 4 hours
- PatternAnalyzer: food-glucose, workout-mood, sleep-energy correlations
- ScheduleAnalyzer: detects busy days, adjusts check-in timing
- CoachingStyleTemplates: Default, Southern Belle, New Yorker, California variations

### Quick Reply System
- Check-in messages include action buttons (e.g., "Take Medicine", "Log Workout")
- Quick reply handlers process button taps without full chat interaction
- Confirmation detector understands natural language confirmations

### Conversational Intelligence
- 10-message thread context (up from 5)
- Intent inference: analytical vs. navigation queries
- Dynamic token limits: 500 for analytical, 350 for regular
- User first name in prompts for personalization
- Anti-hallucination: real data, lower temperature (0.3) for data-heavy queries
- Recent journal entries (14 days) included in context

### Dashboard Insights
- Time-period caching (early_morning/morning/afternoon/evening)
- Immediate invalidation when activities are logged
- Acknowledges completed activities before mentioning pending
- Early morning warmth (before 8am, no "slow start" messaging)
- No duplicate greeting (page already shows one)

### Medicine Nudging Fix
- Split pending into `missed_doses_today` (past due) and `upcoming_doses_today` (future)
- Nudge only fires for overdue doses, not future scheduled ones

### Key Files
- `apps/ai/assistant_intelligence.py` - Master prompt, intelligence orchestration
- `apps/ai/proactive_checkins.py` - Check-in generation with throttling
- `apps/ai/quick_reply_handlers.py` - Button action handlers
- `apps/ai/confirmation_detector.py` - Natural language confirmation parsing
- `apps/ai/personal_assistant.py` - Conversational intelligence, thread management
- `apps/ai/dashboard_ai.py` - Time-period insights, activity acknowledgment
- `apps/ai/services.py` - Token management, context building
- `apps/ai/models.py` - quick_replies JSONField, is_proactive, time_period
- `apps/users/models.py` - Proactive check-in preferences
- `assistant/data_service.py` - Journal data, health data for context
- `assistant/context_builder.py` - Context assembly

### Tests
- Tests across AI module covering check-ins, quick replies, insights

---

## Quick Links (External Links)

### Overview
Users can save up to 16 external links (patient portal, bank login, pharmacy site, etc.) accessible from the profile dropdown and mobile menu.

### Features
- Up to 16 saved links per user
- URL validation on save
- AJAX add/delete (no page reload)
- 60-second per-user cache for performance
- Accessible from profile dropdown and mobile bottom bar

### Key Files
- `apps/users/models.py` - ExternalLink model
- `apps/users/views.py` - CRUD views with AJAX
- `apps/users/urls.py` - Quick link endpoints
- `apps/core/context_processors.py` - Links injected into template context

### Tests
- `apps/users/tests/test_quick_links.py` - 17 tests

---

## User Activity Pattern Tracking

### Overview
System learns when each user starts and ends their day, enabling personalized insight timing and early morning threshold detection.

### Components
- **UserDailyActivity** - One row per user per day recording first/last activity times
- **UserActivityPattern** - Computed summary of typical patterns
- **PageViewTrackingMiddleware** - Records page views for activity detection
- **compute_activity_patterns** - Management command (runs daily at 7 AM UTC)

### Usage
- Dashboard AI uses patterns to determine "early morning" threshold per user
- Insight generation adapts to user's typical schedule

### Key Files
- `apps/core/models.py` - UserDailyActivity, UserActivityPattern
- `apps/core/middleware.py` - PageViewTrackingMiddleware
- `apps/core/management/commands/compute_activity_patterns.py`
- `apps/ai/dashboard_ai.py` - Consumes patterns for insight timing

### Tests
- `apps/core/tests/test_activity_patterns.py` - 17 tests

---

## Brain Training (Cognitive Health)

### Overview
Daily brain training exercises accessible from the Health module. Multiple puzzle types targeting different cognitive skills.

### Available Exercises
| Exercise | Cognitive Skill | Description |
|----------|----------------|-------------|
| **Sudoku** | Logical reasoning | Number placement puzzle, multiple difficulties |
| **KenKen** | Mental math | Arithmetic + Sudoku constraints |
| **Nonogram** | Spatial reasoning | Reveal hidden image from number clues |
| **Word Ladder** | Vocabulary | Transform words one letter at a time |
| **Memory Matrix** | Working memory | Memorize and reproduce grid patterns |

### Features
- Multiple difficulty levels per exercise
- Time and score tracking
- Streaks (consecutive training days)
- Performance statistics and trends
- Game-specific context-aware help topics

### Key Files
- `apps/brain_training/` - Models, views, templates
- `apps/help/fixtures/help_topics_brain_training.json` - 7 game-specific help topics
- `apps/core/context_processors.py` - Dynamic BRAIN_TRAINING_{GAME_SLUG} context_id generation

---

## Dashboard Performance & Caching

### Overview
Dashboard load time optimized from 20+ seconds to 2-3 seconds through query optimization and intelligent caching.

### Improvements
- Fixed N+1 queries in medicine loading with `prefetch_related`
- Moved Google Calendar sync to background thread
- Aggregation for adherence statistics (single query vs. per-dose iteration)
- Cache invalidation via Django signals (medicine, workout, journal actions)
- DashboardCacheService for structured cache management

### Key Files
- `apps/dashboard/cache.py` - DashboardCacheService
- `apps/dashboard/signals.py` - Cache invalidation on data changes
- `apps/dashboard/views.py` - Optimized data loading

---

## Medicine Adherence Calculation

### Overview
Critical fix to medicine adherence reporting. Previous formula only counted logged doses, giving false 100% adherence rates.

### Old Formula (Wrong)
```
taken / (taken + missed) * 100
```
Only counted doses the user explicitly logged as taken or missed. If a user simply forgot (didn't log at all), it wasn't counted — resulting in artificially high adherence.

### New Formula (Correct)
```
taken / (expected - skipped) * 100
```
Counts ALL expected doses based on schedule, minus intentionally skipped ones. Missed/unlogged doses now correctly reduce the percentage.

### Single Source of Truth
- `apps/health/medicine_utils.py` - One function used by all 4 consumers:
  - `apps/ai/dashboard_ai.py` - AI insight generation
  - `apps/dashboard/cache.py` - Dashboard tile display
  - `apps/ai/personal_assistant.py` - Assistant queries
  - `apps/health/trend_tracking.py` - Trend analysis

### Tests
- `apps/health/tests/test_medicine_adherence.py` - 23 tests

---

## Chief of Staff — Personal Operating System

### Overview
The Chief of Staff (CoS) is the app's Life Operating System layer. It sits on top of all WLJ data and intelligence engines to orchestrate the user's day — building daily plans, detecting drift from commitments, and intervening at the right level.

### Personal Operating Blueprint
Users configure their blueprint at `/api/blueprint/` defining:
- **Operating Style** — Executive CoS, Calm Guide, Minimal, Coach, or Custom
- **Life Pillars** — Ranked list of what matters most (Faith, Health, Purpose, etc.)
- **Tier 1 Protected Behaviors** — Identity-defining non-negotiables protected aggressively
- **Interruption Tolerance** — Low/Medium/High controls intervention aggressiveness
- **Sleep & Wake Preferences** — Target duration and wake time policy

### Non-Negotiables
Behaviors that must happen every day (or on specific days):
- Each has a behavior key, time window, frequency, and optional hard deadline
- Tier 1 non-negotiables are protected by Rule B: only displaced if all other options exhausted
- The system monitors completion and escalates if deadlines approach

### Daily Architecture Engine
Each night, the system builds tomorrow's plan:
1. Sleep blocks placed first
2. Tier 1 non-negotiables scheduled in preferred windows
3. Calendar events and tasks fill remaining time
4. Buffer blocks added for transitions
5. If disrupted ("curveball"), the system re-optimizes around it

### Drift Detection
- **Drift Events** — Missed medications, skipped workouts, broken fasts, etc.
- **Drift Score** — Daily aggregate (0-100) weighted by tier importance
- **Drift Prediction** — 24h/72h probability of future drift

### Intervention Engine (5 Levels)
| Level | Name | Behavior |
|-------|------|----------|
| 0 | Silent | Logged but not shown |
| 1 | Nudge | Subtle reminder |
| 2 | Ping | Attention-getting notification |
| 3 | Interrupt | Modal or prominent alert |
| 4 | Friction Gate | Must acknowledge with evidence before proceeding |

### CoS UI Components
- **Command Mode** — Full-screen dashboard with plan, drift status, alerts, text/voice input
- **Assistant Panel** — Pinned right panel (desktop) / pull-up panel (mobile) with plan-at-a-glance
- **Arrival Briefing** — Morning summary shown when user first visits the dashboard
- **Command Brief** — Weekly pressure points and upcoming commitments
- **Chat Widget** — Floating chat drawer for quick AI conversations

### Proactive Questions & Calibration
During initial calibration, the CoS asks getting-to-know-you questions. After calibration, it continues with relationship-deepening questions. Learned profile data (values, sacred items, goals) is injected into the system prompt for personalization.

### Post-Event Reflection Loops
After significant events, the system queues a brief morning reflection check-in. Users answer a few questions about how the event went and capture action items.

### Relationship Intelligence
Tracks important people with relationship types, importance tiers, and interaction cadence targets. Detects when the user hasn't connected with someone too long and suggests reconnection. People are extracted from journal entries and reflections.

### Governance Onboarding
When a user first enables the CoS, a governance session classifies their enabled modules, sets up non-negotiables, and asks for the CoS display name.

### Configurable Display Name
Users can rename the CoS via settings or natural language ("Call yourself Max"). The name persists in `UserPreferences.cos_display_name` and is available as `{{ cos_display_name }}` in all templates.

### Key Files
- `apps/core/blueprint/` — All CoS models, governance, engines, human language
- `apps/core/ai_governance/` — Alignment sessions, governance profile
- `templates/components/cos_command_mode.html` — Command mode UI
- `templates/components/assistant_panel.html` — Assistant panel UI
- `templates/components/cos_arrival_briefing.html` — Morning briefing
- `templates/ai/cos_settings.html` — CoS settings page
- `apps/dashboard/views.py` — Dashboard views with CoS context

---

## Voice Conversation Mode

### Overview
Users can have hands-free voice conversations with the AI assistant. The microphone stays active through the full speak → AI responds → TTS → speak again cycle, eliminating the choppy start/stop between each utterance.

### How It Works
1. User clicks the microphone button in Command Mode or the Chat Widget
2. Web Speech API captures speech and converts to text
3. Text is sent to the AI API with `voice_input: true` in page_context
4. System prompt injects voice-mode instructions so AI responds conversationally (no markdown, no bullet points)
5. Response is spoken via SpeechSynthesis text-to-speech
6. Mic reactivates for the next utterance
7. User clicks mic again to exit voice mode

### TTS Voice Selection
Priority-ordered voice selection: Samantha (macOS) > Karen > Moira > Google US English > first English non-male voice. Rate: 0.95, Pitch: 1.05 for warmth.

### Key Files
- `templates/components/cos_command_mode.html` — Voice input/output in command mode
- `templates/components/chat_widget.html` — Voice input/output in chat drawer
- `apps/ai/personal_assistant.py` — Voice-mode system prompt injection

---

## Finance Module

### Overview
The finance module (`apps/finance/`) provides personal financial tracking with bank connections, transactions, budgets, and reports. Currently gated behind the `finance_enabled` feature flag.

### Features
- **Bank Connections** — Connect bank accounts via Plaid for automatic transaction syncing
- **Accounts** — Track bank accounts, credit cards, and cash accounts with balances
- **Transactions** — View, categorize, and search financial transactions
- **Categories** — Manage transaction categories for expense/income organization
- **Budgets** — Set monthly budgets by category and track spending
- **Recurring Transactions** — Define recurring income/expenses for forecasting
- **Reports** — Spending trends, income vs expenses, category breakdowns
- **CSV Import** — Import transactions from bank CSV exports

### Key Files
- `apps/finance/` — Models, views, services
- `apps/finance/plaid_service.py` — Plaid integration
- `templates/finance/` — All finance templates
- `apps/finance/urls.py` — URL patterns

---

## Nutrition Log Upgrade

### Overview (Feb 2026)
Major 7-phase rebuild of the nutrition tracking system, improving data accuracy, adding copy/template features, and polishing the mobile experience.

### Phase Highlights
1. **Data Model Redesign** — Snapshot nutrients at log time, audit trails, meal templates, overrides, label evidence
2. **Correct Nutrient Math** — Nutrients stored per-serving with multiplier, not pre-multiplied
3. **Copy Features** — Copy individual food entries, entire meals, or full days to other dates
4. **Meal Templates** — Save frequently-eaten meals as reusable templates for one-tap logging
5. **Barcode Accuracy** — FatSecret barcode integration with per-serving validation
6. **Source Badges** — Visual indicators showing where nutrition data came from (FatSecret, AI, Saved, Manual)
7. **UI/UX Polish** — Date navigation arrows, sticky daily totals, improved mobile forms

### Key Files
- `apps/health/views.py` — Nutrition views (NutritionHomeView, FoodEntryCreateView, etc.)
- `apps/health/models.py` — FoodEntry, MealTemplate models
- `templates/health/nutrition/` — Nutrition templates

---

## Intelligence Engine Stack

### Overview
The app uses a 14-engine cognitive pipeline organized in three phases. For full architecture details, see `docs/INTELLIGENCE_ARCHITECTURE.md`.

### Phase 1: Interpretation Engines
| Engine | Code | Purpose |
|--------|------|---------|
| Health Trend Interpretation | HTIE | Detects health data trends and anomalies |
| Spiritual/Life Context Mapping | SLCME | Maps faith and life events to meaning |
| User Activity Intelligence Observer | UAIO | Tracks user behavior patterns |

### Phase 2: Execution Engines
| Engine | Code | Purpose |
|--------|------|---------|
| Sentiment Understanding | SUE | Understands emotional tone in text |
| Pattern & Gap Learning Optimizer | GLOE | Identifies behavioral patterns and gaps |
| Dynamic Briefing | DBE | Generates personalized daily briefings |
| Insight Synthesis | ISE | Combines multi-domain data into insights |
| Weekly Intelligence Report | WIRE | Produces weekly intelligence summaries |

### Phase 3: Post-Execution Engines
| Engine | Code | Purpose |
|--------|------|---------|
| Proactive Insight | PIE | Fires domain-specific insights proactively |
| Predictive Risk & Intervention | PRIE | Predicts risks and suggests interventions |
| State Awareness | SAE | Maintains real-time state across domains |
| Proactive Guidance | PGE | Generates actionable coaching guidance |
| Evidence & Explainability | E3 | Provides evidence chains for AI decisions |
| Delivery & Notification | DNE | Routes intelligence to the right channel |

### Integration Pattern
New features must: fire PIE events for insight detection, fire PRIE predictions for risk assessment, and register SAE state providers for real-time tracking. See `docs/ENGINE_INTEGRATION_GUIDE.md` for step-by-step patterns.

---

## Body Transformation Protocol

### Overview
Complete body transformation intelligence system enabling users to set protocols (cut, bulk, recomp, maintenance, custom) with target weight, body fat %, and end date. The AI monitors progress across all health domains.

### Components
- **TransformationProtocol model** — Protocol type, targets, date range
- **Transformation Dashboard** (`/dashboard/transformation/`) — Trend charts for weight, body fat, calories, protein, fasting, workouts
- **Transformation Score** — Composite 0-100 metric from nutrition compliance, fasting consistency, workout frequency, and recovery
- **Momentum Score** — How many health domains are actively being engaged
- **Shopping Lists** — ShoppingList/ShoppingItem models linked to protocols

### Intelligence Integration
All 4 post-execution engines are wired:
- **SAE** — Real-time transformation state tracking
- **PIE** — Calorie trend, protein deficit, workout plateau, fasting consistency insights
- **PRIE** — Weight projection, strength progression, protocol success probability
- **PGE** — Personalized coaching recommendations

### Key Files
- `apps/health/models.py` — TransformationProtocol, ShoppingList, ShoppingItem
- `apps/dashboard/views.py` — TransformationDashboardView
- `templates/dashboard/transformation/` — Dashboard templates

---

## Admin Guide

### Overview
Staff documentation system providing a comprehensive guide to the WLJ system. Available at `/admin-console/guide/`.

### Structure
- **20 sections, 54+ articles** covering system overview, intelligence architecture, all engines, modules, security, deployment, and developer reference
- **Core articles** — Code-maintained, auto-synced on deploy, locked from editing
- **Supplemental articles** — Created/edited by staff from the Manage Articles page
- **Auto-synchronizing** — CoS documentation registry keeps admin guide in sync with code

### Key Files
- `apps/admin_console/models.py` — AdminGuideSection, AdminGuideArticle
- `apps/admin_console/views.py` — AdminGuideView, AdminGuideManageView
- `apps/admin_console/fixtures/admin_guide.json` — Fixture content
- `templates/admin_console/guide/` — Guide templates

---

## Workout Plans & Training Splits

### Overview
Structured workout programming system allowing users to create named plans with day-of-week scheduling and template grouping.

### Features
- **WorkoutPlan model** — Named plan with optional link to transformation protocol
- **WorkoutSchedule model** — Day-of-week assignment with preferred time and linked workout template
- **Training Splits** — Organize templates into splits (Push/Pull, Upper/Lower, etc.)
- **25 tests** covering model behavior and plan management

### Key Files
- `apps/health/models.py` — WorkoutPlan, WorkoutSchedule
- `apps/health/views.py` — Plan management views
- `apps/health/tests/` — Test coverage

---

## Additional Jan-Feb 2026 Enhancements

### Scroll Position Preservation
- Pages remember scroll position after form actions (medicine Take/Skip, task toggles, quick-log)
- Reusable component: `templates/components/scroll_preserve.html` using sessionStorage
- Applied to: Medicine home, Organize home, Prayer list, Water list

### Help System Expansion
- Grew from 33 to 82 context-aware help topics
- Covers all major views across health, journal, faith, purpose, settings, admin
- Brain training game-specific help (7 topics with rules/controls/tips)
- Auto-mapping URL paths to help context IDs in `apps/core/context_processors.py`
- Module fallback system in `apps/help/views.py`

### Favorites System
- URL normalization (strips query params for matching)
- Increased MAX_FAVORITES from 10 to 16
- Dynamic dropdown sizing

### Health Home Labs Card
- Card showing lab result count, abnormal count, upload button
- Links to full labs summary view

### Notification Service Fixes
- Fixed daily digest recipient address
- Fixed trial_expired page errors
- Disabled notifications for app review account
- Downgraded SMS service logging (prevents admin email spam)

---

*Last updated: 2026-02-19*
