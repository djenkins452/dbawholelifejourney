# ==============================================================================
# File: docs/wlj_claude_tasks.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Task queue for Claude to execute - errors, requests, app ideas
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

# WLJ Project Task Queue

**Claude is your Project Manager.** Just start a session and Claude will:
1. Give you a status summary
2. Show you what's ready to work on
3. Ask what you want to tackle
4. Execute the work and update this document

---

## Quick Start Commands

| Command | What Happens |
|---------|--------------|
| `"Read CLAUDE.md and continue"` | Full project context + status summary |
| `"What's the status?"` | Quick summary of task queue |
| `"Do the next task"` | Execute highest priority NEW task |
| `"Add task: [description]"` | Claude adds a new task to the queue |

---

## Current Status Summary

**Last Updated:** 2026-01-01
**Active Tasks:** 0 in progress
**Pending Tasks:** 0 ready to work
**Blocked Tasks:** 0 waiting

---

## Task Queue

### Priority Legend
- **HIGH** - Bugs, broken features, blocking issues
- **MEDIUM** - New features, enhancements users requested
- **LOW** - Ideas, nice-to-haves, future improvements

### Status Legend
- `NEW` - Ready to work on
- `IN_PROGRESS` - Started, may have phases remaining
- `COMPLETE` - Done and deployed
- `BLOCKED` - Cannot proceed (see notes)
- `CANCELLED` - No longer needed

---

### Active Tasks (IN_PROGRESS)

*None currently in progress*

---

### Ready to Work (NEW) - HIGH Priority

*No high priority tasks*

---

### Ready to Work (NEW) - MEDIUM Priority

*No medium priority tasks*

---

### Ready to Work (NEW) - LOW Priority

*No low priority tasks*

---

### Blocked Tasks

*No blocked tasks*

---

## Completed Tasks Archive

| Task | Category | Completed | Notes |
|------|----------|-----------|-------|
| TASK-000: Task Queue System | FEATURE | 2026-01-01 | Initial setup of this document |

---

## Task Template

When adding tasks, use this format:

```markdown
### TASK-XXX: [Brief Title]
- **Status:** NEW
- **Priority:** HIGH | MEDIUM | LOW
- **Category:** BUG | FEATURE | ENHANCEMENT | IDEA | REFACTOR
- **Added:** YYYY-MM-DD
- **Phases:** (if multi-phase, list them)
  1. Phase 1 description
  2. Phase 2 description
- **Description:**
  What needs to be done and why.
- **Acceptance Criteria:**
  - [ ] Criterion 1
  - [ ] Criterion 2
- **Notes:**
  Any context, links, or implementation hints.
```

---

## Session Log

| Date | Session Label | Tasks Worked | Outcome |
|------|---------------|--------------|---------|
| 2026-01-01 | New App Ideas/Fixes | Created PM workflow | COMPLETE |

---

## How Claude Manages This Project

### Starting a Session
When you say "Read CLAUDE.md and continue", Claude will:
1. Read this task queue
2. Summarize current status (active, pending, blocked)
3. List top 3 ready tasks by priority
4. Ask: "Which task would you like me to work on?"

### During a Task
- If the task has phases, Claude completes ONE phase at a time
- After each phase, Claude updates this document
- Claude asks: "Phase X complete. Continue to Phase Y, or save for next session?"

### After Completing a Task
- Claude updates status to COMPLETE
- Moves task to Completed Archive
- Updates the Status Summary section
- Commits and deploys to GitHub
- Asks: "What's next?" or suggests the next high-priority item

### Adding New Tasks
Just say: "Add task: [description]" and Claude will:
1. Create a properly formatted task entry
2. Assign a task number (TASK-XXX)
3. Ask about priority and category
4. Add acceptance criteria
5. Update this document and commit
