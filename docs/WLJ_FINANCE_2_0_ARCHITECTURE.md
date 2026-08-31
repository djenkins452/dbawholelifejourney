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
| 14 | **Liabilities & loan terms** | **missing-in-WLJ** | No APR, interest method, minimum payment, due date, term or payoff quote exists in WLJ — verified absent from `FinancialAccount`. **Partly obtainable** from Plaid Liabilities (paid, unauthorised) for credit card and mortgage; **not** for auto loans (§2a) |
| 15 | **Debt payoff planning** | **missing** | No amortisation, snowball, avalanche, roll-forward or interest-saved calculation exists |
| 16 | Investments / retirement / allocation | **missing-in-WLJ** | No holding, security, ticker, share or cost-basis model in WLJ. **Obtainable** via Plaid Investments (paid, unauthorised) — holdings, securities, investment transactions, cost basis where the institution reports it (§2a) |
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

## 2a. Provider capability — corrected

An earlier draft of this document said loan terms were **"not importable"**. That was
wrong, and wrong in the place it mattered most. Plaid sells a **Liabilities** product
that returns exactly those fields for some account types. The corrected picture:

### Maturity terminology (used consistently from here)

| Term | Meaning |
|---|---|
| `missing-in-WLJ` | WLJ has no implementation. Says nothing about availability. |
| `available-existing-product` | Obtainable now, from a product WLJ already pays for. |
| `available-paid-addon` | Obtainable, but only by subscribing to an additional billed product. |
| `unavailable-from-provider` | The provider does not offer it at all. |
| `deferred` | Deliberately postponed; not a gap. |

Conflating these is how "we haven't built it" becomes "it can't be done".

### Plaid Liabilities — what it actually returns

Supported types are **`credit` / `credit card`**, **`credit` / `paypal`**,
**`loan` / `student`**, and **`loan` / `mortgage`**
([API reference](https://plaid.com/docs/api/products/liabilities/),
[product docs](https://plaid.com/docs/liabilities/)).

| Field WLJ needs | Credit card | Mortgage | Student | Auto loan |
|---|---|---|---|---|
| APR / interest rate | `aprs[].apr_percentage` | `interest_rate.percentage` (nullable) | `interest_rate_percentage` | — |
| Minimum / next payment | `minimum_payment_amount` | `next_monthly_payment` | `minimum_payment_amount` | — |
| Next due date | `next_payment_due_date` | `next_payment_due_date` | `next_payment_due_date` | — |
| Term / maturity | — | `loan_term`, `maturity_date` | `expected_payoff_date` | — |
| Origination | — | `origination_date`, `origination_principal_amount` | `origination_date`, `origination_principal_amount` | — |
| Prepayment penalty | — | `has_prepayment_penalty` | — | — |
| Last statement / payment | `last_statement_balance`, `last_payment_amount` | `last_payment_amount` | `last_payment_amount` | — |

**Auto loans are not a supported Liabilities subtype.** So for Danny's truck:

- the loan is **absent from WLJ today** — that is a data-entry gap, not a failure;
- if he connects the institution, its **balance** may arrive through the products WLJ
  already uses, if Plaid exposes that account at all;
- its **APR, minimum payment, due date, remaining term and payoff quote will almost
  certainly be user-maintained or statement-derived**, and that is a **first-class
  supported path**, not a degraded one.

**Coverage is not guaranteed even where supported.** Plaid states APR data "is not
provided by all card issuers; if APR data is not available, this array will be empty",
and several loan fields are nullable or of limited availability. Any design that assumes
a field arrives because it is documented will produce confident holes.

**One more consequence worth stating:** the mortgage payload includes
`property_address`. If Liabilities is ever enabled, that field must be dropped at the
ingestion boundary — it is exactly the identifier §6 forbids in CoS evidence.

### Plaid Investments — what it actually returns

[Investments](https://plaid.com/docs/investments/) returns holdings
(`quantity`, `cost_basis`, `institution_price`, `institution_value`, `tax_lots`),
securities (`ticker_symbol`, `name`, `close_price`, `type`, `sector`) and up to 24
months of investment transactions. Cost basis is holding-level; **lot detail is empty
when the institution does not report it**, and `vested_*` is often null.

The corrected finding is therefore four separate statements, not one:
WLJ has no investments domain (`missing-in-WLJ`) · Plaid offers one
(`available-paid-addon`) · coverage and fields vary · **no subscription or
implementation is authorised**.

### 2a.1 The Plaid cost boundary — a hard guardrail

Liabilities and Investments are **subscription-billed per Item**
([billing](https://plaid.com/docs/account/billing/)). Two facts make this sharper than
ordinary cost:

1. **"Plaid will charge for the subscription even if no API calls are made for the
   Item"** — and the subscription persists until `/item/remove` or the user
   depermissions. Cost is not proportional to use.
2. A product **can be added to an existing Item simply by calling one of that product's
   endpoints**. There is no separate "are you sure" step.

Together those mean **a single stray API call can begin an open-ended monthly charge on
every connected Item.** Therefore, as a standing engineering rule:

> **No WLJ code path may call a Liabilities or Investments endpoint, add either product
> to Link, or initialise a new Item, until Danny has separately approved the spend.**
> This belongs in the same category as the real-provider LLM governor: not a preference,
> a guardrail.

Before that approval is even requested, this must be established: exact production
pricing; institution and account-type coverage for Danny's actual banks; the benefit
over manual entry; the consequences for existing Items; and whether the recurring cost
is justified by decisions it would improve.

**Nothing in this architecture authorises it.**

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

Benchmarked against **official product documentation** for the defined comparison set.
An earlier draft cited review blogs and drew a claim ("most apps cannot compare payoff
strategies") that the evidence did not support. Replaced.

| Capability | [YNAB](https://www.ynab.com/features) | [Monarch](https://www.monarch.com/) | [Rocket Money](https://www.rocketmoney.com/) | [Empower](https://www.empower.com/personal-investors/financial-tools) |
|---|---|---|---|---|
| Account aggregation | ✅ "link your accounts" | ✅ "All your accounts, in one place" | ✅ link checking/savings/cards/investments | ✅ |
| Categorization | ✅ "Category Templates" | ✅ transaction management | ✅ "monitors your spending by category" | ✅ "Transactions" |
| Recurring detection | not stated on page | ✅ "automatically detects your recurring subscriptions" | ✅ "Subscription Management" | not stated |
| Budgeting | ✅ core envelope model | ✅ "Budget" | ✅ "Create a budget that works for you" | ✅ "Budgeting & Cash Flow" |
| Controllable-spend insight | not stated | reports only | ✅ cancellation + "Bill Negotiation" | not stated |
| Net worth | ✅ "net worth reports" | ✅ "Net Worth" | ✅ "assets & debt in one place" | ✅ "Net Worth" |
| Property / manual assets | not stated | ✅ manual asset tracking | assets shown | not stated |
| Investments | not stated | ✅ investment tracking | ✅ linkable | ✅ "Portfolio Analysis" |
| Goals | ✅ "Goal tracking" / targets | ✅ "Plan — set goals" | ✅ "Financial Goals" | ✅ "Savings Planner" |
| Debt tracking | ✅ "debt management tools" | implied via planning | ✅ within net worth | ✅ "Debt Paydown" |
| **Payoff planner** | ✅ **"loan planner… how much interest and time you'll save"** | not officially named | **not offered** (absent from official pages) | ✅ "Debt Paydown" |
| **Snowball vs avalanche comparison** | not documented | not documented | not documented | not documented |
| Recommendation transparency | n/a | n/a | n/a | n/a |
| Realized-savings tracking | not stated | not stated | savings claimed via negotiation | not stated |

**How to read the blanks.** "Not documented" means *absent from the official sources
inspected on 2026-08-30* — it is **not** proof the feature does not exist in-product.
Marketing pages are incomplete by nature. Quicken Simplifi was not inspected and is
therefore not represented.

**Adopt:** Rocket Money's recurring/subscription surfacing; Monarch's account breadth,
net-worth roll-up and manual asset tracking; YNAB's every-dollar discipline for
*reserves*; Empower's emergency-fund framing.

**Do not adopt:** YNAB's mandatory envelope ceremony (too heavy for a truth platform);
Rocket Money's cancel-and-negotiate-on-your-behalf model (WLJ takes **no outward action**
without a separately designed approval path).

**The narrower, defensible differentiation WLJ targets** — stated without claiming
others cannot do it:

> Not "a payoff engine nobody else has". Payoff planners plainly exist (YNAB's loan
> planner, Empower's Debt Paydown). What WLJ targets is a payoff engine whose
> **inputs, assumptions, exclusions and calculation version are inspectable**, whose
> **every loan field carries its own provenance and as-of date**, which **refuses to
> compute what it cannot ground**, which is **wired to a conversational layer that also
> knows the rest of Danny's life** — upcoming obligations, goals, the emergency fund —
> and which **measures whether the accepted plan actually worked**. The differentiator is
> auditable grounding and life-context integration, not the arithmetic.

---

## 5. Deterministic calculation authorities

**Rule: one named service owns each calculation. The model may only READ its output.**

| Calculation | Authority (module :: function) | Status |
|---|---|---|
| Net worth, gross assets, liabilities | `asset_registry :: net_worth_breakdown` | **exists** |
| Tangible value, linked debt, equity | `asset_registry :: current_value / linked_debt / net_equity` | **exists** |
| Financial-account totals | `asset_registry :: net_worth_breakdown` | **exists** |
| Economic role classification | `finance_calc.roles :: classify` (extends `transfer_detection`) | new |
| The nine measures (§5.0.3) | `finance_calc.measures :: <measure>` | new |
| Net spending | `measures :: net_spending` (projection of `financial_activity`) | extends existing |
| Controllable spending | `finance_calc.measures :: controllable_spending` (subset of `purchase` ∩ classification ∩ confidence) | new |
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

### 5.0 Financial measures — one classification, nine answers

An earlier draft proposed a single `spending_predicate`: one boolean deciding whether
money "actually left". **That is the wrong shape.** "What did I spend" is not one
question, and a boolean cannot answer nine of them. Worse, a mortgage payment is
simultaneously real cash leaving, a balance-sheet movement, and — in part — not
consumption at all. No boolean survives that.

**Corrected design: ONE authoritative classification, MANY derived measures.**

Every transaction is assigned exactly one **economic role**. Measures are then
*projections* over those roles. Adding a measure never means re-deciding what a
transaction is.

#### 5.0.1 Reuse, not replacement

WLJ already has most of this and it must be extended, not duplicated:

| Existing | Reused as |
|---|---|
| `Transaction.transfer_state` (`unknown / not_transfer / candidate / confirmed`) | the **confidence** axis — `candidate` already means "held for review, never guessed" |
| `Transaction.transfer_kind` (`internal_transfer / credit_card_payment / refund / reversal`) | four of the economic roles, already detected |
| `transfer_detection.classify / pair_transfers / confirm_transfer` | the classifier — extended, not replaced |
| `attribution_population.financial_activity` | **already "THE shared definition"** consumed by Budget, FinanceHistory, snapshots, dashboard and `FinanceDomainTruth` |
| `provider_pending_transaction_id` promotion in `sync_service` | pending→posted, **already solved at ingestion** — the posted row replaces the pending one in place |
| `category_source='user'` precedence | the user-outranks-derivation rule |

**`financial_activity` becomes the `net_spending` projection** rather than being
superseded. A new parallel spending system is forbidden.

**Two corrections to my own earlier P1 claim:** superseded pending rows are *already*
handled at ingestion, so they were never the distortion I described; and `refund_of` was
proposed as a new field when `transfer_kind='refund'` already exists — what is genuinely
missing is not refund *detection* but refund **offsetting**, which today does not exist
anywhere (refunds currently flow through as positive amounts alongside income).

#### 5.0.2 Economic roles

```
purchase                 goods/services acquired (debit or credit card, cash, ACH)
refund                   money back from the original merchant
reimbursement            a third party repaying the user (employer, Beacon, person)
reversal_chargeback      the institution undoing a transaction
income                   earned or other true income
internal_transfer        the user's own money between their own accounts
card_payment             paying a credit card the user holds
savings_allocation       into a savings account/goal
investment_contribution  into an investment account (withdrawal is the inverse)
debt_service             a loan payment (see §5.0.5)
fee_or_interest_charged  bank fee, card interest, overdraft — a real cost
cash_withdrawal          cash out; downstream use unknown (§5.0.6)
uncertain                cannot be classified confidently — counted in NO measure
```

Roles are **mutually exclusive**. `uncertain` is a first-class outcome, not a failure.

#### 5.0.3 The nine measures

| Measure | Definition | Roles included |
|---|---|---|
| **Cash inflow** | external money received | `income`, `refund`, `reimbursement`, `reversal_chargeback` (inbound) |
| **Cash outflow** | external money leaving available cash | `purchase`, `debt_service` (full payment), `fee_or_interest_charged`, `cash_withdrawal` |
| **Gross purchases** | purchases before any offset | `purchase` |
| **Net spending** | what consumption actually cost | `purchase` − `refund` − `reimbursement` − `reversal_chargeback` |
| **Recurring obligations** | committed forward cash need | recurring `purchase` + `debt_service` minimums + insurance/tax |
| **Debt service** | total loan payments | `debt_service` (components separated **when known**) |
| **Transfers & allocations** | own money moved | `internal_transfer`, `card_payment`, `savings_allocation`, `investment_contribution` |
| **Income** | true income only | `income` |
| **Controllable spending** | the actionable subset | `purchase` ∩ controllability classification ∩ confidence ≥ threshold |

**Critical non-identities, stated so nobody re-derives them wrongly:**

- Cash outflow **≠** net spending. A mortgage payment is outflow; its principal is not
  consumption.
- Transfers and allocations are in **neither** spending measure. Moving money is not
  spending it — *"these may affect an individual account's cash movement but must not
  become household spending merely because money moved."*
- Income **excludes** refunds and reimbursements. Getting $80 back for a returned coat
  is not earning $80.
- Controllable spending is a **subset of** `purchase`, gated on explicit classification
  **and** confidence — never "everything that isn't a transfer".

#### 5.0.4 Transaction classification matrix

`+` adds · `−` offsets · `·` no effect · `?` uncertain until resolved

| Transaction class | Role | Inflow | Outflow | Gross | Net spend | Debt svc | Transfers | Income |
|---|---|---|---|---|---|---|---|---|
| Debit-card purchase | `purchase` | · | + | + | + | · | · | · |
| Credit-card purchase | `purchase` | · | · ¹ | + | + | · | · | · |
| **Credit-card payment** | `card_payment` | · | + ¹ | · | **·** | · | + | · |
| Internal transfer (paired) | `internal_transfer` | · | · | · | · | · | + | · |
| **Transfer, counterpart unconnected** | `uncertain` | ? | ? | ? | **?** | ? | ? | ? |
| Savings transfer | `savings_allocation` | · | · | · | · | · | + | · |
| Investment contribution | `investment_contribution` | · | · | · | · | · | + | · |
| Investment withdrawal | `investment_contribution` (inverse) | · | · | · | · | · | − | · |
| Mortgage / loan payment | `debt_service` | · | + | · | **·** ² | + | · | · |
| — principal component | *(component)* | · | *in total* | · | · | + | · | · |
| — interest / fees | *(component)* | · | *in total* | · | **+** ³ | + | · | · |
| — escrow / tax / insurance | *(component)* | · | *in total* | · | **+** ³ | + | · | · |
| Refund | `refund` | + | · | · | **−** | · | · | · |
| Reimbursement | `reimbursement` | + | · | · | **−** | · | · | · |
| Reversal / chargeback | `reversal_chargeback` | + | · | · | **−** | · | · | · |
| Pending superseded by posted | *(none — replaced at ingestion)* | · | · | · | · | · | · | · |
| Cash withdrawal | `cash_withdrawal` | · | + | · | **?** ⁴ | · | · | · |
| Bank fee / card interest | `fee_or_interest_charged` | · | + | · | + | · | · | · |
| Cash-back reward | `refund`-like ⁵ | + | · | · | − | · | · | · |
| Business expense paid personally | `purchase` + pending reimbursement | · | + | + | + ⁶ | · | · | · |
| Income deposit | `income` | + | · | · | · | · | · | + |

¹ A credit-card purchase leaves no cash at purchase time; the cash leaves when the card
is paid. **This is the rule that must never break: the purchase is spending, paying the
card is not spending again.**
² The payment as a whole is not consumption.
³ Interest, fees and escrow **are** costs — but only when the split is known (§5.0.5).
⁴ Cash withdrawal is deliberately unresolved (§5.0.6).
⁵ Cash back reduces the cost of the purchases that earned it; treated as an offset, not
income, unless the user classifies it otherwise.
⁶ Remains full personal spending **until** the reimbursement arrives and offsets it;
Beacon attribution then removes it from *personal* spending without deleting the record.

#### 5.0.5 Debt-payment limitation policy

Plaid does not return a principal/interest split for a payment transaction. Therefore:

- When components are **known** (from `LoanTerms` amortisation, a statement, or user
  entry with provenance), record them separately: principal → balance-sheet movement;
  interest, fees, escrow, tax and insurance → cost, and therefore in net spending.
- When they are **not known**, keep the payment as a single **unsplit `debt_service`
  amount**, count it in cash outflow and debt service, and **exclude it from net
  spending with a stated limitation** — because counting the whole payment as
  consumption overstates spending, and counting none of it understates cost. The
  measure says which it did and why.
- **Never invent a split.** No default amortisation against an unknown APR.
- Every affected measure carries `assumptions: ["debt service unsplit for N payments"]`.

#### 5.0.6 Uncertainty behaviour

Three cases must stay uncertain rather than be guessed:

1. **Transfer with an unmatched or unconnected counterpart.** A $500 debit to an account
   WLJ cannot see is either a transfer or a real expense. It becomes
   `transfer_state='candidate'` → role `uncertain` → **counted in no spending measure**,
   surfaced for review. `financial_activity` already behaves this way; the design
   preserves it.
2. **Cash withdrawal.** Not automatically consumption, not automatically harmless
   movement. Default role `cash_withdrawal`: in cash outflow, **excluded from net
   spending**, flagged so Danny can classify it. Whichever default were chosen silently
   would be wrong for someone.
3. **Anything below the confidence threshold.** Role `uncertain`.

Every measure reports `uncertain_count` and `uncertain_amount`. **A measure computed
over meaningful uncertainty says so** rather than presenting a clean number. Uncertainty
is disclosed, never averaged away.

#### 5.0.7 Refund period policy

A refund arriving in a later month than its purchase is genuinely ambiguous, so WLJ does
not silently pick:

- **Default — `offset_on_receipt`:** the refund reduces net spending in the month it
  arrived. Matches the bank statement, which is what a person checks against.
- **Optional — `restate_original`:** reduces the original purchase's month, correcting
  history. Available where the refund is linked to its original purchase.
- **The report always states which policy produced the figure**, and any restatement
  makes the affected prior month's total change visibly, never silently.
- A linked refund **retains the original purchase's category relationship** where the
  provider supports it, so a grocery refund reduces groceries — not "uncategorised".
- A refund **always keeps its own audit identity.** It is offset, never deleted, never
  excluded.

#### 5.0.8 The `spending_predicate` term is retired

It described a boolean that cannot exist. Replaced by:

- `finance_calc.roles :: classify(transaction) → EconomicRole` — one authority;
- `finance_calc.measures :: <measure>(user, start, end) → CalcResult` — nine projections.

The invariant is enforced by a **classification contract test**, not by grepping source:
every measure must be expressible as a projection over roles; a fixture of one
transaction per class must produce the exact matrix in §5.0.4; and the measures must
reconcile (§5.0.9). A grep test would pass while the numbers were wrong.

#### 5.0.9 Reconciliation identities (must hold, always)

```
net_spending      = gross_purchases − refunds − reimbursements − reversals
cash_outflow      = purchases_settled + debt_service_total + fees + cash_withdrawals
cash_inflow       = income + refunds + reimbursements + reversals
net_cash_movement = cash_inflow − cash_outflow
debt_service_total = principal_known + interest_known + escrow_known + unsplit
```

Any measure set that fails these is reported as **not reconciling** and is not
presented as fact.

### 5.1 Distortion control (non-negotiable)

Spending and cash flow must never be distorted by internal transfers, credit-card
payments, refunds, reimbursements, or superseded pending rows. **The mechanism is the
role classification in §5.0, not a filter re-invented per caller.** Each distortion has
a named role and a defined effect on each measure (§5.0.4); a caller that wants a
different number asks for a different *measure*, never a different filter.

`attribution_population.financial_activity` — already the shared definition consumed by
Budget, FinanceHistory, the metric snapshots, the dashboard and `FinanceDomainTruth` —
becomes the `net_spending` projection. **No second spending system may exist.**

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
```

### 7.1a Field-level provenance — no single source owns a loan

The earlier draft assumed every term was user-entered. That is as wrong as assuming
every term is importable. **Provenance is per FIELD, not per record**, because a single
mortgage can legitimately have an imported interest rate, a statement-derived escrow
figure and a user-entered payoff quote at the same time.

Every term-bearing field carries:

```
FieldProvenance(
    source,        # provider_imported | user_entered
                   # | statement_derived_confirmed | unavailable
    as_of,         # when this value was true, not when we stored it
    confidence,    # high | medium | low
    provider_key,  # only when provider_imported
    confirmed_by_user,  # required for statement_derived_confirmed
)
```

**Authority rules, in order:**

1. A **user-entered** value outranks a provider value for the same field — the person
   holding the statement is a better authority than an aggregator, and this mirrors
   `category_source='user'`, which already works this way.
2. A **provider_imported** value refreshes freely **unless** a user value exists for
   that field; then it is offered as a correction, never silently applied.
3. **statement_derived_confirmed** means WLJ read it from a document *and Danny
   confirmed it*. Unconfirmed derivation is not a source; it is a suggestion.
4. **unavailable** is a recorded state with a reason, not an empty field. It is what the
   calculation layer reads to decide whether it may compute interest at all.
5. Nothing is ever **defaulted**. A missing APR excludes that debt from interest maths
   and says so.

For the truck specifically, the expected steady state is: balance
`user_entered` (or `provider_imported` if the institution connects and the account is
exposed by an existing product), APR / minimum / term / due date `user_entered` or
`statement_derived_confirmed`, payoff quote `user_entered` with an expiry. **That is a
supported configuration, not a degraded one.**

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

- No paid valuation provider (§12).
- **No new paid Plaid product** — Liabilities and Investments are not authorised by
  this architecture (§2a.1). Manual valuation and manual loan-term entry remain
  first-class, permanently supported paths, not stopgaps.
- No outward action: no payments, transfers, cancellations or trades.
- Investments domain `deferred` — lowest decision value now, and gated on a paid
  product nobody has approved.
- No tax, legal or investment advice.
- No scraping, ever.
- No scheduled job that creates recurring external cost.

---

## 12. Standing decisions (recorded, current)

### 12.1 Valuation providers

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

### 12.2 Plaid products

**No new paid Plaid product is authorised by this architecture task.** WLJ continues on
the products it already uses. Liabilities and Investments are documented as future
options (§2a) behind the guardrail in §2a.1, each requiring Danny's explicit approval
after pricing, coverage, benefit-vs-manual, existing-Item consequences and recurring-cost
justification are established.

### 12.3 Manual entry is permanent

Manual valuation and manual loan-term entry are **first-class supported paths**, designed
to remain correct and complete whether or not a provider is ever connected. They are not
placeholders waiting to be replaced, and the architecture must never describe them as a
lesser mode. Where a provider is later added, it becomes **one more source with its own
provenance** (§7.1a) — it does not take ownership of the record.

---

# §5.1 — Six meanings that must never share a label

*Added 2026-08-31 during the accounting closure.*

The Finance 2.0 measures collapsed two different ideas into `cash_outflow`, and counted
one household movement twice in `transfers_and_allocations`. Both are the same underlying
error: **a movement has several true descriptions, and each one needs its own name.**

A single credit-card payment of $1,500 is simultaneously:

* two account movements (chequing −1,500, card +1,500);
* one household movement;
* zero consumer spending (the purchases it settles were counted when they happened);
* a real reduction in liquid cash;
* a real reduction in liabilities;
* zero change in net worth.

Six of those are different questions. They get six names.

## 1. Consumer spending — `net_spending`
What consumption cost: purchases plus fees and interest, less refunds, reimbursements
and reversals. **A card payment is never here.** The purchases it settles were counted
once, when they were made; counting the payment too would count the same consumption
twice.

## 2. Liquid cash — `cash_inflow` / `cash_outflow`
Every movement on an account that holds money — chequing, savings, cash. Debits out,
credits in, whatever the movement MEANT. This is the liquidity view: it answers "what
actually left my account", which is what a forecast and a low-balance warning need.

A card payment IS here, because the money genuinely left the chequing account. So is a
transfer to savings. Neither is spending.

**Deliberately not "external economic outflow".** That question is answered by
`net_spending` plus `debt_service`, and asking one label to mean both is what produced a
figure that included debt service (cash out, correctly) and excluded card payments (also
cash out).

## 3. Household transfers — `transfers_and_allocations`
The household's own money moving between its own accounts, counted **once per movement,
not once per leg**. Both legs keep their rows and both are visible per account; the
household total takes one.

A pair has one canonical identity derived from both primary keys, so whichever leg is
inspected first yields the same key. Without that, a $1,500 payment reads as $3,000 of
transfers.

## 4. Debt service — `debt_service`
Money paid towards a liability, counted once across both legs of the payment.
Principal is balance-sheet movement, not expense. Interest, fees, taxes and insurance
are expense — but only when authoritative data separates them. **An unsplit payment
stays unsplit**, and says so.

## 5. Account-level movement
Both legs of every pair, per account, always preserved. This is the reconciliation view
a person uses to tie WLJ back to a bank statement. It is deliberately NOT a household
total: at this level the same $1,500 appearing twice is correct.

## 6. Household net cash movement
`cash_inflow − cash_outflow`. The change in liquid cash over the period. Distinct from
net worth, which also moves with debt and asset values.

## The net-worth identity for a principal payment

    cash          −1,500
    liabilities   −1,500
    net worth          0

Paying down principal does not make a household richer or poorer; it converts one form
of position into another. Only fees and interest are an expense, and only when known.

## Why this is written down

Each of these six was individually obvious and collectively ignored, and the result was a
transfer total roughly double what it should have been and a cash figure that was neither
of the two things it might have meant. The rule that prevents recurrence:

> **Before adding a measure, name the question it answers. If an existing measure already
> answers a DIFFERENT question, do not widen it — add a name.**
