# CoS (Chief of Staff) v2 — Master Project Tracker

**Created:** 2026-02-24
**Status:** Phase 4 Complete — Ready for Phase 5
**Owner:** Claude Code (lead engineer)

---

## Vision & Success Criteria

### Vision
Transform the existing WLJ intelligence infrastructure into a coherent, system-wide Chief of Staff that is **reactive**, **proactive**, **reflective**, and **predictive** across ALL CRUD-capable modules — not just calendar or journal.

### Success Criteria
1. **Unified CoS Action Contract** — Every CRUD-capable module plugs into a single action framework with consistent create/update/delete/retrieve/summarize + duplicate checks + conflict detection + post-activity feedback
2. **Calendar v2** — Full CRUD with 3-layer duplicate prevention (already exists), enhanced conflict resolution with fit options (shift 15min, next slot, shorten, awareness-only)
3. **Journal v2** — Same-date append-not-duplicate behavior; CoS-driven create/append/update/summarize
4. **Proactive Prompting** — Pre-event and post-event prompts for ALL activity types (meetings, workouts, bible study, etc.), not just medicine/task check-ins
5. **Indefinite Reflection Storage** — Reflections attached to specific entity occurrences, queryable for later use ("yesterday was tough — how was today?")
6. **Pattern Detection + Solutions** — Evidence-based pattern detection with proactive (non-spammy) solution suggestions
7. **Goal Suggestion Policy** — Monthly throttle, never auto-create, 3-decline opt-out
8. **Priority + Time-of-Day Auto-Shifting** — Low-priority auto-shift respects human realism (no late-night workouts)
9. **Tone Modes** — Context-sensitive tone (work vs personal) via existing CoachingStyle infrastructure
10. **Zero regression** — All existing tests pass, new tests added for every feature

---

## Scope

### In Scope
- CoS Action Contract (shared interface for all modules)
- Calendar CRUD enhancements (conflict resolution options)
- Journal append-not-duplicate
- Pre/post event proactive prompting engine
- Reflection storage model (entity-attached, indefinite)
- Pattern detection → solution suggestion pipeline
- Goal suggestion policy (throttle + decline tracking)
- Priority-aware auto-shifting with time-of-day constraints
- Tone mode support
- Feature flag for CoS v2 rollout
- Comprehensive scenario-based tests

### Out of Scope
- New UI pages (CoS works through existing AI assistant chat + notifications)
- Mobile app changes (CoS operates server-side)
- Third-party integrations (no new external APIs)
- Fundamental changes to the 14-engine architecture (build ON it, not replace it)

---

## Architecture Decisions

### AD-1: Build on Existing Infrastructure
The system already has 14 engines, a 3-phase pipeline, proactive check-ins, reflection engine, memory engine, and governance. CoS v2 extends these — it does NOT replace them.

### AD-2: CoS Action Contract as Abstract Base
A `CosActionContract` abstract class defines the interface. Each module provides a concrete implementation (e.g., `CalendarCosActions`, `JournalCosActions`). The UAIO routes through these contracts.

### AD-3: Reflection Model = New `CosReflection` Model
Existing `EventReflection` is limited to calendar/workout events. A new `CosReflection` model supports ANY entity type via generic FK pattern (content_type + object_id), with indefinite retention.

### AD-4: Proactive Prompt Scheduler via ISE
Pre/post event prompts are scheduled tasks managed by ISE (existing scheduler). New prompt types registered with ISE, delivered via DNE (existing delivery engine).

### AD-5: Pattern Detection via PIE Extension
New PIE rules for cross-domain pattern detection. Solutions suggested via PGE (existing guidance engine) with new `cos_suggestion` guidance type.

### AD-6: Goal Suggestion Throttle Model
New `CosGoalSuggestion` model tracks suggestion history, decline count, and opt-out status per theme.

### AD-7: Feature Flag via UserPreferences
CoS v2 features gated behind `cos_v2_enabled` in UserPreferences. Existing CoS behavior preserved when flag is off.

### AD-8: Journal Append via Service Layer
Journal append logic lives in a new `JournalCosActions` service that checks for same-date entries before creating. The existing view/form path is unchanged; CoS-driven operations go through the action contract.

---

## Phase Plan

---

### Phase 0: Baseline + Safety Harness ✅
**Goal:** Inventory, feature flag, baseline regression tests, project structure

**Tasks:**
- [x] Explore and document existing infrastructure (14 engines, models, services)
- [x] Create CoS_Project_v2.md (this file)
- [x] Add `cos_v2_enabled` feature flag to UserPreferences
- [x] Create `apps/cos/` app skeleton (models, services, tests, admin)
- [x] Add baseline regression tests for existing calendar + journal behavior
- [x] Run existing tests to confirm zero regression
- [x] Document architecture decisions

**Files Created/Modified:**
- `CoS_Project_v2.md` (this file)
- `apps/cos/__init__.py`
- `apps/cos/apps.py`
- `apps/cos/models.py`
- `apps/cos/admin.py`
- `apps/cos/services/__init__.py`
- `apps/cos/tests/__init__.py`
- `apps/cos/tests/test_baseline.py`
- `apps/users/models.py` (add cos_v2_enabled flag)
- `apps/users/migrations/XXXX_add_cos_v2_enabled.py`
- `config/settings.py` (register cos app)

**Tests:** Baseline regression tests for calendar create/dup/conflict + journal create
**Risk:** Migration on UserPreferences — low risk, additive only

---

### Phase 1: CoS Action Contract + Shared Services ✅
**Goal:** Define the universal action interface and shared models (reflection, prompt scheduling)

**Tasks:**
- [x] Define `CosActionContract` abstract base class
- [x] Create `CosReflection` model (generic FK, indefinite retention)
- [x] Create `CosPromptSchedule` model (pre/post event scheduling)
- [x] Create `CosGoalSuggestion` model (throttle + decline tracking)
- [x] Create `CosAutoShiftLog` model (audit trail for auto-shifts)
- [x] Implement `CosActionRegistry` (register/lookup module contracts)
- [x] Add migrations
- [x] Add unit tests for models and registry
- [x] Update CoS_Project_v2.md

**Files Created/Modified:**
- `apps/cos/contracts.py` — CosActionContract ABC + ActionResult, DuplicateCheck, ConflictCheck dataclasses
- `apps/cos/registry.py` — CosActionRegistry singleton (register, get, list, clear)
- `apps/cos/models.py` — CosReflection, CosPromptSchedule, CosGoalSuggestion, CosAutoShiftLog
- `apps/cos/admin.py` — Admin registrations for all 4 models
- `apps/cos/migrations/0001_phase1_models.py` — Migration for all Phase 1 models
- `apps/cos/tests/test_contracts.py` — 15 tests (contract enforcement, defaults, dataclasses, registry)
- `apps/cos/tests/test_models.py` — 19 tests (CRUD, lifecycle, querying, decline tracking)

**Tests:** 68 total (17 baseline + 34 new) — all pass
**Risk:** Generic FK complexity — mitigated with 3 indexes per model + explicit content_type fields

---

### Phase 2: Calendar v2 — Enhanced Conflict Resolution ✅
**Goal:** Add conflict resolution options (shift, next slot, shorten, force create)

**Tasks:**
- [x] Implement `CalendarCosActions` (full contract: create, update, delete, retrieve, summarise)
- [x] Add conflict resolution option generator (shift_after_conflict, next_available, shorten, force_create)
- [x] Wire resolution options into create() and check_conflicts() flows
- [x] Implement duplicate detection via check_duplicate (semantic + recurrence)
- [x] Implement reflection hook (capture_reflection_hook stores CosReflection)
- [x] Add tests for all conflict resolution paths
- [x] Update CoS_Project_v2.md

**Files Created/Modified:**
- `apps/cos/actions/calendar_actions.py` — CalendarCosActions + generate_resolution_options()
- `apps/cos/tests/test_calendar_actions.py` — 30 tests (CRUD, dup, conflicts, resolution options, reflections)

**Tests:** 98 total (17 baseline + 51 Phase 1 + 30 Phase 2) — all pass
**Risk:** No changes to existing calendar_engine code — CalendarCosActions wraps CalendarMutationService

---

### Phase 3: Journal v2 — Append Not Duplicate ✅
**Goal:** CoS-driven journal operations with same-date append behavior

**Tasks:**
- [x] Implement `JournalCosActions` (full contract: create, update, delete, retrieve, summarise)
- [x] Add same-date entry detection + append logic (_find_same_date_entry + _append_to_entry)
- [x] Add section update capability (update with append_body kwarg)
- [x] Add entry summarisation with date ranges and word counts
- [x] Add duplicate check (same-date detection with message about append)
- [x] Add reflection hook for journal entries
- [x] Add tests for create/append/update/summarise + edge cases
- [x] Update CoS_Project_v2.md

**Files Created/Modified:**
- `apps/cos/actions/journal_actions.py` — JournalCosActions with append-not-duplicate
- `apps/cos/tests/test_journal_actions.py` — 38 tests

**Tests:** 136 total (17+51+30+38) — all pass
**Risk:** Zero changes to journal models — JournalCosActions is purely additive

---

### Phase 4: Proactive Prompting Engine ✅
**Goal:** Pre/post event prompts for ALL activity types
**Completed:** 2026-02-24 | **Tests:** 41 new (177 total CoS)

**Tasks:**
- [x] Create `CosPromptService` for scheduling pre/post prompts
- [x] Implement activity-type-specific prompt templates (8 types + default)
- [x] Implement pre-event prompts (configurable lead time per activity type)
- [x] Implement post-event check-in flow (Yes/No → optional follow-up → stop)
- [x] Wire delivery through DNE (graceful fallback if unavailable)
- [x] Implement prompt expiration and cleanup logic (stale prompts expired after 4h)
- [x] Implement dedup (no duplicate prompts for same event/timing)
- [x] Implement batch delivery with feature flag gating (`deliver_all_due_for_all_users`)
- [x] Add tests for prompt scheduling, delivery, yes/no flow, batch, expiration
- [x] Update CoS_Project_v2.md

**Files Created:**
- `apps/cos/services/prompt_service.py` — CosPromptService (schedule, deliver, respond, batch)
- `apps/cos/services/prompt_templates.py` — Activity type detection + templates for 8 types
- `apps/cos/tests/test_prompt_service.py` — 41 tests across 8 test classes

**Architecture:**
- `detect_activity_type(title)` — Pattern-based title→type detection (workout, meeting, prayer, etc.)
- Pre-event prompt: scheduled `lead_minutes` before start_dt (configurable per activity type)
- Post-event prompt: scheduled `post_delay_minutes` after end_dt
- Response flow: Yes → capture reflection + return follow-up question → No → stop (no nagging)
- DNE integration: Routes through `deliver_single()` with graceful fallback
- Feature flag: `cos_v2_enabled` checked in batch delivery
- ISE integration: Ready for scheduler registration (Phase 10)

**Risk mitigated:** Prompt spam prevented by dedup, expiration, feature flag, and DNE throttling

---

### Phase 5: Reflection Storage + Retrieval
**Goal:** Indefinite reflection storage attached to entities, queryable for context

**Tasks:**
- [ ] Implement reflection CRUD service
- [ ] Wire reflection capture into post-event check-in flow
- [ ] Implement reflection retrieval for contextual prompts ("yesterday was cold…")
- [ ] Add temporal comparison queries (yesterday vs today)
- [ ] Integrate with SLCME for context memory
- [ ] Add tests for storage, retrieval, temporal queries
- [ ] Update CoS_Project_v2.md

**Files to Touch:**
- `apps/cos/services/reflection_service.py`
- `apps/cos/models.py` (CosReflection already created in Phase 1)
- `apps/core/ai_memory/` (integration point)
- `apps/cos/tests/test_reflection_service.py`

**Tests:** Attach reflection to entity, retrieve by entity, temporal comparison
**Risk:** Query performance with large reflection datasets — add indexes

---

### Phase 6: Pattern Detection + Solution Suggestions
**Goal:** Cross-domain pattern detection with evidence-based solution suggestions

**Tasks:**
- [ ] Create new PIE rules for cross-domain patterns (fatigue, missed tasks, consistent conflicts)
- [ ] Create PGE guidance rules for CoS solution suggestions
- [ ] Implement suggestion deduplication and frequency control
- [ ] Add evidence chain from reflections to suggestions
- [ ] Add tests for pattern detection, suggestion generation, spam prevention
- [ ] Update CoS_Project_v2.md

**Files to Touch:**
- `apps/core/ai_insights/rules/` (new cross-domain rules)
- `apps/core/ai_guidance/rules/` (new CoS suggestion rules)
- `apps/cos/services/pattern_service.py`
- `apps/cos/tests/test_pattern_detection.py`

**Tests:** Pattern detection triggers, solution suggestion output, frequency limits
**Risk:** False positives — require high confidence threshold (0.8+)

---

### Phase 7: Goal Suggestion Policy
**Goal:** Monthly-throttled goal suggestions with 3-decline opt-out

**Tasks:**
- [ ] Implement goal suggestion service with monthly throttle
- [ ] Track decline history per theme
- [ ] Implement 3-decline opt-out prompt ("Stop suggesting this?")
- [ ] Wire into PGE guidance delivery
- [ ] Add tests for throttle, decline tracking, opt-out
- [ ] Update CoS_Project_v2.md

**Files to Touch:**
- `apps/cos/services/goal_suggestion_service.py`
- `apps/cos/models.py` (CosGoalSuggestion already created in Phase 1)
- `apps/cos/tests/test_goal_suggestions.py`

**Tests:** Monthly throttle enforced, decline count tracking, opt-out at 3 declines
**Risk:** Low — isolated feature with clear boundaries

---

### Phase 8: Priority + Time-of-Day Auto-Shifting
**Goal:** Low-priority auto-shift with human-realism constraints

**Tasks:**
- [ ] Define time-of-day suitability rules per activity type
- [ ] Implement auto-shift service for low-priority items
- [ ] Add "ask before moving" gate for important/high-priority items
- [ ] Implement audit logging for all auto-shifts
- [ ] Add tests for shift constraints, priority gates, audit trail
- [ ] Update CoS_Project_v2.md

**Files to Touch:**
- `apps/cos/services/auto_shift_service.py`
- `apps/cos/models.py` (CosAutoShiftLog already created in Phase 1)
- `apps/calendar_engine/services/calendar_mutation_service.py` (integration)
- `apps/cos/tests/test_auto_shift.py`

**Tests:** Time-of-day constraints (no late-night workouts), priority gates, audit logging
**Risk:** Auto-shifting without user consent — mitigate with strict priority gates and logging

---

### Phase 9: Tone Modes + Final Integration
**Goal:** Context-sensitive tone and full system integration

**Tasks:**
- [ ] Implement tone mode selection (work vs personal context detection)
- [ ] Wire tone into CoS prompt generation
- [ ] Integrate all CoS actions with UAIO action router
- [ ] End-to-end integration tests across all modules
- [ ] Update CoS_Project_v2.md

**Files to Touch:**
- `apps/cos/services/tone_service.py`
- `apps/core/ai_orchestrator/action_router.py` (integration)
- `apps/ai/models.py` (CoachingStyle context field if needed)
- `apps/cos/tests/test_tone_modes.py`
- `apps/cos/tests/test_integration.py`

**Tests:** Tone selection by context, end-to-end flows
**Risk:** Tone changes affecting existing AI responses — feature flag protects

---

### Phase 10: Rollout + Backfill + Hardening
**Goal:** Production readiness, data migration, performance tuning

**Tasks:**
- [ ] Enable feature flag for test users
- [ ] Backfill CosReflection from existing EventReflection data
- [ ] Performance profiling on reflection queries
- [ ] Add database indexes as needed
- [ ] Review and harden all error handling
- [ ] Update documentation (features doc, help topics, release notes)
- [ ] Update CoS_Project_v2.md

**Files to Touch:**
- `apps/cos/management/commands/backfill_reflections.py`
- `apps/cos/migrations/` (indexes)
- Documentation files per CLAUDE.md requirements

**Tests:** Backfill correctness, query performance under load
**Risk:** Backfill data integrity — run in dry-run mode first

---

### Phase 11: Final Regression + Scenario Tests
**Goal:** Full scenario coverage, final sign-off

**Tasks:**
- [ ] Scenario: Calendar duplicate prevention (one-off + recurring)
- [ ] Scenario: Conflict detection and resolution option output
- [ ] Scenario: Journal append vs create
- [ ] Scenario: Proactive pre/post prompts firing correctly
- [ ] Scenario: Yes/No flow behavior (No stops; Yes continues)
- [ ] Scenario: Reflection persistence and later retrieval
- [ ] Scenario: Low-priority auto-shift respecting time-of-day
- [ ] Scenario: Goal suggestion throttling and 3-decline behavior
- [ ] Run full test suite (with user approval)
- [ ] Update CoS_Project_v2.md — mark COMPLETE

**Files to Touch:**
- `apps/cos/tests/test_scenarios.py`

**Tests:** All scenario tests listed above
**Risk:** Low — testing phase only

---

## Known Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Prompt spam / notification fatigue | High | DNE throttling, noise budget (PIE), quiet hours, explicit stop flows |
| Auto-shift moving things user doesn't want moved | High | Strict priority gates, audit logging, confirmation for important items |
| Reflection query performance at scale | Medium | Database indexes, pagination, summary caching |
| Generic FK complexity (CosReflection) | Medium | Explicit content_type constraints, well-tested |
| Goal suggestion annoyance | Medium | Monthly throttle, 3-decline opt-out, never auto-create |
| Breaking existing behavior | High | Feature flag, baseline regression tests, phase-by-phase rollout |
| Migration complexity | Medium | Additive migrations only, no destructive changes |

---

## Rollout Plan

1. **Dev/Test:** Feature flag off by default. Enabled per-user for testing.
2. **Staged Rollout:** Enable for owner account first, monitor for 1 week.
3. **Full Rollout:** Enable by default for all users after stability confirmed.
4. **Fallback:** Feature flag can disable CoS v2 instantly without deployment.

---

## Test Plan Summary

| Category | Test Count (est.) | Phase |
|----------|------------------|-------|
| Baseline regression | ~15 | 0 |
| Model + registry | ~10 | 1 |
| Calendar conflict resolution | ~12 | 2 |
| Journal append/create | ~8 | 3 |
| Proactive prompts | ~15 | 4 |
| Reflection CRUD + retrieval | ~10 | 5 |
| Pattern detection | ~8 | 6 |
| Goal suggestions | ~6 | 7 |
| Auto-shift | ~8 | 8 |
| Tone modes + integration | ~10 | 9 |
| Scenario end-to-end | ~10 | 11 |
| **Total** | **~112** | |

---

*Last updated: 2026-02-24 — Phase 3 complete*
