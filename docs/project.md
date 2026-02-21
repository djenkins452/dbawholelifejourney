# Ops Command Center Evolution — Project Tracker

**Project:** Evolve Vegas Ops Wall into Production-Grade Intelligence Operating System
**Started:** 2026-02-21
**Status:** In Progress

---

## Phase Summary

| Phase | Title | Status | Migration | Tests Added |
|-------|-------|--------|-----------|-------------|
| 1 | SAME Background Execution Refactor | **Complete** | None needed | 7 tests |
| 2 | System Integrity Index | **Complete** | 0080_system_integrity_snapshot | 13 tests |
| 3 | Escalation State Machine | **Complete** | 0081_anomaly_escalation_fields | 7 tests |
| 4 | Temporal Engine Cadence Visualization | **Complete** | None needed | 6 tests |
| 5 | Controlled Autonomous Remediation | **Complete** | 0082_intervention_system_initiated | 7 tests |

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

## Architectural Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| AD-1 | Use APScheduler (not Celery) for SAME background job | Project already uses APScheduler via wsgi.py; no Celery infrastructure exists |
| AD-2 | Use existing SchedulerLock model for SAME concurrency guard | Reuse proven DB-lock pattern from ISE scheduler |
| AD-3 | OpsStream endpoint becomes read-only (no SAME trigger) | Decouples monitoring from UI polling; background job maintains state |
| AD-4 | 5-component weighted scoring for System Integrity Index | Covers engine health (40pt), anomaly severity (50pt), error spike (10pt), suppression (5pt), confidence volatility (5pt) — total penalty subtracted from 100 |
| AD-5 | Escalation rules: P3→P2 @10min, P2→P1 @20min with 5min cooldown | Aggressive enough to surface real issues, cooldown prevents flapping |
| AD-6 | Autonomous remediation restricted to P3 + system engines only | DBE/WIRE/DNE are safe to auto-rerun; user-facing engines (UAL/SAE/PIE) never auto-acted on |
| AD-7 | Max 3 auto-actions per SAME cycle + 30min cooldown per engine | Prevents runaway remediation loops while still being useful |

---

## Known Risks

| # | Risk | Mitigation |
|---|------|------------|
| R-1 | APScheduler runs in-process — if Gunicorn worker dies, SAME stops | SchedulerLock staleness timeout (10m) allows recovery on restart |
| R-2 | 60s SAME cycle may accumulate EngineHeartbeat rows | Add periodic cleanup or limit retained rows |
| R-3 | OpsAnomaly escalation could cause alert fatigue | Cooldown logic + configurable thresholds |
| R-4 | Autonomous remediation could mask real failures | Restricted to P3/system-only engines, max 3/cycle, 30min cooldown, full audit trail via AdminIntervention |

---

## Future Enhancements

- Redis-backed distributed lock for multi-container SAME dedup
- WebSocket push instead of polling for Ops Wall
- SAME cycle metrics (duration, anomaly counts) as EngineRun records
- Anomaly notification via SMS/email for P1 escalations
- Historical System Integrity Index charting

---

*Last updated: 2026-02-21*
