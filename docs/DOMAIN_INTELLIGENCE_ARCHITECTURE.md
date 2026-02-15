# Whole Life Journey — Domain Intelligence Architecture

**Purpose:** Maps how each application domain (Health, Body Composition, Labs, Goals, Habits, Journal, Scripture) integrates with the five cognitive engines. Domain engines plug into the UAIO orchestrator and must never bypass cognitive engines.

**Prerequisite:** Read `docs/INTELLIGENCE_ARCHITECTURE.md` first for engine contracts and pipeline.

---

## Domain Integration Principle

Every domain module follows the same integration pattern:

```
User Action in Domain
  → AI Assistant (via UAIO orchestrator)
    → SLCME resolves context ("my weight", "that goal")
    → HTIE resolves time ("yesterday", "last Tuesday")
    → Action Handler executes domain logic
      → PIE evaluates insight rules for this domain
        → PRIE runs prediction rules for this domain
  → Response with temporal context
```

**Rule:** Domain modules MUST NOT directly call `datetime.strptime()` on user input, hard-code context resolution, or generate insights/predictions outside the engine pipeline.

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

## Domain Integration Summary

| Domain | PIE Rules | PRIE Rules | UAIO Intents | SLCME Context |
|--------|-----------|------------|--------------|---------------|
| Health (Weight) | 3 | 1 (3 horizons) | `update_weight` | `health_entry` |
| Body Composition | 2 | 2 (6 horizons) | — | `health_entry` |
| Labs & Vitals | 1 | 1 | — | — |
| Goals | 2 | 1 | `save_goal`, `complete_goal` | `goal_page` |
| Habits | 2 | 1 | `log_habit` | `habit_page` |
| Journal | 2 | 0 | — | `journal_page` |
| Scripture | 1 | 0 | `save_verse` | `scripture_page` |
| **Total** | **13** | **6** | — | — |

---

## Adding a New Domain

When adding a new domain module to WLJ:

1. **Identify intents** — What actions can users perform via the AI assistant?
2. **Wire into UAIO** — Add intents to `intent_engine.py` sets (TIME_AWARE_INTENTS, CONTEXT_AWARE_INTENTS)
3. **Add action handlers** — Implement handlers in `action_handlers.py` using `_get_recorded_at(kwargs)`
4. **Add SLCME context type** — Map module to context type in `context_pipeline.py:MODULE_TO_CONTEXT_TYPE`
5. **Create PIE rules** — What patterns should the system detect? Create rules with `@register`
6. **Create PRIE rules** — What trajectories can be projected? Create rules with `@register_prediction`
7. **Import rules** — Add imports in `run_daily_insights.py` and `run_prediction_engine.py`
8. **Update this document** — Add the new domain section
9. **Update `INTELLIGENCE_ARCHITECTURE.md`** — Add to rule tables

---

*Last updated: 2026-02-15*
