# ==============================================================================
# File: docs/wlj_claude_troubleshoot.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Known issues and solutions for common development problems
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-04
# Last Updated: 2026-01-04
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
- `CLAUDE.md` - Main project reference
