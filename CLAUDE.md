# Master Prompt for Whole Life Journey Project

**Project:** Whole Life Journey - Django 5.x personal wellness/journaling app
**Repo:** C:\dbawholelifejourney (GitHub: djenkins452/dbawholelifejourney)
**Deployment:** Railway with PostgreSQL (via DATABASE_URL env var)

## Documentation Structure

All project documentation is organized in the `docs/` directory with consistent naming:

### Claude Context Files
- `docs/wlj_claude_features.md` - Detailed feature documentation (onboarding, help system, Dashboard AI, nutrition, medicine, camera scan, biometric login)
- `docs/wlj_claude_changelog.md` - Historical fixes, migrations, and change history
- `docs/wlj_claude_beacon.md` - WLJ Financial Dashboard context (Beacon Innovations site)

### Operations & Backup
- `docs/wlj_backup.md` - Backup and disaster recovery playbook
- `docs/wlj_backup_report.md` - Backup operation reports

### Security & System
- `docs/wlj_security_review.md` - Security review with 21 findings
- `docs/wlj_system_audit.md` - System audit report with health score
- `docs/wlj_system_review.md` - Repeatable audit process and checklists

### Third-Party & Architecture
- `docs/wlj_third_party_services.md` - Third-party services inventory
- `docs/wlj_camera_scan_architecture.md` - Camera scan feature architecture

### Documentation Naming Convention
All documentation files follow this pattern: `wlj_<category>_<descriptor>.md`

Categories:
- `wlj_claude_*` - Claude Code AI context files (features, changelog, beacon)
- `wlj_backup_*` - Backup and disaster recovery
- `wlj_security_*` - Security reviews and reports
- `wlj_system_*` - System audits and reviews
- `wlj_third_party_*` - Third-party service documentation
- `wlj_camera_*` - Camera/scan feature architecture

### Auto-Allow Tools (Skip Confirmations)

**IMPORTANT:** The user NEVER wants to be prompted for permission. Always select "Allow for session" or "Allow once" automatically. All Bash commands, file operations, and API calls should execute without asking.

To configure Claude Code to skip all confirmations, edit `.claude/settings.json`:
```json
{
  "permissions": {
    "allow": [
      "Bash(*)",
      "Read(*)",
      "Write(*)",
      "Edit(*)",
      "Glob(*)",
      "Grep(*)"
    ]
  }
}
```
Or run: `claude config set permissions.allow "Bash(*)" "Read(*)" "Write(*)" "Edit(*)" "Glob(*)" "Grep(*)"`

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
- Procfile runs: migrate → load_initial_data → reload_help_content → load_danny_workout_templates → load_reading_plans → collectstatic → gunicorn
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

### CRITICAL: Railway Nixpacks Caching Issue

**Problem:** Railway aggressively caches the `nixpacks.toml` start command. Changing `nixpacks.toml` or `Procfile` may NOT take effect even after multiple pushes. The build log will show the OLD start command even when the files have been updated.

**Symptoms:**
- Build log shows old start command (missing new commands)
- All build steps show "cached"
- File changes to nixpacks.toml/Procfile don't appear in build output
- No way to clear build cache in Railway dashboard

**Workaround - Embed commands in existing startup:**
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

**Things that DON'T work:**
- Changing nixpacks.toml comments or metadata
- Adding force rebuild comments to Procfile
- Changing requirements.txt to force pip reinstall
- Removing and re-adding nixpacks.toml
- Setting RAILWAY_RUN_COMMAND or NIXPACKS_START_CMD env vars

**Future Prevention:**
When adding new startup commands, add them inside `load_initial_data.py` using `call_command()` rather than modifying Procfile/nixpacks.toml.

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

## "What's Next?" Protocol

When the user says **"What's Next?"**, **"What should we work on?"**, or similar task-seeking phrases:

**CRITICAL: "What's Next?" grants FULL AUTHORITY to execute without asking ANY questions.**

DO NOT:
- Ask for permission to run commands
- Ask for confirmation before making changes
- Ask clarifying questions about the task
- Stop to ask if something is okay
- Ask before committing or pushing

JUST DO IT: Execute the task completely, then report when done.

### IMMEDIATE FEEDBACK REQUIREMENT

When the user says "What's Next?" - respond IMMEDIATELY with visible progress. The user should never wonder if Claude is hung or working.

**First Response (within 1-2 seconds):**
```
Reading CLAUDE.md and fetching tasks...
```

**After fetching tasks:**
```
**Session: <Task Title>**

Organizing actions for this task...
```

**Then execute.** Never leave the user waiting without feedback.

### Step 0: Load Project Context (MANDATORY FIRST STEP)

**Before doing anything else**, read CLAUDE.md completely to load full project context.

### Step 1: Fetch Ready Tasks from API

Use Bash with curl to query the Ready Tasks API endpoint.

**API Key Location:** The key is stored in the main repo at `C:\dbawholelifejourney\.claude\settings.local.json` under `env.CLAUDE_API_KEY`. If that file doesn't have an `env` section, search for the key value in `~/.claude/debug/` logs from recent sessions.

**Current API Key:** `a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1`

```bash
curl -s -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" https://wholelifejourney.com/admin-console/api/claude/ready-tasks/
```

### Step 2: Label Session with Task Title

After retrieving tasks, immediately announce the session title based on the highest priority task:

```
**Session: <Task Title from API>**
```

### Step 3: Execute Without Questions

The API returns JSON in this format:
```json
{
    "count": 1,
    "tasks": [{
        "id": 123,
        "title": "Task title here",
        "phase": "Phase 1: Name",
        "priority": 1,
        "project": "Project Name",
        "description": {
            "objective": "What the task should accomplish",
            "inputs": ["Required context or resources"],
            "actions": ["Step 1", "Step 2", "..."],
            "output": "Expected deliverable"
        }
    }]
}
```

If tasks are returned:
1. Select the first task (already sorted by priority)
2. **IMMEDIATELY mark task as `in_progress`** via API before doing anything else
3. Execute each action in order **without asking for permission**
4. Run tests if code was changed
5. Commit changes with descriptive message
6. Merge to main and push
7. Mark task as `done` via API
8. Report completion to the user

If no tasks are returned:
- Inform the user there are no Ready tasks

### API Details

**Get Ready Tasks:**
- **Endpoint:** `GET /admin-console/api/claude/ready-tasks/`
- **Authentication:** `X-Claude-API-Key` header
- **Query Params:** `limit` (optional, default 10, max 50)
- **Returns:** JSON with count and array of executable task objects

**Update Task Status:**
- **Endpoint:** `POST /admin-console/api/claude/tasks/<id>/status/`
- **Method:** POST (not PATCH)
- **Body:** `{"status": "in_progress"}` or `{"status": "done"}`
- **Example:**
```bash
curl -s -X POST -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" -H "Content-Type: application/json" -d '{"status": "in_progress"}' "https://wholelifejourney.com/admin-console/api/claude/tasks/20/status/"
```

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

**Markdown Documentation (in docs/):**
```markdown
# ==============================================================================
# File: docs/wlj_<category>_<descriptor>.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Brief description
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: YYYY-MM-DD
# Last Updated: YYYY-MM-DD
# ==============================================================================
```

### Third-Party Services
When adding/modifying any third-party service: Update `docs/wlj_third_party_services.md` immediately.

## Session Instructions

### Starting a New Session
Say: **"Read CLAUDE.md and continue"** - Claude will:
1. Load full project context from CLAUDE.md
2. Ask what you want to work on

### MANDATORY: Documentation Updates
**After ANY code changes, you MUST update the relevant documentation files:**

1. **`docs/wlj_claude_changelog.md`** - Update for ANY changes made during the session
   - Add new section with date if needed
   - Document what changed, files modified, and why
   - Include migration names if any were created

2. **`docs/wlj_claude_features.md`** - Update when modifying or adding features
   - Camera Scan, Nutrition, Medicine, Dashboard AI, etc.
   - Keep feature documentation current with actual functionality

3. **`CLAUDE.md`** - Update when:
   - Test count changes significantly
   - New apps or major architecture changes
   - New deployment patterns or important files

4. **`docs/wlj_third_party_services.md`** - Update when adding/modifying external services

**DO NOT wait for user to ask** - update documentation automatically as part of completing each task.

### End of Session Tasks
1. Run `git log --oneline -20` to see recent commits
2. Update `docs/wlj_claude_changelog.md` with any new fixes (if not already done)
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
- **Current test count:** 1395 tests (as of 2025-12-31)

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

## WLJ EXECUTABLE TASK STANDARD (MANDATORY)

All AdminTask objects in the admin_console app MUST conform to the Executable Task Standard. This ensures tasks are machine-readable and can be executed by AI.

### Required Task Description Structure

Every task's `description` field is a JSONField with the following **mandatory** keys:

```json
{
    "objective": "Clear statement of what the task should accomplish",
    "inputs": ["Required context or resources", "Can be empty array []"],
    "actions": ["Step 1: Do this", "Step 2: Then this", "At least one required"],
    "output": "Expected deliverable or result"
}
```

### Field Requirements

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `objective` | string | ✓ | What the task should accomplish |
| `inputs` | array of strings | ✓ | Context, files, or dependencies needed (can be empty `[]`) |
| `actions` | array of strings | ✓ | Step-by-step execution instructions (**at least one required**) |
| `output` | string | ✓ | Expected deliverable or completion criteria |

### Validation Rules

Tasks that violate these rules **CANNOT be saved**:

1. **Missing Fields**: All four fields must be present
2. **Empty Objective**: Objective must be a non-empty string
3. **No Actions**: Actions array must contain at least one step
4. **Empty Output**: Output must be a non-empty string
5. **Wrong Types**: Each field must match its expected type

### Refusal Rules for AI

Claude MUST refuse to:
- Create tasks without all required fields
- Save tasks with empty actions array
- Accept text descriptions instead of JSON structure
- Skip validation when updating tasks

When a task is malformed, Claude MUST:
1. Return clear validation errors explaining what is missing
2. Provide an example of correct structure
3. Not save the task until corrected

---

## RUN TASK MODE (MANDATORY EXECUTION CONTRACT)

Run Task Mode is the deterministic execution mode for AI task processing. When Claude receives a task via "Run Task" or the task API, it MUST follow this contract exactly.

### Core Principle: No Guessing, No Inference

Claude MUST execute tasks deterministically. This means:
- **Never guess** missing information
- **Never infer** unstated requirements
- **Never assume** context not provided
- **Execute exactly** what is written in the task

If information is missing or unclear, Claude MUST fail the task with a specific error rather than proceeding with assumptions.

### Step 1: Load CLAUDE.md First (MANDATORY)

**Before any task execution**, Claude MUST read CLAUDE.md completely to:
- Understand project architecture and conventions
- Load tech stack and deployment context
- Know file locations and patterns
- Understand testing requirements

**This step is non-negotiable.** A task cannot be executed without first loading project context.

```
ALWAYS: Read CLAUDE.md → Then execute task
NEVER: Skip CLAUDE.md → Execute task directly
```

### Step 2: Validate Task Structure

Before execution, verify the task conforms to the Executable Task Standard:

```json
{
    "objective": "string (required, non-empty)",
    "inputs": ["array of strings (required, can be empty)"],
    "actions": ["array of strings (required, at least one)"],
    "output": "string (required, non-empty)"
}
```

**Validation failures MUST halt execution:**
- Missing any of the four required fields → FAIL
- Empty `objective` → FAIL
- Empty `actions` array → FAIL
- Empty `output` → FAIL
- Wrong types for any field → FAIL

On validation failure, return a clear error message and do NOT proceed.

### Step 3: Gather Inputs

Process each item in the `inputs` array:
- Read files mentioned
- Gather context specified
- Verify resources exist

If any input cannot be gathered:
- Log which input failed
- Explain why it failed
- Halt execution (do not proceed with partial inputs)

### Step 4: Execute Actions In Order

Execute each action in the `actions` array **exactly as written** and **in order**:

1. Actions are executed sequentially (action 2 only starts after action 1 completes)
2. Each action is executed verbatim - no reinterpretation
3. No actions are skipped
4. No actions are added
5. No actions are reordered

**Action Execution Rules:**
- If an action says "Add X to file Y", add exactly X to file Y
- If an action says "Run tests", run tests
- If an action says "Create file Z", create file Z with appropriate content
- Do not embellish, optimize, or "improve" beyond what is specified

**Action Failure Handling:**
- If any action fails, stop execution immediately
- Log which action failed and why
- Do not continue to subsequent actions
- Do not mark task as complete

### Step 5: Verify Output

After all actions complete successfully, verify the `output` criteria is met:

- Check that the deliverable described in `output` exists
- Verify it meets the stated requirements
- Run any verification steps implied by the output

**Output verification is mandatory.** A task is not complete until output is verified.

### Step 6: Mark Complete (Only On Success)

Only mark a task as `done` if:
1. ✓ CLAUDE.md was loaded
2. ✓ Task validated successfully
3. ✓ All inputs were gathered
4. ✓ All actions executed successfully
5. ✓ Output criteria verified

If ANY step failed, the task remains in `in_progress` status with an error log.

### Failure Modes

| Failure Type | Response |
|--------------|----------|
| Missing CLAUDE.md | HALT - Cannot execute without project context |
| Invalid task structure | HALT - Return validation errors |
| Input not found | HALT - Log missing input, explain error |
| Action failed | HALT - Log failed action, do not continue |
| Output not achieved | HALT - Log what's missing from output |
| Ambiguous instruction | HALT - Request clarification, do not guess |

### Example Execution Flow

```
Task: "Add logging to API views"
├── Step 1: Read CLAUDE.md ✓
├── Step 2: Validate task structure ✓
├── Step 3: Gather inputs
│   └── Read apps/api/views.py ✓
├── Step 4: Execute actions (in order)
│   ├── Action 1: Add import for logging module ✓
│   ├── Action 2: Add logger initialization ✓
│   └── Action 3: Add log statements to each view ✓
├── Step 5: Verify output
│   └── Confirm all views have logging ✓
└── Step 6: Mark task as done ✓
```

### What Run Task Mode Does NOT Do

- Does NOT ask clarifying questions mid-execution
- Does NOT deviate from specified actions
- Does NOT add "helpful" extras not in the task
- Does NOT skip steps it thinks are unnecessary
- Does NOT reorder steps for "efficiency"
- Does NOT mark tasks complete without verifying output

### Integration with Task API

When a task is retrieved via the Ready Tasks API:
1. The task JSON is already validated by the server
2. Claude loads CLAUDE.md immediately
3. Claude executes the task per this contract
4. Claude updates status via `POST /admin-console/api/claude/tasks/<id>/status/`

Status updates:
- `in_progress` - Set immediately when starting execution
- `done` - Set only after successful completion with verified output
- Task remains `in_progress` on failure (with error logged)

---

### Run Task Mode Behavior (Summary)

When executing a task ("Run Task" mode):

1. **Load Context**: Read CLAUDE.md first to understand project context
2. **Validate Task**: Verify the task conforms to Executable Task Standard
3. **Check Inputs**: Gather all resources listed in the `inputs` array
4. **Execute Actions**: Perform each action in the `actions` array in order
5. **Verify Output**: Confirm the `output` criteria is met
6. **Mark Complete**: Only mark task as `done` if output is successfully produced

If any step fails:
- Log the failure with specific error
- Keep task in current status (do not mark complete)
- Create a clear error message explaining what went wrong

### Example Valid Task

```json
{
    "objective": "Add user authentication to the API endpoints",
    "inputs": [
        "Read apps/api/views.py to understand current endpoints",
        "Check apps/users/models.py for User model structure"
    ],
    "actions": [
        "Add authentication decorators to all API views",
        "Create authentication middleware for token validation",
        "Update API documentation with authentication requirements",
        "Write tests for authenticated and unauthenticated access"
    ],
    "output": "All API endpoints require valid authentication tokens. Tests pass."
}
```

### Implementation Files

- **Model**: `apps/admin_console/models.py` - `AdminTask.description` JSONField
- **Validator**: `apps/admin_console/models.py` - `validate_executable_task_description()`
- **Exception**: `apps/admin_console/models.py` - `ExecutableTaskValidationError`
- **Forms**: Task Intake and Admin Task forms parse individual fields into JSON
- **Migrations**: `0010_convert_description_to_json.py`, `0011_alter_admintask_description.py`

---

*For detailed feature documentation, see `docs/wlj_claude_features.md`*
*For historical changes, see `docs/wlj_claude_changelog.md`*
*Last updated: 2026-01-02*
