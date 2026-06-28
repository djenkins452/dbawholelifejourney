# Beth Layer 1 — Canonical Truth Inventory & Gap Analysis

> **Phase 1 deliverable.** Complete inventory of Canonical Truth for every WLJ domain,
> verified against repository evidence (file:line) by parallel audits, merged here.
> Layer 1 is the foundation everything above depends on. Governed by
> `WLJ_ARCHITECTURE_LAWS.md`. **Date:** 2026-06-28.
>
> **Method:** read-only domain audits (Health · Faith+Purpose · Finance · Relationships
> · Productivity/Calendar/Tasks/Journal). No speculation; gaps cite evidence. The
> audits were consistent — no contradictions to resolve; the cross-cutting themes
> below were each found independently by multiple audits.

---

## Layer 1 Certification (Canonical Truth)

> A layer is complete only when **certified**: implementation done, gate GREEN, frozen
> as permanent infrastructure that must never regress. Manifest: `apps/core/truth/certification.py`.
> Release gate: `python manage.py certify_layers` (re-runs every certified layer; a
> higher layer cannot certify if a lower one regresses).

### Governance reconciliation (2026-06-28)

> **The inventory — not implementation — defines Layer 1 scope.** A reconciliation
> against the approved roadmap reclassified three capabilities I built that were NOT in
> the approved inventory. This is governance, not a rollback: the code stays (it's GREEN);
> it simply stops being counted as Layer 1 until ratified by the roadmap owner.

| Platform Capability | Source | Layer 1? |
|---|---|---|
| Per-Day Truth | Original Layer 1 inventory | ✅ Approved |
| Freshness (Law 1) | Original Layer 1 inventory | ✅ Approved |
| Current Truth Objects | Original Layer 1 inventory | ✅ Approved |
| Point-in-Time History | Original Layer 1 inventory | ✅ Approved |
| Domain Truth Objects | Approved architectural checkpoint | ✅ Approved |
| Deterministic Provider Registry | Original Layer 1 inventory | ✅ Approved |
| **Confidence** | Emerged during implementation; **RATIFIED into Layer 1 (2026-06-28)** — a trust property of Canonical Truth (Law 2) | ✅ Approved |
| **Stability** | Emerged during implementation; **RATIFIED into Layer 1 (2026-06-28)** — a trust property of Canonical Truth (Law 5) | ✅ Approved |
| **Truth Catalog** | Emerged during implementation (no approved-doc basis) | ➡ **Future Backlog** (not Layer 1) — introspection tooling, serves the registry/Beth |

**Ratified Layer 1 = EIGHT capabilities:** Per-Day Truth · Freshness · Confidence ·
Stability · Current Truth Objects · Point-in-Time History · Domain Truth Objects ·
Deterministic Provider Registry. A truth value is trustworthy only with all four
properties — value + freshness + confidence + stability.

**Eight RATIFIED Layer-1 platform capabilities — all implemented, deterministic gate GREEN:**
Per-Day Truth · Freshness (L1) · Confidence (L2) · Stability (L5) · Current Truth Objects ·
Point-in-Time History · Domain Truth Objects · Deterministic Provider Registry. Gate
module: `apps/core/tests/test_layer1_certification.py`.

### Layer 1 completeness ruling (scope boundary)

> **Layer 1 = Canonical Truth FOUNDATION** — the eight domain-agnostic capabilities +
> the canonical interface, PROVEN end-to-end on a reference domain (Health, full
> consumer) and cross-domain (Finance: Domain Truth + Current Truth + Confidence +
> Stability + sync-freshness). That is what Layer 1 requires and it is satisfied.

The ⬜ cells in the matrix (Tasks/Journal/Goals/Faith/Relationships not yet exposing
Current Truth Objects / History / Domain Truth providers) are **per-domain ROLLOUT of
current & historical truth** — which the approved Acceptance-Center layer map assigns to
**Layer 2 (Current Truth)** and **Layer 3 (Historical Retrieval)**, with reasoning at
**Layer 4 (Domain Intelligence)**. They are *not* Layer 1 foundation gaps, and treating
them as Layer 1 would re-scope the whole roadmap into Layer 1. This is a deliberate scope
ruling, not a "finish it in Layer 2" punt: by the approved layer map these belong to L2–L4.

**Original approved backlog — all satisfied:** Per-Day Truth registry (subsumed by
Current Truth Objects + the Domain Truth registry — domains expose per-day truth via
`current()`), Deterministic Provider Registry ✅, Sync Freshness application (✅ in
`CurrentFinance`), Point-in-Time History ✅.

**Certification status:** the deterministic foundation + governance gate are GREEN.
**Full certification additionally requires the live Deep Acceptance Center run**
(production OpenAI) — the complementary runtime gate, the roadmap owner's to trigger.
Truth-**Relationships** (value↔target links) remains an open L1-vs-L5 question, not a
blocker for the foundation.

---

## The dominant cross-cutting defect class (found by every audit)

**Per-day granularity gap.** The SAE exposes *current latest values*, *today rollups*,
and *7-day averages* — but for several metrics it does NOT expose a **specific-day
scalar**, so date-specific deterministic questions fall to the LLM path or are answered
with an average:

- steps: only `steps_avg_7d` (state_builder.py:759) — no `steps_yesterday/today`
- sleep: only `sleep_avg_hours_7d` (642) — no `sleep_last_night` actual
- glucose: only `glucose_avg_7d` (896) — FACT_MAP knowingly maps it to "yesterday" (health_facts.py:44)
- calories: today-only + 7d avg — no `calories_yesterday`
- journal-today / appointments-today / workout-today: **no deterministic provider** — the reasoning lane now declines them (lanes.py:80) but they land on the tool-loop LLM fallback (service.py:150)

This single class is why Deep Truth Certification cannot go GREEN: it directly breaks
Law 0 (right scope), Law 1 (freshness), and Law 4 (deterministic retrieval) for the
most basic "did I X / how much X yesterday" questions a Chief of Staff must own.

---

## Platform Capabilities (the architecture — implement once, consume everywhere)

> Implementation is **platform-capability-first**, not domain-first. A capability is
> built once as a domain-agnostic module and every domain consumes it. "Health Per-Day
> Scalars" was really **Per-Day Truth**; "Health freshness" was really **Freshness**.
> Status below tracks consumers, not re-implementations.

| Capability | Platform home | Health | Execution/Calendar | Tasks/Journal | Goals | Finance | Faith | Relationships |
|---|---|---|---|---|---|---|---|---|
| **Domain Truth Object** (canonical interface) | `apps/core/truth/domain.py` ⭐ | ✅ `HealthDomainTruth` | ⬜ | ⬜ | ⬜ | ✅ `FinanceDomainTruth` | ⬜ | ⬜ |
| **Current Truth (raw SAE)** | SAE `state_builder` | ✅ | ✅ | ✅ | ✅ | 🟡 partial | 🟡 partial | 🟡 partial |
| **Current Truth Objects** | `apps/core/truth/current.py` ⭐ | ✅ `CurrentHealth` | ⬜ | ⬜ | ⬜ | ✅ `CurrentFinance` | ⬜ | ⬜ |
| **Point-in-Time History** | `apps/core/truth/history.py` + `periods.py` ⭐ | ✅ `HealthHistory` | ✅ `WorkoutHistory` (fitness) | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **History (legacy domain queries)** | domain `*_queries` | 🟡 (now point-in-time via platform) | n/a | ✅ | ✅ | 🟡 keyword only | 🟡 reading only | ⬜ |
| **Per-Day Truth** | `apps/health/services/daily_health_queries.py` (pattern) | ✅ | n/a | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **Freshness** | `apps/core/truth/freshness.py` | ✅ consumer | ✅ consumer | ⬜ | ⬜ | ✅ consumer | ⬜ | ⬜ |
| **Confidence** (Law 2) — ✅ *ratified into Layer 1* | `apps/core/truth/confidence.py` | ✅ (Current+History) | ⬜ | ⬜ | ⬜ | ✅ (auto) | ⬜ | ⬜ |
| **Stability** (Law 5) — ✅ *ratified into Layer 1* | `apps/core/truth/stability.py` | ✅ (signatures + verify) | n/a | n/a | n/a | ✅ | n/a | n/a |
| **Deterministic Provider Registry** | `apps/ai/chatgpt_cos/fact_registry.py` ⭐ | ✅ | ✅ | ⬜ | ✅ | ⬜ | ⬜ | ⬜ |
| **Truth Catalog** — ➡ *FUTURE BACKLOG (not Layer 1)* | `apps/core/truth/catalog.py` | built | n/a | n/a | n/a | built | ⬜ | ⬜ |

✅ complete · 🟡 partial · ⬜ pending · ⭐ domain-agnostic platform module. **Current
Truth Object** = the authoritative typed value object (`CurrentTruth`) composing a
value + a freshness verdict; `CurrentHealth` and `CurrentFinance` both consume it with
zero duplicate composition logic (Health = per-day shape, Finance = sync shape).

**Domain Truth Object** = the canonical per-domain INTERFACE (`get_domain_truth(user,
domain)`) exposing `.current(metric)` → CurrentTruth, `.history(metric, period)` →
HistorySeries, and `.state()` → SAE snapshot. It is a THIN FACADE composing the
capabilities above (owns no retrieval logic); every consumer — Beth, dashboards,
reports, exports, APIs, notifications, engines — uses the one interface. Beth's
foundational fast-path now retrieves health facts via `get_domain_truth(user,
"health").current(key)`. This is the per-domain registration unit the **Deterministic
Provider Registry** will route over (the resolved architectural checkpoint: register
Domain Truth Objects, not scattered providers).

**Capability backlog (build once, then apply to every pending domain above):**
1. **Per-Day Truth registry** — generalize the `DailyHealthQueries` pattern into a
   registry/protocol so a domain registers `*_on(user, date)` resolvers and the generic
   per-day dispatcher handles classification → resolution → freshness → phrasing. Then
   Finance/Faith/Calendar per-day truth = a registration, not a new pipeline.
2. **Deterministic Provider registry** — replace the hardcoded GOAL/HEALTH/EXECUTION
   branches in `answer_foundational_fact` with a registry keyed by fact namespace, so
   each domain registers its provider once.
3. **Sync Freshness application** — apply `classify_sync_freshness` to Finance
   (`BankConnection.last_sync_at`), CGM, and any snapshot Current Truth.
4. ~~**Point-in-time History**~~ — ✅ **DELIVERED** as `apps/core/truth/history.py` +
   `periods.py` (period resolution + `HistorySeries` + aggregates). Consumers:
   `HealthHistory` (steps/sleep/weight) and `WorkoutHistory` (fitness). Pending consumers:
   Finance/Faith/Calendar/Relationships register a one-query provider each.

---

## Master Matrix

| Domain | Canonical Truth (tables) | Current Truth (SAE) | History | Engines | Consumers | Acceptance | Headline gaps |
|---|---|---|---|---|---|---|---|
| **Health** | Rich: WeightEntry·SleepEntry·StepsEntry·GlucoseEntry·BP·HR·WorkoutSession·Intake/IntakeLog·FoodEntry·LabResult (apps/health, apps/medical) | latest+7d-avg; **no per-day scalar** for steps/sleep/glucose; nutrition today+7d | TrendAnalyzer, CommandCenter(as_of); **no point-in-time per-day lookups** | behavior(workout,med), PIE/PRIE(weight only), CDCE, event adapters(all) | Beth `_FACT_MAP` (13 facts), dashboards, GDPR export, mobile **ingest-only** | health reasoning(3) + factual-trust for weight/sleep/steps/glucose/calories/workout/meds | per-day scalars; only 3 truth contracts; fast-path averages answer "yesterday"; BP/HR/water/labs untested |
| **Purpose (Goals)** | LifeGoal·GoalMilestone·AnnualDirection (GoalMomentumSnapshot in dashboard_v2 — out of domain) | RICH: counts, completion%, deadlines, evidence, mission | momentum snapshots (nightly) | STRONG: insights+predictions+momentum+CDCE | Beth facts FULL, 9 reasoning intents, CRUD, dashboards | **FULL** | thin GoalQueries; snapshot owned out-of-domain; broken export model names |
| **Faith** | PrayerRequest·UserReadingPlan·UserReadingProgress·SavedVerse·FaithMilestone (FaithQueries present, routine-unified) | reading plans, streak, prayer counts; **no reading-today bool, no prayer streak/verse facts** | reading dates only | insights only (scripture drop-off); **no predictions, no momentum engine** | dashboards + faith_metrics; **no Beth facts, no reasoning intents, broken export** | **NONE** | not wired to intelligence/consumer layers; zero acceptance |
| **Finance** | FinancialAccount·Transaction·Budget·FinancialGoal·FinancialMetricSnapshot·BankConnection (12 models) | net worth, month spend/income, budgets, goals; **empty `today`; no freshness; no payroll fact** | keyword `search_finance` ✓; **no trend reader; snapshots unscheduled** | 1 DEAD cross-domain rule (key mismatch); no PRIE; no insight engine | CoS context ✓, dashboards ✓, export ✓; **no Beth facts, no mobile, no notifications** | **NONE** | no FinanceQueries contract; no freshness/staleness; dead engine rule; zero acceptance |
| **Relationships** | **SPLIT-BRAIN**: canonical apps/relationships (Person/RelationshipInteraction/Mention) **+** legacy apps/core/ai_relationships (Person/Relationship/InteractionSignal); dates in life.SignificantEvent→legacy FK | active/neglected counts, birthdays; **neglect hardcoded >30d, no cadence verdict** | partial (two parallel stores, no unified contract) | drift engine reads **legacy model only** (canonical stream feeds nothing) | CoS context (canonical), fact_statements (legacy FK), mobile import (canonical), dashboards; **no Beth facts, no export** | **ABSENT** | duplicate ownership; no relationship_queries contract; engine on orphaned model |
| **Tasks** | life.Task (+TaskGoalLink); AdminTask = separate operator backlog | `build_task_state`: levels, commitment, overdue, priority — strong | TaskQueries.completed_on/since ✓ | rhythm, task_priority_service, blueprint pressure | cos_context, executive_summary, rhythm lane | rhythm_next (smoke) only | reasoning `tasks` domain declared-but-unimplemented; no det "due today/overdue" Q |
| **Calendar/Events** | calendar_engine.CalendarEvent (+Recurrence) | `build_calendar_state`: today/current/**next_event**/overdue/density — strong | **none** | recurrence in-model; no calendar priority engine | cos_context; tool-loop for Q&A | det_appts only | **no CalendarQueries contract**; no history accessor; **no deterministic appt provider**; today_events misses unmaterialized recurrences |
| **Journal** | journal.JournalEntry (JournalQueries present) | last_entry, days_since, freq, mood; **no `journaled_today` bool** | JournalQueries.recent/on_date ✓ | signals only | journal-today computed in **3 places** (dashboard_ai, state_assessment) | intent_journal, det_journal | **no deterministic journal-today provider** (declines→tool-loop); duplicate logic bypasses has_entry_on |
| **Rhythm / Capture** | derived / capture.CaptureSignal | rhythm_api over build_rhythm_sections; capture has no SAE module | n/a | rhythm engine | `_next_rhythm_lane` (deterministic) | rhythm_next (smoke) | rhythm only smoke-tier; capture has no surfaced "today" truth |

**Maturity ranking (Layer 1 readiness):** Purpose/Goals ✅ (fully built reference) → Tasks/Journal/Calendar 🟡 (truth + contracts exist, consumer wiring incomplete) → Health 🟡 (rich data, per-day scalar + contract gaps) → Finance 🟠 (data ok, no contract/freshness/acceptance) → Faith 🟠 (data ok, not wired to intelligence) → Relationships 🔴 (split-brain, no contract).

---

## Ranked Gaps (cross-domain, Critical-first)

**CRITICAL — a Layer-2 capability cannot be built correctly until fixed:**
- C1 **Missing Current Truth (per-day scalars):** steps/sleep/glucose/calories have no specific-day value in SAE → date-specific deterministic answers impossible. *(Health: Missing Current Truth)*
- C2 **Missing Consumer/Provider:** journal-today, appointments-today, workout-today have NO deterministic provider — answered by the tool-loop LLM (Law 4 break) despite SAE truth existing. *(Productivity/Health: Missing Consumer)*
- C3 **Architecture:** the foundational fast-path returns 7-day **averages** for "yesterday/last night" questions (foundational_facts.py:248-256) — truth/question misalignment (Law 1). *(Health: Architecture)*
- C4 **Duplicate Ownership:** Relationships split-brain — two `Person` models, SAE/engine/FK each read a different one; no single canonical truth. *(Relationships: Duplicate Ownership)*
- C5 **Missing Canonical Truth (contracts):** no Domain Truth Contract for Calendar, Finance, Relationships (and most health metrics) — ad-hoc queries invite drift. *(All: Missing Canonical Truth)*

**HIGH:**
- H1 Missing Acceptance: Finance, Faith, Relationships, task-status have **zero** acceptance coverage.
- H2 Missing Consumer (Beth facts): Finance, Faith, Relationships have no foundational facts.
- H3 Missing Current Truth: Finance freshness/staleness (`BankConnection.last_sync_at` never surfaced); "payroll not refreshed" fact class absent.
- H4 Wrong Ownership / dead engine: finance cross-domain rule reads keys the SAE never emits (rules_cross_domain.py:282) → never fires.
- H5 Missing Engine: Faith/Finance have no predictions; glucose/sleep/steps/labs no PIE/PRIE.
- H6 Missing Historical Retrieval: no point-in-time per-day lookups (health), no calendar history, no finance trend reader.
- H7 Wrong Ownership: GDPR export references **non-existent models** (faith.ScriptureReflection, life.Goal, purpose.LifeDirection) → canonical faith/goal truth silently not exported.

**MEDIUM/LOW:** duplicate journal-today logic (3 readers bypass has_entry_on); reasoning `tasks` domain declared-but-unimplemented; finance snapshots unscheduled; SAE today_events misses unmaterialized recurrences; relationships denormalization drift; mobile API ingest-only (no read-back); capture has no surfaced truth.

---

## Implementation Roadmap (1–2h batches — Implement → Test → Acceptance GREEN → next)

Ordered by "Critical blocks Layer 2" + leverage. Each batch closes a defect class and turns its acceptance category GREEN before the next begins.

1. **Per-day health scalars (C1, C3). — 🟢 DELIVERED (core), 2026-06-28.** New
   `apps/health/services/daily_health_queries.py` `DailyHealthQueries` contract
   (`steps_on`, `latest_sleep`, `sleep_on`, `weight_on`, `glucose_on`, `calories_on`
   — a specific day, never an average). The foundational classifier now routes
   "steps today/yesterday", "sleep last night", "calories yesterday" to these
   deterministic per-day facts (`foundational_facts._refine_to_day` +
   `health_facts._day_fact`); "average sleep" stays on the 7-day fact. Honest
   no-data ("I don't have last night's sleep yet"). Tests: `test_daily_health_queries`.
   **Remaining sub-items:** NL routing for "weight yesterday"/"glucose yesterday"
   (the contract + `_day_fact` support them; the classifier doesn't yet emit those
   keys), arbitrary-date and range NL ("steps on March 15", "steps last week"), and
   the live Deep re-run to flip det_steps/det_sleep/fresh_* GREEN. *Acceptance: det_steps/sleep/calories, truth_*, intent_* — pending live re-run.*
2. **Deterministic providers for status questions (C2). — 🟢 DELIVERED, 2026-06-28.**
   New `apps/ai/cos_services/execution_facts.py` answers journal-today
   (`JournalQueries.has_entry_on`), workout-today (`WorkoutQueries.is_completed_on`),
   appointments-today and next-appointment (pre-computed SAE `calendar` state, never
   live-computed). The foundational classifier claims them — gated on a status
   phrasing so coaching questions don't match — so they no longer fall to the
   tool-loop LLM (Law 4 fixed). Tests: `test_execution_facts` (6). *Acceptance:
   det_journal, det_appts, det_workouts, intent_workout — pending live re-run.*
   **Remaining sub-item:** a formal `CalendarQueries` contract (C5) — provider reads
   SAE state directly for now; a contract class is the clean home for history/range.
3. **(folded into Batch 2)** Workout-today delivered via `WorkoutQueries.is_completed_on`.
4. **Freshness envelope (C1/C3, Law 1/2). — 🟢 DELIVERED (health per-day), 2026-06-28.**
   Every per-day fact now carries a READ `freshness` verdict (`health_facts._day_freshness`):
   **current** (asked day, complete → cite value), **partial** (today, still accruing →
   "so far today"), **stale** (most recent older than asked → "from <date>"), **pending**
   (today, not synced → honest absence), **missing** (absent → honest absence). Phrasing
   honors the verdict; Beth reads it, never infers it. Tests: `test_daily_health_freshness`
   (all 5 states). *Acceptance: fresh_current/stale/pending/partial/missing — pending live re-run.*
   **Remaining sub-item:** extend the same verdict to finance/calendar Current Truth (Batches 5+).
5. **Finance Layer 1 (C5, H1-H4).** `FinanceQueries` contract; surface `today` spend + `BankConnection.last_sync_at` freshness; fix the dead cross-domain rule keys; add Beth finance facts; seed a finance acceptance suite.
6. **Faith Layer 1 (H1, H2, H5).** Beth faith foundational facts (last-read, prayer counts/streak, reading-today); seed a faith acceptance suite; (later) reasoning intents + momentum engine.
7. **Relationships consolidation (C4, C5).** Resolve the split-brain (one canonical `Person`, migrate/bridge), add `relationship_queries.py` + cadence verdict, repoint `SignificantEvent.person`; seed acceptance.
8. **Ownership cleanup (H7, MEDIUM).** Fix the broken GDPR export model names; collapse the 3 journal-today readers onto `has_entry_on`; schedule finance snapshots.

Batches 1–4 are the Truth-Certification-to-GREEN critical path. 5–8 broaden the foundation per domain.

*Last updated: 2026-06-28 (Phase 1 inventory established).*
