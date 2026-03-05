# WLJ Engine & CoS Reference

**Auto-maintained document.** Updated whenever engines, CoS context, or intelligence pipeline changes are made.
**Last updated:** 2026-03-05

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Engine Inventory](#engine-inventory)
3. [Celery Beat & ISE Schedules](#celery-beat--ise-schedules)
4. [CoS Context Pipeline](#cos-context-pipeline)
5. [CoS Proactive Check-In System](#cos-proactive-check-in-system)
6. [Truth Layer Architecture (SAE → PIE → PRIE → PGE)](#truth-layer-architecture)
7. [Known Bugs & Gap Analysis](#known-bugs--gap-analysis)
8. [Recommended Fixes](#recommended-fixes)
9. [Key File Paths](#key-file-paths)

---

## Architecture Overview

Three-phase intelligence pipeline: **Interpretation → Execution → Post-Execution** with 50+ engines.

```
Phase 1 (Interpretation)        Phase 2 (Execution)          Phase 3 (Post-Execution)
├─ SUE (Semantic)               ├─ UAIO (Orchestrator)       ├─ SAE (State)
├─ SLCME (Memory)               ├─ Intent Engine              ├─ PIE (Insights)
├─ HTIE (Time)                  ├─ Execution Engine            ├─ PRIE (Predictions)
│                               ├─ Safety Engine               ├─ PGE (Guidance)
│                               └─ Action Router               ├─ GLOE (Learning)
│                                                              ├─ DBE (Daily Briefing)
│                                                              ├─ WIRE (Weekly Report)
│                                                              ├─ E3 (Explain)
│                                                              ├─ DNE (Delivery)
│                                                              ├─ ISE (Scheduler)
│                                                              ├─ IOCD (Observability)
│                                                              ├─ SAME (Monitoring)
│                                                              └─ Blueprint engines (11+)
```

**Central Truth Layer:** `UserState` model (SAE) — one JSON row per user, keyed by module. All engines SHOULD read from SAE, not raw tables.

---

## Engine Inventory

### Phase 1: Interpretation Engines

| Engine | File | Entry Point | Trigger | Purpose |
|--------|------|-------------|---------|---------|
| **SUE** Semantic | `apps/core/ai_semantics/semantic_engine.py` | `interpret()` | Request | Parse intent, extract entities, detect ambiguity |
| **SUE** Ambiguity | `apps/core/ai_semantics/ambiguity_engine.py` | `detect_ambiguity()` | Request | Detect ambiguous inputs |
| **SUE** Confidence | `apps/core/ai_semantics/confidence_engine.py` | `score_confidence()` | Request | Score interpretation confidence |
| **SLCME** Memory | `apps/core/ai_memory/memory_engine.py` | `resolve_context()` | Request | Resolve context via learned mappings |
| **SLCME** Learning | `apps/core/ai_memory/learning_engine.py` | `learn_mappings()` | Post-execution | Learn user context from interactions |
| **SLCME** Retrieval | `apps/core/ai_memory/retrieval_engine.py` | `retrieve_context()` | Request | Retrieve learned context |
| **SLCME** Confidence | `apps/core/ai_memory/confidence_engine.py` | `confidence_score()` | Request | Score memory retrieval confidence |
| **HTIE** Time | `apps/core/ai_orchestrator/time_pipeline.py` | `resolve_time_pipeline()` | Request | Resolve human time expressions |

### Phase 2: Execution Engines

| Engine | File | Entry Point | Trigger | Purpose |
|--------|------|-------------|---------|---------|
| **UAIO** Orchestrator | `apps/core/ai_orchestrator/orchestrator.py` | `process_user_input()` | Request | Main pipeline coordinator |
| **UAIO** Intent | `apps/core/ai_orchestrator/intent_engine.py` | `execute_intent()` | Request | Route intents to handlers |
| **UAIO** Execution | `apps/core/ai_orchestrator/execution_engine.py` | `execute_action()` | Request | Execute domain actions |
| **UAIO** Safety | `apps/core/ai_orchestrator/safety_engine.py` | `validate_action()` | Request | Safety validation |
| **UAIO** Action Router | `apps/core/ai_orchestrator/action_router.py` | `route_action()` | Request | Route enriched actions |

### Phase 3: Post-Execution Engines

| Engine | File | Entry Point | Trigger | Schedule | Inputs | Outputs |
|--------|------|-------------|---------|----------|--------|---------|
| **SAE** State | `apps/core/ai_state/state_engine.py` | `update_user_state()` | Post-execution + ISE 5m | N/A | Raw tables (all modules) | `UserState.state_data` (JSON) |
| **PIE** Insights | `apps/core/ai_insights/insight_engine.py` | `run_insights()` | Post-execution + ISE 5m | N/A | UserState + events | `Insight` model |
| **PIE** Notification | `apps/core/ai_insights/notification_engine.py` | `maybe_notify()` | Event | N/A | Insight severity | Notification queue |
| **PRIE** Predictions | `apps/core/ai_predictions/prediction_engine.py` | `generate_predictions()` | Post-execution + ISE 1h | N/A | UserState OR raw data | `Prediction` model |
| **PRIE** Trajectory | `apps/core/ai_predictions/trajectory_engine.py` | `compute_trajectory()` | Request | N/A | Historical data series | Regression results |
| **PGE** Guidance | `apps/core/ai_guidance/guidance_engine.py` | `generate_guidance()` | ISE 6h | Every 6h | SAE + PIE + PRIE | `GuidanceItem` model |
| **GLOE** Learning | `apps/core/ai_guidance_learning/learning_engine.py` | `update_learning_profile()` | Signal + ISE 6h | Every 6h | User interactions | `GuidanceLearningProfile` model |
| **DBE** Briefing | `apps/core/ai_briefing/briefing_engine.py` | `generate_daily_briefing()` | ISE 24h | Daily | All engines | `DailyBriefing` model |
| **WIRE** Weekly | `apps/core/ai_weekly_report/report_engine.py` | `generate_weekly_report()` | ISE 7d | Weekly | All engines | `WeeklyReport` model |
| **E3** Explain | `apps/core/ai_explain/explain_engine.py` | `ensure_explain_record()` | Post-store hook | N/A | Intelligence outputs | `ExplainRecord` model |
| **DNE** Delivery | `apps/core/ai_delivery/delivery_engine.py` | `deliver_due_notifications()` | ISE 10m | Every 10m | Notification queue | `DeliveredNotification` model |
| **ISE** Scheduler | `apps/core/ai_scheduler/scheduler_engine.py` | `run_scheduler_cycle()` | APScheduler/Celery | Every 5m | `ScheduledIntelligenceTask` | Triggers other engines |
| **IOCD** Observability | `apps/core/ai_observability/observability_engine.py` | `generate_daily_snapshot()` | ISE 24h | Daily | All engine metrics | `IntelligenceMetricsSnapshot` |
| **SAME** Monitoring | `apps/core/ai_observability/same_engine.py` | `run_same()` | Celery Beat 60s | Every 60s | Engine heartbeats | `OpsAnomaly`, `OpsNarrativeSnapshot` |

### Blueprint & Governance Engines

| Engine | File | Entry Point | Trigger | Schedule | Purpose |
|--------|------|-------------|---------|----------|---------|
| **Blueprint** | `apps/core/blueprint/engine.py` | `get_blueprint()` | Request | N/A | Read/update Personal Operating Blueprint |
| **Architecture** | `apps/core/blueprint/architecture_engine.py` | `build_tomorrow_plan()` | ISE 24h | Nightly (7 PM) | Build tomorrow's task plan |
| **Priority** | `apps/core/blueprint/priority_engine.py` | `compute_priorities()` | Request | N/A | Compute task priorities |
| **Alignment** | `apps/core/blueprint/alignment_engine.py` | `compute_alignment()` | Request | N/A | Measure goal alignment |
| **Drift** | `apps/core/blueprint/drift_engine.py` | `compute_drift_scores()` | ISE 6h | Every 6h | Compute commitment drift |
| **Pressure** | `apps/core/blueprint/pressure_engine.py` | `compute_pressure()` | ISE 6h | Every 6h | Forecast pressure/overload |
| **Deadline** | `apps/core/blueprint/deadline_engine.py` | `compute_deadline_snapshots()` | ISE 5m | Every 5m | Track upcoming deadlines |
| **Escalation** | `apps/core/blueprint/escalation_engine.py` | `escalate_anomalies()` | ISE 24h / SAME | Daily | Escalate aged anomalies |
| **Intervention** | `apps/core/blueprint/intervention_engine.py` | `generate_interventions()` | ISE 24h | Daily | Recommend protective actions |
| **Protective** | `apps/core/blueprint/protective_engine.py` | `run_protective_sweep()` | ISE 24h | Daily | Recompute protective recommendations |
| **Recovery** | `apps/core/blueprint/recovery_engine.py` | `compute_recovery_path()` | Request | N/A | Suggest recovery from drift |
| **Reflection** | `apps/core/blueprint/reflection_engine.py` | `queue_reflections()` | ISE 24h | Daily | Queue post-event reflections |

### Arbitration & Cross-Domain Engines

| Engine | File | Entry Point | Trigger | Schedule | Purpose |
|--------|------|-------------|---------|----------|---------|
| **UAL** Arbitration | `apps/core/ai_arbitration/arbitration_engine.py` | `arbitrate_intents()` | Request + ISE 5m | Every 5m | Arbitrate conflicting intents |
| **Capacity** | `apps/core/ai_arbitration/capacity_engine.py` | `compute_capacity()` | Request | N/A | Estimate user capacity |
| **CDCE** Cross-Domain | `apps/core/ai_cross_domain/cdce_engine.py` | `compute_correlations()` | ISE 6h | Every 6h | Detect cross-domain correlations |
| **EAE** Evidence | `apps/core/ai_eae/eae_engine.py` | `aggregate_evidence()` | Request | N/A | Aggregate multi-source evidence |
| **Persona** | `apps/core/ai_persona/persona_engine.py` | `select_persona()` | Request | N/A | Select coaching persona |
| **Relationship** | `apps/core/ai_relationships/relationship_engine.py` | `compute_relationship_drift()` | ISE 24h | Daily | Detect relational drift |

### Domain-Specific Engines

| Engine | File | Entry Point | Purpose |
|--------|------|-------------|---------|
| Health Insights | `apps/health/services/insight_engine.py` | Domain rules | Health metric insight rules |
| Body Comp Intelligence | `apps/health/services/body_composition_intelligence.py` | Compute trends | Body composition trends |
| Meals Intelligence | `apps/meals/services/advanced_intelligence.py` | Request | Meal planning intelligence |
| Meal Substitution | `apps/meals/services/substitution_engine.py` | Request | Meal substitution suggestions |

---

## Celery Beat & ISE Schedules

### Celery Beat (config/settings.py)

| Task | Schedule | Function |
|------|----------|----------|
| `run-same-cycle-every-60-seconds` | 60s | `apps.core.tasks.run_same_cycle_task` |
| `run-ise-cycle-every-300-seconds` | 5m | `apps.core.tasks.run_ise_cycle_task` |
| `cos-keepalive-every-30-seconds` | 30s | `apps.ai.tasks.cos_keepalive_task` |
| `health-nightly-summary-3am-utc` | crontab(3,0) | `health.build_nightly_health_summaries` |

### APScheduler Jobs (apps/core/jobs.py)

| Job | Schedule | Purpose |
|-----|----------|---------|
| `cleanup_soft_deletes()` | Weekly Sun 3AM UTC | Hard-delete soft-deleted records |
| `generate_faith_reminders()` | Daily 6AM UTC | Faith module reminders |
| `generate_health_reminders_morning()` | Daily 12PM UTC | Morning health reminders |
| `generate_health_reminders_evening()` | Daily 12AM UTC | Evening health reminders |
| `send_notification_digest()` | Daily 9:45AM UTC | Email digest |
| `compute_activity_patterns()` | Daily 7AM UTC | Activity pattern analysis |
| `generate_birthday_reminders()` | Daily 12PM UTC | Birthday/memorial reminders |
| `run_intelligence_scheduler()` | Every 5m | ISE scheduler cycle |

### ISE Registry (42+ Tasks — apps/core/ai_scheduler/scheduler_registry.py)

Key tasks by interval:

**Every 5 minutes:**
- `run_ual_synthetic` — UAL arbitration batch
- `run_sae_synthetic` — SAE state rebuild batch
- `run_pie_synthetic` — PIE insight batch
- `compute_deadline_snapshots` — Deadline tracking
- `deliver_cos_prompts` — CoS prompt delivery
- `deliver_protective_alerts` — Protective alert delivery

**Every 10 minutes:**
- `deliver_intelligence_notifications` — DNE delivery cycle

**Every 15 minutes:**
- `run_assistant_triggers` — Assistant trigger conditions

**Every 1 hour:**
- `run_prie_synthetic` — PRIE predictions batch

**Every 6 hours:**
- `update_learning_profiles` — GLOE learning
- `refresh_guidance` — PGE guidance
- `run_drift_scoring` — Drift computation
- `compute_weekly_pressure` — Pressure forecast
- `run_cdce_correlations` — Cross-domain correlations
- `schedule_cos_prompts` — CoS prompt scheduling

**Every 24 hours:**
- `generate_daily_briefings` — DBE briefings
- `generate_observability_snapshot` — IOCD metrics
- `run_architecture_pass` — Tomorrow's plan
- `queue_event_reflections` — Post-event reflections
- `detect_relational_drift` — Relationship drift
- `validate_predictions` — Prediction validation
- `run_protective_sweep` — Protective recommendations
- `update_escalation_states` — Escalation state machine

**Every 7 days:**
- `generate_weekly_reports` — WIRE reports
- `aggregate_quality_metrics` — ICQG quality

---

## CoS Context Pipeline

### Request Flow

```
User Message
  → AssistantChatView.post() [apps/ai/views.py:312]
    → PersonalAssistant.send_message() [apps/ai/personal_assistant.py:2266]
      ├─ 1. ECC Pre-Check (commitment contract)
      ├─ 2. Readiness Cache (try layered → flat → rebuild)
      ├─ 3. Context Resolution (SLCME)
      ├─ 4. Time Resolution (HTIE)
      ├─ 5. Semantic Understanding (SUE)
      ├─ 6. Intent Recognition (OpenAI)
      ├─ 7. Orchestrator Enrichment (enrich_and_execute)
      ├─ 8. _generate_response() with cos_context
      └─ 9. Post-Response Intelligence (async)
```

### Context Builder (12 Parallel Builders)

**Function:** `build_cos_context(user)` — `apps/core/ai_orchestrator/cos_context.py:1068`
Uses `ThreadPoolExecutor(max_workers=6)`.

| Builder | Function | Data Sources | Key Output Fields |
|---------|----------|--------------|-------------------|
| Blueprint & Governance | `_build_blueprint_and_governance()` | Blueprint, Persona | operating_style, protected_tiers, persona |
| Plan & Alignment | `_build_plan_and_alignment()` | ArchitecturePlan, Drift | capacity, alignment_score, drift_probability |
| Pressure & Deadlines | `_build_pressure_and_deadlines()` | PressureSnapshot, DeadlineSnapshot | weekly_pressure, deadline_snapshot |
| Health & Vitals | `_build_health_and_vitals()` | WeightEntry, HealthProfile, FastingSession, **medicine_utils** | weight, trend, fasting, **medication_adherence_state** |
| Calendar Events | `_build_calendar_events()` | CalendarEvent | events with time_status markers |
| Intelligence Signals | `_build_intelligence_signals()` | Insight, Prediction, Guidance | active insights/predictions/guidance |
| People & Mood | `_build_people_and_mood()` | JournalEntry, Relationships | mood_trends, relationship_signals |
| Loops & Events | `_build_loops_and_events()` | Goals, Tasks | open_loops, friction_gates |
| Strategy & Signals | `_build_strategy_and_signals()` | Strategic goals | strategy_snapshot |
| Image Analyses | `_build_recent_image_analyses()` | Vision analysis | recent_analyses |
| Meals | `_build_meals_context()` | FoodEntry | meals_context |
| Faith | `_build_faith_context()` | ReadingProgress | faith_context |

### System Prompt Assembly (Priority Order)

**Function:** `_generate_response()` — `apps/ai/personal_assistant.py:3515`

```
System prompt layers (highest priority first):
├─ 1. Calibration override
├─ 2. Recalibration injection
├─ 3. Governance alignment session
├─ 4. Governance instructions + personality
├─ 5. Learned user profile
├─ 6. format_cos_system_injection(cos_context) ← THE MAIN CONTEXT
├─ 7. Base prompt + coaching style + faith
├─ 8. Pending reflections
└─ 9. Greeting context
```

### CoS Context Injection Output

**Function:** `format_cos_system_injection()` — `cos_context.py:1560`

Outputs:
1. **OPERATIONAL INTELLIGENCE** preamble (honesty rule, link/list formatting)
2. **DAILY SCAN BRIEF** — COMPLETED / OUTSTANDING / TIME-SENSITIVE / RISK FLAGS
3. **Session mode** — DAILY_ORIENTATION vs LIGHT
4. **Schedule blocks** with [NOW], [SOON], [done], [MISSED] markers
5. **Protective flags, deadlines, pressure, relationship, health signals**

### Caching Strategy

| Cache Type | Key Pattern | TTL | Purpose |
|------------|-------------|-----|---------|
| Stable layer | `cos_ctx:stable:v1:{user_id}` | 5 min | Blueprint, governance, persona, permissions |
| Dynamic layer | `cos_ctx:dynamic:v1:{user_id}` | 45 sec | Calendar, mood, pressure, loops |
| Flat (fallback) | `cos_ctx:v1:{user_id}` | 45 sec | Full context (single key) |
| CoS keepalive | Celery Beat 30s | N/A | Pre-warms cache for active users |

---

## CoS Proactive Check-In System

### Check-In Types

| Type | Function | Trigger | Throttle |
|------|----------|---------|----------|
| Medicine (grouped) | `generate_grouped_medicine_check_in()` | `generate_health_reminders` command | 1 per time_of_day per day |
| Workout | `generate_workout_check_in()` | Daily check-in command | 1 per day |
| Journal | `generate_journal_check_in()` | Daily check-in command | 1 per day |
| Overdue Task | `generate_overdue_task_check_in(task)` | Daily check-in command | 1 per run |
| Busy Day Warning | `generate_busy_day_check_in(count)` | Daily if ≥5 items tomorrow | 1 per day |
| Pattern Observation | `generate_pattern_observation()` | Daily check-in command | 1 per run |
| Streak Acknowledgment | `generate_streak_acknowledgment()` | On milestone | 1 per activity |
| Birthday/Anniversary | `generate_birthday_greeting(event)` | Daily check-in command | 1 per event |

### Medicine Check-In Flow

```
APScheduler → generate_health_reminders (--medicine-only --time-period=morning)
  → For each user with proactive_checkins enabled:
    → Query MedicineSchedule + MedicineLog for today
    → Group by time_of_day (morning, evening, nightly)
    → Only doses PAST current_time in user's LOCAL timezone
    → generate_grouped_medicine_check_in(time_of_day, medicines, due_time)
      → Collects med_names = ', '.join(m.name for m, s in medicines)  ✓
      → Gets template: "Your {group} meds are due by {time}."  ✗ NO {names}!
      → Creates AssistantMessage with quick_replies
```

---

## Truth Layer Architecture

### Data Flow: Action → State → Intelligence

```
Action Execution (execution_engine.py)
  ↓
SAE Update (state_updater.py) → UserState.state_data[module]
  ↓
PIE (insight_engine.py) → Insight model (deduplicated)
  ↓
PRIE (prediction_engine.py) → Prediction model (deduplicated)
  ↓
PGE (guidance_engine.py) → GuidanceItem model (priority-ranked, ICQG-gated)
  ↓
DNE (delivery_engine.py) → DeliveredNotification (in-app / email / SMS)
```

### Intelligence Output Models

| Model | Table | Written By | Read By |
|-------|-------|-----------|---------|
| `UserState` | `core_user_state` | SAE state builders | PIE, PRIE, PGE, CoS (partially) |
| `Insight` | `core_ai_insight` | PIE insight_engine | PGE, CoS context, Daily Briefing |
| `Prediction` | `core_ai_prediction` | PRIE prediction_engine | PGE, CoS context |
| `GuidanceItem` | `core_ai_guidance_item` | PGE guidance_engine | DNE delivery, CoS context |
| `DailyBriefing` | `core_ai_daily_briefing` | DBE briefing_engine | User-facing briefing view |
| `WeeklyReport` | `core_ai_weekly_report` | WIRE report_engine | User-facing report view |
| `ExplainRecord` | `core_ai_explain_record` | E3 explain_engine | Transparency/audit |

### SAE State Structure

`UserState.state_data` JSON keyed by module:

| Module Key | Builder | Fields |
|------------|---------|--------|
| `health` | `build_health_state()` | weight_current, weight_trend, weight_entries_90d, body_fat_current, sleep_avg_7d, bp_systolic, bp_diastolic |
| `goals` | `build_goal_state()` | active_goal_count, next_deadline, completion_rate |
| `habits` | `build_habit_state()` | active_habit_count, longest_streak, avg_completion_rate |
| `journal` | `build_journal_state()` | last_entry, entry_frequency, mood_distribution |
| `faith` | `build_faith_state()` | reading_streak, last_scripture_read |
| `nutrition` | `build_nutrition_state()` | calorie_avg_7d, protein_avg_7d, macro_compliance |
| `fasting` | `build_fasting_state()` | rolling_7d_hours, avg_fast_duration, compliance_score |
| `fitness` | `build_fitness_state()` | workout_count_7d, total_volume, pr_count, strength_trend |
| `transformation` | `build_transformation_state()` | transformation_score, weight_trend_score, momentum_score |

---

## Known Bugs & Gap Analysis

### BUG 1: Medicine Names Not Passed to CoS

**Severity:** High — CoS says "meds due" but can't list which ones.

**Three gaps:**

| Gap | Location | Issue |
|-----|----------|-------|
| Template missing `{names}` | `apps/ai/assistant_intelligence.py` templates | `grouped_meds_due` template: `"Your {group} meds are due by {time}."` — no `{names}` placeholder despite names being collected |
| CoS context has no medicine names | `cos_context.py :: _build_health_and_vitals()` lines 306-319 | Only builds `medication_adherence_state` with counts (`total_scheduled`, `taken_today`, `adherence_pct`). No `pending_medicines` field |
| Daily scan brief has no names | `cos_context.py :: _build_daily_scan_brief()` lines 1431-1434 | Says "Medications: 2 dose(s) not yet taken" — no medicine names |

**Root cause:** `calculate_medicine_adherence()` in `apps/health/medicine_utils.py` returns only counts, not medicine details.

### BUG 2: False Routine/Task Completion Claims

**Severity:** High — CoS says "morning routine completed" without evidence.

**Two bugs in `cos_context.py`:**

| Bug | Location | Issue |
|-----|----------|-------|
| Daily scan brief | `cos_context.py:1404-1409` | `if ev.get('time_status') == 'past': completed_items.append(ev['title'])` — treats past-time events as completed without checking `CalendarEvent.status` |
| Schedule display | `cos_context.py:1760-1761` | Marks past-time events with `[done]` tag based purely on clock time |

**Root cause:** `time_status == 'past'` (temporal) is conflated with `status == 'completed'` (actual). `CalendarEvent.status` field exists and is properly maintained by `routine_service.py` but CoS never reads it.

### GAP 3: CoS Bypasses SAE Truth Layer

**Severity:** Medium — potential data drift.

| Component | File | Issue |
|-----------|------|-------|
| Goal Gap Analyzer | `apps/cos/intelligence/goal_gap_analyzer.py` | Queries raw tables (LifeGoal, WorkoutSession, etc.) directly |
| Diagnostic Context | `apps/cos/context/diagnostic_context.py` | Queries raw tables directly |

**Risk:** If SAE state_data diverges from raw data (timing, caching), CoS may present inconsistent information.

### GAP 4: Engine Output Layer — Options Assessment

**Question:** Do engines store results in a central daily record?

**Answer:** Partially. `UserState` (SAE) is the central snapshot, but:
- PIE, PRIE, PGE each have their own output tables
- CoS reads some engine outputs (Insight, Prediction, Guidance) but also queries raw tables directly
- No single "DailyIntelligence" rollup model exists

**Options:**

| Option | Description | Pros | Cons | Blast Radius |
|--------|-------------|------|------|-------------|
| **A: DailyIntelligence model** | New model populated by existing engines daily | Single query for full picture | New migration, new code | ~8 files |
| **B: Lightweight aggregator** | Reads existing engine outputs into daily snapshot | Reuses existing data | Still requires new model | ~5 files |
| **C: Truth adapter layer** (RECOMMENDED) | Enforce CoS reads SAE + engine outputs only; no raw table access | Minimal new code, fixes drift | Requires refactoring CoS context builders | ~4 files |

**Recommendation:** Option C — Refactor CoS context builders to use SAE and engine output models exclusively. Add medicine details to SAE health state.

---

## Recommended Fixes

### Fix 1: Add Medicine Names to CoS Context (3 files)

1. **`apps/health/medicine_utils.py`** — Add `get_pending_medicines(user)` that returns `[{name, dose, scheduled_time, time_of_day}]`
2. **`apps/core/ai_orchestrator/cos_context.py :: _build_health_and_vitals()`** — Call `get_pending_medicines()` and add `pending_medicines` field
3. **`apps/ai/assistant_intelligence.py`** — Update `grouped_meds_due` templates to include `{names}`: `"Your {group} meds ({names}) are due by {time}."`

### Fix 2: Fix False Completion Claims (1 file)

1. **`apps/core/ai_orchestrator/cos_context.py`**:
   - Line ~1405: Change `if ev.get('time_status') == 'past'` to check `ev.get('status') == 'completed'`
   - Line ~1760: Change `[done]` tag to only apply when `status == 'completed'`; past-but-uncompleted events should get `[MISSED]` or `[unconfirmed]`
   - Calendar query (line ~548): Include `status` field in the event dict returned

### Fix 3: Stop CoS Bypassing SAE (2 files)

1. **`apps/cos/intelligence/goal_gap_analyzer.py`** — Refactor to read from `UserState` instead of raw tables
2. **`apps/cos/context/diagnostic_context.py`** — Refactor to read from `UserState`

### Fix 4: Update Proactive Check-In Templates (1 file)

1. **`apps/ai/assistant_intelligence.py`** — All coaching style `grouped_meds_due` templates: add `{names}` placeholder

### Tests Required

- `apps/health/tests/test_medicine_utils.py` — Test `get_pending_medicines()` returns names
- `apps/core/tests/test_cos_context.py` — Test medicine names appear in context; test completion only for status=completed events
- `apps/ai/tests/test_proactive_checkins.py` — Test medicine names appear in check-in messages

---

## Key File Paths

### Core Pipeline

| File | Purpose | Lines |
|------|---------|-------|
| `apps/core/ai_orchestrator/cos_context.py` | CoS context builder (THE BIG ONE) | ~4,668 |
| `apps/core/ai_orchestrator/orchestrator.py` | Main orchestrator entry | ~288 |
| `apps/core/ai_orchestrator/commitment_contract.py` | ECC commitment tracking | ~1,678 |
| `apps/ai/personal_assistant.py` | Main assistant, send_message() | ~6,452 |
| `apps/ai/views.py` | Chat API endpoints | ~1,661 |
| `apps/ai/proactive_checkins.py` | Proactive check-in service | ~829 |
| `apps/ai/assistant_intelligence.py` | Coaching style templates | ~400 |
| `apps/ai/readiness_cache.py` | CoS context caching (Redis) | ~300 |

### Intelligence Engines

| File | Purpose |
|------|---------|
| `apps/core/ai_state/state_engine.py` | SAE — state management |
| `apps/core/ai_state/state_builder.py` | SAE — module state builders |
| `apps/core/ai_state/state_updater.py` | SAE — incremental update |
| `apps/core/ai_insights/insight_engine.py` | PIE — insight generation |
| `apps/core/ai_predictions/prediction_engine.py` | PRIE — predictions |
| `apps/core/ai_guidance/guidance_engine.py` | PGE — guidance |
| `apps/core/ai_scheduler/scheduler_engine.py` | ISE — scheduler |
| `apps/core/ai_scheduler/scheduler_registry.py` | ISE — 42+ task registry |
| `apps/core/ai_scheduler/scheduler_runner.py` | ISE — task runner functions |
| `apps/core/ai_observability/same_engine.py` | SAME — monitoring |
| `apps/core/ai_delivery/delivery_engine.py` | DNE — notification delivery |

### Blueprint & Governance

| File | Purpose |
|------|---------|
| `apps/core/blueprint/engine.py` | Blueprint read/update |
| `apps/core/blueprint/architecture_engine.py` | Tomorrow's plan |
| `apps/core/blueprint/drift_engine.py` | Commitment drift |
| `apps/core/blueprint/pressure_engine.py` | Pressure forecasting |
| `apps/core/blueprint/escalation_engine.py` | Anomaly escalation |
| `apps/core/blueprint/protective_engine.py` | Protective actions |

### Domain

| File | Purpose |
|------|---------|
| `apps/health/models.py` | Medicine, MedicineSchedule, MedicineLog models |
| `apps/health/medicine_utils.py` | Adherence calculations |
| `apps/life/models.py` | Task model (is_completed, completed_at) |
| `apps/life/services/routine_service.py` | Routine completion → CalendarEvent sync |
| `apps/calendar_engine/models.py` | CalendarEvent (status field) |

---

*This document is auto-maintained. Update it when changing engines, CoS context building, intelligence pipeline, or scheduling.*
