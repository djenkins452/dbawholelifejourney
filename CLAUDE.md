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
At the end of a session or when asked, update this file by:
1. Run `git log --oneline -20` to see recent commits
2. Update the "Recent Fixes Applied" section between the HTML comments
3. Commit and push the changes

---
*Last updated: 2024-12-27*
