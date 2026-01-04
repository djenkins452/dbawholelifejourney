# ==============================================================================
# File: docs/wlj_claude_deploy.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Deployment rules, Railway configuration, and environment setup
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-04
# Last Updated: 2026-01-04
# ==============================================================================

# WLJ Deployment Guide

## Quick Reference

| Item | Value |
|------|-------|
| **Platform** | Railway |
| **Database** | PostgreSQL (via DATABASE_URL) |
| **Builder** | Nixpacks |
| **WSGI** | Gunicorn |
| **Main Repo** | C:\dbawholelifejourney |
| **GitHub** | djenkins452/dbawholelifejourney |

---

## Critical Rules

### 1. Always Push from Main Repo

**NEVER push from worktrees.** Always:
1. Merge worktree branch to main in the main repo
2. Push from `C:\dbawholelifejourney`

```bash
# From main repo
cd C:\dbawholelifejourney
git fetch origin worktree-branch
git merge origin/worktree-branch -m "Merge: descriptive message"
git push
```

### 2. No Shell Access on Railway

Railway has NO shell/console access. All fixes must be done via:
- Code changes
- Redeployment
- The `load_initial_data.py` workaround pattern

---

## Procfile Startup Chain

```
migrate → load_initial_data → reload_help_content → load_danny_workout_templates → load_reading_plans → collectstatic → gunicorn
```

**Important:**
- `postgres.railway.internal` hostname only available at runtime, NOT build time
- All DB operations must be in startCommand, not build/release phase

---

## One-Time Data Loading Pattern

Since Railway has NO shell access, one-time data loading must be done via Procfile:

1. **Create an idempotent management command** (uses `get_or_create`, checks for existing records)
2. **Add the command to Procfile** startup chain (after migrate, before collectstatic)
3. **The command runs on every deploy** but only creates data if it doesn't exist
4. **After confirmed working**, optionally remove from Procfile to save startup time

**Example:** `load_danny_workout_templates` - loads workout templates for a specific user, safe to run multiple times.

---

## CRITICAL: Railway Nixpacks Caching Issue

### Problem

Railway aggressively caches the `nixpacks.toml` start command. Changing `nixpacks.toml` or `Procfile` may NOT take effect even after multiple pushes.

### Symptoms

- Build log shows old start command (missing new commands)
- All build steps show "cached"
- File changes to nixpacks.toml/Procfile don't appear in build output
- No way to clear build cache in Railway dashboard

### Workaround - Embed Commands in Existing Startup

Instead of adding new commands to Procfile/nixpacks.toml, add them INSIDE an existing command that's already running:

```python
# In apps/core/management/commands/load_initial_data.py
# Add call_command() for new loaders inside this command:
try:
    self.stdout.write('  Loading project blueprints...')
    call_command(
        'load_project_from_json',
        'project_blueprints/wlj_executable_work_orchestration.json',
        verbosity=1
    )
    self.stdout.write(self.style.SUCCESS(' OK'))
except Exception as e:
    self.stdout.write(self.style.WARNING(f' Skipped ({e})'))
```

This bypasses the cache because the code inside `load_initial_data` is not cached - only the start command string is cached.

### Things That DON'T Work

- Changing nixpacks.toml comments or metadata
- Adding force rebuild comments to Procfile
- Changing requirements.txt to force pip reinstall
- Removing and re-adding nixpacks.toml
- Setting RAILWAY_RUN_COMMAND or NIXPACKS_START_CMD env vars

### Prevention

When adding new startup commands, add them inside `load_initial_data.py` using `call_command()` rather than modifying Procfile/nixpacks.toml.

---

## CRITICAL: Database Migration State Issues

### Problem

Django migrations can be recorded as "applied" in the `django_migrations` table even when the actual database schema change failed.

**How it happens:**
1. Migration runs, gets recorded as applied
2. Actual ALTER TABLE/CREATE fails (silently or with an error)
3. Next deploy skips the migration because Django thinks it's already applied
4. The column/table is missing but Django won't try to create it again

### Symptoms

- `FieldError: Cannot resolve keyword 'fieldname' into field`
- Database errors about missing columns
- Model queries fail even though migration shows as applied

### Solution - The `load_initial_data.py` Workaround Pattern

Since `load_initial_data.py` runs on EVERY deploy (not cached like migrations), add a schema fix function there:

```python
# In apps/core/management/commands/load_initial_data.py

def _fix_missing_column(self):
    """Fix missing column that migration failed to create."""
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            # IMPORTANT: Always include table_schema = 'public' for PostgreSQL!
            cursor.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'your_table_name'
                  AND column_name = 'missing_column'
            """)
            if cursor.fetchone() is None:
                self.stdout.write('  Adding missing column...')
                cursor.execute("""
                    ALTER TABLE your_table_name
                    ADD COLUMN missing_column varchar(10) NOT NULL DEFAULT 'value'
                """)
                self.stdout.write(self.style.SUCCESS(' FIXED!'))
```

### Key Points

1. **Always use `table_schema = 'public'`** in PostgreSQL queries - without it, the query may check the wrong schema and incorrectly report the column exists
2. **Add the fix to `load_initial_data.py`** - this runs on every deploy
3. **Also create a new migration** as a backup - the migration will run once, `load_initial_data` catches any edge cases
4. **Make fixes idempotent** - check if column exists before adding it

### Example - Budget Status Column Fix

```python
# In load_initial_data.py handle() method:
try:
    self.stdout.write('  Checking finance_budget.status...')
    self._fix_finance_budget_status()
except Exception as e:
    self.stdout.write(self.style.WARNING(f' Error: {e}'))
```

### Prevention Checklist for New Migrations

1. ✅ Create the migration normally
2. ✅ Add a fix function to `load_initial_data.py` as backup
3. ✅ Use `table_schema = 'public'` in all PostgreSQL schema checks
4. ✅ Test locally with PostgreSQL before deploying
5. ✅ Check Railway logs after deploy for migration errors

---

## Environment Variables

### Required for Production

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string (auto-set by Railway) |
| `SECRET_KEY` | Django secret key |
| `OPENAI_API_KEY` | OpenAI API for AI features |
| `CLAUDE_API_KEY` | API key for Claude Code task API |

### Optional Services

| Variable | Description |
|----------|-------------|
| `CLOUDINARY_*` | Image storage |
| `TWILIO_*` | SMS notifications |
| `EMAIL_HOST_*` | SMTP email |
| `DEXCOM_*` | CGM integration |
| `RECAPTCHA_V3_*` | Signup protection |

---

## Important Files

| File | Purpose |
|------|---------|
| `Procfile` | Railway deployment startup command |
| `nixpacks.toml` | Nixpacks build configuration |
| `apps/core/management/commands/load_initial_data.py` | System data loading, schema fixes |
| `requirements.txt` | Python dependencies |

---

## Deployment Checklist

Before deploying:
- [ ] Tests pass locally: `python manage.py test`
- [ ] No new migrations with potential issues
- [ ] If adding startup commands, add to `load_initial_data.py` not Procfile
- [ ] Push from main repo, not worktree

After deploying:
- [ ] Check Railway build logs for errors
- [ ] Check Railway runtime logs for migration/startup issues
- [ ] Verify the site loads: https://wholelifejourney.com
- [ ] Test any changed functionality

---

## Related Documentation

- `docs/wlj_claude_troubleshoot.md` - Known issues and solutions
- `docs/wlj_claude_changelog.md` - Historical fixes
- `docs/wlj_backup.md` - Backup and disaster recovery
- `CLAUDE.md` - Main project reference
