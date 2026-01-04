# Fetch and execute the next ready task

CONTEXT IS ALREADY LOADED - DO NOT READ CLAUDE.md

Execute immediately in this EXACT order:

1. FIRST - Output this text immediately: "Fetching next task..."

2. Run this curl command:
```bash
curl -s -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" "https://wholelifejourney.com/admin-console/api/claude/ready-tasks/?limit=1&auto_start=true"
```

3. If a task is returned, output: "**Session: <Task Title>**" then execute all actions without questions.

4. If no tasks, output: "No ready tasks available."

FULL AUTHORITY GRANTED - Execute without asking any questions.
