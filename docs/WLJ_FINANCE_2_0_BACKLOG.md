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
- **Migration:** new table only; no backfill possible — **Plaid does not supply APR**.
- **Acceptance:** an account with no APR is explicitly *unknown* and is excluded from
  interest maths with a stated assumption; never defaulted.
- **Danny must supply:** APR, minimum payment, due date, remaining term for the
  mortgage, the credit card, and the truck loan (§ Missing information).
- **Non-goals:** no rate scraping, no APR inference.

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

## THE FIRST IMPLEMENTATION SLICE

**Goal:** make these three answerable — *truthfully*:

1. What is my largest easily controllable cost?
2. How can I save $100 a month and direct it toward debt?
3. What is the best plan for paying off my truck?

**Slice = Phase 1 + Phase 2 + Phase 3 + minimal Phase 4 + minimal Phase 5 + Phase 6.**

That is the honest floor, and it is bigger than it looks. Question 1 needs spending truth
*and* a controllability taxonomy. Question 2 needs recurring detection *and* opportunity
ranking *and* free cash flow. Question 3 needs loan terms — **which do not exist and
cannot be imported.**

### Required inputs before ANY of the three can be claimed answerable

| Input | Exists? | Source |
|---|---|---|
| Transactions | ✅ 3,792 | Plaid |
| Spending predicate (transfer/refund/card-payment safe) | ❌ | Phase 1 |
| Category controllability taxonomy | ❌ | Phase 1 |
| Recurring obligations | ❌ (0 rows) | Phase 2 detection |
| Free cash flow | ❌ | Phase 2 |
| Emergency-fund target | ❌ | Phase 2 (needs Danny's target) |
| **Truck loan account** | ❌ **not present in the 6 accounts** | Danny |
| **APR / minimum / term / due date** | ❌ | Danny (Phase 3) |
| Payoff maths | ❌ | Phase 4 |
| Opportunity ranking | ❌ | Phase 5 |
| CoS tools | ❌ | Phase 6 |

**Until every row above is ✅, WLJ must not claim to answer these questions.** Stating a
payoff plan without an APR, or "your biggest controllable cost" without a controllability
taxonomy, would be exactly the confident-but-ungrounded answer this architecture exists
to prevent.

### Suggested build order within the slice

`1 → 2 → 3 (Danny's data) → 4 → 5 → 6`, shipping and validating each against Danny's real
data before the next. Phase 3 can be gathered in parallel — it is data entry, not code.
