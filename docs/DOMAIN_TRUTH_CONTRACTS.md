# Domain Truth Contracts — WLJ Architecture Standard

**Last updated: 2026-04-05**

## What This Is

Every user-facing truth claim in WLJ ("Did the user work out?", "Are medicines overdue?", "Was a journal entry written?") flows through a **canonical query contract** — a shared Python class with `@classmethod` methods that return unevaluated QuerySets.

This prevents UI, CoS (Beth), SAE state builders, and the Execution Truth Engine from implementing different logic for the same concept — the root cause of the workout/task/medicine mismatch bugs of 2026-04-04.

## The Pattern

```python
# apps/{domain}/services/{domain}_queries.py

class DomainQueries:
    """Canonical, deterministic queries. No instance state."""

    @classmethod
    def completed_on(cls, user, target_date):
        """Entities completed on a specific date."""
        return Model.objects.filter(user=user, date=target_date, ...)

    @classmethod
    def is_completed_on(cls, user, target_date):
        """Boolean shorthand."""
        return cls.completed_on(user, target_date).exists()
```

**Template**: `apps/life/services/task_queries.py` (the first contract, most mature)

## Rules

1. **All truth-evaluating consumers** (execution truth, SAE builders, CoS context, UI status checks) **MUST** use the contract.
2. **QuerySets are returned unevaluated** — callers chain `.count()`, `.first()`, `.values_list()`, etc.
3. **Semantic variants are explicitly named**: `completed_on()` vs `on_date()` vs `in_range()`.
4. **Display-only queries** (listing pages, search, pagination, admin) are NOT required to use contracts.
5. **No base class or registry** — just convention and documentation.

## Contract Inventory

| Domain | Contract File | Key Methods |
|--------|-------------|-------------|
| **Tasks** | `apps/life/services/task_queries.py` | `pending()`, `overdue()`, `completed_on()`, `due_today()` |
| **Workouts** | `apps/health/services/workout_queries.py` | `completed_on()`, `is_completed_on()`, `on_date()`, `completed_in_range()` |
| **Medicine** | `apps/health/medicine_utils.py` | `calculate_medicine_adherence()`, `calculate_medicine_adherence_rate()` |
| **Routines** | `apps/life/services/routine_helpers.py` | `get_routine_completion_state()`, `auto_complete_routine_schedules()` |
| **Journal** | `apps/journal/services/journal_queries.py` | `on_date()`, `has_entry_on()`, `recent()`, `with_mood()` |
| **Faith** | `apps/faith/services/faith_queries.py` | `active_reading_plans()`, `has_reading_on()`, `unanswered_prayers()` |
| **Goals** | `apps/purpose/services/goal_queries.py` | `active()`, `with_milestones()`, `overdue()` |
| **Habits** | `apps/life/services/habit_queries.py` | `active()` |
| **Nutrition** | `apps/health/services/nutrition_queries.py` | `entries_on_date()`, `has_logged_on()`, `entries_in_range()` |
| **Fasting** | `apps/health/services/fasting_queries.py` | `current_active()`, `is_fasting()`, `completed_in_range()` |
| **Capture** | `apps/capture/services/capture_queries.py` | `pending_uploads()`, `ready_recent()`, `today()`, `stale()` |

## What Belongs in Contracts vs. What Doesn't

### IN the contract:
- Completion/status checks (is_completed, is_active, is_overdue)
- Standard filtered querysets (pending, active, completed_on, in_range)
- Shared calculations (adherence, streaks, counts)

### NOT in the contract:
- CRUD mutations (create, update, delete) — live in views/services
- Display-only queries (listing, pagination, search)
- Admin queries
- One-off analytics that don't affect truth claims
- Event adapters (they source events, not truth)

## Semantic Variants

When a domain has multiple valid meanings of "done", name them explicitly:

| Method | Meaning | Use Case |
|--------|---------|----------|
| `WorkoutQueries.completed_on()` | Finished workout (completed_at OR has exercises OR has duration) | Execution truth, SAE, UI status |
| `WorkoutQueries.on_date()` | Any session, including in-progress | Suppress check-in prompts, protein-day detection |
| `TaskQueries.pending()` | Not completed, not skipped | All pending task counts |
| `TaskQueries.overdue()` | Pending + past due date | Urgency alerts |

## Adding a New Contract

1. Create `apps/{domain}/services/{domain}_queries.py`
2. Add `@classmethod` methods returning QuerySets
3. Update consumers (SAE builder, execution truth, views) to import from it
4. Add entry to the inventory table above
5. Add regression test in `apps/core/tests/test_domain_truth_contracts.py`
