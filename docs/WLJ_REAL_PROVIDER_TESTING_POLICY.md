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
