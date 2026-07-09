# WLJ Architecture Evolution — Refinement Pass

**Date:** 2026-03-14
**Status:** Final architectural refinement before implementation blueprint

---

## Item 1 — Task→Goal Linkage

### Challenge
A direct FK on Task is too restrictive. Real-world examples:
- A workout supports Health Goal, Weight Loss Goal, and Mental Health Goal
- A journal entry supports Faith Goal, Self-Awareness Goal, and Mental Health Goal
- Administrative tasks support no goal

### Analysis

There are actually **two distinct relationships** being conflated:

1. **Attribution:** "This task contributes to these goals" — a structural relationship set at task creation/configuration time
2. **Signal weighting:** "How much does this type of activity matter to this goal?" — a momentum calculation concern

These should be separate. Attribution tells you *which* goals a task serves. Signal weighting tells you *how much* each signal type matters to a goal's momentum score.

### Recommendation: M2M Through Model

```python
class TaskGoalLink(TimeStampedModel):
    task = FK(Task)
    goal = FK(LifeGoal)

    class Meta:
        unique_together = ['task', 'goal']
```

**No weight field on the link.** Here's why:

- Weight belongs at the signal layer (GoalSignalSource), not the attribution layer
- When a task is completed, it generates a signal (e.g., `productivity_progress` or `health_activity` depending on module)
- GoalSignalSource determines how much that signal type contributes to each goal's momentum
- The task link just declares "this task is relevant to this goal" — for display, tracking, and coaching

**Why not a direct FK:**
| Approach | Pros | Cons |
|----------|------|------|
| Direct FK | Simple queries, simple UI | Can't link to multiple goals, forces "pick one" |
| M2M (no through) | Supports multiple goals | No place for future metadata |
| M2M through model (recommended) | Multiple goals, extensible | Slightly more complex queries |

The through model is the right long-term design. Even without weight, it allows future extension (contribution_type, notes, etc.) without migration headaches.

**Migration cost:** 1 new table, 0 changes to existing Task model. Existing tasks simply have no links (empty M2M). No data migration needed.

**This same pattern should also apply to HabitGoal→LifeGoal linkage.** Habits already conceptually serve goals, but the link is implicit today (both reference LifeDomain and AnnualDirection, but there's no direct habit→goal connection).

---

## Item 2 — Signal Classification / Trust Model

### Current State
RawSignal has a `confidence` field (0.0–1.0) but **no concept of verification level**. Beth's system prompt has strong "don't fabricate" rules, but the signal itself doesn't declare whether it came from a verified action, a sensor reading, or an NLP inference.

### The Problem
Confidence and verification are orthogonal:
- A glucose reading is `verified_measurement` with high confidence
- A glucose reading from a miscalibrated sensor is `verified_measurement` with low confidence
- "I took a walk" from a journal entry is `inferred_behavior` with medium confidence
- A momentum trend computed from 30 days of data is `derived_pattern` with high confidence

Confidence says "how sure are we about this value?" Verification class says "what kind of evidence produced this?"

### Recommendation: Add `signal_class` to SignalSnapshot

```python
class SignalSnapshot(TimeStampedModel):
    SIGNAL_CLASS_CHOICES = [
        ('verified_action', 'Verified Action'),       # User explicitly completed something
        ('verified_measurement', 'Verified Measurement'), # Sensor/device/manual data entry
        ('inferred_behavior', 'Inferred Behavior'),    # NLP-extracted from text
        ('derived_pattern', 'Derived Pattern'),        # Computed from multiple signals
    ]

    signal_class = CharField(max_length=25, choices=SIGNAL_CLASS_CHOICES)
    confidence = FloatField()  # Independent of class
```

**Classification rules (set at signal creation, not downstream):**

| Source | Signal Class | Examples |
|--------|-------------|----------|
| Task.completed_at | verified_action | Task completed |
| MedicineLog.taken_at | verified_action | Medication taken |
| WorkoutSession.completed_at | verified_action | Workout completed |
| HabitEntry.completed | verified_action | Habit logged |
| UserReadingProgress.completed_date | verified_action | Bible reading completed |
| Weight measurement | verified_measurement | Weight logged |
| BloodSugar reading | verified_measurement | Glucose reading |
| Sleep record | verified_measurement | Sleep data (manual or HealthKit) |
| Steps (HealthKit) | verified_measurement | Step count |
| JournalSignal (NLP extraction) | inferred_behavior | "I went for a walk" |
| CaptureEntry transcript analysis | inferred_behavior | Behavioral signals from audio |
| Momentum score | derived_pattern | Computed trend |
| Cross-domain insight | derived_pattern | MotivationDriftRule output |
| Goal completion projection | derived_pattern | PRIE prediction |

### Where Should This Live?

**On SignalSnapshot (persisted signals):** Yes. This is the primary consumer-facing classification.

**On RawSignal (ephemeral signals):** Also yes — add `signal_class` field to the RawSignal dataclass. This way the classification is set at collection time and flows through scoring, CoS assembly, and persistence without needing to be re-derived.

**NOT on domain models.** Domain models don't need to know about signal classification. The classification is assigned when a domain record is translated into a signal.

### How Beth Uses This

Add to CoS context assembly: when injecting signals, include `signal_class` alongside `confidence`. Update Beth's system prompt with an explicit rule:

```
SIGNAL TRUST RULES:
- verified_action: State as fact. "You completed your workout."
- verified_measurement: State as fact with source. "Your glucose was 105 mg/dL."
- inferred_behavior: Hedge. "It sounds like you went for a walk based on your journal."
- derived_pattern: Frame as observation. "Your health momentum has been trending up."
- NEVER state inferred_behavior or derived_pattern as verified fact.
```

This is enforceable because the signal itself carries the classification — Beth doesn't have to guess.

---

## Item 3 — Compensatory / Relational Reasoning Safety

### The Core Tension

Compensatory reasoning is valuable ("you walked instead of working out — still progress") but dangerous when misapplied ("you felt fine so skipping medication is okay").

### Recommendation: Domain-Level Compensatory Rules with Non-Compensable Gate

**Architecture: Three layers of safety**

#### Layer 1: Non-Compensable Commitment Types (Hard Gate)

Certain commitment types must NEVER be softened by compensatory reasoning:

```python
# In apps/core/ai_insights/compensatory.py

NON_COMPENSABLE_DOMAINS = {
    'medication': 'Medication adherence cannot be offset by other activities.',
    'safety': 'Safety-critical commitments cannot be compensated.',
}

# Additionally, any commitment with commitment_level='non_negotiable'
# is non-compensable by default, regardless of domain.
```

This is a **hard gate**, not a soft rule. The compensatory reasoning engine checks this list FIRST. If a missed commitment falls in a non-compensable domain or is non_negotiable, no compensatory analysis runs. Beth receives: "This commitment was missed. No compensatory offset applies."

#### Layer 2: Explicit Compensatory Pairs (Allowlist, Not Blocklist)

Compensatory reasoning should be **opt-in per domain pair**, not a general "anything can offset anything" system:

```python
COMPENSATORY_RULES = [
    {
        'missed_domain': 'fitness',
        'compensating_signal': 'health_activity',  # steps, active minutes
        'max_offset_pct': 0.50,  # Can offset up to 50% of missed workout
        'rationale': 'Walking/steps partially compensate for missed structured exercise',
    },
    {
        'missed_domain': 'fitness',
        'compensating_signal': 'mental_reflection',  # journaling about health
        'max_offset_pct': 0.15,  # Minimal credit — acknowledgment, not replacement
        'rationale': 'Reflecting on health shows awareness but does not replace exercise',
    },
    {
        'missed_domain': 'faith_reading',
        'compensating_signal': 'faith_practice',  # prayer, church
        'max_offset_pct': 0.30,  # Partial — prayer is related but distinct
        'rationale': 'Prayer supports faith growth but reading has independent value',
    },
    # Explicitly NOT listed:
    # medication → anything (non-compensable)
    # prayer → journaling (not a valid pair)
    # glucose stability → medication (non-compensable, and also a category error)
]
```

**Why an allowlist:** A blocklist would require anticipating every dangerous combination. An allowlist means only explicitly approved pairs produce compensatory reasoning. Unknown pairs default to "no offset."

#### Layer 3: Beth's Compensatory Prompt Rules

Even when compensatory analysis runs, Beth must follow strict framing:

```
COMPENSATORY REASONING RULES:
1. NEVER suggest that compensatory activity makes missing the original commitment "okay"
2. Frame as: "While you missed X, you still showed progress through Y"
3. NEVER apply compensatory reasoning to medication, safety, or non-negotiable commitments
4. Maximum language: "partially offset" — never "fully replaced" or "made up for"
5. Always end with forward-looking guidance: "Tomorrow, try to get back to X"
6. If signal_class is 'inferred_behavior', double-hedge: "Based on your journal,
   it seems like you were active, which is encouraging"
```

#### Implementation Location

This should be a **new PIE rule set** in `apps/core/ai_insights/rules_compensatory.py`, not embedded in cross-domain rules. Reasons:
- Compensatory rules have their own safety gates (non-compensable check)
- They produce a distinct insight type (`compensatory_progress`, severity: `positive`)
- They need the commitment-vs-actual comparison as input, which cross-domain rules don't currently have
- Keeping them separate makes them independently auditable and testable

The CoS context builder calls the compensatory engine after building the daily commitment summary, passing both planned commitments and actual activity.

---

## Item 4 — Commitment Importance / Non-Negotiables

### Current State

- `Task.commitment_level`: optional / important / non_negotiable ✅
- `LifeGoal.commitment_level`: optional / important / non_negotiable ✅
- `HabitGoal`: Does NOT have commitment_level ❌
- `Medicine`: Does NOT have commitment_level ❌ (but has `frequency` and `is_prn`)
- `MedicineSchedule`: Does NOT have commitment_level ❌
- `PrayerRequest`: Has `priority` (normal/urgent) but not commitment_level
- `CalendarEvent`: Does NOT have commitment_level ❌

### Recommendation: Propagate to CalendarEngine, Not to Every Domain

Adding `commitment_level` to every domain model creates maintenance burden and semantic drift. Instead:

**Option A (Recommended): CalendarEngine carries commitment_level**

```python
# On CalendarEvent
commitment_level = CharField(
    max_length=20,
    choices=COMMITMENT_LEVEL_CHOICES,
    default='important',
)
```

Each projection function sets commitment_level:
- **Task projections:** Copy from `task.commitment_level` (already exists)
- **Goal projections:** Copy from `goal.commitment_level` (already exists)
- **Medicine projections:** Default to `non_negotiable` (medication is inherently non-negotiable)
- **Faith projections:** Default to `important`, configurable per faith routine
- **Workout projections:** Default to `important`
- **Habit projections:** Could derive from `habit.habit_required` (required → important, not required → optional)

**Why this works:** CalendarEvent IS the unified commitment layer. Commitment importance is a property of "I committed to do this at this time," which is exactly what CalendarEvent represents. Domain models that already have commitment_level keep it (Task, LifeGoal). Domain models that don't (Medicine, faith) get sensible defaults at projection time.

**What about HabitGoal?** Add `commitment_level` to HabitGoal as well — it's a natural fit and the model already has similar concepts (`habit_required`, `status`). This is 1 field addition, 1 migration.

**Option B (Not Recommended): Add commitment_level to every domain model**

This would mean adding the field to Medicine, MedicineSchedule, PrayerRequest, WorkoutSchedule, etc. It's more "pure" but creates:
- 5+ migrations across different apps
- Redundant defaults that rarely change (medication is almost always non_negotiable)
- More fields to maintain and keep in sync with CalendarEvent projections

### Connection to Compensatory Reasoning

The `commitment_level` on CalendarEvent directly feeds the compensatory safety gate from Item 3:
- `non_negotiable` → Non-compensable (hard gate, no offset)
- `important` → Compensatory rules may apply (per allowlist)
- `optional` → Full compensatory flexibility, or simply no coaching on misses

This creates a clean chain: commitment_level set → projected to CalendarEvent → compensatory engine checks level → Beth reasons accordingly.

---

## Item 5 — CalendarEngine as Commitment Layer (Pressure Test)

### Can It Scale?

Let me count the commitments for a typical Danny day:

| Source | Count | CalendarEvent Rows |
|--------|-------|--------------------|
| Tasks (routine + one-off) | 5-10 | 5-10 |
| Medication doses | 4-6 | 4-6 |
| Workout | 0-1 | 0-1 |
| Faith routines | 1-3 | 1-3 |
| Habit check-ins | 2-5 | 2-5 |
| Life events / appointments | 0-3 | 0-3 |
| Goal deadline markers | 0-2 | 0-2 |
| **Total** | **12-30** | **12-30** |

Current CalendarEvent row count per day per user: ~5-10. With medicine and faith projections: ~15-25. This is trivially manageable. The indexes on `(user, start_dt)` and `(user, source_type, source_id)` handle this volume.

### Schema Fitness

CalendarEngine is a **flat model** — no metadata JSONField. For new source types:

| New Source | Title | Time | Domain | What's Missing? |
|-----------|-------|------|--------|----------------|
| Medicine dose | "Take Lisinopril 10mg" | 8:00 AM | Health | Nothing — title + time is sufficient |
| Prayer routine | "Morning Prayer" | 6:30 AM | Faith | Nothing — title + time |
| Bible reading | "Read Romans 8" | 6:45 AM | Faith | Reading reference in title is sufficient |
| Workout plan | "Push Day (Upper Body)" | 5:00 PM | Health | Nothing — title + time |

The flat schema works. Domain-specific detail (dose amount, reading reference, exercise list) lives in the source model — CalendarEvent just needs enough to render a timeline entry and link back to the source.

### Risks of Overloading

1. **Projection handler proliferation** — Currently 4 projection sources (task, goal, habit, life_event). Adding 3 more (medicine, faith, workout) means 7 total. Each needs create/update/delete signal handlers. This is manageable but must follow a strict contract.

2. **Signal handler complexity** — Medicine schedules change differently than tasks. A medicine frequency change might need to delete and recreate 4-6 daily events. This is more complex than task projection but well-understood.

3. **Conceptual overload** — "CalendarEvent" starts meaning "anything with a time." A 9am pill isn't really a "calendar event" in the traditional sense.

### The Tipping Point

CalendarEngine becomes fragile when:
- Domain-specific fields are needed ON the event itself (not just in the source)
- Projection logic requires understanding the source model's internal state (e.g., medicine interactions, contraindications)
- The number of source types exceeds ~10-12, making the projection registry hard to maintain

**None of these conditions are met by the proposed additions.**

### Final Answer: Keep CalendarEngine, With Contracts

CalendarEngine is the right layer. But it needs explicit architectural contracts:

**Contract 1 — Projection Interface:**
Every source type must implement:
```python
def upsert_from_{source}(instance) -> CalendarEvent:
    """Create or update CalendarEvent from source instance."""

def delete_{source}_events(instance) -> None:
    """Remove all CalendarEvents for this source instance."""
```

**Contract 2 — Source Type Registry:**
A documented registry of all source types with their:
- Default commitment_level
- Default event_kind
- Domain mapping
- Signal handler locations

**Contract 3 — CalendarEvent Owns Rendering, Source Owns Detail:**
CalendarEvent provides: title, time, domain, status, commitment_level.
Source model provides: domain-specific detail (accessed via source_type + source_id lookup).
CalendarEvent should NEVER need domain-specific fields.

**Contract 4 — Idempotency:**
All source-backed events use `(user_id, source_type, source_id)` idempotency. This already exists and must be maintained.

If a future requirement violates Contract 3 (CalendarEvent needs domain-specific fields), THAT is the signal to introduce a dedicated abstraction layer. But that day is not today.

---

## Item 6 — Phase Order: Signal Persistence vs. Goal-Signal Configuration

### Danny's Concern
If we persist signals before defining which signals matter to which goals, we may store data without enough structure.

### Analysis

Danny is right that the **signal taxonomy** must be defined before persistence. But the signal taxonomy is NOT the same as goal-signal configuration.

- **Signal taxonomy:** "What signal types exist?" (health_activity, faith_practice, etc.) — This must be defined first.
- **Signal persistence:** "Store daily values of each signal type" — Requires taxonomy.
- **Goal-signal configuration:** "Which signal types feed into which goals, with what weights?" — Requires taxonomy AND persisted data to be meaningful.

The taxonomy is a prerequisite for both. But persistence should come before goal-signal config because:

1. **Validation:** You need to see actual signal values before you can tune goal-signal weights. "health_activity = 0.7" means nothing until you've observed the distribution.
2. **Debugging:** If momentum scores look wrong, you need persisted signal history to diagnose whether the problem is in signal computation or goal-signal weighting.
3. **Independence:** Signal persistence has value beyond goals — it enables historical trending, Beth's longitudinal reasoning, and dashboard visualizations.

### Revised Phase Order

Design the signal taxonomy as a standalone deliverable BEFORE either phase. Then:

1. **Phase 3a — Signal Taxonomy Design** (design document, no code)
   - Define all signal types
   - Define signal_class classification rules
   - Define normalization approach (how to map heterogeneous metrics to 0.0–1.0)

2. **Phase 3b — Signal Persistence** (implementation)
   - SignalSnapshot model
   - Nightly aggregation Celery task
   - Signal_class assignment logic

3. **Phase 4 — Goal-Signal Configuration** (implementation)
   - GoalSignalSource model
   - Auto-population from goal domain
   - Integration with GoalMomentumService

This way the taxonomy is designed holistically, persistence validates the taxonomy with real data, and goal-signal config builds on proven signal values.

---

## Item 7 — The Conceptual Architecture (Final Statement)

### The Five Layers of WLJ

```
                    ┌───────────────────────────┐
                    │     BETH (AI Reasoning)    │
                    │  Reasons over all layers   │
                    │  Compares planned vs actual │
                    │  Compensatory analysis      │
                    │  Holistic coaching          │
                    └─────────┬─────────────────┘
                              │ reads
              ┌───────────────┼───────────────┐
              │               │               │
    ┌─────────▼────┐  ┌──────▼──────┐  ┌─────▼──────────┐
    │ GOAL MOMENTUM │  │  SIGNALS    │  │ COMMITMENT vs  │
    │               │  │ (Persistent)│  │ ACTUAL GAP     │
    │ Per-goal score│  │ Daily values│  │ What was planned│
    │ from weighted │◀─┤ with class  │  │ vs what happened│
    │ signal sources│  │ and trend   │  │                 │
    └──────────────┘  └──────┬──────┘  └────┬───────┬───┘
                              │              │       │
                              │ generated    │       │
                              │ from         │       │
                    ┌─────────┴──────┐       │       │
                    │                │       │       │
          ┌─────────▼────┐  ┌───────▼───┐   │       │
          │   ACTIVITY    │  │    NLP     │   │       │
          │  (What        │  │ (Inferred) │   │       │
          │   happened)   │  │ Journal &  │   │       │
          │  Read-time    │  │ Capture    │   │       │
          │  aggregation  │  │ extraction │   │       │
          └───────┬───────┘  └───────────┘   │       │
                  │                          │       │
                  │ reads from               │       │
                  │                          │ reads  │ reads
    ┌─────────────▼──────────────────────────▼───────▼──┐
    │              DOMAIN SYSTEMS (Source of Truth)       │
    │  health │ faith │ journal │ life │ purpose │ ...   │
    │  Each domain owns its data and completion records  │
    └─────────────────────┬─────────────────────────────┘
                          │
                          │ projects into
                          ▼
    ┌───────────────────────────────────────────────────┐
    │          COMMITMENTS (CalendarEngine)              │
    │  Unified view of planned actions for a given day  │
    │  source_type → domain system                      │
    │  commitment_level → importance                    │
    │  status → scheduled / completed / canceled        │
    └───────────────────────────────────────────────────┘
```

### The Relationships, Simply Stated

1. **Domain Systems** are the source of truth. They own structured data. They never change for this architecture.

2. **Commitments** (CalendarEngine) are a projection of "what you plan to do today" from domain systems. They have a time, a source, and an importance level.

3. **Activity** is a read-time aggregation of "what you actually did today" from domain systems. No new model — a service that queries completion records across domains.

4. **Signals** are normalized daily scores derived from activity. They have a type (health_activity, faith_practice), a class (verified_action, inferred_behavior), a confidence score, and a value. They are persisted for trending.

5. **Goal Momentum** consumes signals weighted by explicit goal-signal configuration. Each goal declares which signal types matter to it.

6. **Beth** reasons over all five layers simultaneously:
   - What was planned (commitments)
   - What actually happened (activity)
   - What it means (signals + signal_class)
   - How goals are progressing (momentum)
   - What to coach on (compensatory analysis, forward guidance)

### Why This Architecture Is Durable

- **Adding a new domain** (e.g., relationships, education) means: add models, add CalendarEngine projection, add signal type, done. No other layer changes.
- **Adding a new signal source** (e.g., wearable device) means: add to activity aggregation, map to signal type, done.
- **Adding a new goal type** means: create goal, configure signal sources, momentum engine handles the rest.
- **AI improvements** are prompt-level or new PIE rules — no architectural changes needed.

---

## Changes to the Original Assessment

### Phase Order (Revised)

| Phase | Original | Revised | Change |
|-------|----------|---------|--------|
| 1 | Foundation (Task FK) | Foundation (Task↔Goal M2M, CalendarEngine medicine/faith projections, HabitGoal commitment_level) | M2M instead of FK |
| 2 | Unified Daily View | Unified Daily View (DailyScheduleService + DailyActivityService) | Added activity aggregation alongside commitments |
| 3 | Signal Persistence | Signal Taxonomy Design (document) → Signal Persistence (code) | Split into design-first, then implementation |
| 4 | Goal-Signal Config | Goal-Signal Configuration | Unchanged, but now explicitly after signal validation |
| 5 | Journal NLP | Journal NLP + Compensatory Reasoning Engine | Merged — compensatory reasoning needs inferred signals to be meaningful |
| 6 | Beth Reasoning Upgrade | Beth Reasoning Upgrade (relational reasoning, compensatory prompting, signal_class-aware framing) | Enhanced with signal_class trust rules |

### Model Changes (Revised)

| Model | Original | Revised |
|-------|----------|---------|
| Task.goal FK | Direct nullable FK | **Removed** — replaced by TaskGoalLink M2M through model |
| TaskGoalLink | Not proposed | **New** — M2M through model linking tasks to multiple goals |
| HabitGoalLink | Not proposed | **New** — M2M through model linking habits to multiple goals |
| SignalSnapshot.signal_class | Not proposed | **New field** — verified_action / verified_measurement / inferred_behavior / derived_pattern |
| CalendarEvent.commitment_level | Not proposed | **New field** — optional / important / non_negotiable |
| HabitGoal.commitment_level | Not proposed | **New field** — matching Task and LifeGoal pattern |
| CompensatoryRule config | Not proposed | **New** — allowlist of valid compensatory pairs with max_offset_pct |
| RawSignal.signal_class | Not proposed | **New field** on dataclass — classification set at collection time |

### Total New Models: 4
- TaskGoalLink
- HabitGoalLink (could be same pattern as TaskGoalLink via generic relation, but explicit M2M is cleaner)
- SignalSnapshot
- JournalSignal

### Total Model Enhancements: 4
- CalendarEvent + commitment_level
- HabitGoal + commitment_level
- GoalMomentumSnapshot + signal_scores JSONField
- RawSignal dataclass + signal_class field

### Total Estimated Migrations: ~6-7

---

## Additional Architectural Cautions

### Caution 1: Signal Normalization Is Harder Than It Looks
Normalizing "8,000 steps" and "45-minute workout" and "7.5 hours of sleep" into comparable 0.0–1.0 scores requires establishing baselines. Options:
- **Fixed baselines:** 10,000 steps = 1.0, 8h sleep = 1.0 (simple but ignores individual variation)
- **Personal baselines:** Based on user's 30-day history (better but cold-start problem)
- **Recommendation:** Start with fixed baselines from health guidelines. Add personal baseline adjustment in a future phase once enough history exists.

### Caution 2: Compensatory Reasoning Must Be Testable
The compensatory allowlist should be covered by explicit unit tests that verify:
- Non-compensable domains NEVER produce offset signals
- Non-negotiable commitments NEVER produce offset signals
- Each allowlisted pair produces correct max_offset_pct
- Beth's prompt rules are validated against known edge cases

### Caution 3: Signal Taxonomy Stability
Once signal types are defined and persisted, changing them requires data migration. The initial taxonomy should be conservative (6-8 types) and validated against real data before expanding. Adding types is easy. Renaming or merging types is expensive.

### Caution 4: CalendarEngine Projection Testing
Each new source type projection (medicine, faith, workout) must be tested for:
- Create/update/delete lifecycle
- Recurrence edge cases (timezone changes, DST)
- Idempotency key collisions
- Soft delete propagation
- Performance under multi-schedule scenarios (user with 10 medications)

### Caution 5: Don't Over-Engineer the Activity View
The read-time activity aggregation service should start simple: query each domain's completion records for a date, normalize to `{timestamp, title, domain, source_type, source_id, signal_class}`, return sorted list. Don't add filtering, pagination, or search until there's a proven need. The primary consumers are the signal aggregation engine and the daily view.

### Caution 6: Beth's Prompt Is Already Long
Adding signal_class trust rules, compensatory reasoning rules, and commitment-vs-actual framing adds prompt tokens. Monitor token usage and consider moving static rules into a separate system prompt section that's cached, or using structured tool results rather than prose instructions.

---

*This refinement supersedes the relevant sections of ARCHITECTURE_EVOLUTION_ASSESSMENT.md. Both documents should be read together for the complete picture.*
