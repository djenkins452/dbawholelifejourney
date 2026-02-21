# UAL v2 — Executive Stability & Adaptation Layer

**Implementation Date:** 2026-02-21
**Status:** Complete — deployed
**Test Count:** 71 tests (42 v1 + 29 v2), all passing

---

## Summary

UAL v2 is a refinement pass that adds four capabilities to the Universal Arbitration Layer without expanding domain signals, adding new scenarios, or increasing surface volume. Stability > complexity.

---

## Section 1 — Confidence Dampening

**File:** `apps/core/ai_arbitration/scenario_classifier.py`

The classifier now computes a `confidence_gap` between the top two scenario scores and classifies it:

| Gap | Level | Behavior |
|-----|-------|----------|
| < 0.05 | **LOW** | Surface only 1 item, soften narrative, avoid directive tone, acknowledge ambiguity |
| 0.05 – 0.15 | **MODERATE** | Current v1 behavior unchanged |
| > 0.15 | **HIGH** | Full suppression allowed, clear framing |

**Logged in:** `ArbitrationDecisionLog.confidence_level`

**Impact on intervention:**
- LOW confidence → `MAX_SURFACED = 1` (overrides capacity limit)
- LOW confidence → narrative includes "CONFIDENCE IS LOW" with softening instruction
- HIGH confidence → narrative includes "CONFIDENCE IS HIGH" with direct framing

---

## Section 2 — Scenario History & Pattern Analysis

**New Model:** `ScenarioHistory`
- Fields: user, date, dominant_scenario, intervention_style, capacity_state, suppressed_count, surfaced_count
- One record per user per day (update_or_create)
- Unique constraint on (user, date)

**New Module:** `apps/core/ai_arbitration/pattern_analyzer.py`

**Pattern Rules:**

| Pattern | Trigger | Label |
|---------|---------|-------|
| Mood persistent | MOOD_CRITICAL ≥ 3 in 5 days | `MOOD_PERSISTENT` |
| Drift persistent | DRIFT_CRITICAL ≥ 4 in 7 days | `DRIFT_PERSISTENT` |
| Health persistent | HEALTH_CRITICAL ≥ 3 in 5 days | `HEALTH_PERSISTENT` |
| Generic repetition | Any scenario ≥ 5 in 7 days | `GENERIC_REPETITION` |

**Intensity modifier:** 0.1 per count above threshold, capped at 0.3. Gentle escalation only.

**Narrative impact:** Pattern hints appear as `PATTERN NOTE:` in the executive judgment when detected. Context-setting, not overreaction.

---

## Section 3 — Adaptive Weight Tuning

**New Model:** `WeightAdjustment`
- Fields: user, scenario, signal, baseline_weight, adjustment_delta, last_updated
- Unique constraint on (user, scenario, signal)

**New Module:** `apps/core/ai_arbitration/weight_tuner.py`

**Tuning cycle:**
1. Every 50 decisions (per user), tuning runs
2. Looks at recent decisions with feedback (complied / overrode / ignored)
3. Computes average compliance direction per scenario
4. Adjusts all signal weights for that scenario by ±0.02 max per cycle
5. Clamps total delta to ±0.10 from baseline
6. Weights can never go negative

**Safety bounds:**
- `MAX_ADJUSTMENT_PER_CYCLE = 0.02`
- `MAX_DELTA_FROM_BASELINE = 0.10`
- Requires minimum 10 feedback samples
- Self-amplification impossible — clamp prevents runaway

**Integration:** Adjusted weights loaded at classify time and applied via `_apply_adjustments()`.

---

## Section 4 — Capacity Composite Model

**New Module:** `apps/core/ai_arbitration/capacity_engine.py`

**Composite formula:**

```
load = sleep_deficit × 0.30 + mood_decline × 0.20 + emotional_load × 0.20
     + schedule_overload × 0.20 + open_loop_count × 0.10

capacity_score = 1.0 - load  (normalised 0-1)
```

**Classification:**

| State | Score | Max Surfaced |
|-------|-------|-------------|
| HIGH_CAPACITY | ≥ 0.75 | 3 |
| NORMAL | 0.45 – 0.74 | 3 |
| LOW | 0.25 – 0.44 | 2 |
| CRITICAL | < 0.25 | 1 |

**Narrative impact:**
- CRITICAL → "CAPACITY IS CRITICAL" warning, frame everything as optional
- LOW → "Capacity is reduced" note, keep suggestions light

**New Model:** `DailyCapacityLog`
- Fields: user, date, capacity_score, capacity_state, component scores
- One record per user per day
- Used for observability trend line

---

## Section 5 — Updated Pipeline

```
Signal Collection
  → Scenario Classification (with adaptive weights + confidence dampening)
  → Composite Detection (signal fusion)
  → Capacity Assessment (capacity composite)
  → Pattern Analysis (14-day rolling window)
  → Intervention Decision (confidence + capacity aware)
  → Narrative Engine (confidence + capacity + pattern framing)
  → Decision Log + Scenario History + Capacity Log
  → Weight Tuning Check (every 50 decisions)
```

All new steps are wrapped in try/except. Pipeline never raises — failures produce safe fallback.

---

## Section 6 — Testing

**71 total tests** (was 42 in v1):

| Test Class | Count | Coverage |
|------------|-------|----------|
| ScenarioClassifierTests | 10 | All scenarios, secondaries, empty signals |
| ConfidenceDampeningTests | 7 | LOW/MODERATE/HIGH classification, surfacing limits, narrative softening |
| CapacityCompositeTests | 6 | All states, normalisation, intervention integration, narrative |
| PatternAnalyzerTests | 6 | MOOD/DRIFT persistent, thresholds, intensity bounds, narrative |
| AdaptiveWeightTests | 5 | Adjustments applied, clamped, non-negative, baseline identity |
| SignalFuserTests | 9 | All composites, anti-signals, sorting, contributing signals |
| InterventionEngineTests | 10 | All styles, composites, max surfaced, suppression |
| NarrativeEngineTests | 7 | All scenarios, composites, confidence, suppressed, unify |
| ArbitrationEngineTests | 6 | Full pipeline stable/health, never raises, v2 field logging, history, capacity |
| StabilityTests | 3 | Zero signals unchanged, no feedback loops, empty capacity |
| SignalStrengthTests | 3 | Normalisation edge cases |

**Runtime:** ~1.7 seconds for all 71 tests.

---

## Section 7 — Observability

**Observability Dashboard** (`/intelligence/observability/`) — 4 new UAL panels:

1. **Confidence Distribution (7d)** — HIGH / MODERATE / LOW counts + total decisions
2. **Scenario Frequency (14d)** — Per-scenario count bars
3. **Capacity Trend (14d)** — Daily capacity bars with state coloring (green/blue/amber/red)
4. **Weight Adjustments** — Active weight deltas from baseline with scenario/signal breakdown

**Admin panels** — All 4 new models registered with read-only admin:
- `ScenarioHistoryAdmin` — filterable by scenario, capacity
- `WeightAdjustmentAdmin` — filterable by scenario
- `DailyCapacityLogAdmin` — filterable by capacity state
- `ArbitrationDecisionLogAdmin` — updated with confidence_level and capacity_state columns

---

## Files Modified

| File | Change |
|------|--------|
| `apps/core/ai_arbitration/models.py` | Added ScenarioHistory, WeightAdjustment, DailyCapacityLog; updated ArbitrationDecisionLog with confidence_level, capacity_state, capacity_score |
| `apps/core/ai_arbitration/scenario_classifier.py` | Added confidence dampening, adaptive weight support |
| `apps/core/ai_arbitration/capacity_engine.py` | **NEW** — Capacity composite engine |
| `apps/core/ai_arbitration/pattern_analyzer.py` | **NEW** — Multi-day pattern analyzer |
| `apps/core/ai_arbitration/weight_tuner.py` | **NEW** — Adaptive weight tuning |
| `apps/core/ai_arbitration/arbitration_engine.py` | Updated pipeline with 10 steps |
| `apps/core/ai_arbitration/intervention_engine.py` | Confidence + capacity modifiers for surfacing |
| `apps/core/ai_arbitration/narrative_engine.py` | Confidence-aware framing, capacity/pattern notes |
| `apps/core/ai_arbitration/admin.py` | Registered all new models |
| `apps/core/ai_arbitration/tests.py` | 71 tests (was 42) |
| `apps/core/models.py` | Import new models |
| `apps/core/migrations/0076_ual_v2_stability_adaptation.py` | Migration |
| `apps/core/ai_observability/views.py` | Added UAL metrics to dashboard context |
| `templates/intelligence/observability_dashboard.html` | 4 new UAL panels + CSS |

---

## Design Principles

- **Stability > complexity:** No new scenarios, no new signals, no expanded surface volume
- **Slow adaptation:** Weight tuning at ±0.02 per 50 decisions, clamped ±0.10
- **Gentle escalation:** Pattern hints influence intensity by 0.1-0.3, not hard overrides
- **Safe degradation:** Every new step wrapped in try/except, pipeline never raises
- **Observability:** Every new dimension logged and visible in dashboard

---

*UAL v2 — Executive Stability & Adaptation Layer — 2026-02-21*
