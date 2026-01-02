# ==============================================================================
# File: docs/wlj_claude_changelog.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Historical record of fixes, migrations, and changes
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-28
# Last Updated: 2026-01-01 (Prayer Request Button Text Fix)
# ==============================================================================

# WLJ Change History

This file contains the historical record of all fixes, migrations, and significant changes.
For active development context, see `CLAUDE.md` (project root).

---

## 2026-01-01 Changes

### Remove "Your First" Button Text Across All Templates (UI FIX)

**Session:** Prayer Request Fix

**Problem:**
Multiple buttons and links throughout the app said things like "Add your first prayer request", "Log your first weight", "Create your first tag", etc. even when the user already had existing items. The text implied it was the user's first when it may not be.

**Solution:**
Changed all button/link text to remove "your first" phrasing, making them accurate regardless of whether the user has existing items.

**Files Modified (13 instances fixed):**
- `templates/faith/home.html`:
  - "Add your first prayer request" → "Add a prayer request"
  - "Write your first reflection" → "Write a reflection"
  - "Add your first milestone" → "Add a milestone"
- `templates/health/home.html`:
  - "Log your first weight" → "Log weight"
  - "Log your first reading" → "Log a reading" (heart rate)
  - "Log your first reading" → "Log a reading" (blood pressure)
  - "Log your first reading" → "Log a reading" (blood oxygen)
  - "Add your first medicine" → "Add a medicine"
  - "Log your first workout" → "Log a workout"
- `templates/health/fasting_list.html`:
  - "Start your first fast" → "Start a fast" (text and button)
- `templates/health/medicine/medicine_list.html`:
  - "adding your first medicine" → "adding a medicine"
- `templates/journal/tag_list.html`:
  - "Create your first tag" → "Create a tag" (text and button)
- `templates/journal/entry_form.html`:
  - "Create your first tag" → "Create a tag"
- `templates/admin_console/theme_list.html`:
  - "Create your first theme" → "Create a theme"

---

### Admin Project Tasks - Phase 17 Configurable Task Fields (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 17 Configurable Task Fields

**Description:**
Made task intake fields fully configurable via admin-defined database tables instead of hardcoded enums. Admins can now create, edit, and manage task field options (status, priority, category, effort) through the admin console.

**New Models:**
- `AdminTaskStatusConfig` - Configurable status options (backlog, ready, in_progress, blocked, done)
  - Fields: name, display_name, execution_allowed, terminal, order, active
- `AdminTaskPriorityConfig` - Configurable priority levels (1-5)
  - Fields: value (integer), label, order, active
- `AdminTaskCategoryConfig` - Configurable categories (feature, bug, infra, content, business)
  - Fields: name, display_name, order, active
- `AdminTaskEffortConfig` - Configurable effort levels (S, M, L)
  - Fields: value, label, order, active

**AdminTask Model Changes:**
- Added ForeignKey fields: `status_config`, `priority_config`, `category_config`, `effort_config`
- Legacy fields retained for backward compatibility during migration
- Helper methods: `get_status_display_value()`, `get_priority_display_value()`, etc.

**New Routes (Admin Config Management):**
- `GET /admin-console/projects/config/` - Config dashboard
- Status: `/config/status/`, `/config/status/new/`, `/config/status/<pk>/edit/`, `/config/status/<pk>/delete/`
- Priority: `/config/priority/`, `/config/priority/new/`, `/config/priority/<pk>/edit/`, `/config/priority/<pk>/delete/`
- Category: `/config/category/`, `/config/category/new/`, `/config/category/<pk>/edit/`, `/config/category/<pk>/delete/`
- Effort: `/config/effort/`, `/config/effort/new/`, `/config/effort/<pk>/edit/`, `/config/effort/<pk>/delete/`

**Task Intake Form Updates:**
- Dropdowns now populated from active config tables
- Only active config values appear in dropdowns
- Form creates tasks with both config ForeignKeys and legacy field values for backward compatibility

**Safety Rules (Deletion Protection):**
- Config items in use by tasks cannot be deleted (raises `DeletionProtectedError`)
- Inactive config items cannot be assigned to new tasks
- All existing tasks linked to config records via data migration

**Migrations:**
- `0008_phase17_configurable_task_fields.py` - Creates config models, adds FK fields to AdminTask
- `0009_populate_task_configs.py` - Data migration to populate config tables and link existing tasks

**Modified Files:**
- `apps/admin_console/models.py` - Added 4 config models, updated AdminTask
- `apps/admin_console/views.py` - Added TaskConfigDashboardView and CRUD views for all config types
- `apps/admin_console/urls.py` - Added 17 new URL patterns for config management
- `templates/admin_console/task_intake.html` - Updated to use config dropdowns
- `templates/admin_console/config/` - New directory with 13 templates:
  - `config_dashboard.html`,
  - `status_list.html`, `status_form.html`, `status_confirm_delete.html`
  - `priority_list.html`, `priority_form.html`, `priority_confirm_delete.html`
  - `category_list.html`, `category_form.html`, `category_confirm_delete.html`
  - `effort_list.html`, `effort_form.html`, `effort_confirm_delete.html`

**Tests:** All 178 admin_console tests pass.

---

### Admin Project Tasks - Phase 16 Projects Introduction (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 16 Projects Introduction

**Description:**
Introduced Projects as a first-class object to organize admin tasks. Each task must now belong to a project. Projects can be marked as complete when all their tasks are done.

**New Model:**
- `AdminProject` - Groups related tasks together
  - Fields: id, name, description, status (open/complete), created_at, updated_at
  - Status: 'open' or 'complete'
  - Deletion protection: Cannot delete a project that has tasks

**New Routes:**
- `GET /admin-console/projects/` - Project list page
- `GET /admin-console/projects/<id>/` - Project detail page

**AdminTask Changes:**
- Added required `project` ForeignKey to AdminProject
- All existing tasks assigned to default "General" project via migration
- Task transitions to 'done' now check if project should be completed

**Project Completion Logic:**
- `check_and_complete_project(project)` - Checks if all tasks are done and marks project complete
- `on_task_done_check_project(task)` - Called when task transitions to 'done'
- Creates AdminActivityLog entry when project is completed

**Safety Rules:**
- Project must exist for every task (enforced at DB level)
- Tasks cannot exist without a project
- Deleting projects with tasks raises `DeletionProtectedError`
- No data loss during migration (existing tasks get "General" project)

**Modified Files:**
- `apps/admin_console/models.py` - Added AdminProject model, project FK to AdminTask
- `apps/admin_console/services.py` - Added project completion functions
- `apps/admin_console/views.py` - Added AdminProjectListView, AdminProjectDetailView
- `apps/admin_console/urls.py` - Added project routes
- `apps/admin_console/migrations/0007_add_admin_project.py` - Migration for AdminProject
- `templates/admin_console/admin_project_list.html` - Project list template
- `templates/admin_console/admin_project_detail.html` - Project detail template
- `apps/admin_console/tests/test_admin_console.py` - Updated tests with project field

---

### Admin Project Tasks - Phase 15 Operator Runbook (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 15 Operator Runbook (Contextual Help)

**Description:**
Added an Operator Runbook that appears as contextual help when the user is working in Projects. The runbook is a read-only reference document that explains how to operate the Projects system.

**New Route:**
- `GET /admin-console/projects/help/` - Projects Operator Runbook page

**Contextual Help Integration:**
- When user is on any Projects page (`/admin-console/projects/*`), the Help modal shows a "Projects Operator Runbook" button
- When user is outside Projects, the button is hidden
- Context-awareness implemented via JavaScript URL path detection

**Runbook Content (5 Sections):**
1. **What the Projects System Is** - Purpose of Projects, Phases, and Tasks; why tasks must be entered intentionally
2. **Daily Operating Workflow** - 6-step workflow from Task Intake to reviewing execution results
3. **Task Status Meanings** - Definitions for backlog, ready, in_progress, blocked, done
4. **When Execution Stops** - Explains 4 stop conditions and their resolutions
5. **Golden Rules** - 5 operating principles (database is truth, Claude never invents work, one task at a time, humans control readiness, safety stops are expected)

**Safety Rules:**
- Admin-only access (returns 403 for non-staff users via AdminRequiredMixin)
- Read-only content (no forms, no data modification)
- Does not log activity
- Does not auto-open

**Modified Files:**
- `apps/admin_console/urls.py` - Added projects_runbook route
- `apps/admin_console/views.py` - Added ProjectsRunbookView
- `templates/admin_console/projects_runbook.html` - New runbook template
- `templates/components/help_modal.html` - Added contextual links section with Projects Runbook
- `static/css/help.css` - Added styles for contextual links

---

### Admin Project Tasks - Phase 13 Inline Editing & Priority (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 13 Inline Editing & Priority

**Description:**
Improved admin productivity by allowing quick inline task updates directly from the Task List page. Adds inline dropdowns for status and priority changes that save immediately without needing to navigate to edit pages.

**New API Endpoints:**
- `PATCH /admin-console/api/projects/tasks/<id>/inline-status/` - Inline status updates
- `PATCH /admin-console/api/projects/tasks/<id>/inline-priority/` - Inline priority updates

**Inline Status Edit:**
- Allows changing status via dropdown directly in the Task List
- Only allows transitions between `backlog` and `ready`
- Does NOT allow setting `in_progress`, `blocked`, or `done` via inline edit
- Tasks in other statuses show read-only badge (not dropdown)
- Changes save immediately on selection
- Creates activity log entry for each change

**Inline Priority Edit:**
- Allows changing priority (1-5) via dropdown directly in the Task List
- Works on tasks in any status
- Changes save immediately on selection
- Creates activity log entry for each change
- Priority dropdown shows color-coded styling matching priority level

**Ordering Helpers:**
- Default ordering: priority ASC, created_at ASC (most urgent first)
- Displayed in page subtitle

**Quick Filters:**
- Added quick filter buttons below main filter bar
- "Ready Only" - Shows only tasks with status=ready
- "Backlog Only" - Shows only tasks with status=backlog
- Active filter is highlighted

**Safety Rules:**
- Admin-only (returns 403 for non-staff users)
- No background jobs
- No execution hooks
- No auto-advancement of phases or status

**Modified Files:**
- `apps/admin_console/views.py` - Added InlineStatusUpdateAPIView, InlinePriorityUpdateAPIView
- `apps/admin_console/urls.py` - Added 2 new API routes
- `templates/admin_console/admin_task_list.html` - Added inline dropdowns, quick filters, updated JS/CSS
- `apps/admin_console/tests/test_admin_console.py` - Added 19 new tests for inline editing

**Test Count:** 19 new tests (InlineStatusUpdateAPITest: 9, InlinePriorityUpdateAPITest: 10)

---

### Admin Project Tasks - Phase 12 Task Intake & Controls (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 12 Task Intake & Controls

**Description:**
Added a clean, intentional admin-console interface for human task management. This phase provides admin-only pages for creating and managing project tasks without any automation or execution logic.

**New Routes:**
- `GET/POST /admin-console/projects/intake/` - Task Intake page
- `GET /admin-console/projects/tasks/` - Task List page (enhanced with filtering)
- `POST /api/projects/tasks/<id>/mark-ready/` - Mark Ready toggle API

**Task Intake Page:**
New `TaskIntakeView` provides a form for admins to create tasks:
- Required fields: title, description, phase
- Priority: 1-5 (default 3)
- Status: backlog or ready (default backlog)
- Optional: category, effort
- created_by is ALWAYS set to "human" (enforced server-side)
- Validates phase is selected (cannot create task without phase)
- Redirects to task list after successful creation

**Task List Page:**
Enhanced `AdminTaskListView` with:
- Display columns: title, phase number, status, priority, created_by, created_at
- Order by: priority ASC, created_at ASC
- Filterable by: phase, status
- Read-only list with Mark Ready controls
- Shows truncated task descriptions

**Human Controls:**
1. "Mark Ready" toggle button on backlog tasks
   - Requires explicit click
   - Changes status from backlog to ready
   - Logs activity as created_by="human"
   - No bulk actions (one task at a time)

2. Soft guardrail warning
   - Displays warning when 5+ tasks are marked "ready"
   - Shows on both Task Intake and Task List pages
   - Does NOT block saving (warning only)
   - Updates dynamically when using Mark Ready toggle

**Navigation:**
Added "Projects" section to admin console dashboard with links to:
- Task Intake
- Task List
- Project Status (existing)

**Safety Rules:**
- Non-admin users receive 403 Forbidden
- Cannot create task without selecting a phase
- Cannot auto-assign tasks to future phases
- No execution logic triggered from UI
- No Phase 11 integration from this interface

**Modified Files:**
- `apps/admin_console/urls.py` - Added 2 new routes
- `apps/admin_console/views.py` - Added TaskIntakeView, MarkReadyAPIView, enhanced AdminTaskListView
- `templates/admin_console/task_intake.html` - New template
- `templates/admin_console/admin_task_list.html` - Enhanced with filtering and Mark Ready controls
- `templates/admin_console/dashboard.html` - Added Projects section

**Tests:** All 156 admin_console tests pass.

---

### Admin Project Tasks - Phase 11.1 Preflight Guard & Phase Seeding (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 11.1 Preflight Guard & Phase Seeding

**Description:**
Added preflight execution guard and safe phase seeding for production. Ensures Phase 11 execution can only run when valid phase and task data exists.

**Preflight Guard:**
New `preflight_execution_check()` function verifies:
1. At least one AdminProjectPhase exists
2. Exactly one phase has status = "in_progress"
3. At least one AdminTask exists for the active phase

Returns structured `PreflightResult` with success flag and error messages:
- Does NOT raise exceptions
- Does NOT modify data
- Returns clear error messages for each check failure

**Phase Seeding:**
New `seed_admin_project_phases(created_by)` service function:
- If AdminProjectPhase table is empty: Creates phases 1-11
- Phase 1 set to "in_progress", all others to "not_started"
- Uses minimal names ("Phase 1", "Phase 2", etc.)
- Idempotent: safe to run multiple times
- Logs AdminActivityLog entry when seeding occurs (if tasks exist)

New management command `seed_admin_project_phases`:
- Suitable for production use
- Added to Procfile for Railway deployment

**New API Endpoints:**
- `GET /api/admin/project/preflight/` - Run preflight execution check (read-only)
- `POST /api/admin/project/seed-phases/` - Seed phases 1-11 if empty

**Safety Rules:**
- Never seeds AdminTask data (only phases)
- Never overwrites or resets existing phase data
- Never assumes development environment
- Preflight is mandatory before Phase 11 execution

**Modified Files:**
- `apps/admin_console/services.py` - Added PreflightResult, preflight_execution_check, seed_admin_project_phases
- `apps/admin_console/views.py` - Added PreflightCheckAPIView, SeedPhasesAPIView
- `apps/admin_console/api_urls.py` - Added 2 new API routes
- `apps/admin_console/management/commands/seed_admin_project_phases.py` - New management command
- `apps/admin_console/tests/test_admin_console.py` - Added 20+ tests for new functionality

**Tests:** All 130 admin_console tests pass.

---

### Admin Project Tasks - Phase 10 Hardening & Fail-Safes (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 10 Hardening & Fail-Safes

**Description:**
Added minimal safeguards so the project system cannot get stuck or corrupted. This phase adds detection of stuck states, admin override actions, and guardrails to prevent data corruption.

**Stuck State Detection:**
New `detect_system_issues()` function detects:
- A) No active phase exists (critical)
- B) More than one phase is marked "in_progress" (critical)
- C) A phase is "in_progress" but has zero tasks AND no next phase unlocked (warning)
- D) A task is "in_progress" longer than 24 hours (warning)

**Admin Override Actions:**
Three new service functions for admin-only recovery actions:
1. `reset_active_phase(phase_id, created_by)` - Force exactly one phase to in_progress
2. `force_unblock_task(task_id, reason, created_by)` - Move task from blocked to ready (requires reason)
3. `recheck_phase_completion(phase_id, created_by)` - Re-run phase completion check safely

**New API Endpoints:**
- `GET /api/admin/project/system-issues/` - Detect system issues (read-only)
- `POST /api/admin/project/override/reset-phase/` - Reset active phase
- `POST /api/admin/project/override/unblock-task/` - Force-unblock a task (requires reason)
- `POST /api/admin/project/override/recheck-phase/` - Re-run phase completion check

**Guardrails:**
1. `DeletionProtectedError` exception for protected resources
2. `AdminProjectPhase.delete()` prevents deletion if tasks exist for the phase
3. `AdminTask.delete()` prevents deletion if activity logs exist for the task
4. Invalid status transitions rejected with 400 error (existing behavior, now enforced in API)

**Activity Logging:**
All override/recovery actions are logged with `[ADMIN OVERRIDE]` prefix:
- Phase reset: "[ADMIN OVERRIDE] Active phase reset to Phase X..."
- Task unblock: "[ADMIN OVERRIDE] Task force-unblocked from 'blocked' to 'ready'..."
- Phase recheck: "[ADMIN OVERRIDE] Phase completion recheck initiated..."

**Modified Files:**
- `apps/admin_console/models.py` - Added DeletionProtectedError, delete() guardrails
- `apps/admin_console/services.py` - Added detect_system_issues, reset/unblock/recheck functions
- `apps/admin_console/views.py` - Added 4 new API views, updated delete views
- `apps/admin_console/api_urls.py` - Added 4 new API routes

**Tests:** All 129 admin_console tests pass.

---

### Admin Project Tasks - Phase 8 Phase Auto-Unlock (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 8 Phase Auto-Unlock

**Description:**
Added minimal logic so phases automatically complete and unlock based on task status. When all tasks in a phase are marked as done, the phase is marked complete and the next phase is automatically unlocked.

**Phase Completion Rule:**
A phase is considered COMPLETE when:
- All AdminTask records for that phase have status = "done"
- OR no tasks exist for that phase
- Blocked tasks do NOT count as complete (phase won't complete with blocked tasks)

**New Service Functions (in `services.py`):**
1. `is_phase_complete(phase)` - Check if a phase meets completion criteria
2. `get_next_phase(phase)` - Get the next phase by ascending phase_number
3. `unlock_next_phase(completed_phase, created_by)` - Unlock the next phase
4. `check_and_complete_phase(phase, created_by)` - Main function that checks and completes phase
5. `on_task_done(task, created_by)` - Handler called when task transitions to done

**Integration Point:**
- Phase completion logic is called ONLY when a task status transitions to "done"
- Integrated into `AdminTask.transition_status()` method
- Does NOT run on reads or page loads

**Safety Rules:**
- Never auto-complete a phase with blocked tasks
- Never skip phase numbers
- Never unlock future phases early (only unlocks immediate next phase)
- If no next phase exists, stops quietly

**Activity Logging:**
- Phase completion: "Phase X ('Name') completed. All tasks in phase are done."
- Phase unlock: "Phase X ('Name') unlocked. Previous phase Y ('Name') completed."

**Modified Files:**
- `apps/admin_console/models.py` - Added on_task_done call in transition_status method
- `apps/admin_console/services.py` - Added 5 new service functions for phase auto-unlock
- `apps/admin_console/tests/test_admin_console.py` - Added 25 new tests

**Tests:** 25 new tests for Phase 8 functionality:
- IsPhaseCompleteTests (6 tests): no tasks, all done, various incomplete states
- GetNextPhaseTests (3 tests): next phase, last phase, non-consecutive numbers
- UnlockNextPhaseTests (4 tests): sets status, no next, already started, activity log
- CheckAndCompletePhaseTests (5 tests): completion, blocked tasks, unlock next, already complete, activity log
- OnTaskDoneTests (2 tests): triggers check, does not complete with remaining
- TransitionStatusPhaseAutoUnlockTests (5 tests): full workflow, blocked prevention, multiple phases

---

### Admin Project Tasks - Phase 5 Blocker Task Creation (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 5 Blocker Task Creation

**Description:**
Added minimal logic to capture blockers as tasks instead of stopping progress. When a task encounters a blocker (missing config, required credentials, manual setup needed, or business decision required), a blocker task is created and the original task is marked as blocked.

**Blocker Definition:**
A blocker exists ONLY when one or more of the following is true:
- Required configuration or environment variable is missing
- An external account, credential, or API key is required
- A manual setup step must be completed by a human
- A business rule or decision is required to proceed

**Model Changes:**
- Added `blocking_task` ForeignKey field to AdminTask model
  - Self-referential relationship (`'self'`)
  - `on_delete=SET_NULL` (blocked task persists if blocker is deleted)
  - `null=True, blank=True` (optional field)
  - `related_name='blocks'` for reverse lookup (blocker.blocks returns all blocked tasks)

**New Service Functions (in `services.py`):**
1. `create_blocker_task(blocked_task, title, description, category, effort, created_by)`
   - Creates a new AdminTask with category='infra' or 'business'
   - Sets priority equal to or higher than the blocked task
   - Creates status='ready' blocker task
   - Updates original task to status='blocked' with blocking_task reference
   - Creates AdminActivityLog entries for BOTH tasks
   - Returns tuple: (blocker_task, blocked_task, blocker_log, blocked_log)

2. `get_blocked_tasks(phase=None)` - Query all tasks with status='blocked'
3. `get_blocker_tasks(phase=None)` - Query all tasks that are blocking other tasks
4. `is_valid_blocker_reason(reason)` - Validate blocker reason

**Blocker Task Requirements:**
- **title:** Short, action-oriented description
- **description:** Must include what was being worked on, what caused the block, what is required to unblock
- **category:** 'infra' or 'business' only (not feature, bug, or content)
- **priority:** Equal to or higher than blocked task
- **status:** 'ready' (so it appears in next tasks)
- **effort:** 'S' or 'M' only
- **created_by:** 'claude' or 'human'
- **phase:** Same phase as blocked task

**Activity Logging:**
Both the blocker task and blocked task get AdminActivityLog entries:
1. Blocker task log: "Blocker task created. Blocking task: '[title]' (ID: X). Reason: [description]"
2. Blocked task log: "Task blocked. Blocker task created: '[title]' (ID: X). Reason: [description]"

**New Files:**
- `apps/admin_console/migrations/0006_add_blocking_task.py` - Migration for blocking_task field

**Modified Files:**
- `apps/admin_console/models.py` - Added blocking_task ForeignKey field
- `apps/admin_console/services.py` - Added blocker task creation and query functions
- `apps/admin_console/tests/test_admin_console.py` - Added 17 new tests

**Tests:** 17 new tests for Phase 5 functionality:
- BlockerTaskCreationTest (9 tests): creation, priority, task updates, activity logs, validation
- BlockerTaskQueryTests (4 tests): get_blocked_tasks, get_blocker_tasks with filters
- BlockerModelFieldTests (4 tests): nullable, settable, SET_NULL on delete, reverse relationship

---

### Admin Project Tasks - Phase 4 Task Execution (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 4 Task Execution

**Description:**
Added minimal logic to allow controlled task execution using status updates only. This includes status transition validation, validation rules for phase awareness and blocked reasons, and an admin-only API endpoint for updating task status.

**Status Transition Rules:**
- `backlog` → `ready`
- `ready` → `in_progress`
- `in_progress` → `done` | `blocked`
- `blocked` → `ready`
- `done` → (terminal, no transitions allowed)

**Validation Rules:**
1. A task can only move to `in_progress` if it belongs to the active phase (phase.status = 'in_progress')
2. A task cannot move to `done` unless it was `in_progress`
3. A blocked task must include a reason

**New API Endpoint:**
- `PATCH /api/admin/project/tasks/<id>/status/` - Update task status
  - Admin-only (returns 403 for non-staff users)
  - Request body: `{"status": "in_progress", "reason": "optional, required for blocked"}`
  - Returns: Updated task JSON with activity log entry
  - Error responses: 400 (validation error), 403 (not admin), 404 (task not found)

**Activity Logging:**
Every status change creates an AdminActivityLog entry with:
- Task reference
- Previous status → New status
- Reason (if provided)
- created_by (human or claude)

**Model Changes:**
- Added `TaskStatusTransitionError` exception class
- Added `ALLOWED_TRANSITIONS` constant mapping valid transitions
- Added `blocked_reason` field to AdminTask model
- Added `is_valid_transition()` class method
- Added `validate_status_transition()` instance method
- Added `transition_status()` instance method with validation and logging

**New Files:**
- `apps/admin_console/migrations/0005_add_blocked_reason.py` - Migration for blocked_reason field

**Modified Files:**
- `apps/admin_console/models.py` - Added transition validation, blocked_reason field, logging
- `apps/admin_console/views.py` - Added TaskStatusUpdateAPIView, ActivePhaseAPIView
- `apps/admin_console/urls.py` - Added task status API route
- `apps/admin_console/tests/test_admin_console.py` - Added 31 new tests

**Tests:** 31 tests for Phase 4 functionality (TaskStatusTransitionModelTest + TaskStatusUpdateAPITest), all passing.

---

### Admin Project Tasks - Phase 3 Task Selection (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 3 Task Selection

**Description:**
Added minimal logic to list the next tasks for the active project phase. This includes a helper function and an admin-only API endpoint.

**New Features:**

1. **get_next_tasks(limit=5) Helper Function**
   - Reads the active phase (status='in_progress')
   - Queries AdminTask where phase=active and status IN ('ready', 'backlog')
   - Orders by priority ASC, then created_at ASC
   - Returns up to `limit` tasks

2. **GET /api/admin/project/next-tasks/ API Endpoint**
   - Admin-only (returns 403 for non-staff users)
   - Query params: `limit` (optional, default 5)
   - Returns JSON array of task objects with: id, title, priority, status, phase_number
   - Returns empty list if no active phase or no matching tasks

**Safety Rules Implemented:**
- Does NOT return tasks from future phases (only from active phase)
- Does NOT return tasks with status='done'
- Returns empty list when no tasks exist

**New Files:**
- `apps/admin_console/services.py` - Service functions (get_active_phase, get_next_tasks)
- `apps/admin_console/api_urls.py` - API URL routes

**Modified Files:**
- `apps/admin_console/views.py` - Added NextTasksAPIView
- `config/urls.py` - Added /api/admin/project/ route
- `apps/admin_console/tests/test_admin_console.py` - Added 11 tests for NextTasksAPITest

**Tests:** 11 new tests for NextTasksAPITest, all passing.

---

### Admin Project Tasks - Phase 1 Infrastructure (NEW FEATURE)

**Session:** WLJ Admin Tasks - Phase 1 Infrastructure

**Description:**
Created a simple admin-only project task system for internal project management. This is infrastructure only - no automation, AI, or business rules.

**New Models:**

1. **AdminProjectPhase**
   - `phase_number` (IntegerField, unique)
   - `name` (CharField, max_length=100)
   - `objective` (TextField)
   - `status` (CharField, choices: not_started, in_progress, complete)
   - `created_at`, `updated_at` (auto timestamps)

2. **AdminTask**
   - `title` (CharField, max_length=200)
   - `description` (TextField)
   - `category` (CharField, choices: feature, bug, infra, content, business)
   - `priority` (IntegerField, default=3)
   - `status` (CharField, choices: backlog, ready, in_progress, blocked, done)
   - `effort` (CharField, choices: S, M, L)
   - `phase` (ForeignKey to AdminProjectPhase)
   - `created_by` (CharField, choices: human, claude)
   - `created_at`, `updated_at` (auto timestamps)

3. **AdminActivityLog**
   - `task` (ForeignKey to AdminTask)
   - `action` (TextField)
   - `created_by` (CharField, choices: human, claude)
   - `created_at` (auto timestamp)

**New URL Patterns:**
- `/admin-console/projects/phases/` - Phase list
- `/admin-console/projects/phases/new/` - Create phase
- `/admin-console/projects/phases/<pk>/edit/` - Edit phase
- `/admin-console/projects/phases/<pk>/delete/` - Delete phase
- `/admin-console/projects/tasks/` - Task list
- `/admin-console/projects/tasks/new/` - Create task
- `/admin-console/projects/tasks/<pk>/edit/` - Edit task
- `/admin-console/projects/tasks/<pk>/delete/` - Delete task
- `/admin-console/projects/activity/` - Activity log list
- `/admin-console/projects/activity/new/` - Create log
- `/admin-console/projects/activity/<pk>/edit/` - Edit log
- `/admin-console/projects/activity/<pk>/delete/` - Delete log

**New Files:**
- `apps/admin_console/migrations/0004_admin_project_tasks.py`
- `apps/admin_console/management/commands/load_phase1_data.py`
- `templates/admin_console/project_phase_list.html`
- `templates/admin_console/project_phase_form.html`
- `templates/admin_console/project_phase_confirm_delete.html`
- `templates/admin_console/admin_task_list.html`
- `templates/admin_console/admin_task_form.html`
- `templates/admin_console/admin_task_confirm_delete.html`
- `templates/admin_console/activity_log_list.html`
- `templates/admin_console/activity_log_form.html`
- `templates/admin_console/activity_log_confirm_delete.html`

**Modified Files:**
- `apps/admin_console/models.py` - Added 3 new models
- `apps/admin_console/views.py` - Added 12 new views
- `apps/admin_console/urls.py` - Added 12 new URL patterns
- `Procfile` - Added `load_phase1_data` command

**Seed Data Created:**
- Phase 1: "Core Project Infrastructure" (status: in_progress)

**Tests:** All admin_console tests pass.

---

### Project Manager App Removal (CLEANUP)

**Session:** Update Project Manager App

**Description:**
Removed the ClaudeTask project management feature due to persistent Railway deployment issues preventing the task loading commands from running. The feature was causing confusion and wasn't functioning as expected on Railway due to Nixpacks caching problems.

**Components Removed:**

1. **ClaudeTask Model**
   - Deleted the entire ClaudeTask model from `apps/admin_console/models.py`
   - Created migration `0003_delete_claudetask.py` to drop the database table

2. **Admin Registration**
   - Removed ClaudeTaskAdmin from `apps/admin_console/admin.py`

3. **Management Commands**
   - Deleted `apps/admin_console/management/commands/task_status.py`
   - Deleted `apps/admin_console/management/commands/load_bible_app_task.py`

4. **Deployment Configuration**
   - Removed `load_bible_app_task` from Procfile startup chain
   - Removed `load_bible_app_task` from nixpacks.toml start command

5. **Documentation**
   - Removed all PM/ClaudeTask references from CLAUDE.md
   - Deleted `docs/wlj_claude_tasks.md`
   - Removed "Claude as Project Manager" workflow documentation

**Files Deleted:**
- `apps/admin_console/management/commands/task_status.py`
- `apps/admin_console/management/commands/load_bible_app_task.py`
- `docs/wlj_claude_tasks.md`

**Files Modified:**
- `apps/admin_console/models.py` - Cleared (no models)
- `apps/admin_console/admin.py` - Cleared (no registrations)
- `CLAUDE.md` - Removed all PM references
- `Procfile` - Removed load_bible_app_task
- `nixpacks.toml` - Removed load_bible_app_task

**Migration Created:**
- `apps/admin_console/migrations/0003_delete_claudetask.py`

**Reason for Removal:**
Railway's Nixpacks builder was aggressively caching the old start command configuration, preventing new management commands from running on deploy. After multiple failed deployment attempts, the decision was made to completely remove the feature rather than continue troubleshooting Railway caching issues.

---

### Bible Reading Plans & Study Tools (NEW FEATURE - Phase 1)

**Session:** Bible App Updates

**Description:**
Major enhancement to the Faith module adding Bible reading plans and study tools to help users build consistent Scripture engagement habits.

**New Features:**

1. **Bible Reading Plans**
   - ReadingPlanTemplate model for system-defined plans
   - ReadingPlanDay model for daily readings within a plan
   - UserReadingPlan model for tracking user progress
   - UserReadingProgress model for daily completion tracking
   - Pre-loaded plans: Forgiveness (7 days), Prayer (7 days), Peace in Troubled Times (7 days), Marriage (7 days), Gospel of John (21 days), Psalms of Comfort (5 days)
   - Progress tracking with percentage complete
   - Pause/Resume/Abandon functionality
   - Topic-based filtering

2. **Bible Study Tools**
   - BibleHighlight model - color-coded verse highlighting (yellow, green, blue, pink, purple, orange)
   - BibleBookmark model - save locations to return to
   - BibleStudyNote model - in-depth study notes with tagging
   - Study Tools dashboard showing all tools in one place
   - Filtering by color, book, or tag

**New Files:**
- `apps/faith/migrations/0006_bible_reading_plans_and_study_tools.py`
- `apps/faith/management/commands/load_reading_plans.py`
- `templates/faith/reading_plans/list.html`
- `templates/faith/reading_plans/detail.html`
- `templates/faith/reading_plans/progress.html`
- `templates/faith/study_tools/home.html`
- `templates/faith/study_tools/highlight_list.html`
- `templates/faith/study_tools/highlight_form.html`
- `templates/faith/study_tools/bookmark_list.html`
- `templates/faith/study_tools/bookmark_form.html`
- `templates/faith/study_tools/note_list.html`
- `templates/faith/study_tools/note_form.html`
- `templates/faith/study_tools/note_detail.html`

**Modified Files:**
- `apps/faith/models.py` - Added 7 new models
- `apps/faith/forms.py` - Added forms for reading plans and study tools
- `apps/faith/views.py` - Added 20+ new views
- `apps/faith/urls.py` - Added URL patterns for reading plans and study tools
- `apps/faith/admin.py` - Added admin registrations for new models

**URL Patterns Added:**
- `/faith/reading-plans/` - Browse reading plans
- `/faith/reading-plans/<slug>/` - View plan details
- `/faith/reading-plans/<slug>/start/` - Start a plan
- `/faith/reading-plans/progress/<pk>/` - View progress
- `/faith/reading-plans/progress/<pk>/day/<pk>/complete/` - Mark day complete
- `/faith/study-tools/` - Study tools dashboard
- `/faith/study-tools/highlights/` - View highlights
- `/faith/study-tools/bookmarks/` - View bookmarks
- `/faith/study-tools/notes/` - View study notes

**Tests:**
- All 1395 tests pass including 100 faith tests

---

### Delete Food Entries from History Page (ENHANCEMENT)

**Session:** Delete Food History

**Feature:**
Added the ability to delete food entries directly from the Food History page without navigating to the detail page first.

**Changes Made:**
1. Added inline delete button with confirmation dialog to each food entry row in history
2. Added CSS styles for inline-form and text-danger classes to match nutrition home styling
3. Delete uses existing soft-delete pattern via `FoodEntryDeleteView`

**Files Modified:**
- `templates/health/nutrition/history.html` - Added delete form and styles

**Migration:**
- `apps/core/migrations/0033_food_history_delete_release_note.py` - What's New entry

**Tests:** All 82 nutrition tests and 101 health comprehensive tests pass.

---

### Google Calendar OAuth Redirect URI Fix (BUG FIX)

**Session:** Google Calendar Error

**Problem:**
When trying to connect Google Calendar from production, users received "Access blocked: This app's request is invalid" with error 400: redirect_uri_mismatch.

**Root Cause:**
The `GOOGLE_CALENDAR_REDIRECT_URI` setting had an empty default for production, requiring the environment variable to be set. When not set, the redirect URI sent to Google was empty or didn't match the authorized URI in Google Cloud Console.

**Solution:**
1. Added production default redirect URI: `https://wholelifejourney.com/life/calendar/google/callback/`
2. Added diagnostic logging for redirect URI configuration
3. Follows same pattern as Dexcom OAuth fix (uses env var with sensible default)

**Files Modified:**
- `config/settings.py` - Added production default for GOOGLE_CALENDAR_REDIRECT_URI
- `apps/life/services/google_calendar.py` - Added logging for OAuth configuration

**Required Action:**
User must add `https://wholelifejourney.com/life/calendar/google/callback/` as an authorized redirect URI in Google Cloud Console under:
APIs & Services → Credentials → OAuth 2.0 Client IDs → (your client) → Authorized redirect URIs

---

### Dexcom OAuth v3 Upgrade and Debugging (BUG FIX)

**Session:** Dexcom Fix

**Problem:**
Dexcom OAuth connection was failing with blank screen after user consent. User could log in to Dexcom but after granting permission, the callback resulted in no redirect or error.

**Root Cause:**
1. OAuth endpoints were using v2 paths (`/v2/oauth2/login`, `/v2/oauth2/token`) instead of v3
2. Authorization URL query parameters were not properly URL-encoded
3. Insufficient logging made it impossible to diagnose issues

**Solution:**
1. Updated OAuth endpoints to v3 (`/v3/oauth2/login`, `/v3/oauth2/token`)
2. Added `urllib.parse.urlencode()` for proper URL encoding of query parameters
3. Added comprehensive logging throughout the OAuth flow:
   - Callback receipt with user info and GET parameters
   - Code presence, state comparison, and stored state validation
   - Token exchange URL, redirect_uri, and response status
   - Full error response body for troubleshooting
   - Stack traces for exception handling

**Files Modified:**
- `apps/health/services/dexcom.py` - v3 endpoints, URL encoding, logging
- `apps/health/views.py` - Detailed logging in DexcomCallbackView

---

## 2025-12-31 Changes

### Dexcom CGM Integration (NEW FEATURE)

**Session:** Journal Book View (continued)

Added full Dexcom Continuous Glucose Monitor integration to automatically sync blood glucose data.

**Features Added:**
1. **OAuth 2.0 Authentication**
   - Secure connection to Dexcom account via OAuth flow
   - Token storage and automatic refresh
   - Connect/disconnect UI on glucose dashboard

2. **Glucose Data Sync**
   - Automatic import of EGV (Estimated Glucose Values)
   - Trend arrows showing glucose direction (rising/falling)
   - Trend rate in mg/dL/min
   - Manual sync trigger with day range selection
   - Duplicate detection to prevent re-importing same readings

3. **New Glucose Dashboard**
   - Current reading with large display and trend arrow
   - Time in Range calculation (70-180 mg/dL)
   - Low/high event counts
   - 24-hour chart with color-coded points
   - Stats: average, min, max for past 7 days
   - Recent readings list with source indicators

4. **Extended GlucoseEntry Model**
   - New fields: source, dexcom_record_id, trend, trend_rate, display_device
   - New context choice: "cgm" for CGM readings
   - Status display (Very Low, Low, In Range, High, Very High)

5. **DexcomCredential Model**
   - OAuth token storage (access_token, refresh_token, token_expiry)
   - Sync settings (enabled, days_to_sync)
   - Sync status tracking (last_sync, status, count)

**Files Created:**
- `apps/health/services/__init__.py`
- `apps/health/services/dexcom.py` - DexcomService, DexcomSyncService
- `templates/health/glucose/dashboard.html`
- `templates/health/glucose/form.html`
- `templates/health/glucose/list.html`

**Files Modified:**
- `apps/health/models.py` - Added DexcomCredential, extended GlucoseEntry
- `apps/health/views.py` - Added Dexcom views, GlucoseDashboardView
- `apps/health/urls.py` - Added Dexcom and glucose dashboard routes
- `apps/health/admin.py` - Added DexcomCredentialAdmin, updated GlucoseEntryAdmin
- `config/settings.py` - Added Dexcom configuration settings
- `docs/wlj_third_party_services.md` - Added Dexcom service documentation

**Migration:**
- `apps/health/migrations/0012_dexcom_cgm_integration.py`

**Environment Variables Required:**
- `DEXCOM_CLIENT_ID` - From Dexcom Developer Portal
- `DEXCOM_CLIENT_SECRET` - From Dexcom Developer Portal
- `DEXCOM_REDIRECT_URI` - OAuth callback URL
- `DEXCOM_USE_SANDBOX` - Set to true for sandbox mode (development)

**Setup Instructions:**
1. Register app at https://developer.dexcom.com/
2. Create an application with Redirect URI pointing to `/health/glucose/dexcom/callback/`
3. Set environment variables in Railway
4. Users can connect from Health > Blood Glucose dashboard

---

### Delete Button Contrast Fix (BUG FIX)

**Session:** Significant Events

**Problem:**
The Delete button on the Significant Event detail page had red text on a red background, making the text invisible. The button only showed white text on hover, which is poor accessibility.

**Root Cause:**
The template used `class="btn btn-ghost btn-danger"` where:
- `btn-ghost` sets `background-color: transparent`
- The inline CSS `.btn-danger` set `color: var(--color-error)` (red text)
- Result: red text on transparent button that appears red due to hover styles

**Solution:**
1. Removed `btn-ghost` class from the delete button
2. Updated inline CSS `.btn-danger` to use:
   - `background-color: var(--color-error)` (red background)
   - `color: white` (white text for contrast)
   - Proper hover state with darker red background

**Files Modified:**
- `templates/life/significant_event_detail.html`:
  - Line 34: Changed from `class="btn btn-ghost btn-danger"` to `class="btn btn-danger"`
  - Lines 336-344: Updated `.btn-danger` CSS to have red background with white text
- `templates/life/pet_detail.html`:
  - Line 54: Changed from `class="btn btn-ghost btn-danger"` to `class="btn btn-danger"`
  - (Already had correct `.btn-danger` CSS styling)

**No migrations required** - CSS/template changes only.

---

### Journal Book View Fix (BUG FIX)

**Session:** Journal Book View

**Problem:**
The Journal Book View feature was not working. When users navigated to `/journal/book-view/`, the JavaScript would fail because the `entries_json` context variable was being passed as a Python list directly into the JavaScript code instead of being properly serialized as JSON.

**Root Cause:**
In `apps/journal/views.py`, the `BookView.get_context_data()` method was passing a Python list to the template:
```python
context["entries_json"] = [...]  # Python list with None/True/False
```

When this was rendered in the template with `{{ entries_json|safe }}`, it produced invalid JavaScript because:
- Python `None` was output instead of JavaScript `null`
- Python `True/False` was output instead of JavaScript `true/false`
- Python string quotes and escaping differ from JSON

**Solution:**
1. Added `import json` at the top of `apps/journal/views.py`
2. Changed the context assignment to properly serialize to JSON:
   ```python
   context["entries_json"] = json.dumps(entries_data)
   ```

**Files Modified:**
- `apps/journal/views.py`:
  - Added `import json` (line 33)
  - Changed `entries_json` to use `json.dumps()` for proper JSON serialization (line 163)

**Testing:**
- All 11 journal view tests pass
- Book view test (`test_book_view_loads`) passes

---

### Weight Loss Calculation and Progress Graph (NEW FEATURE)

**Session:** Weight Loss and Graph

Added total weight loss calculation and an interactive progress chart to the Weight History page.

**Features Added:**
1. **Total Weight Change Calculation**
   - Shows how much weight lost/gained from first entry to latest entry
   - Displayed in stats bar with color coding (green for loss, orange for gain)
   - Shows starting weight, current weight, and total change

2. **Weight Progress Chart**
   - Interactive line chart showing weight over time (up to 100 entries)
   - Uses Chart.js for smooth, responsive visualization
   - Hover tooltips show exact weight and date
   - Chart displays journey summary with date range and total change

3. **Enhanced Stats Bar**
   - New "Total Change" stat added to existing Latest/Low/High/Avg bar
   - Highlighted with accent border for visibility

**Layout:**
- Stats bar (Latest, Low, High, Avg, Total Change)
- Weight Progress Chart (new)
- Weight History table (existing)

**Files Modified:**
- `apps/health/views.py` - WeightListView: Added weight_change, first_entry, first_weight, latest_weight_lb, and chart_data to context
- `templates/health/weight_list.html` - Added Total Change stat, chart container with Chart.js, and responsive styles

**Tests Added (4 new tests):**
- `test_weight_list_has_weight_loss_calculation` - Verifies weight change calculation
- `test_weight_list_has_chart_data` - Verifies chart data structure
- `test_weight_list_single_entry_no_change` - No weight_change with single entry

**Test Count:** 1395 tests (was 1392, +3 new tests)

**No migrations required** - View/template changes only.

---

### Data Encryption Roadmap (DOCUMENTATION)

Added comprehensive data encryption analysis and roadmap to security documentation.

**Session:** Encryption of Data

**Analysis Completed:**
- Reviewed current data storage (all sensitive fields stored as plaintext)
- Evaluated three encryption approaches:
  - Option A: Full encryption (breaks search)
  - Option B: Selective encryption (recommended for pre-launch)
  - Option C: Full encryption + search index (complex, for post-launch if needed)
- Assessed impact on AI features (Dashboard AI, Personal Assistant, trend tracking)
- Documented performance implications and trade-offs

**Key Findings:**
- AI features will NOT break with encryption (data decrypted before sending to OpenAI)
- Journal/task search WILL break with encryption (can't search encrypted fields)
- Option B (selective encryption) provides best balance for pre-launch

**Decision:** Defer encryption implementation during development phase to reduce complexity. Implement Option B (selective encryption) before public launch.

**Files Modified:**
- `docs/wlj_security_review.md` - Added Appendix D: Data Encryption Roadmap
  - Documents current state, options evaluated, implementation phases
  - Key management requirements
  - AI feature compatibility analysis
  - Decision rationale

**Security Certifications Discussed:**
- SSL Certificate (already in place via Railway)
- Privacy Policy and Terms of Service
- Penetration testing (recommended pre-launch)
- SOC 2 / ISO 27001 / HIPAA (enterprise-level, not needed yet)

---

### SMS Error 21212 - Phone Number Validation Fix (FIX)

**Problem Solved:**
Twilio Error 21212 "Invalid 'From' number" was occurring when sending SMS because the `TWILIO_PHONE_NUMBER` environment variable wasn't properly validated or normalized to E.164 format.

**Error from Twilio Console:**
- Error Code: 21212
- Message: "The 'From' parameter you supplied was not a valid phone number, Alphanumeric Sender ID or approved WhatsApp Sender."

**Root Cause:**
The `TWILIO_PHONE_NUMBER` could be set incorrectly (missing +, wrong format, extra characters) without validation, causing Twilio to reject SMS sends.

**Solution:**
1. Added `_normalize_phone_number()` method to TwilioService that:
   - Removes formatting characters (spaces, dashes, parentheses, dots)
   - Adds +1 prefix for 10-digit US numbers
   - Adds + prefix for 11-digit numbers starting with 1
   - Validates against E.164 regex pattern (`^\+[1-9]\d{1,14}$`)
   - Returns empty string for invalid numbers
2. Phone number normalization happens at service initialization AND for destination numbers
3. Added detailed error logging showing actual From/To values when errors occur
4. Added specific error messages for common Twilio errors (21212, 21211)
5. Added configuration validation that logs clear errors if TWILIO_PHONE_NUMBER is invalid

**Files Modified:**
- `apps/sms/services.py`:
  - Added `E164_PATTERN` regex constant
  - Added `_normalize_phone_number()` method
  - Updated `__init__()` to validate/normalize the phone number at startup
  - Updated `send_sms()` with detailed error messages and normalization
- `apps/sms/tests/test_sms_comprehensive.py`:
  - Added `TwilioServicePhoneNormalizationTests` class (6 new tests)
  - Tests: E.164 format, 10-digit US, 11-digit US, formatting removal, invalid handling

**Test Count:** 46 SMS tests (was 40, added 6 phone normalization tests)

**Action Required for Railway:**
Verify `TWILIO_PHONE_NUMBER` environment variable is set correctly:
- Must be in E.164 format: `+1XXXXXXXXXX` (e.g., `+12025551234`)
- Or 10-digit format: `2025551234` (will be auto-converted)
- Check in Twilio Console that this number is assigned to your account

---

### SMS History Timezone Fix (FIX)

**Problem Solved:**
SMS notification times in `/sms/history/` were displayed in UTC instead of the user's timezone.

**Solution:**
- Added Django timezone template tag to convert times to user's local timezone
- Updated date grouping to use local timezone (so notifications appear under correct day)
- Added `user_timezone` to view context

**Files Modified:**
- `templates/sms/history.html` - Added `{% load tz %}` and timezone conversion
- `apps/sms/views.py` - Added pytz timezone conversion for date grouping and context

---

### SMS History Link on Preferences (Enhancement)

Added a "View History" button to the SMS Notifications section on the Preferences page for easy access to `/sms/history/`.

**Files Modified:**
- `templates/users/preferences.html` - Added link and CSS for card-title-row

---

### Embedded SMS Scheduler in Web Process (FIX)

**Problem Solved:**
SMS scheduler was configured to run as a separate worker process, but Railway doesn't auto-create worker processes from Procfile - only web and database services are created by default.

**Solution:**
Embedded the APScheduler background jobs directly in the WSGI application. The scheduler starts when Gunicorn loads the application using the `--preload` flag.

**Key Implementation Details:**
1. **Embedded in WSGI:** Scheduler starts in `config/wsgi.py` rather than as separate worker
2. **Single Instance:** Uses `SMS_SCHEDULER_STARTED` environment variable to prevent duplicate schedulers when Gunicorn forks workers
3. **Textual References:** Jobs use textual references (`'apps.sms.jobs:schedule_daily_reminders'`) instead of function objects to avoid APScheduler serialization issues
4. **MemoryJobStore:** Uses in-memory job store (not DjangoJobStore) because jobs are re-registered on each startup anyway

**New File Created:**
- `apps/sms/jobs.py` - Importable job functions for APScheduler:
  - `schedule_daily_reminders()` - Called at midnight to create SMSNotification records
  - `send_pending_sms()` - Called every 5 minutes to send due notifications

**Files Modified:**
- `config/wsgi.py` - Added `start_scheduler()` function that initializes APScheduler with two jobs
- `Procfile` - Added `--preload` flag to Gunicorn command to ensure scheduler starts once before forking

**Error Fixed:**
- `SerializationError: This Job cannot be serialized since the reference to its callable could not be determined`
- Solution: Created standalone functions in `apps/sms/jobs.py` and used textual references

**Deployment Status:**
- Railway logs confirm: "SMS scheduler started successfully"
- Initial send check runs on startup: "Sent 0 SMS, 0 failed, 0 skipped"

---

### Real-Time SMS Scheduling on Save (NEW)

**Problem Solved:**
If you created a medicine schedule at 2pm for 8pm tonight, the SMS reminder wouldn't be scheduled until the next midnight batch job ran.

**Solution:**
Added Django signals that trigger SMS scheduling immediately when you save:
- Medicines and MedicineSchedules → Schedules SMS for any doses due today
- Tasks → Schedules SMS reminder at 9 AM if due today
- Events (LifeEvent) → Schedules SMS 30 minutes before event time

**New File:**
- `apps/sms/signals.py` - Django post_save signal handlers for real-time scheduling

**Files Modified:**
- `apps/sms/apps.py` - Registers signals in `ready()` method

**Test Count:** 1394 tests (+2 new signal tests)

---

### Universal Barcode Scanner Integration (MAJOR FEATURE)

Extended the barcode scanner to work throughout the app, enabling users to scan product barcodes to auto-populate forms. This significantly reduces data entry when adding inventory items or medicines.

**Example Use Case:**
User scans a DeWalt drill barcode → System looks up product in external databases → Returns product name, brand, model, category → Pre-fills Inventory form → User just reviews and submits.

**New Files Created:**
- `apps/scan/services/product_lookup.py` - Product lookup service for electronics, tools, household items
  - Uses UPC Item DB API (free tier) for product lookups
  - OpenAI fallback for unknown products
  - Returns: product_name, brand, category, model_number, description, msrp
  - 24-hour caching to minimize API calls

- `apps/scan/services/medicine_lookup.py` - Medicine lookup service for OTC drugs and supplements
  - Uses RxNav API (NIH, free) for drug name lookups
  - Uses FDA OpenData API (free) for NDC code lookups
  - OpenAI fallback for unknown medicines
  - Returns: medicine_name, generic_name, brand_name, dosage_form, strength, purpose

**Files Modified:**
- `apps/scan/services/__init__.py` - Export new services
- `apps/scan/urls.py` - Added `/barcode/product/` and `/barcode/medicine/` endpoints
- `apps/scan/views.py` - Added `ProductLookupView` and `MedicineLookupView` classes
- `apps/life/views.py` - Updated `InventoryCreateView` with barcode scan support and additional pre-fill fields
- `apps/health/views.py` - Updated `MedicineCreateView` with barcode scan support and context data
- `templates/life/inventory_form.html` - Added barcode scanner UI with camera integration
- `templates/health/medicine/medicine_form.html` - Added barcode scanner UI with camera integration

**New API Endpoints:**
- `POST /scan/barcode/product/` - Look up product barcode, returns inventory pre-fill URL
- `POST /scan/barcode/medicine/` - Look up medicine barcode, returns medicine pre-fill URL

**External APIs Used (All FREE):**
- UPC Item DB - Product database for electronics, tools, appliances
- RxNav API (NIH) - Drug database for medication lookups
- FDA OpenData - Official NDC drug database
- OpenAI (fallback) - For products not in external databases

**Features:**
- Native browser barcode detection using `BarcodeDetector` API
- Manual barcode entry fallback for unsupported browsers
- Real-time camera preview with scanning target overlay
- Haptic feedback on successful barcode detection
- Pre-fill redirect to appropriate form with all fields populated
- Source tracking (`created_via` = barcode_scan) for analytics

**No migrations required** - No database schema changes.

---

### Nutrition Breadcrumbs (Enhancement)

Added breadcrumb navigation to all nutrition pages for improved UX and navigation consistency.

**Files Modified (9 templates):**
- `templates/health/nutrition/home.html` - Health > Nutrition
- `templates/health/nutrition/food_entry_form.html` - Health > Nutrition > Log Food/Edit Entry
- `templates/health/nutrition/food_entry_detail.html` - Health > Nutrition > [Food Name]
- `templates/health/nutrition/history.html` - Health > Nutrition > History
- `templates/health/nutrition/goals.html` - Health > Nutrition > Goals
- `templates/health/nutrition/stats.html` - Health > Nutrition > Stats
- `templates/health/nutrition/quick_add.html` - Health > Nutrition > Quick Add
- `templates/health/nutrition/custom_food_list.html` - Health > Nutrition > My Foods
- `templates/health/nutrition/custom_food_form.html` - Health > Nutrition > My Foods > Create/Edit

**No migrations required** - Template-only changes.

---

### APScheduler for Automatic SMS Notification Scheduling (NEW)

**Problem Solved:**
SMS medicine reminders were not being sent because the notification system required external cron jobs to trigger scheduling and sending - but no scheduler was actually running on Railway.

**Solution:**
Integrated `django-apscheduler` to run background jobs automatically as part of the Django application. Added a worker process that:
1. **Schedules SMS reminders daily at midnight** - Creates SMSNotification records for all users with SMS enabled
2. **Sends pending SMS every 5 minutes** - Finds notifications due and sends via Twilio
3. **Cleans up old job logs weekly** - Prevents database bloat

**New Dependencies:**
- `django-apscheduler>=0.6.2` - APScheduler with Django database job store

**New Files Created:**
- `apps/sms/management/commands/run_sms_scheduler.py` - Management command to run the scheduler
  - Uses `BackgroundScheduler` with `DjangoJobStore` for persistence
  - Configurable schedule hour and send interval via command arguments
  - Runs initial send check on startup
  - Handles graceful shutdown on SIGINT

**Files Modified:**
- `requirements.txt` - Added django-apscheduler
- `config/settings.py` - Added `django_apscheduler` to INSTALLED_APPS, APScheduler configuration
- `Procfile` - Added `worker: python manage.py run_sms_scheduler`

**Deployment:**
Railway will automatically detect the worker process in Procfile and run it alongside the web process. No external cron configuration needed.

**Test Count:** 1392 tests (unchanged)

---

### Medicine Log Edit Feature (NEW)

Added the ability to edit the "taken at" time of medicine log entries. This allows users to correct the time when they actually took a dose - important when they took medicine on time but forgot to log it immediately.

**Problem Solved:**
- User takes medicine at 8:00 AM on schedule
- Forgets to tap "Take" until 9:30 AM
- Medicine is marked as "Taken Late" even though it was on time
- Now users can edit the log to correct the actual taken time

**New Files Created:**
- `templates/health/medicine/log_edit.html` - Edit form template with medicine info display

**Files Modified:**
- `apps/health/forms.py` - Added `MedicineLogEditForm` class
  - Allows editing `taken_at` datetime and `notes`
  - Converts times between user timezone and UTC
  - Recalculates Taken/Taken Late status on save based on new time
- `apps/health/views.py` - Added `MedicineLogEditView` class
  - UpdateView for editing MedicineLog entries
  - User can only edit their own logs (data isolation)
  - Imports `MedicineLogEditForm`
- `apps/health/urls.py` - Added route `/medicine/log/<int:pk>/edit/`
- `templates/health/medicine/home.html` - Added "Edit" link for taken doses
- `templates/health/medicine/history.html` - Added "Edit" link for each log entry
  - Updated CSS grid to accommodate new actions column
  - Added user_timezone to context for time display

**Tests Added (12 new tests):**
- `test_log_edit_view_requires_login` - Authentication required
- `test_log_edit_view_loads` - Page loads correctly
- `test_log_edit_shows_medicine_info` - Displays medicine name and dose
- `test_log_edit_can_update_taken_at` - Can change the time
- `test_log_edit_recalculates_status_to_taken` - Late → Taken when corrected
- `test_log_edit_recalculates_status_to_late` - Taken → Late if time changed
- `test_log_edit_can_add_notes` - Notes field works
- `test_log_edit_redirects_to_next_url` - Respects ?next= parameter
- `test_log_edit_default_redirect_to_history` - Default redirect
- `test_user_cannot_edit_other_users_log` - Data isolation (404)
- `test_log_edit_shows_current_status` - Displays status badge
- `test_history_page_shows_edit_link` - Edit link appears in history
- `test_medicine_home_shows_edit_link_for_taken_doses` - Edit link on home page

**Test Count:** 1381 tests (was 1368, +13 tests)

**No migrations required** - Uses existing MedicineLog fields.

---

### Barcode Scanner Feature (NEW)

Added dedicated barcode scanning mode to the Camera Scan feature for quick food product lookup.

**New Files Created:**
- `apps/scan/services/barcode.py` - Barcode lookup service with database and AI fallback

**Files Modified:**
- `apps/scan/views.py` - Added BarcodeLookupView for barcode API endpoint
- `apps/scan/urls.py` - Added `/scan/barcode/` URL route
- `apps/scan/services/__init__.py` - Exported barcode_service
- `apps/health/views.py` - FoodEntryCreateView now handles barcode source
- `templates/scan/scan_page.html` - Added mode toggle, barcode overlay, and barcode result states

**Test Files Modified:**
- `apps/scan/tests/test_views.py` - Added BarcodeLookupViewTests and BarcodeServiceTests
- `apps/scan/tests/test_security.py` - Fixed user isolation test assertion

**Features:**
1. **Mode Toggle UI**
   - Toggle between Vision mode and Barcode mode at top of scan page
   - Different camera overlay for each mode

2. **Barcode Detection** (Updated: ZXing Library)
   - Uses @zxing/browser library for cross-browser barcode detection
   - CDN: `https://cdn.jsdelivr.net/npm/@zxing/browser@0.1.5/umd/zxing-browser.min.js`
   - Works on all browsers including Safari/iOS (previously Quagga2 was unreliable)
   - Supports UPC-A, UPC-E, EAN-13, EAN-8, Code 128, Code 39
   - Real-time auto-detection from camera feed without button press
   - Vibration feedback on barcode detection

3. **Barcode Lookup Service** (Updated: Open Food Facts API)
   - **Lookup order:** Local DB → Open Food Facts → OpenAI fallback
   - **Open Food Facts:** Free, open-source database with 4M+ products worldwide
   - API: `https://world.openfoodfacts.org/api/v2/product/{barcode}.json`
   - Caches Open Food Facts results to local database for faster future lookups
   - Returns structured BarcodeResult with all nutritional data

4. **Food Entry Integration**
   - Pre-fills food entry form with all nutritional data
   - Sets `entry_source = 'barcode'` automatically
   - Passes barcode value in URL for reference

5. **Result Display**
   - Shows product name, brand, and key nutrition (calories, protein, carbs, fat)
   - "Log to Nutrition" button pre-fills food entry form
   - "Scan Another" to continue scanning

**No migrations required** - Uses existing FoodItem.barcode field and FoodEntry.SOURCE_BARCODE.

---

### File Cleanup & Test Fixes

Fixed 6 failing tests and added temp files to .gitignore for cleaner repository.

**Changes Made:**

1. **Added temp/test output files to .gitignore**
   - `nul` - Windows null device file that can accidentally be created
   - `test_errors.txt` - Test runner error output
   - `test_summary.txt` - Test runner summary output
   - `test_output.txt` - General test output

2. **Fixed Preferences Form Tests**
   - Added missing required fields: `weight_goal_unit`, `sms_quiet_start`, `sms_quiet_end`
   - Corrected `weight_goal_unit` value from 'lbs' to 'lb' (matching model choices)
   - Tests affected: `apps.users.tests.test_users.PreferencesViewTest`

3. **Fixed What's New Preference Tests**
   - Same form field fixes as preferences tests
   - Tests affected: `apps.core.tests.test_core_comprehensive.WhatsNewPreferenceTest`

4. **Fixed Blood Oxygen Data Isolation Test**
   - Changed test strategy: instead of checking if '94' appears in HTML (which matched unrelated content like navigation elements), now verifies entry count in context
   - More robust test that confirms data isolation without false positives
   - Tests affected: `apps.health.tests.test_health_comprehensive.BloodVitalsDataIsolationTest`

5. **Fixed Task Search Tests**
   - Updated assertions to match actual template text
   - Template shows "X results for" not "Found X tasks matching"
   - Tests affected: `apps.life.tests.test_views.TaskViewTest`

**Files Modified:**
- `.gitignore` - Added temp file patterns
- `apps/core/tests/test_core_comprehensive.py` - Fixed What's New preference tests
- `apps/health/tests/test_health_comprehensive.py` - Fixed blood oxygen data isolation test
- `apps/life/tests/test_views.py` - Fixed task search result assertions
- `apps/users/tests/test_users.py` - Fixed preferences form test

**Test Count:** 1379 tests passing (no change in total)

---

### Menu Navigation Reorganization

Updated the Health and Life module navigation menus for better organization.

**Changes Made:**

1. **Moved Fasting from Providers to Nutrition**
   - Fasting is logically related to nutrition tracking, not medical providers
   - Nutrition menu now includes: Nutrition Home, Food History, Statistics, Goals, Fasting
   - Providers menu now contains only: Medical Providers

2. **Added Significant Events to Life Menu**
   - Significant Events (birthdays, anniversaries, etc.) was missing from navigation
   - Now accessible under Life menu alongside Documents

**Files Modified:**
- `templates/components/navigation.html` - Updated Health mega-menu and Life dropdown menu

**No migrations required** - Template-only change.

---

### AI Span: Comprehensive AI Context Enhancement

Enhanced OpenAI integration to read and apply ALL relevant user data when generating Dashboard AI insights and Personal Assistant responses. The AI now has a complete picture of the user's life journey.

**New Data Sent to OpenAI:**

**Purpose Module:**
- Word of the Year and annual theme
- Anchor Scripture (if set)
- Active change intentions (identity-based shifts)
- Life goals with domain names and importance
- Goal details including "why it matters"

**Faith Module:**
- Active prayer count
- Recently answered prayers (shows God's faithfulness)
- Memory verse (if user has one set)
- Recently saved Scripture references (what user is studying)
- Faith milestones count

**Life Module:**
- Tasks due today and overdue counts
- Active projects with progress percentages
- Priority projects (marked as "Now")
- Today's calendar events count

**Health Module:**
- Current weight and weight goal progress
- Weight remaining to goal and direction (lose/gain/maintain)
- Active fasting status with hours fasted
- Today's calorie intake vs goal
- Calories remaining for the day
- Workout count and days since last workout
- Personal records achieved this month
- Medicine adherence rate with quality indicator
- Medicines needing refill

**Files Modified:**
- `apps/ai/dashboard_ai.py` - Enhanced `_gather_user_data()` with comprehensive context
  - Added Purpose module data gathering (Word of Year, goals, intentions)
  - Added enhanced Faith data (memory verse, Scripture study, answered prayers)
  - Added Life module data (projects, events, tasks due)
  - Added Health nutrition data (calories, weight goals)
  - Organized code with clear section headers
- `apps/ai/services.py` - Updated `generate_daily_insight()` to use new data
  - Added sections for Annual Direction & Purpose
  - Added Task & Project Status context
  - Added enhanced Faith Context
  - Added comprehensive Health Status
  - Improved prompt to reference Word of Year and goals

**Impact:**
- AI insights now deeply personalized to user's stated purpose
- Dashboard messages reference user's Word of the Year when appropriate
- AI can encourage progress on specific goals by name
- Health insights include weight goal progress and nutrition tracking
- Faith-aware insights include Scripture study and prayer activity

**No migrations required** - This is a code-only enhancement to AI prompt construction.

---

### Cascading Menu Navigation System

Implemented an industry-standard cascading dropdown menu system for the main navigation. Users can now hover (desktop) or tap (mobile) on module names to reveal dropdown menus with direct links to all sub-pages within each module.

**Key Features:**
- **Desktop:** Hover-triggered dropdown menus with smooth CSS transitions
- **Mobile:** Tap-to-toggle accordion-style menus that work well on touch devices
- **Mega Menu:** Health module features a multi-column mega menu with organized sections (Vitals, Medicine, Fitness, Nutrition, Providers)
- **Two-column Layout:** Life and other larger modules use a two-column dropdown for easier scanning
- **Accessibility:** Full ARIA support, keyboard navigation (ESC closes all menus), focus management
- **Visual Polish:** Icons for each menu item, dividers between sections, chevron rotation on expand

**Menu Structure:**
- Dashboard - Direct link (no dropdown)
- Journal - Home, New Entry, All Entries, Book View, Prompts, Tags
- Faith - Home, Today's Verse, Saved Scripture, Prayers, Milestones, Reflections
- Health - Mega menu with 5 columns:
  - Vitals: Health Home, Weight, Heart Rate, Blood Pressure, Glucose, Blood Oxygen
  - Medicine: Today's Medicines, All Medicines, History, Adherence
  - Fitness: Fitness Home, Workouts, Templates, Personal Records
  - Nutrition: Nutrition Home, Food History, Statistics, Goals, Fasting
  - Providers: Medical Providers
- Life - Two-column: Home, Calendar, Projects, Tasks, Inventory, Pets, Recipes, Maintenance, Documents, Significant Events
- Purpose - Home, Annual Direction, Goals, Intentions, Reflections
- Assistant - Direct link (no dropdown)

**Files Modified:**
- `templates/components/navigation.html` - Complete rewrite with dropdown structure
- `static/css/main.css` - Added 180+ lines for dropdown/mega menu styles
- `static/js/main.js` - Added dropdown toggle functions, click-outside handlers, ESC key support

**Migrations:**
- `apps/core/migrations/0023_merge_20251231_0658.py` - Merge migration for prior conflicts
- `apps/core/migrations/0024_add_cascading_menu_release_note.py` - What's New entry

**What's New Entry Added:**
- Title: "Enhanced Navigation with Cascading Menus"
- Type: Feature

---

### Memory Verse Feature

Added the ability to mark a saved Scripture verse as a "Memory Verse" to display prominently at the top of the Dashboard.

**Features:**
- Toggle button on saved verses to mark/unmark as memory verse
- Only one memory verse allowed per user at a time
- Memory verse displays at top of Dashboard (when Faith module enabled)
- Visual badge and highlight on memory verse in Scripture Library
- Star icon and styled card on Dashboard

**Files Modified:**
- `apps/faith/models.py` - Added `is_memory_verse` field to SavedVerse model
- `apps/faith/views.py` - Added `ToggleMemoryVerseView` class
- `apps/faith/urls.py` - Added route for toggle endpoint
- `apps/dashboard/views.py` - `_get_faith_data()` now fetches memory verse
- `templates/dashboard/home.html` - Added Memory Verse section after header
- `templates/faith/scripture_list.html` - Added Memorize button and badge to verse cards
- `static/css/dashboard.css` - Added Memory Verse section styles

**Migration:**
- `apps/faith/migrations/0005_add_memory_verse_field.py`

**Tests Added (10 new tests):**
- `test_default_is_not_memory_verse` - New verses aren't memory verses
- `test_toggle_to_memory_verse` - Can set as memory verse
- `test_toggle_off_memory_verse` - Can unset memory verse
- `test_only_one_memory_verse_at_a_time` - New one clears previous
- `test_cannot_toggle_other_users_verse` - User isolation
- `test_memory_verse_shows_badge_in_list` - Badge displays correctly
- `test_toggle_requires_post` - GET method not allowed
- `test_dashboard_shows_memory_verse_when_set` - Dashboard displays verse
- `test_dashboard_no_memory_verse_section_when_not_set` - Hidden when none
- `test_dashboard_no_memory_verse_when_faith_disabled` - Hidden when Faith off

---

### Fix SMS Preferences Not Saving

Fixed bug where changes to SMS notification settings in Preferences would not save.

**Issue:**
- SMS notification toggles (enabled, consent, category preferences, quiet hours) were displayed in the preferences form but were not bound to the Django form
- The template used `user.preferences.sms_*` instead of `form.sms_*.value`, which meant the fields weren't part of the form submission
- The `PreferencesForm` class did not include SMS fields in its `fields` list

**Fix:**
1. Added all 11 SMS fields to `PreferencesForm.Meta.fields`:
   - `sms_enabled`, `sms_consent`
   - `sms_medicine_reminders`, `sms_medicine_refill_alerts`
   - `sms_task_reminders`, `sms_event_reminders`
   - `sms_prayer_reminders`, `sms_fasting_reminders`
   - `sms_quiet_hours_enabled`, `sms_quiet_start`, `sms_quiet_end`

2. Added corresponding widget definitions for all SMS fields

3. Updated template to use `form.sms_*.value` instead of `user.preferences.sms_*`

4. Added SMS consent date handling in `PreferencesView.form_valid()`

**Files Modified:**
- `apps/users/forms.py` - Added SMS fields and widgets to PreferencesForm
- `apps/users/views.py` - Added SMS consent date handling
- `templates/users/preferences.html` - Updated SMS section to use form fields

---

### Task List with Search Feature

Added ability to search within tasks and improved task list display with counts.

**Features Added:**
- Full-text search across task title, notes, and project name
- Search preserves existing filters (show, priority)
- Task counts displayed on filter buttons (Active/Completed/All)
- Clear search button when search is active
- Search results count display

**Implementation:**
1. Updated `TaskListView` in `apps/life/views.py`:
   - Added search query handling with Django Q objects
   - Searches across title, notes, and project__title
   - Added `search_query` to context
   - Added `total_active_count`, `total_completed_count`, `total_all_count` to context

2. Updated `templates/life/task_list.html`:
   - Added search bar with search icon and clear button
   - Search results info display
   - Updated filter links to preserve search query
   - Added task counts to filter buttons
   - Added CSS styles for search bar

**Files Modified:**
- `apps/life/views.py` - Enhanced TaskListView with search and counts
- `templates/life/task_list.html` - Added search UI and updated filter links

---

### Improved Help System - "Why Use This Feature"

Completely rewrote the in-app help system to provide more valuable, decision-enabling content. The previous help content explained *how* to use features, but the new content explains *why* users should use each feature and how it all connects.

**New Content Structure:**
Each help topic now includes:
1. **"Why This Feature?"** - Value proposition explaining the reason to use it
2. **"How It Powers Your Dashboard"** - Connection to AI insights and dashboard
3. **"How to Use It"** - Step-by-step instructions
4. **"Tips for Success"** - Best practices
5. **"Related Features"** - Cross-module connections showing how everything integrates

**Help Topics Added/Rewritten (20 total):**
- DASHBOARD_HOME - "Your Dashboard: The Heart of Your Journey"
- GENERAL - "Navigating Your Whole Life Journey"
- JOURNAL_HOME - "Journal: The Foundation of Self-Awareness"
- HEALTH_HOME - "Health: Track What You Can Measure"
- FAITH_HOME - "Faith: Nurture Your Spiritual Journey"
- SETTINGS_PREFERENCES - "Preferences: Make It Yours"
- LIFE_HOME - "Life: Your Daily Operating Layer"
- PURPOSE_HOME - "Purpose: Your North Star"
- NUTRITION_HOME - "Nutrition: Fuel Your Body Intentionally" (NEW)
- HEALTH_MEDICINE_HOME - "Medicine Tracking: Never Miss a Dose" (NEW)
- SCAN_HOME - "Camera Scan: AI-Powered Quick Entry" (NEW)
- ASSISTANT_HOME - "Personal Assistant: Your AI-Powered Guide" (NEW)
- SMS_SETTINGS - "SMS Notifications: Reminders Where You'll See Them" (NEW)
- HEALTH_VITALS - "Vitals: Monitor Your Cardiovascular Health" (NEW)
- HEALTH_PROVIDERS - "Medical Providers: Your Healthcare Contacts" (NEW)

**Help Articles Added/Rewritten (15 total):**
- Welcome to Whole Life Journey
- Understanding Your Dashboard
- Journaling for Self-Awareness
- Health Tracking Overview
- Faith Module: Tracking Your Spiritual Journey
- Customizing Your Preferences
- AI Coaching Styles Explained
- Why Can't I See Certain Features?
- Goals and the Purpose Module
- Tasks, Projects, and the Life Module
- Medicine Tracking and Adherence (NEW)
- Camera Scan: Quick AI-Powered Entry (NEW)
- The Personal Assistant (NEW)
- SMS Notifications Setup (NEW)
- Nutrition and Food Tracking (NEW)

**New Management Command:**
- `reload_help_content` - Clears and reloads help content from fixtures
  - Options: `--dry-run`, `--topics-only`, `--articles-only`
  - Added to Procfile for automatic deployment

**Files Created:**
- `apps/help/management/__init__.py`
- `apps/help/management/commands/__init__.py`
- `apps/help/management/commands/reload_help_content.py`
- `apps/core/migrations/0022_improved_help_system_release_note.py`

**Files Modified:**
- `apps/help/fixtures/help_topics.json` - Complete rewrite (13→20 topics)
- `apps/help/fixtures/help_articles.json` - Complete rewrite (10→15 articles)
- `Procfile` - Added `reload_help_content` command

**Test Status:** All 68 help app tests passing

---

## 2025-12-30 Changes

### SMS Text Notifications Feature

Added first-class SMS notification capabilities using Twilio. Users can receive text message reminders for medicine doses, tasks, events, and more. Replies with shortcuts (D=Done, R=Remind, N=Skip) allow quick status updates directly from text messages.

**New App: `apps/sms/`**
- `models.py` - SMSNotification, SMSResponse models for tracking sent/scheduled SMS and user replies
- `services.py` - TwilioService (Twilio API integration), SMSNotificationService (scheduling, sending, reply processing)
- `scheduler.py` - SMSScheduler for scheduling medicine, task, event, prayer, and fasting reminders
- `views.py` - Phone verification, Twilio webhooks, SMS history page, protected trigger endpoints
- `urls.py` - URL patterns for all SMS endpoints
- `admin.py` - Admin registration with status badges and filters

**New User Preference Fields (15 fields):**
- Phone: `phone_number`, `phone_verified`, `phone_verified_at`
- Master toggles: `sms_enabled`, `sms_consent`, `sms_consent_date`
- Categories: `sms_medicine_reminders`, `sms_medicine_refill_alerts`, `sms_task_reminders`, `sms_event_reminders`, `sms_prayer_reminders`, `sms_fasting_reminders`
- Quiet hours: `sms_quiet_hours_enabled`, `sms_quiet_start`, `sms_quiet_end`

**Management Commands:**
- `send_pending_sms` - Send all pending SMS notifications (run every 5 min)
- `schedule_sms_reminders` - Schedule SMS for all users (run daily)

**URL Routes (10 endpoints):**
- `/sms/api/verify/send/` - Send phone verification code
- `/sms/api/verify/check/` - Verify phone with code
- `/sms/api/phone/remove/` - Remove phone and disable SMS
- `/sms/api/status/` - Get SMS configuration status
- `/sms/api/trigger/send/` - Protected: Send pending SMS
- `/sms/api/trigger/schedule/` - Protected: Schedule SMS
- `/sms/webhook/incoming/` - Twilio incoming SMS webhook
- `/sms/webhook/status/` - Twilio delivery status webhook
- `/sms/history/` - User SMS history page

**Notification Categories:**
- Medicine dose reminders
- Medicine refill alerts
- Task due date reminders
- Calendar event reminders (30 min before)
- Daily prayer reminders
- Fasting window reminders

**Reply Codes:**
- D/done/yes/taken → Mark medicine taken / task complete
- R/R5/R10/R30 → Schedule new reminder in X minutes
- N/no/skip → Mark skipped / dismiss for today

**New Files:**
- `apps/sms/__init__.py`, `apps.py`, `models.py`, `admin.py`
- `apps/sms/services.py`, `scheduler.py`, `views.py`, `urls.py`
- `apps/sms/management/commands/send_pending_sms.py`
- `apps/sms/management/commands/schedule_sms_reminders.py`
- `apps/sms/tests/test_sms_comprehensive.py` (~50 tests)
- `templates/sms/history.html` - SMS history page

**Modified Files:**
- `apps/users/models.py` - Added 15 SMS preference fields
- `templates/users/preferences.html` - Added SMS section with verification, toggles, quiet hours
- `config/settings.py` - Added Twilio settings and 'apps.sms' to INSTALLED_APPS
- `config/urls.py` - Added SMS URL include
- `requirements.txt` - Added `twilio>=9.0.0`
- `THIRD_PARTY_SERVICES.md` - Added Twilio documentation
- `CLAUDE_FEATURES.md` - Added SMS Text Notifications section

**Migrations:**
- `apps/users/migrations/0021_sms_notifications.py` - User preference fields
- `apps/sms/migrations/0001_sms_notifications.py` - SMS models

**Configuration (Environment Variables):**
- `TWILIO_ACCOUNT_SID` - Twilio account SID
- `TWILIO_AUTH_TOKEN` - Twilio auth token
- `TWILIO_PHONE_NUMBER` - Sender phone number (E.164)
- `TWILIO_VERIFY_SERVICE_SID` - Twilio Verify service SID
- `TWILIO_TEST_MODE` - Test mode (logs instead of sending)
- `SMS_TRIGGER_TOKEN` - Secret token for protected endpoints

**Test Mode:**
- When `TWILIO_TEST_MODE=True`, SMS are logged instead of sent
- Verification code `123456` is accepted in test mode

**Cost Estimates:**
- Phone Number: ~$1.15/month
- Outbound/Inbound SMS: ~$0.0079/message
- Phone verification: ~$0.05/verification

---

### Fix Medicine "Taken Late" Status When Taken Early

Fixed bug where medicines taken BEFORE the scheduled time were incorrectly marked as "Taken Late".

**Issue:**
- When a user in America/New_York (EST, UTC-5) took medicine at 8:24 AM local time with a 9:00 AM schedule, it was incorrectly marked "Taken Late"
- The root cause: the `mark_taken()` method was comparing UTC time (stored in database) against a naive local time
- Example: 8:24 AM EST = 1:24 PM UTC. When stripped of timezone, "1:24 PM" > "10:00 AM" (schedule + grace), so marked as late

**Fix:**
Updated three methods in `MedicineLog` model to properly convert times to user's timezone before comparison:

1. `mark_taken()` - Now converts `taken_at` (UTC) to user's local timezone before comparing with scheduled time
2. `was_on_time` property - Same timezone-aware comparison
3. `minutes_late` property - Same timezone-aware comparison

**Technical Details:**
- Uses `pytz.timezone(self.user.preferences.timezone)` to get user's timezone
- Converts `taken_at.astimezone(user_tz)` for UTC → local conversion
- Creates `scheduled_local = user_tz.localize(scheduled_dt)` for proper timezone-aware scheduled time
- Compares both timezone-aware datetimes correctly

**Files Modified:**
- `apps/health/models.py` - Updated `mark_taken()`, `was_on_time`, and `minutes_late` in `MedicineLog` class

**Related:** This is a companion fix to the earlier "Taken At" display fix. The display fix showed the correct time in the UI, but this fix ensures the status (Taken/Taken Late) is also correctly calculated.

---

### Medicine "Taken At" Time Now Displays in User's Timezone

Fixed medicine history showing "Taken Late" incorrectly because the `taken_at` time was being displayed in UTC instead of the user's configured timezone.

**Issue:**
- The `taken_at` field on MedicineLog is a DateTimeField stored in UTC
- When displayed in templates, Django's `time` filter was showing UTC time
- For users in America/New_York (EST/EDT, UTC-5), a medicine taken at 9:24 AM local time was showing as "1:24 PM" (UTC)
- This caused medicines taken on time to appear as "Taken Late"

**Fix:**
1. Added `user_timezone` to the theme context processor so templates can access the user's timezone
2. Used Django's `{% timezone %}` template tag to convert `taken_at` datetimes to user's local time
3. Updated both `medicine_detail.html` and `history.html` templates

**Files Modified:**
- `apps/core/context_processors.py` - Added `user_timezone` to template context
- `templates/health/medicine/medicine_detail.html` - Added `{% load tz %}` and wrapped `taken_at` in timezone tag
- `templates/health/medicine/history.html` - Added `{% load tz %}` and wrapped `taken_at` in timezone tag

**Technical Details:**
- The `scheduled_time` fields are stored as TimeField (no timezone), so they don't need conversion - they represent the desired local schedule time
- Only `taken_at` (DateTimeField stored in UTC) needed the timezone conversion

**Test Results:** 86 medicine tests pass

---

### Documentation Reorganization

Reorganized all project documentation files into a clean, consistent structure in the `docs/` directory.

**Changes Made:**
- Created `docs/` subdirectory for all project documentation
- Renamed all documentation files to follow consistent naming convention: `wlj_<category>_<descriptor>.md`
- Updated `CLAUDE.md` to reference new file locations
- Added `docs/README.md` as documentation index
- Deleted temporary artifact files (test_summary.txt, test_errors.txt, etc.)

**New Naming Convention:**
| Old Name | New Name |
|----------|----------|
| `CLAUDE_CHANGELOG.md` | `docs/wlj_claude_changelog.md` |
| `CLAUDE_FEATURES.md` | `docs/wlj_claude_features.md` |
| `CLAUDE_BEACON.md` | `docs/wlj_claude_beacon.md` |
| `BACKUP.md` | `docs/wlj_backup.md` |
| `BACKUP_REPORT.md` | `docs/wlj_backup_report.md` |
| `SECURITY_REVIEW_REPORT.md` | `docs/wlj_security_review.md` |
| `SYSTEM_AUDIT_REPORT.md` | `docs/wlj_system_audit.md` |
| `SYSTEM_REVIEW.md` | `docs/wlj_system_review.md` |
| `THIRD_PARTY_SERVICES.md` | `docs/wlj_third_party_services.md` |
| `docs/CAMERA_SCAN_ARCHITECTURE.md` | `docs/wlj_camera_scan_architecture.md` |

**Naming Convention Rules:**
- All files start with `wlj_` prefix
- Categories: `claude_*`, `backup_*`, `security_*`, `system_*`, `third_party_*`, `camera_*`
- Use lowercase with underscores
- Example: `wlj_claude_changelog.md`

**Files Kept at Root:**
- `CLAUDE.md` - Remains at root for Claude Code discovery
- `README.md` - Standard project README

**Temporary Files Deleted:**
- `test_summary.txt`
- `test_errors.txt`
- `app_diffs.txt`

---

*Last updated: 2026-01-01*
