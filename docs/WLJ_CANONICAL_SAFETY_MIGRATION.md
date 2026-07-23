# Canonical Safety Migration — platform pattern

**Date:** 2026-07-23 · **Type:** platform-quality pass (not a glucose fix)
**Rule:** *A canonical authority must own validation, temporal integrity, deterministic safety, provenance, confidence and freshness. Projection layers may only EXPOSE already-safe truth — never be the place truth is made safe.*

## 1. Canonical Safety Inventory — where safety actually lives

**Headline finding: safety was already platform-owned. The snapshot path did not own it — it merely SURFACED a precomputed warning.**

| Safety behavior | Owner (today) | Snapshot-owned? |
|---|---|---|
| Future-timestamp rejection | `apps/core/truth/temporal.py :: is_future` (5-min tolerance) | ❌ platform |
| Impossible-evidence verdict + investigation wording | `apps/core/truth/integrity.py :: validate_evidence / attach` | ❌ platform |
| Impossible temporal ordering (`future_predecessor`, duplicate/out-of-order previous) | `integrity.py` | ❌ platform |
| Stale-as-current | `integrity.py` (`presented_as`) | ❌ platform |
| Freshness classification | `apps/core/truth/freshness.py` | ❌ platform |
| Confidence | `apps/core/truth/confidence.py` | ❌ platform |
| Provenance | canonical accessors (`glucose_queries._source_label`, `metric_date._fact`) | ❌ canonical |
| Clinical interpretation (glucose band) | `glucose_interpretation.interpret` — **presentation derived from the value**, re-derived per call | ❌ not truth |

**Correction to the previous session's conclusion (recorded honestly).** The prior pass reported that delegating `last_glucose_reading` "regresses a clinical-safety behavior." **That was wrong.** The failing tests mocked SAE state and passed `user=None`, so they exercised the *snapshot surfacing path*, not the guard. Runtime-proven on a **real future-dated `GlucoseEntry`** through the canonical path:

```
glucose_queries.latest  -> {value 95, recorded_at <future>, freshness current}
integrity.attach        -> integrity.ok = False
                           violations = [future_timestamp / temporal / impossible]
                           investigation message attached
                           recorded_at DROPPED   ("recorded_at" in fact -> False)
                           value preserved (95)
```

Identical to the SAE behavior (`temporal_warning` + dropped timestamp). **No guard needed relocating** — `integrity.attach` already validates a live `recorded_at` directly (`integrity.py` checks `_temporal.is_future(recorded_at, now)`), independent of SAE.

## 2. Safety behaviors moved into canonical authorities
**None required moving.** The reusable platform helper the brief anticipated **already exists**: `apps/core/truth/integrity.py :: attach`. The generalizable rule is therefore not "build a helper" but:

> **Every projection must pass its assembled fact through `integrity.attach` before returning it.**

Verified compliant: `metric_date._fact` · `_previous_glucose_fact` · `_latest_glucose_fact` · `_blood_pressure_fact`. **No new authority was created.**

## 3. Remaining snapshot-owned safety behaviors
- **`average_glucose_yesterday`, `steps_recent`, `average_sleep_7d`, `sleep_trend`, `weight_30_day_change`** — still read SAE. They carry **no timestamp**, so no temporal guard applies; their residual risk is *naming/semantics* (F1/F3/F5), not safety.
- **SAE's own precomputed `*_warning` fields** remain honoured by `integrity.validate_evidence` (a `temporal_warning` is still treated as a future-timestamp violation), so any surface still on SAE keeps its guard.

## 4. Verification that no migrated retrieval regressed safety

| Migrated key | Authority | Safety verified |
|---|---|---|
| `current_weight` | `metric_date.latest_observation_on_or_before` | envelope + integrity via `_fact` |
| derived `*_today` / `*_yesterday` (102) | `metric_date.metric_on_date` | envelope + integrity via `_fact` |
| **`last_glucose_reading` (F2 ✅)** | `glucose_queries.latest` | **future timestamp flagged + dropped, proven on a live row**; clinical interpretation re-derived, not carried |
| **`latest_meal_logged` (F4 ✅)** | `NutritionQueries.last_entry` | no timestamp claim; honest `not_recorded` |
| **`last_blood_pressure_reading` (F6 ✅)** | composite over `bp_systolic/diastolic/pulse` | integrity attached; refuses to pair across observations |

**Regression: 112 scoped tests green** + **71 gate tests** (request-path safety · constitution · natural dates · truth surface · calendar-bound truth · daily health queries). `check` clean; no migrations.

**Safety tests were migrated, not deleted** — `test_temporal_sanity` and `test_evidence_integrity` now seed a **real future-dated reading** and assert the *invariant* (flagged, timestamp dropped, never presented as a sound value) rather than one implementation's wording.

**One production regression caught during this pass:** deleting a key's `_FACT_MAP` spec also dropped it from `model_facing_facts()`, silently un-advertising it to the model — a delegation quietly becoming a removal. Fixed via `_DELEGATED_CURATED_KEYS`, which keeps delegated keys served *and* advertised.

**Wire vs registry:** `stamp()` now puts only `authority` + `semantics` on the wire (what a consumer needs to judge a value); `truth_category` / `classification` / `delegates_to` stay in the declaration registry for certification. Caught by a payload-size test — the metadata contract must not tax every call.

## 5. Recommendation — can Health Retrieval Certification close?

**Not yet — but only naming residuals remain, and none are safety.**

| Finding | Status |
|---|---|
| F2 `last_glucose_reading` | ✅ **CLOSED** (delegated; safety proven) |
| F4 `latest_meal_logged` | ✅ **CLOSED** |
| F6 blood pressure | ✅ **CLOSED** |
| F1 `average_glucose_yesterday` | ❌ open — **rename** (`average_glucose_7d`) |
| F3 `steps_recent` | ❌ open — **rename** (`steps_avg_7d`) |
| F5 sleep/weight aggregates (×3) | ❌ open — declare/delegate |
| F7 `get_domain_state` | ◐ freshness closed; **contract not adopted** |

**Ratchet now pins 5 defects, down from 8.** All remaining are naming/semantics or contract-adoption — **zero are safety, and zero are architectural.**

**Recommendation:** close Health Retrieval Certification after F1/F3 (two renames, blast radius already measured into the second runtime) and F5. F7 and the unbound surfaces (personal truth, standing context, page summaries, briefings, decision/execution truth) belong to the platform-wide contract rollout, not Health.
