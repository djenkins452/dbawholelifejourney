---
name: "source-command-run-task"
description: "Migrated source command `run-task`"
---

# source-command-run-task

Use this skill when the user asks to run the migrated source command `run-task`.

## Command Template

# Execute the current in-progress task(s)

model: sonnet

## Context Loading

Read AGENTS.md to load project context (it's now slim - ~120 lines).

## Fetch In-Progress Tasks

```bash
curl -s -H "X-Codex-API-Key: $WLJ_CLAUDE_API_KEY" "https://wholelifejourney.com/admin-console/api/Codex/ready-tasks/?limit=10&include_in_progress=true"
```

If no tasks found (neither ready nor in_progress), report "No tasks available."

## Parallel Execution

If multiple tasks are in_progress at the same phase+priority:
- Execute them in PARALLEL using Task tool with multiple agents
- Each agent handles one task independently
- Wait for all to complete before proceeding

## Run Task Mode Execution (per task)

1. **Validate** task has: objective, inputs, actions, output
2. **Check for attachment** - if task has `attachment_url`, use the Read tool to view the image
3. **Gather inputs** - read any files mentioned
4. **Execute actions** - in order, exactly as written
5. **Run tests** if code was changed: `python manage.py test`
6. **Verify output** criteria is met

## On Failure

- HALT that task immediately
- Log which step failed
- Do NOT mark task as done
- Continue with other parallel tasks if any
- Report all errors to user at end

## On Success (per task)

1. **Mark task done:**
```bash
curl -s -X POST -H "X-Codex-API-Key: $WLJ_CLAUDE_API_KEY" -H "Content-Type: application/json" -d '{"status": "done"}' "https://wholelifejourney.com/admin-console/api/Codex/tasks/<ID>/status/"
```

## After All Parallel Tasks Complete

1. **Append to changelog** - single entry covering all completed tasks
2. **Commit changes** with descriptive message
3. **Merge to main** and push to deploy
4. **Auto-continue**: Immediately run `/next` to get next batch

## Authority

Full authority granted - execute without asking questions.
Minimal interaction - just do the work and report results.
