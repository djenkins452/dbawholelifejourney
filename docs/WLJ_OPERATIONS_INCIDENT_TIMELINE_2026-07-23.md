# Operations Truth Divergence — Production Timeline Reconstruction (2026-07-23)

**Status:** Evidence milestone — read-only. **No code changed, no production data modified, no correction implemented, OPS-14 not started.**
**Companion:** `docs/WLJ_OPERATIONS_TRUTH_PATH_INVESTIGATION.md` (proved the *mechanism*; this reconstructs the *incident* and specifies the acceptance test).
**Incident:** morning of **2026-07-23**, user-local timezone **US Eastern** (dashboard location Maryville, TN; server `TIME_ZONE=UTC`, so technical evidence is UTC and the report converts to Eastern). Anchors: the CoS "degraded" notice, the CoS "recovered" notice + green 100% badge, and the Operations Wall screenshot showing **Operational Health 51 · DEGRADED · Medium · 5 active incidents**.

> **Headline:** Clara's "recovered" message was **factually correct for the COAS subsystem authority** but made an **unconditional platform-level claim** — *"WLJ automatically recovered from a temporary operational issue. Everything is operating normally again."* — while the executive/integrity authority was still **51 / DEGRADED** with 5 active `OpsAnomaly` incidents. Nothing was *stale*; two authorities disagreed by design, and the notification wording + the green alignment badge implied whole-platform health that the executive authority never asserted.

---

## 1. Evidence-availability matrix (CODE-PROVEN — determines what is reconstructable)

Before any query, this is what production actually persists. Several authorities do **not** retain history, so parts of the row-level timeline are **permanently unavailable** (§11 honesty requirement).

| Authority | Persistence (proven) | Retained for 2026-07-23? | Reconstructable? |
|---|---|---|---|
| **SystemIntegritySnapshot** (Wall score/posture) | `create()` **new row per SAME cycle (~60s)**; **no pruning found** in code | Yes (accumulates ~1440/day; not pruned) | ✅ **Yes** (to confirm on read) |
| **OpsAnomaly** (incident lifecycle) | lifecycle rows: `created_at`/`resolved_at`/`is_active`/`escalation_count`; no cleanup found | Yes | ✅ **Yes** |
| **OperationalAlert** (COAS alert lifecycle) | lifecycle rows: `created_at`/`resolved_at`/`status`/`health_score`/`dedupe_key`/`last_notified_at` | Yes | ✅ **Yes** |
| **AssistantMessage** (Clara's messages) | rows; soft-delete retention 30 days | Yes | ✅ **Yes** (actual wording + timing) |
| **COASHealthSnapshot** (COAS scores) | **`update_or_create(pk=1)` — SINGLE OVERWRITTEN ROW** (`health_scoring.py:436`) | ❌ **No** — overwritten every ~300s (~288× since) | ❌ **GONE** |
| **Alignment "100%" badge** | value only in a **15-min cache** (`context_processors.py:279‑292`); **no persistence** | ❌ **No** — TTL long expired | ❌ **GONE** (only *code behavior* provable) |

**Two definitive evidence gaps exist regardless of read access:** the exact COAS degraded/recovered *scores* and the alignment *value* at incident time were never persisted.

## 2. Deployed-code correlation (affects which notifications fired)

Notification behavior changed on **2026-07-18** (commit `daaefd91`, "Operations Awareness UX — pinned banner"). Assuming it was live on 2026-07-23 (it was committed 5 days prior), then at incident time:
- **DEGRADED (COAS alert/critical):** **no chat message injected** — active-incident state is shown only by the **pinned banner** (which reads `executive.overall_status`). Confirmed at `operational_alerts.py:194` (active injection removed).
- **RECOVERY (COAS severe alert resolves ≥80):** injects **one** `AssistantMessage` `message_type='operations_alert'`, `metadata.level='recovered'`, content = `_build_recovery_message()` → *"WLJ automatically recovered from a temporary operational issue. Everything is operating normally again."* (`operational_alerts.py:126‑130, 306‑309`). **This is the "recovered" message the operator saw.**
- **The reconstruction MUST verify the deployed commit at incident time** via `RAILWAY_GIT_COMMIT_SHA` on the AssistantMessage-adjacent deploy record / `deployment_monitor`, because it determines whether the "degraded" cue was the banner (post-`daaefd91`) or a legacy COAS chat injection (pre-`daaefd91`).

## 3. Exact read queries (parameterized by the incident window `[W0, W1]` in UTC)

These are the deterministic queries an operator (or an approved temporary read-only diagnostic) runs. All are **SELECT-only**. `W0/W1` = incident window bounds from the screenshot/notification anchors.

```python
# 2. System Integrity history (the Wall's 51)
SystemIntegritySnapshot.objects.filter(created_at__range=(W0, W1)) \
    .order_by('created_at').values('created_at','score','posture','components')
#   → for each: score, posture, components (engine/scheduler deductions),
#     and the active-anomaly count embedded in components.

# 3. OpsAnomaly lifecycle — every incident touching the window
OpsAnomaly.objects.filter(
    Q(created_at__lte=W1) & (Q(resolved_at__gte=W0) | Q(resolved_at__isnull=True))
).order_by('created_at').values(
    'id','anomaly_type','engine_name','severity','original_severity',
    'created_at','updated_at','resolved_at','is_active','escalation_count','summary','evidence')
#   Focus subsystems named in the brief: cos_keepalive_task, MISSED_RUN scheduled
#   work, GLOE cadence, ICOG suppression storm, DNE, ICQG, GLOE. The `evidence`
#   JSON carries task_name/last_run_at for MISSED_RUN.

# 5. OperationalAlert lifecycle (COAS)
OperationalAlert.objects.filter(
    Q(created_at__range=(W0, W1)) | Q(resolved_at__range=(W0, W1))
).order_by('created_at').values(
    'id','subsystem','severity','status','health_score','dedupe_key',
    'created_at','resolved_at','last_notified_at','message')
#   → the degraded row (created_at, health_score<threshold) and the resolved row
#     (resolved_at, and the recovered score is derivable from the COAS snapshot at
#     resolve time — but that snapshot is GONE, see §1).

# 6. Notification evidence — Clara's actual messages
AssistantMessage.objects.filter(
    message_type='operations_alert', created_at__range=(W0, W1)
).values('id','conversation__user_id','created_at','content','metadata')
#   → the "Operations Update / recovered" row(s): exact wording, timing, level.
#   (Pre-daaefd91 fallback: metadata__alert_type='coas'.)
```

**Gap #1 (COAS history):** no query can recover the degraded/recovered COAS *scores* — single-row model. The *fact* of degraded→recovered and its *timing* survive in `OperationalAlert`; the *scores* do not.
**Gap #2 (alignment):** no query can recover the badge value — cache-only. Only `context_processors.py` behavior is provable.

## 4. Consolidated timeline (mechanism-derived; row-level cells marked ⧗ PENDING read)

The **shape** below is proven from code; the **timestamped values** require the §3 read (or are permanently ⛔ unavailable). This table IS the reconstruction skeleton to fill on read.

| Local (ET) | System Integrity | Active OpsAnomalies | COAS score/state | OperationalAlert | Notification (Clara) | Header badge |
|---|---|---|---|---|---|---|
| pre-incident | ⧗ (Wall snapshot) | ⧗ | ⛔ score gone | none | none | 🟢 100% (align) |
| Operations first degraded | ⧗ score↓ | ⧗ ≥1 opens | ⛔ subsystem <60 | **created** ⧗ | banner→🟡 (no chat msg, post-daaefd91) | 🟢 100% (align, unaffected) |
| COAS crosses recovery ≥80 | ⧗ **still low (≈51)** | ⧗ **still ≥5 active** | ⛔ subsystem ≥80 | **resolved** ⧗ | **"…recovered. Everything operating normally"** ⧗ | 🟢 100% (align) |
| Wall screenshot | **51 / DEGRADED** ✅ | **5 active** ✅ | ⛔ | (resolved) | (recovered msg persists) | 🟢 100% (align) |
| actual Ops recovery | ⧗ when score→≥70 & anomalies resolve | ⧗ →0 | — | — | (none — no platform-recovery notify exists) | 🟢 |

**Marked moments (to timestamp on read):** ① first degradation = first `SystemIntegritySnapshot.score` drop / first `OpsAnomaly.created_at`; ② degraded cue = banner flip (derived) / (pre-daaefd91) COAS injection; ③ COAS recovery threshold = `OperationalAlert.resolved_at`; ④ recovered notification = `AssistantMessage.created_at` (operations_alert); ⑤ Wall=51 = the `SystemIntegritySnapshot` nearest the screenshot time; ⑥ 5 anomalies active = `OpsAnomaly.filter(is_active=True)` at ④; ⑦ actual recovery = last `OpsAnomaly.resolved_at` + first snapshot ≥ NOMINAL.

## 5. Precise root-cause statement (§9 answers)

1. **Was Clara's recovered message factually correct as written?** *Partially.* It correctly reflected a COAS **subsystem** returning to ≥80, but its wording — *"Everything is operating normally again"* — asserts **whole-platform** recovery, which was false at that instant.
2. **Subsystem or whole-platform recovery?** It **described whole-platform recovery** while only the **COAS subsystem authority** had recovered. `_build_recovery_message` consults **no** executive/integrity/OpsAnomaly state.
3. **Was the real Operations dot green/yellow/red?** The real Operations indicator (`.ap-ops-link` dot, driven by `executive.overall_status`) was **🟡 DEGRADED** (integrity 51). It was **not** the thing the operator read.
4. **Was the "100%" badge stale, fresh, or fallback?** **Unrecoverable as a value** (cache-only, TTL expired). Provable: it is the **alignment** score (not Operations), 15-min cached, and **fails open to a hardcoded 100** on any exception. Whether this instance was a real ≥80 alignment or the 100 fallback **cannot be determined from persisted data** — a gap (§10 audit recommendation).
5. **Were the five Wall incidents genuinely active?** **Yes** — `OpsAnomaly.is_active=True` is the lifecycle truth and the Wall reads it live; COAS recovery does **not** resolve `OpsAnomaly`. (Row-level confirmation pending the §3 read.)
6. **How long did the misleading state persist?** From the recovered-message timestamp until the last `OpsAnomaly.resolved_at`/first NOMINAL snapshot — **derivable on read**; bounded below by the executive→COAS threshold gap, not by cache latency.
7. **What would a single executive authority have said?** At every point: **DEGRADED / 51 / Medium impact / 5 active incidents / investigate the scheduled-task failure** — and it would **not** have emitted a platform-recovery notification until executive truth cleared.

**Classification:** ✅ *correct subsystem truth* (COAS ≥80) → ❌ *incorrect platform-level implication* (recovery wording) → ⚠️ *misleading UI semantics* (alignment badge titled "Status", green 100%) → *no actual stale data* (the Wall was the freshest surface, ~80s worst case).

## 6. Acceptance-test specification for the correction (§10 — primary deliverable)

A deterministic scenario the consolidation milestone must satisfy. **Not implemented here** (would require test scaffolding; specified only).

**Given** a COAS subsystem score path 55 → 85 (degraded then subsystem-recovered), **and** `SystemIntegritySnapshot.score = 51 (DEGRADED)` throughout, **and** ≥1 `OpsAnomaly.is_active=True` throughout, **then:**

| # | Assertion |
|---|---|
| A1 | COAS inputs MAY transition to recovered independently (subsystem truth preserved). |
| A2 | **No platform-recovery notification** is emitted while `executive.overall_status != HEALTHY`. (Today: `_inject_admin_alert` fires unconditionally → **FAILS** — this is the regression the fix must flip.) |
| A3 | Active `OpsAnomaly` incidents keep `executive.overall_status` DEGRADED until they resolve. |
| A4 | The header Operations indicator (`.ap-ops-link[data-ops-status]`) equals `executive.overall_status` at all times. |
| A5 | The alignment badge is labelled **alignment**, not "Status", and is visually distinct from the Operations indicator. |
| A6 | Alignment computation failure yields **Unknown/unavailable**, never a reassuring `100` (align with the ratified UNKNOWN policy, `WLJ_CONFIGURATION_GOVERNANCE.md §4A`). |
| A7 | Any operational notification cites the **executive** authority; none derives platform health independently. |
| A8 | Wall score, header indicator, recommended action, customer impact, and notifications **agree within their documented refresh windows** (§7 divergence budget of the companion doc). |

A2 + A7 encode the exact 2026-07-23 failure; A4–A6 encode the misleading-UI failures.

## 7. Evidence gaps + required future audit logging (§11)

Not inferred — these are proven-unavailable:
1. **COAS score history** — single-row model; the degraded/recovered scores are gone. **Recommend:** persist a `COASHealthSnapshot` history row per cycle (or fold COAS into the retained integrity history when consolidated), so alert transitions carry their triggering/recovery scores.
2. **Alignment provenance** — cache-only; cannot tell a real ≥80 from the 100 fallback. **Recommend:** record `computed_at` + a `source` flag (`computed`|`fallback`) alongside the cached alignment value.
3. **Notification↔authority link** — `AssistantMessage.metadata` for operations_alert records `level` but not the *source snapshot id / authority / executive status at emit time*. **Recommend:** stamp the emitting `executive.overall_status` + snapshot id into the notification metadata, so future audits prove which authority spoke.
4. **Deploy correlation** — confirm `RAILWAY_GIT_COMMIT_SHA` at incident time to bind behavior to code.

## 8. Read-channel note (why the actual rows aren't in this doc yet)

The surviving rows (§1: Integrity/OpsAnomaly/OperationalAlert/AssistantMessage) require a production read path. **No existing `X-Claude-API-Key` operator endpoint exposes these Ops models**, and this milestone forbids modifying code. The row-level cells above are therefore marked ⧗ PENDING a decision on the read channel (a temporary read-only diagnostic vs. an operator running the §3 queries) — surfaced separately, not actioned unilaterally.

---

**Final status:** Production timeline reconstructed *to the limit of persisted evidence and read-only constraints* — mechanism, retention, gaps, root cause, and acceptance test are proven and specified; actual surviving-row values await a read-channel decision. Awaiting approval to consolidate Operations authority.
