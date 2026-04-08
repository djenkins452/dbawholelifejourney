# WLJ Signal Conventions

**Owner:** Chief of Staff intelligence pipeline
**Last updated:** 2026-04-08 (Phase 6 hardening)
**Scope:** State builders, signal trust layer, CoS context, insight rules, dashboards

---

## Why this document exists

The Phase 6 system normalization audit (2026-04-08) found that the WLJ
state layer had drifted on several key conventions: a medication
adherence `×100` bug produced values in the 0–10000 range, orphan
signals were read but never written, nutrition state was gated on
`today_count > 0`, and so on. The root cause was that conventions
had been implemented builder-by-builder without a single place to
check them against.

This doc is that place. **It documents the existing conventions so
that future work can check for drift.** It does NOT introduce a new
architecture — all rules here describe what the code already does
(or should do after Phase 6 fixes).

---

## Core rules

### Rule 1 — Units are in the suffix

The suffix of a state key declares its format. The validator at
`apps/core/ai_state/state_validator.py :: validate_signal_conventions`
enforces these:

| Suffix | Expected format | Examples |
|---|---|---|
| `_pct`, `_percent`, `_percentage` | numeric, 0–100 | `medication_adherence_pct`, `calorie_compliance_pct` |
| `_ratio` | numeric, 0–1 (small rounding slack) | `protein_ratio`, `savings_rate` (exception, see below) |
| `_score` | numeric, 0–100 | `workout_adherence_score`, `sleep_consistency_score` |
| `_trend` | string in approved vocabulary | `sleep_trend`, `weight_trend` |
| `_count`, `_7d`, `_30d` | integer | `workouts_7d`, `food_entries_7d` |
| `_avg_hours_*`, `_avg_duration_*` | numeric, hours or minutes (unit in name) | `sleep_avg_hours_7d`, `sleep_avg_duration_7d` |
| `_g`, `_mg`, `_lb`, `_oz`, `_ml` | numeric in the declared unit | `daily_protein_g`, `total_sodium_mg` |

### Rule 2 — Trend vocabulary

Approved trend string values. Rules and routers match against these.

- Canonical: `"increasing"`, `"decreasing"`, `"stable"`, `"insufficient_data"`
- Legacy (still accepted, but do not add new uses): `"improving"`, `"declining"`, `"up"`, `"down"`, `"flat"`

When adding a new `_trend` field, emit the canonical set only.

### Rule 3 — `None` vs `0` are not interchangeable

`None` means **"not measured"**. `0` means **"measured, value is zero"**.

- A user with zero food entries today → `daily_calories = 0.0`
- A user with no nutrition goal set → `protein_compliance_pct = None`
- A user with no medication schedule → `adherence_7d = None`

Consumers must treat these differently:

```python
# WRONG — treats "not measured" as "zero compliance"
if state.get("calorie_compliance_pct", 0) < 80:
    fire_warning()

# RIGHT — only fires when actually below 80
pct = state.get("calorie_compliance_pct")
if pct is not None and pct < 80:
    fire_warning()
```

The Phase 3 orphan-signal audit specifically flagged the `.get(key, 0)`
anti-pattern because it masks orphan reads.

### Rule 4 — Disabled domains return `{enabled: False}`

When a feature flag is off, the state builder must return
`{"enabled": False}` and nothing else. Examples:

- `build_fasting_state` — gated on both `is_feature_enabled("health", "fasting")` AND `default_fasting_type != "none"`
- `build_nutrition_state` — gated on `is_feature_enabled("health", "nutrition")`

This is the **SAE-level gate**. The CoS context layer applies a
second, independent gate at `cos_context.py :: _TAGGED_BUILDERS`
that filters entire domain context builders based on module-level
permissions from `apps.users.module_permissions`.

**Both layers are needed:** SAE gate prevents insight rules (which
read SAE state directly) from firing on disabled-domain data. CoS
gate prevents disabled-domain data from reaching the LLM.

### Rule 5 — Percent bounds are not optional

If a key is named `_pct`/`_percent`/`_percentage`, the value MUST be
in [0, 100] when non-None. Every multiplication or division must
preserve this invariant.

**Historical bug** (fixed 2026-04-08): `cos_context.py:344` was
`adherence_pct = round(adherence_7d * 100, 1)` where `adherence_7d`
was already 0-100. The result was `6800` for Danny. Always check
the write-site format before adding scaling.

---

## Dual-metric situations (do not delete)

Two domains intentionally emit **two different adherence numbers**
for the same underlying data. These are NOT duplicates — they
serve different semantic purposes.

### Medication adherence

| Key | Formula | Semantic | Consumer |
|---|---|---|---|
| `medicine.adherence_7d` | `taken / (expected - skipped) * 100`, capped at 100 | "Did you take them at all?" — late counts as taken | Patient-facing dashboards, simple compliance rules |
| `medicine.adherence_score_7d` | `(completed*1.0 + late*0.7) / expected * 100`, capped at 100 | "Did you take them on time?" — weighted accountability | Cockpit cards, behavior score engine, CoS accountability framing |

Both are scoped to `INTAKE_TYPE_MEDICATION`. Supplements are tracked
separately under `medicine.supplement_adherence_7d` using the first
(simple) formula.

### Workout adherence

| Key | Source | When populated |
|---|---|---|
| `fitness.workout_adherence_score` | `calculate_workout_behavior_output` — compares scheduled vs completed | User has an active WorkoutPlan |
| `fitness.workout_consistency_score` | Trailing-window ratio: `workouts_7d / (workouts_30d / 4)` | Fallback when no active plan — capped at 150 (exempt from normal 0-100 bound) |

These are **NOT duplicates**. The second is a fallback for users
who log workouts but have no formal plan, computed from their own
30-day baseline. Removing it would leave plan-less users with no
consistency signal at all.

`workout_consistency_score` is listed in
`_SCORE_BOUND_EXEMPT` in the signal validator because its formula
can produce values up to 150.

---

## Nutrition — 7 calculation sites

The nutrition domain has seven independent code paths that sum
`FoodEntry.total_calories / total_protein_g` for different windows
and purposes. These are NOT consolidated, for intentional reasons:

| # | Site | Window | Purpose |
|---|---|---|---|
| 1 | `NutritionQueries.get_daily_totals()` | single day | Real-time views & templates |
| 2 | `build_nutrition_state()` | today | SAE state snapshot |
| 3 | `daily_summary_builder._collect_nutrition()` | single day | DailyHealthSummary persistence (prefers DailyNutritionSummary, falls back to FoodEntry) |
| 4 | `DailyNutritionSummary.recalculate()` | single day | DNS table write |
| 5 | `NutritionStatsView` | per-date range loop | Stats / history pages |
| 6 | `NutritionGapRule` | trailing 7d | PIE insight detection |
| 7 | `nutrition_events_adapter` | per FoodEntry | Event record generation |

Consolidating would require sharing caches across request and
background contexts and is out of scope. The Phase 6 fix (Fix 4)
added the FoodEntry fallback to `build_nutrition_state` when DNS
is empty so that rolling 7-day averages work even without the
DNS table being populated.

---

## Enforcement

The signal validator at
`apps/core/ai_state/state_validator.py :: validate_all_signal_conventions`
runs over a user state dict and logs any violations with prefix
`SIGNAL_CONVENTION_VIOLATION`.

It is safe to call on the critical path (never raises). Intended
use:

```python
from apps.core.ai_state.state_validator import log_signal_convention_violations

state = get_user_state(user)
log_signal_convention_violations(state, user_id=user.pk)
```

Recommended deployments:

1. **Pre-deploy gate test:** Assert `validate_all_signal_conventions({}) == {}`
   and a golden sample state produces zero violations.
2. **Nightly observability:** Call `log_signal_convention_violations`
   for a sample of active users in the SAME cycle and alert on any
   non-empty results.
3. **CI test fixture:** Include a test that builds state for a
   synthetic user and asserts no violations.

Adding new exempt keys requires adding them to `_SCORE_BOUND_EXEMPT`
in `state_validator.py` with a code comment explaining why. That
surfaces in code review.

---

## Two-layer gating summary

```
┌──────────────────┐
│  User preference │  health_enabled, fasting sub-feature, etc.
└────────┬─────────┘
         │
         ▼
┌─────────────────────────┐          ┌────────────────────────┐
│  SAE state builder gate │          │  CoS context filter    │
│  (fasting, nutrition    │          │  (_TAGGED_BUILDERS by  │
│  Phase 5)               │          │  module permissions)   │
│                         │          │                        │
│  returns {enabled:False}│          │  skips disabled modules│
└────────┬────────────────┘          └────────┬───────────────┘
         │                                    │
         ▼                                    ▼
┌────────────────────┐               ┌────────────────────┐
│  Insight rules     │               │  LLM-facing        │
│  read SAE state    │               │  context payload   │
└────────────────────┘               └────────────────────┘
```

**Insight rules** read SAE state and must respect `enabled: False`
themselves. Cross-domain rules should check `state["fitness"].get("enabled", True)`
etc. before firing.

**LLM-facing CoS context** never sees disabled domains.

---

## Appendix: Known historical drift (fixed)

For future audits, these are issues that have been addressed in
the Phase 6 hardening pass. Do not re-flag them:

- `cos_context.py:344 medication_adherence_state.adherence_pct = adherence_7d * 100` — removed the `* 100`
- `state.adherence_7d` mixed medication + supplement — scoped to `INTAKE_TYPE_MEDICATION`
- `sleep_trend` and `sleep_quality_avg_7d` — now written by `build_health_state`
- `build_nutrition_state` gated on `today_count > 0` — now unconditional
- `NutritionQueries.get_daily_totals()` field-name bugs in `ExportAccountDataView` — rewritten
- `ComplianceRiskRule / OvertrainingRiskRule` read from wrong domain — now read correct domain
- `cos_context.py:2297 lab.raw_test_name` on str — fixed
- `cos_context.py:2384 g.name` for LifeGoal — should be `g.title`
- `cos_context.py:1949 detected_at` on DomainCorrelation — should be `created_at`
- `SleepEntry.total_minutes` used in daily activity service — actual field is `total_duration_minutes`
- `RoutineSchedule.duration_minutes` — no such field, fallback to `DEFAULT_ITEM_DURATION`
- `ReadingPlanTemplate.name` in faith progress collector — actual field is `title`
