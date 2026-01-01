# ==============================================================================
# File: docs/wlj_claude_tasks.md
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Task queue for Claude to execute - errors, requests, app ideas
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================

# WLJ Claude Task Queue

This document serves as the central task queue for Claude Code sessions. Tasks are executed one at a time, in order, with status updates after each session.

## How to Use This Document

### For Danny (Adding Tasks)
1. Add new tasks to the **Task Queue** section below
2. Use the template provided for consistency
3. Assign a priority: `HIGH`, `MEDIUM`, or `LOW`
4. Tasks are executed in order (HIGH priority first, then by date added)

### For Claude (Executing Tasks)
1. **Read this document** at the start of each session when asked
2. **Find the first task** with status `NEW` or `IN_PROGRESS`
3. **Execute the task** completely (code, tests, documentation)
4. **Update the status** to `COMPLETE` with completion date and notes
5. **Deploy to GitHub** from main branch
6. **Update What's New** if user-facing changes

### Task Status Legend
- `NEW` - Not yet started
- `IN_PROGRESS` - Started but not complete (include notes on what's done)
- `COMPLETE` - Finished and deployed
- `BLOCKED` - Cannot proceed (include reason)
- `CANCELLED` - No longer needed (include reason)

---

## Task Queue

### Task Template
```
### TASK-XXX: [Brief Title]
- **Status:** NEW
- **Priority:** HIGH | MEDIUM | LOW
- **Category:** BUG | FEATURE | ENHANCEMENT | IDEA | REFACTOR
- **Added:** YYYY-MM-DD
- **Completed:** -
- **Description:**
  Detailed description of what needs to be done.
- **Acceptance Criteria:**
  - [ ] Criterion 1
  - [ ] Criterion 2
- **Notes:**
  Any additional context or implementation hints.
```

---

### TASK-001: [Example - Remove after adding real tasks]
- **Status:** NEW
- **Priority:** LOW
- **Category:** EXAMPLE
- **Added:** 2026-01-01
- **Completed:** -
- **Description:**
  This is an example task. Replace with real tasks.
- **Acceptance Criteria:**
  - [ ] Example criterion
- **Notes:**
  Delete this example when adding your first real task.

---

## Completed Tasks Archive

*Move completed tasks here to keep the active queue clean.*

---

## Session Log

*Brief log of Claude sessions working on this queue.*

| Date | Session | Tasks Worked | Outcome |
|------|---------|--------------|---------|
| 2026-01-01 | New App Ideas/Fixes | Created task queue system | COMPLETE |

---

## Quick Commands for Claude

When starting a session to work on tasks, say:
> "Read wlj_claude_tasks.md and execute the next task"

When adding a new task, say:
> "Add a new task to wlj_claude_tasks.md: [description]"

When checking status, say:
> "Show me the current task queue status"
