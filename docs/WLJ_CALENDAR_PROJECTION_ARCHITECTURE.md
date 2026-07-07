# WLJ Calendar — Projection Architecture (Governing Design Record)

> **Status:** Canonical for the Calendar module. **Established:** 2026-07-07.
> Subordinate to `WLJ_ARCHITECTURE_LAWS.md` (the platform constitution) and
> `LAYER1_DOMAIN_FRAMEWORK.md`. Where a convenience or ticket conflicts with this
> record, this record wins for Calendar; where the Architecture Laws conflict with
> this record, the Laws win. Changes require owner approval.

---

## The one sentence

**The Calendar is the projection of time across WLJ.** It answers exactly one
question — *"What occupies my time?"* — and it owns **time**, not **objects**.

## The Calendar Projection Law

1. **Each domain owns its own truth.** Tasks own tasks; Medicine owns medications;
   Workouts own workouts; Goals own goals; Faith owns reading plans; Routines own
   routines; Calendar owns *only* calendar-native objects (manual Calendar Events
   and Availability Blocks).
2. **The Calendar projects those truths into time.** It never becomes a second
   owner of any domain's object.
3. **Editing from the Calendar always edits the owning domain.** Click a task →
   the Task editor. Click a medication → the Medicine editor. Click a workout →
   the Workout editor. Click a Calendar Event or Availability Block → the calendar
   editor (because those *are* calendar-native).
4. **The projection/cache is an implementation detail.** The materialized
   `CalendarEvent` rows are a non-authoritative read cache. They must never be an
   authoritative source of truth and must never be user-editable as if they were.
5. **The Calendar tells the truth about time.** Only items with a real execution
   time occupy the timeline. Due-dated items with no execution time are shown
   separately, with **no fabricated execution window**. Recommending *when* to do
   an unscheduled item is strategy (the Chief of Staff), explicitly **out of scope**
   for the Calendar.

## Why this satisfies the Architecture Laws

- **F4 (Single Source of Truth):** one owner per fact — editing routes to the owner;
  the cache is derived, never authoritative.
- **F3 (Framework-First):** new domains join the calendar by registering **one**
  `TimeProvider` against their canonical `*_queries.py` truth — never by
  special-casing the calendar.
- **F1/F2 (Truth vs Reasoning; LLM-Last):** the Calendar is pure deterministic
  truth; no LLM in the path. Beth is untouched.
- **F5 (Never Compute on the Request Path):** projection reads are bounded
  (day/week window, indexed lookups) and gated by a query-budget regression test;
  a background snapshot behind the same contract is the escape hatch if a wider
  view exceeds budget. We never trade F4 for an F5 violation.
- **F7 (Visual Truth Contract):** committed vs due separation means only real
  execution times render as "scheduled."

---

## Architecture

### The read contract — `TimeProjection`

`apps/calendar_engine/services/time_projection.py`

```
TimeProjection.for_range(user, range_start, range_end) -> ProjectionResult
    .committed   [ProjectedBlock]   # real execution times occupy the timeline
    .due         [ProjectedBlock]   # due-dated, NO execution time (never on timeline)
    .constraints [ProjectedBlock]   # availability blocks (planning constraints)
```

`ProjectedBlock` is a read-only DTO — the surface-agnostic answer to "what occupies
this slice of time." It carries `origin`, `source_type`, `source_id`, `title`,
`start_dt`, `end_dt`, `lane`, `domain`, `domain_color`, and `editor_route` (the deep
link to the **owning** domain's editor). Nothing on the calendar renders without a
`ProjectedBlock`.

### The provider registry (framework-first)

Every source of time is a `TimeProvider` that returns `ProjectedBlock`s for a range.
Adding a domain = registering one provider, never editing the calendar core.

- `CalendarCacheProvider` — reads the existing materialized `CalendarEvent` cache
  (manual events + the projected rows kept in sync by `services/projection.py`).
  This is the compatibility path and preserves exact parity today. **It is the seam:**
  a future per-domain *live* provider (reading `Task`, `MedicineQueries`, … directly)
  can replace the cache read for its `source_type` with **zero UI change**.
- `AvailabilityProvider` — reads the calendar-native `AvailabilityBlock` model
  **live** (it is not in the legacy cache). This is the first live provider and
  demonstrates the registry's purpose.

### Editor routing — edit the owner, never the cache

`apps/calendar_engine/services/editor_route.py :: resolve_editor_route(...)` maps a
block to where it is truly edited:

| source_type            | routes to (owning domain)         |
|------------------------|-----------------------------------|
| `none` (manual event)  | calendar edit modal (native)      |
| `availability`         | Availability editor (native)      |
| `task`                 | `life:task_update`                |
| `life_event`           | `life:event_update`               |
| `goal`                 | `purpose:goal_detail`             |
| `goal_milestone`       | `purpose:milestone_update`        |
| `habit`                | `purpose:habit_goal_detail`       |
| `medicine_schedule`    | `health:intake_home`¹             |
| `workout_schedule`     | `health:workout_list`¹            |
| `faith_routine`        | `faith:reading_plans`¹            |

¹ Per-object deep links for these three need a source→owner pk resolution (schedule
→ intake, schedule → plan, plan → slug); today they route to the domain landing.
A future refinement (not scope creep) can make them per-object. The law is already
satisfied: the click edits the **owning domain**, never the calendar cache.

Only **native** blocks (`none`, `availability`) are editable inside the Calendar.
Everything else navigates out to its owner.

---

## Availability Blocks (new calendar-native Layer 1 domain)

Availability is *inherently* time-shaped, so the Calendar legitimately owns it.
`AvailabilityBlock` is **not** a Task, Event, or Routine — it is a planning
**constraint** ("Work, Mon–Fri 7:30 AM–6:00 PM, unavailable, recurring") that any
planner in WLJ can read to know when the user is realistically available.

- Model: `AvailabilityBlock` (label, `kind = available | unavailable`, time window,
  optional `RecurrenceRule`, exceptions).
- Truth contract: `apps/calendar_engine/services/availability_queries.py`
  (`AvailabilityQueries.for_range`, `.describe`) — the canonical read every consumer
  uses (F4).
- Recurrence: **calendar-native objects standardize on `calendar_engine.RecurrenceRule`.**
  Task recurrence remains `life.RecurrencePattern`. The two engines are **not** merged
  in this project — each domain owns its recurrence; the Calendar consumes recurrence
  outputs as projections.

### Outlook-style recurrence semantics (calendar-native only)

`RecurrenceException` was a dead model — `RecurrenceRule.get_occurrences()` never
applied it. It now does. Supported edits for native recurring objects:

- **This occurrence** — a `RecurrenceException` (move or cancel a single instance).
- **This and future** — split the series: cap the original rule (`until_dt`) at the
  edit boundary and create a new native object + rule from the edit date forward.
- **Entire series** — edit the base object + rule directly.

---

## Migration posture (why the cache stays)

~49 files outside `apps/calendar_engine/` read `CalendarEvent` as truth — the drift
engine, blueprint/architecture engine, `today_engine`, `ai_state`, and much of
`apps/cos/**` + `apps/ai/**` (executive briefing, proactive check-ins). Most are the
Beth/CoS/executive systems that are **out of scope**. Therefore:

- **The materialized cache stays.** `services/projection.py` and its signals keep
  running. The rows are re-cast as a **non-authoritative** cache + compatibility feed.
- **Full de-materialization is a separate, future initiative** gated on migrating
  those consumers onto `TimeProjection`. It is not part of this project.
- **Google Calendar export** (`CalendarMutationService._sync_to_google`) is preserved.

### What changed to enforce the law now (Phases 0–3)

- **Phase 0:** `TimeProjection` contract + provider registry + `ProjectedBlock` DTO.
  `CalendarCacheProvider` wraps the existing range read (exact parity).
- **Phase 1:** All editing routes to the owning domain via `resolve_editor_route`.
  `CalendarMutationService._auto_create_backing_task` is **retired** — a manual
  Calendar Event stays calendar-native (`source_type=none`) instead of secretly
  manufacturing a Task in the Life domain.
- **Phase 2:** Truth split completed server-side — the projection returns
  `committed` / `due` / `constraints` lanes; the UI renders from lanes; no fabricated
  times anywhere. Query-budget regression test lands here.
- **Phase 3:** `AvailabilityBlock` domain + `availability_queries.py` +
  `AvailabilityProvider` + editor; `RecurrenceException` fixed and this/future/series
  semantics added for native objects.

---

## Invariants (regression-guarded)

1. Projection never fabricates an execution time; deadline/due items are `due` lane.
2. Editing a projected block navigates to its owning domain; it never edits the cache.
3. The cache is never presented as authoritative and never user-editable in place
   except for native (`none`, `availability`) blocks.
4. Adding a domain to the calendar is one `TimeProvider` registration.
5. Native recurrence honors `RecurrenceException`; Task recurrence stays in `life`.
