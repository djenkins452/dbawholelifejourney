# Ops Command Center Evolution — Implementation Report

**Date:** 2026-02-21
**Author:** Claude Code
**Status:** Deployed
**Project Tracker:** `docs/project.md`

---

## Executive Summary

The Vegas Ops Wall has been evolved from a monitoring dashboard into a production-grade Intelligence Operating System across 10 phases in two iterations:

**Iteration 1 (Phases 1–5):** Intelligence features — background execution, integrity index, escalation state machine, cadence visualization, autonomous remediation.

**Iteration 2 (Phases 6–10):** Infrastructure — migrated SAME scheduling from APScheduler to Celery + Redis with dedicated worker/beat services on Railway.

**Iteration 3 (Phase 11):** Visual architecture — enterprise-grade UI redesign with Apache ECharts, glass-morphism, smart DOM patching.

**106 total tests. 3 new migrations. 2 new dependencies. 0 regressions.**

---

## Architecture After Evolution

```
┌─────────────────────────────────────────────────────────────────┐
│              Redis (Railway addon / localhost:6379)              │
└───────────────────────┬─────────────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
┌───────┴─────────┐           ┌─────────┴───────────┐
│  Celery Beat    │           │  APScheduler        │
│  (1 instance)   │           │  (wsgi.py, 15 jobs) │
│                 │           │  SMS, ISE, life,     │
│  SAME cycle     │           │  capture, faith...   │
│  every 60s      │           └─────────────────────┘
└────────┬────────┘
         │
┌────────┴────────┐
│  Celery Worker  │
│  (concurrency=2)│
└────────┬────────┘
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

## Iteration 2 — Celery + Redis Infrastructure (Phases 6–10)

### Phase 6 — Remove APScheduler SAME Scheduling

**Problem:** APScheduler runs in-process — if the Gunicorn worker dies, SAME stops.
**Solution:** Removed SAME Job 16 from wsgi.py. APScheduler retains 15 non-SAME jobs.

### Phase 7 — Celery App Factory + Settings

**What was created:**
- `config/celery.py` — Celery app factory with Django integration and autodiscovery
- `config/__init__.py` — Updated to export `celery_app` for Django startup
- `config/settings.py` — Added `CELERY_*` settings with Redis broker config
- `requirements.txt` — Added `celery>=5.4.0` and `redis>=5.0.0`

### Phase 8 — SAME Celery Task + Beat Schedule

**What was created:**
- `apps/core/tasks.py` — `run_same_cycle_task` shared task
  - `bind=True`, `max_retries=3`, `default_retry_delay=10`
  - `acks_late=True`, `reject_on_worker_lost=True`
  - SoftTimeLimitExceeded handling (returns timeout, no retry)
  - Duration logging on every execution
- Beat schedule: `"run-same-cycle-every-60-seconds"` → 60.0s interval

### Phase 9 — Hardening

| Safeguard | Implementation |
|-----------|---------------|
| Overlap prevention | DB SchedulerLock unchanged — prevents duplicate SAME execution |
| Soft time limit | 50 seconds — raises SoftTimeLimitExceeded |
| Hard time limit | 120 seconds — worker kills task |
| Worker recycling | max_tasks_per_child=500 |
| Task acknowledgment | acks_late=True — re-delivered if worker crashes |
| Retry safety | DB lock released in finally block; retries re-acquire fresh lock |

### Phase 10 — Railway Deployment

| Service | Command |
|---------|---------|
| Web | `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT` |
| Worker | `celery -A config worker --loglevel=info --concurrency=2` |
| Beat | `celery -A config beat --loglevel=info` |

**Required:** Redis addon on Railway (sets `REDIS_URL` automatically).

**How to run locally:**
```bash
# Option A: Full Celery stack
redis-server &
celery -A config worker --loglevel=info &
celery -A config beat --loglevel=info &
python manage.py runserver

# Option B: Direct invocation (no Redis needed)
python manage.py shell -c "from apps.core.jobs import run_same_cycle; run_same_cycle()"
```

**How to revert to APScheduler:**
1. Remove Celery settings from `config/settings.py`
2. Remove `celery_app` import from `config/__init__.py`
3. Re-add Job 16 to `config/wsgi.py` (see git history)
4. Remove `celery` and `redis` from `requirements.txt`

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
| **Subtotal (ops_wall_v2)** | **82** | |
| CelerySettingsTest | 7 | Broker, serialization, timezone, limits |
| CeleryBeatScheduleTest | 4 | Schedule exists, task name, interval |
| CeleryAppTest | 2 | App importable, init export |
| SAMECeleryTaskTest | 4 | Calls run_same_cycle, duration, exception, timeout |
| DBLockProtectionTest | 4 | Lock prevents concurrent, stale override, release |
| NoAPSchedulerSAMERemnantTest | 3 | No SAME in wsgi, 15 jobs, Celery note |
| **Subtotal (tests_celery)** | **24** | |
| **Grand Total** | **106** | |

**Bonus fix:** `tests_diagnostics.py:test_ops_poll_staff_access` — updated v1 response key assertions to match v2 keys.

---

## Migrations

| Migration | Purpose |
|-----------|---------|
| `0080_system_integrity_snapshot` | SystemIntegritySnapshot model |
| `0081_anomaly_escalation_fields` | original_severity, escalation_count, last_escalated_at on OpsAnomaly |
| `0082_intervention_system_initiated` | is_system_initiated on AdminIntervention + new action types |

## Dependencies Added

| Package | Version | Purpose |
|---------|---------|---------|
| `celery` | ≥5.4.0 | Distributed task queue |
| `redis` | ≥5.0.0 | Redis Python client (broker/backend) |
| `echarts` | 5.5.1 (CDN) | Interactive charting library (frontend only) |

## Iteration 3 — Enterprise Visual Redesign (Phase 11)

### Phase 11 — Ops Command Center v3 UI

**Problem:** The backend intelligence (SAME pipeline, integrity index, escalation, remediation) was powerful, but the UI was utilitarian — flat cards, CSS-only sparkline bars, basic timeline strips. Not conference-ready.

**Solution:** Full frontend visual architecture overhaul across 7 sub-phases. Zero backend changes.

#### Sub-Phase 11a — Apache ECharts Integration

| Item | Detail |
|------|--------|
| Library | ECharts 5.5.1 via CDN (`<script nonce>` for CSP) |
| Chart builders | `buildIntegrityGauge(score, posture)` — radial ring gauge |
| | `buildEngineTrendChart(sparklineData, status)` — smooth area chart per engine |
| | `buildIntegrityTrendChart(history)` — 30-snapshot area sparkline with tooltips |
| | `buildCadenceChart(timeline, windowMinutes)` — line + scatter + effectScatter |
| Instance management | `chartRegistry{}` with `getChart()`, `disposeChart()`, `resizeAllCharts()` |
| Update strategy | `setOption()` merge mode — no full redraw on each 2s poll |
| Integrity history | Separate fetch from `/admin-console/ops/integrity/` every 30s |

#### Sub-Phase 11b — Layout Hierarchy Redesign

```
┌─────────────────────────────────────────────────────────────────┐
│  SYSTEM INTEGRITY HERO                                          │
│  ┌──────────┐  ┌──────────────────────┐  ┌───────────────────┐ │
│  │  Radial   │  │ Score: 87            │  │ 30-Snapshot Trend │ │
│  │  Gauge    │  │ Posture: NOMINAL     │  │ (ECharts area)    │ │
│  │ (ECharts) │  │ 5 component metrics  │  │                   │ │
│  └──────────┘  └──────────────────────┘  └───────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│  POSTURE BANNER — ● System Operational                          │
├──────────────────┬──────────────────┬───────────────────────────┤
│  What's Happening│  Recommendations │  Watching Next            │
│  • ...           │  • ...           │  • ...                    │
├──────────────────┴──────────────────┴───────────────────────────┤
│  ENGINE STATUS                                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐│
│  │PIE [Interp]│  │SAE [Exec]  │  │PRIE [Post] │  │ WATCHLIST ││
│  │ OK         │  │ OK         │  │ OK         │  │           ││
│  │[trend line]│  │[trend line]│  │[trend line]│  │ Anomaly   ││
│  │Stats: 4-col│  │Stats: 4-col│  │Stats: 4-col│  │ cards     ││
│  │[cadence]   │  │[cadence]   │  │[cadence]   │  │           ││
│  └────────────┘  └────────────┘  └────────────┘  └───────────┘│
├─────────────────────────────────────────────────────────────────┤
│  LIVE FEED (SOC)                     [All] [Errors] [Decisions] │
│  14:32:05  PIE  Processed journal entry | 45ms                  │
└─────────────────────────────────────────────────────────────────┘
```

#### Sub-Phase 11c — Visual System Upgrade

| Element | Before | After |
|---------|--------|-------|
| Background | Flat `#0a0e1a` | Gradient `#0B1020 → #0E1428` (165deg) |
| Cards | Solid `#111827` + 1px border | Glass: `rgba(17,24,42,0.65)` + `backdrop-filter: blur(16px)` |
| Shadows | None | `0 4px 24px rgba(0,0,0,0.25)` / `0 8px 40px` on hover |
| Engine badges | None | Color-coded category: Interpret (cyan), Execute (purple), Post-Exec (amber), System (slate) |
| Scrollbars | Browser default | Custom 6px with `rgba(255,255,255,0.1)` thumb |
| Hover effects | Border color change | Border + `translateY(-1px)` + shadow elevation |

#### Sub-Phase 11d — ECharts Cadence Timelines (replaces CSS strips)

| Feature | CSS Strip (before) | ECharts Chart (after) |
|---------|-------------------|----------------------|
| Height | 12px | 36px |
| Run visualization | 4px colored rectangles | Smooth line with gradient fill |
| Error display | Red rectangles | Red scatter points with glow shadow |
| Missed ticks | Red bordered rectangles | Triangle scatter markers |
| Threshold | None | Dashed amber line at avg×1.5 |
| Latest run | None | Animated `effectScatter` with ripple pulse |
| Interactivity | `title` attribute only | ECharts tooltip on hover |

#### Sub-Phase 11e — Micro-Animations

| Animation | Trigger | Implementation |
|-----------|---------|---------------|
| Score count-up | Integrity score changes | `requestAnimationFrame` loop with `easeOutCubic`, 600ms |
| Escalation pulse | Anomaly with `escalation_count > 0` | CSS `@keyframes escPulse` — opacity + scale, 1.5s infinite |
| Card status glow | Engine status value changes | CSS `@keyframes statusGlow` — box-shadow fade, 1.2s |
| Page entrance | Initial load | CSS `@keyframes opsEnter` — `translateY(12px)` → 0, staggered 50ms per section |
| Risk banner pulse | Posture = AT_RISK | CSS `@keyframes pulseRisk` — opacity oscillation, 2s infinite |

#### Sub-Phase 11f — Responsiveness

| Breakpoint | Engine Grid | Integrity Hero | Narration |
|------------|-------------|----------------|-----------|
| > 1400px | 3 columns | 3-area grid (gauge / info / trend) | 3 columns |
| ≤ 1400px | 2 columns | 3-area grid | 3 columns |
| ≤ 1024px | 2 columns | 2-area (trend wraps below) | 1 column |
| ≤ 768px | 1 column | 1-column stacked, centered | 1 column |

#### Sub-Phase 11g — Polish

- Whitespace rhythm: 20px section gaps (was 16px), 14px card gaps (was 10px)
- Typography: score at 4rem/800wt, labels at 0.625rem with 0.14em tracking
- Font smoothing: `-webkit-font-smoothing: antialiased`
- Border radius: 10px standard, 6px for small elements
- Transition speed: 0.2s ease standard

#### Smart DOM Patching

**Problem:** Original code cleared and rebuilt all engine cards every 2s poll. With ECharts, this would destroy and recreate chart instances each cycle — causing flicker and memory pressure.

**Solution:** Engine card diffing strategy:
1. Track `currentEngineList` (array of engine names)
2. On poll, compare new engine names with current
3. **Same list** → update card text content + chart `setOption()` in place
4. **Different list** → dispose old charts, full rebuild, reinitialize charts
5. Status change detection triggers temporary `status-changed` CSS class for glow animation

---

## Architecture After v3 UI

```
┌─────────────────────────────────────────────────────────────────┐
│              Redis (Railway addon / localhost:6379)              │
└───────────────────────┬─────────────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
┌───────┴─────────┐           ┌─────────┴───────────┐
│  Celery Beat    │           │  APScheduler        │
│  (1 instance)   │           │  (wsgi.py, 15 jobs) │
│  SAME cycle     │           └─────────────────────┘
│  every 60s      │
└────────┬────────┘
         │
┌────────┴────────┐
│  Celery Worker  │
│  (concurrency=2)│
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SAME Engine Pipeline                          │
│  Steps 1–6 unchanged from Iteration 1                          │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│             Ops Command Center v3 UI (read-only)                │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ INTEGRITY HERO: Gauge (ECharts) + Score + Trend Sparkline│  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Posture Banner (glass) + SAME Narration (3-col, glass)   │  │
│  └──────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────┐ ┌─────────────────┐ │
│  │ Engine Cards (glass, 3-col grid)     │ │ Watchlist (glass)│ │
│  │  • Category badges                   │ │  • Escalation    │ │
│  │  • ECharts trend lines               │ │    pulse badges  │ │
│  │  • 4-stat strips                     │ │  • Action buttons│ │
│  │  • ECharts cadence timelines         │ │                  │ │
│  │  • Smart DOM patching                │ │                  │ │
│  └──────────────────────────────────────┘ └─────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ SOC Live Feed (monospace, glass, custom scrollbar)       │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Polling: /ops/stream/ (2s) + /ops/cadence/ (on render)        │
│           /ops/integrity/ (30s, history for trend sparkline)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Known Limitations

1. **Beat must be single instance** — running multiple Beat processes duplicates scheduled tasks
2. **Redis required for SAME** — if Redis is down, SAME won't run (DB lock prevents stale state)
3. **APScheduler still handles 15 other jobs** — not yet migrated to Celery
4. **No Celery monitoring** — Flower or similar not yet deployed
5. **ECharts CDN dependency** — if jsdelivr is unreachable, charts degrade to empty containers (data still polls and text updates normally)

---

## Files Modified (All Iterations)

### Iteration 1 (Phases 1–5)

| File | Changes |
|------|---------|
| `apps/core/jobs.py` | Added `run_same_cycle()` |
| `config/wsgi.py` | Registered then removed SAME Job 16 |
| `apps/core/ai_observability/models.py` | SystemIntegritySnapshot, escalation fields, system-initiated flag |
| `apps/core/ai_observability/same_engine.py` | Integrity, escalation, remediation logic |
| `apps/core/ai_observability/ops_views.py` | IntegrityIndexView, CadenceTimelineView |
| `apps/admin_console/urls.py` | 2 new routes |
| `templates/admin_console/operations_wall.html` | Integrity tile, cadence strips, escalation badges |
| `apps/core/ai_observability/tests_ops_wall_v2.py` | 40 new tests (82 total) |
| `apps/core/ai_observability/tests_diagnostics.py` | Fixed v2 key assertions |
| `docs/project.md` | Full project tracker |

### Iteration 2 (Phases 6–10)

| File | Changes |
|------|---------|
| `config/wsgi.py` | Removed SAME Job 16, updated job count to 15 |
| `config/celery.py` | **NEW** — Celery app factory |
| `config/__init__.py` | Added `celery_app` export |
| `config/settings.py` | Added CELERY_* and REDIS_URL settings |
| `apps/core/tasks.py` | **NEW** — `run_same_cycle_task` Celery shared task |
| `apps/core/jobs.py` | Updated docstring (Celery reference) |
| `apps/core/tests_celery.py` | **NEW** — 24 Celery infrastructure tests |
| `requirements.txt` | Added `celery>=5.4.0`, `redis>=5.0.0` |
| `docs/project.md` | Added phases 6–10 tracking |

### Iteration 3 (Phase 11)

| File | Changes |
|------|---------|
| `templates/admin_console/operations_wall.html` | Full v3 visual redesign (968 insertions, 406 deletions) |
| `docs/project.md` | Added phase 11 |
| `docs/wlj_claude_changelog.md` | Changelog entry |

---

*Generated: 2026-02-21 (updated with v3 visual redesign)*
