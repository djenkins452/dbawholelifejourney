# WLJ Finance 2.0 — Personal Financial Operating System

**Status:** ARCHITECTURE — ratified design, not yet implemented beyond Phase 0.
**Created:** 2026-08-30
**Governs:** every Finance change from this point. New Finance work conforms to this
document or amends it deliberately.
**Companion:** `docs/WLJ_FINANCE_2_0_BACKLOG.md` (phased, dependency-aware backlog).

---

## 0. North star

> Finance today **displays** money. Finance 2.0 helps Danny **decide** about money.

The system is finished when it can answer, truthfully and with its work shown:

1. What is my largest controllable cost right now?
2. Where can I realistically save $100 a month?
3. Which of those changes would disrupt my life least?
4. I want to pay off my truck — what is the best strategy given my actual finances?
5. How do snowball, avalanche and a custom plan compare?
6. When one debt dies, where should its payment go?
7. Can I pay debt faster without eating my emergency fund?
8. Did the thing I actually did produce the savings we predicted?

**Four rules bind every answer:**

| Rule | Meaning |
|---|---|
| **Grounded** | Every figure traces to a WLJ record. No number originates in a conversation. |
| **Deterministic** | A named Python service computes it. The language model NEVER does arithmetic. |
| **Transparent** | Assumptions, coverage period, exclusions and calculation version travel with the answer. |
| **Honest** | Missing is *unknown*, never `$0.00`. Stale says how stale. Inferred says inferred. |

This is the Personal Truth Platform contract applied to money: **WLJ knows, the model
reasons.** A payoff schedule is not an opinion, and it must never be produced by one.

---

## 1. Current maturity assessment

**Overall: Finance is a competent system of RECORD with almost no system of DECISION.**

The plumbing is genuinely strong — Plaid ingestion is hardened, duplicate prevention is
constraint-backed, categorisation is user-authoritative, the asset registry is complete
and the accounting contract is proven. What is missing is everything *above* the ledger:
there is no loan-terms domain, no payoff engine, no opportunity ranking, no forecast, and
the Chief of Staff has no purpose-built financial reasoning tools.

**The decisive finding is not code — it is data.** A read-only production audit
(2026-08-30, user `dannyjenkins71@gmail.com`):

| Domain | Rows in production |
|---|---|
| Accounts | 6 |
| Transactions | 3,792 |
| Goals | 1 |
| Metric snapshots | 1 |
| **Recurring** | **0** |
| **Budgets** | **0** |
| **Entities** | **0** |
| **Attributions** | **0** |
| **Opportunities** | **0** |
| **Tangible assets** | **0** |
| **Personal categories** | **0** |

Seven domains have shipped code, passing tests, and **zero rows**. They are *unexercised*,
not proven. A capability with no data has never met reality, and several of the questions
above depend on exactly those domains. **This gap is the roadmap's real starting point.**

---

## 2. Capability matrix

Legend — `complete` (works, exercised in production) · `partial` (works, gaps)
· `immature` (code exists, unexercised or thin) · `missing` (no implementation)
· `blocked` (needs a decision or external input).

| # | Capability | State | Evidence |
|---|---|---|---|
| 1 | Institutions & connections | **complete** | `BankConnection`, OAuth, reauth, disconnect; 2 live connections; webhook verification + rejection recording |
| 2 | Accounts & balances | **complete** | `FinancialAccount`, 6 live, institution-grouped UI, `select_related` |
| 3 | Transaction ingestion | **complete** | `sync_service` + cursor + per-connection lock + `uq_txn_provider_id_per_active_account`; 3,792 rows |
| 4 | Scheduled reconciliation | **complete** | `sync_reconciliation`, hourly crontab, 6h staleness, dry-run + audit block |
| 5 | Categories & classification | **complete** | `TransactionCategory`, inline picker + full CRUD, `category_source='user'` outranks provider |
| 6 | Transfer detection | **partial** | `transfer_detection.py`, `transfer_state/kind/pair`; unproven at scale, no refund/reimbursement concept |
| 7 | Duplicate prevention | **complete** | partial unique index + idempotent `get_or_create`; 1,677 historical duplicates remediated |
| 8 | Recurring bills / subscriptions / income | **immature** | `RecurringTransaction` + `recurring.py` exist; **0 rows**; no detection from 3,792 transactions |
| 9 | Budgets | **immature** | `Budget` model + pages; **0 rows**; no sinking funds, no reserves, no rollover in use |
| 10 | Financial goals | **partial** | `FinancialGoal`, 1 row; linked-account derivation shipped; no funding plan, no automation |
| 11 | Entities & attribution | **immature** | full model set (`FinancialEntity`, `AccountEntityAssignment`, `TransactionAttribution`, `AttributionRule`) + review workspace; **0 rows** |
| 12 | Opportunities & insights | **immature** | `FinanceOpportunity` + `opportunity_detection` + lifecycle; **0 rows**; no ranking model |
| 13 | **Assets, valuations, loan links** | **complete** | `TangibleAsset` / `AssetValuation` / `AssetLoanLink`; 11/11 CRUD verified (§3); accounting proven in production |
| 14 | **Liabilities & loan terms** | **missing** | **No APR, interest method, minimum payment, due date, term, or payoff quote anywhere.** Verified absent from `FinancialAccount` |
| 15 | **Debt payoff planning** | **missing** | No amortisation, snowball, avalanche, roll-forward or interest-saved calculation exists |
| 16 | Investments / retirement / allocation | **missing** | No holding, security, ticker, share or cost-basis model |
| 17 | Net worth (point in time) | **complete** | `asset_registry.net_worth_breakdown` — single authority, `reconciles` flag, drill-down page |
| 18 | Net worth history / trends | **immature** | `FinancialMetricSnapshot` exists; **1 row**; no scheduled capture, no trend surface |
| 19 | Cash-flow forecasting | **missing** | No forward projection of any kind |
| 20 | Spending taxonomy (essential/discretionary/fixed/variable) | **missing** | Categories carry no controllability or elasticity dimension |
| 21 | Finance → CoS truth | **partial** | `FinanceDomainTruth` exposes 7 entity types; **no `asset`**; no calculators, no scenarios |
| 22 | Freshness / evidence / audit | **partial** | `FinanceAuditLog`, sync freshness, `CurrentTruth`; no unified evidence packet, no calculation versioning |
| 23 | User correction | **partial** | Category, attribution, valuation corrections exist; no correction of APR/terms (nothing to correct) |
| 24 | Documents & source evidence | **missing** | `TransactionImport` only; no statement/appraisal/title storage |
| 25 | Scenario planning | **missing** | No what-if engine |
| 26 | Realized-vs-projected tracking | **missing** | Opportunity lifecycle has states but no measurement |
| 27 | Currency presentation | **complete** | `finance_format` (`money` / `money_signed` / `money_abs`); 19 templates; audit tests |
| 28 | Valuation providers | **blocked** | Adapter boundary shipped, `PROVIDERS == {}` — **by Danny's decision** (§5) |

**Score: 8 complete · 6 partial · 6 immature · 7 missing · 1 blocked.**

---

## 3. Asset Registry verification (deployed `fbc786ee` + `51607e1a`)

Verified read-only against deployed production code. **The contract is met in full.**

| Required | Verified | Route / evidence |
|---|---|---|
| Create | ✅ | `finance:asset_create` |
| View | ✅ | `finance:asset_detail` |
| Edit | ✅ | `finance:asset_update` |
| Archive | ✅ | `finance:asset_archive` |
| View archived | ✅ | `asset_list` renders `archived_assets` |
| Restore | ✅ | `finance:asset_restore`; `_owned()` uses `all_objects` so an archived asset is reachable |
| Safe delete | ✅ | `finance:asset_delete`, refused while valuations/links exist ("Archive it instead") |
| Append-only manual valuations | ✅ | `record_valuation` only ever `objects.create`; no update path |
| Valuation history + provenance | ✅ | 20 fields incl. `source`, `source_detail`, `effective_date`, `created_at`, `retrieved_at`, `range_low/high`, `confidence`, `limitations`, `notes` |
| Link / unlink loan | ✅ | `asset_loan_link`, `asset_loan_unlink` (takes `pk` + `link_id`) |
| Gross value / linked debt / net equity | ✅ | `current_value`, `linked_debt`, `net_equity` |
| Gross value in net worth, debt not double-subtracted | ✅ | Proven in production: linking the mortgage moved net worth **$0.00** |
| Asset types | ✅ | real_estate, vehicle, boat, rv, other |
| Ownership isolation | ✅ | non-owner **403**, anonymous **302**, neither leaking |
| Audit redaction | ✅ | no address, VIN, hull id or postal code in any payload |
| Responsive | ✅ | 480px breakpoints, 44px targets, no fixed layout widths |

**Gaps recorded, not rebuilt:**

- **A-1** No asset *document* attachment (appraisal PDF, title, purchase invoice).
- **A-2** No valuation *reminder* when a manual valuation goes stale (age is shown; nothing prompts).
- **A-3** Assets carry no `entity` usage in practice (0 entities exist).
- **A-4** Asset is absent from CoS truth (§6) — the single highest-value gap.

---

## 4. Target architecture — 16 capability areas

Finance 2.0 is four layers. Nothing may skip a layer.

```
   L4  DECISION      opportunities · payoff plans · scenarios · accepted actions
                     ── CoS reasons here, over L3 outputs only ──
   L3  CALCULATION   deterministic services; versioned; assumption-carrying
   L2  DERIVED TRUTH recurring · taxonomy · terms · equity · freshness
   L1  RECORD        accounts · transactions · assets · valuations · links
```

| # | Area | Target |
|---|---|---|
| 1 | Accounts & connectivity | *(complete)* — add connection-health surfacing to CoS |
| 2 | Transaction truth | Add **refund**, **reimbursement**, **pending→posted** and **credit-card payment** as first-class states beside `transfer_state`, so none distorts spending |
| 3 | Income & cash-flow forecast | Identify recurring income; project 30/60/90-day balance and free cash flow |
| 4 | Spending taxonomy | Every category gains **essentiality** (essential/discretionary), **variability** (fixed/variable/irregular) and **controllability** (cancellable/negotiable/reducible/avoidable/deferrable/fixed) |
| 5 | Bills & payment calendar | Detected recurring items + due dates + a forward calendar |
| 6 | Budgets & reserves | Envelope-style plan, sinking funds, emergency-fund target |
| 7 | Assets, liabilities, equity, history | *(assets complete)* — add scheduled net-worth snapshots and a trend surface |
| 8 | **Debt terms & payoff** | New `LoanTerms` domain + payoff engine (§7) |
| 9 | Savings goals | Funding plans; auto-progress from linked accounts *(shipped)* |
| 10 | Investments | Holdings, allocation, retirement — **deferred**, lowest decision value today |
| 11 | Ownership & attribution | Personal / household / Beacon *(model exists, unexercised)* |
| 12 | Documents | Attach appraisal, statement, title, payoff quote where it is evidence |
| 13 | Freshness & corrections | One evidence envelope on every answer (§5.3) |
| 14 | **Opportunities & realized results** | Ranking engine + accept/reject + measurement (§8) |
| 15 | Scenario planning | What-if over payoff, budget and goal funding |
| 16 | CoS integration | Purpose-built tools, never raw DB (§9) |

**What WLJ adopts from the market, and what it does differently.**

Benchmarked against current sources for [Monarch](https://www.thepennyhoarder.com/budgeting/monarch-money-review/),
[YNAB, Rocket Money and Simplifi](https://blog.myfinancialfreedomtracker.com/en/budgeting-tool-comparison),
and [debt-payoff apps](https://spendify.money/blog/best-debt-payoff-apps/):

- **Adopt:** Rocket Money's recurring/subscription surfacing; Monarch's account breadth
  and net-worth roll-up; YNAB's every-dollar-has-a-job discipline for *reserves*;
  Empower's allocation view *(later)*.
- **Do NOT adopt:** YNAB's mandatory envelope ceremony (too heavy for a truth platform),
  Rocket Money's "we cancel it for you" model (WLJ takes no outward action without a
  separately designed approval path).
- **The gap WLJ fills:** the benchmark review is explicit that most of these apps
  *track* debt balances but **cannot compare payoff strategies or compute a debt-free
  date**; YNAB alone offers a loan planner. **A deterministic, explainable payoff engine
  wired to a conversational Chief of Staff who knows the rest of Danny's life —
  obligations, goals, upcoming events — is the differentiator.** Nothing on the market
  answers "pay the truck off faster *without* touching the emergency fund, given what
  else is coming".

---

## 5. Deterministic calculation authorities

**Rule: one named service owns each calculation. The model may only READ its output.**

| Calculation | Authority (module :: function) | Status |
|---|---|---|
| Net worth, gross assets, liabilities | `asset_registry :: net_worth_breakdown` | **exists** |
| Tangible value, linked debt, equity | `asset_registry :: current_value / linked_debt / net_equity` | **exists** |
| Financial-account totals | `asset_registry :: net_worth_breakdown` | **exists** |
| Spending & income by period | `finance_calc.cashflow :: period_totals` | new |
| Controllable spending | `finance_calc.taxonomy :: controllable_spend` | new |
| Recurring obligations | `finance_calc.recurring :: obligations` | new |
| Monthly free cash flow | `finance_calc.cashflow :: free_cash_flow` | new |
| Emergency-fund requirement | `finance_calc.reserves :: emergency_target` | new |
| Loan amortisation | `finance_calc.debt :: amortise` | new |
| Snowball / avalanche / custom | `finance_calc.debt :: strategy(kind)` | new |
| Payoff dates, total interest, interest saved | `finance_calc.debt :: schedule_summary` | new |
| Payment roll-forward | `finance_calc.debt :: roll_forward` | new |
| Goal funding | `finance_calc.goals :: funding_plan` | new |
| Opportunity estimates | `finance_calc.opportunity :: estimate` | new |
| Projected vs realized | `finance_calc.opportunity :: realized` | new |

### 5.1 Distortion control (non-negotiable)

Spending and cash flow MUST exclude, by construction: internal transfers, credit-card
payments, refunds matched to an original charge, reimbursements, and pending rows later
superseded by a posted row. Each is a **typed state on the transaction**, not a filter
re-invented per caller. One predicate — `finance_calc.spending_predicate` — is the only
definition of "money that actually left". A contract test rejects any second definition.

### 5.2 Estimates and assumptions

Every calculated figure returns a value **and** its provenance:

```
CalcResult(
    value, unit, as_of, coverage_start, coverage_end,
    calculation_version,     # bump = the maths changed; old answers stay explicable
    inputs_used, inputs_missing,
    assumptions[],           # "APR unknown, excluded from interest total"
    confidence,              # high | medium | low
    exclusions[],            # transfers, refunds, pending
    is_estimate,
)
```

A missing input **narrows the answer or refuses it**. It never becomes a zero.

### 5.3 Evidence envelope

Every CoS-facing fact carries: `source`, `as_of`, `coverage`, `freshness`,
`calculation_version`, `exclusions`, `confidence`, `missing_inputs`. Terse by design —
an envelope nobody can read is not transparency.

---

## 6. Governed CoS asset summary (closes gap A-4)

`FinanceDomainTruth.entity_types` gains `asset`, exposing **only**:

```
asset:  name · type · current_value · valuation_source · valuation_effective_date
        valuation_age_days · is_stale · linked_liabilities[{name, current_balance}]
        total_linked_debt · net_equity · included_in_net_worth
        missing[] · confidence
```

**Never:** street address, VIN, hull id, title number, postal code, plaid ids, raw
provider payloads, notes, or purchase documentation. This is the *minimum necessary* to
answer a net-worth or debt question — nothing that identifies the physical object.

Enforced by an existing test that sweeps every `_describe*` method for known secrets; it
extends to cover the new surface rather than being replaced.

---

## 7. Debt-planning engine

### 7.1 New domain: `LoanTerms`

A liability **account** carries a balance. A **loan** carries terms. These are different
things and the second does not exist yet.

```
LoanTerms (1:1 optional with FinancialAccount, liability types only)
    apr, interest_method (simple|compound|precomputed)
    minimum_payment, contractual_payment, payment_frequency
    due_day_of_month, remaining_term_months, origination_date
    payoff_quote_amount, payoff_quote_expires_on
    secured_asset → TangibleAsset (nullable)
    promo_apr, promo_expires_on
    fees, has_prepayment_penalty
    user_priority (int), user_constraint (text)
    source (statement | user_entered | provider), as_of, confidence
```

Every field is **user-entered and correctable**, each with an `as_of`. Plaid does not
supply APR for these accounts; pretending otherwise would be the fabrication this
architecture forbids.

### 7.2 Strategies compared

`minimum_only` (baseline) · `snowball` (smallest balance) · `avalanche` (highest APR) ·
`custom` (Danny's priority) · `+ extra monthly` · `+ one-time lump sum` · all with
**roll-forward** — a retired debt's payment cascades to the next.

Each returns: payoff order, per-debt payoff date, total interest, months saved vs
baseline, monthly commitment, and **cash released** at each payoff.

### 7.3 Honesty requirements

- **Snowball is not always suboptimal and avalanche is not always optimal.** The engine
  reports the true difference (often small) and lets motivation count.
- A missing APR **excludes that debt from interest totals and says so** — it does not
  assume a rate.
- A payoff quote has an **expiry**; past it the figure is stale, not wrong.
- Recommendations are checked against the emergency-fund target and upcoming
  obligations before being offered.

---

## 8. Spending-opportunity engine

### 8.1 What "controllable" means

Three independent axes, none inferable from a category name alone:

- **Essentiality** — essential · discretionary
- **Variability** — fixed · variable · irregular
- **Controllability** — cancellable · negotiable · reducible · avoidable · deferrable · fixed

Plus: personal vs Beacon, one-time vs recurring, and **confirmed fact vs inferred
opportunity** — which must be visually and verbally distinct.

### 8.2 Ranking

`score = savings_potential × confidence × recurrence ÷ (effort × disruption)`, adjusted
by Danny's stated preferences and by goal/debt impact. Weights are configuration, not
magic constants, and the score is always shown decomposed.

### 8.3 The "$100 a month" contract

A recommendation must: name **specific candidates totalling ≥ $100/mo**; state for each
*why it looks controllable* and *from which transactions*; let Danny accept or reject
each individually; and then **measure whether the saving actually happened** — comparing
the following periods' spend on that candidate and reporting projected vs realized
without flattering itself.

---

## 9. CoS financial-intelligence contract

**Tools (governed, purpose-built — never raw DB access):**

`get_financial_snapshot` · `explain_net_worth` · `explain_cash_flow` ·
`get_assets_and_equity` · `get_top_spending` · `get_controllable_costs` ·
`get_recurring_obligations` · `get_savings_opportunities` · `compare_periods` ·
`run_debt_payoff_scenario` · `explain_recommendation` · `get_data_health` ·
`propose_plan` · `record_decision` · `check_plan_progress`

**CoS must never:** invent a balance, APR, valuation, payment, estimate or category;
present provisional history as complete; move money, pay, cancel, trade or change an
account without a separately designed approval mechanism; hide assumptions or material
alternatives; or imply professional tax, legal or investment advice — WLJ provides
planning information, and says so.

---

## 10. User experience

**Navigation:** Overview · Accounts & connections · Transactions & review · Spending &
cash flow · Bills & recurring · Budgets & reserves · Assets & net worth · **Debts &
payoff** · Goals · **Opportunities & accepted actions** · Reports & trends · **Data
health**.

**The dashboard leads with decisions, exceptions, progress and next actions** — not every
number it happens to know. Numbers are one click away; judgement is on the surface.

**Journeys** (all seven required, each with a defined honest-failure path):

1. Create → value → edit → archive → restore → safely delete an asset. *(shipped)*
2. Link a mortgage/auto loan; read gross value, debt, equity. *(shipped)*
3. Find $100/mo and redirect it to debt.
4. Compare truck payoff: snowball vs avalanche vs custom.
5. Accept a plan; track actual progress.
6. Ask CoS *why* — receive the evidence packet, not a restatement.
7. **Degraded truth:** missing APR, stale balance, incomplete history, uncertain
   categorisation, year-old manual valuation. Each names what is missing, what it
   prevents, and what Danny can do — never a confident number over a hole.

---

## 11. Non-goals for Finance 2.0

- No paid valuation provider (§ Danny's decision, restated below).
- No outward action: no payments, transfers, cancellations or trades.
- No investment/retirement domain in the first phases — lowest decision value now.
- No tax, legal or investment advice.
- No scraping, ever.
- No scheduled job that creates recurring external cost.

---

## 12. Valuation decision (recorded, current)

**Danny is not authorising or paying for an external valuation service.** No ATTOM,
HouseCanary, KBB InfoDriver, J.D. Power, Black Book or ABOS. No credentials, no provider
calls, no scheduled refresh, no scraping, and **no estimated depreciation formula**.

Danny looks values up himself — Zillow or an appraisal for real estate, KBB for vehicles,
J.D. Power/NADA or comparables for boats, appraisals or purchase documents for other
property — and records them. WLJ supports value, source name, effective date, entry date,
optional URL/reference, optional low/high range, condition/mileage/hours basis, notes and
limitations. History stays append-only; **missing means unknown, never zero**.

The `valuation_providers` adapter boundary is **retained** for a possible future
decision. `PROVIDERS` stays empty until Danny separately decides otherwise.
