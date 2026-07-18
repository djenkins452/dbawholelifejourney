# Whole Life Journey — Claude Code Instructions

**Project:** Django 5.x personal wellness/journaling app
**Repo:** GitHub: djenkins452/dbawholelifejourney

> **⭐ START HERE — drag in ONE folder:** `@WLJ_SYSTEM_PROMPTS/00_WLJ_CHIEF_OF_STAFF_STARTUP/` is the
> self-contained onboarding package for every session. Read `00_NEXT_CHAT_STARTUP.md` first (the transient
> bootloader: current sprint/priorities; the one temporary file), then the six evergreen docs it points to:
> `01` architecture (WHAT), `02` Constitution (WHAT MUST NOT CHANGE), `03` engineering guide (HOW TO BUILD
> SAFELY), `04` Danny preferences (HOW TO WORK WITH DANNY), `98` session transition (HOW TO CLOSE A CHAT),
> `99_REFERENCE_INDEX` (WHERE EVERYTHING IS). The **WLJ Constitution** (canonical: `02_WLJ_CONSTITUTION.md`;
> `docs/WLJ_CONSTITUTION.md` is a pointer) is the apex architecture doc — any change to a constitutional
> Article requires a **Constitutional Review** (default NO; Danny's explicit written approval).
> At the **end** of a chat, run `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md` (kept outside the folder) to
> fold durable knowledge up into the package and regenerate the bootloader.

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

**PRODUCT VISION (REQUIRED — the governing "why"): WLJ is a Personal Truth Platform, not an AI.** `docs/WLJ_PRODUCT_VISION.md` is the highest-level document in the repo — every architecture decision is measured against it. WLJ owns the deterministic truth of a person's life; the conversational model reasons over it. Users choose a *default relationship* with their AI (Chief of Staff, Best Friend, Coach…), not which AI they get. "The model reasons. WLJ knows." **Simplicity is a core engineering principle:** before building anything in WLJ, ask "can the conversational model already do this well?" — if yes, don't build it; improve the *truth* available instead. Build deterministic code only where correctness, safety, permissions, auditability, calculations, history, deterministic policy, or action execution require it. As frontier models improve, WLJ gets SIMPLER, not more complex. Read the vision before the architecture docs below.

**ARCHITECTURE (REQUIRED — read first): WLJ owns truth; the conversational model owns reasoning.** WLJ is the deterministic personal truth, preference, history, and action platform underneath a frontier conversational model. **Do NOT build a reasoning engine inside WLJ.** The model drives the turn and requests truth/actions from WLJ; WLJ answers deterministically, exposes truth as composed briefings (never raw signals), executes actions through the safe path, and audits every request. The provider (currently OpenAI) is config behind one seam — **never name a provider, or any assistant name like "Beth," as a system identity** ("Beth" is only one user's chosen display name). Governing contract: `docs/WLJ_LLM_TRUTH_ACTION_CONTRACT.md`.

**PRODUCT is the North Star (REQUIRED — read before the development model):** The only success metric is: *"If this were the only conversation a paying customer ever had with their assistant, would they immediately want to use it again tomorrow?"* Elegant architecture, a correct tool call, a clean handler — none of that is the product; the customer experiences **trust**, not layers. EVERY production transcript begins with a **Product Review BEFORE the Architecture Review**, in this order: (1) Would a paying customer trust this conversation? (2) If not, why — in customer terms (it contradicted itself / forgot / answered the wrong question)? (3) Only THEN, which architectural layer caused it. Never the reverse. Trust-breakers are fixed one at a time, wherever they live (most often Layer 1 truth or Layer 4 experience), ranked by trust impact. **As Chief Architect, call it out plainly when engineering is improving but the product experience is not.**

**Development model (REQUIRED):** For ANY production issue in an assistant / Chief-of-Staff surface, FIRST classify which architectural layer failed — **Truth (WLJ) → Reasoning (the conversational model) → Action (WLJ) → Experience** — and fix the first layer that failed (diagnose top-down). Most fixes are Layer 1: WLJ returned wrong or badly-composed truth. **Do NOT build WLJ reasoning** — a reasoning miss is fixed by giving the model better truth delivery, executive context, a truth/action tool, or a corrected AI Relationship, never by writing a bespoke WLJ capability (the retired approach). A genuine gap is filled as *truth or an action tool*, never as a mind. Governing doc: `docs/WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md` (reframed to this model).

**Eliminate the CLASS, don't detect the symptom (REQUIRED — the default question before any trust-fix):** When a production conversation exposes a trust-breaking failure, do NOT ask "how do we catch/recover from this next time?" Ask: **(1) Does this represent an entire CLASS of failures? (2) What architectural condition makes that class possible? (3) Can we REMOVE that condition instead of detecting its symptoms?** Removing the condition (so the whole class becomes structurally impossible) is almost always preferred over adding another detector, validator, recovery path, or capability. Precedent: we did not "fix" *"6:15 AM tonight"* — we removed the condition that let one sentence be assembled from two independent time sources, killing the class. **Bound by blast radius:** prefer elimination, but when removing the condition would require a disproportionate redesign or destabilize working paths, contain the class as narrowly as possible and LOG the residual — never force a risky rewrite. Only when elimination is genuinely impractical do we fall back to a localized capability/detector.

**Production debugging (REQUIRED):** For ANY "the app shows X but should show Y" bug, follow `docs/WLJ_RUNTIME_TRACE_DEBUGGING.md`. **Never modify code until you have PROVEN (not guessed) that it executed on the request that produced the behavior.** Trace Browser→HTML→Template→View→Composer→Builder→DB; find ALL producers (persisted object vs live composer are different!); build a glass-box debug endpoint if ownership is unclear; verify five-way agreement (DB→Object→Composer→Template→Browser). A passing unit test is NOT proof.

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

## Vendored Static Assets (REQUIRED)

Whenever you vendor a new JS/CSS library into WLJ (self-host a third-party asset under `static/`), **run the production collectstatic pipeline locally BEFORE pushing:**

```bash
python3 manage.py collectstatic --noinput   # prod path: WhiteNoise CompressedManifestStaticFilesStorage
```

Prod's `CompressedManifestStaticFilesStorage` post-processes JS `sourceMappingURL` comments and CSS `url()` / `@import` references and **fails hard on any missing target**. Running it locally catches — before Railway ever sees it — **missing source maps, missing fonts, missing images, bad CSS `url()` references, and WhiteNoise manifest issues**. Fix by removing the dangling reference (e.g. strip a `//# sourceMappingURL=…` comment) or shipping the referenced file (the font/image/map). It must report `… copied, … post-processed` with **0 errors**. (Origin: vendored Leaflet's missing `leaflet.js.map` + `images/*.png` broke a deploy twice.)

---

## Responsive Design (REQUIRED)

Mobile: `max-width: 480px` | Tablet: `max-width: 768px` | Desktop: `min-width: 769px`

- Mobile-friendly defaults first, `@media` queries for larger screens
- Touch targets ≥ 44x44px, `font-size: 16px` min on inputs (iOS zoom prevention)
- No fixed widths — use `max-width`, `%`, or `vw`
- Verify layouts work at 375px width (iPhone SE)

---

## Visual Truth Contract (REQUIRED)

> **Only actual user completion may visually resemble completion.**

Strike-through, "completed" colours, heavy opacity reduction, filled checkmarks, and any other visual that reads as "done" are RESERVED exclusively for items where the data layer confirms `item.completed == True` (or the domain-equivalent boolean — `is_completed`, `taken`, `all_complete`, etc.).

Past-window / behind / missed / recoverable / overdue items may use badges, muted text, subtle dimming (opacity 0.70–0.90), or left-rail colour — NEVER completion-resembling visuals.

Enforced by `apps/core/tests/test_visual_truth_contract.py`. Full rule and rationale in `docs/WLJ_VISUAL_TRUTH_CONTRACT.md` (incident origin: 2026-05-20).

---

## Current Context — every page is Beth-aware (REQUIRED)

> **Every WLJ page declares its Current Context. There are exactly two patterns — pick by page kind.**

When you build or touch ANY page, ask **"what is the user looking at here, deterministically?"** and declare it. Two — and only two — patterns:

1. **Detail page → a focused OBJECT.** The page is about one canonical record. Any `UserOwnedModel` `DetailView` is auto-declared by `base.html` (`object.context_ref` → `<meta name="wlj-context" content="app.model:pk">`); a non-`DetailView` (TemplateView/FBV) detail page adds `CurrentContextMixin` + `get_current_context_object()`.
2. **Overview / dashboard page → a deterministic PAGE SUMMARY.** The page has no single object (Dashboard, Weight, Glucose, Health Overview, Calendar Overview, Finance/Goals/Task Dashboards, Reports, Analytics, …). It declares `summary:<key>` via **`PageSummaryMixin`** (`page_summary_key` + `page_summary_title`), resolved by a provider registered with `@register_page_summary("<key>")`.

**Rules for overview summaries (non-negotiable):**
- The provider is **user-scoped** (its own query is the ownership boundary) and **request-path-safe** (aggregate/pre-computed truth only — no heavy compute).
- **Facts only** — expose numbers/dates; never a verdict ("on track"). The model interprets.
- **ONE deterministic source** feeds BOTH the page render AND the provider (e.g. `build_weight_summary` → `WeightListView` + the `health.weight` provider). Never re-derive the summary independently — that reintroduces the exact page-vs-assistant drift class this pattern eliminates.

Do NOT wait to discover a blind page through testing: a new overview page ships its summary provider in the same change. Full contract + rollout backlog: `docs/WLJ_CURRENT_CONTEXT_CONTRACT.md`.

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

**ENFORCED (not just followed):**
- Request-path enqueues are **fire-and-forget by config**: `CELERY_TASK_IGNORE_RESULT=True` + 0.5s broker/result socket timeouts (`config/settings.py`) mean `.delay()` can never block on a degraded Redis. Always enqueue via `apps/core/celery_utils.py :: safe_enqueue` (non-blocking, no sync fallback). Post-write intelligence goes through `fire_intelligence()` (which enqueues `core.deferred_fire_intelligence`) — **never** call `update_user_state` / `run_intelligence_chain` / `run_insights` / `build_health_state` / `rebuild_user_state` inline in a view or signal.
- Request-path SAE reads use `get_module_state(..., allow_rebuild=False)`.
- **`apps/core/tests/test_request_path_safety_contract.py` fails CI** if any `views*.py` / `signals.py` / `api*.py` calls a heavy-intelligence/rebuild function or issues an inline LLM call. A new user-invoked AI endpoint must be added to that test's `INLINE_LLM_ALLOWLIST` in the same change (the reviewed audit trail). Full guarantee + rationale: `docs/WLJ_REQUEST_PATH_SAFETY.md`.

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

## Administrator Experience Checklist (REQUIRED for any operational feature)

Engineering correctness is not the same as a finished product. Any feature an operator runs (jobs, runs, imports, background work, dashboards with actions) is **not complete** until the operator sitting in front of the screen can naturally:

- **Start** — initiate the work.
- **Stop** — cancel/abort gracefully (cooperative cancellation, never an orphaned state).
- **Monitor** — see progress, current step, and freshness (heartbeat/age), not just a spinner.
- **Recover** — restart/retry after failure, interruption, or cancellation; understand stale vs interrupted vs failed.
- **Understand** — distinguish active vs finished work; see diagnostics and history; know why something stopped.

Every operational feature review must end by answering these five. If any obvious answer is "No", the feature is incomplete — implement the missing control. Do not gold-plate (only build controls an operator would naturally expect), but never ship engineering scaffolding without the operator controls that make it usable. (Origin: P34 — we built heartbeats/stale/interrupted/restart but missed **Cancel**.)

---

## Reference Docs (Read On-Demand)

| Doc | When to Read |
|-----|-------------|
| `docs/WLJ_PRODUCT_VISION.md` | **HIGHEST-level product document — the governing philosophy (the *why*). Read FIRST for any strategic, architecture, or assistant work. WLJ is a Personal Truth Platform, not an AI; the model reasons, WLJ knows; users choose a default relationship; the model derives from facts but never invents them; provider-agnostic forever. Every other doc derives from this; when in tension, this wins.** |
| `docs/WLJ_LLM_TRUTH_ACTION_CONTRACT.md` | **CANONICAL architecture — read FIRST for ANY assistant / Chief-of-Staff / chat / truth / action / preference work. WLJ owns truth; the conversational model owns reasoning. Defines the truth boundary (composed briefings + freshness/confidence/source envelope), the action boundary (safe deterministic path + audit), the preference/learning boundary (explicit-first), the external-work sandbox, and provider-agnosticism. Do NOT build a reasoning engine inside WLJ.** |
| `docs/WLJ_ARCHITECTURE_LAWS.md` | **Platform constitution — ANY subsystem that ingests data or answers a personal question. Run the Answer Precondition Pipeline: Intent→Scope→Freshness→Completeness→Confidence→Strategy→Retrieve→Stability→Reason→Narrate (Laws 0–5) — now re-hosted INSIDE truth tools (Amendment A). Questions determine retrieval; retrieval never determines the answer.** |
| `docs/WLJ_CONDUCTOR_DEVELOPMENT_MODEL.md` | **GOVERNING development model (reframed 2026-07-09) — read at the START of ANY assistant/Chief-of-Staff production issue. Product-first, then classify the failing layer: Truth (WLJ) → Reasoning (the model) → Action (WLJ) → Experience; fix the first that failed. Most fixes are Layer 1 truth. Do NOT build WLJ reasoning — fix via truth delivery, context, a tool, or the profile.** |
| `docs/WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md` | **Phase 4 governing architecture — ANY CoS learning, self-improvement, reflection, correction-handling, trust/quality/scorecard, or Executive Improvement Opportunity (EIO) work. Reflection sits ABOVE Truth→Reasoning→Execution and only OBSERVES them. Learning is default-deny (P2); NEVER learn around a deterministic defect (P3) — surface an EIO instead. Trust + value are the KPIs.** |
| `docs/WLJ_EXECUTIVE_REFLECTION_DESIGN_ASSUMPTIONS.md` | **Engineering memory for Phase 4 — read BEFORE changing anything in `apps/ai/reflection/`, the learning gate, EIO routing, or read-back gating. Explains WHY it was built conservatively and what was intentionally NOT built (deferred reinforcement, gated learning, human-reviewed EIOs). Protects against architectural drift — if you're loosening a gate to make Beth "smarter," read §4 and §8 first.** |
| `docs/LAYER1_DOMAIN_FRAMEWORK.md` | **Building or maturing ANY Layer 1 canonical domain (Goals, Calendar, Relationships, Finance, …). The reusable process extracted from Medication: development standard, certification gates, acceptance playbook, maturity model, lessons learned.** |
| `docs/WLJ_MEAL_INTELLIGENCE_ARCHITECTURE.md` | **GOVERNING architecture for the Meal Intelligence domain (v1.0) — read FIRST for ANY meal / nutrition / pantry / recipe / grocery / shopping / receipt / food-lifecycle work. Meal Intelligence canonically owns the operational recipe (ingredients, nutrition, prep, cost, planning); Legacy projects *meaning* only. Supply is household-scoped; consumption + health are person-scoped; safety composes as a union, targets stay per-person. Two authoritative ledgers (inventory, consumption); recipes are structured at write time; *Capture Once, Reuse Everywhere*. Do NOT re-fragment the domain — conform to this doc or amend it deliberately. Companions: `docs/WLJ_MEAL_INTELLIGENCE_TRUTH_CERTIFICATION.md` (certification standard — 7 gates, M0–M5 ladder, per-truth questions) and `docs/WLJ_MEAL_INTELLIGENCE_ROADMAP.md` (implementation milestones; foundations first).** |
| `docs/WLJ_OPERATIONS_VISION.md` | **GOVERNING (living) document for the WLJ Operations subsystem — read at the START of ANY Operations / Ops Wall / Operations Command Center / monitor / recovery / escalation work. Operations is a Layer 1 Truth Domain (a peer of Health/Finance), NOT a CoS feature and NOT a reasoning engine; the CoS consumes Operations truth like any other domain. Contains the 9-phase roadmap + a maintained status ledger. REQUIRED: any completed Operations work updates this doc (mark status, record ADRs/deferrals). Companion as-built coverage: `WLJ_OPS_WALL_COVERAGE.md`.** |
| `docs/WLJ_LEGACY_DOMAIN_ARCHITECTURE.md` | **Any Legacy domain work — the preservation-truth architecture baseline (Attestation→Assertion→Projection, significance, loss-risk, conflict sets). Read before any Legacy feature.** |
| `docs/WLJ_LEGACY_PLACES.md` | **Places domain (as-built) — canonical Place model + coordinate provenance, the interactive Esri map, geocoding pipeline, and the location-review tool. Read before any map/coordinate/geocoding work.** |
| `docs/WLJ_LEGACY_MAP_TILES.md` | **Map/geocoder provider decision record (why Esri; OSM + Nominatim retired).** |
| `docs/WLJ_RICH_TEXT_EDITOR.md` | **ANY free-form / narrative writing field (journal, notes, reflections, descriptions, comments). The ONE platform Rich Text Editor — never build a second editor or per-module fork. Sanitized-HTML canonical + auto-derived plain-text shadow (`RichTextMixin`); self-hosted TipTap bundle; shared image upload. Adopt via `WLJRichTextWidget`.** |
| `docs/WLJ_VISUAL_TRUTH_CONTRACT.md` | **Any homepage/Action Center CSS or template change** |
| `docs/WLJ_CURRENT_CONTEXT_CONTRACT.md` | **ANY new/changed page — declare its Current Context (detail→object `app.model:pk`; overview→`summary:<key>` via `PageSummaryMixin`). The two-pattern standard + rollout backlog.** |
| `docs/ENGINE_COS_REFERENCE.md` | **Engine/CoS changes — AUTO-MAINTAIN (see below)** |
| `docs/INTELLIGENCE_ARCHITECTURE.md` | AI/intelligence feature work |
| `docs/DOMAIN_INTELLIGENCE_ARCHITECTURE.md` | AI/intelligence feature work |
| `docs/ENGINE_INTEGRATION_GUIDE.md` | Wiring new features into engines |
| `docs/CLAUDE_DOC_UPDATES.md` | After completing features/enhancements |
| `docs/CLAUDE_IOS.md` | iOS app / mobile API work |
| `docs/CLAUDE_BIBLE_PLANS.md` | Bible reading plan work |
| `docs/WLJ_RUNTIME_TRACE_DEBUGGING.md` | **ANY "app shows X, should show Y" bug — PROVE the runtime path before changing code. Governing debugging standard.** |
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

*Last updated: 2026-05-20 (added Visual Truth Contract section + doc reference)*
