# Whole Life Journey - Claude Code Context

**Project:** Django 5.x personal wellness/journaling app
**Repo:** C:\dbawholelifejourney | GitHub: djenkins452/dbawholelifejourney

---

## Quick Reference

| Item | Value |
|------|-------|
| **API Key** | `a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1` |
| **Ready Tasks** | `GET /admin-console/api/claude/ready-tasks/?auto_start=true` |
| **Update Status** | `POST /admin-console/api/claude/tasks/<id>/status/` |
| **Test Count** | 1395 tests |
| **Push From** | Main repo (C:\dbawholelifejourney), NOT worktrees |

**Commands:**
```bash
# Fetch next task (marks as in_progress automatically)
curl -s -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" "https://wholelifejourney.com/admin-console/api/claude/ready-tasks/?limit=1&auto_start=true"

# Mark task done
curl -s -X POST -H "X-Claude-API-Key: a3f8b2c9d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1" -H "Content-Type: application/json" -d '{"status": "done"}' "https://wholelifejourney.com/admin-console/api/claude/tasks/<ID>/status/"

# Run tests
python manage.py test
```

---

## Tech Stack

- Django 5.x with django-allauth | PostgreSQL (prod) / SQLite (dev)
- Railway deployment with Nixpacks | Gunicorn WSGI
- OpenAI API for AI coaching features

## Key Architecture

- **Apps:** users, core, dashboard, journal, faith, health, purpose, ai, life, admin_console, help, scan
- **User model:** Custom User (email-based auth) | UserPreferences for settings
- **Soft deletes:** Models use `soft_delete()` method, not hard deletes

---

## Reference Documentation

| Doc | Purpose |
|-----|---------|
| `.claude/commands/README.md` | **Slash commands** (`/next`, `/run-task`, `/troubleshoot`, `/log-change`) |
| `docs/wlj_claude_troubleshoot.md` | Known issues & solutions (CHECK FIRST) |
| `docs/wlj_claude_deploy.md` | Railway deployment, Nixpacks, migrations |
| `docs/wlj_claude_features.md` | Feature documentation (AI, scan, health) |
| `docs/wlj_claude_changelog.md` | Historical changes and fixes |
| `docs/wlj_third_party_services.md` | External service inventory |

## Slash Commands

| Command | Model | Purpose |
|---------|-------|---------|
| `/next` | Default | Fetch next ready task, mark in_progress |
| `/run-task` | Sonnet | Execute task with full context, auto-changelog |
| `/troubleshoot` | Haiku | Match error to known issues |
| `/log-change <desc>` | Haiku | Append entry to changelog |

---

## Executable Task Standard

All AdminTask `description` fields MUST be JSON with these keys:

```json
{
    "objective": "What the task should accomplish",
    "inputs": ["Required context (can be empty [])"],
    "actions": ["Step 1", "Step 2 (at least one required)"],
    "output": "Expected deliverable"
}
```

**Validation:** All 4 fields required. Empty objective/output/actions = FAIL.

---

## Run Task Mode Contract

When executing tasks from the API:
1. **Context:** CLAUDE.md is already loaded (don't re-read)
2. **Validate:** Task has objective, inputs, actions, output
3. **Execute:** Actions in order, exactly as written
4. **Verify:** Output criteria met
5. **Complete:** Mark `done` only on full success

**On failure:** HALT, log error, do NOT mark complete.

---

## When Something Isn't Working

**READ FIRST:** `docs/wlj_claude_troubleshoot.md`

Common issues: property shadowing fields, migration state, Nixpacks caching, test user onboarding, CSRF origins, PostgreSQL schema checks.

---

## On Task Completion

After ANY code changes, append to `docs/wlj_claude_changelog.md`:
- Date, what changed, files modified, why
- Include migration names if created

---

## "What's Next?" Protocol

Use `/next` slash command or say "What's Next?"

1. Output: `Fetching next task...`
2. Run curl with `auto_start=true`
3. Output: `**Session: <Task Title>**`
4. Execute all actions without asking
5. Run tests if code changed
6. Commit, merge to main, push
7. Mark task `done`
8. Offer next task

**DO NOT:** Read CLAUDE.md again, ask permission, ask clarifying questions.

---

*Last updated: 2026-01-04*
