# WLJ Truth Validation Center — Governing / As-Built

**Status:** ✅ **Type 1 (Truth Validation) implemented.** First type on the unified validation
engine reserved by `docs/WLJ_CERTIFICATION_PLATFORM_FUTURE.md`. Admin-only operational
capability under **Admin Console → AI Operations → Truth Validation Center**.

> **Principle.** WLJ is the deterministic source of truth. The Chief of Staff is the
> conversational interface to that truth. The Truth Validation Center continuously validates
> that the Chief of Staff faithfully represents what WLJ actually knows. **This is not testing
> AI — it is validating truth.** Every comparison is deterministic; **no model ever grades a
> model**; the operator has final authority.

---

## What it does
For each object in the Truth Discovery Suite (`apps/core/truth/discovery_suite.py`, 40 objects
across 18 domains), the operator can **Run Test** — with no copy/paste — and the system:

1. Sends the discovery prompt to the **production Chief of Staff** exactly as a customer would
   (`CoSGateway.respond(surface=SURFACE_CHAT)` — the same path the web chat uses).
2. Stores and displays the complete response + the tool/provider evidence used.
3. Resolves the **deterministic WLJ object** the prompt is about (via the same read surfaces the
   model calls — `get_domain_entity` / `get_domain_state`).
4. **Compares structured truth** — expected typed values VERSUS the structured values present in
   the response — and auto-grades each: **✓ Present / ✗ Missing / ⚠ Mismatch / N/A**.

Runs execute by **single object · whole domain · whole Truth Layer**, worker-only (never inline).

## Architecture (one engine, typed by `validation_type`)
The Acceptance engine was generalized rather than forked. Everything except the work-list and the
evaluator is shared with the live-behavior suite:

| Concern | Reused from Acceptance | Truth-specific |
|---|---|---|
| Production send path | `_gateway_asker` → `CoSGateway.respond` | — |
| Evidence capture | `_extract_evidence` + `ToolCallLog` | — |
| Async worker + progress/cancel/reap | `safe_enqueue`, heartbeat, `request_cancel`, `reap_stale_runs` | task `run_truth_validation` |
| Storage | `AcceptanceRun` / `AcceptanceResult` | `validation_type`, `scope_*`, `checks`, `expected_truth`, versions |
| Work-list | — | `discovery_suite.DISCOVERY_PROMPTS` |
| Evaluator | (behavior: concept rules) | **deterministic comparison engine** |

**Files:**
- `apps/core/truth/validation/comparison.py` — flatten expected object → typed values; deterministic
  numeric (unit-normalized, tolerant) / date / text / forbidden matchers; `grade_checks`.
- `apps/core/truth/validation/surface.py` — resolve a discovery `surface` string to the deterministic
  WLJ object (`resolve_expected_object`).
- `apps/core/truth/validation/recommend.py` — `suites_for_changed_paths` (design-for-CI; **not** wired to CI).
- `apps/ai/chatgpt_cos/truth_validation_service.py` — `execute_truth_run`, `validate_one`, truth-bug report, rollups.
- `apps/ai/chatgpt_cos/tasks.py :: run_truth_validation` — worker task.
- `apps/admin_console/truth_validation_views.py` + `templates/admin_console/truth_validation_{center,run}.html`.

## Object resolution — the validator selects the SAME object the app does
**The validator must never invent its own meaning of "current/active/latest".** Before asking
the CoS, `resolve_expected_object` (`apps/core/truth/validation/surface.py`) resolves the object
using the application's own deterministic rule, declared per discovery prompt as a `selection`
contract:
- `by_name` → `get_domain_entity(name=…)` (unambiguous).
- `active` → among `describe(type)`, the record whose status matches the app's active marker
  (e.g. reading plan `plan_status='active'`) — **never** simply `describe()[0]`.
- `current` → resolve the current object's name via the domain's own `current(metric)` accessor
  (the exact production query), then fetch that record.
- `latest` → the most-recent record (provider composes newest-first).

Every resolution returns a **resolution card** — Resolved Object · Resolved From · Selection Rule ·
Provider · Status — shown to the operator on the run detail, so the expected truth is never a
surprise. (Origin: the first operator validation resolved "current Bible study" to the most
recently *started* plan instead of the `plan_status='active'` plan — a validator bug, not a CoS
bug. Fixed by the `selection` contract; regression-locked in
`apps/faith/tests/test_truth_validation_faith.py`.)

**Prompt modes** (`AcceptanceRun.prompt_mode`): `resolved` (default) sends a prompt that NAMES the
resolved object — removing ambiguity so the comparison validates one specific object; `natural`
sends the raw NL discovery prompt — testing the CoS's OWN "current/latest" resolution. Both are
preserved as first-class modes.

## The comparison engine — why it is never AI-vs-AI
Scoring is 100% deterministic. WLJ's expected object is the authority. The engine flattens the
object into typed scalar values and asks a **typed deterministic question** of the response text
(numeric within tolerance + unit normalization; date across renderings incl. relative; normalized
text containment; forbidden-value contamination). A `⚠ Mismatch` (a same-unit contradiction) is the
highest-severity class. Where a case is genuinely ambiguous, the deterministic result **flags for
the operator** — the only non-deterministic authority is the human operator override, which is
**permanently recorded** (`AcceptanceResult.override_log`) and recomputes the object grade.

> **Deterministic extraction now; blind transcription later.** v1 extracts typed values
> deterministically from the response. The architecture allows a *schema-bounded, answer-key-blind,
> non-scoring* transcriber for ambiguous free-text later (WLJ's own untrusted-extraction→trusted-
> validation pattern). It was intentionally **not** built for v1 — deterministic comparison is
> favored over interpretation.

## Two owners (unchanged)
- **Owner-1 (deterministic foundation):** `QuestionSpec` / `run_spec` vs hand-authored `FIXTURES`
  proves the *provider* returns the right value, independent of any live read. Still mandatory — it
  is the guard against **shared-provider blindness** (the Center reads the same provider the CoS
  reads, so a provider bug could pass silently without Owner-1).
- **Owner-2 (this Center):** proves the model *faithfully conveys* what the provider returns.

## Operator experience (Admin Experience Checklist)
Start (object/domain/full) · Stop (cooperative cancel) · Monitor (live heartbeat + auto-refresh) ·
Recover (stale-reap, re-run object) · Understand (per-check comparison, truth-bug list, first-failing-
layer owner). **Final Approval** turns a run into a certification of record (`approved*`).

## History & dashboard
Every run persists as an `AcceptanceRun` (date, tester, git commit, suite version, provider version,
scope, complete responses, automatic results, operator overrides, approval). The executive dashboard
shows Overall Truth Health, Objects Certified, Truth Checks Passed, Outstanding Bugs, Not-Yet-Validated,
Historical Success, Regression Trend, and Average Validation Time, with live progress during execution.

## Future validation types (design-for)
`validation_type` + pluggable evaluator makes new types additive — **CRUD** (deterministic DB
post-condition), **Domain** (Truth evaluator, scoped), and the judgment tier (**Reasoning / Executive
Briefing / Check-in**) which routes to a *separate* owner and must never be graded by the truth
comparison engine.

## Tests
- `apps/core/tests/test_truth_validation_comparison.py` — the deterministic engine (flatten, numeric/
  date/text/forbidden, grading, surface parsing).
- `apps/ai/chatgpt_cos/tests/test_truth_validation_service.py` — end-to-end run with an injected asker.
- `apps/admin_console/tests/test_truth_validation_views.py` — operator surface (admin-only, start/scope,
  re-run, override, approve).

## Known refinements (logged, not blocking)
- List/collection fields and booleans are not auto-scored in v1 (operator reviews); promote when a
  reliable typed matcher exists.
- `identity` labels that are descriptive (e.g. "Latest weigh-in") may over-flag as a missing text
  check; this errs toward operator review, never a silent miss.
- Per-check regression *trend* uses run-over-run comparison on `checks` JSON; promote to a
  `ValidationCheck` table if per-check analytics are later needed (mirrors the evidence-column promotion).
