# 02 · Engineering Operating Guide

**Responsibility of this document:** how to safely evolve WLJ inside the Constitution. Runtime tracing, root-cause proof, deployment discipline, documentation discipline, product-first engineering, results-not-intentions, and the Session Transition Protocol. It does **not** restate the Articles (that's `02_WLJ_CONSTITUTION.md`) or Danny's collaboration preferences (that's `03`).

Supersedes and merges the retired `00_CORE_STARTUP/WLJ CLAUDE OPUS 4.8 EXECUTION PLAYBOOK.md`.

---

## 1. Prime directive

**Aggressive execution inside protective boundaries — never aggressive architectural mutation.**

> Read speed is free; write speed is earned. **Investigate broadly. Mutate surgically.**

Velocity comes from collapsing *investigation* time, not from skipping the gate before a *write*. And one measure sits above the rest: every change exists to make the **WLJ Chief of Staff** something a paying customer trusts enough to rely on every day. Correct engineering, passing tests, and clean architecture are necessary but never sufficient — they are the means; a *more trusted Chief of Staff* is the end. **The implementation is not the product; the trusted conversation is.**

### 1a. The investigation prime directive — build upward from the lowest deterministic layer

**The first responsibility of every architectural investigation is to preserve and strengthen WLJ's deterministic truth architecture. Evaluate truth-preservation *before* any other architectural consideration.** The order is not negotiable:

1. **Preserve WLJ as the single deterministic owner of truth.** Start every investigation here — not with the Chief of Staff, the experience, or the feature.
2. **If a proposal weakens, duplicates, bypasses, or blurs WLJ's ownership of truth, it is rejected or redesigned before anything else is discussed.** This gate runs first, and a proposal that fails it does not proceed on the strength of its product upside.
3. **Only after deterministic truth is fully preserved** do we evaluate improvements to the Chief of Staff's reasoning, behavior, experience, workflows, conversations, navigation, or product capabilities.

The two halves of the system evolve on **different clocks**: the **Chief of Staff is expected to change continuously** — smarter, more helpful, more proactive, more natural; **WLJ's ownership of deterministic truth is expected to stay stable**. Progress means a more capable Chief of Staff standing on an *increasingly stable* truth foundation — never a truth foundation reshaped to make the assistant look smarter.

Every investigation therefore assumes, by default:
- **improve WLJ truth first**; **expose existing truth before inventing new truth** (IV.2, IV.4);
- **preserve the deterministic authorities** — **one authority per truth domain** (III.1), **one execution authority** (III.2), **Current Context authority** (II), **Conversation State authority** (the working-state index, `03 §3e/§3f`);
- **never move a deterministic responsibility into the model** (I.1–I.4). The model reasons over truth; it never becomes the truth.

**The default question that opens every investigation is: _"Can we improve the Chief of Staff without changing who owns truth?"_** The expected answer is almost always **yes** — and the investigation's job is to find that path. If the honest answer is **no**, the investigation must clearly *prove why*, and any change to who owns truth is an architecture change subject to Constitutional Review (default NO, `02 §3`). *(This is why the CoS-platform investigations of 2026-07-20/21 landed on composition and elimination — bidirectional Current Context, one destination authority — rather than any new subsystem that would have re-owned truth: the truth-preservation gate ran first and the reuse path was found. See `docs/WLJ_COS_PLATFORM_EVOLUTION_INVESTIGATION.md`.)*

**Build upward from the lowest deterministic layer.** Truth-first is the first rung of a full **ascending order** — the layers of `§3` climbed from the bottom: **① Truth → ② Current Context → ③ Reasoning → ④ Actions → ⑤ Experience.** An investigation *starts* at ① and only rises to a higher layer when the layers beneath it genuinely cannot solve the problem:
- **① Truth** — preserve WLJ as the single deterministic truth owner; protect one authority per truth domain (III.1), deterministic calculations (I.3), and deterministic execution (III.2, I.7); never move a deterministic responsibility into the model (I.1–I.4).
- **② Current Context** — preserve and *strengthen* the deterministic understanding of what the user is viewing and doing (Article II); prefer improving deterministic context over adding a higher-level reasoning system. Most "the assistant didn't know what I meant" problems are a Current-Context-coverage gap, not a reasoning gap.
- **③ Reasoning** — only once ① and ② hold, make the Chief of Staff more helpful, proactive, conversational, and human — reasoning *over* deterministic truth, never *replacing* it.
- **④ Actions** — improve the safe, audited execution path only after ①–③ hold.
- **⑤ Experience** — presentation, workflows, navigation, and conversation last, and only while ①–④ remain intact.

So the second default question of every investigation is: **_"Can this problem be solved by strengthening a lower deterministic layer instead of changing a higher one?"_** — again, almost always **yes**. This is the **bottom-up construction** order for a *new* investigation or feature; it is the mirror of `§3`'s **top-down diagnosis** order (for a *reported failure*, find the first layer that *broke*, from the top). Same five layers, opposite direction, different job — climb up when building, look down when diagnosing.

**Certification precedes expansion.** Building *upward* is licensed only when the layer beneath is **certified** — *complete, authoritative, request-path-safe, and production-ready* — not merely *present*. An excitingly higher-level feature never licenses skipping ahead over an uncertified layer, because a layer built on an incomplete one silently inherits its gaps. So the gate before any higher-layer work is: **_"Is the lower deterministic layer fully certified before we build on top of it?"_** If no, strengthen and certify the lower layer first. *(Precedent: the CoS-platform work deliberately stopped to certify Current Context coverage — the Dashboard Day Summary and the domain overview summaries — before starting bidirectional Current Context.)* This is the *when* of construction; the *how* of certifying a layer — the per-domain Owner-1/Owner-2 loop — is `§3c`.

## 2. Product-first engineering

Before any architecture review, run the **product review**, in this order:
1. Would a paying customer **trust** this conversation/experience?
2. If not, why — in **customer terms** (it contradicted itself / forgot / answered the wrong question)?
3. Only **then**, which architectural layer caused it?

Never the reverse. Fix trust-breakers one at a time, ranked by trust impact, wherever they live (most often Layer 1 truth or Layer 4 experience).

## 3. The layered development model (top-down)

Classify which layer failed and fix the **first** one that did: **Truth (WLJ) → Reasoning (model) → Action (WLJ) → Experience.** Most fixes are Layer 1 truth. **Do not build WLJ reasoning** — fix a reasoning miss with better truth delivery, executive context, a truth/action tool, or a corrected AI Relationship. A genuine gap is filled as *truth or an action tool*, never as a mind.

**Investigation order (WLJ is in product-refinement, not architecture-discovery).** For any reported issue, investigate in this order and stop at the first layer that explains it:
1. **Deterministic Truth** — did WLJ produce correct, well-composed truth?
2. **Current Context** — was the authoritative page context right, and did the model get it?
3. **OpenAI Reasoning** — given correct truth, did the model reason well?
4. **Deterministic Actions** — did the safe action path validate/confirm/execute/audit correctly?
5. **Product Experience** — is the surface/experience the real gap?

**Propose an architectural change only after investigation proves it necessary** — never as the opening move. Architecture changes go through Constitutional Review (default NO).

### 3a. Truth before reasoning
The model reasons; it never invents a WLJ fact. When the model answers wrong, the first question is "was the **truth** WLJ handed it correct and well-composed?" — not "how do we make the model smarter?" Give it better truth (composed briefings with a freshness/confidence/source envelope), better delivery, or a truth tool. Improving truth is almost always the fix (constitutional: I.1–I.4, IV.2).

### 3b. Current Context precedence
Answer from the authoritative Current Context **before** retrieving anything. The precedence order is: **Current Context → the conversation → truth already in context → a truth tool → general reasoning.** If Current Context already answers the question, answer from it — don't retrieve further. Never let scraped DOM or related truth override the page's declared, server-resolved Current Context (constitutional: II.1–II.4).

### 3c. Certification drives implementation (the CoS development loop)
**Certification — not intuition or architecture — now drives the Chief of Staff roadmap.** Architecture no longer leads development unless certification *proves* architecture must change. Per truth domain, run the loop and do not skip steps:

**choose a truth domain → Owner-1 certification → Customer Truth certification → attribute the first failing layer → smallest deterministic fix → re-certify → repeat.**

- **Two owners, complementary, sequential:** **Owner-1 = Deterministic Truth Certification** (the provider returns the right value, no OpenAI; `apps/core/truth/question_specs.py` `QuestionSpec` + `capability_matrix()` + `apps/core/tests/test_truth_retrieval_slice.py`). **Owner-2 = Customer Truth Certification** (real question → real production pipeline → grounded answer; the **Truth Validation Center** — the Acceptance engine generalized, typed by `validation_type`, routed through `CoSGateway` — never a second framework). Deterministic → Customer → Executive Judgment; each gates the next.
- **The Owner-2 instrument = the Truth Validation Center** (`docs/WLJ_TRUTH_VALIDATION_CENTER.md`, Admin → AI Operations). Deterministic comparison of the production CoS answer vs WLJ truth — **no model grades a model.** It resolves each object by the app's own selection rule (a visible resolution card: Resolved Object / From / Rule / Provider / Status), classifies every failure by first-failing-layer into an executive **category breakdown** (Object Resolution · Provider Failures · Routing · Tool Selection = **Truth Layer Bugs**; then Answer Grounding · Contamination · Unknown), and runs in **resolved** (prompt bound to the resolved object — removes ambiguity) or **natural** (raw NL prompt — tests the CoS's own resolution) mode. **Fix every Truth Layer Bug before tuning Answer Grounding.** ⚠️ **Altitude caveat (01 §6):** this instrument certifies *implementation layers* — it is the engineering diagnostic, **not** the operator's certification of the conversational experience; operator certification is natural-conversation testing.
- **By-name provider rule (durable gate):** any **multi-entity-type** `DomainTruth` whose `describe_one` covers only a SUBSET of its `entity_types` passes list retrieval but returns nothing by name (the class the Validation Center's resolved mode exposes). Every multi-entity provider's `describe_one` MUST cover **all** its entity types — use the shared `DomainTruth._entity_by_identity(name, types)` fallback (reuses each type's own `describe()` composer; exact→substring; type-order precedence), never a subset or a parallel lookup. **CI-locked by `apps/core/tests/test_truth_by_name_audit.py`.**
- **Local AND production are complementary certifications** — neither replaces the other. Local proves deterministic truth on fixtures; production proves the real customer experience on real data (a Deep run executes in `wlj-worker`).
- **Attribute every failure to its first failing layer** (source truth · provider · registration · routing · tool-selection · tool-arguments · evidence retrieval · evidence delivery · grounded answer · transport · product-design) using the structured evidence the Acceptance Center captures. **Fix only that layer.** Do NOT prompt-patch, special-case routing, hardcode question handling, or "improve AI" to paper over a truth gap.
- **A missing provider is not a missing answer** — the CoS reasons from multiple **Truth Surfaces** (Standing Context, Personal Truth, Domain Entity, Executive Briefings, Decision Authority, Current Context, DomainTruth). Trace *which surface* served an answer before concluding anything. (`docs/WLJ_TRUTH_SURFACES.md`; `01_…ARCHITECTURE §6`.)
- **Evidence, not assumption, sets priority.** Rank the backlog by *measured* customer impact; mark untested domains **NOT YET MEASURED** — absence of testing is never evidence of low priority. Governing docs: `docs/WLJ_CERTIFICATION_BACKLOG.md`, `docs/WLJ_CUSTOMER_TRUTH_CERT_PROD1.md`.

### 3d. The CoS Domain Certification Standard (RATIFIED — the per-domain completeness process)
The repeatable 5-step process for bringing any truth domain to Chief-of-Staff conversational completeness, extracted from the **Nutrition** and **Journal** certifications (both prod-complete). Canonical doc: **`docs/WLJ_COS_DOMAIN_CERTIFICATION_STANDARD.md`**. Run it in order for every future domain (Faith next); never skip or reorder; do not implement past the first failing layer:

1. **Verify deterministic truth** — runtime-trace what the domain already holds (`*Queries`, `DomainTruth` surfaces, what the page shows).
2. **Expose existing truth** — **exposure precedes new truth.** Ask the Meal question ("does it already exist, merely unexposed?"); declare `entity_types`/`history_metrics`/`analysis_subjects` that REUSE canonical producers (zero new retrieval, zero reasoning). Build genuinely-new truth only when Step 1 proved it missing, as the smallest domain-owned aggregate — never a reasoning engine, never free-text extraction.
3. **Validate conversational routing** — exposed ≠ selected. **Routing is a different layer from truth**; investigate it separately (tool selection · domain selection · **capability discovery** · entity discovery). Fix via **drift-proof metadata derived from ONE source** (e.g. `domain_semantics[d].analyzes` DERIVED from `truth_analysis`, so the routing layer and the tool's accepted subjects can never diverge) — never a per-question prompt patch.
4. **Danny production validation is the gate** — local certification with the real model is engineering evidence ONLY; the milestone stays `AWAITING VALIDATION` until Danny confirms in production. impl + tests + deploy ≠ complete.
5. **Close** — mark complete, update roadmap/changelog, remove milestone TODOs/diagnostics, confirm tests + deployed SHA, post-mortem, STOP.

Invariants: **WLJ never renders a verdict** (healthy/concerning/positive/commitment) — it supplies the evidence bundle; the model judges. **Retrieve vs. search vs. analyze are distinct, discoverable tools** — chronological/latest → `get_entity`/`get_domain_state`; content/keyword ("entries mentioning X") → `search_history`; analytical synthesis ("themes/trends/patterns/advice about my records") → `get_analysis`.

### 3e. Deterministic state has ONE writer authority — the model never writes truth

Any deterministic state WLJ owns — a truth surface, Current Context, **Conversation State**, execution/decision state — has **one writer authority**, and it is written **only from concrete deterministic signals** (an uploaded artifact, a tool RESULT, a validated action/confirmation event, a page declaration, a DB record) — **never from the model's output, prose, summary, inferred topic, reflection, or any reasoning-based mechanism.** The conversational model REASONS OVER this state; it never CREATES it. The model's only influence is *which deterministic action it takes* (which tool it calls); WLJ records the **result** deterministically. If a feature seems to need the model to "set" deterministic state, route it through a deterministic action whose result WLJ records — do not write the state from model output. Protect each such authority with a **writer-contract test** (e.g. `apps/ai/tests/test_conversation_state_writer_contract.py`: only the authority module may write; the writer accepts no model-output parameter) so the boundary can never silently erode. (Origin: Conversation State governance, 2026-07-20; runtime-proven that a turn whose answer named a topic in prose produced no state.)

### 3f. Deterministic working-state stays compact & reference-oriented — and eliminates systems, never adds one

Working-state authorities (Conversation State is the reference implementation) must remain a **compact deterministic INDEX** — identifiers, lifecycle scalars, timestamps, provenance, and references to durable truth — **never generated text.** Any proposal to place a summary, transcript, AI-authored prose, inferred intent, reflection, or model-generated free text inside such state is **presumed architectural scope creep** and is declined **unless it demonstrably REPLACES an existing deterministic system.** Guard the schema with an **allow-list contract test** (e.g. `apps/ai/tests/test_conversation_state_schema_contract.py`) so a summary/prose field can never be introduced silently. Before extending any such authority, run the **Expansion Test**: (1) does it replace an existing deterministic system? (2) does it eliminate duplicate logic? (3) does it reduce architecture? (4) does it preserve the deterministic/reasoning boundary? (5) does it preserve the writer contract? **If #1 and #2 are both NO, do not add it.** A deterministic working-state authority is a *system eliminator, not another system* — durable records and long-term memory stay in their own systems; the authority holds only a *reference* to them. (Origin: Conversation State governance freeze, 2026-07-20.)

### 3g. Truth and presentation are separate layers — a domain emits structured truth; a reusable presenter renders it

A domain handler returns **deterministic structured data**, never presentation. How that data is shown to a human — chat text, a web/mobile card, an API payload — belongs to a **reusable presentation layer** that consumes the same structured contract. **Never embed presentation inside a domain handler** (formatted prose, ✓/⚠ glyphs, CTAs, verdict wording): it couples the domain to one surface, blocks reuse, and drifts per-domain. Litmus test: **if you're formatting a string for a human inside a domain handler, it's in the wrong layer.** The reference implementation is the multimodal-import **confirmation framework** (`apps/ai/import_confirmation.py`): each handler returns a structured `confirmation_detail` (recognized / skipped + reasons / derived / counts); ONE domain-agnostic presenter renders it (a registry keyed by `renderer`), so body-measurement import and Structured-Import journal-document import already share the identical rendering path, and a future structured *card* consumes the same contract — the text presenter simply becomes its fallback. This is the Truth↔Experience boundary of §3 made concrete: **the same deterministic contract feeds every current and future surface.** (Origin: Measurement Session Capture confirmation hardening, 2026-07-20; reused by Structured Import the same week.)

## 4. Prove root cause before changing code (runtime tracing)

**Never modify code until you have PROVEN — not guessed — that it executed on the request that produced the behavior.** For any "app shows X, should show Y" (governing doc: `docs/WLJ_RUNTIME_TRACE_DEBUGGING.md`):

- Trace **Browser → HTML → Template → View → Composer → Builder → DB.**
- Find **ALL producers** — a persisted object and a live composer are different producers; check both.
- When ownership is unclear, build a **read-only glass-box debug endpoint** to dump the real truth on the real request.
- Require **five-way agreement**: DB → Object → Composer → Template → Browser.
- **A passing unit test is NOT proof.** `file:line` evidence is.

## 5. Pre-Write Gate (before any code change, all five)

1. **Root cause proven** with `file:line` evidence — no speculative fixes.
2. **Blast radius mapped** — every reader/caller audited (use read-only subagents).
3. **Minimal change** — smallest diff that fixes the proven cause; **modify before adding**.
4. **Complies with the Constitution & Architecture Laws** — phase/layer boundaries, schema/streaming parity, no silent failures, deterministic rendering/decisioning, request-path safety.
5. **Rollback path + verification plan** — revertible; scoped tests only; expected user/CoS/telemetry behavior stated.

## 6. Eliminate the class

When a trust-breaking failure appears, don't ask "how do we catch/recover next time?" Ask: does this represent a **class**? What **condition** makes the class possible? Can we **remove** the condition so the whole class is structurally impossible? Prefer elimination over another detector/validator/recovery path — **bounded by blast radius**: if removal needs a disproportionate rewrite, contain the class narrowly and **log the residual**.

### 6a. When repeated UI patches move the defect, the class is architectural — stop patching, redesign the interaction model

**Trigger (a hard rule, not a judgment call): when two or more consecutive fixes to the same surface each eliminate one defect while introducing another, STOP.** The moving defect is the signal that the problem is not a CSS/markup bug but the **interaction model** itself — continued point-fixes will keep relocating the symptom. Do not ship a third patch. Instead: (1) **reassess the interaction architecture from first principles** (trace the *whole* stack, not the failing element — e.g. discovering the app shell, not the page, owns scrolling); (2) **produce competing design concepts and their trade-offs, and get Danny's explicit approval of a direction before building** (a redesign is an architecture decision, not an implementation detail); (3) then build the approved model once. *(Origin: the Journal editor, 2026-07-21 — six consecutive layout patches (fixed-height → flex-fill → sticky footer → `dvh` → `svh` → direct viewport sizing) each traded one defect for another until the exercise was reframed from "fix the CSS" to "design the Journal workspace," yielding the Focus Compose / Workspace Dock direction, `01 §6`.)*

**The front-end structural invariants this produced (durable, WLJ-wide):**
- **The app shell owns scrolling — page content is plain document flow.** On desktop the shell is a viewport-locked workspace (`body { height:100vh; overflow:hidden }`) with **one** internal scroll region (`.desktop-main-area`); on mobile the document body scrolls. **One scroll owner, never two.** Page content must **never** introduce viewport math (`vh/dvh/svh`), a flex-fill height chain, `overflow`, or a nested scroll container — that makes it a second workspace fighting the shell's scroll ownership (the exact class that killed the Journal editor in WebKit while looking fine in Chromium). If a surface "should fill the screen," that is the *shell's* job, not the page's.
- **The page owns its layout; shared components stay reusable.** A page composes and positions; a shared component (the Rich Text Editor, the confirmation presenter, the Workspace Dock) stays generic and is never given page-specific behavior. Editor height comes from the shared RTE's own `min_height` (grows with content), not a per-page viewport calc — so the same component drops into every workspace unchanged.
- **Verify layout/interaction on the *real* rendered page across engines and breakpoints**, not a synthetic harness — Chromium tolerates flexbox/scroll sins that WebKit (the iOS WKWebView / Safari the product runs in) does not; a defect that "won't reproduce" locally is often engine-specific, so remove the *condition* rather than chase a Chromium repro. Governing doc: `docs/WLJ_JOURNAL_FORM_LAYOUT.md`.

## 7. Results, not intentions

Report what actually happened. If tests fail, say so with the output. If a step was skipped, say so. Persist observed results with provenance — never inferred intent. WLJ facts are never fabricated; the model may reason from facts but may never invent one.

**A confirmation reports RESULTS, not intentions.** Before any write that needs confirmation, state exactly what was perceived and precisely what will and will NOT be saved — and why: what was **recognized**, what will be **imported**, what **cannot** be imported and the **reason**, the recognized/import **counts**, and any blank/absent fields. **Nothing perceived ever disappears silently** — an unrecognized or implausible value is surfaced with its reason, never dropped. It is deterministic truth (facts, never a verdict or "I think…"), rendered by the reusable presentation layer (§3g) so the same guarantee holds on every surface. This is what turns a trust-critical write (a body check-in read from a screenshot; a document imported as many entries) into something a paying customer can confirm with confidence. (Origin: Measurement Session Capture, 2026-07-20.)

**A fact's *precision* is part of the fact — never fabricate it either.** Never store or display more temporal precision than the source provided: a date-only value is never stored at a fabricated noon (before local noon that also invents a *future* instant — the Health Sync "Newest data · 12:00 PM at 6 AM" class), and never rendered with an invented clock time. Resolve every observed-moment timestamp through the ONE non-fabricating rule — `apps/core/truth/precision.py :: resolve_instant` (real time verbatim; date-only placed at noon **clamped to ≤ now**, precision reported) — and render via `format_instant` (DAY → "Today"/"July 20", never a clock time). Governing doc + phased per-domain rollout: `docs/WLJ_TIMESTAMP_PRECISION.md`.

**Validate what you ship; defer what you can't validate.** Runtime-validate every change in the real product (not just tests). When a change is genuinely *unvalidatable in this environment* — e.g. conversational-quality or voice refinements that need a live model (dev has no `OPENAI_API_KEY`) or a real microphone (blocked in the sandbox) — do **not** make it blind. Speculatively re-tuning working prompts or voice code you cannot run or hear risks breaking behavior that already works (violating the Prime Directive) and cannot be reported as a result. Ship the parts you can prove; **carry the unvalidatable refinement to the operator** (bootloader "Waiting on Danny") with a specific validation script, rather than guessing. *(Journal execution milestone, 2026-07-20.)*

## 8. Request-path safety (hard rule)

Interactive requests (views, signals, polling/evidence/scan APIs) may only **read** pre-computed snapshots/cache. **Never** compute heavy analytics or issue an inline LLM call on the request path; if data isn't ready, return "pending" — never a live fallback. Enqueue via `apps/core/celery_utils.py :: safe_enqueue` (non-blocking); post-write intelligence goes through `fire_intelligence()`. Enforced by `apps/core/tests/test_request_path_safety_contract.py`.

## 9. Exception handling

Never `except Exception: pass` on a critical path. Separate `ImportError` (optional module, expected) from `Exception` (real error, must be logged). Safety gates fail **closed**. Use `logger.warning`/`logger.error(exc_info=True)` — `logger.debug` is invisible in production.

## 10. Testing discipline

- **NEVER run the full ~4,400-test suite** unless Danny explicitly asks. Test the changed app + directly-impacted modules; `--keepdb` when a test DB exists.
- New intent → run `apps.ai.tests.test_intent_registration` (the 5-point registration gate) before deploying.
- Architecture-touching change → run the constitutional contract suite (`docs/WLJ_ACCEPTANCE_BASELINE.md §4`).
- Always `python3 manage.py makemigrations --check --dry-run` when a session touches model files.
- **Test the INVARIANT, not the implementation (REQUIRED when replacing an implementation).** When you migrate a key/surface from one producer to another (e.g. an SAE snapshot → a canonical accessor), do **not** carry over tests that assert the *old* implementation's mechanics. Rewrite each test to seed **real data** and assert the deterministic **invariant** (the behavior the product guarantees), then let it run against the **canonical runtime**. A test that `mock`s the retired implementation (e.g. patches `get_module_state` with a fake SAE dict) proves nothing about the replacement — **its failure is evidence of implementation coupling, not a product regression.** Precedent (2026-07-23): a mocked-SAE `test_temporal_sanity` case made a glucose delegation look like it dropped the future-timestamp guard; seeding a real future-dated row proved the platform layer (`truth/integrity.attach`) already owned the guard, and the delegation was correct. **Always verify behavior against the canonical runtime with real data before concluding functionality was lost.**

## 11. Deployment discipline

- **Application work is not complete until committed and pushed to `main`** unless Danny says otherwise. Deploy automatically — don't ask "ready to deploy?".
- Push: `GIT_SSH_COMMAND="ssh -p 443" git push git@ssh.github.com:djenkins452/dbawholelifejourney.git main`. Railway auto-deploys on push.
- **Fetch/parity checks use the same 443 SSH URL** — the default `origin` (github.com:22) is blocked and returns a *stale* `origin/main`. To verify parity: `GIT_SSH_COMMAND="ssh -p 443" git fetch git@ssh.github.com:djenkins452/dbawholelifejourney.git main:refs/remotes/origin/main`, then compare `git rev-parse HEAD` vs `origin/main`.
- **No prod CLI/SSH.** One-off prod changes go through a `RunPython` data migration only (the Procfile runs `migrate` every deploy). Data is **forward-only** — never un-migrate prod; ship a corrective migration.
- Vendored static asset? Run `python3 manage.py collectstatic --noinput` locally first (prod's manifest storage fails hard on missing maps/fonts/images).
- Temporary infra (debug endpoints/flags/glass-box) is production code — remove it **completely in one commit** and verify `manage.py check` before committing.

## 12. Documentation discipline

- **Every commit — even one line — gets a changelog entry** in `docs/wlj_claude_changelog.md` (date, changes, files, why). No exceptions.
- Features/enhancements also update user-facing docs (release notes, help topics, teaching destinations, features doc) per `docs/CLAUDE_DOC_UPDATES.md`.
- **Release altitude** (see `docs/WLJ_RELEASE_POLICY.md`): Level 1 technical changelog (every commit) → Level 2 milestone notes → Level 3 user-facing What's New (benefit-first, "your Chief of Staff", never a user AI name or provider name).
- Auto-maintain `docs/ENGINE_COS_REFERENCE.md` when touching engines/CoS context/schedules (note: that doc is pending a CURRENT-vs-historical decision — see inventory §6).

## 13. Escalate to Danny when…

A fix would touch a protected area's behavior; root cause can't be proven and the next step changes protected code; **blast radius is unclear**; scope creeps past the proven cause; a migration is irreversible or destructive; two valid fixes have materially different architectural tradeoffs; or a prompt instruction conflicts with the Constitution (state it, recommend the compliant path, open a Constitutional Review if it changes an Article).

## 14. Red lines (never autonomous)

- Editing/"tidying" the Constitution, Architecture Laws, Domain Registry, or Signal Ontology.
- Building a reasoning/conductor/classifier engine inside WLJ; letting the model fabricate state or turn a rollup into per-item truth.
- Adding a second writer to the execution path / a second "what to do now" selector.
- `except Exception: pass` on a critical path; making a safety gate fail open; concurrent state-mutating subagents.
- Broad refactors without explicit Danny approval ("while I'm here" modernization).
- Running the full suite unprompted; skipping scoped tests / migration check / changelog before deploy.
- Destructive git/DB ops (force-push, `reset --hard`, drop tables); deploying on an unproven root cause.

## 15. Closing a chat (Session Transition)

When Danny signals a chat is getting large or a body of work is done, close it by **improving the permanent startup package**, not by growing a handoff prompt — so the package gets more complete over time and the bootloader gets smaller.

- The **doctrine** (why/what a good transition achieves, where each kind of knowledge belongs) is `98_SESSION_TRANSITION_PROTOCOL.md` in this package.
- The **runnable procedure + Transition Audit checklist** is `@WLJ_SYSTEM_PROMPTS/99_PREPARE_NEXT_CHAT.md` — Danny drops that at the end of a chat.

Do not duplicate either here. Follow the protocol; produce the audit.
