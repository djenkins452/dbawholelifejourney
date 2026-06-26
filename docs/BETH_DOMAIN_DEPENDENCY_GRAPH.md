# Beth Domain Dependency Graph & Ownership Model

> **The authoritative map of which domain owns which questions, which domains depend
> on which, and who has final authority when they overlap.** Required reference for
> all future domain reasoning work. Documentation/architecture only — no code.
> Governed by P24 (Canonical Truth), P25 (Personal Truth First),
> `BETH_DOMAIN_REASONING_FRAMEWORK.md`, `BETH_TRUTH_COVERAGE_AUDIT.md`,
> `BETH_ARCHITECTURAL_PRINCIPLES.md`, `BETH_GOLDEN_BEHAVIORS.md`.
> **Date:** 2026-06-26

## Why this exists
Before more reasoning domains ship, ownership must be explicit — otherwise we get
duplicate engines, conflicting answers, overlapping ownership, competing truth, and
drift. This document is the contract that prevents all five.

**Core rule:** every user fact has **exactly one owning domain** and **exactly one
canonical engine** (P24). Cross-domain answers **compose mature domain outputs**, never
raw SAE truth (P3/P11). A meta-domain — **Executive (Chief-of-Staff)** — owns
cross-domain synthesis; it has no truth of its own.

---

# Part 1 — Domain Inventory

| Domain | Purpose | Canonical owner (engine) | Maturity | Privacy |
|--------|---------|--------------------------|:--------:|:-------:|
| **Health** | vitals/weight/glucose/sleep trajectory | `build_health_state` | T4 | Tier 2 |
| **Nutrition** | calories/protein/macros/intake | `build_nutrition_state` | T3 | Tier 2 |
| **Medications** | meds/supplements/adherence | `build_medicine_state` | T3 | Tier 2 |
| **Exercise / Fitness** | workouts/volume/PRs/load | `build_fitness_state` | T2 | Tier 2 |
| **Medical / Labs** | lab results/panels/abnormals | `build_medical_state` | T2 | Tier 2 |
| **Goals / Purpose** | life goals/milestones/mission | `build_goal_state` | T3 | Tier 1 |
| **Habits** | habit streaks/consistency | `build_habit_state` | T3 | Tier 1 |
| **Tasks / Execution** | tasks/non-negotiables/execution state | `build_task_state` + `build_execution_state` | T3 | Tier 1 |
| **Schedule / Time** | calendar/routines/today's rhythm | `build_today_execution` + `build_calendar_state` + `build_routine_state` | T3 | Tier 1 |
| **Projects** | multi-step initiatives | *(needs `build_project_state` — thin)* | T1 | Tier 1 |
| **Faith** | prayer/reading/verses/journey | `build_faith_state` | T3 | Tier 3 |
| **Relationships** | people/neglect/birthdays/cadence | `build_relationships_state` | T3 | Tier 2 |
| **Finance** | accounts/transactions/budgets/goals | `build_finance_state` | T3 | Tier 2 |
| **Journal** | entries/frequency | `build_journal_state` | T3 | Tier 3 |
| **Emotional / Mood** | mood/stress signals | *(folded into journal; no module)* | T0 | Tier 3 |
| **Capture** | inbox/backlog pressure | `build_capture_state` | T2 | Tier 1 |
| **Sports** | teams/games/storylines | `build_sports_state` | T2 | Tier 1 |
| **Brain Training** | cognitive game stats | `build_brain_training_state` | T1 | Tier 1 |
| **Meals / Pantry** | pantry/meal-plan | `build_meals_state` | T1 | Tier 2 |
| **Documents** | uploaded files (life + medical) | *(none — orphaned)* | T0 | Tier 3 |
| **Scan** | image analyses | `build_scan_state` | T1 | Tier 2 |
| **Life events** | significant events/birthdays | `build_life_events_state` | T1 | Tier 2 |
| **Executive (Chief-of-Staff)** *(meta)* | cross-domain synthesis & prioritization | `build_executive_summary` + `build_daily_agenda` (composers) | n/a | inherits |
| **Career / Learning** | — | **no canonical truth** | excluded | — |

---

# Part 2 — Dependency Graph

**Direction:** A → B means *A consumes B's truth*. Lower-level domains are leaves;
Goals and Executive are the high-level consumers.

```
                     Executive (Chief-of-Staff)  [composes mature domain OUTPUTS only]
                       ├── Goals ────────┐
                       ├── Schedule ──┐   │
                       ├── Health     │   │
                       ├── Finance    │   │
                       ├── Faith      │   │
                       └── Relationships  │
   Goals ── consumes ──> Tasks, Projects, Habits, Schedule
   Schedule ── consumes ──> Tasks, Routines, Calendar, Medications, Exercise, Faith(reading)
   Health ── consumes ──> Sleep, Nutrition, Exercise, Labs, Medications
   Finance ── consumes ──> Transactions, Bills/Recurring, Budgets
   Tasks/Execution ── consumes ──> Tasks, Routines, Non-negotiables
   (leaves: Journal, Emotional, Relationships, Sports, Capture, Brain-training, Scan,
    Meals, Documents — minimal upstream deps)
```

### Upstream-dependency table

| Domain | Upstream truth it consumes |
|--------|----------------------------|
| **Goals / Purpose** | Tasks, Projects, Habits, Schedule (goal progress is *derived* from task/habit/milestone completion) |
| **Health** | Sleep, Nutrition, Exercise, Labs, Medications (these are health sub-domains feeding the health state) |
| **Finance** | Transactions, Recurring bills, Budgets |
| **Schedule / Time** | Tasks, Routines, Calendar, Medications (doses), Exercise (workouts), Faith (reading) → the rhythm contract |
| **Tasks / Execution** | Tasks, Routines, Non-negotiables |
| **Nutrition / Medications / Exercise / Labs** | raw health logs (leaf feeders into Health) |
| **Executive (meta)** | **ALL mature domain OUTPUTS** (Goals, Health, Schedule, Finance, Faith, Relationships, …) — never raw SAE |
| **Faith, Relationships, Journal, Emotional, Capture, Sports, Brain-training, Meals, Scan, Documents** | mostly self-contained (own raw data) |

**Key derived-vs-canonical note (P24):** Goals' "progress" is *derived* from Tasks/
Habits but Goals is still the **canonical owner of goal questions** — it consumes the
leaves and publishes the canonical goal verdict. Leaves must never publish a
goal-level answer.

---

# Part 3 — Ownership Boundaries

Each domain owns its **canonical quartet** (`biggest_<d>_risk · <d>_progress ·
<d>_focus_today · <d>_concerns`) and the facts in its column. Below: what each owns,
and — critically — what it **MUST NOT** answer.

| Domain | OWNS | MUST NOT answer (owner in parens) |
|--------|------|-----------------------------------|
| **Health** | biggest health risk, health progress, health focus, health concerns; vitals/sleep/glucose facts | overall life progress (Goals); "what's next on my schedule" (Schedule) |
| **Goals / Purpose** | overall life progress ("am I on track"), strategic priority ("what matters most"), goal risk/conflicts, "what should I focus on [strategically]" | the literal "what's next/now" (Schedule); domain-specific risk like health/finance risk (those domains) |
| **Schedule / Time** | "what's next", "what's coming up today", today's agenda/rhythm, next scheduled item, conflicts in the day | "am I on track overall" (Goals); "what should I focus on strategically" (Goals) |
| **Tasks / Execution** | task-level status, overdue tasks, non-negotiable streaks, "what to do right now (urgency)" | "how am I doing overall" (Goals); "what's my mission" (Goals) |
| **Projects** | project status, blocked steps, project risk | "what should I focus on today" (Goals owns prioritization); "what's next on my calendar" (Schedule) |
| **Finance** | financial risk, spending concerns, financial progress, budget/runway | health/goal questions; cross-domain "am I on track in life" (Goals/Executive) |
| **Faith** | spiritual focus, faith progress/consistency, prayer/reading concerns | non-faith prioritization (Goals); "what's next on my schedule" (Schedule) |
| **Relationships** | who to reach out to, relationship concerns, birthdays/neglect | scheduling the reach-out (Schedule); life priority (Goals) |
| **Nutrition / Medications / Exercise / Labs** | their own metric questions (feeders) | "biggest *health* risk" (Health composes them); overall progress (Goals) |
| **Journal / Emotional** | mood/stress trend, emotional concerns | clinical/health risk (Health); life priority (Goals) |
| **Executive (meta)** | cross-domain "give me my brief", "how am I doing across everything", multi-domain conflicts | any single-domain canonical fact (it must *cite* the owning domain, not recompute) |
| **Capture / Sports / Brain-training / Meals / Scan** | facts-only (counts/status) | any reasoning/prioritization (not reasoning domains — see findings) |
| **Documents** | *retrieval only* — "find/show document X" | any reasoning over content (privacy; not a reasoning domain) |

**Canonical examples of the boundary rule (from the prompt):**
- *Projects MUST NOT answer "what should I focus on today?"* → **Goals** owns prioritization.
- *Tasks MUST NOT answer "how am I doing overall?"* → **Goals** owns overall progress.
- *Nutrition MUST NOT answer "what's my biggest health risk?"* → **Health** composes nutrition into its risk.
- *Finance MUST NOT answer "am I on track in life?"* → **Goals/Executive**.

---

# Part 4 — Authority Hierarchy (precedence when domains overlap)

When two domains could answer, precedence resolves it. **P24 always wins: canonical
truth > derived truth.** Beyond that:

### Global precedence ladder (highest first)
1. **Safety / Health** > everything. (A health-risk signal can veto a goal/schedule push.)
2. **Explicit user commitment** (Non-negotiable, scheduled event, stated priority) > **inferred priority**.
3. **Canonical truth (P24)** > derived/composite truth. (`build_goal_state` > `build_transformation_state` for a goal fact.)
4. **Specific-domain owner** > **Executive meta**. (A health question is answered by Health, not by the cross-domain composer.)
5. **Tactical "next/now"** → **Schedule/Execution**; **strategic "should/priority/overall"** → **Goals**; **"everything/brief"** → **Executive**.

### Overlap resolution table
| Overlap | Primary authority | Secondary | Tie-break |
|---------|-------------------|-----------|-----------|
| Schedule vs Goals | **Schedule** for "what's next/today"; **Goals** for "what matters" | the other as context | tactical→Schedule, strategic→Goals |
| Health vs Goals | **Health** for the risk; **Goals** for whether it endangers a goal | — | Safety > Goal priority |
| Finance vs Goals | **Finance** for the money fact; **Goals** for goal impact | — | canonical money fact (Finance) is cited, Goals interprets |
| Tasks vs Projects | **Tasks** for the action; **Projects** for the initiative status | — | a task belongs to its project; project-level rollup = Projects |
| Goals vs Executive | **Goals** for goal questions; **Executive** only when ≥2 domains are in the question | — | single-domain → owner; multi-domain → Executive |
| Nutrition/Meds/Exercise vs Health | **Health** owns the composed risk; sub-domain owns its metric | — | Health composes; sub-domain feeds |

**Invariant:** no two domains may publish the *same* user fact. If they appear to, one
is the canonical owner and the other consumes it (P24). Beth and the Dashboard must
never disagree (the rhythm-vs-`get_next_action` lesson).

---

# Part 5 — Cross-Domain Composition Rules

**Rule 0 (absolute):** cross-domain reasoning consumes **mature domain curated
outputs** (each domain's working memory), **never raw SAE** (P3/P11). A domain must be
**T4** before it can participate.

**Composition strategy:**
1. **Resolve participants** — the question names ≥2 domains (or the Executive intent).
2. **Fetch each domain's curated WM** (already domain-isolated & sanitized).
3. **Compose** a bounded joint WM via a `cross_domain_curator` (executive-clean; no
   internals leak across the seam).
4. **Apply the authority ladder** (Part 4) to order/weight the domains.
5. **Surface tension explicitly** when domains conflict — never silently pick one.

**Orchestration order:** Safety/Health signals evaluated first (they can veto) →
explicit commitments → canonical facts → derived synthesis. The Executive composer
**cites each fact's owning domain** (P24 traceability).

**Conflict-resolution & escalation:**
- *Health says rest, Goals says push* → present the tension; default to Safety > Goal.
- *Schedule says no time, Goals says do X* → surface the feasibility conflict; suggest a trade-off, don't fabricate time.
- *Two canonical facts disagree* → that's a **truth bug** (P24 violation), not a reasoning choice — escalate/flag, never paper over.

**Candidate pairs (value-ordered):** Health+Schedule · Goals+Schedule · Goals+Health ·
Finance+Goals · Faith+Relationships · Schedule+Tasks+Projects.

---

# Part 6 — Chief-of-Staff Ownership Map (routing contract for P25)

**The authoritative `question → owning domain` table.** This *is* the P25 PERSONAL
dispatch contract. (Domains: H=Health, G=Goals, S=Schedule, T=Tasks, P=Projects,
Fin=Finance, Fa=Faith, R=Relationships, N=Nutrition, M=Medications, Ex=Exercise,
L=Labs, J=Journal/Emotional, X=Executive, Cap=Capture, ext=External, clar=Ambiguous.)

| # | User question | Owner |
|---|---------------|-------|
| 1 | What should I do today? | **S** (agenda) → X if multi-domain |
| 2 | What's next? / What's my next activity? | **S** |
| 3 | What's coming up today? | **S** |
| 4 | Am I on track? | **G** |
| 5 | How am I doing overall? | **G** |
| 6 | What should I focus on? (strategic) | **G** |
| 7 | What matters most right now? | **G** |
| 8 | What priorities conflict? | **G** |
| 9 | What goal is at risk? | **G** |
| 10 | How are my goals tracking? | **G** |
| 11 | What goals are overdue? | **G** |
| 12 | When's my next goal deadline? | **G** |
| 13 | What's my top goal? | **G** |
| 14 | What's my biggest health risk? | **H** |
| 15 | How's my health progress? | **H** |
| 16 | What should I focus on health-wise today? | **H** |
| 17 | What are my health concerns? | **H** |
| 18 | What's my weight? | **H** |
| 19 | What's my latest glucose? | **H** |
| 20 | How did I sleep? | **H** |
| 21 | What's my blood pressure? | **H** |
| 22 | How many calories today? | **N** |
| 23 | How much protein today? | **N** |
| 24 | Am I hitting my macros? | **N** |
| 25 | What did I eat today? | **N** |
| 26 | Did I take my meds? | **M** |
| 27 | What's my medication adherence? | **M** |
| 28 | When's my next dose? | **M** (via S rhythm) |
| 29 | What workout is scheduled? | **S** (Ex content) |
| 30 | How's my training going? | **Ex** |
| 31 | What are my recent PRs? | **Ex** |
| 32 | What do my labs say? | **L** |
| 33 | Any abnormal lab results? | **L** |
| 34 | How am I doing financially? | **Fin** |
| 35 | What's my biggest financial risk? | **Fin** |
| 36 | Am I overspending? | **Fin** |
| 37 | What's my net worth? | **Fin** |
| 38 | What's my largest expense category? | **Fin** |
| 39 | What's my savings rate? | **Fin** |
| 40 | When's my next bill? | **Fin** |
| 41 | Am I on pace for my savings goal? | **Fin** (+G context) |
| 42 | How's my walk with God? | **Fa** |
| 43 | What's my reading plan today? | **Fa** |
| 44 | What's my prayer streak? | **Fa** |
| 45 | What should I focus on spiritually? | **Fa** |
| 46 | Any prayers I've been carrying a while? | **Fa** |
| 47 | Who should I reach out to? | **R** |
| 48 | Whose birthday is coming up? | **R** |
| 49 | Who have I been neglecting? | **R** |
| 50 | What's overdue? | **T** |
| 51 | What tasks are due today? | **T** |
| 52 | What should I do right now? (urgency) | **T/S** (focus-now) |
| 53 | Am I keeping my non-negotiables? | **T** |
| 54 | How's [project X] going? | **P** |
| 55 | What's blocking [project]? | **P** |
| 56 | What's on my calendar tomorrow? | **S** |
| 57 | Am I overbooked today? | **S** |
| 58 | How have I been feeling? | **J** |
| 59 | Has my stress been rising? | **J** |
| 60 | How consistent has my journaling been? | **J** |
| 61 | What's in my capture inbox? | **Cap** (fact) |
| 62 | Give me my morning brief / check-in | **X** |
| 63 | How am I doing across everything? | **X** |
| 64 | What's the one thing today? | **X** (composes G+S) |
| 65 | What's my biggest risk anywhere? | **X** |
| 66 | Health vs my goals — am I balancing? | **X** (H+G) |
| 67 | Can I fit a workout in today? | **X** (S+Ex) |
| 68 | Is my spending hurting my goals? | **X** (Fin+G) |
| 69 | Show me [document name] | **Documents** (retrieval) |
| 70 | What's my biggest goal risk? | **G** |
| 71 | What's my health focus this week? | **H** |
| 72 | What habit am I about to break? | **Habits** |
| 73 | What's my longest current streak? | **Habits** |
| 74 | What should I prep for tomorrow? | **S** |
| 75 | What did I accomplish today? | **T** |
| 76 | Am I behind on anything? | **G** (overall) |
| 77 | What's my mission? | **G** |
| 78 | How's my glucose trending? | **H** |
| 79 | Is my weight loss on pace? | **H** (+G context) |
| 80 | What's my budget status this month? | **Fin** |
| 81 | Any subscriptions I'm wasting money on? | **Fin** |
| 82 | What's my next prayer reminder? | **S** (Fa content) |
| 83 | How's my Bible reading consistency? | **Fa** |
| 84 | Who haven't I talked to in a while? | **R** |
| 85 | What's my busiest day this week? | **S** |
| 86 | What should I deprioritize? | **G** |
| 87 | What's slipping? | **G** |
| 88 | What's my recovery looking like? | **H** |
| 89 | How many workouts this week? | **Ex** |
| 90 | What's my fasting window status? | **N** |
| 91 | What's my water intake today? | **H/N** |
| 92 | What's my biggest spending concern? | **Fin** |
| 93 | Am I on track with my faith goals? | **G** (faith goal) or **Fa** |
| 94 | What's the weather today? | **ext** |
| 95 | Who was Abraham Lincoln? | **ext** |
| 96 | Explain photosynthesis | **ext** |
| 97 | Should I eat fruit? | **MIXED** (N + ext) |
| 98 | What's the best exercise for me? | **MIXED** (Ex + ext) |
| 99 | Check in | **clar** → X (daily brief) |
| 100 | Help me | **clar** |
| 101 | Review this | **clar** |
| 102 | What should I do? (no context) | **clar** |
| 103 | How am I doing with my health goals? | **H** |
| 104 | What's my next lab appointment? | **S** (L/Medical content) |
| 105 | What's draining my energy? | **X** (J+H+S) |

(Representative; the registry-keyed ownership table is extended as domains mature.)

---

# Part 7 — P25 Alignment

The ownership map plugs directly into the P25 gate as the **PERSONAL dispatch table**:

```
classify_request(request)            (P25 gate — deterministic-first)
  PERSONAL  → ownership lookup (Part 6) → domain curator → domain reasoning → answer
                 ├─ single domain  → that domain's curator + quartet intent
                 └─ multi domain   → Executive composer over mature domain outputs (Part 5)
  MIXED     → personal-truth (owning domain curator) GROUNDS a general answer
  AMBIGUOUS → clarification (the "check in / help / review" lane)
  EXTERNAL  → general conversation (no domain, no truth)
```

- **PERSONAL** routing is a two-step: (1) is it personal? (P25 classifier); (2) *which
  domain owns it?* (this document). Step 2 replaces ad-hoc lane heuristics with the
  explicit ownership table — the same "explicit, not order-encoded" discipline P25
  established.
- **MIXED** ("should I eat fruit") = the owning domain (Nutrition) provides grounding
  truth; the general lane supplies external knowledge; **personal truth first** (P25.5).
- **AMBIGUOUS** ("check in") = clarification, which on resolution dispatches into the
  Executive daily brief (already live).
- **Executive** is the PERSONAL multi-domain branch; it never bypasses P24 (cites each
  owning domain's canonical fact).
- This map is the contract that keeps P25 routing deterministic and non-duplicative as
  domains are added — **adding a domain = adding rows here + a curator**, not new routing.

---

# Part 8 — Future Domain Sequencing (Impact × Readiness × Dependency)

Prerequisite rule: **a domain ships only after the domains it depends on are mature
enough to feed it**, and a domain must be **T4 before it joins cross-domain**.

| Order | Domain | Prerequisites | Why here |
|------:|--------|---------------|----------|
| 1 | **Goals / Purpose** | Tasks/Habits canonical (✅ exist) | highest impact; consumes existing leaves; reference-pattern fit |
| 2 | **Tasks / Execution reasoning** | execution engine (✅) | feeds Goals; tactical layer |
| 3 | **Schedule deepening** | rhythm/agenda (✅ live) | tactical "next/today" already strong; add conflict reasoning |
| 4 | **Health sub-domains** (Nutrition, Medications, Exercise) reasoning | Health (✅ T4) | mature *before* Health cross-domain |
| 5 | **Medical / Labs** | medical state (✅) | richest under-used; clinical-tone gate |
| 6 | **Finance** | finance state (✅) + privacy ratification | high value; needs Tier-2 gate |
| 7 | **Faith** | faith state (✅) | high value; Tier-3 tone gate |
| 8 | **Relationships, Journal/Emotional** | states (✅/◑) | mid; emotional needs a module decision |
| 9 | **Projects** | **needs `build_project_state`** | blocked until a canonical project engine exists |
| 10 | **Cross-domain** (Executive deepening) | ≥4 domains at T4 | only after the single-domain band matures |
| — | Career/Learning | **no truth** | excluded until data exists |

**Hard sequencing facts:** *Goals before Projects* (Projects lacks a canonical engine
and Goals owns prioritization). *Goals before Tasks-reasoning* is **not** required —
Tasks feeds Goals, so Tasks/Execution reasoning is a peer/feeder; but Goals must own
the *overall* verdict. *Health sub-domains before Health cross-domain.*

---

# Part 9 — Architectural Risks & Mitigations

| Risk | Description | Mitigation |
|------|-------------|------------|
| **Duplicate ownership** | two domains answer the same question (e.g. Goals & Executive both claim "what should I do today") | this ownership table is authoritative; single-domain → owner, multi-domain → Executive; onboarding checklist enforces |
| **Conflicting truth** | two engines compute the same fact differently (the rhythm-vs-`get_next_action` defect) | P24 single-canonical-owner per fact; cross-domain *cites* owners, never recomputes; a canonical-source test per fact |
| **Privacy leakage** | Tier-2/3 raw data (finance ledgers, journal text, labs, documents) reaching OpenAI | curator contract (P3/P10) + privacy tiers; raw detail explicit-ask only; redaction/banding |
| **Orchestration drift** | cross-domain composer bypasses curators and reads raw SAE | Rule 0: compose mature outputs only; lint/test that cross-domain consumes curated WM |
| **Performance** | composing many domains on the request path (the P15 hazard) | compose from pre-computed canonical state in the background task; never live-recompute on the HTTP path; cache; "pending" over live-compute |
| **Boundary erosion** | a feeder domain (Nutrition) starts answering composed (Health) questions | "MUST NOT answer" lists; tests assert feeders don't publish owner-level answers |
| **Authority ambiguity** | overlap with no defined precedence | Part 4 ladder is exhaustive for known overlaps; new overlaps require a ratified precedence entry before shipping |

---

# Required Findings

1. **Single most important domain after Health:** **Goals / Purpose.** It owns
   overall progress and strategic prioritization (the executive spine), has rich
   canonical state, is Tier 1 (no privacy gate), and every cross-domain answer leans on
   it. It is also the prerequisite consumer for Projects and the Executive layer.

2. **Domains that should NEVER own prioritization:** **Projects, Tasks, Schedule,
   Finance, Health, Faith, Nutrition, and all feeders.** Prioritization across life is
   **Goals** (strategic) and the **Executive** meta (cross-domain) only. Tactical
   "what's next/now" is **Schedule/Execution** — that is *sequencing*, not
   *prioritization*. (Projects must not answer "what should I focus on today"; Tasks
   must not answer "how am I doing overall.")

3. **Domains that must NEVER expose raw truth to OpenAI:** all **Tier-2** (Health,
   Finance, Medical/Labs, Medications, Nutrition, Exercise, Relationships) and
   **Tier-3** (Journal, Emotional, Faith, Documents). These pass only **curated,
   sanitized, banded summaries**; **Documents and journal/emotional entry text are
   never ambient** (explicit retrieval only). Tier-1 (Goals, Tasks, Schedule, Habits)
   may pass curated WM freely — but still no enums/labels/source paths (P3/P10/GB-5).

4. **Minimum domain set before cross-domain reasoning begins:** at least **four T4
   domains** that cover the executive spine — **Health (✅), Goals, Schedule, and one
   of {Tasks, Finance}**. Cross-domain composes mature outputs, so it cannot start
   until its inputs are mature; Health alone is insufficient.

5. **Recommended first cross-domain composition pair:** **Health + Schedule** —
   highest everyday CoS value ("you have a 7am workout but only slept 5h"), both are the
   most mature (Health T4; Schedule strong via rhythm/agenda), low privacy complexity,
   and a clean safety-precedence demonstration (Health can temper the schedule). It is
   the ideal first proof of the composition rules.

---

**No code, no implementation — dependency graph, ownership model, and analysis only.**
This document is now the required reference for all future domain reasoning work; P24
and P25 remain authoritative; Health remains the reference implementation; cross-domain
reasoning operates over mature domain outputs, never raw truth. Stopping after
documentation and analysis.
