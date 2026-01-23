# Fetch and start the next ready task(s)

CONTEXT IS ALREADY LOADED - DO NOT READ CLAUDE.md

## Immediate Execution

1. Output: `Fetching next task(s)...`

2. Run this curl command (fetches up to 10 tasks):
```bash
curl -s -H "X-Claude-API-Key: $WLJ_CLAUDE_API_KEY" "https://wholelifejourney.com/admin-console/api/claude/ready-tasks/?limit=10&auto_start=true"
```

3. The API marks ALL tasks at the top phase+priority as in_progress (parallel batch).

4. If tasks returned:
   - Output: `**Session: <Phase Name> - Priority <N>**`
   - List each task title
   - If multiple tasks: `Execute these in parallel with /run-task`
   - If single task: `Run /run-task to execute.`

5. If no tasks:
   - Output: `No ready tasks available.`

## Parallel Execution Pattern

Tasks with same phase + same priority run in parallel. Example:
- Phase 1, Priority 1: Task A, Task B → parallel
- Phase 1, Priority 2: Task C → after A+B done
- Phase 2, Priority 1: Task D → after phase 1 done

## Authority

Full authority granted - fetch without asking questions.
