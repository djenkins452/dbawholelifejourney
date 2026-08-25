# F0 — Financial Entity & Attribution Truth · Implementation Plan

> **Mode:** ARCHITECT. **Status:** **PLAN ONLY — not implemented, no migrations created. Awaiting "go".**
> Governing assessment: `docs/WLJ_FINANCE_INTELLIGENCE_ARCHITECTURE_ASSESSMENT.md` (§10 decisions).
> Prior phase: F-1 complete at `4ee0880f`. **Date:** 2026-08-24

**F0 delivers truth only:** entities, account→entity assignment, first-class attribution with supersession,
user-owned rules, one attributable-population authority, and the truth exposure F1 will read.
**F0 builds no detector, no review queue, no CoS flow, no insights, no outcome verification.**

---

## 1. Current-state evidence

### 1.1 What exists
- `FinancialAccount` (`apps/finance/models.py:50`) — `name`, `account_type` (Assets: checking/savings/cash/
  investment/property; **Liabilities: credit_card/loan/mortgage/student_loan**), `institution`,
  `current_balance`, `account_number_last4`, `is_hidden`, `bank_connection`, `plaid_account_id`.
  **No economic-owner concept of any kind.**
- `Transaction` (`:397`) — `account`, `date`, `amount` (+in/−out), `description`, `category` (`:429`),
  `payee` (`:439`), `tags` (`:476`), `is_opening_balance` (`:460`), `transfer_pair` (`:466`),
  `source_type` (`:502`, incl. `plaid`/`receipt_scan`/`email`), `source_id` (`:509`),
  `fingerprint` (`:516`), `plaid_transaction_id` (`:535`), `plaid_pending` (`:541`).
  Indexes: `(user,date)`, `(account,date)`, `(category,date)`, `(plaid_transaction_id)` (`:550`).
- `Payee` (`:1644`) — **user-owned**, `unique_together ['user','name']` (`:1678`), `default_category`,
  `use_count`, `last_used_at`. **The safe rule anchor.**
- `RecurringTransaction` (`:1694`) — `name`, `amount`, `account`, `category`, `payee`, `frequency`,
  `next_due_date`, `is_active`, `is_auto_post`, `total_generated`.
- `TransactionCategory` (`:275`) — `user` FK is **nullable** with `is_system` (`:315–322`,
  *"Owner (null for system categories)"*). **System categories are shared across every user** — this is
  precisely why a rule may never anchor on category (§9.4).
- Ownership/soft-delete: `UserOwnedModel` (`apps/core/models.py:183`) over `SoftDeleteModel` (`:88`);
  **`objects = SoftDeleteManager()` already filters `status="active"`** (`:118`, `:71–72`);
  `all_objects` bypasses (`:119`).
- **Supersession precedent to reuse:** `PersonalKnowledgeFact` (`apps/core/personal_knowledge/models.py:93`)
  — `UserOwnedModel` + `fact_status` ACTIVE/SUPERSEDED (`:180`, deliberately **not** `status`, which is the
  soft-delete field) + `superseded_by` self-FK `related_name="supersedes"` (`:186`) + index
  `(user, fact_status, status)` (`:211`); and a **three-way trust split** that F0 copies exactly:
  `Provenance` — *how acquired, permanent, never overwritten* (`:60`), `ReviewState` — *trust* (`:78`),
  `confidence` — *numeric* (`:174`).
- Partial-unique precedent: `apps/calendar_engine/migrations/0007_…:19`,
  `apps/health/migrations/0032_…:68`.
- Latest Finance migration: `0018_routine_maintenance_bridge_choices.py` → F0 starts at **`0019_`**.

### 1.2 The defect F0 must resolve — FOUR competing transaction populations
| # | Definition | Soft-deleted | Opening balances | Transfers |
|---|---|---|---|---|
| 1 | `Budget.spent_amount` (`models.py:661`) | excluded (redundant explicit `status='active'`) | **included** | **not excluded at all** |
| 2 | `FinancialMetricSnapshot` (`models.py:1065`, `:1076`) | excluded (redundant) | excluded | `.exclude(transfer_pair__isnull=False)` |
| 3 | `FinanceHistory._monthly_rows` (`services/finance_history.py:57`) | excluded | excluded | `.exclude(category__category_type="transfer")` |
| 4 | `FinanceDomainTruth.describe` (`services/finance_domain_truth.py:81`) | excluded | excluded | **not excluded** |
| — | `FinanceDashboardView` (`views.py:280`, `:291`) | excluded | — | `transfer_pair` |

**Two mutually incompatible definitions of "transfer"** (#2 `transfer_pair` FK vs #3 `category_type='transfer'`).

### 1.3 The finding that drives F1's correctness
**`transfer_pair` is set in exactly one place in the entire codebase** — the manual transfer form
(`apps/finance/forms.py:526–529`), which also stamps the shared system transfer category (`:496–501`).
**Plaid sync never sets it** (`services/sync_service.py:284`, `:299` set only `plaid_pending`) and neither
does the file importer (`import_service.py:577`).

**Therefore:** an imported or synced credit-card payment (personal checking → a business credit card) has
**no `transfer_pair`, no transfer category, and a negative amount** — it is indistinguishable from an expense.
This is the single largest false-positive source for F1's "business expense paid personally" detector, and F0
must name it as a population class rather than let F1 discover it in production. See §5.3.

---

## 2. Proposed models and field-level responsibilities

All four models extend `UserOwnedModel` (user FK, soft delete, `created_via`, timestamps, Narratable).
**No model uses the field name `status`** — that is the soft-delete field (precedent: `FinancialGoal.goal_status`
`models.py:803`, `PersonalKnowledgeFact.fact_status`).

### 2.1 `FinancialEntity` — who money belongs to
| Field | Responsibility |
|---|---|
| `entity_type` | `personal` · `household` · `business` · `other` · `unknown`. **Type is logic; name is data.** |
| `name` | Free text. **"Beacon" lives here and nowhere else.** No code may branch on it. |
| `is_default_personal` | Exactly one per user (partial unique). The bootstrap fallback. |
| `is_active` | Deactivate without deleting; historical attributions keep resolving. |
| `space_ref` | Blank `CharField` forward hook for `WLJ_SECURITY_AUTHORIZATION_FRAMEWORK` Space linkage. **Unused in F0. No permission logic reads it.** |
| `sort_order`, `notes` | Display/free text. Never used in logic. |

- **`unknown` is a real row**, created per user at bootstrap. `attributed_entity` is therefore **never null** —
  "unattributed" is expressed by *the absence of an attribution record*, and "we looked and cannot tell" is
  expressed by *an attribution to the `unknown` entity*. Those are different truths and F0 keeps them distinct.
- **Deletion:** every FK into an entity is `PROTECT`. Entities are retired with `is_active=False`, never
  deleted, because historical attributions must keep resolving (Article IV.1).

### 2.2 `AccountEntityAssignment` — the temporal source of `paid_by`
| Field | Responsibility |
|---|---|
| `account` → `FinancialAccount` | PROTECT |
| `entity` → `FinancialEntity` | PROTECT |
| `effective_from` / `effective_to` | Date range; `effective_to = NULL` means current |
| `actor`, `reason`, `created_at` | Who changed it and why — audit |

`FinancialAccount.entity` (new nullable FK) is the **current-value cache**; this table is the authority.
See §8 for the temporal policy.

### 2.3 `TransactionAttribution` — the first-class attribution record
| Field | Responsibility |
|---|---|
| `transaction` → `Transaction` | CASCADE (an attribution is meaningless without its transaction; transactions soft-delete, so history survives) |
| `attributed_entity` → `FinancialEntity` | PROTECT — **who should bear it** |
| `paid_by_entity` → `FinancialEntity` | PROTECT — **snapshot** of the account's entity as of `transaction.date` at write time (§8, §10.5) |
| `source` | **How** it was attributed. Permanent, never overwritten (§6) |
| `actor` | **Who** acted: `user` · `rule` · `import` · `migration` |
| `confidence` | 0.0–1.0. User-confirmed rows are 1.0 |
| `evidence` | Concise JSON: **references, not content** (§12.5) |
| `user_confirmed` / `confirmed_at` | Settable **only** by the confirmation service (§12.7) |
| `rule` → `AttributionRule` | SET_NULL — which rule produced it (null for user/import/migration) |
| `attribution_status` | `active` · `superseded` |
| `superseded_by` → self | `related_name="supersedes"` — the correction that replaced this row |
| `share_basis` / `share_value` | `full` (F0 always) · `percent` · `amount` — **the split hook** (§16.5) |
| `notes` | Optional user note |

**Immutable after create except**: `attribution_status`, `superseded_by`. Enforced in `save()` and by test.

### 2.4 `AttributionRule` — user-owned, scoped, superseding
| Field | Responsibility |
|---|---|
| `scope` | `recurring_series` · `payee` · `account` · `description_pattern` (**declared, not implemented in F0**) |
| `payee` / `recurring` / `account` | The anchor for that scope — all **user-owned** models |
| `pattern` | Blank in F0 |
| `entity` → `FinancialEntity` | PROTECT — what the rule assigns |
| `origin` | `user_confirmation` · `user_authored` · `imported`. **No inferred origin exists in F0** |
| `user_confirmed`, `confidence` | Trust |
| `rule_status` | `active` · `superseded` · `expired` |
| `superseded_by` → self | Corrections supersede |
| `effective_from` / `effective_to` | Activation + expiry |
| `use_count` / `last_used_at` | Mirrors `Payee.use_count` (`models.py:1665`) |

**There is no category scope. There will never be one** (§9.4).

---

## 3. Relationship table

| From | → | To | on_delete | Meaning |
|---|---|---|---|---|
| `FinancialAccount.entity` | → | `FinancialEntity` | PROTECT (null=True) | **cache** of current economic owner |
| `AccountEntityAssignment.account` | → | `FinancialAccount` | PROTECT | temporal authority for `paid_by` |
| `AccountEntityAssignment.entity` | → | `FinancialEntity` | PROTECT | |
| `TransactionAttribution.transaction` | → | `Transaction` | CASCADE | the subject |
| `TransactionAttribution.attributed_entity` | → | `FinancialEntity` | PROTECT | **who should bear it** |
| `TransactionAttribution.paid_by_entity` | → | `FinancialEntity` | PROTECT | **who did bear it** (snapshot) |
| `TransactionAttribution.rule` | → | `AttributionRule` | SET_NULL | provenance |
| `TransactionAttribution.superseded_by` | → | self | SET_NULL | correction chain |
| `Transaction.current_attribution` | → | `TransactionAttribution` | SET_NULL (null=True) | **cache** (§4) |
| `AttributionRule.{payee,recurring,account}` | → | user-owned models | CASCADE | anchor |
| `AttributionRule.entity` | → | `FinancialEntity` | PROTECT | assignment |

**The mismatch F1 detects is one row-local comparison:** `attributed_entity != paid_by_entity` on an active
attribution — no joins.

---

## 4. Authoritative truth vs cache

**Authorities:** `AccountEntityAssignment` (paid_by over time) · `TransactionAttribution` (attribution, with
full history) · `AttributionRule` (rules).

**Caches — two, both provably derivable:**

| Cache | Derived from | Proof it stays a cache |
|---|---|---|
| `FinancialAccount.entity` | the assignment with `effective_to IS NULL` | written only by `entity_service.assign_account_entity()`; reconciliation test asserts zero divergent rows; `rebuild_finance_caches` command regenerates it |
| `Transaction.current_attribution` | the single `attribution_status='active', share_basis='full'` row | written only by `attribution_service` **inside the same DB transaction** as the attribution row; DB partial-unique guarantees at most one candidate; reconciliation test + rebuild command |

**Rules that keep them caches, not authorities:**
1. **One writer.** Only the service layer writes them; a contract test asserts no view/form/admin/signal does.
2. **Never read for audit.** History, evidence, and supersession are read from the attribution table only.
3. **Rebuildable.** `python manage.py rebuild_finance_caches` reconstructs both from the authorities; a test
   scrambles the caches, rebuilds, and asserts equality.
4. **Reconciliation test** — the queryset of divergent rows must be empty (this is the III.1 guard).

*Alternative considered:* omit `Transaction.current_attribution` and use `~Exists(...)`. Rejected — the
unattributed-list and entity-total queries are the two hottest F1/F2 paths and the null-FK anti-join is the
index-friendly shape (§10). The cache is justified by measurement, not convenience.

---

## 5. The transaction-population contract

**ONE authority:** `apps/finance/services/attribution_population.py`

```
attributable_transactions(user, *, start=None, end=None) -> QuerySet[Transaction]
exclusion_reason(transaction) -> str | None      # why a single row is not attributable
NEEDS_REVIEW_REASONS: frozenset                  # excluded-but-not-settled classes
```

### 5.1 Decisions
| Case | Treatment | Why / evidence |
|---|---|---|
| Soft-deleted / archived | **Excluded** — automatic via `SoftDeleteManager` (`core/models.py:71`) | The explicit `status='active'` in `models.py:661`, `:1069` is redundant; F0 does not repeat it |
| Opening balances | **Excluded** (`is_opening_balance=False`) | Not economic activity (`models.py:460`) |
| Pending (Plaid) | **Excluded** while `plaid_pending=True`; becomes attributable when it posts | Amount/date/id can still change (`sync_service.py:284`) |
| Paired transfers (both legs) | **Excluded** — `transfer_pair__isnull=False` | Internal movement, not spend |
| Transfer-categorised | **Excluded** — `category__category_type='transfer'` | Union with the above; resolves definitions #2 vs #3 |
| **Unpaired internal candidates** (a negative transaction whose payee/description resolves to one of the user's own liability accounts, or a Plaid/import transaction to a credit-card account) | **Excluded from attribution, surfaced as `needs_review`** — never silently attributed, never silently dropped | §1.3 — the F1 false-positive class |
| Credit-card payments | Same as above; a *paired* one is a transfer, an *unpaired* one is `needs_review` | `account_type` liabilities at `models.py:83–89` |
| Refunds / reversals (positive amount, expense category) | **Included** — a refund of a business expense carries the same entity meaning | |
| Income (positive) | **Included** — a business deposit landing in a personal account is a mismatch too. The *population* is "economically real transactions", not "expenses"; direction is F1's concern | |
| Reimbursements | Ordinary transactions in F0; the *link* between them is a later additive model (§16.6) | |
| Duplicates / superseded imports | Not filtered — dedup is the importer's job via `fingerprint` (`models.py:516`). **Residual logged**, not silently handled | |
| Splits | One `Transaction` = one row; a split is multiple attributions summing to 100% (§16.5) | |

### 5.2 Not buried
- Every attribution code path calls this service. A contract test asserts no attribution module contains
  `is_opening_balance`, `transfer_pair`, or `plaid_pending` outside it.
- **Ratchet, not a rewrite:** the four legacy definitions (§1.2) stay as-is in F0 — converting live Budget and
  metrics code is disproportionate blast radius for this phase. A ratchet test **records those four call
  sites by `file:line`** so a fifth cannot appear silently. Convergence is F4 work, logged as the residual.

### 5.3 The named residual
`needs_review` is truth, not a bug: F0 records *why* a transaction is not attributable so F2's review queue can
show it and F1 can never mistake an internal transfer for a business expense paid personally.

---

## 6. Attribution `source` vocabulary

**Deliberately disjoint from `Transaction.source_type`** (`models.py:502`: manual/import/email/document/
receipt_scan/plaid), which records **how the record arrived**. `source` records **how the entity was decided**.
Conflating them would poison the audit trail.

| `source` | Meaning | May set `user_confirmed`? |
|---|---|---|
| `user_direct` | The user chose the entity for this transaction | **yes** (the only path) |
| `user_rule` | Applied from a rule the user confirmed | no — inherits confidence, not confirmation |
| `account_default` | Fell through to the paying account's entity | no |
| `import_declared` | The import source declared it | no |
| `migration_bootstrap` | Written by the F0 data migration | no |
| `model_suggested` | **Reserved for F2.** A conversation-time suggestion. Never written in F0 | **never** |

`actor` (`user` · `rule` · `import` · `migration`) answers *who*; `source` answers *how*. Both are permanent.

---

## 7. Supersession & correction lifecycle

```
create        → attribution_status=active, superseded_by=NULL, Transaction.current_attribution → this row
correct       → NEW active row created; OLD row: attribution_status=superseded, superseded_by=<new>
                (the old row's entity, source, confidence, evidence, actor, timestamps are UNTOUCHED)
re-correct    → chains; the full history is walkable via `supersedes`
```
- **Nothing is ever mutated or deleted.** No `UPDATE` touches `attributed_entity`, `source`, `confidence`,
  `evidence`, or `actor` after insert (enforced in `save()` + test).
- **User confirmation outranks inference, permanently:** a rule/import/migration path **may not** supersede a
  row with `user_confirmed=True`. It is refused at the service layer and asserted by test. Only another
  explicit user action can.
- Both writes happen in one `transaction.atomic()` block with the cache update.
- **Rules supersede identically** (`rule_status`, `superseded_by`) — an edited rule never rewrites the
  attributions it already produced; those keep pointing at the rule version that made them.

---

## 8. Account-entity temporal policy

`paid_by` for a transaction = the `AccountEntityAssignment` for its account whose
`effective_from <= transaction.date` and (`effective_to IS NULL` or `>= transaction.date`);
falling back to `FinancialAccount.entity`, then to the user's default-personal entity.

**Default when an account's entity changes: FORWARD-DATED.** A new assignment opens at
`effective_from = today`; the prior assignment closes at `today - 1 day`. **Existing attributions are not
touched** — their `paid_by_entity` snapshot preserves what was true when the finding was made.

**Retroactive change is an explicit, separate action** (`assign_account_entity(..., effective_from=<past>,
retroactive=True)`) which: opens an assignment with the earlier date, and **supersedes** affected non-user-confirmed
attributions with new rows carrying `source=account_default` — it never rewrites the old rows.
**User-confirmed attributions are never superseded by a retroactive account change.**

> **Approval item (§18.2):** confirm forward-dated as the default.

---

## 9. Rule precedence & scoping

### 9.1 Precedence — most specific wins
```
1. recurring_series   (this exact recurring commitment)
2. payee              (this user-owned Payee)
3. account            (everything paid from this account)
4. description_pattern (declared for a later phase; not implemented in F0)
```
### 9.2 Tie-break within a scope
`user_confirmed` desc → `effective_from` desc → `id` desc. Deterministic, no scoring model.

### 9.3 No broad rules created automatically
F0 creates **zero** rules. Rules only ever come from an explicit user action (F2). An **account-scoped rule is
the broadest and may only be user-authored** — no code path may infer one. Test-enforced.

### 9.4 Category is not a scope — and cannot become one
`TransactionCategory.user` is nullable with `is_system` (`models.py:315–322`): system categories are **shared
across all users**. A category-anchored rule would leak one user's attribution into another's. A contract test
asserts `TransactionCategory` appears in **no** attribution or rule model field.

---

## 10. Query & index strategy

| Operation | Shape | Cost |
|---|---|---|
| Assign current attribution | 1 insert + 1 update (cache), one `atomic()` | 2 writes |
| List unattributed | `attributable_transactions(user).filter(current_attribution__isnull=True).select_related('account','category').order_by('-date')[:N]` | 1 query, index-driven |
| Batch review candidates | Same + `exclusion_reason` computed from already-selected columns | 1 query |
| Entity totals | `TransactionAttribution.objects.filter(user=…, attribution_status='active').values('attributed_entity').annotate(total=Sum('transaction__amount'))` | **1 grouped query — never per-record** |
| **F1 mismatch** | `.filter(attribution_status='active').exclude(attributed_entity=F('paid_by_entity'))` | **1 single-table indexed scan, no joins** — the reason `paid_by_entity` is snapshotted |
| Rule lookup | Preload the user's active rules **once per batch** into a dict keyed by scope+anchor id | 1 query per batch, **not per transaction** |

**Explicitly forbidden:** the `Budget.spent_amount` shape (`models.py:652`) — a per-instance aggregate.
Local SQLite hides what prod Postgres will not.

**Indexes**
- `TransactionAttribution`: `(user, attribution_status)`, `(user, attributed_entity, attribution_status)`,
  `(user, paid_by_entity, attributed_entity, attribution_status)` *(the F1 mismatch index)*, `(rule)`
- `AttributionRule`: `(user, rule_status, scope)`, `(user, payee)`, `(user, recurring)`, `(user, account)`
- `AccountEntityAssignment`: `(account, effective_from)`, `(user, entity)`
- `FinancialEntity`: `(user, entity_type, is_active)`
- `Transaction`: `current_attribution` FK index (automatic). Existing `(user,date)` (`:551`) serves the list.

**Uniqueness constraints**
- `uq_finentity_user_name` — `UniqueConstraint(fields=['user','name'])` *(mirrors `Payee`, `:1678`)*
- `uq_finentity_one_default_personal` — partial: `condition=Q(is_default_personal=True), fields=['user']`
- `uq_finentity_one_unknown` — partial: `condition=Q(entity_type='unknown'), fields=['user']`
- `uq_txattr_one_active_full` — partial: `fields=['transaction'], condition=Q(attribution_status='active',
  share_basis='full')` — **one current attribution per transaction, while admitting future splits without
  dropping the constraint**
- `uq_acct_entity_open` — partial: `fields=['account'], condition=Q(effective_to__isnull=True)` — one open
  assignment per account

*(Partial-unique precedent: `apps/calendar_engine/migrations/0007_…:19`.)*

---

## 11. Migration sequence & bootstrap

| # | Migration | Content | Reversible |
|---|---|---|---|
| `0019` | `financial_entity` | `FinancialEntity` + constraints | yes (drop table) |
| `0020` | `account_entity_assignment` | `AccountEntityAssignment` + `FinancialAccount.entity` (**nullable**) | yes |
| `0021` | `transaction_attribution` | `TransactionAttribution` + `AttributionRule` + `Transaction.current_attribution` (**nullable**) | yes |
| `0022` | `bootstrap_default_entities` | `RunPython`, idempotent + reversible | yes |

**All schema changes are additive** — new tables plus two nullable FKs. **No existing column is altered or
dropped**, which is what makes §15 clean.

### Bootstrap (`0022`) behaviour
For each user **who already has at least one `FinancialAccount` or `Transaction`**:
1. `get_or_create` a `personal` entity (`is_default_personal=True`, name from a neutral default such as
   `"Personal"` — **never a business name**) and an `unknown` entity.
2. For each of that user's accounts with no assignment: create an `AccountEntityAssignment` → the personal
   entity, `actor='migration'`, `effective_from = min(earliest transaction date, account.created_at.date())`
   so historical `paid_by` resolves; set the `FinancialAccount.entity` cache.
3. **Create ZERO `TransactionAttribution` rows.** Every existing transaction remains *unattributed* — which is
   the honest state. Manufacturing attributions in a migration would fabricate truth (Article I.1).

Users with no Finance data get their entities lazily via `entity_service.ensure_default_entities(user)` on
first use — avoiding two rows × every user who never opens Finance.
**Reverse:** delete only bootstrap-created rows (`actor='migration'`, no dependent attributions).

> **Approval item (§18.3):** the default personal entity's display name.

---

## 12. Authorization & audit controls

1. **Every model is `UserOwnedModel`** — user FK, soft delete, timestamps, `created_via`.
2. **Cross-user references rejected.** `clean()` on each model asserts
   `entity.user_id == transaction.user_id == rule.user_id == self.user_id`; the service layer is the single
   writer and re-checks; a test attempts every cross-user combination and asserts refusal.
   **Stated residual:** Django cannot express cross-table ownership as a DB constraint without composite FKs,
   so this boundary is service + validation + test, not a DB guarantee. Recorded, not hidden.
3. **Corrections preserve prior evidence** — supersession only; `save()` refuses to modify an immutable field
   on an existing row (§7), and a test asserts the old row is byte-identical after a correction.
4. **Shared categories cannot leak** — no category field anywhere in the attribution/rule schema; contract
   test (§9.4).
5. **Evidence is minimized** — `evidence` stores **references and scalars only**: matched rule id, matched
   payee id, amount, date, account id, and the exclusion reason. **Never** account numbers, tokens,
   `plaid_transaction_id`, institution credentials, or free-text notes. Size-capped, asserted by test —
   mirroring the existing never-surface list in `finance_domain_truth.py:20–26`.
6. **Soft delete** — attributions are superseded, not deleted. `soft_delete()` remains available for genuine
   user-initiated removal and keeps rows readable via `all_objects`.
7. **AI cannot masquerade as user confirmation.** `user_confirmed=True` + `actor='user'` +
   `source='user_direct'` may be written **only** by `attribution_service.confirm()`, which requires an
   explicit user action. The rule-application path physically cannot produce it — asserted by calling that
   path and checking `user_confirmed is False`, and by asserting `source='model_suggested'` can never carry
   `user_confirmed=True`.
8. **No provider access** — the F-1 contract test
   (`apps/finance/tests/test_finance_read_only_contract.py`) already forbids any provider client or system
   prompt under `apps/finance/`, and F0 adds none. **Finance stays read-only:** F0 adds no intent to
   `ALLOWED_WRITE_INTENTS`.

---

## 13. Focused test matrix

| # | Area | Asserts |
|---|---|---|
| 1–3 | Entity constraints | one default-personal per user; one `unknown` per user; `(user,name)` unique |
| 4 | Entity retirement | `is_active=False` keeps historical attributions resolving; PROTECT blocks deletion |
| 5–6 | Bootstrap | idempotent (runs twice → same rows); **creates zero attributions** |
| 7 | `paid_by` resolution | assignment covering the transaction date wins; fallback chain assignment → account cache → default personal |
| 8 | Temporal policy | forward-dated change leaves existing attributions untouched |
| 9 | Retroactive change | supersedes non-confirmed rows; **never** supersedes `user_confirmed=True` |
| 10–21 | **Population contract — one test per row of §5.1** | soft-deleted · opening · pending · paired transfer (both legs) · transfer-categorised · unpaired internal → `needs_review` · credit-card payment · refund · income · reimbursement · duplicate · split |
| 22 | Population is not duplicated | no attribution module filters `is_opening_balance`/`transfer_pair`/`plaid_pending` outside the service |
| 23 | Legacy ratchet | exactly the four known legacy definitions exist, at the recorded `file:line` |
| 24–25 | Supersession | old row byte-identical after correction; chain walkable |
| 26 | Immutability | `save()` refuses to change `attributed_entity`/`source`/`evidence`/`actor` post-create |
| 27 | **Confirmation cannot be forged** | rule path cannot produce `user_confirmed=True`; `model_suggested` never confirmed |
| 28–30 | Rule precedence | recurring > payee > account; tie-break order; no rule auto-created |
| 31 | Category isolation | `TransactionCategory` in no attribution/rule field |
| 32–34 | Cross-user | entity / rule / attribution cross-user writes rejected |
| 35–36 | Cache integrity | reconciliation empty; scramble → `rebuild_finance_caches` → equality |
| 37–38 | **Query counts** (`assertNumQueries`) | entity totals = 1 query; unattributed list = 1 query; rule lookup = 1 per batch |
| 39 | Truth exposure | `entity` entity type + `attributed_to`/`paid_by` on transaction entities are facts-only, no verdicts |
| 40 | Read-only | F-1 contract still green; `ALLOWED_WRITE_INTENTS` unchanged |

**Zero real-provider calls.**

---

## 14. Expected files changed

**Added**
- `apps/finance/services/attribution_population.py` — the population authority (§5)
- `apps/finance/services/entity_service.py` — entities, assignments, `paid_by` resolution, bootstrap helper
- `apps/finance/services/attribution_service.py` — create / correct / confirm / supersede; the only cache writer
- `apps/finance/services/attribution_rules.py` — precedence + application
- `apps/finance/management/commands/rebuild_finance_caches.py`
- `apps/finance/migrations/0019_…` → `0022_…`
- `apps/finance/tests/test_finance_entities.py`, `test_attribution_population.py`,
  `test_attribution_lifecycle.py`, `test_attribution_rules.py`, `test_attribution_authorization.py`
- `docs/WLJ_FINANCE_F0_ENTITY_ATTRIBUTION_PLAN.md` (as-built section on completion)

**Modified**
- `apps/finance/models.py` — 4 new models + 2 nullable FKs
- `apps/finance/admin.py` — read-only admin for the new models (audit visibility)
- `apps/finance/services/finance_domain_truth.py` — add the `entity` entity type; add `attributed_to` /
  `paid_by` to transaction entities (**requirement 7**, facts only)
- `docs/WLJ_FINANCE_INTELLIGENCE_ARCHITECTURE_ASSESSMENT.md`, `docs/wlj_claude_changelog.md`

**Not changed:** no existing column altered; no view, template, JS, or setting; no
`ALLOWED_WRITE_INTENTS`; nothing outside `apps/finance/` + `docs/`.

---

## 15. Rollback

- **Schema is purely additive** — 4 new tables + 2 nullable FKs. Reverse migrations drop them; **no existing
  data is transformed**, so a rollback cannot corrupt Finance.
- `0022` is reversible and deletes only rows it created (`actor='migration'`).
- **Landing order matters:** ship `0019–0021` (schema, inert) and only then `0022` (bootstrap). If `0022`
  misbehaves, reverse it alone — the schema stays and no user-visible surface depends on it.
- No feature flag required: F0 adds no user-facing surface. Nothing reads the new tables until F1/F2.
- **Forward-fix preference** for anything cache-related — `rebuild_finance_caches` beats a revert.

---

## 16. Risks & unresolved decisions

1. **Unpaired internal transfers (HIGH).** `transfer_pair` exists only for manually-created transfers
   (`forms.py:526`); Plaid and import never set it. F0 mitigates with the `needs_review` class (§5.1), but
   the *classifier* for "this looks like a payment to my own liability account" is heuristic. F0 keeps it
   conservative — **exclude and flag**, never auto-attribute.
2. **Retroactive account-entity change** — semantics chosen (§8) but not user-tested. Approval item.
3. **Entity name case-sensitivity** — `unique_together (user, name)` follows `Payee` (`:1678`) and is
   case-sensitive; "Beacon" and "beacon" could coexist. Acceptable for F0; note it.
4. **Cross-user enforcement is not a DB constraint** (§12.2). Recorded residual.
5. **Splits are designed, not exercised.** `share_basis`/`share_value` exist and the partial-unique admits
   them, but no F0 code writes anything but `full`. Risk: the first real split may want per-share evidence.
6. **Reimbursement linkage is deliberately absent.** A later `ReimbursementLink(from_attribution,
   to_attribution)` model attaches **without changing `TransactionAttribution`** — that is what "designed for"
   means here. If Danny wants a field now, say so.
7. **Four legacy population definitions survive F0** (§5.2), ratcheted not converged. Logged residual;
   convergence is F4.
8. **Duplicate transactions** would double-count entity totals. Dedup stays the importer's job.

---

## 17. F0 definition of done

1. `FinancialEntity`, `AccountEntityAssignment`, `TransactionAttribution`, `AttributionRule` exist, all
   user-scoped, with the §10 constraints and indexes.
2. `paid_by` resolves from the temporal assignment for any transaction date.
3. Attribution is first-class: create → correct → supersede preserves complete history; nothing is mutated.
4. User-confirmed attribution cannot be overridden by any inferred path.
5. **One** attributable-population authority exists, with every §5.1 case decided and tested, and the legacy
   definitions ratcheted.
6. Rules are user-owned, scoped, precedence-ordered, and **never auto-created**; category is not a scope.
7. `FinanceDomainTruth` exposes `entity` plus `attributed_to`/`paid_by` — facts only, ready for F1.
8. 40-test matrix green; query-count tests prove no N+1; `makemigrations --check` clean **after** the four
   planned migrations; zero provider calls.
9. Finance still read-only; F-1 contract test still green.
10. Changelog, pathspec commit, push, deploy verified on **both** web and `wlj-worker`.

---

## 18. Decisions requiring Danny's approval

1. **Account-entity temporal default** — forward-dated (recommended) vs retroactive-by-default. §8.
2. **Retroactive supersession** — confirm a retroactive change may supersede *inferred* attributions but never
   *user-confirmed* ones. §8.
3. **Default personal entity display name** — `"Personal"` (recommended, neutral) or your preference. §11.
4. **Bootstrap scope** — finance-active users only (recommended) vs every user. §11.
5. **Unpaired-internal detection strictness** — conservative exclude-and-flag (recommended) vs attempt
   automatic pairing. §16.1.
6. **Reimbursement** — additive link model later (recommended) vs a field on `TransactionAttribution` now. §16.6.
7. **`Transaction.current_attribution` cache** — accept the denormalization with reconciliation + rebuild
   (recommended) vs pure `Exists()` queries. §4.
