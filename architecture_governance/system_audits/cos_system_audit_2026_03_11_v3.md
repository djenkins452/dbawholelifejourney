# WLJ CoS System Audit — 2026-03-11 (Post-Event-Bus-Completion)

**Auditor:** Architecture Governance Process (Claude Code)
**Framework version:** 1.1
**Audit type:** Full system audit (post-event-bus-completion pass)
**Previous audit:** 2026-03-11 v2 (post-stabilization) — 82.0/100 (B)

---

## Executive Summary

This audit follows two major infrastructure passes since the last scored audit:

1. **System Integration Pass** — Wired AIThresholdConfig to 4 engine files (16 constants), connected domain events with 12 emission points and 12 subscribers, integrated MessageOrchestrator into delivery pipeline, linked engine_runtime to central registry, expanded complexity metrics to 7 dimensions.

2. **Event Bus Completion Pass** — Wired 23 web views with `safe_emit_event()`, added HealthKit sync batch event emission, implemented 4 event bus safeguards (idempotency, loop protection, latency tracking, per-type counters), exposed event telemetry on Operations Wall, added 10 new AIThresholdConfig fields, and rewired 5 consumer files from hardcoded constants to `get_threshold()`.

**The system has moved from "infrastructure without wiring" to "infrastructure with operational consumers."** The #1 risk from the prior audit — newly-built infrastructure with zero runtime impact — has been substantially addressed. AIThresholdConfig now has 25 DB-backed fields with 9 consumer files. Domain events have 37 event types, 14 subscribers, and fire from all mutation paths (web, AI chat, HealthKit). The MessageOrchestrator gates all proactive delivery.

**Overall System Score: 85.6/100 (Grade: B+) — up from 82.0 (B)**

---

## Overall Score Table

| Domain | Weight | Score | Grade | Prev | Trend |
|--------|--------|-------|-------|------|-------|
| CoS Conversation & Action Architecture | 20% | 89 | A- | 87 | ↑ +2 |
| Engine Architecture | 15% | 79 | C+ | 73 | ↑ +6 |
| Hard Coding & Configuration Discipline | 10% | 81 | B | 72 | ↑ +9 |
| Observability & System Health | 15% | 92 | A | 89 | ↑ +3 |
| Proactive Coaching System | 10% | 90 | A | 83 | ↑ +7 |
| AI Decision Quality | 20% | 83 | B | 82 | ↑ +1 |
| User Experience Consistency | 10% | 84 | B+ | 84 | — 0 |
| **Overall (Weighted)** | **100%** | **85.6** | **B+** | **82.0** | **↑ +3.6** |

**Complexity Drift (Supplementary): 75/100 (Grade: C) — ↑3 from 72**

### Score Calculation

```
(89 × 0.20) + (79 × 0.15) + (81 × 0.10) + (92 × 0.15) + (90 × 0.10) + (83 × 0.20) + (84 × 0.10)
= 17.80 + 11.85 + 8.10 + 13.80 + 9.00 + 16.60 + 8.40
= 85.55 → 85.6
```

---

## Section 1: CoS Conversation & Action Architecture

**Score: 89/100 (Grade: A-) — ↑2 from 87**

### What Changed

- **Domain events now fire from ALL mutation paths.** 23 web views, AI chat action handlers, and HealthKit sync all emit events through `safe_emit_event()`. Previously only the AI chat path triggered intelligence reactions.
- **Event bus has 4 safeguards.** Idempotency dedupe (5s TTL), loop protection (max depth 2), exception isolation, and latency tracking. Events never block user requests.
- **Pipeline parity confirmed.** Both streaming and non-streaming paths use identical pre-processing: ECC → confirmations → calibration → intent recognition → Learning Mode gate.

### Evidence

- `action_handlers.py` (6,036 lines): `_emit_domain_event()` fires for all 12+ intent categories
- `health/views.py`: 12 `safe_emit_event()` calls across all health create views
- `journal/views.py`, `purpose/views.py`, `faith/views.py`, `life/views.py`, `finance/views.py`: 11 additional event emission points
- `mobile/views.py`: HealthKit `health_ingest()` emits one event per changed metric type + `HEALTH_SYNC_COMPLETED` catch-all
- `execute_action()` in `execution_engine.py:39` remains the sole AI mutation gateway — zero bypasses found

### Remaining Gaps

- `personal_assistant.py` still 7,437 lines (god object, but actively maintained)
- `cos_context.py` still 5,942 lines (largest god object, untouched)
- `action_handlers.py` still 6,036 lines (no domain decomposition)
- Only 2 of 10+ prompts extracted to external files

### Recommendations

1. Decompose `cos_context.py` — Split 19 builders into per-domain modules
2. Split `action_handlers.py` by domain (health_handlers, faith_handlers, etc.)
3. Continue prompt extraction to `/prompts/system/`

---

## Section 2: Engine Architecture

**Score: 79/100 (Grade: C+) — ↑6 from 73**

### What Changed

- **Registry drift risk eliminated.** `engine_runtime.py` now uses `get_engine()` from central registry as authoritative source, with `ENGINE_PHASE_MAP` as legacy fallback only. Confirmed at lines 100-107.
- **`ops_aggregates.py` sources `ALL_ENGINES` from registry.** Uses `get_scheduled_engines()` with union fallback. Single source of truth.
- **Domain event bus fully operational.** 37 event types, 14 subscribers, 4 safeguards. Previously zero subscribers and zero emission points.
- **`safe_emit_event()` public helper** wraps all event emission in try/except — domain events never block user requests.

### Evidence

- `engine_registry.py`: 45 engines registered with declarative metadata (phase, signal type, ISE task, interval, mutations, dependencies)
- `domain_events.py` (403 lines): `_EventBus` with `_MAX_EVENT_DEPTH=2`, `_DEDUPE_TTL_SECONDS=5.0`, `_LATENCY_WINDOW_SIZE=200`
- `subscribers.py` (208 lines): 5 SAE cache invalidation, 3 PIE insight triggers, 3 CoS context invalidation, 1 catch-all telemetry, 1 faith cache subscriber = 14 total

### Remaining Gaps

- 10+ blueprint engines still mutate state directly without AAFR telemetry or Learning Mode gate
- Engine overlap persists (2 intervention engines, 2 narrative generators)
- 198 cross-engine import paths (21.5% coupling ratio)
- No engine consolidation or retirement since registry creation

### Recommendations

1. Create `system_execute_action()` for blueprint engine observability
2. Consolidate overlapping engines (intervention, narrative)
3. Reduce cross-engine coupling through signal-only interfaces

---

## Section 3: Hard Coding & Configuration Discipline

**Score: 81/100 (Grade: B) — ↑9 from 72**

### What Changed

- **AIThresholdConfig expanded from 15 → 25 fields.** Added 10 new fields across 2 new categories: Insight Budget Limits (5: max_insights_per_day, max_insights_per_6h_window, max_cross_domain_per_day, max_notifications_per_day, insight_freshness_hours) and Safety & Rate Limits (5: max_backdate_days, max_future_days, max_destructive_per_minute, max_general_per_minute, max_actions_per_message).
- **9 consumer files now use `get_threshold()`.** Integration Pass wired: EAE constants, intervention_fatigue, capacity_engine, protective_engine. Event Bus Pass wired: noise_budget, notification_engine, services, safety_engine, action_policy.
- **Consumer rewiring patterns are clean.** `_budget_caps()` helper in noise_budget.py, `_get_limits()` classmethod in ActionRateLimiter, inline `get_threshold()` in safety_engine.py. All preserve original defaults as fallbacks.

### Evidence

- `ai_config.py` (266 lines): 25 configurable fields + `get_threshold()` safe accessor
- `noise_budget.py`: `_budget_caps()` → `get_threshold("max_insights_per_day", 12)` etc.
- `action_policy.py`: `ActionRateLimiter._get_limits()` → `get_threshold("max_destructive_per_minute", 2)` etc.
- `safety_engine.py`: `MAX_BACKDATE_DAYS = get_threshold("max_backdate_days", 365)` at point of use
- Migration `0111_add_threshold_budget_and_ratelimit_fields.py` created and applied

### Remaining Gaps

- **18+ hardcoded constants** still in engine files: 8 in ai_arbitration (scenario_classifier, weight_tuner, capacity_volatility), 7 in ai_insights (confidence gates in rules files), 8 in signal_collector (urgency/risk scorings)
- Only 2 of 10+ prompts externalized to `/prompts/system/`
- 31 ISE scheduler intervals still hard-coded in scheduler_registry.py
- Check-in message templates in proactive_checkins.py still hard-coded

### Recommendations

1. Migrate ai_arbitration signal-scoring constants (8 values) to AIThresholdConfig
2. Migrate ai_insights confidence gates (7 values) to AIThresholdConfig
3. Extract remaining prompts to `/prompts/system/`
4. Consider making ISE intervals configurable via DB

---

## Section 4: Observability & System Health

**Score: 92/100 (Grade: A) — ↑3 from 89**

### What Changed

- **Domain event telemetry exposed on Operations Wall.** `_get_domain_event_telemetry()` returns: total_emitted, suppressed, registered_patterns, total_handlers, avg_handler_ms, p95_handler_ms, type_counts, daily_count. Wired into OpsStreamView JsonResponse.
- **Event bus has built-in latency tracking.** Sliding window of 200 samples computes avg/p95 handler latency. Available via `get_event_bus_stats()`.
- **Complexity score expanded to 7 dimensions.** Added `_score_registry_health()` and `_score_prompt_layers()` to existing 5 dimensions.

### Evidence

- OpsStreamView returns **14 telemetry sections** in a single JSON response: engine_cards, narrative, anomalies, feed, integrity, scheduler_heartbeats, scheduler_health, eae_telemetry, learning_health, health_intelligence, coas_health, aafr, complexity, domain_events
- **21 telemetry helper functions** in ops_telemetry.py — each narrowly scoped to one telemetry vector
- **17 observability models** (EngineRun, EngineSpan, DecisionRecord, OpsAnomaly, OpsNarrativeSnapshot, SystemIntegritySnapshot, SAMEExecutionLog, SchedulerHeartbeat, COASHealthSnapshot, SystemMaturitySnapshot, AIActionMetric, etc.)
- AAFR tracks every `execute_action()` with intent type, outcome, duration, error category

### Remaining Gaps

- Conversation-layer failures (DailyPriority, AssistantMessage creation) still not tracked structurally
- No Redis/Celery health metrics in SAME or IOCD
- AAFR failure logging at `logger.debug()` (invisible in production)
- No request-level trace IDs across event bus → engine runs

### Recommendations

1. Upgrade AAFR failure logging to `logger.warning()`
2. Add trace ID correlation between domain events and engine runs
3. Add Celery queue depth + Redis memory to SAME monitoring

---

## Section 5: Proactive Coaching System

**Score: 90/100 (Grade: A) — ↑7 from 83**

### What Changed

- **MessageOrchestrator IS wired to delivery pipeline.** `deliver_single()` in delivery_engine.py calls `orchestrator.should_deliver()` before sending and `orchestrator.record_delivery()` after success. Non-blocking design — gate failures fall through to delivery.
- **Domain events have 14 active subscribers.** Previously zero. SAE cache invalidation (5), PIE insight triggers (3), CoS context invalidation (3), faith cache (1), global telemetry (1).
- **Events fire from ALL paths.** Web views (23), AI chat handlers (12+), HealthKit sync (batch). Intelligence reactions are now uniform regardless of entry point.

### Evidence

- `delivery_engine.py` lines 83-98: `should_deliver()` gate with proper error handling
- `delivery_engine.py` lines 116-127: `record_delivery()` after successful delivery
- `subscribers.py`: 14 handlers with safe error patterns (ImportError vs Exception separation)
- `domain_events.py`: 37 event types covering health, journal, faith, purpose, tasks, CoS, finance, system

### Remaining Gaps

- Coaching style selection not user-facing (persona engine exists but no UI)
- No real-time intelligence triggers from HealthKit data (only SAE cache invalidation on sync events)
- Domain event subscribers focus on cache invalidation — deeper intelligence reactions (PRIE predictions on weight trends, adherence alerts on medication patterns) not yet wired

### Recommendations

1. Add PIE subscribers for finance and purpose events (currently only health events trigger PIE)
2. Wire PRIE prediction triggers to health event patterns (weight trends, BP patterns)
3. Add coaching style selection to user preferences UI

---

## Section 6: AI Decision Quality

**Score: 83/100 (Grade: B) — ↑1 from 82**

### What Changed

- **Safety engine timestamp bounds now DB-backed.** `MAX_BACKDATE_DAYS` and `MAX_FUTURE_DAYS` read from AIThresholdConfig with `get_threshold()`, falling back to defaults (365).
- **Rate limiter thresholds now DB-backed.** `ActionRateLimiter._get_limits()` reads `max_destructive_per_minute`, `max_general_per_minute`, `max_actions_per_message` from AIThresholdConfig.

### Evidence

- `safety_engine.py`: `MAX_BACKDATE_DAYS = get_threshold("max_backdate_days", 365)` at validation point
- `action_policy.py`: `max_destructive, max_general, _ = cls._get_limits()` in `check_rate_limit()`

### Remaining Gaps (Unchanged)

- `execute_intent()` remains massive if/elif dispatch (74 branches) — not refactored to registry pattern
- Single LLM provider dependency (OpenAI) — no fallback or abstraction layer
- No automated prompt regression testing
- Intent classification confidence not tracked structurally
- No lightweight pre-filtering before API calls

### Recommendations (Unchanged)

1. Refactor `execute_intent()` to dictionary/registry dispatch
2. Add intent classification confidence tracking
3. Add prompt regression test suite (10-20 canonical inputs)
4. Consider LLM abstraction layer for provider flexibility

---

## Section 7: User Experience Consistency

**Score: 84/100 (Grade: B+) — unchanged from 84**

### What Changed

No changes to UX layer in this pass. Focus was on backend infrastructure.

### Current State

- **Prompt centralization:** `build_personal_assistant_prompt()` in prompt_builder.py (667 lines)
- **Beth persona:** Consistent narration with `_SUCCESS_OPENERS`, warm/competent voice
- **CoS Operational Rules v6:** Enforced via external file (`cos_operational_rules.md`)
- **Persona engine:** Operational but no user-facing selection
- **Template coverage:** 490 templates, 242 (49%) with responsive media queries
- **CSP violations:** 57 inline event handlers across 22 templates — silently blocked by nonce-based CSP

### Recommendations

1. **Remediate CSP violations** — 57 inline handlers across 22 templates. Highest priority: dashboard, chat_widget, medicine_form
2. Increase responsive template coverage beyond 49%
3. Add voice consistency evaluation across domains
4. Clean up prompt version references (v4-v8.1)

---

## Complexity Drift Analysis

**Score: 75/100 (Grade: C) — ↑3 from 72**

### Key Metrics Comparison

| Metric | v2 Audit | Current | Trend |
|--------|----------|---------|-------|
| `personal_assistant.py` | 7,437 lines | 7,437 lines | — Unchanged |
| `cos_context.py` | 5,942 lines | 5,942 lines | — Unchanged |
| `action_handlers.py` | 5,970 lines | 6,036 lines | ↑ Slight increase |
| `intent_service.py` | 2,276 lines | 2,276 lines | — Unchanged |
| `ops_views.py` | 1,003 lines | 1,009 lines | — Unchanged |
| AIThresholdConfig fields | 15 | 25 | ↑ +10 (good: centralizes) |
| Event bus event types | 30+ | 37 | ↑ +7 |
| Event bus subscribers | 0 | 14 | ↑ +14 (was dead code) |
| Ops stream telemetry sections | 12 | 14 | ↑ +2 |
| Complexity dimensions | 5 | 7 | ↑ +2 |
| Consumer files using get_threshold() | 0 | 9 | ↑ +9 |

### Assessment

Complexity grew slightly (new fields, subscribers, telemetry) but in a **structured, observable way**. The growth represents wiring — connecting infrastructure to consumers — not new abstraction. The primary concern remains the 3 god objects: `cos_context.py` (5,942), `action_handlers.py` (6,036), `personal_assistant.py` (7,437).

---

## Key System Risks

### Risk 1: God Object Fragility (Severity: HIGH — unchanged)
`cos_context.py` (5,942 lines), `action_handlers.py` (6,036 lines), and `personal_assistant.py` (7,437 lines) remain the three largest files. These are the highest-risk change targets and primary merge conflict sources.

### Risk 2: Blueprint Engine Observability Gap (Severity: MEDIUM — unchanged)
10+ blueprint engines mutate state directly without AAFR telemetry or Learning Mode gating. System-initiated changes are less observable than user-initiated ones.

### Risk 3: Remaining Hardcoded Constants (Severity: MEDIUM — reduced)
18+ signal-scoring and confidence-gate constants remain scattered across ai_arbitration and ai_insights. Now reduced from 50+ but still present.

### Risk 4: Single LLM Provider Dependency (Severity: MEDIUM — unchanged)
All intent recognition and response generation depends on OpenAI. No fallback, graceful degradation, or abstraction layer.

### Risk 5: CSP Non-Compliance (Severity: MEDIUM — new)
57 inline event handlers across 22 templates violate nonce-based CSP. Silently blocked in production browsers. Security posture degradation.

---

## Top Strategic Improvements

### 1. Decompose `cos_context.py` (Priority: HIGH, Effort: MEDIUM)
Split 19 context builders into per-domain modules with builder registry. Keep `build_cos_context()` as orchestrator. Target: <500 lines in main file.

**Expected impact:** Reduces #1 god-object risk. Enables per-domain testing and ownership.

### 2. Decompose `action_handlers.py` (Priority: HIGH, Effort: MEDIUM)
Split handler methods by domain: health_handlers.py, faith_handlers.py, life_handlers.py, etc. Keep shared utilities in base class.

**Expected impact:** Reduces merge conflict surface. Enables domain-focused changes without touching monolith.

### 3. CSP Violation Remediation (Priority: HIGH, Effort: LOW)
Refactor 22 violating templates to use `addEventListener()` inside `<script nonce>` blocks. Start with dashboard, chat_widget, medicine_form.

**Expected impact:** Eliminates silent handler failures. Restores security posture.

### 4. Migrate Remaining Constants (Priority: MEDIUM, Effort: LOW)
Add ai_arbitration signal-scoring constants (8) and ai_insights confidence gates (7) to AIThresholdConfig. ~15 new fields, 2 consumer file rewires.

**Expected impact:** Raises configuration discipline from 81 → 88+ (B+).

### 5. Create `system_execute_action()` (Priority: MEDIUM, Effort: MEDIUM)
Parallel gateway for system-initiated mutations (blueprint engines) that provides AAFR telemetry without user-intent context.

**Expected impact:** Closes blueprint observability gap. All mutations become trackable.

---

## Path to 90+ (A Range)

The system is at **85.6/100 (B+)**. To reach 90+:

| Action | Domain Impact | Estimated Score Gain |
|--------|--------------|---------------------|
| Decompose `cos_context.py` | CoS +3, Complexity +5 | +1.5 overall |
| Decompose `action_handlers.py` | CoS +2, Decision +2 | +0.8 overall |
| CSP remediation | UX +6 | +0.6 overall |
| Migrate remaining 15 constants | Config +7 | +0.7 overall |
| Blueprint `system_execute_action()` | Engine +5 | +0.8 overall |
| **Combined** | | **+4.4 → ~90.0** |

The path to A range is achievable through **decomposition and compliance**, not new features.

---

## Overall Assessment

The WLJ CoS platform has progressed from **82.0 (B) → 85.6 (B+)** through systematic infrastructure wiring. Six of seven domains improved, one held steady (UX Consistency).

**What improved most:**
- **Configuration Discipline (+9)** — 25 DB-backed fields, 9 consumer files wired
- **Proactive Coaching (+7)** — MessageOrchestrator gating, domain events with 14 subscribers
- **Engine Architecture (+6)** — Registry drift eliminated, event bus fully operational

**What didn't change:**
- God objects (cos_context, action_handlers, personal_assistant) remain untouched
- CSP violations remain (57 inline handlers)
- Intent dispatch pattern still if/elif (74 branches)
- Single LLM provider dependency

**The system's narrative has shifted from "infrastructure without wiring" to "wired infrastructure with god-object debt."** The next phase of improvement is decomposition.

---

*Audit completed: 2026-03-11*
*Previous audit: 2026-03-11 v2 (post-stabilization) — 82.0 (B)*
*Next recommended audit: 2026-04-11 (monthly cadence)*
*Framework version: 1.1*
