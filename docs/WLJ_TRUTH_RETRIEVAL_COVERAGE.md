# WLJ Truth Retrieval — Certification Coverage Report (v0)

**Date:** 2026-07-18 · **Scope:** first vertical slice (Weight · Medications · Nutrition)
**Two owners:** Owner-1 = deterministic Layer-1 (provider returns the right value, no model) · Owner-2 = Customer Truth (real question → gateway → ModelInterface → grounded answer).

> **Integrity note — this report does NOT claim domains are certified because a slice passed.** Every cell carries an explicit evidence tier:
> - **✅ executed** — a deterministic test ran and asserted the value (no OpenAI).
> - **◐ provider-assessed** — the provider capability is known from the read-only audit; no slice test has executed it yet.
> - **⧗ pending live run** — requires the Customer Truth run through the real gateway/ModelInterface (needs OpenAI + the deployed worker); **not runnable from the build environment** — Danny must execute it.
> - **✗ missing** — no provider/surface exists (additive follow-on milestone).

---

## By runtime surface
| Surface | Status | Why |
|---|---|---|
| **Deterministic Layer-1 (Owner-1)** | partially executed | Medicine history executed ✅; Weight/Nutrition deterministic tests are the next increment ◐ |
| **Customer Truth — synchronous gateway path (Owner-2)** | ⧗ not yet certified | Harness is retargeted (`a009c35b`) but no live Deep run has executed on the deployed worker at that commit |
| **Streaming worker path (SSE)** | ✗ not yet certified | Shares the `generate` core (proven), but the `chat_stream_bus` relay wrapper is uncertified — separate thin suite |

---

## Capability matrix (deterministic, v1 — generated from `capability_matrix()`)
✓ certified (passing deterministic spec) · ◐ assessed (provider `supports()` implies it, no spec yet) · ✗ gap (declared missing) · — n/a

| domain | current | historical | latest | timeline | list | count | existence | comparison |
|---|---|---|---|---|---|---|---|---|
| **health** (weight) | ✓ | ✓ | ✓ | ✓ | ◐ | ✗ | ◐ | ✓ |
| **medicine** | ✓ | ✓ | ◐ | ◐ | ✓ | ✗ | ✓ | ✗ |
| **nutrition** | ✗ | ✗ | ✓ | ✗ | ✓ | — | ✓ | ✗ |
| calendar | ◐ | — | ◐ | — | — | — | — | — |
| faith | ◐ | — | ◐ | — | — | — | — | — |
| finance | ◐ | — | ◐ | — | — | — | — | — |
| journal | ◐ | — | ◐ | — | ◐ | — | ◐ | — |
| legacy | ◐ | — | ◐ | — | ◐ | — | ◐ | — |
| relationships | ◐ | — | ◐ | — | — | — | — | — |
| tasks | ◐ | — | ◐ | — | — | — | — | — |

**Totals across 10 registered domains × 8 capabilities:** 12 certified · 22 assessed · 7 gaps · 39 n/a. **Slice = 14 deterministic specs** (`test_truth_retrieval_slice`, green, no OpenAI). This matrix is the primary planning artifact — the ◐ cells are the next deterministic-certification targets; the ✗ cells are the additive truth follow-ons (nutrition date-scoping is the highest-value one).

---

## Weight (health domain)
| Question | Category | Provider surface | Owner-1 | Owner-2 |
|---|---|---|---|---|
| What do I weigh? | Current fact | `health.current("weight_yesterday")` (latest ≤ today) | ◐ | ⧗ |
| Weight on a seeded date? | Historical fact | `health.history("weight", custom)` point | ◐ | ⧗ |
| Latest recorded weight? | Latest | `health.current("weight_yesterday")` | ◐ | ⧗ |
| Weights in a seeded range? | Timeline | `health.history("weight", period)` | ◐ | ⧗ |
| Latest lower than previous? | Comparison | `health.history("weight")` → last two points | ◐ | ⧗ |
| **Current waist measurement?** | Current fact | **none — `BodyMeasurementSession` unexposed** | **✗ missing** | ✗ |

**Weight verdict:** current/history/timeline **provider-assessed available**; body-measurement/comparison-of-circumference **missing provider** (additive follow-on). Deterministic tests pending.

## Medications (medicine domain)
| Question | Category | Provider surface | Owner-1 | Owner-2 |
|---|---|---|---|---|
| What meds am I taking? | List | `medicine.describe("medication")` / `current("current_medications")` | ◐ | ⧗ |
| Is a named med active? | Existence | `medicine.describe_one(name)` | ◐ | ⧗ |
| Latest medication state? | Latest/Current | `medicine.current("medication_execution_today")` | ◐ | ⧗ |
| **What medication history is available?** | Historical/Timeline | `medicine.history("adherence")` | **✅ executed** (fixed 2026-07-18) | ⧗ |
| Adherence-history contract mismatch | (contract) | declared vs raised | **✅ resolved** — real `HistorySeries` | — |

**Medications verdict:** **history capability certified deterministically** (`test_adherence_history_fulfils_the_advertised_contract`, 18 tests green — the audited `KeyError` mismatch is fixed). List/existence/current **provider-assessed**; Customer Truth pending live run.

## Nutrition (nutrition domain)
| Question | Category | Provider surface | Owner-1 | Owner-2 |
|---|---|---|---|---|
| What did I eat today? | Current/List | `nutrition.describe("food")` — **no date filter** | ◐ (thin) | ⧗ |
| What did I eat yesterday? | Historical | `describe("food")` — model must date-scope | ◐ (thin) | ⧗ |
| Latest meal? | Latest | `describe("food")` (recent 40) | ◐ | ⧗ |
| When did I last eat <food>? | Existence | `nutrition.describe_one(name)` (last match only) | ◐ | ⧗ |
| Have I eaten <food>? | Existence | `describe_one(name)` | ◐ | ⧗ |
| Daily calories/protein? | Current fact | **none via DomainTruth** (only SAE state) | ✗ (no `current()`) | — |

**Nutrition verdict:** entity retrieval **provider-assessed**, but **date-scoping is a known thin spot** (no date filter, no `current()`/`history()`) — the highest-value additive fix for this domain. Deterministic tests pending.

---

## By question category (slice domains)
| Category | Executed ✅ | Provider-assessed ◐ | Missing ✗ |
|---|---|---|---|
| Current fact | — | weight, meds, (nutrition daily via SAE) | body-measurements, nutrition `current()` |
| Historical fact | medicine adherence history | weight-on-date | — |
| Latest | — | weight, meds, meal | — |
| List | — | meds, foods | — |
| Timeline | medicine adherence (weekly) | weight range | nutrition, most non-health |
| Existence | — | named med, named food (last-only) | full occurrence history/count |
| Comparison | — | weight last-two | body-measurement comparison |

---

## Date/time semantics (to prove in the deterministic slice — user timezone, explicit calendar days)
`resolve_period` supports: `today`, `yesterday`, `last_7_days`, `this_week`/`last_week`, `this_month`/`last_month`, quarters, years, and `custom(start,end)` — all resolved against `get_user_today(user)` (**user-local**, not UTC). The slice fixtures must seed at explicit user-local dates and assert `today`/`yesterday`/specific-date/latest/bounded-range against that timezone. The broader UTC-vs-user-local **ingestion** decision stays a separate backlog item.

---

## What Danny must run (cannot execute from the build environment)
1. **Deploy** `a009c35b`+ to the **`wlj-worker`** service (the Deep run executes there) and the **web** service (for the CoS suite). `/_health/` reports WEB only — verify worker separately.
2. **Run a Deep "Truth Certification" acceptance run** from the Acceptance Center → the new evidence columns (runtime/tool/args/provider/records/first-failing-layer) populate against **ModelInterface**. That is the Owner-2 result that turns every ⧗ into a real pass/fail with a first-failing-layer.

## Next increment (build-side, no production access needed)
- Weight + Nutrition deterministic (Owner-1) fixtures + provider tests → flip their ◐ to ✅/✗.
- Formalize the shared data-driven question spec (Phase 4) consumed by BOTH owners.
- Regenerate this report from the executed results.
