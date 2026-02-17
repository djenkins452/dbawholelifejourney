# Whole Life Journey — Intelligence Architecture

**Purpose:** Permanent architectural authority defining the fourteen-engine cognitive stack that powers all AI-driven features in WLJ. Claude Code must read this document before implementing any feature that touches AI, data logging, insights, predictions, or user interactions.

**Status:** Active — All engines implemented and deployed.

---

## Intelligence Execution Model

The WLJ intelligence system operates in **three distinct phases**. Every engine belongs to exactly one phase. Phase boundaries must never be violated.

### Phase 1 — Interpretation (Pre-Execution)

**Purpose:** Understand user meaning safely and accurately. Prepare execution instructions.

| Engine | Location | Responsibility |
|--------|----------|----------------|
| **SUE** — Semantic Understanding Engine | `apps/core/ai_semantics/` | Parse intent, extract entities, detect ambiguity |
| **SLCME** — Self-Learning Context Memory Engine | `apps/core/ai_memory/` | Resolve context references via learned mappings |
| **HTIE** — Human Temporal Intelligence Engine | `apps/core/time/` | Resolve human time expressions to timestamps |

**These engines do NOT execute actions. They prepare execution instructions.**

### Phase 2 — Execution

**Purpose:** Execute actions safely and consistently. Single execution authority.

| Engine | Location | Responsibility |
|--------|----------|----------------|
| **UAIO** — Unified AI Orchestrator | `apps/core/ai_orchestrator/` | Validate, route, and execute domain actions |

**UAIO is the ONLY execution authority. No engine may execute actions independently.**

### Phase 3 — Post-Execution

**Purpose:** Update awareness, detect patterns, predict trajectory, surface guidance.

| Engine | Location | Responsibility |
|--------|----------|----------------|
| **SAE** — State Awareness Engine | `apps/core/ai_state/` | Update authoritative user state snapshot |
| **PIE** — Proactive Insight Engine | `apps/core/ai_insights/` | Evaluate patterns and detect factual insights |
| **PRIE** — Predictive Intelligence Engine | `apps/core/ai_predictions/` | Project future trajectory via linear regression |
| **PGE** — Proactive Guidance Engine | `apps/core/ai_guidance/` | Surface evidence-based proactive guidance |
| **GLOE** — Guidance Learning Optimization Engine | `apps/core/ai_guidance_learning/` | Learn from user guidance interactions to improve PGE ranking |
| **DBE** — Daily Briefing Engine | `apps/core/ai_briefing/` | Aggregate daily intelligence summaries from all engines |
| **ISE** — Intelligence Scheduler Engine | `apps/core/ai_scheduler/` | Centrally manage scheduled execution of all intelligence engines |
| **WIRE** — Weekly Intelligence Report Engine | `apps/core/ai_weekly_report/` | Generate weekly longitudinal intelligence summaries from all engines |
| **E3** — Evidence & Explainability Engine | `apps/core/ai_explain/` | Attach evidence and explanations to all intelligence outputs (PGE, DBE, WIRE) |
| **DNE** — Delivery & Notification Engine | `apps/core/ai_delivery/` | Deliver intelligence outputs through user-configured channels with throttling/dedupe |

**Cross-Cutting Quality Layer:**

| Layer | Location | Purpose |
|-------|----------|---------|
| **ICQG** — Intelligence Calibration & Quality Gate | `apps/core/ai_quality/` | Reduce repetition (72h suppression), detect conflicts, enforce minimum quality thresholds. Hooks into PGE, DBE, WIRE, DNE. |

**Execution order within Phase 3:** SAE → PIE → PRIE → PGE (+ICQG, +E3) → GLOE (on interaction) → DBE (+ICQG, +E3, scheduled daily) → WIRE (+ICQG, +E3, scheduled weekly) → DNE (+ICQG, scheduled every 10min)
**Scheduling:** ISE orchestrates when engines run (cron-triggered every 5 minutes)
**Enrichment:** E3 hooks into PGE, DBE, and WIRE post-store (non-blocking)
**Quality Gate:** ICQG filters candidates before storage (PGE), before summary (DBE/WIRE), and before delivery (DNE) — always fails open
**Delivery:** DNE scans for undelivered PGE/DBE/WIRE outputs and routes to in-app/email/SMS

**These engines do NOT execute actions. They observe and interpret system state.**

---

## Architecture Diagram

```
                          ┌──────────────────────┐
                          │     User Input        │
                          └──────────┬───────────┘
                                     │
              ╔══════════════════════════════════════════╗
              ║    PHASE 1 — INTERPRETATION              ║
              ╠══════════════════════════════════════════╣
              ║                                          ║
              ║   ┌──────────┐ ┌──────────┐ ┌────────┐  ║
              ║   │   SUE    │ │  SLCME   │ │  HTIE  │  ║
              ║   │ Semantic │ │  Memory  │ │  Time  │  ║
              ║   │ Under-   │ │ Resol-   │ │ Resol- │  ║
              ║   │ standing │ │ ution    │ │ ution  │  ║
              ║   └────┬─────┘ └────┬─────┘ └───┬────┘  ║
              ║        └────────────┼────────────┘       ║
              ╚═════════════════════╪════════════════════╝
                                    │
              ╔═════════════════════╪════════════════════╗
              ║    PHASE 2 — EXECUTION                   ║
              ╠═════════════════════╪════════════════════╣
              ║              ┌──────▼───────┐            ║
              ║              │     UAIO     │            ║
              ║              │ Orchestrator │            ║
              ║              │  (Action     │            ║
              ║              │   Handlers)  │            ║
              ║              └──────┬───────┘            ║
              ╚═════════════════════╪════════════════════╝
                                    │
              ╔═════════════════════╪════════════════════╗
              ║    PHASE 3 — POST-EXECUTION              ║
              ╠═════════════════════╪════════════════════╣
              ║              ┌──────▼───────┐            ║
              ║              │     SAE      │            ║
              ║              │  State       │            ║
              ║              └──────┬───────┘            ║
              ║              ┌──────▼───────┐            ║
              ║              │     PIE      │            ║
              ║              │  Insights    │            ║
              ║              └──────┬───────┘            ║
              ║              ┌──────▼───────┐            ║
              ║              │    PRIE      │            ║
              ║              │  Predictions │            ║
              ║              └──────┬───────┘            ║
              ║              ┌──────▼───────┐            ║
              ║              │     PGE      │            ║
              ║              │  Guidance    │            ║
              ║              └──────┬───────┘            ║
              ║              ┌──────▼───────┐            ║
              ║              │    GLOE      │            ║
              ║              │  Learning    │◄── User    ║
              ║              │  (on action) │   Actions  ║
              ║              └──────┬───────┘            ║
              ║              ┌──────▼───────┐            ║
              ║              │     DBE      │            ║
              ║              │  Briefing    │            ║
              ║              │  (daily)     │            ║
              ║              └──────┬───────┘            ║
              ║              ┌──────▼───────┐            ║
              ║              │    WIRE      │            ║
              ║              │  Weekly      │            ║
              ║              │  Report      │            ║
              ║              └──────────────┘            ║
              ║                                          ║
              ║    ┌─────────────────────────────────┐   ║
              ║    │           E3                    │   ║
              ║    │  Evidence & Explainability      │   ║
              ║    │  (hooks into PGE, DBE, WIRE)    │   ║
              ║    └─────────────────────────────────┘   ║
              ║                                          ║
              ║    ┌─────────────────────────────────┐   ║
              ║    │           ISE                   │   ║
              ║    │  Scheduler (cron, every 5min)   │   ║
              ║    │  Orchestrates: DBE, PGE, GLOE,  │   ║
              ║    │               WIRE, DNE          │   ║
              ║    └─────────────────────────────────┘   ║
              ║                                          ║
              ║    ┌─────────────────────────────────┐   ║
              ║    │           DNE                   │   ║
              ║    │  Delivery & Notification        │   ║
              ║    │  (in-app, email, SMS)           │   ║
              ║    │  (every 10 min via ISE)         │   ║
              ║    └─────────────────────────────────┘   ║
              ╚══════════════════════════════════════════╝
                                    │
                          ┌─────────▼──────────┐
                          │ Guidance, Insights, │
                          │ Predictions, Weekly │
                          │ Reports, Briefings  │
                          └────────────────────┘
```

---

## Execution Pipeline (Detailed)

All AI execution follows this pipeline. It must never be bypassed.

```
User Input
  → PHASE 1 — INTERPRETATION
    → UAIO (process_user_input — orchestrates interpretation)
      → SLCME (resolve_context — memory/learned mappings)
      → HTIE (interpret_human_time — temporal resolution)
      → SUE (interpret — semantic understanding, entity resolution)
      → Clarification check (ask user if ambiguous)
  → Intent Recognition (OpenAI function calling)
  → PHASE 2 — EXECUTION
    → UAIO (enrich_and_execute — sole execution authority)
      → Safety Engine (validate timestamps, bounds)
      → Action Router (enrich with time/context)
      → Module Execution (action_handlers.py)
      → Learning Pipeline (store mappings from successful actions)
  → PHASE 3 — POST-EXECUTION
    → SAE (update_user_state — refresh state snapshot)
    → PIE (run_insights — generate factual insights, enriched with SAE state)
      → PRIE (generate_predictions — trajectory projections)
    → PGE (generate_guidance — scheduled/on-demand, reads SAE + PIE + PRIE)
      → E3 (ensure_explain_record — evidence + explanation, non-blocking)
    → GLOE (update_learning_profile — triggered on guidance interactions)
    → DBE (generate_daily_briefing — scheduled daily, reads SAE + PIE + PRIE + PGE)
      → E3 (ensure_explain_record — evidence + explanation, non-blocking)
    → WIRE (generate_weekly_report — scheduled weekly)
      → E3 (ensure_explain_record — evidence + explanation, non-blocking)
    → ISE (run_scheduler_cycle — cron every 5min, orchestrates DBE/PGE/GLOE/DNE)
    → DNE (deliver_due_notifications — every 10min via ISE, routes to in-app/email/SMS)
  → Response Builder (enhance with temporal context)
  → Response to User
```

---

## Engine 1: HTIE — Human Temporal Intelligence Engine

**Location:** `apps/core/time/`
**Responsibility:** Parse natural language time expressions into precise timestamps. Never guess — ask clarification for ambiguous expressions.

### Public API

```python
from apps.core.time import interpret_human_time, get_current_time

result = interpret_human_time("3 days ago", user_timezone="America/New_York")
# result.success            → bool
# result.resolved_time      → TimeResolution (datetime_aware, confidence)
# result.is_ambiguous       → bool
# result.clarification_question → str (if ambiguous)
# result.time_expression    → str (extracted expression)
# result.remaining_text     → str (text after time removed)
# result.error              → str (if failed)

now = get_current_time("America/New_York")
# Returns timezone-aware datetime
```

### Internal Pipeline

```
User text → Parser (regex extraction) → Ambiguity Detector → Resolver → InterpretationResult
```

### Files

| File | Purpose |
|------|---------|
| `system_clock.py` | Single authoritative time source |
| `parser.py` | Regex-based extraction of time phrases from text |
| `resolver.py` | Converts expressions to timezone-aware datetimes |
| `ambiguity_detector.py` | Detects vague references ("recently", "a while ago") |
| `interpreter.py` | Orchestrator: parse → detect → resolve |

### Integration Rules

- UAIO calls HTIE via `time_pipeline.py` to enrich action parameters with `recorded_at`
- Action handlers use `_get_recorded_at(kwargs)` to respect HTIE-resolved timestamps
- If HTIE returns ambiguous, UAIO sets `needs_clarification=True` and halts execution

### Tests

76 tests in `apps/core/time/tests.py`

---

## Engine 2: SLCME — Self-Learning Context Memory Engine

**Location:** `apps/core/ai_memory/`
**Responsibility:** Learn from user clarifications. Store phrase→meaning mappings permanently. Auto-reuse based on confidence thresholds.

### Public API

```python
from apps.core.ai_memory import (
    resolve_context,
    store_learned_mapping,
    store_context_snapshot,
    log_clarification,
    get_current_context,
)

# Resolve what a user means
resolution = resolve_context(user, "my morning reading", context_type_hint="scripture")
# resolution.resolved            → bool
# resolution.meaning_type        → str
# resolution.meaning_identifier  → str
# resolution.source              → "context" | "learned" | None
# resolution.confidence          → "high" | "medium" | "low" | "none"
# resolution.needs_confirmation  → bool
# resolution.confirmation_question → str

# Store a learned mapping after clarification
mapping = store_learned_mapping(user, "my morning reading", "scripture", "psalm_23")

# Track current page context
snapshot = store_context_snapshot(user, "scripture_page", "psalm_23", {"book": "Psalms"})
```

### Confidence Thresholds

| Threshold | Value | Behavior |
|-----------|-------|----------|
| `CONFIDENCE_THRESHOLD` | 0.75 | Auto-use (no confirmation) |
| `CONFIRMATION_THRESHOLD` | 0.50 | Suggest with confirmation |
| Below 0.50 | — | Ignore, ask user |

### Resolution Priority

1. Current context snapshot (if `context_type_hint` provided)
2. High-confidence learned mapping → auto-use
3. Medium-confidence learned mapping → confirm with user
4. Unresolved → caller must ask or do DB lookup

### Models (app_label="core")

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `LearnedMapping` | Phrase→meaning associations | `phrase`, `meaning_type`, `meaning_identifier`, `confidence_score`, `usage_count`, `is_active` |
| `ContextSnapshot` | Current page/context tracking | `context_type`, `context_identifier`, `metadata` |
| `ClarificationLog` | Audit trail | `original_input`, `clarification_question`, `user_response`, `was_resolved`, FK to `LearnedMapping` |

### Learning Mechanics

- Initial confidence: **0.80**
- Reinforcement (same meaning): **+0.05** per use (max 1.0)
- Contradiction (different meaning): **reset to 0.80**
- Usage count tracks how often a mapping is applied

### Integration Rules

- UAIO calls SLCME via `context_pipeline.py` before intent execution
- Learning pipeline stores new mappings after successful actions
- Context snapshots are set by page_context from the frontend

### Tests

53 tests in `apps/core/ai_memory/tests.py`

---

## Engine 3: UAIO — Unified AI Orchestrator

**Location:** `apps/core/ai_orchestrator/`
**Responsibility:** Central brain. Connects HTIE and SLCME into the existing AI pipeline as an enhancement layer. Single entry point for all AI operations.

### Public API

```python
from apps.core.ai_orchestrator.orchestrator import process_user_input, enrich_and_execute

# Step 1: Pre-process (time + memory resolution)
orch_result = process_user_input(user, message, page_context=page_context)
# orch_result.success               → bool
# orch_result.needs_clarification    → bool
# orch_result.clarification_question → str
# orch_result.clarification_source   → "time" | "context"
# orch_result.time_resolved          → bool
# orch_result.context_resolved       → bool

# Step 2: Enrich intents and execute (after intent recognition)
action_results = enrich_and_execute(user, intent_results, orch_result)
```

### Integration Point

Wired into `apps/ai/personal_assistant.py` `send_message()`:

```python
# In send_message():
orch_result = orchestrator_process(self.user, message, page_context=page_context)
if orch_result.needs_clarification:
    response = orch_result.clarification_question
else:
    action_results = enrich_and_execute(self.user, intent_results, orch_result)
```

### Safety Engine

| Constant | Value | Purpose |
|----------|-------|---------|
| `MAX_BACKDATE_DAYS` | 365 | Maximum days into the past |
| `MAX_FUTURE_DAYS` | 365 | Maximum days into the future |

Validates all resolved timestamps are within bounds. Allows future timestamps for scheduling intents.

### Sub-Components

| File | Purpose |
|------|---------|
| `orchestrator.py` | Main entry points (`process_user_input`, `enrich_and_execute`) |
| `intent_engine.py` | Intent categorization (TIME_AWARE_INTENTS, CONTEXT_AWARE_INTENTS) |
| `time_pipeline.py` | Wraps HTIE — adds `recorded_at` to parameters |
| `context_pipeline.py` | Wraps SLCME — resolves context from page and learned mappings |
| `action_router.py` | `EnrichedAction` class, enriches parameters |
| `execution_engine.py` | Single execution authority + intelligence chain (SAE → PIE → PRIE) |
| `safety_engine.py` | Timestamp bounds validation |
| `learning_pipeline.py` | Stores mappings after successful actions |
| `response_builder.py` | Enhances messages with temporal context |
| `audit_logger.py` | JSON structured logging of all orchestrator interactions |

### Tests

35 tests in `apps/core/ai_orchestrator/tests.py`

---

## Engine 4: PIE — Proactive Insight Engine

**Location:** `apps/core/ai_insights/`
**Responsibility:** Event-driven + scheduled insight generation. Produces factual, explainable insights across all WLJ modules using a pluggable rule system.

### Public API

```python
from apps.core.ai_insights.insight_engine import run_insights

insights = run_insights(user, event)
# Returns: list[Insight] — created or updated Insight model instances
```

### Event Format

```python
event = {
    "event_type": "record_created" | "record_updated" | "scheduled_check",
    "module": "health" | "goals" | "scripture" | "journal" | "habits" | "all",
    "action": "update_weight" | "log_habit" | "scheduled_check" | ...,
    "record_id": int | None,
    "timestamp_utc": "2026-02-15T10:00:00+00:00",
    "user_timezone": "America/New_York",
    "context": {}  # Optional additional context
}
```

### Rule Contract

```python
from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.rule_registry import register

@register
class MyRule(BaseInsightRule):
    rule_name = "my_rule"
    module = "health"
    insight_type = "my_insight"
    min_confidence_to_store = 0.6    # Minimum to persist
    min_confidence_to_notify = 0.8   # Minimum to notify user

    def applies(self, user, event) -> bool:
        return event.get("module") in ("all", "health")

    def evaluate(self, user, event) -> list[dict]:
        return [{
            "severity": "warning",        # info | positive | warning | critical
            "title": "Short title",
            "message": "Detailed message",
            "confidence_score": 0.85,
            "explain_why": "Why this insight was generated",
            "evidence": {"record_ids": [...], "values": [...]},
            "dedupe_key": "sha256-hash",   # REQUIRED
        }]
```

### Registered Rules (20 rules, 11 domains)

| File | Rules |
|------|-------|
| `rules_health.py` | WeightTrendUp, WeightTrendDown, MissingWeightLogging |
| `rules_body_composition.py` | MissingBodyComp, BodyFatChange |
| `rules_labs_vitals.py` | RepeatedOutOfRange |
| `rules_goals.py` | GoalDeadlineRisk, GoalStagnation |
| `rules_habits.py` | HabitBrokenStreak, HabitConsistencyPositive |
| `rules_scripture.py` | ScriptureReadingDropOff |
| `rules_journal.py` | JournalStreakPositive, JournalDropOff |
| `rules_transformation.py` | NutritionCalorieTrend, ProteinDeficit, CarbGlucoseCorrelation, FastingConsistency, WorkoutConsistency, StrengthPlateau, TransformationMomentum |

### Insight Model (app_label="core", db_table="core_ai_insight")

| Field | Type | Purpose |
|-------|------|---------|
| `user` | FK(User) | Owner (related_name="pie_insights") |
| `module` | CharField(100) | Source module |
| `insight_type` | CharField(120) | Rule identifier |
| `severity` | CharField(20) | info / positive / warning / critical |
| `title` | CharField(180) | Short display title |
| `message` | TextField | Full insight message |
| `confidence_score` | Float | 0.0–1.0 |
| `explain_why` | TextField | Human-readable reasoning |
| `evidence` | JSONField | Auditable provenance data |
| `status` | CharField(20) | new / read / dismissed |
| `dedupe_key` | CharField(255) | SHA-256 deduplication key |
| `notified_at` | DateTimeField | When user was notified |

### Deduplication

```python
from apps.core.ai_insights.models import build_dedupe_key

key = build_dedupe_key(user_id, insight_type, window_start, window_end, key_record_ids)
# Returns: SHA-256 hash truncated to 64 chars
```

Same `dedupe_key` + non-dismissed → update existing. Dismissed → skip.

### Notification Rate Limiting

Maximum **3 notifications per day** per user. Only warning/critical/high-confidence positive insights trigger notifications.

### Scheduled Execution

```bash
python manage.py run_daily_insights
```

### User Interface

Insights Inbox at `/insights/` — filterable by status (new/read/dismissed), AJAX mark read/dismiss.

### Integration Rules

- UAIO fires PIE via `execution_engine.py:_run_intelligence_chain()` after every successful action
- PIE calls `_trigger_predictions()` after insight generation (→ PRIE)
- Scheduler runs daily for all active users (`run_daily_insights` management command)
- Failures in PIE never break the main AI pipeline (wrapped in try/except)

### Tests

30 tests in `apps/core/ai_insights/tests.py`

---

## Engine 5: PRIE — Predictive Intelligence Engine

**Location:** `apps/core/ai_predictions/`
**Responsibility:** Trajectory projection using deterministic math (linear regression). Forecasts future values based on historical data. Never hallucinated — always explainable with confidence scores.

### Public API

```python
from apps.core.ai_predictions import generate_predictions

predictions = generate_predictions(user, module="health", record_id=None)
# Returns: list[Prediction] — created Prediction model instances
```

### Prediction Rule Contract

```python
from apps.core.ai_predictions.base_prediction_rule import BasePredictionRule
from apps.core.ai_predictions.prediction_registry import register_prediction

@register_prediction
class MyPrediction(BasePredictionRule):
    rule_name = "my_prediction"
    module = "health"
    prediction_type = "weight_30d"
    min_confidence_to_store = 0.30

    def applies(self, user, event) -> bool:
        return event.get("module") in ("all", "health")

    def predict(self, user, event) -> list[dict]:
        return [{
            "prediction_type": "weight_30d",
            "module": "health",
            "predicted_value": 265.5,
            "predicted_date": datetime(...),
            "confidence_score": 0.72,
            "explanation": "Human-readable projection",
            "evidence": {"slope": 0.5, "r_squared": 0.92, ...},
            "dedupe_key": "sha256-hash",
        }]
```

### Registered Prediction Rules (9 rules, 6 modules)

| Rule | Module | Prediction |
|------|--------|-----------|
| `WeightProjectionRule` | health | Weight at 30/60/90 days |
| `BodyFatProjectionRule` | health | Body fat % at 30/60/90 days |
| `LeanMassProjectionRule` | health | Lean mass at 30/60/90 days |
| `GoalCompletionDateRule` | goals | Completion date from milestone velocity |
| `HabitContinuationRule` | habits | Continuation probability (0–1) |
| `LabMarkerTrendRule` | labs | Marker trend direction + out-of-range warnings |
| `NutritionWeightProjectionRule` | nutrition | Weight projection from calorie surplus/deficit at 30/60/90d |
| `StrengthProgressionPredictionRule` | fitness | Training volume trajectory at 30/60d |
| `TransformationSuccessProbabilityRule` | transformation | Protocol goal probability (0–1) by target date |

### Projection Math

```python
from apps.core.ai_predictions.projection_math import linear_regression, project_value

slope, intercept, r_squared = linear_regression(x_values, y_values)
# Pure Python — no numpy required
# Returns (0.0, mean_y, 0.0) if n < 2
# R² = 0.0–1.0 (goodness of fit)

future_value = project_value(slope, intercept, x_target)
```

### Confidence Scoring

```python
from apps.core.ai_predictions.confidence_engine import compute_confidence

score = compute_confidence(
    data_point_count=15,
    r_squared=0.85,
    days_of_history=60,
    days_forward=30,
)
# Returns: float 0.0–1.0
```

**Four scoring factors (max 1.0 total):**

| Factor | Weight | Scoring |
|--------|--------|---------|
| Data volume | 0–0.30 | 20+ pts: 0.30, 10+: 0.25, 5+: 0.18, 3+: 0.10, <3: 0.05 |
| Trend consistency (R²) | 0–0.30 | `r_squared × 0.30` |
| History-to-projection ratio | 0–0.20 | ≥3x: 0.20, ≥2x: 0.15, ≥1x: 0.10, <1x: 0.05 |
| Projection distance | 0–0.20 | ≤30d: 0.20, ≤60d: 0.15, ≤90d: 0.10, >90d: 0.05 |

**Confidence labels:** ≥0.75 high, ≥0.50 medium, ≥0.30 low, <0.30 very low

### Prediction Model (app_label="core", db_table="core_ai_prediction")

| Field | Type | Purpose |
|-------|------|---------|
| `user` | FK(User) | Owner (related_name="prie_predictions") |
| `prediction_type` | CharField(120) | e.g., "weight_30d" |
| `module` | CharField(100) | Source module |
| `predicted_value` | Float | Projected numeric value |
| `predicted_date` | DateTimeField | When the prediction applies |
| `confidence_score` | Float | 0.0–1.0 |
| `explanation` | TextField | Human-readable projection |
| `evidence` | JSONField | Auditable data (slope, R², points) |
| `status` | CharField(20) | active / superseded / expired |
| `dedupe_key` | CharField(255) | SHA-256 deduplication key |

### Supersede Pattern

When a new prediction is generated with the same `dedupe_key`:
1. Existing active prediction → marked `superseded`
2. New prediction created as `active`

### Scheduled Execution

```bash
python manage.py run_prediction_engine
```

### Data Abstraction Layer

```python
from apps.core.ai_predictions.prediction_engine import get_prediction_input_data

# Returns QuerySet/list — reads from SAE cache when available, DB fallback
data = get_prediction_input_data(user, module="health", data_type="weight_entries", lookback_days=90)
```

Supported data types: `weight_entries`, `body_fat_entries`, `lean_mass_entries`, `active_goals`, `active_habits`, `lab_results`.

### Integration Rules

- PIE's `run_insights()` calls `_trigger_predictions()` after insight processing
- Predictions also generated via daily scheduler (`run_prediction_engine` management command)
- `get_prediction_input_data()` provides SAE-ready data access with DB fallback
- Failures in PRIE never break the insight pipeline (wrapped in try/except)

### Tests

32 tests in `apps/core/ai_predictions/tests.py`

---

## Cross-Engine Integration Map

| From | To | Mechanism | Location |
|------|----|-----------|----------|
| UAIO → SLCME | Context resolution | `context_pipeline.py` |
| UAIO → HTIE | Time resolution | `time_pipeline.py` |
| UAIO → SUE | Semantic understanding | `orchestrator.py:_run_semantic_understanding()` |
| UAIO → Safety | Timestamp validation | `safety_engine.py` |
| UAIO → Actions | Enriched execution | `execution_engine.py` |
| UAIO → Learning | Store mappings | `learning_pipeline.py` |
| UAIO → SAE | State update | `execution_engine.py:_run_intelligence_chain()` |
| UAIO → PIE | Fire insight event | `execution_engine.py:_run_intelligence_chain()` |
| SUE → SLCME | Entity resolution | `entity_resolver.py:_resolve_from_slcme()` |
| SUE → SAE | Entity resolution | `entity_resolver.py:_resolve_from_sae()` |
| PIE → PRIE | Trigger predictions | `insight_engine.py:_trigger_predictions()` |
| PRIE → SAE | Read cached state | `prediction_engine.py:get_prediction_input_data()` |
| PIE → SAE | Event enrichment | `insight_engine.py:_enrich_event_with_state()` |
| Action Handlers → HTIE | Use resolved time | `action_handlers.py:_get_recorded_at()` |
| PGE → SAE | Read user state | `guidance_engine.py:_get_user_state()` |
| PGE → PIE | Read recent insights | `guidance_engine.py:_get_recent_insights()` |
| PGE → PRIE | Read active predictions | `guidance_engine.py:_get_active_predictions()` |
| All Engines → HTIE | System time | `system_clock.py:get_current_time()` |
| PGE → E3 | Evidence enrichment | `guidance_logger.py` (post-store hook) |
| DBE → E3 | Evidence enrichment | `briefing_engine.py` (post-store hook) |
| WIRE → E3 | Evidence enrichment | `report_engine.py` (post-store hook) |
| DNE → PGE | Scan undelivered guidance | `delivery_engine.py:_get_undelivered_guidance()` |
| DNE → DBE | Scan undelivered briefings | `delivery_engine.py:_get_undelivered_briefings()` |
| DNE → WIRE | Scan undelivered reports | `delivery_engine.py:_get_undelivered_reports()` |
| ISE → DNE | Scheduled delivery cycle | `scheduler_runner.py:run_delivery_cycle()` |

### Phase 3 — Post-Execution Intelligence Chain

After execution completes, the Phase 3 intelligence chain fires from `execute_action()`:

```
Action Success (Phase 2 complete)
  → PHASE 3 — POST-EXECUTION
    → SAE (update_user_state)
      → Rebuild affected module state from database
    → PIE (run_insights, enriched with SAE state)
      → Evaluate all applicable insight rules
      → PRIE (_trigger_predictions)
        → Evaluate all applicable prediction rules
    → PGE (generate_guidance) — scheduled/on-demand
      → Read SAE state + PIE insights + PRIE predictions
      → Select → Rank → Store guidance items
```

The SAE→PIE→PRIE chain is centralized in `execution_engine.py:_run_intelligence_chain()`.
PGE runs separately (daily scheduler or on-demand) and reads the outputs of all three engines.

**Phase boundary:** No Phase 3 engine may execute domain actions. They observe and analyze only.

---

## Database Migrations

| Migration | Engine | Models |
|-----------|--------|--------|
| `core.0053` | SLCME | LearnedMapping, ContextSnapshot, ClarificationLog |
| `core.0054` | PIE | Insight |
| `core.0055` | PRIE | Prediction |
| `core.0056` | SAE | UserState |
| `core.0057` | SUE | SemanticDecisionLog |
| `core.0058` | PGE | GuidanceItem |
| `core.0059` | PGE | GuidanceItem lifecycle fields (acknowledged_at, dismissed_at, snoozed_until, acted_upon_at, action_type, feedback) |
| `core.0064` | WIRE | WeeklyIntelligenceReport |
| `core.0065` | E3 | ExplainRecord |
| `core.0066` | DNE | DeliveredNotification + Notification.intelligence category |
| `users.0062` | DNE | UserPreferences intelligence notification fields |

HTIE and UAIO are stateless — no database models required.

---

## Compliance Rules

1. **No bypass:** All AI interactions must flow through the UAIO orchestrator
2. **No direct time parsing:** Use HTIE, never `datetime.strptime()` on user input
3. **No hardcoded context:** Use SLCME for phrase→meaning resolution
4. **No untracked insights:** All data pattern observations must go through PIE
5. **No untracked predictions:** All trajectory projections must go through PRIE
6. **No silent failures:** Engine errors are logged but never break the user flow
7. **No black-box math:** All projections use explainable, auditable calculations
8. **Dedupe everything:** Both insights and predictions use SHA-256 dedupe keys
9. **Confidence always:** Every insight and prediction must carry a confidence score
10. **Evidence always:** Every insight and prediction must carry auditable evidence
11. **Single time source:** All intelligence pipeline code uses `get_current_time()` from HTIE, never `datetime.now()` or `timezone.now()` directly
12. **Single execution authority:** All post-action intelligence triggers (SAE, PIE, PRIE) flow through `execution_engine.py:_run_intelligence_chain()` only
13. **State authority:** SAE is the authoritative source of current user state. No intelligence engine may reconstruct full user state independently — use `get_user_state()` or `get_module_state()`. Direct database queries for current state summaries are prohibited when SAE state is available.
14. **State currency:** All features that modify user data must ensure SAE is updated. AI-initiated actions update SAE automatically via the intelligence chain. Non-AI data changes must call `update_user_state()` explicitly.
15. **Semantic understanding:** SUE provides pre-intent semantic analysis (intent candidates, entity extraction, ambiguity detection). SUE does NOT execute actions — UAIO remains execution authority. SUE failures must never break the pipeline.
16. **Guidance authority:** PGE is the sole authority for proactive guidance. Guidance must always be evidence-based (backed by SAE state, PIE insights, or PRIE predictions). PGE does NOT execute actions or generate insights — it surfaces existing intelligence. PGE failures must never break any other engine.
17. **Phase integrity:** Each engine operates only within its designated phase. Interpretation engines (SUE, SLCME, HTIE) may not execute actions. The execution engine (UAIO) may not interpret meaning independently. Post-execution engines (SAE, PIE, PRIE, PGE) may not execute actions. Violating phase boundaries is a critical architectural error.
18. **State-first for current values:** Any code that needs "current" scalar values (current weight, active goal count, days since last entry, etc.) MUST read from SAE via `get_user_state()`, `get_module_state()`, or `get_state_value()`. Direct database queries are allowed ONLY for: (a) historical time-series data (charts, regressions, trend windows), (b) display-specific objects that SAE doesn't store (recent entry lists, medicine schedules, goal progress objects). Use `@state_first` decorator or `require_state_first()` to document state-first intent.

### State Authority Rules

| Rule | Allowed | Prohibited |
|------|---------|------------|
| **Current scalar values** | `get_state_value(user, "health.weight_current")` | `WeightEntry.objects.filter(user=user).first().value` |
| **Historical time-series** | `WeightEntry.objects.filter(recorded_at__gte=cutoff)` | N/A — DB queries for history are correct |
| **Display object lists** | `JournalEntry.objects.order_by('-date')[:5]` | N/A — SAE doesn't store display objects |
| **Trend direction** | `get_state_value(user, "health.weight_trend")` | Re-computing trend from DB when SAE has it |
| **Counts** | `get_state_value(user, "goals.active_goal_count", 0)` | `LifeGoal.objects.filter(status='active').count()` for display |

**Enforcement:** `apps/core/ai_state/state_guards.py` provides `@state_first(reason)` decorator and `require_state_first(path, reason)` for documenting state-first intent. These are audit markers, not runtime blockers.

---

## Engine 6: SAE — State Awareness Engine

**Location:** `apps/core/ai_state/`
**Responsibility:** Maintain an always-current snapshot of each user's life state. Authoritative source of "current state" for the entire intelligence system.

### Public API

```python
from apps.core.ai_state import (
    get_user_state,      # Full state snapshot
    get_module_state,    # Single module state
    get_state_value,     # Single value by dot-path
    update_user_state,   # Incremental update after action
    rebuild_user_state,  # Full rebuild from database
    get_cached_data,     # Data access for PRIE predictions
)

# Read full state
state = get_user_state(user)
# state["health"]["weight_current"] → 180.5
# state["goals"]["active_goal_count"] → 3
# state["habits"]["longest_streak"] → 7

# Read single module
health = get_module_state(user, "health")

# Read single value (preferred for point lookups)
weight = get_state_value(user, "health.weight_current")
goal_count = get_state_value(user, "goals.active_goal_count", 0)

# Update after action (called by UAIO automatically)
update_user_state(user, "health", record_id=42)
```

### State Structure

```json
{
  "health": {
    "weight_current": 180.5,
    "weight_unit": "lb",
    "weight_trend": "decreasing",
    "last_weight_entry": "2026-02-15T...",
    "weight_entries_90d": 12,
    "body_fat_current": 22.5,
    "sleep_avg_duration_7d": 450.0,
    "steps_avg_7d": 8500,
    "bp_systolic": 120,
    "bp_diastolic": 80
  },
  "goals": {
    "active_goal_count": 3,
    "completion_rate": 0.65,
    "next_deadline": "2026-03-15",
    "days_to_next_deadline": 28,
    "overdue_goal_count": 0,
    "total_milestones": 12,
    "completed_milestones": 8
  },
  "habits": {
    "active_habit_count": 4,
    "longest_streak": 14,
    "avg_completion_rate": 0.82,
    "last_activity": "2026-02-15"
  },
  "faith": {
    "active_reading_plans": 1,
    "last_scripture_read": "2026-02-14T...",
    "days_since_reading": 1,
    "reading_streak": 5,
    "unanswered_prayers": 3
  },
  "journal": {
    "last_entry": "2026-02-14",
    "last_mood": "good",
    "days_since_entry": 1,
    "entry_frequency": 3.5,
    "entries_30d": 15,
    "mood_distribution": {"great": 3, "good": 8, "okay": 4}
  }
}
```

### Database Model

| Model | Table | Fields |
|-------|-------|--------|
| `UserState` | `core_user_state` | user (1:1), state_data (JSON), last_updated, created_at |

### Module Files

| File | Purpose |
|------|---------|
| `models.py` | UserState model (OneToOneField per user) |
| `state_engine.py` | Primary read interface: `get_user_state()`, `rebuild_user_state()` |
| `state_updater.py` | Incremental update: `update_user_state()` (called by UAIO) |
| `state_builder.py` | Domain builders: `build_health_state()`, `build_goal_state()`, `build_nutrition_state()`, `build_fasting_state()`, `build_fitness_state()`, `build_transformation_state()`, etc. |
| `state_reader.py` | PRIE data access: `get_cached_data()` |
| `state_registry.py` | Custom builder registration for new modules |
| `state_utils.py` | Debugging: `get_state_age_seconds()`, `invalidate_state()` |
| `admin.py` | Read-only admin display |
| `tests.py` | 50 tests covering all components |

### Integration Points

| From | To | Mechanism |
|------|----|-----------|
| UAIO → SAE | Post-action state update | `execution_engine.py:_run_intelligence_chain()` |
| PIE → SAE | Event enrichment with state | `insight_engine.py:_enrich_event_with_state()` |
| PRIE → SAE | Cached data read | `prediction_engine.py:get_prediction_input_data()` |

### Safety Requirements

- State always reflects actual database values
- State never invents or infers unsupported values
- State updates immediately after data changes
- State remains fully auditable via admin interface

---

## Engine 7: SUE — Semantic Understanding Engine

**Location:** `apps/core/ai_semantics/`
**Responsibility:** Interpret human meaning and intent from raw text. Parses input into structured semantic data (intent candidates, entities, time expressions, contextual references) without executing actions. UAIO remains execution authority.

### Public API

```python
from apps.core.ai_semantics import interpret

result = interpret(user, "log weight 175 lbs yesterday", context=page_context)
# result.intent              → "log_weight"
# result.domain              → "health"
# result.entities            → {"value": 175.0, "unit": "lb"}
# result.time_expression     → "yesterday"
# result.confidence          → ConfidenceScore (overall, intent_score, entity_score)
# result.is_ambiguous        → bool
# result.ambiguity_type      → "intent" | "entity" | "multi_intent" | "insufficient_info"
# result.clarification_question → str (if ambiguous)
# result.alternative_intents → [{intent, domain, confidence}]
# result.used_slcme          → bool
# result.used_sae            → bool
# result.used_context        → bool
```

### Internal Pipeline

```
Raw Text → Parser (regex intent/entity detection) → Entity Resolver (context→SLCME→SAE→DB)
         → Ambiguity Engine (detect conflicts) → Confidence Engine (composite score)
         → SemanticResult
```

### Entity Resolution Priority Chain

1. **Current page context** (highest — user is looking at this object)
2. **SLCME learned mappings** (previous clarifications)
3. **SAE state** (current user state, e.g., "my weight" → latest weight)
4. **Database fallback** (deferred to UAIO execution phase)

### Confidence Threshold

- `>= 0.80` → Safe to execute without clarification
- `< 0.80` → Ask for clarification

### Files

| File | Purpose |
|------|---------|
| `semantic_engine.py` | Main entry: `interpret()` orchestrates full pipeline |
| `semantic_parser.py` | Rule-based parsing: intent candidates, entities, time, references |
| `entity_resolver.py` | Resolve contextual references via priority chain |
| `ambiguity_engine.py` | Detect intent/entity/domain/multi-intent ambiguity |
| `confidence_engine.py` | Compute composite confidence score |
| `semantic_logger.py` | Log decisions to SemanticDecisionLog |
| `semantic_models.py` | `SemanticDecisionLog` model (append-only audit) |
| `admin.py` | Read-only admin display |
| `tests.py` | 77 tests covering all components |

### Integration Points

| From | To | Mechanism |
|------|----|-----------|
| UAIO → SUE | Semantic understanding | `orchestrator.py:_run_semantic_understanding()` |
| SUE → SLCME | Entity resolution | `entity_resolver.py:_resolve_from_slcme()` |
| SUE → SAE | Entity resolution | `entity_resolver.py:_resolve_from_sae()` |

### Safety Requirements

- SUE does NOT execute actions
- SUE failures never break the orchestrator pipeline (ImportError guard)
- All decisions are logged to SemanticDecisionLog for audit
- Confidence thresholds prevent low-confidence auto-execution

---

## Engine 8: PGE — Proactive Guidance Engine

**Location:** `apps/core/ai_guidance/`
**Responsibility:** Evaluate user state, insights, and predictions to determine what the user should be proactively shown. PGE does NOT execute actions or generate insights — it selects, ranks, and surfaces the most important existing intelligence as actionable guidance items.

### Public API

```python
from apps.core.ai_guidance import generate_guidance
from apps.core.ai_guidance.guidance_engine import get_active_guidance, expire_old_guidance

# Generate guidance for a user (full pipeline)
items = generate_guidance(user)
# Returns: list[GuidanceItem] — created or updated instances

# Retrieve active guidance (for display)
items = get_active_guidance(user, limit=5)
# Returns: QuerySet[GuidanceItem] — sorted by priority, excludes expired

# Expire old items (cleanup)
count = expire_old_guidance()
```

### Internal Pipeline

```
SAE State + PIE Insights + PRIE Predictions
  → Guidance Selector (evaluate all rules)
    → Guidance Ranker (score, sort, limit to top 5)
      → Guidance Logger (store with deduplication)
        → GuidanceItem instances
```

### Guidance Rule Contract

```python
from apps.core.ai_guidance.guidance_registry import register_guidance
from apps.core.ai_guidance.guidance_rules import BaseGuidanceRule

@register_guidance
class MyRule(BaseGuidanceRule):
    rule_name = "my_rule"
    module = "health"

    def evaluate(self, user, state, insights, predictions):
        return [{
            "title": "Short headline",
            "message": "Detailed guidance message",
            "priority": 3,          # 1=Critical, 5=Info
            "guidance_type": self.rule_name,
            "source": "pie_insight", # pie_insight | prie_prediction | sae_state | composite
            "module": self.module,
            "confidence_score": 0.85, # Optional
            "evidence": {...},       # Auditable data
            "dedupe_key": "sha256",  # REQUIRED
        }]
```

### Registered Rules (9 rules, 8 modules)

| Rule | Module | Surfaces |
|------|--------|----------|
| `GoalRiskRule` | goals | Overdue goals + PRIE behind-schedule predictions |
| `HabitInactivityRule` | habits | PIE broken-streak warnings |
| `HealthTrendRule` | health | PIE health insights + PRIE health projections |
| `JournalInactivityRule` | journal | PIE journal drop-off + SAE zero-entry detection |
| `PositiveReinforcementRule` | (all) | PIE positive insights across all modules |
| `TransformationCoachingRule` | transformation | Overall transformation status + PRIE predictions |
| `ProteinAdjustmentRule` | nutrition | Specific protein intake recommendations from PIE insights |
| `WorkoutFrequencyAdjustmentRule` | fitness | Workout frequency recommendations from PIE + SAE |
| `FastingOptimizationRule` | fasting | Fasting schedule optimization from PIE insights |

### Ranking Algorithm

Score = Priority weight (10–50) + Confidence bonus (0–10) + Source bonus (2–5) + Evidence richness (0–3)

| Factor | Points | Details |
|--------|--------|---------|
| Priority | 10–50 | `(6 - priority) × 10` |
| Confidence | 0–10 | `confidence × 10` |
| Source | 2–5 | prie_prediction=5, pie_insight=3, sae_state=2 |
| Evidence | 0–3 | `min(3, len(evidence))` |

Maximum 5 items surfaced per user (`MAX_GUIDANCE_ITEMS`).

### GuidanceItem Model (app_label="core", db_table="core_guidance_item")

| Field | Type | Purpose |
|-------|------|---------|
| `user` | FK(User) | Owner (related_name="guidance_items") |
| `title` | CharField(255) | Short guidance headline |
| `message` | TextField | Detailed guidance message |
| `priority` | IntegerField | 1=Critical, 2=High, 3=Medium, 4=Low, 5=Info |
| `guidance_type` | CharField(100) | Rule that generated this |
| `source` | CharField(50) | pie_insight / prie_prediction / sae_state / composite |
| `module` | CharField(50) | Domain module |
| `confidence_score` | Float | 0.0–1.0 (if predictive) |
| `evidence` | JSONField | Structured evidence |
| `is_active` | Boolean | Currently active |
| `is_read` | Boolean | User has seen it |
| `expires_at` | DateTimeField | Auto-expire date |
| `acknowledged_at` | DateTimeField | When user acknowledged |
| `dismissed_at` | DateTimeField | When user dismissed (deactivates item) |
| `snoozed_until` | DateTimeField | Hidden until this time |
| `acted_upon_at` | DateTimeField | When user took action |
| `action_type` | CharField(100) | What action was taken (e.g., 'navigated', 'updated_goal') |
| `feedback` | CharField(255) | User feedback on guidance quality |
| `dedupe_key` | CharField(255) | SHA-256 deduplication key |
| `metadata` | JSONField | Additional rendering data |

### Guidance Lifecycle

Guidance items follow a lifecycle: **new → acknowledged → acted_upon / dismissed / snoozed**.

| Action | Method | Effect |
|--------|--------|--------|
| Acknowledge | `item.acknowledge()` | Sets `acknowledged_at`, marks read |
| Dismiss | `item.dismiss()` | Sets `dismissed_at`, deactivates — item never reappears |
| Snooze | `item.snooze(until)` | Sets `snoozed_until` — hidden until that time, then reappears |
| Acted Upon | `item.mark_acted_upon(action_type)` | Sets `acted_upon_at`, optionally records action_type |
| Feedback | `item.set_feedback(text)` | Stores user feedback (max 255 chars) |

**Lifecycle properties:**
- `is_acknowledged` — `acknowledged_at is not None`
- `is_dismissed` — `dismissed_at is not None`
- `is_snoozed` — `snoozed_until` is in the future
- `is_acted_upon` — `acted_upon_at is not None`
- `is_active_guidance` — `is_active AND NOT dismissed AND NOT snoozed`

**Time resolution:** All lifecycle timestamps use HTIE's `get_current_time()` via `_get_now()` helper (with `timezone.now()` fallback).

**Query filtering:** `get_active_guidance()` excludes dismissed items (`dismissed_at__isnull=True`) and currently snoozed items (`snoozed_until__gt=now`). Snoozed items automatically reappear when the snooze period ends.

### Deduplication

```python
from apps.core.ai_guidance.models import build_guidance_dedupe_key

key = build_guidance_dedupe_key(user_id, guidance_type, *extra_parts)
# Returns: SHA-256 hash truncated to 64 chars
```

Same `dedupe_key` + active → update existing. Inactive → create new.

### Scheduled Execution

```bash
python manage.py run_guidance_engine              # All active users
python manage.py run_guidance_engine --user=42    # Single user
python manage.py run_guidance_engine --expire     # Only expire old items
```

Default expiry: 7 days.

### User Interface

Guidance Inbox at `/guidance/` — filterable by status (active/read/all), AJAX mark-read/dismiss.
JSON API at `/guidance/api/` — returns active items sorted by priority, includes lifecycle fields.
Action API at `/guidance/<pk>/action/` — POST with `action` = read/acknowledge/dismiss/snooze/acted/feedback.

### Files

| File | Purpose |
|------|---------|
| `guidance_engine.py` | Main entry: `generate_guidance()`, `get_active_guidance()`, `expire_old_guidance()` |
| `guidance_selector.py` | Run all rules, collect candidates |
| `guidance_ranker.py` | Score, sort, and limit candidates |
| `guidance_logger.py` | Store with deduplication |
| `guidance_rules.py` | 5 registered rules + `BaseGuidanceRule` |
| `guidance_registry.py` | `@register_guidance` decorator |
| `models.py` | `GuidanceItem` model + `build_guidance_dedupe_key()` |
| `views.py` | Inbox view, action view, JSON API view |
| `urls.py` | URL routing |
| `admin.py` | Read-only admin display |
| `tests.py` | 109 tests covering all components + lifecycle |

### Integration Points

| From | To | Mechanism |
|------|----|-----------|
| PGE → SAE | Read user state | `guidance_engine.py:_get_user_state()` |
| PGE → PIE | Read recent insights | `guidance_engine.py:_get_recent_insights()` |
| PGE → PRIE | Read active predictions | `guidance_engine.py:_get_active_predictions()` |

### Safety Requirements

- PGE does NOT execute actions or generate insights
- PGE failures never break any other engine (all reads are ImportError-guarded)
- All guidance is evidence-based — no hallucinated recommendations
- Deduplication prevents duplicate guidance for the same situation
- Expired items are automatically deactivated

---

## Engine 9: GLOE — Guidance Learning Optimization Engine

**Location:** `apps/core/ai_guidance_learning/`
**Responsibility:** Learn from user interactions with guidance items (acknowledge, dismiss, act) to compute a per-user responsiveness score that gently adjusts PGE ranking. Users who engage more with guidance get slightly boosted relevance; users who dismiss frequently get slightly reduced volume emphasis.

### Public API

```python
from apps.core.ai_guidance_learning import update_learning_profile, log_learning_event

# Log a lifecycle event (called automatically by GuidanceActionView)
event = log_learning_event(user, guidance_item, "acknowledged")  # or "dismissed", "acted"

# Manually trigger profile recalculation
profile = update_learning_profile(user)

# Get current responsiveness score (0.0-1.0, 0.5 = neutral)
from apps.core.ai_guidance_learning.learning_engine import get_responsiveness_score
score = get_responsiveness_score(user)  # Returns 0.5 for new users
```

### Scoring Formula

```
responsiveness_score = (
    acted_rate × 0.40           # Highest weight — user takes action
  + acknowledged_rate × 0.25    # User reads and acknowledges
  - dismissed_rate × 0.20       # Negative — user finds guidance unhelpful
  + response_speed × 0.15       # Faster response = more engaged
)
```

Response speed: < 1 hour = 1.0, > 3 days = 0.0, linear interpolation between.

### PGE Ranker Integration

```
final_score = base_score × (1 + (responsiveness - 0.5) × 2 × 0.25)
```

At neutral (0.5), no adjustment. Maximum ±25% influence. Priority ordering is never overridden.

### Files

| File | Purpose |
|------|---------|
| `learning_models.py` | GuidanceLearningProfile (per-user aggregate), GuidanceLearningEvent (individual events) |
| `learning_calculator.py` | Weighted responsiveness score computation |
| `learning_logger.py` | Log events and trigger profile updates |
| `learning_engine.py` | Aggregate events into profile, public score API |
| `admin.py` | Read-only admin views for both models |

### Cross-Engine Dependencies

| From | To | Mechanism |
|------|----|-----------|
| GLOE → PGE | Adjust ranking scores | `guidance_ranker.py:_get_responsiveness()` |
| PGE → GLOE | Log lifecycle events | `views.py:_log_gloe_event()` |

### Safety Requirements

- GLOE failures never break guidance actions (fire-and-forget)
- GLOE failures never break PGE ranking (returns None → no adjustment)
- Score is clamped to [0.0, 1.0]
- Adjustment is proportional (never overrides priority)

### Tests

40 tests in `apps/core/ai_guidance_learning/tests.py`

---

## Engine 10: DBE — Daily Briefing Engine

**Location:** `apps/core/ai_briefing/`
**Responsibility:** Aggregate intelligence from SAE, PIE, PRIE, and PGE into a single daily briefing per user. Surfaces the most important items across all engines in a prioritized summary.

### Public API

```python
from apps.core.ai_briefing import generate_daily_briefing

# Generate today's briefing for a user
briefing = generate_daily_briefing(user)

# Get today's briefing (read-only, no generation)
from apps.core.ai_briefing.briefing_engine import get_todays_briefing
briefing = get_todays_briefing(user)  # Returns None if not generated yet
```

### Pipeline

```
gather (SAE + PIE + PRIE + PGE) → select (max 5, priority-ordered) → rank → summarize → store
```

### Selection Priority

1. Critical guidance items
2. High-confidence predictions
3. Warning/critical insights
4. Remaining items by composite score

### Files

| File | Purpose |
|------|---------|
| `models.py` | DailyBriefing model (unique per user per day) |
| `briefing_engine.py` | Main pipeline: gather → select → rank → summarize → store |
| `briefing_selector.py` | Select and prioritize items (max 5) |
| `briefing_ranker.py` | Composite score from priority, confidence, type |
| `briefing_logger.py` | Dedup per user per day, race-condition safe |
| `admin.py` | Read-only admin view |
| `management/commands/generate_daily_briefings.py` | Cron command with `--user` and `--dry-run` |

### Cross-Engine Dependencies

| From | To | Mechanism |
|------|----|-----------|
| DBE → SAE | Read user state | `briefing_engine.py:_gather_state()` |
| DBE → PIE | Read recent insights | `briefing_engine.py:_gather_insights()` |
| DBE → PRIE | Read active predictions | `briefing_engine.py:_gather_predictions()` |
| DBE → PGE | Read active guidance | `briefing_engine.py:_gather_guidance()` |

### Safety Requirements

- DBE is read-only — never creates insights, predictions, or guidance
- One briefing per user per day (unique constraint + dedup)
- Race-condition safe (IntegrityError → return existing)
- All engine reads are ImportError-guarded

### Tests

27 tests in `apps/core/ai_briefing/tests.py`

---

## Engine 11: ISE — Intelligence Scheduler Engine

**Location:** `apps/core/ai_scheduler/`
**Responsibility:** Centrally manage scheduled execution of all intelligence engines. ISE does NOT generate intelligence — it orchestrates when engines run. Triggered via Railway cron every 5 minutes.

### Public API

```python
from apps.core.ai_scheduler import run_scheduler_cycle

# Execute one scheduler cycle (checks all due tasks)
result = run_scheduler_cycle()
# result = {"executed": 2, "skipped": 1, "failed": 0}
```

### Management Command

```bash
# Run one scheduler cycle (Railway cron calls this every 5 minutes)
python manage.py run_intelligence_scheduler

# Dry run — show task status without executing
python manage.py run_intelligence_scheduler --dry-run
```

### Registered Tasks

| Task Name | Engine | Interval | Description |
|-----------|--------|----------|-------------|
| `generate_daily_briefings` | DBE | 24 hours | Daily briefings for all active users |
| `update_learning_profiles` | GLOE | 6 hours | Recalculate responsiveness profiles |
| `refresh_guidance` | PGE | 6 hours | Refresh guidance + expire old items |

### Files

| File | Purpose |
|------|---------|
| `scheduler_models.py` | ScheduledIntelligenceTask model (per-task state tracking) |
| `scheduler_registry.py` | Task registry: name → function path + interval |
| `scheduler_engine.py` | Core scheduler: check due tasks, execute, update state |
| `scheduler_runner.py` | Task functions wrapping existing engine APIs |
| `admin.py` | Read-only admin (allow toggling is_active) |

Command: `apps/core/management/commands/run_intelligence_scheduler.py`

### Auto-Seeding

On first run, ISE auto-creates `ScheduledIntelligenceTask` records for all registered tasks. No manual setup required.

### Cross-Engine Dependencies

| From | To | Mechanism |
|------|----|-----------|
| ISE → DBE | Schedule daily briefings | `scheduler_runner.run_daily_briefings()` |
| ISE → GLOE | Schedule profile updates | `scheduler_runner.run_learning_profile_updates()` |
| ISE → PGE | Schedule guidance refresh | `scheduler_runner.run_guidance_refresh()` |
| ISE → WIRE | Schedule weekly reports | `scheduler_runner.run_weekly_reports()` |

### Safety Requirements

- ISE never generates intelligence directly — only calls existing engine APIs
- Each task failure is isolated (never crashes the cycle)
- Failed tasks still advance `next_run_at` to prevent infinite retry loops
- All engine imports are guarded against ImportError
- Errors are logged with full context

### Tests

32 tests in `apps/core/ai_scheduler/tests.py`

---

## Engine 12: WIRE — Weekly Intelligence Report Engine

**Phase:** 3 — Post-Execution
**Location:** `apps/core/ai_weekly_report/`
**Purpose:** Generate weekly longitudinal intelligence summaries aggregating SAE, PIE, PRIE, PGE, and GLOE data.

### Architecture

WIRE produces one report per user per week (Monday-Sunday). It reads from all Phase 3 engines but never executes actions.

**Pipeline:** Gather → Compute Deltas → Select → Rank → Summarize → Store

| Component | File | Responsibility |
|-----------|------|----------------|
| Engine | `report_engine.py` | Main pipeline: gather data, orchestrate processing, generate summary |
| Selector | `report_selector.py` | Priority-based item selection (critical predictions → insights → state changes → guidance) |
| Ranker | `report_ranker.py` | Score items by priority, confidence, and type bonus |
| Logger | `report_logger.py` | Store reports with deduplication and race-condition safety |
| Model | `models.py` | `WeeklyIntelligenceReport` — unique per (user, week_start_date) |

### Data Sources

| Source Engine | Data Gathered | Method |
|---------------|---------------|--------|
| SAE | Current user state + deltas | `get_user_state()` |
| PIE | Week's insights (severity, confidence) | Query `Insight` model |
| PRIE | Week's predictions (confidence, status) | Query `Prediction` model |
| PGE | Week's guidance (acknowledged, acted, dismissed) | Query `GuidanceItem` model |
| GLOE | Learning profile snapshot | Query `GuidanceLearningProfile` model |

### Selection Priority

1. Critical predictions (confidence ≥ 0.8) — priority 1
2. Critical insights — priority 2
3. Warning insights — priority 3
4. Significant state changes — priority 3
5. Guidance acted items — priority 4
6. Remaining predictions/insights — priority 5

Maximum 10 items per report.

### Ranking Score

- Priority: `(6 - priority) × 10` → 10–50 points
- Confidence: `confidence × 8` → 0–8 points
- Type bonus: prediction=5, insight=3, state_change=2, guidance=1

### Summary Generation

Template-based (no AI call). Groups items by type and includes learning engagement assessment:
- High responsiveness (≥ 0.7): "highly engaged" message
- Low responsiveness (≤ 0.3): "review guidance" suggestion

### Scheduling

ISE runs WIRE every 7 days (604800 seconds). Registry entry: `generate_weekly_reports`.

### UI

- **Dashboard tile:** `templates/dashboard/tiles/weekly_report.html` — shows latest summary with date range
- **History page:** `/intelligence/weekly/` — paginated list of past reports
- **Detail page:** `/intelligence/weekly/<pk>/` — full report with learning engagement stats

### Tests

54 tests in `apps/core/ai_weekly_report/tests.py`

---

## Engine 13: E3 — Evidence & Explainability Engine

**Phase:** 3 — Post-Execution (enrichment layer)
**Location:** `apps/core/ai_explain/`
**Purpose:** Attach evidence and human-readable explanations to all intelligence outputs so WLJ can answer "Why are you saying this?", "What data is that based on?", "How sure are you, and why?"

### Architecture

E3 does NOT generate new intelligence — it enriches existing outputs from PGE, DBE, and WIRE with explanations and evidence chains. E3 failures must never block core intelligence generation.

**Pipeline:** Source object stored → E3 hook (non-blocking) → Build evidence → Generate explanation → Store ExplainRecord

| Component | File | Responsibility |
|-----------|------|----------------|
| Engine | `explain_engine.py` | Entry point: `ensure_explain_record()`, handler dispatch, dedup |
| Evidence Builder | `evidence_builder.py` | Build evidence lists for guidance, briefings, weekly reports |
| Templates | `explain_templates.py` | Template-based explanation generators (no AI call) |
| Logger | `explain_logger.py` | Store records with dedup + IntegrityError safety |
| Model | `models.py` | `ExplainRecord` — links to source object via engine + type + ID |

### ExplainRecord Model

| Field | Type | Purpose |
|-------|------|---------|
| `user` | FK(User) | Owner |
| `source_engine` | CharField(10) | PIE, PRIE, PGE, DBE, or WIRE |
| `source_object_type` | CharField(100) | Model name (e.g., GuidanceItem) |
| `source_object_id` | IntegerField | PK of source object |
| `title` | CharField(255) | Short title |
| `explanation` | TextField | Human-readable explanation |
| `confidence_explanation` | TextField (nullable) | Why the confidence score is what it is |
| `evidence` | JSONField | List of evidence objects |
| `created_at` | DateTimeField | Auto-set |

**Indexes:** `(user, source_engine)`, `(user, source_object_type, source_object_id)`

### Evidence Format

```json
[
  {"type": "state", "id": null, "date": "2026-02-15", "summary": "Weight trend: decreasing", "url": null},
  {"type": "insight", "id": 42, "date": "2026-02-14", "summary": "3-day workout streak", "url": "/insights/42/"},
  {"type": "prediction", "id": 7, "date": "2026-02-13", "summary": "Weight projected: 195 lbs in 30d", "url": null}
]
```

### Pipeline Hooks (Non-Blocking)

| Engine | Hook Location | Trigger |
|--------|---------------|---------|
| PGE | `guidance_logger.py:log_guidance()` | After `_upsert_guidance` creates/updates item |
| DBE | `briefing_engine.py:generate_daily_briefing()` | After `store_briefing()` returns briefing |
| WIRE | `report_engine.py:generate_weekly_report()` | After `store_weekly_report()` returns report |

All hooks use: `try: ensure_explain_record(user, engine, obj) except Exception: pass`

### Handler Mapping

```python
_HANDLERS = {
    "GuidanceItem": {"engine": "PGE", "explain_fn": explain_guidance, "evidence_fn": build_evidence_for_guidance},
    "DailyBriefing": {"engine": "DBE", "explain_fn": explain_briefing, "evidence_fn": build_evidence_for_briefing},
    "WeeklyIntelligenceReport": {"engine": "WIRE", "explain_fn": explain_weekly_report, "evidence_fn": build_evidence_for_weekly_report},
}
```

### On-Demand Creation

The `ExplainDetailView` creates records on-demand if they don't exist. When a user clicks "Why?" and no record exists, the view loads the source object and creates the record in real-time.

### UI

- **Detail page:** `/intelligence/explain/<engine>/<type>/<id>/` — shows explanation, confidence, evidence list
- **"Why?" links:** Added to guidance inbox, daily briefing tile, weekly report detail

### Tests

37 tests in `apps/core/ai_explain/tests.py`

---

## Engine 14: DNE — Delivery & Notification Engine

**Phase:** 3 — Post-Execution (delivery layer)
**Location:** `apps/core/ai_delivery/`
**Purpose:** Deliver intelligence outputs (PGE guidance, DBE briefings, WIRE weekly reports) through user-configurable channels with deduplication, throttling, and quiet hours.

### Architecture

DNE does NOT generate intelligence. It scans for undelivered PGE/DBE/WIRE items and routes them through enabled channels, respecting user preferences.

**Pipeline:** Scan sources → Build payload → Apply policies (dedupe, quiet hours, throttle) → Route to channels → Log delivery

| Component | File | Responsibility |
|-----------|------|----------------|
| Engine | `delivery_engine.py` | Main cycle: `deliver_due_notifications()`, user iteration, item gathering |
| Policies | `delivery_policies.py` | Dedupe (SHA-256), quiet hours, hourly/daily throttle |
| Router | `delivery_router.py` | Channel implementations: in_app, email, SMS |
| Logger | `delivery_logger.py` | Log skipped deliveries with reason |
| Model | `models.py` | `DeliveredNotification` — tracks every delivery attempt |

### Delivery Channels

| Channel | Default | Implementation |
|---------|---------|----------------|
| In-app | **On** | Creates `Notification` via existing `NotificationService` (bell + dropdown) |
| Email | Off | Uses Django `send_mail()` with existing email infrastructure |
| SMS | Off | Uses existing `SMSNotificationService` (requires verified phone) |

### Delivery Policies

1. **Deduplication:** SHA-256 hash on (user, channel, engine, object type, object ID). Each item delivered at most once per channel.
2. **Quiet hours:** Email/SMS blocked during user's configured quiet hours. In-app always allowed.
3. **Throttle:** Configurable max per hour (default: 2) and max per day (default: 6).
4. **Skip logging:** Every skipped delivery recorded with `skip_reason` for audit.

### User Preferences

Added to `UserPreferences`:
- `intelligence_inapp_enabled` (default: True)
- `intelligence_email_enabled` (default: False)
- `intelligence_sms_enabled` (default: False)
- `intelligence_max_per_day` (default: 6)
- `intelligence_max_per_hour` (default: 2)

### Scheduling

ISE runs DNE every 10 minutes (600 seconds). Registry entry: `deliver_intelligence_notifications`.

### UI

- **Settings page:** `/intelligence/delivery/settings/` — toggle channels, set rate limits
- **History page:** `/intelligence/delivery/history/` — audit log of all delivery attempts

### Tests

29 tests in `apps/core/ai_delivery/tests.py`

---

## Adding New Intelligence

### New Insight Rule
1. Create class inheriting `BaseInsightRule`
2. Decorate with `@register`
3. Import in `run_daily_insights.py`
4. Add tests

### New Prediction Rule
1. Create class inheriting `BasePredictionRule`
2. Decorate with `@register_prediction`
3. Import in `run_prediction_engine.py`
4. Add tests

### New Guidance Rule
1. Create class inheriting `BaseGuidanceRule`
2. Decorate with `@register_guidance`
3. Implement `evaluate(user, state, insights, predictions) -> list[dict]`
4. Each returned dict must include `dedupe_key`
5. Add tests

### New Engine
1. Create module under `apps/core/`
2. Define public API in `__init__.py`
3. Wire into UAIO orchestrator pipeline
4. Update this document
5. Update CLAUDE.md boot sequence

---

*Last updated: 2026-02-15 — Twelve-engine cognitive stack (added GLOE + DBE + ISE + WIRE)*
