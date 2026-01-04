# WLJ Claude Code Slash Commands

Custom slash commands for the Whole Life Journey project.

## Available Commands

### /next
**Purpose:** Fetch the next ready task from the API
**Model:** Default
**Usage:** `/next`
**Actions:**
- Fetches ready task with `auto_start=true` (marks as in_progress)
- Displays task title, objective, and actions
- Prompts to run `/run-task` for full execution

### /run-task
**Purpose:** Execute the current in-progress task with full context
**Model:** Sonnet
**Usage:** `/run-task`
**Actions:**
- Reads slim CLAUDE.md for context
- Validates task structure
- Executes all actions in order
- Runs tests if code changed
- Commits, merges to main, pushes
- Marks task as done
- Appends to changelog

### /troubleshoot
**Purpose:** Diagnose a problem using known issues database
**Model:** Haiku
**Usage:** `/troubleshoot` (then describe the error)
**Actions:**
- Reads troubleshooting guide
- Matches error to known issues
- Provides documented solution

### /log-change
**Purpose:** Add an entry to the changelog
**Model:** Haiku
**Usage:** `/log-change <description>`
**Example:** `/log-change Added auto_start parameter to ready-tasks API`
**Actions:**
- Appends formatted entry to docs/wlj_claude_changelog.md

## Typical Workflow

1. `/next` - See what's ready to work on
2. `/run-task` - Execute the task with full context
3. (Automatic) - Changelog updated on completion

## Troubleshooting Workflow

1. Encounter an error
2. `/troubleshoot` - Describe the error
3. Get solution from known issues database

## Command Files

All commands are in `.claude/commands/`:
- `next.md`
- `run-task.md`
- `troubleshoot.md`
- `log-change.md`
- `README.md` (this file)
