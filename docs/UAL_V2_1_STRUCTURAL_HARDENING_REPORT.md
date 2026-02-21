# UAL v2.1 — Structural Intelligence Hardening Report

**Date:** 2026-02-21
**Author:** Claude Code (automated)
**Scope:** Surgical refinement of UAL v2 — no new scenarios, no new signals, no surface volume increase

---

## Summary

UAL v2.1 strengthens arbitration realism in five areas without expanding the system's scope or surface volume. All new logic is wrapped in try/except and fails gracefully to v2 behavior.

### Changes Implemented

| Area | Module | Type |
|------|--------|------|
| Intervention Fatigue Awareness | `intervention_fatigue.py` | NEW |
| Recent Nudge Memory | `nudge_memory.py` | NEW |
| Capacity-Based Style Bias | `intervention_engine.py` | MODIFIED |
| Pattern Escalation Tier 2 | `pattern_analyzer.py` | MODIFIED |
| Capacity Volatility Index | `capacity_volatility.py` | NEW |
| Pipeline v2.1 Order | `arbitration_engine.py` | MODIFIED |
| Narrative Style Awareness | `narrative_engine.py` | MODIFIED |
| Observability Panels (4) | `views.py` + template | MODIFIED |

---

## New Modules

### 1. `intervention_fatigue.py`
**Purpose:** Track per-scenario fatigue from repeated ignored interventions.

**Model:** `InterventionResponseLog` (user, date, scenario, surfaced/complied/ignored/overrode counts)

**Formula:**
```
ignored_ratio = ignored / surfaced
fatigue_score = ignored_ratio × 0.7 + consecutive_ignore_days × 0.1
Clamped 0–1
```

**Bias behavior:**
- `fatigue_score > 0.6` → surfacing penalty (max -0.05)
- `fatigue_score < 0.3 AND compliance > 0.6` → slight positive bias (+0.03)
- Bias is **ephemeral** — applied only during classification, NEVER persisted to WeightAdjustment

**Safety bounds:** `±0.05` max, never exceeds

### 2. `nudge_memory.py`
**Purpose:** Prevent cognitively redundant nudges within 12h windows.

**Model:** `RecentNudgeMemory` (user, surfaced_at, scenario, semantic_tag, trace_id)

**Behavior:**
- Before surfacing, check recent 12h nudge memory
- If semantic tag matches prior nudge: apply -0.1 priority penalty
- If severity escalation (HEALTH_CRITICAL, MOOD_CRITICAL): bypass penalty
- Tags reuse category/scenario names — no embeddings

**Retention:** 12 hours, auto-purged

### 3. `capacity_volatility.py`
**Purpose:** Detect capacity instability and reduce surfacing aggressiveness.

**Formula:**
```
std_dev = population_std_dev(last 5 DailyCapacityLog scores)
volatility_flag = std_dev > 0.25
```

**Behavior when volatile:**
- Downgrade confidence framing by one level (HIGH→MODERATE, MODERATE→LOW)
- Flag for reduced surfacing aggressiveness
- Does NOT alter baseline capacity score

---

## Modified Modules

### 4. Intervention Engine — Capacity Style Bias
**Mapping:**
| Capacity State | Style Bias | Behavior |
|---------------|-----------|----------|
| HIGH_CAPACITY | `strategic` | Strategic framing allowed |
| NORMAL | `normal` | Unchanged |
| LOW | `tactical` | Tactical only, no multi-step planning |
| CRITICAL | `maintenance` | One item max, language softened, no strategic planning |

Style bias flows to narrative engine for tone adjustment.

### 5. Pattern Analyzer — Tier 2 Escalation
**New thresholds:**
| Pattern | Trigger | Label |
|---------|---------|-------|
| DRIFT_CRITICAL ≥7 in 14d | Extended drift | DRIFT_PERSISTENT_T2 |
| MOOD_CRITICAL ≥5 in 7d | Extended mood | MOOD_PERSISTENT_T2 |
| HEALTH_CRITICAL ≥5 in 7d | Extended health | HEALTH_PERSISTENT_T2 |

**When Tier 2 active:**
- Override max surfaced to 1
- Insert "Strategic Reset Consideration" flag
- Narrative frames as "We may need a reset conversation" — no alarmism
- Does NOT expand volume or bypass safety clamps

---

## Pipeline v2.1 Order

```
1.  Signal Collection
2.  Adaptive Weight Application
3.  Intervention Fatigue Bias           ← NEW (try/except)
4.  Scenario Classification (confidence gap)
5.  Fuse Cross-Domain Signals
6.  Capacity Composite
7.  Capacity Volatility Check           ← NEW (try/except)
8.  Pattern Analysis (Tier 1 + Tier 2)  ← ENHANCED
9.  Recent Nudge Memory Penalty         ← NEW (try/except)
10. Intervention Decision (capacity + fatigue + pattern aware)  ← ENHANCED
11. Narrative Engine (style bias aware) ← ENHANCED
12. Log Decision
13. Update ScenarioHistory + InterventionResponseLog + RecentNudgeMemory ← ENHANCED
14. Weight Tuning Check
```

All new steps (3, 7, 9, 13) wrapped in individual try/except blocks. Failure at any new step logs debug and falls back to v2 behavior.

---

## Safety Boundaries

| Boundary | Enforcement |
|----------|------------|
| Fatigue bias ±0.05 max | `MAX_NEGATIVE_BIAS = -0.05`, `MAX_POSITIVE_BIAS = 0.03` |
| Fatigue bias is ephemeral | Never written to WeightAdjustment model |
| Weight tuning ±0.10 max | Existing v2 clamp preserved |
| Weights never negative | Existing v2 clamp preserved |
| Tier 2 does not expand volume | `max_surfaced = 1` (reduction only) |
| Nudge penalty does not prevent surfacing | Priority adjustment only (-0.1) |
| Severity escalation bypasses nudge penalty | HEALTH_CRITICAL, MOOD_CRITICAL exempt |
| Volatility does not alter capacity score | Only confidence framing affected |
| All new steps fail gracefully | Individual try/except with debug logging |
| Pipeline never raises | Outer try/except returns safe fallback |

---

## Observability Panels (4 new)

1. **Fatigue Score Distribution (7d)** — Surfaced/complied/ignored/overrode counts, per-scenario fatigue ratio
2. **Nudge Collision Rate (12h)** — Total nudges, unique tags, collision count and rate
3. **Capacity Volatility Indicator (14d)** — Std dev, stable/volatile status, sample count, mean score
4. **Pattern Tier 2 Trigger Count** — Per-rule count vs threshold, active/inactive status

No UI redesign. Panels added to existing observability dashboard under UAL section.

---

## Example Decision Trace — Before vs After

### Before (v2)
```
Signal Collection → Classify(DRIFT_CRITICAL, HIGH confidence)
→ Capacity(NORMAL) → Patterns(DRIFT_PERSISTENT)
→ Intervene(ACCOUNTABILITY, 3 surfaced) → Narrative(standard)
→ Log → Tune
```

### After (v2.1)
```
Signal Collection → Load Weights
→ Fatigue Check(DRIFT: fatigue=0.7, bias=-0.03)
→ Classify(DRIFT_CRITICAL, HIGH confidence)
→ Fuse → Capacity(NORMAL)
→ Volatility Check(std_dev=0.12, stable)
→ Patterns(DRIFT_PERSISTENT + DRIFT_PERSISTENT_T2)
→ Nudge Memory(no collision)
→ Intervene(ACCOUNTABILITY, max_surfaced=1 via Tier 2, style_bias=normal)
→ Narrative(Strategic Reset Consideration, fatigue bias logged)
→ Log Decision + InterventionResponseLog + NudgeMemory
→ Tune
```

Key differences:
- Fatigue bias reduces surfacing priority for repeatedly ignored DRIFT interventions
- Tier 2 overrides max surfaced to 1 (structural intervention)
- Narrative includes strategic reset framing
- InterventionResponseLog and NudgeMemory logged for future analysis

---

## Confirmation: No Surface Volume Increase

- MAX_SURFACED constant unchanged (3)
- Capacity limits unchanged (3/3/2/1)
- Confidence LOW limit unchanged (1)
- Tier 2 only reduces (→1), never increases
- Nudge memory only penalises priority, does not add items
- No new signal sources
- No new scenarios
- No UI expansion beyond observability panels

---

## Test Coverage

| Test Class | New Tests | Coverage |
|-----------|-----------|----------|
| InterventionFatigueTests | 5 | Fatigue scoring, bias bounds, compliance, logging |
| NudgeMemoryTests | 4 | Collision detection, escalation bypass, recording |
| CapacityStyleBiasTests | 5 | All 4 bias states + narrative tone |
| PatternTier2Tests | 6 | Triggers, overrides, safety, narrative |
| CapacityVolatilityTests | 6 | Flag detection, confidence downgrade, stability |
| ArbitrationNeverRaisesTests | 4 | Pipeline survives fatigue/volatility/nudge failures |
| **Total new** | **30** | |
| **Total suite** | **101** | 71 v2 + 30 v2.1 |

All 101 tests pass. Runtime: ~4.4 seconds.

---

## Files Changed

### New Files
- `apps/core/ai_arbitration/intervention_fatigue.py`
- `apps/core/ai_arbitration/nudge_memory.py`
- `apps/core/ai_arbitration/capacity_volatility.py`
- `apps/core/migrations/0078_recentnudgememory_interventionresponselog_and_more.py`

### Modified Files
- `apps/core/ai_arbitration/models.py` — Added InterventionResponseLog, RecentNudgeMemory
- `apps/core/ai_arbitration/arbitration_engine.py` — v2.1 pipeline (14 steps)
- `apps/core/ai_arbitration/intervention_engine.py` — Style bias, fatigue, Tier 2
- `apps/core/ai_arbitration/pattern_analyzer.py` — Tier 2 escalation
- `apps/core/ai_arbitration/narrative_engine.py` — Style bias, Tier 2, volatility notes
- `apps/core/ai_arbitration/admin.py` — Registered new models
- `apps/core/ai_arbitration/tests.py` — 30 new tests
- `apps/core/ai_observability/views.py` — 4 new panel data methods
- `templates/intelligence/observability_dashboard.html` — 4 new panels

---

## Runtime Impact

- 3 new try/except blocks in pipeline: ~0ms additional on success, 0ms on failure (debug log only)
- Fatigue: 1 DB query (7-day window) — negligible
- Nudge memory: 1 DB query (12h window) + 1 bulk_create — negligible
- Volatility: 1 DB query (5-day window) — negligible
- Pattern Tier 2: No additional queries (reuses existing history data)
- Total estimated pipeline overhead: <5ms

---

*Stability > cleverness. Executive realism > feature expansion.*
