# WLJ Architecture Evolution Assessment

**Date:** 2026-03-14
**Author:** Claude (System Architect)
**Status:** Assessment & Recommendation — NOT an implementation plan yet

---

## Executive Summary

After deep analysis of the WLJ codebase, the system is **significantly more mature** than the design prompt assumes. Many of the proposed conceptual layers already exist in sophisticated form. The key finding is that **WLJ doesn't need a ground-up redesign — it needs targeted gap-filling and stronger cross-domain connective tissue.**

The biggest structural tension — "everything is a Task" — is partially solved by the CalendarEngine projection layer and the CoS Architecture Plan, but these aren't yet surfaced as a unified daily operating view.

---

## Part 1: Mapping the Proposed Model to What Already Exists

### Layer 1: Domain Systems ✅ FULLY EXISTS

Every proposed domain has its own dedicated model with rich schema:

| Domain | App | Key Models | Status |
|--------|-----|-----------|--------|
| Tasks | `apps/life` | Task, Project, ProjectMilestone | Complete |
| Medicines | `apps/health` | Medicine, MedicineSchedule, MedicineLog | Complete |
| Workouts | `apps/health` | WorkoutSession, WorkoutPlan, WorkoutSchedule, ExerciseSet, PersonalRecord | Complete |
| Journal | `apps/journal` | JournalEntry, Emotion, JournalPrompt | Complete |
| Sleep | `apps/health` | Sleep, SleepGoal | Complete |
| Health Metrics | `apps/health` | Weight, BloodPressure, BloodSugar, Temperature | Complete |
| Faith | `apps/faith` | PrayerRequest, UserReadingPlan, UserReadingProgress, FaithMilestone | Complete |
| Calendar Events | `apps/life` | LifeEvent (with recurrence, external sync) | Complete |
| Goals | `apps/purpose` | LifeGoal, GoalMilestone, HabitGoal, HabitEntry | Complete |
| Finance | `apps/finance` | FinancialAccount, Transaction, Budget, FinancialGoal | Complete |
| Brain Training | `apps/brain_training` | Game, Challenge, GameSession, DailyStats | Complete |
| Capture | `apps/capture` | CaptureEntry, PendingCapture | Complete |

**Assessment:** Domain systems are the strongest layer. No changes needed here. Each domain owns its data and is the source of truth. The abstract base classes (TimeStampedModel, SoftDeleteModel, UserOwnedModel) provide excellent consistency.

---

### Layer 2: Scheduled Commitments ⚠️ PARTIALLY EXISTS (Fragmented)

**What exists today:**

1. **CalendarEvent** (`apps/calendar_engine/models.py`) — This IS essentially the ScheduledCommitment concept:
   - `source_type`: task, goal, goal_milestone, habit, life_event, external
   - `source_id`: FK to source object
   - `status`: scheduled, completed, canceled
   - `kind`: manual, deadline_marker, execution_block, external_readonly
   - Idempotency key for dedup
   - RecurrenceRule for recurring patterns

2. **ArchitecturePlan + ArchitectureBlock** (`apps/core/blueprint/`) — CoS daily plan:
   - Tier 1/2/3 priority blocks
   - Time-based blocks (start_time, end_time)
   - Links to routine tasks and behavior keys

3. **Per-domain scheduling:**
   - Task: `scheduled_time`, `scheduled_end_time`, `is_routine`, recurrence
   - MedicineSchedule: `scheduled_time`, `time_of_day`, `days_of_week`
   - WorkoutSchedule: `day_of_week`, `preferred_time`
   - PrayerRequest: `remind_daily` flag
   - DailyVerse: date-based assignment

**What's MISSING:**

- **No unified daily timeline view** — Each domain renders independently on the dashboard
- **Medicine schedules don't project into CalendarEngine** — They have their own parallel scheduling system
- **Faith routines don't project into CalendarEngine** — No CalendarEvent source_type for prayer/reading
- **The dashboard shows tiles, not a chronological daily schedule**

**Gap Assessment:** CalendarEngine is 80% of the proposed ScheduledCommitment model. The remaining 20% is connecting medicine schedules, faith routines, and other time-based commitments into CalendarEngine projections, plus building a unified chronological daily view.

---

### Layer 3: Life Events ⚠️ PARTIALLY EXISTS (Different Concept)

**What exists today:**

1. **LifeEvent** (`apps/life/models.py`) — Calendar events (birthdays, trips, appointments)
   - This is about *planned future events*, NOT "things that actually happened"
   - Supports recurrence, external calendar sync, reminders

2. **Domain-specific completion records** — Things that DID happen, but scattered:
   - `MedicineLog` (taken_at, log_status: taken/missed/skipped/late)
   - `WorkoutSession` (started_at, completed_at)
   - `HabitEntry` (date, completed)
   - `JournalEntry` (created_at)
   - `UserReadingProgress` (completed_date)
   - `Sleep` (sleep records)
   - `Weight`, `BloodPressure`, `BloodSugar` (measurement timestamps)
   - `Task` (completed_at)
   - `GameSession` (completed_at)

3. **UserDailyActivity** (`apps/core/models.py`) — Page-level activity tracking
   - first_seen, last_seen, interaction_count per day

**What's MISSING:**

- **No universal "what happened" event log** — Completions exist per-domain but there's no single table/view that answers "What did Danny do today?" across all domains
- **No unified event type taxonomy** — Each domain has its own status/completion semantics
- **No event-level metadata normalization** — Can't query "all health-related events this week" without knowing each domain's schema

**Gap Assessment:** The raw data for "things that happened" exists in every domain. What's missing is a **unified materialized view or projection** — similar to how CalendarEngine projects scheduled items, there's no equivalent that projects completed/actual events.

**Critical Design Question:** Should this be a new model (write-time denormalization) or a query-time aggregation (read-time view)?

---

### Layer 4: Life Signals ⚠️ PARTIALLY EXISTS (Sophisticated but Ephemeral)

**What exists today:**

1. **EAE Signal Collector** (`apps/core/ai_eae/signal_collector.py`):
   - `RawSignal` dataclass with: engine, signal_type, module, score, confidence, severity
   - `RawSignalSet` with drift_risk_severity and capacity_state
   - Collects from: PIE insights, PRIE predictions, PGE guidance, drift/pressure, UAL

2. **SAE State Builders** (`apps/core/ai_state/state_builder.py`):
   - Per-domain state builders that read actual DB records
   - Health: weight_trend, sleep_avg, glucose_avg, workout_count, macro_compliance
   - Faith: reading_streak, active_plans, prayer_counts
   - Goals: active_count, completion_rate, overdue_count
   - Journal: entry_frequency, mood_distribution

3. **Cross-Domain Insight Rules** (`apps/core/ai_insights/rules_cross_domain.py`):
   - MotivationDriftRule (mood ↓ + goals ↓)
   - OvertrainingRiskRule (sleep ↓ + workouts ↑)
   - FinancialAnxietyRule, OverextensionRiskRule, ComplianceRiskRule, BehavioralInstabilityRule

4. **CoSSituationState** — Pre-computed situation assessment every 15 minutes

**What's MISSING:**

- **Signals are ephemeral** — RawSignal is a dataclass, not persisted. Computed on-demand and discarded.
- **No signal history** — Can't answer "How has the health_activity signal trended over 30 days?"
- **No derived signal taxonomy** like the proposed: health_activity, faith_practice, mental_reflection, productivity_progress
- **No NLP-derived signals from journal entries** — Journal entries aren't analyzed for behavioral indicators ("I went for a walk today")

**Gap Assessment:** The signal infrastructure is architecturally sound but ephemeral. The proposed "Life Signals" layer maps to making EAE signals persistent and adding NLP-derived signals from unstructured data (journal entries, capture transcripts).

---

### Layer 5: Goal Momentum Engine ✅ MOSTLY EXISTS

**What exists today:**

**GoalMomentumService** (`apps/dashboard_v2/services/momentum_service.py`) — This is remarkably close to the proposed design:

| Component | Weight | Source | Status |
|-----------|--------|--------|--------|
| Habits | 30% | HabitEntry completion rates + streaks | ✅ Working |
| Tasks | 20% | Domain-linked Task completions (7d) | ✅ Working |
| Domain Signals | 20% | SAE state (workouts, weight, sleep, etc.) | ✅ Working |
| Discipline | 15% | Max streak across habits | ✅ Working |
| Recency | 15% | Exponential decay of last action | ✅ Working |

- Computes per-goal momentum score (0-100)
- Persists nightly via GoalMomentumSnapshot
- Calculates 7-day momentum_trend
- Returns breakdown of "drivers" explaining the score

**What's MISSING:**

- **Domain signal mapping is hardcoded** — Health goals read workout/weight/sleep; Faith goals read reading_streak. But there's no formal "goal → signal source" configuration.
- **No journal/NLP contribution** — "I went for a walk today" in a journal entry doesn't feed health goal momentum
- **No capture/audio contribution** — Transcribed audio doesn't feed any goal
- **Limited cross-domain synergy** — A workout helping BOTH a health goal and a mental health goal simultaneously isn't modeled
- **Task → Goal linkage is weak** — Tasks have a `module` field but no FK to LifeGoal. The momentum service queries tasks by module name matching, not explicit goal linkage.

**Gap Assessment:** The momentum engine exists and works well. Enhancements needed: explicit goal-signal configuration, NLP-derived signal input, and stronger task-to-goal linkage.

---

### Layer 6: AI Reasoning ✅ MOSTLY EXISTS

**What exists today:**

Beth (the AI) already reasons over a comprehensive context:

1. **CoS Context Builder** (`apps/core/ai_orchestrator/cos_context.py`) — Parallel assembly of:
   - Health signals (weight, sleep, vitals, medications, workouts)
   - Goal signals (active goals, deadlines, velocity)
   - Habit signals (streaks, completion rates)
   - Task signals (pending, overdue, completed today)
   - Faith signals (reading progress, prayer)
   - Journal signals (mood, frequency)
   - Situation state (morning/midday/evening mode)

2. **14-Engine Intelligence Pipeline** — Three-phase execution:
   - Phase 1: Semantic understanding, context memory, time resolution
   - Phase 2: Orchestration, intent, execution, safety
   - Phase 3: State awareness, insights, predictions, guidance, learning, briefing, weekly report, explanation

3. **Cross-domain correlation** — 6 insight rules that detect multi-domain patterns

**What's MISSING for the proposed "holistic coaching" scenario:**

> "Danny missed his scheduled workout but walked 6,000 steps and journaled about it. Beth should recognize progress rather than failure."

Current state: Beth CAN access steps data and journal entries via CoS context. But:
- **No compensatory reasoning** — The system fires a "missed workout" insight but doesn't automatically weigh steps as partial compensation
- **No journal NLP** — Journal text isn't parsed for behavioral signals
- **No explicit "commitment vs. actual" comparison** — No model says "planned: workout, actual: walk + journal" and evaluates net outcome
- **Insight rules are threshold-based** — They fire independently, not relationally (e.g., "workout missed BUT steps high" is two separate signals, not one integrated assessment)

**Gap Assessment:** The reasoning infrastructure is strong. The gap is in **relational reasoning** — comparing planned vs. actual across domains and producing net-positive/net-negative assessments rather than per-domain binary evaluations.

---

## Part 2: What Should NOT Be Implemented

### 2a. Do NOT create a new ScheduledCommitment model

**CalendarEngine already IS this.** It has source_type, source_id, status, time fields, and dedup. Creating a parallel model would:
- Duplicate CalendarEngine's purpose
- Create sync headaches between two projection layers
- Add migration complexity for no architectural gain

**Instead:** Extend CalendarEngine to project from medicine schedules, faith routines, and other currently-unrepresented commitment types.

### 2b. Do NOT create a write-time LifeEvent denormalization table

Writing every completion event to a separate table creates:
- Double-write performance cost on every action
- Sync drift risk (domain record says X, event log says Y)
- Schema bloat (metadata varies wildly across domains)

**Instead:** Create a **read-time unified activity view** — a service/query layer that aggregates completed actions from all domain tables with a normalized interface. This preserves single-source-of-truth per domain.

### 2c. Do NOT replace the per-domain SAE state builders

The current state_builder.py pattern (one builder per domain reading actual DB records) is architecturally excellent:
- Each domain owns its schema
- State is always fresh from the database
- No stale cache risk on the state layer
- Easy to add new domains

**Instead:** Enhance the builders to emit additional signal metadata that can be persisted.

### 2d. Do NOT restructure the 14-engine pipeline

The three-phase intelligence pipeline is well-designed and working. Reorganizing it would be high-risk, high-effort with unclear benefit.

**Instead:** Add new capabilities as new rules within existing engines (PIE, PRIE, PGE) and enhance CoS context assembly.

---

## Part 3: Recommended Architecture

### High-Level Architecture (Target State)

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERFACE                         │
│  Dashboard (unified daily view) │ Chat (Beth) │ Mobile   │
└──────────────┬──────────────────┬──────────────┬────────┘
               │                  │              │
┌──────────────▼──────────────────▼──────────────▼────────┐
│              AI REASONING LAYER (Beth/CoS)                │
│  CoS Context │ Situation State │ Relational Reasoning     │
│  Compensatory Logic │ Net-Outcome Assessment              │
└──────────────┬──────────────────────────────────┬────────┘
               │                                  │
┌──────────────▼────────┐    ┌───────────────────▼────────┐
│   SIGNAL LAYER         │    │   GOAL MOMENTUM ENGINE      │
│   (Persistent Signals) │───▶│   Per-goal weighted score   │
│   - Structured events  │    │   Signal→Goal configuration │
│   - NLP-derived signals│    │   Compensatory scoring      │
│   - Cross-domain       │    │   Trend & trajectory        │
└──────────────┬─────────┘    └───────────────────┬────────┘
               │                                  │
┌──────────────▼──────────────────────────────────▼────────┐
│           UNIFIED ACTIVITY VIEW (Read-Time)               │
│  Aggregates completions from all domains                  │
│  Normalized interface: who, what, when, domain, source    │
└──────────────┬──────────────────────────────────┬────────┘
               │                                  │
┌──────────────▼──────────┐    ┌─────────────────▼────────┐
│  COMMITMENT LAYER        │    │   DOMAIN SYSTEMS          │
│  (CalendarEngine+)       │    │   (Source of Truth)        │
│  - Tasks                 │    │   health, faith, journal,  │
│  - Medicine schedules    │    │   life, purpose, finance,  │
│  - Workout plans         │    │   brain_training, capture  │
│  - Faith routines        │    │                            │
│  - Habit reminders       │    │                            │
└──────────────────────────┘    └──────────────────────────┘
```

### Core Design Principles

1. **Domain systems remain source of truth** — No new "event" table duplicates domain data
2. **CalendarEngine is THE commitment layer** — Extend, don't replace
3. **Activity view is read-time, not write-time** — Query aggregation, not denormalization
4. **Signals persist for trend analysis** — New SignalSnapshot model for historical signal tracking
5. **Goal momentum gets explicit signal configuration** — Formal goal→signal mapping
6. **AI reasoning gets relational logic** — Compare planned vs. actual, compensatory scoring

---

## Part 4: Core Models in the Final Architecture

### New Models Needed

```python
# 1. Signal Persistence (apps/core/ai_eae/models.py)
class SignalSnapshot(TimeStampedModel):
    """Persisted signal for historical trending"""
    user = FK(User)
    date = DateField()
    signal_type = CharField()     # e.g., 'health_activity', 'faith_practice'
    domain = CharField()          # e.g., 'health', 'faith', 'journal'
    score = FloatField()          # 0.0-1.0 normalized
    confidence = FloatField()
    source_signals = JSONField()  # Evidence: which raw signals contributed

    class Meta:
        unique_together = ['user', 'date', 'signal_type']
        # One signal per type per day — idempotent upsert

# 2. Goal-Signal Configuration (apps/purpose/models.py)
class GoalSignalSource(TimeStampedModel):
    """Maps which signals feed into a goal's momentum"""
    goal = FK(LifeGoal)
    signal_type = CharField()     # e.g., 'health_activity'
    weight = FloatField()         # 0.0-1.0, relative importance

    class Meta:
        unique_together = ['goal', 'signal_type']

# 3. NLP Signal Extraction (apps/journal/models.py)
class JournalSignal(TimeStampedModel):
    """Behavioral signals extracted from journal text"""
    entry = FK(JournalEntry)
    signal_type = CharField()     # e.g., 'physical_activity_mentioned'
    domain = CharField()          # e.g., 'health', 'faith'
    confidence = FloatField()
    extracted_text = TextField()  # The phrase that triggered the signal

# 4. Daily Commitment Summary (could be a DB view or service)
# NOT a new model — this is a service layer that queries:
# - CalendarEvent (tasks, goals, habits, life events)
# - MedicineSchedule (medication times)
# - WorkoutSchedule (planned workouts)
# - Faith routine flags (prayer reminders, reading plan)
# Returns a unified chronological list for a given date
```

### Models That Get Enhanced (Not New)

```python
# CalendarEngine — add new source types
CalendarEvent.source_type choices += [
    'medicine_schedule',
    'faith_routine',
    'workout_plan',
]

# Task — optional explicit goal linkage
Task.goal = FK(LifeGoal, null=True, blank=True)
# Replaces the current implicit module-name matching

# GoalMomentumSnapshot — add signal breakdown
GoalMomentumSnapshot.signal_scores = JSONField()
# Stores per-signal-type scores for historical analysis
```

---

## Part 5: Data Flow

### How Data Flows in the Target Architecture

```
USER ACTION (or passive data import)
    │
    ▼
DOMAIN SYSTEM records the fact
    │  (e.g., MedicineLog.create(), WorkoutSession.save())
    │
    ├──▶ Django signal fires ──▶ CalendarEngine updates status
    │                            (commitment marked completed)
    │
    ├──▶ SAE state_builder recalculates domain state
    │    (next time CoS context is assembled)
    │
    ├──▶ PIE evaluates insight rules
    │    (fires if threshold met)
    │
    ▼
NIGHTLY BATCH (Celery Beat)
    │
    ├──▶ Signal Aggregation Service
    │    - Reads SAE state for each domain
    │    - Computes normalized daily signals
    │    - Upserts SignalSnapshot rows
    │    - Runs NLP on new journal entries → JournalSignal
    │
    ├──▶ Goal Momentum Service (enhanced)
    │    - Reads GoalSignalSource configs per goal
    │    - Pulls SignalSnapshot scores for each mapped signal
    │    - Computes weighted momentum
    │    - Upserts GoalMomentumSnapshot with signal_scores
    │
    ├──▶ PRIE evaluates predictions
    │    - Goal completion projections
    │    - Signal trend projections
    │
    ▼
REAL-TIME (on dashboard load or chat)
    │
    ├──▶ CoS Context Builder
    │    - Reads current SAE state (live)
    │    - Reads latest SignalSnapshots (historical)
    │    - Reads GoalMomentumSnapshots (trend)
    │    - Reads active Insights, Predictions, Guidance
    │    - Builds DailyCommitmentSummary (read-time aggregation)
    │
    ├──▶ Relational Reasoning (new)
    │    - Compares commitments (planned) vs activity (actual)
    │    - Identifies compensatory behaviors
    │    - Produces net-outcome assessment per domain
    │
    ▼
BETH RESPONDS with holistic awareness
    - "You missed your workout, but your 6,000 steps and
       journal reflection show you're still moving forward."
```

---

## Part 6: Phased Implementation Roadmap

### Phase 1 — Foundation Strengthening (Low Risk, High Value)
**Purpose:** Close the task→goal gap and extend CalendarEngine coverage without new models.

**Changes:**
- Add `goal` FK to Task model (nullable) — explicit task-to-goal linkage
- Add CalendarEngine projection for MedicineSchedule (new source_type)
- Add CalendarEngine projection for faith routines (reading plan, prayer)
- Update GoalMomentumService to use explicit goal FK instead of module-name matching

**Models impacted:** Task (1 field), CalendarEvent (2 new source_type choices)
**Code areas:** `apps/life/models.py`, `apps/calendar_engine/`, `apps/health/signals.py`, `apps/faith/signals.py`, `apps/dashboard_v2/services/momentum_service.py`
**Risks:** Low. Nullable FK is backwards-compatible. CalendarEngine already handles multiple source types.
**Migrations:** 1 migration for Task FK, 0 for CalendarEngine (source_type is a CharField, choices are just validation)

---

### Phase 2 — Unified Daily View (Medium Risk, High Value)
**Purpose:** Build the "daily operating schedule" that shows all commitments chronologically.

**Changes:**
- Create `DailyScheduleService` that queries CalendarEngine + any remaining unrepresented commitments
- Returns normalized list: `[{time, title, domain, source_type, source_id, status, commitment_level}]`
- New dashboard component: chronological daily timeline (replaces/supplements current tile layout)
- Mobile API endpoint for daily schedule

**Models impacted:** None new — this is a service/view layer
**Code areas:** New service in `apps/dashboard/services/`, dashboard template, mobile API
**Risks:** Medium. UI change affects daily user experience. Should be opt-in initially (new dashboard tile, not replacement).
**Migrations:** None

---

### Phase 3 — Signal Persistence (Medium Risk, Medium Value)
**Purpose:** Enable historical signal trending and goal momentum evolution tracking.

**Changes:**
- Create `SignalSnapshot` model
- Create nightly Celery task: `compute_daily_signals`
  - Reads SAE state builders
  - Normalizes into standard signal types: `health_activity`, `faith_practice`, `mental_reflection`, `productivity_progress`, `financial_health`, `cognitive_fitness`
  - Upserts one SignalSnapshot per signal_type per day
- Extend `GoalMomentumSnapshot` with `signal_scores` JSONField
- Add signal trend endpoint for dashboard charts

**Models impacted:** New `SignalSnapshot`, enhanced `GoalMomentumSnapshot`
**Code areas:** `apps/core/ai_eae/`, `apps/dashboard_v2/services/`, new Celery task
**Risks:** Medium. New model + nightly batch job. Must handle missing data gracefully (not all signal types will have data every day).
**Migrations:** 2 migrations (new model, alter existing model)

---

### Phase 4 — Goal-Signal Configuration (Low Risk, Medium Value)
**Purpose:** Let goals explicitly declare which signals matter to them, enabling accurate cross-domain momentum.

**Changes:**
- Create `GoalSignalSource` model
- Auto-populate defaults based on goal's LifeDomain (Health goals get health signals, etc.)
- Allow user/AI customization ("This health goal should also track faith signals")
- Update GoalMomentumService to use GoalSignalSource instead of hardcoded domain mapping
- Add intent handler: "link signal to goal" / "adjust goal signals"

**Models impacted:** New `GoalSignalSource`
**Code areas:** `apps/purpose/`, `apps/dashboard_v2/services/momentum_service.py`, `apps/ai/intents/`
**Risks:** Low. Additive change. Existing momentum calculation continues working with auto-populated defaults.
**Migrations:** 1 migration

---

### Phase 5 — Journal NLP Signals (Medium Risk, High Value)
**Purpose:** Extract behavioral signals from unstructured text (journal entries, capture transcripts).

**Changes:**
- Create `JournalSignal` model
- Create extraction service using existing OpenAI integration
- Extract signals like: physical_activity_mentioned, prayer_mentioned, social_interaction, emotional_state, goal_reference
- Run on journal entry save (async Celery task)
- Feed JournalSignals into SignalSnapshot aggregation
- Feed into GoalMomentumService as an additional signal source

**Models impacted:** New `JournalSignal`
**Code areas:** `apps/journal/`, `apps/ai/`, `apps/core/ai_eae/`
**Risks:** Medium. LLM extraction can be noisy. Needs confidence thresholds and human-verifiable evidence (extracted_text). Cost consideration for OpenAI calls per journal entry.
**Migrations:** 1 migration

---

### Phase 6 — Relational Reasoning for Beth (Higher Risk, Highest Value)
**Purpose:** Enable Beth to compare planned vs. actual and produce holistic assessments.

**Changes:**
- New CoS context section: `daily_commitment_vs_actual`
  - For each commitment today: planned time, actual status, compensatory signals
  - Net domain assessment: positive/negative/neutral
- New PIE rules for compensatory detection:
  - `CompensatoryActivityRule`: missed commitment + alternative positive signal in same domain
  - `HolisticProgressRule`: overall signal trend positive despite individual misses
- Updated system prompt for Beth: reason over commitment-vs-actual, prefer encouragement when net-positive
- New insight type: "compensatory progress" (positive severity)

**Models impacted:** None new — extends existing PIE rules and CoS context
**Code areas:** `apps/core/ai_orchestrator/cos_context.py`, `apps/core/ai_insights/rules_cross_domain.py`, `apps/ai/personal_assistant.py`
**Risks:** Higher. Changes how Beth communicates. Must not dismiss genuine failures. Needs careful prompt engineering and testing.
**Migrations:** None

---

## Part 7: What This Architecture Gets Right (and Risks)

### Strengths of This Approach

1. **No Big Bang** — Every phase is independently valuable and deployable
2. **Domain sovereignty preserved** — No domain loses ownership of its data
3. **CalendarEngine reuse** — Avoids duplicate scheduling infrastructure
4. **Read-time aggregation** — Activity view doesn't require double-writes
5. **Signal persistence is opt-in** — Existing real-time signal flow continues working; persistence adds trending
6. **Goal momentum evolves, not replaces** — GoalMomentumService already works; enhancements are additive
7. **AI reasoning enhancement is prompt-level** — No engine restructuring needed

### Risks to Monitor

1. **CalendarEngine scope creep** — Adding medicine/faith/workout projections increases its surface area. Need clear projection contracts.
2. **Signal normalization challenge** — Defining what "health_activity = 0.7" means across heterogeneous data (steps, workouts, glucose) requires careful calibration.
3. **NLP signal noise** — Journal text extraction will produce false positives. Confidence thresholds and human review needed.
4. **Momentum gaming** — If users learn the momentum formula, they might optimize for score rather than actual progress. Keep scoring opaque.
5. **Performance** — Nightly batch jobs must complete within reasonable time. Signal aggregation across all domains for all users could be heavy. Implement user-level batching.
6. **Compensatory reasoning edge cases** — "Missed workout but walked" is positive. "Missed medication but felt fine" is NOT positive. Domain-specific safety rules needed.

---

## Part 8: Decision Points for Danny

Before implementation begins, these decisions need human input:

### Decision 1: Activity View — Service vs. Materialized Model?
- **Option A (Recommended):** Read-time service that queries domain tables and returns normalized list. No new model. Always fresh.
- **Option B:** Write-time denormalization into a `CompletedActivity` table via Django signals. Faster reads, but sync risk.

### Decision 2: Signal Taxonomy — How Many Signal Types?
- **Minimal (6):** health_activity, faith_practice, mental_reflection, productivity_progress, financial_health, cognitive_fitness
- **Detailed (15+):** Break health into exercise, nutrition, sleep, medication_adherence, etc. More granular momentum but more complex.

### Decision 3: Journal NLP — Per-Entry or Batch?
- **Per-entry (Recommended):** Process on save via async Celery task. Near-real-time signals.
- **Batch:** Nightly processing of all new entries. Simpler but delayed signals.

### Decision 4: Goal-Signal Configuration — AI-Managed or User-Managed?
- **AI-managed (Recommended):** Beth auto-configures signal sources when goals are created based on domain + goal description. User can override.
- **User-managed:** User explicitly selects which signals matter for each goal. More control but higher friction.

### Decision 5: Daily View — Replace Dashboard or Add To It?
- **Add (Recommended):** New "Daily Schedule" tile/tab alongside existing dashboard tiles. Gradual transition.
- **Replace:** Rebuild dashboard around chronological timeline as primary view. Higher risk, higher reward.

---

## Summary Table

| Proposed Layer | Current Status | Recommendation |
|---------------|---------------|----------------|
| Domain Systems | ✅ Complete | No changes needed |
| Scheduled Commitments | ⚠️ 80% (CalendarEngine) | Extend CalendarEngine to cover medicine, faith, workouts |
| Life Events (what happened) | ⚠️ Data exists, no unified view | Read-time aggregation service, NOT new model |
| Life Signals | ⚠️ Exists but ephemeral | Add SignalSnapshot persistence + NLP extraction |
| Goal Momentum | ✅ 85% (GoalMomentumService) | Add explicit signal config + NLP input |
| AI Reasoning | ✅ 90% (14-engine pipeline) | Add relational/compensatory reasoning to CoS |

**Total estimated new models: 3** (SignalSnapshot, GoalSignalSource, JournalSignal)
**Total estimated model enhancements: 3** (Task FK, GoalMomentumSnapshot JSONField, CalendarEvent source_type choices)
**Total estimated migrations: ~5-6** across all phases

---

*This assessment is based on deep analysis of the current codebase as of 2026-03-14. It should be reviewed by Danny and the ChatGPT architecture partner before any implementation begins.*
