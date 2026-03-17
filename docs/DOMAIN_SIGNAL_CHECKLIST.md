# Domain Signal Checklist

**Purpose:** Step-by-step guide for adding PIE/PRIE/PGE signal coverage to a new domain module.

**Reference implementation:** Tasks domain (2026-03-17)
- PIE: `apps/core/ai_insights/rules_tasks.py`
- PRIE: `apps/core/ai_predictions/prediction_rules_tasks.py`

---

## Steps

### 1. Create PIE insight rules

**File:** `apps/core/ai_insights/rules_<domain>.py`

```python
from apps.core.ai_insights.base_rules import BaseInsightRule
from apps.core.ai_insights.rule_registry import register

@register
class MyDomainRule(BaseInsightRule):
    rule_name = "my_domain_pattern"
    module = "<module_slug>"          # e.g., "life", "health", "faith"
    insight_type = "my_domain_pattern"
    severity = "warning"              # info, warning, critical

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def evaluate(self, user, event):
        # Query domain data, return list of insight dicts or []
        # MUST include entity IDs in evidence for tracing
        return [{
            "insight_type": self.insight_type,
            "module": self.module,
            "severity": self.severity,
            "title": "...",
            "message": "...",
            "evidence": {
                "rule_name": self.rule_name,
                "entity_id": 42,        # <-- REQUIRED for entity tracing
                "entity_title": "...",
            },
            "dedupe_key": build_dedupe_key(user.id, self.insight_type, ...),
        }]
```

**Key requirements:**
- Use `@register` decorator (auto-registers with PIE)
- Inherit `BaseInsightRule`
- `applies()` + `evaluate()` methods
- Include entity IDs in `evidence` dict
- Use `build_dedupe_key()` with date window to prevent duplicates

### 2. Create PRIE prediction rules

**File:** `apps/core/ai_predictions/prediction_rules_<domain>.py`

```python
from apps.core.ai_predictions.base_prediction_rule import BasePredictionRule
from apps.core.ai_predictions.prediction_registry import register_prediction

@register_prediction
class MyDomainPredictionRule(BasePredictionRule):
    rule_name = "my_domain_risk"
    module = "<module_slug>"
    prediction_type = "my_domain_risk"
    min_confidence_to_store = 0.25

    def applies(self, user, event):
        return event.get("event_type") == "scheduled_check"

    def predict(self, user, event):
        # Return list of prediction dicts or []
        return [{
            "prediction_type": self.prediction_type,
            "module": self.module,
            "predicted_value": 0.75,           # probability or numeric value
            "predicted_date": target_date,
            "confidence_score": 0.65,
            "explanation": "Human-readable explanation",
            "evidence": {
                "rule_name": self.rule_name,
                "entity_id": 42,               # <-- entity tracing
            },
            "dedupe_key": build_prediction_dedupe_key(...),
        }]
```

### 3. Create PGE guidance rules (ONLY after PIE/PRIE generate data)

**File:** `apps/core/ai_guidance/guidance_rules_<domain>.py`

PGE rules consume insights + predictions as inputs. Don't create until PIE/PRIE rules are generating data.

### 4. Register imports in all loading paths

Add import lines to these files:

| File | Import |
|------|--------|
| `apps/core/ai_orchestrator/intelligence_hook.py` | `import apps.core.ai_insights.rules_<domain>` |
| `apps/core/ai_orchestrator/execution_engine.py` | `import apps.core.ai_insights.rules_<domain>` |
| `apps/core/ai_insights/management/commands/run_daily_insights.py` | `import apps.core.ai_insights.rules_<domain>` |
| `apps/core/ai_predictions/management/commands/run_prediction_engine.py` | `import apps.core.ai_predictions.prediction_rules_<domain>` |

### 5. Verify CoS context includes your module

In `apps/core/ai_orchestrator/cos_context.py`, the `_build_intelligence_signals()` function queries all Insights/Predictions and filters by `_enabled_modules`. Your module slug must be in the module catalog (`apps/users/fixtures/module_definitions.json`) with `cos_participation=True` (default).

### 6. Add tests

```bash
python3 manage.py test apps.core.ai_insights.tests apps.core.ai_predictions.tests -v 1 --failfast
```

Test pattern: create user state → run `scheduled_check` event → verify insight/prediction created with correct entity IDs in evidence.

### 7. Update documentation

- `docs/DOMAIN_INTELLIGENCE_ARCHITECTURE.md` — add domain section + update summary table
- `docs/ENGINE_COS_REFERENCE.md` — add rule files to Key File Paths

---

## Trigger Strategy

**Start with scheduled triggers.** The ISE `run_pie_synthetic()` job fires `event_type="scheduled_check"` for all users on a regular cadence. Rules that check this event type get evaluated automatically with zero additional wiring.

**Add event-driven triggers later** once scheduled rules are proven:
- Wire `fire_intelligence(user, "<module>", record_id, action)` in model save/complete methods
- Add `event_type` checks for real-time events in `applies()`
- Dedupe keys prevent duplicate insights when both scheduled and event triggers fire

---

## Domain Coverage Inventory (2026-03-17)

| Domain | PIE | PRIE | PGE | Notes |
|--------|-----|------|-----|-------|
| Health | 15 | 4 | 2 | Comprehensive |
| Purpose | 7 | 2 | 2 | Goals + Habits |
| Journal | 3 | 0 | 1 | Missing PRIE |
| Tasks | 3 | 1 | 0 | Scheduled-only triggers |
| Meals | 3 | 2 | 3 | Comprehensive |
| Faith | 2 | 0 | 0 | Missing PRIE + PGE |
| Medical | 1 | 1 | 0 | Labs only |
| Finance | 0 | 0 | 0 | No signal coverage |
| Brain Training | 0 | 0 | 0 | No signal coverage |

---

*Created: 2026-03-17*
