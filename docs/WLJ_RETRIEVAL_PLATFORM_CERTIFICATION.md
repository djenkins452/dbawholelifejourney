# WLJ Retrieval Platform — Certification Report

**Date:** 2026-07-23
**Certifies:** HEAD `5b4bd722` against `docs/WLJ_RETRIEVAL_AUTHORITY_AUDIT.md` (the acceptance criteria)
**Method:** mechanical classification pass over **every** key the retrieval surface can serve, plus cross-checks against the canonical authority. Runtime, not inspection.

## VERDICT: ⚠️ **NOT YET COMPLETE** — one structural blocker + 7 residual findings

The retrieval *architecture* is certified. The retrieval *surface* is not yet **mechanically** certifiable, because 9 keys do not declare their authority. That is the blocker, and it is small.

---

## 0. What is certified (do not revisit)

| Certified property | Evidence |
|---|---|
| **Date-scoped metric class eliminated** | `metric_on_date` / `latest_observation_on_or_before`; carry-forward can no longer wear an exact-date key |
| **Incomplete-key-set class eliminated** | Key set now **derived** from `history_capability_index()` — **111 served keys**, complete by construction (`5b4bd722`) |
| **All 102 derived day-keys delegate** | sampled + verified: `authority` present, `semantics=exact_date`, honest `not_recorded` |
| **Natural date authority** | WLJ resolves the year, not the model (`f7cad624`) |
| **Production forensics** | per-turn `turn_id`, `conversation_id`, actual values in `truth_digest` |
| **Contradiction eliminated** | `weight_on` (exact) now agrees with `get_history` |

---

## 1. Deliverable 1 — Remaining Certification Findings

### 🔴 **BLOCKER — F0: certification is not mechanical, because authority is not declared**

The mechanical pass classifies a key by whether its envelope carries `authority`. **All 102 derived keys declare it. None of the 9 curated `_FACT_MAP` keys do.** A machine therefore cannot distinguish:

- `current_medications` — **a compliant projection** (`source: MedicineQueries`, the canonical live Medicine authority), from
- `average_glucose_yesterday` — **a shadow** (`source: SAE.health.glucose_avg_7d`).

Both present identically to a classifier: `authority=absent`. *(My own probe mis-flagged `current_medications` as a shadow for exactly this reason — proof the ambiguity is real, not theoretical.)*

**Why it blocks certification:** the rule requires every surface be *mechanically* classifiable as exactly one of the five conditions. Today 9 keys require human inspection of the source file. **Nothing may remain ambiguous** — and these are ambiguous by construction.

**Smallest compliant change:** every fact returned by this surface declares `authority` (and `semantics`) in its envelope — including snapshot-backed ones (`authority: "SAE.health.glucose_avg_7d"`, `semantics: "rolling_average_7d"`). Then a permanent contract test asserts *every* served key declares an authority, and that no two keys declare the same `(domain, metric, semantics)` triple. **Certification becomes a test, not a review.**

### Residual findings

| # | Finding | Classification | Why it blocks | Smallest compliant change |
|---|---|---|---|---|
| **F1** | `average_glucose_yesterday` — `SAE.health.glucose_avg_7d`; its own note admits *"7-day average; SAE has no yesterday-specific glucose average"*, while derived `glucose_yesterday` delegates exact-date beside it | **Shadow** | Two keys answer "glucose yesterday" with different semantics; snapshots independently | **Rename to `average_glucose_7d`** (the honest name) and declare `semantics: rolling_average_7d`. Renaming — not deleting — preserves the genuinely different question |
| **F2** | `last_glucose_reading` — `SAE.health.latest_glucose`, while its twin `current_weight` was migrated to `latest_observation_on_or_before` | **Shadow** (asymmetric residual) | Snapshots independently; same class already fixed for weight | Add to `_LATEST_OBSERVATION_FACTS` — the one-line delegation proven for `current_weight`. **Must preserve the existing clinical `interpretation` block** (band/display), which is presentation, not truth |
| **F3** | `steps_recent` — SAE `steps_avg_7d`, alongside derived `steps_today`/`steps_yesterday` | **Shadow** (naming) | Name implies recency, serves a 7-day average, snapshots independently | Rename `steps_avg_7d` + declare semantics |
| **F4** | `latest_meal_logged` — SAE `nutrition.last_food_entry`; `NutritionQueries`/`get_entity` own meals | **Shadow** | Snapshots independently over an owned domain | Delegate to the nutrition entity authority |
| **F5** | `average_sleep_7d`, `sleep_trend`, `weight_30_day_change` — SAE-backed aggregates | **Shadow** (strict rule) *— lowest risk* | Violate "never snapshots independently"; overlap `get_history` windows/comparison | Declare authority + semantics; longer term delegate to `get_history` aggregates. **These claim no date scope, so they cannot contradict an exact-date answer** — rank last |
| **F6** | `last_blood_pressure_reading` — SAE `bp_systolic` while `bp_systolic/diastolic/pulse` resolve canonically | **Missing Projection** | Canonical authority exists and is unused | See §5 (product decision) |
| **F7** | `get_domain_state` stale-snapshot freshness defect | **Projection with a defect** | A populated-but-stale snapshot is never refreshed by a read → can disagree with a live authority | **IN FLIGHT** — a concurrent session is editing `domain_state.py` / `state_builder.py` / `state_freshness.py` right now. Verify, do not duplicate |
| **F8** | `top_goal`, `search_history` | **Shadow (latent)** | Duplicate `personal_truth` / `get_entity(contains=)` | Unchanged from the audit; not implicated in any proven production failure |

---

## 2–4. Deliverables 2–4 — Remaining Shadow Authorities / Missing Projections / Missing Authorities

- **Remaining Shadow Authorities:** F1, F2, F3, F4, F5 (7 keys total), plus latent F8.
- **Remaining Missing Projections:** **F6 blood pressure**; latest-observation projections for metrics other than weight (only `current_weight` is projected today, though the authority is generic); body measurements / sleep detail / labs remain audit-listed candidates.
- **Remaining Missing Authorities:** **none in health.** Only the two cross-cutting gaps stand: **arbitrary windowed counts** ("how many X this week") and **cross-domain comparison**. Blood pressure is *not* one — corrected in `ac8a3c41`.

---

## 5. Blood Pressure — the product decision (no implementation)

**Which tool should expose BP, and at what granularity?**

**Recommendation: BOTH, with a strict split — and no new authority.**

1. **Raw metrics stay on `get_history`** (`bp_systolic`, `bp_diastolic`, `bp_pulse`) — correct for trends, timelines, averages, comparisons. Already canonical, already working, already date-scoped through `metric_date`. **Unchanged.**
2. **Add ONE composite *projection* for the clinical reading.** A blood-pressure reading is clinically **one fact — "118/76"** — not three independent metrics. If retrieval exposes only three separate metrics, then answering *"what's my blood pressure?"* requires the **model** to issue three retrievals and pair them into a clinical reading. That is composition-by-model — precisely what WLJ must own deterministically, and exactly the seam where a systolic from one date could get paired with a diastolic from another.

**Constraints (this is a projection, not an authority):**
- It **delegates** to the three canonical metrics via `latest_observation_on_or_before` / `metric_on_date`.
- It **computes nothing** — it pairs values already returned.
- It must **refuse to pair across dates**: if systolic and diastolic resolve to different `observed_on`, that is a truthful integrity failure, not a reading. One envelope, one `observed_on`.
- Smallest change: re-point the existing `last_blood_pressure_reading` key to this composite projection (the key already exists and is already what the model reaches for).

This is a product decision layered on a certified authority — it adds a *name for a composed reading*, not a second producer.

---

## 6. Deliverable 6 — Can certification be declared COMPLETE?

**No — but it is close, and what remains is mechanical, not architectural.**

Nothing remaining requires architectural discovery. Every finding has a known, proven-shaped fix:
- **F0** makes certification a test instead of a review (the true blocker).
- **F1–F5** are the *same* delegation/rename already proven for weight, steps, calories, protein.
- **F6** is the one-line delegation proven for `current_weight`, plus the composite decision above.
- **F7** is in flight; **F8** is latent and unproven in production.

### Recommended closing sequence (one commit each, smallest-first)
1. **F0** — declare `authority` + `semantics` on every served fact; add the contract test *(unlocks mechanical certification)*.
2. **F1–F4** — delegate or rename the four keys that claim a scope they do not honor.
3. **F6** — BP composite projection.
4. **F5** — declare/delegate the three aggregates.
5. **Verify F7** (do not duplicate); defer **F8**.

### Permanent regression tests protecting this architecture
Already in place: `test_metric_date_authority`, `test_truth_subject_anchoring`, `test_domain_history_natural_dates`, `test_domain_history`, `test_health_facts`, `test_foundation_validation`, `test_truth_surface_contract`, `test_daily_health_queries`, plus `test_request_path_safety_contract` and `test_constitution_contract`.
**Missing — and required to close certification: the F0 single-authority contract test.** That test is what makes this document self-enforcing rather than a point-in-time review.

---

## 7. Coordination note

A concurrent session is actively editing `domain_state.py`, `state_builder.py`, `state_freshness.py` (F7) and has recently edited `health_facts.py` (F1–F5 territory). **F1–F6 all live in `health_facts.py`.** Assign these to one session to avoid two sessions creating authorities while removing one.

---

*Mechanical certification pass run against HEAD `5b4bd722`; probe was throwaway and not committed. No production code modified by this certification.*
