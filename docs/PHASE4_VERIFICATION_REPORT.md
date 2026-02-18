# Phase 4 — Verification & Wiring Report

**Date:** 2026-02-18
**Objective:** Verify all Phase 4 trackers are wired into production call sites. Add noise budget controls and backfill command.

---

## 1. Wiring Map — Call Sites

Every Phase 4 tracker/service is now wired into a production call site:

### Write-Side Wiring (Data Collection)

| Tracker | Call Site | File | Trigger |
|---------|----------|------|---------|
| **InsightEngagementTracker** | `InsightActionView.post()` | `apps/core/ai_insights/views.py` | User reads/dismisses an insight |
| **BriefingEngagementTracker** | `DashboardView.get_context_data()` | `apps/dashboard/views.py` | User views dashboard (daily briefing + weekly report) |
| **BriefingEngagementTracker** | `WeeklyReportDetailView.get_context_data()` | `apps/core/ai_weekly_report/views.py` | User views report detail page |
| **PredictionValidator** | `run_prediction_validation()` | `apps/core/ai_scheduler/scheduler_runner.py` | Scheduled daily via ISE |
| **InterventionEffectivenessTracker** | `run_intervention_effectiveness()` | `apps/core/ai_scheduler/scheduler_runner.py` | Scheduled daily via ISE |
| **LearningExtractor** | `AssistantChatView.post()` | `apps/ai/views.py` | After every user chat message |
| **Cross-Domain Rules** | `__init__.py` import | `apps/core/ai_insights/__init__.py` | Module import registers rules via `@register` |
| **Cross-Domain Scheduled Check** | `run_cross_domain_insights()` | `apps/core/ai_scheduler/scheduler_runner.py` | Scheduled every 6 hours via ISE |

### Read-Side Wiring (Data Consumption)

| Signal | Consumer | File | Effect |
|--------|----------|------|--------|
| **Confidence Adjustment** | `generate_predictions()` | `apps/core/ai_predictions/prediction_engine.py` | ±0.2 confidence on predictions based on accuracy history |
| **Escalation Speed Modifier** | `compute_intensity()` | `apps/core/blueprint/intervention_intensity.py` | ±15 points on intervention intensity score |
| **Preferred Briefing Length** | `generate_daily_briefing()` | `apps/core/ai_briefing/briefing_engine.py` | Concise mode skips optional sections (3-5) |
| **Feedback Profiles** | `build_cos_context()` | `apps/core/ai_orchestrator/cos_context.py` | Engagement/effectiveness injected into LLM context |
| **Learned Profile** | `build_cos_context()` | `apps/core/ai_orchestrator/cos_context.py` | User values/goals/frustrations injected into system prompt |
| **Tone Mode** | `format_cos_system_injection()` | `apps/core/ai_orchestrator/cos_context.py` | Strategic/Direct/Reflective mode instructions |
| **Insight Type Weights** | `InsightEngagementProfile` | `apps/core/ai_feedback/insight_tracker.py` | Available for PIE ranking (consumed via feedback_profiles) |

### ISE Scheduler Registry (3 new tasks)

| Task Name | Interval | Runner |
|-----------|----------|--------|
| `validate_predictions` | 24h | `run_prediction_validation()` |
| `evaluate_intervention_effectiveness` | 24h | `run_intervention_effectiveness()` |
| `run_cross_domain_insights` | 6h | `run_cross_domain_insights()` |

---

## 2. Noise Budget Rules

### New Module: `apps/core/ai_insights/noise_budget.py`

Caps insight generation to prevent user fatigue. Applied in `insight_engine.py` AFTER rule evaluation, BEFORE persistence.

| Cap | Limit | Scope | Bypass |
|-----|-------|-------|--------|
| Daily insight limit | 12 per user/day | All insights | Critical severity |
| 6-hour window limit | 5 per user/6h | All insights | Critical severity |
| Cross-domain daily limit | 4 per user/day | `cross_domain_*` insight types | Critical severity |
| Dedupe check | 1 active per dedupe_key | Per user | Dismissed insights don't block |

### Integration Point

```
insight_engine.py → run_insights() loop:
  1. Rule evaluation
  2. Confidence threshold check
  3. ★ Noise budget check (new) ← check_noise_budget()
  4. _upsert_insight()
  5. Notification
```

### Existing ICQG Integration (Unchanged)

- `filter_briefing_items()` — conflict detection + confidence threshold for DBE/WIRE
- `filter_guidance_candidates()` — repeat suppression + conflict detection for PGE
- `filter_delivery_candidates()` — confidence threshold for DNE

---

## 3. Backfill Approach

### New Command: `python manage.py backfill_phase4_engagement`

| Option | Default | Description |
|--------|---------|-------------|
| `--days` | 30 | Lookback window |
| `--dry-run` | False | Preview without writing |

### Backfill Sources

| Target | Source | Logic |
|--------|--------|-------|
| `BriefingEngagement` | `DailyBriefing` records | Creates "opened" event for each existing briefing |
| `BriefingEngagement` | `WeeklyIntelligenceReport` records | Creates "opened" event for each existing report |
| `InsightEngagement` | `Insight` with status=read/dismissed | Creates viewed/dismissed event per insight |
| `InterventionEffectivenessProfile` | `InterventionLog` with responses | Runs `evaluate_intervention_effectiveness()` per user |

### Deduplication

All backfill operations check for existing engagement records before creating new ones. Safe to run multiple times.

---

## 4. Test Summary

### New Test File: `apps/core/tests/test_phase4_verification.py`

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `CrossDomainRuleRegistrationTest` | 1 | Rules registered in PIE registry |
| `NoiseBudgetTest` | 7 | Daily cap, 6h cap, dedupe, cross-domain cap, critical bypass, dismissed bypass, budget status |
| `ConfidenceAdjustmentWiringTest` | 1 | PredictionAccuracyProfile → PRIE adjustment |
| `EscalationModifierWiringTest` | 1 | InterventionEffectivenessProfile → intensity modifier |
| `BriefingLengthWiringTest` | 1 | Preferred length → DBE concise mode |
| `SchedulerRegistrationTest` | 3 | 3 new tasks in ISE registry |
| **Total new tests** | **14** | |

### Full Phase 4 Test Count

| Module | Tests |
|--------|-------|
| `apps/core/ai_feedback/tests.py` | 17 |
| `apps/core/ai_learning/tests.py` | 14 |
| `apps/core/ai_insights/tests_cross_domain.py` | 11 |
| `apps/core/tests/test_phase4_cos.py` | 14 |
| `apps/core/tests/test_phase4_verification.py` | 14 |
| **Total Phase 4 tests** | **70** |

All 70 tests passing.

---

## 5. Files Modified (Verification Pass)

| File | Change |
|------|--------|
| `apps/core/ai_insights/__init__.py` | Import `rules_cross_domain` so `@register` fires |
| `apps/core/ai_insights/views.py` | Hook `record_insight_engagement()` into `InsightActionView` |
| `apps/core/ai_insights/insight_engine.py` | Hook noise budget check before persistence |
| `apps/dashboard/views.py` | Hook `record_briefing_opened()` for daily briefing + weekly report |
| `apps/core/ai_weekly_report/views.py` | Hook `record_briefing_opened()` for detail view |
| `apps/core/ai_scheduler/scheduler_registry.py` | Register 3 new scheduled tasks |
| `apps/core/ai_scheduler/scheduler_runner.py` | Add 3 runner functions |
| `apps/ai/views.py` | Hook `extract_learning()` after chat message |
| `apps/core/ai_predictions/prediction_engine.py` | Apply confidence adjustment from feedback loop |
| `apps/core/blueprint/intervention_intensity.py` | Apply escalation speed modifier from feedback loop |
| `apps/core/ai_briefing/briefing_engine.py` | Apply preferred briefing length from engagement profile |

## 6. Files Created (Verification Pass)

| File | Purpose |
|------|---------|
| `apps/core/ai_insights/noise_budget.py` | Noise budget caps + dedupe for insight engine |
| `apps/core/management/commands/backfill_phase4_engagement.py` | Backfill engagement signals from existing records |
| `apps/core/tests/test_phase4_verification.py` | 14 verification tests |
| `docs/PHASE4_VERIFICATION_REPORT.md` | This report |

---

## 7. Architecture Compliance

- No new engines created
- No new domains added
- No new URLs exposed to users
- No new API endpoints
- All changes are internal wiring of existing Phase 4 infrastructure
- All feedback hooks are wrapped in try/except (fail-open, never break production)
- Noise budget respects critical severity override
