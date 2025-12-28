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
- **Apps:** users, core, dashboard, journal, faith, health, purpose, ai, life, admin_console, help, scan
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
- **Railway has no shell access** - user cannot run commands manually. All fixes must be done via code changes and redeployment. Use data migrations or modify startup commands in Procfile to fix production data issues.

## Recent Fixes Applied
<!-- RECENT_FIXES_START -->
- **Dashboard and AI Integration for Medicine, Workout, Scan (2025-12-28):** Comprehensive dashboard enhancements integrating all new modules. Dashboard now shows: Today's Medicine Schedule with status badges (taken/missed/skipped/pending), Recent Workouts with PR highlights, Quick Stats header with medicine doses and workout counts. AI integration updated to gather: medicine adherence rate, active medicines, refill alerts, workout frequency, recent PRs, scan activity. Added celebrations for: perfect medicine adherence (95%+), all doses taken today, workout streaks, new PRs, AI Camera usage. Added nudges for: pending medicine doses, low adherence, refill needs, workout gaps. New CSS for medicine-schedule-section and recent-workouts-section with responsive design. 965 tests passing.
- **Food/Nutrition Tracking (2025-12-28):** Added comprehensive Nutrition section to Health module with food logging, macro tracking, daily summaries, and nutrition goals. Features: FoodItem global library (USDA support, barcode scanning, AI recognition ready), CustomFood for user recipes, FoodEntry logging with meal type, location, eating pace, hunger/fullness tracking, DailyNutritionSummary with automatic recalculation and macro percentages, NutritionGoals with calorie/macro targets and dietary preferences. Views: NutritionHomeView (daily dashboard), FoodEntryCreateView/UpdateView, QuickAddFoodView, FoodHistoryView, NutritionStatsView, NutritionGoalsView, CustomFoodListView/CreateView/UpdateView. CameraScan model in apps/core for future AI-powered food recognition. 80 new tests (1045 total).
- **Medicine Tracking Section (2025-12-28):** Added comprehensive Medicine section to Health module with daily tracker, adherence stats, PRN support, refill tracking, and dashboard integration. Features: Medicine Master List (name, dose, frequency, schedules, prescribing doctor, pharmacy), Daily Tracker with one-tap check-off, Missed/Overdue detection with configurable grace period, History & Adherence views, Quick Look for screenshots, refill alerts, pause/resume without losing history. 77 new tests (965 total).
- **CSO Security Review & Fixes (2025-12-28):** Comprehensive security review conducted with 21 findings. Critical fixes implemented:
  - C-2: Bible API key removed from frontend, replaced with server-side proxy at `/faith/api/bible/*`
  - C-3: AI data consent field added to UserPreferences (ai_data_consent, ai_data_consent_date)
  - H-3: Rate limiting via django-axes (5 attempts, 1 hour lockout)
  - H-4: Django admin moved to configurable path (default: /wlj-admin/, set via ADMIN_URL_PATH env var)
  - M-1: SameSite cookie attribute configured (Lax) for CSRF protection
  - See `SECURITY_REVIEW_REPORT.md` for full report with all 21 findings and remediation roadmap
- **Django-allauth deprecation warnings fix:** Updated settings.py to use new django-allauth settings format. Replaced deprecated `ACCOUNT_AUTHENTICATION_METHOD`, `ACCOUNT_EMAIL_REQUIRED`, `ACCOUNT_USERNAME_REQUIRED`, and `ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE` with `ACCOUNT_LOGIN_METHODS` and `ACCOUNT_SIGNUP_FIELDS`. Added `apps/__init__.py` for Python 3.14 module discovery compatibility. All 877 tests pass with zero warnings.
- **Backup and Disaster Recovery Playbook:** Added comprehensive BACKUP.md document for backup, restore, and disaster recovery operations. Includes complete inventory of all models and data types, GitHub-based backup strategy, database restore procedures, environment reconstruction steps, and security guidelines. Designed to be executable by Claude instances without human intervention.
- **Edit/Delete saved Scripture verses:** Added ability to edit and delete saved Scripture verses from the Scripture Library. Each verse card now has Edit and Delete buttons. Edit page allows modifying reference, text, translation, themes, and personal notes. Delete uses soft-delete. All actions are user-scoped for security.
- **Test suite onboarding fixes:** Fixed 185+ test failures caused by onboarding middleware. All test setups now call `_complete_onboarding()` to set `has_completed_onboarding = True`. Additional fixes: journal prompt filter test accounts for migration-loaded prompts, event is_today test uses timezone-aware dates, dashboard streak test uses `get_user_today()`, cache test uses LocMemCache. All 857 tests now pass.
- **User-specific saved verses:** Fixed bug where saved Scripture verses were shared across all users. Created new `SavedVerse` model with user ownership. Data migration assigns existing verses to Danny's account. Each user now has their own private Scripture library.
- **Project Add Task default:** When adding a task from within a project, the project dropdown now auto-selects that project. After creating, redirects back to the project detail page.
- **Dev environment dependency check:** Added `check_dependencies.py` script to verify all required packages are installed in venv. Run `python check_dependencies.py` to check, or `python check_dependencies.py --install` to auto-install missing packages.
- **Missing packages fix:** Installed `cloudinary`, `django-cloudinary-storage`, and `markdown` packages that were in requirements.txt but missing from venv.
- **Task undo link:** Added "Undo" link next to completed tasks so users can easily revert accidental completions without navigating to Completed filter
- **Journal prompts migration:** Data migration (`0003_load_journal_prompts.py`) to load 20 journal prompts into production database. Fixes "no prompts available" issue.
- **ChatGPT journal import:** Management command (`import_chatgpt_journal`) and data migration to import journal entries from ChatGPT JSON exports
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
- `SECURITY_REVIEW_REPORT.md` - CSO-level security review with 21 findings and remediation roadmap
- `BACKUP.md` - Comprehensive backup and disaster recovery playbook
- `Procfile` - Railway deployment startup command
- `check_dependencies.py` - Verifies all required packages are installed in venv
- `run_tests.py` - Enhanced test runner with database history and output files
- `apps/core/management/commands/load_initial_data.py` - System data loading (fixtures + populate commands)
- `apps/users/management/commands/create_superuser_from_env.py` - Superuser creation
- `apps/journal/management/commands/import_chatgpt_journal.py` - One-time ChatGPT journal import
- `apps/journal/migrations/0003_load_journal_prompts.py` - Data migration for 20 journal prompts
- `apps/ai/models.py` - AIPromptConfig, CoachingStyle, AIInsight, AIUsageLog models
- `apps/ai/services.py` - AIService with database-driven prompts
- `apps/ai/fixtures/ai_prompt_configs.json` - Default AI prompt configurations (10 types)
- `apps/ai/fixtures/coaching_styles.json` - Default coaching styles (7 styles)
- `apps/journal/fixtures/prompts.json` - Journal prompts fixture (20 prompts)
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

## Development Setup

### First-Time Setup
```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Verify all dependencies are installed
python check_dependencies.py
```

### Quick Dependency Check
If the dev server fails to start with `ModuleNotFoundError`, run:
```bash
python check_dependencies.py --install
```

### Common Missing Packages
These packages are sometimes missing from the venv:
- `cloudinary` and `django-cloudinary-storage` - Media file storage
- `markdown` - Help system rendering

## Testing
- **Run all tests:** `python manage.py test` or `python run_tests.py`
- **Run specific app tests:** `python manage.py test apps.<app_name>`
- **Test files location:** `apps/<app>/tests/` (directory) or `apps/<app>/tests.py` (file)
- **Test runner:** `run_tests.py` provides enhanced output with summaries
- **Current test count:** 1045 tests across all apps (as of 2025-12-28)

### Test Patterns Used
- `TestCase` for database tests
- `SimpleTestCase` for non-DB tests
- Factory pattern for creating test objects
- `setUp()` for common test fixtures
- `@patch` for mocking external services (AI, APIs)

### CRITICAL: Test User Setup Pattern
**All test users MUST have onboarding completed** or tests will fail with 302 redirects. The onboarding middleware enforces `has_completed_onboarding = True` before users can access protected pages.

Every test mixin or setUp that creates users should include:

```python
def create_user(self, email='test@example.com', password='testpass123'):
    """Create a test user with terms accepted and onboarding completed."""
    user = User.objects.create_user(email=email, password=password)
    self._accept_terms(user)
    self._complete_onboarding(user)
    return user

def _accept_terms(self, user):
    from apps.users.models import TermsAcceptance
    TermsAcceptance.objects.create(user=user, terms_version='1.0')

def _complete_onboarding(self, user):
    """Mark user onboarding as complete."""
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
```

### Test Files with User Mixins
These files contain test mixins that create users. If adding new tests, use these patterns:
- `apps/users/tests/test_users_comprehensive.py` - `UserTestMixin`
- `apps/dashboard/tests/test_dashboard_comprehensive.py` - `DashboardTestMixin`
- `apps/journal/tests/test_journal_comprehensive.py` - `JournalTestMixin`
- `apps/faith/tests/test_faith_comprehensive.py` - `FaithTestMixin`
- `apps/health/tests/test_health_comprehensive.py` - `HealthTestMixin`
- `apps/health/tests/test_nutrition.py` - `NutritionTestMixin`
- `apps/health/tests/test_medicine.py` - `MedicineTestMixin`
- `apps/life/tests/test_life_comprehensive.py` - `LifeTestMixin`
- `apps/purpose/tests/test_purpose_comprehensive.py` - `PurposeTestMixin`
- `apps/admin_console/tests/test_admin_console.py` - `AdminTestMixin`
- `apps/ai/tests/test_ai_comprehensive.py` - `AITestMixin`
- `apps/core/tests/test_core_comprehensive.py` - `CoreTestMixin`

### Common Test Gotchas
1. **302 redirects instead of 200:** User not marked as onboarding complete
2. **Count assertions failing:** Data migrations may pre-load records (e.g., 20 journal prompts)
3. **Date comparisons failing:** Use `timezone.now().date()` or `get_user_today(user)` instead of `date.today()`
4. **Cache tests failing:** Test settings use DummyCache; use `@override_settings` with LocMemCache

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

## ChatGPT Journal Import

### Overview
Management command to import journal entries from ChatGPT JSON exports. Used for one-time data migration from ChatGPT conversations.

### Usage
```bash
# Dry run (preview what will be imported)
python manage.py import_chatgpt_journal export.json --dry-run

# Import for a specific user
python manage.py import_chatgpt_journal export.json --user=email@example.com

# Import using user ID
python manage.py import_chatgpt_journal export.json --user-id=1
```

### Expected JSON Format
```json
[
  {
    "date": "2025-12-03",
    "faith": "Faith content or null",
    "health": "Health content or null",
    "family": "Family content or null",
    "work": "Work content or null",
    "reflection_summary": "Summary text"
  }
]
```

### Key Files
- `apps/journal/management/commands/import_chatgpt_journal.py` - Management command
- `apps/journal/migrations/0002_import_chatgpt_journal.py` - One-time data migration (runs on deploy)
- `apps/journal/tests/test_import_chatgpt_journal.py` - Command tests (15+ tests)

### Features
- Maps JSON fields to journal categories (Faith, Health, Family, Work)
- Auto-generates entry titles from dates (e.g., "Wednesday, December 03, 2025")
- Skips duplicate entries by date
- Dry-run mode for previewing imports
- Builds markdown body with section headers

---

## Journal Prompts

### Overview
Journal prompts are curated writing prompts to inspire journal entries. They can be general or category-specific, and faith-specific prompts may include Scripture references.

### Data Source
Prompts are loaded via data migration `0003_load_journal_prompts.py` which runs automatically on deploy. This ensures prompts exist in production regardless of fixture loading success.

### Prompt Categories
| Category PK | Name | Example Prompts |
|-------------|------|-----------------|
| 1 | Faith | "How have you seen God at work in your life recently?" |
| 2 | Family | "How can you show love to your family this week?" |
| 3 | Work | "What's one thing you're learning at work right now?" |
| 4 | Health | "What does rest look like for you right now?" |
| 5 | Gratitude | "What are three things you're grateful for today?" |
| 6 | Growth | "What challenged you today, and how did you respond?" |
| 7 | Relationships | "Write about someone who made a positive impact on your day." |
| 8 | Dreams | "What's one step you can take toward a goal this week?" |
| null | General | "What's weighing on your heart today?" |

### Key Files
- `apps/journal/models.py` - `JournalPrompt` model
- `apps/journal/fixtures/prompts.json` - Fixture file (20 prompts)
- `apps/journal/migrations/0003_load_journal_prompts.py` - Data migration
- `apps/journal/tests/test_journal_prompts_migration.py` - Migration tests (15+ tests)

### Testing
```bash
# Run prompt migration tests
python manage.py test apps.journal.tests.test_journal_prompts_migration

# Run all journal tests
python manage.py test apps.journal
```

---

## Project Add Task Default

### Overview
When adding a task from within a project detail page, the project dropdown automatically defaults to that project, saving users from manually selecting it each time.

### How It Works
1. User navigates to a project detail page
2. User clicks "Add Task" button
3. Task creation form opens with the project pre-selected
4. After creating the task, user is redirected back to the project detail page

### Implementation
- **View:** `apps/life/views.py` - `TaskCreateView` with `get_initial()` and updated `get_success_url()`
- **Template:** `templates/life/task_form.html` - Project dropdown checks `form.initial.project.pk`
- **URL Pattern:** `?project=ID` query parameter passed from project detail page

### Key Code Changes
```python
# TaskCreateView.get_initial() - Pre-selects project from query param
def get_initial(self):
    initial = super().get_initial()
    project_id = self.request.GET.get('project')
    if project_id:
        project = Project.objects.get(pk=project_id, user=self.request.user)
        initial['project'] = project
    return initial

# TaskCreateView.get_success_url() - Returns to project after creation
def get_success_url(self):
    project_id = self.request.GET.get('project')
    if project_id:
        return reverse('life:project_detail', kwargs={'pk': project_id})
    return reverse_lazy('life:task_list')
```

### Tests
Located in `apps/life/tests/test_views.py` (TaskViewTest class):
- `test_task_create_preselects_project_from_query_param` - Verify project is pre-selected
- `test_task_create_with_project_redirects_to_project_detail` - Verify redirect after creation
- `test_task_create_with_invalid_project_id_ignores_param` - Verify invalid IDs are ignored
- `test_task_create_with_other_users_project_ignores_param` - Verify security (can't use other user's project)

### Running Tests
```bash
# Run project add task tests
python run_tests.py apps.life.tests.test_views.TaskViewTest

# Run all life app view tests
python run_tests.py apps.life.tests.test_views
```

---

## Task Undo Feature

### Overview
When a task is accidentally marked as complete, users can now easily undo the action using an "Undo" link that appears next to completed tasks.

### How It Works
1. User marks a task complete by clicking the checkbox
2. Task shows as completed (strikethrough, faded)
3. An "Undo" link appears next to the completed task
4. Clicking "Undo" toggles the task back to active

### Implementation
- **Template:** `templates/life/task_list.html` (lines 94-100) - Undo form with button
- **View:** `apps/life/views.py` - `TaskToggleView` handles both complete and undo
- **Model:** `apps/life/models.py` - `Task.mark_incomplete()` method clears completion

### Tests
Located in `apps/life/tests/test_views.py`:
- `test_task_toggle_completes_task` - Verify toggle marks task complete
- `test_task_toggle_uncompletes_task` - Verify toggle marks task incomplete (undo)
- `test_completed_task_shows_undo_link` - Verify Undo link appears for completed tasks
- `test_incomplete_task_no_undo_link` - Verify no Undo link for incomplete tasks

### Running Tests (Local Development)
```bash
# Run task-related tests
python run_tests.py apps.life.tests.test_views.TaskViewTest

# Run all life app tests
python run_tests.py apps.life.tests
```

**Note:** Railway has no shell access. All tests must be run locally before pushing to main. Railway auto-deploys on push.

---

## User-Specific Saved Verses

### Overview
Users can save Scripture verses to their personal library. Each user's saved verses are private and not shared with other users.

### The Bug (Fixed)
Previously, saved Scripture verses were stored in a global `ScriptureVerse` table with no user association. This meant:
- When Danny saved a verse, all users could see it
- Heather saw Danny's saved verses when she logged in for the first time
- This was a data leak / privacy issue

### The Fix
Created a new `SavedVerse` model that extends `UserOwnedModel` (which includes a `user` foreign key):
- Each saved verse now belongs to a specific user
- The Scripture list view filters by `user=request.user`
- New verses are created with the current user assigned

### Key Files
- `apps/faith/models.py` - `SavedVerse` model (line 174+)
- `apps/faith/views.py` - `ScriptureListView` and `ScriptureSaveView` updated to use `SavedVerse`
- `apps/faith/admin.py` - `SavedVerseAdmin` for admin interface
- `apps/faith/migrations/0002_add_saved_verse_model.py` - Creates the SavedVerse table
- `apps/faith/migrations/0003_migrate_existing_verses_to_danny.py` - Data migration to assign existing verses to Danny

### Data Migration
The data migration (`0003_migrate_existing_verses_to_danny.py`) copies all existing `ScriptureVerse` entries to the new `SavedVerse` table and assigns them to `dannyjenkins71@gmail.com`. This preserves Danny's saved verses while ensuring new users start with an empty library.

### Tests
Located in `apps/faith/tests/test_saved_verses.py`:
- `test_saved_verse_belongs_to_user` - Verify SavedVerse has user field
- `test_user_only_sees_own_saved_verses` - Verify data isolation
- `test_save_verse_assigns_to_current_user` - Verify new verses assigned correctly
- `test_other_user_cannot_see_saved_verses` - Verify privacy between users

### Running Tests
```bash
# Run saved verses tests
python manage.py test apps.faith.tests.test_saved_verses

# Run all faith app tests
python manage.py test apps.faith
```

---

## System Audit & Security

### Overview
A comprehensive system audit was conducted on 2025-12-28. The audit evaluated security, code quality, error handling, and maintainability. All CRITICAL and HIGH priority issues have been fixed.

### Current Health Score: 8.5/10

### Audit Documents
- `SYSTEM_AUDIT_REPORT.md` - Full findings with remediation status
- `SYSTEM_REVIEW.md` - Repeatable audit process with checklists

### Security Fixes Applied (2025-12-28)

#### CRITICAL Issues (Fixed)
1. **Open Redirect Vulnerability** - Created `is_safe_redirect_url()` and `get_safe_redirect_url()` utilities in `apps/core/utils.py`. Fixed 3 vulnerable locations.
2. **Hardcoded API Key** - Removed hardcoded Bible API key from `config/settings.py`. Now uses environment variable only.

#### HIGH Priority Issues (Fixed)
1. **Bare except clauses (10+ locations)** - Replaced with specific exception types in:
   - `apps/users/views.py`
   - `apps/ai/dashboard_ai.py`
   - `apps/admin_console/views.py`
   - `run_tests.py`

2. **XSS Risk in HTMX Response** - Added `django.utils.html.escape()` to `RandomPromptView` in `apps/journal/views.py`

3. **Unsafe Client IP Extraction** - Added validation and documentation to `get_client_ip()` in `apps/users/views.py`

4. **Missing Custom Error Pages** - Created:
   - `templates/404.html` - User-friendly 404 page
   - `templates/500.html` - User-friendly 500 page
   - Custom error handlers in `config/urls.py` and `apps/core/views.py`

5. **Console-Only Logging** - Added persistent logging in `config/settings.py`:
   - `logs/error.log` - RotatingFileHandler (5MB, 5 backups)
   - `logs/app.log` - RotatingFileHandler (10MB, 3 backups)
   - AdminEmailHandler for critical errors

### Security Tests
Located in `apps/core/tests/test_core_comprehensive.py`:
- `SafeRedirectUrlTests` - 14 tests for redirect URL validation
- Tests cover: relative URLs, same-host URLs, external URLs, protocol-relative URLs, javascript: URLs

### Running Security Tests
```bash
# Run safe redirect tests
python manage.py test apps.core.tests.test_core_comprehensive.SafeRedirectUrlTests

# Run all core tests
python manage.py test apps.core.tests
```

### Audit Checklist (Quick Check)
Run these commands to check for common issues:
```bash
# Check for bare except clauses
grep -rn "except:" apps/ --include="*.py" | grep -v "except Exception"

# Check for |safe filter usage
grep -rn "|safe" templates/

# Check for hardcoded emails
grep -rn "@.*\.com" apps/ --include="*.py" | grep -v test

# Check for TODO/FIXME
grep -rn "TODO\|FIXME\|HACK\|XXX" apps/ --include="*.py"

# Run full test suite
python run_tests.py
```

### Remaining Issues (Medium/Low Priority)
- Error dashboard widget (no admin visibility for errors)
- Health check endpoint (no `/health/` endpoint)
- Input validation improvements (timezone, year/month, file uploads)
- Large file splitting (views.py files over 500 lines)
- 29 backup files to clean up

---

## Nutrition/Food Tracking

### Overview
The Nutrition feature allows users to log food consumption, track macros (protein, carbs, fat), set nutrition goals, and view daily/historical stats. It includes support for a global food library, custom user foods/recipes, and is prepared for future AI-powered food recognition via camera scanning.

### Models (`apps/health/models.py`)
| Model | Description |
|-------|-------------|
| `FoodItem` | Global food library (USDA, barcode, AI sources) - shared across all users |
| `CustomFood` | User-created foods and recipes (user-scoped via `UserOwnedModel`) |
| `FoodEntry` | Individual food log entry with meal type, location, eating context |
| `DailyNutritionSummary` | Aggregated daily totals with macro percentages (auto-recalculated) |
| `NutritionGoals` | User's calorie/macro targets with effective date ranges |

### CameraScan Model (`apps/core/models.py`)
Foundation for AI-powered scanning (food recognition, barcode scanning, medicine recognition). Fields include:
- `image` - Uploaded photo
- `detected_category` - food, packaged_food, medicine, etc.
- `confidence_score` - AI confidence (0-1)
- `raw_ai_response` - Full AI response JSON
- `processing_status` - pending, processing, completed, failed, cancelled

### URL Routes (`/health/nutrition/`)
| Route | View | Description |
|-------|------|-------------|
| `/nutrition/` | `NutritionHomeView` | Daily dashboard with meal breakdown |
| `/nutrition/add/` | `FoodEntryCreateView` | Full food entry form |
| `/nutrition/quick-add/` | `QuickAddFoodView` | Simplified calorie-only logging |
| `/nutrition/entry/<pk>/` | `FoodEntryDetailView` | View entry details |
| `/nutrition/entry/<pk>/edit/` | `FoodEntryUpdateView` | Edit entry |
| `/nutrition/entry/<pk>/delete/` | `FoodEntryDeleteView` | Delete entry |
| `/nutrition/history/` | `FoodHistoryView` | Historical log with date/meal filters |
| `/nutrition/stats/` | `NutritionStatsView` | Trends and analytics |
| `/nutrition/goals/` | `NutritionGoalsView` | Set calorie/macro goals |
| `/nutrition/foods/` | `CustomFoodListView` | List user's custom foods |
| `/nutrition/foods/add/` | `CustomFoodCreateView` | Create custom food |
| `/nutrition/foods/<pk>/edit/` | `CustomFoodUpdateView` | Edit custom food |
| `/nutrition/foods/<pk>/delete/` | `CustomFoodDeleteView` | Delete custom food |

### Key Features
- **Meal Types**: Breakfast, Lunch, Dinner, Snack
- **Entry Sources**: Manual, Barcode, Camera, Voice, Quick Add
- **Location Context**: Home, Restaurant, Work, Travel, Other
- **Eating Pace**: Rushed, Normal, Slow/Mindful
- **Hunger/Fullness Tracking**: 1-5 scale before/after eating
- **Mood Tags**: JSON field for emotional context
- **Net Carbs**: Auto-calculated (carbs - fiber)
- **Macro Percentages**: Auto-calculated in DailyNutritionSummary

### Test Files
- `apps/health/tests/test_nutrition.py` - 80 tests covering:
  - Model tests (FoodItem, CustomFood, FoodEntry, DailyNutritionSummary, NutritionGoals)
  - View tests (authentication, CRUD, context data)
  - Form validation tests
  - Data isolation tests (users can only see their own data)
  - Quick add functionality

### Running Nutrition Tests
```bash
# Run all nutrition tests
python manage.py test apps.health.tests.test_nutrition

# Run specific test class
python manage.py test apps.health.tests.test_nutrition.FoodEntryModelTest

# Run all health tests (includes nutrition, medicine, fitness)
python manage.py test apps.health
```

### Future AI Integration Points
1. **Camera Recognition**: Use `CameraScan` model to upload food photos for AI identification
2. **Barcode Scanning**: Lookup `FoodItem` by barcode, create if not found
3. **Voice Input**: Parse natural language food descriptions
4. **Smart Suggestions**: Based on eating patterns and time of day

---
*Last updated: 2025-12-28*
