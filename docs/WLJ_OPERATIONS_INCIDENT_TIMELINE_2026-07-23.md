# Operations Truth Divergence — Production Timeline Reconstruction (2026-07-23)

**Status:** Evidence milestone — read-only. **PRODUCTION EVIDENCE COLLECTED 2026-07-24** via a temporary read-only diagnostic (introduced, queried, and **removed same session — 404 verified**). No production data modified, no correction implemented, OPS-14 not started.
**Companion:** `docs/WLJ_OPERATIONS_TRUTH_PATH_INVESTIGATION.md` (proved the *mechanism*).
**Incident (now pinpointed from rows):** **2026-07-23, 09:47–10:43 UTC (05:47–06:43 US Eastern)** — a recurring MISSED_RUN/SUPPRESSION burst. Server `TIME_ZONE=UTC`; report converts to Eastern (Maryville, TN).

> **⚠️ CORRECTION — the row-level evidence FALSIFIED my prior hypothesis.** The pre-read reconstruction assumed Clara's "recovered" came from the **COAS recovery message**. **It did not.** Over 5 days there were only **4 `OperationalAlert` rows — all `severity: warning`, all `last_notified_at: None`, and ZERO `operations_alert` notifications.** The COAS message-injection path requires `alert`/`critical`; it never triggered. **What the operator actually saw was ONE authority (integrity) *flapping*:** the integrity score oscillated across the DEGRADED↔NOMINAL boundary (70) — **50→51 DEGRADED (09:47) → 76.5 NOMINAL (09:54) → 67 DEGRADED (10:06) → … → 98 OPTIMAL (10:43)** — so the pinned **banner (executive) legitimately flipped yellow→green→yellow**, the **Wall's "51" was the real 09:50 trough**, the **5 incidents were genuinely active**, and the constant green **"100%" is the alignment badge (not Operations)**. Nothing was stale; nothing was fabricated; a **flapping score sampled at different cadences + a transient "recovered" cue that ignored still-active incidents + a mislabeled always-green badge** produced the contradiction. *(The two-authority architectural risk from the companion doc is real, but it was **not** the cause of this specific observation.)*

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

## 1A. PRODUCTION ROW-LEVEL EVIDENCE (collected 2026-07-24, read-only)

### Integrity score curve — `SystemIntegritySnapshot`, 2026-07-23 09:30–11:00 UTC (95 rows; changes only)
```
09:42:46  93.0  OPTIMAL     (healthy pre-incident)
09:47:36  50.0  DEGRADED  ◀ incident hits (5 anomalies)
09:50:28  51.0  DEGRADED  ◀◀ THE WALL SCREENSHOT ("Operational Health 51")
09:52:41  55.0  DEGRADED
09:53:01  67.0  DEGRADED
09:54:55  76.5  NOMINAL   ◀ recovered above 70 → banner flips GREEN ("recovered")
10:05:05  70.0  NOMINAL
10:06:05  67.0  DEGRADED  ◀ FLAP: re-degraded (banner would flip yellow again)
10:09:26  76.5  NOMINAL   ◀ recovered
10:13:05  88.5  NOMINAL
10:38:25  69.5  DEGRADED  ◀ FLAP: re-degraded
10:40:25  86.0  NOMINAL
10:43:48  98.0  OPTIMAL   ◀ fully recovered
```
min 50.0 · max 98.0 · **the score crossed the DEGRADED/NOMINAL boundary (70) at least 4 times in ~1 hour.** Posture DEGRADED = 40–69, NOMINAL = 70–89.

### Active incidents at the peak — `OpsAnomaly`, peak **5 concurrent at 09:52 UTC** (matches the Wall's "5")
| id | type | engine/task | sev | created (UTC) | resolved (UTC) |
|---|---|---|---|---|---|
| 9248 | SIGNAL_DROUGHT | — | P3 | (pre-existing) | later |
| 9269 | MISSED_RUN | GLOE | P2 | 09:47:36 | 10:43:48 |
| 9270 | SUPPRESSION_STORM | ICQG | P2 | 09:47:36 | 10:13:05 |
| 9271 | MISSED_RUN | `cos_keepalive_task` | **P1** | 09:47:36 | 09:52:24 |
| 9272 | MISSED_RUN | DNE | P2 | 09:50:27 | 09:54:54 |
These are **exactly** the subsystems the brief named (cos_keepalive, missed scheduled work, GLOE cadence, ICQG suppression storm, DNE). They resolved progressively 09:52 → 10:43 — the same window over which the score flapped.

### COAS alerts — `OperationalAlert`, 2026-07-20…25 (only 4 rows, ALL warning, NONE notified)
```
id 79  scheduler  warning  score 60  2026-07-20 23:45 → resolved 23:45  last_notified_at=None
id 80  scheduler  warning  score 70  2026-07-21 11:31 → resolved 11:33  last_notified_at=None
id 81  scheduler  warning  score 70  2026-07-22 10:58 → resolved 11:01  last_notified_at=None
id 82  scheduler  warning  score 70  2026-07-24 10:04 → resolved 10:05  last_notified_at=None
```
**None on 2026-07-23. None ever reached `alert`/`critical`. `last_notified_at` is None on all four.**

### Notifications — `AssistantMessage(message_type='operations_alert')`
**ZERO** in the incident window (and zero across 2026-07-20…25). **Clara sent no COAS operations message.**

### COAS snapshot — `COASHealthSnapshot` (single row, pk=1)
Current value at read time: `100/100/100/100` (computed 2026-07-24 10:05). This is the **current overwritten value, NOT the incident value** — confirming the no-history gap (§1).

**Conclusion from rows:** the "degraded → recovered → green" the operator experienced was the **executive-driven pinned banner flapping** on an oscillating integrity score, plus the always-green **alignment** badge — **not** a COAS notification (there was none).

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

## 4. Consolidated timeline (row-level, from production — 2026-07-23 UTC / ET)

| UTC | ET | System Integrity | Active OpsAnomalies | COAS/OperationalAlert | Notification (Clara) | Header badge |
|---|---|---|---|---|---|---|
| 09:42 | 05:42 | **93 OPTIMAL** | 0–1 | quiet | none | 🟢 100% (align) |
| **09:47** | **05:47** | **50 DEGRADED** ◀ incident | burst → 4–5 open (P1 cos_keepalive + GLOE + ICQG + DNE) | no COAS alert (all warnings, none notified) | **banner → 🟡** (executive DEGRADED) | 🟢 100% (align) |
| **09:50** | **05:50** | **51 DEGRADED** ◀ **the Wall "51"** | **5 concurrent** | — | banner 🟡 | 🟢 100% (align) |
| **09:54** | **05:54** | **76.5 NOMINAL** ◀ recovered >70 | resolving (cos_keepalive/DNE cleared) | — | **banner → 🟢 "recovered" cue** | 🟢 100% (align) |
| **10:06** | **06:06** | **67 DEGRADED** ◀ FLAP | GLOE/ICQG still open | — | **banner → 🟡 again** | 🟢 100% (align) |
| 10:13 | 06:13 | 88.5 NOMINAL | ICQG resolved | — | banner 🟢 | 🟢 100% (align) |
| 10:38 | 06:38 | 69.5 DEGRADED ◀ FLAP | — | — | banner 🟡 | 🟢 100% (align) |
| **10:43** | **06:43** | **98 OPTIMAL** ◀ real recovery | last (GLOE) resolved → 0 active | — | banner 🟢 | 🟢 100% (align) |

**Marked moments (proven):** ① first degradation **09:47 UTC**; ② degraded cue = banner flip to 🟡 at 09:47 (no COAS chat message — none was sent); ③ *there was no COAS recovery threshold crossing to alert/critical* — the 4 alerts were warnings, unnotified; ④ *there was no operations_alert notification*; ⑤ Wall "51" = the **09:50 UTC** snapshot; ⑥ 5 concurrent anomalies at **09:52 UTC**; ⑦ actual recovery **10:43 UTC** (score 98, 0 active). The green→ banner "recovered" the operator saw = the **09:54 transient NOMINAL**, before the 10:06 re-degradation.

## 5. Precise root-cause statement (§9 answers — CORRECTED by the rows)

1. **Was Clara's "recovered" message factually correct as written?** **There was no COAS "recovered" chat message** — 0 `operations_alert` notifications, all alerts warning-level/unnotified. What the operator saw was the **pinned banner's transient "recovered" cue**, which fired correctly for a **real but momentary** executive recovery (integrity 76.5/NOMINAL at 09:54). It was *accurate for that instant* but *premature*: incidents were still active and the score re-degraded 12 minutes later.
2. **Subsystem or whole-platform recovery?** Neither a COAS subsystem message nor a platform-recovery message existed. The banner reflected **executive** status, which had **genuinely (if briefly) returned to healthy**. The failure is that the recovered cue treated a **transient NOMINAL as "recovered"** without requiring active incidents to be cleared.
3. **Was the real Operations dot green/yellow/red?** It **flapped** with the score: 🟡 at 09:47/09:50, 🟢 at 09:54, 🟡 at 10:06, 🟢 by 10:43 — because `.ap-ops-link[data-ops-status]` reads `executive.overall_status`, which oscillated.
4. **Was the "100%" badge stale, fresh, or fallback?** **Value unrecoverable** (cache-only, TTL expired). Provable: it is the **alignment** score (not Operations), 15-min cached, **fails open to 100** on any exception. It was green the *entire* incident regardless of Operations state — the constant reassuring signal.
5. **Were the five Wall incidents genuinely active?** **Yes — proven.** Peak **5 concurrent `OpsAnomaly.is_active=True` at 09:52 UTC** (cos_keepalive P1, GLOE, ICQG, DNE, SIGNAL_DROUGHT). The Wall read them live and correctly.
6. **How long did the misleading state persist?** The score was DEGRADED-or-flapping from **09:47 to 10:43 (~56 min)**; the specific "banner said recovered while incidents active" window ran from the **09:54 transient recovery** until at least the **10:06 re-degradation**, recurring until 10:43.
7. **What would a single executive authority have said?** Continuously **DEGRADED with active incidents from 09:47 until 10:43** *if it applied recovery hysteresis* (do not declare recovered while any `OpsAnomaly.is_active` remains) — and it would **not** have flashed "recovered" at 09:54.

**Classification (corrected):** *no stale data* (both surfaces were fresh; the Wall was faithful, the banner was faithful) → **the divergence was a *flapping single authority* sampled at different cadences** (banner 60s vs Wall 10s) → **a transient-recovery cue with no incident-aware hysteresis** → **a mislabeled always-green alignment badge** titled "Status." My prior "two authorities (COAS vs integrity) disagreed" hypothesis was **architecturally valid but not the cause here** — COAS never spoke.

## 6. Acceptance-test specification for the correction (§10 — primary deliverable)

A deterministic scenario the consolidation milestone must satisfy, **built from the actual 2026-07-23 rows.** **Not implemented here** (would require test scaffolding; specified only).

**Given** the proven integrity path **50 → 51 → 76.5 (NOMINAL) → 67 (DEGRADED) → 98**, **and** `OpsAnomaly.is_active=True` for cos_keepalive/GLOE/ICQG/DNE across 09:47–10:43, **and** COAS producing only warning-level alerts (unnotified), **then:**

| # | Assertion | Which 2026-07-23 failure it encodes |
|---|---|---|
| A1 | **Recovery is incident-aware (hysteresis):** the banner/executive must **not** declare "recovered" while any `OpsAnomaly.is_active=True` — even if the score momentarily crosses ≥70. (The 09:54 transient NOMINAL must NOT have flashed "recovered".) | the core failure |
| A2 | **Flap suppression / debounce:** a single sub-cycle crossing of the DEGRADED/NOMINAL boundary must not toggle the customer-facing recovered cue; require sustained recovery (e.g. N consecutive cycles **and** zero active incidents). | the 09:54↔10:06 flap |
| A3 | Active `OpsAnomaly` incidents keep `executive.overall_status` non-HEALTHY until they resolve (independent of the raw score band). | 5 active while score touched NOMINAL |
| A4 | The header Operations indicator equals `executive.overall_status`, and both the banner (60s) and Wall (10s) reconcile within the documented budget rather than showing opposite states. | banner 🟢 vs Wall 🟡 |
| A5 | The alignment badge is labelled **alignment**, not "Status", and is visually distinct from the Operations indicator. | green 100% read as health |
| A6 | Alignment computation failure yields **Unknown/unavailable**, never a reassuring `100` (ratified UNKNOWN policy, `WLJ_CONFIGURATION_GOVERNANCE.md §4A`). | fail-open-to-100 |
| A7 | Any operational notification cites the **executive** authority + records the emitting `overall_status`/snapshot id; none derives platform health independently. | audit gap |
| A8 | Wall score, header indicator, recommended action, customer impact, and notifications **agree within their documented refresh windows**. | overall coherence |

**A1 + A2 are the primary corrective assertions** (incident-aware, debounced recovery); A3–A4 enforce single-authority coherence; A5–A6 fix the misleading badge; A7 closes the audit gap. Note the earlier draft's "no platform-recovery notification while executive ≠ HEALTHY" still holds as a rule, but the *observed* failure was a **UI recovered-cue** flap, not a COAS notification.

## 7. Evidence gaps + required future audit logging (§11)

Not inferred — these are proven-unavailable:
1. **COAS score history** — single-row model; the degraded/recovered scores are gone. **Recommend:** persist a `COASHealthSnapshot` history row per cycle (or fold COAS into the retained integrity history when consolidated), so alert transitions carry their triggering/recovery scores.
2. **Alignment provenance** — cache-only; cannot tell a real ≥80 from the 100 fallback. **Recommend:** record `computed_at` + a `source` flag (`computed`|`fallback`) alongside the cached alignment value.
3. **Notification↔authority link** — `AssistantMessage.metadata` for operations_alert records `level` but not the *source snapshot id / authority / executive status at emit time*. **Recommend:** stamp the emitting `executive.overall_status` + snapshot id into the notification metadata, so future audits prove which authority spoke.
4. **Deploy correlation** — confirm `RAILWAY_GIT_COMMIT_SHA` at incident time to bind behavior to code.

## 8. Read-channel provenance (temporary diagnostic — introduced, used, removed)

The §1A rows were collected via a **temporary, read-only, SELECT-only, `X-Claude-API-Key`-gated** diagnostic (`apps/admin_console/ops_incident_diagnostic.py`), window-scoped and field-minimal (AssistantMessage restricted to `operations_alert`). It was **introduced** (commit `72640b34`, field-fix `05933d73`), queried against production for the incident window, then **removed** in the paired cleanup commit; the endpoint now returns **HTTP 404** (verified). No writes occurred; production is left exactly as before. Two records remain permanently unrecoverable (COAS score history — single row; alignment value — cache-only), as predicted in §1.

---

**Final status:** Production timeline reconstructed from row-level evidence; the prior hypothesis was corrected by the data (flapping single authority + transient recovered cue + mislabeled alignment badge; COAS never notified). Temporary diagnostic removed (404 verified). Awaiting approval to consolidate Operations authority.
