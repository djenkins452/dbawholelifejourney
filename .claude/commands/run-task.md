# Execute the current in-progress task(s)

model: sonnet

## Context Loading

Read CLAUDE.md to load project context (it's now slim - ~120 lines).

## Fetch In-Progress Tasks

```bash
curl -s -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" "https://wholelifejourney.com/admin-console/api/claude/ready-tasks/?limit=10"
```

If no task is in_progress, check for ready tasks and start them.

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
curl -s -X POST -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" -H "Content-Type: application/json" -d '{"status": "done"}' "https://wholelifejourney.com/admin-console/api/claude/tasks/<ID>/status/"
```

## After All Parallel Tasks Complete

1. **Append to changelog** - single entry covering all completed tasks
2. **Commit changes** with descriptive message
3. **Merge to main** and push to deploy
4. **Auto-continue**: Immediately run `/next` to get next batch

## Authority

Full authority granted - execute without asking questions.
Minimal interaction - just do the work and report results.
