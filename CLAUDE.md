# Master Prompt for Whole Life Journey Project

**Project:** Whole Life Journey - Django 5.x personal wellness/journaling app
**Repo:** C:\dbawholelifejourney (GitHub: djenkins452/dbawholelifejourney)
**Deployment:** Railway with PostgreSQL (via DATABASE_URL env var)

## Tech Stack
- Django 5.x with django-allauth for authentication
- PostgreSQL (production) / SQLite (development)
- Railway deployment with Nixpacks builder
- Gunicorn for WSGI
- OpenAI API for AI coaching features

## Key Architecture
- **Apps:** users, core, dashboard, journal, faith, health, purpose, ai, life, admin_console
- **User model:** Custom User in apps/users/models.py (email-based auth)
- **Preferences:** UserPreferences model stores timezone, module toggles, AI settings (coaching_style)
- **Soft deletes:** Models use soft_delete() method, not hard deletes
- **AI Service:** Database-driven prompts and coaching styles via AIPromptConfig and CoachingStyle models

## Deployment Notes
- Always push from the main repository, not from working branches (worktrees)
- Use meaningful merge commit messages with `-m` flag when merging to main
- Procfile runs: migrate → load_initial_data → collectstatic → gunicorn
- postgres.railway.internal hostname only available at runtime, NOT build time
- All DB operations must be in startCommand, not build/release phase
- System data loaded via `python manage.py load_initial_data` (fixtures + populate commands)

## Recent Fixes Applied
<!-- RECENT_FIXES_START -->
- **Step-by-step onboarding wizard:** New 6-step wizard for new users (Welcome, Theme, Modules, AI Coaching, Location, Complete)
- **Onboarding enforcement:** Middleware enforces onboarding completion - users redirected to wizard until complete
- **Intro transcript:** Created `docs/intro_transcript.md` - narration script for voiceover/video explaining the app
- **Database-driven AI prompts:** AIPromptConfig model allows admin control of all AI prompt types (10 types) via Django admin at /admin/ai/aipromptconfig/
- **Database-driven coaching styles:** CoachingStyle model with 7 styles, editable via Django admin, with icon field for UI
- **Django admin improvements:** Added "Back to Admin Console" link in header, fixed capitalization (AI Insights, AI Usage Logs)
- **Life dashboard:** Quick Access tiles now show counts for each section
- **Test history:** Added dev-only "Run Tests" button, sync_test_results command for pushing local test data to production
- **Fitness tracking:** Added comprehensive fitness tracking feature
- **Google Calendar:** Added API dependencies to requirements.txt
- **Preferences page:** Dynamic coaching style rendering from database with responsive grid layout
- **Fixture loading:** Fixed to use fixture names without app prefix
- **Login page CSS:** Fixed auth_content block in templates/account/base.html
- **Timezone display:** Fasting list uses {% timezone user_timezone %} tag
- **Faith module default:** Changed to default=True in UserPreferences
- **Speech-to-text:** Set continuous: false to prevent duplication
- **Superuser creation:** create_superuser_from_env only creates if user doesn't exist
- **Footer logo:** Increased size to 200px
- **Custom domain:** Added support for wholelifejourney.com
- **Media files:** Fixed serving in production
<!-- RECENT_FIXES_END -->

## Important Files
- `Procfile` - Railway deployment startup command
- `apps/core/management/commands/load_initial_data.py` - System data loading (fixtures + populate commands)
- `apps/users/management/commands/create_superuser_from_env.py` - Superuser creation
- `apps/ai/models.py` - AIPromptConfig, CoachingStyle, AIInsight, AIUsageLog models
- `apps/ai/services.py` - AIService with database-driven prompts
- `apps/ai/fixtures/ai_prompt_configs.json` - Default AI prompt configurations (10 types)
- `apps/ai/fixtures/coaching_styles.json` - Default coaching styles (7 styles)
- `apps/<app>/fixtures/<name>.json` - Reference data fixtures
- `templates/admin/base_site.html` - Custom Django admin branding with Admin Console link

## AI Configuration (via Django Admin)
- **AI Prompt Configurations** (/admin/ai/aipromptconfig/): 10 prompt types controlling system instructions, sentence counts, max tokens, tone guidance, and things to avoid
- **Coaching Styles** (/admin/ai/coachingstyle/): 7 personality styles (Supportive Partner, Direct Coach, Gentle Guide, etc.) with prompt instructions and icons
- **AI Insights** (/admin/ai/aiinsight/): Cached AI-generated insights
- **AI Usage Logs** (/admin/ai/aiusagelog/): API usage tracking

## User Preferences
- Do NOT make pushes that could wipe database data
- User is deploying to Railway with PostgreSQL
- User's timezone: America/New_York (EST)
- Prefers descriptive merge commit messages, not auto-generated ones

## Session Instructions

### Starting a New Session
Just say: **"Read CLAUDE.md and continue"** - this gives full project context.

### End of Session Tasks (Do Automatically)
1. Run `git log --oneline -20` to see recent commits
2. Update the "Recent Fixes Applied" section between the HTML comments
3. Commit and push CLAUDE.md changes with descriptive merge message

### After Making Code Changes
1. Run tests: `python manage.py test` or `python run_tests.py`
2. If new features were added, check if tests exist in `apps/<app>/tests/`
3. If tests are missing, create them following existing test patterns
4. Update CLAUDE.md if significant new functionality was added

## Testing
- **Run all tests:** `python manage.py test` or `python run_tests.py`
- **Run specific app tests:** `python manage.py test apps.<app_name>`
- **Test files location:** `apps/<app>/tests/` (directory) or `apps/<app>/tests.py` (file)
- **Test runner:** `run_tests.py` provides enhanced output with summaries
- **Current test count:** ~700+ tests across all apps

### Test Patterns Used
- `TestCase` for database tests
- `SimpleTestCase` for non-DB tests
- Factory pattern for creating test objects
- `setUp()` for common test fixtures
- `@patch` for mocking external services (AI, APIs)

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
- `docs/intro_transcript.md` - Narration transcript for voiceover/video

### Testing the Wizard
- **New user**: Sign up → Accept terms → Wizard starts
- **Reset existing user**: Set `has_completed_onboarding = False` in Django Admin (`/admin/users/userpreferences/`)
- **Direct access**: Visit `/user/onboarding/start/` while logged in

### URL Note
The users app is mounted at `/user/` (singular), not `/users/`. Middleware paths must match:
- `/user/onboarding/` - Onboarding paths
- `/user/accept-terms/` - Terms acceptance

---

## Context-Aware Help System

### Role When Working on Help Features
When working on help system tasks, act as a **Senior Technical Documentation Architect & Context-Aware UX Help Systems Designer**. This means:
- Write precise, click-by-click user guides
- Design context-aware help that maps directly to screens
- Structure documentation for both humans AND AI chatbots
- Think in systems, not pages—documentation is part of the product
- Create documentation that stays accurate as software evolves

### Overview
The application has a "?" help icon in the upper-right corner that provides context-aware help. This is NOT marketing content—it is authoritative user guidance with exact, step-by-step instructions.

### Core Principle: HELP_CONTEXT_ID
Every page declares a stable identifier called `HELP_CONTEXT_ID`. The help system uses this to show the exact relevant documentation—no searching, no guessing.

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
- `HEALTH_WORKOUT_LIST`
- `HEALTH_WORKOUT_CREATE`
- `HEALTH_WORKOUT_EDIT`
- `JOURNAL_ENTRY_LIST`
- `JOURNAL_ENTRY_EDIT`
- `FAITH_ROOT`
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
│   ├── journal.md          # Journal app help content
│   ├── faith.md            # Faith app help content
│   └── ...
└── system/                 # Technical/system documentation
```

### Help Index Format (index.json)
```json
{
  "DASHBOARD_HOME": { "file": "dashboard.md", "help_id": "dashboard-overview" },
  "HEALTH_ROOT": { "file": "health.md", "help_id": "health-overview" },
  "HEALTH_WORKOUT_CREATE": { "file": "health.md", "help_id": "health-log-workout" }
}
```

### Help Entry Format (STRICT)
Each help entry in documentation files MUST include:

```markdown
## [HELP_ID: health-log-workout]
**Title:** How to Log a Workout
**Context:** HEALTH_WORKOUT_CREATE screen
**Description:** Record your exercise activities with duration, type, and notes.

### Steps
1. Click "Health" in the left navigation menu.
2. Click the "Log Workout" button in the top-right corner.
3. Select a workout type from the dropdown (e.g., "Running", "Weight Training").
4. Enter the duration in minutes.
5. (Optional) Add notes about your workout.
6. Click "Save" to record your workout.

### Notes
- Workouts are displayed in reverse chronological order.
- You can edit a workout by clicking on it in the list.
```

### Writing Rules for Help Content
1. **Start each step with an action verb** (Click, Enter, Select, Navigate)
2. **Reference exact UI labels** in quotes (e.g., Click "Save")
3. **Be exact**—a chatbot will read these verbatim
4. **No vague or interpretive text**
5. **No summaries**—full step-by-step instructions
6. **Do NOT invent UI elements**—if unsure, ASK

### Chatbot Compatibility
These docs are designed to be read by a future chatbot that will:
- Search by HELP_CONTEXT_ID, HELP_ID, and titles
- Return step-by-step instructions verbatim
- Provide exact answers, not summaries

### Change Management Rule (MANDATORY)
When ANY feature is added, changed, or removed:
1. Update the relevant help documentation immediately
2. Add or update HELP_CONTEXT_ID mappings in index.json
3. Never leave outdated steps in documentation
4. **Documentation changes are part of the feature, not a follow-up task**

### Help System Files (when implemented)
- `docs/help/index.json` - Central mapping of HELP_CONTEXT_ID → documentation
- `docs/help/*.md` - Help content files organized by app/feature
- `templates/components/help_button.html` - The "?" icon component
- `static/js/help.js` - JavaScript for reading context and displaying help

---
*Last updated: 2025-12-27*
