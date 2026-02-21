# Ops Command Center Evolution — Project Tracker

**Project:** Evolve Vegas Ops Wall into Production-Grade Intelligence Operating System
**Started:** 2026-02-21
**Status:** Complete

---

## Phase Summary

| Phase | Title | Status | Migration | Tests Added |
|-------|-------|--------|-----------|-------------|
| 1 | SAME Background Execution Refactor | **Complete** | None needed | 7 tests |
| 2 | System Integrity Index | **Complete** | 0080_system_integrity_snapshot | 13 tests |
| 3 | Escalation State Machine | **Complete** | 0081_anomaly_escalation_fields | 7 tests |
| 4 | Temporal Engine Cadence Visualization | **Complete** | None needed | 6 tests |
| 5 | Controlled Autonomous Remediation | **Complete** | 0082_intervention_system_initiated | 7 tests |
| 6 | Celery + Redis: Remove APScheduler SAME | **Complete** | None | 3 tests |
| 7 | Celery + Redis: App factory + settings | **Complete** | None | 11 tests |
| 8 | Celery + Redis: SAME task + Beat schedule | **Complete** | None | 4 tests |
| 9 | Celery + Redis: Hardening + DB lock tests | **Complete** | None | 4 tests |
| 10 | Celery + Redis: Railway deployment docs | **Complete** | None | 2 tests |
| 11 | UI v3: Enterprise Visual Redesign | **Complete** | None | 0 (frontend-only) |
| V2 | Final Visual Upgrade (7 sub-phases) | **Complete** | None | 0 (frontend-only) |

---

## Phase 1 — SAME Background Execution Refactor

**Objective:** Monitoring must not depend on browser polling.

**Tasks:**

| # | Task | Status |
|---|------|--------|
| 1.1 | Add SAME cycle job to APScheduler (60s interval) | Complete |
| 1.2 | Implement concurrency guard (DB lock) for SAME execution | Complete |
| 1.3 | Make run_same() idempotent with overlap prevention | Complete |
| 1.4 | Refactor OpsStream endpoint to read-only (no SAME execution) | Complete (already read-only) |
| 1.5 | Ensure latest heartbeats, anomalies, narrative always persisted | Complete |
| 1.6 | Add tests for background execution | Complete |
| 1.7 | Update docs/project.md | Complete |

**Files Modified:** `apps/core/jobs.py`, `config/wsgi.py`
**Files Created:** None
**Migrations:** None needed (reuses existing SchedulerLock model)
**Tests Added:** 7 tests in `SAMEBackgroundExecutionTest` class

---

## Phase 2 — System Integrity Index

**Objective:** Create executive-level compression metric (0–100).

**Tasks:**

| # | Task | Status |
|---|------|--------|
| 2.1 | Create SystemIntegritySnapshot model | Complete |
| 2.2 | Implement score calculation (engine health, severity weights, penalties) | Complete |
| 2.3 | Persist snapshot every SAME cycle | Complete |
| 2.4 | Expose via stream endpoint | Complete |
| 2.5 | Add dedicated API endpoint | Complete |
| 2.6 | Add UI tile to Ops Wall | Complete |
| 2.7 | Add unit tests for score calculation | Complete |
| 2.8 | Update docs/project.md | Complete |

**Files Modified:** `apps/core/ai_observability/models.py`, `apps/core/ai_observability/same_engine.py`, `apps/core/ai_observability/ops_views.py`, `apps/admin_console/urls.py`, `templates/admin_console/operations_wall.html`
**Files Created:** None
**Migrations:** `apps/core/migrations/0080_system_integrity_snapshot.py`
**Tests Added:** 13 tests: `SystemIntegritySnapshotModelTest` (2), `IntegrityScoreCalculationTest` (7), `IntegrityEndpointTest` (4)

---

## Phase 3 — Escalation State Machine

**Objective:** Anomalies must escalate over time.

**Tasks:**

| # | Task | Status |
|---|------|--------|
| 3.1 | Add escalation fields to OpsAnomaly (migration) | Complete |
| 3.2 | Implement configurable escalation thresholds | Complete |
| 3.3 | Add automatic severity promotion logic | Complete |
| 3.4 | Add cooldown logic to prevent flapping | Complete |
| 3.5 | Update narrative to reference escalations | Complete |
| 3.6 | Update stream endpoint with escalation data | Complete |
| 3.7 | Add UI escalation badge display | Complete |
| 3.8 | Add tests for promotion, dedup, resolution reset | Complete |
| 3.9 | Update docs/project.md | Complete |

**Files Modified:** `apps/core/ai_observability/models.py`, `apps/core/ai_observability/same_engine.py`, `apps/core/ai_observability/ops_views.py`, `templates/admin_console/operations_wall.html`
**Files Created:** None
**Migrations:** `apps/core/migrations/0081_anomaly_escalation_fields.py`
**Tests Added:** 7 tests in `EscalationStateMachineTest`

---

## Phase 4 — Temporal Engine Cadence Visualization

**Objective:** 30-minute rolling cadence timeline per engine.

**Tasks:**

| # | Task | Status |
|---|------|--------|
| 4.1 | New endpoint returning time-series heartbeat history | Complete |
| 4.2 | UI timeline strip with expected/actual cadence markers | Complete |
| 4.3 | Missed interval highlighting + hover tooltips | Complete |
| 4.4 | Query optimization (no re-trigger of SAME) | Complete |
| 4.5 | Add tests for new endpoint | Complete |
| 4.6 | Update docs/project.md | Complete |

**Files Modified:** `apps/core/ai_observability/ops_views.py`, `apps/admin_console/urls.py`, `templates/admin_console/operations_wall.html`
**Files Created:** None
**Migrations:** None needed
**Tests Added:** 6 tests in `CadenceTimelineTest`

---

## Phase 5 — Controlled Autonomous Remediation

**Objective:** Safe automatic actions for low-severity anomalies.

**Tasks:**

| # | Task | Status |
|---|------|--------|
| 5.1 | Auto-rerun for single missed run (P3 only) | Complete |
| 5.2 | Auto-clear suppression cache at threshold | Complete |
| 5.3 | Log system-generated AdminIntervention (system-initiated flag) | Complete |
| 5.4 | Add safeguards against infinite loops (max 3/cycle, 30m cooldown) | Complete |
| 5.5 | Add feature flag to enable/disable autonomous mode | Complete |
| 5.6 | Add tests (single-fire, logging, no recursion, disable) | Complete |
| 5.7 | Update docs/project.md | Complete |

**Files Modified:** `apps/core/ai_observability/models.py`, `apps/core/ai_observability/same_engine.py`
**Files Created:** None
**Migrations:** `apps/core/migrations/0082_intervention_system_initiated.py`
**Tests Added:** 7 tests in `AutonomousRemediationTest`

---

## Phase 6 — Remove APScheduler SAME Scheduling

**Objective:** Remove SAME job from APScheduler wsgi.py registration.

| # | Task | Status |
|---|------|--------|
| 6.1 | Remove Job 16 (run_same_cycle) from wsgi.py | Complete |
| 6.2 | Update job count from 16 to 15 | Complete |
| 6.3 | Add Celery migration note in wsgi.py | Complete |
| 6.4 | Verify app still boots normally | Complete |

**Files Modified:** `config/wsgi.py`
**Tests Added:** 3 tests in `NoAPSchedulerSAMERemnantTest`

---

## Phase 7 — Install and Configure Celery

**Objective:** Celery app factory, Redis broker, Django settings integration.

| # | Task | Status |
|---|------|--------|
| 7.1 | Add celery>=5.4.0 and redis>=5.0.0 to requirements.txt | Complete |
| 7.2 | Create config/celery.py (app factory, autodiscover) | Complete |
| 7.3 | Update config/__init__.py to export celery_app | Complete |
| 7.4 | Add CELERY_* settings to config/settings.py | Complete |
| 7.5 | Add REDIS_URL env var with localhost fallback | Complete |

**Files Modified:** `requirements.txt`, `config/settings.py`, `config/__init__.py`
**Files Created:** `config/celery.py`
**Tests Added:** 7 settings tests + 2 app tests + 2 Beat schedule tests = 11 tests

---

## Phase 8 — SAME Celery Task + Beat Schedule

**Objective:** Thin Celery task wrapper calling existing run_same_cycle().

| # | Task | Status |
|---|------|--------|
| 8.1 | Create apps/core/tasks.py with run_same_cycle_task | Complete |
| 8.2 | Configure shared_task with bind, max_retries, acks_late | Complete |
| 8.3 | Add SoftTimeLimitExceeded handling | Complete |
| 8.4 | Add duration logging | Complete |
| 8.5 | Configure Beat schedule (60s interval) | Complete |

**Files Created:** `apps/core/tasks.py`
**Tests Added:** 4 tests in `SAMECeleryTaskTest`

---

## Phase 9 — Hardening + DB Lock Protection

**Objective:** Ensure no duplicate execution, proper timeout, lock integrity.

| # | Task | Status |
|---|------|--------|
| 9.1 | soft_time_limit=50s, time_limit=120s | Complete |
| 9.2 | acks_late=True, reject_on_worker_lost=True | Complete |
| 9.3 | DB SchedulerLock still enforced (unchanged) | Complete |
| 9.4 | Retry does not bypass DB lock | Complete |
| 9.5 | Worker recycling (max_tasks_per_child=500) | Complete |

**Tests Added:** 4 tests in `DBLockProtectionTest`

---

## Phase 10 — Railway Deployment Structure

**Objective:** Document deployment topology and environment variables.

**Railway Services:**

| Service | Command | Purpose |
|---------|---------|---------|
| Web | `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT` | Django web server |
| Worker | `celery -A config worker --loglevel=info --concurrency=2` | Celery task execution |
| Beat | `celery -A config beat --loglevel=info` | Celery periodic scheduler |

**Required Environment Variables:**

| Variable | Required | Description |
|----------|----------|-------------|
| `REDIS_URL` | Yes | Redis connection string (auto-set by Railway Redis addon) |
| `CELERY_BROKER_URL` | No | Override for broker URL (defaults to REDIS_URL) |
| `CELERY_RESULT_BACKEND` | No | Override for result backend (defaults to REDIS_URL) |
| `AUTONOMOUS_REMEDIATION_ENABLED` | No | Enable/disable auto-remediation (default: True) |

**Redis Service:** Attach Railway Redis addon → sets `REDIS_URL` automatically.

**Local Development:**
- Redis not required for web server (APScheduler handles non-SAME jobs)
- To run SAME via Celery locally: `redis-server` + `celery -A config worker` + `celery -A config beat`
- Or just call `run_same_cycle()` directly from shell

**Scaling:**
- Workers can be scaled horizontally — DB lock prevents duplicate SAME execution
- Beat must remain single instance (only one scheduler)
- Web server scaling unchanged (Gunicorn workers)

---

## Architectural Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| AD-1 | ~~Use APScheduler for SAME~~ → Migrated to Celery Beat | APScheduler runs in-process and dies with Gunicorn workers; Celery provides isolated worker process |
| AD-2 | Use existing SchedulerLock model for SAME concurrency guard | Reuse proven DB-lock pattern from ISE scheduler |
| AD-3 | OpsStream endpoint becomes read-only (no SAME trigger) | Decouples monitoring from UI polling; background job maintains state |
| AD-4 | 5-component weighted scoring for System Integrity Index | Covers engine health (40pt), anomaly severity (50pt), error spike (10pt), suppression (5pt), confidence volatility (5pt) — total penalty subtracted from 100 |
| AD-5 | Escalation rules: P3→P2 @10min, P2→P1 @20min with 5min cooldown | Aggressive enough to surface real issues, cooldown prevents flapping |
| AD-6 | Autonomous remediation restricted to P3 + system engines only | DBE/WIRE/DNE are safe to auto-rerun; user-facing engines (UAL/SAE/PIE) never auto-acted on |
| AD-7 | Max 3 auto-actions per SAME cycle + 30min cooldown per engine | Prevents runaway remediation loops while still being useful |
| AD-8 | Celery task is a thin wrapper — no SAME logic in task | Keeps business logic in same_engine.py; Celery only triggers execution |
| AD-9 | Keep APScheduler for non-SAME jobs (SMS, ISE, etc.) | Incremental migration — avoids massive refactor; migrate others later |
| AD-10 | acks_late + reject_on_worker_lost for SAME task | Ensures task is re-delivered if worker crashes mid-execution |
| AD-11 | soft_time_limit=50s, hard time_limit=120s | Prevents stuck SAME cycles from blocking the worker indefinitely |

---

## Known Risks

| # | Risk | Mitigation |
|---|------|------------|
| R-1 | ~~APScheduler in-process~~ — Resolved by Celery migration | SAME now runs in dedicated Celery worker, independent of web process |
| R-2 | 60s SAME cycle may accumulate EngineHeartbeat rows | Add periodic cleanup or limit retained rows |
| R-3 | OpsAnomaly escalation could cause alert fatigue | Cooldown logic + configurable thresholds |
| R-4 | Autonomous remediation could mask real failures | Restricted to P3/system-only engines, max 3/cycle, 30min cooldown, full audit trail via AdminIntervention |
| R-5 | Celery Beat must be single instance | Running multiple Beat processes would duplicate scheduled tasks. Railway should run exactly one Beat service |
| R-6 | Redis availability required for SAME | If Redis is down, Celery cannot deliver tasks. DB lock prevents stale state but SAME won't run until Redis recovers |

---

## Phase V2 — Final Visual Upgrade

**Objective:** Elevate Ops Wall from 8/10 to 10/10 visual quality. Conference-demo ready.

**Sub-phases:**

| # | Sub-phase | Status |
|---|-----------|--------|
| V2.1 | Redesign System Integrity Hero (dominant score, delta, mini sparkline, progress bars) | Complete |
| V2.2 | Add Macro System Chart Row (anomaly trend + health distribution) | Complete |
| V2.3 | Engine Card Enhancements (metrics strip, phase colors, top accent, 15% taller charts) | Complete |
| V2.4 | Watchlist Drama (ambient empty state, slide-in, severity icons, glow) | Complete |
| V2.5 | Wall Mode (toggle, hide nav, clock, density, localStorage persistence) | Complete |
| V2.6 | Micro-Animations (score pop, glow sweep, fade-in, 200-400ms easing) | Complete |
| V2.7 | Visual Polish (glassmorphism refinement, typography hierarchy, contrast, spacing) | Complete |

**Files Modified:** `templates/admin_console/operations_wall.html` (819 insertions, 183 deletions)
**Backend Impact:** Zero — no models, views, URLs, SAME, Celery, or API changes
**Tests:** 173 tests pass, 0 regressions

---

## Future Enhancements

- Migrate remaining APScheduler jobs (SMS, ISE, life, capture) to Celery
- WebSocket push instead of polling for Ops Wall
- SAME cycle metrics (duration, anomaly counts) as EngineRun records
- Anomaly notification via SMS/email for P1 escalations
- Historical System Integrity Index charting
- Celery Flower monitoring dashboard
- Redis Sentinel for high-availability broker

---

*Last updated: 2026-02-21*
