# WLJ Engine & CoS Reference

**Auto-maintained document.** Updated whenever engines, CoS context, or intelligence pipeline changes are made.
**Last updated:** 2026-06-03 (Nutrition Answer-First Response Contract — follow-up to the routing-precedence fix below: routing and state were now correct, but the RESPONSE SHAPE was wrong — "How am I doing on protein today?" returned the full CoS decision template (a "Priority note: sleep" cross-domain overlay + "Macro compliance 23/100 — well off target" interpretation + an Action coaching line) when the user asked one narrow factual question. Defect class: correct routing + correct nutrition state + wrong response assembly. Root cause in `apps/ai/deterministic_router.py :: _handle_nutrition_query` — it unconditionally rendered `_format_decision_response(situation, interpretation, action, trust, priority_note=_get_high_priority_note(user, exclude_domain='nutrition'))`; the decision/coaching template + an always-on cross-domain priority note is the wrong UX contract for a direct factual status question. Fix (Problem 1 only — answer-first): new `_nutrition_fact_response(nut, msg_lower)` returns grounded totals ONLY (the asked nutrient — protein/calorie detected from the message; generic phrasing reports both — plus a neutral over/under target delta when a target is grounded; no priority note, no macro-score verdict, no Interpretation/Action, no cross-domain content); new `_is_nutrition_coaching_request(msg_lower)` makes fact mode the DEFAULT and reserves the Situation/Interpretation/Action template for explicit guidance asks ("what should I do about my macros?"); `_handle_nutrition_query(user, msg_lower=None)` gains an early return after the confidence guard (factual → fact response, or None → fall through, never to the coaching template). Phase 0a.2 call site passes `msg_lower`; the Phase 1 data-route dispatcher auto-passes it via signature inspection; the validator-regenerate path (`msg_lower=None`) defaults to answer-first. Before→after for "How am I doing on protein today?": a 4-section decision block with a sleep priority note and macro-compliance coaching → "You're at 136g protein today. / Target: 180g. / That's 44g under target." Scope held to Problem 1 — protein target source, NutritionGoals, macro-compliance formula, calorie-burn grounding, exercise attribution, and workout timezone are UNTOUCHED (separate PRs). +6 tests in `apps/ai/tests/test_nutrition_trust.py` (`TestNutritionAnswerFirstContract`); 19/19 nutrition-trust tests pass; pre-existing router failures identical on baseline via `git stash` — zero new failures. No model/schema/migration changes. Previous: Nutrition Status Routing Precedence Fix — regression follow-up to the Beth-Trust fix below: food estimates correctly bypassed coaching, but "How am I doing on protein today?" routed into EXECUTION COACHING ("Go straight into Bike Ride…") instead of a nutrition status answer. Root cause traced through `classify_and_route` in `apps/ai/deterministic_router.py`: the nutrition data route lives in Phase 1 (`_try_deterministic_data_routes`), but the decision/focus routers run EARLIER — Phase 11.1 `_try_decision_query_route` and Phase 4 `_try_focus_query_route`. "How am I doing…" contains `'how am i doing'` ∈ `_FOCUS_QUERY_PHRASES` → `_is_focus_query` → `_is_decision_query` → Phase 11.1 fired and returned coaching BEFORE Phase 1 nutrition ever ran. Secondary defect: `_match_nutrition_query` only knew a hand-curated phrase list, so `'protein today'`/`'nutrition today'`/`'macro compliance'`/`'how am I doing on protein…'` matched NOTHING. Two-part fix: (1) new Phase 0a.2 HARD nutrition-status route inserted in `classify_and_route` BEFORE Phase 11.1 — a nutrition status query is now answered deterministically and is no longer preemptable by decision/focus/execution routing; food-estimate/logging phrasing is excluded inside the matcher so "I had 8 oysters…" still falls through, and a None handler return (no data / confidence-guard refusal) falls through to the normal pipeline unchanged; (2) `_match_nutrition_query` rewritten two-tier — Tier 1 keeps the exact-phrase anchors, Tier 2 is compositional: a nutrient keyword (protein/calorie(s)/macro(s)/carb(s)/carbohydrate/nutrition/fiber) + a status anchor (today/how am i doing/how are my/how much/status/compliance/this week/have i had/where am i/…), with logging verbs and burn/burned/burnt (exercise calories) excluded. Verified routing: "How am I doing on protein today?", "How are my calories today?", "Protein today", "Calories today", "Nutrition today", "Macro compliance", "How much protein have I had?" → all `route_name='nutrition_query'`; "I had 8 oysters…", "I ate 2 eggs", "how many calories did I burn today", "log my protein for today", "what's left today", "other than nutrition, anything left?" → correctly NOT. +4 tests in `apps/ai/tests/test_nutrition_trust.py` (13/13 pass); pre-existing router failures identical on baseline. No model/schema/migration changes. Previous: Nutrition Beth-Trust Fix — "I had 8 oysters, how much protein?" returned a confident 0 cal / 0 protein while the dashboard showed 1418 cal / 136g. Three nutrition-only defects in the deterministic CoS path, fixed scope-controlled: (FIX 1 routing) `_match_nutrition_query()` in `apps/ai/deterministic_router.py` matched the `'how much protein'` substring INSIDE a food-estimate sentence, hijacking the terminal nutrition STATUS route before the log/estimate path could run — new `_is_food_estimate_query()` guard returns False (suppressing the status route) for consumption phrasing ("I had/ate X", "I just had a …") and `<macro> in/of <food>` estimates so they fall through to log_food/estimate; (FIX 2 grounding) `build_nutrition_state()` in `apps/core/ai_state/state_builder.py` computed "today" from the SERVER tz (`get_current_time().date()`) while the dashboard uses USER tz (`get_user_today`) — near midnight they disagree on which day's intake to show; now `today = get_user_today(user)` and `cutoff_7d` derives from it, so Beth and dashboard share one definition of "today"; (FIX 3 freshness+confidence) `_handle_nutrition_query()` read an unguarded SAE snapshot — now calls `ensure_fresh(user, ["nutrition"])` before reading (same pattern as the `dashboard_v3/services/composer.py` reader) AND refuses a confident "0 calories today" when the snapshot is contradictory (`cal==0` but `food_entries_today>0`) or suspicious (zero cal, no today-count, but weekly entries exist) → returns None / falls through rather than asserting a falsehood. Legitimate "nothing logged yet today" (`food_entries_today==0`) still answers truthfully. Hard invariant under test: after logging food, dashboard total == Beth/SAE total. 9 new tests in `apps/ai/tests/test_nutrition_trust.py`. EXPLICITLY DEFERRED (separate validated Phase B PR): promoting freshness into `get_module_state()` for ALL manual-entry modules — unknown blast radius; this PR's `ensure_fresh` is nutrition-scoped and reversible. No model/intent/schema/migration changes. Previous: Skip-Command Router Interception Fix — follow-up to the routine-skip work below: in production "skip shower" still didn't skip, returning `"No — just shower left."`. Root cause: `'skip '` is a `QUALIFIED_STATUS_PREFIXES` member in `apps/ai/deterministic_router.py` (built for "skip workout, am I done?"), and `is_qualified_status_query()` matched the prefix with no requirement of a status-question closer — so the bare imperative "skip shower" matched the terminal Phase 0a.1 qualified-status route in `classify_and_route`, which runs BEFORE intent recognition. `personal_assistant.send_message` set the response and never reached `handle_skip_routine`. NOT a check-in/end-of-day context issue (the check-in prefilter excludes qualified-status queries). Fix: `is_qualified_status_query` now requires a status closer (`?`, a yes/no status question, or a distinctive remaining-fragment) for the imperative-exclusion prefixes that collide with real commands (`_IMPERATIVE_COMMAND_PREFIXES` = skip/skipping/forget/ignore/leave out/take away). Prepositional prefixes (other than/besides) stay permissive. Net: "skip workout, am I done?" still answers the status question; "skip shower" falls through to intent recognition → skip_routine fires. New helpers `_has_status_closer` + `_STATUS_CLOSER_PHRASES`. 2 new router regression tests in `apps/ai/tests/test_skip_routine.py`. No model changes. Previous: Natural-Language Routine Skip + Skip-Honoring Check-ins — closes the "Beth acknowledged a skip but ignored it" trust gap. Two proven defects fixed: (#1) no NL path existed to skip a routine — `skip_task` is Task-only and the `skip_routine()` helper (`apps/life/services/routine_helpers.py`) was button-only (needed a `schedule_id`), so when the user said "I'm not showering today" the LLM improvised an acknowledgment with NO state mutation; (#2) `today_engine` ignored `RoutineLog.log_status='skipped'`, so even a button-skipped routine still surfaced in check-ins. Fix #1 — new `skip_routine` CoS intent registered across all 8 points: tool def `apps/ai/intents/life_intents.py`, handler map `apps/ai/intents/__init__.py`, `LIFE_INTENTS` set `intent_engine.py`, dispatcher elif `intent_service.py::execute_intent`, `ACTION_POLICY` entry `action_policy.py` (MUTATE/MEDIUM/CONFIRM), system-prompt examples + explicit SKIP-vs-DEFER boundary `intent_service.py::_build_intent_system_prompt`, `NON_TIME_INTENTS` `test_intent_registration.py`, and handler `apps/ai/action_handlers.py::handle_skip_routine`. The handler resolves today's matching `RoutineSchedule` (mirrors reschedule's applies_to_day/specific_date logic), returns honest `item_not_found`/`multiple_matches` when it cannot, calls the EXISTING deterministic `skip_routine()` helper, invalidates CoS cache + emits TASK_UPDATED — confirmation is returned ONLY after the mutation persists (capability-honesty: never "I'll skip it" without a real skipped RoutineLog). Fix #2 — `apps/core/today/today_engine.py::_collect_routine_items` now drops items whose `status=='skipped'` so they never appear in overdue/coming_up/later or inflate the day's total; completion truth/streaks read `RoutineLog` directly so adherence is unaffected. Blast radius verified: streaks/health/drift/compliance read RoutineLog (not today_engine buckets); morning_reconciliation already counts skipped as resolved; next-day reset is natural (RoutineLog is per scheduled_date). 8 new regression tests `apps/ai/tests/test_skip_routine.py` (NL skip writes skipped log + succeeds, unknown routine fails honestly, skipped hidden from check-in via NL + button paths, collector drops only skipped, tomorrow resets). No model changes, no migration. Previous: SAE Manual-Entry Freshness Guard — new `apps/core/ai_state/state_freshness.py :: ensure_fresh(user, modules)` closes the "stale mission signal" trust gap where a journal entry or nutrition log made minutes ago still showed `Journal → 0/wk` / `Nutrition → 0%` until the nightly rebuild. Root cause: the SAE snapshot (`UserState.state_data`) is updated by a fire-and-forget Celery `deferred_sae_refresh` whose sync fallback only triggers when `.delay()` *raises* (broker unreachable) — not when the worker is merely down/backed up, so the broker accepts the task and the snapshot silently lags. The guard is a request-path freshness check wired into `dashboard_v3/services/composer.py :: _read_mission_states()` BEFORE the `get_module_state` reads: for manual-entry modules ONLY (`_MANUAL_MODULE_SOURCES` registry — currently `journal`→JournalEntry, `nutrition`→FoodEntry, keyed by module with phased promotion lines for medicine/habits/checkins), it runs a cheap indexed `Model.objects.filter(user=user, updated_at__gt=UserState.last_updated).exists()` existence check and, only when stale, calls `update_user_state(user, module)` to rebuild that ONE signal via its builder, then clears any per-request `user._sae_cache`. Idempotent/self-healing (the rebuild bumps `last_updated` past the raw write so it won't re-fire) and resilient to Celery being down. Critically preserves `raw → signal → narrative`: it rebuilds the SIGNAL via the builder and reads the signal — it never reads raw rows into narrative logic. Heavy modules (health = ~69 queries, fitness) are deliberately EXCLUDED from the guard to honor the no-heavy-compute-on-request-path rule; they stay background-only. 6 new tests in `apps/core/ai_state/tests_state_freshness.py`; 69 MissionCardTests still pass. No model changes, no migration. Previous: Mission Framework Phase 2B + safe 2C foundation — Mission hero card: `_build_mission_card` (dashboard_v3 composer) now also returns `icon`, `title` (display, leading emoji stripped), `is_primary`, `progress`, and `why`. Icon via `_resolve_mission_icon()` — explicit `LifeGoal.mission_icon` metadata → user-typed leading emoji (`_LEADING_EMOJI_RE`, Unicode-codepoint only, NEVER word inference) → None. New `_build_mission_progress()` = deterministic milestone count (completed/total/filled 0–100) for the SVG hero ring; this is a literal count, NOT readiness. `templates/dashboard_v3/sections/mission.html` rebuilt as a premium hero card with a CSP-safe SVG ring (`pathLength`/`stroke-dasharray` presentation attributes, no inline JS/style); CSS in `static/dashboard_v3/css/dashboard_v3.css`. Safe 2C groundwork: `mission_icon` field (migration 0014, additive) + the `_build_mission_progress` primitive; readiness %, key drivers, watch items, and generated summaries remain DEFERRED and uncomputed (every visible claim must be explainable). NO change to selection, the shared selector, or CoS mission narration — dashboard mission == CoS mission still holds. Previous: Mission Framework Phase 2A — Primary Mission selection: mission selection is now EXPLICIT user intent. New `LifeGoal.is_primary_mission` BooleanField; `select_active_mission_goal()` returns `is_primary_mission=True AND status='active'` with NO derived fallback (removed the foundational/deadline/momentum ranking). One active Primary Mission per user, enforced at the app layer (`make_primary_mission()` atomic unset→set) and DB layer (partial `UniqueConstraint`). Toggle via `GoalPrimaryMissionToggleView` + "⭐ Make this my Primary Mission" control on goal_detail; flag is NOT in the create/edit form fields and NOT AI-settable (deliberate). When no Primary Mission is selected the dashboard card hides and the CoS stays silent (existing None-guards). Both dashboard_v3 composer and `build_goal_state()` consume the one selector → no divergence. Previous: Mission Framework Phase 1B — Beth Mission Awareness: new `apps/purpose/mission_selection.py :: select_active_mission_goal(user)` is the single source of truth for picking the headline foundational LifeGoal (active + foundational, ranked has-milestones → future date → long-horizon ≥90d → momentum score → id). Both the dashboard_v3 composer (`_build_mission_card`) and the SAE goal-state builder consume it, guaranteeing dashboard mission == Beth mission. `build_goal_state()` gains an additive `mission` key (title/current_focus/momentum_trend/days_remaining) composed deterministically from the shared selector; read-only — nightly `GoalMomentumSnapshot` only, no request-path compute. `_build_purpose_context()` passes the mission through and attaches a fixed-mapping `coach_line` via `_MISSION_COACH_LINE` (rising/stable/falling; None → omit), CONTEXTUAL tier — no readiness, no %, no completion language, NOT LLM-generated. No new engine, no MissionBriefing, no schema change. Tests: 3 new in TestGoalStateBuilder + 4 in new `apps/core/ai_orchestrator/tests/test_mission_context.py`. Previous: 2026-05-14 Action Center Chronological Timeline: new `build_chronological_timeline()` in `apps/core/decision_engine/action_prioritizer.py` is a thin wrapper over `build_grouped_action_center` that adds chronological sort, recovery annotations, and per-item emphasis metadata. Action Center becomes a daily execution timeline — time controls vertical ordering; urgency/foundationality/expiry/recovery surface as emphasis (color, ring, badge, dimming) via `_compute_emphasis()`. `RECOVERY_BANNER_COPY` is a deterministic table mapping `recovery_state.mode` to banner text + severity; no LLM in the path. `DashboardV2Service.get_execution_context` merges timeline data into `ac` alongside `phase_groups` so both rendering paths get full data. New partials: `_action_timeline_block.html` (one time block, chronological), `_action_recovery_banner.html` (NORMAL = no banner; RECOVERY/STABILIZE/SHUTDOWN show their canonical line). `templates/dashboard_v2/partials/action_center.html` branches on `ac.timeline_version == 'v2_chronological'` AND `feature_flags.WLJ_ACTION_CENTER_CHRONOLOGICAL`; legacy phase_groups path preserved behind the flag. New `feature_flags` context processor exposes `WLJ_ACTION_CENTER_CHRONOLOGICAL` to templates. Within-block item sort: effective_time, then foundational desc, then title. Cross-block sort: effective_time only (strict). 45 new tests; full focused sweep passes. Feature flag defaults True; legacy path removable after 30-day burn-in. X4 (reschedule visibility — original vs rescheduled time) is deferred. Previous: 2026-05-10 Narration Contract: new `apps/core/ai_orchestrator/narration_contract.py` defines four trust tiers — `canonical_item_truth`, `rollup_summary`, `advisory`, `contextual`. Every section appended in `format_cos_system_injection` (cos_context.py:5833+) carries an explicit `[TIER:...]` header; untagged sections default to `contextual` per the preamble. New DECISIONS section injected after locked facts as canonical_item_truth, carrying selector outputs from `build_execution_state` (next_action / biggest_risk / fix_priority / recovery_state / day_narrative). ACTION PRIORITIES now filters to `eligible_actions` (block-gated); far-future items moved to a new FORWARD SCHEDULE section tagged `contextual`. NEXT UP suppressed when target time is beyond `AT_RISK_HORIZON_MINUTES`. Medication narration collapsed to a single source (exec_summaries) with the dual `_fresh_module_state` rollup narration removed from the prompt — fresh state remains in context for entity grounding only. New `apps/ai/narration_contract_validator.py` performs soft post-response validation: detects "done / overdue / at risk / next action / fix first" claims and grades each by traceability to canonical_item_truth content. New `apps/core/ai_orchestrator/contradiction_telemetry.py` emits `ROLLUP_CONTRADICTION_WARNING` when domain rollup says DONE while a child item is still actionable, or when a medication window's all_taken disagrees with fresh per-dose state. New flag-gated `apps/ai/observability/chat_snapshot.py` writes a single JSON artifact per request to `LOG_DIR/chat_snapshots/<date>/<request_id>.json` (controlled by `WLJ_CHAT_SNAPSHOTS_ENABLED`). All three enforcement layers wired into `personal_assistant.send_message` post-response, after locked-facts truth validation. Architecture Laws bumped to 1.2 with Law 16 (Narration Contract). 36 new tests; full focused test sweep passes. No DB migrations. Previous: 2026-05-03 CoS Recovery Contract: deterministic task classification + recoverability + recovery-state machine + block-collapse selection gate. New modules `apps/core/execution/constants.py`, `apps/core/execution/task_classifier.py`, `apps/core/execution/recoverability.py`, `apps/core/execution/recovery_state.py`. `apps/core/execution/today_execution.py` annotates every ExecutionItem with `task_class ∈ {HARD_EXPIRED, WINDOWED, SOFT_EXPIRED, FLEXIBLE}`, `recovery_grace_minutes`, `is_reset_action` — additive, idempotent. WINDOWED hard cutoff = `min(scheduled + grace, next_anchor_block_start)` so morning anchors cannot drift into afternoon recommendations. `apps/core/decision_engine/action_prioritizer.py` adds three pure helpers consumed by `build_execution_state`: `compute_block_collapses` (strategy ∈ `recover_partially | skip | defer`; foundational AND reset levers stay alive in `recover_partially`); `compute_at_risk` (60–90 min standard horizon, 4 h only with dependency chain via `blocked_dependents`, suppressed entirely when overdue exists and no dependency); `apply_recovery_bucket_selection` (NORMAL pass-through; STABILIZE pushes reset first; RECOVERY orders reset → foundational overdue → quick win → rest; SHUTDOWN drops non-foundational overdue chatter). `prioritize_execution_items` filters non-recoverable items and collapse-suppressed source keys before ranking. `apps/core/execution/recovery_state.py :: compute_recovery_state` emits `{mode, day_narrative ∈ {on_track, behind_recoverable, behind_reset_required, day_lost_salvage, evening_closeout}, missed_foundational_count, recoverable_overdue_count, expired_count, recommended_strategy, reset_action_available}`; mode rules: SHUTDOWN at hour ≥ 20 with ≥ 3 unresolved; RECOVERY at hour ≥ 12 with ≥ 2 recoverable overdue; STABILIZE when ≥ 1 foundational missed AND a reset action is available; NORMAL otherwise. `apps/core/execution/execution_state.py` now exposes `eligible_actions` (active-block filtered subset for EXECUTION mode), `expired_items`, `deferred_items`, `collapsed_blocks`, `at_risk_actions`, `recovery_state`. Active-block gate moved upstream from selectors. `apps/core/execution/selectors.py` slimmed to pure picks: `get_next_action` reads `eligible_actions`, `get_biggest_risk` reads `at_risk_actions` with foundational-expired fall-through, `get_fix_priority` prefers reset / collapsed-block lever in RECOVERY/STABILIZE before existing unblock-count logic. No selector does priority computation, re-ranking, DB reads, or LLM calls. `apps/ai/cos_fact_statements.py :: build_recovery_brief` adds a 2–4 line "DAY MODE" hint to the locked-facts block ONLY when mode != NORMAL — keeps prompt lean in the common case. The classifier's `is_reset_action` flag is set ONLY by `activity_type` rules (`hydration`, `hygiene`, `movement`, `pause`, `faith`) or registry pin — title-token matching is forbidden. The classifier registry recognizes `event/service/appointment/meeting/class` as HARD_EXPIRED, `nutrition_anchor/weigh_in/measurement` as WINDOWED, supplements with `priority='optimization'` get 120 min grace, critical medications get 60 min, generic WINDOWED defaults to 90 min. Tests: 56 new tests in `apps/core/execution/tests/`; canonical 2:10 PM scenario asserts Church filtered, Protein Shake filtered, Shower kept via `recover_partially`, Fish Oil NOT at risk, RECOVERY/STABILIZE triggered post-noon, morning block collapsed. All 94 execution-layer tests pass. No DB migrations. Previous: 2026-04-28 Signal Rendering Framework — Phase 1: new `apps/core/signals/signal_renderer.py` is the single canonical interpretation layer that turns a `UnifiedSignal` into deterministic Label/Meaning/Action text via table lookup `SIGNAL_RENDER_MAP[(domain, type, severity)] → template`. NO LLM, NO branching per domain. Renderer must NOT depend on `signal.title` / `signal.message` — `normalize_signal()` strips them so producer-authored prose can never leak into user output. `LABEL_TAXONOMY = {Alert, Trend, Opportunity}` enforced; `Unclear`/`Mixed`/`Needs clarity` rejected. `DOMAIN_PRIORITY` maps health/medical→foundational, faith/meals/sleep→important, life/tasks→supporting. `select_top_signals(signals, max_n=2)` sorts by (priority, severity, confidence, recency); foundational always surfaces. `resolve_conflicts()` drops same-domain non-foundational signals when a foundational is present (e.g. glucose_high suppresses weight_loss_positive). `_TYPE_ALIAS` is a temporary translation layer so PIE/PRIE/PGE producers stay untouched in Phase 1; every alias use is logged. New endpoint `GET /api/signals/` exposes the renderer over HTTP. `apps/health/services/physical_decision.py` vitals branches now route through the renderer (legacy inline copy retained as fallback). `apps/ai/cos_fact_statements.py` summary builders + `apps/ai/beth_checkin_renderer.py` remain untouched — Phase 2/3 will lift them. Previous: 2026-04-26 CoS Strict Mode Isolation — three deterministic decision modes (Execution / Risk / Fix) now produce ONE line each with a strict format contract: `Next: X. Do this now.` / `Biggest risk: X. Fix this next.` / `Fix this first: X.`. No time math, no reason text, no follow-on, no commentary. `is_item_in_active_block` tightened so overdue items are Execution-eligible only if scheduled in the active block OR the immediately preceding canonical block — long-past items (e.g. 5:30 AM at noon) surface in Risk/Fix only. The locked-facts block sent to the LLM (`format_locked_facts_block`) is slimmed to JUST the next action line — no domain summaries, no overdue lists, no future items, no event acknowledgment — the LLM has nothing to blend. The richer `build_locked_facts()` dict remains available to the truth validator and other surfaces. The keyword router (`cos_mode_router.py`) now covers status queries (`how am I doing`, `where am I at`, `status`, `what's going on`, `update me`, `walk me through`, `where do I stand`, etc.) and defaults them to Execution; precedence is Fix > Risk > Execution. `beth_checkin_renderer.py` schedule guidance, escalation reasons, and directives use categorical phrasing only (`behind` / `at risk` / `upcoming` / `recoverable`) — no minute counts, no countdown language. Previous: 2026-04-26 Action Center: Time Block as Primary Execution Unit — every time-bound section in `_action_group.html` now renders one consistent parent control posting to `dashboard_v2:block_complete_toggle` (`actions/block/<block_key>/toggle/`). The new `BlockCompleteToggleAction` view in `apps/dashboard_v2/views.py` reads items from `build_today_execution(user)` (single source of truth), and either completes or undoes every item in the block. Intake optimization preserved: a block that is purely doses from one window delegates to the canonical `IntakeGroupLogAction` so the analytics rollup is a single window-level event. Mixed-domain blocks dispatch per item: `toggle_routine_completion` for routine items, `Task.mark_complete/mark_incomplete` for tasks, `IntakeLog` create/delete for individual doses (mirrors `IntakeLogAction`'s supply + event semantics). The homogeneity branch in `action_prioritizer.py :: build_grouped_action_center` is gone — result groups always use `group_type='time_block'`, with a new `intake_window_key` field exposed only when the block is purely one intake window (consumed by the new endpoint as an optimization hint). New public helper `time_block_key_for(time)` exported so endpoints match the Action Center's 15-minute rounding rule. Fixes the silent-skip bug where a block of 1 routine + 1 standalone task showed a routine checkbox that only completed the routine items. Existing per-domain endpoints (`routine_complete_toggle`, `intake_group_log`, `task_toggle`, `routine_schedule_toggle`, `intake_log`) untouched and reachable for non-Action-Center callers. Previous: 2026-04-26 CoS Decision Modes — Execution / Risk / Fix: new `apps/core/execution/execution_state.py :: build_execution_state(user, now)` composes Today Execution + active_block + prioritizer into a single state dict consumed by three deterministic selectors in `apps/core/execution/selectors.py` (`get_next_action`, `get_biggest_risk`, `get_fix_priority`). Mode resolution is keyword-based via `apps/ai/cos_mode_router.py` (NO LLM); `send_message()` shortcut + new `GET /assistant/api/cos/decision/?mode=...` endpoint expose the modes to chat and to iOS/future surfaces with identical structured payloads `{mode, primary_action, reason, follow_on, message}`. Risk-mode v1 deliberately omits "If ignored:" consequence text — no deterministic source. Fix-mode unblock counts derive from `dependency_gating.is_task_blocked` semantics via `state["blocked_dependents"]` (pre-computed in build_execution_state). `build_locked_next_action(user)` refactored to a thin wrapper over `get_next_action(state)`. Previous: 2026-04-26 CoS Time/Sequence Integrity — new `apps/core/execution/active_block.py` resolves the user's currently active execution block (morning / mid_morning / lunch / afternoon / evening / nightly) with per-user `scheduled_time` min/max as primary signal and `time_windows.WINDOW_HOURS` as static fallback; includes `LEAD_IN_MINUTES = 15` so the next block's earliest items become eligible only as the current block winds down. `build_locked_next_action()` in `apps/ai/cos_fact_statements.py` now restricts "Start with X" eligibility to `{overdue, now}` only — `next` (≤2h away) is referenced only as a follow-on hint, never as the primary recommendation — and applies the active-block gate so future-block items cannot override an unfinished current-block item even when foundational. `action_prioritizer.py` medicine groups now carry their `scheduled_time` as `time_display` (was empty string) so intra-tier sort orders intake correctly. Dashboard and CoS continue to share `prioritize_execution_items()`; with CoS restricted to overdue+now, both surfaces resolve the same primary action without a parallel engine. Regression test: at 07:55, with Measurements at 08:00 and Fish Oil at 09:00, "Start with Measurements" is mandatory. Previous: 2026-04-22 Phase 3 metric-trust — unified signal feed: new `apps/core/ai_signals/unified_feed.py` consolidates signals from PIE / PRIE / PGE / CDCE / cross-domain detector into a single `UnifiedSignal` shape with deterministic priority scoring, dedupe-key-first cluster collapse, source precedence (Guidance > Insight > Prediction > Cross-domain > Correlation > Drift), and bucket assignment into TOP / CRITICAL / POSITIVE lists. CoS context now exposes `top_signals`, `critical_signals`, `positive_signals`, and `signal_summary` keys; the adapter reuses the intelligence payload already loaded in `build_cos_context` (no extra DB queries). 21/21 new `SimpleTestCase` tests. Previous: 2026-04-21 Phase 2 metric-trust cleanup — CoS state-first hardening: added `goals.active_titles`, `goals.upcoming_titles`, `goals.overdue_titles`, and `habits.streaks_per_habit` to SAE state builders. Migrated 5 CoS raw reads (4 `LifeGoal`, 1 `HabitGoal`) to SAE. Replaced `FastingSession.objects.filter(...)` lookup with canonical `fasting.current_fast_active`. Added `log_state_gap()` observability hook; 3 `LabResult` reads now emit explicit `medical.recent_labs` / `medical.lab_test_counts` / `medical.lab_test_trends` state gap warnings instead of hiding the drift. New `apps/core/ai_orchestrator/cos_read_allowlist.py` enumerates every remaining direct ORM read in `cos_context.py` with classification (engine_output / self_state / continuity / reference_data / structured_lookup / gap_pending_state) and rationale. New `CosReadAllowlistTests` fails CI if an unlisted read appears or if counts diverge. Previous: 2026-04-20 Metric Access Layer: new `apps/core/ai_state/metric_access.py` + `metric_registry.py` as the single approved path for AI-facing metric reads. 10 `PersonalDataService.get_*_data()` methods migrated to read canonical SAE state instead of re-aggregating raw models — glucose/weight/sleep/food/steps/water/workout/journal/mood/medication. 12 methods deprecated to stubs returning None. In `cos_context.py`, the `_build_data_state_snapshot` lifetime-count block no longer issues 8 raw `.count()` queries; presence is derived from SAE signals. Medication adherence state now reads `health.medication_status`. `log_direct_orm_read()` telemetry added at 10 remaining direct-ORM read sites for Phase 2 cleanup. Purity-ratcheting test in `tests_metric_access.py` enforces zero aggregations in migrated files and blocks regressions elsewhere. Previous: 2026-04-15 Execution Escalation Engine: 4-level deterministic escalation in beth_checkin_renderer.py, trivial completion rule, duration estimate fixes, nudge state, move_later gating. Earlier: 2026-04-07 Workout-Tomorrow Hardening: workout event adapter is now date-aware — past/today → `WorkoutSession`, future → `WorkoutSchedule`; deterministic empty-state contract in `handle_query_event_history` structurally bypasses the LLM for empty/future queries via `ar.message` direct return; new generic `_is_future_tense_query` gate applied to every per-domain summary matcher in `deterministic_router.py` — generalizes future-tense protection across all domains. Earlier the same day: CDCE domain gating added to `detect_fasting_fitness` + `build_fasting_state`; `workout_consistency_score` now uses canonical schedule-based adherence; data migration 0123 purges stale fasting_fitness correlations for users with fasting disabled.)

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
| **ETE** Execution Truth | `apps/core/execution/` | `get_execution_truth()` | Request | Single source of truth for expected vs completed. Cross-domain bridges. |
| **Today Engine** | `apps/core/today/` | `build_today()` | Request | Day aggregation: routines + tasks + calendar + meds into time-bucketed dataset. |

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
| **Compliance Engine** | `apps/dashboard_v2/compliance/service.py` | `compute_compliance()` | Post-execution + nightly | N/A | Execution compliance tracking across 6 domains with reconciliation. | `ComplianceEvent` model |
| **Signal V3** | `apps/core/signals/signal_engine.py` | `detect_signals()` | Post-execution + ISE | N/A | Behavioral signal detection, health signals, execution signals, adaptive presentation. | Signal models |

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
| **Purpose** (Phase 7.3) | `_build_purpose_context()` | LifeGoal, HabitGoal, HabitEntry, SAE `goals.mission` | active goals with deadlines, habit weekly completion rates, **mission block** (title/current_focus/days_remaining/momentum_trend + deterministic `coach_line`). Mission is pass-through of SAE `goals.mission` composed in `build_goal_state()`; selection via shared `apps/purpose/mission_selection.py :: select_active_mission_goal()` = **explicit** `is_primary_mission=True AND status='active'` (Phase 2A — no derived fallback; same selector dashboard_v3 uses → no divergence). One active Primary Mission per user (DB partial unique constraint). Coach lines are a fixed `_MISSION_COACH_LINE` mapping (rising/stable/falling), CONTEXTUAL tier, no readiness/%. **Dashboard hero card (Phase 2B)** adds presentation-only fields to `_build_mission_card` (icon via `mission_icon` metadata/leading-emoji, deterministic milestone-progression ring, `why_it_matters` excerpt) — no new truth, CoS narration unchanged. |
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

### Metric Access Layer (2026-04-20)

`apps/core/ai_state/metric_access.py` is the single approved entry point for **AI-facing** metric reads. It is a thin facade over `get_state_value()` — it does not compute, aggregate, cache, or fall back.

```
AI-facing caller
  └─> get_metric(user, "health.glucose_avg_7d")
        ├─> METRIC_REGISTRY lookup  → unregistered ⇒ log warning, return None
        └─> get_state_value(user, state_path)
              └─> SAE state  → absent ⇒ log "orphan" info, return None
                             → present ⇒ return MetricResult(value, source, domain, window, unit)
```

**Rules enforced by `apps/core/ai_state/tests_metric_access.py`:**
- `PURITY_ENFORCED_FILES` (currently `assistant/data_service.py`, `apps/core/ai_orchestrator/cos_context.py`) must contain zero `.aggregate()`, `.annotate()`, or bare `.count()` calls.
- `PURITY_BASELINE` files (20 existing AI-facing modules with known Phase 2 debt) may not regress above their current violation count.
- Any new AI-facing file with raw aggregation fails CI.
- Every key in `METRIC_REGISTRY` must be written by some `state["<key>"] = ...` line in `state_builder.py`.

**Observability hooks** (`logger.warning` / `logger.info` with `metric_access: True`):
- `metric_access.unregistered_key` — caller asked for a key not in the registry.
- `metric_access.orphan` — key is registered but SAE has not populated it yet.
- `metric_access.divergence` — same metric key emitted with conflicting values in one turn.
- `metric_access.direct_orm_read` — AI-facing code still reads a model directly (Phase 2 migration target).
- `personal_data_service.deprecated_call` — one of the 12 deprecated `get_*_data` methods was called.

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
| `journal` | `build_journal_state()` | last_entry, entry_frequency, mood_distribution, **entries_7d** (journaling-activity count — EVERY entry in last 7d, NOT mood-gated; consumed by mission card / CoS / cockpit), moods_7d/mood_trend (mood-filtered, trend only) |
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

### BUG 0: CDCE Surfaces False Fasting/Workout Correlation for Disabled Domain — FIXED (2026-04-07)

**Severity:** High — CoS told a user "Both fasting (0%) and workout consistency (43%) have dropped" when fasting was not enabled and workout adherence was actually high. False insights are worse than no insights.

**Root cause:** Two colluding bugs.
1. `apps/core/ai_state/state_builder.py::build_fasting_state()` ran for every user regardless of preferences and skipped writing `fasting_compliance_score` when `fasts_7d == 0`. `apps/core/ai_cross_domain/cdce_engine.py::detect_fasting_fitness()` then read it back with `.get('fasting_compliance_score', 0)` — silently defaulting "no data" to "0% adherence" — and emitted a correlation against an inactive domain. The CoS context filter at `cos_context.py:1343-1346` only gates by parent module ("health"), so a disabled sub-feature like fasting still leaked through.
2. `build_fitness_state()` computed `workout_consistency_score` as `workouts_7d ÷ (workouts_30d ÷ 4)`, which under-reports highly adherent users whose 30d window is depressed by a vacation/rest week. The canonical `workout_adherence_score` (schedule-based, from `calculate_workout_behavior_output`) was already set in state but ignored.

**Fix:**
- `build_fasting_state()` returns `{"enabled": False}` (no other keys) when `health_features['fasting']` is off OR `default_fasting_type == 'none'`. When enabled with no fasts, `fasting_compliance_score` is now explicit `None` (sentinel), never absent or 0.
- `detect_fasting_fitness()` short-circuits if `fasting.enabled` is False or if either compliance/consistency score is `None`. Both `fasts_7d` and `workouts_7d` must be > 0 to emit a correlation.
- `build_fitness_state()` now sets `workout_consistency_score = workout_adherence_score` when available (per CLAUDE.md "calculation reuse rule"). The trailing-30d ratio is only used as a fallback when no active workout plan exists. Score is `None`, never 0, when neither source has data.
- Data migration `apps/core/migrations/0123_purge_stale_fasting_correlations.py` deletes existing `fasting_fitness` `DomainCorrelation` rows for users with fasting disabled.
- Regression suite `apps/core/ai_cross_domain/tests.py::FastingFitnessGatingTests` (7 tests) covers all four gating paths.

**Watch-list:** The `signals.get(key, 0)` anti-pattern that caused this lives in other CDCE detectors too — same audit recommended for `detect_nutrition_energy`, `detect_habit_goal_alignment`, etc., before adding new domains.

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

### OPEN: Signal Models Without Migrations

**Severity:** Medium — `apps/core/signals/models.py` defines `SignalFeedback` and `ExecutionSignal` but `apps/core/signals/` is not in INSTALLED_APPS and has no migrations directory. DB persistence of these models may not be operational.

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
| `apps/ai/beth_checkin_renderer.py` | Deterministic check-in renderer (morning/midday/evening briefings, schedule drift, execution escalation engine, trivial completion) | ~2000+ |
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
| `apps/core/ai_state/metric_access.py` | Metric Access Layer — approved entry point for AI-facing metric reads |
| `apps/core/ai_state/metric_registry.py` | Canonical metric key registry (domain + window + SAE state path) |
| `apps/core/ai_state/tests_metric_access.py` | Metric-access unit tests + purity/orphan/allowlist CI gates |
| `apps/core/ai_orchestrator/cos_read_allowlist.py` | CoS direct-ORM-read allowlist (Phase 2: state-first CoS) |
| `apps/core/ai_signals/unified_feed.py` | Phase 3: UnifiedSignal adapter — PIE/PRIE/PGE/CDCE/cross-domain consolidation, dedupe, priority scoring, TOP/CRITICAL/POSITIVE bucketing |
| `apps/core/ai_signals/tests_unified_feed.py` | Phase 3 unified feed tests |
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

### Execution Truth & Today

| File | Purpose |
|------|---------|
| `apps/core/execution/execution_truth_engine.py` | Completion authority |
| `apps/core/execution/expected_map.py` | Signal bridge |
| `apps/core/execution/today_execution.py` | Dashboard V2 execution items |
| `apps/core/signals/signal_renderer.py` | **Phase 1 Signal Rendering Framework** — canonical interpretation layer. Table-driven `(domain, type, severity) → template` dispatch. Exports `render_signal`, `normalize_signal`, `select_top_signals`, `resolve_conflicts`. Consumed by Physical Intelligence + `/api/signals/`. |
| `apps/core/decision_engine/action_prioritizer.py` | Action prioritizer + `build_grouped_action_center` (Action Center grouping; every time block uses `group_type='time_block'`). Exports `time_block_key_for(time)` helper. |
| `apps/dashboard_v2/views.py :: BlockCompleteToggleAction` | Block-level completion endpoint — one parent control per time block, dispatches to per-item handlers, preserves intake-window rollup. URL: `dashboard_v2:block_complete_toggle`. |
| `apps/core/execution/active_block.py` | Active execution block resolver — gates "Start with X" eligibility for CoS / Today Engine. Per-user `scheduled_time` min/max with `time_windows.WINDOW_HOURS` fallback; 15-minute lead-in to next block. |
| `apps/core/execution/execution_state.py` | `build_execution_state(user, now)` — single composed state dict consumed by all three CoS decision-mode selectors (no parallel engines). |
| `apps/core/execution/selectors.py` | Three pure CoS decision-mode selectors: `get_next_action` (execution), `get_biggest_risk` (risk), `get_fix_priority` (fix). Same state input, three distinct outputs. NO LLM, NO DB. |
| `apps/ai/cos_mode_router.py` | Keyword-based deterministic mode resolver. Routes user messages to "execution" / "risk" / "fix" or None. NO LLM. |
| `apps/core/today/today_engine.py` | Day aggregation |

### Compliance

| File | Purpose |
|------|---------|
| `apps/dashboard_v2/compliance/service.py` | Compliance pipeline |
| `apps/dashboard_v2/compliance/models.py` | ComplianceEvent model |
| `apps/dashboard_v2/compliance/adapters/` | 6 domain adapters |

### Signals V3

| File | Purpose |
|------|---------|
| `apps/core/signals/signal_engine.py` | Behavioral detection |
| `apps/core/signals/health_signals.py` | Deterministic health signals |
| `apps/core/signals/execution_signals.py` | Django signal handlers |
| `apps/core/signals/signal_presenter.py` | Dashboard presentation |

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
