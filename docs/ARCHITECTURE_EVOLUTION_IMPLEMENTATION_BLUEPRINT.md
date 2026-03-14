# WLJ Architecture Evolution — Implementation Blueprint

**Date:** 2026-03-14
**Status:** Implementation plan — pending phase-by-phase approval
**Reference:** docs/ARCHITECTURE_EVOLUTION_FINAL.md (canonical architecture)

---

## Overview

This blueprint defines the incremental implementation of the WLJ five-layer architecture across 8 phases. Each phase is independently deployable and valuable. No phase requires the subsequent phases to be useful.

**Total new models:** 5
**Total model enhancements:** 5
**Total estimated migrations:** 8–10
**Total new services:** 5
**Total new Celery tasks:** 2

---

## Phase 1 — Foundation

### Purpose
Establish structural links between tasks/habits and goals, extend CalendarEngine to project medicine, faith, and workout commitments, and standardize commitment importance.

### Models Introduced

**TaskGoalLink** (`apps/life/models.py`)
```python
class TaskGoalLink(TimeStampedModel):
    task = ForeignKey('life.Task', on_delete=CASCADE, related_name='goal_links')
    goal = ForeignKey('purpose.LifeGoal', on_delete=CASCADE, related_name='task_links')

    class Meta:
        unique_together = ['task', 'goal']
```

**HabitGoalLink** (`apps/purpose/models.py`)
```python
class HabitGoalLink(TimeStampedModel):
    habit = ForeignKey('purpose.HabitGoal', on_delete=CASCADE, related_name='goal_links')
    goal = ForeignKey('purpose.LifeGoal', on_delete=CASCADE, related_name='habit_links')

    class Meta:
        unique_together = ['habit', 'goal']
```

### Model Enhancements

**CalendarEvent** (`apps/calendar_engine/models.py`)
- Add `commitment_level` CharField (optional/important/non_negotiable, default='important')
- Add source_type choices: `medicine_schedule`, `faith_routine`, `workout_schedule`

**HabitGoal** (`apps/purpose/models.py`)
- Add `commitment_level` CharField (optional/important/non_negotiable, default='important')

### Migrations Required
1. `apps/life/0XXX_create_taskgoallink.py` — New TaskGoalLink table
2. `apps/purpose/0XXX_create_habitgoallink_add_commitment_level.py` — New HabitGoalLink table + HabitGoal.commitment_level
3. `apps/calendar_engine/0XXX_add_commitment_level_source_types.py` — CalendarEvent.commitment_level

### Services Introduced

**Medicine Projection** (`apps/calendar_engine/services/projection.py`)
- `upsert_from_medicine_schedule(schedule)` — Project daily dose instances
- `delete_medicine_events(schedule)` — Remove events on schedule deactivation
- Medicine schedules project as `execution_block` with `commitment_level='non_negotiable'`
- Creates one CalendarEvent per active MedicineSchedule per applicable day
- Title format: "Take {medicine.name} {medicine.dosage}" (e.g., "Take Metformin 500mg")
- Status updated from MedicineLog: taken → completed, missed → canceled

**Faith Projection** (`apps/calendar_engine/services/projection.py`)
- `upsert_from_faith_routine(plan_day)` — Project daily reading/prayer instances
- `delete_faith_events(plan)` — Remove events on plan deactivation
- Faith routines project as `execution_block` with `commitment_level='important'`
- For reading plans: title from ReadingPlanDay scripture references
- For prayer: project from HabitGoal entries where domain=faith

**Workout Projection** (`apps/calendar_engine/services/projection.py`)
- `upsert_from_workout_schedule(schedule)` — Project daily workout instances
- `delete_workout_events(schedule)` — Remove events on schedule deactivation
- Workouts project as `execution_block` with `commitment_level='important'`
- Title from WorkoutTemplate name; time from WorkoutSchedule.preferred_time

### Signal Handlers

**New signal handlers:**
- `apps/health/signals.py` — `post_save` on MedicineSchedule → `upsert_from_medicine_schedule()`
- `apps/health/signals.py` — `post_save` on MedicineLog → Update CalendarEvent status
- `apps/health/signals.py` — `post_save`/`post_delete` on WorkoutSchedule → projection lifecycle
- `apps/faith/signals.py` — `post_save` on UserReadingPlan/UserReadingProgress → projection lifecycle

### Code Areas Impacted
- `apps/calendar_engine/models.py` — Field additions
- `apps/calendar_engine/services/projection.py` — New projection functions
- `apps/calendar_engine/utils/idempotency.py` — New source type handling
- `apps/life/models.py` — TaskGoalLink model
- `apps/purpose/models.py` — HabitGoalLink model, HabitGoal field
- `apps/health/signals.py` — Medicine and workout projection signal handlers
- `apps/faith/signals.py` — Faith projection signal handlers
- `apps/life/signals.py` — Task projection: copy commitment_level to CalendarEvent
- `apps/purpose/signals.py` — Goal/Habit projection: copy commitment_level to CalendarEvent

### Testing Strategy
- Unit tests for each projection function (create, update, delete lifecycle)
- Unit tests for idempotency (duplicate projection doesn't create duplicates)
- Unit tests for commitment_level propagation (source → CalendarEvent)
- Integration tests for signal handler → projection flow
- Verify existing CalendarEngine projections (task, goal, habit) still work unchanged
```bash
python3 manage.py test apps.calendar_engine apps.life.tests apps.purpose.tests apps.health.tests -v 1 --failfast
```

### Rollback Safety
- All new models are additive (new tables, no schema changes to existing data)
- CalendarEvent.commitment_level defaults to 'important' — existing events unaffected
- New source_type choices are additive — existing choices unchanged
- Rollback: drop new tables, remove new field. Existing data untouched.

### Performance Considerations
- Medicine projection for a user with 10 medications × 3 daily doses = 30 CalendarEvents per day — trivial
- Signal handlers fire on save, not in batch — acceptable since projections are single-row upserts
- Index on `(user, source_type, source_id)` already exists for fast lookups

### Documentation Updates
- Update `docs/ENGINE_COS_REFERENCE.md` — New CalendarEngine source types
- Changelog entry in `docs/wlj_claude_changelog.md`
- Release notes in `apps/core/fixtures/release_notes.json`

---

## Phase 2 — Unified Daily View

### Purpose
Build service layers that aggregate today's commitments and today's activity into normalized interfaces, enabling the dashboard to show a chronological daily timeline.

### Models Introduced
None. This phase is service and view layer only.

### Services Introduced

**DailyScheduleService** (`apps/dashboard/services/daily_schedule_service.py`)
```python
class DailyScheduleService:
    @staticmethod
    def get_daily_schedule(user, date) -> list[dict]:
        """Returns chronological list of all commitments for a date.
        Each item: {
            time: datetime,
            end_time: datetime | None,
            title: str,
            domain: str,           # From LifeDomainEnum
            source_type: str,
            source_id: str,
            commitment_level: str,
            status: str,           # scheduled / completed / canceled
            event_kind: str,
        }
        """
```

Queries CalendarEngine for the given date. Includes:
- Direct CalendarEvent records (tasks, goals, medicine, faith, workouts, life events)
- RecurrenceRule-generated occurrences for habits and recurring events
- Sorted by time ascending, with all-day events first

**DailyActivityService** (`apps/dashboard/services/daily_activity_service.py`)
```python
class DailyActivityService:
    @staticmethod
    def get_daily_activity(user, date) -> list[dict]:
        """Returns chronological list of all completed actions for a date.
        Each item: {
            timestamp: datetime,
            title: str,
            domain: str,           # From LifeDomainEnum
            source_type: str,
            source_id: str,
            signal_class: str,     # verified_action, verified_measurement
        }
        """
```

Queries each domain's completion records:
- Task.objects.filter(user=user, completed_at__date=date)
- MedicineLog.objects.filter(user=user, scheduled_date=date, log_status='taken')
- WorkoutSession.objects.filter(user=user, date=date)
- HabitEntry.objects.filter(user=user, date=date, completed=True)
- UserReadingProgress.objects.filter(user=user, completed_date=date)
- JournalEntry.objects.filter(user=user, created_at__date=date)
- Weight/BloodSugar/BloodPressure entries for the date
- GameSession.objects.filter(user=user, completed_at__date=date, status='completed')

Each record is normalized to the standard interface with signal_class assigned based on source type.

### Code Areas Impacted
- `apps/dashboard/services/` — New service files
- `apps/dashboard/views.py` — Add daily schedule/activity data to dashboard context
- `templates/dashboard/` — New daily timeline component (or new dashboard tile)
- `apps/mobile/api/` — New API endpoint for mobile daily view
- `apps/core/ai_orchestrator/cos_context.py` — CoS can use DailyScheduleService + DailyActivityService for commitment-vs-actual comparison

### Testing Strategy
- Unit tests for each service method with fixture data
- Test each domain's completion record aggregation independently
- Test chronological sorting with mixed domain sources
- Test empty day (no commitments, no activity)
- Test timezone handling (user in different timezone)
```bash
python3 manage.py test apps.dashboard.tests -v 1 --failfast
```

### Rollback Safety
- No model changes — pure service/view layer
- New dashboard tile can be opt-in via dashboard tile configuration
- Rollback: remove service files and template, revert dashboard view changes

### Performance Considerations
- DailyActivityService queries ~8 domain tables per call. Each query is filtered by user + date with indexes.
- Cache daily schedule for 5 minutes (invalidated on CalendarEvent changes via existing cache invalidation)
- Cache daily activity for 5 minutes (invalidated on relevant domain model saves)
- Consider `select_related`/`prefetch_related` for domain queries that need FK data

### Documentation Updates
- Changelog entry
- Release notes: "New daily timeline view"
- Help topics if new UI is user-facing

---

## Phase 3 — Signal Taxonomy Design

### Purpose
Define the complete signal taxonomy, classification rules, and normalization approach before building the persistence layer. This is a **design document phase** — no code changes.

### Deliverable
`docs/SIGNAL_TAXONOMY.md` containing:

1. **Signal type definitions** — Each of the 10 signal types with:
   - Name, domain, description
   - Data sources (which domain models feed it)
   - Normalization formula (how raw values map to 0.0–1.0)
   - Default signal_class for each source

2. **Signal class assignment rules** — Decision tree for classifying signals:
   - Source model → signal_class mapping table
   - Edge cases (e.g., HealthKit sleep data = verified_measurement, manual sleep entry = verified_action)

3. **Normalization baselines** — Fixed baseline values for initial launch:
   - Per-signal-type 0.0, 0.5, 1.0 reference points
   - Interpolation method (linear between reference points)
   - Handling of missing data (no data for a signal type on a given day)

4. **Aggregation rules** — When a signal type has multiple sources for one day:
   - How to combine (max, average, weighted)
   - How to handle mixed signal_class (e.g., both verified and inferred sources)

### Models Introduced
None.

### Code Areas Impacted
None — document only.

### Testing Strategy
Review document against actual database content to verify:
- Every proposed data source exists in the codebase
- Every proposed normalization formula produces valid 0.0–1.0 output for realistic data ranges
- Signal type names don't conflict with existing naming conventions

### Rollback Safety
N/A — document only.

---

## Phase 4 — Signal Persistence

### Purpose
Implement the SignalSnapshot model and nightly aggregation task that computes and persists daily signal values.

### Models Introduced

**SignalSnapshot** (`apps/core/ai_eae/models.py`)
```python
class SignalSnapshot(TimeStampedModel):
    user = ForeignKey(User, on_delete=CASCADE, related_name='signal_snapshots')
    date = DateField()
    signal_type = CharField(max_length=30)
    domain = CharField(max_length=20)
    signal_class = CharField(max_length=25)
    score = FloatField()
    confidence = FloatField()
    source_signals = JSONField(default=dict)

    class Meta:
        unique_together = ['user', 'date', 'signal_type']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'signal_type', 'date']),
        ]
```

### Model Enhancements

**RawSignal dataclass** (`apps/core/ai_eae/signal_collector.py`)
- Add `signal_class: str = ''` field

### Migrations Required
1. `apps/core/0XXX_create_signalsnapshot.py` — New SignalSnapshot table

### Services Introduced

**SignalAggregationService** (`apps/core/ai_eae/signal_aggregation.py`)
```python
class SignalAggregationService:
    @staticmethod
    def compute_daily_signals(user, date) -> list[SignalSnapshot]:
        """Compute all signal types for a user for a date.
        Uses DailyActivityService + SAE state builders.
        Returns list of upserted SignalSnapshot records."""

    @staticmethod
    def normalize_score(signal_type, raw_value) -> float:
        """Map raw metric to 0.0-1.0 using taxonomy baselines."""

    @staticmethod
    def determine_signal_class(source_type, source_model) -> str:
        """Classify signal based on data source."""
```

### Celery Tasks

**compute_nightly_signals** (`apps/core/ai_eae/tasks.py`)
```python
@shared_task
def compute_nightly_signals():
    """Run nightly. Compute and persist signal snapshots for all active users for today."""
```

- Schedule: Daily at 11:30 PM (after most daily activity is recorded)
- Iterates active users, calls `SignalAggregationService.compute_daily_signals(user, today)`
- Uses `update_or_create` with `unique_together` for idempotency
- Logs per-user success/failure, does not halt batch on individual failure

### Code Areas Impacted
- `apps/core/ai_eae/models.py` — New model
- `apps/core/ai_eae/signal_collector.py` — Add signal_class to RawSignal dataclass
- `apps/core/ai_eae/signal_aggregation.py` — New service
- `apps/core/ai_eae/tasks.py` — New Celery task
- `config/settings.py` — Add to CELERY_BEAT_SCHEDULE
- `apps/core/ai_eae/admin.py` — Admin registration for SignalSnapshot

### Testing Strategy
- Unit tests for each signal type's normalization formula
- Unit tests for signal_class assignment logic
- Unit tests for aggregation with mixed sources
- Integration test: create domain records → run aggregation → verify SignalSnapshot rows
- Test idempotency: running aggregation twice for same date produces same results
- Test missing data: user with no activity for a signal type → no snapshot (not score=0)
```bash
python3 manage.py test apps.core.ai_eae.tests -v 1 --failfast
```

### Rollback Safety
- New table only — drop table to rollback
- Celery task can be disabled in CELERY_BEAT_SCHEDULE without code changes
- No existing functionality depends on SignalSnapshot

### Performance Considerations
- Nightly batch for N users × 10 signal types = 10N rows per night
- Each user's computation queries DailyActivityService (8 domain queries) + SAE state
- For 1 user: <500ms. For 100 users: batch with 100ms delay between users = ~15 seconds total
- SignalSnapshot table grows at ~10 rows/user/day. At 1 user, 365 days = 3,650 rows — trivial
- Add periodic cleanup (retain 1 year of signal history, archive older)

### Documentation Updates
- Update `docs/ENGINE_COS_REFERENCE.md` — Signal persistence layer
- Changelog entry

---

## Phase 5 — Goal-Signal Configuration

### Purpose
Introduce explicit goal-to-signal weighting configuration and integrate with GoalMomentumService.

### Models Introduced

**GoalSignalSource** (`apps/purpose/models.py`)
```python
class GoalSignalSource(TimeStampedModel):
    goal = ForeignKey('purpose.LifeGoal', on_delete=CASCADE, related_name='signal_sources')
    signal_type = CharField(max_length=30)
    weight = FloatField()

    class Meta:
        unique_together = ['goal', 'signal_type']
```

### Model Enhancements

**GoalMomentumSnapshot** (`apps/dashboard_v2/models.py`)
- Add `signal_scores` JSONField (default=dict) — Stores per-signal-type scores for historical analysis

### Migrations Required
1. `apps/purpose/0XXX_create_goalsignalsource.py` — New table
2. `apps/dashboard_v2/0XXX_add_signal_scores_to_momentum.py` — New field

### Services Introduced

**GoalSignalConfigService** (`apps/purpose/services/goal_signal_config.py`)
```python
class GoalSignalConfigService:
    @staticmethod
    def auto_populate(goal) -> list[GoalSignalSource]:
        """Create default GoalSignalSource records based on goal's domain."""

    @staticmethod
    def get_signal_weights(goal) -> dict[str, float]:
        """Return {signal_type: weight} mapping for a goal."""
```

### Changes to Existing Services

**GoalMomentumService** (`apps/dashboard_v2/services/momentum_service.py`)
- Replace hardcoded domain → signal mapping with GoalSignalSource lookups
- Pull signal scores from SignalSnapshot (7-day window) instead of computing inline
- Store signal_scores breakdown in GoalMomentumSnapshot

### Signal Handlers
- `post_save` on LifeGoal → `GoalSignalConfigService.auto_populate()` (only if no existing sources)

### Code Areas Impacted
- `apps/purpose/models.py` — New model
- `apps/purpose/services/goal_signal_config.py` — New service
- `apps/purpose/signals.py` — Auto-populate on goal creation
- `apps/dashboard_v2/models.py` — Field addition
- `apps/dashboard_v2/services/momentum_service.py` — Refactor to use SignalSnapshot + GoalSignalSource
- `apps/ai/intents/purpose_intents.py` — Optional: intent for "adjust goal signal weights"
- `apps/ai/action_handlers.py` — Optional: handler for signal weight adjustment

### Testing Strategy
- Unit tests for auto-population (each domain produces correct defaults)
- Unit tests for momentum calculation with GoalSignalSource weights
- Integration test: create goal → auto-populate → compute momentum → verify breakdown
- Regression test: existing GoalMomentumService behavior matches for goals with default configs
```bash
python3 manage.py test apps.purpose.tests apps.dashboard_v2.tests -v 1 --failfast
```

### Rollback Safety
- New table + new field — both additive
- GoalMomentumService can fall back to existing hardcoded logic if GoalSignalSource is empty
- Rollback: revert momentum service changes, drop new table/field

### Performance Considerations
- GoalSignalSource is ~3-5 rows per goal — negligible
- Momentum computation now reads SignalSnapshot instead of querying domain tables directly — should be faster (single table vs 8 domain tables)
- Cache GoalSignalSource per goal (invalidate on save) — small dataset, fast lookup

### Documentation Updates
- Update `docs/ENGINE_COS_REFERENCE.md` — Goal momentum architecture
- Changelog entry
- Release notes: "Goal momentum now tracks cross-domain signals"

---

## Phase 6 — Compensatory Reasoning Engine

### Purpose
Enable Beth to compare planned commitments vs actual activity and produce safe, hedged compensatory analysis using verified signals only.

### Models Introduced
None. Compensatory rules are code-defined (not database-driven) for auditability.

### Services Introduced

**CompensatoryReasoningService** (`apps/core/ai_insights/compensatory.py`)
```python
class CompensatoryReasoningService:
    # Constants
    NON_COMPENSABLE_RULES = { ... }
    COMPENSATORY_PAIRS = [ ... ]

    @staticmethod
    def analyze_commitment_gap(user, date) -> list[dict]:
        """Compare DailyScheduleService (planned) vs DailyActivityService (actual).
        Returns list of gap analyses:
        {
            commitment: {...},           # The missed commitment
            compensating_signals: [...], # Signals that partially offset
            net_assessment: str,         # 'positive_partial', 'negative', 'neutral'
            offset_pct: float,           # 0.0-1.0 actual offset achieved
            framing: str,               # Pre-built text for Beth
            is_compensable: bool,        # False for non-negotiable/medication
        }
        """

    @staticmethod
    def _check_non_compensable(commitment) -> bool:
        """Hard gate: returns True if commitment cannot be compensated."""

    @staticmethod
    def _find_compensating_signals(missed_domain, missed_signal, user, date) -> list:
        """Find allowlisted compensating signals with verified signal_class."""
```

### New PIE Rules

**CompensatoryProgressRule** (`apps/core/ai_insights/rules_compensatory.py`)
- Fires when compensatory analysis finds positive partial offset
- Insight severity: `positive`
- Insight type: `compensatory_progress`
- Evidence: missed commitment + compensating signals + offset_pct

### Code Areas Impacted
- `apps/core/ai_insights/compensatory.py` — New service
- `apps/core/ai_insights/rules_compensatory.py` — New PIE rule
- `apps/core/ai_insights/rule_registry.py` — Register new rule
- `apps/core/ai_orchestrator/cos_context.py` — Add `daily_commitment_gap` section to CoS context
- `apps/ai/personal_assistant.py` — Add compensatory reasoning rules to Beth's system prompt

### Testing Strategy
- Unit tests for non-compensable hard gate (medication NEVER produces offset)
- Unit tests for each compensatory pair (verify max_offset_pct respected)
- Unit tests for signal_class gating (inferred_behavior rejected where not in requires_signal_class)
- Unit tests for unlisted pairs (no offset produced)
- Unit tests for non_negotiable commitment_level (never compensable regardless of domain)
- Integration test: create missed workout + step data → verify compensatory analysis
- Negative test: create missed medication + any signal → verify NO compensatory analysis
- Beth prompt test: verify framing output matches expected language rules
```bash
python3 manage.py test apps.core.ai_insights.tests -v 1 --failfast
```

### Rollback Safety
- No model changes — pure service/rule layer
- New PIE rule can be disabled in rule_registry without code removal
- CoS context section is additive — Beth ignores missing sections gracefully
- Rollback: remove rule from registry, remove CoS context section

### Performance Considerations
- Compensatory analysis runs on dashboard load or chat (part of CoS context build)
- Calls DailyScheduleService + DailyActivityService (already cached from Phase 2)
- Allowlist lookup is in-memory constant — O(1)
- Typically 0-3 missed commitments per day → 0-3 compensatory analyses — negligible

### Documentation Updates
- Update `docs/ENGINE_COS_REFERENCE.md` — Compensatory reasoning
- Changelog entry
- Release notes: "Beth now recognizes partial progress when commitments are missed"

---

## Phase 7 — Journal NLP Integration

### Purpose
Extract behavioral signals from journal entries and capture transcripts, feeding inferred_behavior signals into the signal persistence layer.

### Models Introduced

**JournalSignal** (`apps/journal/models.py`)
```python
class JournalSignal(TimeStampedModel):
    entry = ForeignKey('journal.JournalEntry', on_delete=CASCADE, related_name='signals')
    signal_type = CharField(max_length=30)
    domain = CharField(max_length=20)
    confidence = FloatField()
    extracted_text = TextField()

    class Meta:
        indexes = [
            models.Index(fields=['entry', 'signal_type']),
        ]
```

### Migrations Required
1. `apps/journal/0XXX_create_journalsignal.py` — New table

### Services Introduced

**JournalSignalExtractor** (`apps/journal/services/signal_extractor.py`)
```python
class JournalSignalExtractor:
    @staticmethod
    def extract_signals(entry) -> list[JournalSignal]:
        """Use OpenAI to extract behavioral signals from journal text.
        Returns list of created JournalSignal records."""

    EXTRACTION_PROMPT = """
    Analyze this journal entry and identify any behavioral signals.
    For each signal found, return:
    - signal_type: one of [health_activity, faith_practice, mental_reflection, ...]
    - domain: the life domain
    - confidence: 0.0-1.0 how confident you are this behavior occurred
    - extracted_text: the exact phrase that indicates the behavior
    Only return signals with confidence >= 0.5.
    Do NOT infer behaviors that are not explicitly described.
    """
```

### Celery Tasks

**extract_journal_signals** (`apps/journal/tasks.py`)
```python
@shared_task
def extract_journal_signals(entry_id):
    """Async task: extract signals from a single journal entry."""
```

- Triggered by `post_save` signal on JournalEntry (async via Celery)
- Skips entries shorter than 20 words (insufficient text for meaningful extraction)
- Skips entries that already have JournalSignal records (idempotency)
- Stores results in JournalSignal table

### Integration with Signal Persistence

**SignalAggregationService** (Phase 4) updated to:
- Query JournalSignal for the date
- Include in relevant signal type aggregation (e.g., health_activity if journal mentions exercise)
- Set `signal_class='inferred_behavior'` for journal-sourced signals
- Apply confidence discount: journal signal confidence × 0.7 (reduced trust for inferred data)

### Code Areas Impacted
- `apps/journal/models.py` — New model
- `apps/journal/services/signal_extractor.py` — New service
- `apps/journal/tasks.py` — New Celery task
- `apps/journal/signals.py` — Trigger extraction on JournalEntry save
- `apps/core/ai_eae/signal_aggregation.py` — Include JournalSignal in aggregation
- `apps/core/ai_insights/compensatory.py` — Compensatory pairs with `inferred_behavior` now have data to work with

### Testing Strategy
- Unit tests for extraction prompt (mock OpenAI, verify signal parsing)
- Unit tests for confidence threshold (signals below 0.5 rejected)
- Unit tests for idempotency (re-running on same entry doesn't duplicate)
- Unit tests for signal aggregation with journal signals (verify signal_class='inferred_behavior')
- Integration test: create journal entry → trigger extraction → verify JournalSignal records → run signal aggregation → verify SignalSnapshot includes inferred signals
- Cost test: verify short entries (<20 words) skip OpenAI call
```bash
python3 manage.py test apps.journal.tests apps.core.ai_eae.tests -v 1 --failfast
```

### Rollback Safety
- New table only — drop table to rollback
- Celery task can be disabled without affecting existing functionality
- Signal aggregation falls back to verified-only if no JournalSignal records exist
- OpenAI calls are isolated in async task — failure doesn't affect journal entry creation

### Performance Considerations
- OpenAI call per journal entry: ~500ms, ~$0.005 per entry (gpt-4o-mini)
- Async via Celery — no impact on journal save latency
- Typical user: 0-2 journal entries per day = $0.01/day max
- JournalSignal table: ~3-5 signals per entry × 365 entries/year = ~1,500 rows/year — trivial

### Documentation Updates
- Changelog entry
- Release notes: "Beth now understands behavioral context from your journal entries"
- Help topic update for journal feature

---

## Phase 8 — Beth Reasoning Upgrade

### Purpose
Upgrade Beth's reasoning to use signal_class-aware framing, relational analysis across all signal types (verified + inferred), and holistic coaching.

### Models Introduced
None.

### Changes to CoS Context Assembly

**`apps/core/ai_orchestrator/cos_context.py`:**

New context sections:
```python
def _build_signal_aware_context(user) -> dict:
    """Assemble signal data with trust classification for Beth."""
    return {
        'daily_signals': [
            {
                'signal_type': s.signal_type,
                'domain': s.domain,
                'score': s.score,
                'signal_class': s.signal_class,
                'confidence': s.confidence,
                'trend_7d': _compute_trend(user, s.signal_type, 7),
            }
            for s in SignalSnapshot.objects.filter(user=user, date=today)
        ],
        'goal_momentum': [
            {
                'goal_title': g.title,
                'momentum_score': snapshot.momentum_score,
                'momentum_trend': snapshot.momentum_trend,
                'signal_breakdown': snapshot.signal_scores,
                'commitment_level': g.commitment_level,
            }
            for g, snapshot in goal_momentum_pairs
        ],
        'commitment_gap': CompensatoryReasoningService.analyze_commitment_gap(user, today),
    }
```

### Changes to Beth's System Prompt

**`apps/ai/personal_assistant.py`:**

Add signal-class-aware framing rules:
```
SIGNAL TRUST RULES:
- verified_action: State as fact. "You completed your workout."
- verified_measurement: State as fact with source. "Your glucose was 105 mg/dL."
- inferred_behavior: Hedge. "It sounds like you went for a walk based on your journal."
- derived_pattern: Frame as observation. "Your health momentum has been trending up."
- NEVER state inferred_behavior or derived_pattern as verified fact.

COMPENSATORY REASONING RULES:
- Frame as: "While you missed X, you still showed progress through Y."
- NEVER: "It's okay you missed X."
- NEVER apply to medication or non-negotiable commitments.
- Maximum language: "partially offset" — never "fully replaced."
- If compensating signal is inferred_behavior, double-hedge.
- Always end with forward guidance.

HOLISTIC COACHING RULES:
- Reference goal momentum trends, not just daily snapshots.
- Acknowledge cross-domain progress. "Your faith practice is supporting your mental health goal."
- When momentum is declining, identify the specific signal driving the decline.
- When momentum is improving, celebrate the specific behaviors driving it.
```

### Code Areas Impacted
- `apps/core/ai_orchestrator/cos_context.py` — New context sections
- `apps/ai/personal_assistant.py` — System prompt additions
- `apps/ai/views.py` — Ensure both streaming and non-streaming paths receive new context

### Testing Strategy
- Unit tests for signal-aware context assembly (verify signal_class flows through)
- Unit tests for trend computation (7-day window)
- Integration test: full CoS context build with signals, momentum, and compensatory data
- Prompt validation: review Beth's responses against known scenarios:
  - Missed workout + high steps → positive partial framing
  - Missed medication → no compensatory framing
  - High momentum trend → celebration
  - Declining momentum → specific signal identified
- Verify streaming and non-streaming parity
```bash
python3 manage.py test apps.core.ai_orchestrator.tests apps.ai.tests -v 1 --failfast
```

### Rollback Safety
- No model changes — prompt and context assembly changes only
- CoS context is additive — if new sections fail, existing sections still work
- System prompt changes can be reverted with a single commit
- Beth's existing behavior is preserved for signals/contexts not covered by new rules

### Performance Considerations
- Signal-aware context adds ~1 additional query (SignalSnapshot for today)
- Goal momentum data is already cached via GoalMomentumSnapshot
- Compensatory analysis is lightweight (in-memory allowlist lookup + cached services)
- Total CoS context size increase: ~500-800 tokens — within budget

### Documentation Updates
- Update `docs/ENGINE_COS_REFERENCE.md` — Full Beth reasoning architecture
- Changelog entry
- Release notes: "Beth now provides holistic, signal-aware coaching"
- Update `docs/INTELLIGENCE_ARCHITECTURE.md` — New signal and reasoning layers

---

## Cross-Phase Summary

### Migration Count by Phase

| Phase | Migrations | New Tables | Altered Tables |
|-------|-----------|------------|---------------|
| 1 | 3 | 2 (TaskGoalLink, HabitGoalLink) | 2 (CalendarEvent, HabitGoal) |
| 2 | 0 | 0 | 0 |
| 3 | 0 | 0 | 0 |
| 4 | 1 | 1 (SignalSnapshot) | 0 |
| 5 | 2 | 1 (GoalSignalSource) | 1 (GoalMomentumSnapshot) |
| 6 | 0 | 0 | 0 |
| 7 | 1 | 1 (JournalSignal) | 0 |
| 8 | 0 | 0 | 0 |
| **Total** | **7** | **5** | **3** |

### Celery Tasks by Phase

| Phase | Task | Schedule |
|-------|------|----------|
| 4 | compute_nightly_signals | Daily 11:30 PM |
| 7 | extract_journal_signals | On JournalEntry save (async) |

### Service Layer by Phase

| Phase | Service | Location |
|-------|---------|----------|
| 2 | DailyScheduleService | apps/dashboard/services/ |
| 2 | DailyActivityService | apps/dashboard/services/ |
| 4 | SignalAggregationService | apps/core/ai_eae/ |
| 5 | GoalSignalConfigService | apps/purpose/services/ |
| 6 | CompensatoryReasoningService | apps/core/ai_insights/ |
| 7 | JournalSignalExtractor | apps/journal/services/ |

### Risk Assessment by Phase

| Phase | Risk Level | Primary Risk |
|-------|-----------|-------------|
| 1 | Low | Signal handler proliferation — mitigated by projection contracts |
| 2 | Low | No model changes, service layer only |
| 3 | None | Document only |
| 4 | Medium | Signal normalization calibration — mitigated by fixed baselines |
| 5 | Medium | Momentum calculation regression — mitigated by fallback to existing logic |
| 6 | Medium | Compensatory reasoning edge cases — mitigated by allowlist + hard gates |
| 7 | Medium | NLP extraction noise — mitigated by confidence thresholds + signal_class |
| 8 | Medium | Beth behavior change — mitigated by prompt-level changes only, no engine restructuring |

---

## LifeDomain Fixture Alignment

Before Phase 1 begins, verify the existing LifeDomain fixture records align with the standardized enumeration:

| Enum Value | Expected LifeDomain Record | Verify Exists |
|-----------|--------------------------|--------------|
| health | Health | ☐ |
| faith | Faith | ☐ |
| mind | Mind (may need to add — currently might not exist as distinct domain) | ☐ |
| relationships | Relationships (may be "Family" — verify) | ☐ |
| work | Work | ☐ |
| finance | Finance/Finances | ☐ |
| life | Life/Personal | ☐ |

If any are missing or named differently, a data migration in Phase 1 should align them.

---

## Implementation Protocol

For each phase:
1. Read this blueprint and the architecture lock document
2. Implement changes
3. Run scoped tests (specified per phase)
4. Run `python3 manage.py makemigrations --check --dry-run` if models were touched
5. Update changelog
6. Update release notes if user-facing
7. Commit, merge to main, push
8. Verify deployment succeeds on Railway
9. Confirm phase complete before moving to next

---

*This blueprint is the implementation guide for the WLJ architecture evolution. Each phase should be implemented sequentially unless explicitly parallelized. Changes to the blueprint require updating this document before implementation.*
