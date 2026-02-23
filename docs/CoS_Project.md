# WLJ CoS Executive Upgrade Project

**Created:** 2026-02-23
**Objective:** Upgrade CoS from "strong deterministic system" to "executive-grade operational intelligence system"
**Source:** External audit findings against the CoS Full System Picture Report

---

## Current Phase

**Phase 4 — Forecasting & Pressure Modeling** ✅ COMPLETE (2026-02-23)

---

## Phase Status Table

| Phase | Title | Tier | Status | Started | Completed | Notes |
|-------|-------|------|--------|---------|-----------|-------|
| 1 | Commitment System Hardening | T1 — Critical Structural Integrity | ✅ Complete | 2026-02-23 | 2026-02-23 | Persistent model, history, concurrency, false-positive mitigation |
| 2 | Time & Deadline Authority Reinforcement | T2 — Executive-Quality Reliability | ✅ Complete | 2026-02-23 | 2026-02-23 | Explicit boundaries, DST, deadline surfacing, conflict detection |
| 3 | Drift & Escalation Continuity | T2 — Executive-Quality Reliability | ✅ Complete | 2026-02-23 | 2026-02-23 | Persistent escalation, decay model, downgrade prevention |
| 4 | Forecasting & Pressure Modeling | T3 — Forward-Looking Intelligence | ✅ Complete | 2026-02-23 | 2026-02-23 | Calendar density, pressure index, deadline collision, CPI 0–100, event-driven triggers |
| 5 | Protective Action Engine | T4 — Proactive Protection | ✅ Complete | 2026-02-23 | 2026-02-23 | Advisory-only recs, capacity warnings, pre-deadline alerts, overload triggers, DNE delivery, audit trail |
| 6 | Observability & Concurrency Hardening | T5 — Observability & Concurrency | Not Started | — | — | Locks, atomicity, degraded-mode tests |
| 7 | Test Expansion | T6 — Testing & Verification | Not Started | — | — | DST, concurrency, stacking, forecasting, cache failure tests |

---

## Detailed Phase Breakdown

---

### Phase 1 — Commitment System Hardening

**Tier:** T1 — Critical Structural Integrity
**Priority:** Highest — this is the foundation all other phases build on

#### Objective

Convert the ECC commitment system from runtime-only conversation metadata into a persistent, auditable, concurrency-safe database model with historical tracking, cross-session continuity, and analytics foundation.

#### Why It Matters

The audit identified that commitments today are:
- **Runtime-only** — stored in `AssistantConversation.metadata['ecc_active_commitment']` as a JSON dict
- **Lost on new conversation** — user cannot query "What did I commit to yesterday?"
- **No historical tracking** — no aggregate patterns, no long-term accountability trends
- **No concurrency protection** — rapid double-submit can read stale commitment state
- **False-positive prone** — "I'll have pizza" triggers commitment detection via substring "I'll"
- **Single-commitment only** — no stacking support for "I'll do X and then Y"

An executive-grade system must have durable, auditable commitment records with concurrency-safe mutation.

#### Scope Boundaries

- **IN SCOPE:** New `Commitment` model, migration from metadata to DB, renegotiation history, concurrency locking, false-positive mitigation, multi-commitment support, analytics foundation
- **OUT OF SCOPE:** UI for commitment history (Phase 5 or later), AI-driven commitment suggestions, integration with external calendars

#### Atomic Tasks

| # | Task | Description |
|---|------|-------------|
| 1.1 | Create `Commitment` database model | New model in `apps/core/ai_orchestrator/models.py` with fields: `user` (FK, required — commitments are user-global), `conversation` (FK, nullable — optional traceability only, not ownership), `normalized_text`, `commitment_type` (DO/DECIDE/SCHEDULE/STOP), `time_boundary` (DateTimeField), `time_boundary_display`, `done_definition` (nullable — only required for vague actions), `status` (pending/closed_success/closed_missed/cancelled/renegotiated), `created_at`, `closed_at`, `closure_type`, `session_id` (for cross-session tracking). Commitments belong to the user, not to a conversation. Closure allowed from any conversation. Add `select_for_update()` pattern for mutation. |
| 1.2 | Create `CommitmentRenegotiation` model | Track renegotiation history: `commitment` (FK), `original_time_boundary`, `requested_time_boundary`, `tier_at_time`, `was_blocked`, `blocked_choice_selected` (A/B), `created_at`. Replaces ephemeral renegotiation handling. |
| 1.3 | Create `CommitmentAnalytics` materialized view/model | Daily rollup: `user`, `date`, `commitments_made`, `commitments_honored`, `commitments_missed`, `commitments_renegotiated`, `honor_rate`, `avg_time_to_closure`. Foundation for future dashboards. |
| 1.4 | Migrate ECC runtime to persistent model | Update `commitment_contract.py` to write/read from DB model instead of `conversation.metadata`. Maintain backward compatibility: if metadata commitment exists, migrate it to DB on first access. Keep `conversation.metadata` as a cache/pointer only (stores commitment PK, not full dict). |
| 1.5 | Add concurrency-safe locking | Wrap commitment mutation (create, renegotiate, close) in `transaction.atomic()` with `select_for_update()` on the commitment row. Prevent stale-read on rapid double-submit. |
| 1.6 | Add cross-session commitment continuity | On conversation start, query `Commitment.objects.filter(user=user, status='pending')` to surface unclosed commitments. Inject into system prompt via `format_ecc_injection()`. User can close commitments from any conversation. |
| 1.7 | False-positive mitigation | Add context-aware filtering to `detect_commitment_intent()`: skip trigger if followed by food/casual words (configurable exclusion list). E.g., "I'll have pizza" → no commitment. "I'll have the report done" → commitment. Pattern: trigger + exclusion check before extraction. **Commitment activation rules:** Time boundary is ALWAYS required. Done-definition required ONLY when action contains vague verbs. Initial vague verb list: `["work on", "review", "start", "progress", "handle", "deal with", "improve", "figure out"]`. Simple atomic verbs (call, send, submit, pay, schedule, log) do NOT require done-definition. |
| 1.8 | Multi-commitment stacking | Allow multiple pending commitments per user (currently max 1 via metadata). ECC detection creates new commitment without closing existing ones. Tightening questions apply per-commitment. Closure rules: if exactly 1 pending → "Done." closes it automatically. If >1 pending → system must list commitments numerically and require explicit numeric selection. No heuristic selection allowed. No auto-closure of most recent. |
| 1.9 | Update pipeline integration | Update `personal_assistant.py` `send_message()` to use DB-backed commitments. Update `format_ecc_injection()` to handle multiple commitments. Update closure logic to handle commitment selection. Preserve hard short-circuit sentinel pattern. |
| 1.10 | Write migration | `makemigrations` for new models. Test migration forward and backward. |
| 1.11 | Write tests | Unit tests: model creation, renegotiation logging, analytics rollup, concurrency locking, false-positive filtering, multi-commitment stacking, hard limit enforcement, idempotency protection. Integration tests: pipeline with DB-backed commitments, cross-session continuity, migration from metadata. |
| 1.12 | Enforce hard commitment limit | Limit active pending commitments to MAX 5 per user. If user attempts to create a 6th, deterministically block with message: "You have 5 active commitments. Close or cancel one before creating another." No override allowed. No admin bypass. Checked in `process_ecc_detection()` before field extraction. |
| 1.13 | Add backend idempotency protection | Implement 3-second idempotency window using SHA256 hash of `(user_id + normalized_message + timestamp_rounded_to_second)`. If duplicate detected within window, bypass pipeline and return original response. Log `DecisionRecord` type `IDEMPOTENT_REPLAY`. Prevents double-submit from creating duplicate commitments or actions. |

#### Files Touched

| File | Change Type |
|------|-------------|
| `apps/core/blueprint/models.py` | Added Commitment, CommitmentRenegotiation, CommitmentAnalytics models (core app, not ai_orchestrator) |
| `apps/core/ai_orchestrator/commitment_contract.py` | Major refactor — DB-backed operations, false-positive filtering, multi-commitment |
| `apps/ai/personal_assistant.py` | Moderate — DB reads/writes instead of metadata, multi-commitment closure |
| `apps/ai/models.py` | Minor — metadata now stores commitment PK pointer only |
| `apps/core/ai_orchestrator/cos_context.py` | Minor — `format_ecc_injection()` handles multiple commitments |
| `apps/core/tests/test_phase5_commitment.py` | Major expansion — new test classes |
| `apps/core/tests/test_phase5_commitment_pipeline.py` | Major expansion — DB integration tests |

#### Safety Invariants

1. **Closure precedence preserved** — Phase 5C hard short-circuit unchanged
2. **Deterministic detection unchanged** — Substring matching, no LLM inference
3. **Tightening question flow unchanged** — One missing field at a time
4. **Renegotiation blocking unchanged** — EARLY_EROSION/STRUCTURAL_DRIFT still block
5. **Pipeline ordering preserved** — ECC before intent recognition
6. **Backward compatibility** — Existing metadata commitments migrate gracefully

#### Test Requirements

- Commitment CRUD with all status transitions
- `select_for_update()` under concurrent access (simulated with threading)
- Cross-session commitment surfacing
- False-positive exclusion list (food, casual phrases)
- Multi-commitment creation, individual closure, bulk closure
- Renegotiation history recording and retrieval
- Analytics rollup accuracy
- Migration from metadata to DB (existing conversations)
- Pipeline integration with DB-backed commitments
- Hard short-circuit still works with DB errors

#### Rollback Plan

Models are additive. If Phase 1 fails:
1. Drop new migration (reverse migrate)
2. Revert `commitment_contract.py` to metadata-based
3. Revert `personal_assistant.py` pipeline changes
4. No data loss — existing metadata commitments untouched

---

### Phase 2 — Time & Deadline Authority Reinforcement

**Tier:** T2 — Executive-Quality Reliability

#### Objective

Establish authoritative, deterministic time handling and proactive deadline surfacing by eliminating silent defaults, enforcing explicit time boundaries, adding DST safety, implementing local-intent timezone recalculation, and introducing ISE-driven deadline snapshots.

#### Why It Matters

The audit identified:
- **Silent all-day default** — When no time specified, `_parse_time_boundary()` defaults to 23:59 (silent assumption)
- **No DST testing** — Spring/fall transitions could cause 1-hour scheduling errors
- **`datetime.now()` usage** — `_handle_clean_renegotiation()` uses naive `datetime.now()` instead of `system_clock.get_current_time()`
- **No deadline surfacing** — User has no proactive view of what's due in 24h/72h/7d
- **No conflict detection hardening** — Protected blocks can overlap without warning

#### Scope Boundaries

- **IN SCOPE:** Explicit time boundary requirement, DST tests, `datetime.now()` fix, deadline surfacing engine, protected-block conflict detection
- **OUT OF SCOPE:** Calendar UI redesign, recurring event DST handling (separate concern), timezone migration for existing events

#### Atomic Tasks

| # | Task | Description |
|---|------|-------------|
| 2.1 | Enforce explicit time boundary | Silent end-of-day (23:59) default is removed. `_parse_time_boundary()` must return `MissingField("time_boundary")` when time is not explicitly specified. `ALLOW_END_OF_DAY_DEFAULT = False` hardcoded. No fallback to 23:59. Tightening question required. |
| 2.2 | Time authority audit | Audit entire CoS codebase for: `datetime.now()`, `timezone.now()`, naive datetime creation. Replace all time access with `get_current_local_datetime(user)` or `system_clock.get_current_time()`. Confirm single time authority invariant. |
| 2.3 | DST handling determinism | Use `zoneinfo` (not `pytz`). Spring-forward gap: move to next valid time. Fall-back fold: always select first occurrence (`fold=0`). Deterministic behavior only. No prompting user for DST ambiguity. |
| 2.4 | Timezone change behavior (local-intent preservation) | Timezone Change Model = Local-Intent Preservation. When user timezone changes, for all `Commitment` where `status='pending'`: preserve original wall-clock time, recalculate UTC value using new timezone, use stored `timezone_at_creation`, add field `timezone_at_last_recalculation`, log timezone recalculation event. Do NOT prompt user. Do NOT preserve absolute UTC. Completed commitments unaffected. |
| 2.5 | Deadline surfacing engine (ISE-driven) | Deadline surfacing is ISE-driven only. Create `DeadlineSnapshot` model: `user`, `due_24h`, `due_72h`, `due_7d`, `collision_flags`, `computed_at`. ISE runs every 5 minutes. Only executes if: pending commitments OR future goal deadlines OR scheduled blocks in next 7 days. `build_cos_context()` reads latest snapshot. If snapshot >10 minutes old: raise SAME anomaly `STALE_DEADLINE_SNAPSHOT`. No deadline computation inside `send_message()`. |
| 2.6 | Protected block conflict enforcement (graduated resistance) | Tier 1 Conflict Model = Graduated Resistance. When scheduling overlaps Tier 1 block: (1) First attempt — hard block, explain conflict, reference user's Tier 1 designation, offer alternatives. (2) Explicit override required — only allow if user states deterministic override phrase "Override Tier 1 protection". (3) On override — create `Tier1OverrideEvent`, log: `user`, `original_block_id`, `conflicting_block_id`, `timestamp`, `escalation_level_at_time`, `density_score_at_time`. Feed into drift and pressure modeling. Tier 2 & Tier 3: warn but allow without override phrase. |
| 2.7 | Write tests | Spring-forward gap handling. Fall-back fold handling. Timezone change recalculation accuracy. Deadline snapshot accuracy. Snapshot staleness anomaly. Tier 1 graduated override logic. Override logging correctness. |

#### Files Touched

| File | Change Type |
|------|-------------|
| `apps/core/ai_orchestrator/commitment_contract.py` | Moderate — time boundary enforcement, DST handling |
| `apps/core/ai_orchestrator/cos_context.py` | Moderate — deadline surfacing, conflict injection |
| `apps/core/blueprint/architecture_engine.py` | Minor — conflict detection hardening |
| `apps/core/time/resolver.py` | Minor — DST-aware resolution |
| `apps/core/ai_orchestrator/models.py` | Minor — `timezone_at_creation` field |
| `apps/core/tests/test_phase5_commitment.py` | Expansion — time boundary tests |
| New: `apps/core/tests/test_dst_transitions.py` | New — DST-specific test suite |
| New: `apps/core/tests/test_deadline_surfacing.py` | New — deadline engine tests |

#### Safety Invariants

1. **Single time authority preserved** — All paths use `get_current_local_datetime(user)` or `system_clock.get_current_time()`
2. **No silent defaults for critical time parameters**
3. **Timezone changes preserve local wall-clock intent** — completed commitments unaffected
4. **Deadline computation never inside `send_message()`** — ISE-driven only via `DeadlineSnapshot`
5. **Tier 1 protected blocks require explicit override phrase** — graduated resistance, not silent override

#### Test Requirements

- Spring-forward gap handling
- Fall-back fold handling
- Timezone change recalculation accuracy
- Deadline snapshot accuracy
- Snapshot staleness anomaly (`STALE_DEADLINE_SNAPSHOT`)
- Tier 1 graduated override logic
- Override logging correctness
- Explicit time enforcement: "today" without time → tightening question

#### Rollback Plan

All changes are backward-compatible. DST handling and deadline surfacing are additive. The explicit time boundary enforcement is hardcoded (`ALLOW_END_OF_DAY_DEFAULT = False`) but can be reverted. `DeadlineSnapshot` model is additive. `Tier1OverrideEvent` model is additive.

---

### Phase 3 — Drift & Escalation Continuity

**Tier:** T2 — Executive-Quality Reliability

#### Objective

Make escalation state and enforcement level persistent across sessions, add a drift recovery decay model, prevent premature tier downgrade from single positive inputs, and track behavioral trends longitudinally.

#### Why It Matters

The audit identified:
- **Escalation has no memory** — Level 3 enforcement doesn't carry to next conversation
- **Tier is per-request** — A single positive message can drop STRUCTURAL_DRIFT to CLEAN if thresholds aren't met at that exact moment
- **No drift recovery model** — No concept of "sustained recovery" vs "one good day"
- **No trend persistence** — System can't differentiate improving vs degrading trajectory over time

#### Scope Boundaries

- **IN SCOPE:** Persistent escalation state, decay model, downgrade protection, trend tracking
- **OUT OF SCOPE:** Drift UI redesign, new drift types, changes to drift scoring formula

#### Atomic Tasks

| # | Task | Description |
|---|------|-------------|
| 3.1 | Create `EscalationState` model | Persistent per-user escalation tracking: `user` (FK), `current_level` (0-4), `peak_level_7d`, `last_escalation_at`, `last_de_escalation_at`, `consecutive_clean_days`, `metadata` (JSON). Updated on every `determine_activation_state()` call. |
| 3.2 | Persist escalation history | Create `EscalationEvent` model: `user`, `from_level`, `to_level`, `trigger`, `timestamp`, `behavior_key`. Records every level change for audit trail. |
| 3.3 | Cross-session enforcement memory | `determine_activation_state()` now reads `EscalationState` as a floor. If `peak_level_7d >= 2`, minimum activation is `EARLY_EROSION` regardless of current threshold computation. Decays over time (see 3.4). |
| 3.4 | Drift recovery decay model (Hybrid Recovery Rule) | To downgrade one escalation level, ALL of the following must be met: (1) 7 consecutive clean days, (2) ≥3 honored commitments in that window, (3) 0 Tier 1 misses, (4) 0 blocked renegotiations, (5) no new drift threshold events. Escalation can increase immediately. Downgrade requires sustained proof. Evaluated daily via `EscalationState` model. |
| 3.5 | Prevent CLEAN downgrade from single positive input | In `determine_activation_state()`: if current computed state is CLEAN but `EscalationState.current_level > 0` and Hybrid Recovery Rule criteria not met, maintain at EARLY_EROSION minimum. Only downgrade to CLEAN after all 5 recovery criteria are satisfied. |
| 3.6 | Trend persistence tracking | Create `BehavioralTrend` model: `user`, `behavior_key`, `trend_direction` (improving/stable/declining), `confidence`, `data_points`, `window_start`, `window_end`, `updated_at`. Computed daily from drift events and completion patterns. Injected into trajectory signals. |
| 3.7 | Update `determine_activation_state()` | Integrate `EscalationState` floor, recovery score check, and `BehavioralTrend` into activation computation. Maintain threshold-based override semantic (thresholds still trump everything). |
| 3.8 | Write tests | Escalation persistence across sessions, decay model progression, downgrade prevention, trend computation, threshold override still works. |

#### Files Touched

| File | Change Type |
|------|-------------|
| `apps/core/blueprint/models.py` | New models — EscalationState, EscalationEvent, BehavioralTrend |
| `apps/core/ai_orchestrator/cos_context.py` | Moderate — activation state with persistence and decay |
| `apps/core/blueprint/drift_engine.py` | Minor — trend computation integration |
| `apps/core/tests/test_phase4_cos.py` | Major expansion — escalation continuity tests |
| New: `apps/core/tests/test_escalation_continuity.py` | New — dedicated escalation test suite |

#### Safety Invariants

1. **Threshold-based overrides still supreme** — Numeric thresholds (≥3 renegotiations, ≥2 T1 skips) always trigger STRUCTURAL_DRIFT regardless of recovery score
2. **Escalation can only go up immediately, down slowly** — Asymmetric by design
3. **No new drift types introduced**
4. **Existing DriftScore/DriftEvent models unchanged**
5. **Pipeline ordering preserved**

#### Test Requirements

- Escalation from Level 0 → 3 persists across new conversation
- Hybrid Recovery Rule: all 5 criteria met → downgrade allowed
- Hybrid Recovery Rule: any 1 criterion unmet → downgrade blocked
- STRUCTURAL_DRIFT → CLEAN requires 7 clean days + 3 honored commitments + 0 T1 misses + 0 blocked renegotiations + 0 new drift events
- Single positive message does NOT downgrade if recovery criteria unmet
- Threshold override still triggers STRUCTURAL_DRIFT regardless of recovery
- Behavioral trend computation accuracy

#### Rollback Plan

New models are additive. If `determine_activation_state()` changes cause issues:
1. Remove `EscalationState` floor check (feature flag or code revert)
2. System reverts to per-request computation (current behavior)
3. No data loss — drift events and scores unchanged

---

### Phase 4 — Forecasting & Pressure Modeling

**Tier:** T3 — Forward-Looking Intelligence

#### Objective

Build a comprehensive forecasting layer that computes calendar density, workload compression, habit protection breach probability, goal trajectory erosion, deadline collision risk, and a composite "pressure index" score.

#### Why It Matters

The current system has:
- **Weekly pressure engine** — but only 7-day capacity load, no granular scoring
- **Drift probability** — but heuristic-only, no calendar-aware modeling
- **No deadline collision detection** — overlapping deadlines not surfaced
- **No composite pressure score** — no single metric for "how overloaded is this person"

An executive-grade system must model future pressure and surface it proactively.

#### Scope Boundaries

- **IN SCOPE:** Density scoring, compression modeling, breach prediction, erosion detection, collision modeling, pressure index
- **OUT OF SCOPE:** ML-based prediction models, external calendar integration, UI for pressure visualization (future phase)

#### Atomic Tasks

| # | Task | Description |
|---|------|-------------|
| 4.1 | Calendar density scoring | New function `compute_calendar_density(user, date_range)`: for each day in range, compute ratio of scheduled time to available time (7 AM–10 PM). Score 0.0–1.0. Flag days > 0.8 as "overloaded". Store in new `PressureSnapshot` model. |
| 4.2 | Workload compression modeling | Detect when flexible tasks are being squeezed: if available_time < sum(flexible_block_durations) × 1.2, flag as "compressed". Model compression trajectory over 7 days. |
| 4.3 | Habit protection breach prediction | For each protected habit block (non-negotiables), compute probability of breach based on: surrounding density, historical breach rate for similar density, day-of-week pattern. Output: per-block breach probability (0.0–1.0). |
| 4.4 | Goal trajectory erosion detection | For each active goal with a deadline, compute: days_remaining, progress_rate_needed vs actual_rate, gap_percentage. If gap > 20%, flag as "eroding". If gap > 50%, flag as "critical". |
| 4.5 | Deadline collision modeling | Scan all deadlines (commitments, goals, calendar events) within 72h window. Flag pairs with < 2h gap between them. Flag days with > 3 hard deadlines as "collision risk". |
| 4.6 | Composite pressure index | `compute_pressure_index(user)` → single score 0–100. Weights loaded from `PressureWeightConfig` model (admin-configurable, not hardcoded). Default weights: `density_weight=30, compression_weight=20, breach_weight=20, erosion_weight=15, collision_weight=15`. Validation: sum must equal 100. No adaptive ML behavior. Formula: `density_score × density_weight + compression_score × compression_weight + breach_risk × breach_weight + erosion_score × erosion_weight + collision_score × collision_weight`, all divided by 100. Store daily in `PressureSnapshot`. |
| 4.7 | Integrate into CoS context | Inject pressure index and sub-scores into `build_cos_context()`. Surface in executive briefing format. |
| 4.8 | Write tests | Density computation, compression detection, breach prediction, erosion thresholds, collision detection, composite score math. |

#### Files Touched

| File | Change Type |
|------|-------------|
| New: `apps/core/blueprint/pressure_engine.py` | New — all forecasting logic |
| New: `apps/core/blueprint/pressure_models.py` | New — PressureSnapshot, PressureWeightConfig models |
| `apps/core/ai_orchestrator/cos_context.py` | Minor — inject pressure data |
| `apps/core/blueprint/weekly_pressure.py` | Minor — integrate with new engine |
| New: `apps/core/tests/test_pressure_engine.py` | New — comprehensive forecasting tests |

#### Safety Invariants

1. **Read-only** — Pressure engine only reads data, never modifies schedules or commitments
2. **No new user-facing actions** — Advisory only, no auto-blocking
3. **Existing weekly pressure engine preserved** — New engine extends, doesn't replace
4. **Score computation is deterministic** — No randomness, no LLM calls

#### Test Requirements

- Density scoring: empty day = 0.0, full day = 1.0, half day = ~0.5
- Compression: flexible blocks fit → no flag, don't fit → flag
- Breach prediction: high-density day → higher breach probability
- Erosion: goal on track → no flag, behind → eroding, far behind → critical
- Collision: 3 deadlines within 2h → collision risk
- Composite: all sub-scores at 0 → index 0, all at max → index 100

#### Rollback Plan

Entirely additive. New models and engine. Remove by:
1. Reverse migration
2. Remove import from `cos_context.py`
3. No impact on existing functionality

---

### Phase 5 — Protective Action Engine

**Tier:** T4 — Proactive Protection & Forecasting

#### Objective

Build an engine that converts pressure signals and deadline forecasts into actionable protective recommendations: auto-recommend time blocking, trigger early renegotiation prompts, issue capacity warnings, and generate pre-deadline alerts.

#### Why It Matters

Forecasting (Phase 4) identifies risk. This phase converts risk into protective action. Without it, pressure data is informational but not operational.

#### Scope Boundaries

- **IN SCOPE:** Time blocking recommendations, renegotiation prompts, capacity warnings, overload triggers, pre-deadline alerts
- **OUT OF SCOPE:** Auto-execution of protective actions (advisory only in v1), calendar modification, notification channel changes

#### Atomic Tasks

| # | Task | Description |
|---|------|-------------|
| 5.1 | Auto-recommend time blocking | When pressure index > 60 and available gaps exist, generate recommendation: "Block [time] for [habit/goal] — density tomorrow is [score]". Surface via PGE guidance item or CoS briefing. |
| 5.2 | Early renegotiation prompts | When commitment deadline approaches and breach probability > 0.6, proactively prompt: "Your commitment [X] is due in [Y hours]. Density suggests risk. Renegotiate now or confirm execution plan." |
| 5.3 | Capacity warning system | When daily density > 0.85 for any day in next 72h, inject capacity warning into CoS context. Escalate based on consecutive high-density days: 1 day = nudge, 2 days = warning, 3+ days = alert. |
| 5.4 | Overload threshold triggers | When pressure index > 80, trigger `InterventionLog` entry at Level 2 (Ping). When > 90, trigger Level 3 (Interrupt). Observable via Ops Wall. |
| 5.5 | Pre-deadline alerts | For commitments and goals with deadlines: alert at 24h, 4h, and 1h before deadline if status is still pending. Respects DNE throttle limits. |
| 5.6 | Integration with existing engines | Wire recommendations through PGE (guidance items), DNE (delivery), and InterventionLog (audit trail). Follow existing engine contracts. |
| 5.7 | Write tests | Recommendation generation thresholds, renegotiation prompt timing, capacity escalation levels, overload triggers, pre-deadline alert timing. |

#### Files Touched

| File | Change Type |
|------|-------------|
| New: `apps/core/blueprint/protective_engine.py` | New — all protective action logic |
| `apps/core/ai_orchestrator/cos_context.py` | Minor — inject protective recommendations |
| `apps/core/ai_guidance/guidance_rules.py` | Minor — new guidance rule for protective recommendations |
| `apps/core/blueprint/intervention_engine.py` | Minor — overload triggers |
| New: `apps/core/tests/test_protective_engine.py` | New — protective action tests |

#### Safety Invariants

1. **Advisory only** — No auto-execution of schedule changes
2. **Respects DNE throttle** — Pre-deadline alerts count toward daily/hourly limits
3. **No new escalation levels** — Uses existing L0-L4 framework
4. **Existing intervention logic unchanged** — New triggers are additive

#### Test Requirements

- Time blocking recommendation generated when density > threshold and gaps available
- Renegotiation prompt timing (24h, 4h, 1h before deadline)
- Capacity warning escalation (1 day, 2 days, 3+ days)
- Overload Level 2 at pressure > 80, Level 3 at > 90
- Pre-deadline alerts respect throttle limits
- No recommendations generated when pressure is low

#### Rollback Plan

Entirely additive. Remove engine file and integration points. Existing systems unaffected.

#### Implementation Decisions (Phase 5 Complete — 2026-02-23)

1. **Advisory only v1** — No auto-modification of schedule or commitments. Recommendations require user action.
2. **Human language only** — All user-facing fields use plain language. Raw metrics stored in `metadata` for audit only.
3. **Transparent when input required** — System notifies user when input is needed or when an automatic change occurs (e.g., alert suppressed by throttle).
4. **Supersede/expire rules** — New recommendation of same type for same object within 12h expires the older one (no deletion). User can dismiss with reason.
5. **Pressure alone never escalates** — CPI > 80/90 creates InterventionLog entries but never alters EscalationState.
6. **DNE throttle respected** — 3/hour, 10/day per user. Suppressed alerts are logged with next eligible time.
7. **Models:** ProtectiveRecommendation, ProtectiveAlert, ProtectiveActionLog — all append-only with audit trail.
8. **Event-driven + daily sweep** — Signals fire on PressureSnapshot, DeadlineSnapshot, Commitment changes. Daily ISE sweep catches idle users.
9. **Open Questions resolved:** Pressure index is admin-only (not shown to user). Pre-deadline alerts enabled by default for all users with active commitments.

---

### Phase 6 — Observability & Concurrency Hardening

**Tier:** T5 — Observability & Concurrency

#### Objective

Add database-level locking where metadata is mutated, ensure commitment write atomicity, add scheduler overlap protection, add observability events for enforcement escalation, and add degraded-mode tests.

#### Why It Matters

The audit identified:
- **No `select_for_update()` on conversation metadata** — concurrent writes overwrite (last-write-wins)
- **`ArchitecturePlan.activate()` non-atomic** — race window between update() and save()
- **No observability for escalation transitions** — Level changes not tracked as EngineRun events
- **No degraded-mode testing** — What happens when LLM/DB/cache are down?

#### Scope Boundaries

- **IN SCOPE:** Locking, atomicity, overlap protection, observability events, degraded-mode tests
- **OUT OF SCOPE:** Redis clustering, database replication, distributed locking (overkill for single-user app)

#### Atomic Tasks

| # | Task | Description |
|---|------|-------------|
| 6.1 | Add `select_for_update()` to conversation metadata | In `send_message()`, wrap the conversation metadata read-modify-write cycle in `transaction.atomic()` with `select_for_update()` on the conversation row. Prevents stale-read on rapid double-submit. |
| 6.2 | Commitment write atomicity | Phase 1 already adds `select_for_update()` on Commitment model. This task ensures the full create→save→notify cycle is wrapped in `transaction.atomic()`. |
| 6.3 | Fix `ArchitecturePlan.activate()` atomicity | Wrap the supersede-old + activate-new sequence in `transaction.atomic()`. Eliminates race window. |
| 6.4 | Scheduler overlap protection tests | Add tests proving ISE's `scheduler_lock.py` prevents duplicate engine runs. Test: two concurrent ISE triggers → only one executes. |
| 6.5 | Add anomaly for commitment race condition | Register new SAME anomaly type `COMMITMENT_RACE_CONDITION`: triggered when two commitment mutations occur within 1 second for same user. |
| 6.6 | Observability events for enforcement escalation | Log `EngineRun` entries when escalation level changes. Add `DecisionRecord` with rationale for each escalation/de-escalation. |
| 6.7 | Degraded-mode tests (LLM down) | Test: OpenAI returns None/timeout → user gets graceful fallback message, no crash, commitment state preserved. |
| 6.8 | Degraded-mode tests (DB down) | Test: DB write fails during commitment save → sentinel pattern fires, user gets closure response, error logged. |
| 6.9 | Degraded-mode tests (Cache down) | Test: Redis unavailable → scheduling context not found, system falls back gracefully, no crash. |
| 6.10 | Write tests | Concurrency locking, atomicity, scheduler overlap, anomaly detection, degraded-mode fallbacks. |

#### Files Touched

| File | Change Type |
|------|-------------|
| `apps/ai/personal_assistant.py` | Moderate — `select_for_update()` on conversation |
| `apps/core/blueprint/architecture_engine.py` | Minor — atomic activate() |
| `apps/core/ai_observability/same_engine.py` | Minor — new anomaly type |
| `apps/core/ai_observability/ops_anomalies.py` | Minor — COMMITMENT_RACE_CONDITION |
| `apps/core/ai_orchestrator/cos_context.py` | Minor — escalation observability |
| New: `apps/core/tests/test_concurrency.py` | New — concurrency test suite |
| New: `apps/core/tests/test_degraded_mode.py` | New — degraded-mode test suite |

#### Safety Invariants

1. **Locking is narrow** — Only lock rows being mutated, not tables
2. **Lock timeout** — Use `nowait=True` or short timeout to prevent deadlocks
3. **Existing sentinel pattern preserved** — Hard short-circuit still works
4. **Fire-and-forget observability unchanged** — Instrumentation never blocks pipeline

#### Test Requirements

- Two simultaneous metadata writes → only one succeeds (or serialized correctly)
- ArchitecturePlan.activate() atomicity under concurrent calls
- ISE scheduler lock prevents duplicate runs
- COMMITMENT_RACE_CONDITION anomaly fires on sub-second double-write
- Escalation EngineRun and DecisionRecord created on level change
- LLM down → graceful fallback
- DB down during commitment → sentinel fires
- Cache down → scheduling context gracefully unavailable

#### Rollback Plan

Locking changes are in the data access layer. Revert by removing `select_for_update()` calls and `transaction.atomic()` wrappers. Observability additions are purely additive.

---

### Phase 7 — Test Expansion

**Tier:** T6 — Testing & Verification

#### Objective

Add explicit test coverage for all blind spots identified in the audit, ensuring the system behaves correctly under edge cases, concurrent access, and failure scenarios.

#### Why It Matters

The audit identified 10 specific blind spots (Section 8) with no test coverage. An executive-grade system must have tests for every failure mode, not just happy paths.

#### Scope Boundaries

- **IN SCOPE:** All 10 audit blind spots, plus any gaps discovered during Phases 1-6
- **OUT OF SCOPE:** Performance/load testing, end-to-end browser testing

#### Atomic Tasks

| # | Task | Description |
|---|------|-------------|
| 7.1 | DST transition tests | Spring-forward gap, fall-back fold, commitment crossing DST boundary, scheduling across DST. (May partially exist from Phase 2 — expand here.) |
| 7.2 | Multi-tab same-user concurrency | Simulate two concurrent `send_message()` calls for same user. Verify: no data corruption, no duplicate commitments, no lost closure. |
| 7.3 | Rapid message double-submit | Simulate identical message sent twice within 100ms. Verify: idempotent handling, no duplicate actions, commitment state consistent. |
| 7.4 | Commitment stacking | Create 3 pending commitments. Close one. Verify: other two remain. Close all. Verify: all closed. Attempt closure with no pending → graceful message. |
| 7.5 | Deadline surfacing accuracy | Create commitments with deadlines at 12h, 36h, 5d. Verify correct categorization into 24h/72h/7d buckets. Edge case: deadline exactly at boundary (24h). |
| 7.6 | Drift downgrade prevention | Set escalation to Level 3 (STRUCTURAL_DRIFT). Send single positive message. Verify: state does NOT drop to CLEAN. Send 7 consecutive clean days. Verify: state drops to CLEAN. |
| 7.7 | Forecast modeling correctness | Pressure index computation with known inputs. Verify each sub-score and composite. Edge cases: empty calendar (pressure = 0), fully packed (pressure = 100). |
| 7.8 | Calendar collision detection | Create two events with 30-minute overlap. Verify: collision detected. Create two events 3 hours apart. Verify: no collision. Edge: events in different timezones. |
| 7.9 | Cache failure fallback | Mock Redis as unavailable. Verify: scheduling context returns empty (not crash), system prompt assembly completes, commitment operations work (DB-only). |
| 7.10 | Model pricing absence | Remove all `LLMPriceBook` entries. Verify: `log_llm_usage()` stores event with `cost=0` and `missing_pricebook=True` in metadata. No crash. |
| 7.11 | Cross-phase integration test | Full pipeline: create commitment (Phase 1), advance to near-deadline (Phase 2), trigger pressure forecast (Phase 4), receive protective recommendation (Phase 5), observe escalation (Phase 6). End-to-end verification. |

#### Files Touched

| File | Change Type |
|------|-------------|
| `apps/core/tests/test_dst_transitions.py` | Expansion from Phase 2 |
| `apps/core/tests/test_concurrency.py` | Expansion from Phase 6 |
| `apps/core/tests/test_degraded_mode.py` | Expansion from Phase 6 |
| New: `apps/core/tests/test_commitment_stacking.py` | New — stacking-specific tests |
| New: `apps/core/tests/test_deadline_surfacing.py` | Expansion from Phase 2 |
| New: `apps/core/tests/test_escalation_continuity.py` | Expansion from Phase 3 |
| New: `apps/core/tests/test_pressure_engine.py` | Expansion from Phase 4 |
| New: `apps/core/tests/test_cross_phase_integration.py` | New — end-to-end integration |
| `apps/core/tests/test_phase4_cos.py` | Minor — drift downgrade tests |
| `apps/owner_finance/tests.py` | Minor — pricing absence test |

#### Safety Invariants

1. **Tests are additive** — No existing test modified or deleted
2. **No production code changes in this phase** — Tests only
3. **Tests use Django TestCase** — Transactional isolation

#### Test Requirements

This entire phase IS the test requirements. Target: 100+ new test cases across all blind spots.

#### Rollback Plan

Tests are purely additive. Remove test files to roll back. No production impact.

---

## Audit Alignment Matrix

| Audit Finding | Phase | Task(s) | How Addressed |
|---------------|-------|---------|---------------|
| ECC runtime-only commitments | 1 | 1.1–1.4 | Persistent DB model with migration |
| No historical commitment tracking | 1 | 1.1, 1.3 | Commitment model + analytics rollup |
| No cross-session continuity | 1 | 1.6 | Query pending commitments on conversation start |
| No concurrency locking for commitments | 1, 6 | 1.5, 6.1–6.2 | `select_for_update()` + `transaction.atomic()` |
| No renegotiation history | 1 | 1.2 | CommitmentRenegotiation model |
| False-positive detection ("I'll have pizza") | 1 | 1.7 | Context-aware exclusion filtering |
| No multi-commitment stacking | 1 | 1.8 | Multiple pending commitments per user |
| Silent all-day time default | 2 | 2.1 | Explicit time boundary enforcement |
| `datetime.now()` usage | 2 | 2.2 | Replace with `get_current_local_datetime()` |
| No DST handling/testing | 2, 7 | 2.3–2.4, 7.1 | DST-aware parsing + comprehensive tests |
| No deadline surfacing | 2 | 2.6 | 24h/72h/7d categorized deadline engine |
| No protected-block conflict detection | 2 | 2.7 | Overlap detection for locked blocks |
| Escalation has no memory | 3 | 3.1–3.2 | EscalationState + EscalationEvent models |
| Single positive drops STRUCTURAL_DRIFT | 3 | 3.4–3.5 | Recovery decay model (score >= 0.7 required) |
| No drift recovery model | 3 | 3.4 | Recovery score with asymmetric up/down rates |
| No trend persistence | 3 | 3.6 | BehavioralTrend model |
| No calendar density scoring | 4 | 4.1 | Daily density computation (0.0–1.0) |
| No workload compression modeling | 4 | 4.2 | Flexible task squeeze detection |
| No habit breach prediction | 4 | 4.3 | Per-block breach probability |
| No goal erosion detection | 4 | 4.4 | Progress rate gap analysis |
| No deadline collision modeling | 4 | 4.5 | 72h window collision scan |
| No composite pressure score | 4 | 4.6 | Pressure index 0–100 |
| No auto time-blocking recommendations | 5 | 5.1 | Pressure-driven recommendations via PGE |
| No early renegotiation prompts | 5 | 5.2 | Breach-probability-driven prompts |
| No capacity warning system | 5 | 5.3 | Density-based escalating warnings |
| No overload threshold triggers | 5 | 5.4 | Pressure → InterventionLog integration |
| No pre-deadline alerts | 5 | 5.5 | 24h/4h/1h alerts via DNE |
| No `select_for_update()` on metadata | 6 | 6.1 | Row-level locking on conversation |
| `ArchitecturePlan.activate()` non-atomic | 6 | 6.3 | `transaction.atomic()` wrapper |
| No observability for escalation | 6 | 6.6 | EngineRun + DecisionRecord logging |
| No degraded-mode testing | 6, 7 | 6.7–6.9, 7.9 | LLM/DB/cache down tests |
| 10 audit blind spots untested | 7 | 7.1–7.11 | Comprehensive test expansion |

---

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Phase 1 migration complexity | High | Backward-compatible migration; metadata preserved as fallback |
| `select_for_update()` deadlock potential | Medium | Use `nowait=True` with graceful fallback |
| Performance impact of DB-backed commitments | Medium | Index on `(user, status)`, query only pending |
| Recovery decay model too aggressive/lenient | Medium | Tunable constants; start conservative (0.7 threshold) |
| Pressure index formula weights incorrect | Low | Weights are configurable; tune based on real data |
| Test suite expansion slows CI | Low | New tests scoped to changed modules only |
| Cross-phase dependencies | Medium | Phases designed for sequential execution; each phase is self-contained |

---

## Open Questions

| # | Question | Impact | Decision Needed By |
|---|----------|--------|--------------------|
| 1 | ~~Should multi-commitment limit be enforced?~~ | Phase 1 | **RESOLVED** — Yes, hard limit of 5. |
| 2 | ~~Should the pressure index be visible to the user or admin-only initially?~~ | Phase 4-5 | **RESOLVED** — Admin-only. Users see human-language Load Status (Normal/Elevated/High/Critical). |
| 3 | ~~Should pre-deadline alerts be enabled by default or opt-in?~~ | Phase 5 | **RESOLVED** — Enabled by default for all users with active commitments. |
| 4 | ~~Should timezone-change recomputation be automatic or prompt the user?~~ | Phase 2 | **RESOLVED** — Automatic. Local-intent preservation, no user prompt. |
| 5 | ~~What should the commitment false-positive exclusion list contain initially?~~ | Phase 1 | **RESOLVED** — Vague verb list defined; atomic verbs exempt from done-definition. |

---

## Decisions Log

| Date | Decision | Rationale | Phase |
|------|----------|-----------|-------|
| 2026-02-23 | Project created | External audit identified 30+ upgrade opportunities | All |
| 2026-02-23 | Locked structural policies for Phase 1–4 before implementation | Architectural precision before code execution | Phase 1–4 |
| 2026-02-23 | Locked Phase 2 authority policies (timezone intent, ISE snapshots, graduated Tier 1 override, single time authority) | Deterministic time handling before execution | Phase 2 |
| 2026-02-23 | Phase 2 complete — all 7 atomic tasks implemented, 186 tests passing | Explicit time boundaries, zoneinfo DST, local-intent TZ recalculation, ISE-driven DeadlineSnapshot, Tier 1 graduated resistance | Phase 2 |
| 2026-02-23 | Phase 3 complete — persistent escalation, recovery gate, behavioral trends, 345 tests passing | DB-backed EscalationState floor, Hybrid Recovery Rule (5 criteria), BehavioralTrend daily rollup, ISE scheduler integration | Phase 3 |
| 2026-02-23 | Phase 4 complete — deterministic pressure modeling, CPI 0–100, event-driven triggers, 44 new tests + 419 regression tests passing | PressureSnapshot + PressureWeightConfig models, 5-component pressure engine (density/compression/breach/erosion/collision), horizon attenuation (7/14/30d), signal-based triggers, ISE daily sweep, CoS context injection with human-readable narratives | Phase 4 |

---

## Locked Architectural Policy Decisions

- Maximum 5 active pending commitments per user (hard limit).
- Commitments are user-global (conversation optional for traceability).
- Explicit numeric selection required when closing multiple commitments.
- Time boundary always required for commitments.
- Done-definition required only for vague actions (deterministic verb list).
- Hybrid drift recovery model (7 clean days + behavioral proof).
- Pressure weights configurable via `PressureWeightConfig`.
- Backend idempotency protection (3-second duplicate window).
- Timezone changes preserve local wall-clock intent.
- Deadline surfacing is ISE-driven via `DeadlineSnapshot`.
- Tier 1 conflicts use graduated resistance with explicit override and logging.
- Single authoritative time source enforced across codebase.
- Hybrid Recovery Rule: de-escalation requires 7 clean days + 3 honored commitments + 0 Tier 1 misses + 0 blocked renegotiations + 0 drift events.
- Escalation state persists across sessions (DB-backed EscalationState as floor).
- Escalation increases immediately; de-escalation drops by 1 level only.
- Pressure is predictive, not punitive — pressure alone NEVER raises escalation level.
- Composite Pressure Index (CPI) 0–100 with fixed thresholds: >60 elevated, >80 high, >90 critical.
- CPI weights: density 30, compression 20, breach 20, erosion 15, collision 15 (sum=100).
- Horizon attenuation: 0–7 days full precision (×1.0), 8–14 moderate (×0.6), 15–30 early warning (×0.3).
- Pressure recompute is event-driven (commitment/block/goal/override changes) + daily ISE sweep.
- PressureSnapshot records are immutable — never overwritten, always appended.
- Baseline variance stored in metadata for future adaptive thresholds (not used in Phase 4).

---

*Last updated: 2026-02-23 (Phase 4 complete)*
