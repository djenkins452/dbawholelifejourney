# Ops Command Center Evolution — Implementation Report

**Date:** 2026-02-21
**Author:** Claude Code
**Status:** Deployed (`5bb6a0b`)
**Project Tracker:** `docs/project.md`

---

## Executive Summary

The Vegas Ops Wall has been evolved from a monitoring dashboard into a production-grade Intelligence Operating System across 5 phases. The system now runs autonomously in the background, computes executive-level health metrics, escalates anomalies over time, visualizes engine cadence, and can auto-remediate low-severity issues — all without human intervention.

**82 new tests. 3 new migrations. 0 regressions.**

---

## Architecture After Evolution

```
┌─────────────────────────────────────────────────────────────────┐
│                   APScheduler (wsgi.py)                         │
│                   Job 16: run_same_cycle (60s)                  │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SAME Engine Pipeline                          │
│                                                                 │
│  Step 1: Compute heartbeats (all engines)                       │
│  Step 2: Detect anomalies (7 detectors)                         │
│  Step 3: Reconcile anomaly lifecycle (active ↔ resolved)        │
│  Step 3.5: Escalate anomalies (P3→P2→P1)          ← NEW        │
│  Step 3.6: Autonomous remediation (P3/system only) ← NEW        │
│  Step 4: Generate narrative                                     │
│  Step 5: Compute System Integrity Index            ← NEW        │
│  Step 6: Persist all state                                      │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Ops Wall UI (read-only)                       │
│                                                                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Posture     │  │ Integrity    │  │ SAME Narration         │ │
│  │ Banner      │  │ Tile (0-100) │  │ (3-column)             │ │
│  └─────────────┘  └──────────────┘  └────────────────────────┘ │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ Engine Cards + Cadence Timeline Strips (30min rolling)     ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────────────────────────┐│
│  │ Watchlist         │  │ SOC Live Feed                       ││
│  │ (escalation       │  │ (filters: core/errors/decisions/    ││
│  │  badges)          │  │  anomalies)                         ││
│  └──────────────────┘  └──────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase Breakdown

### Phase 1 — SAME Background Execution Refactor

**Problem:** SAME only ran when someone polled the UI.
**Solution:** APScheduler Job 16 runs `run_same_cycle()` every 60 seconds with a `SchedulerLock` DB lock to prevent concurrent execution. OpsStream endpoint is read-only.

| Item | Detail |
|------|--------|
| Job function | `apps/core/jobs.py:run_same_cycle()` |
| Lock | `SchedulerLock(lock_name="same_execution")`, 120s timeout |
| Stale recovery | If lock age > 120s, new worker takes over |
| Tests | 7 (cycle execution, dedup, lock acquisition/release, stale override) |

### Phase 2 — System Integrity Index

**Problem:** No single metric to answer "how healthy is the system?"
**Solution:** 5-component weighted score computed every SAME cycle, stored in `SystemIntegritySnapshot`.

| Component | Max Penalty | Logic |
|-----------|-------------|-------|
| Engine health | 40 pts | % of engines not OK |
| Anomaly severity | 50 pts | P1=25, P2=10, P3=3, capped |
| Error spike | 10 pts | 30min error rate above baseline |
| Suppression rate | 5 pts | Above 50% threshold |
| Confidence volatility | 5 pts | stddev > 0.3 |

**Posture:** OPTIMAL ≥90 | NOMINAL ≥70 | DEGRADED ≥40 | CRITICAL <40

| Item | Detail |
|------|--------|
| Model | `SystemIntegritySnapshot` (score, posture, components JSON) |
| Endpoint | `GET /admin-console/ops/integrity/` (latest + 30-snapshot history) |
| UI | Color-coded tile between posture banner and narration bar |
| Migration | `0080_system_integrity_snapshot` |
| Tests | 13 (model, calculation, endpoint, stream integration) |

### Phase 3 — Escalation State Machine

**Problem:** Anomalies stayed at their initial severity forever.
**Solution:** Time-based escalation with cooldown to prevent flapping.

| Rule | Trigger | Result |
|------|---------|--------|
| P3 → P2 | Active > 10 minutes | Severity promoted, count incremented |
| P2 → P1 | Active > 20 minutes | Severity promoted, count incremented |
| P1 | Terminal | No further escalation |
| Cooldown | 5 minutes | Between successive escalations |
| Resolution | Anomaly resolved | `escalation_count` resets to 0 |

| Item | Detail |
|------|--------|
| Fields added | `original_severity`, `escalation_count`, `last_escalated_at` |
| UI | Escalation badge in watchlist (e.g., "ESC P3→P2") |
| Migration | `0081_anomaly_escalation_fields` |
| Tests | 7 (promotion, terminal, cooldown, resolution reset, stream) |

### Phase 4 — Temporal Engine Cadence Visualization

**Problem:** No way to see if engines are running on time over a window.
**Solution:** 30-minute rolling timeline strip per engine card.

| Item | Detail |
|------|--------|
| Endpoint | `GET /admin-console/ops/cadence/?minutes=30&engine=UAL` |
| Response | heartbeats, runs, expected_ticks, missed_ticks per engine |
| UI | CSS timeline strip: green ticks (heartbeats), blue dots (runs), red marks (missed) |
| Tests | 6 (JSON response, runs, expected ticks, auth, no SAME trigger, window cap) |

### Phase 5 — Controlled Autonomous Remediation

**Problem:** P3 issues on background engines sit until a human acts.
**Solution:** Safe, limited auto-remediation for low-severity anomalies.

| Action | Trigger | Scope |
|--------|---------|-------|
| Auto-rerun engine | P3 `MISSED_RUN` anomaly | System engines only (DBE, WIRE, DNE) |
| Auto-clear suppression | P3 `SUPPRESSION_STORM` anomaly | System engines only |

| Safeguard | Value |
|-----------|-------|
| Feature flag | `AUTONOMOUS_REMEDIATION_ENABLED` (default: True) |
| Max actions/cycle | 3 |
| Cooldown per engine | 30 minutes |
| Severity restriction | P3 only (never P2 or P1) |
| Engine restriction | DBE, WIRE, DNE only (never user-facing) |
| Audit trail | `AdminIntervention(is_system_initiated=True)` |

| Item | Detail |
|------|--------|
| Migration | `0082_intervention_system_initiated` |
| Tests | 7 (auto-rerun, severity gate, engine gate, cooldown, flag, max limit, audit) |

---

## Test Summary

| Test Class | Tests | Focus |
|------------|-------|-------|
| SAMEBackgroundExecutionTest | 7 | Background job, locking, idempotency |
| SystemIntegritySnapshotModelTest | 2 | Model creation, ordering |
| IntegrityScoreCalculationTest | 7 | Score math, components, posture mapping |
| IntegrityEndpointTest | 4 | API response, auth, stream integration |
| EscalationStateMachineTest | 7 | Promotion, cooldown, terminal, reset |
| CadenceTimelineTest | 6 | Timeline data, window, auth |
| AutonomousRemediationTest | 7 | Auto-actions, safeguards, audit |
| *Pre-existing (42)* | 42 | Original v2 test suite |
| **Total** | **82** | |

**Bonus fix:** `tests_diagnostics.py:test_ops_poll_staff_access` — updated v1 response key assertions to match v2 keys.

---

## Files Modified

| File | Changes |
|------|---------|
| `apps/core/jobs.py` | Added `run_same_cycle()` |
| `config/wsgi.py` | Registered Job 16 (SAME 60s) |
| `apps/core/ai_observability/models.py` | SystemIntegritySnapshot, escalation fields, system-initiated flag |
| `apps/core/ai_observability/same_engine.py` | Integrity, escalation, remediation logic |
| `apps/core/ai_observability/ops_views.py` | IntegrityIndexView, CadenceTimelineView |
| `apps/admin_console/urls.py` | 2 new routes |
| `templates/admin_console/operations_wall.html` | Integrity tile, cadence strips, escalation badges |
| `apps/core/ai_observability/tests_ops_wall_v2.py` | 40 new tests (82 total) |
| `apps/core/ai_observability/tests_diagnostics.py` | Fixed v2 key assertions |
| `docs/project.md` | Full project tracker |

## Migrations

| Migration | Purpose |
|-----------|---------|
| `0080_system_integrity_snapshot` | SystemIntegritySnapshot model |
| `0081_anomaly_escalation_fields` | original_severity, escalation_count, last_escalated_at on OpsAnomaly |
| `0082_intervention_system_initiated` | is_system_initiated on AdminIntervention + new action types |

---

## Architectural Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| AD-4 | 5-component weighted scoring | Covers all observable failure modes with tunable weights |
| AD-5 | Escalation: P3→P2 @10min, P2→P1 @20min | Aggressive enough to surface real issues; 5min cooldown prevents flapping |
| AD-6 | Remediation restricted to P3 + system engines | DBE/WIRE/DNE are safe to auto-rerun; user-facing engines never auto-acted on |
| AD-7 | Max 3 auto-actions/cycle + 30min cooldown | Prevents runaway loops while still being useful |

---

*Generated: 2026-02-21*
