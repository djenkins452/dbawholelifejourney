# WLJ Engine Catalog

Complete inventory of the Whole Life Journey three-phase intelligence pipeline engines, verified against source code with `file:line` evidence.

**Method:** Cross-referenced the authoritative auto-maintained doc `docs/ENGINE_COS_REFERENCE.md` (Engine Inventory + schedules), `docs/INTELLIGENCE_ARCHITECTURE.md`, and `docs/ENGINE_INTEGRATION_GUIDE.md` against actual code under `apps/core/ai_*`, `apps/core/blueprint`, `apps/core/execution`, `apps/core/signals`, plus `config/settings.py :: CELERY_BEAT_SCHEDULE` and `apps/core/ai_scheduler/scheduler_registry.py`.

**Pipeline shape (per code + docs):**

```
Phase 1 (Interpretation)     Phase 2 (Execution)        Phase 3 (Post-Execution)
├─ SUE   (semantic)          ├─ UAIO  (orchestrator)    ├─ SAE   (state)
├─ SLCME (memory)            ├─ Intent Engine            ├─ PIE   (insights)
└─ HTIE  (time)              ├─ Execution Engine          ├─ PRIE  (predictions)
                             ├─ Safety Engine             ├─ PGE   (guidance)
                             ├─ Action Router             ├─ GLOE  (guidance learning)
                             ├─ ETE   (execution truth)   ├─ DBE   (daily briefing)
                             └─ Today Engine              ├─ WIRE  (weekly report)
                                                          ├─ E3    (explain)
                                                          ├─ DNE   (delivery)
                                                          ├─ ISE   (scheduler)
                                                          ├─ IOCD  (observability)
                                                          ├─ SAME  (ops monitoring)
                                                          ├─ Maturity, AAFR, PGS
                                                          ├─ Blueprint engines (12)
                                                          ├─ UAL/Capacity (arbitration)
                                                          ├─ EAE   (executive arbitration)
                                                          ├─ CDCE  (cross-domain)
                                                          ├─ Persona, Relationship
                                                          └─ Signal V3 / Unified Feed
```

**Central truth layer:** `UserState` model (SAE) — one JSON row per user keyed by module. Engines are expected to read SAE, not raw tables.

---

## Master Summary Table

| Engine | Acronym | Phase | Cadence | Status | Primary file:line |
|--------|---------|-------|---------|--------|-------------------|
| Semantic Engine | SUE | 1 Interpretation | Per request | Active | `apps/core/ai_semantics/semantic_engine.py:102` (`interpret`) |
| Ambiguity Engine | SUE | 1 Interpretation | Per request | Active | `apps/core/ai_semantics/ambiguity_engine.py` |
| Confidence Engine (semantic) | SUE | 1 Interpretation | Per request | Active | `apps/core/ai_semantics/confidence_engine.py` |
| Memory Engine | SLCME | 1 Interpretation | Per request | Active | `apps/core/ai_memory/memory_engine.py:63` (`resolve_context`) |
| Learning Engine (memory) | SLCME | 1/3 cross | Post-execution | Active | `apps/core/ai_memory/learning_engine.py` |
| Retrieval Engine | SLCME | 1 Interpretation | Per request | Active | `apps/core/ai_memory/retrieval_engine.py` |
| Confidence Engine (memory) | SLCME | 1 Interpretation | Per request | Active | `apps/core/ai_memory/confidence_engine.py` |
| Time Pipeline | HTIE | 1 Interpretation | Per request | Active | `apps/core/ai_orchestrator/time_pipeline.py:15` (`resolve_time_pipeline`) |
| Orchestrator | UAIO | 2 Execution | Per request | Active | `apps/core/ai_orchestrator/orchestrator.py:127` (`process_user_input`) |
| Intent Engine | UAIO | 2 Execution | Per request | Active | `apps/core/ai_orchestrator/intent_engine.py:150` (`get_intent_module`) |
| Execution Engine | UAIO | 2 Execution | Per request | Active | `apps/core/ai_orchestrator/execution_engine.py:39` (`execute_action`) |
| Safety Engine | UAIO | 2 Execution | Per request | Active | `apps/core/ai_orchestrator/safety_engine.py:53` (`validate_action`) |
| Action Router | UAIO | 2 Execution | Per request | Active | `apps/core/ai_orchestrator/action_router.py:60` (`route_action`) |
| Execution Truth Engine | ETE | 2 Execution | Per request | Active | `apps/core/execution/execution_truth_engine.py:81` (`get_execution_truth`) |
| Today Engine | — | 2 Execution | Per request | Active | `apps/core/today/today_engine.py` (`build_today`) |
| State Engine | SAE | 3 Post-exec | Per-request reads + ISE 5m batch | Active | `apps/core/ai_state/state_engine.py:19` (`get_user_state` / `rebuild_user_state:95`) |
| Insight Engine | PIE | 3 Post-exec | Event + ISE 5m | Active | `apps/core/ai_insights/insight_engine.py:21` (`run_insights`) |
| Prediction Engine | PRIE | 3 Post-exec | Event + ISE 1h | Active | `apps/core/ai_predictions/prediction_engine.py:128` (`generate_predictions`) |
| Trajectory Engine | PRIE | 3 Post-exec | Per request | Active | `apps/core/ai_predictions/trajectory_engine.py` |
| Guidance Engine | PGE | 3 Post-exec | ISE 6h | Active | `apps/core/ai_guidance/guidance_engine.py:24` (`generate_guidance`) |
| Guidance Learning Engine | GLOE | 3 Post-exec | ISE 6h | Active | `apps/core/ai_guidance_learning/learning_engine.py:20` (`update_learning_profile`) |
| Briefing Engine | DBE | 3 Post-exec | ISE 24h | Active | `apps/core/ai_briefing/briefing_engine.py:26` (`generate_daily_briefing`) |
| Weekly Report Engine | WIRE | 3 Post-exec | ISE 7d | Active | `apps/core/ai_weekly_report/report_engine.py:23` (`generate_weekly_report`) |
| Explain Engine | E3 | 3 Post-exec | Post-store hook | Active | `apps/core/ai_explain/explain_engine.py:45` (`ensure_explain_record`) |
| Delivery Engine | DNE | 3 Post-exec | ISE 10m | Active | `apps/core/ai_delivery/delivery_engine.py:18` (`deliver_due_notifications`) |
| Scheduler Engine | ISE | 3 / cross-cut | Celery 5m | Active | `apps/core/ai_scheduler/scheduler_engine.py:28` (`run_scheduler_cycle`) |
| Observability Engine | IOCD | 3 Post-exec | ISE 24h | Active | `apps/core/ai_observability/observability_engine.py:27` (`generate_daily_snapshot`) |
| SAME Monitoring Engine | SAME | Cross-cutting | Celery 60s | Active | `apps/core/ai_observability/same_engine.py:32` (`run_same`) |
| Maturity Engine | — | 3 Post-exec | On-demand + ISE create_maturity_snapshot 24h | Active | `apps/core/ai_observability/maturity_engine.py:30` (`compute_all_maturity_scores`) |
| AAFR Telemetry | AAFR | 2/3 cross | Every `execute_action` | Active | `apps/core/ai_orchestrator/execution_engine.py:22` (`_record_aafr`) |
| Proactive Guidance Scheduler | PGS | 3 Post-exec | ISE 15m | Active | `apps/ai/proactive_checkins.py:3078` (`run_proactive_guidance_scheduler`) |
| Arbitration Engine | UAL | 3 Post-exec | ISE 5m (`run_ual_synthetic`) | Active | `apps/core/ai_arbitration/arbitration_engine.py:64` (`run_arbitration`) |
| Capacity Engine | — | 3 Post-exec | Per request | Active | `apps/core/ai_arbitration/capacity_engine.py` |
| Cross-Domain Engine | CDCE | 3 Post-exec | ISE 6h (`run_cdce_correlations`) | Active | `apps/core/ai_cross_domain/cdce_engine.py:69` (`run_cdce`) |
| Executive Arbitration Engine | EAE | 3 Post-exec | Per delivery decision | Active | `apps/core/ai_eae/eae_engine.py:107` (`arbitrate`) |
| Persona Engine | — | Cross-cutting | Per message render | Active | `apps/core/ai_persona/persona_engine.py:22` (`render_with_persona`) |
| Relationship Engine | — | 3 Post-exec | ISE 24h (`detect_relational_drift`) | Active | `apps/core/ai_relationships/relationship_engine.py:202` (`detect_relational_drift`) |
| Blueprint Engine | — | Cross-cutting | Per request | Active | `apps/core/blueprint/engine.py:36` (`get_blueprint`) |
| Architecture Engine | — | 3 Post-exec | ISE 24h (`run_architecture_pass`) | Active | `apps/core/blueprint/architecture_engine.py:47` (`run_architecture_pass`) |
| Priority Engine | — | 2/3 | Per request | Active | `apps/core/blueprint/priority_engine.py` |
| Alignment Engine | — | 3 | Per request | Active | `apps/core/blueprint/alignment_engine.py` |
| Drift Engine | — | 3 Post-exec | ISE 6h (`run_drift_scoring`) | Active | `apps/core/blueprint/drift_engine.py:130` (`compute_daily_drift_score`) |
| Pressure Engine | — | 3 Post-exec | ISE 6h (`compute_weekly_pressure`) | Active | `apps/core/blueprint/pressure_engine.py` |
| Deadline Engine | — | 3 Post-exec | ISE 5m (`compute_deadline_snapshots`) | Active | `apps/core/blueprint/deadline_engine.py` |
| Escalation Engine | — | 3 Post-exec | ISE 24h (`update_escalation_states`) | Active | `apps/core/blueprint/escalation_engine.py` |
| Intervention Engine (blueprint) | — | 3 Post-exec | ISE 24h | Active | `apps/core/blueprint/intervention_engine.py` |
| Protective Engine | — | 3 Post-exec | ISE 24h (`run_protective_sweep`) | Active | `apps/core/blueprint/protective_engine.py` |
| Recovery Engine (blueprint) | — | 3 Post-exec | Per request | Active | `apps/core/blueprint/recovery_engine.py` |
| Reflection Engine | — | 3 Post-exec | ISE 24h (`queue_event_reflections`) | Active | `apps/core/blueprint/reflection_engine.py` |
| Compliance Engine | — | 3 Post-exec | Post-exec + nightly | Active | `apps/dashboard_v2/compliance/service.py` (`compute_compliance`) |
| Signal V3 Engine | — | 3 Post-exec | Post-exec + nightly | Active | `apps/core/signals/signal_engine.py:194` (`detect_signals`) |
| Unified Signal Feed | — | 3 Post-exec | On CoS context build | Active | `apps/core/ai_signals/unified_feed.py` |
| Health Insight Engine (domain) | — | 3 Post-exec | Domain rules | Active | `apps/health/services/insight_engine.py` |
| Health Screenshot Analysis | PIE | 3 Post-exec | Chat image upload | Active | `apps/core/ai_insights/health/sleep_analysis.py` (`analyze_sleep_data`) |

---

## Phase Classification

### Phase 1 — Interpretation (per-request, synchronous)
- **SUE** (Semantic Understanding): `semantic_engine.py`, `ambiguity_engine.py`, `confidence_engine.py` (`apps/core/ai_semantics/`)
- **SLCME** (Self-Learning Context/Memory): `memory_engine.py`, `retrieval_engine.py`, `confidence_engine.py`, plus `learning_engine.py` (writes post-execution) (`apps/core/ai_memory/`)
- **HTIE** (Human Time Interpretation): `apps/core/ai_orchestrator/time_pipeline.py`

### Phase 2 — Execution (per-request, synchronous)
- **UAIO** (Unified AI Orchestrator) cluster: `orchestrator.py`, `intent_engine.py`, `execution_engine.py`, `safety_engine.py`, `action_router.py` (`apps/core/ai_orchestrator/`)
- **ETE** (Execution Truth Engine): `apps/core/execution/execution_truth_engine.py`
- **Today Engine**: `apps/core/today/today_engine.py`

### Phase 3 — Post-Execution (event-driven and/or scheduled)
- Truth/intelligence chain: **SAE → PIE → PRIE → PGE → DNE** (state → insights → predictions → guidance → delivery)
- Learning/reporting: **GLOE, DBE, WIRE, E3**
- Blueprint/governance suite (12 engines under `apps/core/blueprint/`)
- Arbitration: **UAL** (`ai_arbitration`), **EAE** (`ai_eae`)
- Cross-domain: **CDCE** (`ai_cross_domain`), Unified Feed / Signal V3
- Relationship Engine, Maturity Engine, IOCD Observability

### Cross-cutting
- **ISE** (Intelligence Scheduler Engine) — orchestrates the Phase-3 cadence
- **SAME** (System Anomaly Monitoring Engine) — ops health every 60s
- **AAFR** — AI action outcome telemetry on every mutation
- **Persona Engine**, **Blueprint Engine** (`get_blueprint`) — read on any path

---

## Per-Engine Detail

### SUE — Semantic Understanding Engine (Phase 1)
- **Acronym:** Semantic Understanding Engine.
- **Purpose:** Parse user intent, extract entities, detect ambiguity, score interpretation confidence.
- **Inputs:** Raw user text + per-request context dict (`interpret(user, raw_text, context=None)`).
- **Outputs:** `SemanticResult` dataclass (`semantic_engine.py:37`).
- **Storage:** None persistent; stateless per request.
- **Consumers:** `PersonalAssistant.send_message` pipeline step 5 (per `cos_context` pipeline doc); orchestrator.
- **Cadence:** Per request (synchronous).
- **Status:** Active — `interpret()` at `apps/core/ai_semantics/semantic_engine.py:102`; ambiguity/confidence sub-engines present.
- **Files:** `apps/core/ai_semantics/semantic_engine.py:102`, `ambiguity_engine.py`, `confidence_engine.py`.

### SLCME — Self-Learning Context / Memory Engine (Phase 1 + post-exec learning)
- **Purpose:** Resolve user-specific context phrases via learned mappings; retrieve and score learned context; learn new mappings from interactions.
- **Inputs:** Phrase + context-type hint (`resolve_context(user, phrase, context_type_hint=None)`).
- **Outputs:** `MemoryResolution` dataclass (`memory_engine.py:22`).
- **Storage:** Learned-mapping models in `apps/core/ai_memory/`.
- **Consumers:** Pipeline step 3 (Context Resolution); semantic memory retrieval in `_generate_response`.
- **Cadence:** Resolution/retrieval per request; learning post-execution.
- **Status:** Active.
- **Files:** `apps/core/ai_memory/memory_engine.py:63`, `retrieval_engine.py`, `confidence_engine.py`, `learning_engine.py`.

### HTIE — Human Time Interpretation Engine (Phase 1)
- **Purpose:** Resolve human time expressions ("tomorrow at 5pm") to concrete datetimes in user timezone.
- **Inputs:** `resolve_time_pipeline(user_input, user_timezone=None)`.
- **Outputs:** Resolved time-result structure consumed by Action Router / Execution Engine.
- **Storage:** None.
- **Consumers:** Pipeline step 4; `route_action(..., time_result=...)`.
- **Cadence:** Per request.
- **Status:** Active.
- **Files:** `apps/core/ai_orchestrator/time_pipeline.py:15`.

### UAIO — Unified AI Orchestrator (Phase 2)
- **Purpose:** Main pipeline coordinator: route intents to handlers, validate via safety gate, execute domain actions, record telemetry.
- **Inputs:** `process_user_input(user, user_input, page_context=None)`.
- **Outputs:** `OrchestratorResult` (`orchestrator.py:58`); `EnrichedAction` (`action_router.py:21`); `SafetyResult` (`safety_engine.py:42`).
- **Storage:** Writes `AIActionMetric` via AAFR (`_record_aafr`).
- **Consumers:** `PersonalAssistant.send_message` step 7 (`enrich_and_execute`); intent service dispatcher.
- **Cadence:** Per request.
- **Status:** Active.
- **Files:** `orchestrator.py:127`, `intent_engine.py:150`, `execution_engine.py:39`, `safety_engine.py:53`, `action_router.py:60` (all `apps/core/ai_orchestrator/`).
- **Note:** `intent_engine.py` exposes registry/classification helpers (`get_intent_module:150`, `is_time_aware:202`, `is_context_aware:207`); the `*_INTENTS` category sets used by the New-Intent registration gate live here. Actual handler dispatch is in `apps/ai/intent_service.py :: execute_intent`.

### ETE — Execution Truth Engine (Phase 2)
- **Purpose:** Single source of truth for expected-vs-completed across domains (cross-domain bridges, e.g. routine→faith).
- **Inputs:** `get_execution_truth(user, target_date=None)`.
- **Outputs:** Execution-truth dict.
- **Storage:** Reads RoutineLog, Task, IntakeLog, CalendarEvent; no dedicated table.
- **Consumers:** Action Center, CoS locked-facts, check-in renderers, `build_execution_state`.
- **Cadence:** Per request.
- **Status:** Active.
- **Files:** `apps/core/execution/execution_truth_engine.py:81`. Related execution-layer modules: `today_execution.py`, `execution_state.py`, `selectors.py`, `recovery_state.py`, `task_classifier.py`, `recoverability.py`, `active_block.py` (all `apps/core/execution/`).

### Today Engine (Phase 2)
- **Purpose:** Aggregate routines + tasks + calendar + meds into a time-bucketed day dataset; honors skipped RoutineLogs.
- **Inputs:** `build_today(user)`.
- **Outputs:** Time-bucketed day structure (overdue / coming_up / later).
- **Consumers:** Action Center, check-ins, execution truth.
- **Cadence:** Per request.
- **Status:** Active.
- **Files:** `apps/core/today/today_engine.py` (`_collect_routine_items` drops `status=='skipped'`).

### SAE — State Aggregation Engine (Phase 3 — central truth layer)
- **Purpose:** Maintain `UserState.state_data` JSON keyed by module — the canonical per-user truth layer all engines read.
- **Inputs:** Raw module tables via builders in `apps/core/ai_state/state_builder.py` (`build_health_state`, `build_goal_state`, `build_nutrition_state`, etc.).
- **Outputs:** `UserState.state_data[module]`.
- **Storage:** `UserState` model (`core_user_state`); per-request cache `user._sae_cache`.
- **Reads/access:** `get_user_state:19`, `get_module_state:74`, `rebuild_user_state:95`, `get_state_value:142` (`state_engine.py`); approved AI-facing reads via `metric_access.py` + `metric_registry.py`.
- **Consumers:** PIE, PRIE, PGE, CoS context builders, dashboard composers.
- **Cadence:** Per-request reads + ISE 5m batch (`run_sae_synthetic`); plus request-path freshness guard `state_freshness.py :: ensure_fresh` for manual-entry modules (journal, nutrition).
- **Status:** Active.
- **Files:** `apps/core/ai_state/state_engine.py:19`; builders `apps/core/ai_state/state_builder.py`.

### PIE — Proactive Insight Engine (Phase 3)
- **Purpose:** Generate deduplicated `Insight` records from state + events; includes health-screenshot vision analysis path.
- **Inputs:** `run_insights(user, event)`; rule registry `rule_registry.py`.
- **Outputs:** `Insight` model (`core_ai_insight`).
- **Consumers:** PGE, CoS context (`_build_intelligence_signals`), Daily Briefing, notification engine.
- **Cadence:** Event-driven + ISE 5m (`run_pie_synthetic`).
- **Status:** Active.
- **Files:** `apps/core/ai_insights/insight_engine.py:21`; `notification_engine.py`; `health/sleep_analysis.py` (screenshot).

### PRIE — Predictive Risk/Insight Engine (Phase 3)
- **Purpose:** Generate deduplicated `Prediction` records; trajectory regression on historical series.
- **Inputs:** `generate_predictions(user, module=None, record_id=None)`; `trajectory_engine.compute_trajectory`.
- **Outputs:** `Prediction` model (`core_ai_prediction`).
- **Consumers:** PGE, CoS context.
- **Cadence:** Event-driven + ISE 1h (`run_prie_synthetic`); `validate_predictions` daily.
- **Status:** Active.
- **Files:** `apps/core/ai_predictions/prediction_engine.py:128`, `trajectory_engine.py`, `confidence_engine.py`, `prediction_registry.py`.

### PGE — Personalized Guidance Engine (Phase 3)
- **Purpose:** Compose priority-ranked, quality-gated `GuidanceItem`s from SAE + PIE + PRIE.
- **Inputs:** `generate_guidance(user)`.
- **Outputs:** `GuidanceItem` model (`core_ai_guidance_item`).
- **Consumers:** DNE delivery, CoS context.
- **Cadence:** ISE 6h (`refresh_guidance`).
- **Status:** Active.
- **Files:** `apps/core/ai_guidance/guidance_engine.py:24`, `guidance_registry.py`.

### GLOE — Guidance Learning/Optimization Engine (Phase 3)
- **Purpose:** Update per-user guidance learning profile from interaction outcomes.
- **Inputs:** `update_learning_profile(user)`.
- **Outputs:** `GuidanceLearningProfile` model.
- **Consumers:** PGE ranking.
- **Cadence:** ISE 6h (`update_learning_profiles`).
- **Status:** Active.
- **Files:** `apps/core/ai_guidance_learning/learning_engine.py:20`.

### DBE — Daily Briefing Engine (Phase 3)
- **Purpose:** Compose a daily briefing across all engines.
- **Inputs:** `generate_daily_briefing(user)`.
- **Outputs:** `DailyBriefing` model (`core_ai_daily_briefing`).
- **Cadence:** ISE 24h (`generate_daily_briefings`).
- **Status:** Active.
- **Files:** `apps/core/ai_briefing/briefing_engine.py:26`.

### WIRE — Weekly Intelligence Report Engine (Phase 3)
- **Purpose:** Compose weekly report across all engines.
- **Inputs:** `generate_weekly_report(user)`.
- **Outputs:** `WeeklyReport` model (`core_ai_weekly_report`).
- **Cadence:** ISE 7d (`generate_weekly_reports`).
- **Status:** Active.
- **Files:** `apps/core/ai_weekly_report/report_engine.py:23`.

### E3 — Explainability Engine (Phase 3)
- **Purpose:** Attach an `ExplainRecord` to intelligence outputs for transparency/audit.
- **Inputs:** `ensure_explain_record(user, source_engine, obj)`.
- **Outputs:** `ExplainRecord` model (`core_ai_explain_record`).
- **Cadence:** Post-store hook (when an Insight/Prediction/Guidance is stored).
- **Status:** Active.
- **Files:** `apps/core/ai_explain/explain_engine.py:45`.

### DNE — Delivery/Notification Engine (Phase 3)
- **Purpose:** Deliver due notifications across channels (in-app / email / SMS).
- **Inputs:** `deliver_due_notifications()` (queue scan).
- **Outputs:** `DeliveredNotification` model; `AssistantMessage(is_proactive=True)` for PGS messages.
- **Cadence:** ISE 10m (`deliver_intelligence_notifications`).
- **Status:** Active.
- **Files:** `apps/core/ai_delivery/delivery_engine.py:18`.

### ISE — Intelligence Scheduler Engine (cross-cutting)
- **Purpose:** Drive the Phase-3 cadence — runs the registered task set on intervals.
- **Inputs:** `run_scheduler_cycle()`; registry `scheduler_registry.py`.
- **Outputs:** Triggers downstream engines via Celery dispatch; `EngineRun` telemetry per task (`engine_runtime.py`).
- **Cadence:** Celery Beat 5m (`run-ise-cycle-every-300-seconds` → `apps.core.tasks.run_ise_cycle_task`).
- **Status:** Active. 35 registered tasks (`scheduler_registry.py`; intervals 5m–7d).
- **Files:** `apps/core/ai_scheduler/scheduler_engine.py:28`, `scheduler_registry.py`.

### IOCD — Intelligence Observability/Command Dashboard Engine (Phase 3)
- **Purpose:** Generate daily intelligence metrics snapshot.
- **Inputs:** `generate_daily_snapshot(target_date=None)`.
- **Outputs:** `IntelligenceMetricsSnapshot`.
- **Cadence:** ISE 24h (`generate_observability_snapshot`).
- **Status:** Active.
- **Files:** `apps/core/ai_observability/observability_engine.py:27`.

### SAME — System Anomaly Monitoring Engine (cross-cutting ops)
- **Purpose:** Compute engine heartbeats / ops anomalies / narrative ops snapshot for the ops dashboard.
- **Inputs:** `run_same()` — engine heartbeats.
- **Outputs:** `OpsAnomaly`, `OpsNarrativeSnapshot`, cache `wlj:ops:stream_payload`.
- **Cadence:** Celery Beat 60s (`run-same-cycle-every-60-seconds` → `apps.core.tasks.run_same_cycle_task`).
- **Status:** Active.
- **Files:** `apps/core/ai_observability/same_engine.py:32`. Related: `heartbeat.py`, `diagnostic_engine.py`, `engine_registry.py`, `ops_aggregates.py`.

### Maturity Engine (Phase 3)
- **Purpose:** 6-dimension system maturity scoring (Infrastructure/Intelligence/Safety/Domain Coverage/Life Impact/Overall).
- **Inputs:** `compute_all_maturity_scores(user=None)`.
- **Outputs:** `SystemMaturitySnapshot` (`core_systemmaturitysnapshot`).
- **Cadence:** On-demand + ISE `create_maturity_snapshot` (24h).
- **Status:** Active.
- **Files:** `apps/core/ai_observability/maturity_engine.py:30`.

### AAFR — AI Action Feedback/Reliability Telemetry (cross-cutting)
- **Purpose:** Record outcome of every AI mutation for reliability tracking.
- **Inputs:** `_record_aafr(user, intent_type, outcome, error_category, start_time)`.
- **Outputs:** `AIActionMetric` model.
- **Cadence:** Real-time on every `execute_action()`.
- **Status:** Active.
- **Files:** `apps/core/ai_orchestrator/execution_engine.py:22`.

### PGS — Proactive Guidance Scheduler (Phase 3)
- **Purpose:** Time-window proactive check-in dispatch (medicine, workout, journal, overdue, faith, finance, goals, relationships, patterns, birthdays, midday/afternoon/evening wraps).
- **Inputs:** `run_proactive_guidance_scheduler()` — per-user local time windows + feature flags + consent.
- **Outputs:** `AssistantMessage(is_proactive=True)` routed via DNE; deduped 1/type/day + InteractionThrottler 3/hr.
- **Cadence:** ISE 15m (`run_proactive_guidance`).
- **Status:** Active. (Memory note: proactive PUSH delivery to Danny is device-blocked — no MobileDevice registered — but in-app generation works; not a code defect.)
- **Files:** `apps/ai/proactive_checkins.py:3078`; generators in same file; `apps/ai/assistant_intelligence.py`.

### UAL — Unified Arbitration Layer / Arbitration Engine (Phase 3)
- **Purpose:** Arbitrate conflicting intents/signals into a single decision per user.
- **Inputs:** `run_arbitration(user)`.
- **Outputs:** `ArbitrationResult` (`arbitration_engine.py:36`); decision log (`_log_decision`).
- **Cadence:** Per request + ISE 5m (`run_ual_synthetic`).
- **Status:** Active.
- **Files:** `apps/core/ai_arbitration/arbitration_engine.py:64`. Sibling: `capacity_engine.py`, `intervention_engine.py`, `narrative_engine.py`.

### Capacity Engine (Phase 3)
- **Purpose:** Estimate user capacity / load classification.
- **Inputs/Outputs:** classification helper (`_classify_state(score)` at `capacity_engine.py:92`).
- **Status:** Active (helper-level; consumed by arbitration).
- **Files:** `apps/core/ai_arbitration/capacity_engine.py`.

### EAE — Executive Arbitration Engine (Phase 3)
- **Purpose:** Single entry point for delivery arbitration (Phase 8.5) — whether/what to surface to the user.
- **Acronym (verified):** "Executive Arbitration Engine" per module docstring (`eae_engine.py:1`). NOTE: the prompt's hint "EAE→Evidence" and the reference-doc "Evidence" purpose label are inaccurate; code says Executive Arbitration.
- **Inputs:** `arbitrate(...)` (`eae_engine.py:107`); `EAEResult` (`:52`); `EAEState` per user.
- **Outputs:** Arbitration result; loads recent deliveries for suppression.
- **Storage:** `EAEState`; registered in INSTALLED_APPS (`config/settings.py:187` — "Executive Arbitration Engine (CoS Phase 8)").
- **Cadence:** Per delivery decision (request/post-exec).
- **Status:** Active.
- **Files:** `apps/core/ai_eae/eae_engine.py:107`; `pattern_engine.py`.

### CDCE — Cross-Domain Correlation Engine (Phase 3)
- **Purpose:** Detect cross-domain correlations (sleep↔mood, exercise↔mood, fasting↔fitness, etc.) with domain-enablement gating.
- **Inputs:** `run_cdce(user)` (`cdce_engine.py:69`); detectors `detect_sleep_mood:310`, `detect_fasting_fitness:636`, etc.
- **Outputs:** `DomainCorrelation` rows.
- **Consumers:** Unified feed, CoS context, CDCE check-ins (`generate_cdce_check_ins`).
- **Cadence:** ISE 6h (`run_cdce_correlations`, `run_cross_domain_insights`).
- **Status:** Active. Domain gating fixed (BUG 0, 2026-04-07): `_domains_enabled` short-circuits disabled domains; `None` sentinel scores prevent "0% adherence" false correlations.
- **Files:** `apps/core/ai_cross_domain/cdce_engine.py:69`.

### Persona Engine (cross-cutting)
- **Purpose:** Render messages in a selected coaching persona/voice.
- **Inputs:** `render_with_persona(user, base_message, message_type, ...)` (`persona_engine.py:22`).
- **Outputs:** Persona-styled message string.
- **Cadence:** Per message render.
- **Status:** Active.
- **Files:** `apps/core/ai_persona/persona_engine.py:22`, `persona_registry.py`.

### Relationship Engine (Phase 3)
- **Purpose:** Extract people from text, baseline interactions, detect relational drift, suggest re-connection windows.
- **Inputs:** `extract_people_from_text:74`, `compute_interaction_baselines:148`, `detect_relational_drift:202`, `generate_relationship_suggestion:270`.
- **Outputs:** Relationship/drift models + suggestions.
- **Cadence:** ISE 24h (`detect_relational_drift`).
- **Status:** Active.
- **Files:** `apps/core/ai_relationships/relationship_engine.py`.

### Blueprint & Governance Suite (Phase 3 / cross-cutting)
All under `apps/core/blueprint/`:
- **Blueprint Engine** — `engine.py:36` `get_blueprint(user)`; read/update Personal Operating Blueprint. Per request. Active.
- **Architecture Engine** — `architecture_engine.py:47` `run_architecture_pass(user)`; builds tomorrow's plan. ISE 24h (`run_architecture_pass`). Active. Also `handle_curveball:170`, `get_todays_plan:300`.
- **Priority Engine** — `priority_engine.py`; compute task priorities. Per request. Active.
- **Alignment Engine** — `alignment_engine.py`; goal-alignment measurement. Per request. Active.
- **Drift Engine** — `drift_engine.py:130` `compute_daily_drift_score`; also `record_drift_event:70`, `predict_drift_probability:198`. ISE 6h (`run_drift_scoring`). Active.
- **Pressure Engine** — `pressure_engine.py`; weekly pressure forecast. ISE 6h (`compute_weekly_pressure` / `compute_pressure_snapshots`). Active.
- **Deadline Engine** — `deadline_engine.py`; deadline snapshots. ISE 5m (`compute_deadline_snapshots`). Active.
- **Escalation Engine** — `escalation_engine.py`; escalate aged anomalies. ISE 24h (`update_escalation_states`). Active.
- **Intervention Engine** — `intervention_engine.py`; recommend protective actions. ISE 24h. Active. (Note: separate from `ai_arbitration/intervention_engine.py`.)
- **Protective Engine** — `protective_engine.py`; protective sweep. ISE 24h (`run_protective_sweep` + `deliver_protective_alerts` 5m). Active.
- **Recovery Engine** — `recovery_engine.py`; recovery-from-drift path. Per request. Active. (Distinct from execution-layer `recovery_state.py`.)
- **Reflection Engine** — `reflection_engine.py`; queue post-event reflections. ISE 24h (`queue_event_reflections`). Active.

### Compliance Engine (Phase 3)
- **Purpose:** Execution compliance tracking across domains with reconciliation.
- **Outputs:** `ComplianceEvent` model.
- **Cadence:** Post-execution + nightly.
- **Status:** Active.
- **Files:** `apps/dashboard_v2/compliance/service.py` (`compute_compliance`); `reconciliation.py`, `adapters/`.

### Signal V3 Engine + Unified Feed (Phase 3)
- **Signal V3:** `apps/core/signals/signal_engine.py:194` `detect_signals(user, lookback_hours=24)` — behavioral/health/execution signal detection. Active for detection.
- **Unified Feed:** `apps/core/ai_signals/unified_feed.py` — consolidates PIE/PRIE/PGE/CDCE/cross-domain into `UnifiedSignal` with priority scoring + bucket assignment (TOP/CRITICAL/POSITIVE); exposed over `GET /api/signals/`. Active.
- **Signal Renderer:** `apps/core/signals/signal_renderer.py` — canonical Label/Meaning/Action lookup (`SIGNAL_RENDER_MAP`). Active.
- **Status caveat — partially wired persistence:** `apps/core/signals/models.py` defines `SignalFeedback` and `ExecutionSignal`, but `apps/core/signals/` has **no migrations directory** (verified: directory absent) and is not separately listed in INSTALLED_APPS (it is a sub-package of `apps.core`). Per the reference doc's own "OPEN" gap note, DB persistence of those two signal models may not be operational. Detection/rendering logic is active; model persistence is the open item.

### Health Screenshot Analysis (PIE sub-engine)
- **Purpose:** Interpret uploaded health screenshots (Vision API structured JSON → deterministic analysis → CoS injection + Insight).
- **Inputs:** `analyze_sleep_data()` on chat image upload.
- **Status:** Active.
- **Files:** `apps/core/ai_insights/health/sleep_analysis.py`.

---

## Scheduling / Cadence

### Celery Beat (`config/settings.py:1158` `CELERY_BEAT_SCHEDULE`)
Intelligence-relevant entries (selected):

| Beat key | Schedule | Task |
|----------|----------|------|
| `run-same-cycle-every-60-seconds` | 60s | `apps.core.tasks.run_same_cycle_task` (SAME) |
| `run-ise-cycle-every-300-seconds` | 5m | `apps.core.tasks.run_ise_cycle_task` (ISE primary trigger) |
| `cos-keepalive-every-30-seconds` | 30s | `apps.ai.tasks.cos_keepalive_task` (warm CoS context) |
| `core.check_system_health` | 5m | COAS health monitoring |
| `core.compute_nightly_signals` | crontab 04:30 UTC | Signal V3 nightly |
| `core.compute_nightly_patterns` | crontab 04:45 UTC | pattern compute |
| `compute_operating_profiles_task` | crontab 07:00 UTC | Operating profiles |
| `dashboard_v2.compute_nightly_momentum` | crontab 07:30 UTC | momentum |
| `dashboard_v2.detect_celebrations` | crontab 08:00 UTC | celebrations |
| `life.recalculate_task_priorities` | crontab 06:00 UTC | task priorities |
| `health.build_nightly_health_summaries` | crontab 03:00 UTC | health summaries |

On-demand (not beat-scheduled): `run_chat_generation` (`apps.ai.tasks.run_chat_generation`) — dispatched per chat message by `AssistantChatStreamView`, routed to `CHAT_GENERATION_QUEUE` (default `celery`). Background chat generation P0 fix (2026-06-23).

### ISE Registry (`apps/core/ai_scheduler/scheduler_registry.py` — 35 tasks)
Each entry: `task_name → {function_path, interval_seconds, description}`.

| Interval | Tasks |
|----------|-------|
| 5m (300s) | `run_ual_synthetic`, `run_sae_synthetic`, `run_pie_synthetic`, `compute_deadline_snapshots`, `deliver_cos_prompts`, `deliver_protective_alerts` |
| 10m (600s) | `deliver_intelligence_notifications` (DNE) |
| 15m (900s) | `run_assistant_triggers`, `run_proactive_guidance` (PGS) |
| 1h (3600s) | `run_prie_synthetic` |
| 3h (10800s) | `run_cos_event_engine` |
| 6h (21600s) | `update_learning_profiles`, `refresh_guidance`, `run_drift_scoring`, `compute_weekly_pressure`, `compute_pressure_snapshots`, `run_cdce_correlations`, `run_cross_domain_insights`, `schedule_cos_prompts`, `compute_cos_situation`, `generate_cdce_check_ins`, `generate_health_trend_check_ins` |
| 24h (86400s) | `generate_daily_briefings`, `generate_observability_snapshot`, `run_architecture_pass`, `queue_event_reflections`, `detect_relational_drift`, `validate_predictions`, `run_protective_sweep`, `update_escalation_states`, `evaluate_intervention_effectiveness`, `run_tomorrow_protection_pass`, `create_maturity_snapshot` |
| 7d (604800s) | `generate_weekly_reports`, `aggregate_quality_metrics` |

(Reference doc states "43+ tasks"; the registry currently defines **35**. The doc's "43+" appears to predate registry consolidation — minor doc drift, see Gaps.)

### APScheduler (`apps/core/jobs.py`)
Per the reference doc, legacy APScheduler jobs (soft-delete cleanup, faith/health reminders, digests, activity patterns, birthday reminders, `run_intelligence_scheduler` 5m). Several "(was APScheduler)" beat entries indicate ongoing migration of these into Celery Beat.

---

## Gaps & Discrepancies (Docs vs Code)

1. **EAE acronym/purpose mismatch.** The prompt hint and `docs/ENGINE_COS_REFERENCE.md` label EAE "Evidence" / "Aggregate multi-source evidence." Code is explicit: `apps/core/ai_eae/eae_engine.py:1` docstring = "EAE — Executive Arbitration Engine (Phase 8.5)... single entry point for all arbitration"; `config/settings.py:187` registers it as "Executive Arbitration Engine (CoS Phase 8)." **Code wins: EAE = Executive Arbitration Engine.**

2. **ISE task count drift.** Reference doc says "43+ Tasks"; actual registry has **35** (`scheduler_registry.py`). Doc overstates.

3. **Signal model persistence (OPEN, acknowledged in doc).** `apps/core/signals/models.py` defines `SignalFeedback` + `ExecutionSignal`, but the package has **no `migrations/` directory** (verified absent) and is not separately in INSTALLED_APPS. Detection (`signal_engine.py`) and rendering (`signal_renderer.py`, `ai_signals/unified_feed.py`) are active; those two models' DB persistence is unconfirmed.

4. **Two distinct "Intervention" engines.** `apps/core/blueprint/intervention_engine.py` (protective-action recommendations, ISE 24h) and `apps/core/ai_arbitration/intervention_engine.py` (arbitration-side) are different modules. The reference doc lists only the blueprint one. Both exist in code.

5. **Two distinct "Recovery" concepts.** `apps/core/blueprint/recovery_engine.py` (drift-recovery path) vs `apps/core/execution/recovery_state.py` (`compute_recovery_state` day-mode machine). Different layers; only the blueprint one is in the doc's engine table.

6. **`ai_arbitration/narrative_engine.py` undocumented.** Present in code (`narrative_engine.py`) but not in the reference-doc engine inventory.

7. **Non-"engine"-suffixed ai_* packages are support layers, not standalone named engines** (no separate acronym): `ai_feedback` (insight/briefing/intervention trackers + `prediction_validator.py`), `ai_quality` (ICQG quality gate `quality_gate.py`, conflict detector, repeat suppression — feeds `aggregate_quality_metrics`), `ai_governance` (alignment session, recalibration, validator gate, tomorrow protection, language rules), `ai_learning` (`learning_extractor.py`), `ai_events` (event record/resolver/followup/truth_depth). These are wired into the pipeline but are not "engines" in the named/acronym sense.

8. **`intent_engine.py` is a classifier/registry, not the dispatcher.** The reference doc's "Intent Engine — execute_intent()" conflates two files: category/registry logic is in `apps/core/ai_orchestrator/intent_engine.py` (`get_intent_module`, `is_time_aware`); the actual `execute_intent()` dispatcher lives in `apps/ai/intent_service.py`.

9. **All catalogued engines have live entry points** (every `file:line` above was confirmed present). No reference-doc engine was found entirely missing from code. No additional named/acronym engine was found in code that the reference doc omits (the extras in #6/#7 are support modules, not named engines).
