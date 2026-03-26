# WLJ Engine & CoS Reference

**Auto-maintained document.** Updated whenever engines, CoS context, or intelligence pipeline changes are made.
**Last updated:** 2026-03-25 (SAE single-source-of-truth: dashboard cockpit reads from SAE, sleep/water/med/workout fields added to state builders)

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
| **PIE** Health Screenshot | `apps/core/ai_insights/health/sleep_analysis.py` | `analyze_sleep_data()` | Chat image upload | N/A | Vision API structured JSON + user context | CoS injection + `Insight` model |
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
| **SAME** Monitoring | `apps/core/ai_observability/same_engine.py` | `run_same()` | Celery Beat 60s | Every 60s | Engine heartbeats | `OpsAnomaly`, `OpsNarrativeSnapshot`, `wlj:ops:stream_payload` cache |
| **Maturity** Engine | `apps/core/ai_observability/maturity_engine.py` | `compute_all_maturity_scores()` | On-demand + daily snapshot | Daily | All engines + registry | `SystemMaturitySnapshot` |
| **AAFR** Telemetry | `apps/core/ai_orchestrator/execution_engine.py` | `_record_aafr()` | Every `execute_action()` call | Real-time | AI mutation outcomes | `AIActionMetric` |
| **PGS** Proactive Guidance | `apps/ai/proactive_checkins.py` | `run_proactive_guidance_scheduler()` | ISE 15m | Every 15m | Per-user time windows, feature flags | `AssistantMessage(is_proactive=True)` via DNE |

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
| Health Screenshot Analysis | `apps/core/ai_insights/health/sleep_analysis.py` | `analyze_sleep_data()` | PIE sleep screenshot interpretation (Vision API → deterministic analysis → CoS injection) |
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
| `operating-profiles-nightly-7am-utc` | crontab(7,0) | `apps.core.tasks.compute_operating_profiles_task` |
| `dashboard-v2-nightly-momentum-730am-utc` | crontab(7,30) | `dashboard_v2.compute_nightly_momentum` |
| `dashboard-v2-detect-celebrations-8am-utc` | crontab(8,0) | `dashboard_v2.detect_celebrations` |
| `dashboard-v2-expire-celebrations-9am-utc` | crontab(9,0) | `dashboard_v2.expire_celebrations` |
| `life-recalculate-task-priorities-6am-utc` | crontab(6,0) | `life.recalculate_task_priorities` |

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

### ISE Registry (43+ Tasks — apps/core/ai_scheduler/scheduler_registry.py)

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
- `run_proactive_guidance` — PGS: time-window check-in dispatch (medicine, workout, journal, overdue tasks, faith, finance, goals, relationships, patterns, birthdays, midday alignment, afternoon momentum, evening wrap)

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
      ├─ 6. Intent Recognition (OpenAI) + UI Context Grounding (page_context → domain preference)
      ├─ 7. Orchestrator Enrichment (enrich_and_execute)
      ├─ 8. _generate_response() with cos_context
      └─ 9. Post-Response Intelligence (async)
```

### Context Builder (19 Parallel Builders)

**Function:** `build_cos_context(user, scoped_builders=None)` — `apps/core/ai_orchestrator/cos_context.py:1068`
Uses `ThreadPoolExecutor(max_workers=6)`.

**Domain Scoping (Phase 5):** Builders are tagged in `_TAGGED_BUILDERS` (list of `(tag, fn)` tuples). When `scoped_builders` is a set of tag strings, only matching builders run. The deterministic router infers the message domain and calls `get_scoped_builders(domain)` to get the relevant set (domain-specific + core tags). Feature-flagged: `WLJ_DOMAIN_SCOPED_CONTEXT_ENABLED` (default False). When disabled or domain is ambiguous, all builders run (full backward compatibility).

**SAE Truth Layer:** `build_cos_context()` pre-loads `get_user_state(user)` into `user._sae_cache` so all builders share one DB hit for SAE reads. Builders read from SAE via `get_state_value()` / `get_module_state()` instead of raw ORM queries for domain state.

| Builder | Function | Data Sources | Key Output Fields |
|---------|----------|--------------|-------------------|
| Blueprint & Governance | `_build_blueprint_and_governance()` | Blueprint, Persona | operating_style, protected_tiers, persona |
| Plan & Alignment | `_build_plan_and_alignment()` | ArchitecturePlan, Drift | capacity, alignment_score, drift_probability |
| Pressure & Deadlines | `_build_pressure_and_deadlines()` | **SAE intervention** | weekly_pressure, deadline_snapshot |
| Health & Vitals | `_build_health_and_vitals()` | **SAE health/fitness**, FastingSession, medicine_utils | weight, trend, vitals, workouts, fasting, medication, **exercise_progress** (per-exercise e1RM trends & plateau status) |
| Calendar Events | `_build_calendar_events()` | CalendarEvent (live) | events with time_status markers |
| Intelligence Signals | `_build_intelligence_signals()` | Insight, Prediction, Guidance (engine output) | active insights/predictions/guidance, **intelligence_status** (full/partial/degraded), intelligence_sources_failed |
| **Signal Arbitration** (v1.0) | `_rank_top_signals()` (POST-ASSEMBLY) | All intelligence signals + drift_score + CoSSituationState | **ranked_signals**: top_signal (tier, delivery_mode, arbitration_score), supporting_signals (0-2), suppression_reason. 6 tiers, tier-first comparison, surfacing gate. Falls back to flat lists on failure. |
| People & Mood | `_build_people_and_mood()` | JournalEntry, Relationships | mood_trends, relationship_signals |
| Loops & Events | `_build_loops_and_events()` | **SAE goals/intervention/feedback/life_events** | open_loops, friction_gates |
| Strategy & Signals | `_build_strategy_and_signals()` | Strategic goals | strategy_snapshot |
| Image Analyses | `_build_recent_image_analyses()` | **SAE scan** | recent_analyses |
| Meals | `_build_meals_context()` | **SAE meals**, HouseholdMembership | meals_context |
| Faith | `_build_faith_context()` | **SAE faith** | faith_context |
| Situational Awareness (v8/v8.1) | `_build_situational_awareness_context()` | DailyHealthSummary, WeightEntry, JournalEntry, AssistantMessage, HabitGoal, medicine_utils, streak_service, PersonalOperatingBlueprint, GovernanceProfile, NonNegotiable | momentum_signals, drift_signals, one_off_sensitive_domains, emotional_context, user_priority_model |
| **Finance** (Phase 7.3) | `_build_finance_context()` | FinancialGoal, Budget | active goals with progress %, budgets near/over limit |
| **Brain Training** (Phase 7.3) | `_build_brain_training_context()` | UserOverallStats, DailyStats | streak, sessions, favorite game, 7-day history |
| **Capture** (Phase 7.3) | `_build_capture_context()` | PendingCapture, CaptureEntry | pending uploads, recent ready items |
| **Medical** (Phase 7.3) | `_build_medical_context()` | LabResult, LabPanel | abnormal lab results (90 days), recent panels |
| **Purpose** (Phase 7.3) | `_build_purpose_context()` | LifeGoal, HabitGoal, HabitEntry | active goals with deadlines, habit weekly completion rates |
| **Operating Profile** (POC v2) | `_build_operating_profile()` | UserOperatingProfile (pre-computed) | productive_windows, deferral_patterns, momentum_phase, behavior_drift. Per-dimension confidence gates (0.60/0.60/0.40), confidence-scaled language, drift detection between computations |

### System Prompt Assembly (Priority Order)

**Function:** `_generate_response()` — `apps/ai/personal_assistant.py:3515`

```
System prompt layers (highest priority first):
├─ 1. Calibration override (v4: SUPPRESSED for functional queries — see below)
├─ 2. Recalibration injection
├─ 3. Governance alignment session
├─ 4. Governance instructions + personality
├─ 5. Learned user profile
├─ 6. format_cos_system_injection(cos_context) ← THE MAIN CONTEXT
│     └─ v4: Data State Snapshot moved to END (highest recency weight)
│     └─ v5: RESPONSE QUALITY RULES + CoS Voice + Missing Data Framing
│     └─ Today State: CURRENT FOCUS + NUDGE GUIDANCE + CONVERSATION AWARENESS
│     └─ v6: Consolidated CHIEF OF STAFF OPERATIONAL RULES (8 rules)
│     └─ v7: MANDATORY CONTEXT EVALUATION (8 steps — added STEP 8: EVALUATE INTELLIGENCE SIGNALS)
│     └─ v7: PROACTIVE INTELLIGENCE directive (priority-ranked signal surfacing)
│     └─ v8: SITUATIONAL AWARENESS SUMMARY (pattern-aware guidance rules)
├─ 7. Executive briefing + conversation memory (rolling summary)
├─ 8. Semantic memory retrieval (Phase 7.1: query-relevant past conversations)
├─ 9. Correction record retrieval (Phase 7.1: [CORRECTED] past mistakes)
├─ 10. Base prompt + coaching style + faith
├─ 11. Pending reflections
└─ 12. Greeting context
```

### v4 Calibration Suppression (2026-03-07)

**Problem:** When calibration is active (stage not complete, not paused), `build_calibration_system_injection()` injects ~6000 chars with "MANDATORY OVERRIDE — GETTING TO KNOW YOU SESSION". This conflicts with check-in/operational data — the LLM sees "your ONLY job is calibration" AND "give a briefing", and fabricates data (e.g., "3 of 5 tasks" when only 1 exists).

**Fix:** `_generate_response()` now detects "functional queries" before assembling priority layers. If the message is a functional query, calibration injection is skipped entirely. Only pure calibration responses (statements answering calibration questions) still get the injection.

**Detection logic** (`_is_functional_query`):
- Message contains `?`
- Message contains question words: what, how, why, when, where, which
- Message contains imperative verbs: tell me, remind me, encourage, explain, help me, show me
- Message matches any `CHECKIN_PATTERNS` entry

**CHECKIN_PATTERNS** (v4 expansion): Added 15+ advisory/planning patterns including `'structure my day'`, `'biggest improvement'`, `'highest impact'`, `'if you were my chief of staff'`, `'what would improve my life'`, `'top priority'`, `'where should i start'`, etc.

### v4 Data State Snapshot (2026-03-07)

**Change:** `_build_data_state_snapshot()` now includes `active_tasks`, `completed_tasks_today` counts, and `non_negotiable_skip_streaks` count (v5). The snapshot is injected at the END of `format_cos_system_injection()` (just before "END SITUATIONAL AWARENESS") for maximum recency weight — LLMs weight later-appearing context more heavily.

**Grounding rules:** Snapshot includes "ABSOLUTE GROUNDING RULES" that instruct the LLM to use exact counts or say "no data logged" — never estimate or infer. When NN skip streaks > 0, a "NON-NEGOTIABLE COMMITMENT AWARENESS" section instructs the LLM to approach with supportive coaching.

### v5 Pipeline Routing Fix + Voice Enforcement (2026-03-07)

**Problem:** `needs_web_search()` in `web_search_service.py` had overly broad regex that caught personal/CoS questions (e.g., "How should I structure my day?") and routed them to gpt-4o-mini with NO CoS context. Root cause of persistent Eisenhower Matrix responses.

**Fix:**
1. **PERSONAL_DATA_EXCLUSIONS** — 18 new regex patterns in `web_search_service.py` prevent personal/advisory questions from being intercepted by the web search path.
2. **Guard in `_generate_response()`** — Skip web search when personal data query already detected.
3. **RESPONSE QUALITY RULES** — CoS voice enforcement, missing-data framing ("not logged yet" instead of "unable to access"), knowledge response grounding.

**Files changed:** `apps/ai/web_search_service.py`, `apps/ai/personal_assistant.py`, `apps/core/ai_orchestrator/cos_context.py`

**Evaluation report:** `docs/CoSEvaluation_v5.md`

### v6 Operational Tuning — Decision Mode + Briefing Format (2026-03-07)

**Changes:** Consolidated all prompt rules into single `CHIEF OF STAFF OPERATIONAL RULES (v6)` block with 6 rules:

| Rule | Purpose | Key Behavior |
|------|---------|-------------|
| RULE 1 | No Generic Productivity Advice | Eisenhower Matrix, Pomodoro explicitly forbidden |
| RULE 2 | Chief of Staff Voice | 9 banned generic assistant phrases |
| RULE 3 | Missing Data Framing | "not logged yet" + actionable tracking link |
| RULE 4 | Decision Mode | Situation→Assessment→Recommendation→Next Step for "should I..." |
| RULE 5 | Operational Briefing Format | Goals→Actions→Tasks→Overdue→Maintenance→Recommendation |
| RULE 6 | Knowledge Response Grounding | Acknowledge missing data→provide knowledge→suggest tracking |
| RULE 7 | Reinforcement Mode | SATISFIED domain + signal → scripture/encouragement, NOT action |

**RULE 0 update (2026-03-19):** Added MODE AWARENESS (section D) — Action Mode vs Reinforcement Mode. Action Mode: primary recommendations from action priorities list, reinforcement permitted for SATISFIED domains. Reinforcement Mode: all domains satisfied, no new actions, focus on meaning/encouragement/scripture.

**Domain State Classification (2026-03-19):** Each domain is classified as ACTIONABLE (not completed, eligible for recommendation), SATISFIED (completed today, blocked from recommendations but eligible for reinforcement), or IRRELEVANT (not applicable). Classification drives Response Mode selection and RULE 7 eligibility. Scripture reinforcement queries `ScriptureVerse.contexts` against active emotional signals (stress→anxiety/worry/stress, declining mood→sadness/difficulty, positive→gratitude/growth).

**RULE 8 (2026-03-20):** Response Rules by Question Type — pattern-matched response guidance for "Did I...?", "How's my day?", "What should I do?", "I just did X", and general chat. Ensures Beth answers definitively from Truth State rather than hedging.

**Today State Enhancements (2026-03-20):**
- **Routine truth fix:** `_build_routine_state()` was reading wrong dict keys (`total`/`completed` instead of `total_count`/`completed_count` from `_routine_internal.py`), causing routines to always show 0/0. Fixed.
- **Faith bridge:** New `_bridge_routine_to_faith()` — when a routine item named "Prayer Time" or "Bible Reading" is completed in RoutineLog, it propagates to the faith domain. Prevents the split where routine shows "Prayer: DONE" but faith shows "NOT DONE".
- **Current Focus block:** Surfaces `action_priorities[0]` as a dedicated CURRENT FOCUS section in the system prompt. No new computation — reads existing action priorities.
- **Nudge Guidance block:** Per-domain nudge hints based on `_classify_domain_states()`. ACTIONABLE → "gently mention", SATISFIED → "reinforce the win", IRRELEVANT → omit.
- **Conversation Awareness directive:** Rules for handling user claims ("I just did X") vs truth state, and tone-matching from conversation context.
- **CoS voice upgrade (RULE 2):** Added warmth/authority voice markers, humanized data language ("knocked out 3 of 4" vs "75% completion"), banned system-speak phrases ("based on your data", "according to your logs").

**Additional v6 changes:**
- **Mandatory Context Evaluation** expanded to 6 steps (from 4) — now explicitly checks tasks due/overdue, outstanding commitments, missing data domains
- **Anti-template test** strengthened: "does it reference the user's actual task count, workout status, goal state, or time context? If not, rewrite."
- **`_is_personal_reflection()` rewritten** — strategic exclusions (`?`, "should I", "improve", etc.) prevent strategic questions from being misclassified as emotional reflections. Now requires phrase-level matching ("I feel ", "I'm struggling") instead of single-word triggers.
- **SECTION 8** — added "Eisenhower Matrix", "Pomodoro Technique" as explicitly prohibited; banned decision-mirroring and empathy templates for strategic questions.

**Files changed:** `apps/ai/personal_assistant.py`, `apps/core/ai_orchestrator/cos_context.py`

**Evaluation report:** `docs/CoSEvaluation_v6.md` (projected ~7.0-7.5/10; full eval pending API quota reset)

### v7+v7.1 Proactive Daily Executive Briefing Engine (2026-03-07)

**Change:** First proactive intelligence behavior — CoS automatically generates a Daily Executive Briefing when the user opens the chat interface.

**Architecture:**
```
User opens chat → loadHistory() → maybeTriggerBriefing()
  → POST /assistant/api/briefing/
  → PersonalAssistant.generate_proactive_briefing()
    → Cooldown check (last_briefing_at timestamp, 4-hour window)
    → Idempotency check (recent proactive state_assessment within 2 min)
    → _generate_response("briefing") ← FULL CoS PIPELINE
    → Save as AssistantMessage(is_proactive=True)
```

**v7.1 Hardening:**
- Timestamp-based cooldown (`last_briefing_at` ISO, not just date)
- Server-side idempotency (2-minute dedup)
- Synthetic message leakage prevention ("SYSTEM-INITIATED DAILY ORIENTATION")
- Frontend trigger safety (`briefingDrawerOpen` + `briefingRequested` flags)
- Delivery context metadata (`delivery_reason`, `generated_at`)
- Low-data day handling (goals + routines + missing tracking)

**Files changed:** `apps/ai/personal_assistant.py`, `apps/ai/views.py`, `apps/ai/urls.py`, `templates/components/chat_widget.html`

**New endpoint:** `POST /assistant/api/briefing/` → `ProactiveBriefingView`

**New endpoint (v8 — Adaptive CoS Presence):** `POST /assistant/api/session-start/` → `SessionStartView`
- Deterministic, no LLM. Returns structured JSON: briefing, lightweight_alignment, drift_intervention, or none.
- Reads pre-computed data only (DriftScore, execution truth, today engine).
- Auto-completes wake_up on first-of-day via `auto_complete_wakeup()`.

**New: Interaction Awareness** (`apps/ai/executive_briefing.py`):
- `record_interaction_depth()` — post-response hook tracks deep vs shallow interactions.
- `build_lightweight_alignment()` — compressed briefing when deep interaction within 90 min.
- `alignment_snapshot` in conversation metadata — captures execution truth state at alignment time.

**New: Assertiveness Preference** (`apps/users/models.py`):
- `UserPreferences.assistant_assertiveness` — gentle / firm_respectful / direct.
- Adjusts PGS nudge scoring (0.7x / 1.0x / 1.3x) and cooldown timing (1.5x / 1.0x / 0.7x).

**Enhanced PGS generators** (`apps/ai/proactive_checkins.py`):
- `generate_midday_alignment_for_user()` — now uses execution truth + today engine (slipping items, next action).
- `generate_evening_wrap_for_user()` — now uses execution truth (explicit misses, med adherence).

**Evaluation report:** `docs/CoSEvaluation_v7.md`

### CoS Context Injection Output

**Function:** `format_cos_system_injection()` — `cos_context.py:1560`

Outputs:
1. **OPERATIONAL INTELLIGENCE** preamble (honesty rule, link/list formatting, **insight-first rule**)
2. **DAILY SCAN BRIEF** — COMPLETED / OUTSTANDING / TIME-SENSITIVE / RISK FLAGS
3. **Session mode** — DAILY_ORIENTATION vs LIGHT (situation-aware: 8 modes)
4. **DAILY CONTEXT SUMMARY** (Phase 7.5) — Synthesized narrative: completed commitments, missed commitments, compensatory activity, goal momentum trends, signal highlights
5. **CONVERSATIONAL RESPONSE MODE** (Phase 7.5) — Keyword-detected: Reflection / Planning / Check-In coaching directives
6. **Schedule blocks** with [NOW], [SOON], [done], [MISSED] markers
7. **SIGNAL INTERPRETATION SUMMARY** (Phase 7.5) — Signals grouped by strength: Strong (≥0.7), Moderate (0.4-0.7), Needs Attention (<0.4)
8. **COMMITMENT GAP ANALYSIS** (Phase 6) — Missed commitments, partial offsets, compensatory reasoning rules
9. **Protective flags, deadlines, pressure, relationship, health signals**
10. **HEALTH SCREENSHOT ANALYSIS (PIE)** — When user uploads health screenshot

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
| Medicine (grouped) | `generate_grouped_medicine_check_in()` | PGS (all active hours) | 1 per time_of_day per day |
| Workout | `generate_workout_check_in()` | PGS midday | 1 per day |
| Journal | `generate_journal_check_in()` | PGS evening | 1 per day |
| Overdue Task | `generate_overdue_task_check_in(task)` | PGS midday | 1 per run |
| Busy Day Warning | `generate_busy_day_check_in(count)` | PGS evening | 1 per day |
| Pattern Observation | `generate_pattern_observation()` | PGS afternoon | 1 per run |
| Birthday/Anniversary | `generate_birthday_greeting(event)` | PGS morning | 1 per event |
| NN Skip | `generate_nn_skip_check_in(task)` | PGS midday | 1 per day |
| Faith Reading Gap | `generate_faith_reading_check_in(plan, days)` | PGS morning | 4h throttle |
| Faith Prayer | `generate_faith_prayer_check_in(count)` | PGS morning | 4h throttle |
| Finance Budget | `generate_finance_budget_check_in(budget, pct, days)` | PGS afternoon | 4h throttle |
| Finance Goal | `generate_finance_goal_check_in(goal, stalling_days)` | PGS afternoon | 4h throttle |
| Relationship Drift | `generate_relationship_drift_check_in(drift_alert)` | PGS evening | 4h throttle |
| Goal Deadline | `generate_goal_deadline_check_in(goal, days_until)` | PGS afternoon | 4h throttle |
| Goal Stalling | `generate_goal_stalling_check_in(goal, days_stalled)` | PGS afternoon | 4h throttle |
| Habit Streak | `generate_habit_streak_check_in(habit, streak, is_break)` | PGS afternoon | 4h throttle |
| Journal Concern | `generate_journal_concern_check_in(concern, count)` | PGS afternoon | 4h throttle |
| Journal Gap | `generate_journal_gap_check_in(days_since)` | PGS afternoon | 4h throttle |
| **Midday Alignment** | `generate_midday_alignment_for_user(user)` | PGS midday (weekdays) | 1 per day |
| **Afternoon Momentum** | `generate_afternoon_momentum_for_user(user)` | PGS afternoon (weekdays) | 1 per day |
| **Evening Wrap** | `generate_evening_wrap_for_user(user)` | PGS evening | 1 per day |

### PGS Time Window Dispatch

```
ISE (every 15m) → run_proactive_guidance_scheduler()
  → _get_proactive_users() — AI + PA consent + proactive_checkins enabled
  → For each user:
    → get_user_now(user) → local hour + is_weekend
    → Quiet hours (<7 or ≥22): skip
    → _dispatch_for_window(user, prefs, hour, is_weekend):
      Morning (7–9):  medicine, birthday, faith
      Midday (10–12): medicine, workout, overdue, nn_skip, midday_alignment (weekday)
      Afternoon (13–16): medicine, goals, journal_intel, patterns, finance, afternoon_momentum (weekday)
      Evening (17–21): medicine, journal, busy_day, relationships, evening_wrap
    → All generators dedup internally (1/type/day) + InteractionThrottler (3/hour max)
    → Messages route through DNE for multi-channel delivery
```

---

## Truth Layer Architecture

### Data Flow: Action → State → Intelligence

```
Action Execution (execution_engine.py)
  ↓
SAE Update (state_updater.py) → UserState.state_data[module]
  ↑ also triggered by post_save/post_delete signals (ai/signals.py, dashboard/signals.py)
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
| `SystemMaturitySnapshot` | `core_systemmaturitysnapshot` | Maturity engine | Command Center dashboard, trend analysis |

### SAE State Structure

`UserState.state_data` JSON keyed by module:

| Module Key | Builder | Fields |
|------------|---------|--------|
| `health` | `build_health_state()` | weight_current, weight_trend, weight_entries_90d, body_fat_current, sleep_avg_7d, **sleep_avg_hours_7d, sleep_good_nights_7d, sleep_consistency_score**, bp_systolic, bp_diastolic, heart_rate_avg_7d, glucose_avg_7d, blood_oxygen_avg_7d, heart_rate_events_7d, weight_goal, weight_goal_unit, weight_goal_target_date, weight_goal_remaining, weight_goal_on_track, **water_avg_oz_7d, water_good_days_7d, water_tracked_days_7d, water_goal_oz, water_consistency_score** |
| `goals` | `build_goal_state()` | active_goal_count, next_deadline, completion_rate |
| `habits` | `build_habit_state()` | active_habit_count, longest_streak, avg_completion_rate |
| `journal` | `build_journal_state()` | last_entry, entry_frequency, mood_distribution |
| `faith` | `build_faith_state()` | reading_streak, last_scripture_read, answered_prayers, recent_prayer_titles, urgent_prayers, bible_plan_name |
| `nutrition` | `build_nutrition_state()` | calorie_avg_7d, protein_avg_7d, macro_compliance |
| `fasting` | `build_fasting_state()` | rolling_7d_hours, avg_fast_duration, compliance_score |
| `fitness` | `build_fitness_state()` | workout_count_7d, total_volume, pr_count, strength_trend, workout_calories_7d, workout_minutes_7d, workout_avg_hr_7d, workout_distance_7d, recent_workouts, **workout_adherence_score, workout_completed_7d, workout_expected_7d, workout_missed_7d** |
| `transformation` | `build_transformation_state()` | transformation_score, weight_trend_score, momentum_score |
| `meals` | `build_meals_state()` | pantry_item_count, expiring_item_names, has_dinner_planned, dinner_recipe |
| `intervention` | `build_intervention_state()` | override_frequency_14d, override_count_10d, pending_friction_gates, deferrals_7d, renegotiation_patterns, tier1_skip_patterns, consecutive_tier1_skips |
| `feedback` | `build_feedback_state()` | insight_engagement, briefing_open_rate, preferred_briefing_length, intervention_effectiveness, escalation_modifier |
| `life_events` | `build_life_events_state()` | approaching_events |
| `scan` | `build_scan_state()` | recent_analyses |
| `governance` | `build_governance_state()` | declared_priorities, drift_scenario_count_14d |
| `tasks` | `build_task_state()` | task_commitment_summary (nn totals, 7d counts, consistency_score), nn_skip_streaks (top 5), active_tasks_by_level, overdue_nn_count |

---

## Domain Capability Registry (Phase 3)

**Location:** `apps/core/domain_registry/`

Auto-discovered at startup via `CoreConfig.ready()` → `autodiscover()`. Each domain app registers a `DomainCapability` descriptor in its `capabilities.py`.

### Registered Domains (10)

| Domain | App | Intent Types | Proactive Signals | Coverage |
|--------|-----|-------------|-------------------|----------|
| health | apps.health | 8 | vitals_alert, medication_due, workout_reminder | 100% |
| medical | apps.medical | 2 | appointment_due | 80% |
| journal | apps.journal | 3 | mood_trend, journaling_streak | 80% |
| faith | apps.faith | 4 | bible_plan_behind, prayer_reminder | 100% |
| life | apps.life | 5 | task_overdue, routine_missed | 80% |
| purpose | apps.purpose | 4 | goal_stalling, habit_streak_break | 80% |
| finance | apps.finance | 3 | budget_threshold, goal_milestone | 80% |
| meals | apps.meals | 2 | pantry_expiring | 60% |
| brain_training | apps.brain_training | 1 | session_reminder | 60% |
| capture | apps.capture | 0 | unprocessed_captures | 60% |

**Key functions:**
- `registry.get_coverage_summary()` — Returns all domains with coverage scores
- `registry.get_domains_with_signal(signal)` — Find domains by proactive signal
- `registry.get_all_intent_types()` — All registered intent types across domains
- `management/commands/audit_domains.py` — CLI audit tool

### CoS Integration

`cos_context.py :: _build_domain_coverage()` injects domain coverage data into CoS context. The Command Center dashboard reads this via `registry.get_coverage_summary()`.

---

## System Maturity Engine (Phase 5+6)

**Location:** `apps/core/ai_observability/maturity_engine.py`

6-dimension scoring system (0-100 each) with weighted overall:

| Dimension | Weight | Data Sources |
|-----------|--------|-------------|
| Infrastructure | 0.20 | EngineRun health (COAS heartbeat) |
| Intelligence | 0.20 | Memory utilization, proactive delivery, domain coverage |
| Safety | 0.25 | Error rates, Learning Mode status |
| Domain Coverage | 0.15 | Domain Registry coverage scores |
| Life Impact | 0.20 | Goal completion, task completion, engagement |
| **Overall** | — | Weighted average of above |

### Persistent Snapshots

`SystemMaturitySnapshot` model stores daily scores + JSON details for each dimension. Functions:
- `create_daily_snapshot(user)` — Creates/updates daily record
- `generate_recommendations(scores)` — Rule-based improvement suggestions
- `get_trend_data(days=30)` — Historical score data for charting
- `detect_regressions(threshold=10)` — Flags >10pt drops in 48 hours

### Command Center Integration

`AdminDashboardView` displays: maturity score cards (color-coded), domain coverage table, proactive stats (7-day), regressions (red), improvement recommendations (priority-colored).

---

## Known Bugs & Gap Analysis

### BUG 1: Medicine Names Not Passed to CoS — FIXED (2026-03-06)

**Severity:** High — CoS says "meds due" but can't list which ones.

**Fix:** Added `pending_medications` list to CoS context in `_build_health_and_vitals()`. Each entry has `name`, `dose`, `scheduled_time`, `time_of_day`, `status` (taken/overdue/upcoming). Daily scan brief and schedule display now show medicine names. Executive briefing HEALTH GATE also includes medicine names in overdue/upcoming messages.

**Remaining gap:** `assistant_intelligence.py` template still missing `{names}` placeholder — lower priority since CoS context now has the data.

### BUG 2: False Routine/Task Completion Claims — FIXED (2026-03-06)

**Severity:** High — CoS says "morning routine completed" without evidence.

**Fix:** Calendar event builder now queries `status__in=['scheduled', 'completed']` and adds `actual_status` field to event summaries. Daily scan brief only counts events as COMPLETED when `actual_status == 'completed'`. Schedule display shows `[done]` only for completed events, `[MISSED]` for past-but-uncompleted. `is_overdue` now properly checks `actual_status != 'completed'`.

### BUG 3: Timezone Bug in Executive Briefing — FIXED (2026-03-06)

**Severity:** High — Medication overdue/upcoming comparison used UTC time instead of user's local time.

**Fix:** `_build_health_gate_section()` now uses `get_user_now(user).time()` instead of `timezone.now().time()`. This was causing 2 AM medication reminders for 7 AM medicines (UTC offset made them appear overdue).

### BUG 4: Calibration Injection Causes Task/Medication Hallucinations — FIXED (2026-03-07)

**Severity:** Critical — CoS fabricated "3 of 5 tasks" when user had only 1 task, and "medication due" when user had 0 medications.

**Root cause:** Active calibration injection (~6000 chars "MANDATORY OVERRIDE") conflicted with operational check-in data. The LLM resolved the conflict by fabricating data to bridge both instructions. 8/24 evaluation questions had task hallucinations; 5/24 had medication hallucinations.

**Fix (v4 stability upgrade):**
1. **Calibration suppression** — `_generate_response()` detects functional queries (questions, commands, advisory requests) and skips calibration injection. Only pure calibration responses get the injection.
2. **Data state snapshot** — `_build_data_state_snapshot()` adds exact `active_tasks` and `completed_tasks_today` counts with "ABSOLUTE GROUNDING RULES".
3. **Snapshot positioning** — Moved to END of CoS system injection for highest recency weight.
4. **Anti-generic rules** — RESPONSE QUALITY RULES block prevents fallback to generic productivity advice.
5. **Calibration data isolation** — Added isolation markers in `cos_governance.py` noting calibration data is NOT for operational briefings.

**Result:** Task hallucinations: 8/24 → 0/24. Medication hallucinations: 5/24 → 1/24. Overall eval score: 5.8 → 6.0/10.

**Files changed:** `apps/ai/personal_assistant.py`, `apps/core/ai_orchestrator/cos_context.py`, `apps/core/blueprint/cos_governance.py`

**Evaluation report:** `docs/CoSEvaluation_v4.md`

### BUG 5: ISE Engines Missing EngineRun Telemetry — FIXED (2026-03-08)

**Severity:** High — COAS monitoring was blind to ISE-scheduled engines.

**Root cause:** ISE scheduler runner functions (`scheduler_runner.py`) executed engine logic directly without creating `EngineRun` records. Heartbeat calculator treated `last_run_at=NULL` as `status="OK"`, giving perfect scores to engines that never ran.

**Fix:**
1. Created `engine_runtime.py` with `run_engine()` telemetry wrapper
2. ISE scheduler now dispatches to Celery workers (with direct-execution fallback)
3. All 29 ISE tasks create EngineRun records via telemetry wrapper
4. Heartbeat `NEVER_RUN` status replaces false `OK` for unexecuted engines
5. Fixed ENGINE_CADENCES mismatches: GLOE, PGE, DNE, ICQG
6. Added GLOE to ALL_ENGINES (was missing)

**Files:** `apps/core/engine_runtime.py` (NEW), `apps/core/tasks.py`, `apps/core/ai_scheduler/scheduler_engine.py`, `apps/core/ai_observability/heartbeat.py`, `apps/core/ai_observability/models.py`, `apps/core/ai_observability/ops_aggregates.py`

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

### FIX APPLIED: Health Intelligence Enum-Only CoS Output (2026-03-05)

**Status:** FIXED

**Problem:** CoS paraphrased health intelligence enums ("in the fat loss phase", "muscle preservation is stable") instead of quoting exact DHS enum values. Also ignored "keep it short" requests by adding sleep/calendar content.

**Changes:**
1. `cos_context.py :: _format_health_intelligence_block()` — Added prominent HEALTH INTELLIGENCE STATUS sub-block at the top with exact enum values + UNKNOWN placeholders + strict verbatim-quote rule
2. `cos_health_context.py :: build_cos_health_intelligence()` — Added `last_computed` timestamp to body_comp_intelligence dict
3. `personal_assistant.py :: _classify_response_mode()` — "keep it short", "keep it brief", "just the numbers", "tl;dr" now classify as `brief` mode
4. `personal_assistant.py :: _generate_response()` — Health intelligence keyword detection adds strict enum-only format rule; brief mode + health intel = mandatory 4-line output
5. `health_response_validator.py` — Added `_check_health_intelligence_enums()`: rejects "stable"/"good" for muscle status, rejects paraphrased phase language
6. Tests: `apps/ai/tests/test_health_intelligence_cos.py` — 21 tests covering enum rendering, UNKNOWN placeholders, validator enforcement, response mode classification

**CoS Output Contract:**
```
When asked: "What is my fat loss phase, plateau risk, and muscle preservation status? Keep it short."
Must respond:
  Fat loss phase: STABLE_FAT_LOSS
  Plateau risk: LOW
  Muscle preservation: HIGH_QUALITY
  Last updated: 2026-03-05T08:00:00
```

Valid enums:
- `fat_loss_phase`: RAPID_INITIAL_LOSS, STABLE_FAT_LOSS, RECOMPOSITION, PLATEAU, REBOUND_RISK
- `plateau_risk_label`: LOW, RISING, HIGH
- `muscle_preservation_status`: HIGH_QUALITY, MODERATE_QUALITY, MUSCLE_RISK

### No-Append Rule for STRICT_HEALTH_STATUS (2026-03-05)

**Status:** ENFORCED

**Problem:** Even with strict prompt rules and 100-token cap, LLM still appended sleep, calendar, and coaching content after the 4-line health status. Prompt engineering alone cannot guarantee format compliance.

**Solution: Deterministic enforcement — LLM output is DISCARDED entirely.**

When the user asks a health intelligence question with a brevity keyword ("keep it short", "tl;dr", etc.), the system:
1. Detects health intel keywords + brevity keywords in the message
2. Still sends the message to the LLM (for logging/observability)
3. **Discards the LLM response completely**
4. Calls `enforce_strict_health_status(cos_context)` which reads enum values directly from the CoS context dict
5. Returns a deterministic 4-line string — no LLM involvement in the output

**Enforcement points:**
- **Non-streaming path** (`personal_assistant.py :: _generate_response()`, ~line 4950): After LLM response, replaces it with `enforce_strict_health_status()` output
- **Streaming path** (`personal_assistant.py :: send_message_stream()`, ~line 5777): Sets `_direct_response` before LLM streaming begins, skips SSE streaming entirely

**Key function:** `health_response_validator.py :: enforce_strict_health_status(cos_context) -> str`
- Reads `cos_context['health_intelligence']['body_comp']` for enum values
- Missing/None values → `UNKNOWN (awaiting data)`
- Strips microseconds from ISO timestamps
- Returns exactly 4 lines, no exceptions

**Tests:** `apps/ai/tests/test_health_intelligence_cos.py` — 29 tests (8 specifically for `enforce_strict_health_status`)

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
| `apps/core/ai_orchestrator/orchestrator.py` | Main orchestrator entry (reconciliation + rate limit + CRUD gate) | ~467 |
| `apps/core/ai_orchestrator/activity_reconciliation.py` | Activity Reconciliation Layer (duplicate detection, 17 registered intents) | ~883 |
| `apps/core/ai_orchestrator/crud_confirmation.py` | CRUD Confirmation Gate (A/B/C structured options + legacy text parsing) | ~340 |
| `apps/core/ai_orchestrator/action_policy.py` | Centralized ACTION_POLICY (50+ intents, risk/category/authority enums, rate limiter) | ~375 |
| `apps/core/ai_orchestrator/decision_memory.py` | Decision memory (confidence tracking, decay, suggestion reordering) | ~120 |
| `apps/core/ai_governance/models.py` | PendingAction (incl. `proactive_checkin` type) + UserDecisionPreference models | ~630 |
| `apps/core/ai_orchestrator/commitment_contract.py` | ECC commitment tracking | ~1,678 |
| `apps/ai/personal_assistant.py` | Main assistant, send_message() | ~6,500 |
| `apps/ai/deterministic_router.py` | LLM-last shared routing layer (8 data routes, domain scoping, memory gating, feature flags) | ~470 |
| `apps/ai/deterministic_health_summary.py` | Health summary fast path (lexical detection + SAE formatting) | ~287 |
| `apps/ai/views.py` | Chat API endpoints | ~1,661 |
| `apps/ai/proactive_checkins.py` | Proactive check-in service (20 check-in types, 5 domain schedulers) | ~1200+ |
| `apps/ai/assistant_intelligence.py` | Coaching style templates (22+ template keys × 4 styles) | ~600+ |
| `apps/ai/quick_reply_handlers.py` | Quick reply button generators (13+ handlers) | ~400+ |
| `apps/ai/readiness_cache.py` | CoS context caching (Redis) | ~300 |

### Intelligence Engines

| File | Purpose |
|------|---------|
| `apps/core/ai_state/state_engine.py` | SAE — state management |
| `apps/core/ai_state/state_builder.py` | SAE — module state builders |
| `apps/core/ai_state/state_updater.py` | SAE — incremental update |
| `apps/core/ai_insights/insight_engine.py` | PIE — insight generation |
| `apps/core/ai_insights/health/screenshot_parser.py` | PIE — health screenshot Vision API extraction |
| `apps/core/ai_insights/health/sleep_analysis.py` | PIE — deterministic sleep analysis + PIE rule |
| `apps/core/ai_insights/health/user_context.py` | PIE — health user context for analysis personalization |
| `apps/core/ai_insights/health/reference_ranges.py` | PIE — clinical reference ranges (sleep, vitals) |
| `apps/core/ai_insights/rules_tasks.py` | PIE — task insight rules (overdue, stall, due-today) |
| `apps/core/ai_predictions/prediction_rules_tasks.py` | PRIE — task prediction rules (deadline miss risk) |
| `apps/core/ai_predictions/prediction_engine.py` | PRIE — predictions |
| `apps/core/ai_guidance/guidance_engine.py` | PGE — guidance |
| `apps/core/ai_scheduler/scheduler_engine.py` | ISE — scheduler (dispatches to Celery) |
| `apps/core/ai_scheduler/scheduler_registry.py` | ISE — 42+ task registry |
| `apps/core/ai_scheduler/scheduler_runner.py` | ISE — task runner functions |
| `apps/core/engine_runtime.py` | Engine telemetry wrapper (EngineRun records) |
| `apps/core/ai_observability/same_engine.py` | SAME — monitoring |
| `apps/core/ai_observability/maturity_engine.py` | Maturity scoring (6 dimensions + snapshots + recommendations) |
| `apps/core/ai_observability/ops_views.py` | Operations Wall data (OpsStreamView JSON endpoint, AAFR aggregation) |
| `apps/core/ai_observability/models.py` | Observability models (AIActionMetric, EngineRun, SystemMaturitySnapshot, etc.) |
| `apps/core/ai_delivery/delivery_engine.py` | DNE — notification delivery |
| `apps/core/domain_registry/registry.py` | Domain Capability Registry (autodiscover, coverage) |
| `apps/core/domain_registry/descriptors.py` | DomainCapability descriptor dataclass |

### Behavior System

| File | Purpose |
|------|---------|
| `apps/core/behavior/status_engine.py` | Shared occurrence status + adherence math (all domains use this) |
| `apps/core/behavior/behavior_score_engine.py` | Composite behavior score across domains |
| `apps/core/behavior/domain_medication.py` | Medication adapter for behavior contract |
| `apps/core/behavior/domain_workout.py` | Workout adapter for behavior contract |
| `apps/core/behavior/domain_routine.py` | Routine adapter for behavior contract |
| `apps/core/ai_insights/rules_behavior.py` | PIE — behavior score drop, domain weakness, multi-domain decline |
| `apps/life/models.py` (Routine/RoutineSchedule/RoutineLog) | Routine domain models |
| `apps/health/models.py` (WorkoutScheduleLog) | Workout schedule adherence log |

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
