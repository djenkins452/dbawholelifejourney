# Operations Truth Path — Divergence Investigation

**Status:** INVESTIGATION COMPLETE — findings only. **No corrective code implemented.** Awaiting approval before any correction.
**Date:** 2026-07-19
**Trigger:** Clara reported Operations degraded, then reported recovery and the indicator beside Clara showed green **100%**. Immediately afterward the Operations Wall showed **Operational Health 51 · DEGRADED · Medium customer impact · 5 active incidents · critical scheduled-task failure · recommended operator action.**
**Question posed:** which surface is wrong — the Wall, the CoS, or are consumers reading different authorities?

> **Verdict:** **Neither surface was stale and neither was "wrong."** They were reporting **different authorities**. Two independent operational-health scoring systems exist, and the green "100%" the operator read was **not an Operations indicator at all**. (Hypothesis 3 of 4, with a contributing element of 4.)

---

## 1. Complete Operations truth flow (as-built, traced)

| Stage | Producer (file:line) | Authoritative object | Cadence | Cache | Consumer |
|---|---|---|---|---|---|
| Detection (anomalies) | `same_engine.run_same` detectors (`same_engine.py:60‑79`) | in-memory descriptors | SAME cycle **60s** (`run_same_cycle_task`) | — | `_reconcile_anomalies` |
| Incident lifecycle | `_reconcile_anomalies` (SAME) | **`OpsAnomaly`** (`is_active`, `resolved_at`) | 60s | `wlj:ops:active_anomalies` 10s | `anomalies` section, executive |
| Integrity score | `same_engine.py:1510` `SystemIntegritySnapshot.objects.create(...)` | **`SystemIntegritySnapshot`** (`score`, `posture`) | 60s | `wlj:ops:latest_integrity` 10s | `integrity` section, executive |
| Executive summary | `ops_executive.build_executive_summary` (called last in payload build) | `executive` section | 60s | in payload | Wall, CoS banner/dot |
| Ops payload | `ops_telemetry.build_ops_stream_payload` | `wlj:ops:stream_payload` | 60s (SAME) | that key | `OpsStreamView` |
| Operations Wall | `OpsStreamView` → cached payload | — | browser poll **10s** | 10s section caches | operator |
| CoS status dot | `apps/ai/operations_banner.get_customer_operations_status` → `payload["executive"]["overall_status"]` | same executive | browser poll **60s** | payload | CoS header icon |
| **COAS scores** | `apps/core/jobs.py:294` `compute_all_scores()` → `save_health_snapshot()` | **`COASHealthSnapshot`** | **`core.check_system_health` every 300s** | — | `operational_alerts` |
| **CoS operational messages** | `operational_alerts.check_and_alert(scores)` → `OperationalAlert` → `_inject_admin_alert` | **`OperationalAlert`** | 300s | — | **Clara's degraded/recovered messages** |
| Alignment badge ("100%") | `context_processors.py:275‑301` → `compute_alignment_score(user)` | alignment score | on request | **15 min** per-user cache | header badge beside Clara |

## 2. Authority diagram (as-built — note the parallel branch)

```
                    ┌──────────────── SAME cycle (60s) ─────────────────┐
 detectors ──▶ OpsAnomaly (incident lifecycle) ──┐
                                                 ├─▶ executive ──▶ payload ──▶ Wall (10s poll)
            SystemIntegritySnapshot (score 51) ──┘                     └──▶ CoS ops dot (60s poll)
                    └───────────────────────────────────────────────────┘

                    ┌────────── COAS job (300s) — SEPARATE AUTHORITY ───────────┐
 compute_all_scores ──▶ COASHealthSnapshot ──▶ OperationalAlert ──▶ Clara's "degraded"/"recovered" messages
                    └───────────────────────────────────────────────────────────┘

 compute_alignment_score ──▶ (15-min cache, FAILS OPEN TO 100) ──▶ green "100%" badge beside Clara
                                                                    ⚠ NOT Operations truth
```

**There is NOT exactly one deterministic executive Operations authority. There are two operational scoring authorities, plus a non-Operations badge that reads like one.**

## 3. What drives each surface (§2 of the request)

| Surface | Source of truth | Authority |
|---|---|---|
| **A. Green/“100%” badge beside Clara** | `compute_alignment_score()` — **plan/commitment alignment** | ❌ **not Operations** |
| A′. 🟢🟡🔴 ops dot on the Operations icon | `executive.overall_status` | ✅ Integrity/executive |
| A″. CoS panel "Status" tab badge | pending **blueprint interventions** count | ❌ not Operations |
| **B. Executive Summary** | `build_executive_summary(sections)` | ✅ Integrity/executive |
| **C. Operational Health score** | `integrity.score` (`SystemIntegritySnapshot`); `executive.score.value = integrity.score` (`ops_executive.py:737`) | ✅ same |
| **D. Active Incidents** | `OpsAnomaly.is_active` via SAME reconcile | ✅ same |
| **E. Recommended Action** | `executive.recommended_action` (top incident) | ✅ derived |
| **F. Customer Impact** | `executive.customer_impact` (derived from anomalies+sections) | ✅ derived |
| **G. Recovery banner** | `RecoveryAttempt` 24h telemetry (now active-gated) | ✅ derived |
| **H. Operations notifications (Clara's messages)** | **COAS scores → `OperationalAlert`** | ❌ **different authority** |

## 4. Root cause of the divergence

**Two independent scoring systems with different scales, thresholds, engines, models, and cadences:**

| | Integrity (Wall + Executive + ops dot) | COAS (Clara's messages) |
|---|---|---|
| Model | `SystemIntegritySnapshot` | `COASHealthSnapshot` |
| Producer | SAME cycle | `core.check_system_health` |
| Cadence | **60s** | **300s** |
| Bands | OPTIMAL 90‑100 · NOMINAL 70‑89 · **DEGRADED 40‑69** · CRITICAL 0‑39 (`same_engine.py:1289‑1292`) | **HEALTHY ≥ 80** · alert < 60 · critical < 40 (`operational_alerts.py:31‑33`) |

A COAS subsystem returning to **≥ 80** resolves its `OperationalAlert` and fires Clara's **"recovered"** message — while Integrity can simultaneously be **51 → DEGRADED** with 5 `OpsAnomaly` rows still `is_active`. **Both statements were true of their own authority at the same instant.**

**Compounding factor (the green 100%):** the badge the operator actually looked at is the **alignment badge** — verified in the DOM as `class="cos-alignment-badge align-good"`, text `100%`, `href="/assistant/cos/settings/"`, `title="Status — Click for details"`. It is a *personal planning* metric, **cached 15 minutes**, and **fails open to a hardcoded `alignment_score: 100`** on any exception (`context_processors.py:297‑301`). A green badge literally titled **"Status"** sitting beside the assistant is read as system status by an operator at 2 AM.

## 5. Duplicate/competing authorities discovered

1. **Operational health score** — `SystemIntegritySnapshot` **vs** `COASHealthSnapshot` (two scores, two cadences, two band sets).
2. **Incident/alert lifecycle** — `OpsAnomaly` (SAME reconcile) **vs** `OperationalAlert` (COAS state-change). These open/resolve **independently**; COAS resolution does not consult, and does not resolve, `OpsAnomaly`.
3. **"Status"-looking surfaces that are not Operations** — the alignment badge ("100%", titled "Status") and the CoS panel "Status" tab badge (interventions count).

*Consumer bypassing the executive:* **Clara's operational notifications** — they are produced from COAS scores and never consult `executive`. Every other Operations surface (Wall, ops dot, banner) correctly derives from the executive/integrity authority.

## 6. Incident reconstruction (2026-07-19 morning)

| Observation | Maps to | Verdict |
|---|---|---|
| Clara: "Operations degraded" | COAS subsystem score fell < 60 → `OperationalAlert` created → injected | COAS authority, 300s cadence |
| Clara: "recovered" + alert cleared | that COAS subsystem returned **≥ 80** → alert resolved → recovery note | COAS authority — correct *by its own rules* |
| Green **100%** beside Clara | **alignment badge** (15-min cache, fails open to 100) | **never Operations truth** |
| Wall: score **51**, DEGRADED | `SystemIntegritySnapshot.score = 51` → posture DEGRADED (40‑69 band) | Integrity authority |
| Wall: **5 active incidents**, critical scheduled-task failure, recommended action | 5 `OpsAnomaly.is_active` rows → `executive.incidents` / `recommended_action` | Integrity/executive authority |

**Answers:** *Was the Wall stale?* **No** — it is the freshest surface (60s recompute + 10s caches + 10s poll ⇒ worst case ≈ 70‑80s). *Was Clara wrong?* **No** — her message was correct for the COAS authority. *Were the incidents actually active?* **Yes** — `OpsAnomaly.is_active` is the lifecycle truth and the Wall reads it live; COAS recovery does not resolve `OpsAnomaly`. *Was the Executive Summary incorrect?* **No** — `executive.overall_status`/score derive from the same integrity snapshot the Wall displayed and were self-consistent.

*Evidence boundary:* the mechanism, thresholds, cadences, and surface bindings above are proven from code and a live DOM check. The row-level per-incident timeline (exact `OpsAnomaly`/`COASHealthSnapshot`/`OperationalAlert` rows and timestamps) was **not** queried — that requires a production read, which was out of scope for an investigation-only milestone.

## 7. Divergence budget (staleness analysis)

| Surface | Recompute | Read cache | Client poll | Max divergence vs Integrity truth |
|---|---|---|---|---|
| Operations Wall | 60s | 10s | 10s | **≈ 80s** |
| CoS ops dot | 60s | — | 60s | **≈ 120s** |
| Clara's operational messages | **300s** | — | event-driven | **≈ 5 min + threshold mismatch (unbounded semantic divergence)** |
| Alignment "100%" badge | on request | **15 min** | page load | **15 min — or permanently wrong (fails open to 100)** |

The Wall–vs–CoS-message divergence is therefore **not primarily latency**; it is **semantic** (different scores, different thresholds). Latency alone caps at ~5 min; the threshold mismatch can diverge indefinitely.

## 8. Recommended architectural correction (NOT implemented — for approval)

Target: `Detection → Incident Truth → Executive Operations Truth → every consumer.`

1. **Make the Executive the single operational authority for *notifications*.** Clara's degraded/recovered messages should derive from `executive.overall_status` (+ its incident lifecycle), exactly as the ops dot and banner already do — not from COAS scores. This removes the semantic divergence at its source.
2. **Demote COAS to an input, not an authority.** Keep COAS scoring as a *contributor* feeding the integrity computation (or retire the duplicate score), so exactly one operational score exists. Do not maintain two band sets.
3. **Unify the incident lifecycle.** `OperationalAlert` and `OpsAnomaly` should not open/resolve independently; one lifecycle, or `OperationalAlert` becomes a projection of `OpsAnomaly`.
4. **Fix the "Status" naming collision (UX, low risk, high value).** The alignment badge must not be titled "Status" or read as system health — retitle it ("Plan alignment") and/or visually distinguish it from the ops dot. Also reconsider its **fail-open-to-100** default: a health-looking indicator should fail to *unknown*, never to a reassuring green (this is the same "never fabricate certainty" principle already ratified as the UNKNOWN policy in `WLJ_CONFIGURATION_GOVERNANCE.md §4A`).
5. **Sequencing on resolution** (currently non-deterministic across the two systems): incident resolved → executive recomputed → score/impact/recommended action recomputed → notifications → wall/history. Ordering is already deterministic *within* the SAME cycle; the COAS branch is what breaks it.

**Priority:** item 4 is a contained UX correction; items 1–3 are the real consolidation and should be scoped as an Operations milestone of their own (they touch notification behavior and scoring — explicitly out of scope here).

---

**Non-goals honored:** Operations not redesigned; scoring unchanged; Configuration Governance untouched; OPS-14 not started; no speculative fixes implemented.
