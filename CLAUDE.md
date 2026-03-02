# Whole Life Journey — Claude Code Instructions

**Project:** Django 5.x personal wellness/journaling app
**Repo:** GitHub: djenkins452/dbawholelifejourney

---

## Behavior Rules

**Do NOT ask permission for:** reading files, searching, grepping, running tests/migrations, making commits, deploying.

**Ask permission for:** destructive operations (deleting files, dropping tables), genuinely ambiguous or risky actions.

**Task Discussion Flow** (when fetching tasks from backlog):
1. Present the task and explore as needed
2. Discuss scope and approach
3. **Wait for "go"** — do NOT implement until user says "go"

**Communication:** Be direct, skip "Would you like me to...", execute don't propose, summarize results not intentions.

**Auto-fix rule:** Fix broken/non-compliant code (CSP violations, quality issues) when you encounter it in files you're touching.

**Conserve limits:** Keep responses concise. Batch changes. Use Task/Explore agent for broad searches. Warn before high-token operations.

---

## Tech Stack & Architecture

- Django 5.x, django-allauth | PostgreSQL (prod) / SQLite (dev)
- Railway deployment with Nixpacks | Gunicorn WSGI
- OpenAI API for AI features | iOS app: Swift/SwiftUI wrapper
- **Apps:** users, core, dashboard, journal, faith, health, purpose, ai, life, admin_console, help, scan, mobile, medical, billing, brain_training, capture, finance, security, sms
- **User model:** Custom User (email-based auth) | UserPreferences for settings
- **Soft deletes:** Models use `soft_delete()`, not hard deletes. See `docs/wlj_claude_troubleshoot.md` #7 for SoftDeleteManager pattern

---

## Intelligence Architecture

The app uses a three-phase intelligence pipeline: **Interpretation → Execution → Post-Execution** with 14 engines. When working on AI, data logging, insights, predictions, or user interaction features, **read these docs first:**

- `docs/INTELLIGENCE_ARCHITECTURE.md` — Engine inventory, pipeline, contracts
- `docs/DOMAIN_INTELLIGENCE_ARCHITECTURE.md` — Per-module integration map
- `docs/ENGINE_INTEGRATION_GUIDE.md` — Step-by-step integration patterns

New features must integrate with the correct phase. New data-logging features must fire PIE events and PRIE predictions.

---

## CSP Compliance (REQUIRED)

Nonce-based CSP. Browsers ignore `'unsafe-inline'` when nonce is present.

- **NEVER** use inline event handlers (`onclick`, `onchange`, `onsubmit`, etc.) — silently blocked
- **ALWAYS** use `addEventListener()` inside `<script nonce="{{ csp_nonce }}">`
- For dynamic elements, use event delegation on parent/document
- Derive context from `data-*` attributes, not function arguments

---

## Responsive Design (REQUIRED)

Mobile: `max-width: 480px` | Tablet: `max-width: 768px` | Desktop: `min-width: 769px`

- Mobile-friendly defaults first, `@media` queries for larger screens
- Touch targets ≥ 44x44px, `font-size: 16px` min on inputs (iOS zoom prevention)
- No fixed widths — use `max-width`, `%`, or `vw`
- Verify layouts work at 375px width (iPhone SE)

---

## Quick Reference

| Item | Value |
|------|-------|
| **Task API** | `GET /admin-console/api/claude/ready-tasks/?auto_start=true` |
| **Task Status** | `POST /admin-console/api/claude/tasks/<id>/status/` |
| **API Key Header** | `X-Claude-API-Key: $WLJ_CLAUDE_API_KEY` |
| **Test Count** | ~4,400 tests |
| **Git Push** | `GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main` |

**Testing (IMPORTANT — scoped tests only):**
- **NEVER run the full test suite** (`python manage.py test`) unless the user explicitly asks for it
- **ONLY test what you changed** and modules that could be directly impacted
- ~4,400 tests take a very long time — running them all wastes time and blocks other sessions

```bash
python manage.py test apps.health.tests.test_fitness -v 1 --failfast  # specific module
python manage.py test apps.health apps.journal -v 1 --failfast        # multiple affected apps
python manage.py check                                                 # check for issues
```
**Migrations:** `python manage.py makemigrations && python manage.py migrate`

**Troubleshooting:** Read `docs/wlj_claude_troubleshoot.md` FIRST. Common issues: property shadowing, migration state, Nixpacks caching, test user onboarding, CSRF origins, SoftDeleteManager filtering.

---

## Task Standard

AdminTask `description` fields must be JSON: `{"objective": "...", "inputs": [...], "actions": [...], "output": "..."}`

**Run Task Contract:** Validate → Execute actions in order → Verify output → Mark `done` only on success. On failure: HALT, do NOT mark complete.

---

## On Task Completion

**EVERY commit — no matter how small — MUST include a changelog entry. No exceptions. Even one-line bug fixes get logged. This is non-negotiable.**

After ANY changes (code, docs, or config), do ALL of the following **automatically without asking**:

1. **Changelog (REQUIRED, EVERY COMMIT):** Append to `docs/wlj_claude_changelog.md` (date, changes, files, why)
2. **User-facing docs (MANDATORY for features/enhancements):** Update ALL of the following. See `docs/CLAUDE_DOC_UPDATES.md` for full checklist.
   - **Release notes** (`apps/core/fixtures/release_notes.json`) — user-facing What's New entry
   - **Help topics** (`apps/help/fixtures/help_topics.json`) — if new page has `help_context_id`
   - **Teaching destinations** (`apps/help/fixtures/teaching_destinations.json`) — if new navigable page
   - **Features doc** (`docs/wlj_claude_features.md`) — if major feature, add/update section + ToC
   - **Fixture loader reset** (`apps/core/management/commands/load_initial_data.py`) — if any fixture modified
3. **Commit & Deploy** — do this immediately, never ask "ready to deploy?":
   - Commit all changed files with a descriptive message
   - **ALWAYS merge to main and push main** — never leave changes only on a feature/worktree branch:
     - If on a worktree branch: `cd /Users/dannyjenkins/Projects/dbawholelifejourney && git merge <branch-name>` then push main
     - Push main: `GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main`
   - **DO NOT** push only to the worktree branch — that does NOT deploy. Main must be pushed.

**A task is NOT complete until main is pushed to GitHub. Deploy automatically — never wait for permission.**

4. **Post-Completion Summary** — After deploying, always provide a brief summary:
   - **Root cause:** What was wrong and why
   - **Changes:** Files modified and approach taken
   - **Verification:** Tests run and results

---

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/next` | Fetch next ready task, mark in_progress |
| `/run-task` | Execute task with full context, auto-changelog |
| `/troubleshoot` | Match error to known issues |
| `/log-change <desc>` | Append entry to changelog |
| `/close` | End-of-session review |
| `/process-emails` | Check Automate folder, create tasks from emails |

---

## "What's Next?" Protocol

1. Run curl with `auto_start=true`
2. Show task title, objective, and actions
3. Output: `Run /run-task to execute.`
4. Do NOT execute automatically — wait for user.

---

## AI Engineering Rules (REQUIRED)

These rules prevent the silent-failure and schema-drift bugs that have caused production outages.

**Exception Handling — Never Swallow Errors:**
- **NEVER** use `except Exception: pass` on critical paths (intent recognition, execution, safety gates). This hides real errors and causes silent functional loss.
- **Separate `ImportError` from `Exception`:** Use `except ImportError: pass` for optional modules (expected), then `except Exception: logger.error(...)` for real errors (must be visible).
- **Fail-closed safety gates:** Safety gates (Learning Mode, validator) that catch all exceptions and `pass` fail *open* — they silently bypass the safety check. Always log and re-raise or return a safe default.
- **Log level matters in production:** `logger.debug()` is invisible in production. Critical-path failures need `logger.warning()` or `logger.error()` with `exc_info=True`.

**Schema Parity — Model ↔ Intent ↔ Handler:**
- When a Django model has a user-settable field, the AI intent schema (`apps/ai/intents/`) and the action handler (`apps/ai/action_handlers.py`) MUST both support that field.
- When adding a field to a model, also add it to: (1) the OpenAI function schema, (2) the handler method signature and logic, (3) the system prompt examples.
- When modifying intent schemas, verify the handler accepts the new parameter and maps it to the correct model field name (e.g., schema `end_time` → model `scheduled_end_time`).
- Time range patterns ("5pm - 6pm") must extract BOTH start and end times — never silently drop one.

**Streaming vs Non-Streaming Parity:**
- The web UI uses two paths: `/api/chat/` (non-streaming) and `/api/chat/stream/` (SSE streaming). Both must call the same orchestrator pipeline. Any fix to one path must be verified on the other.

---

## Reference Docs (Read On-Demand)

| Doc | When to Read |
|-----|-------------|
| `docs/INTELLIGENCE_ARCHITECTURE.md` | AI/intelligence feature work |
| `docs/DOMAIN_INTELLIGENCE_ARCHITECTURE.md` | AI/intelligence feature work |
| `docs/ENGINE_INTEGRATION_GUIDE.md` | Wiring new features into engines |
| `docs/CLAUDE_DOC_UPDATES.md` | After completing features/enhancements |
| `docs/CLAUDE_IOS.md` | iOS app / mobile API work |
| `docs/CLAUDE_BIBLE_PLANS.md` | Bible reading plan work |
| `docs/wlj_claude_troubleshoot.md` | When something isn't working (CHECK FIRST) |
| `docs/wlj_claude_deploy.md` | Deployment issues |
| `docs/wlj_claude_features.md` | Feature documentation |
| `docs/improvement_tasks.md` | Improvement backlog |
| `docs/ios-healthkit-integration.md` | HealthKit technical details |
| `docs/ios-app-store-submission.md` | App Store submission guide |

---

*Last updated: 2026-02-19*
