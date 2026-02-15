# Whole Life Journey — Intelligence Architecture

**Purpose:** Permanent architectural authority defining the five-engine cognitive stack that powers all AI-driven features in WLJ. Claude Code must read this document before implementing any feature that touches AI, data logging, insights, predictions, or user interactions.

**Status:** Active — All engines implemented and deployed.

---

## Architecture Diagram

```
                          ┌──────────────────────┐
                          │     User Input        │
                          └──────────┬───────────┘
                                     │
                          ┌──────────▼───────────┐
                          │        UAIO          │
                          │  Unified AI          │
                          │  Orchestrator        │
                          │                      │
                          │  apps/core/          │
                          │  ai_orchestrator/    │
                          └──┬──────────────┬────┘
                             │              │
                    ┌────────▼──┐     ┌─────▼────────┐
                    │   SLCME   │     │    HTIE      │
                    │  Memory   │     │   Time       │
                    │ Resolution│     │ Resolution   │
                    │           │     │              │
                    │ apps/core/│     │ apps/core/   │
                    │ ai_memory/│     │ time/        │
                    └────────┬──┘     └─────┬────────┘
                             │              │
                          ┌──▼──────────────▼────┐
                          │  Module Execution    │
                          │  (Action Handlers)   │
                          │                      │
                          │  apps/ai/            │
                          │  action_handlers.py  │
                          └──────────┬───────────┘
                                     │
                          ┌──────────▼───────────┐
                          │        PIE           │
                          │  Proactive Insight   │
                          │  Engine              │
                          │                      │
                          │  apps/core/          │
                          │  ai_insights/        │
                          └──────────┬───────────┘
                                     │
                          ┌──────────▼───────────┐
                          │       PRIE           │
                          │  Predictive          │
                          │  Intelligence Engine │
                          │                      │
                          │  apps/core/          │
                          │  ai_predictions/     │
                          └──────────┬───────────┘
                                     │
                          ┌──────────▼───────────┐
                          │     Response         │
                          └──────────────────────┘
```

---

## Execution Pipeline

All AI execution follows this pipeline. It must never be bypassed.

```
User Input
  → UAIO (process_user_input)
    → SLCME (resolve_context — memory/learned mappings)
    → HTIE (interpret_human_time — temporal resolution)
    → Clarification check (ask user if ambiguous)
  → Intent Recognition (OpenAI function calling)
  → UAIO (enrich_and_execute)
    → Safety Engine (validate timestamps, bounds)
    → Action Router (enrich with time/context)
    → Module Execution (action_handlers.py)
    → Learning Pipeline (store mappings from successful actions)
    → PIE (run_insights — generate factual insights)
      → PRIE (generate_predictions — trajectory projections)
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
| `execution_engine.py` | Delegates to existing `intent_service.execute_intent()` |
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

### Registered Rules (13 rules, 7 domains)

| File | Rules |
|------|-------|
| `rules_health.py` | WeightTrendUp, WeightTrendDown, MissingWeightLogging |
| `rules_body_composition.py` | MissingBodyComp, BodyFatChange |
| `rules_labs_vitals.py` | RepeatedOutOfRange |
| `rules_goals.py` | GoalDeadlineRisk, GoalStagnation |
| `rules_habits.py` | HabitBrokenStreak, HabitConsistencyPositive |
| `rules_scripture.py` | ScriptureReadingDropOff |
| `rules_journal.py` | JournalStreakPositive, JournalDropOff |

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

- UAIO fires `_fire_insight_event()` after every successful action execution
- PIE calls `_trigger_predictions()` after insight generation (→ PRIE)
- Scheduler runs daily for all active users
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

### Registered Prediction Rules (6 rules, 4 modules)

| Rule | Module | Prediction |
|------|--------|-----------|
| `WeightProjectionRule` | health | Weight at 30/60/90 days |
| `BodyFatProjectionRule` | health | Body fat % at 30/60/90 days |
| `LeanMassProjectionRule` | health | Lean mass at 30/60/90 days |
| `GoalCompletionDateRule` | goals | Completion date from milestone velocity |
| `HabitContinuationRule` | habits | Continuation probability (0–1) |
| `LabMarkerTrendRule` | labs | Marker trend direction + out-of-range warnings |

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

### Integration Rules

- PIE's `run_insights()` calls `_trigger_predictions()` after insight processing
- Predictions also generated via daily scheduler
- Failures in PRIE never break the insight pipeline (wrapped in try/except)

### Tests

32 tests in `apps/core/ai_predictions/tests.py`

---

## Cross-Engine Integration Map

| From | To | Mechanism | Location |
|------|----|-----------|----------|
| UAIO → SLCME | Context resolution | `context_pipeline.py` |
| UAIO → HTIE | Time resolution | `time_pipeline.py` |
| UAIO → Safety | Timestamp validation | `safety_engine.py` |
| UAIO → Actions | Enriched execution | `execution_engine.py` |
| UAIO → Learning | Store mappings | `learning_pipeline.py` |
| UAIO → PIE | Fire insight event | `orchestrator.py:_fire_insight_event()` |
| PIE → PRIE | Trigger predictions | `insight_engine.py:_trigger_predictions()` |
| Action Handlers → HTIE | Use resolved time | `action_handlers.py:_get_recorded_at()` |

---

## Database Migrations

| Migration | Engine | Models |
|-----------|--------|--------|
| `core.0053` | SLCME | LearnedMapping, ContextSnapshot, ClarificationLog |
| `core.0054` | PIE | Insight |
| `core.0055` | PRIE | Prediction |

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

### New Engine
1. Create module under `apps/core/`
2. Define public API in `__init__.py`
3. Wire into UAIO orchestrator pipeline
4. Update this document
5. Update CLAUDE.md boot sequence

---

*Last updated: 2026-02-15*
