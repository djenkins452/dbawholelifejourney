# CoS Context Intelligence Architecture (COS-CX)

**Version:** 1.0
**Date:** 2026-02-27
**Status:** Active

---

## Overview

The COS-CX system is a 6-phase context intelligence expansion for the Chief of Staff (CoS) AI assistant. It transforms CoS from a data reporter into a strategic advisor with:

- **Named specificity** (not counts) in every interaction
- **Signal prioritization** (single most important thing right now)
- **Gap detection** (you're doing A, B, D, E but not C)
- **Temporal matching** (task → available time window)
- **Diagnostic reasoning** (why questions trigger cross-domain causal analysis)
- **Behavioral prediction** (tomorrow's completion probabilities)

All modules are **fail-safe** — they return empty strings on any error and never break the chat pipeline.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│             format_cos_system_injection()                │
│  (apps/core/ai_orchestrator/cos_context.py)             │
│                                                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌──────────┐  │
│  │  CX1    │  │  CX2    │  │  CX3    │  │  CX4     │  │
│  │Specific.│→ │Lead Sig.│→ │Goal Gap │→ │Temporal  │  │
│  │ Block   │  │Priorit. │  │Analyzer │  │ Matcher  │  │
│  └─────────┘  └─────────┘  └─────────┘  └──────────┘  │
│                                                         │
│  ┌─────────┐                                            │
│  │  CX6    │                                            │
│  │Behavior │                                            │
│  │Forecast │                                            │
│  └─────────┘                                            │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│          _generate_response() system prompt              │
│  (apps/ai/personal_assistant.py)                        │
│                                                         │
│  ┌─────────┐                                            │
│  │  CX5    │  ← Only on diagnostic "why" questions      │
│  │Diagnos. │                                            │
│  │Context  │                                            │
│  └─────────┘                                            │
└─────────────────────────────────────────────────────────┘
```

---

## Phase Details

### CX1: Always-On Specificity Block
**File:** `apps/cos/context/specificity_block.py`
**Entry:** `build_specificity_block(user, now) → str`
**Injected:** Every CoS context, every message, unconditionally
**Token Budget:** ~200 tokens max
**Performance:** < 10ms (4 bounded queries)

Provides named items instead of counts:
- **Tasks:** Top 3 by urgency (overdue first, then due today) with names and priority tags
- **Events:** Today's 5 events with times and status tags [NOW], [SOON], [done]
- **Medications:** Up to 5 outstanding medications by name with scheduled time
- **Goals:** Up to 3 active goals with milestone progress and deadline proximity

### CX2: Lead Signal Prioritizer
**File:** `apps/cos/context/signal_prioritizer.py`
**Entry:** `compute_lead_signal(user, specificity_block, now, cos_context) → str`
**Injected:** Every CoS context (after CX1 and CX3)
**Token Budget:** 1-2 sentences max
**Performance:** < 2ms (pure computation + bounded queries)

Scoring algorithm: `base_urgency × time_decay × tier_weight`

| Signal | Score Range |
|--------|-------------|
| Imminent event (≤2 min) | 100 |
| Imminent event (≤5 min) | 95 |
| Imminent event (≤15 min) | 85 |
| Overdue medications | 70-90 |
| Active event (NOW) | 60 |
| Overdue tasks | 55-80 |
| Severe goal gap | 50 |
| High pressure | 45 |

Minimum threshold: score ≥ 30 to emit.

### CX3: Goal Behavior Gap Analyzer (NEW ENGINE)
**File:** `apps/cos/intelligence/goal_gap_analyzer.py`
**Entry:** `analyze_goal_behavior_gaps(user, now) → list[dict]`
**Format:** `format_goal_gaps_block(gaps) → str`
**Injected:** Every CoS context
**Token Budget:** ~150 tokens max
**Performance:** < 10ms (bounded queries per goal, max 3 goals)

Domain-specific analyzers:
- **Fitness:** WorkoutSession frequency vs target (e.g., "3x/week")
- **Faith:** UserReadingProgress daily completion vs target
- **Journal:** JournalEntry frequency vs target
- **Weight:** Current WeightEntry vs target extracted from goal text
- **Generic:** Milestone completion pace vs deadline

Risk levels: high (≤-60%), moderate (≤-30%), low (≤-15%)

### CX4: Temporal Execution Matching
**File:** `apps/cos/context/temporal_matcher.py`
**Entry:** `compute_execution_windows(user, now, cos_context) → str`
**Injected:** Every CoS context
**Token Budget:** ~100 tokens max
**Performance:** < 5ms

Matches unfinished high-priority tasks to available time windows:
1. Gets busy blocks (calendar events + architecture blocks)
2. Merges overlapping blocks
3. Finds free windows ≥30 min between now and 9 PM
4. Matches highest-priority overdue/due-today tasks to earliest windows

### CX5: Diagnostic Context Expansion
**File:** `apps/cos/context/diagnostic_context.py`
**Entry:** `is_diagnostic_query(message) → bool`
**Context:** `build_diagnostic_context(user, now, message) → str`
**Injected:** Only on diagnostic "why" queries (message-level, not context-level)
**Token Budget:** ~200 tokens max
**Performance:** < 8ms

Trigger phrases: "why am I", "what's going wrong", "struggling with", "can't seem to", "keep failing", etc.

Cross-domain signals gathered:
- Sleep (avg hours, low days)
- Exercise (frequency + trend)
- Mood (from journal entries)
- Task completion (completed + overdue count)
- Medication adherence (% adherence)
- Stress markers (elevated resting HR)

Includes a reasoning instruction that tells the LLM to trace causal chains.

### CX6: Behavioral Forecast
**File:** `apps/cos/intelligence/behavior_forecast.py`
**Entry:** `compute_behavior_forecast(user, now, cos_context) → str`
**Injected:** Every CoS context
**Token Budget:** ~100 tokens max
**Performance:** < 8ms (with cached schedule load)

Predicts completion probability for tomorrow based on:
- 8-week lookback of daily behavior data
- Schedule load classification (light/moderate/heavy)
- Load-specific completion rates (e.g., "on heavy days, user works out 20% of the time")

Behaviors forecasted: Workout, Bible Reading, Journal Entry.

---

## Safety Directives

1. **Never break existing chat** — all CX modules wrapped in try/except
2. **No new models or migrations** — reads from existing tables only
3. **Bounded queries** — all queries have hard limits (MAX_TASKS=3, MAX_EVENTS=5, etc.)
4. **Token discipline** — each phase has a budget, total CX overhead < 600 tokens
5. **Performance** — total CX overhead < 15ms per request
6. **Graceful degradation** — missing data → empty string, never error

---

## File Inventory

| File | Phase | Type |
|------|-------|------|
| `apps/cos/context/__init__.py` | — | Package init |
| `apps/cos/context/specificity_block.py` | CX1 | Context builder |
| `apps/cos/context/signal_prioritizer.py` | CX2 | Signal scorer |
| `apps/cos/context/temporal_matcher.py` | CX4 | Task-window matcher |
| `apps/cos/context/diagnostic_context.py` | CX5 | Diagnostic expander |
| `apps/cos/intelligence/__init__.py` | — | Package init |
| `apps/cos/intelligence/goal_gap_analyzer.py` | CX3 | New engine |
| `apps/cos/intelligence/behavior_forecast.py` | CX6 | Forecast engine |
| `apps/cos/tests/test_cos_cx.py` | — | Test suite (38 tests) |
| `apps/core/ai_orchestrator/cos_context.py` | — | Wiring (CX1-4, CX6) |
| `apps/ai/personal_assistant.py` | — | Wiring (CX5) |

---

## Testing

```bash
# Run CX-specific tests
python3 manage.py test apps.cos.tests.test_cos_cx -v 2

# Run all CoS + AI tests for regression
python3 manage.py test apps.cos apps.ai.tests -v 1 --failfast
```

Test results at implementation: 38 CX tests pass, 939 total CoS+AI tests pass (0 failures).
