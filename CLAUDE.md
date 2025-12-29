# Master Prompt for Whole Life Journey Project

**Project:** Whole Life Journey - Django 5.x personal wellness/journaling app
**Repo:** C:\dbawholelifejourney (GitHub: djenkins452/dbawholelifejourney)
**Deployment:** Railway with PostgreSQL (via DATABASE_URL env var)

## Related Documentation
- `CLAUDE_FEATURES.md` - Detailed feature documentation (onboarding, help system, Dashboard AI, nutrition, medicine, camera scan, biometric login)
- `CLAUDE_CHANGELOG.md` - Historical fixes, migrations, and change history
- `THIRD_PARTY_SERVICES.md` - Third-party services inventory
- `SECURITY_REVIEW_REPORT.md` - Security review with 21 findings
- `BACKUP.md` - Backup and disaster recovery playbook

## Tech Stack
- Django 5.x with django-allauth for authentication
- PostgreSQL (production) / SQLite (development)
- Railway deployment with Nixpacks builder
- Gunicorn for WSGI
- OpenAI API for AI coaching features

## Key Architecture
- **Apps:** users, core, dashboard, journal, faith, health, purpose, ai, life, admin_console, help, scan
- **User model:** Custom User in apps/users/models.py (email-based auth)
- **Preferences:** UserPreferences model stores timezone, module toggles, AI settings
- **Soft deletes:** Models use soft_delete() method, not hard deletes
- **AI Service:** Database-driven prompts via AIPromptConfig and CoachingStyle models

## Deployment Notes
- **Claude performs all merges and pushes** - Always merge worktree branches to main and push to GitHub
- Always push from the main repository (C:\dbawholelifejourney), not from worktrees
- Use meaningful merge commit messages with `-m` flag when merging to main
- Procfile runs: migrate → load_initial_data → load_danny_workout_templates → collectstatic → gunicorn
- postgres.railway.internal hostname only available at runtime, NOT build time
- All DB operations must be in startCommand, not build/release phase
- **Railway has no shell access** - All fixes must be done via code changes and redeployment

### One-Time Data Loading Pattern (Railway)
Since Railway has NO shell/console access, one-time data loading must be done via Procfile:

1. Create an idempotent management command (uses `get_or_create`, checks for existing records)
2. Add the command to Procfile startup chain (after migrate, before collectstatic)
3. The command runs on every deploy but only creates data if it doesn't exist
4. After confirmed working, optionally remove from Procfile to save startup time

**Example:** `load_danny_workout_templates` - loads workout templates for a specific user, safe to run multiple times.

## Important Files
- `Procfile` - Railway deployment startup command
- `run_tests.py` - Enhanced test runner with database history
- `check_dependencies.py` - Verifies all required packages
- `apps/core/management/commands/load_initial_data.py` - System data loading
- `apps/ai/models.py` - AIPromptConfig, CoachingStyle, AIInsight, AIUsageLog, Dashboard AI models
- `apps/ai/services.py` - AIService with database-driven prompts
- `apps/ai/personal_assistant.py` - Dashboard AI Personal Assistant service
- `apps/ai/trend_tracking.py` - Trend analysis and drift detection

## AI Configuration (via Django Admin)
- **AI Prompt Configurations** (/admin/ai/aipromptconfig/): 10 prompt types
- **Coaching Styles** (/admin/ai/coachingstyle/): 7 personality styles
- **AI Insights** (/admin/ai/aiinsight/): Cached AI-generated insights
- **AI Usage Logs** (/admin/ai/aiusagelog/): API usage tracking

## User Preferences
- Do NOT make pushes that could wipe database data
- User is deploying to Railway with PostgreSQL
- User's timezone: America/New_York (EST)
- Prefers descriptive merge commit messages, not auto-generated ones

## Code Style & Documentation Standards

### File Header Comments (MANDATORY)
Every file created or updated MUST include a documentation header:

**Python:**
```python
# ==============================================================================
# File: filename.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Brief description of what this file does
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: YYYY-MM-DD
# Last Updated: YYYY-MM-DD
# ==============================================================================
```

**JavaScript:**
```javascript
// ==============================================================================
// File: filename.js
// Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
// Description: Brief description
// Owner: Danny Jenkins (dannyjenkins71@gmail.com)
// Created: YYYY-MM-DD
// Last Updated: YYYY-MM-DD
// ==============================================================================
```

### Third-Party Services
When adding/modifying any third-party service: Update `THIRD_PARTY_SERVICES.md` immediately.

## Session Instructions

### Starting a New Session
Say: **"Read CLAUDE.md and continue"** - this gives full project context.

### MANDATORY: Documentation Updates
**After ANY code changes, you MUST update the relevant documentation files:**

1. **`CLAUDE_CHANGELOG.md`** - Update for ANY changes made during the session
   - Add new section with date if needed
   - Document what changed, files modified, and why
   - Include migration names if any were created

2. **`CLAUDE_FEATURES.md`** - Update when modifying or adding features
   - Camera Scan, Nutrition, Medicine, Dashboard AI, etc.
   - Keep feature documentation current with actual functionality

3. **`CLAUDE.md`** - Update when:
   - Test count changes significantly
   - New apps or major architecture changes
   - New deployment patterns or important files

4. **`THIRD_PARTY_SERVICES.md`** - Update when adding/modifying external services

**DO NOT wait for user to ask** - update documentation automatically as part of completing each task.

### End of Session Tasks
1. Run `git log --oneline -20` to see recent commits
2. Update `CLAUDE_CHANGELOG.md` with any new fixes (if not already done)
3. Verify all .md files are current
4. Commit and push changes with descriptive message

### After Making Code Changes
1. Run tests: `python manage.py test` or `python run_tests.py`
2. If new features, check if tests exist in `apps/<app>/tests/`
3. Create missing tests following existing patterns
4. **Update relevant .md documentation files**

## Development Setup

```bash
# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Verify dependencies
python check_dependencies.py --install
```

## Testing

### Commands
- **Run all tests:** `python manage.py test` or `python run_tests.py`
- **Run specific app:** `python manage.py test apps.<app_name>`
- **Current test count:** 1302 tests (as of 2025-12-29)

### CRITICAL: Test User Setup Pattern
**All test users MUST have onboarding completed** or tests fail with 302 redirects.

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
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
```

### Test Files with User Mixins
- `apps/users/tests/test_users_comprehensive.py` - `UserTestMixin`
- `apps/dashboard/tests/test_dashboard_comprehensive.py` - `DashboardTestMixin`
- `apps/journal/tests/test_journal_comprehensive.py` - `JournalTestMixin`
- `apps/faith/tests/test_faith_comprehensive.py` - `FaithTestMixin`
- `apps/health/tests/test_health_comprehensive.py` - `HealthTestMixin`
- `apps/life/tests/test_life_comprehensive.py` - `LifeTestMixin`
- `apps/ai/tests/test_ai_comprehensive.py` - `AITestMixin`
- `apps/core/tests/test_core_comprehensive.py` - `CoreTestMixin`

### Common Test Gotchas
1. **302 redirects instead of 200:** User not marked as onboarding complete
2. **Count assertions failing:** Data migrations may pre-load records (e.g., 20 journal prompts)
3. **Date comparisons failing:** Use `timezone.now().date()` or `get_user_today(user)`
4. **Cache tests failing:** Use `@override_settings` with LocMemCache

## Testing Strategy

### Role & Mindset
Act as a **senior software engineer and release manager**. Balance speed, stability, and user trust.

### Requirements
1. **NEW APP/FEATURE:** Fully test normal flows, edge cases, permissions, errors
2. **INTEGRATION:** Test anything the new app reads from, writes to, triggers, or depends on
3. **SMOKE TEST:** Before deploy - login works, dashboard loads, critical workflows function

### What NOT To Do
- Fully retest unrelated modules
- Perform manual full regression
- Retest untouched, stable code

### Exceptions (Always Extra Testing)
- Authentication/authorization changes
- Security-related changes
- Shared core libraries
- Database schema/migration changes

### Decision Rule
Before deploying: **"What could this change accidentally break?"** Only test those areas.

---

*For detailed feature documentation, see `CLAUDE_FEATURES.md`*
*For historical changes, see `CLAUDE_CHANGELOG.md`*
*Last updated: 2025-12-29*
