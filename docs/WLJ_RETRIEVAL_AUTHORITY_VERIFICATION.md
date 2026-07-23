# Retrieval Authority — Implementation Verification

**Date:** 2026-07-23
**Verifies:** `140e6c3c` (Single Date-Scoped Metric Authority) **against** `docs/WLJ_RETRIEVAL_AUTHORITY_AUDIT.md` (`f86cc421`)
**Method:** runtime probes against the canonical providers + a live multi-turn `CoSGateway` conversation. Neither the audit nor the implementation was assumed correct.
**Headline:** the implementation **satisfies the audit's core findings and exceeds them in two places** — and the verification **found an error in the audit itself** (blood pressure was mis-classified).

---

## 1. Deliverable 1 — Audit vs Implementation

| # | Audit finding | Status | Evidence |
|---|---|---|---|
| 1 | Shadow: `get_foundational_health_facts` metric-on-a-day keys | ✅ **Implemented** | `_DATE_SCOPED_FACTS` → `metric_date.metric_on_date`; duplicate `_FACT_MAP` SAE specs **deleted, not dormant** |
| 2 | Shadow: `current_weight` (envelope-less, not date-scoped) | ✅ **Implemented** | → `latest_observation_on_or_before`; runtime: `value 298.3, observed_on 2026-04-14, age_days 100, freshness stale, confidence low, exact false` |
| 3 | Shadow: A1 carry-forward vs A3 windowed contradiction | ✅ **Implemented** | `DailyHealthQueries.weight_on` now exact-date (`no_data`); `get_history` yesterday `empty` — **they now agree**; `weight_latest_on_or_before` added |
| 4 | Protein false-zero class | ✅ **Implemented** | `protein_today` → `status:"not_recorded"` + full envelope (was `value: 0.0`) |
| 5 | Audit layer: values never recorded | ✅ **Implemented** | `truth_digest` records `value/unit/semantics/observed_on/age_days/exact/freshness/confidence/authority` |
| 6 | Audit layer: `turn_id` not per-turn | ✅ **Implemented** | live 2-turn conversation → **2 distinct `turn_id`s**, `conversation_id=188` kept separately (migration `ai.0037`) |
| 7 | Envelope on every health fact | ✅ **Implemented** | `_fact()` complete by contract, via shared `classify_period_freshness` / `confidence_from_freshness` |
| 8 | Collapse `top_goal` duplication | ❌ **Not implemented** | still in `foundational_facts.GOAL_FACT_KEYS` |
| 9 | Resolve `search_history` vs `get_entity(contains=)` | ❌ **Not implemented** | unchanged |
| 10 | `get_domain_state` freshness defect (stale snapshot never refreshed by a read) | ❌ **Not addressed** | unchanged |

### Implemented **differently — and better** than the audit proposed
- **The audit under-specified the fix.** It proposed "make the surface a projection and auto-derive the key set from `history_metrics × periods`." The implementation instead named **two semantics explicitly** — `exact_date` vs `latest_on_or_before`. This is **stronger**: auto-derivation would have made the key set *complete*, but the real defect was that carry-forward and exact-date were **conflatable**. Naming them makes the contradiction structurally impossible, which completeness alone would not have achieved. Carry-forward can no longer wear an exact-date key.
- **Retrieval anchoring** (not in the audit): active subject is now derived from **every** successful truth retrieval, not only `get_entity`. Verified live — *"Yesterday's?"* correctly anchored to weight (previously drifted to Journal).
- **`not_recorded` vs `unknown`** are now distinct states — an honest absence is no longer indistinguishable from a provider miss.

---

## 2. Deliverable 2 — Retrieval Authority verification matrix

### 2.1 The Date-Scoped Metric Authority (`metric_date.py`)
- **Delegates only.** `_series()` → `get_domain_history(period="custom", start, end)` — the same producer behind `get_history`. **No ORM access, no date math, no second retrieval path.** Verified by reading the full module.
- **Composes correctly with Milestone 1** — passes `date` objects, so natural-phrase resolution is bypassed and explicit dates are honored.
- **Complete caller map** (module consumers; `metric_date` as a *model field name* elsewhere is unrelated):

| Caller | Keys | Semantic | Verified |
|---|---|---|---|
| `health_facts._day_fact` | `steps_today/yesterday`, `weight_yesterday`, `glucose_yesterday`, `calories_today/yesterday`, `protein_today` | `exact_date` | ✅ |
| `health_facts._latest_observation_fact` | `current_weight` | `latest_on_or_before` | ✅ |
| `apps/ai/tests/test_metric_date_authority.py` | — | both | ✅ |

**No other caller computes date-scoped metrics independently** for these keys. `foundational_facts.py` (the ChatGPT-CoS runtime) reaches the same values through `fact_registry` → `_health_fact_provider` → `get_foundational_health_facts`, so it inherits the delegation rather than duplicating it.

### 2.2 Retrieval Topology (verified)

| Question | Tool | Retrieval surface | Canonical authority | Truth producer | Verdict |
|---|---|---|---|---|---|
| **weight on date** | `get_history(period="July 4")` | `domain_history` | `get_history` | `WeightEntry` | ✅ (M1) |
| **current weight** | `get_foundational_health_facts(current_weight)` | `health_facts` → `metric_date` | `latest_observation_on_or_before` → `get_domain_history` | `WeightEntry` | ✅ live: *"280.4 lb, recorded today"* (`exact:true, age_days:0`) |
| **weight yesterday** | `get_history(weight, yesterday)` | `domain_history` | `get_history` | `WeightEntry` | ✅ live: **281.5** — anchored, no contradiction |
| **protein yesterday** | `get_history(nutrition, protein, yesterday)` | `domain_history` | `get_history` | `FoodEntry` | ✅ 75 g; curated key now honest `not_recorded` |
| **latest protein** | *(no `protein` latest key)* | — | `latest_observation_on_or_before` exists | `FoodEntry` | ⚠️ **Missing Projection** — authority reachable, no curated key delegates |
| **last pizza** | `get_entity(nutrition, meal, contains=pizza)` | `domain_entity` | `get_entity` | `FoodEntry` | ✅ unchanged |
| **calf raises** | `get_entity(health, workout)` | `domain_entity` | `get_entity` | `WorkoutSession/Exercise/Set` | ✅ unchanged |
| **mission** | `get_user_truth(section=goals)` | `personal_truth` | `personal_truth` | `LifeGoal` | ✅ (latent `top_goal` dup) |

---

## 3. Deliverable 3 — Remaining Shadow Authorities *(runtime-verified)*

| Shadow | Evidence | Owning authority | Smallest correction |
|---|---|---|---|
| **`average_glucose_yesterday`** | Still a `_FACT_MAP` SAE spec; **its own note admits "7-day average; SAE has no yesterday-specific glucose average."** A key named `_yesterday` does not answer a date-scoped question — while `glucose_yesterday` delegates correctly right beside it. Probe: returns `unknown`, whereas `get_history(health, glucose, yesterday)` = **110**. | `get_history` / `metric_date` | Either delegate it to `metric_date` (exact-date) **or rename it `average_glucose_7d`** so the name stops claiming a date scope. |
| **`last_glucose_reading`** | Latest-observation key **still on SAE** (`latest_glucose`) — probe returns `unknown`, while `latest_observation_on_or_before(health, glucose, today)` returns **110, observed_on 2026-07-22, age_days 1**. This is **exactly the `current_weight` defect, unfixed for glucose** — an asymmetric residual. | `latest_observation_on_or_before` | Add to `_LATEST_OBSERVATION_FACTS` — a one-line delegation, identical to `current_weight`. |
| `steps_recent` | 7-day average under a name that reads as "recent steps" | `get_history` | Rename or delegate (minor). |
| `top_goal` (latent) | Duplicates `personal_truth` mission identity | `personal_truth` | Remove/redirect. |
| `search_history` (latent) | Separate registry from `DomainTruth` | one substring authority | Decide one owner. |

> **Environmental caveat, stated honestly:** the probe ran with a **cold SAE**, so SAE-backed keys returned `unknown`. In production (warm SAE) these two keys would return *values* — a 7-day average and a latest reading — which can **disagree** with the exact-date authority. Cold SAE makes the defect visible; it does not create it. Both keys are shadows **by construction** (they do not delegate), independent of environment.

**`sleep_last_night` is an accepted, disclosed residual, not a shadow** — it is deliberately kept on `CurrentHealth.latest_sleep` with `semantics: "latest_observation"` disclosed, and the reason is logged (night-of vs wake-date is a separate truth question needing its own proof). Disclosing rather than guessing is correct.

---

## 4. Deliverables 4 & 5 — Remaining Missing Projections / Missing Authorities

### Missing Projection (authority exists; nothing exposes it)
1. **Blood pressure** — **RECLASSIFIED, see §5.**
2. **Latest protein / latest glucose / other latest-observation metrics** — `latest_observation_on_or_before` works for any history metric, but only `current_weight` is projected.
3. Body measurements, sleep detail, labs — unchanged from the audit; still candidates requiring a capability-index check.

### Missing Authority (no canonical owner)
- **Arbitrary windowed counts** ("how many X this week") — unchanged.
- **Cross-domain comparison** — unchanged.
- *(Blood pressure has been **removed** from this list.)*

---

## 5. Blood Pressure — classification only (no implementation)

**BP was mis-classified in the audit. It is NOT a Missing Authority.**

The audit probed `get_history("health", "blood_pressure")` → `unsupported` and read a truncated `supported_metrics` list. The correct metric names are **`bp_systolic` / `bp_diastolic` / `bp_pulse`**, and they are registered health history metrics. Verified:

```
get_history(health, bp_systolic,  yesterday) -> ready, 118.0 mmHg
get_history(health, bp_diastolic, yesterday) -> ready,  76.0 mmHg
get_history(health, bp_pulse,     yesterday) -> ready,  64.0 bpm
metric_on_date(health, bp_systolic, yesterday)
    -> ok, semantics=exact_date, 118.0, observed_on 2026-07-22, confidence high
latest_observation_on_or_before(health, bp_systolic, today)
    -> ok, semantics=latest_on_or_before, 118.0, age_days 1
```

**Correct classification: MISSING PROJECTION.** A canonical live authority exists and fully works — including through the new date-scoped authority. What is missing is the projection: `last_blood_pressure_reading` still reads the SAE snapshot (`bp_systolic` field) instead of delegating, and no curated key composes systolic+diastolic into one reading.

The refactor **did not change BP's implementation**, but it **changed what the right fix is**: Milestone 3 is no longer "investigate and create a BP authority." It is the **same one-line delegation already proven for `current_weight`**, plus a composite-reading decision (systolic+diastolic as one fact). Materially smaller and lower-risk than the audit implied.

---

## 6. Deliverable 6 — Is Retrieval Authority Cleanup complete?

**Not yet — but the hard part is done and verified.**

**Certified complete:**
- ✅ The **weight/protein date-scoped parallel-authority class is eliminated** — the two contradicting authorities now agree, verified at the provider level and end-to-end through a live conversation.
- ✅ **Carry-forward can no longer masquerade as exact-date** — the structural fix.
- ✅ **Production forensics now work** — all five investigator questions are answerable.
- ✅ 91 scoped tests green (`metric_date_authority`, `truth_subject_anchoring`, `domain_history_natural_dates`, `domain_history`, `daily_health_queries`, `truth_surface_contract`, plus request-path-safety and constitution gates).

**Blocking completion:** two **same-class** glucose residuals (`average_glucose_yesterday`, `last_glucose_reading`) that the refactor fixed for weight/steps/calories/protein but not glucose. These are not new architecture — they are the *identical* mechanical delegation, already proven.

### Recommendation
1. **Milestone 2b (small, mechanical):** delegate `last_glucose_reading` → `latest_observation_on_or_before`; delegate-or-rename `average_glucose_yesterday` and `steps_recent` so no key name claims a scope it does not honor. This finishes the class the refactor started.
2. **Then Milestone 3 (BP) — now re-scoped** from "create an authority" to "project the existing one," identical in shape to 2b.
3. Defer `top_goal`, `search_history`, and the `get_domain_state` freshness defect to a later pass — they are latent, not implicated in a proven production failure.

**2b and 3 are the same fix applied to three more keys.** Doing them together is lower-risk than sequencing them apart.

---

*Verification probes were throwaway (one hit OpenAI) and were not committed. No production code was modified by this verification.*
