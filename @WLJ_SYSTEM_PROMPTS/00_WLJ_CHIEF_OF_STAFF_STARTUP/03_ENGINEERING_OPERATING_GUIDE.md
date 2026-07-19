# 02 · Engineering Operating Guide

**Responsibility of this document:** how to safely evolve WLJ inside the Constitution. Runtime tracing, root-cause proof, deployment discipline, documentation discipline, product-first engineering, results-not-intentions, and the Session Transition Protocol. It does **not** restate the Articles (that's `02_WLJ_CONSTITUTION.md`) or Danny's collaboration preferences (that's `03`).

Supersedes and merges the retired `00_CORE_STARTUP/WLJ CLAUDE OPUS 4.8 EXECUTION PLAYBOOK.md`.

---

## 1. Prime directive

**Aggressive execution inside protective boundaries — never aggressive architectural mutation.**

> Read speed is free; write speed is earned. **Investigate broadly. Mutate surgically.**

Velocity comes from collapsing *investigation* time, not from skipping the gate before a *write*. And one measure sits above the rest: every change exists to make the **WLJ Chief of Staff** something a paying customer trusts enough to rely on every day. Correct engineering, passing tests, and clean architecture are necessary but never sufficient — they are the means; a *more trusted Chief of Staff* is the end. **The implementation is not the product; the trusted conversation is.**

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

## 7. Results, not intentions

Report what actually happened. If tests fail, say so with the output. If a step was skipped, say so. Persist observed results with provenance — never inferred intent. WLJ facts are never fabricated; the model may reason from facts but may never invent one.

## 8. Request-path safety (hard rule)

Interactive requests (views, signals, polling/evidence/scan APIs) may only **read** pre-computed snapshots/cache. **Never** compute heavy analytics or issue an inline LLM call on the request path; if data isn't ready, return "pending" — never a live fallback. Enqueue via `apps/core/celery_utils.py :: safe_enqueue` (non-blocking); post-write intelligence goes through `fire_intelligence()`. Enforced by `apps/core/tests/test_request_path_safety_contract.py`.

## 9. Exception handling

Never `except Exception: pass` on a critical path. Separate `ImportError` (optional module, expected) from `Exception` (real error, must be logged). Safety gates fail **closed**. Use `logger.warning`/`logger.error(exc_info=True)` — `logger.debug` is invisible in production.

## 10. Testing discipline

- **NEVER run the full ~4,400-test suite** unless Danny explicitly asks. Test the changed app + directly-impacted modules; `--keepdb` when a test DB exists.
- New intent → run `apps.ai.tests.test_intent_registration` (the 5-point registration gate) before deploying.
- Architecture-touching change → run the constitutional contract suite (`docs/WLJ_ACCEPTANCE_BASELINE.md §4`).
- Always `python3 manage.py makemigrations --check --dry-run` when a session touches model files.

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
