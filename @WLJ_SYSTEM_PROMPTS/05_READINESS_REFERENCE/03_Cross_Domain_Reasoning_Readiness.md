# Document 3 — Cross-Domain Reasoning Readiness

**Question under test:** Can WLJ deterministically explain changes like *"Why has my weight loss slowed down?"* — and analogous questions about stress, productivity, motivation, and routine breakdown — using deterministic truth, as Architecture Law 1 (LLM Last) requires?

**Short answer:** WLJ has **7 of 10** cross-domain factors computed deterministically, and it has a **real deterministic root-cause composer** for the weight question. But that composer's causal aperture is only **5 physical-health domains**, so **6 of the 10 factors are computed-but-stranded** — they exist as truth but can never surface as the cause of a weight slowdown today. For non-weight domains, generalized "why did X change" reasoning is largely **not assembled** at all.

---

## 1. The 10-Factor Deterministic Inventory

Status: COMPLETE = named deterministic metric/signal exists and is queryable · PARTIAL = raw/transient only, or partial sub-case · MISSING = not computed.

| # | Factor | Deterministic provider (file:line) | Status | Reaches the weight composer? |
|---|--------|-----------------------------------|--------|------------------------------|
| 1 | **Stress from journals** | `stress_score` (14-day decay) `state_builder.py:1860-1885`; `mood_trend` `:1817`; `anxiety_mention_count_7d` `:1848`; `StressRecoveryRule`/`EmotionalOverloadRule` `rules_cross_domain.py:553,644` | **COMPLETE** | ❌ No — not on executive board, not in weight `rel` set |
| 2 | **Travel disruption** | `TravelActiveRule` `rules_context.py:503-622` (keyword detection across journal+calendar+sleep) | **PARTIAL** | ❌ No — transient info insight only; no `build_travel_state` |
| 3 | **Sleep disruption** | `_build_sleep_mood_series` `cdce_engine.py:190`; CDCE `detect_sleep_mood` `:310`; executive board sleep signal `executive_state.py:198-212` | **COMPLETE** | ✅ Yes — sleep rule in `_ROOT_CAUSE_RULES['weight']` `deterministic_router.py:6205` |
| 4 | **Routine disruption** | `build_routine_state` adherence `state_builder.py:4033-4038`; `_contract` `:4062` | **COMPLETE** (as state) | ❌ No — executive `routines` signal is a shallow fallback (`executive_state.py:543-552`); not in weight `rel` set |
| 5 | **Meal adherence** | `macro_compliance_score` `state_builder.py:2036`; `calorie_compliance_pct` `:2016`; CDCE `detect_nutrition_energy` `:734` | **COMPLETE** | ✅ Yes — nutrition rule in `_ROOT_CAUSE_RULES['weight']` `:6208` |
| 6 | **Medication adherence** | `adherence_7d`/`adherence_score_7d` via `calculate_medicine_adherence_rate` `state_builder.py:3650-3677`; `ComplianceRiskRule` `rules_cross_domain.py:413` | **COMPLETE** | ⚠️ Partial — in `rel` set as *evidence*, but no medication rule in `_ROOT_CAUSE_RULES['weight']`; ComplianceRiskRule only fires for weight *increasing* |
| 7 | **Execution overload** | `compute_weekly_pressure` (`avg_load`) `rules_cross_domain.py:328-409`; `OverextensionRiskRule`; calendar `schedule_density` `state_builder.py:3928` | **PARTIAL** | ❌ No — `_overload` proxy (`deterministic_router.py:6233`) feeds sleep/nutrition causes, not weight |
| 8 | **Relationship stress** | `build_relationships_state` neglect/cadence `state_builder.py:4708-4741`; `OverextensionRiskRule` relational-drift `rules_cross_domain.py:349` | **PARTIAL** | ❌ No — neglect computed, but no *stress* metric, not in weight `rel` set |
| 9 | **Faith drift** | `reading_streak`/`days_since_reading` `state_builder.py:1648-1652`; `ScriptureReadingDropOffRule` `rules_scripture.py:15`; CDCE `detect_faith_consistency` `:529` | **COMPLETE** (as faith signal) | ❌ No — not metabolically wired to weight |
| 10 | **Calendar overload** | `schedule_density` `state_builder.py:3928`; `schedule_conflicts` `:3953-3964` | **COMPLETE** (as calendar state) | ❌ No — not a board domain signal, not in weight `rel` set |

**Count:** COMPLETE 6 · PARTIAL 4 · MISSING 0. Seven factors (1,3,4,5,6,9,10 — counting the COMPLETE-as-state ones) are deterministically computed. The deterministic *ingredients* for a holistic answer largely exist.

---

## 2. Does a composed holistic root-cause provider exist?

**Yes — but narrow and weight-specific.**

There is a genuine deterministic composer for exactly this question:

- **`_handle_weight_assessment_query` → `_render_structured_assessment(user, "weight")`** — `apps/ai/deterministic_router.py:6375` / `:6279`.
- Triggered by cues including *"why has my weight loss slowed / stalled / plateaued"* — `_WEIGHT_ASSESS_CUES` `:6356-6368`.
- Emits a deterministic **Facts / Evidence / Assessment / Confidence / Recommendation** object; cause inferred by `_root_cause` `:6229` from co-occurring negative domains on the executive board (`_life_state_signals` `:6087` → `build_executive_state_signals`). This is law-compliant: the LLM narrates over it, it does not invent it.

**The aperture is the limitation.** The evidence pool and root-cause inference are hard-filtered to:

```
rel = {"sleep", "nutrition", "workouts", "glucose", "medication"}   # deterministic_router.py:6308, :6321
_ROOT_CAUSE_RULES['weight'] = [sleep rule, nutrition rule]           # :6204 (only two rules)
```

So of the 10 factors:
- **Can be named as the cause:** sleep (3), nutrition/meals (5).
- **Appear as evidence but never as named cause:** medication (6), workouts (on the board, no weight rule).
- **Cannot reach the composer at all** (computed elsewhere, absent from both the executive board and the `rel` filter): **stress/journal (1), travel (2), routine (4), execution-overload (7), relationship (8), faith (9), calendar-overload (10).**

A consumer asking "why has my weight loss slowed" therefore gets a deterministic answer — but it can only ever blame **sleep or nutrition**. The other deterministically-computed factors are stranded.

---

## 3. Can WLJ explain the other change-types?

| Change-type | Deterministic composer? | Evidence |
|---|---|---|
| **Weight changes** | **PARTIAL** | Real composer (`_render_structured_assessment`) but 5-domain aperture, 2 cause rules (`deterministic_router.py:6204/6308`) |
| **Stress changes** | **PARTIAL** | `stress_score` computed (`state_builder.py:1883`) + `StressRecoveryRule` (`rules_cross_domain.py:553`); but no composed "why is stress up" root-cause provider — `_ROOT_CAUSE_RULES` (`:6168`) defines no stress entry |
| **Productivity / execution changes** | **PARTIAL** | Execution state + RecoveryState modes computed (`execution_state.py`, weekly pressure `rules_cross_domain.py:328`); `_overload` proxy exists but feeds only sleep/nutrition assessments, no productivity root-cause composer |
| **Motivation / momentum changes** | **PARTIAL** | `momentum_trend` (`state_builder.py:1526`) + CDCE `detect_momentum_engagement` (`cdce_engine.py:824`) computed; no composed motivation root-cause provider |
| **Routine breakdown** | **PARTIAL** | `build_routine_state` adherence + `RecoveryState.day_narrative` computed; surfaced as state, but no composed "why did routine break" cause provider; executive routine signal is a shallow fallback (`executive_state.py:543`) |

**Pattern:** the underlying metrics exist for all five change-types, but `_ROOT_CAUSE_RULES` (`deterministic_router.py:6168`) only defines rules for sleep, workouts, glucose, nutrition, and weight. There is **no generalized "explain change in domain X" composer**; everything else relies on this fixed, physical-health-only table.

---

## 4. CDCE — what it actually computes

CDCE (`apps/core/ai_cross_domain/cdce_engine.py`, 6-hour cadence via ISE, `run_cdce:69`) is a **fixed-detector co-occurrence engine**, not a general correlation discoverer. It runs exactly **7 hardcoded detectors** (`CORRELATION_DETECTORS` `:893`), storing `DomainCorrelation` rows (`models.py:15`, strength/direction/narrative/evidence):

1. `detect_sleep_mood` `:310` — sleep < 6.5h → negative next-day mood
2. `detect_exercise_mood` `:373` — exercise → next-day mood
3. `detect_habit_goal_alignment` `:432` — habit rate vs goal completion
4. `detect_faith_consistency` `:529` — reading streak vs mood
5. `detect_fasting_fitness` `:636` — fasting compliance vs workout consistency
6. `detect_nutrition_energy` `:734` — macro compliance vs transformation score
7. `detect_momentum_engagement` `:824` — multi-domain momentum vs mood

**Two critical facts for this audit:**
- CDCE computes **no weight-related correlation**, and none of its 7 detectors covers stress→weight, travel→weight, routine→weight, calendar→weight, or med-adherence→weight.
- CDCE is **decoupled from the weight composer** — `_render_structured_assessment` reads the executive board (`build_executive_state_signals`), **not** `DomainCorrelation`. So even CDCE's discovered correlations do not feed the "why did weight slow" answer.

---

## 5. Verdict

**Can WLJ explain weight/stress/productivity/motivation/routine changes using deterministic truth today?**

- **The deterministic ingredients exist** — 7 of 10 cross-domain factors are COMPLETE as state or signals, and a law-compliant deterministic root-cause composer is real and working for the weight question.
- **The assembly is the bottleneck.** The composer ingests only 5 physical-health domains via a hardcoded `rel` filter and a 2-rule `_ROOT_CAUSE_RULES['weight']` table. Six computed factors (stress, travel, routine, execution overload, relationship, calendar) are **stranded** — present as truth, absent from the explanation. CDCE, the one cross-domain correlation engine, is fixed-detector, weight-blind, and not wired into the composer.
- **For non-weight change-types**, there is no generalized root-cause composer at all — only the same physical-health rule table.

So: WLJ **possesses** enough deterministic truth to begin holistic reasoning, but it does **not yet assemble** that truth into holistic cross-domain explanations beyond a narrow physical-health weight/sleep/nutrition core. The gap is in **composition and aperture**, not in the existence of the underlying deterministic metrics.

*(This document states findings only. It does not propose how to widen the aperture — that is a later, joint decision.)*
