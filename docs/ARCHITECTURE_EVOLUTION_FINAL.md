# WLJ Architecture Evolution — Final Architecture Lock

**Date:** 2026-03-14
**Status:** LOCKED — Canonical architecture reference for WLJ
**Supersedes:** ARCHITECTURE_EVOLUTION_ASSESSMENT.md, ARCHITECTURE_EVOLUTION_REFINEMENT.md

---

## 1. Vision

Whole Life Journey (WLJ) is a holistic life operating system where Beth (the AI Chief of Staff) reasons over planned commitments, actual activity, derived signals, goal momentum, and cross-domain progress — coaching Danny toward long-term flourishing across every life domain.

---

## 2. The Five-Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 LAYER 5: BETH (AI Reasoning)                │
│  CoS context assembly │ Signal-class-aware framing          │
│  Compensatory analysis │ Relational reasoning               │
│  Commitment vs actual comparison │ Holistic coaching        │
└───────────────────────────┬─────────────────────────────────┘
                            │ reads all layers
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼───────┐  ┌───────▼───────┐  ┌────────▼──────────┐
│ GOAL MOMENTUM │  │   SIGNALS     │  │ COMMITMENT vs     │
│ (Layer 4)     │  │   (Layer 3)   │  │ ACTUAL GAP        │
│               │  │               │  │                   │
│ Per-goal score│  │ Persistent    │  │ Planned (L1) vs   │
│ from weighted │◀─┤ daily values  │  │ happened (L2)     │
│ signal sources│  │ with class,   │  │ Net assessment    │
│               │  │ confidence,   │  │ per domain        │
│ GoalSignal-   │  │ and trend     │  │                   │
│ Source config │  │               │  │                   │
└───────────────┘  └───────┬───────┘  └───┬───────────┬───┘
                           │              │           │
                  generated from          │           │
                           │              │           │
             ┌─────────────┴─────┐        │           │
             │                   │        │           │
   ┌─────────▼─────┐  ┌─────────▼────┐   │           │
   │  ACTIVITY     │  │  NLP         │   │           │
   │  (Layer 2)    │  │  (Inferred)  │   │           │
   │               │  │              │   │           │
   │  Read-time    │  │  Journal &   │   │           │
   │  aggregation  │  │  Capture     │   │           │
   │  of completed │  │  text        │   │           │
   │  actions      │  │  extraction  │   │           │
   └───────┬───────┘  └─────────────┘   │           │
           │                             │           │
           │ queries                     │ queries   │ queries
           │                             │           │
┌──────────▼─────────────────────────────▼───────────▼────────┐
│              DOMAIN SYSTEMS (Source of Truth)                 │
│  health │ faith │ journal │ life │ purpose │ finance │ ...   │
│  Each domain owns its structured data and completion records │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           │ projects into
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              COMMITMENTS — Layer 1 (CalendarEngine)          │
│  Unified view of planned actions for a given day/time        │
│  source_type → domain system                                 │
│  commitment_level → importance classification                │
│  status → scheduled / completed / canceled                   │
└─────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| Layer | Responsibility | Key Principle |
|-------|---------------|---------------|
| **Domain Systems** | Own structured data. Record what happened. Source of truth. | Never duplicated. Never bypassed. |
| **Layer 1: Commitments** | Project "what you plan to do today" from domain systems into CalendarEngine. | Instance, not definition. |
| **Layer 2: Activity** | Aggregate "what you actually did today" from domain completion records. | Read-time query. No new model. |
| **Layer 3: Signals** | Normalize daily activity into scored, classified signal types. | Persisted. Classified by trust level. |
| **Layer 4: Goal Momentum** | Consume weighted signals to compute per-goal momentum scores. | Explicit signal→goal configuration. |
| **Layer 5: Beth** | Reason over all layers. Compare planned vs actual. Coach holistically. | Signal-class-aware. Compensatory-safe. |

---

## 3. LifeDomain Enumeration

A single shared enumeration prevents domain drift across models, signals, commitments, and reasoning logic.

```python
class LifeDomainEnum:
    HEALTH = 'health'          # Physical wellness, fitness, nutrition, sleep, medication
    FAITH = 'faith'            # Prayer, Bible reading, church, spiritual growth
    MIND = 'mind'              # Journaling, reflection, brain training, mental health
    RELATIONSHIPS = 'relationships'  # Family, friends, community, social
    WORK = 'work'              # Career, projects, professional growth
    FINANCE = 'finance'        # Budgeting, savings, investments, giving
    LIFE = 'life'              # Household, administration, errands, personal

    CHOICES = [
        (HEALTH, 'Health'),
        (FAITH, 'Faith'),
        (MIND, 'Mind'),
        (RELATIONSHIPS, 'Relationships'),
        (WORK, 'Work'),
        (FINANCE, 'Finance'),
        (LIFE, 'Life'),
    ]
```

**Referenced by:**
- LifeGoal.domain
- SignalSnapshot.domain
- CalendarEvent.domain (via LifeDomain FK — already exists, but the FK target should align with this enumeration)
- Compensatory rules (missed_domain, compensating_domain)
- GoalSignalSource (implicit via signal_type → domain mapping)
- Cross-domain insight rules
- SAE state builders

**Implementation note:** The existing `LifeDomain` model in `apps/purpose/models.py` is database-driven (user-configurable). The enumeration above should be enforced as the **system default set** loaded via fixture, with the database model remaining the FK target. This preserves the existing FK pattern while standardizing the domain vocabulary.

---

## 4. CalendarEngine Contracts

### Contract 1 — Instance, Not Definition

**Rule:** CalendarEvent represents the **scheduled commitment instance for a specific day/time**, never the reusable schedule definition.

| Domain | Definition (stays in domain) | Instance (projected to CalendarEngine) | Completion (stays in domain) |
|--------|------------------------------|----------------------------------------|------------------------------|
| Tasks | Task (with recurrence config) | CalendarEvent: "Review quarterly report — Today 2:00 PM" | Task.completed_at |
| Medicine | MedicineSchedule: "Metformin at 8 AM daily" | CalendarEvent: "Take Metformin — Today 8:00 AM" | MedicineLog: taken_at 8:02 AM |
| Habits | HabitGoal: "Morning Prayer, daily" | CalendarEvent: "Morning Prayer — Today 6:30 AM" | HabitEntry: date=today, completed=True |
| Workouts | WorkoutSchedule: "Push Day, Mondays 5 PM" | CalendarEvent: "Push Day (Upper Body) — Monday 5:00 PM" | WorkoutSession: completed_at |
| Faith | UserReadingPlan + day config | CalendarEvent: "Read Romans 8 — Today 6:45 AM" | UserReadingProgress: completed_date |
| Life Events | LifeEvent (with recurrence) | CalendarEvent: "Dentist Appointment — March 20 10:00 AM" | LifeEvent status |

All projections follow this rule, regardless of whether the source uses recurrence rules or explicit per-day records.

### Contract 2 — Projection Interface

Every source type must implement:

```python
def upsert_from_{source}(instance) -> CalendarEvent | None:
    """Create or update CalendarEvent from source instance.
    Returns None if source doesn't qualify for projection."""

def delete_{source}_events(instance) -> int:
    """Remove all CalendarEvents for this source instance.
    Returns count of deleted events."""
```

### Contract 3 — Source Type Registry

| source_type | event_kind | Default commitment_level | Domain | Signal handler |
|-------------|-----------|-------------------------|--------|---------------|
| `task` | execution_block or deadline_marker | From task.commitment_level | Derived from task.module | apps/life/signals.py |
| `goal` | deadline_marker | From goal.commitment_level | From goal.domain | apps/purpose/signals.py |
| `goal_milestone` | deadline_marker | important | From parent goal.domain | apps/purpose/signals.py |
| `habit` | manual (with RecurrenceRule) | From habit.commitment_level | From habit.domain | apps/purpose/signals.py |
| `life_event` | manual | important | Derived from event_type | apps/life/signals.py |
| `external` | external_readonly | optional | N/A | apps/calendar_engine/ |
| `medicine_schedule` | execution_block | non_negotiable | health | apps/health/signals.py (new) |
| `faith_routine` | execution_block | important | faith | apps/faith/signals.py (new) |
| `workout_schedule` | execution_block | important | health | apps/health/signals.py (new) |

### Contract 4 — CalendarEvent Owns Rendering, Source Owns Detail

CalendarEvent provides: title, time, domain, status, commitment_level, source_type, source_id.
Source model provides: domain-specific detail (accessed via source_type + source_id lookup when needed).
CalendarEvent must NEVER require domain-specific fields.

### Contract 5 — Idempotency

All source-backed events use `(user_id, source_type, source_id)` for idempotency key computation. This is the existing pattern and must be maintained for all new source types.

---

## 5. Attribution Model

### TaskGoalLink

```python
class TaskGoalLink(TimeStampedModel):
    """Structural attribution: this task serves these goals."""
    task = ForeignKey(Task, on_delete=CASCADE, related_name='goal_links')
    goal = ForeignKey(LifeGoal, on_delete=CASCADE, related_name='task_links')

    class Meta:
        unique_together = ['task', 'goal']
```

### HabitGoalLink

```python
class HabitGoalLink(TimeStampedModel):
    """Structural attribution: this habit serves these goals."""
    habit = ForeignKey(HabitGoal, on_delete=CASCADE, related_name='goal_links')
    goal = ForeignKey(LifeGoal, on_delete=CASCADE, related_name='habit_links')

    class Meta:
        unique_together = ['habit', 'goal']
```

### Layer Responsibility Separation

| Layer | Model | What It Answers |
|-------|-------|----------------|
| Attribution | TaskGoalLink, HabitGoalLink | "What serves what?" — structural, stable, human-declared |
| Commitment | CalendarEvent | "What is planned for today?" — time-based instance |
| Activity | Domain completion records | "What actually happened?" — read-time aggregation |
| Signal | SignalSnapshot | "What does today's activity mean?" — normalized, classified |
| Weighting | GoalSignalSource | "How much does each signal matter to each goal?" — quantitative, tunable |
| Momentum | GoalMomentumSnapshot | "How is this goal progressing?" — weighted signal aggregation |

**Momentum flows through signals, not directly from task or habit completion.**

A task completion → recorded in domain system → aggregated by DailyActivityService → generates signal (e.g., `productivity_progress`) → GoalSignalSource determines weight → GoalMomentumService computes score.

---

## 6. Signal Architecture

### Signal Types (Initial Taxonomy)

| Signal Type | Domain | Description | Primary Sources |
|-------------|--------|-------------|----------------|
| `health_activity` | health | Physical activity level | WorkoutSession, Steps (HealthKit), Exercise |
| `health_biometrics` | health | Vital sign stability | Weight, BloodSugar, BloodPressure, Sleep |
| `medication_adherence` | health | Medication compliance | MedicineLog |
| `nutrition_compliance` | health | Dietary adherence | DailyNutritionLog, WaterIntake, FastingWindow |
| `faith_practice` | faith | Spiritual discipline engagement | UserReadingProgress, PrayerRequest activity, HabitEntry (faith habits) |
| `mental_reflection` | mind | Introspective activity | JournalEntry, JournalSignal (NLP), CaptureEntry |
| `cognitive_fitness` | mind | Brain training engagement | GameSession, DailyStats |
| `productivity_progress` | work/life | Task and project execution | Task completions, ProjectMilestone completions |
| `financial_health` | finance | Financial behavior signals | Transaction, Budget adherence, FinancialGoal progress |
| `relational_engagement` | relationships | Social and family activity | Relationship interactions, LifeEvent (family/social) |

### Signal Classes

```python
SIGNAL_CLASS_CHOICES = [
    ('verified_action', 'Verified Action'),
    ('verified_measurement', 'Verified Measurement'),
    ('inferred_behavior', 'Inferred Behavior'),
    ('derived_pattern', 'Derived Pattern'),
]
```

| Signal Class | Meaning | Examples | Beth's Framing |
|-------------|---------|----------|---------------|
| `verified_action` | User explicitly completed an action | Task completed, medication taken, workout logged, habit checked off | State as fact: "You completed your workout." |
| `verified_measurement` | Sensor, device, or manual data entry | Glucose reading, weight, sleep duration, step count | State as fact with source: "Your glucose was 105." |
| `inferred_behavior` | NLP-extracted from unstructured text | "I took a walk" from journal, behavioral signals from capture transcript | Hedge: "It sounds like you were active based on your journal." |
| `derived_pattern` | Computed from multiple signals over time | Momentum trend, cross-domain correlation, drift detection | Frame as observation: "Your health momentum has been trending up." |

**Classification is set at signal creation time and flows through the entire pipeline unchanged.**

### SignalSnapshot Model

```python
class SignalSnapshot(TimeStampedModel):
    user = ForeignKey(User, on_delete=CASCADE)
    date = DateField()
    signal_type = CharField(max_length=30)      # From signal taxonomy
    domain = CharField(max_length=20)            # From LifeDomainEnum
    signal_class = CharField(max_length=25)      # verified_action, etc.
    score = FloatField()                         # 0.0–1.0 normalized
    confidence = FloatField()                    # 0.0–1.0 independent of class
    source_signals = JSONField(default=dict)     # Evidence: which raw data contributed

    class Meta:
        unique_together = ['user', 'date', 'signal_type']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['user', 'signal_type', 'date']),
        ]
```

### JournalSignal Model

```python
class JournalSignal(TimeStampedModel):
    entry = ForeignKey(JournalEntry, on_delete=CASCADE, related_name='signals')
    signal_type = CharField(max_length=30)       # Maps to signal taxonomy
    domain = CharField(max_length=20)            # From LifeDomainEnum
    confidence = FloatField()                    # 0.0–1.0
    extracted_text = TextField()                 # The phrase that triggered detection

    class Meta:
        indexes = [
            models.Index(fields=['entry', 'signal_type']),
        ]
```

### Signal Normalization (Initial Approach)

Start with **fixed baselines from health guidelines**. Personal baselines can be added later.

| Signal Type | 1.0 Baseline | 0.5 Baseline | 0.0 Baseline |
|-------------|-------------|-------------|-------------|
| health_activity | 10,000 steps or 45+ min exercise | 5,000 steps or 20 min exercise | No activity |
| health_biometrics | All metrics in target range | Some metrics in range | No data logged |
| medication_adherence | 100% doses taken on time | 80% doses taken | <50% doses taken |
| faith_practice | All planned readings/prayer completed | Partial completion | No engagement |
| mental_reflection | Journal entry + mood tracking | Brief entry | No entry |
| productivity_progress | All due tasks completed | >50% tasks completed | <25% completed |

---

## 7. Goal Momentum Architecture

### GoalSignalSource Model

```python
class GoalSignalSource(TimeStampedModel):
    goal = ForeignKey(LifeGoal, on_delete=CASCADE, related_name='signal_sources')
    signal_type = CharField(max_length=30)       # From signal taxonomy
    weight = FloatField()                        # 0.0–1.0, relative importance

    class Meta:
        unique_together = ['goal', 'signal_type']
```

### Auto-Population Defaults

When a goal is created, GoalSignalSource records are auto-populated based on the goal's LifeDomain:

| Goal Domain | Default Signal Sources | Default Weights |
|-------------|----------------------|-----------------|
| Health | health_activity (0.35), health_biometrics (0.25), medication_adherence (0.20), nutrition_compliance (0.20) | Totals 1.0 |
| Faith | faith_practice (0.50), mental_reflection (0.30), relational_engagement (0.20) | Totals 1.0 |
| Mind | mental_reflection (0.40), cognitive_fitness (0.30), health_biometrics (0.15), faith_practice (0.15) | Totals 1.0 |
| Work | productivity_progress (0.50), mental_reflection (0.20), health_activity (0.15), cognitive_fitness (0.15) | Totals 1.0 |
| Finance | financial_health (0.60), productivity_progress (0.25), mental_reflection (0.15) | Totals 1.0 |

Defaults can be overridden by the user or by Beth (via intent handler).

### Momentum Calculation

GoalMomentumService computes per-goal momentum by:
1. Reading GoalSignalSource records for the goal
2. Pulling recent SignalSnapshot values for each signal_type (7-day window)
3. Computing weighted average: `momentum = Σ(signal_score × weight)` for each signal source
4. Blending with existing components (discipline/streaks, recency)
5. Persisting to GoalMomentumSnapshot with signal_scores breakdown

---

## 8. Compensatory Reasoning Architecture

### Layer 1 — Hard Gate (Non-Compensable)

```python
NON_COMPENSABLE_RULES = {
    # Domain-level blocks
    'medication_adherence': 'Medication adherence cannot be offset by other activities.',

    # Commitment-level block (applies across all domains)
    # Any commitment with commitment_level='non_negotiable' is non-compensable.
}
```

If a missed commitment falls in a non-compensable domain OR has `commitment_level='non_negotiable'`, the compensatory engine returns immediately with no analysis. Beth receives: "This commitment was missed. No compensatory offset applies."

### Layer 2 — Allowlist (Explicit Compensatory Pairs)

```python
COMPENSATORY_PAIRS = [
    {
        'missed_domain': 'health',
        'missed_signal': 'health_activity',
        'compensating_signal': 'health_activity',
        'max_offset_pct': 0.50,
        'rationale': 'Steps/walking partially compensate for missed structured exercise.',
        'requires_signal_class': ['verified_action', 'verified_measurement'],
    },
    {
        'missed_domain': 'health',
        'missed_signal': 'health_activity',
        'compensating_signal': 'mental_reflection',
        'max_offset_pct': 0.15,
        'rationale': 'Reflecting on health shows awareness but does not replace exercise.',
        'requires_signal_class': ['verified_action', 'verified_measurement', 'inferred_behavior'],
    },
    {
        'missed_domain': 'faith',
        'missed_signal': 'faith_practice',
        'compensating_signal': 'faith_practice',
        'max_offset_pct': 0.30,
        'rationale': 'Prayer supports faith growth but reading has independent value.',
        'requires_signal_class': ['verified_action'],
    },
    {
        'missed_domain': 'mind',
        'missed_signal': 'mental_reflection',
        'compensating_signal': 'faith_practice',
        'max_offset_pct': 0.25,
        'rationale': 'Scripture reading supports mental reflection but is not equivalent.',
        'requires_signal_class': ['verified_action'],
    },
]
```

**Allowlist semantics:**
- Only explicitly listed pairs produce compensatory analysis
- Unlisted pairs default to "no offset"
- `requires_signal_class` gates which signal classes qualify (inferred_behavior only allowed where explicitly permitted)
- `max_offset_pct` caps the compensatory credit (0.50 = "at most half credit")

### Layer 3 — Beth's Prompt Rules

```
COMPENSATORY REASONING RULES:
1. NEVER suggest that compensatory activity makes missing the original commitment "okay."
2. Frame as: "While you missed X, you still showed progress through Y."
3. NEVER apply compensatory reasoning to medication or non-negotiable commitments.
4. Maximum language: "partially offset" — never "fully replaced" or "made up for."
5. Always end compensatory observations with forward guidance: "Tomorrow, let's aim for X."
6. If compensating signal is inferred_behavior, double-hedge:
   "Based on your journal, it seems like you were active, which is encouraging."
7. NEVER cite a derived_pattern as compensatory evidence.
   Only verified_action, verified_measurement, and (with hedging) inferred_behavior.
```

---

## 9. Finalized Phase Order

| Phase | Name | Purpose |
|-------|------|---------|
| **1** | Foundation | Structural links, CalendarEngine projections, commitment_level |
| **2** | Unified Daily View | DailyScheduleService + DailyActivityService |
| **3** | Signal Taxonomy Design | Define types, classes, normalization (document, no code) |
| **4** | Signal Persistence | SignalSnapshot model + nightly aggregation |
| **5** | Goal-Signal Configuration | GoalSignalSource + GoalMomentumService integration |
| **6** | Compensatory Reasoning | Commitment vs actual, allowlist rules, verified signals only |
| **7** | Journal NLP | JournalSignal extraction, inferred_behavior signals |
| **8** | Beth Reasoning Upgrade | Signal-class-aware framing, relational analysis, holistic coaching |

**Dependencies:**
- Phase 2 depends on Phase 1 (CalendarEngine projections must exist for daily view)
- Phase 4 depends on Phase 3 (taxonomy must be designed before persistence)
- Phase 5 depends on Phase 4 (needs persisted signals to configure and validate)
- Phase 6 depends on Phase 2 + Phase 4 (needs commitment-vs-actual + signal_class)
- Phase 7 depends on Phase 4 (needs signal persistence infrastructure)
- Phase 8 depends on Phase 6 + Phase 7 (needs compensatory engine + NLP signals)
- Phases 5, 6, 7 can potentially parallelize after Phase 4

---

## 10. Architectural Rules (Immutable)

1. **Domain systems are the source of truth.** No layer duplicates domain data.
2. **CalendarEngine projects instances, not definitions.** Schedule definitions stay in domain models.
3. **Momentum flows through signals.** Task/habit completion → activity → signal → goal momentum. Never shortcut.
4. **Signal class is set at creation.** It flows unchanged through scoring, persistence, CoS assembly, and Beth reasoning.
5. **Non-negotiable commitments are non-compensable.** Hard gate, no exceptions.
6. **Compensatory pairs are allowlisted.** Unlisted pairs produce no offset.
7. **Beth never states inferred data as verified fact.** Signal class determines framing.
8. **LifeDomainEnum is the single domain vocabulary.** All models, signals, and rules reference the same set.
9. **Attribution and weighting are separate.** Links declare relevance. GoalSignalSource declares importance.
10. **Activity aggregation is read-time.** No write-time denormalization table for completed actions.

---

## 11. New Models Summary

| Model | App | Purpose | Phase |
|-------|-----|---------|-------|
| TaskGoalLink | apps/life | M2M attribution: task → goals | 1 |
| HabitGoalLink | apps/purpose | M2M attribution: habit → goals | 1 |
| SignalSnapshot | apps/core/ai_eae | Persisted daily signal values | 4 |
| GoalSignalSource | apps/purpose | Signal→goal weighting config | 5 |
| JournalSignal | apps/journal | NLP-extracted behavioral signals | 7 |

## 12. Model Enhancements Summary

| Model | Change | Phase |
|-------|--------|-------|
| CalendarEvent | + commitment_level field | 1 |
| CalendarEvent | + source_type choices (medicine_schedule, faith_routine, workout_schedule) | 1 |
| HabitGoal | + commitment_level field | 1 |
| RawSignal dataclass | + signal_class field | 4 |
| GoalMomentumSnapshot | + signal_scores JSONField | 5 |

---

*This document is the canonical architecture reference for the WLJ evolution. All implementation work should reference this document. Changes to architectural decisions require a revision to this document before implementation.*
