# Phase 5 — Governance Onboarding + Adaptive Authority

**Date:** 2026-02-19
**Status:** Complete

---

## Overview

Phase 5 transforms the Chief of Staff from a reactive scheduler into a governance-aware partner. It adds:

1. **Conversational Alignment Session** — A 4-stage + per-module classification flow that understands what the user values, how they define success, and what to protect under pressure.

2. **Consistency Monitor** — DriftPressure formula comparing declared importance vs. observed behavior.

3. **Strategy Selection** — 4 behavioral strategies (ALIGN, PROTECT, CHALLENGE, COMPRESS) that replace simple tone switching.

4. **Recalibration Loop** — Automatic reclassification conversations when a non-negotiable is repeatedly missed.

5. **Tomorrow Protection Pass** — 7 PM scheduled check that locks non-negotiables, detects overload, and moves flexible items.

6. **Language Rules** — Banned internal terminology, natural language only.

7. **Display Budget** — Max 6 items/day, priority slots for at-risk non-negotiables, 48h repeat suppression.

---

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Engine approach** | Extend CoS + governance layer | No new engines per spec; governance sits inside existing CoS pipeline |
| **Data storage** | GovernanceProfile + GovernanceAlignmentSession models | Separate from PersonalOperatingBlueprint to avoid field bloat |
| **DriftPressure location** | Computed on-demand (not cached) | Values change with each plan/block change; caching would stale quickly |
| **Strategy injection** | System prompt via `build_cos_context()` | Consistent with existing governance instructions pattern |
| **Alignment delivery** | Conversational (injected into LLM prompt) | Not a form/wizard — natural dialogue discovery |
| **Circular import avoidance** | Direct plan query in evaluator/selector | Avoid `build_cos_context()` → `strategy_selector` → `build_cos_context()` loop |

---

## Files Created

| File | Purpose |
|------|---------|
| `apps/core/ai_governance/__init__.py` | Package init |
| `apps/core/ai_governance/models.py` | GovernanceProfile + GovernanceAlignmentSession |
| `apps/core/ai_governance/consistency_evaluator.py` | DriftPressure computation |
| `apps/core/ai_governance/strategy_selector.py` | ALIGN/PROTECT/CHALLENGE/COMPRESS selection |
| `apps/core/ai_governance/alignment_session.py` | Conversational alignment flow handler |
| `apps/core/ai_governance/recalibration.py` | Recalibration loop for repeated violations |
| `apps/core/ai_governance/tomorrow_protection.py` | 7 PM protection pass |
| `apps/core/ai_governance/language_rules.py` | Banned terminology rules |
| `apps/core/ai_governance/display_filter.py` | 6/day display budget + 48h suppression |
| `apps/core/migrations/0073_phase5_governance_onboarding.py` | Database migration |
| `apps/core/tests/test_phase5_governance.py` | 36 tests |

## Files Modified

| File | Change |
|------|--------|
| `apps/core/models.py` | Import GovernanceProfile, GovernanceAlignmentSession |
| `apps/core/ai_orchestrator/cos_context.py` | Strategy injection + language rules in system prompt |
| `apps/ai/personal_assistant.py` | Alignment + recalibration injections in _generate_response() |
| `apps/core/ai_scheduler/scheduler_registry.py` | Register `run_tomorrow_protection_pass` |
| `apps/core/ai_scheduler/scheduler_runner.py` | Add `run_tomorrow_protection_pass()` runner |

---

## DriftPressure Formula

```
DriftPressure = (MissRate x ImportanceWeight)
              + GoalImpactScore      [0-30]
              + TimeSensitivity       [0-15]
              + CapacityAvailability  [0-20]
              - RecentResponsiveness  [0-25]
```

Clamped to 0-100. Higher = more intervention needed.

### Component Details

| Component | Range | Logic |
|-----------|-------|-------|
| MissRate x ImportanceWeight | 0-2.0 | NonNeg weight 2.0, Important 1.0, Flexible 0.3 |
| GoalImpactScore | 0-30 | Overdue goals: 15, due this week: 10, due this month: 5 |
| TimeSensitivity | 0-15 | NonNeg: 10, Important: 5, Flexible: 0 |
| CapacityAvailability | 0-20 | >80% cap: 20, >60%: 10, else: 0 |
| RecentResponsiveness | 0-25 | (accepted+adjusted)/total interventions x 25 |

---

## Strategy Selection Logic

```
if capacity < 50% AND commitment = non_negotiable AND miss >= 0.3:
    COMPRESS — Reduce duration, not frequency
elif drift_pressure >= 50 AND miss_rate >= 0.6:
    CHALLENGE — Direct, evidence-based confrontation
elif capacity >= 80% OR drift_pressure >= 40:
    PROTECT — Lock commitments, move flexible items
else:
    ALIGN — Light nudge, ask first
```

---

## Alignment Session Stages

| # | Stage | Question | Purpose |
|---|-------|----------|---------|
| 1 | core_values | "What does a genuinely good day look like?" | Understand values |
| 2 | success_definition | "When you feel like you nailed a week, what happened?" | Define success |
| 3 | chaos_protection | "When life gets chaotic, what do you refuse to give up?" | Identify anchors |
| 4 | top_three | "If you could only do 3 things tomorrow, what would they be?" | Force-rank priorities |
| 5 | module_classification | Per-module: NonNeg / Important / Flexible | Create GovernanceProfiles |

---

## Noise Budget (Display Layer)

| Rule | Value |
|------|-------|
| Max items displayed per day | 6 |
| Priority slots (non-negotiable at-risk) | 2 |
| Repeat suppression window | 48 hours |
| Critical items | Always pass through |

This sits ON TOP of the Phase 4 noise budget (12/day generation cap).

---

## Test Coverage

36 tests across 10 test classes:
- GovernanceProfileModelTest (4 tests)
- GovernanceAlignmentSessionTest (3 tests)
- DriftPressureTest (5 tests)
- StrategySelectionTest (5 tests)
- AlignmentSessionTest (5 tests)
- RecalibrationTest (5 tests)
- LanguageRulesTest (2 tests)
- DisplayFilterTest (3 tests)
- SchedulerRegistrationTest (2 tests)
- CosContextIntegrationTest (2 tests)
