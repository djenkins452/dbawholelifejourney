# Calendar Engine — Admin Guide

**App:** `apps.calendar_engine`
**URL Prefix:** `/calendar/`
**Created:** 2026-02-19

---

## Overview

The Calendar Engine provides a unified time interface for the Whole Life Journey CoS (Chief of Staff). It projects Tasks, Goals, and Habits onto a single calendar timeline, supports drag-and-drop with writeback to source items, and includes behavioral features (Habit Protection Layer, Smart Gap Detection, Domain Imbalance Bar).

---

## Models

### CalendarEvent
The core model. Each event can be:

| Event Kind | Description |
|-----------|-------------|
| `manual` | User-created events (not linked to source) |
| `deadline_marker` | Auto-projected from task/goal due dates |
| `execution_block` | Scheduled work time linked to a task/goal |
| `external_readonly` | Read-only events from external sources |

**Source Linking:** `source_type` + `source_id` link to the original Task, Goal, Habit, etc. Calendar edits on projected events write back to the source.

### RecurrenceRule
One-to-one with CalendarEvent. Stores frequency, byweekday (JSON list of ISO weekday numbers), interval, until date, and count. Occurrences are computed dynamically — no row-per-occurrence storage.

### RecurrenceException
For single-occurrence overrides in a recurring series (moved or canceled).

### CalendarOverrideLog
Audit trail for when users override protected-event conflicts.

---

## Services

| Service | File | Purpose |
|---------|------|---------|
| **Projection** | `services/projection.py` | Syncs tasks/goals/habits → CalendarEvent |
| **Conflicts** | `services/conflicts.py` | Detects overlaps with protected events |
| **Suggestions** | `services/suggestions.py` | Smart Gap Detection — finds open windows and suggests execution blocks |
| **Metrics** | `services/metrics.py` | Domain Imbalance Bar — time per domain |
| **NLP Parse** | `services/nlp_parse.py` | Natural language quick-add parser |

### Projection Functions
- `upsert_from_task(task)` — creates/updates DEADLINE_MARKER from task.due_date
- `upsert_execution_block_for_task(task, start_dt, end_dt)` — creates EXECUTION_BLOCK
- `upsert_from_goal(goal)` — creates DEADLINE_MARKERs for goal + milestones
- `upsert_from_habit(habit)` — creates recurring event with is_protected=True
- `delete_*_events()` — cleanup functions

### Integration Points
Call projection functions from existing CRUD views when tasks/goals/habits are created, updated, or deleted. Example:

```python
from apps.calendar_engine.services.projection import upsert_from_task

# In task create/update view:
task.save()
upsert_from_task(task)
```

---

## API Endpoints

| Method | URL | Purpose |
|--------|-----|---------|
| GET | `/calendar/` | Dashboard (Today Timeline default) |
| GET | `/calendar/api/today/` | Events for today |
| GET | `/calendar/api/range/?start=&end=` | Events in date range |
| POST | `/calendar/api/events/` | Create manual event |
| GET | `/calendar/api/events/<id>/` | Get event detail |
| PATCH | `/calendar/api/events/<id>/` | Update event |
| DELETE | `/calendar/api/events/<id>/` | Delete event |
| POST | `/calendar/api/events/<id>/move/` | Drag-drop move with writeback |
| GET/POST | `/calendar/api/suggestions/gaps/` | Smart Gap suggestions |
| POST | `/calendar/api/suggestions/accept/` | Accept suggestion → create execution block |
| GET | `/calendar/api/metrics/balance/?period=today\|week` | Domain balance percentages |
| POST | `/calendar/api/nlp_create/` | Natural language quick add |

### Move API (Drag-Drop)
POST body: `{new_start_dt, new_end_dt, override: bool}`

- Returns 200 on success with updated event
- Returns 409 on protected conflict with `{conflict: true, conflict_message, conflicting_events}`
- When `override: true`, logs the override and allows the move

### NLP Quick Add
POST body: `{text: "Bible Study Wednesdays 6pm-8pm"}`

Parses day names, time ranges, recurring keywords, and domain hints. Creates event + recurrence rule.

---

## Django Admin

All models are registered:
- **CalendarEventAdmin** — list with filters for kind, source, status, protected
- **RecurrenceRuleAdmin** — inline on event, also standalone
- **CalendarOverrideLogAdmin** — audit trail

---

## Dashboard Views

Default view: **Today Timeline** with toggles for Today | 3-Day | Week | Agenda.

Sidebar includes:
- **Quick Add** — NLP text input
- **Smart Suggestions** — one-click accept for execution blocks

Top: **Domain Imbalance Bar** — visual bar showing time distribution across life domains (Faith, Health, Family, Work, etc.)

---

## Configuration

| Setting | Location | Default |
|---------|----------|---------|
| Min gap for suggestions | `services/suggestions.py:MIN_GAP_MINUTES` | 90 minutes |
| Lookahead for due items | `services/suggestions.py:LOOKAHEAD_DAYS` | 14 days |
| Execution check window | `services/suggestions.py:EXECUTION_CHECK_DAYS` | 7 days |
| Work day window | `services/suggestions.py:find_gaps_for_day` | 6 AM – 10 PM |

---

## Tests

29 tests in `apps/calendar_engine/tests.py` covering:
- Task/Goal/Habit projection CRUD
- Drag-drop writeback to task.due_date
- Protected conflict detection and override logging
- Gap detection and suggestion generation
- Accept suggestion → execution block creation
- Domain balance percentages sum to 100%
- NLP parsing (Bible Study, gym, meetings)
- All API endpoints (GET, POST, PATCH, DELETE, move)
- Dashboard loads with correct content
