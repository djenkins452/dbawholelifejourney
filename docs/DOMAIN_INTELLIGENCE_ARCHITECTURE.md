# Whole Life Journey — Domain Intelligence Architecture

**Purpose:** Maps how each application domain (Health, Body Composition, Labs, Goals, Habits, Journal, Scripture) integrates with the six cognitive engines. Domain engines plug into the UAIO orchestrator and must never bypass cognitive engines.

**Prerequisite:** Read `docs/INTELLIGENCE_ARCHITECTURE.md` first for engine contracts and pipeline.

---

## Domain Integration Principle

Every domain module follows the three-phase integration pattern:

```
User Action in Domain
  → PHASE 1 — INTERPRETATION
    → SLCME resolves context ("my weight", "that goal")
    → HTIE resolves time ("yesterday", "last Tuesday")
    → SUE interprets semantics (intent, entities, ambiguity)
  → PHASE 2 — EXECUTION
    → UAIO orchestrator routes to Action Handler
    → Action Handler executes domain logic
  → PHASE 3 — POST-EXECUTION
    → SAE updates user state for this domain
    → PIE evaluates insight rules (enriched with SAE state)
    → PRIE runs prediction rules for this domain
    → PGE evaluates guidance rules (scheduled/on-demand)
  → Response with temporal context
```

**Rules:**
- Domain modules MUST NOT directly call `datetime.strptime()` on user input, hard-code context resolution, or generate insights/predictions outside the engine pipeline.
- Domain modules MUST NOT reconstruct full user state independently — use SAE via `get_user_state()` or `get_module_state()`.
- Domain modules MUST NOT violate phase boundaries — interpretation engines do not execute, execution engines do not interpret, post-execution engines do not execute.

---

## State Awareness Engine — Domain Integration

**SAE is the authoritative source of current user state for all domains.** After every successful action, SAE updates the affected module's state snapshot. Intelligence engines (PIE, PRIE) receive enriched state data instead of re-querying the database for common lookups.

### Domain → SAE State Mapping

| Domain | SAE Module Key | State Builder | Key State Fields |
|--------|----------------|---------------|------------------|
| Health (Weight) | `health` | `build_health_state()` | weight_current, weight_trend, weight_entries_90d |
| Body Composition | `health` | `build_health_state()` | body_fat_current, lean_mass_current |
| Labs & Vitals | `health` | `build_health_state()` | bp_systolic, bp_diastolic, sleep_avg_duration_7d |
| Goals | `goals` | `build_goal_state()` | active_goal_count, completion_rate, next_deadline |
| Habits | `habits` | `build_habit_state()` | active_habit_count, longest_streak, avg_completion_rate |
| Journal | `journal` | `build_journal_state()` | last_entry, entry_frequency, mood_distribution |
| Scripture | `faith` | `build_faith_state()` | reading_streak, last_scripture_read, unanswered_prayers |

### Reading State in Domain Code

```python
from apps.core.ai_state import get_user_state, get_module_state

# Full state (all domains)
state = get_user_state(user)
weight = state.get("health", {}).get("weight_current")

# Single module
health = get_module_state(user, "health")
trend = health.get("weight_trend")
```

### SAE Update Flow

SAE updates happen automatically via the UAIO intelligence chain. No manual calls are needed for AI-initiated actions. For non-AI data changes (form submissions, API imports), call:

```python
from apps.core.ai_state import update_user_state
update_user_state(user, "health", record_id=entry.id)
```

---

## Domain 1: Health (Weight)

**App:** `apps/health/`
**Key Model:** `WeightEntry` — `value`, `unit`, `recorded_at`, `body_fat_percentage`, `lean_body_mass`

### UAIO Integration

| Intent | Action Handler | Parameters |
|--------|---------------|------------|
| `update_weight` | `handle_update_weight()` | `value`, `unit`, `recorded_at` (from HTIE) |

`recorded_at` is set by `_get_recorded_at(kwargs)` which respects HTIE-resolved timestamps.

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `WeightTrendUpRule` | warning | 14-day window, ≥3 entries, +5lb net change |
| `WeightTrendDownRule` | positive | 14-day window, ≥3 entries, -5lb net change |
| `MissingWeightLoggingRule` | info | No weight entry in 14+ days |

### PRIE Predictions

| Rule | Horizons | Data Source |
|------|----------|-------------|
| `WeightProjectionRule` | 30, 60, 90 days | Last 90 days of `WeightEntry` |

Projects weight trajectory using linear regression on `(recorded_at, value)` pairs.

### SLCME Context

- Context type: `health_entry`
- Learned mappings: User phrases like "my weight" → weight logging intent

---

## Domain 2: Body Composition

**App:** `apps/health/`
**Key Model:** `BodyCompositionEntry` — `metric_name`, `value`, `unit`, `measurement_date`, `source`

### Metric Names

| `metric_name` | Unit | Description |
|---------------|------|-------------|
| `body_fat_pct` | % | Body fat percentage |
| `lean_mass` | lb | Lean body mass |
| `waist` | in | Waist circumference |
| `muscle_mass` | lb | Muscle mass |

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `MissingBodyCompRule` | info | No body comp entry in 30+ days |
| `BodyFatChangeRule` | warning/positive | ≥2% body fat change over 60 days |

### PRIE Predictions

| Rule | Horizons | Data Source |
|------|----------|-------------|
| `BodyFatProjectionRule` | 30, 60, 90 days | `BodyCompositionEntry` where `metric_name="body_fat_pct"` |
| `LeanMassProjectionRule` | 30, 60, 90 days | `BodyCompositionEntry` where `metric_name="lean_mass"` |

---

## Domain 3: Labs and Vitals

**App:** `apps/medical/`
**Key Model:** `LabResult` — `raw_test_name`, `value_numeric`, `unit`, `range_low`, `range_high`, `abnormal_flag`, `collected_at`

### Abnormal Flags

| Flag | Meaning |
|------|---------|
| `""` | Normal |
| `L` | Low |
| `H` | High |
| `LL` | Critical Low |
| `HH` | Critical High |
| `A` | Abnormal (unspecified) |

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `RepeatedOutOfRangeRule` | warning | Same marker flagged abnormal 2+ times in 30 days |

### PRIE Predictions

| Rule | Horizons | Data Source |
|------|----------|-------------|
| `LabMarkerTrendRule` | 90 days | `LabResult` grouped by `raw_test_name`, ≥2 numeric results |

Projects marker value and flags if projected value would exceed reference range.

---

## Domain 4: Goals

**App:** `apps/purpose/`
**Key Model:** `LifeGoal` — `title`, `domain`, `timeframe`, `target_date`, `status`
**Related:** `Milestone` — tracks progress steps toward goal completion

### UAIO Integration

| Intent | Action Handler | Parameters |
|--------|---------------|------------|
| `save_goal` | `handle_save_goal()` | `title`, `target_date` (from HTIE) |
| `complete_goal` | `handle_complete_goal()` | `goal_id` (from SLCME context) |

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `GoalDeadlineRiskRule` | warning | Active goal with `target_date` within 30 days, low milestone completion |
| `GoalStagnationRule` | info | Active goal with no milestone update in 14+ days |

### PRIE Predictions

| Rule | Horizons | Data Source |
|------|----------|-------------|
| `GoalCompletionDateRule` | Dynamic | Milestone completion velocity → estimated completion date |

Compares predicted completion to `target_date` and reports ahead/behind schedule.

### SLCME Context

- Context type: `goal_page`
- Learned mappings: "that goal" → specific goal ID based on page context

---

## Domain 5: Habits

**App:** `apps/purpose/`
**Key Models:**
- `HabitGoal` — `name`, `measurement_type`, `frequency_type`, `target_value`, `start_date`, `end_date`, `status`
- `HabitEntry` — `goal` (FK), `date`, `completed`, `duration_minutes`, `count_value`, `target_value`

### Measurement Types

| Type | Tracking | Fields Used |
|------|----------|-------------|
| `binary` | Yes/No daily | `completed` |
| `duration` | Timed sessions | `duration_minutes` |
| `count` | Repetitions | `count_value` |
| `target` | Numeric goal | `target_value` |

### UAIO Integration

| Intent | Action Handler | Parameters |
|--------|---------------|------------|
| `log_habit` | `handle_log_habit()` | `habit_id` (from SLCME), `date` (from HTIE), `completed` |

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `HabitBrokenStreakRule` | warning | 7+ consecutive completions then 3+ day gap |
| `HabitConsistencyPositiveRule` | positive | 10+ completions in last 14 days |

### PRIE Predictions

| Rule | Horizons | Data Source |
|------|----------|-------------|
| `HabitContinuationRule` | 30 days | 28-day completion rate + 7-day trend analysis |

Returns probability (0–1) that user will continue the habit. Factors: completion rate, recent trend direction, and total entry count.

### SLCME Context

- Context type: `habit_page`
- Learned mappings: "my reading habit" → specific habit ID

---

## Domain 6: Journal

**App:** `apps/journal/`
**Key Model:** `JournalEntry` — `title`, `content`, `mood`, `created_at`

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `JournalStreakPositiveRule` | positive | 5+ consecutive days with journal entries |
| `JournalDropOffRule` | info | Previously active journaler with 10+ day gap |

### PRIE Predictions

No prediction rules currently registered for Journal. Future candidates:
- Journaling consistency projection
- Mood trend analysis (if mood data is structured)

### SLCME Context

- Context type: `journal_page`
- Learned mappings: "my journal" → journal module intent

---

## Domain 7: Scripture / Faith

**App:** `apps/faith/`
**Key Models:** Scripture reading plans, daily readings, verse tracking

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `ScriptureReadingDropOffRule` | info | Daily reading for 7+ days then 5+ day gap |

### PRIE Predictions

No prediction rules currently registered for Scripture. Future candidates:
- Reading plan completion date projection
- Engagement consistency forecast

### SLCME Context

- Context type: `scripture_page`
- Learned mappings: "my reading plan" → specific plan, "that verse" → verse reference

---

## Domain 8: Nutrition

**App:** `apps/health/`
**Key Model:** `FoodEntry` — food_name, total_calories, total_protein_g, total_carbohydrates_g, total_fat_g, logged_date
**Key Model:** `NutritionGoals` — daily_calorie_target, daily_protein_target_g, daily_carb_target_g, daily_fat_target_g

### SAE State Builder

`build_nutrition_state(user)` → rolling 7d calorie/protein averages, macro compliance scores, food entry counts, calorie/protein targets from NutritionGoals.

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `NutritionCalorieTrendRule` | warning/positive | 7d avg calories ±20% from target |
| `ProteinDeficitRule` | warning | Protein <80% of target for 3+ days |
| `CarbGlucoseCorrelationRule` | info | High carbs + elevated glucose same day |

### PRIE Predictions

| Rule | Horizons | Data Source |
|------|----------|-------------|
| `NutritionWeightProjectionRule` | 30/60/90d | FoodEntry calories (90d) + WeightEntry (90d) |

### PGE Rules

| Rule | Sources | Guidance |
|------|---------|----------|
| `ProteinAdjustmentRule` | PIE ProteinDeficit + SAE nutrition_state | Specific protein intake recommendations |

### UAIO Integration

No direct UAIO intents — nutrition data logged via existing food entry handlers.

---

## Domain 9: Fasting

**App:** `apps/health/`
**Key Model:** `FastingWindow` — started_at, ended_at, fasting_type, target_hours

### SAE State Builder

`build_fasting_state(user)` → active fast detection, rolling 7d fasting hours, avg fast duration, compliance score, fast count.

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `FastingConsistencyRule` | info/positive | Fasting consistency drop (7d vs 30d) or high compliance |

### PRIE Predictions

No prediction rules currently registered for fasting.

### PGE Rules

| Rule | Sources | Guidance |
|------|---------|----------|
| `FastingOptimizationRule` | PIE FastingConsistency + SAE fasting_state | Fasting schedule optimization |

### UAIO Integration

No direct UAIO intents — fasting data logged via existing fast start/end handlers.

---

## Domain 10: Fitness

**App:** `apps/health/`
**Key Models:** `WorkoutSession` — name, date, duration_minutes; `ExerciseSet` — weight, reps, set_number; `PersonalRecord` — achieved_date

### SAE State Builder

`build_fitness_state(user)` → workout counts (7d/30d), total volume, avg duration, PR count, consistency score, strength trend.

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `WorkoutConsistencyRule` | warning/positive | Workout frequency drop/increase (7d vs 30d) |
| `StrengthPlateauRule` | info | No new PRs in 30+ days with consistent training |

### PRIE Predictions

| Rule | Horizons | Data Source |
|------|----------|-------------|
| `StrengthProgressionPredictionRule` | 30/60d | ExerciseSet volume (90d) |

### PGE Rules

| Rule | Sources | Guidance |
|------|---------|----------|
| `WorkoutFrequencyAdjustmentRule` | PIE WorkoutConsistency + SAE fitness_state | Workout frequency recommendations |

### UAIO Integration

No direct UAIO intents — workout data logged via existing fitness handlers.

---

## Domain 11: Transformation (Composite)

**App:** `apps/health/` (protocol model), `apps/core/ai_state/` (composite builder)
**Key Model:** `TransformationProtocol` — name, protocol_type (cut/bulk/recomp/maintenance/custom), start_date, target_end_date, goal_weight, goal_body_fat, is_active

### SAE State Builder

`build_transformation_state(user)` → reads from **SAE sub-states only** (never raw DB): transformation_score (0-100), weight_trend_score, nutrition_score, fasting_score, workout_score, recovery_score, momentum_score. Uses `UserState.objects.get()` to avoid recursion.

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `TransformationMomentumRule` | positive/warning | Composite momentum from transformation_state |

### PRIE Predictions

| Rule | Horizons | Data Source |
|------|----------|-------------|
| `TransformationSuccessProbabilityRule` | target_date | SAE transformation_state → probability (0-1) |

### PGE Rules

| Rule | Sources | Guidance |
|------|---------|----------|
| `TransformationCoachingRule` | SAE transformation_state + PRIE predictions | Overall transformation status/recommendations |

### UAIO Integration

| Intent | Action Handler | Parameters |
|--------|---------------|------------|
| `log_transformation_protocol` | `handle_log_transformation_protocol` | name, protocol_type, start_date, target_end_date, goal_weight, goal_body_fat |
| `log_shopping_item` | `handle_log_shopping_item` | name, quantity, category, list_name |
| `complete_shopping_item` | `handle_complete_shopping_item` | name, list_name |

---

## Domain 13: Tasks

**App:** `apps/life/`
**Key Model:** `Task` — title, priority (now/soon/someday), due_date, scheduled_date, completion_status, completed_at
**Service:** `apps/life/services/task_queries.py` — TaskQueries (pending, overdue, due_within, completed_since)

### PIE Rules

| Rule | Type | Trigger |
|------|------|---------|
| `TaskOverduePatternRule` | warning | 2+ overdue tasks (due_date < today, pending) |
| `TaskStallRule` | info | No completions in 5+ days with pending tasks |
| `TaskDueTodayRule` | info | Tasks due today (by due_date or scheduled_date), top 5 by priority |

**File:** `apps/core/ai_insights/rules_tasks.py`
**Trigger:** `event_type == "scheduled_check"` (batch via ISE)
**Evidence:** All rules include `task_id` and `task_title` for entity tracing.

### PRIE Predictions

| Rule | Type | Trigger |
|------|------|---------|
| `TaskOverdueRiskRule` | task_overdue_risk | Tasks with due_date in next 3 days |

**File:** `apps/core/ai_predictions/prediction_rules_tasks.py`
**Model:** Velocity-based — 14-day completion rate predicts miss probability. Adjusted by days remaining (due today = 1.5x multiplier).
**Trigger:** `event_type == "scheduled_check"` (batch via ISE)

### SAE State

No dedicated SAE state builder yet. Tasks are queried live in CoS context via `task_queries.py`.

### PGE Guidance

No guidance rules yet. Candidate: task prioritization coaching when >5 now-priority tasks.

### Known Limitations

- **Event-driven triggers:** `Task.mark_complete()` fires `fire_intelligence()` with `self.module` (e.g., "health", not "life"), so event-driven PIE/PRIE rules would miss most tasks. Current rules are scheduled-only. See Phase 2.5 in plan for fix.
- **CoS task context:** Task IDs are TEMPORARILY included in CoS authoritative task list for entity resolution. Will be removed once signal-driven insights fully replace raw task injection.

---

## Domain Integration Summary

| Domain | SAE State | PIE Rules | PRIE Rules | PGE Rules | UAIO Intents | SLCME Context |
|--------|-----------|-----------|------------|-----------|--------------|---------------|
| Health (Weight) | `health` | 3 | 1 (3 horizons) | `health_trend` | `update_weight` | `health_entry` |
| Body Composition | `health` | 2 | 2 (6 horizons) | `health_trend` | — | `health_entry` |
| Labs & Vitals | `health` | 1 | 1 | `health_trend` | — | — |
| Goals | `goals` | 2 | 1 | `goal_risk` | `save_goal`, `complete_goal` | `goal_page` |
| Habits | `habits` | 2 | 1 | `habit_inactivity` | `log_habit` | `habit_page` |
| Journal | `journal` | 2 | 0 | `journal_inactivity` | — | `journal_page` |
| Scripture | `faith` | 1 | 0 | — | `save_verse` | `scripture_page` |
| Nutrition | `nutrition` | 3 | 1 (3 horizons) | `protein_adjustment` | — | — |
| Fasting | `fasting` | 1 | 0 | `fasting_optimization` | — | — |
| Fitness | `fitness` | 2 | 1 (2 horizons) | `workout_frequency` | — | — |
| Transformation | `transformation` | 1 | 1 | `transformation_coaching` | `log_transformation_protocol` | — |
| **Tasks** | — | **3** | **1** | — | `create_task`, `complete_task`, `mutate_task` | — |
| **Behavior (cross-domain)** | `behavior` | **3** | 0 | — | — | — |
| Cross-module | — | — | — | `positive_reinforcement` | — | — |
| **Total** | **10 modules** | **26** | **10** | **9** | — | — |

---

## Adding a New Domain

When adding a new domain module to WLJ:

1. **Identify intents** — What actions can users perform via the AI assistant?
2. **Wire into UAIO** — Add intents to `intent_engine.py` sets (TIME_AWARE_INTENTS, CONTEXT_AWARE_INTENTS)
3. **Add action handlers** — Implement handlers in `action_handlers.py` using `_get_recorded_at(kwargs)`
4. **Add SLCME context type** — Map module to context type in `context_pipeline.py:MODULE_TO_CONTEXT_TYPE`
5. **Add SAE state builder** — Create `build_<domain>_state(user)` in `state_builder.py`, register in `MODULE_BUILDERS`
6. **Create PIE rules** — What patterns should the system detect? Create rules with `@register`
7. **Create PRIE rules** — What trajectories can be projected? Create rules with `@register_prediction`
8. **Create PGE rules** — What guidance should be surfaced proactively? Create rules with `@register_guidance`
9. **Import rules** — Add imports in `run_daily_insights.py`, `run_prediction_engine.py`, and `run_guidance_engine.py`
10. **Update this document** — Add the new domain section
11. **Update `INTELLIGENCE_ARCHITECTURE.md`** — Add to rule tables

---

*Last updated: 2026-03-18 — Added Behavior cross-domain (3 PIE rules), Routine domain models, WorkoutScheduleLog*
