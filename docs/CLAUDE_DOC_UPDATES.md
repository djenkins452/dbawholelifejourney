# Documentation Update Procedures (Claude Code)

When adding **new features, pages, or significant enhancements**, update ALL of these:

## 1. What's New Release Notes

**File:** `apps/core/fixtures/release_notes.json`

- Add a new entry with next PK, user-friendly title and description
- Include `created_at`/`updated_at` timestamps (required by auto_now fields)
- Set `is_major: true` for big features, `false` for enhancements
- Add a one-time reset in `load_initial_data.py` so the fixture reloads on deploy

## 2. Teaching Destinations

**File:** `apps/help/fixtures/teaching_destinations.json`

- Add entries for any new pages/features users can navigate to
- Include relevant keywords for search matching
- Check for duplicate `destination_id` values before adding

Each destination entry includes:
- `destination_id`: Unique slug identifier
- `name`: Display name shown to users
- `path_description`: Navigation breadcrumb (e.g., "Health - Weight")
- `explanation`: Brief description of what users can do there
- `url`: Direct URL path to the destination
- `keywords`: Comma-separated search terms for intent matching
- `module`: App module name (health, journal, life, purpose, ai, etc.)
- `sort_order`: Display priority for suggestions

**API endpoints:**
- `GET /help/api/teaching/search/?q=<query>` - Search for destinations
- `GET /help/api/teaching/suggestions/` - Get popular destinations

## 3. Help Topics

**File:** `apps/help/fixtures/help_topics.json`

- Add/update help topics for any new `help_context_id` referenced in views
- Include comprehensive content covering what the feature does and how to use it

## 4. Fixture Loader Resets

**File:** `apps/core/management/commands/load_initial_data.py`

- If you modified any fixture that was already loaded in production, add a one-time reset method so it reloads on next deploy

## Skip Documentation Updates For

Bug fixes, CSS tweaks, refactors, test-only changes, and backend-only changes invisible to users.

## Production Data Loading

The user cannot run scripts in production manually. All data loading happens automatically on deploy.

**How it works:**
- The `Procfile` runs `python manage.py load_initial_data` on every deploy
- `load_initial_data` uses `DataLoadConfig` to track what's been loaded
- New fixtures/commands only run once (tracked by name in database)

**To add new fixtures or data:**
1. Create the fixture file in `apps/<app>/fixtures/<name>.json`
2. Register it in `apps/core/management/commands/load_initial_data.py` under `FIXTURE_LOADERS`
3. Commit and push to deploy - it loads automatically

**DO NOT** tell the user to run `loaddata` or any management command in production. Just push the code and it deploys automatically.
