# WLJ Domain & Data Catalog — Part B (Purpose, Life/Tasks, Calendar Engine, Relationships, Finance)

> Grounded, objective documentation. Every structural claim carries a `file:line` anchor. Read-only extraction — no code was modified. Generated 2026-06-23 against `main`.

---

## Cross-Cutting Framing (verified)

- **Truth Contracts** — Each domain exposes canonical, deterministic queryset classmethods in `apps/{domain}/services/{domain}_queries.py`; all truth-evaluating consumers (Execution Truth, SAE builders, CoS context, UI status) must use them (`docs/DOMAIN_TRUTH_CONTRACTS.md:1-60`). Inventory in that doc lists: Tasks `apps/life/services/task_queries.py`, Goals `apps/purpose/services/goal_queries.py`, Habits `apps/life/services/habit_queries.py`, Routines `apps/life/services/routine_helpers.py`.
- **Signal Ontology** — Domains emit producer-native signals; `apps/core/ai_signals/unified_feed.py` consolidates them into the `UnifiedSignal` shape (`domain, type, severity, priority_tier, confidence, dedupe_key, source, evidence, explain_why, recency`). Required fields missing → signal dropped (`@WLJ_SYSTEM_PROMPTS/03_CANON_REFERENCE/WLJ SIGNAL ONTOLOGY.md:1-40`). Producers: **PIE** (single-domain factual rules), **PRIE** (regression/trajectory), **PGE** (proactive guidance).
- **SAE module registry** — `MODULE_BUILDERS` dict in `apps/core/ai_state/state_builder.py:5576-5607` maps module key → builder fn. Relevant aliases/entries: `goals`/`purpose` → `build_goal_state`, `habits` → `build_habit_state`, `tasks` → `build_task_state`, `calendar` → `build_calendar_state`, `routine` → `build_routine_state`, `finance` → `build_finance_state`, `relationships` → `build_relationships_state`. `execution` registered separately at `:5621` wrapping `build_today_execution`.
- **PIE insight rules** registered via `@register` decorator in `apps/core/ai_insights/rule_registry.py:13`, filtered per-module by `get_rules_for_module(module)` (`:24`). PRIE prediction rules via `@register_prediction` in `apps/core/ai_predictions/prediction_registry.py:11`.

---

# 1. PURPOSE (Goals / Habits / Direction)

## Purpose
The Purpose domain owns the user's long-horizon intentions: annual direction (word/theme of the year), life goals with milestones, habit goals with daily tracking, change intentions, and structured reflections. It is the canonical source for "what the user is trying to become" and feeds goal/habit signals into the intelligence pipeline and projections into the calendar.

## Primary Models (`apps/purpose/models.py`)
- **LifeDomain** (`:35`) — shared taxonomy: `name`/`slug` (`:42-43`), `icon` (`:46`), `color` hex (`:50`), `sort_order` (`:55`), `is_active` (`:56`). Re-used app-wide (calendar FK's directly to it). Defaults: Faith, Health, Family, Work, Finances, Learning, Personal Growth.
- **ReflectionPrompt** (`:70`) — prompt bank: `prompt_type` (`:84`), `question` (`:89`).
- **AnnualDirection** (`:115`, UserOwnedModel) — `year` (`:122`), `word_of_year` (`:127`), `theme` (`:137`), `anchor_text` (`:148`), `is_current` (`:159`).
- **LifeGoal** (`:190`, UserOwnedModel) — `title` (`:212`), `why_it_matters` (`:219`), `success_looks_like` (`:225`), `domain` FK→LifeDomain nullable (`:231`), `timeframe` year_1/2/3/ongoing (`:241`), `target_date` (`:246`), `status` active/paused/completed/released (`:253`), `commitment_level` (`:266`), `is_foundational` (`:272`), `is_primary_mission` (`:277`), `annual_direction` FK (`:315`). Has `deadline_urgency` / `is_overdue` properties.
- **GoalMilestone** (`:523`) — child of LifeGoal: `title` (`:556`), `target_date` (`:566`), `completed` (`:573`), `objective_metric`/`objective_target_value`/`objective_operator` (`:580-598`) for measurable milestones.
- **GoalMotivationLink** (`:657`), **GoalVictoryMilestone** (`:703`) — motivation URLs and victory markers under a goal.
- **ChangeIntention** (`:766`, UserOwnedModel) — `intention` (`:785`), `motivation` (`:795`), `status` (`:801`).
- **Reflection** (`:836`, UserOwnedModel) + **ReflectionResponse** (`:904`) — periodic reflections with `reflection_type` (`:850`), `ai_summary` (`:879`).
- **PlanningAction** (`:955`, UserOwnedModel) — direction-derived actions.
- **HabitGoal** (`:1021`, UserOwnedModel) — `name` (`:1044`), `measurement_type` binary/duration/count/target (`:1063`), `frequency_type` daily/weekly/monthly (`:1069`), `target_value`/`target_unit` (`:1075-1082`), `sessions_per_week` (`:1088`), `category` (`:1093`), `start_date`/`end_date` (`:1051-1054`).
- **HabitGoalLink** (`:1458`), **GoalSignalSource** (`:1489`), **HabitEntry** (`:1525`, daily tracking child), **GoalInsight** (`:1666`).

## Canonical State
- **SAE builder:** `build_goal_state(user)` (`apps/core/ai_state/state_builder.py:1424`) and `build_habit_state(user)` (`:1534`). Registered under both `goals` and `purpose` aliases (`:5578-5580`).
- **Truth contract:** `apps/purpose/services/goal_queries.py` (`active()`, `with_milestones()`, `overdue()`) per `docs/DOMAIN_TRUTH_CONTRACTS.md`.
- **Analytics / streaks:** `GoalAnalytics` (`apps/purpose/services/analytics_service.py:27`) — `get_analytics()` (`:48`), `get_completion_rate()` (`:98`), `get_weekly_consistency()` (`:133`), `get_trend()` (`:206`). `StreakData` (`apps/purpose/services/streak_service.py:20`) — `get_streak_data()` (`:28`), `get_current_streak()` (`:57`), `get_longest_streak()` (`:80`), `_is_at_risk()` (`:338`).

## Signal Outputs
- **PIE rules** (`module = "purpose"`): `GoalProgressRule` (`apps/core/ai_insights/rules_goals.py:15`), `GoalDeadlineRiskRule` (`:138`), `GoalStagnationRule` (`:204`); `HabitBrokenStreakRule` (`apps/core/ai_insights/rules_habits.py:14`), `HabitConsistencyPositiveRule` (`:96`).
- **PRIE prediction rules:** `apps/core/ai_predictions/prediction_rules_goals.py`, `prediction_rules_habits.py`.
- **Capability proactive_signals:** `goal_deadline_approaching`, `habit_streak_break`, `intention_unchecked` (`apps/purpose/capabilities.py:4`).
- **Signal weighting:** `GoalSignalConfigService.auto_populate()` (`apps/purpose/services/goal_signal_config.py:78`), `get_signal_weights()` (`:117`).

## Major Services
`analytics_service.py`, `streak_service.py`, `goal_signal_config.py`, `recommendation_service.py`, `objective_weight_milestones.py`, plus `mission_selection.py` (top-level).

## APIs / Endpoints (`apps/purpose/urls.py`)
HTML/HTMX views (no JSON API). Key routes: `PurposeHomeView` (`:79`); goals CRUD `GoalListView` (`:93`) / `GoalCreateView` (`:94`) / `GoalDetailView` (`:95`) / `GoalToggleStatusView` (`:98`) / `GoalPrimaryMissionToggleView` (`:99`); `MilestoneToggleView` (`:105`); direction `DirectionListView` (`:82`); habits `HabitGoalListView` (`:136`), `HabitLogTodayView` (`:143`), `HabitLogDatesView` (`:145`), `GoalAnalyticsView` (`:154`), `GoalInsightsView` (`:155`).
Intelligence hook `fire_intelligence()` invoked from `apps/purpose/views.py` lines 362, 427, 896, 1009, 1406 (intents create_goal/complete_goal/create_habit/log_habit/complete_milestone).

## Dashboards / UI
`templates/purpose/` views above. Dashboard tiles `goal_progress`, `habit_goals` (`docs/calendar_engine_discovery.md:65`).

## Relationships to Other Domains
- → **Calendar Engine**: goals/milestones/habits projected via signals (below).
- → **Life/Tasks**: `TaskGoalLink` (`apps/life/models.py:578`), `HabitGoalLink` (`apps/purpose/models.py:1458`).
- → **Finance**: `FinancialGoal.life_goal` FK→LifeGoal (`apps/finance/models.py:820`).
- **LifeDomain** is the shared domain taxonomy consumed across calendar, finance metrics, etc.

## Observability Path
- `apps/purpose/signals.py`: `handle_goal_saved` (`:24`, post_save LifeGoal → `upsert_from_goal()` + `GoalSignalConfigService.auto_populate()`), `handle_milestone_saved` (`:52`), `handle_habit_saved` (`:69`), `handle_goal_deleted` (`:84`), `handle_habit_deleted` (`:97`).
- SAE cache: `wlj:user_state:{user.id}:goals` / `:habits` (standard SAE module cache convention).

---

# 2. LIFE / TASKS (Tasks, Routines, Events, Pets, Inventory, Documents)

## Purpose
The Life domain is the execution surface: discrete tasks, recurring routines, calendar/life events, household inventory & maintenance, pets, and documents. Tasks + routines are the atoms consumed by the **execution-state decision pipeline** that drives the CoS's "what next / biggest risk / fix first" answers.

## Primary Models (`apps/life/models.py`)
- **Project** (`:47`, UserOwnedModel) — `title` (`:68`), `status` (`:78`), `priority` (`:83`), `target_date` (`:91`), `category` (`:99`).
- **Task** (`:161`, UserOwnedModel) — `title` (`:199`), `project` FK (`:203`), `priority` now/soon/someday (`:211`), `effort` (`:216`), `module` (`:221`), `commitment_level` (`:229`), `is_foundational` (`:235`), `skip_streak` (`:240`), `due_date` (`:251`), `completion_status` (`:259`), `completed_at` (`:265`), `progress_state` JSON (`:272`), `is_recurring`/`recurrence_pattern` (`:279-280`), `is_routine` (`:298`), `scheduled_time`/`scheduled_end_time` (`:302-307`), `grace_minutes` (`:312`), `estimated_duration_minutes` (`:316`), `depends_on_key` (`:336`), `hide_until_ready` (`:349`), `email_source_*` (`:358-374`). **No domain/LifeDomain FK** (`docs/calendar_engine_discovery.md:15`).
- **TaskGoalLink** (`:578`) — Task↔LifeGoal link.
- **LifeEvent** (`:612`, UserOwnedModel) — `title` (`:631`), `event_type` (`:634`), `start_date`/`start_time`/`end_date`/`end_time`/`is_all_day` (`:641-645`), `location` (`:648`), `is_recurring`/`recurrence_pattern`/`recurrence_end_date` (`:651-657`), `external_id`/`external_source` (`:669-674`).
- **InventoryItem** (`:724`) + **InventoryPhoto** (`:797`); **MaintenanceLog** (`:821`, `matched_schedule_id` `:891`); **Pet** (`:913`) + **PetRecord** (`:1061`).
- **Document** (`:1218`) + **DocumentSignal** (`:1450`) — uploaded documents and extracted metadata signals (KNOWLEDGE domain).
- **SignificantEvent** (`:1751`) — relational/birthday events surfaced as signals.
- **Routine canon:** **Routine** (`:2528`, UserOwnedModel), **RoutineSchedule** (`:2553`, per-time-window schedule), **RoutineLog** (`:2720`, UserOwnedModel — completion log with `log_status` completed/completed_late). This is the *routine-domain* model set, distinct from task-based routines (`Task.is_routine=True`, `apps/life/models.py:298`).

## Canonical State — Execution Decision Pipeline (central)
The pipeline lives in `apps/core/execution/` and `apps/core/today/`.

**Execution Truth Engine** (`apps/core/execution/execution_truth_engine.py`) — the cross-domain single source of completion + expectation, using ONLY raw authoritative data (no cache/inference):
- `get_execution_truth(user, target_date)` (`:81`) → `{date, domains{faith,workout,journal}, routines, tasks, medications}`.
- Cross-domain bridge name sets `FAITH_PRAYER_NAMES` (`:58`), `FAITH_BIBLE_NAMES` (`:61`), `WORKOUT_NAMES` (`:66`), `JOURNAL_NAMES` (`:74`).
- `_derive_expectations` (`:172`), `_check_faith` (`:285`), `_check_workout` (`:338`), `_check_journal` (`:357`), `_check_routines` (`:375`), `_check_tasks` (`:525`), `_check_medications` (`:568`), `_apply_routine_faith_bridge` (`:599`).

**Today Execution Contract** (`apps/core/execution/today_execution.py`) — atomic daily item list:
- `build_today_execution(user)` (`:34`) → `{items, summaries}`. Collectors: `_collect_task_items` (`:141`, excludes blocked via `is_task_blocked()`), `_collect_routine_items` (`:216`), `_collect_medication_items` (`:324`), `_collect_domain_summaries` (`:441`).

**Unified Execution State** (`apps/core/execution/execution_state.py`):
- `build_execution_state(user, now, execution_contract)` (`:46`) — composes today_execution + active_block + action prioritizer into the single contract for all three CoS modes. Returns keys incl. `active_block, items, actions, eligible_actions, overdue_actions, now/next/upcoming_actions, expired_items, deferred_items, at_risk_actions, recovery_state, blocked_dependents`. `_compute_blocked_dependents` (`:189`) maps `depends_on_key` → blocked Task pks.

**Deterministic Selectors / CoS modes** (`apps/core/execution/selectors.py`):
- `get_next_action(state)` (`:145`, EXECUTION mode), `get_biggest_risk(state)` (`:254`, RISK mode), `get_fix_priority(state)` (`:326`, FIX mode), dispatch `SELECTORS`/`select(mode, state)` (`:434/:441`).

**Task Classification** (`apps/core/execution/task_classifier.py`) — the HARD_EXPIRED / WINDOWED / SOFT_EXPIRED / FLEXIBLE enum:
- Constants `HARD_EXPIRED` (`:31`, time-bound external event/service/appt, no recovery value past window), `WINDOWED` (`:32`, nutrition anchors/meds — meaningful only in window), `SOFT_EXPIRED` (`:33`, faith/workout/journal/routine — recoverable until day close), `FLEXIBLE` (`:34`, unscheduled — any time OK).
- `_ACTIVITY_TYPE_RULES` (`:44`) maps `activity_type` → `(task_class, grace_minutes, is_reset_action)`.
- `classify(item)` (`:100`, resolution: registry → activity-type → medication → source-type → schedule → FLEXIBLE), `annotate(item)` (`:151`, mutates item with `task_class`/`recovery_grace_minutes`/`is_reset_action`).

**Active Block resolver** (`apps/core/execution/active_block.py`) — current execution time-window context:
- `get_active_block(user, now, execution_items)` (`:145`) → `{name, start_time, end_time, lead_in_end_time, next_block_name, next_block_start, bounds}`. `_derive_per_user_bounds` (`:75`), `_merge_with_static` (`:122`), `is_item_in_active_block` (`:296`, EXECUTION-mode eligibility gate), `first_eligible_overdue` (`:268`).

**Action routing** (`apps/core/execution/action_routing.py`): `resolve_action_destination(item)` (`:150`, metadata-first deep-link resolver), `_activity_to_dest` (`:60`), `_module_to_dest` (`:74`), `_keyword_dest` (`:115`).

**Completion / verification:**
- `apps/core/execution/completion_service.py` — per-domain boolean truth: `is_workout_complete` (`:34`), `is_journal_complete` (`:48`), `is_bible_reading_complete` (`:61`), `is_prayer_complete` (`:77`), `is_medication_complete` (`:92`), `is_task_complete` (`:122`), `is_routine_item_complete` (`:131`), `validate_completion_invariants` (`:154`).
- `apps/core/execution/verified_completion.py` — `VERIFIED_ACTIVITIES` registry (`:44`), `apply_verified_completion` (`:69`), `complete_wake_up` (`:178`), `_complete_execution_item` (`:256`).

**Today Engine / Today State** (renderer-facing canonical day context):
- `get_today_context(user)` (`apps/core/today/today_engine.py:30`) → `{all_items, foundation, overdue, coming_up, later, completed, next}`. Collectors `_collect_routine_items` (`:188`), `_collect_task_items` (`:227`), `_collect_calendar_items` (`:289`), `_collect_medication_items` (`:345`).
- `build_today_state(user)` (`apps/core/services/today_state.py:27`, delegates all completion to Execution Truth), `_build_confidence_rollup` (`:90`), `format_today_state_injection` (`:145`, renders truth block into CoS system prompt).

**SAE builders:** `build_task_state(user)` (`apps/core/ai_state/state_builder.py:3121`), `build_routine_state(user)` (`:3999`), `build_life_events_state(user)` (`:2962`).

## Signal Outputs
- **Task signals** (`apps/life/services/task_signals.py`): `build_task_signals(task_state)` (`:124`) emitting `_signal(key, state, value, insight)` (`:29`) — `_eval_momentum` (`:38`, `task_momentum` strong/moderate), `_eval_pressure` (`:69`), `_eval_slippage` (`:96`).
- **Event signals** (`apps/life/services/event_signals.py`): `build_significant_event_signals(events_state)` (`:108`), `infer_relationship_priority` (`:46`).
- **PIE rules** (`module = "life"`): `TaskOverduePatternRule` (`apps/core/ai_insights/rules_tasks.py:18`), `TaskStallRule` (`:87`), `TaskDueTodayRule` (`:150`).
- **PRIE:** `apps/core/ai_predictions/prediction_rules_tasks.py`.
- **Document signals:** `DocumentSignalExtractor.extract_signals()` (`apps/life/services/document_signal_extractor.py:102`).
- **Capability proactive_signals:** `task_overdue`, `event_approaching`, `nn_skip_streak`, `busy_day_upcoming` (`apps/life/capabilities.py:4`); `document_expiring` (KNOWLEDGE, `:27`).

## Major Services (`apps/life/services/`)
`task_queries.py` (truth contract), `task_priority_service.py`, `task_coaching_builder.py`, `task_signals.py`, `event_signals.py`, `event_acknowledgment.py`, `recurrence.py` (recurring engine), `routine_service.py` (`RoutineTaskService:30`), `routine_helpers.py`, `_routine_internal.py`, `routine_health_service.py`, `routine_sync_service.py`, `morning_reconciliation.py`, `proactive_planning_service.py`, `maintenance_routine_matcher.py`, `document_signal_extractor.py`, `document_fact_extractor.py`, email pipeline (`email_processor.py`, `email_classifier.py`, `email_fact_extractor.py`, `email_fact_service.py`), Google sync (`google_calendar.py`, `gmail.py`, `gmail_sync.py`).

## APIs / Endpoints (`apps/life/urls.py`)
HTML/HTMX (no JSON API namespace). Key: `LifeHomeView` (`:129`); tasks `TaskListView` (`:139`), `TaskCreateView` (`:140`), `TaskToggleView` (`:143`), `TaskSkipView` (`:144`); routines `RoutineListView` (`:148`), `RoutineAdherenceView` (`:157`); calendar `CalendarView` (`:162`), `EventCreateView` (`:163`); pets `PetListView` (`:181`); documents `DocumentListView` (`:222`), `DocumentDownloadView` (`:227`); `SignificantEventListView` (`:232`); Google `GoogleCalendarSettingsView` (`:240`), `GoogleCalendarSyncView` (`:245`); `GmailSyncCronView` (`:255`).

## Dashboards / UI
`templates/life/`; dashboard tiles `upcoming_events`, plus Today/agenda renderers consume `get_today_context`. No standalone timeline (calendar_engine adds it).

## Relationships to Other Domains
- → **Calendar Engine**: Task/LifeEvent/Routine projected to CalendarEvent (signals below).
- → **Purpose**: `TaskGoalLink` (`:578`).
- → **Health/Faith/Journal/Medicine**: Execution Truth bridges routine items into those domains' completion (`execution_truth_engine.py:55-78`).
- → **Relationships**: Task/LifeEvent text parsed for @mentions (relationships signals below).

## Observability Path (`apps/life/signals.py`)
- `handle_task_saved` (`:46`, post_save Task → `upsert_from_task()`, invalidate CoS cache, defer SAE refresh, invalidate dashboard cache, `:66-119`), `handle_routine_saved` (`:122`), `handle_routine_schedule_saved` (`:132`), `handle_routine_log_saved` (`:166`, defers SAE for routine+execution, invalidates CoS+dashboard caches), `handle_life_event_saved` (`:204`, `upsert_from_life_event()`), `handle_task_deleted` (`:220`), `handle_pet_saved/deleted` (`:25/:233`, birthday SignificantEvent), `handle_document_saved_for_extraction` (`:257`).
- Cache keys: `wlj:user_state:{user.id}:routine` / `:execution`, `wlj:cos_context:{user.id}` (`apps/life/services/routine_helpers.py:972-974`); `wlj:reconcile:{user_id}:{date}` (`morning_reconciliation.py:26`); ops telemetry `wlj:ops:document_content_extraction` (`apps/life/tasks/document_extraction.py:208`), `wlj:ops:document_fact_extraction` (`:233`), `wlj:ops:email_fact_extraction` (`email_fact_service.py:528`).
- Deferred refresh helpers: `_defer_sae_refresh()` (`apps/ai/signals.py`, called from `life/signals.py:110,150,184`), `invalidate_cos_context()` (`apps/ai/readiness_cache.py`, called `:102,156,192`), `DashboardV2CacheService.invalidate_all()` (called `:117,161,199`).

---

# 3. CALENDAR ENGINE (`apps/calendar_engine`)

## Purpose
The Calendar Engine is the **projection + scheduling layer**: a unified timeline that ingests source items (tasks, goals, habits, medicine schedules, faith plans, workouts, life events) and projects them as `CalendarEvent` rows, with recurrence expansion, conflict detection, gap suggestions, domain-balance metrics, and deterministic NL date resolution. It does not own source data — it mirrors it via idempotent upserts.

## Primary Models (`apps/calendar_engine/models.py`)
- **CalendarEvent** (`:13`) — `user` FK (`:82`), `title` (`:87`), `start_dt`/`end_dt` (`:90-91`), `is_all_day` (`:92`), `domain` FK→purpose.LifeDomain (`:94`), `event_kind` (`:102`), `source_type` (`:107`), `source_id` (`:112`), `commitment_level` (`:118`), `is_protected` (`:126`), `status` (`:131`), `idempotency_key` (`:137`), `deleted_at` soft-delete (`:143`).
- **RecurrenceRule** (`:203`) — OneToOne to event (`:219`): `frequency` (`:224`), `byweekday` JSON (`:225`), `interval` (`:230`), `until_dt` (`:231`), `count` (`:232`), `timezone` default America/Chicago (`:233`).
- **RecurrenceException** (`:330`) — per-occurrence override/cancel: `original_start_dt` (`:341`), `new_start_dt`/`new_end_dt` (`:344-345`), `is_canceled` (`:346`).
- **CalendarOverrideLog** (`:356`) — drift/override audit: `event`/`overridden_event` (`:367-372`), `reason` (`:377`).
- **DeclinedSuggestion** (`:384`) — `source_type`/`source_id` (`:395-396`), `declined_date` (`:397`).

## Canonical State / Resolvers
- **Projection engine** (`apps/calendar_engine/services/projection.py`): idempotent upserts keyed by `idempotency_key` — `upsert_from_task` (`:119`), `upsert_from_routine_task` (`:210`), `upsert_execution_block_for_task` (`:303`), `upsert_from_goal` (`:370`), `_upsert_milestone_marker` (`:431`), `upsert_from_habit` (`:499`), `upsert_from_medicine_schedule` (`:606`), `upsert_from_faith_routine` (`:710`), `upsert_from_workout_schedule` (`:802`), `upsert_from_life_event` (`:920`); matching `delete_*_events` cleanups.
- **Deterministic date resolution** (`apps/calendar_engine/utils/date_resolution.py`): `resolve_weekday_to_date(...)` (`:75`, all weekday/relative-date math server-side, never trusts the LLM), `_next_weekday` (`:238`), `_last_weekday` (`:279`), `_weekday_n_weeks_from_now` (`:293`).
- **Mutation service** (`apps/calendar_engine/services/calendar_mutation_service.py`): `MutationResult` (`:43`), `CalendarMutationService.create` (`:171`), `.update` (`:449`), `.delete` (`:581`); `should_auto_protect` (`:157`), `_auto_create_backing_task` (`:387`), `_check_pre_commit_conflicts` (`:644`), `_run_post_scheduling` (`:710`), `_sync_to_google` (`:779`).
- **SAE builder:** `build_calendar_state(user)` (`apps/core/ai_state/state_builder.py:3833`).

## Signal Outputs
No `signals.py` in this app — it is a downstream **consumer** of upstream domain post_save signals (Purpose/Life trigger the `upsert_from_*` projections). Emits `CalendarOverrideLog` drift records and `DeclinedSuggestion` learning records rather than UnifiedSignals.

## Major Services (`apps/calendar_engine/services/`)
`projection.py` (35.8KB core), `calendar_mutation_service.py`, `conflicts.py` — `check_conflicts` (`:38`), `detect_all_conflicts` (`:121`), `classify_conflict_case` (`:169`), `build_conflict_message` (`:197`); `suggestions.py` — `find_gaps_for_day` (`:21`), `get_items_due_soon` (`:109`), `generate_suggestions` (`:182`); `metrics.py` — `compute_domain_minutes` (`:16`), `compute_domain_percentages` (`:68`), `get_today_balance` (`:98`), `get_week_balance` (`:107`); `nlp_parse.py`. Utils: `formatting.py` (`friendly_date/time/datetime` `:28-72`), `idempotency.py` (`compute_idempotency_key` `:20`), `date_resolution.py`.

## APIs / Endpoints (`apps/calendar_engine/urls.py`) — primary JSON API surface of these 5 domains
HTML: `CalendarDashboardView` (`:9`), `ManageEventsView` (`:10`), `MonthView` (`:13`).
JSON API: `TodayTimelineView` `api/today/` (`:16`), `RangeView` `api/range/` (`:17`), `MonthDataView` `api/month/` (`:18`), `AllEventsView` `api/events/all/` (`:19`), `EventCreateView` `api/events/` (`:20`), `EventDetailView` `api/events/<pk>/` (`:21`), `EventMoveView` `api/events/<pk>/move/` (`:22`), `GapSuggestionsView` `api/suggestions/gaps/` (`:25`), `AcceptSuggestionView` (`:26`), `DeclineSuggestionView` (`:27`), `DomainBalanceView` `api/metrics/balance/` (`:30`), `NLPCreateView` `api/nlp_create/` (`:33`).

## Dashboards / UI
`templates/calendar_engine/` — timeline/month dashboard fed by the `api/today` and `api/range` JSON endpoints (HTMX/JS). New timeline surface vs. the legacy life CalendarView.

## Relationships to Other Domains
Consumes from Purpose (goals/milestones/habits), Life (tasks/routines/events), Health/Medicine (medicine schedules, workouts), Faith (reading plans). FKs to `purpose.LifeDomain` for domain tagging (`:94`). Co-exists with `apps/core/blueprint` `ScheduledBlock` (reads, does not own — `docs/calendar_engine_discovery.md:90`).

## Observability Path
`CalendarOverrideLog` (`:356`) for drift/override audit; `DeclinedSuggestion` (`:384`) for suggestion-learning; `idempotency_key` (`:137`) prevents duplicate projections. Google sync via mutation service `_sync_to_google` (`:779`).

---

# 4. RELATIONSHIPS (`apps/relationships`)

## Purpose
The Relationships domain models the people in the user's life, their groupings, interaction history, and @mentions extracted from other domains. It produces a relational-health signal (neglect detection, cadence) that feeds the CoS context.

## Primary Models (`apps/relationships/models.py`)
- **Person** (`:35`, SoftDeleteModel) — `owner` FK (`:71`), `first_name`/`last_name`/`display_name` (`:78-87`), `email`/`phone` (`:92-97`), `relationship_type` (`:103`), `household` self-FK (`:114`), `last_interaction_date` (`:124`), `interaction_count` (`:129`); `all_objects` manager (`:135`).
- **PersonGroup** (`:179`, SoftDeleteModel) — `owner` (`:187`), `name` (`:193`), `members` M2M→Person (`:201`).
- **RelationshipInteraction** (`:239`, TimeStampedModel) — `person` FK (`:258`), `user` (`:263`), `context_type_label` (`:268`), `interaction_date` (`:273`), generic `content_type`/`object_id` (`:278-284`).
- **Mention** (`:310`, TimeStampedModel) — `person` (`:318`), generic `content_type`/`object_id` (`:325-329`) linking @mention back to source object.

## Canonical State
- **SAE builder:** `build_relationships_state(user)` (`apps/core/ai_state/state_builder.py:4671`) — connection health/neglect; uses canonical `Person`/`RelationshipInteraction`, falls back to legacy `apps.core.ai_relationships` for importance_tier/cadence.
- **Relational health:** `RelationalHealthService.compute_health()` (`apps/relationships/services.py:219`), `_compute` (`:241`), `_generate_insights` (`:437`). Cached at `relational_health:{user.pk}` (`:231-237`).
- **Analytics:** `RelationshipAnalyticsService` (`:43`) — `record_interaction()` (`:47`), `last_interaction()` (`:110`), `days_since_last_interaction()` (`:135`), `context_breakdown()` (`:142`), `get_summary()` (`:160`), `top_interacted()` (`:180`).

## Signal Outputs
- **Capability:** proactive_signals `relationship_gap`, `birthday_approaching`; `expected_signal_types=['relational_engagement']`; context_builder `_build_people_and_mood` (`apps/relationships/capabilities.py:4`).
- Relational-health insights produced by `_generate_insights` (`services.py:437`).

## Major Services (`apps/relationships/services.py`)
`RelationshipAnalyticsService` (`:43`), `RelationalHealthService` (`:202`), `MentionParserService` (`:477`) — `parse_and_link()` (`:494`), `_find_person()` (`:622`), `_create_mention()` (`:644`), `_detect_context_type()` (`:656`); `ContactImportService` (`:674`) — `import_vcf()` (`:685`), `_parse_vcf()` (`:761`).

## APIs / Endpoints (`apps/relationships/urls.py`)
`PersonListView` (`:20`), `PersonCreateView` (`:21`), `PersonDetailView` (`:22`), `GroupListView` (`:27`), `GroupCreateView` (`:28`), `RelationshipInsightsView` (`:35`); JSON helpers `PersonAutocompleteView` (`:41`), `PersonQuickCreateView` (`:42`).

## Dashboards / UI
`templates/relationships/` — people list, person detail, groups, `RelationshipInsightsView` insights page.

## Relationships to Other Domains
Pulls @mentions FROM Journal, Life (Task, LifeEvent), Faith (PrayerRequest), Meals (MealPlan) via generic FK Mention. `RelationshipInteraction` uses generic content_type to point at any source object.

## Observability Path (`apps/relationships/signals.py`)
- Mention extraction handlers (all gated on AI/PA enabled + contacts exist, via `_extract_mentions_from_instance` `:28`): `extract_mentions_from_journal` (`:79`, journal.JournalEntry), `extract_mentions_from_task` (`:87`, life.Task), `extract_mentions_from_prayer` (`:95`, faith.PrayerRequest), `extract_mentions_from_mealplan` (`:105`, meals.MealPlan), `extract_mentions_from_event` (`:113`, life.LifeEvent).
- Cache key: `relational_health:{user.pk}` with `CACHE_TTL` (`services.py:231-237`).

---

# 5. FINANCE (`apps/finance`)

## Purpose
The Finance domain tracks accounts, transactions, categories, budgets, financial goals, and computed metric snapshots (net worth, cash flow, savings rate). It supports file imports (CSV/OFX/QIF) and Plaid bank connections, with a dedicated security layer (audit, rate limit, MFA) and an AI insights service. Gated behind the `finances_enabled` preference.

## Primary Models (`apps/finance/models.py`)
- **FinancialAccount** (`:50`, UserOwnedModel) — `name` (`:106`), `account_type` (`:110`), `institution` (`:115`), `current_balance` (`:122`), `include_in_net_worth` (`:166`), `is_hidden` (`:170`), `bank_connection` FK (`:176`), `plaid_account_id` (`:184`), `is_synced` (`:189`).
- **TransactionCategory** (`:275`) — `name` (`:294`), `category_type` (`:298`), `parent` self-FK (`:305`), `is_system` (`:338`).
- **Transaction** (`:397`, UserOwnedModel) — `account` FK (`:409`), `date` (`:415`), `amount` (`:418`), `description` (`:423`), `category` FK (`:429`), `payee` (`:439`), `is_cleared` (`:452`), `is_recurring` (`:456`), `is_opening_balance` (`:460`), `transfer_pair` O2O (`:466`), `tags` JSON (`:476`), `import_record` FK (`:483`), `source_type`/`source_id` (`:502-508`), `fingerprint` (`:516`), `receipt_document` FK (`:525`), `plaid_transaction_id` (`:535`), `plaid_pending` (`:541`).
- **Budget** (`:594`, UserOwnedModel) — `month` (`:602`), `category` FK (`:607`), `budgeted_amount` (`:615`), `rollover_enabled`/`rollover_amount` (`:623-627`).
- **FinancialGoal** (`:721`, UserOwnedModel) — `name` (`:758`), `goal_type` (`:762`), `target_amount`/`current_amount` (`:773-779`), `target_date` (`:787`), `goal_status` (`:803`), `linked_account` FK (`:810`), `life_goal` FK→purpose.LifeGoal (`:820`).
- **FinancialMetricSnapshot** (`:931`, UserOwnedModel) — `snapshot_date` (`:940`), `total_assets`/`total_liabilities`/`net_worth` (`:945-957`), `monthly_income`/`monthly_expenses`/`monthly_cash_flow` (`:965-977`), `savings_rate` (`:985`), `debt_to_income_ratio` (`:991`), `liquid_assets` (`:1000`), `emergency_fund_months` (`:1006`).
- **TransactionImport** (`:1123`), **BankConnection** (`:1311`, encrypted `access_token_encrypted` `:1344`, `connection_status` `:1368`), **BankIntegrationLog** (`:1498`), **FinanceAuditLog** (`:1560`), **Payee** (`:1644`), **RecurringTransaction** (`:1694`).

## Canonical State
- **SAE builder:** `build_finance_state(user)` (`apps/core/ai_state/state_builder.py:4521`) — obligations/cash pressure/spending; gated on `prefs.finances_enabled`, returns `{"enabled": False}` when off (`:4534-4537`).
- **Metric snapshots:** `FinancialMetricSnapshot` (`:931`) is the persisted observability/history record; sync via `apps/finance/services/sync_service.py`.

## Signal Outputs
- **Capability:** intent_types `log_transaction`, `check_budget`; context_builder `_build_finance_context`; proactive_signals `budget_threshold`, `savings_milestone`, `spending_pattern`; `expected_signal_types=['financial_health']` (`apps/finance/capabilities.py:4-12`).
- **AI insights:** `FinanceAIService` (`apps/finance/services/ai_insights.py:49`) — `generate_spending_insight()` (`:375`), `generate_budget_alert()` (`:439`), `generate_goal_encouragement()` (`:473`), `generate_subscription_review()` (`:509`), `_detect_unusual_spending()` (`:264`), `_identify_recurring_transactions()` (`:332`).
- No `signals.py` in this app (no Django post_save signal handlers).

## Major Services
- `ai_insights.py` — `FinanceAIService` (`:49`, `check_consent()` `:72`).
- `plaid_service.py` — `PlaidService` (`:40`): `create_link_token()` (`:108`), `exchange_public_token()` (`:186`), `get_accounts()` (`:237`), `sync_transactions()` (`:269`).
- `sync_service.py`, `recurring.py`, `encryption.py`.
- `apps/finance/import_service.py` — `TransactionImportService` (`:50`): `detect_file_type()` (`:107`), `parse_file()` (`:136`), `_parse_csv()` (`:156`), `_parse_ofx()` (`:296`), `_parse_qif()` (`:432`), `create_transactions()` (`:542`).
- `apps/finance/security.py` — `FinanceAuditLogger` (`:41`), `FinanceRateLimiter` (`:290`, cache-backed `_get_cache_key` `:311`), `FinanceMFAController` (`:512`); decorators `finance_rate_limit()` (`:363`), `requires_recent_auth()` (`:401`), `requires_mfa_for_sensitive_ops()` (`:599`); helpers `verify_ownership()` (`:438`), `is_large_transaction()` (`:470`), `mask_account_number()` (`:483`).

## APIs / Endpoints (`apps/finance/urls.py`)
HTML: `FinanceDashboardView` (`:17`), `AccountListView` (`:20`), `TransactionListView` (`:27`), `TransactionCreateView` (`:28`), `BudgetListView` (`:39`), `GoalListView` (`:56`), `MetricsDashboardView` (`:64`), `import_upload_view` (`:71`), `BankConnectionListView` (`:86`).
JSON API: `quick_transaction` `transactions/quick/` (`:29`), `api_payee_suggestions` `api/payees/` (`:76`), `api_account_balance` `api/accounts/<pk>/balance/` (`:77`), `api_spending_insight` `api/insights/spending/` (`:80`), `api_subscription_review` `api/insights/subscriptions/` (`:81`), `api_budget_alert` `api/insights/budget/<pk>/` (`:82`); `bank_connection_start` (`:87`), `plaid_webhook` `webhooks/plaid/` (`:94`).

## Dashboards / UI
`templates/finance/` — `FinanceDashboardView` (`:17`), `MetricsDashboardView` (`:64`, net-worth/cash-flow), accounts/transactions/budgets/goals lists.

## Relationships to Other Domains
- → **Purpose**: `FinancialGoal.life_goal` FK→LifeGoal (`:820`).
- → **Capture/Documents**: `Transaction.receipt_document` FK (`:525`).
- → **Plaid/Google** external integrations via `BankConnection` (`:1311`).

## Observability Path
- `FinancialMetricSnapshot` (`:931`) — persisted daily metrics history.
- `FinanceAuditLog` (`:1560`) + `BankIntegrationLog` (`:1498`) — audit/integration telemetry.
- Rate-limit cache keys via `FinanceRateLimiter._get_cache_key` (`apps/finance/security.py:311`).

---

## Notable Gaps & Doc-vs-Code Deltas

1. **`docs/calendar_engine_discovery.md` line numbers are stale.** It cites Task at `apps/life/models.py:161-344`, LifeGoal at `apps/purpose/models.py:190-436`, HabitGoal at `783-1219`. Actual: Task starts `:161` (still valid), LifeGoal `:190` (valid), but **HabitGoal is at `:1021`, not `783`** (`apps/purpose/models.py:1021`). The discovery doc predates later model additions.
2. **`docs/calendar_engine_discovery.md:53` references `ScheduledBlock` at `apps/core/blueprint/models.py:642-725`** — not re-verified in this pass; flagged for confirmation if blueprint is in scope.
3. **No `signals.py` in `apps/calendar_engine` or `apps/finance`.** Calendar projection is driven entirely by upstream `purpose`/`life` post_save handlers; Finance has no Django signal handlers (state refresh is preference-gated SAE + explicit service calls). Documented above, but worth noting since other domains follow the signals.py-per-app convention.
4. **PIE rules use `module = "purpose"` for both goals AND habits** (`rules_goals.py:25`, `rules_habits.py:16`), while habit *SAE state* is a separate builder (`build_habit_state`). The `purpose`/`goals` SAE aliases both resolve to `build_goal_state` (`state_builder.py:5578-5580`) — habit state is only reachable via the explicit `habits` key.
5. **Task has no LifeDomain FK** (confirmed `apps/life/models.py:161` block has no `domain` field) — calendar projection infers domain from `module`/project, consistent with `calendar_engine_discovery.md:15`.
6. **Two routine notions coexist** (documented): the Routine-canon models `Routine`/`RoutineSchedule`/`RoutineLog` (`apps/life/models.py:2528/2553/2720`) vs. task-based routines (`Task.is_routine=True`, `:298`). The Execution Truth Engine reconciles both via `_check_routines` (`execution_truth_engine.py:375`).
