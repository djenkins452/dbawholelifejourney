# WLJ Full System Audit — 2026-03-14

## Scope
Bottom-up architecture review of the entire Whole Life Journey codebase.
Goal: Identify what's solid, what's duplicated, what's harmful, and the correct stabilization order.

---

# PHASE 1 — FULL INVENTORY

## 1.1 Models (~200+ across 22 apps)

| App | Model Count | Key Models | Base Class |
|-----|------------|------------|------------|
| users | 5 | User, UserPreferences, TermsAcceptance, WebAuthnCredential | AbstractBaseUser / models.Model |
| core | 14 | SoftDeleteModel (abstract), SiteConfiguration, ReleaseNote, CameraScan | TimeStampedModel / SoftDeleteModel |
| dashboard | 1 | DailyEncouragement | models.Model |
| journal | 4 | JournalEntry, Emotion, JournalPrompt, EntryLink | UserOwnedModel |
| faith | 14 | PrayerRequest, UserReadingPlan, UserReadingProgress, ReadingPlanTemplate, BibleHighlight/Bookmark/StudyNote | UserOwnedModel |
| health | 30+ | WeightEntry, WorkoutSession, Medicine, MedicineSchedule, MedicineLog, GlucoseEntry, BloodPressure, SleepEntry, FoodEntry, BodyComposition, DailyHealthSummary, HealthProfile | UserOwnedModel |
| purpose | 5+ | LifeGoal, HabitGoal, AnnualDirection, ChangeIntention, GoalMilestone | UserOwnedModel |
| ai | 10+ | CoachingStyle, AssistantConversation, AssistantMessage, AIInsight, ConversationMemory, UserStateSnapshot, DailyPriority, ReflectionPromptQueue | Mixed |
| life | 30+ | Task, Project, LifeEvent, Pet, Recipe, Document, InventoryItem, SignificantEvent, ShoppingList | UserOwnedModel |
| calendar_engine | 5 | CalendarEvent, RecurrenceRule, RecurrenceException, DeclinedSuggestion | models.Model (NOT SoftDeleteModel) |
| cos | 4 | CosReflection, CosPromptSchedule, CosGoalSuggestion, CosAutoShiftLog | TimeStampedModel |
| medical | 8 | LabTestCatalog, LabResult, LabPanel, MedicalDocument, ImportBatch | UserOwnedModel (UUID PKs) |
| billing | 11 | BillingProfile, ReferralReward, CreditTransaction, PaymentAuditLog | TimeStampedModel |
| brain_training | 8 | Game, Challenge, GameSession, DailyStats, UserGameStats, UserOverallStats | TimeStampedModel |
| capture | 2 | CaptureEntry, PendingCapture | TimeStampedModel (UUID PKs) |
| finance | 15+ | FinancialAccount, Transaction, Budget, FinancialGoal, FinancialMetricSnapshot | UserOwnedModel |
| security | 6 | SecurityRun, SecurityScore, SecurityTest, SecurityFinding (encrypted fields) | models.Model |
| sms | 2 | SMSNotification, SMSResponse | TimeStampedModel |
| mobile | 4 | MobileDevice, MobileAPIToken, MobileTokenExchangeCode, HealthIngestionRun | TimeStampedModel |
| help | 7 | HelpTopic, HelpArticle, HelpCategory, TeachingDestination, HelpConversation | models.Model |
| admin_console | 2 | AdminTask, DataLoadConfig | models.Model |
| scan | 3 | ScanLog, ScanConsent, ImageAnalysis | TimeStampedModel |

**Key architectural pattern:** `SoftDeleteModel` → `UserOwnedModel` hierarchy. `SoftDeleteManager` filters `status='active'` by default. CalendarEvent is a notable exception (uses `models.Model`).

## 1.2 Services & Engines (~115 major components)

### AI Engines (14 engine families in apps/core/)

| Engine Family | Directory | Files | Purpose | Status |
|--------------|-----------|-------|---------|--------|
| **PIE: Insight Engine** | ai_insights/ | insight_engine.py, 80+ rules, scheduler.py | Event-driven insight generation | Active |
| **PIE: Prediction Engine** | ai_predictions/ | prediction_engine.py, 20+ rules, confidence_engine.py | Forward-looking predictions | Active |
| **PIE: Guidance Engine** | ai_guidance/ | guidance_engine.py, 40+ rules, ranker, selector | Personalized guidance items | Active |
| **PIE: Briefing Engine** | ai_briefing/ | briefing_engine.py, ranker, selector, formatter | Executive briefing assembly | Active |
| **SAE: State Engine** | ai_state/ | state_builder.py, state_engine.py, state_reader.py, state_updater.py, operating_profile.py, situation_computer.py | Complete user state assembly | Active |
| **Arbitration Engine** | ai_arbitration/ | 11 files: arbitration_engine.py, signal_collector.py, capacity_engine.py, scenario_classifier.py, intervention_engine.py, pattern_analyzer.py, nudge_memory.py, narrative_engine.py, signal_fuser.py, capacity_volatility.py, weight_tuner.py | Intervention decision-making | Active |
| **Blueprint Engines** | blueprint/ | 11 files: architecture_engine.py, priority_engine.py, pressure_engine.py, drift_engine.py, protective_engine.py, escalation_engine.py, reflection_engine.py, recovery_engine.py, assistant_triggers.py, priority_conflict_detector.py, weekly_pressure.py | Life architecture & schedule | Active |
| **Delivery Engine** | ai_delivery/ | delivery_engine.py, delivery_router.py, delivery_policies.py, delivery_logger.py, apns_sender.py | Multi-channel notification dispatch | Active |
| **Quality Gate** | ai_quality/ | quality_gate.py | Conflict detection, repeat suppression | Active |
| **Governance** | ai_governance/ | validator_gate.py, self_governance.py, language_rules.py | Safety gates, learning mode | Active |
| **Feedback Engines** | ai_feedback/ | prediction_validator.py, insight_tracker.py, briefing_tracker.py, intervention_tracker.py | Accuracy & engagement tracking | Active |
| **EAE Engine** | ai_eae/ | eae_engine.py, bundler.py, dedup.py, formatter.py | Escalation evaluation & bundling | Active |
| **Cross-Domain** | ai_cross_domain/ | cdce_engine.py | Cross-domain correlations | Active |
| **Explain Engine** | ai_explain/ | explain_engine.py, evidence_builder.py, templates | Explanation generation | Active |

### AI Orchestration Layer (apps/ai/)

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| **PersonalAssistant** | personal_assistant.py | 7,917 | Core chat: state assessment, prioritization, response generation |
| **IntentService** | intent_service.py | 2,286 | Intent recognition + dispatch via OpenAI function calling (50+ intents) |
| **ActionHandlers** | action_handlers.py | ~2,000 | Execute recognized intents (CRUD mutations) |
| **Executive Briefing** | executive_briefing.py | 1,224 | Morning briefing, gap detection, rolling memory |
| **Proactive Check-ins** | proactive_checkins.py | 2,196 | 14+ proactive message generators |
| **Assistant Intelligence** | assistant_intelligence.py | 822 | Coaching style templates, throttling |
| **Situational Awareness** | situational_awareness.py | 747 | 7-14 day behavioral pattern builder |
| **Dashboard AI** | dashboard_ai.py | 770 | Dashboard-specific AI insights |
| **Memory Service** | memory_service.py | 533 | RAG-based conversation memory |

### CoS Context Builder (apps/core/ai_orchestrator/)

| Component | File | Purpose |
|-----------|------|---------|
| **CoS Context** | cos_context.py | 5,000+ lines — assembles full operational context from 14+ parallel builders |
| **Execution Engine** | execution_engine.py | Post-intent intelligence chain |
| **Intelligence Hook** | intelligence_hook.py | PIE event firing after mutations |
| **Action Router** | action_router.py | Intent-to-handler routing |
| **Entity Resolver** | entity_resolver.py | Ambiguous reference disambiguation |
| **Commitment Contract** | commitment_contract.py | Validates commitment data before writes |
| **Briefing Formatter** | briefing_formatter.py | Output formatting |
| **Intent Engine** | intent_engine.py | Intent categorization |

### Domain Services

| Domain | Key Services |
|--------|-------------|
| Health | command_center_api.py, body_composition_service.py, correlation_service.py, protein_service.py, fitness_utils.py, medicine_utils.py |
| Dashboard v2 | dashboard_service.py, daily_progress_service.py, celebration_service.py, momentum_service.py |
| CoS | prompt_service.py, tone_service.py, reflection_service.py, pattern_service.py, auto_shift_service.py |
| Finance | plaid_service.py, sync_service.py, import_service.py |
| Purpose | analytics_service.py, recommendation_service.py, streak_service.py |
| Life | routine_service.py |
| Calendar | calendar_mutation_service.py |

## 1.3 Signals (116 @receiver decorators)

**Signal hotspots (multiple handlers for same models):**
- `WeightEntry` post_save → triggers in: ai/signals, dashboard/signals, dashboard_v2/signals (3 handlers)
- `Task` post_save → triggers in: ai/signals, dashboard/signals, dashboard_v2/signals, life/signals, sms/signals (5 handlers)
- `Medicine`/`MedicineLog` post_save → triggers in: ai/signals, dashboard/signals, sms/signals (3 handlers)

**Key redundancy:** Dashboard v1 + v2 both listen to same models → double cache invalidation.

## 1.4 Celery Beat Schedule (10 scheduled tasks)

| Time (UTC) | Task | Purpose |
|------------|------|---------|
| Every 30s | cos_keepalive_task | Pre-warm CoS context for active users |
| Every 60s | run_same_cycle_task | SAME engine heartbeat |
| Every 300s | run_ise_cycle_task | ISE scheduler dispatch |
| Every 300s | process_pending_captures | Recover stuck transcriptions |
| 3:00 AM | health_nightly_summary | Build DailyHealthSummary for all users |
| 6:00 AM | recalculate_task_priorities | Refresh Now/Soon/Someday |
| 7:00 AM | compute_operating_profiles | Behavioral pattern computation |
| 7:30 AM | compute_nightly_momentum | Dashboard v2 momentum |
| 8:00 AM | detect_celebrations | Dashboard v2 celebrations |
| 9:00 AM | expire_celebrations | Clean up expired celebrations |

## 1.5 Domain Event System

- **40 event types defined** (EventTypes class)
- **12 active subscribers** (apps/core/events/subscribers.py)
- **~28 event types defined but with no subscribers** — infrastructure ready but underutilized
- Key subscribers: SAE state cache invalidation, PIE event triggering, CoS context invalidation, telemetry

## 1.6 URL/API Layer

- **937 URL patterns** across 26 apps
- **Largest apps by URL count:** health (236), admin_console (132), life (85), faith (58), finance (52)
- **Key API surfaces:** Claude task API, mobile health ingest, assistant chat (streaming + non-streaming), dashboard tiles, blueprint API

## 1.7 Context Processors (11 total)

- Run on every HTML request (skipped for /api/, /static/, /media/)
- **Performance concern:** `theme_context` computes alignment score and calibration state inline on every request

---

# PHASE 2 — DOMAIN TRUTH MAP

## Where Does Truth Live?

| Domain | Current Truth Source(s) | Duplicate Sources | Conflicting Interpretations | Target Canonical Source |
|--------|----------------------|-------------------|---------------------------|----------------------|
| **Tasks** | `Task` model + `_refresh_stale_task_priorities()` | PersonalAssistant._get_task_state(), cos_context builders, executive_briefing._build_day_overview_section(), proactive_checkins, situational_awareness | Task counts diverge: _get_task_state `due_today` = priority='now' count (includes overdue); `remaining_tasks` double-counts overdue | `Task` model with `_refresh_stale_task_priorities()` pre-call. Single `TaskMetricsService` for all consumers. |
| **Task Priorities** | `Task.priority` field (stored) | `calculate_priority()` at save, `_refresh_stale_task_priorities()` bulk update, nightly Celery recalc | Stale priority if not refreshed (overnight drift) | `_refresh_stale_task_priorities(user)` must precede any priority-based query. Already standardized. |
| **Health State** | Raw models (WeightEntry, WorkoutSession, etc.) + DailyHealthSummary (pre-computed) | PersonalAssistant._get_health_state(), cos_context._build_health_and_vitals(), executive_briefing._build_health_gate_section(), proactive_checkins, situational_awareness | Different time windows (today vs 7d vs 14d), different field subsets, different cache TTLs | Health Command Center service for dashboard; SAE state_builder for AI. Both should read same underlying models. |
| **Medicine** | Medicine, MedicineSchedule, MedicineLog models | PersonalAssistant check-in med details (lines 4694-4748), executive_briefing health gate, proactive_checkins medicine generators, dashboard_ai, cos_context | Personal assistant computes per-schedule granularity; other paths use coarser adherence % | Medicine models are canonical. PersonalAssistant's per-schedule approach is correct. |
| **Fitness/Workout** | WorkoutSession model | PersonalAssistant._get_health_state(), executive_briefing health gate ("Workout: logged/not yet logged"), situational_awareness consistency, dashboard health snapshot | PA and EB both check `workout_today` independently | WorkoutSession model. Single `workout_logged_today(user)` utility. |
| **Journal** | JournalEntry model | PersonalAssistant._get_journal_state(), cos_context._build_people_and_mood(), executive_briefing._build_pattern_section(), situational_awareness._build_emotional_context(), memory_service | Different mood scoring, different time windows (7d vs 14d), different keyword sets | JournalEntry model. Mood analysis should use single `JournalAnalysisService`. |
| **Goals** | LifeGoal, HabitGoal models | PersonalAssistant._get_priority_context(), cos_context._build_loops_and_events(), proactive_checkins goal alerts, dashboard_ai | Different query patterns (active goals count vs goal details) | Purpose models. No critical divergence — queries are appropriately scoped. |
| **Calendar** | CalendarEvent model (NOT SoftDeleteModel) | PersonalAssistant check-in calendar details, cos_context._build_calendar_events(), executive_briefing._build_day_overview_section() | CalendarEvent uses `models.Model` — `.exclude(deleted_at__isnull=False)` IS legitimate here | CalendarEvent model. Current handling is correct. |
| **Faith** | PrayerRequest, UserReadingPlan, UserReadingProgress | PersonalAssistant._get_faith_state(), cos_context._build_faith_context(), executive_briefing health gate (reading status), proactive_checkins faith generators | Reading plan completion checked in multiple places with slightly different logic | Faith models. Consistent enough — no critical divergence. |
| **Finance** | FinancialAccount, Transaction, Budget models | cos_context._build_finance_context(), proactive_checkins finance generators | Limited — finance is newer and less duplicated | Finance models. Well-isolated. |
| **User State (aggregate)** | UserStateSnapshot (cached), UserState (SAE), CoSSituationState | PersonalAssistant.assess_current_state() → UserStateSnapshot (2h cache), SAE state_builder → UserState, cos_context → live parallel builders | **CRITICAL:** Three separate state aggregation paths with different cache strategies and TTLs | SAE state_builder should be canonical. PersonalAssistant should read from SAE, not maintain its own snapshot. |
| **Coaching Context** | CoachingStyle model, PersonalOperatingBlueprint, GovernanceProfile | cos_context, personal_assistant._build_system_prompt(), assistant_intelligence COACHING_STYLE_TEMPLATES | Coaching style applied in 3 places: system prompt, proactive check-in templates, dashboard AI tone | CoachingStyle model. Already well-centralized. |

---

# PHASE 3 — EXECUTION PATH AUDIT

## 3.1 Organize Page Task Display

```
Browser → GET /life/tasks/ → TaskListView.get_queryset()
  → _refresh_stale_task_priorities(user)
  → Task.objects.filter(user=user) [SoftDeleteManager: status='active']
  → .filter(completion_status='pending')  [or completed/skipped per ?show=]
  → .filter(priority=priority) [if ?priority= provided]
  → .annotate(priority_order=Case(...))
  → .order_by('completion_status', 'priority_order', 'due_date', 'scheduled_time', '-created_at')
  → Template: {% regroup tasks by priority %} → {{ priority_group.list|length }}
```
**Truth source:** Task model directly. Canonical. ✅

## 3.2 Dashboard Task Widgets

```
Browser → GET /dashboard/ → DashboardView.get_context_data()
  → Thread pool parallel collection
  → Task.objects.filter(user=user, completion_status='pending')
  → Dashboard tiles render counts
```
**Also:**
```
Dashboard v2 → dashboard_v2/services/ → daily_progress_service.py
  → Reads pre-computed momentum snapshots + task completion data
```
**Truth source:** Task model directly for v1. Pre-computed for v2. ⚠️ Two paths.

## 3.3 Beth Task Answer ("how many tasks do I have today")

```
User message → personal_assistant.send_message()
  → _generate_response()
    → is_asking_about_tasks matches "how many tasks" → is_requesting_checkin = True
    → assess_current_state() → _get_task_state() → remaining_tasks (NOT used in prompt)
    → Check-in assembly block (line 4506):
      → _refresh_stale_task_priorities(user)
      → pending_base = LifeTask.objects.filter(user=self.user, completion_status='pending')
      → now_count = pending_base.filter(priority='now').count()
      → task_details built with ALL task titles (fixed this session)
      → System prompt includes TASKS section with "NOW (10)" and all titles
    → OpenAI API call with system prompt
    → LLM generates response
```
**Truth source:** Task model with canonical query (matching Organize page). ✅ (fixed this session)

## 3.4 Check-in Flow

Same as 3.3 but with additional sections:
- Calendar details (CalendarEvent query)
- Medication details (Medicine + MedicineLog per-schedule query)
- Health gate (from executive_briefing._build_health_gate_section())
- Goals, prayers, priority synthesis, situational awareness

**Truth source:** Mixed — some sections query models directly, some use executive_briefing section builders. ⚠️

## 3.5 Executive Briefing

```
_generate_response() → build_executive_briefing(user, conversation)
  → First-of-day gate OR 4-hour gap gate
  → _ensure_routine_tasks_for_today(user, today)  [only on first-of-day]
  → Auto-complete "Wake Up" task
  → Section builders:
    → _build_greeting_section() — time-aware greeting
    → _build_health_gate_section() — meds/fasting/workout
    → _build_day_overview_section() — calendar + tasks (canonical query)
    → _build_pattern_section() — journal mood trends
    → _build_life_events_section() — approaching birthdays
    → _build_journal_followup_section() — yesterday's themes
```
**Truth source:** Each section queries models directly. Task section uses canonical query. ✅

## 3.6 Medicine Reminders

```
Proactive check-ins: generate_medicine_check_in_for_user()
  → Medicine.objects.filter(user=user, medicine_status='active')
  → MedicineSchedule.applies_to_day(today)
  → MedicineLog check for each schedule
  → Format "take [med name] ([time])" message

Personal assistant check-in:
  → Same pattern but more granular per-schedule detail (lines 4694-4748)
  → Separates: overdue (past time, not taken), upcoming (future time), taken

Executive briefing health gate:
  → Coarser "meds due/taken" status
```
**Truth source:** Medicine/MedicineSchedule/MedicineLog models. Multiple query patterns but all correct. ✅ (PA has the most accurate per-schedule logic)

## 3.7 Workout Status

```
Personal assistant:
  → health.get('workout_today', False) from assess_current_state()
  → _get_health_state() checks WorkoutSession.objects.filter(user=user, date=today)
  → Injected as "Workout: logged today" or "not yet logged" with AUTHORITATIVE warning

Executive briefing health gate:
  → Same WorkoutSession query

Context processor (theme_context):
  → Also queries workout status for dashboard state
```
**Truth source:** WorkoutSession model. Consistent. ✅

## 3.8 Goal Summaries

```
Personal assistant:
  → assess_current_state() → _get_purpose_state() → active goals count + list

CoS context:
  → _build_purpose_context() → goals, habits, intentions with detail

Dashboard:
  → Direct Goal model queries for goal tiles
```
**Truth source:** LifeGoal/HabitGoal models. Multiple query patterns but no conflict. ✅

## 3.9 Proactive Nudges

```
Celery Beat → run_proactive_guidance_scheduler()
  → Batch loads dedup cache (all today's proactive messages)
  → Dispatches to 14+ generators:
    → Medicine, task, non-negotiable, busy day, pattern, faith, finance, relationship, goal,
      journal intelligence, CDCE correlation, midday alignment, afternoon momentum, evening wrap
  → Each generator queries relevant domain models DIRECTLY
  → Stores as proactive AssistantMessage
```
**Truth source:** Each generator queries models directly. Some overlap with PA and EB queries. ⚠️

---

# PHASE 4 — TARGET ARCHITECTURE

## Layer Model

```
Layer 6: LLM NARRATION
├── OpenAI API calls (chat completion, function calling, embeddings)
├── System prompt assembly (coaching style, CoS context, anti-fabrication rules)
└── Response quality gates (streaming parity, fallback detection)

Layer 5: PRESENTATION CONSUMERS
├── Personal assistant check-in prompt builder
├── Executive briefing section builders
├── Dashboard view data gathering
├── Proactive check-in generators
├── Dashboard AI insight generators
└── Mobile API responses

Layer 4: INTERPRETATION / SCORING ENGINES
├── PIE Pipeline (Insight → Prediction → Guidance → Briefing engines)
├── Arbitration Engine (signal collection → capacity → scenario → intervention)
├── Blueprint Engines (architecture → pressure → drift → escalation)
├── Quality/Governance gates
└── Feedback/learning engines

Layer 3: AGGREGATED STATE (SAE / UserState)
├── SAE state_builder.py (modular domain builders)
├── state_engine.py (assembly orchestrator)
├── CoSSituationState (situation snapshot)
├── UserOperatingProfile (behavioral baseline)
└── UserStateSnapshot (SHOULD BE RETIRED — see below)

Layer 2: CANONICAL DOMAIN SERVICES
├── Health: command_center_api.py, medicine_utils.py, fitness_utils.py
├── Purpose: streak_service.py, analytics_service.py
├── Life: routine_service.py, _refresh_stale_task_priorities()
├── Calendar: calendar_mutation_service.py
├── Finance: plaid_service.py, sync_service.py
├── Faith: (no service layer yet — direct model queries)
├── Journal: (no service layer yet — direct model queries)
└── CoS: prompt_service.py, tone_service.py

Layer 1: CORE DOMAIN MODELS
├── SoftDeleteModel → UserOwnedModel hierarchy
├── All app models (Task, Medicine, JournalEntry, etc.)
├── SoftDeleteManager (filters status='active')
└── Domain events (fire on mutations)
```

## Component Placement Assessment

| Component | Current Layer | Correct Layer | Status |
|-----------|-------------|---------------|--------|
| Task model + calculate_priority() | 1 | 1 | ✅ Correctly placed |
| _refresh_stale_task_priorities() | 2 | 2 | ✅ Correctly placed |
| SAE state_builder | 3 | 3 | ✅ Correctly placed |
| CoSSituationState | 3 | 3 | ✅ Correctly placed |
| **UserStateSnapshot** | **3** | **RETIRE** | ❌ **Duplicate of SAE. PA.assess_current_state() should use SAE.** |
| PIE engines | 4 | 4 | ✅ Correctly placed |
| Arbitration engine | 4 | 4 | ✅ Correctly placed |
| Blueprint engines | 4 | 4 | ✅ Correctly placed |
| **PA._get_task_state()** | **5** | **2 or 3** | ⚠️ Should use Layer 2 service, not query models directly |
| **PA._get_health_state()** | **5** | **2 or 3** | ⚠️ Same — should use service |
| **PA._get_journal_state()** | **5** | **2 or 3** | ⚠️ Same |
| **PA._get_faith_state()** | **5** | **2 or 3** | ⚠️ Same |
| Executive briefing section builders | 5 | 5 | ✅ Correctly placed (but should use Layer 2/3 data) |
| Proactive check-in generators | 5 | 5 | ✅ Correctly placed (but query models directly) |
| Dashboard view | 5 | 5 | ✅ Correctly placed |
| cos_context.py (5,000+ lines) | 5 | 3-5 | ⚠️ **Massive file mixing Layer 3 assembly with Layer 5 formatting** |
| personal_assistant.py (7,917 lines) | 5-6 | 5-6 | ⚠️ **Too large — mixes prompt building (L5) with state queries (L2-3)** |

---

# PHASE 5 — REBUILD / CONSOLIDATION ORDER

## Priority Order (Safe, Incremental)

### P0 — Immediate Stabilization (Already Done This Session)
1. ✅ Task query alignment — all Beth-facing queries now use canonical pattern
2. ✅ Prompt starvation fix — LLM now receives all task titles and accurate counts
3. ✅ Harmful filter removal — `.exclude(deleted_at__isnull=False)` removed from 4 locations

### P1 — remaining_tasks Double-Count Bug
**File:** `apps/ai/personal_assistant.py:4493`
```python
remaining_tasks = tasks.get('due_today', 0) + tasks.get('overdue', 0)
```
`due_today` = `priority='now'` count (INCLUDES overdue). Adding `overdue` double-counts.
**Impact:** Only affects non-check-in paths (analysis, general task queries).
**Fix:** `remaining_tasks = tasks.get('due_today', 0)` — overdue is already included.

### P2 — Consolidate Dashboard Signal Handlers
**Problem:** Dashboard v1 + v2 both listen to same models (WeightEntry, Task, JournalEntry, etc.). Both fire cache invalidation. SAE refresh also fires from ai/signals.py AND dashboard/signals.py.
**Fix:** Create single `invalidation_dispatcher.py` that all signal handlers route through. Deduplicate SAE refresh calls.
**Files:** `apps/dashboard/signals.py`, `apps/dashboard_v2/signals.py`, `apps/ai/signals.py`

### P3 — UserStateSnapshot → SAE Migration
**Problem:** `PersonalAssistant.assess_current_state()` maintains its own `UserStateSnapshot` model with a 2-hour cache. SAE (`apps/core/ai_state/`) maintains a separate `UserState`. Two parallel state systems.
**Fix:** Migrate PA to read from SAE state. Retire UserStateSnapshot model (or repurpose as SAE read cache).
**Complexity:** Medium — need to map all PA state fields to SAE equivalents.
**Files:** `apps/ai/personal_assistant.py` (assess_current_state, _get_task_state, _get_health_state, _get_journal_state, _get_faith_state, _get_purpose_state, _gather_comprehensive_state)

### P4 — Beth Prompt Builder Simplification
**Problem:** `personal_assistant.py` is 7,917 lines. `_generate_response()` alone is ~2,500 lines with interleaved state queries, prompt building, and flow control.
**Fix:** Extract prompt builders into focused modules:
- `checkin_prompt_builder.py` — check-in/status system prompt assembly
- `analysis_prompt_builder.py` — analysis/habit system prompt
- `task_prompt_builder.py` — task-specific context
Keep `_generate_response()` as thin orchestrator.
**Complexity:** High — needs careful extraction to preserve all conditional logic.

### P5 — Domain Service Layer for Faith & Journal
**Problem:** Faith and journal have no service layer. Every consumer (PA, EB, cos_context, proactive_checkins) queries models directly with slightly different patterns.
**Fix:** Create `FaithMetricsService` and `JournalMetricsService` with standard queries.
**Files:** New `apps/faith/services/`, `apps/journal/services/`

### P6 — Proactive Check-in → Service Alignment
**Problem:** 14+ proactive generators each query domain models directly. Some overlap with PA and EB queries.
**Fix:** Have generators call domain services (from P3/P5) instead of querying models directly.
**Files:** `apps/ai/proactive_checkins.py`

### P7 — cos_context.py Decomposition
**Problem:** 5,000+ line file with 14+ parallel builders. Mixes state assembly (Layer 3) with prompt formatting (Layer 5).
**Fix:** Split into `cos_state_assembly.py` (data gathering) and `cos_prompt_formatter.py` (string formatting). State assembly should call domain services.
**Complexity:** High — touching core AI pipeline.

### P8 — Observability & Debug Instrumentation
**Problem:** Many silent failures in check-in data assembly. Crashes caught by bare `except Exception: pass`.
**Fix:** Add structured logging with context (user_id, function, data_shape) to all state query functions. Replace `pass` with `logger.warning(exc_info=True)`.

### P9 — Domain Event Adoption
**Problem:** 28 event types defined but unused. Django signals do heavy lifting with 116 handlers.
**Fix:** Gradually migrate signal handlers to domain event subscribers where it reduces coupling. Not urgent — signals work, events are cleaner but equivalent.

### P10 — Context Processor Optimization
**Problem:** `theme_context` computes alignment score and calibration state on every HTML request.
**Fix:** Cache alignment/calibration in UserPreferences or session. Recompute on explicit triggers only.

---

# PHASE 6 — OUTPUT ARTIFACTS

## Artifact 1: WLJ System Inventory
See Phase 1 above. 200+ models, 115+ services/engines, 937 URL patterns, 116 signal handlers, 10 Celery Beat tasks, 40 domain event types.

## Artifact 2: Domain Truth Map
See Phase 2 table. Key finding: **3 parallel state systems** (UserStateSnapshot, SAE UserState, CoSSituationState) with different cache strategies.

## Artifact 3: Execution Path Audit
See Phase 3. All 9 flows traced. Task truth now standardized ✅. Medicine truth is correct but spread across 3 query locations. User state truth has the most divergence.

## Artifact 4: Target Architecture (Text Form)
```
┌─────────────────────────────────────────────────┐
│  Layer 6: LLM NARRATION                         │
│  OpenAI API ← System Prompt + History + Context  │
├─────────────────────────────────────────────────┤
│  Layer 5: PRESENTATION CONSUMERS                 │
│  ┌──────────┐ ┌─────────┐ ┌───────────────┐    │
│  │ PA Prompt │ │ EB Sect │ │ Proactive Gen │    │
│  │ Builders  │ │ Builders│ │ (14 gens)     │    │
│  └────┬─────┘ └────┬────┘ └───────┬───────┘    │
│       │             │              │             │
├───────┼─────────────┼──────────────┼─────────────┤
│  Layer 4: INTERPRETATION / SCORING               │
│  ┌─────────────────────────────────────────┐    │
│  │ PIE (Insight→Predict→Guide→Brief)       │    │
│  │ Arbitration (Signal→Capacity→Intervene)  │    │
│  │ Blueprint (Arch→Pressure→Drift→Protect)  │    │
│  │ Quality + Governance Gates               │    │
│  └────────────────────┬────────────────────┘    │
├───────────────────────┼──────────────────────────┤
│  Layer 3: AGGREGATED STATE                       │
│  ┌────────────────────┴────────────────────┐    │
│  │ SAE State Engine (canonical aggregate)   │    │
│  │   └── state_builder.py (domain builders) │    │
│  │ CoSSituationState (dynamic snapshot)     │    │
│  │ UserOperatingProfile (behavioral)        │    │
│  └────────────────────┬────────────────────┘    │
├───────────────────────┼──────────────────────────┤
│  Layer 2: CANONICAL DOMAIN SERVICES              │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐   │
│  │ Health  │ │ Task   │ │ Faith  │ │ Journal│   │
│  │ Service │ │ Service│ │ Service│ │ Service│   │
│  └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘   │
├──────┼──────────┼──────────┼──────────┼──────────┤
│  Layer 1: CORE DOMAIN MODELS                     │
│  ┌─────────────────────────────────────────┐    │
│  │ SoftDeleteModel → UserOwnedModel        │    │
│  │ Task, Medicine, JournalEntry, Goal, etc. │    │
│  │ SoftDeleteManager (status='active')      │    │
│  │ Domain Events (fire on mutation)         │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

## Artifact 5: Redundant / Harmful Systems List

| System | Type | Location | Issue |
|--------|------|----------|-------|
| `remaining_tasks` double-count | Bug | personal_assistant.py:4493 | `due_today` + `overdue` double-counts overdue tasks |
| Dashboard v1 + v2 dual signals | Redundant | dashboard/signals.py + dashboard_v2/signals.py | Same models trigger cache invalidation twice |
| SAE refresh in 3+ places | Redundant | ai/signals.py, dashboard/signals.py, purpose/signals.py | Same SAE module refreshed multiple times per event |
| UserStateSnapshot vs SAE UserState | Duplicate | personal_assistant.py + core/ai_state/ | Two parallel state aggregation systems |
| theme_context computing alignment per-request | Performance | core/context_processors.py | Expensive computation on every HTML request |
| 28 unused domain event types | Dead infrastructure | core/events/domain_events.py | Defined but no subscribers — harmless but misleading |
| cos_context.py 5000+ lines | Complexity | core/ai_orchestrator/cos_context.py | Mixing Layer 3 + Layer 5 concerns in one file |
| personal_assistant.py 7917 lines | Complexity | ai/personal_assistant.py | Too many responsibilities in one file |

## Artifact 6: Recommended Consolidation Order
See Phase 5 (P0-P10).

## Artifact 7: Immediate Stabilization Priorities
1. **P1** — Fix `remaining_tasks` double-count (5 minutes, low risk)
2. **P2** — Consolidate signal handlers (1-2 hours, medium risk)
3. **P8** — Add structured logging to state query functions (1 hour, low risk)

## Artifact 8: Deferred / Optional Improvements
- **P7** cos_context.py decomposition — works today, complexity is managed
- **P9** Domain event adoption — signals work fine, events are cleaner but equivalent
- **P10** Context processor optimization — performance, not correctness
- **P4** Personal assistant file splitting — quality of life, not bugs

---

# FINAL ANSWERS

## 1. What parts of WLJ are already solid?

1. **Core model hierarchy** — SoftDeleteModel → UserOwnedModel → SoftDeleteManager is well-designed and consistently applied. The CalendarEvent exception (models.Model) is correctly handled.

2. **Task truth** — After this session's fixes, all Beth-facing task queries use the canonical Organize page pattern. Priority refresh is standardized. Task counts are accurate.

3. **Medicine per-schedule granularity** — The personal assistant's med detail builder (lines 4694-4748) correctly handles per-schedule dose tracking, avoiding the dangerous "take your meds" when one dose is taken but another isn't.

4. **PIE Intelligence Pipeline** — The 3-phase pipeline (Insight → Prediction → Guidance) with 140+ rules is well-architected. Event-driven, deterministic, with proper feedback loops.

5. **Arbitration Engine** — 11-file subsystem with clean separation: signal → capacity → scenario → intervention → narrative. Well-engineered.

6. **Blueprint Engines** — Architecture, pressure, drift, escalation, reflection, recovery engines are cleanly separated with clear contracts.

7. **Intent System** — 50+ intents with OpenAI function calling, action handlers, and registration gate tests. The 7-point registration checklist prevents silent failures.

8. **Mobile API** — Clean token exchange flow, HealthKit ingestion with proper rate limiting, CSRF exemption for token-based auth.

9. **Domain event infrastructure** — Thread-safe, idempotent, loop-protected. Ready for wider adoption.

10. **Anti-fabrication rules** — The check-in prompt's anti-fabrication section (lines 5007-5016) is thorough and prevents the LLM from hallucinating completions.

## 2. What parts are duplicated or conflicting?

1. **State aggregation** — UserStateSnapshot (PA) vs UserState (SAE) vs CoSSituationState vs live cos_context builders. Four parallel views of user state.

2. **Signal handlers** — Dashboard v1 + v2 double-invalidation. SAE refresh triggered from 3 separate signal files.

3. **Health context building** — PA._get_health_state(), cos_context._build_health_and_vitals(), EB._build_health_gate_section(), proactive_checkins, situational_awareness all query health models independently.

4. **Journal mood analysis** — 5 separate paths analyze journal mood with different scoring, windows, and keyword sets.

5. **Task count computation** — `remaining_tasks` at line 4493 double-counts overdue tasks. Used only in non-check-in paths but still wrong.

## 3. What are the 5 most harmful architectural problems right now?

1. **`remaining_tasks` double-count** (P1) — `due_today` (priority='now', which includes overdue) + `overdue` = double-counted. Affects analysis and general task query responses. Active bug.

2. **Dual state systems** (P3) — PersonalAssistant maintaining its own UserStateSnapshot parallel to SAE. Creates drift between what Beth "knows" and what engines compute. Each has different cache TTL and invalidation triggers.

3. **personal_assistant.py at 7,917 lines** (P4) — `_generate_response()` alone is ~2,500 lines mixing state queries, prompt building, intent detection, and flow control. Makes every change risky. Every session touches this file.

4. **Dashboard signal double-invalidation** (P2) — Every data mutation triggers cache invalidation in dashboard v1 signals AND dashboard v2 signals AND ai signals. Wastes CPU and increases risk of cache stampede.

5. **theme_context computing alignment per-request** (P10) — Calls `compute_alignment_score()` and `get_calibration_state()` on every HTML page load. These involve model queries and computation that should be cached.

## 4. In what exact order should WLJ be stabilized?

1. **P1** — Fix `remaining_tasks` double-count (5 min, immediate)
2. **P8** — Add structured logging to state queries (1 hr, observability)
3. **P2** — Consolidate signal handlers (2 hrs, reduce redundant work)
4. **P3** — Migrate PA from UserStateSnapshot to SAE (4-8 hrs, eliminate dual state)
5. **P5** — Create Faith & Journal service layers (2-4 hrs, foundation for P6)
6. **P6** — Align proactive check-ins to use services (2-4 hrs)
7. **P4** — Extract PA prompt builders into modules (4-8 hrs, quality of life)
8. **P10** — Cache theme_context computations (1 hr, performance)
9. **P7** — cos_context.py decomposition (4-8 hrs, optional)
10. **P9** — Domain event adoption (ongoing, optional)

## 5. What should NOT be touched yet?

1. **PIE engines** (insight/prediction/guidance/briefing) — Working correctly. 140+ rules. High risk, low reward.

2. **Arbitration engine** — 11-file subsystem. Complex but well-architected. No bugs reported.

3. **Blueprint engines** — Architecture, pressure, drift, escalation. Working. No complaints.

4. **Intent system** — 50+ intents with registration tests. Stable. Only touch when adding new intents.

5. **Mobile API** — Clean, focused, working. iOS app depends on exact API contracts.

6. **Calendar engine** — Working correctly. CalendarEvent NOT being SoftDeleteModel is intentional and handled.

7. **Medical module** — Newer, well-isolated, UUID-based. No cross-contamination.

8. **Security module** — Encrypted fields, isolated. Don't touch without explicit need.

9. **Billing/Stripe integration** — Revenue-critical. Test extensively before any changes.

10. **cos_context.py** — Yes, it's 5,000+ lines. But it works. Decomposition is P7 (deferred) because the risk of breaking the AI pipeline outweighs the code organization benefit.

---

*Audit completed: 2026-03-14*
*Auditor: Claude Code (Architecture Reset)*
