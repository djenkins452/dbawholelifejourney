# Whole Life Journey — Engine Integration Guide

**Purpose:** Step-by-step guide for integrating new features with the six cognitive engines. Includes code examples, prohibited patterns, and checklists.

**Prerequisite:** Read `docs/INTELLIGENCE_ARCHITECTURE.md` and `docs/DOMAIN_INTELLIGENCE_ARCHITECTURE.md` first.

---

## When Integration is Required

| Change Type | UAIO | SLCME | HTIE | SAE | PIE | PRIE |
|-------------|------|-------|------|-----|-----|------|
| New AI assistant action | **YES** | **YES** | If time-aware | **YES** | Consider | Consider |
| New data logging feature | — | — | — | **YES** | **YES** | Consider |
| New page/view | — | Consider | — | — | — | — |
| New model with trends | — | — | — | **YES** | **YES** | **YES** |
| Bug fix / CSS tweak | — | — | — | — | — | — |

---

## Integration 1: Adding an AI Assistant Action

### Step 1 — Register the Intent

**File:** `apps/core/ai_orchestrator/intent_engine.py`

Add your intent to the appropriate set:

```python
# If the action involves dates/times:
TIME_AWARE_INTENTS = {
    "update_weight", "log_sleep", ...,
    "your_new_intent",  # ← Add here
}

# If the action references a specific record:
CONTEXT_AWARE_INTENTS = {
    "save_verse", "complete_task", ...,
    "your_new_intent",  # ← Add here
}
```

### Step 2 — Add the Action Handler

**File:** `apps/ai/action_handlers.py`

```python
def handle_your_new_intent(self, **kwargs):
    """Handle the new intent."""
    # Use HTIE-resolved time (never parse time yourself)
    recorded_at = self._get_recorded_at(kwargs)

    # Use the resolved context if available
    record_id = kwargs.get("record_id")

    # Execute domain logic
    result = YourModel.objects.create(
        user=self.user,
        value=kwargs.get("value"),
        recorded_at=recorded_at,  # ← From HTIE via orchestrator
    )

    return {"success": True, "message": f"Logged successfully for {recorded_at.strftime('%b %d')}"}
```

### Step 3 — Add SLCME Context Type

**File:** `apps/core/ai_orchestrator/context_pipeline.py`

```python
MODULE_TO_CONTEXT_TYPE = {
    "faith": "scripture_page",
    "health": "health_entry",
    ...,
    "your_module": "your_context_type",  # ← Add here
}
```

### Step 4 — Add OpenAI Function Definition

**File:** `apps/ai/personal_assistant.py` (function definitions section)

Add the function definition so OpenAI can recognize the intent.

---

## Integration 2: Adding a PIE Insight Rule

### Step 1 — Create the Rule File

**File:** `apps/core/ai_insights/rules_yourmodule.py`

```python
"""
PIE — Your Module insight rules.
"""
from django.utils import timezone

from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.models import build_dedupe_key
from apps.core.ai_insights.pattern_utils import get_time_window
from apps.core.ai_insights.rule_registry import register


@register
class YourPatternRule(BaseInsightRule):
    """Detect a specific pattern in user data."""

    rule_name = "your_pattern"
    module = "your_module"
    insight_type = "your_pattern"
    min_confidence_to_store = 0.6
    min_confidence_to_notify = 0.8

    def applies(self, user, event):
        """Only run for relevant events."""
        module = event.get("module", "")
        return module in ("all", "your_module")

    def evaluate(self, user, event):
        """Analyze data and return insights."""
        from apps.yourmodule.models import YourModel

        window_start, window_end = get_time_window(days=14)

        entries = YourModel.objects.filter(
            user=user,
            created_at__gte=window_start,
            created_at__lte=window_end,
        )

        if entries.count() < 3:
            return []  # Not enough data

        # Analyze the data
        # ...

        dedupe_key = build_dedupe_key(
            user.id, self.insight_type,
            window_start.isoformat(), window_end.isoformat(),
        )

        return [{
            "severity": "warning",
            "title": "Pattern detected in your data",
            "message": "Detailed explanation of what was found.",
            "confidence_score": 0.85,
            "explain_why": "This was generated because X happened Y times in Z days.",
            "evidence": {
                "rule": self.rule_name,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "data_points": entries.count(),
            },
            "dedupe_key": dedupe_key,
        }]
```

### Step 2 — Register in Scheduler

**File:** `apps/core/ai_insights/management/commands/run_daily_insights.py`

```python
import apps.core.ai_insights.rules_yourmodule  # noqa: F401
```

### Step 3 — Add Tests

Test `applies()` returns True/False for correct events, `evaluate()` returns insights with all required fields, and dedupe works correctly.

---

## Integration 3: Adding a PRIE Prediction Rule

### Step 1 — Create the Rule File

**File:** `apps/core/ai_predictions/prediction_rules_yourmodule.py`

```python
"""
PRIE — Your Module prediction rules.
"""
from django.utils import timezone

from apps.core.ai_predictions.base_prediction_rule import BasePredictionRule
from apps.core.ai_predictions.confidence_engine import confidence_label
from apps.core.ai_predictions.models import build_prediction_dedupe_key
from apps.core.ai_predictions.prediction_registry import register_prediction
from apps.core.ai_predictions.trajectory_engine import calculate_linear_projection


@register_prediction
class YourProjectionRule(BasePredictionRule):
    """Project future values based on historical data."""

    rule_name = "your_projection"
    module = "your_module"
    prediction_type = "your_projection"
    min_confidence_to_store = 0.25

    HORIZONS = [30, 60, 90]
    LOOKBACK_DAYS = 90

    def applies(self, user, event):
        module = event.get("module", "")
        return module in ("all", "your_module")

    def predict(self, user, event):
        from apps.yourmodule.models import YourModel

        cutoff = timezone.now() - timezone.timedelta(days=self.LOOKBACK_DAYS)
        entries = (
            YourModel.objects.filter(user=user, created_at__gte=cutoff)
            .order_by("created_at")
            .values_list("created_at", "value")
        )

        data_points = [(dt, float(val)) for dt, val in entries]
        if len(data_points) < 3:
            return []

        predictions = []
        for days in self.HORIZONS:
            result = calculate_linear_projection(data_points, days, unit_label="units")
            if result is None:
                continue

            pred_type = f"your_metric_{days}d"
            date_str = result.predicted_date.strftime("%Y-%m-%d")
            dedupe_key = build_prediction_dedupe_key(user.id, pred_type, date_str)

            predictions.append({
                "prediction_type": pred_type,
                "module": "your_module",
                "predicted_value": result.predicted_value,
                "predicted_date": result.predicted_date,
                "confidence_score": result.confidence_score,
                "explanation": f"Based on {result.data_point_count} entries, "
                               f"projected value in {days} days: {result.predicted_value:.1f}",
                "evidence": {
                    "rule": self.rule_name,
                    "data_points": result.data_point_count,
                    "slope_per_day": round(result.slope, 4),
                    "r_squared": round(result.r_squared, 4),
                },
                "dedupe_key": dedupe_key,
            })

        return predictions
```

### Step 2 — Register in Scheduler

**File:** `apps/core/ai_predictions/management/commands/run_prediction_engine.py`

```python
import apps.core.ai_predictions.prediction_rules_yourmodule  # noqa: F401
```

### Step 3 — Add Tests

Test with sufficient data (≥3 points), insufficient data (returns []), correct horizons generated, and confidence scoring.

---

## Integration 4: Adding a SAE State Builder

When a new domain stores user data that should be part of the state snapshot, add a state builder.

### Step 1 — Create the Builder Function

**File:** `apps/core/ai_state/state_builder.py`

```python
def build_yourmodule_state(user):
    """Build state for your module from actual database records."""
    from apps.yourmodule.models import YourModel
    from apps.core.time.system_clock import get_current_time

    now = get_current_time()
    state = {}

    latest = YourModel.objects.filter(user=user).order_by("-created_at").first()
    if latest:
        state["latest_value"] = float(latest.value)
        state["last_entry"] = latest.created_at.isoformat()

    return state
```

### Step 2 — Register in MODULE_BUILDERS

**File:** `apps/core/ai_state/state_builder.py`

```python
MODULE_BUILDERS = {
    "health": build_health_state,
    "goals": build_goal_state,
    # ...
    "yourmodule": build_yourmodule_state,  # ← Add here
}
```

### Step 3 — Call SAE After Non-AI Data Changes

For data created outside the AI assistant (form submissions, API imports):

```python
from apps.core.ai_state import update_user_state
update_user_state(user, "yourmodule", record_id=entry.id)
```

AI-initiated actions update SAE automatically via the UAIO intelligence chain.

### Step 4 — Read State Instead of Querying

```python
from apps.core.ai_state import get_module_state

# Instead of: YourModel.objects.filter(user=user).last()
state = get_module_state(user, "yourmodule")
latest_value = state.get("latest_value")
```

---

## Integration 5: Firing Events from Views/Signals

When data is created/updated outside the AI assistant (e.g., form submissions), update SAE and fire PIE events:

```python
from apps.core.ai_state import update_user_state
from apps.core.ai_insights.insight_engine import run_insights
from apps.core.time.system_clock import get_current_time

# After saving a record — update state first, then fire insights
update_user_state(user, "health", record_id=weight_entry.id)

run_insights(user, {
    "event_type": "record_created",
    "module": "health",
    "action": "update_weight",
    "record_id": weight_entry.id,
    "timestamp_utc": get_current_time().isoformat(),
})
# This also triggers PRIE predictions automatically
```

---

## Prohibited Patterns

### 1. Direct Time Parsing on User Input

```python
# WRONG — bypasses HTIE
from datetime import datetime
dt = datetime.strptime(user_input, "%Y-%m-%d")

# CORRECT — use HTIE
from apps.core.time import interpret_human_time
result = interpret_human_time(user_input, user_timezone=user_tz)
if result.success:
    dt = result.resolved_time.datetime_aware
```

### 2. Hardcoded Context Resolution

```python
# WRONG — bypasses SLCME
if "my weight" in user_input:
    intent = "update_weight"

# CORRECT — use SLCME through UAIO
from apps.core.ai_orchestrator.orchestrator import process_user_input
result = process_user_input(user, user_input, page_context=context)
```

### 3. Untracked Pattern Detection

```python
# WRONG — insight logic outside PIE
if weight_entries.count() > 5:
    trend = compute_trend(weight_entries)
    send_notification(user, f"Your weight is {trend}")

# CORRECT — create a PIE rule
@register
class WeightTrendRule(BaseInsightRule):
    rule_name = "weight_trend"
    # ... proper rule implementation
```

### 4. Untracked Predictions

```python
# WRONG — prediction logic outside PRIE
projected = current_weight + (slope * 30)
show_user(f"In 30 days: {projected}")

# CORRECT — create a PRIE rule
@register_prediction
class WeightProjectionRule(BasePredictionRule):
    rule_name = "weight_projection"
    # ... proper rule implementation
```

### 5. Silent Failures

```python
# WRONG — swallowing errors silently
try:
    run_insights(user, event)
except:
    pass

# CORRECT — log the error
try:
    run_insights(user, event)
except Exception as e:
    logger.error(f"Insight generation failed: {e}", exc_info=True)
```

### 6. Missing Confidence Scores

```python
# WRONG — insight without confidence
return [{"title": "Weight up", "message": "...", "dedupe_key": "..."}]

# CORRECT — always include confidence + explain_why + evidence
return [{
    "title": "Weight up",
    "message": "...",
    "confidence_score": 0.85,
    "explain_why": "3 entries show +5lb over 14 days",
    "evidence": {"entries": 3, "change": 5.0},
    "dedupe_key": "...",
}]
```

### 7. Missing Dedupe Keys

```python
# WRONG — insight without dedupe_key (will be silently dropped)
return [{"title": "...", "confidence_score": 0.8}]

# CORRECT — always include dedupe_key
from apps.core.ai_insights.models import build_dedupe_key
key = build_dedupe_key(user.id, "my_rule", start_iso, end_iso)
return [{"title": "...", "confidence_score": 0.8, "dedupe_key": key}]
```

### 8. Bypassing SAE for Current State

```python
# WRONG — reconstructing user state by querying all models
weight = WeightEntry.objects.filter(user=user).order_by("-recorded_at").first()
goals = LifeGoal.objects.filter(user=user, status="active").count()
habits = HabitGoal.objects.filter(user=user, status="active").count()
# ... building state manually

# CORRECT — read from SAE
from apps.core.ai_state import get_user_state
state = get_user_state(user)
weight = state.get("health", {}).get("weight_current")
goals = state.get("goals", {}).get("active_goal_count")
habits = state.get("habits", {}).get("active_habit_count")
```

### 9. Forgetting SAE Update After Non-AI Data Changes

```python
# WRONG — saving data without updating SAE
weight_entry = WeightEntry.objects.create(user=user, value=180.0)
# State is now stale!

# CORRECT — update SAE after saving
weight_entry = WeightEntry.objects.create(user=user, value=180.0)
from apps.core.ai_state import update_user_state
update_user_state(user, "health", record_id=weight_entry.id)
```

---

## New Feature Integration Checklist

Before marking a feature complete, verify:

- [ ] **Time-aware actions** use `_get_recorded_at(kwargs)` not `timezone.now()`
- [ ] **Context-aware actions** are in `CONTEXT_AWARE_INTENTS` set
- [ ] **Time-aware intents** are in `TIME_AWARE_INTENTS` set
- [ ] **SAE state builder** exists for new domain (registered in `MODULE_BUILDERS`)
- [ ] **SAE update** called after non-AI data changes (`update_user_state()`)
- [ ] **PIE rules** created for detectable patterns (if data model has trends)
- [ ] **PRIE rules** created for projectable metrics (if numeric over time)
- [ ] **Rule imports** added to management commands (`run_daily_insights.py`, `run_prediction_engine.py`)
- [ ] **SLCME context type** mapped in `MODULE_TO_CONTEXT_TYPE` (if new module)
- [ ] **Tests** cover applies/evaluate/predict with sufficient and insufficient data
- [ ] **Docs updated** — `DOMAIN_INTELLIGENCE_ARCHITECTURE.md` and `INTELLIGENCE_ARCHITECTURE.md`
- [ ] **All insights** have `confidence_score`, `explain_why`, `evidence`, `dedupe_key`
- [ ] **All predictions** have `confidence_score`, `explanation`, `evidence`, `dedupe_key`
- [ ] **No prohibited patterns** in new code (including SAE bypass)

---

*Last updated: 2026-02-15 — SAE integration requirements added*
