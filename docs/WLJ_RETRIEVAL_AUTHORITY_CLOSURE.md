# Retrieval Authority Certification — Closure Report

**Date:** 2026-07-23 · **Baseline:** `49d9e0d1` + this change
**Acceptance mechanism:** the certified metadata contract + ratchet (`apps/core/truth/authority.py`, `test_retrieval_authority_contract.py`)

## VERDICT: ⚠️ **NOT COMPLETE** — framework certified, surfaces partially certified

Per the two-level distinction: **the Retrieval Authority Framework is certified; individual retrieval surfaces are not yet all compliant.** A declared `shadow_authority` is visible and contained, but it is not compliant. Three of six residuals remain open, and one is **blocked by a safety finding** that changes its cost.

---

## 1. Residual closure matrix

| # | Finding | Status | Evidence |
|---|---|---|---|
| **F6** | BP composite projection | ✅ **CLOSED** | Implemented as a projection over canonical `bp_systolic`/`bp_diastolic`/`bp_pulse`. Runtime: `{status: ok, value: 118, diastolic: 76, pulse: 64, reading: "118/76", observed_on, semantics: latest_on_or_before, classification: projection, freshness, confidence, age_days}`; no data → honest `not_recorded`. Raw metrics still retrievable via `get_history`. **No new authority.** |
| **F2** | `last_glucose_reading` | 🔴 **BLOCKED — safety finding** | Delegation to `glucose_queries.latest` was implemented, **runtime-tested, and REVERTED**. The **future-timestamp guard** (drop an impossible time + flag it) lives in the SAE path in `health_facts.py`, **not** in `glucose_queries` (`_row_to_reading` computes freshness only). Delegating as-is **regresses a clinical-safety behavior** — proven by 2 failing `test_temporal_sanity` cases. Closing F2 requires **first relocating that guard into the canonical accessor**. |
| **F4** | `latest_meal_logged` | ⏸ **Deferred with F2** | Delegation to `NutritionQueries.last_entry` was implemented and reverted alongside F2 — both intercept the same serve path and should land together once F2's guard is relocated. |
| **F1** | `average_glucose_yesterday` | ❌ **Open (rename)** | Blast radius **measured**: the second runtime (`chatgpt_cos/foundational_facts.py` classifier, `conversation_memory`, `conversation_object`, `service.py`) + 5 test modules. Not a one-line change. |
| **F3** | `steps_recent` | ❌ **Open (rename)** | Same shape; `foundational_facts.py` (×4) + `conversation_memory` + tests. |
| **F5** | `average_sleep_7d`, `sleep_trend`, `weight_30_day_change` | ❌ **Open (declared)** | Enumerated mechanically via declarations, not names. **Lowest risk: none claims a date scope, so none can contradict an exact-date answer.** |
| **F7** | `get_domain_state` | ◐ **Freshness closed; contract NOT adopted** | `49d9e0d1` added `ensure_fresh` self-heal, day-stamped freshness, and honest `pending`/`ready`. **But it declares no authority/semantics** — it does not yet participate in the contract. Smallest correction: surface-level declaration (SAE = store, module builders = authority). **No competing implementation written.** |
| **F8** | `top_goal`, `search_history` | 📌 **Latent, recorded** | Not serving conflicting truth today; no active violation observed at runtime. Recorded as backlog rather than speculative refactor, per instruction. |

## 2. Certified retrieval surfaces
- ✅ **`get_foundational_health_facts`** — fully in the contract: **127 served keys, 127 declared, zero anonymous**; 102 derived day-keys all delegate to the systematic authority.
- ✅ **`metric_date`** (date-scoped authority) · **`get_history`** · **`get_entity`** — canonical, envelope-complete.
- ◐ **`get_domain_state`** — freshness-correct, contract not yet adopted (F7).
- ⬜ **Not yet in the contract:** personal truth · standing context · page summaries · executive briefings · decision/execution truth. These were inventoried in the audit but have **not** been bound to the metadata contract.

## 3. Explicitly accepted residuals (safe, disclosed)
- **`sleep_last_night`** — a *disclosed* residual, not a shadow: it delegates to `CurrentHealth.latest_sleep` and declares `semantics: latest_observation`. Night-of vs wake-date is a separate truth question needing its own runtime proof.
- **F5 aggregates** — declared shadows that claim **no date scope**, so they cannot contradict an exact-date answer. Contained by the ratchet.
- **BP cross-date refusal is defensive, not currently reachable** — `BloodPressureEntry` co-locates systolic/diastolic in one row, so components share an observation by construction. The guard costs nothing and protects if a future source ever populates them independently.

## 4. Permanent regression-test inventory
`test_retrieval_authority_contract` (**contract + ratchet**) · `test_metric_date_authority` · `test_truth_subject_anchoring` · `test_domain_history_natural_dates` · `test_domain_history` · `test_health_facts` · `test_foundation_validation` · `test_truth_surface_contract` · `test_daily_health_queries` · `test_temporal_sanity` · `test_evidence_integrity` · `test_calendar_bound_truth` · `test_request_path_safety_contract` · `test_constitution_contract`.

## 5. Runtime certification results
- **F6 BP:** complete reading composed from canonical components with full envelope; honest `not_recorded` with no data.
- **Regression:** 86 impacted tests green (contract, temporal sanity, evidence integrity, health facts, foundation validation, glucose aliases/interpretation, metric-date authority).
- **Gates:** 75 green (contract · request-path safety · constitution · natural dates · truth surface · calendar-bound truth). `check` clean; `makemigrations --check` → no changes.

## 6. What remains before COMPLETE
1. **Relocate the glucose future-timestamp guard** into `glucose_queries` (or the shared integrity layer) → then land **F2 + F4** together.
2. **F1 + F3 renames** with the second-runtime classifier updated (blast radius measured above).
3. **F5** — delegate the three aggregates to `get_history` windows.
4. **F7** — bind `get_domain_state` to the contract.
5. **Bind the remaining foundational surfaces** (personal truth, standing context, page summaries, briefings, decision/execution truth).

**The framework holds the line meanwhile:** every remaining defect is declared, pinned, and cannot grow — a new anonymous key or new shadow fails the build.
