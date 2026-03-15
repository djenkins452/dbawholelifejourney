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

**Observability Performance — Never Compute on Request Path (CRITICAL):**
All heavy analytics (maturity scores, signal health, validator health, CoS performance, complexity scores) MUST run in background workers (SAME cycle / Celery tasks). HTTP request paths (views, polling endpoints, evidence/scan APIs) may ONLY read pre-computed data from cache or DB snapshots. If snapshot data is not yet available, return a "pending" state — **NEVER fall back to live computation**. This rule exists because:
- `compute_system_life_impact()` runs 600+ queries (200 users × domains)
- `compute_signal_health()` runs ~24 queries per call
- Gunicorn has only 2–4 workers; one slow request blocks the entire site
- Live fallbacks caused repeated 524 Cloudflare timeouts in production (2026-03-15)

The correct pattern for any `_get_*()` cache-reader function:
```python
def _get_expensive_metric():
    cached = cache.get("wlj:ops:metric_key")
    if cached is not None:
        return cached
    return None  # NEVER: return compute_expensive_metric()
```
Background population (SAME cycle, every 60s):
```
compute → write DB snapshot (for history) → update cache (for real-time display)
```

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

**New Intent Checklist (REQUIRED when adding any CoS intent):**
Every new intent touches 5+ files. Missing any one causes a silent runtime failure. After adding an intent, **always run the registration gate tests BEFORE deploying**:
```bash
python manage.py test apps.ai.tests.test_intent_registration -v 2 --failfast
```
The 5-point registration:
1. **Tool definition** — `apps/ai/intents/<category>_intents.py` (OpenAI function schema)
2. **Handler map** — `apps/ai/intents/__init__.py` → `INTENT_HANDLERS` dict
3. **Engine category** — `apps/core/ai_orchestrator/intent_engine.py` → add to the correct `*_INTENTS` set
4. **Execute dispatcher** — `apps/ai/intent_service.py` → add `elif` branch in `execute_intent()`
5. **Action handler** — `apps/ai/action_handlers.py` → add `handle_<intent_name>()` method
6. **System prompt examples** — `apps/ai/intent_service.py` → `_build_intent_system_prompt()` examples
7. **Time awareness** — If the intent has NO date/time component, add to `NON_TIME_INTENTS` in `apps/ai/tests/test_intent_registration.py`

**Calculation reuse rule:** When the handler needs a metric that already exists in a `*_utils.py` module (e.g., adherence, streaks), use the existing utility function — never re-derive the calculation inline. Inline re-derivation causes drift (e.g., log-based vs schedule-based adherence).

---

## Reference Docs (Read On-Demand)

| Doc | When to Read |
|-----|-------------|
| `docs/ENGINE_COS_REFERENCE.md` | **Engine/CoS changes — AUTO-MAINTAIN (see below)** |
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

## Auto-Maintain: Engine & CoS Reference (REQUIRED)

**When you modify ANY of these areas, update `docs/ENGINE_COS_REFERENCE.md` to reflect the change:**

- Engine files (`apps/core/ai_*/`, `apps/core/blueprint/`)
- CoS context builder (`apps/core/ai_orchestrator/cos_context.py`)
- Proactive check-ins (`apps/ai/proactive_checkins.py`, `apps/ai/assistant_intelligence.py`)
- Celery Beat schedule (`config/settings.py` CELERY_BEAT_SCHEDULE)
- ISE scheduler registry (`apps/core/ai_scheduler/scheduler_registry.py`)
- Intelligence models (Insight, Prediction, GuidanceItem, UserState)
- SAE state builders (`apps/core/ai_state/state_builder.py`)
- Chat pipeline (`apps/ai/personal_assistant.py :: send_message()`, `apps/ai/views.py`)

**What to update in the doc:**
- Engine inventory table (new/renamed/removed engines)
- Schedule tables (changed intervals or new scheduled tasks)
- CoS context pipeline (new builders, changed data sources, new cache keys)
- Known bugs section (new bugs found, bugs fixed — mark as FIXED with date)
- Key file paths (new files, renamed files)
- Update the "Last updated" date at the top

---

*Last updated: 2026-03-05*
