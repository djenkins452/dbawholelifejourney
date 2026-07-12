# WLJ Ops Wall — Production Coverage Audit

> **Governing document:** `docs/WLJ_OPERATIONS_VISION.md` — the WLJ Operations subsystem vision +
> 9-phase living roadmap. This coverage audit is the **Phase I as-built** companion (the coverage
> matrix + the categorized post-Phase-I backlog, §4). **Phase I (Operations Visibility) is COMPLETE
> (2026-07-12)** — see §4. Remaining work is reclassified by category (§4.1), not a numbered OPS-N list.

**Status:** CURRENT · Milestone audit (2026-07-11)
**Governing principle:** *"If it runs in production, it must be observable."*
**Scope decision:** This document **reports** coverage and **prioritizes** remediation. Building observability for the un-monitored subsystems is tracked as a phased backlog (§4), not implemented in the milestone — per the Constitution's "harden, don't redesign; bounded by blast radius." The gaps are recorded honestly (Article IV.1), not hidden.

---

## 1. What the Ops Wall is

A single read-only monitoring surface at **`/admin-console/ops/`** — the **Operations Command Center** — polled every 2s, driven by a background-computed telemetry payload (`build_ops_stream_payload()`, 27 sections). The page opens with an **Executive Operations Summary** that answers the five operator questions in ten seconds (Am I okay? / What's wrong? / Why? / Who's affected? / What next?), synthesized deterministically from the telemetry below (`ops_executive.py :: build_executive_summary`, runs last in the SAME cycle — no new monitoring, no AI, no request-path compute). A component is observable **only if** it is either (a) a registered engine with a heartbeat cadence, (b) has a dedicated `_get_*` telemetry section, or (c) is a scheduled Beat task tracked by the scheduled-task monitor (OPS-1, below). Anything else running in prod is invisible.

**Key code:**
- Telemetry: `apps/core/ai_observability/ops_telemetry.py`
- Anomaly engine (SAME, 11 detectors, 60s): `apps/core/ai_observability/same_engine.py`
- Scheduled Beat-task monitor (OPS-1): `apps/core/ai_observability/scheduled_task_monitor.py` — generic Beat-schedule-vs-actual-run reconciler; cadence derived from `CELERY_BEAT_SCHEDULE`, runs recorded via Celery `task_postrun`, MISSED_RUN emitted through the SAME pipeline.
- Storage / volume monitor (OPS-2): `apps/core/ai_observability/storage_monitor.py` — Postgres size + growth, Redis memory/eviction, disk/volume utilization; daily `StorageSnapshot` for trend.
- Chat queue monitor (OPS-3): `apps/core/ai_observability/chat_queue_monitor.py` — passive Celery-signal lifecycle (publish/prerun/postrun) over the chat tasks; Redis-backed depth/wait/throughput/stuck/starvation.
- OpenAI upstream monitor (OPS-4): `apps/core/ai_observability/upstream_health.py` — passive per-call recorder at `AIService._log_usage`; availability, latency, consecutive failures, degradation state (distinguishes "WLJ healthy" from "OpenAI degraded").
- Executive synthesis / Command Center (`ops_executive.py :: build_executive_summary`): deterministic reduction over the assembled sections → `executive` payload section (overall status, customer impact, explainable score deductions, single prioritized action, enriched incidents with root-cause chains, operational narrative, per-KPI trends). Presentation + synthesis only; reuses all telemetry above.
- Celery/infra health: `apps/core/ai_observability/celery_health.py`, `apps/core/scheduler_health.py`
- Engine registry (~46 engines): `apps/core/engine_registry.py`
- Separate infra liveness (NOT on the wall): `/_health/` (`HealthCheckView` — DB `SELECT 1`, Redis probe, scheduler)

**Deployment (Railway):** web (gunicorn), `worker` (celery), `beat`, optional `chatworker` (`-Q chat`); Redis = broker+cache; Postgres; 25 `CELERY_BEAT_SCHEDULE` entries.

---

## 2. Coverage matrix — infrastructure

| Component | Monitored | Status/freshness/cadence/diagnostics | Notes |
|---|---|---|---|
| Web Application | Partial | Partial | `/_health/` covers liveness+DB; no web-dyno card on the wall |
| Celery Worker(s) | ✅ Yes | Mostly | HEALTHY/DEGRADED/CRITICAL/DOWN via `inspect().ping()`; worker count, concurrency, failed_1h |
| Celery Beat | Partial | Partial | Liveness **inferred** from ISE+SAME heartbeats; no direct beat-process heartbeat |
| Deployment / version | ✅ Yes (in-process) | Running SHA + migration | `deployment` section: running commit SHA, environment, runtime versions, migration status (partial-deploy guard), self-observed deploy detection (OPS-9). **Build runner itself stays Railway-side** — build status/failures/duration/rollback are not knowable from a running process (documented, not fabricated) |
| PostgreSQL | ✅ Yes | Size + growth + health | `storage` section: `pg_database_size` + 30-day growth (OPS-2). `db_health` section: connections vs `max_connections`, long-running queries, dead-tuple bloat + autovacuum age (OPS-5) |
| Redis | ✅ Yes | Memory + eviction | `storage` section: used/max memory, utilization %, `maxmemory_policy`, `evicted_keys` (OPS-2); plus broker connectivity + circuit breaker |
| Database Administration | ✅ Mostly | Migrations + pool + vacuum | `db_health` section: unapplied-migration detection (partial-deploy guard), connection-pool saturation, dead-tuple/vacuum lag (OPS-5). **Backup verification remains a FUTURE Operations capability** — there is no *trustworthy automated signal* available today (Railway-managed; no in-DB probe). Kept in the vision; not built and not faked (operator-verified for now) |
| Volumes | ✅ Yes | Disk utilization | `storage` section: `shutil.disk_usage` on the Railway volume / MEDIA_ROOT with warn/critical thresholds (OPS-2). S3 audio bucket still unmonitored (OPS-8) |
| Queues | ✅ Yes | Depth + backlog | `chat_queue` section: chat depth, oldest-queued age, throughput, queue wait, stuck, worker starvation (OPS-3); `celery` default queue via `LLEN` |
| Scheduler health | ✅ Yes | ✅ Yes | status, drift_seconds, cadence, MISSED_RUN/ENGINE_STARVATION |
| API health | ✅ Yes | Mostly | 24h volume, avg/P95, error rate, per-endpoint, channel split |
| OpenAI upstream | ✅ Yes | Availability + latency | `upstream_health` section: availability %, avg latency, consecutive failures, breaker state, last success; OUTAGE/DEGRADED/HEALTHY/IDLE (OPS-4) |

## 3. Coverage matrix — logical WLJ services

| Service | Monitored | Notes |
|---|---|---|
| Current Context | Partial | SAE engine heartbeat; state-freshness metric not surfaced |
| Current Action | ❌ No | Not a named section / registered engine |
| Execution Truth | Partial | Indirect via action outcomes / feed; no dedicated health |
| Mission Link | ❌ No | Zero ops coverage |
| Timing Calculations | Partial | HTIE engine heartbeat; correctness not surfaced |
| AI Relationship | Partial | PERSONA + RELDRIFT engines; no relationship-quality card |
| Executive Context Envelope | ✅ Yes | `_get_eae_ops_telemetry()` — decisions, arbitration, escalation, freshness |
| Model Interface | Partial | Upstream availability/latency/error now on the wall (OPS-4); adapter-internal errors still inferred |
| OpenAI connectivity | ✅ Yes | `upstream_health` section (OPS-4) — availability %, latency, consecutive failures, degradation state, last success; attributes outages to the provider, not WLJ |
| Streaming generation | Partial | TTFT tracked; no stream dropout/abort card |
| Scheduled Check-ins | ✅ Yes | COSSCHED, COSDELIV, CDCE_CI heartbeats |
| Notifications | ✅ Yes | DNE heartbeat + DELIVERY_RETRY_SPIKE |
| Action execution | ✅ Yes | `aafr` metrics (success/blocked/top-failure) |
| Confirmation queue | ✅ Yes | `confirmation_audit` section: pending-active, **stalled** (orphaned past expiry), oldest-pending age, age buckets, 24h flow — from `PendingAction` (OPS-8a) |
| Audit pipeline | ✅ Yes (liveness) | `confirmation_audit` section: `DecisionRecord` + `AIActionMetric` throughput/hour + last-write recency (OPS-8a). Audit is synchronous — no queue-lag exists; stream-liveness facts make a flatline visible |
| Signal pipeline | ✅ Yes | Per-domain freshness/volume/diversity + drought/diversity detectors |
| Goal momentum | ✅ Yes | Covered by scheduled-task monitor (OPS-1) → MISSED_RUN fires |
| Deterministic Understanding | Partial | SUE heartbeat; classifier drift not surfaced |
| Multimodal / capture ingestion | ✅ Yes | `media_persistence` section: capture pipeline status/failed_24h/top-error/**stuck** + `PendingCapture` abandoned/high-retry (OPS-8b) |
| Artifact / object storage | ✅ Config facts | `media_persistence`: which store is configured (Cloudinary/S3) + 24h artifact-ingestion count (OPS-8b). Local-disk fill = OPS-2. **No S3 bucket in use** (prod = Cloudinary); no synthetic reachability probe |
| Conversation image retention | ✅ Yes | `media_persistence`: expired 72h `image_data` never purged — surfaces a missing cleaner + Postgres growth (OPS-8b) |
| Duplicate detection | ❌ N/A | Dedup mechanism exists (sha256 unique) but **outcome is not recorded queryably** — a dedup-*rate* metric would be fabricated (OPS-8b finding). Not built |
| Background cleanup jobs | ✅ Yes | Covered by scheduled-task monitor (OPS-1) → MISSED_RUN fires |
| Image retention jobs | ✅ Yes | Capture expiry/retention Beat tasks covered by scheduled-task monitor (OPS-1) |
| Queue backlog | ✅ Yes | `celery` queue thresholds + `chat` queue depth/wait/throughput/stuck/starvation (OPS-3) |
| Failure monitoring | ✅ Yes | ERROR_SPIKE + aafr + failed_1h (engines); `task_health` pool-wide `task_failure` capture — recurring-vs-isolated by name (OPS-7) |
| Retry monitoring | ✅ Yes | `task_health` captures Celery `task_retry` for ALL tasks (OPS-7); DNE delivery-retry proxy still via DELIVERY_RETRY_SPIKE |
| Dead-job detection | ✅ Mostly | `task_health`: pool-wide stuck (active past the 120s time-limit) + `task_revoked` capture (OPS-7). Dead-letter/orphaned-broker-message detection still pending |
| Scheduler drift | ✅ Yes | drift_seconds + MISSED_RUN + ENGINE_STARVATION |

Every monitored item exposes Healthy / Degraded / Failed. The **owner** dimension is currently absent system-wide (see backlog OPS-6).

---

## 4. Backlog — Phase I complete; residual reclassified by category

> **Phase I (Operations Visibility) is COMPLETE (2026-07-12).** The mission — *"nothing important happens in
> production without being visible"* — is achieved: the critical infrastructure + execution surface (web
> liveness, workers, Beat, PostgreSQL depth, Redis, disk, queues, scheduled tasks, OpenAI upstream, and
> pool-wide background-task lifecycle) is comprehensively observable via OPS-1…5,7. Judged by the mission,
> **not** the backlog count. The remaining items below are **not** critical-visibility gaps — they are
> operational hardening, administrative metadata, external infrastructure, and technical debt. They are
> therefore reclassified out of Phase I (§4.1). WLJ Operations remains an active initiative (Phases II–IX).

### 4.0 Completed under Phase I (historical record)

| ID | Gap | Impact | Status |
|---|---|---|---|
| ~~**OPS-1**~~ | ~~non-engine Beat tasks are structurally invisible~~ → **DONE (2026-07-11).** All 23 non-engine Beat tasks (Goal momentum, `cleanup_soft_deletes`, capture retention/reminders, celebrations, digests, `cos_keepalive`, …) are now covered by the generic scheduled-task monitor. MISSED_RUN fires for every scheduled job. | ~~Highest~~ | ✅ Done |
| ~~**OPS-2**~~ | ~~Volumes / DB / Redis storage capacity unmonitored~~ → **DONE (2026-07-11).** `storage` section: Postgres size + 30-day growth, Redis used/max memory + eviction, disk/volume utilization, warn/critical thresholds, daily `StorageSnapshot`, graceful UNAVAILABLE per resource. (S3 audio bucket deferred to OPS-8.) | ~~High~~ | ✅ Done |
| ~~**OPS-3**~~ | ~~`chat` queue + chatworker backlog not measured~~ → **DONE (2026-07-11).** `chat_queue` section: passive Celery-signal lifecycle over the chat tasks → depth, oldest-queued age, throughput, queue wait, stuck detection, worker starvation. | ~~High~~ | ✅ Done |
| ~~**OPS-4**~~ | ~~OpenAI connectivity / Model Interface health not surfaced~~ → **DONE (2026-07-11).** `upstream_health` section: passive per-call recorder → availability %, latency, consecutive failures, breaker state, degradation (OUTAGE/DEGRADED/HEALTHY/IDLE), last success. Distinguishes "WLJ healthy" from "OpenAI degraded". | ~~High~~ | ✅ Done |
| ~~**OPS-5**~~ | ~~PostgreSQL depth + DB administration (connections, migrations, bloat, backup verification)~~ → **DONE (2026-07-11).** `db_health` section: connection-pool saturation (active/idle/idle-in-txn vs `max_connections`), long-running queries (max age + count over threshold), dead-tuple bloat + autovacuum age (`pg_stat_user_tables`), and unapplied-migration detection (partial-deploy guard). Telemetry-only (no anomaly/recovery), request-path-safe, graceful UNAVAILABLE on non-Postgres. **Scope refinement:** *backup verification* has no *trustworthy automated signal* today (Railway manages backups; no in-DB probe) → it remains a **FUTURE Operations capability** (kept in the vision), operator-verified for now, NOT faked with an artificial status. | ~~Medium~~ | ✅ Done |
| ~~**OPS-7**~~ | ~~Dead-job / stuck-task / general Celery-retry aggregation~~ → **DONE (2026-07-11).** `task_health` section: pool-wide worker-side capture of the Celery task lifecycle for ALL task names — active/oldest-age/**stuck** (past the 120s time-limit), **failures** (recurring-vs-isolated by name), **retries**, **revocations**. Fills the genuine gap (`task_failure`/`task_retry`/`task_revoked` were captured nowhere; no result backend). Redis-only (no model/migration), telemetry-only, worker-side (zero request-path). Reuses OPS-3's signal→Redis pattern; complements `celery_health` (workers) + `chat_queue` (chat-specific). | ~~Medium~~ | ✅ Done |

### 4.1 Post-Phase-I backlog (by category — the active list)

The remaining work is heterogeneous; a numbered `OPS-N` list misrepresented it. Reclassified by what each item actually is:

| Category | Item | What it is | Priority |
|---|---|---|---|
| ~~**Operational Hardening**~~ | ~~**OPS-8a — Confirmation queue & audit-pipeline health**~~ → **DONE (2026-07-12).** `confirmation_audit` section: confirmation queue (pending-active, **stalled** = orphaned pending past expiry, oldest-pending age, age buckets, 24h flow) from the durable `PendingAction` record; audit-stream **liveness** (throughput/hour + last-write recency) for `DecisionRecord` + `AIActionMetric`. Telemetry-only, request-path-safe, no model/migration; reuses existing truth. **Scope refinement (evidence):** auditing is **synchronous/inline** (no audit queue/deferred writer exists), so "audit lag / oldest unapplied audit / delayed writes / failed processing" were **not fabricated** — replaced with the honest, deterministic signal (stream throughput + recency, facts not a verdict; a flatline is visible). | ~~NEXT~~ ✅ Done |
| ~~**Operational Hardening**~~ | ~~**OPS-8b — Attachment persistence + dedup + S3 artifact bucket**~~ → **DONE (2026-07-12).** `media_persistence` section: **capture-audio pipeline** (`CaptureEntry` status breakdown / failed_24h + top error type / **stuck** in-progress; `PendingCapture` abandoned + high-retry), **image retention** (expired `image_data` never purged — surfaces a missing cleaner + Postgres-growth risk), **storage-config facts** (which store is configured). Telemetry-only, request-path-safe, no model/migration; reuses existing truth. **Roadmap corrections (evidence, see below):** NO S3 audio bucket in use (prod media = **Cloudinary**; S3 dormant/env-gated) → S3 item VOID; dedup-rate / orphaned-object / persistence-verification-failure signals **not built** (mechanisms don't exist → would be fabricated). | ✅ Done |

**OPS-8b truth refinements (2026-07-12 — the roadmap was half-wrong):**
- **No "S3 audio bucket."** Production media is **Cloudinary** (`STORAGES["default"] = MediaCloudinaryStorage`, `config/settings.py:388`). The capture-audio S3 path exists but is env-gated (`CAPTURE_AUDIO_BUCKET` empty by default) and Cloudinary is checked first (`apps/capture/views.py`). The `media_persistence` section exposes *which store is configured* as a deterministic fact — no fabricated S3 probe, no synthetic Cloudinary ping (OPS-4 no-synthetic-pings discipline).
- **Dedup-rate, orphaned/missing-object, persistence/verification-failure signals were NOT built** — no backing evidence exists: dedup outcome is never recorded queryably (`MultimodalArtifact.status='duplicate'` never written; message idempotency is cache-only), `storage_ref` is never populated (no DB→object linkage to diff), and image writes are fire-and-forget with swallowed exceptions. Truth before abstraction.
- **Discovered gap (not fixed here — observability, not action):** there is **no cleanup task** for expired conversation images — `AssistantMessage.image_data` (base64, 72h `image_expires_at`) is never purged, so expired image bytes accumulate in Postgres. `media_persistence` surfaces the "expired-but-never-purged" count; a future **Layer-1 hygiene task** should add the cleaner (candidate follow-up).
| **Administrative** | **OPS-6 — Per-component `owner` dimension** | Organizational metadata (no owner field exists). Near-zero value for a single-owner (solo-founder) system. | Deferred — revisit for a multi-owner/team surface |
| ~~**Infrastructure**~~ | ~~**OPS-9 — Build-runner / deploy-pipeline observability**~~ → **DONE (2026-07-12).** `deployment` section: current **running commit SHA** + environment + Django/Python versions, **migration status** (= the deterministic "did the release `migrate` step complete / did the deploy fully succeed?" — unapplied ⇒ CRITICAL partial-deploy), and **self-observed deploy detection** (SHA-change tracking → "current version first observed at" + previous SHA). NO external Railway/GitHub poll. Telemetry-only, request-path-safe, no model/migration (deploy marker is a cache key). **Roadmap corrections (evidence):** build status/duration/failures, failed deploys, deploy duration, and rollback state are **Railway-side, invisible to a running process** → NOT built (documented, not fabricated). | ✅ Done |
| **Technical Debt** | **OPS-11 — Retire legacy `_run_autonomous_remediation`** | Inert dead code (P3 filter never matches P1/P2 MISSED_RUN/SUPPRESSION_STORM; investigated 2026-07-11). No active conflict, no constitutional concern. Latent reactivation footgun + audit-split. Retire or fold into the recovery framework. | Opportunistic (with Phase III or engine-recovery enablement) |
| **Technical Debt** | **OPS-10 — Direct Beat measurement** | **Accept-inference / won't-do.** Beat blindness is already caught by three independent signals (scheduler_health ISE/SAME drift + OPS-1 MISSED_RUN + OPS-7 active-count drop). Direct measurement adds only marginal precision. **Residual logged:** if a real "Beat died but nothing lit up" incident ever occurs, reopen. | Closed (accept-inference) |

**Also tracked separately (NOT engineering):** the **O1→O2 production pilot** is an **Operational Rollout**
activity — engineering is complete (recovery framework + 3 R1 handlers + runbook `WLJ_OPERATIONS_PHASE2_PLAN.md
§11.1`); what remains is an operator-gated Railway env-var change + observation. See the vision ledger §15.

**Future capability (kept in the vision, not built):** *backup verification* — no trustworthy automated
signal exists today (Railway-managed); operator-verified for now, never faked with an artificial status.

**Recovery Engine component as-built (2026-07-12, ADR-24):** the read-only "Recovery Activity" card is now a
first-class **Recovery Engine** panel exposing existing deterministic truth (no new recovery logic, no invented
metrics). The producer `apps/core/operations/recovery/telemetry.py::build_recovery_telemetry()` adds a `config`
block — mode + source, configured vs enabled handlers, per-handler enabled + allowlist counts, beat/engine/
maturity flags — plus `failed_24h` and `last_activity`; handler config comes from the single source
`recovery/handlers.py::recovery_config_snapshot()` (each handler's `is_enabled()`/`allowlist_size()`, reused by
`diagnose()`). Critically, telemetry now publishes **every SAME cycle regardless of mode** via a separate
read-only `publish_recovery_telemetry_task` (name-based enqueue, §11 boundary preserved), so mode/handlers/
allowlists/status are visible even when recovery is **DISABLED** — the state in which an operator most needs
them. The Ops Wall reader (`ops_telemetry.py::_get_recovery_telemetry`) stays cache-only (request-path safe).
Tests: `test_recovery_shadow_mode.py::RecoveryConfigTelemetryTests`.

**Presentation fix (2026-07-12, ADR-25) — wall HTML must not be cached.** During Stage-0 Shadow validation the
Recovery telemetry was proven correct (SHADOW rows written; `/ops/stream/` JSON carried the full `recovery`
section) yet the panel was invisible to the operator. Root cause was purely presentation: `OperationsWallView`
sent **no cache headers**, so the wall's HTML *shell* — which carries each monitor card's DOM — was served
**stale** from browser/WKWebView/CDN, predating the newly-added Recovery Engine card. The polled JSON was fresh
but the missing DOM node never appeared. Fix: `@never_cache` on `OperationsWallView`
(`Cache-Control: no-cache, no-store, must-revalidate`). No telemetry/recovery change. This upholds the
Operations principle *"if it runs in production, it must be observable"*: freshness of the HTML shell (not just
the polled data) is a correctness requirement whenever a new monitor card can be added.

**Follow-on placement fix (2026-07-12) — Recovery promoted out of the collapsed Diagnostics drawer.** After the
cache fix, the panel was still absent because the Recovery Engine card was rendered inside Zone 5 "Diagnostics"
(`#diagnosticsBody`, `display:none` by default; all OPS monitor cards live there). Browser trace: card present
in DOM but 0×0 / `offsetParent:null`, hidden by `#diagnosticsBody`. Fix (template-only): moved the card into a
new always-visible zone `ops-zone-recovery` directly above the Diagnostics drawer — Recovery is now observable
without expanding Diagnostics. Card ids/body unchanged (`renderRecovery()` untouched).

**Recovery Events banner (2026-07-12).** A real ACTIVE recovery is a significant operational event and must not
happen silently. `build_recovery_telemetry` now emits an `events` list (real `mode=ACTIVE` outcomes only —
success/failed/escalated; shadow excluded) composed deterministically from the `RecoveryAttempt` rows already
written, enriched with `updated_at` (new `auto_now` audit field, migration `core/0133`) so **recovery duration**
= `updated_at − created_at`. A prominent **Recovery Events banner** at the top of the wall
(`renderRecoveryEvents`) shows these most-severe-first (escalated pulses; failures red), expandable to full
detail (reason, action, verification, duration, incident, attempts, escalation, retry history, Attempt ID) and
**acknowledgeable** via `localStorage` (ephemeral client state — no backend write, no new model/endpoint; events
expire out of the 24h window). No new notification framework; recovery still never writes incident state.

**OPS-1 as-built (2026-07-11):** implemented the **generic Beat-schedule-vs-actual-run reconciler** (the cleaner of the two options — no per-task registration, future Beat tasks are covered automatically). `apps/core/ai_observability/scheduled_task_monitor.py`:
- **Expected cadence** is derived directly from `settings.CELERY_BEAT_SCHEDULE` (interval numbers used as-is; crontabs estimated to a nominal period). The two scheduler *cycle* tasks (SAME/ISE) are excluded — already covered by `SchedulerHeartbeat`.
- **Actual runs** are recorded by Celery `task_prerun`/`task_postrun` signals (connected in `apps/core/apps.py::ready()`), each UPSERTing one current-state `ScheduledTaskRun` row per task (bounded storage even for the 30s `cos_keepalive`).
- **MISSED_RUN** descriptors flow through the existing SAME anomaly pipeline (`run_same` → `_detect_scheduled_task_missed_runs` → `_reconcile_anomalies`), so they appear on the Ops Wall, escalate, and resolve exactly like engine misses. NEVER_RUN (no run since deploy) is intentionally *not* flagged.
- A dedicated **`scheduled_tasks`** telemetry section + Ops Wall card shows the freshness of every scheduled job (23 tasks), not just fires on a miss.
- Kept deliberately separate from `EngineRun`/engine heartbeats so it does not pollute engine-health/integrity/narrative or the error-spike/starvation detectors.

Tests: `apps/core/tests/test_scheduled_task_monitor.py` (13 tests, incl. an end-to-end SAME-cycle proof that a stale Beat task becomes an active `OpsAnomaly`).

**OPS-2 / OPS-3 / OPS-4 as-built (2026-07-11):** three new telemetry sections, all following the OPS-1 / `api_health` architecture — probing/collection runs ONLY inside `build_ops_stream_payload()` (SAME background cycle, every 60s); the HTTP request path reads the cached payload and never computes.

- **OPS-2 storage (`storage_monitor.py`, `storage` section):** three independent probes — Postgres `pg_database_size(current_database())` + a 30-day growth trend from the daily `StorageSnapshot` table; Redis `INFO memory` → `used_memory`/`maxmemory`/`maxmemory_policy`/`evicted_keys`; disk via `shutil.disk_usage` on `RAILWAY_VOLUME_MOUNT_PATH` (→ `MEDIA_ROOT` → `BASE_DIR`). Utilization thresholds WARNING 75% / CRITICAL 90%; `noeviction` Redis under pressure → CRITICAL. Any unmeasurable resource → UNAVAILABLE with a reason (never a fabricated zero); the roll-up takes the worst *measured* state. Reader cache-guarded 5 min.
- **OPS-3 chat queue (`chat_queue_monitor.py`, `chat_queue` section):** passive Celery-signal lifecycle — `before_task_publish` (enqueue, web process) / `task_prerun` (start) / `task_postrun` (complete), filtered to `run_chat_generation` + `run_chatgpt_cos_generation`, connected in `apps/core/apps.py::ready()` alongside the OPS-1 signals. Cross-process Redis structures (pending/active sorted sets + wait/completion lists, self-expiring in 1h) yield queue depth, oldest-queued age, throughput/min, avg queue wait, stuck (active past the 120s time-limit), and worker starvation (backlog with nothing active/draining). No Redis (dev) → recorders no-op, reader UNAVAILABLE.
- **OPS-4 upstream (`upstream_health.py`, `upstream_health` section):** a single fire-and-forget recorder at `AIService._log_usage` (both streaming and non-streaming, before the no-user guard) records every OpenAI outcome into per-minute cache buckets — no synthetic pings, zero added request-path latency. Reader computes windowed availability %, avg latency, error rate, consecutive failures, and consults the existing `openai_rate_limited` breaker flag. Degradation state machine: OUTAGE (≥3 consecutive failures or recent-failure-with-no-success) / DEGRADED (>25% window error rate or breaker active) / HEALTHY / IDLE — the attribution that separates "WLJ down" from "OpenAI down".

Tests: `apps/core/tests/test_storage_monitor.py`, `apps/core/tests/test_chat_queue_monitor.py`, `apps/core/tests/test_upstream_health.py` (28 tests total).

---

## 5. Human-judgment items recorded

- **`/_health/` split:** DB/Redis/scheduler liveness IS checked at `/_health/` (Railway + uptime monitors) but is not on the Ops Wall. Decision pending: mirror infra liveness onto the wall, or accept the split (Ops Wall = intelligence/execution; `/_health/` = infra).
- **"Engine ran" vs "service healthy":** many logical services are "partial" because the underlying engine heartbeat is monitored but output correctness is not. Whether heartbeat satisfies "healthy" for a given service is a per-service call.
- **Some logical names are conceptual** (Current Action = 2 files, Mission Link = 7 files) — confirm which warrant a dedicated card vs. which are internal terms before treating each as a hard gap.
