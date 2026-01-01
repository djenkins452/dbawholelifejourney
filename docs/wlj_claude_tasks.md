# ==============================================================================
# File: docs/wlj_claude_tasks.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Quick reference for Claude task workflow - Source of truth is Django Admin
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

# WLJ Project Task Workflow

## Source of Truth: Django Admin

**All tasks are managed in Django Admin:**
- URL: `/admin/admin_console/claudetask/`
- Model: `apps.admin_console.models.ClaudeTask`
- Management Command: `python manage.py task_status`

This markdown file is for quick reference only. The database is the source of truth.

---

## Quick Commands

| Command | What Happens |
|---------|--------------|
| `"Read CLAUDE.md and continue"` | Full project context + status summary |
| `"What's the status?"` | Quick summary from ClaudeTask database |
| `"Next item"` | Execute highest priority NEW task |
| `"Add task: [description]"` | Claude adds a task via admin |

---

## How "Next item" Works

When you say **"Next item"**, Claude will:

1. **Check for IN_PROGRESS tasks** - Must finish current work first
2. **Find highest priority NEW task:**
   - **HIGH Priority** (execute first):
     - Bugs, Security issues, Performance problems
   - **MEDIUM Priority** (execute second):
     - Features, Enhancements, Refactors, Maintenance
   - **LOW Priority** (execute last):
     - Ideas, Cleanup, Documentation
3. **Present the task** with description and acceptance criteria
4. **Ask**: "Should I proceed with this task?"
5. **Update status** to IN_PROGRESS when started
6. **Mark COMPLETE** when done
7. **Show next task** or confirm queue is empty

---

## Task Statuses

| Status | Meaning |
|--------|---------|
| `new` | Ready to work on |
| `in_progress` | Currently being worked on |
| `complete` | Done and deployed |
| `blocked` | Cannot proceed (see notes) |
| `cancelled` | No longer needed |

---

## Task Categories (Priority Order)

### HIGH Priority
1. **Bug** - Fix broken functionality
2. **Security** - Security improvements
3. **Performance** - Speed/efficiency issues

### MEDIUM Priority
4. **Feature** - New functionality
5. **Enhancement** - Improve existing feature
6. **Refactor** - Code restructuring
7. **Maintenance** - System upkeep

### LOW Priority
8. **Cleanup** - Remove unused code/files
9. **Documentation** - Docs updates
10. **Idea** - Future consideration

### Special Categories
- **ACTION REQUIRED** - User must do something (env vars, config, etc.)
- **REVIEW** - Claude completed work, user should verify

---

## Current Tasks (Query from Database)

To see current tasks, Claude can read from the database via Django ORM or the user can:
1. Visit Django Admin at `/admin/admin_console/claudetask/`
2. Filter by status (New, In Progress, Blocked)
3. Sort by priority and category

### Expected Tasks

The following Bible App tasks should be loaded via `load_bible_app_task`:

| Task ID | Title | Status |
|---------|-------|--------|
| TASK-001 | Bible App Phase 1: Bible Reading + Study Tools | Complete |
| TASK-002 | Bible App Phase 2: Prayer Prompts Before Bible Study | New |
| TASK-003 | Bible App Phase 3: Background Worship Music + Voice Narration | New |
| TASK-004 | Bible App Phase 4: Interactive Q&A / AI Help | New |
| TASK-005 | Bible App Phase 5: Learning Tools | New |
| TASK-006 | Bible App Phase 6: AR/Immersive Experiences | New |

---

## Multi-Phase Task Workflow

For complex tasks with multiple phases:

1. Claude reads the task and its phases from the database
2. Claude completes **ONE phase at a time**
3. After each phase, Claude asks: "Continue to next phase or save for later?"
4. Claude updates `current_phase` field as phases complete
5. Task marked COMPLETE only when all phases done

---

## Adding Tasks

### Via Django Admin (Preferred)
1. Go to `/admin/admin_console/claudetask/`
2. Click "Add Claude Task"
3. Fill in title, description, priority, category
4. Save

### Via Claude Session
Say: "Add task: [description]"
Claude will ask about priority and category, then create the task.

### Via Management Command (Bulk Loading)
For loading multiple predefined tasks:
```bash
python manage.py load_bible_app_task
```

---

## Session Log

Recent sessions and their outcomes:

| Date | Session Label | Tasks Worked | Outcome |
|------|---------------|--------------|---------|
| 2026-01-01 | Update Project Manager App | Task system review | Setup verified |
| 2026-01-01 | Bible App Updates | Phase 1 | COMPLETE |
| 2026-01-01 | New App Ideas/Fixes | Created PM workflow | COMPLETE |

---

## Management Commands

| Command | Purpose |
|---------|---------|
| `python manage.py task_status` | Show summary and next task |
| `python manage.py task_status --all` | Show all open tasks by priority |
| `python manage.py task_status --next` | Show only the next task |
| `python manage.py task_status --list` | List all tasks in table format |
| `python manage.py load_bible_app_task` | Load/reload Bible App tasks |

---

*For full project documentation, see `CLAUDE.md`*
*For feature details, see `docs/wlj_claude_features.md`*
*For change history, see `docs/wlj_claude_changelog.md`*
