# WLJ Calendar — Projection Architecture (Design Note)

> **Status:** Canonical for the Calendar module. **Established:** 2026-07-07.
> Subordinate to `WLJ_ARCHITECTURE_LAWS.md`. This is an **evolution of the existing
> `calendar_engine` module**, not a new platform — the Calendar stayed recognizable.

## The one sentence

**The Calendar is the projection of time across WLJ.** It answers one question —
*"what occupies my time?"* — and owns **time**, not **objects**.

## The Calendar Projection Law

1. **Each domain owns its own truth.** Tasks own tasks; Medicine owns medications;
   Workouts own workouts; Goals own goals; Faith owns reading plans; Routines own
   routines. The Calendar owns only calendar-native objects (manual Calendar Events
   and Availability Blocks).
2. **The Calendar projects those truths into time** — it never becomes a second owner.
3. **Editing from the Calendar edits the owning object.** Click a task → the Task
   editor; a medication → Medicine; a workout → Workouts; a Calendar Event or
   Availability Block → the calendar's own editor.
4. **The materialized `CalendarEvent` rows are a non-authoritative cache/interface** —
   never a source of truth, never user-editable as if they were.
5. **The timeline tells the truth about time.** Only items with a real execution time
   occupy the timeline; due-dated items with no time appear in a separate "Due Today"
   lane with **no fabricated execution window**. Recommending *when* to do an
   unscheduled item is the Chief of Staff's job — out of scope for the Calendar.

## How it was built — by extending existing components (no new frameworks)

This was deliberately kept to the **smallest footprint**. There is **no** projection
engine, provider registry, editor-routing framework, or new service layer.

- **Projection** = the existing `apps/calendar_engine/views.py :: _get_events_in_range()`,
  extended to also yield Availability Block occurrences (flagged
  `event_kind='availability'`). The existing `/api/today/` and `/api/range/` endpoints
  serve them. Because Availability Blocks are a separate model, they never enter the
  `CalendarEvent` stream the ~49 other consumers read.
- **Editing routes to owners** = the existing `SOURCE_URLS` map in
  `templates/calendar_engine/dashboard.html`, extended to every source type; the click
  handler navigates to the owning object (calendar-native events open the existing modal).
- **Recurrence** = the existing `RecurrenceRule` gained a reusable `expand()`
  classmethod (DST-safe, exception-aware). `get_occurrences()` now applies
  `RecurrenceException` (previously a silent no-op). **Availability Blocks reuse
  `RecurrenceRule.expand()`.** Task recurrence stays in `life.RecurrencePattern`; the
  engines are **not** merged.
- **`_auto_create_backing_task` was removed** from `CalendarMutationService` so a manual
  Calendar Event stays calendar-native (`source_type=none`) instead of manufacturing a
  Task in the Life domain.

## Availability Blocks (a Calendar-native feature, not a Layer 1 domain)

`AvailabilityBlock` (one model) describes when the user is available/unavailable — a
planning constraint (work hours, PTO), **not** a Task, Event, or Routine. It belongs to
the Calendar because the Calendar owns time.

- Fields: label, `kind` (available/unavailable), time window, inline recurrence
  (frequency/byweekday/interval/until/count/timezone), and a JSON `exceptions` list.
- **Outlook-style recurring edits** are model methods: `cancel_occurrence()` /
  `move_occurrence()` (single occurrence, stored in the JSON `exceptions` list),
  `split_future()` (this-and-future — caps the series and creates a new block), and
  in-place field edits (entire series).
- Read via `AvailabilityBlock.active(user)`; managed at `/calendar/availability/` with a
  CRUD API under `/calendar/api/availability/`.
- Single-occurrence overrides live in JSON (not a table) because they only alter
  recurrence generation and aren't reported on independently. If reporting is ever
  needed, migrate to a table then.

## Why this satisfies the Architecture Laws

- **F4 (Single Source of Truth):** editing always hits the owning domain; the cache is
  derived, never authoritative.
- **F5 (Never Compute on the Request Path):** projection reads are bounded, indexed
  lookups gated by a query-budget regression test (profiles query count).
- **F1/F2:** the Calendar is pure deterministic truth; Beth/CoS untouched.
- **F7 (Visual Truth Contract):** committed-vs-due separation keeps due items from
  wearing "scheduled" visuals.

## Cache posture (why materialization stays)

~49 files outside `calendar_engine` read `CalendarEvent` as truth (drift, blueprint,
`today_engine`, `ai_state`, much of `apps/cos/**` + `apps/ai/**`) — mostly out-of-scope
Beth/CoS systems. So the materialized `CalendarEvent` cache and its projection signals
stay; full de-materialization is a separate future initiative. Google Calendar export is
preserved.

## Invariants (regression-guarded in `tests/test_projection_layer.py`)

1. Projection never fabricates an execution time; due items stay off the timeline.
2. Editing a projected block navigates to its owning domain; it never edits the cache.
3. Native recurrence honors `RecurrenceException`; Task recurrence stays in `life`.
4. Availability recurrence + this/future/series edits behave; overrides persist in JSON.
