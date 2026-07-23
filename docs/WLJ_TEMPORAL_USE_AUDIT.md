# Temporal-Use Audit & User-Local Semantics Certification

**Date:** 2026-07-23
**Status:** Phase 1 audit COMPLETE · first slice IMPLEMENTED + CERTIFIED — AWAITING PRODUCTION VALIDATION
**Builds on:** `docs/WLJ_CALENDAR_BOUND_TRUTH.md` (`49d9e0d1`) — the snapshot-rollover class, now closed
**Companion:** `apps/core/truth/calendar_day.py` (the authority) · `apps/core/tests/test_user_local_temporal_contract.py` (the CI guard)

---

## 0. Why classification comes first

A global search-and-replace of `timezone.now()` would be **wrong**. Most temporal uses in
the truth layer are legitimately absolute. The risk is narrower and specific: a
calculation that represents the user's *lived calendar* silently using a UTC, server,
naive, or independently-computed boundary.

So every site is classified by **meaning** before anything is touched.

## 1. Phase 1 — classification totals

212 temporal call sites across the deterministic truth layer
(`health/services`, `meals/services`, `life/services`, `core/truth`, `core/ai_state`,
`ai/cos_services`, `journal`, `faith`, `purpose/services`, `core/execution`):

| Category | Meaning | Sites | User-local required? |
|---|---|---:|---|
| **A** | System instant (audit, cache age, telemetry, ordering, elapsed) | **79** | No — UTC/system correct |
| **B** | User-local calendar truth (today, yesterday, overdue, day totals) | **60** | **Yes** |
| **C** | User-local rolling period (last 7 calendar days, this week/month) | **42** | **Yes** |
| **D** | Source-observed instant (device/measurement timestamps) | **4** | Preserve instant; convert only to answer a calendar question |
| **E** | System/business schedule (billing, cron, maintenance) | **27** | No — business timezone |

**102 sites (B + C) must consume the canonical user-local authority.** A+D+E = 110 are
correct as-is and were **not modified**.

> Category counts come from an automated first pass (`scratchpad/phase1_temporal_classify.py`).
> The classification is a *starting map*, not a verdict: **no site is changed until its
> category is confirmed by reading it.** That is how the slice below was chosen.

## 2. Selected slice — the canonical Task day authority

**Chosen by customer-trust risk**, not by file count:

| Criterion | Why Task won |
|---|---|
| Direct daily answer | "What's due today?" / "Am I overdue?" — asked constantly |
| Cross-midnight contradiction | Proven wrong on **both** sides at one instant |
| Consuming surfaces | CoS executive context, situation computer, SAE snapshot, dashboards, Action Center |
| **Drives an action** | Overdue status escalates and prompts the user |
| Coherence | One authority file, four sibling methods — a clean bounded slice |

### Proven pre-fix defect

`TaskQueries.overdue / due_today / due_tomorrow / due_future` documented *"user
timezone"* but defaulted to `timezone.localdate()` — the **server** date
(`settings.TIME_ZONE = UTC`). At 8:00 PM Pacific (03:00 UTC the next day):

```
server/UTC date : 2026-07-23
USER-local today: 2026-07-22  (America/Los_Angeles)

TaskQueries.due_today(user) -> ["Due on the user's tomorrow"]   *** wrong day
TaskQueries.overdue(user)   -> ["Due on the user's today"]      *** nothing IS overdue
```

Real consumers relied on that default — `apps/ai/chatgpt_cos/executive_interpretation.py`
(`due_today`, `overdue`) and `apps/core/ai_state/situation_computer.py` (`overdue` ×2).
For every user west of UTC, each evening the CoS could report a task overdue that was not.

### After

```
TaskQueries.due_today(user) -> ["Due on the user's today"]
TaskQueries.overdue(user)   -> []
TaskQueries.due_tomorrow(user) -> ["Due on the user's tomorrow"]
```

Also migrated in the same slice: `history_search._today()` anchored rolling windows
(`7d`, `week`) to the **UTC** date; it now takes the user and anchors to their calendar
(Category C).

## 3. Phase 5 — instant preservation vs day attribution

Both are certified, and they are different things:

* The **absolute instant is never rewritten.** A record created `2026-07-24T03:00:00Z`
  keeps that instant, its timezone, and its microsecond precision.
* Its **user-local attribution** for an `America/New_York` user is `2026-07-23`
  (11:00 PM EDT), and a calendar question at that moment includes it as *today*.

Asserted by `InstantVersusDayAttributionTests`.

## 4. Certification

`apps/life/tests/test_task_user_local_dates.py` — **13 gates**: the proven boundary
defect; day advances exactly once after the user's midnight; a zone *ahead* of UTC
(Sydney); all nine required zones each get their own `due_today`; an explicit `as_of`
still wins (only the default changed); DST spring-forward, leap day, month rollover,
year rollover; instant-vs-attribution; rolling-window anchoring; and **surface
agreement** — canonical producer, SAE snapshot projection and the model-facing
`get_domain_state` all return the same records for the same user-local day, with the
snapshot declaring `day_state_date` / `day_freshness` / `user_local_date` / `timezone`.

`apps/core/tests/test_user_local_temporal_contract.py` — **the CI guard (4 gates)**,
deliberately **allow-list / semantic registration** rather than a broad regex, because
79 Category-A and 27 Category-E sites are legitimately UTC. A module joins
`USER_CALENDAR_SERVICES` when it is certified; inside those files a server-clock date
derivation fails CI. Comments and docstrings are stripped via `tokenize` first (a
docstring *explaining* the defect must not trip the gate). It also asserts the authority
stays a **façade** — still delegating, and never growing its own `weekday()`/
`isocalendar()` math. One documented exception: `history_search._today(user=None)`
retains a server fallback for the no-user case, which the search path never takes.

## 5. Phase 7 — runtime evidence (real gpt-4o, ToolCallLog)

User `America/Los_Angeles`, clock frozen at **8:00 PM Pacific** (UTC already the next
day) — the exact instant that produced the defect. **8/8:**

| Question | Result |
|---|---|
| "How much protein did I get yesterday?" | ✅ 88 g (the user's Jul 21) — `get_history(period="yesterday")` |
| "What did I eat today?" | ✅ the Jul 22 lunch — `get_entity(on_date="today")` |
| "What tasks do I have due today?" | ✅ "Pay the water bill" via `get_domain_state(tasks)` |
| (same turn) | ✅ **no false "overdue" claim** |
| "How am I doing this week?" | ✅ no UTC-date claim |
| follow-up "And calories?" | ✅ stays on yesterday → 1,400 kcal |
| "I logged something at 11 PM last night — which day?" | ✅ answered in local-day terms |

## 6. Phase 9 — ranked residual backlog

Ranked by daily-answer risk × cross-midnight contradiction × consumers × action-driving:

| Rank | Slice | Sites | Why |
|---|---|---:|---|
| 1 | `purpose/services/goal_queries.py` — `overdue`, `overdue_milestones` | 2 | Same *overdue* class just proven in Tasks; drives goal escalation |
| 2 | `core/execution/timing.py` — `compute_execution_timing`, `completed_ahead_of_schedule` | 3 | Feeds the execution/decision authority; "on time?" is a day judgement |
| 3 | `life/services/recurrence.py` — recurring-task rollover | 2 | Generates the *next occurrence*; a wrong day writes a wrong record |
| 4 | `health/services/weight_summary.py`, `trend_analyzer.py`, `correlation_service.py` | ~4 | Calendar-defined analytic windows behind page + Current Context |
| 5 | `meals/services/*` (advanced_intelligence, meal_scoring, waste, inventory_gap) | ~8 | Meal-day attribution and expiry; user-visible but lower frequency |
| 6 | `health/services/cycle_*`, `protein_service`, `baseline_policy` | ~10 | Longer windows; DST-exposed but less midnight-sensitive |

**Recommended next slice: rank 1 + 2 together** — both are the *overdue / on-time*
judgement class, they share the `TaskQueries` pattern just certified, and together they
close "is it late?" across Goals and Execution.

Not implemented in this milestone by instruction.

## 7. Remaining risks

* The classifier is heuristic; ranks 4–6 need per-site reading before change (some are
  genuinely Category A).
* `settings.TIME_ZONE = UTC` means server-date bugs are invisible to UTC-resident
  developers and only appear for users west of UTC — boundary fixtures are the only
  reliable detection.
* Pre-existing and untouched: `apps.life.tests.test_models` fails to import (stale
  `Recipe` import; `Recipe` lives in the meals app), plus `test_empty_health_state`,
  `test_nutrition_entity_truth`, `test_chatgpt_cos_clean`, `test_p29_morning_and_precedence`.
