# Body `region_state` — Design Contract (DESIGN ONLY, not implemented)

**Status:** Design contract. **NOT built.** No production `region_state` primitive exists.
**Created:** 2026-07-13 (during Body Intelligence Phase II-A).
**Governs:** the *future* shared truth foundation for the Body Overlay (Phase III), the
Body Heat Map (Phase IV), and per-region click-to-coach (Phase V).

> This document exists so the shared foundation is designed before it is written. Phase
> II-A deliberately did **not** add this primitive — it shipped a narrow, visual-scoped
> facts helper (`apps/health/services/body_visual_stories.py`) instead. Do **not** create
> a production `region_state` module from this doc without an explicit review.

---

## 1. Why design-first (the concern this prevents)

The tempting abstraction — "one `region_state(user, region)` that tells the UI what colour
to paint" — quietly fuses **seven distinct concerns**:

1. Measurement truth (what was measured)
2. Change calculation (delta vs a comparison point)
3. Statistical significance (is the delta real vs measurement noise?)
4. Mission direction (is this region moving toward the user's goal?)
5. Confidence (how much do we trust this read?)
6. Product colour (green / yellow / red / gray)
7. Interpretation (what it *means* — cause, recommendation)

Fusing them is how WLJ would **quietly become a reasoning/verdict engine** — the exact
thing the architecture forbids (WLJ owns deterministic truth; the conversational model
owns interpretation). Concerns **4, 6, and 7 are the dangerous ones**: mission direction
is only sometimes deterministically known, product colour is a policy that needs review,
and interpretation is not WLJ's job at all.

**The rule for the future primitive:** it exposes **structured evidence and deterministic
calculations only**. It never emits a narrative conclusion, never asserts an unsupported
cause, and (in its first version) never emits mission-alignment colour.

---

## 2. Proposed contract

```
region_state(user, region, *, as_of=None) -> RegionEvidence
```

`region` is a canonical body region key (`waist`, `chest`, `arm_left`, …). The function is
**deterministic, user-scoped, request-path-safe** (pure arrangement of the pre-computed
body-composition snapshot + measurement history — no heavy compute, no LLM).

### Output — `RegionEvidence` (facts and calculations only)

| Field | Meaning | Owner |
|-------|---------|-------|
| `region` | canonical region key | truth |
| `label` | human label | truth |
| `current_value`, `unit` | latest measured value | truth |
| `current_date` | date of the latest reading | truth |
| `comparison_value` | value at the comparison point (or `null`) | truth |
| `comparison_date` | date of the comparison reading (or `null`) | truth |
| `absolute_delta` | `current − comparison` (or `null`) | calculation |
| `percent_delta` | signed % change (or `null`) | calculation |
| `observation_count` | how many readings exist for this region | truth |
| `days_between` | days spanned by the comparison | calculation |
| `freshness` | `current` \| `stale` (+ `age_days`) | calculation |
| `significance` | `{threshold, result: significant \| within_noise \| insufficient}` | calculation |
| `target_direction` | `up` \| `down` \| **`unknown`** — populated **only when a target truly exists** (an explicit user goal / mission for this region); otherwise `unknown`, never guessed | truth (policy input) |
| `confidence` | `high` \| `medium` \| `low` | calculation |
| `confidence_basis` | the factual inputs behind the level (counts, span, freshness) | calculation |
| `missing_reason` | when there is no value: `never_measured` \| `not_in_latest_batch` \| … | truth |

### Explicitly NOT in the output (v1)

- **No `tone` / colour** (`green|yellow|red|gray`). Colour is a *product policy* layered
  on top later, after review (§4).
- **No verdict / narrative** ("on track", "concerning", "great progress").
- **No cause** ("this is muscle", "this is water"). Circumference alone cannot prove it.
- **No recommendation.** That is the conversational model's job, over this evidence.

---

## 3. How the two layers compose (future)

```
region_state (deterministic evidence)      ← this contract (truth + calculation)
   │
   ├── Overlay (III)      geometry: previous vs current, per region
   ├── Heat Map (IV)      colour: a REVIEWED policy mapping evidence → tone (§4)
   └── Click-to-coach (V) the model narrates the evidence in the user's relationship
```

The overlay and heat map are **two layers of one parametric body** (geometry + colour) on
top of one evidence layer — but each layer is added and reviewed independently. II-A's
`body_visual_stories.py` is the concrete precursor of the **evidence** layer, scoped to two
visuals; a future `region_state` would generalise it (adding `observation_count`,
`target_direction`, richer `confidence_basis`) without changing its facts-only posture.

---

## 4. The colour policy is a separate, reviewed decision (Phase IV)

Green / yellow / red / gray **mission alignment** is a *product policy*, not a truth. It
requires:

- A deterministic, **explicit** `target_direction` for the region (a real user goal/mission
  — never an assumed one). Where no target truly exists, the region cannot be "toward" or
  "away"; it is only *changed / stable / current-only / missing* (the neutral II-A
  vocabulary).
- A written mapping `RegionEvidence → tone` reviewed against the architecture so WLJ does
  not become a verdict engine. Red means **needs attention**, never "bad".
- A significance gate so noise never paints a colour.

Until that review, WLJ shows **neutral, directional facts** (larger / smaller / stable /
current-only / not-measured / stale), which is exactly what II-A ships.

---

## 5. Open questions to resolve before building

- Comparison point: latest-vs-previous (II-A) vs a chosen baseline vs a scrubbable pair?
- Cross-metric confidence: should limb "muscle-preservation" confidence combine tape with
  lean-mass / skeletal-muscle / body-fat trends and workout history (deterministic joins)?
- Unit / method inconsistency: detect when a region's history mixes units or measurement
  sources (tape vs scan) and mark it `incompatible_history`.
- Left/right timing: how to present a balance number when the two sides were measured on
  different days (II-A flags `different_dates`; the primitive should formalise it).

---

*This is a contract, not a plan of record. Building it requires its own review.*
