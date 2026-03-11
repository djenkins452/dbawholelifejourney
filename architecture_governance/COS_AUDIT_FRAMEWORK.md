# WLJ CoS Architecture Audit Framework

**Version:** 1.1
**Created:** 2026-03-11
**Last updated:** 2026-03-11 (Stabilization Pass — added infrastructure sections)

---

## Purpose

This framework defines how holistic system architecture audits are performed on the Whole Life Journey (WLJ) Chief of Staff (CoS) platform. It enables any authorized reviewer to say:

> "Run the WLJ Full System Audit."

and produce a complete, scored architectural assessment.

---

## System Vision

WLJ is a personal life operating system. The CoS should feel human to the user while operating as a powerful orchestration system behind the scenes.

### Target Architecture

```
User Interface
  ↓
CoS Conversation Layer
  ↓
Intent & Action Router
  ↓
Action Execution Gateway (execute_action)
  ↓
Domain Engines
  ↓
Database
  ↓
Observability & Monitoring
```

### Key Architectural Principles

1. **Single Mutation Gateway:** ALL AI-driven mutations MUST flow through `execute_action()` in `apps/core/ai_orchestrator/execution_engine.py`.
2. **Engine Signal Model:** Engines should primarily produce signals (insights, predictions, guidance, state updates) — NOT orchestrate actions or mutate state directly.
3. **CoS Synthesis:** The CoS layer synthesizes engine signals and determines behavior. Engines inform; the CoS decides.
4. **Phase Boundaries:** The three-phase pipeline (Interpretation → Execution → Post-Execution) must never be violated.
5. **SAE Truth Layer:** All intelligence consumers should read from `UserState` (SAE), not raw database tables.

---

## Audit Domains (7)

Each audit evaluates the system across these seven domains:

### Domain 1: CoS Conversation & Action Architecture
**Scope:** Chat pipeline, intent interpretation, domain routing, confirmation triggering, action execution.

**Key questions:**
- Is `execute_action()` the single mutation gateway?
- Are there hidden mutation paths?
- Is routing logic centralized?
- Is domain logic embedded in the conversation layer?

**Key files:**
- `apps/ai/personal_assistant.py` — Main chat orchestrator
- `apps/ai/views.py` — Chat API endpoints
- `apps/ai/intent_service.py` — Intent dispatch
- `apps/ai/action_handlers.py` — Action handler implementations
- `apps/core/ai_orchestrator/orchestrator.py` — UAIO orchestrator
- `apps/core/ai_orchestrator/execution_engine.py` — `execute_action()` gateway
- `apps/core/ai_orchestrator/intent_engine.py` — Intent routing
- `apps/core/ai_orchestrator/action_router.py` — Action routing
- `apps/core/ai_orchestrator/safety_engine.py` — Safety validation

### Domain 2: Engine Architecture
**Scope:** All engines — behavioral, momentum, streak, intervention, scheduling, profiling, state, observability.

**Key questions:**
- Do engines operate independently?
- Do engines call each other directly (coupling)?
- Do engines mutate state or only produce signals?
- Does any engine contain orchestration logic?

**Key directories:**
- `apps/core/ai_*/` — All core engine directories
- `apps/core/blueprint/` — Blueprint & governance engines
- `apps/core/domain_registry/` — Domain capability registry
- `apps/health/services/` — Domain-specific engines

### Domain 3: Hard Coding & Configuration Discipline
**Scope:** Constants, configuration, database rules, embedded logic.

**Key questions:**
- Are behavioral thresholds configurable or hard-coded?
- Are prompts managed centrally or scattered?
- Are time intervals and scoring weights appropriate for hard-coding?
- Which hard-coded values are safety invariants (acceptable) vs. tunable parameters (should be configurable)?

**Key areas to examine:**
- Scoring thresholds in engine files
- Prompt strings in `personal_assistant.py` and `intent_service.py`
- Time intervals in scheduler configuration
- Feature flags and configuration models

### Domain 4: Observability & System Health
**Scope:** Monitoring coverage, error tracking, system health, telemetry.

**Key questions:**
- Does the system detect AI execution failures?
- Are confirmation failures and entity resolution errors tracked?
- Are handler exceptions logged and monitored?
- Is there Celery/Redis/scheduler health monitoring?
- Is the AAFR (AI Action Failure Rate) comprehensive?

**Key files:**
- `apps/core/ai_observability/` — Observability engine (IOCD, SAME, Maturity)
- `apps/core/engine_runtime.py` — Engine telemetry wrapper
- `apps/core/ai_orchestrator/execution_engine.py` — AAFR recording
- `apps/admin_console/` — Operations Wall / Command Center

### Domain 5: Proactive Coaching System
**Scope:** Proactive guidance orchestration, signal sources, prioritization, throttling, fatigue protection.

**Key questions:**
- Do proactive messages flow through a centralized orchestration layer?
- Is there effective fatigue protection?
- Are messages coordinated to prevent conflicts?
- Is prioritization evidence-based?

**Key files:**
- `apps/ai/proactive_checkins.py` — Check-in generation
- `apps/ai/assistant_intelligence.py` — Assistant triggers
- `apps/core/ai_guidance/` — PGE guidance engine
- `apps/core/ai_delivery/` — DNE delivery engine
- `apps/core/ai_quality/` — ICQG quality gate

### Domain 6: AI Decision Quality
**Scope:** Intent classification, domain resolution, confirmation logic, safety protections.

**Key questions:**
- Is intent classification reliable?
- Is domain resolution unambiguous?
- Are confirmation prompts triggered appropriately?
- Are safety protections comprehensive?

**Key files:**
- `apps/core/ai_semantics/` — SUE semantic engine
- `apps/core/ai_memory/` — SLCME context memory
- `apps/core/time/` — HTIE temporal intelligence
- `apps/core/ai_orchestrator/safety_engine.py` — Safety validation
- `apps/core/ai_arbitration/` — UAL arbitration engine

### Domain 7: User Experience Consistency
**Scope:** Voice consistency, action narration, coaching tone, conversation continuity, topic persistence.

**Key questions:**
- Is the AI personality (Beth) defined centrally?
- Is the voice consistent across domains?
- Is action narration clear and trustworthy?
- Can the CoS maintain conversation context?

**Key files:**
- `apps/ai/personal_assistant.py` — System prompt assembly, personality
- `apps/core/ai_orchestrator/cos_context.py` — Context injection
- `apps/core/ai_persona/` — Persona engine
- `apps/core/blueprint/cos_governance.py` — Governance instructions

---

## Cross-Cutting Analysis

### Complexity Drift Analysis
Evaluate whether system complexity is increasing beyond maintainable levels:
- Number of engines and their dependencies
- Execution path complexity (how many layers does a user message traverse?)
- Orchestration layer count
- Duplicated logic across engines
- Dead code or unused engine paths

### Phase Boundary Compliance
Verify that the three-phase pipeline is not violated:
- Phase 1 engines (SUE, SLCME, HTIE) do NOT execute actions
- Phase 2 (UAIO) is the ONLY execution authority
- Phase 3 engines observe and signal — they do NOT orchestrate

---

## Data Sources for Audit

| Source | Location | Purpose |
|--------|----------|---------|
| Engine reference | `docs/ENGINE_COS_REFERENCE.md` | Current engine inventory, schedules, known bugs |
| Intelligence architecture | `docs/INTELLIGENCE_ARCHITECTURE.md` | Authoritative engine definitions |
| Domain architecture | `docs/DOMAIN_INTELLIGENCE_ARCHITECTURE.md` | Per-module integration map |
| Engine integration guide | `docs/ENGINE_INTEGRATION_GUIDE.md` | Integration patterns |
| Codebase | `apps/` | Source of truth |
| Previous audits | `architecture_governance/system_audits/` | Historical context |

---

## Additional Audit Checks (Added 2026-03-11)

The inaugural audit identified areas not fully captured by the seven domains:

### File Complexity Metrics
Measure and track line counts for key files:
- `apps/ai/personal_assistant.py` — threshold: 5,000 lines (ALERT if exceeded)
- `apps/core/ai_orchestrator/cos_context.py` — threshold: 4,000 lines
- `apps/ai/action_handlers.py` — threshold: 4,000 lines

### Engine Count & Consolidation
- Total named engines (target: ≤60)
- Total ISE scheduled tasks (target: ≤50)
- Total context builders (target: ≤20)
- System prompt layers (target: ≤10)
- Identify candidate engines for consolidation

### Conversation-Layer Mutation Tracking
- Inventory mutations in `personal_assistant.py` that bypass `execute_action()`
- Assess whether these need telemetry coverage

### Blueprint Engine Observability
- Verify blueprint engine mutations have structured logging
- Assess whether `system_execute_action()` gateway is needed

### System Complexity Score (Added 2026-03-11)
Automated complexity measurement via `apps/core/observability/complexity_metrics.py`.

**Dimensions (5):**
1. **File Size Complexity** (25%) — Key file line counts vs thresholds
2. **Engine Proliferation** (20%) — Total engines, scheduled tasks, directory sprawl
3. **Inter-Engine Coupling** (20%) — Cross-engine import dependencies
4. **Method Complexity** (20%) — Function count in critical files
5. **Configuration Scatter** (15%) — Threshold constants spread across files

**Score:** 0-10 scale (lower is better)
- 0-2: A (Excellent) — Complexity well-managed
- 2-4: B (Good) — Manageable, some areas to simplify
- 4-6: C (Acceptable) — Growing complexity, attention needed
- 6-8: D (Concerning) — Significant refactoring needed
- 8-10: F (Critical) — Complexity impeding development

**To compute:** `from apps.core.observability.complexity_metrics import compute_complexity_score`

### Central Engine Registry (Added 2026-03-11)
All engines are now declared in `apps/core/engine_registry.py` with:
- Engine code, name, phase, module path
- Schedule interval (if ISE-scheduled)
- Signal types produced
- State mutation flag
- Category (core, blueprint, observability, domain)

**To validate:** `from apps.core.engine_registry import validate_registry`

### Domain Events Infrastructure (Added 2026-03-11)
Domain event bus at `apps/core/events/domain_events.py` enables real-time
intelligence triggers without polling. Events are emitted when domain
mutations occur and subscribed to by intelligence engines.

### AI Threshold Configuration (Added 2026-03-11)
DB-backed threshold configuration via `apps/core/ai_config.py`:
- `AIThresholdConfig` model (singleton pattern)
- Covers: confidence, capacity, delivery, fatigue, protective, cache thresholds
- Accessible via `get_ai_config()` or `get_threshold(name, default)`

### Message Orchestration (Added 2026-03-11)
Centralized message coordination at `apps/core/cos/message_orchestrator.py`:
- Per-channel delivery limits
- Per-type cooldown enforcement
- Priority-based message deduplication
- Delivery budget tracking

---

## Framework Evolution

After each audit, review this framework for gaps:
- New engine categories not covered
- New orchestration layers
- New AI subsystems
- Changed architectural patterns
- Updated key file paths

Update this document to keep the framework current with the system.

---

*Maintained by the WLJ Architecture Governance process.*
