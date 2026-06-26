# Beth Truth Coverage Audit

> **Comprehensive audit of every source of Danny's user truth in WLJ and whether
> Beth can access, reason over, and use it.** Read-only architecture audit — no
> code changes. Companion docs: `BETH_TRUTH_GAP_ANALYSIS.md`,
> `BETH_HOLISTIC_TRUTH_ROADMAP.md`, `BETH_DOMAIN_MATURITY_MATRIX.md`.
> Governing principle (P-candidate): *"If WLJ knows it about Danny, Beth should
> know it too unless there is an explicit architectural reason she should not."*
> **Date:** 2026-06-26

## Method & scope

- **462 Django models** across 21 WLJ apps (introspected). Infrastructure/audit/
  cache/log/snapshot/scheduler/engine-telemetry tables excluded.
- The truth pipeline traced per domain:
  **storage (models) → SAE canonical state (`get_module_state`) → executive
  briefing / standing context → foundational facts → reasoning lane → Beth read
  access (tools / dashboard).**
- Source maps: SAE `MODULE_BUILDERS` (`apps/core/ai_state/state_builder.py:5576`),
  Beth read surface (`apps/ai/cos_services/*`), reasoning vocab
  (`apps/ai/chatgpt_cos/reasoning/plan.py`, `stages.py`), dashboard
  (`apps/dashboard_v3/services/composer.py`), briefing
  (`apps/core/cos_briefing/executive_summary.py`), proactive
  (`apps/ai/proactive_checkins.py`), rhythm
  (`apps/core/execution/today_execution.py`).

## Headline finding

WLJ's **canonical state layer (SAE) is broad** — ~24 module builders, rich state
for ~18 domains. Beth's **read access is good** (~11 domains via tools/standing/
history). But Beth's **deliberate reasoning lane is HEALTH-ONLY** (4 intents,
`INTENT_TRUTH_SCOPE = HEALTH_TRUTH`). So for every non-health domain, Beth can
*read summaries and answer via the demoted tool loop*, but cannot *reason* the way
she does for health. **The gap is not storage or canonical state — it is the
reasoning + briefing + facts surface.**

## Master coverage table

Stages: **Store**=user truth exists · **SAE**=canonical module state · **Dash**=on
dashboard · **Fact**=foundational fast-fact · **Brief**=executive summary/standing ·
**Proact**=proactive check-in · **Reason**=deliberate reasoning lane · **Read**=Beth
can read (tool/state/history).  ✅ full · ◑ partial/summary-only · ❌ none.

| Domain | Store | SAE | Dash | Fact | Brief | Proact | Reason | Read | Should Beth know? |
|--------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| **Health (vitals/weight/glucose/sleep)** | ✅ | ✅ rich | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | **Yes — fully covered** |
| **Nutrition (cal/protein/macros)** | ✅ | ✅ rich | ✅ | ✅ | ◑ | ◑ | ❌ | ✅ | Yes |
| **Medication / supplements** | ✅ | ✅ rich | ✅ | ✅ (meds) | ✅ adherence | ✅ | ❌ | ✅ | Yes |
| **Fitness / workouts / PRs** | ✅ | ✅ rich | ◑ | ❌ | ◑ | ✅ workout | ❌* | ✅ | Yes |
| **Medical / labs** | ✅ | ✅ rich | ◑ | ❌ | ◑ | ❌ | ❌ | ◑ tool | **Yes — under-surfaced** |
| **Faith (prayer/reading/verses)** | ✅ | ✅ rich | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ +write | Yes |
| **Goals / purpose** | ✅ | ✅ rich | ✅ mission | ❌ | ✅ | ✅ | ❌* | ✅ +write | Yes |
| **Habits** | ✅ | ✅ rich | ✅ | ❌ | ◑ | ✅ | ❌ | ✅ | Yes |
| **Tasks / execution / routines / calendar** | ✅ | ✅ rich | ✅ rhythm | ❌ | ✅ | ✅ | ◑ exec | ✅ +write | Yes |
| **Journal** | ✅ | ✅ rich | ◑ card | ❌ | ◑ insights | ✅ | ❌ | ✅ +write | Yes |
| **Emotional state** | ✅ (Emotion) | ❌ (via journal) | ❌ | ❌ | ◑ mood | ❌ | ❌ | ◑ | **Yes — orphaned** |
| **Finance** | ✅ | ✅ rich | ◑ card | ❌ | ◑ insights | ✅ | ❌ | ✅ | Yes (with privacy gate) |
| **Relationships / people** | ✅ | ✅ rich | ◑ card | ❌ | ◑ | ✅ drift/bday | ❌ | ✅ | Yes |
| **Sports (teams/games)** | ✅ | ✅ rich | ❌ | ❌ | ❌ | ❌ | ❌ | ◑ tool +write | Maybe (low stakes) |
| **Brain training** | ✅ | ◑ thin | ❌ | ❌ | ❌ | ❌ | ❌ | ◑ tool | Maybe |
| **Capture (inbox)** | ✅ | ◑ thin | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | Yes (backlog pressure) |
| **Meals / pantry** | ✅ | ◑ thin | ❌ | ❌ | ❌ | ❌ | ❌ | ◑ tool | Low |
| **Documents (life + medical)** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | **Yes — orphaned** |
| **Life misc (pets, inventory, recipes, shopping, events)** | ✅ | ◑ life_events only | ❌ | ❌ | ◑ events | ✅ bday/event | ❌ | ◑ | Partial |
| **Scan / camera analyses** | ✅ | ◑ thin | ❌ | ❌ | ❌ | ❌ | ❌ | ◑ | Low |

\* `fitness`/`goals` are in the reasoning planner's `ALLOWED_DOMAINS` vocabulary but
**no intent is implemented**, so they are never actually retrieved/reasoned over
(`IMPLEMENTED_INTENTS` = the 4 health intents only).

## The eight questions, answered per domain (summary)

For every domain the audit answers: (1) what truth exists, (2) where stored, (3) is
it canonical, (4) on dashboard, (5) available to Beth, (6) can Beth reason over it,
(7) can Beth include it in check-ins/briefings, (8) should Beth know it. The table
above encodes (3)–(8); (1)–(2) per domain:

- **Health** — vitals/weight/glucose/sleep/steps/HR/O2/BP/water/cycle/body-comp;
  `apps/health/models.py` (53 models) + `DailyHealthSummary`. Canonical: SAE
  `build_health_state`. Reason: ✅ (only domain).
- **Nutrition** — `FoodEntry`, `DailyNutritionSummary`, `NutritionGoals`. Canonical:
  `build_nutrition_state`. Reason: ❌ (read-only via foundational facts + state).
- **Medication** — `Intake`/`IntakeLog`/`IntakeSchedule`. Canonical:
  `build_medicine_state` (adherence/refills). Reason: ❌; surfaced via meds fact +
  adherence in standing context + proactive check-ins.
- **Fitness** — `WorkoutPlan`, `Exercise`, `PersonalRecord`, `StepsEntry`. Canonical:
  `build_fitness_state` (rich: volume, training-load, PRs). Reason: ❌.
- **Medical/labs** — `apps/medical` (`LabResult`, `LabPanel`, `MedicalDocument`).
  Canonical: `build_medical_state` (rich: abnormal-90d, glycemic labs). Reason: ❌;
  only meds reach foundational facts → **richest under-used truth.**
- **Faith** — `apps/faith` (prayer/reading/verses/milestones). Canonical:
  `build_faith_state`. Reason: ❌; ✅ briefing + proactive + write.
- **Goals/Purpose** — `apps/purpose` (`LifeGoal`, `GoalMilestone`, `HabitGoal`,
  `AnnualDirection`). Canonical: `build_goal_state`/`build_habit_state`. Reason: ❌.
- **Tasks/Execution** — `apps/life` (`Task`, `Routine`, `Project`, calendar) →
  `build_today_execution` → rhythm. Canonical: `build_task_state`/`build_routine_state`/
  `build_execution_state`. Reason: ◑ (execution selectors feed rhythm/next-action).
- **Journal/Emotional** — `apps/journal` (`JournalEntry`, `Emotion`). Canonical:
  `build_journal_state` (mood/stress); **no emotional module** (emotion is a journal
  property). Reason: ❌.
- **Finance** — `apps/finance` (`Transaction`, `FinancialAccount`, `Budget`,
  `FinancialGoal`). Canonical: `build_finance_state` (net-worth, budgets, pressure).
  Reason: ❌; ✅ proactive + card.
- **Relationships** — `build_relationships_state` (people, neglect, birthdays).
  Reason: ❌; ✅ proactive (drift/birthday).
- **Sports/Brain-training/Capture/Meals/Scan** — SAE thin-to-rich, Beth read via
  tool only, no briefing/reasoning.
- **Documents** — `life.Document`, `medical.MedicalDocument`: **no SAE, no Beth
  access at all (orphaned).**

## Pipeline integrity notes (P24-relevant)

- **Canonical alignment is largely sound:** SAE is a read-only consumer of nightly
  summaries (`DailyHealthSummary`, `DailyNutritionSummary`); the rhythm/next-action
  the dashboard and Beth use derive from the same `build_today_execution` contract
  (the P24 fix). Glucose has an intentional multi-representation (latest vs 7d vs
  projected A1c) to prevent the "last reading = average" confusion.
- **No problematic duplicate truth engines** were found — the apparent duplicates
  (DHS/SAE, DNS/SAE) are layered consumer relationships, not divergent computations.
  See `BETH_TRUTH_GAP_ANALYSIS.md` for the one residual risk (selector-vs-rhythm
  "next", already addressed by the canonical Rhythm API).

*Coverage detail and scoring continue in `BETH_DOMAIN_MATURITY_MATRIX.md`; gaps and
remediation in `BETH_TRUTH_GAP_ANALYSIS.md`; sequencing in `BETH_HOLISTIC_TRUTH_ROADMAP.md`.*
