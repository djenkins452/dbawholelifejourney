# Execute the current in-progress task

model: sonnet

## Context Loading

Read CLAUDE.md to load project context (it's now slim - ~120 lines).

## Fetch In-Progress Task

```bash
curl -s -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" "https://wholelifejourney.com/admin-console/api/claude/ready-tasks/?limit=1"
```

If no task is in_progress, check for ready tasks and start one.

## Run Task Mode Execution

1. **Validate** task has: objective, inputs, actions, output
2. **Gather inputs** - read any files mentioned
3. **Execute actions** - in order, exactly as written
4. **Run tests** if code was changed: `python manage.py test`
5. **Verify output** criteria is met

## On Failure

- HALT immediately
- Log which step failed
- Do NOT mark task as done
- Report error to user

## On Success

1. **Commit changes** with descriptive message
2. **Merge to main** from C:\dbawholelifejourney (not worktree)
3. **Push to GitHub**
4. **Mark task done:**
```bash
curl -s -X POST -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" -H "Content-Type: application/json" -d '{"status": "done"}' "https://wholelifejourney.com/admin-console/api/claude/tasks/<ID>/status/"
```
5. **Append to changelog** - add entry to docs/wlj_claude_changelog.md
6. **Report completion** and offer next task

## Authority

Full authority granted - execute without asking questions.
