# WLJ Chief of Staff (CoS) — Full System Picture Report

**Generated:** 2026-02-22
**Scope:** Audit-grade inventory, execution trace, and failure-mode review
**Status:** Zero-omission documentation of production code

---

## 0) Executive Abstract

### What CoS Is Responsible For

The Chief of Staff (CoS) is the AI orchestration layer of Whole Life Journey. It is the **single authority** for:
- Interpreting user natural-language input and routing to domain actions
- Enforcing executive-grade accountability via deterministic commitment contracts (ECC)
- Evaluating user behavioral trajectory (CLEAN / EARLY_EROSION / STRUCTURAL_DRIFT) and adjusting tone/enforcement
- Assembling full situational context for every LLM interaction
- Managing the 17-engine intelligence pipeline (interpretation → execution → post-execution)
- Delivering proactive guidance, daily briefings, and weekly intelligence reports
- Monitoring system health via autonomous anomaly detection (SAME)

### What CoS Is NOT Responsible For

- Database schema management or migrations
- User authentication (handled by django-allauth)
- UI rendering (handled by Django templates)
- iOS app native behavior (Swift/SwiftUI)
- Direct database CRUD for domain models (delegated to action handlers per module)
- Billing/subscription logic (handled by billing app)

### Top 10 Invariants (Based on Code)

1. **Single Execution Authority** — All domain actions flow through `execution_engine.execute_action()` (`apps/core/ai_orchestrator/execution_engine.py`)
2. **Closure Precedence** — Phase 5C closure ("It's done") always short-circuits before renegotiation, new commitment detection, and intent recognition (`apps/ai/personal_assistant.py:3025-3050`)
3. **No Fabricated Data** — Source-Integrity Gate validates every data source before use; insufficient sources produce placeholders, never synthetic data (`apps/core/ai_orchestrator/cos_context.py:1401-1425`)
4. **No Deferral Under Erosion** — EARLY_EROSION and STRUCTURAL_DRIFT tiers block all deferral language ("tomorrow", "next week", "later") (`apps/core/ai_orchestrator/cos_context.py:2721-2725`)
5. **Deterministic Commitment Detection** — ECC uses substring matching on normalized input, never LLM inference (`apps/core/ai_orchestrator/commitment_contract.py:307-328`)
6. **Tier Re-evaluation Per Request** — Activation state (CLEAN/EARLY_EROSION/STRUCTURAL_DRIFT) recomputed on every message, never cached (`apps/core/ai_orchestrator/cos_context.py:determine_activation_state()`)
7. **Threshold-Based Overrides Semantic** — Numeric thresholds (renegotiations ≥3/10d, skips ≥2/7d) always override semantic erosion detection (`apps/core/ai_orchestrator/cos_context.py:2664+`)
8. **Silent Engine Failures** — All engine errors are caught and logged; no engine failure breaks the user flow (`apps/core/ai_orchestrator/execution_engine.py`, all engine try/except wrappers)
9. **Single Time Authority** — All date/time uses `get_current_local_datetime(user)`, never `timezone.now()` or `datetime.now()` (`apps/core/utils.py`)
10. **Phase Integrity** — Phase 1 engines never execute actions; Phase 3 engines never execute actions; only Phase 2 (UAIO) has execution authority

---

## 1) High-Level Architecture Map (Inventory)

### 1.1 CoS Entry Points

#### A. HTTP Endpoints

| Endpoint | View Class | File | Method | Inputs | Purpose |
|----------|-----------|------|--------|--------|---------|
| `POST /ai/chat/` | `AssistantChatView` | `apps/ai/views.py` | POST | `{message, page_context, image_data, image_mime_type}` | Primary user message processing |
| `GET /ai/opening/` | `AssistantOpeningView` | `apps/ai/views.py` | GET | None | Daily check-in greeting + CoS snapshot |
| `GET /ai/conversation/<id>/` | `ConversationHistoryView` | `apps/ai/views.py` | GET | `conversation_id` | Conversation history retrieval |
| `GET /ai/cos/settings/` | `CosSettingsView` | `apps/ai/views.py` | GET | None | Governance settings form |
| `POST /ai/cos/settings/save/` | `CosSettingsSaveView` | `apps/ai/views.py` | POST | Form fields | Save governance preferences |
| `POST /ai/learning-mode/toggle/` | `LearningModeToggleView` | `apps/ai/views.py` | POST | `{action}` | Enter/exit learning mode |
| `POST /ai/event-reflection/` | `EventReflectionView` | `apps/ai/views.py` | POST | `{reflection_id, action, text}` | Post-event reflection |
| `POST /ai/message-feedback/` | `MessageFeedbackView` | `apps/ai/views.py` | POST | `{message_id, was_helpful}` | Message quality feedback |
| `POST /ai/quick-reply/` | `QuickReplyView` | `apps/ai/views.py` | POST | `{message_id, reply_id, action, params}` | Quick-action responses |

#### B. Internal Service Calls

| Entry Point | Class/Function | File | Purpose |
|-------------|---------------|------|---------|
| `PersonalAssistant.send_message()` | `PersonalAssistant` | `apps/ai/personal_assistant.py:1918` | Primary message pipeline |
| `PersonalAssistant.get_opening_message()` | `PersonalAssistant` | `apps/ai/personal_assistant.py` | Daily greeting assembly |
| `get_personal_assistant(user)` | Factory function | `apps/ai/personal_assistant.py:3965` | Singleton accessor |
| `build_cos_context(user)` | Module function | `apps/core/ai_orchestrator/cos_context.py` | Full context assembly |
| `determine_activation_state()` | Module function | `apps/core/ai_orchestrator/cos_context.py` | Tier computation |
| `process_user_input()` | Module function | `apps/core/ai_orchestrator/orchestrator.py` | Orchestrator pipeline |
| `execute_action()` | Module function | `apps/core/ai_orchestrator/execution_engine.py` | Single execution authority |
| `process_ecc_detection()` | Module function | `apps/core/ai_orchestrator/commitment_contract.py` | ECC main entry |
| `process_ecc_closure()` | Module function | `apps/core/ai_orchestrator/commitment_contract.py` | Closure processing |

#### C. Celery Tasks

| Task | File | Schedule | Purpose |
|------|------|----------|---------|
| `run_same_cycle_task()` | `apps/core/tasks.py` | Every 60s | SAME autonomous monitoring |
| ISE runner | `apps/core/ai_scheduler/scheduler_runner.py` | Every 5 min | Intelligence Scheduler Engine |
| Various engine commands | `apps/core/management/commands/` | Via ISE | PIE, PRIE, PGE, DBE, WIRE, DNE, GLOE |

#### D. Admin Console Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /admin-console/ops/` | Operations Wall main page |
| `GET /admin-console/ops/stream/` | JSON polling for real-time status |
| `POST /admin-console/ops/actions/` | Admin intervention actions |
| `GET /admin-console/ops/integrity/` | System Integrity Index |
| `GET /admin-console/diagnostics/` | Diagnostics Console |
| `GET /admin-console/diagnostics/trace/<trace_id>/` | Trace waterfall detail |

---

### 1.2 CoS Core Pipeline

```
USER MESSAGE (POST /ai/chat/)
    │
    ▼
AssistantChatView.post()
    │
    ▼
PersonalAssistant.send_message()
    │
    ├──► [1] Save user message to DB (AssistantMessage)
    │
    ├──► [2] Check AI availability + user consent
    │         └─ AIService.check_user_consent(user) → bool
    │
    ├──► [3] PHASE 5C: CLOSURE PRECEDENCE (hard short-circuit)
    │         ├─ Load active commitment from conversation.metadata
    │         ├─ process_ecc_closure(message, commitment)
    │         ├─ If closure detected:
    │         │   ├─ Set sentinel: _ecc_closure_handled = True
    │         │   ├─ Remove commitment from metadata
    │         │   ├─ Save conversation
    │         │   └─ RETURN immediately (bypass ALL below)
    │         └─ Fallback: if _ecc_closure_handled, RETURN
    │
    ├──► [4] PHASE 5A/5B: ECC DETECTION & COMMITMENT
    │         ├─ process_ecc_detection(message, tier, commitments)
    │         ├─ If renegotiation detected:
    │         │   └─ Return blocked choices OR updated commitment
    │         ├─ If new commitment detected:
    │         │   ├─ Extract fields (action, time, done-def)
    │         │   ├─ If missing field → tightening question
    │         │   ├─ If complete → normalize + confirm
    │         │   ├─ Persist to conversation.metadata
    │         │   └─ RETURN (no LLM call)
    │         └─ If no commitment → continue pipeline
    │
    ├──► [5] PROACTIVE CONFIRMATION CHECK
    │         └─ handle_proactive_confirmation() (e.g., "Did you take meds?")
    │
    ├──► [6] CALIBRATION CHECK
    │         └─ _is_calibration_active() → skip normal intent recognition
    │
    ├──► [7] DATA VISIBILITY CONFIRMATION
    │         └─ _handle_data_visibility_confirmation()
    │
    ├──► [8] LEARNING MODE EXIT CONFIRMATION
    │         └─ _handle_learning_mode_exit_confirmation()
    │
    ├──► [9] PENDING ACTION CONFIRMATION
    │         └─ intent_service.get_pending_confirmation() → yes/no handler
    │
    ├──► [10] INTENT RECOGNITION
    │         ├─ intent_service.recognize_intents(message, user)
    │         │   └─ OpenAI function calling → List[IntentResult]
    │         ├─ For each actionable intent:
    │         │   ├─ If requires_confirmation → store pending, ask
    │         │   └─ If not → execute via orchestrator
    │         └─ Multi-command support (multiple intents per message)
    │
    ├──► [11] ORCHESTRATOR PIPELINE
    │         ├─ orchestrator.process_user_input()
    │         │   ├─ resolve_context_pipeline() [SLCME]
    │         │   ├─ resolve_time_pipeline() [HTIE]
    │         │   └─ _run_semantic_understanding() [SUE]
    │         ├─ orchestrator.enrich_and_execute()
    │         │   ├─ route_action() → EnrichedAction
    │         │   └─ execution_engine.execute_action()
    │         │       ├─ Learning Mode gate
    │         │       ├─ safety_engine.validate_action()
    │         │       ├─ intent_service.execute_intent()
    │         │       └─ _run_intelligence_chain()
    │         │           ├─ SAE state update
    │         │           ├─ Blueprint recomputation
    │         │           └─ PIE → PRIE chain
    │         └─ response_builder.build_response()
    │
    ├──► [12] LLM RESPONSE GENERATION
    │         ├─ build_cos_context(user) → 50+ context fields
    │         ├─ determine_activation_state() → tier
    │         ├─ format_cos_system_injection(context) → prompt injection
    │         ├─ AIService._call_api() → OpenAI completion
    │         └─ Post-processing (quality gate, guardrails)
    │
    └──► [13] SAVE & RETURN
              ├─ AssistantMessage.objects.create()
              └─ JsonResponse({response, actions_taken, conversation_id})
```

**Short-Circuit Points (in precedence order):**
1. Phase 5C closure → immediate return
2. Phase 5A/5B commitment detection/tightening → return without LLM
3. Proactive confirmation → return handler response
4. Calibration active → restricted processing
5. Data visibility confirmation → return confirmation
6. Learning mode exit → return confirmation
7. Pending action confirmation → return yes/no handling

---

### 1.3 Engine Inventory (Complete)

#### Summary Table

| # | Engine | Acronym | Phase | Location | Purpose |
|---|--------|---------|-------|----------|---------|
| 1 | Human Temporal Intelligence | HTIE | 1 (Interp) | `apps/core/time/` | Parse time expressions to concrete datetimes |
| 2 | Self-Learning Context Memory | SLCME | 1 (Interp) | `apps/core/ai_memory/` | Learn phrase→meaning associations |
| 3 | Semantic Understanding | SUE | 1 (Interp) | `apps/core/ai_semantics/` | Parse intent + extract entities |
| 4 | Unified AI Orchestrator | UAIO | 2 (Exec) | `apps/core/ai_orchestrator/` | Central execution brain |
| 5 | Intelligence Scheduler | ISE | 2 (Exec) | `apps/core/ai_scheduler/` | Manage engine execution schedules |
| 6 | Intelligent Content Quality Gate | ICQG | 2 (Exec) | `apps/core/ai_quality/` | Suppress repeats, enforce quality |
| 7 | State Awareness | SAE | 3 (Post) | `apps/core/ai_state/` | Authoritative user state snapshot |
| 8 | Proactive Insight | PIE | 3 (Post) | `apps/core/ai_insights/` | Generate evidence-based insights |
| 9 | Predictive Intelligence | PRIE | 3 (Post) | `apps/core/ai_predictions/` | Project trajectories (linear regression) |
| 10 | Proactive Guidance | PGE | 3 (Post) | `apps/core/ai_guidance/` | Surface ranked guidance items |
| 11 | Guidance Learning Optimization | GLOE | 3 (Post) | `apps/core/ai_guidance_learning/` | Learn from user guidance interactions |
| 12 | Daily Briefing | DBE | 3 (Post) | `apps/core/ai_briefing/` | Aggregate daily intelligence summary |
| 13 | Weekly Intelligence Report | WIRE | 3 (Post) | `apps/core/ai_weekly_report/` | Weekly longitudinal summaries |
| 14 | Evidence & Explainability | E3 | 3 (Post) | `apps/core/ai_explain/` | Attach evidence to intelligence outputs |
| 15 | Delivery & Notification | DNE | 3 (Post) | `apps/core/ai_delivery/` | Multi-channel delivery with throttling |
| — | System Autonomous Monitoring | SAME | Obs | `apps/core/ai_observability/` | Anomaly detection + auto-remediation |
| — | Intelligence Observability | IOCD | Obs | `apps/core/ai_observability/` | Daily system-wide metrics snapshots |

**Total: 15 production engines + 2 observability engines = 17**

#### Detailed Engine Profiles

##### 1. HTIE — Human Temporal Intelligence Engine

- **Files:** `apps/core/time/parser.py`, `resolver.py`, `ambiguity_detector.py`, `system_clock.py`
- **Trigger:** Event-driven (every user message with time expressions)
- **Inputs:** Raw text, user timezone
- **Outputs:** Concrete timezone-aware datetime
- **Persistence:** None (stateless)
- **Schedule:** Event-driven only
- **UI:** None (internal pipeline)
- **Observability:** EngineRun traces
- **Failure:** Returns ambiguity result; never guesses
- **Key Functions:** `parse_time_expression()`, `resolve_time_expression()`, `detect_ambiguity()`
- **Tests:** 122 tests in `apps/core/time/tests/`

##### 2. SLCME — Self-Learning Context Memory Engine

- **Files:** `apps/core/ai_memory/models.py`, `context_pipeline.py`
- **Trigger:** Event-driven (when contextual references detected)
- **Inputs:** User phrase, page context
- **Outputs:** Resolved meaning (entity reference)
- **Persistence:** `LearnedMapping` model (phrase→meaning, confidence score), `ContextSnapshot`, `ClarificationLog`
- **Schedule:** Event-driven
- **UI:** None (internal pipeline)
- **Observability:** ClarificationLog audit trail
- **Failure:** Asks for clarification; never guesses below confidence threshold
- **Tests:** `apps/core/ai_memory/tests.py`

##### 3. SUE — Semantic Understanding Engine

- **Files:** `apps/core/ai_semantics/semantic_engine.py`, `models.py`
- **Trigger:** Event-driven (on each user message)
- **Inputs:** User text, context
- **Outputs:** Parsed intent, entities, confidence
- **Persistence:** `SemanticDecisionLog`
- **Schedule:** Event-driven
- **Failure:** Falls through to LLM-based intent recognition

##### 4. UAIO — Unified AI Orchestrator

- **Files:** `apps/core/ai_orchestrator/orchestrator.py`, `execution_engine.py`, `action_router.py`
- **Trigger:** Event-driven (every actionable intent)
- **Inputs:** IntentResult, user, enrichments
- **Outputs:** ActionResult
- **Persistence:** Audit logs
- **Schedule:** Event-driven
- **Key Functions:** `process_user_input()`, `enrich_and_execute()`, `execute_action()`
- **Failure:** Logs error, returns failure ActionResult; never crashes user flow

##### 5. ISE — Intelligence Scheduler Engine

- **Files:** `apps/core/ai_scheduler/scheduler_engine.py`, `scheduler_runner.py`, `scheduler_models.py`, `scheduler_registry.py`, `scheduler_lock.py`
- **Trigger:** Every 5 minutes (Celery beat via `CELERY_BEAT_SCHEDULE` in `config/settings.py`)
- **Inputs:** None (scans registered schedules)
- **Outputs:** Triggers engine runs per schedule
- **Persistence:** `ScheduledIntelligenceTask` model
- **Schedule:** Every 5 minutes
- **UI:** Admin console
- **Observability:** `SchedulerHeartbeat` model
- **Failure:** Missed schedules detected by SAME

##### 6. ICQG — Intelligent Content Quality Gate

- **Files:** `apps/core/ai_quality/quality_gate.py`, `repeat_suppression.py`, `conflict_detector.py`, `quality_models.py`, `quality_metrics.py`
- **Trigger:** Event-driven (before guidance/insight delivery)
- **Inputs:** Content to evaluate, recent history
- **Outputs:** Allow/suppress decision
- **Persistence:** DecisionRecord (suppression audit)
- **Schedule:** Event-driven
- **Failure:** Fails open (allows content if gate errors)
- **Tests:** `apps/core/ai_quality/tests.py`

##### 7. SAE — State Awareness Engine

- **Files:** `apps/core/ai_state/state_engine.py`, `state_builder.py`, `state_updater.py`, `models.py`
- **Trigger:** Event-driven (after action execution) + periodic refresh
- **Inputs:** User, event type
- **Outputs:** `UserState` model instance
- **Persistence:** `UserState` (authoritative user state snapshot)
- **Schedule:** Event-driven + ISE refresh
- **Key Functions:** `rebuild_user_state()`, `update_user_state()`
- **Failure:** Falls back to partial state; never blocks pipeline
- **Learning Mode Gate:** SAE writes blocked during Learning Mode (`state_updater.py:36-42`)
- **Tests:** `apps/core/ai_state/tests.py`

##### 8. PIE — Proactive Insight Engine

- **Files:** `apps/core/ai_insights/insight_engine.py`, `rules_health.py`, `rules_body_composition.py`, `rules_labs_vitals.py`, `rules_goals.py`, `rules_habits.py`, `rules_scripture.py`, `rules_journal.py`, `rules_transformation.py`, `models.py`
- **Trigger:** Event-driven (after action) + daily via ISE
- **Inputs:** User, event data
- **Outputs:** `Insight` model instances
- **Persistence:** `Insight` (title, message, insight_type, module, evidence, dedupe_key)
- **Schedule:** Event-driven + daily
- **UI:** Guidance inbox (via PGE), dashboard
- **Failure:** PIE failures never break action execution
- **Tests:** `apps/core/ai_insights/tests.py` (30 tests)

##### 9. PRIE — Predictive Intelligence Engine

- **Files:** `apps/core/ai_predictions/prediction_engine.py`, `base_prediction_rule.py`, `prediction_registry.py`, `projection_math.py`, `confidence_engine.py`, `models.py`
- **Trigger:** Event-driven (after PIE generates insights) + daily via ISE
- **Inputs:** User, event
- **Outputs:** `Prediction` model instances
- **Persistence:** `Prediction` (prediction_type, predicted_value, predicted_date, confidence_score, evidence, status, dedupe_key)
- **Prediction Math:** Pure Python linear regression (`projection_math.py`); no numpy
- **Confidence Scoring:** 4 factors (data volume 0-0.30, R² 0-0.30, history ratio 0-0.20, projection distance 0-0.20) → max 1.0
- **9 Prediction Rules:** Weight, Body Fat, Lean Mass, Goals, Habits, Labs, Nutrition, Fitness, Transformation
- **Failure:** PRIE failures never break PIE
- **Tests:** `apps/core/ai_predictions/tests.py` (32 tests)

##### 10. PGE — Proactive Guidance Engine

- **Files:** `apps/core/ai_guidance/guidance_engine.py`, `guidance_selector.py`, `guidance_ranker.py`, `guidance_logger.py`, `guidance_rules.py`, `guidance_registry.py`, `models.py`, `views.py`
- **Trigger:** Every 6 hours via ISE + on-demand
- **Inputs:** User
- **Outputs:** `GuidanceItem` model instances (max 5 active per user)
- **Persistence:** `GuidanceItem` (title, message, priority 1-5, guidance_type, source, module, confidence_score, evidence, lifecycle states)
- **Lifecycle States:** new → acknowledged → acted_upon / dismissed / snoozed
- **9 Guidance Rules:** GoalRisk, HabitInactivity, HealthTrend, JournalInactivity, PositiveReinforcement, TransformationCoaching, ProteinAdjustment, WorkoutFrequency, FastingOptimization
- **Ranking:** Score = Priority weight (10-50) + Confidence bonus (0-10) + Source bonus (2-5) + Evidence richness (0-3)
- **Deduplication:** SHA-256 dedupe_key
- **UI:** Guidance Inbox (`/guidance/`), JSON API (`/guidance/api/`), Action API (`/guidance/<pk>/action/`)
- **Tests:** `apps/core/ai_guidance/tests.py` (109 tests)

##### 11. GLOE — Guidance Learning Optimization Engine

- **Files:** `apps/core/ai_guidance_learning/learning_engine.py`, `learning_calculator.py`, `learning_logger.py`, `learning_models.py`
- **Trigger:** Event-driven (on guidance action) + every 6 hours via ISE
- **Inputs:** User, guidance_item, event_type
- **Outputs:** `GuidanceLearningProfile`, responsiveness_score (0.0-1.0)
- **Scoring Formula:** `acted_rate×0.40 + acknowledged_rate×0.25 - dismissed_rate×0.20 + response_speed×0.15`
- **PGE Integration:** `final_score = base_score × (1 + (responsiveness - 0.5) × 2 × 0.25)` — max ±25% influence

##### 12. DBE — Daily Briefing Engine

- **Files:** `apps/core/ai_briefing/briefing_engine.py`, `briefing_selector.py`, `briefing_ranker.py`, `briefing_logger.py`, `models.py`
- **Trigger:** Daily via ISE
- **Inputs:** User
- **Outputs:** `DailyBriefing` (unique per user per day)
- **Pipeline:** gather (SAE+PIE+PRIE+PGE) → select (max 5, priority-ordered) → rank → summarize → store
- **Deduplication:** One briefing per user per day (unique constraint)
- **UI:** Dashboard tile, full view at `/intelligence/briefing/`
- **Tests:** `apps/core/ai_briefing/tests.py` (27 tests)

##### 13. WIRE — Weekly Intelligence Report Engine

- **Files:** `apps/core/ai_weekly_report/report_engine.py`, `report_selector.py`, `report_ranker.py`, `report_logger.py`, `models.py`
- **Trigger:** Weekly via ISE (604800 seconds)
- **Inputs:** User
- **Outputs:** `WeeklyIntelligenceReport` (unique per user per week)
- **Pipeline:** gather (SAE+PIE+PRIE+PGE+GLOE) → compute deltas → select (max 10) → rank → summarize
- **Summary:** Template-based (no AI call); includes learning engagement assessment
- **UI:** Dashboard tile, history at `/intelligence/weekly/`, detail at `/intelligence/weekly/<pk>/`
- **Tests:** `apps/core/ai_weekly_report/tests.py` (54 tests)

##### 14. E3 — Evidence & Explainability Engine

- **Files:** `apps/core/ai_explain/explain_engine.py`, `evidence_builder.py`, `explain_templates.py`, `explain_logger.py`, `models.py`, `views.py`
- **Trigger:** Non-blocking hooks after PGE/DBE/WIRE storage
- **Inputs:** Source engine, source object
- **Outputs:** `ExplainRecord` (explanation, confidence_explanation, evidence)
- **Handler Mapping:** GuidanceItem→PGE, DailyBriefing→DBE, WeeklyIntelligenceReport→WIRE
- **On-Demand:** ExplainDetailView creates records if missing (user clicks "Why?")
- **Failure:** E3 failures NEVER block core engines
- **UI:** `/intelligence/explain/<engine>/<type>/<id>/`
- **Tests:** `apps/core/ai_explain/tests.py` (37 tests)

##### 15. DNE — Delivery & Notification Engine

- **Files:** `apps/core/ai_delivery/delivery_engine.py`, `delivery_policies.py`, `delivery_router.py`, `delivery_logger.py`, `models.py`, `views.py`
- **Trigger:** Every 10 minutes via ISE
- **Inputs:** None (scans for undelivered items)
- **Outputs:** `DeliveredNotification` (status, skip_reason, dedupe_hash)
- **Channels:** In-app (default ON), Email (default OFF), SMS (default OFF), Push (optional)
- **User Preferences:** `intelligence_inapp_enabled`, `intelligence_email_enabled`, `intelligence_sms_enabled`, `intelligence_max_per_day` (6), `intelligence_max_per_hour` (2)
- **Policies:** Deduplication (SHA-256), quiet hours, throttle, skip logging
- **UI:** Settings at `/intelligence/delivery/settings/`, history at `/intelligence/delivery/history/`
- **Tests:** `apps/core/ai_delivery/tests.py` (29 tests)

##### SAME — System Autonomous Monitoring Engine

- **Files:** `apps/core/ai_observability/same_engine.py`, `heartbeat.py`, `ops_anomalies.py`, `ops_aggregates.py`, `ops_feed.py`, `ops_views.py`
- **Trigger:** Every 1-2 minutes (periodic)
- **Anomaly Types:** MISSED_RUN, ERROR_SPIKE, CONFIDENCE_VOLATILITY, SUPPRESSION_STORM, LOOPING_REMINDER, ENGINE_STARVATION, DELIVERY_RETRY_SPIKE
- **Escalation:** P3→P2 (10 min), P2→P1 (20 min), 5 min cooldown
- **Auto-Remediation:** P3 only, max 3 per cycle, 30 min cooldown per anomaly
- **System Integrity Index:** 0-100 (OPTIMAL 90+, NOMINAL 70-89, DEGRADED 40-69, CRITICAL 0-39)
- **Models:** `OpsAnomaly`, `OpsNarrativeSnapshot`, `SystemIntegritySnapshot`, `AdminIntervention`, `EngineExecutionLog`, `SAMEExecutionLog`, `SchedulerHeartbeat`

##### IOCD — Intelligence Observability (Metrics Snapshot)

- **Files:** `apps/core/ai_observability/observability_engine.py`, `metrics_calculator.py`
- **Trigger:** Daily via ISE
- **Outputs:** `IntelligenceMetricsSnapshot` (guidance effectiveness, prediction coverage, delivery effectiveness, user engagement, quality metrics, persona effectiveness)

---

## 2) Deterministic Layers and "Executive Authority" Controls

### 2.1 Phase 3 (Frozen) Controls

**File:** `apps/core/ai_orchestrator/cos_context.py`

#### Activation State Detection

**Function:** `determine_activation_state(trajectory_signals, user_input='')` (line ~2664)

**Three States:**

| State | Constant | Trigger |
|-------|----------|---------|
| CLEAN | `ACTIVATION_CLEAN` | No thresholds met, no erosion markers |
| EARLY_EROSION | `ACTIVATION_EARLY_EROSION` | No thresholds met, but erosion markers present in user input |
| STRUCTURAL_DRIFT | `ACTIVATION_STRUCTURAL_DRIFT` | Numeric thresholds met |

**Priority:** `STRUCTURAL_DRIFT > EARLY_EROSION > CLEAN` — Threshold-based always overrides semantic detection.

#### Threshold Rules

**Renegotiation Patterns** (`_build_trajectory_signals()`, lines 1459-1500):
- Source: `InterventionLog` (10-day window)
- Filter: `user_response IN ['proceeded', 'dismissed']` AND `behavior_key > ''`
- Threshold: **≥3 per behavior → STRUCTURAL_DRIFT**
- Output: `renegotiation_patterns` list, `override_count_10d`

**Tier 1 Skip Patterns** (lines 1502-1545):
- Source: `InterventionLog` (7-day window)
- Filter: `trigger_type IN ['tier1_violation', 'non_negotiable_miss']`
- Threshold: **≥2 per behavior OR ≥2 consecutive days → STRUCTURAL_DRIFT**
- Consecutive tracking: Sorts unique dates, counts ≤1 day apart
- Output: `tier1_skip_patterns` list, `consecutive_tier1_skips`

**Drift Scenario Frequency** (lines 1547-1569):
- Source: `ScenarioHistory` (14-day window)
- Filter: `dominant_scenario='DRIFT_CRITICAL'`
- Minimum: ≥5 total events in 14 days

**Progress Trend** (lines 1571-1587):
- Source: State engine (weight_trend, alignment.trend)
- Negative if weight increasing OR alignment declining

#### Early Erosion Semantic Detection

**Erosion Markers** (normalized substring matching):
```
'never', 'cant', "can't", 'too much', 'too busy', 'overwhelmed',
'give up', 'forget', 'forgot', 'missed', ...
```

**Function:** `detect_erosion_markers(user_input)` — returns list of matched markers.

#### Source-Integrity Gate (lines 1401-1425)

**Function:** `_source_integrity_gate(source_name, queryset_fn, min_records)`
- Each data source verified independently
- Fails closed: returns `None` on any import/access failure
- **No fabricated data** — placeholders used only when real data unavailable

#### Framework Injection by State

**CLEAN** (lines 914-915): No trajectory framework injected. Only Phase 2 COGNITIVE_PRECISION_FRAMEWORK.

**EARLY_EROSION** (lines 923-926, EARLY_EROSION_FRAMEWORK at 2708-2747):
- Soft observational framework
- **FORBIDDEN:** 72-hour and 30-day projections
- **FORBIDDEN:** References to drift frequency, renegotiation counts, skip patterns
- **FORBIDDEN deferral language:** "tomorrow", "next week", "Monday", "later", "make up"
- Corrective minimum MUST be today, NOW, immediate
- Structure: Name pattern → Conditional escalation → Corrective minimum (3-5 sentences)

**STRUCTURAL_DRIFT** (TRAJECTORY_PRECISION_FRAMEWORK at 1120-1190):
- Three layers:
  - **Layer 1 — Contextual Pattern Surfacing** (triggers: same commitment renegotiated ≥3x/10d)
  - **Layer 2 — Drift Alert** (triggers: Tier 1 skip ≥2x/7d OR 2 consecutive)
  - **Layer 3 — Weekly Trajectory Framing** (during planning/review only)
- Horizon Modeling: 72-hour (concrete, behavioral) + 30-day (directional identity shift)
- Tone: High-density, no "I've noticed", no defensive framing

#### "Frozen" Enforcement

Phase 3 is documented as frozen: no infrastructure changes, no new engines, no DB modifications, no arbitration modifications. This is enforced by convention/documentation, not by code guards.

#### Test Files

- `apps/core/tests/test_phase4_cos.py` — `Phase3TieredActivationTest` (6 tests)

---

### 2.2 Phase 4 Controls (R1-R5)

**File:** `apps/core/ai_orchestrator/cos_context.py`

#### R1 — Decision Branch Modeling

**Function:** `evaluate_decision_branch_gate(cos_context, user_input)` (lines 1875-1968)

**Activation Conditions:**
- User expresses a decision (detected via decision indicators: "should I", "thinking about", "skip", "cancel", "move", "defer", etc.)
- Decision impacts an alignment target (active goal, protected block, or deadline within 14 days)

**Gate Conditions:**
- **Condition A:** Protected time block would be canceled + decision language detected
- **Condition B:** Decision deferred ≥2 times in 7 days + decision language detected

**Output Structure:**
```python
{
    'active': bool,
    'reason': 'decision_impacts_protected_block' | 'repeated_deferral' | '',
    'signals': {goals, protected_blocks, deferrals_7d, renegotiations, tier1_skips, consecutive_skips},
    'user_input': str,
    'deferrals_7d': int,
}
```

**Decision Indicators** (lines 1670-1742): 8 categories — deliberation, skip/cancel, deferral-by-action, explicit delay, time-based abandonment, repeated-deferral acknowledgement, commitment withdrawal, flat refusal.

#### R2 — Cost-of-Inaction Modeling (CIM)

**Function:** `_build_cim_injection(gate_result, activation_state)` (lines 2566-2605)

**Activation:** Decision Branch active AND severity ≥ Moderate.

**Severity triggers** (lines 2441-2457):
- Goal already overdue
- ≥2 deferrals within 7 days
- Protected block cancellation
- Abandonment language detected
- EARLY_EROSION or STRUCTURAL_DRIFT tier

**CIM Blocks (Tier-Dependent):**
- CLEAN: What compresses, compounds, becomes harder (3-6 lines, deterministic only)
- EROSION: Emphasizes erosion pattern reinforcement
- DRIFT: Integrates with 72h/30d modeling

#### R3 — Lexical Hardening

**Function:** `_normalize_input(user_input)` (lines 1309-1324)
- Lowercase → normalize curly apostrophes → strip apostrophes → remove punctuation → collapse spaces

Used for all deterministic pattern matching throughout Phase 3/4/5.

#### R4 — Abandonment Language Detection

**Function:** `_detect_abandonment_language(user_input)` (lines 2414-2430)

**Phrases:** "stop tracking", "drop it", "pause this", "shelve this", "scrap it", "restart next month", "give up", "giving up", "not ready to face", "walking away"

#### R5 — Enforcement Escalation Ladder

**Function:** `_evaluate_enforcement_level(gate_result, activation_state)` (lines 2210-2275)

| Level | Name | Triggers | Language Pattern |
|-------|------|----------|-----------------|
| 0 | Clarification | First deferral, no compounding | "Execute {subject} as scheduled." |
| 1 | Reinforcement | Single deferral OR mild erosion | "Do not reschedule. Complete {subject} tonight." |
| 2 | Containment | ≥2 deferrals/7d OR abandonment OR erosion tier OR protected block impact | "Stop deferring. Execute {subject} today." |
| 3 | Control Assertion | ≥2 deferrals + abandonment OR erosion + ≥2 deferrals OR abandonment + erosion markers | "This pattern ends now. Execute {subject}." |

**Important:** STRUCTURAL_DRIFT does NOT automatically force Level 3. Actual resistance patterns drive escalation.

#### Test Files

- `apps/core/tests/test_phase4_cos.py` — `DecisionBranchGateActivationTest`, `EnforcementLevelEvaluationTest`, `CIMSeverityTest`, `CIMBlocksByTierTest`, `CIMLanguageTest`, `LexicalHardeningTest`

---

### 2.3 Phase 5 Controls (ECC)

**File:** `apps/core/ai_orchestrator/commitment_contract.py`

#### Phase 5A — Commitment Detection & Field Extraction

**Commitment Triggers** (lines 120-128):
```python
_COMMITMENT_TRIGGERS = (
    'i am going to', 'im going to', 'i plan to',
    'i will', 'ill', 'lets', 'let us',
)
```

**Detection Function:** `detect_commitment_intent(text)` (lines 307-328) — Normalized substring matching. No NLP.

**Field Extraction:** `extract_commitment_fields(text)` (lines 331-421)

Extraction order:
1. Done-definition from ORIGINAL text (preserves case)
2. Done-definition clause stripped
3. Action from ORIGINAL text
4. Time display from ORIGINAL text
5. First letter of action/done-definition capitalized

**Done-Definition Patterns** (lines 161-167):
```python
_DONE_PATTERNS = (
    r"done (?:means|when|if|is when)\s+(.+)",
    r"(?:it's|its|it is) done (?:when|if)\s+(.+)",
    r"complete (?:means|when|if)\s+(.+)",
    r"finished (?:means|when|if)\s+(.+)",
    r"success (?:means|looks like)\s+(.+)",
)
```

**Time Boundary Patterns** (lines 136-153): Specific times, relative days, day-of-week, date patterns, relative durations, end-of-period expressions.

**Missing Field Priority:**
1. Missing time_boundary → `MissingField('time_boundary')`
2. Missing done_definition → `MissingField('done_definition')`
3. Both present → `CommitmentDraft`

**Tightening Questions** (`generate_tightening_question()`, lines 424-445):
- Time missing: `"When specifically will this be completed?"`
- Done-definition missing: `"What does 'done' mean in one sentence?"`

#### Phase 5B — Normalization & Renegotiation

**Commitment Types:** `DO`, `DECIDE`, `SCHEDULE`, `STOP` — classified via `_classify_commitment_type()`

**Normalization** (`normalize_commitment()`, lines 448-484):
```python
Commitment(
    normalized_text, commitment_type, time_boundary,
    done_definition, status='pending', time_boundary_display
)
```

**Renegotiation Rules** (`apply_renegotiation_rules()`, lines 487-521):

| Tier | Behavior |
|------|----------|
| CLEAN | Allow renegotiation IF new explicit time boundary present; if scope changed, require new done-definition |
| EARLY_EROSION | **Block entirely** → `RenegotiationBlocked` with two choices |
| STRUCTURAL_DRIFT | **Block entirely** → `RenegotiationBlocked` with two choices |

**Blocked Choices:**
- `"A) Keep original commitment with a 15-30 minute minimum version now"`
- `"B) Formally cancel and accept consequence"`

**Renegotiation Triggers** (lines 719-727):
```python
_RENEGOTIATION_TRIGGERS = ('move', 'push', 'delay', 'reschedule', 'next week', 'later', 'instead')
```

**Renegotiation Detection** (`_detect_renegotiation_intent()`, lines 719-745) — Checked BEFORE new commitment detection. Does NOT require commitment intent trigger.

#### Phase 5C — Closure & Positive Lock-In

**Closure Triggers** (lines 634-644):
```python
_CLOSURE_TRIGGERS = (
    'its done', 'done', 'finished', 'completed', 'i finished it',
    'yes', 'yeah', 'yep', 'yea',
)
```

**Closure Function** (`close_commitment()`, lines 524-562):
- Affirmative only (no negative) → `status = 'closed_success'`
- Negative only (no affirmative) → `status = 'closed_missed'`
- Ambiguous → `"Is it done — yes or no?"`

**Positive Lock-In** (`render_positive_lock_in()`, lines 602-624):
- ONLY renders if `status == 'closed_success'`
- Output: `"Time boundary honored. Repeat this structure."`
- Returns `None` for missed/pending/renegotiated

**Hard Short-Circuit in Pipeline** (`apps/ai/personal_assistant.py`, lines 3025-3085):

```python
# Sentinel setup
_ecc_closure_handled = False
_ecc_closure_response = ''

# Closure check FIRST
closure = process_ecc_closure(message, _ecc_restored)
if closure is not None:
    _ecc_closure_handled = True           # Set BEFORE DB ops
    _ecc_closure_response = closure['response']
    conversation.metadata.pop('ecc_active_commitment', None)
    conversation.save()
    return _ecc_closure_response          # Bypass LLM entirely

# Fallback hard short-circuit (if DB operation threw)
if _ecc_closure_handled and _ecc_closure_response:
    return _ecc_closure_response
```

#### Persistence

**Location:** `conversation.metadata['ecc_active_commitment']`

**Serialization:**
```python
commitment.to_dict() -> {
    'normalized_text': str,
    'commitment_type': str,
    'time_boundary': str (ISO format),
    'done_definition': str,
    'status': str,
    'time_boundary_display': Optional[str],
}
```

**Lifecycle:**
- Detection → serialize → store in metadata → save
- Next message → load from metadata → deserialize via `Commitment.from_dict()`
- Closure → remove from metadata → save

**Important:** Commitments are runtime-only. No DB model. Cleared on new conversation.

#### Exact Precedence Chain

```
Closure (5C) → Renegotiation (5B) → New Commitment (5A) → Intent Recognition
```

#### ECC Injection into LLM Prompt

**Function:** `format_ecc_injection(active_commitments)` (lines 847-886)
```
--- ACTIVE COMMITMENTS (ECC) ---
COMMITMENT [DO]: {action} {time}. Done means: {definition}.
ENFORCEMENT: Commitments require explicit closure (done or missed).
Do not allow ambiguous completion claims.
--- END ACTIVE COMMITMENTS ---
```

#### Test Files

| File | Coverage |
|------|----------|
| `apps/core/tests/test_phase5_commitment.py` | 28 test classes: detection, extraction, tightening, normalization, renegotiation, closure, lock-in, rendering |
| `apps/core/tests/test_phase5_commitment_pipeline.py` | 8 test classes: pipeline integration, short-circuit, precedence, cross-message continuity |

---

## 3) Time/Timezone and Scheduling Behavior

### Authoritative Time Source

**Function:** `get_current_local_datetime(user)` — `apps/core/utils.py`

This is an alias for `get_user_now()` (required by scheduling reliability contract). **All CoS code MUST use this function, never `timezone.now()`, `datetime.now()`, or `timezone.now().date()`.**

**System Clock:** `get_current_time(tz_str)` — `apps/core/time/system_clock.py`

### Timezone Loading

- **Storage:** `UserPreferences.timezone_iana` (IANA format, e.g., "America/New_York")
- **Legacy conversion:** `timezone_iana` property auto-converts "US/Eastern" → "America/Eastern"
- **Migration:** `0024_convert_legacy_timezones.py` handles old format
- **Supported:** 7 US timezones (ET, CT, MT, PT, AK, HI, UTC)

### Relative Date Parsing (HTIE)

Three-phase system:

1. **Parser** (`apps/core/time/parser.py`): Extracts temporal phrases using ordered regex patterns
2. **Ambiguity Detector** (`apps/core/time/ambiguity_detector.py`): Never guesses. Asks for clarification on:
   - "next Friday" if today IS Friday
   - "recently" (no concrete mapping)
   - Invalid month dates
3. **Resolver** (`apps/core/time/resolver.py`): Converts to precise timezone-aware datetimes

### Default Times

```python
TIME_OF_DAY = {
    'morning': time(9, 0),
    'afternoon': time(14, 0),
    'evening': time(18, 0),
    'night': time(21, 0),
}
```

- Event duration default: 1 hour (if start_time specified but no end_time)
- All-day default: midnight to 23:59:59 (when no time specified)

### Calendar Scheduling Flow

```
User says "Schedule a workout tomorrow at 6am"
    │
    ├─ Intent Recognition (OpenAI function calling)
    │   └─ System prompt includes user-local date (NOT UTC)
    │
    ├─ IntentResult: intent_type='create_event', parameters={title, start_time, ...}
    │
    ├─ Time Resolution (HTIE)
    │   └─ "tomorrow at 6am" → concrete datetime in user timezone
    │
    ├─ Action Handler: handle_create_event()
    │   ├─ Create CalendarEvent (timezone-aware start_dt, end_dt)
    │   ├─ Store scheduling context in cache (30-min TTL)
    │   └─ Fire intelligence chain (PIE, PRIE)
    │
    └─ Post-scheduling chain:
        ├─ Conflict detection
        ├─ Drift recomputation
        └─ Google Calendar sync (if connected)
```

### Clone/Same Event Behavior

Implemented 2026-02-22. When user says "same workout":

- Intent emits `clone_from_last=true`
- Handler retrieves prior context from Django cache (30-min TTL, key: `scheduling_context_{user.id}`)
- Inherits: title, start_time, end_time, location, description, event_type, is_all_day
- Explicit parameters override inherited values
- Safety assertion: cloned_event.time must match original_event.time

### Recent Hardening (2026-02-22)

1. **Date Authority:** Use `get_current_local_datetime(user)`, never UTC date
2. **Parameter Inheritance:** Cache-based context with 30-min TTL
3. **Safety Invariants:** Warn if time defaults to all-day during clone
4. **Debug Logging:** `[SCHED]` prefix at all decision points
5. **22 new scheduling reliability tests** (zero regressions)

### Calendar Model

**File:** `apps/calendar_engine/models.py`

**`CalendarEvent`**: Stores timezone-aware `start_dt`, `end_dt` with `RecurrenceRule` support.

---

## 4) Memory, State, and Persistence

### 4.1 User State Model

**File:** `apps/core/ai_state/models.py`

**`UserState`** — Authoritative user state snapshot maintained by SAE:
- Health metrics, journal activity, faith engagement, goal progress, habit streaks
- Module-specific builders in `state_builder.py`
- Updated incrementally via `state_updater.py` after each action

**SAE Write Blocking:** During Learning Mode, `update_user_state()` skips writes (`state_updater.py:36-42`):
```python
if is_learning_mode_active(user):
    logger.debug("SAE write blocked (Learning Mode active)")
    return
```

### 4.2 Conversation Metadata

**Model:** `AssistantConversation` (`apps/ai/models.py`)

**Key metadata keys:**

| Key | Type | Purpose | Set By | Cleared By |
|-----|------|---------|--------|------------|
| `ecc_active_commitment` | dict | Active ECC commitment | Phase 5A detection | Phase 5C closure |
| `awaiting_data_visibility_confirmation` | bool | Data visibility gate | Pipeline step 7 | Confirmation handler |
| `awaiting_data_type` | str | Data type needing confirmation | Pipeline step 7 | Confirmation handler |
| `calibration_*` | various | Calibration state | Calibration flow | Calibration completion |

### 4.3 Conversation Messages

**Model:** `AssistantMessage` (`apps/ai/models.py`)
- `conversation` (FK), `role` (user/assistant), `content` (text), `image_data`, `image_mime_type`
- `was_helpful` (user feedback), `quick_reply_data` (JSON)
- Created for both user input and assistant response

### 4.4 EngineRun and Observability

**Model:** `EngineRun` (`apps/core/ai_observability/models.py`)
- `trace_id` (correlates all runs in one request)
- `engine_name`, `phase`, `started_at`, `ended_at`, `duration_ms`
- `status` (success/error/skipped), `error_type`, `error_message`
- `input_fingerprint`, `output_fingerprint`, `user_id`, `metadata`

**Model:** `EngineSpan` — Sub-step within an engine run

**Model:** `DecisionRecord` — Why an engine made a decision
- Types: arbitration, suppression, delivery_route, guidance_rank, insight_filter, noise_budget, prediction_store

### 4.5 Caching Layers

| Cache Key Pattern | TTL | Purpose |
|-------------------|-----|---------|
| `system_prompt_{style}_{faith}` | 1 hour | Base system prompt |
| `coaching_styles_all` | 1 hour | Coaching style list |
| `ai_prompt_config_{type}` | 1 hour | Prompt config lookup |
| `scheduling_context_{user_id}` | 30 min | Clone/same event context |
| `pending_intent_{user_id}` | 5 min | Pending confirmation storage |
| `values_guardrail_patterns_input` | 1 hour | Input filter patterns |
| `values_guardrail_patterns_output` | 1 hour | Output filter patterns |

### 4.6 rebuild_user_state

**Function:** `rebuild_user_state(user)` — `apps/core/ai_state/state_engine.py`

Full state reconstruction from DB. Used on first access and periodic refresh. Instrumented via `@_instrument_engine_run("SAE", 3)` decorator.

---

## 5) Intent Recognition and Routing

### 5.1 Intent Recognition Service

**File:** `apps/ai/intent_service.py`

**Class:** `IntentService`

**Primary Method:** `recognize_intents(user_message, user) → List[IntentResult]`
- Uses OpenAI function calling with structured tools
- System prompt includes user-local date (critical for relative date resolution)
- Supports multi-command: "update my oxygen to 95 and my weight to 350" → 2 IntentResults

### 5.2 All Intent Types

| Category | Intent Types |
|----------|-------------|
| **Health** | `log_heart_rate`, `log_blood_pressure`, `log_weight`, `log_glucose`, `log_blood_oxygen`, `log_food` |
| **Medicine** | `take_medicine` |
| **Fasting** | `start_fast`, `end_fast` |
| **Journal** | `create_journal_entry`, `add_gratitude` |
| **Faith** | `log_prayer`, `mark_prayer_answered`, `save_verse`, `add_faith_milestone` |
| **Purpose** | `create_goal`, `update_goal_progress`, `set_intention`, `log_habit` |
| **Life** | `create_task`, `complete_task`, `create_event`, `add_reminder` |
| **Fitness** | `log_workout`, `log_exercise_set`, `log_cardio` |
| **Transformation** | `log_transformation_protocol`, `log_shopping_item`, `complete_shopping_item` |
| **Settings** | `set_cos_name` |
| **Calibration** | `pause_calibration`, `complete_calibration` |
| **Learning Mode** | `exit_learning_mode`, `enter_learning_mode` |

### 5.3 Routing

**File:** `apps/core/ai_orchestrator/intent_engine.py`

**Function:** `get_intent_module(intent_type) → str` — Maps intent to WLJ module (health, faith, journal, purpose, life, etc.)

**Time-Aware Intents:** All health, medicine, fasting, journal, faith, fitness, transformation, `log_habit`, `complete_task`
**Context-Aware Intents:** `mark_prayer_answered`, `save_verse`, `update_goal_progress`, `complete_task`

### 5.4 Priority vs ECC

**Precedence:**
1. Phase 5C closure (hard short-circuit)
2. Phase 5A/5B commitment (detection, renegotiation)
3. Proactive confirmation
4. Calibration
5. Data visibility confirmation
6. Learning mode exit
7. Pending confirmation
8. **Normal intent recognition** ← Only reached if all above pass through

### 5.5 Confidence and Validation

**Validation Layer** (`_check_validation()` in `IntentService`):
- Health-specific ranges (heart rate 40-180, BP 90-180/60-110, weight 50-500, glucose 40-400, SpO2 95%+)
- Out-of-range values trigger confirmation before execution

**Ambiguity Handling:**
- HTIE: Asks clarification for ambiguous times
- SLCME: Asks clarification for ambiguous context references below confidence threshold
- SUE: Falls through to LLM if semantic confidence is low

---

## 6) LLM Orchestration

### 6.1 Models

**Configuration** (`config/settings.py`):
```
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY')       # Required
OPENAI_MODEL = os.environ.get('OPENAI_MODEL', 'gpt-4o') # Default
OPENAI_VISION_MODEL = os.environ.get('OPENAI_VISION_MODEL', 'gpt-4o')
```

**AIService initialization** (`apps/ai/services.py:95-96`):
```python
self.model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
```

**Timeout:** `LLM_TIMEOUT_SECONDS = 40`

### 6.2 PriceBook & Cost Tracking

**Models** (`apps/owner_finance/models.py`):
- `LLMPriceBook` — Per-model pricing (input/output cost per 1M tokens, effective date range)
- `LLMUsageEvent` — Per-call telemetry (user, feature, model, tokens, cost_usd, escalated)
- `DailyCostRollup` — Pre-aggregated daily summary
- `BudgetGuardrail` — Configurable spend limits (total, per-user, per-feature)

**Telemetry** (`apps/owner_finance/services/telemetry.py`):
```python
log_llm_usage(user=user, feature='COS_CHAT', model_name='gpt-4o',
              input_tokens=1500, output_tokens=300)
```
- Auto-computes cost from PriceBook lookup
- Best-effort; never raises on failure
- If PriceBook missing: stores `cost=0` with `missing_pricebook=True` in metadata

**Feature Categories:** INTENT, MAIN_RESPONSE, JOURNAL_REFLECTION, DAILY_INSIGHT, WEEKLY_SUMMARY, COS_CHAT, EXEC_BRIEFING, VISION, TRANSCRIPTION, SUMMARIZATION, NUTRITION_AI, OTHER

### 6.3 Prompt Assembly

**System Prompt Construction** (`apps/ai/services.py:168-233`):

1. **Base System Prompt** — From `AIPromptConfig` (database) or `FALLBACK_SYSTEM_BASE` (hardcoded)
2. **Coaching Style** — From `CoachingStyle` model (database), cached 1 hour
3. **Faith Context** — Conditional on `faith_enabled` preference
4. **User Profile** — Via `build_safe_profile_context()` with `PROFILE_SAFETY_INSTRUCTIONS`
5. **Personal Context** — Via `build_personal_context_prompt()`
6. **CoS Injection** — `format_cos_system_injection(cos_context)` with:
   - Blueprint state, protected tiers, capacity snapshot
   - Module permissions, active commitments
   - Trajectory framework (tier-dependent)
   - Calendar events today, risk warnings

**User profile is NOT cached** (varies per user, safety processing each time).

### 6.4 Guardrails

**Content Filter** (`apps/ai/values_filter.py`):
- `ValuesGuardrailPattern` model — Regex patterns by category (explicit, violence, illegal, injection, hate, off_topic, negative)
- Severity: `refuse` (block completely) or `redirect` (gentle redirection)
- Applied to both input and output
- Cached 1 hour, invalidated on save/delete

**Appeal Flow:** User responds "yes" → email sent to admin → message marked as appealed

**Profile Safety:** Never repeat user profile verbatim, no medical/legal/financial advice, suggest professional support for concerning content.

### 6.5 Failure Handling

**Retry Logic** (`apps/ai/services.py:263-384`):
```python
LLM_MAX_RETRIES = 3
LLM_BASE_BACKOFF_SECONDS = 1.0  # Doubles: 1s, 2s, 4s
```

**Flow:**
1. Check client availability (API key configured)
2. Retry loop with exponential backoff
3. Log success with token counts and latency
4. On all retries exhausted: log error, return `None`

**Degraded Mode:** When `_call_api()` returns `None`, callers handle gracefully (return generic message or skip AI feature).

---

## 7) Observability & Admin Console Surfaces

### 7.1 Operations Wall

**URL:** `/admin-console/ops/`
**File:** `apps/core/ai_observability/ops_views.py`

**Real-time polling endpoint** (`/admin-console/ops/stream/`):
```json
{
    "server_time": "ISO",
    "posture": "OK|WARN|CRIT",
    "engine_cards": [{"name", "status", "last_run_at", "avg_duration_15m", "error_rate_15m", "runs_15m"}],
    "narrative": {"posture", "headline", "bullets_now", "recommendations", "watching_next"},
    "anomalies": [{"severity", "engine_name", "anomaly_type", "summary"}],
    "feed": [],
    "integrity": {"aggregate_integrity", "posture"},
    "scheduler_heartbeats": {}
}
```

**Engine Status Logic:**
- `gray`: Never run
- `red`: Error rate > 20%
- `yellow`: Error rate > 5% OR last run > 2× cadence
- `green`: Normal

### 7.2 Diagnostics Console

**URL:** `/admin-console/diagnostics/`
**File:** `apps/core/ai_observability/diagnostics_views.py`

- Engine runs with trace correlation
- Decision records with rationale
- Trace waterfall detail view

### 7.3 System Integrity Index

**Computation:**
```
Base: 100
- Engine health: -(1-pct_ok)×40
- Anomaly severity: -severity_weight (max 50)
- Error spike: -min(error_rate×50, 10)
- Suppression rate: -max(0, (rate-0.5)×10) (max 5)
- Confidence volatility: -min((stddev-0.3)×15, 5)
```

**Posture:** OPTIMAL (90-100), NOMINAL (70-89), DEGRADED (40-69), CRITICAL (0-39)

### 7.4 Alerting

- Email alerts for critical anomalies
- Ops Wall real-time visibility
- Heartbeat monitoring (ISE + SAME)
- No automated Slack/PagerDuty integration

---

## 8) Test Coverage Map

### Test Files → Coverage

| Test File | Covers | Does NOT Cover |
|-----------|--------|----------------|
| `apps/core/tests/test_phase5_commitment.py` | Detection, extraction, tightening, normalization, renegotiation, closure, lock-in (28 classes) | Multi-turn history, concurrent commitments, partial achievement |
| `apps/core/tests/test_phase5_commitment_pipeline.py` | Pipeline integration, short-circuit, precedence, cross-message (8 classes) | Failure scenarios, multi-turn renegotiation, tier-aware enforcement |
| `apps/core/tests/test_phase4_cos.py` | Activation states, framework injection, decision branch, enforcement levels, CIM (11 classes) | Real LLM integration, state mutation effects, feedback loops |
| `apps/core/tests/test_phase4_verification.py` | Rule registration, noise budget, confidence adjustment, escalation, briefing length (7 classes) | Cross-domain rule firing, budget saturation, scheduler precision |
| `apps/ai/tests/test_scheduling_reliability.py` | Timezone authority, local date resolution, parameter inheritance (22 tests) | DST edge cases, collision detection, recurring event inheritance |
| `apps/ai/tests/test_ai_comprehensive.py` | AIInsight, AIService, caching, coaching styles, errors (100+ tests) | Real OpenAI API, rate limiting, token budget enforcement |
| `apps/ai/tests/test_intent_service.py` | Intent recognition, action handlers, confirmation flow | Multi-command edge cases, concurrent intents |
| `apps/core/ai_orchestrator/tests.py` | Orchestrator pipeline, action routing, time/context pipeline (16 classes) | Concurrent execution, rollback, module downtime |
| `apps/core/ai_guidance/tests.py` | Guidance rules, ranking, dedup, lifecycle (109 tests) | Cross-engine state inconsistency, ranking under load |
| `apps/core/ai_predictions/tests.py` | Prediction rules, confidence scoring, projection math (32 tests) | Long-term accuracy validation, model drift |
| `apps/core/ai_briefing/tests.py` | Briefing generation, selection, ranking (27 tests) | Race conditions, user with 0 data |
| `apps/core/ai_weekly_report/tests.py` | Report generation, selection, ranking (54 tests) | Week boundary edge cases, timezone-aware week starts |
| `apps/core/ai_explain/tests.py` | Explain records, evidence builder (37 tests) | On-demand creation race conditions |
| `apps/core/ai_delivery/tests.py` | Delivery engine, policies, routing (29 tests) | Channel failure cascades, throttle edge cases |
| `apps/core/ai_quality/tests.py` | Quality gate, repeat suppression, conflict detection | Suppression false positives at scale |
| `apps/core/ai_observability/tests_diagnostics.py` | EngineRun, DecisionRecord, trace context | Trace correlation under high concurrency |
| `apps/core/ai_observability/tests_ops_wall_v2.py` | Ops Wall views, anomaly detection | Real SAME cycle integration |
| `apps/dashboard/tests/test_cos_unification.py` | AM/PM formatting, timeline cap, banned terms, greeting | Context accuracy, responsive layout |

### Blind Spots (Untested Critical Paths)

1. **LLM unavailability** — No tests for OpenAI API outage during conversation
2. **Database connection loss** — No tests for mid-conversation DB failure
3. **Redis unavailability** — No tests for cache/queue offline
4. **Concurrent conversation handling** — Same user, two open conversations
5. **Daylight Savings transitions** — Spring/fall edge cases in scheduling
6. **State rollback on error** — Failed action, does state revert?
7. **Multi-turn commitment chains** — Stacking "I'll do X, then Y, then Z"
8. **Commitment memory across sessions** — New conversation starts fresh (by design, but untested assumption)
9. **Calendar event collision detection** — Two events at same time
10. **Large data volumes** — User with 1000+ closed commitments, 100+ timeline blocks

---

## 9) Known Limitations & Risk Register

### Silent Defaults

| Default | Location | Impact |
|---------|----------|--------|
| `OPENAI_MODEL = 'gpt-4o-mini'` | `apps/ai/services.py:95` | Falls back to cheaper model if env var missing |
| `intelligence_max_per_day = 6` | DNE user prefs | User receives max 6 notifications/day |
| `intelligence_max_per_hour = 2` | DNE user prefs | Max 2 notifications/hour |
| `LLM_MAX_RETRIES = 3` | `apps/ai/services.py` | 3 retries before giving up |
| `Commitment status = 'pending'` | `commitment_contract.py` | New commitments always start pending |
| `Confidence threshold = 0.8` | LearnedMapping default | SLCME auto-uses above 0.8 |
| `SESSION_COOKIE_AGE = 86400` | settings.py | 24 hours before session expires |

### Swallowed Exceptions

| Location | Pattern | Risk |
|----------|---------|------|
| `cos_context.py:_source_integrity_gate()` | `try/except → None` | Missing trajectory signals silently produce placeholders |
| `execution_engine.py:_run_intelligence_chain()` | `try/except → log` | PIE/PRIE failures don't break action execution |
| `personal_assistant.py:~3001` ECC pre-check | `except Exception as ecc_err: logger.debug()` | ECC errors logged at DEBUG level, pipeline continues |
| `state_updater.py:36-42` | `except Exception: pass` | Learning mode check failure → state update proceeds |
| All engine imports | `ImportError guard` | Missing engine package → feature silently disabled |
| `log_llm_usage()` | `try/except → pass` | Telemetry failure → cost not recorded |
| `E3 hooks` | `try/except` | Explain record creation failure → no explanation available |

### "Best Effort" Writes

| Write | Location | Risk |
|-------|----------|------|
| `conversation.metadata` save | `personal_assistant.py` | If save fails, commitment state lost (mitigated by sentinel) |
| `AssistantMessage.objects.create()` | Phase 5C fallback | Best-effort message creation after closure |
| `log_llm_usage()` | `telemetry.py` | Cost tracking is best-effort, never blocks |
| `EngineRun` creation | Instrumentation decorator | Observability is fire-and-forget |

### Multi-Entrypoint Inconsistencies

- `POST /ai/chat/` goes through full `send_message()` pipeline
- `GET /ai/opening/` bypasses ECC, intent recognition, and action execution
- Admin console views bypass all CoS enforcement
- Direct engine triggers via Ops Wall bypass the orchestrator pipeline

### Timezone Risks

- **UTC date mismatch:** Using `timezone.now().date()` returns UTC date, which may differ from user's local date near midnight — mitigated by `get_current_local_datetime()` but requires all code paths to use it
- **DST transitions:** Not tested; could cause 1-hour scheduling errors during spring/fall transitions
- **User timezone change:** If user changes timezone mid-conversation, cached scheduling context may have stale timezone

### Concurrency Risks

- **No locking on commitment operations:** If user submits 2 messages rapidly, both may process against same pending commitment
- **Last-write-wins on metadata:** `conversation.save(update_fields=['metadata'])` — concurrent writes overwrite
- **Calendar event creation:** No conflict detection for overlapping events
- **ISE scheduler:** Uses `scheduler_lock.py` for single-instance enforcement

### Areas Where Behavior May Drift from "Executive-Grade" Expectations

1. **Commitment is runtime-only:** Commitments don't survive new conversations. User cannot query "What did I commit to yesterday?"
2. **No commitment database model:** No historical tracking, no aggregate patterns, no long-term accountability
3. **Tier is per-request, not per-session:** A single positive message can drop STRUCTURAL_DRIFT back to CLEAN if thresholds are no longer met
4. **ECC false positives:** "I'll have pizza" triggers commitment detection (substring "I'll")
5. **No undo for tightening:** Once ECC asks a tightening question, user must answer or start over
6. **Enforcement has no memory:** Level 3 enforcement doesn't "remember" it was level 3 for next conversation
7. **PriceBook gap:** If model pricing not configured, cost=0 stored (silent cost tracking failure)

---

## 10) Appendices

### A) Full File List for CoS-Related Modules

```
# AI Service Layer
apps/ai/views.py
apps/ai/personal_assistant.py
apps/ai/services.py
apps/ai/intent_service.py
apps/ai/action_handlers.py
apps/ai/models.py
apps/ai/values_filter.py
apps/ai/profile_moderation.py
apps/ai/personal_context.py
apps/ai/confirmation_detector.py
apps/ai/urls.py

# Core Orchestrator
apps/core/ai_orchestrator/__init__.py
apps/core/ai_orchestrator/orchestrator.py
apps/core/ai_orchestrator/execution_engine.py
apps/core/ai_orchestrator/cos_context.py
apps/core/ai_orchestrator/commitment_contract.py
apps/core/ai_orchestrator/action_router.py
apps/core/ai_orchestrator/intent_engine.py
apps/core/ai_orchestrator/time_pipeline.py
apps/core/ai_orchestrator/context_pipeline.py
apps/core/ai_orchestrator/safety_engine.py
apps/core/ai_orchestrator/response_builder.py
apps/core/ai_orchestrator/briefing_formatter.py
apps/core/ai_orchestrator/intelligence_hook.py
apps/core/ai_orchestrator/learning_pipeline.py
apps/core/ai_orchestrator/audit_logger.py
apps/core/ai_orchestrator/tests.py

# Time (HTIE)
apps/core/time/parser.py
apps/core/time/resolver.py
apps/core/time/ambiguity_detector.py
apps/core/time/system_clock.py

# Memory (SLCME)
apps/core/ai_memory/models.py

# Semantics (SUE)
apps/core/ai_semantics/semantic_engine.py
apps/core/ai_semantics/models.py

# State (SAE)
apps/core/ai_state/state_engine.py
apps/core/ai_state/state_builder.py
apps/core/ai_state/state_updater.py
apps/core/ai_state/models.py

# Insights (PIE)
apps/core/ai_insights/insight_engine.py
apps/core/ai_insights/rules_health.py
apps/core/ai_insights/rules_body_composition.py
apps/core/ai_insights/rules_labs_vitals.py
apps/core/ai_insights/rules_goals.py
apps/core/ai_insights/rules_habits.py
apps/core/ai_insights/rules_scripture.py
apps/core/ai_insights/rules_journal.py
apps/core/ai_insights/rules_transformation.py
apps/core/ai_insights/models.py

# Predictions (PRIE)
apps/core/ai_predictions/prediction_engine.py
apps/core/ai_predictions/base_prediction_rule.py
apps/core/ai_predictions/prediction_registry.py
apps/core/ai_predictions/projection_math.py
apps/core/ai_predictions/confidence_engine.py
apps/core/ai_predictions/models.py

# Guidance (PGE)
apps/core/ai_guidance/guidance_engine.py
apps/core/ai_guidance/guidance_selector.py
apps/core/ai_guidance/guidance_ranker.py
apps/core/ai_guidance/guidance_logger.py
apps/core/ai_guidance/guidance_rules.py
apps/core/ai_guidance/guidance_registry.py
apps/core/ai_guidance/models.py
apps/core/ai_guidance/views.py

# Guidance Learning (GLOE)
apps/core/ai_guidance_learning/learning_engine.py
apps/core/ai_guidance_learning/learning_calculator.py
apps/core/ai_guidance_learning/learning_logger.py
apps/core/ai_guidance_learning/learning_models.py

# Quality (ICQG)
apps/core/ai_quality/quality_gate.py
apps/core/ai_quality/repeat_suppression.py
apps/core/ai_quality/conflict_detector.py
apps/core/ai_quality/quality_models.py
apps/core/ai_quality/quality_metrics.py

# Briefing (DBE)
apps/core/ai_briefing/briefing_engine.py
apps/core/ai_briefing/briefing_selector.py
apps/core/ai_briefing/briefing_ranker.py
apps/core/ai_briefing/briefing_logger.py
apps/core/ai_briefing/models.py

# Weekly Report (WIRE)
apps/core/ai_weekly_report/report_engine.py
apps/core/ai_weekly_report/report_selector.py
apps/core/ai_weekly_report/report_ranker.py
apps/core/ai_weekly_report/report_logger.py
apps/core/ai_weekly_report/models.py

# Evidence (E3)
apps/core/ai_explain/explain_engine.py
apps/core/ai_explain/evidence_builder.py
apps/core/ai_explain/explain_templates.py
apps/core/ai_explain/explain_logger.py
apps/core/ai_explain/models.py
apps/core/ai_explain/views.py

# Delivery (DNE)
apps/core/ai_delivery/delivery_engine.py
apps/core/ai_delivery/delivery_policies.py
apps/core/ai_delivery/delivery_router.py
apps/core/ai_delivery/delivery_logger.py
apps/core/ai_delivery/models.py
apps/core/ai_delivery/views.py

# Scheduler (ISE)
apps/core/ai_scheduler/scheduler_engine.py
apps/core/ai_scheduler/scheduler_runner.py
apps/core/ai_scheduler/scheduler_models.py
apps/core/ai_scheduler/scheduler_registry.py
apps/core/ai_scheduler/scheduler_lock.py

# Observability (SAME + IOCD)
apps/core/ai_observability/same_engine.py
apps/core/ai_observability/heartbeat.py
apps/core/ai_observability/ops_anomalies.py
apps/core/ai_observability/ops_aggregates.py
apps/core/ai_observability/ops_feed.py
apps/core/ai_observability/ops_views.py
apps/core/ai_observability/diagnostics_views.py
apps/core/ai_observability/observability_engine.py
apps/core/ai_observability/metrics_calculator.py
apps/core/ai_observability/engine_registry.py
apps/core/ai_observability/models.py

# Persona
apps/core/ai_persona/persona_adaptation.py
apps/core/ai_persona/persona_profiles.py

# Blueprint
apps/core/blueprint/engine.py
apps/core/blueprint/models.py
apps/core/blueprint/learning_mode.py

# Calendar
apps/calendar_engine/models.py

# Cost Tracking
apps/owner_finance/models.py
apps/owner_finance/services/telemetry.py

# Configuration
config/settings.py
config/celery.py
```

### B) All Metadata Keys Used by CoS

| Key | Location | Purpose | Lifecycle |
|-----|----------|---------|-----------|
| `ecc_active_commitment` | `conversation.metadata` | Active ECC commitment (serialized dict) | Set on detection, removed on closure |
| `awaiting_data_visibility_confirmation` | `conversation.metadata` | Data visibility gate active | Set when gate triggered, cleared on response |
| `awaiting_data_type` | `conversation.metadata` | Which data type needs confirmation | Set with above, cleared with above |
| `calibration_active` | `conversation.metadata` | Calibration session in progress | Set on calibration start, cleared on completion |
| `calibration_next_question` | `conversation.metadata` | Next calibration question index | Updated each calibration step |

### C) All Celery Schedules Relevant to CoS/Engines

**Defined in:** `config/settings.py` (`CELERY_BEAT_SCHEDULE`)

| Schedule Name | Task | Interval | Purpose |
|---------------|------|----------|---------|
| ISE | `apps.core.ai_scheduler.scheduler_runner` | Every 5 minutes | Run all scheduled intelligence tasks |
| SAME | `apps.core.tasks.run_same_cycle_task` | Every 60 seconds | Autonomous monitoring cycle |

**ISE-Managed Schedules (via ScheduledIntelligenceTask):**

| Engine | Interval | Management Command |
|--------|----------|--------------------|
| PIE | Daily + event-driven | `run_insights` |
| PRIE | Daily + event-driven | `run_prediction_engine` |
| PGE | Every 6 hours | `run_guidance_refresh` |
| GLOE | Every 6 hours + event-driven | `run_learning_profile_updates` |
| DBE | Daily | `generate_daily_briefings` |
| WIRE | Weekly (604800s) | `run_weekly_reports` |
| DNE | Every 10 minutes (600s) | `run_delivery_cycle` |
| IOCD | Daily | `generate_daily_snapshot` |

### D) All Environment Variables Influencing CoS Behavior

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_KEY` | **Required** | LLM access; no response if missing |
| `OPENAI_MODEL` | `gpt-4o` | LLM model selection |
| `OPENAI_VISION_MODEL` | `gpt-4o` | Vision model for image analysis |
| `DATABASE_URL` | SQLite (dev) | Database connection |
| `REDIS_URL` | `localhost:6379/0` | Cache + Celery broker |
| `CELERY_BROKER_URL` | `REDIS_URL` | Message queue |
| `SECRET_KEY` | **Required** | Django secret key |
| `DEBUG` | `False` | Debug mode (affects Sentry, email backend) |
| `GOOGLE_CALENDAR_CLIENT_ID` | Empty | Calendar OAuth |
| `GOOGLE_CALENDAR_CLIENT_SECRET` | Empty | Calendar OAuth |
| `STRIPE_PUBLIC_KEY` | Empty | Billing |
| `STRIPE_SECRET_KEY` | Empty | Billing |

**Note:** There are **NO environment variables dedicated to CoS behavioral control**. All enforcement (ECC, tiers, escalation) is hardcoded and deterministic. There are no feature flags or toggles for CoS behavior.

---

*End of Report*
