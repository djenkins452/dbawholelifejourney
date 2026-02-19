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

**Testing:**
```bash
python manage.py test apps.health.tests.test_fitness -v 1 --failfast  # specific module
python manage.py test -v 1                                             # all tests
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

After ANY code changes:

1. **Changelog:** Append to `docs/wlj_claude_changelog.md` (date, changes, files, why)
2. **User-facing docs:** If feature/enhancement, see `docs/CLAUDE_DOC_UPDATES.md` for full checklist
3. **Deploy:**
   - Push branch: `GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git <branch>:<branch>`
   - Fetch: `GIT_SSH_COMMAND="ssh -p 443" git fetch git@ssh.github.com:djenkins452/dbawholelifejourney.git <branch>:refs/remotes/origin/<branch>`
   - Merge: `git checkout main && git merge origin/<branch> --no-edit`
   - Push main: `GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main`

**A task is NOT complete until deployed.**

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
