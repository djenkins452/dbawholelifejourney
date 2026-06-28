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

1. **Per-day health scalars (C1, C3).** Add SAE per-day fields from existing rows — `steps_yesterday/today`, `sleep_last_night` (most-recent SleepEntry), `glucose_yesterday`, `calories_yesterday` — and point the foundational facts at them (replace the average-as-specific answers). *Acceptance: det_steps/sleep/calories, truth_*, intent_* GREEN.*
2. **Deterministic journal-today & appointments-today providers (C2).** Wire `JournalQueries.has_entry_on` and `build_calendar_state.next_event` into a foundational provider so the declined questions answer deterministically; add a `CalendarQueries` contract (C5). *Acceptance: det_journal, det_appts GREEN.*
3. **Workout-today fact (C2).** `WorkoutQueries.completed_in_range(today,today)` → SAE `workouts_today` + foundational fact. *Acceptance: det_workouts, intent_workout GREEN.*
4. **Freshness envelope (C1/C3, Law 1/2).** Attach as-of + freshness verdict (current/stale/pending/partial/missing) to the per-day facts; pending/missing answer honestly. *Acceptance: fresh_* GREEN; Deep Truth Certification GREEN target.*
5. **Finance Layer 1 (C5, H1-H4).** `FinanceQueries` contract; surface `today` spend + `BankConnection.last_sync_at` freshness; fix the dead cross-domain rule keys; add Beth finance facts; seed a finance acceptance suite.
6. **Faith Layer 1 (H1, H2, H5).** Beth faith foundational facts (last-read, prayer counts/streak, reading-today); seed a faith acceptance suite; (later) reasoning intents + momentum engine.
7. **Relationships consolidation (C4, C5).** Resolve the split-brain (one canonical `Person`, migrate/bridge), add `relationship_queries.py` + cadence verdict, repoint `SignificantEvent.person`; seed acceptance.
8. **Ownership cleanup (H7, MEDIUM).** Fix the broken GDPR export model names; collapse the 3 journal-today readers onto `has_entry_on`; schedule finance snapshots.

Batches 1–4 are the Truth-Certification-to-GREEN critical path. 5–8 broaden the foundation per domain.

*Last updated: 2026-06-28 (Phase 1 inventory established).*
