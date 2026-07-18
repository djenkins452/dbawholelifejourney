# Customer Truth Certification — PRODUCTION Run 1 (Danny's real data)

**Date:** 2026-07-18 · **Evidence:** production transcript results reported by the operator (Danny), run against the production Chief of Staff with real WLJ data. This is the **first production Customer Truth evidence** and it supersedes the local fixture run for the domains it covers.

## Evidence-source discipline (every claim below is tagged)
- **[PROD]** measured production behavior (the reported transcript).
- **[LOCAL]** the earlier local fixture slice-1.
- **[ARCH]** repository inspection — what truth path exists (proven from code).
- **[TRACE]** internal tool/ledger not visible from here — needs the production Acceptance Center `AcceptanceResult` rows / worker logs.
- **Confidence:** proven-from-trace · strongly-indicated · requires-log-inspection.

## Correction of the prior claim (owned)
My earlier statement that Fitness / Goals / Body-Measurements / etc. were "unmeasured" or "impossible" was **wrong on an architectural point**: the `DomainTruth` registry is **not** the only truth path to the model. **Standing context, executive briefings, and cross-domain entities also deliver facts.** Fitness answers came through `health.describe("workout")`; Goals answers came through **standing context** (`user_priorities` + `cos_intelligence`). A missing `DomainTruth` provider does not make a production answer impossible — it changes *which layer* served it. Corrected throughout.

---

## Scorecard by domain

| Domain | Production verdict | Truth path (reconciled) | First failing layer (weakness) | Confidence |
|---|---|---|---|---|
| **Weight** | ✅ **PASS** [PROD] | `weight_yesterday`/`get_history` + SAE `current_weight` (fresh in prod) | — (the [LOCAL] failures were test-env SAE staleness — **now confirmed environmental**) | proven (prod PASS reconciles local) |
| **Medication** | ✅ **PASS** [PROD] | medicine `describe` + adherence + `last_taken` | — | strongly-indicated (last-taken source = [TRACE]) |
| **Nutrition** | ❌ **FAIL / PARTIAL** [PROD] | `describe(food)` (no date filter) + `latest_meal_logged` (date only) | **Canonical provider — no date-scoped food retrieval** (+ tool-selection to the date-only fact) | strongly-indicated |
| **Health — glucose/BP current** | ✅ **PASS** [PROD] | day-facts (glucose 81, BP 126/83) | — | proven |
| **Health — glucose/BP trend** | ❌ **FAIL** [PROD] | — | **Canonical provider — `history_metrics` excludes glucose & BP** | **proven-from-trace** [ARCH] |
| **Body Measurements** | ❌ **FAIL (unsupported)** [PROD] | none | **Missing provider** — `BodyMeasurementSession` model EXISTS, no `DomainTruth` | **proven-from-trace** [ARCH] |
| **Fitness** | ◐ **PARTIAL PASS** [PROD] | `health.describe("workout")` (per-set `weight_lb`/`reps`/`is_pr`, `since_days`) | **Grounding / evidence-shape** — squat-load conflated bodyweight reps vs resistance load | strongly-indicated |
| **Goals / Missions** | ◐ **PARTIAL PASS** [PROD] | **standing context** (`user_priorities`, `cos_intelligence`) — canonical SUMMARY | **Missing provider** for item-level — no `goals` `DomainTruth`, so milestones can't be tool-confirmed | strongly-indicated (fields = [TRACE]) |
| **Journal** | ⚠️ **PARTIAL — trust defect** [PROD] | `journal.describe` is clean [ARCH], but prod blended mobility/audio-exposure | **Source blending — likely a broad path (search_history/other) mixed health telemetry into "journal"** | requires-log-inspection [TRACE] |
| **Relationships** | ❌ **INCOMPLETE** [PROD] | none reachable — `RelationshipDomainTruth` has no `entity_types`; People not registered | **Missing provider/registration** → announced retrieval, empty/incomplete final | strongly-indicated (exact stop = [TRACE]) |
| **Cross-domain executive** | ◐ **PARTIAL** [PROD] | multiple domains + model synthesis | **Grounding discipline** — generic external guidance (sleep ranges, 10k steps) mixed into a "strictly WLJ" answer | strongly-indicated |

## Scorecard by capability (production-measured, across tested domains)
| Capability | Working | Weak / failing |
|---|---|---|
| Current fact | weight, meds, glucose, BP, fitness-latest, goals-summary | body measurements (unsupported) |
| Historical | med adherence | glucose/BP trend, nutrition, goals-milestones |
| Latest | weight, meds, fitness, nutrition-**date-only** | nutrition meal **contents** |
| List | meds, goals, workout-exercises | — |
| Count | — | (no windowed-count surface anywhere) |
| Timeline | weight, fitness 7-day | glucose/BP, nutrition |
| Existence | calf-raises, meds | pizza history (nutrition), person lookup (relationships) |
| Comparison | weight (monthly) | body-measurement limb comparison, squat-load precision |
| Summary | goals/mission, cross-domain | cross-domain **grounding** (generic advice leaked) |

---

## Trace plan (before finalizing the backlog — per operator instruction)
Each needs the production Acceptance Center `AcceptanceResult` evidence columns (which now exist: `selected_tool`, `tool_arguments`, `canonical_provider`, `retrieved_records`, `first_failing_layer`). Run the questions through the Acceptance Center in prod and read the columns:
1. **Nutrition** — was `selected_tool` the date-only `latest_meal_logged` fact or `get_entity(food)`? Do `FoodEntry` rows exist for today (missing DATA vs missing RETRIEVAL)? → separates provider-gap from empty-data.
2. **Journal** — which tool served the journal answer (`get_entity(journal)` vs `search_history` vs standing context)? `retrieval_evidence` shows what records blended. → confirms source-typing loss vs a broad-search blend.
3. **Relationships** — the ledger `result_status` (unsupported / empty / error / timeout) → tool-loop vs empty-final.
4. **Fitness squat** — `retrieved_records` for the squat entity: did it carry `weight_lb`? If yes, the miss is grounding, not truth.
5. **Goals** — the standing-context snapshot fields present for the run → confirms canonical summary vs stale.

---

## Revised evidence-driven backlog (PROVISIONAL — finalize after trace)
Ranked by measured customer impact → deterministic-gap clarity → effort → risk.

| # | Item | Impact | Deterministic gap | Effort | Risk | Status |
|---|---|---|---|---|---|---|
| 1 | **Nutrition date-scoped food retrieval** | HIGH [PROD] | Yes — clean (reuse `entries_on_date`/`entries_in_range`) | S | Low | measured FAIL |
| 2 | **Health glucose/BP trend (history metrics)** | HIGH [PROD] | Yes — clean (add to `_HISTORY`) | S | Low | measured FAIL, **proven** |
| 3 | **Body Measurements truth provider** | MED-HIGH [PROD] | Yes — register provider (data model exists) | S-M | Low | measured FAIL, **proven** |
| 4 | **Journal source separation** | HIGH (trust) [PROD] | **TRACE FIRST** | ? | Med | trust defect — trace before fix |
| 5 | **Relationships/People retrieval** | MED [PROD] | Yes — missing person entity surface | M-H | Med-High | measured INCOMPLETE |
| 6 | **Goals item-level (milestones) provider** | MED [PROD] | Yes — no goals `DomainTruth` | M | Med | summary works, detail gap |
| 7 | **Fitness squat-load precision** | LOW-MED [PROD] | No — grounding/evidence-shape | S | Low | Owner-2 (grounding) |
| 8 | **Cross-domain grounding discipline** | MED [PROD] | No — grounding | — | — | Owner-2 (no truth fix) |
| — | Weight current-fact | — | RESOLVED — prod PASS (was local staleness) | — | — | ✅ |

## Recommended next implementation slice
**Nutrition date-scoped retrieval (#1)** — the highest measured customer impact with the smallest, lowest-risk deterministic fix that reuses existing canonical queries. **Health glucose/BP trends (#2)** and **Body Measurements provider (#3)** are the immediate follow-ons (both proven, small, low-risk). **Journal (#4)** is trust-critical but must be **traced first** (which path blended) before any fix. **Do not implement until the trace above is run and this order is confirmed.**

*This is analysis + prioritization only. No code changed. No new provider added. The order is provisional pending the production Acceptance Center trace.*
