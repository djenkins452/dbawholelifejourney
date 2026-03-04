# Health Intelligence Engine

**Created:** 2026-03-04
**Status:** Active

The Health Intelligence Engine aggregates data from 15+ health source tables into a unified daily rollup, computes recovery and health scores, detects multi-week trends and plateaus, and provides cross-domain correlation analysis. It powers the Health Command Center dashboard and gives CoS multi-week pattern awareness.

---

## Architecture Overview

```
Source Tables (15+)          Services                    Consumers
─────────────────       ─────────────────           ─────────────────
SleepEntry          ─→  DailyHealthSummary      ─→  Health Command Center
StepsEntry          ─→       Builder                     Dashboard
WeightEntry         ─→                          ─→  CoS Context Hooks
GlucoseEntry        ─→  RecoveryScoreService    ─→       (cos_context.py)
FoodEntry           ─→
DailyNutrition      ─→  HealthScoreService      ─→  Health Score Card
Summary             ─→
HeartRateEntry      ─→  HealthTrendAnalyzer     ─→  Pattern Detection
BloodPressureEntry  ─→
BloodOxygenEntry    ─→  CorrelationService      ─→  Cross-domain Insights
WaterEntry          ─→
MedicineLog         ─→  ScorePipeline           ─→  Orchestration
FastingWindow       ─→
WorkoutSession      ─→  BaselinePolicy          ─→  14-day Gate
BodyCompositionEntry─→
```

---

## Model: DailyHealthSummary

**Location:** `apps/health/models.py`
**Table:** `health_dailyhealthsummary`

One row per user per day. Pre-computed from 15+ source tables.

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `user` | FK | User this summary belongs to |
| `summary_date` | Date | Date covered (unique with user) |
| `baseline_ready` | Bool | True if user has >= 14 days of core signals |
| `health_score` | SmallInt | Composite 0-100 (null until baseline ready) |
| `health_score_drivers` | JSON | Explainable breakdown |
| `recovery_score` | SmallInt | Recovery readiness 0-100 |
| `recovery_drivers` | JSON | Recovery score breakdown |
| `sleep_hours` | Decimal | Total sleep duration |
| `sleep_quality_score` | SmallInt | Sleep quality 0-100 |
| `sleep_debt_minutes` | Int | Minutes below 7.5h target |
| `resting_hr` | SmallInt | Resting heart rate (bpm) |
| `hrv` | Decimal | Heart rate variability (ms) |
| `steps` | Int | Daily step count |
| `workout_count` | SmallInt | Workouts completed |
| `training_load` | Decimal | Volume-based training load |
| `weight` | Decimal | Latest weight (lbs) |
| `body_fat_pct` | Decimal | Body fat percentage |
| `glucose_avg` | Decimal | Average glucose (mg/dL) |
| `glucose_variability` | Decimal | Coefficient of variation (%) |
| `time_in_range_pct` | Decimal | % readings 70-180 mg/dL |
| `calories_consumed` | Int | Total calories consumed |
| `protein_g` | Decimal | Total protein (grams) |
| `nutrition_logged` | Bool | At least one food entry logged |
| `medication_adherence_pct` | Decimal | Adherence rate 0-100 |
| `data_completeness_pct` | Decimal | % of trackable domains with data |
| `signals_present` | JSON | List of domain names with data |

### Indexes
- `(user, summary_date)` — unique constraint
- `(user, -summary_date)` — recent queries
- `(user, baseline_ready, -summary_date)` — filtered queries

---

## Services

### DailyHealthSummaryBuilder

**Location:** `apps/health/services/daily_summary_builder.py`

Aggregates data from all source tables into one DailyHealthSummary row.

```python
from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

builder = DailyHealthSummaryBuilder()
summary = builder.build_for_date(user, date.today())
builder.build_range(user, start_date, end_date)
```

**Idempotent:** Uses `update_or_create`. Safe to rerun.

**Collectors:** `_collect_sleep`, `_collect_vitals`, `_collect_activity`, `_collect_workouts`, `_collect_weight_and_composition`, `_collect_glucose`, `_collect_nutrition`, `_collect_hydration`, `_collect_medication`, `_collect_fasting`

---

### BaselinePolicy

**Location:** `apps/health/services/baseline_policy.py`

Requires >= 14 DailyHealthSummary rows with core signals before scoring activates.

```python
from apps.health.services.baseline_policy import BaselinePolicy

BaselinePolicy.baseline_ready(user, date.today())        # True/False
BaselinePolicy.baseline_days_available(user)               # int
BaselinePolicy.days_until_baseline(user)                   # int
BaselinePolicy.baseline_message(user)                      # str or None
```

**Core signal groups (at least one from each required):**
- Activity/sleep: `sleep` OR `steps`
- Outcome: `weight` OR `glucose` OR `nutrition`

---

### RecoveryScoreService

**Location:** `apps/health/services/recovery_score.py`

Baseline-aware recovery scoring (0-100).

```python
from apps.health.services.recovery_score import RecoveryScoreService

score, drivers = RecoveryScoreService.compute(user, date.today())
# score: int 0-100 or None
# drivers: {"status": "good", "components": {...}, "recommendation": "..."}
```

**Weights:**
| Component | Weight | Signal |
|-----------|--------|--------|
| Sleep | 40% | Duration + quality vs baseline |
| HRV | 25% | HRV ratio to 14-day baseline |
| Resting HR | 15% | Deviation from baseline (lower = better) |
| Training load | 10% | Load vs baseline (inverse) |
| Glucose stability | 10% | Time in range + CV% |

**Status labels:** excellent (85+), good (70-84), fair (50-69), poor (30-49), critical (<30)

---

### HealthScoreService

**Location:** `apps/health/services/health_score.py`

Composite health score (0-100), longevity-first.

```python
from apps.health.services.health_score import HealthScoreService

score, drivers = HealthScoreService.compute(user, date.today())
# drivers: {"domains": {...}, "missing_signals": [...], "immediate_focus": "..."}
```

**Weights (renormalized when signals are missing):**
| Domain | Weight | What it measures |
|--------|--------|-----------------|
| Sleep consistency | 20 | 7-day avg duration + consistency + quality |
| Recovery | 20 | Today's recovery score |
| Glucose stability | 15 | Time in range, variability |
| Weight trend | 15 | Direction relative to goal, rate |
| Workout consistency | 10 | Frequency over 7 days |
| Nutrition consistency | 10 | Tracking days + protein adequacy |
| Activity level | 10 | Average steps |

**Missing signals do NOT punish:** If glucose isn't connected, its weight is redistributed across active domains.

---

### HealthTrendAnalyzer

**Location:** `apps/health/services/trend_analyzer.py`

Detects 7/28-day rolling patterns.

```python
from apps.health.services.trend_analyzer import HealthTrendAnalyzer

analysis = HealthTrendAnalyzer.analyze(user, date.today())
# Returns: strengths, weaknesses, risk_flags, top_recommendation, rolling_7d, rolling_28d, trends
```

**Detects:**
- Weight plateaus (flat 10+ days with goal to lose)
- Sleep debt (3+ nights below 7h in a week)
- Nutrition logging drop-off (week-over-week decline)
- Glucose worsening (28d vs prior 28d average rising)
- Workout frequency decline
- Low protein intake
- Training volume stagnation

---

### CorrelationService

**Location:** `apps/health/services/correlation_service.py`

Computes Spearman rank correlations between health signals.

```python
from apps.health.services.correlation_service import CorrelationService

correlations = CorrelationService.compute(user, date.today())
# Returns top 3: [{"signal_a", "signal_b", "correlation", "direction", "interpretation"}, ...]
```

**Correlations computed:**
1. Sleep hours ↔ Glucose average
2. Sleep hours ↔ Next-day recovery score
3. Training load ↔ Next-day recovery score
4. Caffeine ↔ Sleep quality
5. Nutrition tracking ↔ Weekly weight change
6. Workout days ↔ Glucose average

---

### ScorePipeline

**Location:** `apps/health/services/score_pipeline.py`

Orchestrates the full build pipeline.

```python
from apps.health.services.score_pipeline import ScorePipeline

# Build summary + compute scores in one call
ScorePipeline.full_build(user, date.today())

# Range backfill
ScorePipeline.full_build_range(user, start_date, end_date)
```

---

## Nightly Job

### Management Command

```bash
# Yesterday for all active users (default)
python manage.py build_daily_health_summaries

# Backfill a date range
python manage.py build_daily_health_summaries --from 2026-01-01 --to 2026-02-28

# Specific user
python manage.py build_daily_health_summaries --user 42

# Rebuild last 7 days (catch late-arriving data)
python manage.py build_daily_health_summaries --days 7

# Skip scoring for fast bulk backfill
python manage.py build_daily_health_summaries --from 2025-06-01 --to 2026-02-28 --no-scores
```

### Celery Tasks

**Location:** `apps/health/tasks.py`

| Task | Schedule | Description |
|------|----------|-------------|
| `health.build_nightly_health_summaries` | Nightly 3:00 AM UTC | Rebuilds last 7 days for all active users |
| `health.build_user_health_summary` | On-demand | Build one user/date (with retry) |

**Celery Beat configuration** (add to settings if not using dynamic scheduling):
```python
CELERY_BEAT_SCHEDULE = {
    "nightly-health-summaries": {
        "task": "health.build_nightly_health_summaries",
        "schedule": crontab(hour=3, minute=0),
    },
}
```

---

## CoS Context Hooks

**Location:** `apps/health/services/cos_health_context.py`

Injected into `apps/core/ai_orchestrator/cos_context.py` under `_build_health_and_vitals()`.

```python
# What CoS sees:
result['health_intelligence'] = {
    'health_score': 78,
    'recovery_score': 72,
    'recovery_status': 'good',
    'strengths': ['Healthy weight loss pace', 'Strong workout frequency'],
    'weaknesses': ['Low nutrition tracking'],
    'risk_flags': ['Sleep debt pattern: 4/7 nights below 7h'],
    'top_recommendation': 'Prioritize consistent 7+ hour sleep',
    'trends_7d': {'sleep_hours': 6.8, 'steps': 8500, ...},
    'correlations': [{'signals': 'sleep_hours ↔ glucose_avg', 'interpretation': '...'}],
}
result['health_intelligence_summary'] = "Health score: 78/100 | Recovery: 72/100 (good) | ..."
```

---

## Health Command Center API

**Location:** `apps/health/services/command_center_api.py`

Single-call service for the dashboard.

```python
from apps.health.services.command_center_api import HealthCommandCenterService

data = HealthCommandCenterService.get_dashboard_data(user)
# Returns: score_card, domain_panels, trend_lines, key_drivers, recommendation
```

**Domain panels:** weight, sleep, workout, activity, glucose, nutrition, recovery, medication

**Trend lines:** weight, sleep_hours, steps, glucose_avg, health_score, recovery_score, hrv (up to 56 days)

---

## Testing

```bash
# Run all health intelligence tests
python manage.py test apps.health.tests.test_health_intelligence -v 2 --failfast

# 37 tests covering:
# - DailyHealthSummary model (create, unique, str)
# - Builder (empty day, sleep, steps, weight, glucose, idempotent, range, nutrition)
# - BaselinePolicy (new user, few days, 14 days, missing signals, messages)
# - RecoveryScore (no baseline, with baseline, status labels)
# - HealthScore (no baseline, with data, missing signals)
# - TrendAnalyzer (insufficient data, plateau, sleep debt, strengths)
# - CorrelationService (insufficient data, rank function, with data)
# - ScorePipeline (full build, idempotent)
# - CommandCenter (empty, with data)
# - CoS context (no data, summary text, with data)
```

---

## Backfill Guide

For existing users with historical data:

```bash
# 1. Build summaries for all historical data (skip scores for speed)
python manage.py build_daily_health_summaries --from 2025-06-01 --to 2026-03-03 --no-scores

# 2. Compute scores (baseline will already be ready for established users)
python manage.py build_daily_health_summaries --from 2025-06-01 --to 2026-03-03

# 3. Verify
python manage.py shell -c "
from apps.health.models import DailyHealthSummary
print(DailyHealthSummary.objects.count(), 'summaries')
print(DailyHealthSummary.objects.filter(health_score__isnull=False).count(), 'with scores')
"
```
