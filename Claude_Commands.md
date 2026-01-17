# Claude Code Slash Commands

Quick reference for all available slash commands in this project.

---

## Task Management

| Command | Purpose |
|---------|---------|
| `/next` | Fetch next ready task(s) from the API and mark as in_progress |
| `/run-task` | Execute the current in-progress task(s) with full context |

## Utilities

| Command | Purpose |
|---------|---------|
| `/troubleshoot` | Match an error to known issues in `docs/wlj_claude_troubleshoot.md` |
| `/log-change <desc>` | Append an entry to `docs/wlj_claude_changelog.md` |
| `/process-emails` | Manually trigger email intake processing |
| `/close` | Close out the current coding session |

---

## Command Details

### `/next`
Fetches up to 10 ready tasks from the API. Tasks at the same phase and priority are fetched together for parallel execution. Automatically marks fetched tasks as `in_progress`.

### `/run-task`
Executes all in-progress tasks. For multiple tasks at the same phase/priority, runs them in parallel using agents. After completion:
1. Updates the changelog
2. Commits changes
3. Merges to main and pushes to deploy
4. Automatically runs `/next` to get the next batch

### `/troubleshoot`
When you encounter an error, run this command. It searches `docs/wlj_claude_troubleshoot.md` for known issues and solutions.

### `/log-change <description>`
Appends a dated entry to the changelog. Use after making any code changes.

Example: `/log-change Fixed honeypot validation in signup form`

### `/process-emails`
Manually triggers the email intake system to check for new emails in the Automate folder and create tasks from them.

### `/close`
Wraps up the current session - commits any pending changes, updates documentation, and provides a summary.

---

*Last updated: 2026-01-17*
