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

**Outcome:** each financial measure means what its name says — gross purchases, net
spending, cash outflow, debt service, transfers and income stop being one number wearing
different labels (architecture §5.0).

- **Data:** 3,792 existing transactions.
- **Models:** extend `Transaction` with `economic_role`, `role_confidence`,
  `role_source` and `refund_of`. NOT `is_card_payment` — `transfer_kind` already
  carries it. Category taxonomy moves to P2 where it belongs.
- **Calculations:** `finance_calc.roles :: classify` (THE economic-role authority) +
  `finance_calc.measures` (the nine projections, architecture §5.0). The term
  `spending_predicate` is retired — see §5.0.8.
- **UI:** review queue for uncertain classifications; spending page.
- **CoS:** none yet.
- **Migration:** backfill classification over 3,792 rows; **dry-run + report first**.
- **Audit:** every reclassification audited; user corrections outrank derivation.
- **Acceptance:** the classification contract test reproduces the §5.0.4 matrix exactly
  and the §5.0.9 reconciliation identities hold. A grep-style test is explicitly
  rejected — it would pass while the numbers were wrong.
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
| **P1** | Nine named financial measures, each meaning what it says | — | role classification + measures + dry run |
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

## THE FIRST BUILD PACKAGE — P1 (revised)

**P1 = economic role classification + the measure contract. One package.**

The earlier P1 promised "one predicate for what I spent". That shape was wrong
(architecture §5.0): a mortgage payment is cash leaving, a balance-sheet movement, and
partly not consumption — no boolean survives it. P1 now delivers **one classification
feeding nine named measures.**

### User outcome
Danny can ask a *specific* financial question and get a figure that means what its name
says: gross purchases, net spending, cash outflow, debt service and transfers stop being
the same number wearing different labels. A card payment stops being counted as spending
twice. A refund reduces spending instead of arriving as income.

### Reuse — no parallel system
Extends what exists: `transfer_state` (confidence, incl. `candidate`), `transfer_kind`
(four roles already detected), `transfer_detection.classify / pair_transfers /
confirm_transfer`, and `attribution_population.financial_activity` — **already the shared
definition** for Budget, FinanceHistory, snapshots, dashboard and CoS, which becomes the
`net_spending` projection. Pending→posted needs nothing: `sync_service` already replaces
the pending row in place.

### Models / services
- `Transaction.economic_role` (choices per §5.0.2) + `role_confidence` + `role_source`
  (`derived | provider | user`), user outranking derivation.
- `refund_of` self-FK — refund **offsetting** is the genuine gap; detection already
  exists via `transfer_kind='refund'`.
- `finance_calc/roles.py :: classify` — the one authority.
- `finance_calc/measures.py` — the nine projections, each returning `CalcResult`.

### Authoritative calculations
The nine measures of §5.0.3, obeying the reconciliation identities of §5.0.9. Debt
service stays **unsplit with a stated limitation** until `LoanTerms` exists (P7) — it is
never invented.

### UI
One surface: the **classification review queue** — `uncertain` rows, unmatched-counterpart
transfers and cash withdrawals, each confirmable. No spending page (P3).

### CoS contract
**None.** P1 exposes nothing to CoS. Numbers earn exposure after Danny trusts them.

### Production prerequisites
None. 3,792 transactions, 6 accounts. **Requires nothing from Danny** — why it is first.

### Migrations / backfill
Additive schema. The backfill assigns roles to existing rows.

### Report-only dry run (BLOCKING — writes nothing)

Produces, per transaction class and in total:

| Section | Contents |
|---|---|
| Per-row | current classification · proposed economic role · confidence · **reason** · affected measures |
| Monthly totals | current vs proposed, for all nine measures, every month covered |
| Offsets | refund and reimbursement offsets applied, with counts and amounts |
| Exclusions | transfer and card-payment exclusions, counted separately |
| Debt service | unsplit amounts, count and total, with the limitation stated |
| Uncertain | rows requiring review, by reason (unmatched counterpart · cash withdrawal · low confidence) |
| Impact | by month **and** by category |
| Samples | representative **redacted** rows per class — no full merchant strings where identifying |
| **Reconciliation** | gross purchases · refunds/reimbursements · net spending · debt service · transfers/allocations · income · cash inflow · cash outflow — **must balance to §5.0.9 or the run is reported as failed** |

**Approval rule:** the 5% reclassification and 10% monthly-movement thresholds remain as
**automatic warning gates**, but they are **not** approval. **Every production backfill
requires Danny's explicit review and authorisation regardless of how small the change
is.** A change of 0.1% still waits.

### Tests
Classification contract: a fixture of **one transaction per class in §5.0.4** produces
exactly that matrix. Reconciliation identities hold on real-shaped data. Card payment
excluded from net spending while its purchase is included (**the double-count rule**).
Refund offsets net spending, keeps its audit identity, retains the original category, and
does **not** appear as income. Unmatched-counterpart transfer stays `uncertain` and
enters no measure. Cash withdrawal is in outflow, not in net spending. Unsplit debt
service is in outflow and debt service, not net spending, and carries the limitation.
Both refund period policies produce the documented, labelled result. User classification
outranks derivation. Backfill idempotent. Measures report `uncertain_count/amount`.

### Stop conditions (halt and report)
- Reconciliation identities fail on production-shaped data.
- Dry run reclassifies **>5%** of transactions *(warning gate)*.
- Any measure's monthly total moves **>10%** *(warning gate)*.
- Any user-confirmed classification would be overwritten.
- `uncertain` exceeds **10%** of transactions or **15%** of outflow — the classifier is
  not ready.
- The classifier cannot explain a specific transaction Danny queries.

### Definition of done
Migration applied · dry run produced, reviewed and **explicitly authorised by Danny** ·
backfill applied · review queue live · classification contract and reconciliation tests
green · Finance regression green · changelog updated · **and Danny confirms that at least
one figure he checks by hand — a month's net spending and that month's card payments —
matches WLJ and is not double-counted.**

### Explicit non-goals
No controllability taxonomy (P2) · no spending page (P3) · no recurring detection (P4) ·
no opportunity ranking (P6) · no `LoanTerms` or principal/interest split (P7) · no CoS
exposure (P11) · no budgets, no goals, no debt work.

---

## Later decisions requiring Danny's approval

| Decision | Needed before | Notes |
|---|---|---|
| P1 backfill dry-run sign-off | P1 write | **blocking — required for EVERY backfill regardless of size** |
| Truck: connect institution **or** manual liability record | P9 | either is supported; no connection during architecture work |
| Loan terms data entry (APR, minimum, due date, term) | P7/P8 | manual or statement-derived; permanently supported |
| Emergency-fund target | P5 | one number from Danny |
| **Plaid Liabilities subscription** | any import of APR/minimum/due date | per-Item monthly, charged even when unused; §2a.1 guardrail |
| **Plaid Investments subscription** | any investments domain | per-Item monthly; currently `deferred` |
| Paid valuation provider | — | **declined**, standing |
| Outward action (payments, cancellations) | P10+ | needs a separate approval mechanism |

---

# IMPLEMENTATION STATUS LEDGER — 2026-08-31

Built under Danny's overnight autonomous-build authorization. This section records what
is **actually deployed**, what it refuses to do, and what is genuinely outstanding.

## P1 — economic roles and the nine measures · **SHIPPED AND ACTIVE**

Classifier `1.2.1`, measures `1.2.1`. Backfilled on production: **3,795 transactions, 0
unclassified**, in 8 transactional batches. A second run wrote 0 and reported 3,795
unchanged. All six reconciliation identities hold. Rendered Finance truth was byte-identical
either side of the backfill.

Three defects were found by rehearsing against real history, each only visible once the
previous one was removed:

1. **Borrowing counted as a refund.** `_looks_like_refund` treats any credit that is
   neither a transfer nor INCOME as a refund. 259,531.55 of loan disbursements were
   offsetting 335,225.50 of purchases and driving net spending negative in 9 of 25 months.
   A refund now requires evidence — a proven `refund_of` link or a provider detail that
   actually says refund/return.
2. **Mortgage payments labelled card payments.** `_transfer_kind` calls any
   liability-touching transfer a credit-card payment, which removed mortgage payments from
   spending *and* from debt service. Classification now reads the SETTLED LIABILITY.
   Debt service moved from 49,550.35 to 106,112.61.
3. **A credit on a liability is not proof of borrowing.** 249,246.70 of credits on a credit
   card carried `LOAN_DISBURSEMENTS` and each matched, to the cent and month, a payment
   leaving chequing. Removing them made cash inflow equal income plus refunds **exactly**
   (419,725.18). The rule now follows the INSTRUMENT: closed-end debt can only receive a
   payment; a revolving credit without a visible counterpart is held for review.

**Residual, deliberately not fixed:** 62 rows / 258,387.28 of revolving-liability credits
sit in review because WLJ cannot pair them. The architecturally correct fix is to improve
pairing inside `transfer_detection` — a separate, reviewable change with real blast radius
on `financial_activity`. Holding them misstates nothing: they are on card accounts, so they
touch no cash measure, and card purchases are already counted from the card side.

## P2 — controllability · **SHIPPED**
Three axes (necessity, variability, levers), not one enum. Precedence: transaction >
series > payee > rule > category; within a scope, user beats inference. Unclassified spend
is reported as unclassified — never as uncontrollable.

## P3 — recurring detection · **SHIPPED**
Detector `1.0.0`. Proposes candidates; only a CONFIRMED series enters
`recurring_obligations`. Variable series count at their ceiling. Cross-referenced to the
existing `RecurringTransaction` templates so one subscription is never shown as two.

## P5 — savings opportunities · **SHIPPED**
Engine `1.0.0`. Requires a confirmed series AND a user-recorded lever. Answers "largest
controllable cost" and "find $X a month", or names exactly what is missing.

## P6 — loan terms · **SHIPPED**
Per-FIELD provenance and as-of dates. Manual entry is permanent and first-class.
`LoanTermsChange` is append-only.

## P7 — payoff engine · **SHIPPED**
Payoff `1.0.0`. Minimum/snowball/avalanche/custom, extra payments, lump sums,
roll-forward, promotional rates, non-convergence. Missing minimum → that debt is excluded
and named, the rest still get a plan. Missing APR → balance-only mode, interest UNKNOWN
not zero. Never declares a winner between snowball and avalanche.

## P9 — governed CoS evidence · **SHIPPED**
Nine packets on `FinanceDomainTruth`. Redaction enforced by a test that walks every packet.
Every packet carries as-of, calculation version, assumptions, exclusions, confidence,
missing inputs, and an explicit instruction not to recompute.

## P10 — the workspaces · **SHIPPED**
Spending & Cash Flow · Money Review · What You Can Change · Debts & Payoff. Full
ordinary-user CRUD, four Current Context providers, navigation, help, teaching
destinations, release notes.

## NOT BUILT — and why

| Package | State | Blocker or reason |
|---|---|---|
| **P4 budgets, reserves, cash-flow forecast** | not built | Depends on confirmed recurring obligations, of which Danny has zero. The forecast would be a projection over an empty commitment set — a number that looks authoritative and means nothing. Build after the review queue is worked. |
| **P8 net-worth history / investments** | not built | Asset Registry, manual valuations and asset-loan links already ship and are untouched. Governed historical snapshots remain outstanding. Plaid Investments NOT activated. |
| **P11 action plans and realized outcomes** | partial | `SavingsOpportunity` carries `realized_monthly_savings`, `observed_from` and `variance`, and projected is never merged with realized. The observation job that populates them is not built. |
| **P12 data-health checks** | partial | Coverage, held-for-review and missing-terms are surfaced on the pages and in the `data_health` packet. The scheduled sweep is not built. |
| Pairing improvement in `transfer_detection` | not attempted | Would change `financial_activity` for every existing surface. Needs its own rehearsal and sign-off. |
