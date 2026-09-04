# Real Provider Testing Policy

**Status:** ENFORCED IN CODE (2026-08-20). This is not guidance — the governor refuses.

> **NO EXPLICIT AUTHORIZATION → NO REAL PROVIDER CALL.**
> **AUTHORIZATION → HARD FINITE BUDGET → FAIL CLOSED WHEN EXHAUSTED.**

---

## Why this exists

A development session made **63 paid provider calls** (~$3.57–4.94) against Danny's OpenAI
account without anyone deciding it should happen. Nothing in the codebase could have stopped
it:

- the only precondition for a real request was a non-empty API key;
- there was no budget, cap or counter anywhere;
- local calls recorded **$0.00** because the local price book was empty, so no dashboard,
  report or alert ever showed them;
- unlabelled traffic defaulted to `production`, so development spend was auto-classified as
  real customer usage;
- the *only* thing actually blocking local provider access was an unrelated settings bug —
  which the developer diagnosed and worked around.

It was discovered from a credit-card auto-recharge. Documentation asking people to be careful
had been in place the whole time.

**Claude Code does not have standing permission to spend Danny's OpenAI credits.**

---

## What does NOT count as authorization

None of these permit a paid call:

- a configured `OPENAI_API_KEY`;
- milestone language such as *"real-model smoke allowed"*, *"Tier-2 permitted"*,
  *"production-equivalent validation"*, *"validate with the real model"*;
- a previous authorization (they do not carry forward);
- Claude's own judgment that a real call is warranted;
- "just one more verification call".

Authorization is **Danny explicitly approving that specific paid test**.

---

## Before asking for one

State these five things, then WAIT:

1. What exact uncertainty remains?
2. Why deterministic/mocked testing cannot answer it.
3. Why Danny's normal use of WLJ cannot provide the evidence.
4. Exactly how many real provider calls are proposed.
5. The maximum number that will be allowed.

If those lack concrete answers, there is no request to make.

## Even when approved — bare minimum

Use the fewest calls physically necessary, normally **one**. Never run matrices, never
simulate long conversations, never test multiple personas through the provider when prompt
inspection establishes the difference, never repeat a successful test for confidence. **If
one call answers the question, STOP.**

---

## Default testing strategy

Real calls are the **last resort**, not normal validation. Use, in order:

deterministic unit tests · contract tests · lifecycle tests · mocked provider responses ·
fixtures · browser/UI tests · prompt & envelope inspection · `ToolCallLog` evidence ·
canonical database/state inspection · **recorded evidence from Danny's actual WLJ use**

---

## How the governor works

**One admission seam.** `apps/ai/llm_admission.py`. Every provider request in WLJ goes through
a client object, so the guard wraps the *client*: `build_guarded_client()` returns a proxy
that admits or refuses each billable operation immediately before the network call. That
governs all 34 call sites — including ones not yet written — without touching them.

**Not on the API key.** A key is configuration. Emptying it at runtime would be a
process-local mutation that web and worker would disagree about.

**Environment policy**

| Environment | Behaviour |
|---|---|
| **Production** (`RAILWAY_GIT_COMMIT_SHA` set, or `WLJ_ENV=production`) | Real customer traffic admitted unconditionally and accounted as before. **Unaffected.** |
| **Everything else** (local, CI, shells) | **DENY by default.** Requires `WLJ_ALLOW_REAL_LLM=1` **and** a live `WLJ_LLM_RUN_ID`. |

**The budget is a database row, not an environment integer.** Web and worker are separate
processes; an env-var count would let each believe it owned the whole budget. A single
conditional `UPDATE … WHERE calls_remaining > 0` is atomic, so the N+1th call is refused no
matter how many processes race. Retries and tool-loop continuations each consume one call,
because each is a real billable request.

**Fail closed.** If the budget store is unreachable, the call is denied. We do not spend money
when we cannot account for it.

---

## Authorization workflow (Danny only)

```bash
python manage.py authorize_real_llm --calls 1 --reason "persona smoke test"
```

It requires an **interactive terminal** and a typed confirmation. That is the technical
control that stops automated tooling — Claude Code included — from self-authorizing: a
non-interactive shell has no TTY and cannot get past it. Authorization is narrow by design
(small count, stated purpose, expiry) — it approves *this test*, not "real AI testing on".

The command prints what to export:

```bash
export WLJ_ALLOW_REAL_LLM=1
export WLJ_LLM_RUN_ID=wlj-llm-…
```

Review spend afterwards:

```bash
python manage.py llm_dev_usage --days 7
```

### The rule for Claude Code

Claude may **consume** a budget Danny has already approved, for the purpose he approved.
When it is exhausted: **STOP.**

- Do **not** reset it.
- Do **not** mint another authorization.
- Do **not** switch environments (`WLJ_ENV=production` to escape the governor is a serious
  violation, not a workaround).
- Do **not** use another API key.
- Do **not** ask the governor for one more call because the last one nearly worked.

Report what was learned with the budget that was given, and ask.

---

## Accounting fixes that came with the governor

**Unattributed ≠ production.** `traffic_class` now defaults to `unattributed`. Production is
asserted by the certified production path. A missing classification must never mean "a real
user did this".

**Unknown cost ≠ $0.00.** `LLMUsageEvent.cost_is_known` distinguishes a genuine zero from a
model with no price-book entry. Unpriced calls are reported as **UNPRICED with their token
counts**, never folded into a dollar total, and logged at WARNING. **No price is ever
fabricated** — pricing comes from the existing authoritative `seed_pricebook` command.

**Attribution.** A paid development call is stamped with `metadata.llm_run_id` and classified
as certification traffic, so every authorized call traces back to the authorization that
permitted it.

---

## Enforced by

`apps/core/tests/test_llm_admission_contract.py` — 34 tests, **all mocked, zero provider
calls**. We do not spend money to prove that code prevents spending money.

Including a structural (AST, not grep) CI gate: **if any module constructs an OpenAI client
outside the approved seam, CI fails.** That is the bypass that made the original overspend
possible.

---

## Provider-backed PROACTIVE AI — PAUSED for pre-production (2026-08-20)

> **ENVIRONMENT decides whether real product traffic may use the provider.**
> **WORKLOAD ORIGIN decides whether AUTONOMOUS provider spend is authorized.**

Being in production is **not** permission for a background job to spend money. Without that
split, any future scheduled feature would start consuming credits merely by shipping.

**Why it was paused.** WLJ is not in production use, yet provider-backed proactive work was
costing **~$1.09/day (~24% of production spend)**, firing whether or not anyone opened the
app: the Daily Executive Brief ($2.55 / 36 calls over 3 days) and proactive check-ins ($0.72
/ 25 calls).

### What is paused

Only **provider-backed autonomous generation**:

| Path | Behaviour while paused |
|---|---|
| PGS cycle (`run_proactive_guidance_scheduler`) | returns `{"status": "skipped", "reason": "proactive_ai_disabled"}` before querying users |
| Daily Executive Brief | returns `None` before taking the daily lock — nothing is marked delivered |
| Proactive check-ins (midday / evening) | not reached; also refused at the admission seam |
| Conversation follow-ups | returns before claiming a follow-up, so none is stranded in `delivering` |

### What is NOT paused

- **User-initiated Chief of Staff conversation** — completely unaffected, including the
  streaming worker task (it runs in a worker, but a human asked for it).
- **All deterministic background processing** — SAME/ISE cycles, snapshots, aggregation,
  cleanup. Anything that costs no provider money keeps running.
- **PGS architecture, beat/scheduler infrastructure, deterministic scheduling, proactive
  configuration (`assistant_proactive_checkins`), the Brief and check-in architecture, and
  their tests.** Nothing was deleted or redesigned. This is a pause.

### How it is enforced

Two layers, deliberately:

1. **Authoritative gate at the admission seam** (`may_real_llm_call`), checked *before* the
   production allow. Autonomous work is refused in every environment when the flag is off —
   so a future scheduled feature that forgets to check still cannot spend.
2. **Clean early exits** at each orchestration entry point, so jobs skip tidily: no provider
   calls, no exceptions implying service failure, no retry storms, no fabricated
   `LLMUsageEvent` rows, and the scheduler stays healthy.

A workload is autonomous when it runs inside `autonomous_workload(...)` **or** carries a
`proactive`/`background` traffic class — which every existing scheduled provider path
already sets.

### Proven state — HELD, pending a separately-authorized experiment (2026-09-04)

What follows is only what was **observed**, in production, on 2026-09-04. It contains no
statement about environment configuration, because configuration was never read.

| Proven | Evidence |
|---|---|
| Autonomous provider attempts were **refused** | Admission denied the calls at the seam |
| Those refused attempts consumed **0 tokens / $0.00** | Cost ledger, `traffic_class: proactive` — 2 calls, 0 input, 0 output, $0.00, 2 failures |
| Deterministic fallback messaging after a refusal is **removed** | `author_checkin` no longer calls `current_action_directive`; asserted by contract |
| A refusal now means **silence** | `RealLLMCallDenied` handled explicitly; nothing is published |
| OpenAI can explicitly choose **`NO_MESSAGE`** when authoring is admitted | Silence affordance in the user turn; `declined` outcome honoured |
| Check-in **decisions are audited** | `ToolCallLog` `kind="checkin"`, outcome ∈ authored / declined / refused / quiet / empty / error, with envelope telemetry |
| A **cross-producer interruption cooldown** is enforced | Atomic claim at the single delivery seam; per user, not per check-in type |

**What is NOT proven.** Whether the environment flag is set either way — that requires
reading the configuration, which was not done. A refusal is evidence the gate denied a call;
it is not a reading of the environment. (An earlier changelog entry inferred the opposite
value from the opposite behaviour; both inferences were unsound and are corrected in place.)

**What has still never happened.** The usefulness gate has not run in production even once.
Every proactive message delivered to date was authored by WLJ, not chosen by the model — so
the architecture being certified (WLJ detects, OpenAI decides whether speaking is
worthwhile, silence is valid) remains unexercised by real traffic.

**Status: HELD.** Proactive behaviour stays disabled pending a separately-authorized
production usefulness experiment. The `kind="checkin"` audit rows are what will make that
experiment measurable — how many decisions reached authoring, how many chose silence, and
whether what arrived was worth the interruption.

### Re-enabling (Danny only)

Set on the Railway environment (both **web** and **worker**), then redeploy:

```
WLJ_PROACTIVE_AI_ENABLED=true
```

Default is `false`, so it stays off unless deliberately turned on. **Claude Code must never
set this flag** — re-enabling provider-backed proactive execution is a product/environment
decision, exactly like authorizing a paid test. Enforced by contract test: no code path
assigns it and no management command turns it on.

Re-enable when validating proactive features deliberately, or at launch readiness. Verify
afterwards with `manage.py llm_dev_usage --days 1` and `/owner/finance/`.

---

## Operator diagnostics in production — CLOSED 2026-09-02

**The hole.** `may_real_llm_call` admits production unconditionally, which is right:
real customers must never be refused. But an operator endpoint that *runs in* production
inherited that permission. On 2026-09-02 a verification call to `cos-run` ran a real
Chief-of-Staff turn and spent credits with nobody having authorized it.

**Being in production is not evidence that a human asked for this particular call.**
The governor already knew that for *autonomous* work — `current_workload_is_autonomous()`
is checked BEFORE the production allow for exactly this reason. Diagnostics needed the
same treatment and did not have it.

**The gate.** `diagnostic_workload(reason, authorized_calls=0)` marks a block as operator
diagnostic. `may_real_llm_call` checks it before the production allow and refuses unless
a budget was granted:

| Situation | Outcome |
|---|---|
| Customer request in production | admitted (`production_runtime`) — unchanged |
| Diagnostic, no authorization | **refused** (`diagnostic_not_authorized`) |
| Diagnostic, `authorized_calls=N` | admitted for exactly N, then refused |

**Using it.** `cos-run` authorizes nothing by default and passes `0` to the worker, so a
plain verification call now fails closed with an explanation. A real call requires:

```
?authorize_paid_calls=<1..5>&authorized_by=<who agreed>
```

Both are required, the count is capped, and authorizing writes a `SecurityAuditLog` row
(`resource_id="cos-run"`) **before** the run — recording the number and who agreed, and
storing only the email domain, not the address. The result carries `provider_spend`
saying how many calls were actually made.

**Normal verification does not need this.** Use the truth probe, `finance-audit`,
deterministic fixtures, DB/state inspection, or `ToolCallLog` — all read-only and free.
A diagnostic that needs the model to answer its question is usually asking the wrong
question.

Enforced by `apps/ai/tests/test_diagnostic_spend_gate.py`, including that the gate is
ordered before the production allow — after it, production would admit everything.
