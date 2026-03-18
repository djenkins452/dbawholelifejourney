# SAE Rich State Contract — Migration Reference

**Last updated:** 2026-03-18
**Status:** Phase 1.75B — Contract overlay active, flat keys preserved

## Architecture

SAE domain builders produce a flat-key dict (operational interface) plus a
`_contract` overlay (canonical target structure) and `_meta` (reliability signal).

**Current rule:**
- Flat keys = operational interface consumed by 50+ files
- `_contract` = canonical structure for future migration
- `_meta` = state reliability metadata
- All new domains (Phase 2+) should design to `_contract` first

**Migration path:**
1. Phase A: Add `_contract` overlay (**DONE**)
2. Phase B: Migrate consumers to read `_contract` (FUTURE)
3. Phase C: Remove flat keys (FUTURE — only after all consumers migrated)

---

## Standard Contract Shape

Every domain with a `_contract` overlay follows:

```python
{
    # Flat keys (current operational interface)
    "some_flat_key": value,
    ...

    # Canonical target structure
    "_contract": {
        "summary": {},   # Aggregates, counts, scores
        "today": {},     # Current day items, in-progress, time-aware
        "upcoming": {},  # Near-future items
        "alerts": {},    # Overdue, missed, conflicts, risks
    },

    # State reliability metadata
    "_meta": {
        "last_updated": "ISO timestamp",
        "source": "SAE",
        "completeness": "full | partial | limited",
        "confidence": "high | medium | low",
    },
}
```

---

## Domain Mapping Tables

### Tasks (`build_task_state`)

| Flat Key | Contract Path | Type |
|----------|--------------|------|
| `tasks_now` | `_contract.summary.by_priority.now` | int |
| `tasks_soon` | `_contract.summary.by_priority.soon` | int |
| `tasks_someday` | `_contract.summary.by_priority.someday` | int |
| `active_tasks_by_level` | `_contract.summary.by_level` | dict |
| `completed_today` | `_contract.summary.completed_today` | int |
| `completed_today_detail` | `_contract.today.completed` | dict |
| `completed_today_titles` | `_contract.today.completed.titles` | list |
| `due_today_tasks_detail` | `_contract.today.items` | list[dict] |
| `tasks_due_today` | (legacy title list — no contract equivalent) | list[str] |
| `next_up_task` | `_contract.today.next_up` | dict |
| `overdue_tasks` | `_contract.alerts.overdue` | list[dict] |
| `overdue_count` | `_contract.alerts.overdue_count` | int |
| `nn_skip_streaks` | `_contract.alerts.nn_skip_streaks` | list |
| `due_tomorrow_tasks` | `_contract.upcoming.tomorrow` | list[dict] |
| `future_tasks` | `_contract.upcoming.future` | list[dict] |
| `no_due_date_tasks` | `_contract.upcoming.no_due_date` | list[dict] |
| `due_tomorrow_count` | (count derivable from upcoming.tomorrow) | int |
| `task_commitment_summary` | (partial in summary.nn_consistency_score) | dict |
| `overdue_nn_count` | (no direct mapping — derivable from alerts) | int |

### Calendar (`build_calendar_state`)

| Flat Key | Contract Path | Type |
|----------|--------------|------|
| `today_event_count` | `_contract.summary.today_count` | int |
| `schedule_density` | `_contract.summary.schedule_density` | float |
| `today_events` | `_contract.today.items` | list[dict] |
| `current_event` | `_contract.today.current_event` | dict/None |
| `next_event` | `_contract.today.next_event` | dict/None |
| `overdue_events` | `_contract.alerts.overdue` | list[dict] |
| `schedule_conflicts` | `_contract.alerts.conflicts` | list[dict] |
| `upcoming_events` | `_contract.upcoming.events` | list[dict] |

### Medicine (`build_medicine_state`)

| Flat Key | Contract Path | Type |
|----------|--------------|------|
| `active_count` | `_contract.summary.active_count` | int |
| `active_medicines` | `_contract.summary.active_medicines` | list[str] |
| `adherence_7d` | `_contract.summary.adherence_7d` | float |
| `expected_today` | `_contract.summary.expected_today` | int |
| `today_taken` | `_contract.today.taken` | int |
| `today_missed` | `_contract.today.missed` | int |
| `today_pending` | `_contract.today.pending` | int |
| `schedule_status_today` | `_contract.today.schedule_status` | list[dict] |
| `needs_refill` | `_contract.alerts.needs_refill` | list[str] |

### Routine (`build_routine_state`)

| Flat Key | Contract Path | Type |
|----------|--------------|------|
| `total_routines` | `_contract.summary.total_routines` | int |
| `today_item_count` | `_contract.summary.today_count` | int |
| `today_completed` | `_contract.summary.today_completed` | int |
| `today_missed` | `_contract.summary.today_missed` | int |
| `routine_items_today` | `_contract.today.items_by_window` | dict |
| `current_window` | `_contract.today.current_window` | str |
| `next_pending_item` | `_contract.today.next_up` | dict/None |

---

## Consumer Inventory

### Tasks flat-key consumers

| File | Keys Read | Context |
|------|-----------|---------|
| `apps/core/ai_orchestrator/cos_context.py` | overdue_tasks, due_today_tasks_detail, due_tomorrow_tasks, future_tasks, no_due_date_tasks, tasks_now, tasks_soon, tasks_someday, completed_today, overdue_count, nn_skip_streaks, completed_today_titles, next_up_task, completed_today_detail | CoS context |
| `apps/life/views.py` | next_up_task | View |
| `apps/ai/state_assessment.py` | completed_today, overdue_count, tasks_now | Assessment |

### Medicine flat-key consumers

| File | Keys Read | Context |
|------|-----------|---------|
| `apps/core/ai_orchestrator/cos_context.py` | active_count, adherence_7d, expected_today, today_taken, active_medicines, today_missed, today_pending, needs_refill, schedule_status_today | CoS context (2 blocks) |
| `apps/ai/deterministic_router.py` | active_count, adherence_7d, today_taken, today_missed, today_pending, expected_today | AI routing |
| `apps/ai/state_assessment.py` | adherence_7d | Assessment |
| `apps/ai/deterministic_health_summary.py` | adherence_pct_7d (via 'medication' key — **BUG**: wrong domain key) | AI routing |

### Calendar flat-key consumers

| File | Keys Read | Context |
|------|-----------|---------|
| `apps/core/ai_orchestrator/cos_context.py` | today_events, current_event, next_event, schedule_density, today_event_count, overdue_events, schedule_conflicts, upcoming_events | CoS context |

### Routine flat-key consumers

| File | Keys Read | Context |
|------|-----------|---------|
| `apps/core/ai_orchestrator/cos_context.py` | total_routines, today_item_count, today_completed, today_missed, current_window, routine_items_today, next_pending_item | CoS context |

---

## Routine Canon Decision

**Canonical source:** `Routine` / `RoutineSchedule` / `RoutineLog` (apps.life.models)
**Legacy:** `Task.is_routine` — NOT used in routine state builder

The routine SAE builder reads ONLY from the dedicated routine models.
`Task.is_routine` tasks remain in task state where they belong.

---

## Known Issues

1. **`deterministic_health_summary.py`** uses domain key `'medication'` instead of `'medicine'` — likely returns empty dict silently.
2. **`cos_context.py`** reads medicine state twice in two try-blocks — should consolidate.
3. **`state_assessment.py`** has two read paths for same domains (get_module_state + direct sd.get).

---

## Validation

State contract validator: `apps/core/ai_state/state_validator.py`
- Validates `_contract` shape for all Phase 1 domains
- Validates `_meta` completeness and confidence values
- Can be called from tests or background observability tasks
