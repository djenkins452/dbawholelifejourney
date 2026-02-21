# Vegas Ops Wall v2 — Architecture Report

**Date:** 2026-02-21
**Author:** Claude Code
**Status:** Deployed

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Ops Wall UI                          │
│     /admin-console/ops/  (Vegas-grade dark theme)       │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Posture  │  │ SAME     │  │ Watchlist │              │
│  │ Banner   │  │ Narration│  │ Anomalies│              │
│  └──────────┘  └──────────┘  └──────────┘              │
│                                                         │
│  ┌──────────────────────────────────────────────┐       │
│  │  Engine Cards (9 core engines)               │       │
│  │  Status | Cadence | Sparkline | Counters     │       │
│  └──────────────────────────────────────────────┘       │
│                                                         │
│  ┌──────────────────────────────────────────────┐       │
│  │  SOC Live Feed (2s polling)                  │       │
│  │  Filter: All | Errors | Decisions            │       │
│  └──────────────────────────────────────────────┘       │
└─────────────────────────────────────────────────────────┘
         │ polls every 2s
         ▼
┌─────────────────────────────────────────────────────────┐
│              /admin-console/ops/stream/                  │
│                                                         │
│  Returns JSON:                                          │
│  - engine_cards (status, sparkline, miss/error counts)  │
│  - narrative (SAME posture + bullets + recs)            │
│  - anomalies (active watchlist)                         │
│  - feed (incremental since cursor)                      │
│  - posture (OK / DEGRADED / AT_RISK)                   │
└─────────────────────────────────────────────────────────┘
         │ reads from
         ▼
┌─────────────────────────────────────────────────────────┐
│                  SAME Engine                            │
│    (System Autonomous Monitoring Engine)                 │
│                                                         │
│  Deterministic. No OpenAI. Runs locally.                │
│                                                         │
│  1. Compute heartbeats (EngineHeartbeat)                │
│  2. Detect anomalies (7 rules)                          │
│  3. Reconcile active/resolved anomalies (OpsAnomaly)    │
│  4. Generate narrative (OpsNarrativeSnapshot)            │
└─────────────────────────────────────────────────────────┘
         │ reads from
         ▼
┌─────────────────────────────────────────────────────────┐
│              Observability Data Layer                    │
│                                                         │
│  EngineRun       — Per-engine execution records         │
│  DecisionRecord  — Why engines made decisions           │
│  EngineSpan      — Sub-step tracing                     │
│  EngineHeartbeat — Expected vs actual cadence           │
│  EngineExpectedCadence — Configurable cadence config    │
└─────────────────────────────────────────────────────────┘
```

---

## New Models

| Model | Table | Purpose |
|-------|-------|---------|
| EngineExpectedCadence | `core_engine_expected_cadence` | Configurable expected run interval per engine |
| EngineHeartbeat | `core_engine_heartbeat` | Tracks OK/LATE/MISSED/ERROR status per engine |
| AdminIntervention | `core_admin_intervention` | Audit trail for admin actions via Ops Wall |
| OpsAnomaly | `core_ops_anomaly` | Persistent anomaly records with lifecycle |
| OpsNarrativeSnapshot | `core_ops_narrative_snapshot` | SAME narrative: posture + bullets + recommendations |

---

## Anomaly Types & Thresholds

| Type | Trigger | Severity | Engine |
|------|---------|----------|--------|
| MISSED_RUN | now > next_expected + jitter | P1 (>3x interval), P2 | Any |
| ERROR_SPIKE | 30m errors > 3x 24h baseline | P1 (>10 errors), P2 | Any |
| CONFIDENCE_VOLATILITY | UAL confidence stddev > 0.3 (24h, >=5 samples) | P3 | UAL |
| SUPPRESSION_STORM | ICQG 30m suppressions > 3x 7d baseline | P2 | ICQG |
| LOOPING_REMINDER | Same DNE decision >=3x in 2h | P2 | DNE |
| ENGINE_STARVATION | Frequent engine has 0 runs in 24h | P1 | UAL, SAE, PIE, DNE, PGE, ICQG |
| DELIVERY_RETRY_SPIKE | DNE 30m runs > 3x 24h baseline | P2 | DNE |

---

## Admin Action Commands

| Action | Target | Effect | Safety |
|--------|--------|--------|--------|
| rerun_engine | DBE, WIRE, DNE | Re-runs engine entry point with trace context | User-required engines return info message |
| requeue_job | Any | Same as rerun (no queue system currently) | Safe |
| clear_suppression_cache | ICQG | Deletes QualitySuppressionRecord from last 24h | Logged |
| restart_scheduler | ISE | Signals restart on next cron cycle | No-op, informational |
| acknowledge_anomaly | Any | Resolves all active anomalies for engine | Logged |

All actions:
- Create AdminIntervention record
- Generate trace_id (source=admin_action)
- Return success/failure with detail message
- Never crash on failure (try/except wrapped)

---

## Routes

| Route | View | Purpose |
|-------|------|---------|
| `/admin-console/ops/` | OperationsWallView | Flagship Vegas Ops Wall |
| `/admin-console/ops/stream/` | OpsStreamView | JSON polling (2s) |
| `/admin-console/ops/actions/` | OpsActionView | POST admin actions |
| `/admin-console/ops/all-engines/` | AllEnginesView | Full engine table |

---

## Engine Cadence Defaults

| Engine | Interval | Jitter | Notes |
|--------|----------|--------|-------|
| UAL | 5m (300s) | 2m (120s) | Per-request, fires on user activity |
| SAE | 5m (300s) | 2m (120s) | Per-request |
| PIE | 5m (300s) | 2m (120s) | Per-request |
| PRIE | 1h (3600s) | 5m (300s) | Scheduler |
| PGE | 1h (3600s) | 5m (300s) | Scheduler |
| ICQG | 1h (3600s) | 5m (300s) | Scheduler |
| DNE | 1h (3600s) | 5m (300s) | Scheduler |
| DBE | 24h (86400s) | 1h (3600s) | Daily |
| WIRE | 7d (604800s) | 24h (86400s) | Weekly |
| GLOE | 24h (86400s) | 1h (3600s) | Scheduler |

Override via Django Admin → EngineExpectedCadence.

---

## How to Extend Cadence Config for New Engines

1. Add engine to `ENGINE_CADENCES` dict in `ops_aggregates.py`
2. Add to `ALL_ENGINES` list if it should appear on Ops Wall
3. Run `seed_cadence_config()` to create database record
4. Or manually create via Django Admin → EngineExpectedCadence

---

## What SAME is "Watching"

SAME evaluates these conditions on every run:
1. **Cadence drift** — Any engine approaching its missed threshold
2. **Error patterns** — Rolling 30m error rates vs 24h baseline
3. **UAL confidence** — Standard deviation across 24h arbitration decisions
4. **Suppression behavior** — ICQG suppression rate vs 7d baseline
5. **Delivery patterns** — DNE run frequency vs 24h baseline
6. **Content loops** — Repeated identical DNE decisions within 2h
7. **Engine health** — Whether frequent engines have run in last 24h

---

## Test Coverage

42 tests covering:
- Model CRUD and constraints (5 models)
- Heartbeat calculator (OK, LATE, MISSED, database override)
- SAME anomaly detection (missed runs, error spikes, suppression storms, confidence volatility)
- Anomaly reconciliation (create, update, resolve lifecycle)
- SAME narrative generation (posture, headlines, bullets)
- Ops stream endpoint (JSON structure, incremental cursor)
- Admin actions (intervention audit, trace_id, acknowledge)
- Access control (staff-only, non-staff blocked)

---

## Files Modified/Created

### New Files
- `apps/core/ai_observability/heartbeat.py` — Heartbeat calculator
- `apps/core/ai_observability/same_engine.py` — SAME engine
- `apps/core/ai_observability/tests_ops_wall_v2.py` — 42 tests
- `apps/core/migrations/0079_vegas_ops_wall_v2_models.py` — Migration
- `templates/admin_console/all_engines.html` — All Engines view
- `docs/OPS_WALL_V2_REPORT.md` — This document

### Modified Files
- `apps/core/ai_observability/models.py` — 5 new models added
- `apps/core/ai_observability/admin.py` — Admin registration for new models
- `apps/core/ai_observability/ops_views.py` — Rewritten: OpsStreamView, OpsActionView, AllEnginesView
- `apps/admin_console/urls.py` — New routes: stream, actions, all-engines
- `templates/admin_console/operations_wall.html` — Full Vegas UI redesign
