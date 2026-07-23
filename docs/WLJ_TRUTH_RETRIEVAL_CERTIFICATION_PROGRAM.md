# WLJ Truth Retrieval Certification — Program & Runtime Evidence

**Status:** Investigation + program design COMPLETE · **Milestone 1 (D1) and Milestone 2 (D2) IMPLEMENTED** · Milestone 3 (D3 — blood pressure) open
**Date:** 2026-07-21 (updated 2026-07-22 — D2 eliminated for date-scoped + current metrics)
**Type:** Runtime-trace investigation (real `CoSGateway.respond` → `model_interface` → real gpt-4o) + program design
**Governs:** the standard used before any domain is declared *"Chief of Staff Complete."*
**Does NOT re-open architecture.** WLJ owns deterministic truth; the model owns reasoning; Current Context is authoritative; one deterministic authority per truth. This program *certifies* that established architecture — it changes none of it.

> **Success criterion (verbatim):** A paying customer can ask any factual question about their life, in natural language, and the Chief of Staff retrieves the correct deterministic truth **every time, through one authoritative path.**

---

## 0. Executive result

Six representative questions were run through the **real production path** (`CoSGateway.respond(surface="chat")` → `ModelInterfaceRuntime` → gpt-4o, owner flag on), reading back the `ToolCallLog` ledger per turn, then cross-checked against the deterministic providers directly (no OpenAI).

**3 / 6 correct, 3 / 6 failed** at investigation time. **Now 5 / 6** — D1 fixed by Milestone 1 (`f7cad624`), D2 fixed by the Single Date-Scoped Metric Authority milestone (2026-07-22, `docs/WLJ_WEIGHT_YESTERDAY_INVESTIGATION.md`). **D3 (blood pressure) remains open.** All three share the broader principle of **retrieval-contract fragmentation**, but they are **three DISTINCT implementation defects** and must not be conflated:

| Defect class | Meaning | Instance | Fix |
|---|---|---|---|
| **D1 — Date-contract drift** | Two retrieval tools disagree about *who* resolves a date; the one that delegates to the model gets a fabricated year | weight × "July 4" | **Milestone 1 — DONE** |
| **D2 — Shadow / parallel authority** | A curated snapshot surface answers a question a canonical **live** authority already owns, and wins | protein × yesterday; weight × yesterday | **Milestone 2 — DONE for date-scoped + current metrics (2026-07-22)**; non-date-scoped SAE keys + `get_domain_state` remain |
| **D3 — Missing systematic exposure** | **No** canonical live retrieval authority exists for the metric at all; snapshot surfaces are the only path | blood pressure | Milestone 3 |

> **D2 ≠ D3.** Delegating `get_foundational_health_facts` to `get_history` eliminates the protein shadow class — but it **cannot** fix blood pressure, because `get_history("health", "blood_pressure")` is `unsupported`: there is nothing to delegate *to*. Creating or selecting a BP authority is separate work and must not be hidden inside the foundational-facts cleanup.

| # | Question | Result | Failing condition | Class |
|---|----------|--------|-------------------|-------|
| 1 | What did I weigh on July 4? | ✅ **FIXED** | `get_history` told the model to compute the ISO date; it produced **2023**-07-04 → empty | D1 |
| 2 | How much protein did I eat yesterday? | ✅ **FIXED** | `get_foundational_health_facts` (SAE snapshot) **shadowed** `get_history` (live) → false 0 g. `protein_today`/`protein`-class keys now delegate to the one date-scoped authority | D2 |
| 3 | When was the last time I had pizza? | ✅ | `get_entity(nutrition, meal, contains=pizza)` — correct | — |
| 4 | Did I do calf raises during my last workout? | ✅ | `get_entity(health, workout, period=yesterday)` — correct | — |
| 5 | What is my current blood pressure? | ❌ | Snapshot-only surfaces missed it AND `get_history(blood_pressure)` = `unsupported`: **no canonical live BP authority exists to delegate to** | D3 |
| 6 | What is my current mission? | ✅ | `get_user_truth(section=goals)` — correct | — |

**The deterministic truth existed for all three failures** (proven directly): weight-Jul-4 via `get_history` at the *correct* year → 178 lb; protein-yesterday via `get_history(nutrition, protein, yesterday)` → 75 g; a live `BloodPressureEntry` of 118/76 was on record. **These are retrieval failures, not data failures.**

Two failures (weight, protein) are **environment-independent and architecturally decisive**. One (BP) is confounded by a cold test-env SAE snapshot but exposes a genuine coverage gap (below).

---

## 1. Task 1 — end-to-end runtime trace

For each question: **(1)** tool the model selected · **(2)** why · **(3)** truth surface that answered · **(4)** provider that owns the truth · **(5)** duplicate authority? · **(6)** correct architectural path?

Runtime ledger evidence lives in `scratchpad/runtime_trace.json` (this session).

### Q1 — "What did I weigh on July 4?" ❌
1. **Tool:** `get_history(domain=health, metric=weight, period=custom, start=2023-07-04, end=2023-07-04)`.
2. **Why:** correct tool for a metric-on-a-day aggregate — but the `get_history` schema instructs *"A specific date (e.g. 'July 4th') → set start=end=that date"* + *"ISO date 'YYYY-MM-DD'"*, so the model computed the calendar date itself and **hallucinated the year (2023)**.
3. **Surface:** `get_domain_history` → `HealthDomainTruth.history("weight")`.
4. **Provider:** `WeightEntry` (live ORM). Correct owner.
5. **Duplicate authority?** Not of the *tool* — but of the **date-resolution contract**: `get_entity` resolves natural dates in WLJ (*"Do NOT compute the calendar date yourself (you will get the year wrong)"*), while `get_history` pushes date-grounding onto the model. Two contracts for one concept (a date).
6. **Correct path?** Tool ✅, provider ✅, **argument grounding ✗**. WLJ owns date resolution everywhere except here.
- **Proof:** same call at `2026-07-04` → `{present: true, total: 178.0}`; at `2023-07-04` → `{status: empty}`.

### Q2 — "How much protein did I eat yesterday?" ❌ (reproduces the prior "protein yesterday" incident, live)
1. **Tool:** `get_foundational_health_facts(keys=['protein_today'])`.
2. **Why:** the tool is described as *"foundational, canonical health facts"* — it reads as **the** one-stop lookup, so the model reaches it first for a simple current-ish metric. (Note it even asked `protein_today` for a *yesterday* question — the curated key set has no `protein_yesterday`.)
3. **Surface:** `get_foundational_health_facts` → SAE nutrition snapshot field `daily_protein_g`.
4. **Provider (that SHOULD own it):** `get_history(nutrition, protein, yesterday)` → `NutritionQueries` (live) → **75 g**.
5. **Duplicate authority?** **YES — the core finding.** A hand-curated, SAE-snapshot-backed key/value surface shadows the systematic live aggregate authority for the same *"value of ⟨metric⟩ on ⟨day⟩"* question.
6. **Correct path?** ✗. The right authority (`get_history`) was **never called**.
- **Proof:** `get_history` → `75.0 g present`; `get_foundational_health_facts(protein_today)` → `{value: 0.0, source: SAE.nutrition.daily_protein_g}` — an affirmative **false zero**.

### Q3 — "When was the last time I had pizza?" ✅
1. **Tool:** `get_entity(domain=nutrition, entity_type=meal, filters={contains: pizza})`.
2. **Why:** `get_entity`'s description explicitly claims *"how often have I eaten X"* via the `contains` filter, and tells the model to pass the natural expression.
3–4. **Surface/Provider:** `get_domain_entity` → `NutritionQueries` → `FoodEntry`. Correct owner.
5. **Duplicate?** `search_history` (legacy keyword engine) also *could* answer this — the model correctly preferred the structured entity surface. Latent overlap, not triggered.
6. **Correct path?** ✅ ("July 11, 2026 — Pepperoni Pizza").

### Q4 — "Did I do calf raises during my last workout?" ✅
1. **Tool:** `get_entity(domain=health, entity_type=workout, filters={period: yesterday})`.
2. **Why:** `get_entity` names this exact case (*"did I do calf raises?"*) and instructs the model to pass the natural period; WLJ resolved "last workout".
3–4. **Surface/Provider:** `get_domain_entity` → `WorkoutQueries.describe` → `WorkoutSession`/`WorkoutExercise`/`ExerciseSet`. Correct — the exercise-level detail law delivered sets/reps/weight.
5. **Duplicate?** None reached. (`get_history` correctly withholds exercise contents.)
6. **Correct path?** ✅ ("Yes — Standing Calf Raise, 3×10 @ 90 lb").

### Q5 — "What is my current blood pressure?" ❌
1. **Tool:** `get_foundational_health_facts(keys=['last_blood_pressure_reading'])`.
2. **Why:** same "canonical facts" gravity as Q2.
3. **Surface:** SAE `health` snapshot field `bp_systolic`.
4. **Provider (owner):** `BloodPressureEntry` (live) — 118/76 on record.
5. **Duplicate authority?** YES, and worse: **three snapshot-or-absent paths, zero live path.** `get_foundational` → `unknown ("SAE health state did not include bp_systolic")`; `get_domain_state(health)` → `bp_reading: null` (also snapshot); `get_history(health, blood_pressure)` → **`unsupported`**. BP has **no live systematic authority at all**.
6. **Correct path?** ✗. *Caveat:* the test-env SAE was cold, which contributes to the snapshot misses; in prod (warm SAE) the snapshot path can succeed. But the architectural fragility is real and env-independent: **BP's only retrieval paths are snapshot-backed; there is no live fallback**, so any missed/stale rebuild yields a false absence with nothing to catch it. Same class as Q2, one layer deeper.

### Q6 — "What is my current mission?" ✅
1. **Tool:** `get_user_truth(section=goals)`.
2. **Why:** mission/primary-goal is durable explicit truth in the Personal Truth layer.
3–4. **Surface/Provider:** `get_user_truth` → `personal_truth` composer → `LifeGoal(is_primary_mission=True)`. Correct.
5. **Duplicate?** **Latent** — `get_foundational_goal_facts` also exposes `top_goal` from the goals SAE state (`build_goal_state`). Two authorities for "my top goal"; the model happened to pick the durable one.
6. **Correct path?** ✅ ("Move to France 2027").

---

## 2. Task 2 — the duplicate-authority census (and how to eliminate each)

**Do not patch missing fields.** Every item below is an *architectural* duplication; the fix removes an authority, it never adds a key.

### Class A (= D2) — the SAE-snapshot "facts" surface shadows the live systematic authority *(Q2, latent Q6)* — ✅ **ELIMINATED for date-scoped + current metrics (2026-07-22)**

> **Resolved by the Single Date-Scoped Metric Authority milestone** (`docs/WLJ_WEIGHT_YESTERDAY_INVESTIGATION.md` §10), driven by a second live instance of this class ("weight yesterday" answered 280.4 then 281.5 in one conversation).
> Option **(b)** was implemented: `get_foundational_health_facts` is now a **projection, not an authority**. `steps_today`, `steps_yesterday`, `weight_yesterday`, `glucose_yesterday`, `calories_today`, `calories_yesterday`, `protein_today` delegate to `metric_date.metric_on_date`; `current_weight` delegates to `metric_date.latest_observation_on_or_before`; both delegate onward to the systematic authority behind `get_history`. Their duplicate `_FACT_MAP` SAE specs were **deleted**, so no second definition remains to drift.
> Priority-2 ("guarantee current-fact freshness or read live") is satisfied **by delegation** — `current_weight` no longer touches the snapshot, and the answer carries `observed_on` + `age_days` + `freshness`, so a stale value can no longer present as current. Priority-3 ("never answer with a bare absence") is satisfied by the **exact-date/carry-forward split**: an exact-date miss returns `status="not_recorded"` from the SAME authority `get_history` would have used, so there is nothing left to fall through TO.
> **Sharper than the original decision:** the census framed this as "one authority." The weight incident proved that is insufficient — one authority with **two unnamed semantics** still contradicts itself. Carry-forward must be a *separately named contract* (`latest_on_or_before`), never a silent fallback inside an exact-date key.
> **Certification gate exists:** `apps/ai/tests/test_metric_date_authority.py` (generic — enumerates the registered date-scoped keys).
> **SECOND VARIANT FOUND AND ELIMINATED (2026-07-22, `docs/WLJ_NUTRITION_PROTEIN_INVESTIGATION.md`):** delegating the curated keys was necessary but NOT sufficient. The curated key LIST was itself hand-maintained and **asymmetric** — `protein_yesterday` did not exist, so the model substituted `protein_today` and reported the wrong day while the page showed 79 g. Measured: 3 of 5 curated metrics asymmetric, covering 7 of 50 (domain, metric) pairs. Metrics with NO curated key answered CORRECTLY (they fell through to `get_history`) — **the incompleteness was the defect.** Fixed by DERIVING the key set from `history_capability_index()` (7 → 101 keys, symmetric by construction) and REMOVING date-scoped keys from the model-facing enum so `get_history` is the one door. The legacy `_refine_to_day` had the same asymmetry hand-coded; it is now generic.
> **NUTRITION `get_domain_state` CLOSED (2026-07-23, `docs/WLJ_NUTRITION_STATE_INVESTIGATION.md`).** The carried-forward residual ("`daily_protein_g` = 0.0 vs canonical 79 g") was **a mis-statement in my own note** — `daily_*` means TODAY and the 79 g was YESTERDAY. Runtime proof found a **different, real** contradiction: `daily_*` claimed a calendar day but recorded no date, and `ensure_fresh` detects staleness by looking for a NEWER RAW WRITE — so a **date rollover is structurally invisible** (midnight writes nothing). Every morning before the first log, the snapshot reported yesterday's macros as today's while `metric_on_date`/`get_history` said not-recorded. Fixed by: delegate to `NutritionQueries.get_daily_totals` (the snapshot no longer calculates), **date-stamp** (`daily_totals_date`), **rollover detection** (`_DATE_BOUND_MODULES` checked before the write check), and **disclosure** (`day_freshness`/`state_date`/`user_local_date`; stale values are returned WITH the disclosure, never hidden). 17 certification gates.
> **Remaining in Class A:** the non-date-scoped SAE-backed keys (`last_glucose_reading`, `average_glucose_yesterday`, `sleep_*`, `steps_recent`, `last_blood_pressure_reading`, `weight_30_day_change`); and — from the Phase 6 audit — **`tasks/life.completed_today` and `calendar.today_events`** carry the SAME undated-day-claim shape nutrition had (ranked #1/#2 for the next slice; the mechanism `_DATE_BOUND_MODULES` + `day_bound_field()` + `_day_freshness()` is now generic and reusable).

**Original analysis (retained):**

> **Scope correction:** blood pressure (Q5) is **NOT** in this class. Class A is defined by the existence of a canonical **live** authority that the snapshot surface shadows. BP has no such authority (`get_history` = `unsupported`), so it is **D3 — missing systematic exposure**, handled separately in Milestone 3. Fixing Class A will not fix BP.
`get_foundational_health_facts` and `get_domain_state` both project the **SAE snapshot** (`get_module_state(..., allow_rebuild=False)`); `get_history` reads **live**. For a *"current / on-a-day metric"* question the model can reach any of the three, and the snapshot surfaces:
- return **false absence / false zero** when the module omits the field (protein `daily_protein_g`) or the snapshot is cold/stale (BP);
- **answer instead of deferring**, so the model never falls through to the live authority that holds the number.

This is a direct violation of *one deterministic authority per truth*. **It is already half-fixed inside the same file:** medication facts and the per-day batch were deliberately migrated to **live reads** (`health_facts.py` comments: *"read live, never SAE… so it can never go missing or stale"*). The class was recognised; the migration simply wasn't finished for macros / vitals / nutrition-current.

**Eliminate the class (in priority order):**
1. **Make `get_foundational_health_facts` a projection, not an authority.** Either (a) **retire** the overlapping metric-on-a-day keys so `get_history` is the sole answer to *"value of a metric for a day/period"*, or (b) have each key **delegate to `get_history` / the live provider** and **auto-derive the key set** from `history_metrics × periods` — a pure projection that can never be incomplete or drift. (a) is smaller and preferred.
2. **Guarantee current-fact freshness or read live.** Where a genuine *current* fact must come from the snapshot, route it through the existing `ensure_fresh` self-heal (see `journal_snapshot_freshness`) so a missed rebuild can't serve a false absence — or read the current value live.
3. **Never answer with a bare absence from a snapshot surface.** A snapshot miss must return a *defer* signal, not a confident "not recorded," so the loop falls through to the live authority.

### Class B (= D1) — divergent date-resolution contracts across retrieval tools *(Q1)* — ✅ **ELIMINATED (Milestone 1)**
`get_entity` delegates natural-date resolution to WLJ (*"you will get the year wrong"*); `get_history` instructs the model to emit absolute ISO dates. Same concept, two contracts — and the one that pushes grounding onto the model fails.

**Eliminate the class:** make **WLJ the single date-resolution authority for every retrieval tool.** `get_history` should accept the natural expression (`on_date`/`period` = "July 4", "yesterday", "last Tuesday") and resolve it via the existing shared resolver `truth/periods.py :: resolve_date_expression` (most-recent-past), exactly as `get_entity` does. Deprecate model-supplied `start`/`end` for single-date questions (keep them only for explicit ranges, and resolve/clamp those in WLJ too).

### Class C — duplicate "current metric" tool surface *(structural)*
`get_domain_state` (snapshot) and `get_history` (live) both answer "current" metric questions, and Current Context page summaries carry the same numbers as *context*. This is tolerable **only if all three derive from ONE deterministic source per metric** (the Current Context contract already mandates this for page-vs-provider). The audit action is: for each current metric, confirm a **single shared builder** feeds the page summary, the SAE snapshot, and any tool — and that the tool prefers the live builder when snapshot freshness is not guaranteed.

### Class D — latent goal-fact duplication *(Q6)*
`get_user_truth(section=goals)` (durable Personal Truth) and `get_foundational_goal_facts` `top_goal` (goals SAE state) both answer "my mission/top goal." Collapse to one: the durable Personal Truth layer owns identity-of-mission; the SAE goal state owns *progress*. Remove `top_goal` from the foundational surface (or delegate it).

### Not duplicates (leave alone)
- **Executive briefings** and **Current Context page summaries** are *composed context injected into the prompt*, **not model-callable retrieval tools** — they do not compete with a tool call and are not part of this census (they must still obey the single-source rule of Class C).
- **`get_analysis`** composes `get_history` + `get_entity`; it reuses authorities rather than duplicating them.

---

## 3. Task 3 — the permanent Truth Retrieval Certification framework

The instruments already exist; this formalises them into the **gate every domain passes before "CoS Complete."** No new framework is built — the two-owner model (`docs/WLJ_CERTIFICATION_PLATFORM_FUTURE.md`) is adopted as the standard.

### The two owners
- **Owner-1 — Deterministic (committed CI, no OpenAI).** `apps/core/truth/question_specs.py` (`QuestionSpec` × `CAPABILITIES`) + `certification_fixtures.py`, run by `test_truth_retrieval_slice.py`. Proves the canonical provider returns the right value for each capability. **A green Owner-1 means a live failure is a genuine product defect, not missing deterministic coverage.**
- **Owner-2 — Live runtime (operator-triggered, never CI).** The Beth **Acceptance Center** Deep run routes the same NL questions through **`CoSGateway.respond` → `ModelInterfaceService`** (the production path) and captures per-turn `selected_tool` / `tool_arguments` / `canonical_provider` / `retrieval_evidence` joined by `turn_id`. **Live cert never runs in the normal test suite** (it hits OpenAI); it runs through the Acceptance Center in the worker.

### Per-domain certification record (the required template)
Every domain declares, in one place:

| Field | Meaning |
|---|---|
| **Deterministic owner** | the single `DomainTruth` provider + the `*_queries.py` authority behind it |
| **Retrieval tools** | which of `get_domain_state / get_history / get_entity / get_analysis / get_user_truth` serve it (a metric appears under **exactly one** "value-on-a-day" authority) |
| **Supported question types** | the `CAPABILITIES` row (current / historical / latest / timeline / list / count / existence / comparison) |
| **Single-authority attestation** | *no other advertised tool answers the same question with a conflicting or absent result* (the new gate below) |
| **Production validation** | the last Owner-2 Deep run id + date + pass rate against this domain |
| **Regression tests** | the Owner-1 specs + the single-authority contract test |
| **Ongoing monitoring** | the ToolCallLog signal (below) |

### The three certification gates a domain must pass
1. **Deterministic floor (Owner-1):** every declared capability returns the right value from its provider.
2. **Single-authority gate (NEW — the class-eliminator):** a contract test enumerates each `metric × {today, yesterday, this week, a specific past date}` and asserts **(a)** the systematic authority returns the page-agreeing number **and (b)** no *other* advertised tool answers the same question with a conflicting or absent result. This makes a shadow authority (Class A/D) and a date-contract divergence (Class B) **detectable before the domain ships.**
3. **Live grounding (Owner-2):** the Acceptance Center Deep run confirms the model **selects the right tool with WLJ-resolved arguments** and grounds the answer in the returned truth (freshness / confidence / provenance present).

### Ongoing monitoring — close the audit blind spot
The `ToolCallLog` ledger already records every turn, but **has no operator read channel** (flagged residual, twice). Ship a small read-only operator endpoint (behind `X-Claude-API-Key`, like the other operator endpoints) that returns recent `(question, selected_tool, args, result_status)` rows. Then a live monitor can flag **the certification-relevant signal:** *a turn where a snapshot surface returned `unknown`/`0` while a live authority for the same metric held a value* — the shadow-authority fingerprint — without reproducing the turn.

---

## 4. Task 4 — implementation roadmap (implementation work only; no ratified decision re-opened)

Ordered by trust impact × leverage. Each item eliminates a class or unblocks certification; none add a bespoke capability or a WLJ reasoning path.

**Track 1 — Retrieval Certification (the spine; everything else rides it).** Executed as four strictly sequential milestones — one class per milestone, each proven at runtime before the next begins.

- **Milestone 1 — Natural Date Authority (D1). ✅ COMPLETE (runtime-verified).** `get_history` accepts the natural expression; the ONE shared resolver (`truth/periods.py`) resolves it against the user's **local** today; explicit ISO preserved for existing callers; unparseable phrases rejected honestly. Tool schema now instructs the model to pass the user's words (the `period` enum, which structurally *blocked* natural phrases, was removed). Runtime: model sends `period:"July 4"` → **"On July 4, your weight was 178 lb."**
- **Milestone 2 — Eliminate supported-metric shadow authorities (D2).** Build a precise key inventory across `get_foundational_health_facts` / `get_domain_state` / `get_history` / other health surfaces, classify each key (delegates · legitimately summary-specific · shadow · unsupported by any live authority · broken/falsely-absent), then retire or thin-project every duplicate onto its canonical authority. Kills the protein false-zero class — **without** patching `protein_today` or adding `protein_yesterday` as another curated key.
- **Milestone 3 — Blood-pressure authority investigation (D3).** *Prove before coding:* where the latest BP record lives, which builder feeds the BP page, whether a canonical deterministic BP query authority already exists, why `get_history` reports BP unsupported, and which surface should own current / latest / history / date-specific BP. Then expose the **existing** authority through the systematic surface — never a second BP calculator, snapshot authority, or facts-specific implementation.
- **Milestone 4 — Single-authority certification gate.** Permanent deterministic contract audit over representative metric × time combinations (weight × natural date · protein × today · protein × yesterday · BP × latest · BP × specific date where supported), asserting exactly one canonical authority per class, delegation from convenience tools, no conflicting snapshot value, honest and *distinguishable* unsupported states (no data · unsupported metric · stale snapshot · provider failure), page agreement, and honest source/freshness/confidence metadata.

**Then:** point Owner-2 at ModelInterface and record a per-domain Deep-run pass rate; re-run the six-question slice in **production** (warm SAE) to separate the BP env-confound from the real gap.

**Track 2 — Duplicate-Authority Elimination** *(Class C/D cleanup after Track 1)*
2.1 Per-metric single-source audit: one shared builder feeds page summary + snapshot + tool.
2.2 Collapse the goal-fact duplication (Class D): Personal Truth owns mission identity; SAE owns progress; remove/redirect `top_goal` from foundational facts.
2.3 Decide `search_history` vs `get_entity(contains=)` overlap — one keyword/substring authority, not two.

**Track 3 — Bidirectional Current Context** *(the overview-tier work is the prerequisite, already CC-certified for Dashboard/Health/Finance/Meals home)*
3.1 Extend the certified `build_*_home_summary` shared-builder + SAE-snapshot pattern to the remaining overview pages (glucose / calendar / goals / tasks).
3.2 Let the model *write back* Current Context intent (page ↔ conversation) once retrieval is single-authority — do not start before Track 1 lands (it would encode the drift).

**Track 4 — Reveal Target** — surface, per answer, the exact deterministic record(s)/provider that grounded it (built on the ToolCallLog read channel from §3). Turns "trust me" into "here's the row."

**Track 5 — Client Presentation Adapters** — one composed-truth envelope, per-client rendering (web / iOS / voice). Pure presentation; blocked on nothing but adds no truth authority — sequence after Track 1–2 so adapters render a single-source truth.

**Track 6 — Platform Consumers (Travel, Legacy, …)** — the first *platform-consumer* domain (Travel) composes existing platform truth; it must consume the **certified** retrieval contract, so it follows Track 1. Legacy already rides the contract; certify it via the §3 record.

---

## 5. Constitutional check
- **WLJ owns truth; the model reasons** — preserved. Every fix removes or projects an authority; none add WLJ reasoning.
- **One authority per truth** — this program's entire purpose; Classes A–D are the current violations.
- **Improve truth before adding intelligence** — every recommendation *deletes* a drifting/shadow surface or *resolves a date in WLJ*; none add a capability or a key.
- **No redesign** — the `DomainTruth` contract, the runtimes, and Current Context are unchanged; this is certification + de-duplication.

---

*Runtime evidence gathered this session via the real `CoSGateway` path against the test DB (full schema); no production code modified. Live-runtime harness was throwaway (hits OpenAI) and was not committed. Deterministic evidence is reproducible via the providers directly.*
