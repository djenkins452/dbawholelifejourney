# ==============================================================================
# File: docs/wlj_claude_features.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Detailed feature documentation for reference when needed
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-12-28
# Last Updated: 2026-02-20
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
26. [Quick Links with Mobile Deep Linking](#quick-links-external-links-with-mobile-deep-linking) *(Feb 2026)*
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
40. [Time Command Center (Calendar Engine)](#time-command-center-calendar-engine) *(Feb 2026)*
41. [Users & Authentication](#users--authentication)
42. [Core Infrastructure](#core-infrastructure)
43. [Dashboard](#dashboard)
44. [Journal](#journal)
45. [Life & Organization](#life--organization)
46. [Admin Console](#admin-console)
47. [Help System](#help-system)
48. [Mobile API & iOS Support](#mobile-api--ios-support)
49. [Security Assessment](#security-assessment)
50. [Ops Command Center (Intelligence Monitoring)](#ops-command-center-intelligence-monitoring)
51. [Calendar Engine (Technical Reference)](#calendar-engine-technical-reference)
52. [Owner Financial Command Center](#owner-financial-command-center) *(Feb 2026)*

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
| `/assistant/` | `AssistantDashboardView` | Redirects to dashboard (legacy — CoS panel is the single chat interface) |
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
`apps/ai/tests/test_personal_assistant.py` - 61 tests

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
`apps/health/tests/test_nutrition.py` - 94 tests

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
`apps/health/tests/test_medicine.py` - 100 tests

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
- Uses OpenAI GPT-4o model
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
`apps/health/tests/test_medical_providers.py` - 36 tests covering:
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
`apps/scan/tests/` - 107 tests including:
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
33 tests in `apps/faith/tests/test_saved_verses.py`

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

## Quick Links (External Links) with Mobile Deep Linking

### Overview
Users can save up to 10 external links (patient portal, bank login, pharmacy site, etc.) accessible from the profile dropdown and mobile menu. Links support **mobile app deep linking** — on mobile devices, links with an app URL (e.g., `chase://`, `bofa://`, `mychart://`) attempt to open the native app first, with automatic fallback to the website if the app isn't installed.

### Features
- Up to 10 saved links per user
- **Mobile deep linking** — optional `mobile_app_url` per link (e.g., `chase://`, `bofa://`)
- **Device-aware redirect** — `/user/open-link/<id>/` detects mobile via User-Agent, renders deep link page with 1.5s fallback to web URL
- **Categories** — General, Finance & Banking, Health & Medical, Work & Productivity, Social & Communication, Other
- **Usage tracking** — `usage_count` incremented atomically on each click
- **Edit modal** — inline editing of name, URL, mobile URL, and category without page reload
- URL validation on save
- AJAX add/delete/update (no page reload)
- 60-second per-user cache for performance
- Accessible from profile dropdown and mobile navigation
- Django admin with deep link configuration fieldset
- **Intelligence hook** — `get_most_used_links(user, limit, days)` for future AI surfacing

### Deep Link Flow
1. User clicks link in profile menu → routed to `/user/open-link/<id>/`
2. View increments `usage_count` and checks User-Agent
3. **Desktop**: 302 redirect to `url`
4. **Mobile + `mobile_app_url` set**: Renders redirect template that attempts deep link via hidden iframe + `window.location`, with 1.5s timer fallback to web URL
5. **Mobile + no `mobile_app_url`**: 302 redirect to `url`

### Common App URLs
| App | Deep Link |
|-----|-----------|
| Chase Bank | `chase://` |
| Bank of America | `bofa://` |
| Capital One | `capitalone://` |
| Schwab | `schwab://` |
| Venmo | `venmo://` |
| PayPal | `paypal://` |
| MyChart | `mychart://` |

### Key Files
- `apps/users/models.py` - ExternalLink model with deep link fields
- `apps/users/views.py` - CRUD + redirect views (QuickLinkOpenView, QuickLinkUpdateView)
- `apps/users/urls.py` - Quick link endpoints including `/open-link/<id>/`
- `apps/users/admin.py` - ExternalLinkAdmin with deep link fieldset
- `apps/core/context_processors.py` - Links injected into template context with new fields
- `templates/users/quick_link_redirect.html` - Deep link redirect template with JS fallback
- `templates/users/preferences.html` - Quick Links UI with edit modal

### Tests
- `apps/users/tests/test_quick_links.py` - 40 tests (model, API create/delete/update, redirect, device detection, usage counter, security, context processor)

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
- **Assistant Panel** — Pinned right panel (desktop) / pull-up panel (mobile) with Chat + Status tabs
- **Chat Timestamps** — Every message shows the time below the bubble (e.g. "2:30 PM"), aligned to the message side. Date separators ("Today", "Yesterday", "Monday, Feb 19") appear at day boundaries when scrolling through history.
- **Arrival Briefing** — Morning summary shown when user first visits the dashboard
- **Command Brief** — Weekly pressure points and upcoming commitments

### AI Model & Prompt Architecture
- **Model:** GPT-4o for both response generation and intent recognition (intent upgraded from GPT-4o-mini). Configurable via `OPENAI_INTENT_MODEL` setting.
- **Prompt hierarchy:** Priority-ordered layers — personality and relationship instructions first, user knowledge second, operational context last. This ensures the CoS maintains warmth and perceptiveness even when loaded with situational data.
- **Situational awareness:** Compact context injection with schedule, calendar, medication, insights, predictions, and relationship signals. Raw metrics (drift scores, tier weights, override frequencies) are computed internally but not injected into the prompt.
- **Temperature:** 0.65 for conversational warmth (0.4 for data-heavy responses)

### Contextual Intelligence *(Feb 2026)*
Major upgrade to CoS reasoning and context awareness:
- **Expanded context window:** 40 messages of history (up from 15), with 20 messages in the user prompt for conversational threading. Response token budgets: brief 400, adaptive 800, deep 1200.
- **Context-priority routing:** Per-page-type disambiguation instructions. When the user is on a reading plan page, scripture context is prioritized over conversation history. When on a journal, goal, task, or prayer page, the page content is prioritized. Prevents "topic mixing" where CoS answers about routines when the user asks about scripture.
- **Rich page content capture:** Frontend captures goal milestones/progress/target dates, habit streaks/completion info, scripture text (up to 2000 chars), and sends all content to the backend for injection into the system prompt.
- **Session activity tracking:** Tracks page visits in `sessionStorage` (last 10 pages). Navigation history is sent with each message and injected into the system prompt as "SESSION ACTIVITY" so CoS understands the user's browsing flow and intent.
- **Conversation topic threading:** Detects whether the user is asking about the current page ("this", "it", "here") or continuing a previous conversation thread ("going back to", "you said", "earlier"), and injects a topic signal hint.
- **Pre-response reasoning:** Chain-of-thought "think before speaking" instruction injected into every user prompt. CoS silently reasons through: (1) user's current context, (2) most likely topic, (3) relevant data, (4) what NOT to talk about — before generating the visible response.

### Long-Term Memory (RAG) *(Feb 2026)*
Vector-based semantic memory so CoS can reference past conversations naturally:
- **Embedding storage:** Each conversation turn is embedded via OpenAI `text-embedding-3-small` (1536 dimensions) and stored in `ConversationMemory` model. 500-memory cap per user with automatic pruning.
- **Semantic retrieval:** Before each response, the current message is embedded and compared against past memories using cosine similarity. Top-5 matches above 0.35 threshold are retrieved.
- **System prompt injection:** Retrieved memories are formatted with natural time labels ("Last Tuesday", "2 weeks ago") and injected as "RELEVANT PAST CONVERSATIONS". CoS references them naturally ("You mentioned last week...").
- **Topic tagging:** Each memory is auto-tagged with detected topics (faith, health, goals, tasks, journal, relationships, finance) for potential filtering.
- **Cost:** ~$0.02 per 1M tokens for embeddings — roughly $0.00002 per conversation turn.
- **Key files:** `apps/ai/memory_service.py`, `apps/ai/models.py` (ConversationMemory)

### Response Quality Validation *(Feb 2026)*
Post-generation check that catches context mismatches before the response reaches the user:
- **Scripture mismatch detection:** If user is on a reading plan page and asks about scripture, but the response mentions routines/schedule/tasks, it triggers regeneration with explicit correction.
- **Goal/task mismatch detection:** If user references "this" on a goal/task page but the response doesn't mention any words from the goal/task title, it triggers regeneration.
- **Journal mismatch detection:** If user asks about "this entry" but response doesn't reference any words from the journal body, it triggers regeneration.
- **Zero extra cost on success:** Validation is keyword-based (no API call). Only costs an extra API call when a mismatch is detected.

### Expanded Learning Patterns *(Feb 2026)*
Extended the learning extractor with new categories:
- **Explanation preferences:** Detects when users say "keep it brief", "go deeper", "just the basics", etc. Stored in profile for response style adaptation.
- **Time patterns:** Detects time-of-day behavioral patterns ("every morning I...", "my evening routine includes..."). Stored for temporal context awareness.

### Proactive Questions & Calibration
The CoS has a relationship-building introduction flow before it starts managing the user's day:
- **11 calibration questions** covering: core people, non-negotiables, preferred activities, accountability style, communication frequency, and focus areas
- **Data-aware questions:** The system gathers a live snapshot of ALL user data (weight, goals, journals, faith, medicines, habits, workouts, vitals, labs, nutrition, fasting, finances, etc.) and injects it into the system prompt so the AI references what it already knows instead of asking generic questions
- **Questions cycle:** After all 11 are asked, they loop back for deeper follow-ups. No auto-complete — only the user decides when they're done
- **User-controlled completion:** User finishes by saying "I think you know me well enough" (triggers `complete_calibration` intent) or clicking "I'm Ready — Let's Work" button
- **Listening mode during calibration:** All action intents (log food, start fast, log weight, etc.) are disabled. The AI absorbs what the user shares and reflects it back — it does NOT execute commands
- **Banner states:** First visit ("Let's Go →"), in-progress ("Continue →"), ready to finish (two buttons: "Keep Going" / "I'm Ready — Let's Work")
- **System injection priority:** Calibration injection is PREPENDED before all other system prompt content with mandatory override headers
- **Key files:** `apps/core/blueprint/cos_governance.py` (calibration engine, `build_calibration_system_injection()`, `_gather_user_snapshot()`), `apps/ai/personal_assistant.py` (`_is_calibration_active()`, `_try_calibration_intents()`), `templates/components/cos_command_mode.html` (banner)
- After calibration, the system continues with relationship-deepening questions. Learned profile data (values, sacred items, goals) is injected into the system prompt for personalization.

### Post-Event Reflection Loops
After significant events, the system queues a brief morning reflection check-in. Users answer a few questions about how the event went and capture action items.

### Relationship Intelligence
Tracks important people with relationship types, importance tiers, and interaction cadence targets. Detects when the user hasn't connected with someone too long and suggests reconnection. People are extracted from journal entries and reflections.

### Executive Operator (Behavioral Intelligence)
Transforms the CoS from reactive assistant into proactive executive operator:
- **Morning Executive Briefing** — First-of-day structured greeting with sleep data, approaching life events, medication/health gates, day overview narrative, and journal pattern follow-up. Replaces simple greeting injection with a multi-section briefing service.
- **Session Gap Detection** — Computes time since last interaction, translates to human language ("It's been 3 days"), summarizes what changed during absence (missed journals, medication gaps, overdue tasks).
- **Rolling Conversation Memory** — When messages exceed 20, generates an AI summary of older messages (beyond the 15-message window) using gpt-4o-mini. Stored in `conversation.context_summary` and injected into every response for continuity.
- **Life Event Surfacing** — Queries `SignificantEvent` and `LifeEvent` models for approaching events (14-day window in CoS context, 7-day window in morning briefing). Cross-references with Person records for relational context.
- **Journal Review Intelligence** — Mood trend analysis (numeric scoring across last 5 entries, decline detection) and repeated health keyword detection (regex scan for pain/injury/fatigue terms across entries).
- **Health Gates** — Before tasks, checks medication adherence, active fasting window, and scheduled workouts. Instructs the AI to address health first.
- **Extended Learning Categories** — 3 new extraction patterns: health_concern, life_event_mention, commitment_made. Stored in UserLearnedProfile for cross-conversation recall.
- **Key files:** `apps/ai/executive_briefing.py`, `apps/ai/personal_assistant.py` (lines 2785+)
- **Tests:** 28 in `apps/ai/tests/test_executive_briefing.py`

### Governance Onboarding
When a user first enables the CoS, a governance session classifies their enabled modules, sets up non-negotiables, and asks for the CoS display name.

### Configurable Display Name
Users can rename the CoS via settings or natural language ("Call yourself Max"). The name persists in `UserPreferences.cos_display_name` and is available as `{{ cos_display_name }}` in all templates.

### Learning Mode & Priority System *(Feb 2026)*
Phase 1 of the CoS Foundational Restructure adds structured listening and priority accountability:

**Learning Mode** — A system-wide state where the CoS listens and learns without taking actions:
- UAIO execution, PIE insights, PRIE predictions, SAE writes, and action audit entries are suppressed
- SAE reads, conversation memory, governance evaluation, and safety remain fully active
- SLCME stores only preference/value mappings actively; execution-relevant types stored inactive for Phase 2 review
- Lighter system prompt injection during Learning Mode (excludes active insights/predictions/executive block)
- Toggle UI on CoS Settings page with enter → exit → confirm flow
- Exit confirmation: CoS summarizes what it learned, user confirms before execution resumes

**Priority Weighting** — Declare what matters most:
- `UserPriorityProfile` model with 3 tiers: Non-Negotiable (weight 3.0), Important (2.0), Flexible (1.0)
- Hierarchical drill-down onboarding: top-level modules → health physical/cognitive → specific sub-areas
- Priority onboarding injected into Learning Mode system prompt (one question at a time)

**Priority Conflict Detection** — Behavioral accountability:
- Compares declared priorities vs 7-day behavior across health, faith, purpose, journal
- Health sub-module awareness (weight, activity, sleep, medications, nutrition, fasting)
- Tier 1 gaps → accountability tone, Tier 2/3 → curious reflection tone
- Respects partial task progress (>0% = "worked on")

**System Gap Awareness** — Proactive transparency:
- Surfaces known system limitations (from ImprovementTaskModel) in governance prompt
- CoS acknowledges what it can't do yet instead of guessing

**Partial Task Progress** — Track work-in-progress:
- `progress_percentage` (0-100) range slider on task edit form
- `progress_state` JSON for flexible step tracking
- Counts toward priority conflict resolution

### Key Files
- `apps/core/blueprint/` — All CoS models, governance, engines, human language
- `apps/core/blueprint/learning_mode.py` — Learning Mode state management
- `apps/core/blueprint/priority_conflict_detector.py` — Priority vs behavior conflicts
- `apps/core/blueprint/priority_questions.py` — Priority onboarding drill-down
- `apps/core/blueprint/system_gap_awareness.py` — System limitation transparency
- `apps/core/ai_governance/` — Alignment sessions, governance profile
- `templates/components/cos_command_mode.html` — Command mode UI
- `templates/components/assistant_panel.html` — Assistant panel UI
- `templates/components/cos_arrival_briefing.html` — Morning briefing
- `templates/ai/cos_settings.html` — CoS settings page + Learning Mode toggle
- `apps/dashboard/views.py` — Dashboard views with CoS context

### CoS Performance — Instant-Readiness Architecture *(Feb 2026)*
Full-stack latency elimination so Beth feels instant and responsive:
- **Intent-Based Pre-Warm:** Frontend fires lightweight `/assistant/api/wake/` on input focus and mobile panel open (30s cooldown). Warms DB connections and pre-builds CoS context before the user sends a message.
- **Redis Context Cache:** `build_cos_context()` results (15-20 DB queries) cached in Redis with 45-second TTL. Cache miss falls through to existing behavior — never serves stale data.
- **Fast-Path Execution:** `send_message()` and `_generate_response()` check readiness cache before full rebuild, eliminating ~50-150ms of non-LLM latency per pre-warmed request.
- **Background Post-Response Ops:** Learning extraction, correction detection, and pattern detection moved off response path to background threads.
- **Celery Keep-Alive:** Beat task (30s) refreshes context cache for recently active users (cap: 5 per cycle).
- **Readiness State Tracking:** Per-user states (`cold → warming → ready → active`) tracked in Redis to prevent duplicate warm-ups.
- **Observability:** Logging telemetry for wake hit/miss rates, context build times, fast-path vs full-path usage.
- **Key files:** `apps/ai/readiness_cache.py`, `apps/ai/readiness_telemetry.py`, `apps/ai/tasks.py`
- **Tests:** 19 in `apps/ai/tests/test_readiness_cache.py`

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

## 40. Time Command Center (Calendar Engine)

**Added:** Feb 2026
**App:** `apps/calendar_engine/`
**Templates:** `templates/calendar_engine/`

### Overview
The Time Command Center (TCC) is the user's daily schedule hub. It provides multiple calendar views, life balance tracking, smart gap detection, and NLP-powered quick event creation. The CoS panel includes a clock icon shortcut to the TCC.

### Features
- **Multiple views:** Today timeline, 3-Day, Week, Agenda, and full Month grid
- **Month view:** Full calendar grid with color-coded domain chips, event popovers, month navigation
- **Life balance bar:** Visual breakdown of time allocation across life domains (health, faith, work, family, etc.)
- **Smart gap detection:** AI identifies unused time blocks and suggests activities
- **NLP quick add:** Natural language event creation ("Pickleball tomorrow at 6pm" → creates event titled "Pickleball")
- **Event CRUD:** Create, edit, move, and delete events via API
- **Conflict detection:** Warns when new events overlap protected Tier-1 commitments
- **CoS schedule awareness:** Calendar events injected into every CoS LLM prompt with time-relative status tags ([NOW], [SOON], [MISSED], [done])
- **Morning greeting enrichment:** CoS references schedule proactively when user sends a greeting
- **Domain metrics API:** Per-domain time allocation percentages
- **Manage Events page:** Full CRUD management view

### Key Files
- `apps/calendar_engine/models.py` — CalendarEvent, RecurrenceRule models
- `apps/calendar_engine/views.py` — All views (dashboard, month, API endpoints)
- `apps/calendar_engine/urls.py` — URL routing
- `apps/calendar_engine/services/nlp_parse.py` — NLP quick-add parser with temporal cleanup
- `apps/calendar_engine/services/metrics.py` — Domain balance calculations
- `apps/calendar_engine/services/suggestions.py` — Smart gap detection
- `apps/core/ai_orchestrator/cos_context.py` — Calendar context injection into CoS
- `apps/ai/personal_assistant.py` — Morning greeting enrichment
- `templates/calendar_engine/dashboard.html` — TCC dashboard with view toggles
- `templates/calendar_engine/month.html` — Full month grid view
- `templates/calendar_engine/manage.html` — Event management page
- `templates/components/assistant_panel.html` — CoS panel with TCC clock icon link

### Tests
- 31 tests in `apps/calendar_engine/tests.py`
- Covers: NLP parsing, recurrence, API CRUD, conflict detection, gap suggestions, domain balance, month view

---

## Users & Authentication

**App:** `apps/users/`
**Templates:** `templates/users/`, `templates/account/`

### Overview
The users app provides the custom User model (email-based authentication via django-allauth), UserPreferences for per-user settings, onboarding wizard, biometric/WebAuthn login, MFA, quick links, data export, and account management. It is the foundational identity layer that every other app depends on.

### Features
- **Custom User model** — Email as unique identifier (no username), avatar, date of birth, admin/staff flags
- **UserPreferences** — One-to-one settings: theme (10 personality themes + custom), module toggles, sub-feature flags, AI settings, timezone, coaching style, CoS display name, quiet hours, notification preferences
- **Onboarding wizard** — 6-step flow (welcome → theme → modules → AI → location → complete) enforced by middleware
- **Biometric login** — WebAuthn/FIDO2 for Face ID, Touch ID, and security keys; multi-credential per user
- **MFA** — Email-based 6-digit codes with 10-minute expiry and rate limiting (5/hour)
- **Quick links** — User-defined external URL shortcuts with mobile deep linking support
- **Data export** — GDPR-compliant export (JSON/CSV/ZIP) spanning 20+ models across all apps
- **Account deletion** — Permanent deletion with `AccountDeletionAudit` trail
- **Module system** — `ModuleDefinition` registry + `UserModulePreference` for bottom nav ordering (Home + 4 modules + More)
- **Signup protection** — reCAPTCHA v3, COPPA age check (13+), geo-blocking (USA-only unless whitelisted), disposable email blocking, honeypot fields, `SignupAttempt` fraud detection with risk scoring

### Key Models
| Model | Purpose |
|-------|---------|
| `User` | Custom user with email auth, avatar, DOB |
| `UserPreferences` | Per-user settings (theme, modules, AI, timezone) |
| `WebAuthnCredential` | Biometric/FIDO2 credentials |
| `MFAEmailCode` | Temporary 6-digit email verification codes |
| `TermsAcceptance` | Terms of service acceptance audit trail |
| `SignupAttempt` | Signup fraud detection with risk scoring |
| `AccountDeletionAudit` | GDPR account deletion records |
| `ExternalLink` | Quick link shortcuts with deep link fields |
| `ModuleDefinition` | System-wide module registry |
| `UserModulePreference` | Per-user module ordering and visibility |
| `IPBlocklist` | Blocked IPs (individual or CIDR range) |
| `DisposableEmailDomain` | Blocked temporary email services |
| `AllowedInternationalEmail` | Whitelist for geo-block bypass |

### Key Views & Endpoints
- `/user/profile/`, `/user/profile/edit/` — Profile display and editing
- `/user/preferences/` — Main preferences page (theme, modules, AI, timezone)
- `/user/onboarding/start/`, `/user/onboarding/step/<step>/` — Onboarding wizard
- `/user/accept-terms/` — Terms acceptance (enforced by middleware)
- `/user/biometric/*` — WebAuthn registration, login, credential management (7 endpoints)
- `/user/mfa/*` — MFA code send/verify for login and authenticated sessions (4 endpoints)
- `/user/data-export/`, `/user/data-export/download/` — GDPR data export
- `/user/delete-account/` — Account deletion with confirmation
- `/user/api/quick-links/*` — Quick link CRUD (3 endpoints)
- `/user/api/sub-feature-toggle/`, `/user/api/sub-features/` — Sub-feature management
- `/user/api/module-order/` — Module reordering
- `/user/api/ai-profile-builder/` — AI profile editing with streaming

### Middleware
- **TermsAcceptanceMiddleware** — Enforces terms acceptance and onboarding completion
- **SubscriptionRequiredMiddleware** — Enforces active subscription or valid trial
- **MFAEnforcementMiddleware** — Enforces MFA for staff and configured users
- **TimezoneMiddleware** — Activates user's timezone per request

### Key Files
- `apps/users/models.py` — All 13 models
- `apps/users/views.py` — 27+ views
- `apps/users/middleware.py` — 4 middleware classes
- `apps/users/services/data_export.py` — GDPR data export service
- `apps/users/services/recaptcha.py` — reCAPTCHA v3 verification
- `apps/users/services/geoip.py` — GeoIP country detection via ipinfo.io
- `apps/users/security.py` — PII hashing (email, IP, fingerprint)
- `apps/users/adapters.py` — Custom allauth adapter (honeypot, reCAPTCHA, signup logging)
- `apps/users/signals.py` — Auto-create preferences, cycle tracking auto-enable
- `apps/users/management/commands/` — create_superuser_from_env, purge_old_signups, setup_app_review_account

### Tests
- 233 tests in `apps/users/tests/`
- Covers: signup (COPPA, reCAPTCHA, geo-blocking), onboarding wizard, biometric login, MFA, preferences, data export, module ordering, quick links, middleware

### Integration Points
- Every app imports `User` and `UserPreferences` for auth and feature flags
- `apps/core/context_processors.py` reads module toggles and sub-feature flags
- `apps/billing/` checks subscription status via middleware
- `apps/mobile/` uses User for API token authentication
- `apps/ai/` reads AI settings and coaching style for personalization

---

## Core Infrastructure

**App:** `apps/core/`
**Templates:** `templates/core/`, `templates/components/`

### Overview
The core app is the shared infrastructure layer providing base models, middleware, context processors, the 14-engine intelligence architecture, the Chief of Staff blueprint system, notification delivery, activity tracking, and site configuration. It serves as the orchestration hub for the entire application.

### Features
- **Base models** — `TimeStampedModel`, `SoftDeleteModel` (30-day retention + `SoftDeleteManager`), `UserOwnedModel` (ownership + source tracking)
- **Site configuration** — `SiteConfiguration` singleton for branding, themes, feature toggles, legal links
- **Database themes** — `Theme` model with CSS variable generation (light/dark modes)
- **Dynamic choices** — `ChoiceCategory`/`ChoiceOption` for configurable dropdowns (mood, milestone_type, prayer_priority, etc.)
- **Notification system** — Category-based notifications with generic foreign key, read tracking, email delivery
- **Activity tracking** — `UserDailyActivity` per-day metrics, `UserActivityPattern` computed behavioral patterns
- **Release notes** — `ReleaseNote`/`UserReleaseNoteView` for "What's New" feature
- **Favorites** — `FavoritePage` (max 16) and `PageView` analytics
- **API request logging** — `APIRequestLog` with real-time anomaly detection (burst, error rate, 404 probing, auth failures)
- **Camera scan** — `CameraScan` for AI-powered food/medicine/receipt intake via camera

### Intelligence Architecture (15 Engines)
| Phase | Engine | Code | Location |
|-------|--------|------|----------|
| Interpretation | Health Trend Interpretation | HTIE | `ai_health_trends/` |
| Interpretation | Spiritual/Life Context Mapping | SLCME | `ai_spiritual/` |
| Interpretation | User Activity Intelligence | UAIO | `ai_activity/` |
| Execution | Sentiment Understanding | SUE | `ai_sentiment/` |
| Execution | Pattern & Gap Learning | GLOE | `ai_patterns/` |
| Execution | Dynamic Briefing | DBE | `ai_briefing/` |
| Execution | Insight Synthesis | ISE | `ai_insights/` |
| Execution | Weekly Intelligence Report | WIRE | `ai_weekly_report/` |
| Post-Execution | Proactive Insight | PIE | `ai_insights/` |
| Post-Execution | Predictive Risk & Intervention | PRIE | `ai_predictions/` |
| Post-Execution | State Awareness | SAE | `ai_state/` |
| Post-Execution | Proactive Guidance | PGE | `ai_guidance/` |
| Post-Execution | Evidence & Explainability | E3 | `ai_explain/` |
| Post-Execution | Delivery & Notification | DNE | `ai_delivery/` |
| Arbitration | Universal Arbitration Layer | UAL | `ai_arbitration/` |

### Universal Arbitration Layer (UAL)
- **Purpose:** Central reasoning layer between multi-engine signal generation and user-facing intervention
- **Pipeline:** Collect 13 signal sources → Normalise 14 dimensions → Classify scenario → Fuse cross-domain composites → Select intervention style → Build executive narrative → Log decision
- **Scenarios:** TIME_CRITICAL, HEALTH_CRITICAL, DRIFT_CRITICAL, MOOD_CRITICAL, RELATIONSHIP_CRITICAL, STABLE_EXECUTION
- **Composites:** LOW_CAPACITY_DAY, PHYSICAL_RISK, RELATIONAL_OPPORTUNITY, EMOTIONAL_OVERLOAD, RECOVERY_NEEDED, ALIGNMENT_CRISIS, DEADLINE_CONVERGENCE
- **Interventions:** DIRECTIVE, PROTECTIVE, ACCOUNTABILITY, SUPPORTIVE, STRATEGIC, EXECUTION
- **Key files:** `signal_collector.py`, `scenario_classifier.py`, `signal_fuser.py`, `intervention_engine.py`, `narrative_engine.py`, `arbitration_engine.py`
- **Model:** ArbitrationDecisionLog (decision logging for refinement)
- **Tests:** 42 tests in `apps/core/ai_arbitration/tests.py`
- **Integration:** Injected into personal_assistant.py after Executive Briefing, before final message generation

### Blueprint & CoS System
- `apps/core/blueprint/` — Personal Operating Blueprint with alignment, drift, intervention, recovery, and reflection engines
- `apps/core/blueprint/cos_governance.py` — Calibration system, daily briefing generation, calendar context injection, morning greeting logic, non-negotiables enforcement
- Models: `ArchitecturePlan`, `PersonalOperatingBlueprint`, `NonNegotiable`, `ScheduledBlock`, `DriftEvent`, `DriftScore`, `InterventionLog`

### Middleware
- **CSPNonceMiddleware** — Per-request nonce for Content Security Policy
- **ContentSecurityPolicyMiddleware** — Nonce-based CSP headers
- **PageViewTrackingMiddleware** — Records page views and daily activity
- **NoCacheHTMLMiddleware** — Prevents HTML caching
- **APIRequestLoggingMiddleware** — API logging with anomaly detection

### Context Processors
- `site_context()` — Site config, branding, reCAPTCHA key
- `theme_context()` — Theme, accent color, module toggles, sub-feature flags, CoS name
- `csp_nonce()` — CSP nonce for inline scripts
- `favorites_context()` — Favorites menu data
- `quick_links_context()` — External quick links
- `navigation_modules_context()` — Mobile/desktop nav modules
- `notifications_context()` — Unread notification count
- `help_context()` — Auto-provide help_context_id by URL matching

### Key Files
- `apps/core/models.py` — Base models, SiteConfiguration, Theme, Tag, Category, Notification, CameraScan, ReleaseNote, etc.
- `apps/core/views.py` — Landing page, notifications, favorites, restore, search history, 404 reporting, health check
- `apps/core/urls.py` — Routes for landing, notifications, favorites, API endpoints
- `apps/core/middleware.py` — CSP, page view tracking, API logging
- `apps/core/context_processors.py` — 8 context processors
- `apps/core/ai_orchestrator/` — Intelligence engine coordination
- `apps/core/blueprint/` — Blueprint + CoS governance system
- `apps/core/ai_state/`, `ai_guidance/`, `ai_briefing/`, etc. — Individual engine implementations
- `apps/core/encryption.py` — AES encryption utilities
- `apps/core/rate_limiting.py` — Rate limiting helpers
- `apps/core/management/commands/load_initial_data.py` — Fixture loader for themes, choices, release notes, help topics, teaching destinations

### Tests
- 160 tests in `apps/core/tests/`
- Covers: soft delete, notifications, favorites, context processors, API logging, activity patterns, release notes, blueprint engines

### Integration Points
- Every app inherits from `UserOwnedModel`, `SoftDeleteModel`, or `TimeStampedModel`
- Intelligence engines consume data from health, journal, faith, life, purpose, and finance apps
- Notification system delivers across SMS (`apps/sms`), email, and in-app channels
- Blueprint/CoS system integrates with calendar engine for schedule awareness

---

## Dashboard

**App:** `apps/dashboard/`
**Templates:** `templates/dashboard/`, `templates/dashboard/tiles/`

### Overview
The dashboard is the main landing page after login. It aggregates data from every module into configurable tiles, provides AI-generated insights, daily briefings, the Chief of Staff command brief, weather, transformation tracking, and personalized encouragement.

### Features
- **Configurable tiles** — 30+ tile types with drag-and-drop reordering, show/hide, sizing (small/medium/large)
- **Module-aware rendering** — Tiles conditionally display based on enabled modules and user data
- **AI insights** — Pattern analysis across all modules with configurable coaching styles
- **Daily briefing** — DBE-generated intelligence summary with engagement tracking
- **Weekly report** — WIRE-generated weekly analysis
- **Command brief** — CoS architecture, alignment, drift, capacity, and non-negotiable status
- **State snapshot** — SAE real-time state across all domains
- **Guidance panel** — PGE evidence-based coaching (limit 5 active)
- **Transformation tracker** — Dedicated dashboard for body transformation metrics
- **Daily encouragement** — Curated messages with optional Scripture references
- **Weather widget** — Open-Meteo API with extreme weather alerts
- **Quarterly reviews** — Auto-generated retrospectives on quarter boundaries
- **Celebrations & nudges** — Achievement recognition and accountability reminders

### Key Models
| Model | Purpose |
|-------|---------|
| `DailyEncouragement` | Curated messages with scripture, themes, seasonal targeting |

### Key Views & Endpoints
- `/dashboard/` — Main dashboard (DashboardView)
- `/dashboard/transformation/` — Transformation metrics dashboard
- `/dashboard/api/config/` — Dashboard tile configuration (GET/POST)
- `/dashboard/api/config/reorder/` — Tile drag-and-drop reordering
- `/dashboard/api/config/tile/<tile_id>/` — Individual tile settings
- `/dashboard/api/weight-data/` — Weight chart data API
- `/dashboard/api/transformation-data/` — Transformation chart data API
- `/dashboard/tiles/journal/`, `/dashboard/tiles/encouragement/` — HTMX tile endpoints
- `/dashboard/api/quarterly-review/dismiss/` — Dismiss quarterly review
- `/dashboard/debug/` — Staff-only diagnostic endpoint

### Key Files
- `apps/dashboard/models.py` — DailyEncouragement model
- `apps/dashboard/views.py` — DashboardView (main), TransformationDashboardView, tile APIs
- `apps/dashboard/services/config_service.py` — Tile configuration management (30+ definitions)
- `apps/dashboard/cache.py` — Signal-based cache invalidation (5-minute timeout, section-based)
- `apps/dashboard/services/weather.py` — Open-Meteo weather API integration
- `templates/dashboard/home.html` — Main dashboard layout
- `templates/dashboard/transformation.html` — Transformation dashboard
- `templates/dashboard/tiles/` — 26 tile templates (ai_insights, daily_briefing, medicine_schedule, etc.)

### Tests
- 108 tests in `apps/dashboard/tests/`
- Covers: dashboard rendering, tile configuration, cache invalidation, weather service, transformation tracker, encouragement, API endpoints

### Integration Points
- Reads from every major app: journal (entries, streaks), health (weight, medicines, workouts, vitals, fasting, cycle), faith (prayers, verses), life (tasks, events, projects, birthdays), purpose (goals, habits), finance (recurring transactions), capture (pending uploads)
- Integrates SAE, DBE, WIRE, PGE for intelligence tiles
- Blueprint system provides command brief and alignment score
- Dashboard cache invalidated by signals from health, journal, faith, life, purpose, scan, capture apps

---

## Journal

**App:** `apps/journal/`
**Templates:** `apps/journal/templates/journal/`

### Overview
The journal app provides a full-featured writing and reflection system with multiple viewing modes, mood/emotion tracking, writing prompts, AI milestone detection, and cross-module entry linking. It is the primary qualitative data source for the intelligence engines.

### Features
- **Journal entries** — CRUD with title, body, entry date, mood (5 levels), word count, categories, tags, and emotions
- **Multiple views** — Entry list, calendar view, continuous page view, and book/flipbook view
- **Mood tracking** — Optional mood per entry (great/good/okay/low/difficult) with emoji display
- **Emotions** — Multi-select predefined emotions with emoji (separate from mood)
- **Writing prompts** — Curated prompts with optional Scripture references for faith users
- **Calendar view** — Monthly calendar with entry count indicators and navigation
- **Soft delete** — 30-day grace period with archive and permanent delete options
- **Bulk actions** — Multi-select delete and archive via JSON API
- **HTMX components** — Dynamic form loading, mood picker, tag creation modals
- **Entry linking** — Cross-module references via `EntryLink` (related, inspired_by, during, reflection_on)

### Key Models
| Model | Purpose |
|-------|---------|
| `JournalEntry` | Primary entry with title, body, mood, word_count, categories, tags, emotions |
| `JournalPrompt` | Curated writing prompts with optional Scripture and category |
| `Emotion` | Predefined emotions with emoji and display ordering |
| `EntryLink` | Cross-module references (source entry → target type + id) |

### Key Views & Endpoints
- `/journal/` — Journal home dashboard with stats, streak, recent entries, AI insight
- `/journal/entries/` — Entry list with filters (category, tag, mood, search)
- `/journal/calendar/` — Monthly calendar view with entry indicators
- `/journal/page-view/` — Continuous scroll view (50 per page)
- `/journal/book-view/` — Page-by-page flipbook view
- `/journal/new/` — Create entry (supports `?prompt=id` pre-fill)
- `/journal/<pk>/` — Entry detail with milestone suggestion
- `/journal/<pk>/edit/` — Edit entry
- `/journal/archived/`, `/journal/deleted/` — Archived and deleted entry lists
- `/journal/bulk/delete/`, `/journal/bulk/archive/` — Bulk actions
- `/journal/prompts/`, `/journal/prompts/random/` — Prompt browsing and random prompt (HTMX)
- `/journal/tags/*` — Tag CRUD (3 endpoints)
- `/journal/htmx/*` — HTMX endpoints for form fields, mood select, tag creation (3 endpoints)

### Key Files
- `apps/journal/models.py` — JournalEntry, JournalPrompt, Emotion, EntryLink
- `apps/journal/views.py` — 20+ views including HTMX and bulk action endpoints
- `apps/journal/forms.py` — JournalEntryForm, TagForm
- `apps/journal/signals.py` — People extraction from entry text via relationship engine
- `apps/journal/fixtures/prompts.json` — Curated writing prompts
- `apps/journal/management/commands/import_chatgpt_journal.py` — ChatGPT export importer

### Tests
- 107 tests in `apps/journal/tests/`
- Covers: entry CRUD, mood tracking, emotions, prompts, calendar view, bulk actions, soft delete, HTMX endpoints, tag management

### Integration Points
- **Intelligence pipeline** — `fire_intelligence()` on entry creation triggers SAE → PIE → PRIE chain
- **AI milestone detection** — Checks if entry text indicates goal milestone completion
- **People extraction** — Signal extracts person mentions via `apps.core.ai_relationships`
- **Dashboard** — Provides entries, streaks, mood distribution for dashboard tiles
- **Core** — Uses `UserOwnedModel`, `Category`, `Tag` from core

---

## Life & Organization

**App:** `apps/life/`
**Templates:** `templates/life/`

### Overview
The life app is a comprehensive personal operations system organizing projects, tasks, calendar events, household inventory, pets, recipes, shopping lists, documents, and significant events. It includes Google Calendar sync, Gmail task extraction, and recurring task automation.

### Features
- **Projects** — Long-running efforts with status (active/paused/completed/archived), priority, task progress tracking
- **Tasks** — Individual action items (standalone or project-linked), auto-prioritized from due dates, with recurrence support (daily/weekly/biweekly/monthly/yearly, specific weekdays)
- **Calendar events** — `LifeEvent` with timing, event types, location, recurrence, Google Calendar sync
- **Significant events** — Recurring annual events (birthdays, anniversaries, memorials) with SMS reminders and Person linkage
- **Inventory** — Household item documentation with photos, warranty tracking, condition assessment (for insurance)
- **Maintenance log** — Home repair/maintenance history with cost, provider, follow-up scheduling
- **Pets** — Pet profiles with medical records, vaccinations, vet visits, auto-birthday reminders
- **Recipes** — Family recipes with prep/cook times, servings, difficulty, favorites
- **Shopping lists** — Grocery planning with categorized items and completion tracking
- **Documents** — File storage via Cloudinary (insurance, legal, financial, medical, etc.) with expiration tracking
- **Google Calendar sync** — Two-way OAuth sync (import/export) with event type filters
- **Gmail task extraction** — AI-powered inbox scanning that creates tasks from email action items

### Key Models
| Model | Purpose |
|-------|---------|
| `Project` | Long-running efforts with tasks and phases |
| `Task` | Action items with priority, recurrence, email source tracking |
| `LifeEvent` | Calendar events with timing, recurrence, Google sync |
| `SignificantEvent` | Annual events (birthdays/anniversaries) with SMS reminders |
| `InventoryItem` | Household items with photos, warranty, condition |
| `MaintenanceLog` | Home maintenance records with cost and follow-up |
| `Pet` / `PetRecord` | Pet profiles with medical records |
| `Recipe` | Family recipes with metadata |
| `ShoppingList` / `ShoppingItem` | Grocery lists with categories |
| `Document` | File storage via Cloudinary with expiration tracking |
| `GoogleCalendarCredential` | Encrypted OAuth tokens for Google Calendar |
| `GmailCredential` / `ProcessedEmail` | Gmail OAuth and processed message tracking |

### Key Views & Endpoints
- `/life/` — Life home with task summary, upcoming events, stats, AI insight
- `/life/projects/*` — Project CRUD (5 views)
- `/life/tasks/*` — Task CRUD with toggle completion and bulk delete (5 views)
- `/life/calendar/`, `/life/events/*` — Calendar and event CRUD (5 views)
- `/life/inventory/*` — Inventory CRUD with photo management (8 views)
- `/life/pets/*` — Pet CRUD with medical records (6 views)
- `/life/recipes/*` — Recipe CRUD with favorites toggle (7 views)
- `/life/maintenance/*` — Maintenance log CRUD (6 views)
- `/life/documents/*` — Document CRUD with download/inline view (8 views)
- `/life/significant-events/*` — Significant event CRUD (6 views)
- `/life/calendar/google/*` — Google Calendar OAuth and sync (6 views)
- `/life/gmail/*` — Gmail OAuth and inbox scanning (7 views)

### Key Files
- `apps/life/models.py` — All 13 models
- `apps/life/views.py` — 44 views spanning all features
- `apps/life/services/recurrence.py` — Complex recurrence pattern service
- `apps/life/services/google_calendar.py` — Google Calendar API sync
- `apps/life/services/gmail.py` / `gmail_sync.py` / `email_processor.py` — Gmail scanning pipeline
- `apps/life/jobs.py` — Scheduled jobs: task priority recalculation (6:00 AM), recurring task processing (6:05 AM)
- `templates/life/` — 43 templates spanning all features

### Tests
- 226 tests in `apps/life/tests/`
- Covers: projects, tasks (including recurrence), events, inventory, pets, recipes, maintenance, documents, significant events, Google Calendar, Gmail scanning

### Integration Points
- **Calendar Engine** — Tasks, goals, and habits projected onto calendar via `projection.py`
- **AI relationships** — `SignificantEvent` links to `Person` model for relationship tracking
- **Dashboard** — Provides tasks, events, projects, birthdays for dashboard tiles
- **Core** — Uses `UserOwnedModel`, encryption for OAuth tokens, `get_user_today()` timezone helper

---

## Admin Console

**App:** `apps/admin_console/`
**Templates:** `apps/admin_console/templates/admin_console/`

### Overview
The admin console provides a custom admin interface for site management, project/task management with an executable task standard, test planning, system announcements, codebase metrics, data load tracking, and the Claude Code API for automated task execution.

### Features
- **Task management** — `AdminTask` with JSON description format (`{objective, inputs, actions, output}`), status transitions with validation, activity logging
- **Project management** — `AdminProject` with phases, auto-phase completion and unlock
- **Phase management** — `AdminProjectPhase` with sequential unlock logic
- **Task intake** — Human-friendly task creation form
- **Inline editing** — AJAX status and priority updates
- **System hardening** — Issue detection (stuck phases, stuck tasks), admin overrides with confirmation
- **Preflight checks** — System readiness validation before execution
- **Test planning** — `TestCycle`/`TestPhase`/`TestItem` for production release testing (300+ item templates)
- **System announcements** — Modal announcements with severity levels and scheduling
- **Data load tracking** — `DataLoadConfig` prevents redundant fixture loading
- **Email notification templates** — Admin-editable templates for 13 notification categories
- **Codebase metrics** — File counts, line counts, language analysis, git history
- **Admin guide** — Markdown documentation sections and articles
- **Claude Code API** — Ready task fetch, status updates, email processing for automated execution

### Key Models
| Model | Purpose |
|-------|---------|
| `AdminTask` | Executable tasks with JSON description, status transitions, blocking |
| `AdminProject` | Project container for tasks |
| `AdminProjectPhase` | Sequential phases with auto-unlock |
| `AdminActivityLog` | Immutable audit trail for task changes |
| `AdminTaskStatusConfig` / `PriorityConfig` / `CategoryConfig` / `EffortConfig` | Database-driven task configuration |
| `DataLoadConfig` | Tracks one-time data loader execution |
| `SystemAnnouncement` / `SystemAnnouncementDismissal` | System-wide announcements |
| `EmailNotificationTemplate` | Admin-editable email templates |
| `TestCycle` / `TestPhase` / `TestItem` | Production test planning |
| `AdminGuideSection` / `AdminGuideArticle` | Admin documentation |

### Key Views & Endpoints
- `/admin-console/` — Admin dashboard with system overview
- `/admin-console/projects/tasks/*` — Task CRUD with intake form and inline editing
- `/admin-console/projects/*` — Project and phase management
- `/admin-console/projects/status/` — Phase completion dashboard
- `/admin-console/projects/config/*` — Database-driven task configuration
- `/admin-console/test-plans/*` — Test cycle management with bulk item updates
- `/admin-console/announcements/*` — System announcement CRUD
- `/admin-console/dataload/*` — Data load status and reset
- `/admin-console/codebase-metrics/` — Codebase analysis
- `/admin-console/admin-guide/*` — Documentation browsing and editing
- `/admin-console/api/claude/ready-tasks/` — Claude Code: fetch ready tasks
- `/admin-console/api/claude/tasks/<id>/status/` — Claude Code: update task status
- `/admin-console/api/claude/process-emails/` — Claude Code: email intake

### Key Files
- `apps/admin_console/models.py` — All 14 models
- `apps/admin_console/views.py` — 60+ views (~4,750 lines)
- `apps/admin_console/services.py` — System state, phase management, metrics, issue detection, overrides (~1,450 lines)
- `apps/admin_console/email_intake.py` — IMAP email intake → task creation pipeline
- `apps/admin_console/metrics_service.py` — Codebase metrics collection
- `apps/admin_console/security_assessment.py` — Security posture analysis

### Tests
- 278 tests in `apps/admin_console/tests/`
- Covers: task CRUD, status transitions, phase auto-unlock, project management, inline editing, system hardening, preflight checks, test planning, announcements, data loading, Claude API, email intake

### Integration Points
- **Claude Code** — API endpoints for automated task execution via `/next` and `/run-task` slash commands
- **Core** — Uses `SiteConfiguration`, `Category`, `Theme`, `ChoiceCategory/Option` for site management
- **Email** — IMAP inbox scanning creates tasks from forwarded emails
- **Help** — Uses `HelpContextMixin` for admin help topics

---

## Help System

**App:** `apps/help/`
**Templates:** `templates/help/`, `templates/components/help_button.html`, `templates/components/help_modal.html`

### Overview
The help app provides a three-tier assistance system: context-aware "?" button help (per-page), a searchable help center with categorized articles, and a WLJ Assistant chatbot. It also includes a teaching tool that maps natural language navigation queries to app destinations.

### Features
- **Context-aware help** — Every page declares a `HELP_CONTEXT_ID`; clicking "?" shows the matching help topic with Markdown content
- **Help center** — Browsable categorized articles for self-service support
- **WLJ Assistant chatbot** — AI-powered chat with article search, personal data queries, and coaching-style adaptation
- **Teaching tool** — Natural language navigation ("Where do I log weight?") → direct link to destination
- **Admin help** — Separate staff-only help topics for admin console
- **Search** — Full-text search across titles, descriptions, and content
- **Related topics** — Cross-references between help topics
- **Fallback mechanism** — Missing specific context falls back to module home (e.g., `HEALTH_HEART_RATE` → `HEALTH_HOME`)

### Key Models
| Model | Purpose |
|-------|---------|
| `HelpTopic` | Per-page help content with `context_id` matching |
| `AdminHelpTopic` | Staff-only admin help content |
| `HelpCategory` | Organizes help articles (Getting Started, Features, etc.) |
| `HelpArticle` | Searchable documentation with module association and keywords |
| `HelpConversation` / `HelpMessage` | Chat sessions with message history |
| `TeachingDestination` | Maps navigation intents to app URLs with keywords |

### Key Views & Endpoints
- `/help/` — Help center home with category cards
- `/help/category/<slug>/` — Articles within a category
- `/help/article/<slug>/` — Individual article view
- `/help/api/topic/<context_id>/` — Context-aware help lookup (JSON with Markdown→HTML)
- `/help/api/admin/<context_id>/` — Staff-only admin help lookup
- `/help/api/search/?q=<query>` — Full-text search (top 10 results)
- `/help/api/chat/start/`, `message/`, `end/` — Chat conversation lifecycle
- `/help/api/chat/search/`, `suggestions/` — Article search and module suggestions
- `/help/api/teaching/search/?q=<query>` — Navigation intent matching
- `/help/api/teaching/suggestions/` — Popular navigation destinations

### HelpContextMixin Pattern
```python
class MyView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    help_context_id = "HEALTH_WORKOUT_CREATE"
```
- Injects `help_context_id` into template context
- Template uses `data-help-context="{{ help_context_id }}"` on help button
- JavaScript fetches help from `/help/api/topic/<context_id>/` on click
- Override `get_help_context_id()` for dynamic context per request
- Fallback: `apps/core/context_processors.py` auto-provides help_context_id by URL path matching

### Key Files
- `apps/help/models.py` — 6 models (HelpTopic, AdminHelpTopic, HelpCategory, HelpArticle, HelpConversation, HelpMessage, TeachingDestination)
- `apps/help/views.py` — 13 views (API + pages + chat + teaching)
- `apps/help/mixins.py` — HelpContextMixin and HelpTopicMixin
- `apps/help/fixtures/help_topics.json` — User-facing help content
- `apps/help/fixtures/admin_help_topics.json` — Admin help content
- `apps/help/fixtures/help_categories.json` — Help center categories
- `apps/help/fixtures/help_articles.json` — Searchable articles
- `apps/help/fixtures/teaching_destinations.json` — Navigation destinations
- `templates/components/help_button.html` — Reusable "?" button component
- `templates/components/help_modal.html` — Help content modal

### Tests
- 103 tests in `apps/help/tests/`
- Covers: help topic API, admin help, search, help center pages, chat lifecycle, teaching tool, HelpContextMixin, fixture loading, fallback mechanism

### Integration Points
- **Every app** — Views use `HelpContextMixin` for per-page help (journal, health, life, purpose, etc.)
- **Core context processor** — Auto-provides help_context_id for pages without the mixin
- **AI service** — Chat uses `AIService.process_assistant_message()` for personal data queries
- **Fixture loader** — `load_initial_data` command loads all 6 fixtures

---

## Mobile API & iOS Support

**App:** `apps/mobile/`

### Overview
The mobile app provides a REST API layer for the iOS (Swift/SwiftUI) wrapper application. It handles device registration, bearer token authentication, HealthKit data ingestion (37+ metric types including mobility, HR events, audio exposure, and dietary nutrients), push notification token management, and sync status tracking. All endpoints return JSON with no server-side templates.

### Features
- **Token exchange** — Web-to-native auth flow: WKWebView generates one-time code → iOS app exchanges for 90-day bearer token
- **Device management** — Register, list, and deactivate devices with metadata (model, OS, app version)
- **HealthKit ingestion** — Processes 37+ metric types (steps, weight, sleep, heart rate, blood glucose, blood oxygen, water, workouts with avg HR, blood pressure, body temperature, HRV, VO2 max, respiratory rate, body fat, walking asymmetry, walking steadiness, walking speed, step length, double support time, stair speed, 6-min walk, high/low HR events, AFib detection, headphone/environmental audio, and 13 dietary nutrients)
- **Deduplication** — Uses `sync_id` (HealthKit source IDs) to prevent duplicate entries; falls back to date/source matching
- **Ingestion audit** — `HealthIngestionRun` logs every submission with processing stats and error tracking
- **Push notifications** — APNs token registration/unregistration scaffold for intelligence delivery
- **Sync status** — Last sync time, per-metric counts, device info

### Key Models
| Model | Purpose |
|-------|---------|
| `MobileDevice` | Registered device with metadata, push token, active status |
| `MobileAPIToken` | Bearer tokens (SHA-256 hashed, 90-day expiry, revocable) |
| `MobileTokenExchangeCode` | One-time codes for web-to-native auth (5-minute expiry) |
| `HealthIngestionRun` | Audit log for each data submission with processing stats |

### Key Views & Endpoints
- `POST /api/mobile/generate-code/` — Generate one-time exchange code (requires session auth)
- `POST /api/mobile/token/exchange/` — Exchange code for bearer token
- `POST /api/mobile/token/revoke/` — Revoke current token
- `POST /api/mobile/token/revoke-all/` — Revoke all user tokens
- `GET /api/mobile/devices/` — List registered devices
- `POST /api/mobile/devices/<id>/deactivate/` — Deactivate device and revoke tokens
- `POST /api/mobile/health/ingest/` — HealthKit data ingestion (up to 5,000 metrics, 1MB limit)
- `GET /api/mobile/health/sync-status/` — Last sync status with per-metric counts
- `POST /api/mobile/push/register/` — Register APNs push token
- `POST /api/mobile/push/unregister/` — Clear push token

### Key Files
- `apps/mobile/models.py` — MobileDevice, MobileAPIToken, MobileTokenExchangeCode, HealthIngestionRun
- `apps/mobile/views.py` — 10 endpoint handlers + 37+ metric processor functions
- `apps/mobile/middleware.py` — Bearer token auth middleware, `@require_mobile_auth` decorator
- `apps/mobile/urls.py` — API routing
- `apps/mobile/admin.py` — Color-coded admin interfaces for all models

### Tests
- 51 tests in `apps/mobile/tests/`
- Covers: token exchange flow, device management, HealthKit ingestion (all metric types), deduplication, sync status, push registration

### Integration Points
- **Health models** — Ingests into `WeightEntry`, `StepsEntry`, `SleepEntry`, `GlucoseEntry`, `BloodOxygenEntry`, `WaterEntry`, `WorkoutSession` (with avg heart rate), `BloodPressureEntry`, `BodyTemperatureEntry`, `MobilityEntry`, `HeartRateEventEntry`, `AudioExposureEntry`, `DietaryNutrientEntry`
- **AI delivery engine** — Checks `MobileDevice` for push-enabled devices to route intelligence notifications
- **Users** — Token authentication resolves to `User` for all API calls

---

## Security Assessment

**App:** `apps/security/`
**Templates:** `apps/security/templates/security/`

### Overview
The security app provides an automated security assessment system that runs 40+ tests across 10 categories, generates CVSS v3.1 scores, tracks findings across runs (new/recurring/fixed/regressed), detects quick wins, and produces executive reports. All sensitive data is encrypted at rest with AES-256 Fernet.

### Features
- **Security scanner** — 40+ automated tests across 10 categories (secrets, auth, authorization, input validation, data protection, logging, web security, dependencies, deployment, abuse prevention)
- **CVSS scoring** — v3.1 base scores for each finding
- **Multi-score system** — SecurityScorecard grade (A–F), BitSight-style score (250–900), risk score (0–100), maturity level (0–3)
- **Finding tracking** — Stable `finding_key` hash for cross-run comparison; status: new, recurring, fixed, regressed
- **Quick win detection** — Auto-identifies low-effort remediation opportunities
- **Risk acceptance** — `AcknowledgedFinding` for tracking accepted risks with justification and expiration
- **Executive reports** — Summary, attack paths, failure modes, CISO sleep test, remediation prompts
- **Trend analysis** — Historical dashboards showing score progression and finding status trends
- **Audit logging** — `SecurityAuditLog` for all access (who, what, when, IP, user-agent)
- **Export** — CSV and PDF report generation

### Key Models
| Model | Purpose |
|-------|---------|
| `SecurityRun` | Master assessment record with summary counts and encrypted reports |
| `SecurityScore` | Append-only scoring ledger (CVSS stats, grades, risk, maturity) |
| `SecurityTest` | Individual test result (pass/fail/skipped) with encrypted evidence |
| `SecurityFinding` | Vulnerability with CVSS, severity, recommendations, status tracking |
| `AcknowledgedFinding` | Risk acceptance records with justification and expiration |
| `SecurityAuditLog` | Access audit trail for compliance |

### Key Views & Endpoints
- `/security/dashboard/` — Main dashboard with trends, scores, and run history
- `/security/run-assessment/` — Trigger new assessment (POST) or check status (GET)
- `/security/run/<uuid>/` — Detailed run view with tests and findings
- `/security/api/test/<uuid>/` — Test detail (AJAX)
- `/security/api/finding/<uuid>/` — Finding detail (AJAX)
- `/security/api/remediation/<uuid>/` — Remediation prompt text
- `/security/api/trends/` — 50-run historical trend data
- `/security/api/finding-trends/` — Finding status trends
- `/security/api/improvement/` — Improvement metrics over configurable period
- `/security/export/csv/<uuid>/`, `/security/export/pdf/<uuid>/` — Report exports

### Key Files
- `apps/security/models.py` — 6 models with `EncryptedTextField`/`EncryptedJSONField` custom fields
- `apps/security/views.py` — 13 views (dashboard, run detail, 6 APIs, export, delete, notes)
- `apps/security/scanner.py` — SecurityScanner with 40+ tests and CVSSCalculator
- `apps/security/scoring.py` — ScoringEngine (5 scoring methodologies)
- `apps/security/report_generator.py` — Executive summary, attack paths, CISO sleep test
- `apps/security/finding_tracker.py` — Cross-run finding comparison and trend analysis
- `apps/security/quick_win_detector.py` — Auto-detect low-effort remediation opportunities
- `apps/security/management/commands/run_security_assessment.py` — CLI assessment runner

### Tests
- 184 tests in `apps/security/tests/`
- Covers: scanner, scoring engine, finding tracker, quick win detection, report generation, views, export, audit logging, encryption

### Integration Points
- **Staff-only access** — All views enforce `is_staff` via `SecurityAccessMixin`
- **Core encryption** — Uses `SECURITY_DATA_ENCRYPTION_KEY` (falls back to `OAUTH_TOKEN_ENCRYPTION_KEY`) for AES-256 Fernet
- **Admin console** — `security_assessment.py` provides security posture data

---

## Ops Command Center (Intelligence Monitoring)

**URL:** `/admin-console/ops/`
**Templates:** `templates/admin_console/operations_wall.html`

### Overview
The Ops Command Center (formerly Operations Wall) is a live Bloomberg/NASA-style monitoring dashboard for the 9-engine intelligence pipeline. It provides real-time engine health, anomaly detection, manual execution controls, and system integrity scoring — giving operators full visibility and control over the AI subsystem.

### Features
- **System Integrity Index** — 0–100 composite score (engine health 40pts, anomaly severity 50pts, error spikes 10pts, suppression 5pts, volatility 5pts) with OPTIMAL/NOMINAL/DEGRADED/CRITICAL posture
- **Engine cards** — Per-engine tiles showing status (OK/MISSED/STALE), last-run time, cadence timeline strip (30-min rolling window), and miss count
- **Manual execution controls** — Execute buttons on all 9 engines. Batch-native engines (DBE, WIRE, DNE, PGE) run directly; context-dependent engines (UAL, SAE, PIE, PRIE, ICQG) run in Synthetic Batch Evaluation Mode with purple "Synthetic" badge
- **Synthetic Batch Evaluation** — Iterates all active AI users, calls each engine's existing logic with current stored data. No fake events, no data alteration. Uses `trace_context(source="manual_synthetic")`
- **Scheduler Heartbeat tile** — Live status of ISE scheduler (Railway cron, 5-min) and SAME monitor (Celery Beat, 60s). Shows ALIVE/DELAYED/OFFLINE with pulse indicators, last tick, expected interval, and drift delta. Configurable thresholds (1.5x→DELAYED, 3x→OFFLINE). Auto-refreshes with 2s polling
- **SAME engine** — System Autonomous Monitoring Engine runs every 60s via Celery Beat. Computes heartbeats, detects anomalies, escalates severity (P3→P2→P1), auto-remediates low-severity issues
- **Anomaly detection** — 7 detectors: missed runs, error bursts, suppression spikes, delivery storms, latency degradation, stale state, guidance drought
- **Hybrid Recovery Model** — Manual execution immediately recomputes heartbeats, resolves MISSED_RUN anomalies, and creates fresh integrity snapshots. Historical misses age out naturally over 30 minutes
- **SAME manual trigger** — "Execute Now" button with real-time status feedback, idempotency guard, execution duration tracking
- **Narrative bar** — AI-generated plain-English summary of system state
- **Anomaly watchlist** — Active anomalies with severity, age, and resolution status
- **Live feed** — Real-time engine activity stream via SSE

### Key Models
| Model | Purpose |
|-------|---------|
| `EngineExpectedCadence` | Expected run frequency per engine |
| `EngineHeartbeat` | Per-engine health observations (OK/MISSED/STALE) |
| `EngineRun` | Instrumented engine execution records |
| `EngineExecutionLog` | Manual/automated execution audit trail |
| `OpsAnomaly` | Detected anomalies with severity escalation |
| `OpsNarrativeSnapshot` | AI-generated system summaries |
| `SystemIntegritySnapshot` | Point-in-time integrity scores |
| `AdminIntervention` | Manual action audit records |
| `SchedulerHeartbeat` | ISE/SAME scheduler liveness tracking (single-row per scheduler) |

### Key Files
- `apps/core/ai_observability/same_engine.py` — SAME cycle, heartbeats, integrity scoring, recovery
- `apps/core/ai_observability/engine_registry.py` — ENGINE_REGISTRY: centralized engine metadata, batch runners, execution modes
- `apps/core/ai_observability/ops_views.py` — Dashboard views, engine cards, manual execution API
- `apps/core/ai_observability/heartbeat.py` — Heartbeat computation
- `apps/core/ai_observability/instrumentation.py` — `@_instrument_engine_run` decorator
- `apps/core/ai_scheduler/scheduler_runner.py` — Batch runners (native + 5 synthetic)
- `apps/core/tasks.py` — Celery tasks for engine execution with recovery hooks
- `templates/admin_console/operations_wall.html` — Full dashboard UI

### Tests
- 160 tests in `apps/core/tests/test_ai_observability/`
- Covers: SAME cycle, heartbeats, anomaly detection, escalation, auto-remediation, integrity scoring, manual execution, synthetic runners, engine registry, recovery model

### Integration Points
- **Celery + Redis** — SAME runs as periodic Celery Beat task; manual executions queued as Celery tasks
- **ENGINE_REGISTRY** — All 9 engines registered with metadata, batch runners, and execution modes
- **Intelligence Pipeline** — Monitors all 14 engines across Interpretation → Execution → Post-Execution phases
- **Admin Console** — Accessible from admin navigation at `/admin-console/ops/`

---

## Calendar Engine (Technical Reference)

**App:** `apps/calendar_engine/`
**Templates:** `templates/calendar_engine/`

### Overview
This section provides the full technical reference for the Time Command Center (see [section 40](#time-command-center-calendar-engine) for the feature overview). The calendar engine manages events, projections from tasks/goals/habits, recurrence, conflict detection, NLP quick add, smart gap suggestions, domain balance metrics, and CoS schedule awareness.

### Key Models
| Model | Purpose |
|-------|---------|
| `CalendarEvent` | Main event with title, start/end, domain, event_kind (manual/deadline/execution/external), source_type, status, is_protected |
| `RecurrenceRule` | Frequency (daily/weekly/monthly), byweekday, interval, until/count limits |
| `RecurrenceException` | Single-occurrence overrides (reschedule or cancel) |
| `CalendarOverrideLog` | Audit trail for conflict override moves |

### Key Views & Endpoints
- `/calendar/` — Dashboard with balance metrics and suggestions
- `/calendar/manage/` — Full CRUD event management page
- `/calendar/month/` — Full month calendar grid
- `/calendar/api/today/` — Today's timeline (6am–10pm window)
- `/calendar/api/range/?start=&end=` — Events in date range
- `/calendar/api/month/?year=&month=` — Month grid data with edge padding
- `/calendar/api/events/` — Create event (POST)
- `/calendar/api/events/all/?status=&kind=&source=&q=` — Filtered event list (paginated 200)
- `/calendar/api/events/<id>/` — Event detail, update, delete (GET/PATCH/DELETE)
- `/calendar/api/events/<id>/move/` — Drag-drop move with conflict check (409 if protected overlap), writeback to source
- `/calendar/api/suggestions/gaps/?date=` — Smart gap detection (≥90 min gaps)
- `/calendar/api/suggestions/accept/` — One-click execution block creation from suggestion
- `/calendar/api/metrics/balance/?period=today|week` — Domain time allocation percentages
- `/calendar/api/nlp_create/` — NLP free-text event creation

### Services
| Service | Purpose |
|---------|---------|
| `services/calendar_mutation_service.py` | **Single mutation path** for all CalendarEvent create/update/delete — used by both AI handlers and view layer. Uses `select_for_update()` row locking, idempotency with nested savepoints, ExecutionLog writes, and post-commit hooks (conflict detection, drift, instability, Google Calendar sync) |
| `services/projection.py` | Syncs Tasks→deadline markers, Goals→milestone markers, Habits→recurring protected events |
| `services/conflicts.py` | Protected event overlap detection, override logging (Habit Protection Layer) |
| `services/metrics.py` | Domain balance computation (minutes and percentages per period) |
| `services/suggestions.py` | Gap detection in 6am–10pm window, matches gaps to due-soon items |
| `services/nlp_parse.py` | Free-text parsing with day names, time ranges, temporal tokens, domain hints |

### Key Files
- `apps/calendar_engine/models.py` — CalendarEvent (with `deleted_at` soft-delete field), RecurrenceRule, RecurrenceException, CalendarOverrideLog
- `apps/calendar_engine/views.py` — 15 views (3 template + 12 API), `EventDetailView.patch/delete` delegates to CalendarMutationService
- `apps/calendar_engine/services/` — 6 service modules (including CalendarMutationService)
- `templates/calendar_engine/dashboard.html` — TCC dashboard with view toggles
- `templates/calendar_engine/month.html` — Full month grid view
- `templates/calendar_engine/manage.html` — Event management page

### Tests
- 31 tests in `apps/calendar_engine/tests.py`
- 22 tests in `apps/ai/tests/test_calendar_crud.py` (Calendar CRUD via CoS)
- Covers: task/goal/habit projections, conflict detection, gap suggestions, domain balance, NLP parsing, API CRUD, recurrence, event moves with writeback, AI read/update/delete, idempotency, execution logging, learning mode gate, view layer integration, drift hooks

### Integration Points
- **CoS schedule awareness** — `apps/core/ai_orchestrator/cos_context.py` injects today's events into every CoS LLM prompt with time-relative tags ([past], [in_progress], [upcoming_soon], [upcoming])
- **Morning greeting** — `apps/ai/personal_assistant.py` references schedule proactively
- **Life app** — Tasks and LifeEvents sync to calendar via projection service
- **Purpose app** — Goals and habits sync to calendar; habits get `is_protected=True` flag
- **CoS action handlers** — `apps/ai/action_handlers.py` creates, reads, updates, and deletes events via CalendarMutationService. Full CRUD via two LLM tools: `read_calendar_events` (query) and `mutate_calendar_event` (create/update/delete with idempotency). Post-scheduling chain: conflict detection → drift recomputation → schedule instability → Google Calendar sync.
- **Google Calendar** — Life app's `GoogleCalendarService` pushes events to external calendar

---

## Owner Financial Command Center

**App:** `apps/owner_finance/`
**URL:** `/owner/finance/`
**Access:** Superuser only (OwnerOnlyMixin)

### Overview
Internal owner dashboard for tracking LLM costs, per-user economics, gross margin, and vendor billing. Answers: "What does it cost to run WLJ, and is each user profitable?"

### Key Models
| Model | Purpose |
|-------|---------|
| `ThirdPartyVendor` | External service vendors (OpenAI, Twilio, Railway, etc.) |
| `VendorBillingRecord` | Monthly/periodic billing from vendors |
| `LLMPriceBook` | Per-model pricing by effective date (never hardcoded) |
| `LLMUsageEvent` | Ledger row per LLM call with auto-computed cost |
| `UserSubscriptionSnapshot` | User tier snapshots for margin calculations |
| `DailyCostRollup` | Pre-aggregated daily costs for fast chart queries |
| `BudgetGuardrail` | Budget thresholds with alert triggers |

### Pages
- **Overview** (`/owner/finance/`) — KPI cards, daily cost chart (Chart.js), budget alert tiles, top 10 users (with drill-down links), top features, escalation economics, CSV export button
- **Per-User** (`/owner/finance/users/`) — Per-user cost, revenue, margin, and tier breakdown
- **Features** (`/owner/finance/features/`) — Cost by feature, model, and engine
- **Vendors** (`/owner/finance/vendors/`) — Vendor billing ledger and summary
- **Audit Ledger** (`/owner/finance/audit/`) — Per-call event log with filtering by feature, model, user, escalated status
- **Power User** (`/owner/finance/users/<id>/`) — Deep-dive diagnostics for a single user: cost/call/token breakdown by feature and model, recent calls
- **Simulator** (`/owner/finance/simulator/`) — What-if scenario modeling: adjust users, interactions, model mix, tier mix, pricing to project monthly costs, revenue, and margin
- **Budgets** (`/owner/finance/budgets/`) — Visual budget guardrail cards showing current spend vs. budget with progress bars

### Telemetry Integration
- `log_llm_usage()` in `services/telemetry.py` — called from 9 integration points across the codebase
- Auto-computes cost from `LLMPriceBook` effective date range
- **Call sites:** `apps/ai/services.py`, `apps/ai/intent_service.py`, `apps/capture/services/summarization.py`, `apps/health/services/ai_nutrition.py`, `apps/health/views.py` (ProviderAILookupView), `apps/scan/services/vision.py`, `apps/scan/services/barcode.py`, `apps/scan/services/medicine_lookup.py`, `apps/scan/services/product_lookup.py`

### Management Commands
- `seed_pricebook` — Seeds OpenAI pricing for gpt-4o, gpt-4o-mini, whisper-1
- `rollup_daily_costs` — Aggregates LLMUsageEvent into DailyCostRollup (schedulable)
- `check_budget_guardrails` — Checks active guardrails, logs warnings, creates notifications

### Full Spec
`docs/owner/ultimate_financial_command_center.md`

---

*Last updated: 2026-02-21*
