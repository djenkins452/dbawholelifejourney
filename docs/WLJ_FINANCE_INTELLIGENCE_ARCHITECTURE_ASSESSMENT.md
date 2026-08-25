# WLJ Finance Intelligence — Architecture & Product Assessment

> **Mode:** ARCHITECT (`WLJ_MASTER_PROMPT.md` §5). **Status:** assessment only — **nothing implemented,
> no provider installed, no governing document modified.** Awaiting Danny's explicit "go".
> **Date:** 2026-08-24

---

## 1. Verdict up front

**Do not build a "Finance Intelligence Engine."** Finance is already a registered WLJ truth domain with a
`DomainTruth` surface, a Current Context page summary, a domain capability registration, a Plaid adapter, and
record-level entity exposure. An "engine" would be a **second reasoning authority inside WLJ** — barred by
Constitution I.2 / IV.2 / IV.4, and it would duplicate machinery that already exists and is prod-proven.

The proposed loop maps onto the platform almost one-for-one:

| Loop stage | Owner | Existing mechanism |
|---|---|---|
| Observe | WLJ | `Transaction` + Plaid sync + import service |
| Understand | WLJ | `FinanceDomainTruth` (current / history / entities) |
| **Contextualize** | **WLJ — GAP** | **no entity attribution truth exists** |
| Detect | WLJ | `Insight` (evidence, explain_why, confidence, dedupe) |
| Prioritize | **the model** | facts from WLJ; ranking-by-magnitude is a calculation, "your biggest problem" is judgment |
| Recommend | **the model** | never WLJ — Article I.4 |
| Learn | WLJ | corrections + `LearnedMapping` pattern; reflection gate is default-deny |
| Verify outcome | WLJ | `ConversationFollowUp` + deterministic re-query |

**The MVP is therefore one new deterministic truth (entity attribution) plus one detector, not a new subsystem.**
Everything else is exposure and reuse.

---

## 2. Required discovery — evidence

### 2.1 User ownership and authorization
- `apps/core/models.py:183` — `UserOwnedModel(NarratableMixin, SoftDeleteModel)`: `user` FK, `created_via`
  provenance choices, soft delete, and the Narratable protocol (`context_ref`, `is_owned_by`).
- Every Finance record already inherits it: `FinancialAccount` (`apps/finance/models.py:50`), `Transaction`
  (`:397`), `Budget` (`:594`), `FinancialGoal` (`:721`), `TransactionImport` (`:1123`), `BankConnection`
  (`:1311`), `Payee` (`:1644`), `RecurringTransaction` (`:1694`).
- Finance carries **extra** authorization beyond the platform baseline: `apps/finance/security.py:41`
  `FinanceAuditLogger`, `:290` `FinanceRateLimiter`, `:401` `requires_recent_auth`, `:438` `verify_ownership`,
  `:483` `mask_account_number`, `:512` `FinanceMFAController`, `:599` `requires_mfa_for_sensitive_ops`. Plus a
  dedicated audit table `FinanceAuditLog` (`apps/finance/models.py:1560`).
- **Forward constraint:** `docs/WLJ_SECURITY_AUTHORIZATION_FRAMEWORK.md` makes **Space** the canonical
  container and today's `user_id` the physical stand-in for a Personal Space. A business entity is a
  **future Space**, not a column — see §5.1.

### 2.2 Domain and engine registration
- `apps/core/domain_registry/descriptors.py:51` `DomainCapability`; `:16` `DomainClass`
  (BEHAVIORAL / INFLUENCE / KNOWLEDGE / CONTEXT / SYSTEM / PRESERVATION); `:47` `COS_PARTICIPATING`.
- Finance is **already registered**: `apps/finance/capabilities.py:4` — `intent_types=['log_transaction',
  'check_budget']`, `related_domains=['goals']`, `feature_flag='features.finance.enabled'`.
- `apps/core/engine_registry.py:64` `EngineDefinition`, `:32` `EnginePhase` — the 14-engine inventory.
  **Finance registers no engine, and should not.**

### 2.3 Personal truth and provenance
- `apps/core/truth/domain.py:94` `DomainTruth`, `:62` `@register_domain_truth`.
- `apps/finance/services/finance_domain_truth.py:14` `FinanceDomainTruth` — `current_metrics` (`:16`),
  `history_metrics` (`:20`), `entity_types = ("transaction", "account")` (`:27`), with an explicit
  never-surface list for credentials/tokens/full account numbers.
- Transaction-level provenance already exists: `source_type` (`apps/finance/models.py:502`, incl. `plaid`,
  `receipt_scan`, `email`), `source_id` (`:509`), `fingerprint` for cross-source dedup (`:516`),
  `plaid_transaction_id` (`:535`), `receipt_document` FK, `import_record` FK.
- **Gap:** there is **no confidence, no classifier attribution, and no "who decided this" field** on
  `category` (`:429`) or `payee` (`:439`). Category is a bare FK — a WLJ-assigned category and a
  user-confirmed category are indistinguishable.

### 2.4 Temporal truth and user corrections
- `apps/core/truth/periods.py :: resolve_date_expression` / `resolve_period` — the single date resolver;
  `FinanceDomainTruth.describe()` already routes through `resolve_period`.
- Corrections: `apps/ai/correction_service.py` — detect → store `CorrectionRecord` → retrieve with priority.
- Learned mappings: `apps/core/ai_memory/models.py:112` `LearnedMapping` (phrase → meaning_type +
  meaning_identifier + `confidence_score` + `usage_count` + `is_active`) — **the exact shape a payee→entity
  attribution rule needs**; `:15` `PersonalFact`; `:222` `ClarificationLog`; `:271` `BehaviorDirective`.
- Learning is **default-deny**: `apps/ai/reflection/engine.py:83` (five-condition gate) and `:182`
  (default-deny read-back). Per `docs/WLJ_EXECUTIVE_REFLECTION_ARCHITECTURE.md` P3, never learn around a
  deterministic defect.

### 2.5 Chief of Staff orchestration and briefing composition
- Runtime: `apps/ai/model_interface/` — `service.py` (turn loop), `constitution.py` (the governing prompt +
  tool surface), `synthesis.py`, `understanding.py`, `confirmation.py`.
- **23 tools total** (`constitution.py`). The truth tools are **domain-agnostic and registry-driven**:
  `get_domain_state` (`:1119`), `search_history` (`:1131`), `get_history` (`:1159`), `get_readings` (`:1204`),
  `get_event_frequency` (`:1250`), `get_consistency` (`:1297`), `get_change_point` (`:1333`),
  `get_ranked_entity` (`:1366`), `get_comparison` (`:1396`), `get_adherence` (`:1425`), `get_entity` (`:1452`),
  `get_analysis` (`:1500`), `get_user_truth` (`:1563`), `get_data_health` (`:1625`).
  **Finance already answers through all of them** by virtue of `FinanceDomainTruth`.
- Dispatch: `apps/ai/model_interface/service.py:931` (`get_domain_state` → `get_domain_state(user, domain)`).
- Briefing composition: `apps/core/cos_briefing/executive_summary.py:339` and `:652` read `Insight`;
  `apps/core/ai_orchestrator/cos_context.py:1651` pulls recent insights into CoS context — **so a Finance
  `Insight` reaches the Chief of Staff with no new plumbing.**
- Current Context: `apps/core/current_context.py:85` `register_page_summary`, `:292` `PageSummaryMixin`, `:268` `CurrentContextMixin`;
  Finance provider at `apps/finance/page_summaries.py:26` (`finance.dashboard`) — facts-only, reads the one
  shared `build_finance_home_summary`.

### 2.6 Goals integration
- `apps/finance/models.py:820` — `FinancialGoal.life_goal` FK → `purpose.LifeGoal`. The join already exists.
- `apps/purpose/mission_link.py` — Mission Link is a deterministic **join + rank**
  (`action → signal_type → GoalSignalSource → active goals`), explicitly *not* an engine. Finance
  participates by producing a `signal_type`, not by inventing a taxonomy.

### 2.7 Insight, recommendation, and action lifecycles
- `apps/core/ai_insights/models.py:11` `Insight` — `severity`, `confidence_score` (`:53`), `explain_why`
  (`:57`), `evidence` JSON "dates, values, record ids, rule_name" (`:60`), `dedupe_key` (`:72`), `status`
  new/read/dismissed (`:65`), `notified_at` (`:75`). **This is already the "detect + explain the evidence"
  contract the MVP asks for.**
- Feedback: `apps/core/ai_feedback/models.py:112` `InsightEngagement`, `:152` `InsightEngagementProfile`,
  `:17` `PredictionOutcome`.
- Routing: `apps/core/action_router.py` — every actionable item resolves to ONE `ActionRoute`
  (`informational` / `complete_here` / `open_workflow`) against the canonical `TeachingDestination` registry.
- Follow-through: `apps/ai/models.py:2322` `ConversationFollowUp` — WLJ owns the commitment (`due_at`,
  `topic`, `subject_ref` as `app_label.model:pk`, status lifecycle pending→delivering→delivered/resolved/
  cancelled/failed, `MAX_ATTEMPTS`), the model authors the wording **fresh from current truth at fire time**.
  **This is the "verify whether the change occurred" mechanism — already built and prod-validated.**
- Write path: `apps/ai/model_interface/constitution.py:1653` `ALLOWED_WRITE_INTENTS` — 16 curated intents.
  **No finance intent is in it.** `apps/ai/models.py:2259` `ToolCallLog` audits every call.

### 2.8 Memory and learned preferences
- `apps/core/ai_memory/` — `memory_engine.py`, `confidence_engine.py`, `learning_engine.py`,
  `retrieval_engine.py`, `context_resolver.py`.
- `apps/core/ai_learning/models.py:17` `UserLearnedProfile`, `:178` `LearningExtraction`.
- `apps/ai/memory_service.py`, `apps/ai/correction_service.py`.

### 2.9 Background jobs and scheduling
- `config/settings.py:1259` `CELERY_BEAT_SCHEDULE` — `run-same-cycle-every-60-seconds` (`:1262`
  `apps.core.tasks.run_same_cycle_task`), `run-ise-cycle-every-300-seconds`, plus ~25 crontab jobs.
- **Finance has no `tasks.py` and no beat entry.** Any Finance detection must run inside an existing cycle or
  add one crontab entry — never on the request path.
- Enqueue contract: `apps/core/celery_utils.py :: safe_enqueue`; request-path safety enforced by
  `apps/core/tests/test_request_path_safety_contract.py`.
- Railway's ephemeral filesystem resets `PersistentScheduler` → **long-interval periodic tasks must be
  crontab, not interval.**

### 2.10 Notifications
- `apps/core/models.py:1798` `Notification`; `Insight.notified_at` gates duplicate notification.
- Proactive delivery: `apps/ai/proactive_checkins.py :: _create_proactive_message` (called at `:204`, `:276`,
  `:332`, `:358`, `:423`, `:458`) — the existing channel the follow-up system already reuses.
- Digest: `notification-digest-daily-945am-utc` in the beat schedule.

### 2.11 External-provider adapters
- **Plaid already exists:** `apps/finance/services/plaid_service.py:40` `PlaidService` — `is_configured()`
  (`:59`), `create_link_token` (`:108`), `exchange_public_token` (`:186`), `get_accounts` (`:237`),
  cursor-based `sync_transactions` (`:269`), `remove_item` (`:326`); `PlaidNotConfiguredError` (`:35`).
  Config at `config/settings.py:1006–1008` (`PLAID_ENV` defaults to **sandbox**; client id/secret default
  empty). Token storage: `BankConnection` (`apps/finance/models.py:1311`) +
  `apps/finance/services/encryption.py`; audit `BankIntegrationLog` (`:1498`).
- **Model provider:** every client goes through `apps/ai/llm_admission.py :: build_guarded_client`
  (`apps/ai/services.py:214`) and every billable request writes `owner_finance.LLMUsageEvent` via
  `apps/ai/llm_accounting.py` (`apps/ai/services.py:815, 984, 1030, 1229`).

---

## 3. What already exists that the proposal would duplicate

1. **Domain truth** — `FinanceDomainTruth` already serves current metrics, 3 history metrics, and
   record-level `transaction` / `account` entities to all 14 generic truth tools.
2. **Detection contract** — `Insight` already carries evidence + explain_why + confidence + dedupe + status,
   and already flows into the executive briefing and CoS context.
3. **Correction & learning** — `LearnedMapping` / corrections / default-deny reflection gate.
4. **Outcome verification** — `ConversationFollowUp` with `subject_ref` and a real status lifecycle.
5. **Delivery** — `Notification`, proactive messages, `ActionRoute`, Current Context page summary.
6. **Ingestion** — Plaid adapter + file import + fingerprint dedup + source provenance.

## 4. The genuine gaps (this is the whole MVP)

| # | Gap | Evidence it's missing |
|---|---|---|
| **G1** | **Entity attribution.** No concept of a business/entity anywhere in the repo — no `is_business`, no entity FK on `Transaction` or `FinancialAccount`; "Beacon" appears nowhere in `apps/`. | §2.3, grep of `apps/` |
| **G2** | **Classification provenance + confidence.** `Transaction.category` (`:429`) and `payee` (`:439`) record *what* but never *who decided it, from what evidence, how sure, and whether the user confirmed*. | §2.3 |
| **G3** | **A deterministic Finance detector** producing `Insight` rows. `apps/finance/` has no `tasks.py`, no beat entry, and no insight producer. | §2.9 |
| **G4** | **Attribution learning store** — the Finance analogue of `LearnedMapping` (merchant/payee → entity, with confidence and usage), so a confirmation actually changes future classification. | §2.4 |
| **G5** | **Outcome re-verification query** — "did this charge move to a Beacon account?" needs a deterministic recurring-charge comparison; `RecurringTransaction` (`:1694`) + `fingerprint` (`:516`) are the raw material, unassembled. | §2.7 |

## 5. Recommended architecture

### 5.1 One new truth object: the financial entity
Model a **`FinancialEntity`** (user-owned) — *not* a hardcoded "Beacon", *not* a boolean on the account.
Two attributions per transaction, and the whole product lives in the difference between them:

- **paid_by** — derived deterministically from `Transaction.account` (already truth, zero new state).
- **attributed_to** — which entity *should* bear the cost, with `source` (rule / user / import),
  `confidence`, and `evidence`.

A finding is then a pure deterministic predicate: `attributed_to = <business>` **AND**
`paid_by.entity = <personal>`. No reasoning, no model call, fully auditable.

**Space alignment (important):** `docs/WLJ_SECURITY_AUTHORIZATION_FRAMEWORK.md` names **Space** as the
canonical container and `user_id` as today's stand-in for the Personal Space. A business is a textbook future
Space. **Design `FinancialEntity` so it can later become a Space reference** (stable id, ownership through the
user, no capability logic on it). Do not build entity-scoped permissions now — that is the framework's job.

### 5.2 Attribution provenance (G2) — extend, don't fork
Add attribution fields alongside the existing `source_type` provenance rather than a parallel table, and give
the *rule* its own record (the `LearnedMapping` shape): `payee/merchant pattern → entity`, `confidence`,
`usage_count`, `is_active`, `created_from` (user confirmation vs seeded rule). Reuse `Payee`
(`apps/finance/models.py:1644`, already has `default_category`) as the anchor — a new merchant taxonomy
would violate IV.3.

### 5.3 Detection (G3) — a deterministic rule, in an existing cycle
A `finance` insight producer that emits `Insight(module="finance", insight_type="entity_expense_mismatch")`
with `evidence` = the transaction ids, amounts, dates, the matched rule, and the account. It runs in the
**SAME/ISE cycle or one crontab entry**, never on the request path, and it emits **facts only** — the
`message` states the mismatch and the magnitude; it must not say "you should move this."

### 5.4 Prioritize / recommend — the model, not WLJ
WLJ supplies magnitude, frequency, recurrence, confidence, and history (all I.3 calculations). Ranking *by a
stated numeric* is a calculation; declaring something "your biggest financial problem" or "you should switch
the card" is judgment (I.4) and belongs to the model. **No verdict fields, no "recommendation" text
generated by WLJ.**

### 5.5 Confirm / correct / learn — the existing spine
Confirmation and correction flow through the existing deterministic path
(validate → confirm → execute → audit), and a confirmation writes the attribution rule (G4). Learning stays
**explicit-first and default-deny**: a user confirmation is an explicit signal and may write a rule; an
inferred pattern may not silently do so.

### 5.6 Verify outcomes — `ConversationFollowUp`, unchanged
When Danny accepts "move this to the Beacon card", the CoS calls the existing `schedule_follow_up` with
`subject_ref` pointing at the recurring charge. At fire time the follow-up re-grounds in **current** truth and
the deterministic re-query (G5) answers whether the charge moved. **No new scheduler, no new channel, no
stored prose.**

### 5.7 What must be retired, not extended
`apps/finance/services/ai_insights.py:49` `FinanceAIService` is a **domain-local reasoning engine**: its own
system prompt (`:562`), its own insight generation (`:375`, `:439`, `:473`, `:509`), calling
`AIService._call_api` from four view endpoints (`apps/finance/views.py:1499, 1551, 1584, 1622`). It predates
the pivot and conflicts with I.2 / IV.4 (a second reasoning path outside the Model Interface seam). It also
reaches the provider from a **request path** through a service layer — the documented residual the safety
contract explicitly cannot catch (`apps/core/tests/test_request_path_safety_contract.py:26–29`), and it is
**not** in `INLINE_LLM_ALLOWLIST` (`:80`, which contains only `apps/health/views.py`).
**Recommendation: retire these four endpoints in the same milestone that ships Finance truth** — the CoS
already answers these questions better through the generic truth tools. Do not build new capability on top of
it. *(Flagged, not fixed — out of this assessment's scope.)*

---

## 6. Constitution check

| Article | Assessment |
|---|---|
| **I.1 truth in WLJ** | ✅ Entity attribution is deterministic personal truth — correctly WLJ's. |
| **I.2 no reasoning engine** | ⚠️ The word "Engine" is the risk. A detector emitting facts is fine; a Finance "intelligence engine" that ranks, recommends, or narrates is not. **§5.7 already violates this today.** |
| **I.3 WLJ owns calculations** | ✅ Mismatch detection, magnitude, recurrence, annualized impact = WLJ. |
| **I.4 model owns judgment** | ⚠️ "Prioritize" and "recommend" in the stated loop must resolve to *facts + model reasoning*, never a WLJ verdict field. |
| **I.7 safe action path** | ✅ Read-only MVP. Structurally enforced today: no finance intent in `ALLOWED_WRITE_INTENTS` (`constitution.py:1653`). **Keep it that way — that is the "must not move money" guarantee.** |
| **II Current Context** | ✅ `finance.dashboard` provider exists; any new Finance page ships its provider in the same change. |
| **III single authority** | ⚠️ `FinanceDomainTruth`/`FinanceHistory` must remain the one producer. A detector must consume them, not re-derive spending. §5.7's service currently re-derives (`_get_spending_summary` at `:99`). |
| **IV.2/IV.3/IV.4 reuse & expose** | ✅ The recommendation is ~1 new model + 1 rule record + 1 detector; everything else is reuse. |
| **V.1 product-first** | ✅ The Beacon case is real friction with a verifiable outcome — the right MVP. |
| **Naming §1** | ⚠️ **"Beacon" must never be hardcoded.** It is one user's entity name, exactly as "Beth" is one user's assistant name. |

**No Constitutional Review is required** for the recommended shape. One *would* be required to build a Finance
reasoning/classifier engine, to let WLJ emit financial verdicts, or to add finance write intents.

---

## 7. Risks

1. **Cost.** Per-transaction model classification would be ruinous (`docs/WLJ_OPENAI_COST_AUDIT.md`).
   Classification must be **deterministic rules + user confirmation**; the model reasons only inside a
   conversation the user started. No batch model passes over transaction history.
2. **Fabrication in a high-stakes domain.** A wrong financial claim destroys trust faster than a wrong step
   count. Every attribution must carry confidence + evidence and be presented as such.
3. **Provider credentials.** Connecting a bank via Plaid means the *user* enters institution credentials in
   Plaid Link — never Claude, never WLJ. `PLAID_ENV` currently defaults to `sandbox`; a production connection
   is Danny's decision and its own milestone.
4. **Request-path regression.** Finance already has the only unreviewed service-layer LLM path in the repo
   (§5.7). Adding more before retiring it compounds it.
5. **Scope creep into money movement.** The read-only boundary is currently structural. It stops being
   structural the moment a finance write intent is added — that should require an explicit decision, not a
   milestone footnote.
6. **Premature multi-entity permissions.** Building entity-level access control now would pre-empt the
   ratified Space model. Keep `FinancialEntity` a plain user-owned record.

---

## 8. Proposed phasing (for approval — not started)

- **F0 — Entity truth.** `FinancialEntity` + attribution fields + rule record. Migrations, admin, tests.
  No detection, no CoS surface. *Exit: Danny can mark a payee as belonging to an entity and it persists with
  provenance.*
- **F1 — Detection.** The deterministic mismatch rule emitting `Insight` in an existing cycle, with evidence.
  *Exit: the Beacon-paid-from-personal set appears with correct evidence and no false positives on real data.*
- **F2 — Conversation.** Expose attribution through the existing truth tools; the CoS explains the evidence
  and Danny confirms or corrects in conversation; confirmations write rules. *Exit: the loop works in one
  real conversation.*
- **F3 — Follow-through.** `schedule_follow_up` on accepted recommendations + the deterministic outcome
  re-query. *Exit: the CoS asks later, and answers correctly whether the charge moved.*
- **F4 — Cleanup (independent).** Retire the four `FinanceAIService` endpoints (§5.7).

**Deferred with triggers (not "someday"):** production Plaid connection → trigger: Danny wants live sync
rather than imports. Multi-entity Spaces → trigger: a second person needs access to Beacon data. Finance
write actions → trigger: an explicit decision to leave read-only, taken on its own merits.

## 9. Open decisions for Danny

1. **Entity naming/scope** — is "Beacon" one of several entities (LLC, side business, household), or the only
   one? Determines whether `FinancialEntity` is a list or a pair.
2. **Attribution source of record** — should attribution live on the transaction (fast queries, per-row
   override) or be derived from a rule at read time (no stale rows, no backfill)? *Recommendation: store on the
   row with the rule id + confidence, so a rule change is auditable rather than retroactive.*
3. **Read-only confirmation** — confirm the MVP stays read-only, i.e. **no finance intent is added to
   `ALLOWED_WRITE_INTENTS`**.
4. **§5.7 retirement** — retire the legacy Finance AI endpoints in F4, or earlier?
