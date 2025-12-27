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
- **Context-aware help system (IMPLEMENTED):** Full "?" help button with page-specific content
  - `apps/help/` - New Django app with HelpTopic and AdminHelpTopic models
  - HelpContextMixin added to all major views for automatic context injection
  - Django Admin "?" button in header with URL-based context detection
  - API endpoints: `/help/api/topic/<context_id>/` and `/help/api/admin/<context_id>/`
  - Fixtures: `help_topics.json` (13 topics), `admin_help_topics.json` (7 topics)
  - Tests: `apps/help/tests/` - test_models.py, test_views.py, test_mixins.py
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
- `templates/admin/base_site.html` - Custom Django admin branding with Admin Console link and help button
- `apps/help/` - Context-aware help system (see Help System section below)
- `static/js/help.js` - Help modal JavaScript (openHelpModal, closeHelpModal, fetchHelpContent)
- `static/css/help.css` - Help button and modal styles

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

## Context-Aware Help System (IMPLEMENTED)

### Overview
The application has a "?" help button that provides context-aware help. The button appears:
- **User pages:** In the navigation bar (upper-right, next to avatar)
- **Django Admin:** In the header (next to "Back to Admin Console" link)

### Architecture

**Models (apps/help/models.py):**
- `HelpTopic` - User-facing help content (Dashboard, Journal, Health, etc.)
- `AdminHelpTopic` - Admin/technical help content (Django Admin pages)

**Views (apps/help/views.py):**
- `HelpTopicAPIView` - GET `/help/api/topic/<context_id>/` - Returns user help
- `AdminHelpTopicAPIView` - GET `/help/api/admin/<context_id>/` - Returns admin help (staff only)
- `HelpSearchAPIView` - GET `/help/api/search/?q=<query>` - Search help topics

**Mixin (apps/help/mixins.py):**
- `HelpContextMixin` - Add to any view to inject `help_context_id` into template context

### Adding Help to a New View

1. Add the mixin to your view:
```python
from apps.help.mixins import HelpContextMixin

class MyView(HelpContextMixin, LoginRequiredMixin, TemplateView):
    template_name = "myapp/mypage.html"
    help_context_id = "MYAPP_MYPAGE"
```

2. Add a HelpTopic fixture entry in `apps/help/fixtures/help_topics.json`:
```json
{
  "model": "help.helptopic",
  "pk": 14,
  "fields": {
    "context_id": "MYAPP_MYPAGE",
    "help_id": "myapp-mypage",
    "title": "My Page Help",
    "description": "Brief description",
    "content": "## My Page\n\nMarkdown help content...",
    "app_name": "myapp",
    "order": 1,
    "is_active": true
  }
}
```

3. Load the fixture: `python manage.py loaddata help_topics`

### Current HELP_CONTEXT_IDs

**User Pages (HelpTopic):**
- `DASHBOARD_HOME` - Dashboard main page
- `JOURNAL_HOME`, `JOURNAL_ENTRY_LIST`, `JOURNAL_ENTRY_DETAIL`, `JOURNAL_ENTRY_CREATE`
- `HEALTH_HOME` - Health module home
- `FAITH_HOME` - Faith module home
- `LIFE_HOME` - Life module home
- `PURPOSE_HOME` - Purpose module home
- `SETTINGS_PREFERENCES` - User preferences page
- `SETTINGS_PROFILE`, `SETTINGS_PROFILE_EDIT` - Profile pages
- `ADMIN_CONSOLE_HOME`, `ADMIN_CONSOLE_SITE_CONFIG`, `ADMIN_CONSOLE_THEMES`, `ADMIN_CONSOLE_USERS`

**Django Admin (AdminHelpTopic):**
- `ADMIN_DASHBOARD` - Django Admin home (/admin/)
- `ADMIN_AI_PROMPTS` - AI Prompt Configurations
- `ADMIN_COACHING_STYLES` - Coaching Styles
- `ADMIN_SITE_CONFIG` - Site Configuration
- `ADMIN_THEMES` - Theme Management
- `ADMIN_HELP_TOPICS` - Help Topics management
- `ADMIN_GENERAL` - Fallback for unmapped admin pages

### Files

**Backend:**
- `apps/help/models.py` - HelpTopic, AdminHelpTopic models with caching
- `apps/help/views.py` - API endpoints
- `apps/help/mixins.py` - HelpContextMixin
- `apps/help/urls.py` - URL routing
- `apps/help/admin.py` - Django admin registration
- `apps/help/fixtures/help_topics.json` - User help content (13 topics)
- `apps/help/fixtures/admin_help_topics.json` - Admin help content (7 topics)

**Frontend:**
- `static/js/help.js` - openHelpModal(), closeHelpModal(), fetchHelpContent()
- `static/css/help.css` - Button and modal styles
- `templates/components/help_button.html` - Reusable button component
- `templates/components/help_modal.html` - Modal dialog component
- `templates/components/navigation.html` - Contains the "?" button
- `templates/admin/base_site.html` - Django Admin help button

**Tests:**
- `apps/help/tests/test_models.py` - Model tests (caching, queries)
- `apps/help/tests/test_views.py` - API endpoint tests
- `apps/help/tests/test_mixins.py` - Mixin tests

### Testing the Help System
```bash
# Run all help tests
python manage.py test apps.help

# Run specific test file
python manage.py test apps.help.tests.test_views
python manage.py test apps.help.tests.test_models
python manage.py test apps.help.tests.test_mixins
```

### Writing Help Content Rules
1. **Start each step with an action verb** (Click, Enter, Select, Navigate)
2. **Reference exact UI labels** in quotes (e.g., Click "Save")
3. **Use Markdown formatting** - The content is rendered as HTML
4. **Keep descriptions concise** - They appear as subtitles
5. **Organize with headers** - Use ## for sections, ### for subsections

---
*Last updated: 2024-12-27*
