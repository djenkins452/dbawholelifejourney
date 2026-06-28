# Beth Architectural Principles — The Constitution

> **This is the highest-order governance document for the Chief of Staff (CoS /
> "Beth").** Where any other doc, ticket, or convenience conflicts with a principle
> here, the principle wins. Changes to this document require explicit owner approval.
>
> **Companions:** `BETH_GOLDEN_BEHAVIORS.md` (what must not regress),
> `BETH_CHANGE_CONTROL.md` (how to change safely),
> `BETH_PRODUCTION_VALIDATION_CHECKLIST.md` (how to prove it),
> `BETH_ROLLBACK_AND_RECOVERY.md` (how to undo),
> `BETH_REGRESSION_TEST_MATRIX.md` (what is covered).
>
> **Last updated:** 2026-06-25

---

## Preamble

> **Superior document:** this Constitution governs the CoS, but it is **subordinate
> to `WLJ_ARCHITECTURE_LAWS.md`** — the platform constitution. The five Laws promoted
> 2026-06-28 bind Beth: **Data Freshness (1)**, **Confidence (2)**, **Orchestration
> (3)**, **Deterministic Retrieval ≠ AI failure (4)**, **Stable Truth (5)**. Beth must
> run the **Answer Precondition Pipeline** (validate freshness, completeness, strategy,
> stability) *before* any reasoning or narration.

Beth's architecture rests on one sentence: **WLJ owns truth; the LLM owns
reasoning.** Every principle below is a consequence of refusing to blur that line.
The system is *framework-first*: capabilities are added by extending a small set of
contracts, never by special-casing a question. Stability is a feature; a regression
in a validated behavior is a defect regardless of what shipped alongside it.

Each principle states the rule, why it exists, how it is enforced, and what a
violation looks like.

---

## Core Principles

### P1 — Truth first, reasoning second
WLJ computes and owns the authoritative facts; the LLM only narrates and reasons
*over* facts it is handed. The model never sources its own truth.
- **Why:** prevents fabrication, drift, and "confident wrong" answers.
- **Enforced by:** deterministic retrieval in the reasoning lane; `cos_context` /
  `build_cos_intelligence` compose state before the model is called.
- **Violation:** asking the model to "figure out" a metric instead of retrieving it.

### P2 — Deterministic retrieval before LLM reasoning
The flow is: question → Planner (structured plan) → **deterministic** authoritative
retrieval → curated Working Memory → one reasoning call. Retrieval is code, not a
model guess.
- **Enforced by:** `apps/ai/chatgpt_cos/reasoning/plan.py` (plan only) +
  deterministic retrieval/curator in `stages.py`.
- **Violation:** letting the LLM choose or fabricate which data to fetch.

### P3 — OpenAI never receives raw SAE state
The model sees only an executive-clean Working Memory. Raw SAE objects, enum codes,
internal labels, `source` paths, and field names never reach the prompt.
- **Enforced by:** `stages.py` curator (strips `source`/`_label`/raw enums);
  `test_reasoning_lane::test_raw_enum_never_leaks_to_model_facing_wm`,
  `test_health_working_memory_is_health_only`.
- **Violation:** dumping a module state dict into the system/user prompt.

### P4 — The Planner never answers the user
The Planner LLM emits a structured `RetrievalPlan` and nothing else. It never
produces user-facing text.
- **Enforced by:** `plan.py::parse_plan` (closed vocabulary; unknown → `other`);
  reasoning is a separate, later call.
- **Violation:** returning the planner's output to the user, or having it "just
  answer" when confident.

### P5 — Every implemented intent provides a deterministic fallback
An implemented reasoning intent must return a correct, useful answer even if every
LLM call fails. No implemented intent can produce a blank or error-only response.
- **Enforced by:** `reasoning/engine.py` guarantee + `_health_risk_fallback` /
  `_health_progress_fallback`; `test_foundation_validation::test_deterministic_fallback_*`,
  `test_reasoning_lane::test_health_fallback_uses_ranked_concerns`.
- **Violation:** shipping an intent whose only path to an answer is a successful LLM call.

### P6 — Framework-first, never special-case-first
New behavior is added by extending shared contracts (intent registry, retrieval
vocabulary, curators), not by branching on a specific question or string.
- **Why:** special cases multiply silently and rot; the framework is testable once
  and reused everywhere.
- **Violation:** `if "biggest risk" in message:` style branching outside the registry.

### P7 — Stable behavior outranks new capability
If a change risks a Golden Behavior and the risk cannot be removed, the change does
not ship. Preservation beats shipping.
- **Enforced by:** `BETH_CHANGE_CONTROL.md` (Blast Radius Assessment + sign-off).

### P8 — The tool loop is fallback/debug infrastructure only
The agentic tool loop is demoted to a fallback/diagnostic path. The framework
(Planner + deterministic retrieval + curated reasoning) is the primary path.
- **Enforced by:** fast path + reasoning lane bypass the tool loop;
  `test_foundation_validation::test_fast_path_uses_plain_call_api_never_tool_loop`.
- **Violation:** routing a normal implemented intent through the tool loop by default.

### P9 — User-facing language stays coaching-oriented
Responses are warm, direct, evidence-based, and non-alarmist. Beth coaches; it does
not diagnose, scold, or catastrophize.
- **Enforced by:** tone calibration in `stages.py`;
  `test_reasoning_lane::test_prompts_carry_calibration_and_no_alarmist_words`,
  `test_severe_labels_softened`.

### P10 — Internal implementation details never surface to users
No enums, no `LOW/MED/HIGH` codes, no `SAE.*` paths, no field names, no system
terminology, no engine names — ever — in user-facing output.
- **Enforced by:** curator stripping + label calibration; same tests as P3/P9.
- **Violation:** "muscle loss risk level: MED" reaching the user.

### P11 — Domain curators own context isolation
Each domain's curator is responsible for keeping its Working Memory to its own
domain. Health answers are health-only; cross-domain truth is never fetched or shown.
- **Enforced by:** HEALTH-scoped retrieval + `HealthWorkingMemoryCurator`;
  `test_reasoning_lane::test_scope_drops_cross_domain_truth_and_never_fetches_it`,
  `test_biggest_health_risk_no_contamination`.
- **Violation:** journal/faith/finance content bleeding into a health answer.

### P12 — Every qualifying change requires blast-radius analysis
A Blast Radius Assessment (files, subsystems, Golden Behaviors at risk, required
tests, validation, rollback) is mandatory before significant Beth changes.
- **Enforced by:** `BETH_CHANGE_CONTROL.md`.

### P13 — New reasoning capability = framework extension, not ad hoc branching
A new intent is added through the registry/vocabulary/curator contracts and the
5-point registration gate — not by inserting bespoke conditionals.
- **Enforced by:** `apps.ai.tests.test_intent_registration`; the New Intent Checklist
  in `CLAUDE.md`.

### P14 — Validated behaviors are protected and may not regress without approval
The Golden Behaviors are a contract. Regressing one requires explicit owner approval
and is otherwise treated as a defect to be reverted.
- **Enforced by:** `BETH_GOLDEN_BEHAVIORS.md` + production validation + stable tags.

---

## Supporting Principles
*(refinements consistent with the core and with established WLJ practice)*

### P15 — Never compute heavy analytics on the request/task path
Heavy analytics (full SAE rebuilds, system-impact, signal health) must run in
background workers and be read from cache/snapshots; request/task paths read
pre-computed data or return "pending" — never live-compute as a fallback.
- **Why:** live compute caused 524 timeouts and is the root of the open worker-kill
  durability gap (`BETH_GOLDEN_BEHAVIORS.md` known-limitation #1; matrix R-1).
- **Status:** *aspirational at baseline* — `service.py::generate` still warms with
  `get_user_state(allow_rebuild=True)`; closing this is prioritized post-baseline.

### P16 — Fail loud on critical paths; never swallow errors
No `except Exception: pass` on intent recognition, execution, retrieval, or safety
gates. Separate `ImportError` (optional) from `Exception` (logged with `exc_info`).
Safety gates fail closed.

### P17 — Single source of truth for in-flight state
"A request is in flight" is derived from exactly one signal — the sessionStorage
pending marker. The thinking indicator, recovery, and notifications all read it. **No
second pending-tracking system.**

### P18 — Beth consumes composed briefings, not raw signals
Intelligence features produce composed, deterministic state objects (verdict already
inside) for Beth to narrate over. PIE/PRIE/CDCE feed the composer, not Beth directly.
Never add "more atomic signals for Beth to reason from."

### P19 — Streaming and non-streaming paths stay at parity
Both chat paths call the same orchestrator. A fix to one must be verified on the other.

### P20 — Every lifecycle stage is observable
Each request carries a single correlation id (`cid`) through `BETH_LIFECYCLE`
telemetry (client + server) so any failure is locatable from production logs without
guesswork.

### P21 — "Deferred" means phased, not abandoned
Cut scope gets a phase number and an explicit promotion trigger. v1 architecture must
remain additive-compatible with the full roadmap. "Maybe someday" is forbidden in plans.

### P22 — General Knowledge Fallback
If a request is not personal, not ambiguous, and not actionable within WLJ, Beth
gracefully falls back to general conversational capability rather than failing.
Beth remains a Chief of Staff but must never feel incapable of basic conversation.
- **Why:** an intent-failure / empty-response message for "Who was Abraham Lincoln?"
  reads as broken. A capable assistant answers it.
- **Enforced by:** the General Conversation lane (`chatgpt_cos/lanes.py`), tried
  after the personal + clarification lanes; **SANDBOXED** — it receives no
  personal/SAE data (upholds P1/P3/P11). Conservative claim: any personal/WLJ
  reference declines to the tool loop instead of guessing.
- **Violation:** answering a personal question from the General lane (no personal
  data → would fabricate), or returning the empty-response message for plain
  general knowledge.

### P24 — Canonical Truth Source  *(CONSTITUTIONAL — WLJ-wide, not Beth-only)*
When a domain engine already computes a user-facing fact, **all WLJ experiences**
must consume that engine's output rather than independently calculating or
inferring the fact. Dashboard, Beth, notifications, reports, mobile experiences,
widgets, and future experiences must derive facts from the **same authoritative
engine**. Independent computation of an existing fact is **prohibited**.
- **Canonical engines (examples):** next rhythm item → Rhythm engine; dashboard
  scores → Scoring engine; health risks → Health briefing engine; goal status →
  Goal engine.
- **Why:** divergent re-computation breaks trust — e.g. the dashboard's "Today's
  Rhythm" (`build_rhythm_sections`, schedule-ordered) said *Work on WLJ* while Beth
  (`get_next_action`, urgency-ordered) said *Bible Reading is next*. Two selectors,
  two "next," one broken promise.
- **Direction:** facts are **computed once and consumed everywhere** via a canonical
  API/service layer (e.g. `get_current_rhythm_item` / `get_next_rhythm_item` /
  `get_remaining_rhythm_items` / `get_current_rhythm_bucket`). Consumers — Dashboard,
  Beth, Notifications, Daily Briefings, Mobile, Widgets — all read the same API.
- **Distinct facts stay distinct:** "next *rhythm* item" (schedule) and "focus *right
  now*" (urgency) are different canonical facts with different engines; consumers must
  request the one they mean, not silently substitute.
- **Enforced by:** a canonical-source test that the Dashboard and Beth return identical
  "next rhythm item"; code review (P12) flags any independent re-computation.

### P23 — Clarification Before Failure
When intent confidence is low or a request is ambiguous, Beth asks a clarifying
question rather than returning a failure.
- **Why:** "check in" / "help me" / "review this" are under-specified; a guess or a
  failure both erode trust. Asking is the Chief-of-Staff move.
- **Enforced by:** the Clarification lane (`chatgpt_cos/lanes.py`,
  `AMBIGUITY_TYPES` registry) — DETERMINISTIC templates, no OpenAI; tried before
  the General lane. New ambiguity types are added by appending to the registry
  (P6/P13), never by branching.
- **Violation:** a large if/else of special-cased phrases, or a hard failure on an
  ambiguous request.

---

### P25 — Personal Truth First  *(RATIFIED; activation phased — shadow first)*
For every request, Beth first determines whether Danny's personal WLJ truth is
relevant, then routes on that single explicit decision rather than on lane order:
1. If personal truth is **required or would materially improve** the answer →
   retrieve and reason over WLJ truth (**PERSONAL**).
2. If personal truth is **not relevant** → answer with normal OpenAI capability,
   consulting no WLJ truth (**EXTERNAL**, sandboxed).
3. If personal truth helps but general knowledge is also needed → ground a general
   answer on WLJ truth, **truth first** (**MIXED**).
4. If Beth **cannot determine** whether personal truth is needed → ask a clarifying
   question rather than guessing (**AMBIGUOUS**).
5. **Personal truth always outranks generalized advice** unless the user explicitly
   requests external-only guidance.
- **Why:** lane order was carrying the personal-vs-external semantics implicitly,
  which produced repeated routing regressions (`check in` → health planner; general
  → planner/breaker). P25 makes that one decision explicit, deterministic, and
  testable — and contains the planner/SAE-warm to PERSONAL only.
- **Classification is deterministic-first** (reuses existing predicates); the LLM is
  at most an optional gray-zone tie-breaker, never the heavy planner, never the
  critical path; genuine uncertainty defaults to **clarify** (rule 4).
- **Activation is phased** (`docs/BETH_P25_PERSONAL_TRUTH_FIRST.md`): shadow →
  validate → flag-activate → remove legacy. P25 routing is **NOT active**; a shadow
  classifier runs for telemetry only. Generalizes P1/P2; subsumes the implicit lane
  ordering; consistent with P6/P8/P11/P22/P23/P24. Target milestone: `beth-stable-v3`.

## Amendment process
1. Propose the change with rationale and the principle(s) affected.
2. If it weakens a protection, it requires explicit owner approval (P7, P14).
3. On approval, update this doc, bump "Last updated", and note it in
   `docs/wlj_claude_changelog.md`.
4. If the change alters runtime contracts, follow `BETH_CHANGE_CONTROL.md` in full.
