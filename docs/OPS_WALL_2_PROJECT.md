# Ops Wall 2.0 — Project Document

**Status:** Architecture Review (awaiting approval before deeper phases)
**Author:** Claude Code / Danny Jenkins
**Created:** 2026-03-15
**Last Updated:** 2026-03-15

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Current System Analysis](#current-system-analysis)
3. [Telemetry Map](#telemetry-map)
4. [Architecture Gap Analysis](#architecture-gap-analysis)
5. [Ops Wall 2.0 Panel Specifications](#ops-wall-20-panel-specifications)
6. [Implementation Phases](#implementation-phases)
7. [Risk Analysis](#risk-analysis)

---

## 1. Project Overview

### Purpose

Evolve the existing Ops Wall (`/admin-console/ops/`) from a dense, flat monitoring page into a layered diagnostic command center with clear situation awareness at the top level and drill-down panels for investigation.

### What This Is NOT

- NOT a second/parallel command center
- NOT a replacement for existing telemetry (SAME, COAS, IOCD, Maturity)
- NOT a speculative system — all panels map to existing or clearly-needed telemetry

### Architecture Principles

| Principle | Description |
|-----------|-------------|
| **One Command Center** | The Ops Wall is the single monitoring surface. No parallel dashboards. |
| **Three Investigation Levels** | Level 1: Main wall (awareness) → Level 2: Diagnostic panel (investigation) → Level 3: Trace logs (forensics) |
| **Reuse Over Build** | Every panel must map to existing telemetry models. New models only for genuinely missing data. |
| **Extend SAME** | New real-time monitoring capabilities are added as SAME detectors, not new systems. |
| **Declarative Metadata** | Engine dependencies, health thresholds, and contracts live in the engine registry, not scattered across scoring code. |

### Relationship to Existing Ops Wall

The current Ops Wall (`templates/admin_console/operations_wall.html`, 4,394 lines) has 16+ sections with deep telemetry. The problem isn't missing data — it's information hierarchy. The redesign restructures the same data into:

- **Executive row** — 3 cards answering "is the system healthy?"
- **Core systems row** — 3 cards for the architectural backbone
- **Support systems row** — 3 cards for action/delivery/API layers
- **Incident feed** — active problems, linked to diagnostic panels
- **Trend strip** — directional awareness (improving/degrading)
- **Event log** — recent monitoring events

Each card clicks through to a diagnostic panel that contains what currently lives in the flat wall.

---

## 2. Current System Analysis

### Existing Monitoring Infrastructure

| System | Location | What It Does | Cadence |
|--------|----------|-------------|---------|
| **Ops Wall** | `operations_wall.html` + `ops_views.py` | 16-section command center with engine cards, integrity gauge, SAME narrative, anomaly watchlist, live feed, maturity scores, AAFR metrics, pipeline health, learning health | 2s polling |
| **SAME** | `same_engine.py` | 7 anomaly detectors: MISSED_RUN, ERROR_SPIKE, CONFIDENCE_VOLATILITY, SUPPRESSION_STORM, LOOPING_REMINDER, ENGINE_STARVATION, DELIVERY_RETRY_SPIKE | 60s (Celery Beat) |
| **COAS** | `health_scoring.py` | 3 health scores: scheduler (30%), engine (40%), freshness (30%) → composite score | Updated per SAME cycle |
| **IOCD** | `observability_engine.py` | Daily `IntelligenceMetricsSnapshot`: guidance effectiveness, prediction confidence, delivery rates, engagement, persona effectiveness | 24h (ISE) |
| **Maturity Engine** | `maturity_engine.py` | 6-dimension maturity: infrastructure, intelligence, safety, domain_coverage, life_impact, overall | Daily + on-demand |
| **System Integrity** | `SystemIntegritySnapshot` | 0-100 composite: engines_ok, anomaly_penalty, error_penalty, suppression_impact, volatility_impact | Per SAME cycle |
| **Diagnostics Console** | Separate `/admin-console/diagnostics/` | Request-level tracing, truth-layer visibility | On-demand |

### What Already Works Well

- **EngineRun** telemetry covers all 56 registered engines via `@log_engine_run` decorator
- **Heartbeat** system tracks cadence for all scheduled engines with OK/LATE/MISSED/ERROR/NEVER_RUN states
- **DecisionRecord** captures why engines made decisions (arbitration, suppression, routing)
- **SAME** provides real-time anomaly detection with severity escalation
- **Maturity Engine** provides multi-dimensional system health scoring
- **Engine Registry** (`apps/core/engine_registry.py`) is a clean declarative registry with 56 engines

### What Needs Improvement

1. **Information hierarchy** — All 16 sections rendered at the same level; no visual prioritization
2. **No drill-down** — Clicking a card doesn't open a focused diagnostic view
3. **Missing panels** — Validator gate, CoS performance, signal health, data integrity not surfaced
4. **Dependency blind spot** — Engine `dependencies` field exists but is empty for all 56 engines
5. **Duplicate registry** — `apps/core/ai_observability/engine_registry.py` (13 engines, dict-based) duplicates `apps/core/engine_registry.py` (56 engines, dataclass-based) with different metadata
6. **No incident linking** — Anomalies don't link to the specific diagnostic panel for investigation

---

## 3. Telemetry Map

### Mapping: Proposed Panels → Existing Telemetry

| Panel | Primary Data Sources | Models/Functions | Gap? |
|-------|---------------------|-----------------|------|
| **System Integrity** | `SystemIntegritySnapshot` | score, posture, 5 components | No — already exists as hero gauge |
| **CoS Performance** | `ChatLatencySnapshot`, CoS context timing | `_get_chat_latency_telemetry()` | **Partial** — latency tracked, context build time and token count not surfaced as a card |
| **Validator Gate** | `SelfError` logs in response validator | Logger-based currently | **Gap** — needs DB aggregation of block/pass/crash rates |
| **Engine Health** | `EngineHeartbeat`, `EngineRun`, `OpsAnomaly` | `_build_engine_cards()`, COAS engine score | No — engine cards already rich |
| **Signal Health** | `Insight`, `JournalSignal`, `Prediction`, `GuidanceItem` | No aggregation view | **Gap** — per-domain signal freshness/diversity not computed |
| **Data Integrity** | Domain Registry, SAE state, canonical services | `registry.get_coverage_summary()` | **Gap** — cross-consumer mismatch detection doesn't exist |
| **Action Systems** | `AIActionMetric` (AAFR) | `_get_aafr_metrics()` | No — AAFR tile already exists |
| **Observability** | `IntelligenceMetricsSnapshot`, `SystemMaturitySnapshot` | Maturity hero + IOCD | No — already exists as maturity section |
| **Mobile/API Health** | None currently | No model/view | **Gap** — API response times not tracked |
| **Incident Feed** | `OpsAnomaly` | `_get_active_anomalies()` | **Partial** — anomaly watchlist exists but needs incident linking |
| **Trend Strip** | `SystemIntegritySnapshot` history, `COASHealthSnapshot` | `IntegrityIndexView` sparklines | **Partial** — integrity trend exists, other trends need adding |

### Telemetry That Can Be Reused Immediately (No New Code)

- System Integrity gauge + components + sparkline
- Engine cards grid (heartbeat + run metrics + sparklines)
- SAME narrative bar (posture + bullets + recommendations)
- Anomaly watchlist (severity-sorted, filterable)
- AAFR metrics (5m/1h/24h success rates)
- COAS health scores (scheduler/engine/freshness)
- Scheduler heartbeat (ISE + SAME pulse)
- Live feed (EngineRun + DecisionRecord timeline)
- Maturity scores (6 dimensions + trends)
- Domain coverage grid

### New Telemetry Required

| Telemetry | Purpose | Implementation |
|-----------|---------|----------------|
| **Signal freshness per domain** | Track when each domain last produced signals | Query `Insight.objects.filter(domain=d).order_by('-created_at')[:1]` per domain |
| **Signal diversity per domain** | Count distinct signal types per domain (7d window) | Aggregate from `Insight.insight_type` grouped by domain |
| **Validator gate metrics** | Block rate, crash rate, most common violation | Aggregate `SelfError` logger output → new lightweight model or in-memory counter |
| **CoS context token estimate** | Token bloat monitoring | Add token count to `ChatLatencySnapshot` or log |
| **Cache hit/miss rate** | CoS context cache effectiveness | Counter in `readiness_cache.py`, persist to `COASHealthSnapshot.details` |

---

## 4. Architecture Gap Analysis

### Gap 1: Engine Dependency Declarations (EMPTY)

**Current state:** `EngineDefinition.dependencies` exists as a field but is `()` for all 56 engines.

**Impact:** Cannot trace root causes through dependency chains. When Signal Health degrades, there's no declarative way to know which engines are affected.

**Required:** Populate `dependencies` tuples based on actual data flow:
- PIE depends on SAE (reads UserState)
- PRIE depends on SAE (reads UserState)
- PGE depends on PIE + PRIE (reads Insights + Predictions)
- DBE depends on SAE + PIE + PRIE + PGE (reads all)
- DNE depends on PGE + TRIGGERS (delivers their outputs)
- DRIFT depends on SAE + ECC (reads state + commitments)
- PRESSURE depends on ECC + DRIFT (reads deadlines + drift)
- PROTECTIVE depends on PRESSURE (reads pressure scores)
- And so on for all 56 engines

### Gap 2: Duplicate Engine Registry

**Current state:** Two registries exist:
- `apps/core/engine_registry.py` — 56 engines, `EngineDefinition` dataclass, canonical
- `apps/core/ai_observability/engine_registry.py` — 13 engines, plain dicts, used by TriggerEngineView

**Impact:** Metadata drift between registries. The observability registry has `batch_runner`, `per_user_func`, `can_manual_run`, `execution_mode` that the canonical registry lacks.

**Required:** Consolidate. Add `batch_runner`, `per_user_func`, `can_manual_run`, `execution_mode` to `EngineDefinition`. Make the observability registry read from the canonical one.

### Gap 3: Signal Health Monitoring

**Current state:** No per-domain signal freshness/diversity view. COAS `freshness_score` is task-staleness-based, not signal-based.

**Impact:** Cannot detect "meals domain hasn't produced any signals in 7 days" or "journal NLP extraction stopped working."

**Required:** Query existing `Insight` and `JournalSignal` models grouped by domain, compute freshness + diversity, surface on Ops Wall.

### Gap 4: Validator Gate Visibility

**Current state:** The response validator (`health_response_validator.py`, structural validator) logs `SelfError` via Python logger but doesn't persist metrics for aggregation.

**Impact:** Validator block rate spikes are invisible on the Ops Wall. A misconfigured validator could block 50% of responses without triggering any monitoring.

**Required:** Either persist validator outcomes to a lightweight model or add a SAME detector that queries recent validator logs.

### Gap 5: CoS Performance Panel

**Current state:** `ChatLatencySnapshot` tracks TTFT, total duration, and context build time. `_get_chat_latency_telemetry()` surfaces some of this. But it's buried in the "Intelligence Pipeline Health" section, not a first-class card.

**Impact:** Context build performance degradation (the single biggest user-facing latency factor) is not immediately visible.

**Required:** Promote to a top-row card with P50/P95 context build time, TTFT, and estimated token count.

### Gap 6: No Incident → Panel Linking

**Current state:** Anomaly watchlist shows issues but clicking an anomaly doesn't navigate to the relevant diagnostic panel.

**Impact:** Investigation requires manual navigation. The "control tower" metaphor breaks when alerts don't lead anywhere.

**Required:** Each anomaly type maps to a diagnostic panel (e.g., `engine_silence` → Engine Health panel, `suppression_spike` → Validator/ICQG panel).

### Gap 7: Mobile/API Health

**Current state:** No API response time tracking. No mobile-specific health metrics.

**Impact:** iOS app degradation is invisible until users report it.

**Required:** Middleware-level API response time tracking for `/api/*` endpoints. Lower priority than Gaps 1-6.

---

## 5. Ops Wall 2.0 Panel Specifications

### Page Layout

```
┌─────────────────────────────────────────────────────────┐
│ HEADER: System Status │ Last Refresh │ Incidents │ Scan │
├───────────────────┬──────────────────┬──────────────────┤
│ System Integrity  │ CoS Performance  │ Validator Gate   │  ← ROW 1: Executive Health
├───────────────────┼──────────────────┼──────────────────┤
│ Engine Health     │ Signal Health    │ Data Integrity   │  ← ROW 2: Core Systems
├───────────────────┼──────────────────┼──────────────────┤
│ Action Systems    │ Observability    │ Mobile/API       │  ← ROW 3: Support Systems
├─────────────────────────────────────────────────────────┤
│ INCIDENT FEED: Active issues, severity-ordered          │  ← ROW 4
├────────────┬────────────┬────────────┬──────────────────┤
│ Integrity  │ CoS Perf   │ Engine     │ Validator Rate   │  ← ROW 5: Trend Strip
│ trend      │ trend      │ trend      │ trend            │
├─────────────────────────────────────────────────────────┤
│ RECENT SYSTEM EVENTS: Chronological monitoring feed     │  ← ROW 6
└─────────────────────────────────────────────────────────┘
```

### Panel Specifications

#### ROW 1: Executive Health

**Card: System Integrity**
- Purpose: Overall system health at a glance
- Metrics: Score (0-100), posture (OPTIMAL/NOMINAL/DEGRADED/CRITICAL), trend arrow, active incident count
- Data sources: `SystemIntegritySnapshot`, `OpsAnomaly.objects.filter(is_active=True).count()`
- Drill-down (Level 2): 5-component breakdown (engines_ok, anomaly_penalty, error_penalty, suppression_impact, volatility_impact), 24h sparkline, component trend charts
- Drill-down (Level 3): Individual component traces → EngineRun/OpsAnomaly records
- **Existing telemetry:** Already computed. Repackage current integrity hero.

**Card: CoS Performance**
- Purpose: Is the AI assistant responsive and grounded?
- Metrics: P50 context build time (ms), P95 TTFT (ms), grounding guard trigger count (24h), cache hit rate (%)
- Data sources: `ChatLatencySnapshot`, CoS readiness logger, future: token count field
- Drill-down (Level 2): Latency histogram (1h, 24h), context builder breakdown (which of the 19 builders is slow?), cache hit/miss timeline
- Drill-down (Level 3): Individual `ChatLatencySnapshot` records with per-builder timing
- **Existing telemetry:** `ChatLatencySnapshot` exists. Cache hit rate and token count are gaps.

**Card: Validator Gate**
- Purpose: Is the safety layer working without over-blocking?
- Metrics: Block rate (24h %), crash rate (24h), most common violation type, pass count
- Data sources: Validator logger output (currently `logger.warning` in `personal_assistant.py`)
- Drill-down (Level 2): Block rate by violation type, blocked response samples (anonymized), time-series of block rate
- Drill-down (Level 3): Individual blocked response logs
- **Existing telemetry:** Gap. Needs either log aggregation or lightweight model.

#### ROW 2: Core Systems

**Card: Engine Health**
- Purpose: Are all 56 engines running on cadence?
- Metrics: Engines OK (%), engines missed (count), P1 anomalies (count), worst engine (name + status)
- Data sources: `EngineHeartbeat`, `EngineRun`, `OpsAnomaly`
- Drill-down (Level 2): Full engine card grid (current engine cards section), per-engine sparklines, manual trigger buttons, dependency chain view
- Drill-down (Level 3): Per-engine EngineRun trace history, EngineSpan sub-step breakdown
- **Existing telemetry:** Fully covered. Repackage current engine cards as drill-down.

**Card: Signal Health**
- Purpose: Are all life domains producing intelligence signals?
- Metrics: Domains active (X/Y), domains silent (>48h), signal diversity score, freshest/stalest domain
- Data sources: `Insight` (grouped by domain), `JournalSignal`, `Prediction`, `GuidanceItem`
- Drill-down (Level 2): Per-domain signal freshness table, signal type distribution chart, signal production timeline (7d)
- Drill-down (Level 3): Individual signal records per domain
- **Existing telemetry:** Gap. Needs new aggregation queries on existing models.

**Card: Data Integrity**
- Purpose: Is the truth layer consistent across consumers?
- Metrics: Domain Registry coverage (%), SAE freshness, known consumer mismatches (count)
- Data sources: `registry.get_coverage_summary()`, `UserState.last_updated`, future: consumer alignment checks
- Drill-down (Level 2): Domain consistency map (registry coverage per domain), SAE module freshness per module, known bypass list (CoS builders reading raw tables)
- Drill-down (Level 3): Per-consumer query comparison (future CI check output)
- **Existing telemetry:** Partial. Registry coverage exists. Consumer alignment is a future CI check.

#### ROW 3: Support Systems

**Card: Action Systems**
- Purpose: Are AI actions succeeding?
- Metrics: Success rate (5m, 1h, 24h), blocked count (24h), most common failure, AAFR trend
- Data sources: `AIActionMetric`, `DecisionRecord`
- Drill-down (Level 2): Per-intent success/failure breakdown, blocked action log, safety gate trigger log
- Drill-down (Level 3): Individual AIActionMetric records with trace_id linking
- **Existing telemetry:** Fully covered. Repackage current AAFR tile.

**Card: Observability**
- Purpose: Are the monitoring systems themselves healthy?
- Metrics: SAME last run, IOCD last snapshot, Maturity last snapshot, monitoring coverage (%)
- Data sources: `SchedulerHeartbeat`, `IntelligenceMetricsSnapshot`, `SystemMaturitySnapshot`
- Drill-down (Level 2): SAME narrative (current narrative bar), maturity 6-dimension breakdown, IOCD daily trends
- Drill-down (Level 3): SAME execution logs, maturity snapshot history
- **Existing telemetry:** Fully covered. Repackage current maturity hero + SAME bar.

**Card: Mobile/API Health**
- Purpose: Is the iOS app and API performing well?
- Metrics: API P95 response time, error rate, active sessions, version distribution
- Data sources: Future: API middleware metrics
- Drill-down: API endpoint response time breakdown, error log
- **Existing telemetry:** Gap. Lower priority — implement in later phase.

#### ROW 4: Incident Feed

- Purpose: Active problems requiring attention, severity-ordered
- Format: `SEVERITY │ Description │ Affected System │ Duration │ [Investigate →]`
- Data sources: `OpsAnomaly.objects.filter(is_active=True)`, plus new SAME detectors
- Behavior: Each incident links to the relevant Level 2 diagnostic panel
- **Existing telemetry:** Anomaly watchlist exists. Needs incident-to-panel linking.

#### ROW 5: Trend Strip

- Purpose: Are things getting better or worse?
- Charts: 4 mini sparklines (24h window): System Integrity, CoS P95 TTFT, Engine OK%, Validator Block Rate
- Data sources: `SystemIntegritySnapshot` history, `ChatLatencySnapshot`, `EngineHeartbeat` aggregates, future: validator metrics
- **Existing telemetry:** Integrity sparkline exists. Others need new aggregation.

#### ROW 6: Recent System Events

- Purpose: Chronological monitoring activity log
- Format: `TIME │ Event │ Engine │ Severity`
- Data sources: Current live feed (`get_recent_feed()`)
- **Existing telemetry:** Fully covered. Repackage current live feed section.

---

## 6. Implementation Phases

### Phase 1: Architecture Metadata (SAFE — no UI changes)

**Goal:** Fill in the structural gaps that all future phases depend on.

**Tasks:**
1. Populate `dependencies` tuples for all 56 engines in `engine_registry.py`
2. Add `can_manual_run`, `batch_runner`, `per_user_func`, `execution_mode` fields to `EngineDefinition`
3. Refactor `apps/core/ai_observability/engine_registry.py` to read from canonical registry
4. Add query helpers: `get_dependents(code)`, `get_dependency_chain(code)`, `get_dependency_graph()`
5. Add `validate_dependencies()` to registry validation (cycle detection, missing refs)
6. Add tests for dependency graph integrity

**Risk:** Zero runtime risk. Metadata-only changes. No UI, no new models, no new scheduled tasks.

**Estimated files changed:** 3 (engine_registry.py, observability/engine_registry.py, tests)

---

### Phase 2: Signal Health Diagnostics

**Goal:** Add per-domain signal freshness/diversity monitoring.

**Tasks:**
1. Create `compute_signal_health()` in `ops_telemetry.py` — queries `Insight`, `JournalSignal`, `Prediction` grouped by domain
2. Add `SIGNAL_DROUGHT` detector to SAME engine (domain silent >48h)
3. Add signal health data to OpsStreamView JSON response
4. Surface signal health in Ops Wall (initially as a new card in existing layout)

**Risk:** Low. Read-only queries on existing models. SAME detector follows established pattern.

**Estimated files changed:** 3-4

---

### Phase 3: Validator Gate Monitoring

**Goal:** Make validator block/pass/crash rates visible.

**Tasks:**
1. Add lightweight `ValidatorMetric` model (or extend `AIActionMetric`) to persist outcomes
2. Instrument response validator to record outcomes
3. Add `VALIDATOR_SPIKE` detector to SAME engine
4. Add validator metrics to OpsStreamView JSON
5. Surface validator card in Ops Wall

**Risk:** Low-medium. New model requires migration. Validator instrumentation must not affect response latency.

**Estimated files changed:** 4-5

---

### Phase 4: CoS Performance Diagnostics

**Goal:** Promote CoS performance to a first-class monitoring card.

**Tasks:**
1. Add token count estimate to `ChatLatencySnapshot` or CoS context builder
2. Add cache hit/miss counter to `readiness_cache.py`
3. Restructure Ops Wall to show CoS Performance as a top-row card
4. Build Level 2 drill-down: per-builder timing breakdown

**Risk:** Low. Extends existing `ChatLatencySnapshot`. Cache counter is in-memory.

**Estimated files changed:** 3-4

---

### Phase 5: UI Restructuring (The Big Change)

**Goal:** Restructure `operations_wall.html` from flat 16-section layout to the 6-row hierarchy.

**Tasks:**
1. Create card component template (`ops_card.html`) with standard structure
2. Reorganize existing sections into Row 1-3 cards
3. Move detailed views (engine grid, maturity breakdown, SAME narrative) into Level 2 drill-down panels
4. Add incident feed with panel linking
5. Add trend strip with mini sparklines
6. Preserve all existing functionality — nothing removed, only reorganized

**Risk:** Medium. Large template change. Must preserve existing JS polling, chart rendering, and interactive features.

**Estimated files changed:** 2-3 (template + view context adjustments)

---

### Phase 6: Incident Feed + Dependency Chain UI

**Goal:** Connect anomalies to investigation panels and visualize dependency chains.

**Tasks:**
1. Add anomaly-to-panel mapping (anomaly type → diagnostic panel URL)
2. Build incident feed component with severity ordering and panel links
3. Build dependency chain visualization (uses Phase 1 metadata)
4. Add "Generate Debug Prompt" button on incident detail (uses existing WLJ debugging template)

**Risk:** Low-medium. UI additions on top of Phase 5 restructuring.

**Estimated files changed:** 2-3

---

### Phase 7: CI Canonical Query Audit (OPTIONAL)

**Goal:** Detect rogue ORM queries at build time, not runtime.

**Tasks:**
1. Create management command `audit_canonical_queries` that statically analyzes imports
2. Maintain allowlist of canonical service patterns per domain
3. Add to CI pipeline

**Risk:** Low. CI-only change. No runtime impact.

**Estimated files changed:** 1-2

---

### Phase 8: Mobile/API Health (OPTIONAL)

**Goal:** Track API performance for iOS app monitoring.

**Tasks:**
1. Add API response time middleware for `/api/*` endpoints
2. Create `APIHealthSnapshot` model
3. Add mobile/API card to Ops Wall

**Risk:** Low-medium. Middleware must not affect API latency. New model requires migration.

**Estimated files changed:** 3-4

---

## 7. Risk Analysis

### Risk 1: Duplicate Monitoring (MITIGATED)

**Risk:** Building new monitoring alongside existing creates confusion about which is authoritative.

**Mitigation:** This project explicitly extends the existing Ops Wall. No new monitoring surfaces. New detectors go into SAME. New metrics use existing snapshot models where possible.

### Risk 2: Telemetry Drift

**Risk:** Ops Wall 2.0 cards show different numbers than underlying monitoring systems.

**Mitigation:** All cards read from the same models that SAME, COAS, and IOCD already use. No parallel data paths. Phase 1 consolidates the duplicate engine registry to prevent metadata drift.

### Risk 3: Snapshot Data Volume

**Risk:** More frequent snapshots (validator metrics, signal health) increase database size.

**Mitigation:** Use rolling retention — keep hourly snapshots for 7 days, daily for 90 days, monthly beyond that. Same pattern as existing `EngineRun` data.

### Risk 4: UI Complexity (Phase 5)

**Risk:** Restructuring a 4,394-line template could break existing functionality.

**Mitigation:** Phase 5 is deliberately last among the core phases. All telemetry additions (Phases 2-4) work within the current layout first. Phase 5 is a pure reorganization of working components.

### Risk 5: Performance Impact

**Risk:** New aggregation queries (signal health, validator metrics) could slow the 2s polling endpoint.

**Mitigation:** All new metrics computed on longer cadences (SAME 60s or COAS 5m) and cached. Polling endpoint reads cached values, never runs live queries.

### Risk 6: Engine Registry Consolidation (Phase 1)

**Risk:** Changing the observability engine registry breaks TriggerEngineView, SAME auto-remediation, or manual engine triggers.

**Mitigation:** The observability registry is refactored to delegate to the canonical registry. Existing function signatures (`get_engine_meta()`, `resolve_batch_runner()`, `get_manual_engines()`) are preserved. Tests verify all 13 currently-registered engines remain accessible.

---

*This document will be reviewed by Danny and ChatGPT before implementation proceeds beyond Phase 1.*
