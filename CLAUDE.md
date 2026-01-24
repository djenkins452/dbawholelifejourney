# Whole Life Journey - Claude Code Context

**Project:** Django 5.x personal wellness/journaling app
**Repo:** C:\dbawholelifejourney | GitHub: djenkins452/dbawholelifejourney

---

## ⚠️ BEHAVIOR RULES (FOLLOW IMMEDIATELY)

**Do NOT ask permission for:**
- Reading files, searching, grepping
- Running tests or migrations
- Making commits when task is complete
- Deploying (changelog → commit → merge → push)

**Still ask permission for:**
- Destructive operations (deleting files, dropping tables)
- Genuinely ambiguous or risky actions

**⚠️ IMPORTANT: Task Discussion Flow**
When fetching a new task from the improvement backlog:
1. **Present the task** - Show what's next and explore the codebase as needed
2. **Discuss scope** - Talk through the approach and implementation details with the user
3. **Wait for "go"** - Do NOT start implementation until the user explicitly says "go"
4. Only after "go" → proceed with implementation

**Communication style:**
- Be direct - skip "Would you like me to..."
- Execute (after "go"), don't propose
- If something fails, fix it and move on
- Summarize results, not intentions

---

## ⚠️ CRITICAL: ALWAYS DEPLOY AFTER CODE CHANGES

**After ANY code changes, you MUST:**
1. Update changelog (`docs/wlj_claude_changelog.md`)
2. Commit changes
3. Push worktree branch to GitHub
4. Merge to main and push to deploy (see "On Task Completion" section)

**A task is NOT complete until it is deployed to production.**

---

## Quick Reference

| Item | Value |
|------|-------|
| **API Key** | Set `WLJ_CLAUDE_API_KEY` in your `.env` file (see `.env.example`) |
| **Ready Tasks** | `GET /admin-console/api/claude/ready-tasks/?auto_start=true` |
| **Update Status** | `POST /admin-console/api/claude/tasks/<id>/status/` |
| **Test Count** | 1395 tests |
| **Push From** | Main repo (C:\dbawholelifejourney), NOT worktrees |

**Commands:**
```bash
# Fetch next task (marks as in_progress automatically)
curl -s -H "X-Claude-API-Key: $WLJ_CLAUDE_API_KEY" "https://wholelifejourney.com/admin-console/api/claude/ready-tasks/?limit=1&auto_start=true"

# Mark task done
curl -s -X POST -H "X-Claude-API-Key: $WLJ_CLAUDE_API_KEY" -H "Content-Type: application/json" -d '{"status": "done"}' "https://wholelifejourney.com/admin-console/api/claude/tasks/<ID>/status/"
```

## Testing & Migrations

**RESOLVED (2026-01-06):** `manage.py` commands now work. Ensure `.env` file exists with at minimum:
```
SECRET_KEY=dev-secret-key-for-local-testing-only
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

**Testing:**
```bash
# Test specific app module
python manage.py test apps.health.tests.test_fitness -v 1 --failfast

# Run all tests
python manage.py test -v 1

# Check for issues
python manage.py check
```

**Migrations:**
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate
```

---

## Tech Stack

- Django 5.x with django-allauth | PostgreSQL (prod) / SQLite (dev)
- Railway deployment with Nixpacks | Gunicorn WSGI
- OpenAI API for AI coaching features
- **iOS App:** Native Swift/SwiftUI wrapper with WKWebView + HealthKit

## Responsive Design (REQUIRED)

**This app is used on phones, tablets, and desktops.** All UI changes MUST be responsive.

**Breakpoints:**
- Mobile: `max-width: 480px`
- Tablet: `max-width: 768px`
- Desktop: `min-width: 769px`

**When writing CSS:**
1. Start with mobile-friendly defaults (reasonable padding, readable font sizes)
2. Add `@media` queries for tablet/desktop enhancements
3. Test that touch targets are at least 44x44px on mobile
4. Use `font-size: 16px` minimum on inputs (prevents iOS auto-zoom)
5. Avoid fixed widths - use `max-width`, `%`, or `vw` units

**Common mobile issues to avoid:**
- Horizontal scrolling (content wider than viewport)
- Text too small to read
- Buttons/links too close together
- Forms that don't fit on screen
- Modals/drawers that overflow

**Before completing UI tasks:** Mentally verify the layout works at 375px width (iPhone SE).

## Key Architecture

- **Apps:** users, core, dashboard, journal, faith, health, purpose, ai, life, admin_console, help, scan, **mobile**
- **User model:** Custom User (email-based auth) | UserPreferences for settings
- **Soft deletes:** Models use `soft_delete()` method, not hard deletes. See troubleshoot.md #7 for SoftDeleteManager pattern

---

## Reference Documentation

| Doc | Purpose |
|-----|---------|
| `.claude/commands/README.md` | **Slash commands** (`/next`, `/run-task`, `/troubleshoot`, `/log-change`) |
| `docs/wlj_claude_troubleshoot.md` | Known issues & solutions (CHECK FIRST) |
| `docs/wlj_claude_deploy.md` | Railway deployment, Nixpacks, migrations |
| `docs/wlj_claude_features.md` | Feature documentation (AI, scan, health) |
| `docs/wlj_claude_changelog.md` | Historical changes and fixes |
| `docs/wlj_third_party_services.md` | External service inventory |
| `docs/improvement_tasks.md` | **Improvement backlog** - prioritized feature tasks |
| `docs/task9_ai_assistant_search.md` | **Active:** AI Assistant search gateway design & sub-tasks |
| `docs/ios-wrapper-setup.md` | iOS app Xcode setup and running guide |
| `docs/ios-healthkit-integration.md` | HealthKit technical documentation |
| `docs/ios-app-store-submission.md` | Complete App Store submission guide |

## Slash Commands

| Command | Model | Purpose |
|---------|-------|---------|
| `/next` | Default | Fetch next ready task, mark in_progress |
| `/run-task` | Sonnet | Execute task with full context, auto-changelog |
| `/troubleshoot` | Haiku | Match error to known issues |
| `/log-change <desc>` | Haiku | Append entry to changelog |

---

## Executable Task Standard

All AdminTask `description` fields MUST be JSON with these keys:

```json
{
    "objective": "What the task should accomplish",
    "inputs": ["Required context (can be empty [])"],
    "actions": ["Step 1", "Step 2 (at least one required)"],
    "output": "Expected deliverable"
}
```

**Validation:** All 4 fields required. Empty objective/output/actions = FAIL.

---

## Run Task Mode Contract

When executing tasks from the API:
1. **Context:** CLAUDE.md is already loaded (don't re-read)
2. **Validate:** Task has objective, inputs, actions, output
3. **Execute:** Actions in order, exactly as written
4. **Verify:** Output criteria met
5. **Complete:** Mark `done` only on full success

**On failure:** HALT, log error, do NOT mark complete.

---

## When Something Isn't Working

**READ FIRST:** `docs/wlj_claude_troubleshoot.md`

Common issues: property shadowing fields, migration state, Nixpacks caching, test user onboarding, CSRF origins, PostgreSQL schema checks, **SoftDeleteManager filtering**.

---

## Teaching Tool Navigation Destinations

When adding new features or pages to the application, **review and update the Teaching Tool destinations** to ensure users can find the new functionality.

**Fixture file:** `apps/help/fixtures/teaching_destinations.json`

Each destination entry includes:
- `destination_id`: Unique slug identifier
- `name`: Display name shown to users
- `path_description`: Navigation breadcrumb (e.g., "Health - Weight")
- `explanation`: Brief description of what users can do there
- `url`: Direct URL path to the destination
- `keywords`: Comma-separated search terms for intent matching
- `module`: App module name (health, journal, life, purpose, ai, etc.)
- `sort_order`: Display priority for suggestions

**To add a new destination:**
1. Add an entry to `teaching_destinations.json`
2. Fixture loads automatically on deploy (see "Production Data Loading" section)

**API endpoints:**
- `GET /help/api/teaching/search/?q=<query>` - Search for destinations
- `GET /help/api/teaching/suggestions/` - Get popular destinations

---

## Production Data Loading

**IMPORTANT:** The user cannot run scripts in production manually. All data loading happens automatically on deploy.

**How it works:**
- The `Procfile` runs `python manage.py load_initial_data` on every deploy
- `load_initial_data` uses `DataLoadConfig` to track what's been loaded
- New fixtures/commands only run once (tracked by name in database)

**To add new fixtures or data:**
1. Create the fixture file in `apps/<app>/fixtures/<name>.json`
2. Register it in `apps/core/management/commands/load_initial_data.py` under `FIXTURE_LOADERS`
3. Commit and push to deploy - it loads automatically

**DO NOT** tell the user to run `loaddata` or any management command in production. Just push the code and it deploys automatically.

---

## On Task Completion

After ANY code changes:

1. Append to `docs/wlj_claude_changelog.md`:
   - Date, what changed, files modified, why
   - Include migration names if created

2. **Merge and Deploy:**
   - Go to main repo: `cd /Users/dannyjenkins/Projects/dbawholelifejourney`
   - Fetch worktree branch: `GIT_SSH_COMMAND="ssh -p 443" git fetch git@ssh.github.com:djenkins452/dbawholelifejourney.git <branch>:refs/remotes/origin/<branch>`
   - Checkout main and merge: `git checkout main && git merge origin/<branch> --no-edit`
   - Push to GitHub: `GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main`

**Note:** Use SSH on port 443 (`ssh -p 443` via `ssh.github.com`) as port 22 may timeout.

---

## "What's Next?" Protocol

Use `/next` slash command or say "What's Next?"

1. Output: `Fetching next task...`
2. Run curl with `auto_start=true`
3. Output: `**Session: <Task Title>**`
4. Show the task objective and actions
5. Output: `Run /run-task to execute.`

**DO NOT:** Read CLAUDE.md again, execute the task automatically.

---

## Bible Reading Plans Project

**Roadmap:** `docs/reading_plans_roadmap.md`

An ongoing project to create comprehensive Bible reading plans across multiple categories. Each plan includes:
- Three difficulty levels (Beginner, Intermediate, Advanced)
- Context summaries for each day
- Commentary appropriate to each level
- Reflection prompts

**Quality Standards:**
- Biblical accuracy (verified Scripture, no assumptions)
- Non-denominational, Bible-based content
- Appropriate complexity per difficulty level
- Pastor review before deployment

**To continue this project:**
1. Read `docs/reading_plans_roadmap.md` for current status
2. Implement the next plan marked as "Next Plan to Implement"
3. After deployment, update the roadmap status
4. Prompt user for confirmation before starting next plan

**Current Status:** Starting with "Jonah: The Reluctant Prophet" (Phase 1)

**Command pattern:** `apps/faith/management/commands/load_<plan>_plan.py`

---

## iOS App (Native Wrapper)

**Location:** `ios/WLJWrapper/`

Native iOS wrapper that loads WLJ in a WKWebView with HealthKit integration for App Store approval.

**Key Components:**
- `WLJWrapper.xcodeproj` - Xcode project (open to build/run)
- `WLJWrapper/Views/MainWebView.swift` - WKWebView with domain allowlist + JS bridge
- `WLJWrapper/Views/SettingsView.swift` - Native settings (required for App Store)
- `WLJWrapper/Views/HealthSyncView.swift` - HealthKit authorization + sync
- `WLJWrapper/Services/HealthKitManager.swift` - HealthKit queries (steps, weight, sleep, HR)
- `WLJWrapper/Services/KeychainManager.swift` - Secure token storage
- `WLJWrapper/Services/APIClient.swift` - HTTP client for mobile API

**Django Backend:** `apps/mobile/`
- Bearer token authentication (not session-based)
- Token exchange flow: web session → one-time code → API token
- Health data ingestion endpoint with audit logging
- Device registration and management

**Mobile API Endpoints:**
| Endpoint | Purpose |
|----------|---------|
| `POST /api/mobile/generate-code/` | Get one-time exchange code (from web session) |
| `POST /api/mobile/token/exchange/` | Exchange code for Bearer token |
| `POST /api/mobile/health/ingest/` | Submit HealthKit data |
| `GET /api/mobile/health/sync-status/` | Check last sync status |

**Token Authentication:**
```
Authorization: Bearer <token>
```
All mobile API endpoints require Bearer token auth (added via `MobileAuthenticationMiddleware`).

**HealthKit Data Synced:**
- Steps (daily totals) → `StepsEntry`
- Weight (most recent/day) → `WeightEntry`
- Sleep (sessions) → `SleepEntry`
- Heart rate (resting) → stored as note

**Testing iOS Locally:**
1. Open `ios/WLJWrapper/WLJWrapper.xcodeproj` in Xcode
2. Configure signing (your Apple Developer team)
3. Connect iPhone, enable Developer Mode
4. Build and run (Cmd+R)

**App Store Submission:**
See `docs/ios-app-store-submission.md` for complete guide including:
- Apple Developer Portal setup
- Privacy nutrition label answers
- HealthKit justification text
- WKWebView defense (why it's not "just a website")

---

*Last updated: 2026-01-24*
