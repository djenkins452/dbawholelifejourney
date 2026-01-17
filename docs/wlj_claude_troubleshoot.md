# ==============================================================================
# File: docs/wlj_claude_troubleshoot.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Known issues and solutions for common development problems
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-04
# Last Updated: 2026-01-16
# ==============================================================================

# WLJ Troubleshooting Guide

**CHECK THIS FILE BEFORE IMPLEMENTING** - These are known issues that have caused problems in the past.

---

## 1. Property Shadowing Database Fields

**Error:** `FieldError: Cannot resolve keyword 'fieldname' into field`

**Cause:** Python property with same name as inherited DB field shadows it

**Solution:** Rename property (e.g., `status` → `health_status`)

**Example:** Budget model had `status` property that shadowed `SoftDeleteModel.status` field

---

## 2. Railway Migration State Issues

**Error:** Missing columns even though migration shows as "applied"

**Cause:** Migration recorded in `django_migrations` but schema change failed

**Solution:** Add fix function to `load_initial_data.py` (runs on every deploy)

```python
def _fix_missing_column(self):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public'  -- CRITICAL for PostgreSQL!
              AND table_name = 'your_table' AND column_name = 'missing_col'
        """)
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE your_table ADD COLUMN missing_col...")
```

**See also:** `docs/wlj_claude_deploy.md` for the full migration fix pattern.

---

## 3. Railway Nixpacks Caching

**Problem:** Changes to `nixpacks.toml` or `Procfile` ignored due to caching

**Solution:** Embed new commands inside `load_initial_data.py` using `call_command()`

```python
# In load_initial_data.py handle() method:
call_command('your_new_command', verbosity=1)
```

**See also:** `docs/wlj_claude_deploy.md` for the full Nixpacks caching workaround.

---

## 4. Test Users Require Onboarding

**Error:** 302 redirects instead of 200 in tests

**Solution:** All test users MUST have onboarding completed:

```python
user.preferences.has_completed_onboarding = True
user.preferences.save()
TermsAcceptance.objects.create(user=user, terms_version='1.0')
```

**Test Mixin Pattern:**
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

---

## 5. CSRF Trusted Origins

**Error:** "Origin checking failed" on forms

**Cause:** `CSRF_TRUSTED_ORIGINS` was inside `if not DEBUG:` block

**Solution:** Keep `CSRF_TRUSTED_ORIGINS` outside any DEBUG conditional

```python
# settings.py - CORRECT
CSRF_TRUSTED_ORIGINS = [
    'https://wholelifejourney.com',
    'https://www.wholelifejourney.com',
]

# NOT inside if not DEBUG block!
```

---

## 6. PostgreSQL Schema Checks

**Error:** Column appears to exist but doesn't

**Cause:** Query missing `table_schema = 'public'`

**Solution:** ALWAYS include `table_schema = 'public'` in PostgreSQL info_schema queries

```python
# CORRECT
cursor.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'your_table'
      AND column_name = 'your_column'
""")

# WRONG - may check wrong schema
cursor.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'your_table'
      AND column_name = 'your_column'
""")
```

---

## 7. SoftDeleteManager and Automatic Filtering

**Error:** `FieldError: Cannot resolve keyword 'is_deleted' into field`

**Cause:** Attempting to filter by `is_deleted=False` on models that use `SoftDeleteModel`

**Background:**
Models inheriting from `UserOwnedModel` (which inherits `SoftDeleteModel`) use a custom `SoftDeleteManager` that **automatically excludes deleted records**. The manager filters by `status="active"` in its `get_queryset()` method.

**Key Points:**
- `is_deleted` is a **@property**, NOT a database field - you cannot filter by it
- The actual database field is `status` with values: `'active'`, `'archived'`, `'deleted'`
- The default manager (`objects`) already filters to only show active records
- You do NOT need to manually filter out deleted records

**Correct Pattern:**
```python
# CORRECT - Let the manager handle soft delete filtering
queryset = JournalEntry.objects.filter(user=self.user)

# CORRECT - If you need to include deleted records
queryset = JournalEntry.all_objects.filter(user=self.user)

# CORRECT - If you need only deleted records
queryset = JournalEntry.objects.deleted_only()
```

**Incorrect Pattern:**
```python
# WRONG - is_deleted is a property, not a field
queryset = JournalEntry.objects.filter(user=self.user, is_deleted=False)

# WRONG - status field exists but filtering by it defeats the purpose
queryset = JournalEntry.objects.filter(user=self.user, status='active')
```

**Reference:** See `apps/core/models.py` for `SoftDeleteManager` and `SoftDeleteModel` implementation.

---

## 8. Django Management Commands Hanging on Windows

**Problem:** `python manage.py` commands (test, check, makemigrations) hang indefinitely

**Cause:** DATABASE_URL is set in environment, causing Django to try connecting to production PostgreSQL, which times out on Windows.

**Solution:** Create migrations manually instead of using `makemigrations`:

```python
# Create migration file manually in apps/<app>/migrations/
# Example: 0015_add_project_priority.py

from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('app_name', '0014_previous_migration'),
    ]
    operations = [
        migrations.AddField(
            model_name='modelname',
            name='fieldname',
            field=models.CharField(max_length=100, default=''),
        ),
    ]
```

**For Claude Code:** Skip running `manage.py` commands. Create migrations manually and let Railway apply them on deploy.

---

## Quick Diagnostic Commands

```bash
# Check if migration is recorded
python manage.py showmigrations app_name

# Check actual database schema (local)
python manage.py dbshell
\d table_name  # PostgreSQL
.schema table_name  # SQLite

# Run specific migration
python manage.py migrate app_name migration_name

# Check for model/migration sync issues
python manage.py makemigrations --check
```

---

## Related Documentation

- `docs/wlj_claude_deploy.md` - Deployment patterns and Railway-specific issues
- `docs/wlj_claude_changelog.md` - Historical fixes and what caused them
- `apps/core/models.py` - SoftDeleteManager and SoftDeleteModel (soft delete pattern)
- `assistant/data_service.py` - Personal Data Query System (uses soft delete pattern)
- `CLAUDE.md` - Main project reference

---

## 9. "Slide to Right" Visual Glitch on Page Navigation (SOLVED)

**Problem:** Pages show a "PowerPoint-like" slide transition on every navigation. Initially misdiagnosed as FOUC (Flash of Unstyled Content).

**Symptoms:**
- Occurs on page navigation (clicking links)
- Does NOT occur on hard refresh
- Described as "something sliding right off screen" or "PowerPoint transition"
- Visible for ~0.3 seconds on every page load

**Root Cause:** Chat drawer widget (`templates/components/chat_widget.html`) was:
1. Persisting open state in localStorage via `DRAWER_STATE_KEY`
2. Auto-opening on page load via `checkSavedState()` function
3. Immediately closing (for unknown reason), causing visible slide animation
4. CSS transition `transform 0.3s ease-out` made the close visible

**Key Diagnostic Clue:** User described "slides to the right" - this pointed to `translateX` animation, NOT CSS loading issues. Searching for `translateX` led directly to the chat drawer.

**Solution (2026-01-13):**
1. Removed `checkSavedState()` function - drawer no longer auto-opens from localStorage
2. Removed CSS transition from base `.assistant-drawer` class
3. Added `.animate` class that contains the transition
4. JavaScript adds `.animate` class only on first user click

**Files Modified:**
- `templates/components/chat_widget.html`

**Code Pattern (Preventing Animation on Initial Render):**
```css
/* Base class - NO transition */
.assistant-drawer {
    transform: translateX(100%);
    /* No transition property here */
}

/* Transition only after user interaction */
.assistant-drawer.animate {
    transition: transform 0.3s ease-out;
}
```

```javascript
function openDrawer() {
    drawer.classList.add('animate');  // Enable transition on first click
    drawer.classList.add('open');
}
```

**Lesson Learned:** When user describes something "sliding" or "transitioning", search for CSS animations (`transition`, `transform`, `@keyframes`) before assuming it's a loading/caching issue. The word "slide" should trigger a search for `translateX` or `translateY`.

**Also Added (Preventive Measures):**
- Critical inline CSS in `base.html` and `account/base.html` for nav/logo sizing
- Strengthened cache headers in `NoCacheHTMLMiddleware`
- bfcache handler for pageshow event

---

## 10. Staticfiles Manifest Error in Tests

**Error:** `ValueError: Missing staticfiles manifest entry for 'icons/common/logo.svg'`

**Cause:** `CompressedManifestStaticFilesStorage` requires `collectstatic` to generate a manifest, but this doesn't exist in development/test environments.

**Solution (2026-01-16):** Added `TESTING` detection to `config/settings.py` that uses a simpler storage backend during tests:

```python
# At top of settings.py
import sys
TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test'

# In STORAGES configuration
if TESTING:
    STORAGES = {
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
    }
else:
    STORAGES = {
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
        "default": {
            "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage",
        },
    }
```

**Files Modified:** `config/settings.py`

---

## 11. Missing .env File in Git Worktrees

**Error:** `ImproperlyConfigured: Set the SECRET_KEY environment variable`

**Cause:** Git worktrees don't automatically copy untracked files like `.env` from the main repository.

**Solution (2026-01-16):** Added a `post-checkout` git hook that automatically copies `.env` to new worktrees:

**Location:** `.git/hooks/post-checkout` (in main repository)

```bash
#!/bin/bash
MAIN_REPO=$(git rev-parse --git-common-dir 2>/dev/null | xargs dirname)
CURRENT_DIR=$(pwd)

if [ -f "$MAIN_REPO/.env" ] && [ ! -f "$CURRENT_DIR/.env" ]; then
    cp "$MAIN_REPO/.env" "$CURRENT_DIR/.env"
    echo "Copied .env from main repository to worktree"
fi
```

**Note:** The hook is stored in the main repo's `.git/hooks/` directory, not in a worktree. New worktrees automatically use hooks from the shared git directory.
