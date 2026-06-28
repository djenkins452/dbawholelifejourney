# Beth Domain Reasoning Framework

> **The master specification for how Beth reasons across every life domain.** Health
> is the reference implementation; every future domain is *configured within this
> framework*, not architected from scratch. Documentation/architecture only — no
> code. Governed by `BETH_ARCHITECTURAL_PRINCIPLES.md` (esp. P1, P2, P3, P5, P6,
> P10, P11, P13, P24, P25), `BETH_GOLDEN_BEHAVIORS.md`, `BETH_CHANGE_CONTROL.md`,
> and the worked reference `BETH_HEALTH_INTENT_CONTRACTS.md`.
> **Date:** 2026-06-26
>
> **Validation precedes reasoning (`WLJ_ARCHITECTURE_LAWS.md`, 2026-06-28).** This
> framework specifies how Beth reasons *once inputs are validated*. Before reasoning,
> every domain runs the **Answer Precondition Pipeline**: establish Data Freshness
> (Law 1) and Confidence (Law 2); answer workflow-shaped questions with the
> **Enumeration+Enrichment** orchestration (Law 3), not one reasoning prompt; answer
> deterministic questions deterministically, never with an AI-failure message (Law 4);
> and return identical facts for identical questions over unchanged data (Law 5).
> Reasoning depth is built **on top of** validated, stable, composed truth.

## Purpose & philosophy

The Truth Coverage Audit established that WLJ already computes rich canonical state
for ~18 domains; the gap is **reasoning depth**, not data. This framework converts
future domain expansion from *"design new architecture every time"* into
*"configure a new domain within an existing framework."*

A domain reaches "Beth reasons over it" by filling **eight reusable contracts**
(below). Health already implements all eight — it is the template every domain copies.

```
Reusable per-domain contracts (the framework):
  ① Domain Overview        ② Canonical Truth Source(s)   ③ Foundational Facts
  ④ Reasoning Intents      ⑤ Curator Contract            ⑥ Reasoning Profile
  ⑦ Deterministic Fallback ⑧ Privacy Classification      (+ ⑨ Validation Scenarios)
```

The reasoning lane already implements the *mechanism* (`reasoning/plan.py` planner +
`stages.py` `TRUTH_PROVIDERS` → `INTENT_CURATORS` → `REASONING_PROFILES` → fallbacks).
Adding a domain = **registering entries** in those registries (P6/P13), never new
control flow.

---

# PART A — THE REUSABLE FRAMEWORK (defined once, from Health)

## ① Domain Overview contract
Each domain documents: **name · purpose in WLJ · why Beth should reason about it ·
user value · Chief-of-Staff value.** (Filled per domain in Part B.)

## ② Canonical Truth Source contract (P24)
Each domain names **one canonical source** Beth consumes — never recomputes. The SAE
`build_<domain>_state` (`apps/core/ai_state/state_builder.py`) is the canonical layer
for nearly every domain; the execution contract (`build_today_execution`) is
canonical for schedule/rhythm. Each source is classified:
- **Canonical** — the single authoritative engine Beth reads.
- **Secondary** — a feeder the canonical engine itself consumes (e.g. `DailyHealthSummary` → SAE health). Beth must NOT read it directly.
- **Derived** — a composite over canonical (e.g. `build_transformation_state`, `build_behavior_state`). Allowed as a *read*, never as a competing "next/risk."
- **Deprecated** — must not be used (e.g. `daily_execution_status`).
**Rule:** no duplicate truth sources; if two engines compute the same user fact, one
is canonical and the other is removed or made a consumer (P24).

## ③ Foundational Facts contract
Deterministic, no-LLM, fast scalar answers. Each fact documents:
`fact_id · user questions · deterministic retrieval (which SAE field) · fallback`.
Pattern mirrors `foundational_facts.py` `_FACT_MAP`. Facts NEVER call the planner or
the LLM; they read canonical state and phrase deterministically.

## ④ Reasoning Intents contract — **the canonical quartet**
Generalized directly from the validated Health intents. Every reasoning domain
implements up to **four differentiated intents**:

| Generic intent | Purpose | Cardinality | Frame | Health analog |
|----------------|---------|-------------|-------|---------------|
| `biggest_<domain>_risk` | the **single** top-priority issue | 1 | diagnostic | `biggest_health_risk` |
| `<domain>_progress` | executive **summary** / trajectory | multi-field | status | `overall_progress` |
| `<domain>_focus_today` | **one** concrete action for today | 1 action | imperative, time-aware | `health_focus_today` |
| `<domain>_concerns` | **ranked list** of current concerns | N | enumeration | `health_concerns` |

Each intent documents: purpose · example questions · expected output structure ·
deterministic-fallback requirement · **anti-collapse rules**.

**Anti-collapse invariants (generalized INV-1…5 from `BETH_HEALTH_INTENT_CONTRACTS.md`):**
- **INV-1** `concerns` returns ≥2 items when ≥2 exist; `risk` returns exactly 1.
- **INV-2** `focus_today` contains an imperative action + time context; ≠ `risk` text.
- **INV-3** `progress` is a multi-field status summary, no single-risk framing.
- **INV-4** the four answers are pairwise structurally distinct on one fixture.
- **INV-5** `focus_today` always ends with a concrete action completable in 24h.
*Every intent must produce materially different output — no variations of one answer.*

## ⑤ Curator Contract (P3, P10, P11) — the safety boundary
Each domain has a **`<domain>_working_memory` curator** mirroring
`HealthWorkingMemoryCurator` (`stages.py`). Contract:
- **Inputs:** only its own domain's canonical truth (the SAE state + the domain's
  foundational facts). **No cross-domain truth** (P11) — domain-scoped retrieval drops
  everything outside `INTENT_TRUTH_SCOPE`.
- **Output (model-facing WM):** numbers, booleans, plain coaching phrases, ranked
  concerns. **NEVER** exposes: raw SAE objects, enum codes (`MED`/`LOW`/`HIGH`),
  internal field names, `source` paths (`SAE.<domain>…`), or internal interpretation
  tokens (P3/P10/GB-3.2/GB-5). Internal enums stay in the *ranking inputs*, never in
  what the model sees.
- **Sanitization:** strip `source`, drop `*_label` keys, calibrate severe labels to
  coaching language (the health `_calibrate_label` pattern), time-aware where relevant.

## ⑥ Reasoning Profile Contract
Each domain defines its **coaching style · tone · escalation rules · safety/trust
boundaries** as a `REASONING_PROFILES[intent]` system prompt + max_tokens + fallback.
All profiles carry the shared guidance (no internal labels, evidence-based,
non-alarmist, domain-only — the `_HEALTH_GUIDANCE` pattern, generalized).

## ⑦ Deterministic Fallback Contract (P5) — **Beth must always answer**
Each intent has a deterministic fallback that composes a useful answer from canonical
state **with zero LLM** (the `_health_*_fallback` pattern). Requirements:
- Minimum answer: names the domain's top fact + one action (risk/focus), or the
  ranked list (concerns), or the status summary (progress).
- Graceful degradation: insufficient data → an honest, non-deflecting statement
  ("Your <domain> looks steady — nothing stands out"), never empty, never a generic
  error, never "go look it up" (GB-5).
- The fallback is reached whenever the planner or reasoning LLM fails/empties.

## ⑧ Privacy Classification Contract
Every domain is assigned a tier with explicit OpenAI-exposure rules:

| Tier | Meaning | OpenAI exposure | Summarization | Consent | Redaction |
|------|---------|-----------------|---------------|---------|-----------|
| **Tier 1** (operational) | low sensitivity | curated WM freely | normal | none | none |
| **Tier 2** (sensitive) | health, finance | curated **summaries/derived signals** only; no raw ledgers/clinical values beyond what the fact contract allows | aggressive | ambient OK; raw detail on explicit ask | numbers rounded/banded where possible |
| **Tier 3** (intimate) | emotional, journal, documents | **derived signals only** (mood trend, not entry text); document *content* never ambient | maximal | **explicit retrieval required** for content | full redaction of free text |

## ⑨ Validation Scenarios contract
Each domain ships ≥5 production scenarios covering **happy path · insufficient data ·
contradictory data · stale data · missing data**, each with a *bad* example, a *good*
example, and success criteria.

---

# PART B — PER-DOMAIN CONFIGURATIONS

> Health is the fully-implemented reference. Goals, Finance, and Faith are **fully
> worked** below (they are the near-term targets). The remaining domains are
> configured concisely — each is "fill the eight contracts," not new architecture.

## Health — REFERENCE IMPLEMENTATION (already live)
- **Overview:** vitals/weight/glucose/sleep/nutrition trajectory. Reason: highest
  personal stakes, chronic-condition management. **Canonical:** `build_health_state`
  (Secondary feeder: `DailyHealthSummary`; Derived: `build_transformation_state`).
- **Facts:** weight, glucose (latest/7d), BP, sleep, calories, protein, meds (12 live).
- **Intents:** `biggest_health_risk · overall_progress · health_focus_today · health_concerns` (live, validated).
- **Curator:** `health_working_memory` (drops enums/labels/source; ranked concerns).
- **Profile:** evidence-based, non-alarmist, behavior-focused.
- **Fallback:** `_health_risk_fallback` / `_health_progress_fallback` etc.
- **Privacy:** **Tier 2.** **Status: T4 / complete.**

## Goals / Purpose — **HIGHEST-ROI NEXT (fully worked)**
- **Overview:** life goals, milestones, habits, annual direction. **Why Beth:** a CoS
  exists to keep the principal on-mission. **User value:** "am I on track / what's
  slipping." **CoS value:** prioritization across competing goals.
- **② Canonical:** `build_goal_state` (active_count, completion_rate, next_deadline,
  overdue, active/upcoming/overdue_titles, mission) **+** `build_habit_state` (streaks,
  at_risk, completion_rate). *Canonical.* (`purpose` models = Secondary feeders.)
- **③ Foundational facts:** `top_goal` ("what's my top goal"), `goals_overdue`
  ("what goals are overdue"), `next_goal_deadline`, `active_goal_count`,
  `goal_completion_rate`. Retrieval: `build_goal_state` fields; fallback: "no active goals set."
- **④ Intents:**
  - `biggest_goal_risk` — the single most-at-risk goal (overdue or stalling) + why + one action.
  - `goals_progress` — executive summary: active count, completion rate, mission, next deadline, momentum.
  - `goals_focus_today` — the one goal action to advance today (concrete, INV-5).
  - `goal_conflicts` / `goals_concerns` — ranked list of at-risk/overdue/stalling goals + habits.
  - Anti-collapse: risk=1, concerns=ranked, focus=action, progress=summary (INV-1…5).
- **⑤ Curator `goals_working_memory`:** exposes goal titles, counts, %s, deadlines,
  ranked concerns as coaching phrases. Never: internal goal IDs, raw momentum enums, source paths.
- **⑥ Profile:** motivating, honest about slippage, non-shaming; "name the slip, give the next step."
- **⑦ Fallback:** rank goals by (overdue, days-to-deadline, stall) → risk[0]; list for concerns; status from counts/rate.
- **⑧ Privacy: Tier 1.**
- **⑨ Validation:** on-track goals; no goals set (insufficient); a goal both "ahead" and "overdue milestone" (contradictory); deadline passed weeks ago (stale); habit data missing (missing).

## Finance — fully worked
- **Overview:** accounts, transactions, budgets, financial goals, recurring bills.
  **Why Beth:** financial pressure is a top life-stressor; a CoS watches runway.
  **Value:** "am I overspending / on pace for my savings goal." **CoS value:** early
  risk flags without judgment.
- **② Canonical:** `build_finance_state` (net_worth, accounts, budgets over/warning,
  recurring_obligations, cash_pressure_level, financial goals). *Canonical.*
- **③ Facts:** `net_worth`, `monthly_spending`, `largest_expense_category`,
  `savings_rate`, `next_bill`, `budget_status`. **Tier-2 gated** (banded/rounded).
- **④ Intents:** `biggest_financial_risk` (top pressure: over-budget/low-runway/missed bill) · `financial_progress` (net-worth trend, savings pace, budget health) · `spending_focus` (one money action today) · `financial_concerns` (ranked: over-budget categories, stalled goals, large recurring).
- **⑤ Curator `finance_working_memory`:** **Tier-2 sanitization** — expose *banded* figures and pressure levels ("savings ~12% of income", "groceries 20% over budget"), **never raw account numbers/balances/ledger lines** ambiently. No institution names unless asked.
- **⑥ Profile:** prudent, **non-judgmental**, risk-aware; never moralize spending.
- **⑦ Fallback:** rank by (over-budget severity, runway, missed obligations); status from net-worth trend + savings rate.
- **⑧ Privacy: Tier 2** (raw ledgers Tier-3-style: explicit ask only).
- **⑨ Validation:** healthy budget; no bank connected (insufficient); income up but savings down (contradictory); 3-week-old balances (stale); budgets unset (missing).

## Faith — fully worked
- **Overview:** prayer, Bible reading plans/progress, saved verses, milestones.
  **Why Beth:** Danny's faith is central; a CoS supports consistency, never prescribes
  belief. **Value:** "how's my walk / reading streak." **CoS value:** gentle
  accountability + encouragement.
- **② Canonical:** `build_faith_state` (reading_plans, streak, prayer_requests
  answered/unanswered/urgent, bible_plan, journey_state). *Canonical.*
- **③ Facts:** `reading_plan_current`, `prayer_streak`, `unanswered_prayers_count`, `reading_streak`.
- **④ Intents:** `spiritual_focus_today` (one faith step today — a reading/prayer) · `faith_progress` (reading consistency, prayer life, plan position) · `faith_consistency` (streak/cadence status) · `spiritual_concerns` (ranked: lapsed plan, long-unanswered prayers, dropped streak).
- **⑤ Curator `faith_working_memory`:** plan names, streaks, prayer counts as coaching language; never raw plan IDs/enums.
- **⑥ Profile:** **supportive, reflective, non-prescriptive** — encourage, never command; never theologize or judge.
- **⑦ Fallback:** rank by (broken streak, lapsed plan, urgent prayers); status from streak + plan position.
- **⑧ Privacy: Tier 3** (faith is intimate — derived signals/encouragement, prayer *text* only on explicit ask).
- **⑨ Validation:** active streak; no plan started (insufficient); reading ahead but prayer lapsed (contradictory); plan abandoned a month ago (stale); prayer data empty (missing).

## Tasks / Execution — config
Canonical: `build_task_state` + `build_execution_state` + `build_routine_state`
(execution selectors are **canonical for "focus right now"**; Rhythm API canonical for
"next" — P24). Intents: `biggest_execution_risk` (most overdue/at-risk) ·
`execution_progress` (consistency, overdue count, completion) · already has rhythm
"next" + daily agenda · `execution_concerns` (ranked overdue/skipped). Curator
`tasks_working_memory`. Profile: practical, momentum-focused. **Tier 1.** *Partly live
via rhythm/agenda — needs the risk/progress/concerns intents.*

## Schedule / Time (calendar + routine) — config
Canonical: `build_calendar_state` + `build_routine_state` + execution contract.
Largely covered by the **Daily Agenda** (live). Add `schedule_concerns` (conflicts,
overbooking). **Tier 1.**

## Projects — config
Canonical: `life.Project` (needs a `build_project_state` — **truth thin today**).
Intents mirror goals. **Defer until a canonical project-state engine exists** (see §11).
**Tier 1.**

## Medical / Labs — config (rich, under-used)
Canonical: `build_medical_state` (abnormal-90d, glycemic labs, metabolic intelligence).
Intents: `lab_concerns` (ranked abnormal results) · `labs_progress` (trends) ·
`biggest_lab_risk`. **Clinical-caution tone: narrate trends, NEVER diagnose** (extend
health tone). **Tier 2.** *Richest under-used truth — high priority.*

## Nutrition / Medication / Fitness / Habits — config
Each has rich canonical SAE state (`build_nutrition_state`, `build_medicine_state`,
`build_fitness_state`, `build_habit_state`). Treat as **health-adjacent sub-domains**:
reuse the health profile/curator patterns; add the quartet where it adds value
(nutrition_concerns, fitness_progress, medication_adherence). **Tier 2** (medication),
**Tier 1–2** (nutrition/fitness/habits).

## Relationships — config
Canonical: `build_relationships_state` (people, neglected, birthdays, cadence). Intents:
`relationship_concerns` (neglected contacts) · `relationship_focus_today` (who to reach
out to). Profile: warm, prompting, never prescriptive. **Tier 2.**

## Journal / Emotional — config
Canonical: `build_journal_state` (mood_avg, mood_trend, stress_score, emotion_counts).
**No `emotional` SAE module — fold into journal or promote.** Intents:
`emotional_progress` (mood/stress trend), `emotional_concerns` (rising stress).
**Tier 3 — derived signals only; journal entry text NEVER exposed ambiently.**

## Capture / Sports / Brain-training / Meals / Scan — config
Thin canonical state. **Facts-only** (e.g. `capture_backlog_count`); reasoning is **low
priority / optional** — see §11 and the "should NOT reason" analysis.

## Documents — config
Canonical: none today (`life.Document`, `medical.MedicalDocument` are orphaned).
**Retrieval, not reasoning:** Beth should *fetch a named document on explicit ask*
(Tier 3, no ambient content). **Do NOT build free-form document reasoning** until a
governance decision; content reasoning is a privacy hazard.

## Career / Learning — config
**No canonical WLJ truth exists** for these as distinct domains. **No reasoning until
truth exists** (see §11). Listed for completeness; explicitly out of scope now.

---

# PART C — §10 CROSS-DOMAIN REASONING ROADMAP

**Principle:** cross-domain answers are composed from **per-domain curated working
memories**, never from raw multi-domain SAE (P3/P11), and always respect a single
**truth precedence** (P24) and the **Personal-Truth-First** gate (P25).

**Architectural approach (future):**
1. **Single-domain first.** Every domain must reach T4 (its own curator + fallback)
   before it participates in cross-domain reasoning. Cross-domain is a *composition
   layer over mature single-domain curators*, not a shortcut around them.
2. **Composer, not concatenation.** A `cross_domain_curator` takes the relevant
   domains' *already-curated* WMs (e.g. health + goals) and composes a bounded,
   executive-clean joint WM. Each input is domain-isolated before composition.
3. **Conflict resolution rules:** when two domains imply opposing actions (e.g. health
   says "rest", goals says "push"), Beth surfaces the *tension explicitly* and defers to
   (a) safety/health > (b) explicit user priority > (c) schedule feasibility — never
   silently picks one.
4. **Truth precedence (P24):** the canonical engine for the *fact in question* wins
   (rhythm for "next", get_next_action for "focus now", health engine for risk). A
   cross-domain answer cites each fact's canonical owner; it never recomputes.

**Candidate cross-domain pairs (value-ordered):**
- **Health + Schedule** ("you have a workout at 7am but you slept 5h") — high value.
- **Health + Goals** ("your weight goal is on pace; protein is the lever").
- **Finance + Goals** ("your savings goal needs $X/mo; you're $Y short").
- **Schedule + Tasks + Projects** ("today is overbooked; defer the low-priority task").
- **Faith + Relationships** ("you mentioned praying for X; their birthday is today").

**Sequencing:** cross-domain is **post-T4-band** work — explicitly *after* the
single-domain roadmap (`BETH_HOLISTIC_TRUTH_ROADMAP.md` Phases 1–4).

---

# PART D — §11 DOMAIN PRIORITIZATION (Impact × Readiness × Risk)

Readiness = canonical state already built. Risk = privacy/tone/regression hazard.

| Domain | Impact | Readiness | Risk | Score | Tier when |
|--------|:------:|:---------:|:----:|-------|-----------|
| **Goals / Purpose** | High | ✅ High | Low | **Immediate** | next after Health |
| **Tasks / Execution (risk/progress/concerns)** | High | ✅ High | Low | **Immediate** | with Goals |
| **Medical / Labs** | High | ✅ High | Med (tone) | **Near-term** | |
| **Finance** | High | ✅ High | Med (privacy) | **Near-term** | after privacy ratification |
| **Faith** | High | ✅ High | Med (intimacy/tone) | **Near-term** | |
| **Nutrition / Medication / Fitness / Habits** | Med | ✅ High | Low | **Mid-term** | health-adjacent reuse |
| **Relationships** | Med | ✅ High | Med | **Mid-term** | |
| **Journal / Emotional** | Med | ◑ (no emotional module) | High (Tier 3) | **Mid-term** | derived signals only |
| **Schedule deepening / Projects** | Med | ◑ thin (projects) | Low | **Mid-term** | needs project-state engine |
| **Documents** | Low–Med | ❌ orphaned | High (privacy) | **Long-term** | retrieval only, not reasoning |
| **Capture / Sports / Brain-training / Meals / Scan** | Low | ◑ thin | Low | **Long-term / opportunistic** | facts-only |
| **Career / Learning** | n/a | ❌ no truth | — | **Excluded** | no canonical truth |

**Recommended immediate next after Health: Goals / Purpose** (highest Impact ×
Readiness, lowest Risk; directly mirrors the validated Health quartet).

---

# §Additional — NEW DOMAIN ONBOARDING CHECKLIST

When adding a future domain, complete (mostly *configuration*, not architecture):

```
[ ] ② Canonical truth source identified (single; P24) — name the build_<domain>_state
       engine; classify feeders as Secondary; confirm no duplicate truth.
[ ] ⑤ Domain curator built — <domain>_working_memory, domain-isolated (P11),
       executive-clean (P3/P10/GB-5): no enums/labels/source paths.
[ ] ③ Foundational facts added — register fast-facts in the fact map (deterministic).
[ ] ④ Reasoning intents defined — the quartet (risk/progress/focus_today/concerns)
       with anti-collapse invariants INV-1…5; register in IMPLEMENTED_INTENTS,
       INTENT_CURATORS, REASONING_PROFILES, INTENT_TRUTH_SCOPE.
[ ] ⑦ Deterministic fallback implemented — per intent; Beth always answers (P5).
[ ] ⑥ Reasoning profile written — style/tone/escalation/safety boundaries.
[ ] ⑧ Privacy classification approved — Tier 1/2/3 + exposure/consent/redaction rules.
[ ] ⑨ Validation scenarios added — ≥5 (happy/insufficient/contradictory/stale/missing).
[ ] Tests created — intent differentiation, no-leak, fallback, no-deflection (GB-5).
[ ] Golden Behaviors reviewed — durability/health-scope/GB-5/P24/P25 unaffected;
       Blast Radius Assessment per BETH_CHANGE_CONTROL.
[ ] Shipped one domain at a time, validated, stable-tagged.
```

A domain that completes this checklist is **T4**. If every "Beth should know it"
domain reaches T4, the Truth-Parity principle is satisfied.

---

# COMPLETION ANALYSIS

### 1. Major findings
- The reasoning *mechanism* is already general (planner → curator → profile →
  fallback registries). Adding a domain is **registry configuration**, not new
  architecture — exactly the framework goal. Health proves the pattern end-to-end.
- The **canonical quartet** (risk / progress / focus_today / concerns) + the **INV-1…5
  anti-collapse invariants** generalize cleanly to every domain — they are the reusable
  intent contract.
- The **curator is the single most important reusable contract** — it is where P3/P10/
  P11 safety lives; every domain must isolate truth and strip internals identically.
- The biggest cross-cutting requirement is **privacy tiering** (Tier 2 finance/health,
  Tier 3 emotional/journal/documents) — it must be decided *before* a domain's curator
  is built, not after.

### 2. Highest-ROI domain after Health
**Goals / Purpose.** Highest Impact × Readiness, lowest Risk: rich canonical state
(`build_goal_state`/`build_habit_state`) already exists, it's already on the dashboard
and in briefings/proactive, it's Tier 1 (no privacy gate), and it maps 1:1 onto the
validated Health quartet — so it's almost pure configuration.

### 3. Domains that should NOT receive reasoning capabilities (now)
- **Career, Learning** — **no canonical WLJ truth exists**; reasoning would fabricate.
  Excluded until a data source exists.
- **Documents** — **retrieval only, never free-form reasoning** over content (Tier 3
  privacy hazard); Beth fetches a named document on explicit ask, nothing ambient.
- **Capture, Sports, Brain-training, Meals, Scan** — too thin / low CoS value for
  reasoning; **facts-only** (a count or status), not the quartet.
- **`faith.journey`** — a dead registry reference; **delete**, do not build.

### 4. Recommended first implementation phase (after approval)
**Phase G1 — Goals reasoning + non-health foundational facts**, step-gated under
`BETH_CHANGE_CONTROL`:
1. Register the four Goals intents (`biggest_goal_risk`, `goals_progress`,
   `goals_focus_today`, `goal_conflicts`) with a `goals_working_memory` curator +
   deterministic fallbacks, scoped to goal/habit truth only.
2. Add the cheap deterministic foundational facts (goals + a few finance/faith/exec)
   from existing SAE state.
3. Anti-collapse + no-leak + no-deflection tests; §9 validation scenarios; ship,
   validate in production, and fold into the `beth-stable-v3` milestone (alongside P25
   activation), each behind its own validation gate.

---

**No code, no implementation — framework specification and analysis only.** Health
remains the reference implementation; every future domain is now a checklist, not a
redesign. Stopping after documentation and analysis.
