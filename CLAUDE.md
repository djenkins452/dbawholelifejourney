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
- **Apps:** users, core, dashboard, journal, faith, health, purpose, ai, life, admin_console, help
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
- **WLJ Assistant Chat Bot (IMPLEMENTED):** Floating chat widget for internal help
  - Bot name: "WLJ Assistant" with welcome message: "I am your WLJ assistant, what can I help you with today?"
  - Searches internal help articles only (no external AI)
  - Tone adapts to user's selected AI coaching style (7 styles supported)
  - Floating button in bottom-right corner on all authenticated pages
  - Email conversation transcript option before closing
  - Ephemeral sessions (deleted when chat ends)
  - Company logo in header (replaced robot emoji)
  - 10 help articles covering core app features
- **Context-aware help system (IMPLEMENTED):** Full "?" help button with page-specific content
  - `apps/help/` - Django app with HelpTopic, AdminHelpTopic, HelpCategory, HelpArticle, HelpConversation, HelpMessage models
  - HelpContextMixin added to all major views for automatic context injection
  - Django Admin "?" button in header with URL-based context detection
  - API endpoints for help topics, chat, and search
- **Onboarding wizard:** Step-by-step wizard for new users (location, timezone, preferences)
- **Database-driven AI prompts:** AIPromptConfig model allows admin control of all AI prompt types (10 types)
- **Database-driven coaching styles:** CoachingStyle model with 7 styles, editable via Django admin
- **Django admin improvements:** Added "Back to Admin Console" link in header
- **Fitness tracking:** Added comprehensive fitness tracking feature
- **Custom domain:** Added support for wholelifejourney.com
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
- `apps/help/` - Help system with context-aware help AND WLJ Assistant chat bot
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
- **Run help app tests:** `python manage.py test apps.help` (69 tests)
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

## WLJ Assistant Chat Bot (IMPLEMENTED)

### Overview
A floating chat widget that helps users find information in the internal help documentation. The bot adapts its tone based on the user's selected AI coaching style.

### Features
- **Floating Button:** Bottom-right corner on all authenticated pages
- **Company Logo:** Uses the WLJ logo instead of a robot emoji
- **Tone Adaptation:** Matches user's AI coaching style (7 styles)
- **Article Search:** Searches by title, keywords, summary, and content
- **Module Priority:** Boosts results matching current page's module
- **Email Export:** Option to email conversation before closing
- **Ephemeral Sessions:** Conversations deleted when chat ends

### Architecture

**Models (apps/help/models.py):**
- `HelpCategory` - Categories for organizing help articles
- `HelpArticle` - Help articles with title, summary, content, keywords, module
- `HelpConversation` - Chat session with user, context, timestamps
- `HelpMessage` - Individual messages (user or assistant)

**Service (apps/help/services.py):**
- `HelpChatService` - Main service class
  - `search_articles(query, module, limit)` - Search with scoring
  - `generate_response(query, context_module)` - Format response with tone
  - `get_suggestions_for_module(module)` - Get contextual suggestions
  - `TONE_TEMPLATES` - 7 coaching style templates

**Views (apps/help/views.py):**
- `ChatStartView` - POST `/help/api/chat/start/` - Start conversation
- `ChatMessageView` - POST `/help/api/chat/message/` - Send message
- `ChatEndView` - POST `/help/api/chat/end/` - End conversation (optional email)
- `ChatSearchView` - GET `/help/api/chat/search/?q=<query>` - Search articles
- `ChatSuggestionsView` - GET `/help/api/chat/suggestions/?module=<module>` - Get suggestions
- `HelpCenterView` - GET `/help/` - Browse all help categories
- `HelpArticleView` - GET `/help/article/<slug>/` - View single article
- `HelpCategoryView` - GET `/help/category/<slug>/` - View category articles

**Frontend:**
- `templates/components/chat_widget.html` - Complete widget (HTML, CSS, JS)
- Included in `templates/base.html` for authenticated users

**Fixtures:**
- `apps/help/fixtures/help_categories.json` - 5 categories
- `apps/help/fixtures/help_articles.json` - 10 help articles

### Coaching Style Tone Templates

| Style | Greeting Response | Not Found Response |
|-------|------------------|-------------------|
| `supportive` | "Great question! Here's what I found..." | "I couldn't find a specific answer..." |
| `direct_coach` | "Here's what you need to know:" | "No exact match. Check these..." |
| `gentle_guide` | "Let me share what I found for you:" | "I wasn't able to find exactly..." |
| `wise_mentor` | "Here's some wisdom on that topic:" | "That's not something I have specific guidance on..." |
| `cheerful_friend` | "Awesome question! Here's what I found:" | "Hmm, couldn't find an exact match..." |
| `calm_companion` | "Here's some helpful information:" | "I don't have an exact answer..." |
| `accountability_partner` | "Let's get you sorted. Here's what you need:" | "Couldn't find that specific info..." |

### Adding Help Articles

1. Add to `apps/help/fixtures/help_articles.json`:
```json
{
    "model": "help.helparticle",
    "pk": 11,
    "fields": {
        "title": "My New Article",
        "slug": "my-new-article",
        "summary": "Brief description for search results",
        "content": "Full article content with **markdown** support...",
        "category": 2,
        "module": "journal",
        "keywords": "keyword1, keyword2, keyword3",
        "is_active": true,
        "sort_order": 1,
        "created_at": "2024-12-27T12:00:00Z",
        "updated_at": "2024-12-27T12:00:00Z"
    }
}
```

2. Load the fixture: `python manage.py loaddata help_articles`

### Module Values
Use these module values for contextual help:
- `general` - General/overview articles
- `dashboard` - Dashboard features
- `journal` - Journal/entries
- `health` - Health tracking
- `faith` - Faith/prayers/scripture
- `life` - Life module (tasks, projects, documents, recipes)
- `purpose` - Goals and purpose tracking
- `settings` - Preferences and settings

### Testing the Chat Bot
```bash
# Run all help tests (69 tests)
python manage.py test apps.help

# Run specific test files
python manage.py test apps.help.tests.test_models      # Model tests
python manage.py test apps.help.tests.test_views       # View/API tests
python manage.py test apps.help.tests.test_services    # Service tests
python manage.py test apps.help.tests.test_mixins      # Mixin tests
```

### Test Coverage
- **test_models.py:** HelpCategory, HelpArticle, HelpConversation, HelpMessage
- **test_views.py:** All API endpoints, authentication, chat flow
- **test_services.py:** HelpChatService, search, tone templates, response generation

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
- `apps/help/models.py` - All help models with caching
- `apps/help/views.py` - API endpoints
- `apps/help/services.py` - HelpChatService
- `apps/help/mixins.py` - HelpContextMixin
- `apps/help/urls.py` - URL routing
- `apps/help/admin.py` - Django admin registration
- `apps/help/fixtures/help_topics.json` - User help content (13 topics)
- `apps/help/fixtures/admin_help_topics.json` - Admin help content (7 topics)
- `apps/help/fixtures/help_categories.json` - Chat bot categories (5)
- `apps/help/fixtures/help_articles.json` - Chat bot articles (10)

**Frontend:**
- `static/js/help.js` - openHelpModal(), closeHelpModal(), fetchHelpContent()
- `static/css/help.css` - Button and modal styles
- `templates/components/help_button.html` - Reusable button component
- `templates/components/help_modal.html` - Modal dialog component
- `templates/components/chat_widget.html` - WLJ Assistant chat widget
- `templates/components/navigation.html` - Contains the "?" button
- `templates/admin/base_site.html` - Django Admin help button

**Tests:**
- `apps/help/tests/test_models.py` - Model tests (all 6 models)
- `apps/help/tests/test_views.py` - API endpoint tests (help topics + chat)
- `apps/help/tests/test_services.py` - HelpChatService tests
- `apps/help/tests/test_mixins.py` - Mixin tests

### Testing the Help System
```bash
# Run all help tests (69 tests total)
python manage.py test apps.help

# Run specific test file
python manage.py test apps.help.tests.test_views
python manage.py test apps.help.tests.test_models
python manage.py test apps.help.tests.test_services
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
