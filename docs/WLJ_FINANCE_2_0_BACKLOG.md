# WLJ Finance 2.0 — Implementation Backlog

**Status:** PROPOSED — awaiting Danny's approval of the sequence.
**Governed by:** `docs/WLJ_FINANCE_2_0_ARCHITECTURE.md`.
**Rule:** phases are dependency-ordered. No phase starts before its inputs exist.

Progress is recorded HERE and in the changelog — never in the architecture document.

---

## Phase ladder

| Phase | Outcome | Unblocks |
|---|---|---|
| **0** | Asset registry + manual valuations *(SHIPPED)* | net worth completeness |
| **1** | Spending truth is trustworthy | every spending answer |
| **2** | Recurring obligations are known | free cash flow, bills, opportunities |
| **3** | Loan terms exist | all debt planning |
| **4** | Payoff engine | truck question, snowball/avalanche |
| **5** | Opportunity engine | the "$100/month" question |
| **6** | CoS financial tools | Danny can ASK instead of navigate |
| **7** | Plans, decisions, measurement | "did it work?" |
| **8** | Forecasting & scenarios | forward-looking guidance |
| **9** | Net-worth history & trends | "am I improving?" |
| **10** | Documents, investments | completeness |

---

## Phase 0 — Asset registry *(SHIPPED: `fbc786ee`, `51607e1a`)*

Verified complete (architecture §3). Residual items, deliberately deferred:

- **A-1** asset document attachment → Phase 10
- **A-2** stale-valuation prompt → Phase 9
- **A-3** entity usage on assets → Phase 1 (needs entities to exist at all)
- **A-4** asset in CoS truth → **Phase 6**

---

## Phase 1 — Spending truth

**Outcome:** "what did I spend" is correct, because transfers, refunds, reimbursements,
card payments and pending duplicates no longer distort it.

- **Data:** 3,792 existing transactions.
- **Models:** extend `Transaction` with `refund_of`, `reimbursement_state`,
  `is_card_payment` (derived, stored); category gains `essentiality`, `variability`,
  `controllability`.
- **Calculations:** `finance_calc.spending_predicate` (THE definition of money that left);
  `cashflow.period_totals`.
- **UI:** review queue for uncertain classifications; spending page.
- **CoS:** none yet.
- **Migration:** backfill classification over 3,792 rows; **dry-run + report first**.
- **Audit:** every reclassification audited; user corrections outrank derivation.
- **Acceptance:** the sum of "spending" excludes a known transfer pair, a refund, a
  card payment and a superseded pending row — each proven by test; a second definition
  of the predicate fails CI.
- **Risks:** mis-classifying a real expense as a transfer *understates* spending — the
  more dangerous direction. Bias to "uncertain, ask" over silent exclusion.
- **Non-goals:** no ML categorisation.

---

## Phase 2 — Recurring obligations

**Outcome:** WLJ knows what repeats — bills, subscriptions, income — from real history.

- **Data:** Phase 1 output. **0 recurring rows exist today; detection must create them.**
- **Services:** `recurring.detect` (cadence + amount tolerance + merchant identity),
  proposing candidates for confirmation — never silently creating obligations.
- **UI:** detected-recurring review; payment calendar.
- **Calculations:** `recurring.obligations`, `cashflow.free_cash_flow`.
- **Acceptance:** detection over Danny's real 3,792 rows proposes his actual subscriptions
  and misses none he names; every candidate is confirmable/rejectable.
- **Risks:** false positives create phantom obligations that distort free cash flow.
- **Non-goals:** no cancellation on Danny's behalf.

---

## Phase 3 — Loan terms *(BLOCKED on Danny's input)*

**Outcome:** each debt has APR, minimum payment, due date and term.

- **Models:** `LoanTerms` (architecture §7.1).
- **UI:** terms form per liability account; "what's missing" prompts.
- **Migration:** new table only. No backfill from the current products. APR/minimum/due
  date ARE obtainable for credit card and mortgage via Plaid Liabilities — a paid,
  unauthorised add-on (architecture §2a) — and are **not** available for auto loans at
  all. Manual and statement-derived entry are first-class, permanent paths.
- **Acceptance:** an account with no APR is explicitly *unknown* and is excluded from
  interest maths with a stated assumption; never defaulted.
- **Danny supplies (or Plaid Liabilities later provides for card + mortgage only):**
  APR, minimum payment, due date, remaining term. For the **truck this will be manual
  or statement-derived regardless** — auto loans are not a Liabilities subtype.
- **Non-goals:** no rate scraping, no APR inference, no defaulting, and no Liabilities
  API call (§2a.1 guardrail — a single call starts per-Item monthly billing).

---

## Phase 4 — Payoff engine

**Outcome:** snowball vs avalanche vs custom, compared honestly.

- **Data:** Phase 3.
- **Calculations:** `debt.amortise`, `debt.strategy`, `debt.schedule_summary`,
  `debt.roll_forward` — all versioned.
- **UI:** Debts & payoff surface; strategy comparison; roll-forward visualisation.
- **Acceptance:** hand-checked amortisation to the cent on a known loan; roll-forward
  proven; a missing APR degrades the answer rather than silently defaulting; the engine
  refuses to call snowball or avalanche universally better.
- **Risks:** a wrong payoff date is worse than none — golden-value tests required.

---

## Phase 5 — Opportunity engine

**Outcome:** "here is $100/month, specifically."

- **Data:** Phases 1–2.
- **Calculations:** `opportunity.estimate`, ranking (architecture §8.2).
- **UI:** Opportunities surface; accept/reject per candidate.
- **Acceptance:** named candidates summing ≥ $100/mo, each traced to transactions, each
  independently acceptable; inferred is visibly distinct from confirmed.
- **Non-goals:** no auto-cancellation.

---

## Phase 6 — CoS financial tools

**Outcome:** Danny asks instead of navigating.

- **Adds `asset` to `FinanceDomainTruth`** with the minimum-necessary shape
  (architecture §6) — closes A-4.
- **Tools:** the 15 in architecture §9.
- **Security:** identifier redaction extended; existing sweep test covers the new surface.
- **Acceptance:** CoS answers all three first-slice questions with an evidence packet
  and refuses when an input is missing.

---

## Phase 7 — Plans, decisions, measurement

`propose_plan` → `record_decision` → `check_plan_progress`. Projected vs realized,
reported without flattery.

## Phase 8 — Forecasting & scenarios
## Phase 9 — Net-worth history, trends, stale-valuation prompts
## Phase 10 — Documents, investments, allocation

---

## Package sizing — correction

An earlier draft named "Phases 1–6" as the first slice. **That is not a slice; it is
most of the programme.** It could not be independently verified, had no stop condition,
and would have run for weeks before anything was provable against Danny's real data.

Phases are now decomposed into **bounded packages**, each independently shippable,
independently verifiable, and each leaving WLJ in a coherent state if the next never
happens.

| Pkg | Outcome | Depends on | Ships |
|---|---|---|---|
| **P1** | Spending figures exclude transfers, refunds, card payments and superseded pending rows | — | predicate + backfill report |
| **P2** | Every category carries essentiality / variability / controllability | P1 | taxonomy + review UI |
| **P3** | "Largest controllable cost" is answerable on screen | P1, P2 | spending surface |
| **P4** | Recurring obligations detected and confirmed | P1 | detection + review |
| **P5** | Free cash flow + emergency-fund target | P4 | cash-flow service |
| **P6** | "$100/month" candidates named and acceptable | P3, P5 | opportunity engine |
| **P7** | Governed liability record with per-field provenance | — | `LoanTerms` + manual entry |
| **P8** | Payoff engine: baseline / snowball / avalanche / custom + roll-forward | P7 | debt calculations |
| **P9** | Truck payoff comparable | P7, P8 + Danny's data | — |
| **P10** | Redirect found money into a debt plan | P6, P8 | plan composition |
| **P11** | CoS answers with evidence packets | P3, P6, P8 | CoS tools + asset summary |
| **P12** | Accepted plans measured, projected vs realized | P10, P11 | measurement |

**Mapping to Danny's five questions:**

1. Largest controllable cost → **P3**
2. Find $100/month → **P6**
3. Redirect it into debt → **P10**
4. Compare truck payoff → **P9** (needs P7 + P8 + his data)
5. Did the plan work → **P12**

Note P7/P8 do **not** depend on P1–P6. Debt planning and spending truth are independent
tracks that meet at P10 — so if Danny's loan data arrives first, P7 can start
immediately.

---

## THE FIRST BUILD PACKAGE — P1 only

**Exactly one package. Not a phase, not a bundle.**

### User outcome
Danny's spending figures stop lying. Today a transfer between his own accounts, a credit
card payment, a refund, or a pending row later replaced by a posted one can all be
counted as money spent. Every number built on top of that — every opportunity, budget and
recommendation this architecture describes — inherits the error. **P1 makes "what I
spent" mean what it says.**

### Models / services
- `Transaction`: add `refund_of` (self-FK, nullable), `reimbursement_state`,
  `is_card_payment` (derived, stored, with provenance).
- **New:** `apps/finance/services/finance_calc/spending.py` ::
  `spending_predicate(user, start, end)` — the ONLY definition of "money that left".

### Authoritative calculation
`spending_predicate` returns a `CalcResult` carrying `coverage_start/end`,
`exclusions[]` (counts per exclusion reason), `calculation_version`, `confidence`,
`inputs_missing`. Every later spending figure derives from it. A CI contract test fails
the build if a second definition appears anywhere in `apps/finance`.

### UI
One surface only: a **classification review queue** listing transactions WLJ believes are
transfers / card payments / refunds, each confirmable or rejectable. No spending page yet
— that is P3.

### CoS contract
**None.** P1 ships no CoS tool. Nothing is exposed until the number is trusted.

### Production data prerequisites
None. 3,792 transactions and 6 accounts already exist. **P1 needs nothing from Danny** —
which is precisely why it goes first.

### Migrations / backfill
Schema migration is additive. The backfill classifies existing rows and is the risky
part.

**Dry-run requirement (blocking):** the backfill runs first in report-only mode and
produces counts by proposed classification, the resulting change in reported spend per
month, and a sample of each class for inspection. **Danny reviews that report before any
row is written.** No production write happens on the strength of a test suite alone.

### Tests
Transfer pair excluded; card payment excluded; refund netted against its original;
superseded pending row excluded; an ordinary expense **included**; a second predicate
definition fails CI; the backfill is idempotent; user confirmation outranks derivation;
`CalcResult` carries exclusions and version.

### Stop conditions
Stop and report — do not proceed — if any of these occur:
- the dry-run reclassifies **more than 5%** of transactions as non-spending;
- reported monthly spend moves by more than **10%** in any month;
- any confirmed-by-user classification would be overwritten;
- the predicate cannot explain a specific transaction Danny queries.

### Definition of done
Migration applied; dry-run reviewed and approved by Danny; backfill applied; review queue
live; all tests green; Finance regression green; changelog updated; **and Danny has
confirmed that a spending figure he can check by hand matches WLJ's**.

### Explicit non-goals for P1
No taxonomy, no opportunity ranking, no recurring detection, no CoS exposure, no
budgets, no debt work, no spending page.

---

## Later decisions requiring Danny's approval

| Decision | Needed before | Notes |
|---|---|---|
| P1 backfill dry-run sign-off | P1 write | blocking |
| Truck: connect institution **or** manual liability record | P9 | either is supported; no connection during architecture work |
| Loan terms data entry (APR, minimum, due date, term) | P7/P8 | manual or statement-derived; permanently supported |
| Emergency-fund target | P5 | one number from Danny |
| **Plaid Liabilities subscription** | any import of APR/minimum/due date | per-Item monthly, charged even when unused; §2a.1 guardrail |
| **Plaid Investments subscription** | any investments domain | per-Item monthly; currently `deferred` |
| Paid valuation provider | — | **declined**, standing |
| Outward action (payments, cancellations) | P10+ | needs a separate approval mechanism |
