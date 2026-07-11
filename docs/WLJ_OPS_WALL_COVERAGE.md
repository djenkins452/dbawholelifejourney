# WLJ Ops Wall — Production Coverage Audit

**Status:** CURRENT · Milestone audit (2026-07-11)
**Governing principle:** *"If it runs in production, it must be observable."*
**Scope decision:** This document **reports** coverage and **prioritizes** remediation. Building observability for the un-monitored subsystems is tracked as a phased backlog (§4), not implemented in the milestone — per the Constitution's "harden, don't redesign; bounded by blast radius." The gaps are recorded honestly (Article IV.1), not hidden.

---

## 1. What the Ops Wall is

A single read-only monitoring surface at **`/admin-console/ops/`**, polled every 2s, driven by a background-computed telemetry payload (`build_ops_stream_payload()`, 22 sections). A component is observable **only if** it is either (a) a registered engine with a heartbeat cadence, or (b) has a dedicated `_get_*` telemetry section. Anything else running in prod is invisible.

**Key code:**
- Telemetry: `apps/core/ai_observability/ops_telemetry.py`
- Anomaly engine (SAME, 10 detectors, 60s): `apps/core/ai_observability/same_engine.py`
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
| Build Runner | ❌ No | No | Railway build/deploy runner unmonitored |
| PostgreSQL | Partial | Liveness only | `SELECT 1` only; no connections/disk/bloat/slow-query |
| Redis | Partial | Partial | Broker connectivity + cache probe + circuit breaker; no memory/eviction/latency card |
| Database Administration | ❌ No | No | No migration status, backup verification, pool, vacuum |
| Volumes | ❌ No | No | No disk/volume/media/S3 usage — capacity exhaustion is blind |
| Queues | Partial | Partial | `LLEN "celery"` only; **`chat` queue not measured** |
| Scheduler health | ✅ Yes | ✅ Yes | status, drift_seconds, cadence, MISSED_RUN/ENGINE_STARVATION |
| API health | ✅ Yes | Mostly | 24h volume, avg/P95, error rate, per-endpoint, channel split |

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
| Model Interface | Partial | No adapter health/error card; inferred via latency |
| OpenAI connectivity | ❌ No | No upstream ping/health/error-rate — outage inferred downstream |
| Streaming generation | Partial | TTFT tracked; no stream dropout/abort card |
| Scheduled Check-ins | ✅ Yes | COSSCHED, COSDELIV, CDCE_CI heartbeats |
| Notifications | ✅ Yes | DNE heartbeat + DELIVERY_RETRY_SPIKE |
| Action execution | ✅ Yes | `aafr` metrics (success/blocked/top-failure) |
| Confirmation queue | ❌ No | Depth/staleness not measured |
| Audit pipeline | Partial | DecisionRecord in feed; no lag/failure metric |
| Signal pipeline | ✅ Yes | Per-domain freshness/volume/diversity + drought/diversity detectors |
| Goal momentum | ❌ No | Nightly Beat task, not a registered engine → no heartbeat/MISSED_RUN |
| Deterministic Understanding | Partial | SUE heartbeat; classifier drift not surfaced |
| Multimodal ingestion | Partial | `_get_ingestion_stats()`; no capture/transcription failure card |
| Artifact storage | ❌ No | S3 audio bucket + media volume unmonitored |
| Conversation attachment persistence | ❌ No | No durability health |
| Duplicate detection | ❌ No | No dedup rate/failure metric |
| Background cleanup jobs | ❌ No | Beat tasks, not engines → no heartbeat |
| Image retention jobs | ❌ No | Capture 72h/expiry deletion not surfaced |
| Queue backlog | Partial | `celery` queue thresholds; `chat` invisible |
| Failure monitoring | ✅ Yes | ERROR_SPIKE + aafr + failed_1h |
| Retry monitoring | Partial | Only DNE delivery retries; general Celery retries not aggregated |
| Dead-job detection | ❌ No | No dead-letter/stuck/orphaned-job alarm |
| Scheduler drift | ✅ Yes | drift_seconds + MISSED_RUN + ENGINE_STARVATION |

Every monitored item exposes Healthy / Degraded / Failed. The **owner** dimension is currently absent system-wide (see backlog OPS-6).

---

## 4. Ranked remediation backlog (phased)

The observability gaps below run in production but have no operational health. Each is a tracked follow-up, not a milestone blocker.

| ID | Gap | Impact | Phase |
|---|---|---|---|
| **OPS-1** | ~10 non-engine Beat tasks are structurally invisible (Goal momentum, `cleanup_soft_deletes`, capture retention/reminders, celebrations, digests, `cos_keepalive`). No heartbeat → **MISSED_RUN never fires**. | Highest — silent scheduled-job death | Next |
| **OPS-2** | Volumes / Artifact storage / DB storage capacity unmonitored | High — classic outage cause is blind | Next |
| **OPS-3** | `chat` queue + chatworker backlog not measured (`LLEN "celery"` only) | High — the exact P0 the chatworker exists for | Next |
| **OPS-4** | OpenAI connectivity / Model Interface health not surfaced | High — LLM outage seen only after downstream damage | Next |
| **OPS-5** | PostgreSQL depth + DB administration (connections, migrations, bloat, backup verification) | Medium | Following |
| **OPS-6** | No `owner` field on any component (cross-cutting; add via engine registry) | Medium | Following |
| **OPS-7** | Dead-job / stuck-task / general Celery-retry aggregation | Medium | Following |
| **OPS-8** | Confirmation queue, attachment persistence, duplicate detection, audit-pipeline lag health | Medium | Following |
| **OPS-9** | Build Runner / deploy pipeline observability (note: every deploy silently runs `load_initial_data` + `recalculate_task_priorities`) | Low–Medium | Later |
| **OPS-10** | Celery Beat directly measured (not inferred from ISE/SAME) | Low–Medium | Later |

**Recommended fix for OPS-1 (the biggest hole):** register the plain Beat tasks as engines (or add a generic Beat-schedule-vs-actual-run reconciler) so MISSED_RUN covers every scheduled job. This single change closes Goal momentum, Background cleanup, and Image-retention observability at once.

---

## 5. Human-judgment items recorded

- **`/_health/` split:** DB/Redis/scheduler liveness IS checked at `/_health/` (Railway + uptime monitors) but is not on the Ops Wall. Decision pending: mirror infra liveness onto the wall, or accept the split (Ops Wall = intelligence/execution; `/_health/` = infra).
- **"Engine ran" vs "service healthy":** many logical services are "partial" because the underlying engine heartbeat is monitored but output correctness is not. Whether heartbeat satisfies "healthy" for a given service is a per-service call.
- **Some logical names are conceptual** (Current Action = 2 files, Mission Link = 7 files) — confirm which warrant a dedicated card vs. which are internal terms before treating each as a hard gap.
