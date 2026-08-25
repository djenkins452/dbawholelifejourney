# F-1 — Legacy Finance AI Retirement · Implementation Plan

> **Mode:** ARCHITECT → BUILD. **Status:** ✅ **IMPLEMENTED 2026-08-24** (see §8 As-built). F0 NOT started.
> Governing assessment: `docs/WLJ_FINANCE_INTELLIGENCE_ARCHITECTURE_ASSESSMENT.md` (§10.4 ratifies this phase).
> **Date:** 2026-08-24

**Goal:** remove the domain-local Finance reasoning service and its request-path provider calls **without
losing any user outcome**, and leave behind the canonical replacements plus the read-only invariant test.

---

## 1. The proven runtime / caller map

**Method:** repo-wide search across `apps/`, `templates/`, `static/`, `frontend/` (excluding `venv/`, `.git/`,
`staticfiles/`, `node_modules/`, `.claude/worktrees/`) for the four view symbols, the four URL names, and the
four literal URL paths.

### 1.1 The surface

| URL | Name | View | Service method |
|---|---|---|---|
| `/finance/api/insights/spending/` | `finance:api_spending_insight` | `views.py:1492` | `generate_spending_insight` (`ai_insights.py:375`) |
| `/finance/api/insights/subscriptions/` | `finance:api_subscription_review` | `views.py:1547` | `generate_subscription_review` (`:509`) |
| `/finance/api/insights/budget/<pk>/` | `finance:api_budget_alert` | `views.py:1580` | `generate_budget_alert` (`:439`) |
| `/finance/api/insights/goal/<pk>/` | `finance:api_goal_encouragement` | `views.py:1618` | `generate_goal_encouragement` (`:473`) |

Routes: `apps/finance/urls.py:80–83`. Service: `apps/finance/services/ai_insights.py:49` `FinanceAIService`
(+ factory `:662`), own system prompt at `:562`, provider call via `AIService._call_api`
(`apps/ai/services.py:493`) at `ai_insights.py:412, 467, 503, 542`.

### 1.2 Callers — **the finding**

**Zero live callers.** Verified absent:

- **Templates:** no reference in `templates/` — the only `fetch()` calls in `templates/finance/*.html` are the
  five Plaid connection endpoints (`bank_connection_list.html:141, 154, 197, 233, 265`).
  `templates/finance/dashboard.html` contains **no** insight surface at all.
- **JavaScript / static:** no reference in `static/` or `frontend/`.
- **Python:** `get_finance_ai_service` / `FinanceAIService` are imported **only** by the four view functions
  (`apps/finance/views.py:1499, 1551, 1584, 1622`). Nothing else in `apps/` imports the module.
  *(Note: `apps.core.ai_insights` — the canonical PIE insight service — is a different module with a
  similar name; its many callers are unrelated to this retirement.)*
- **Tests:** `apps/finance/tests/` contains `test_finance_comprehensive.py`, `test_finance_history.py`,
  `test_finance_home_summary.py` — **none** reference the service, the views, or the URLs.
- **Only mention outside the code:** `@WLJ_SYSTEM_PROMPTS/04_DISCOVERY_REFERENCE/02b_Domain_Catalog_…_Finance.md:258`
  — a dated (2026-06-23) point-in-time catalog, REFERENCE_ONLY. Not a caller.

### 1.3 Reachability today

The endpoints are reachable **only by typing the URL**. Even then they are gated:
`FinanceAIService.check_consent` (`ai_insights.py:72`) requires `AIService.check_user_consent(user)` **and**
`prefs.finance_enabled` **and** `not prefs.finance_ai_disabled`; `api_spending_insight` additionally
rate-limits to 10/hour (`views.py:1504, 1510`; limits at `security.py:301`) and writes a `FinanceAuditLog` row
(`log_ai_query`, `security.py:275`).

**Conclusion: no user-visible feature depends on these endpoints.** The risk they carry is not lost
functionality — it is an unreviewed request-path provider call and a second reasoning authority.

---

## 2. User-visible behavior being preserved

Nothing is visible today, so the honest question is: **is the underlying capability available through the
canonical path?** Three of four are; one has a real gap, and F-1 closes it by **exposure, not invention**.

| Legacy capability | Canonical replacement | Status |
|---|---|---|
| Spending insight (30-day summary, trends, unusual spend) | `get_domain_state("finance")` + `get_history("finance", "spending"/"income"/"net_cashflow")` + `get_analysis` — all served by `FinanceDomainTruth` (`finance_domain_truth.py:16, 20`) over `FinanceHistory` | ✅ exists, strictly better (real numbers, model interprets) |
| Subscription review (recurring/subscription list) | — `RecurringTransaction` (`models.py:1694`) is **not** in `FinanceDomainTruth.entity_types` (`:27`) | ⚠️ **gap — F-1 closes it** |
| Budget alert (one budget's status) | — `Budget` (`models.py:594`) not exposed as an entity; only `over_budget_count` in the page summary | ⚠️ **gap — F-1 closes it** |
| Goal encouragement (one savings goal) | — `FinancialGoal` (`models.py:721`) not exposed as an entity; only `active_goal_count` in the page summary | ⚠️ **gap — F-1 closes it** |

**Net effect for the user:** questions that previously required an unlinked JSON endpoint ("what subscriptions
am I paying for?", "how is my vacation fund doing?", "am I over on groceries?") become answerable **in the
Chief of Staff conversation**, grounded in real records rather than a summarized prompt.

---

## 3. Replacement design

### 3.1 Expose three existing truths (the only additive work)
Extend `FinanceDomainTruth.entity_types` from `("transaction", "account")` to
`("transaction", "account", "recurring", "budget", "goal")`, following the existing `_transaction_entity` /
`_account_entity` pattern (`finance_domain_truth.py:98, 114`) exactly:

- **`recurring`** — identity = merchant/description; definition = amount, cadence/frequency, category,
  account, next due date; status = active/paused.
- **`budget`** — identity = category name; definition = budgeted amount, period; standing = spent-to-date and
  remaining, read from the **existing** budget computation, never re-derived (III.1 / IV.3).
- **`goal`** — identity = goal name; definition = target amount, target date, linked `LifeGoal`;
  standing = current amount and progress.

**Facts only — no verdicts** ("over budget by $40", never "you're overspending"). All three reuse existing
model fields and existing computations; F-1 adds **no new calculation**.

### 3.2 Remove the legacy service
Delete `apps/finance/services/ai_insights.py`, the four view functions, and `urls.py:80–83`.

**Deliberately *not* removed:**
- `FinanceAuditLog.ACTION_AI_QUERY` (`models.py:1584`) and the migration's choice list — **historical audit
  rows must stay readable**; removing the choice would force a migration and destroy evidence.
- `FinanceRateLimiter`'s `ai_query` limit (`security.py:301`) and `log_ai_query` (`:275`) — harmless, and F2's
  controlled review experience is the natural next consumer of exactly this limiter.

### 3.3 The documented (not built) on-page path
If a Finance insight surface is ever wanted on the dashboard, the canonical path is
`apps.core.ai_insights.services.get_module_insight(user, "finance")` (`services.py:27`) — a **pure DB read**
of a pre-computed `Insight`, zero provider cost, request-path safe, and already the pattern other module home
pages use (e.g. `apps/journal/views.py:1155`). It is fed by **F1's deterministic detector**, not by a provider
call. **F-1 documents this; it does not build it.**

### 3.4 The read-only invariant (ratified §10.3)
A new contract test records the invariant permanently:

- **no Finance intent in `ALLOWED_WRITE_INTENTS`** (`constitution.py:1653`);
- **no module under `apps/finance/` constructs a provider client, imports `AIService`, or defines a system
  prompt** — the class-elimination move: it makes a *recurrence* structurally detectable, not just this
  instance removed;
- `apps/finance/views.py` stays clean under the existing request-path scanner, and Finance is **not** added to
  `INLINE_LLM_ALLOWLIST`.

The distinction the test encodes: **WLJ may write its own classification of the world; it may never write to
the world.**

---

## 4. Focused acceptance tests

| # | Test | Asserts |
|---|---|---|
| T1 | `test_finance_read_only_contract.py::test_no_finance_write_intents` | No name in `ALLOWED_WRITE_INTENTS` maps to a Finance handler/model |
| T2 | `…::test_no_provider_client_in_finance` | No file under `apps/finance/` imports `AIService`/`OpenAI`/`build_guarded_client` or defines a system prompt (AST/source scan) |
| T3 | `…::test_finance_not_in_inline_llm_allowlist` | `apps/finance/views.py` ∉ `INLINE_LLM_ALLOWLIST` |
| T4 | `test_finance_domain_truth.py::test_recurring_entities` | `describe("recurring")` returns facts-only entities, user-scoped, no verdict strings |
| T5 | `…::test_budget_entities` | Budget entities reuse the existing computation (asserted equal to the page-summary source) |
| T6 | `…::test_goal_entities` | Goal entities expose target/current/linked `LifeGoal` |
| T7 | `…::test_ownership_isolation` | A second user's recurring/budget/goal records never appear |
| T8 | `test_finance_urls.py::test_legacy_ai_routes_gone` | `reverse("finance:api_spending_insight")` (and the other three) raise `NoReverseMatch`; the literal paths 404 |
| T9 | Existing regression | `apps.finance` suite + `apps.core.tests.test_request_path_safety_contract` + `apps.core.tests.test_constitution_contract` still pass |
| T10 | Page smoke | `/finance/` and each Finance list/detail page render 200 (proves nothing broke) |

**Cost evidence (acceptance criterion "reduced, not relocated"):** F-1 removes four provider-calling endpoints
and adds **zero**. The three new entity types are ORM reads. Verified by T2 + a `LLMUsageEvent` check that no
new `source` value appears.

**Real-provider calls required: NONE.** Every assertion above is deterministic.

---

## 5. Files expected to change

**Deleted**
- `apps/finance/services/ai_insights.py` (664 lines)

**Modified**
- `apps/finance/views.py` — remove 4 view functions (`:1492–~1660`)
- `apps/finance/urls.py` — remove 4 route rows (`:80–83`)
- `apps/finance/services/finance_domain_truth.py` — `entity_types` + 3 `_*_entity` builders + `describe()` routing
- `docs/ENGINE_COS_REFERENCE.md` — Finance truth surface (auto-maintain rule)
- `docs/WLJ_FINANCE_INTELLIGENCE_ARCHITECTURE_ASSESSMENT.md` — mark F-1 done
- `docs/wlj_claude_changelog.md` — required entry

**Added**
- `apps/finance/tests/test_finance_read_only_contract.py` (T1–T3)
- `apps/finance/tests/test_finance_domain_truth.py` (T4–T7)
- `apps/finance/tests/test_finance_urls.py` (T8)

**Explicitly NOT changed:** no models, **no migrations**, no schema, no fixtures, no templates, no JS, no
settings, no `INLINE_LLM_ALLOWLIST`, no governing document, and nothing outside `apps/finance/` +
`docs/`.

---

## 6. Rollback

- **Single-commit revert.** No migration, no schema change, no data transformation, no fixture reload, no
  settings flag → `git revert <sha>` fully restores the prior state, including the deleted service file.
- **No feature flag needed** — with zero callers there is no traffic to shed; a flag would add a config
  surface for a path nobody calls.
- **Deploy risk:** the removed routes are the only externally-visible change; a stale bookmark to one of the
  four URLs returns 404 instead of JSON. Nothing in the app links to them.
- **Forward-fix preference:** if T4–T7 expose a wrong entity shape after deploy, correct the entity builder
  (a facts-only read) rather than reverting — the removal and the exposure are independent.

---

## 7. Sequenced execution (once "go" is given)

1. Add T1–T3 (read-only invariant) — **expected to FAIL** while the service exists. That failure is the proof.
2. Add the three entity types + T4–T7 — replacement lands **before** removal.
3. Remove the service, views, and routes; T1–T3 now pass; add T8.
4. Run scoped tests: `apps.finance`, `apps.core.tests.test_request_path_safety_contract`,
   `apps.core.tests.test_constitution_contract`. Page smoke T10.
5. `python3 manage.py check` + `makemigrations --check --dry-run` (must report **no changes** — proof that no
   schema moved).
6. Changelog, commit by pathspec, push `main`, verify deploy.

**Not in F-1:** any entity/attribution model (that is F0), any detector (F1), any review UI (F2), any Plaid
change, any `ALLOWED_WRITE_INTENTS` change (forbidden outright by §10.3).


---

## 8. As-built (2026-08-24)

Implemented exactly as sequenced. Deviations from the plan, stated plainly:

- **`docs/ENGINE_COS_REFERENCE.md` was NOT updated.** The plan listed it under the auto-maintain rule, but
  that document does not describe `DomainTruth` entity types anywhere (verified by search) — it covers
  engines, schedules, the CoS context pipeline, and the chat pipeline, none of which this change touched.
  Editing it would have meant inventing a section, not maintaining one.
- **`apps/finance/tests/test_finance_urls.py` also carries the page smoke (T10)** rather than a separate
  file — same scope, one fewer file.

**Proof the invariant is real:** T2/T4 (`test_no_provider_client_in_finance`,
`test_no_domain_local_system_prompt_in_finance`) were written FIRST and **failed**, naming
`apps/finance/services/ai_insights.py` with `['_call_api', 'import apps.ai.services']`. They pass only
because the service is gone.

**Results:** 68 tests green (`apps.finance` + `test_request_path_safety_contract` +
`test_constitution_contract`), plus 10 new entity-truth tests, 5 read-only contract tests, and 4 route/smoke
tests. `makemigrations --check --dry-run` → **"No changes detected"**. **Zero provider calls.**
