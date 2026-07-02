# Significant Event Pipeline — the Chief-of-Staff reflex

**Status:** v1 implemented & tested (2026-07-02). Additive; no new model; no migration.

> A production-ready Chief of Staff does not wait for a scheduler to notice that
> something important happened. When a mission-significant event occurs it must,
> **in the moment**: detect it, determine why it matters, update dependent truth,
> notify appropriately, and re-evaluate the plan.

---

## Origin (the capability gap)

Danny hit the **France 2027 Family 18K Mission** weight milestone — 283.1 lb
against a 284.9 lb target due June 30, achieved July 2 (two days late, but
achieved). The dashboard number updated, but **nothing recognized it as
mission-significant** until the 3-hour CoS Event Engine scheduler happened to run.

Root cause (investigated, not assumed): WLJ had a healthy **event bus** and a good
**significance-bearing engine** (`cos_event_engine`), but they were **disconnected**.
Significance detection, notification, and re-planning were all *scheduled* (CoS
Event Engine every 3h) or *lazy per-request* — never *event-driven*. And the most
mission-significant events of all — `purpose.milestone.completed` /
`purpose.goal.completed` — fired the bus but ran **no** intelligence pass at all
(only an SAE cache invalidation). See the five-capability gap analysis in the
2026-07-02 changelog entry.

---

## The v1 pipeline

```
WeightEntry.save()  (or any milestone/goal completion)
   │  post_save signal → evaluate_weight_milestones()  [milestone flips complete]
   │      └─ FALSE→TRUE transition → safe_emit_event("purpose.milestone.completed", …)
   ▼
Domain event bus  (apps/core/events/domain_events.py)
   │  @subscribe("purpose.milestone.completed") / ("purpose.goal.completed")
   │      on_milestone_completed_react / on_goal_completed_react
   ▼
enqueue_significant_event_reaction()   → react_to_significant_event_task.delay()
   │  (Celery — keeps the request path fast; EAGER in tests runs it inline)
   ▼
react_to_significant_event()   (apps/ai/significant_events.py)  — the reflex:
   1. classify_significance()      → is this mission-significant? why?
   2. _refresh_dependent_truth()   → SAE + CoS caches invalidated; PIE 'goals' pass
   3. _mission_progress()          → derived count (e.g. 2/12)
   4. _next_planning_step()        → goal_pace() → the next milestone (the re-plan)
   5. _persist_major_win()         → GuidanceItem (MAJOR_WIN, sticky key) with a
                                      CoS-quality acknowledgment (what/why/next)
   6. run_cos_event_engine()       → strategic layer fresh NOW, not in 3h
   7. _notify()                    → DNE deliver_single (existing channels+policies)
   ▼
Beth sees it on the NEXT message  (recent_cos_events → CoS standing read)
+ notification center / bell + push/SMS/email per DNE policy
```

### What makes an event significant (v1)

Defined in `apps/ai/significant_events.py :: SIGNIFICANT_EVENT_TYPES`:

- `purpose.milestone.completed`
- `purpose.goal.completed`

These are **intrinsically significant** — a milestone or goal *reaching completion*
is significant by identity, not by a threshold. `classify_significance()` ranks a
**mission** event (on the user's Primary Mission) at priority 2 (surfaces first);
non-mission goal events at priority 3.

### Why it reuses existing substrate

- **Persistence:** the achievement is a `GuidanceItem` (the CoS Event Engine's
  substrate) under a **sticky** dedupe key `cos_event:win:milestone:<id>`, so it
  appears in Beth's standing read (`recent_cos_events`) and the notification center
  for free. The CoS Event Engine's re-detection auto-resolve **exempts**
  `cos_event:win:` (`_WIN_PREFIX`) — a milestone you actually reached is true
  forever and must never be resolved just because it isn't re-detected.
- **Notification:** routed through the DNE (`deliver_single`), which applies the
  existing quiet-hours / throttle / dedupe / MessageOrchestrator policies.
- **Re-plan:** `goal_pace()` — the same computation Beth's standing read uses —
  supplies the next milestone / next planning implication.

### Guarantees

- **Request path stays fast** — the reaction is enqueued to a background worker
  (Observability Performance Law). The emitting write returns immediately.
- **Fail-soft everywhere** — no step raises into the caller. If the enqueue fails
  (broker down), the 3-hour CoS Event Engine remains the backstop (degraded, not
  broken).
- **Deterministic acknowledgment** — no OpenAI on this path. The three-part
  acknowledgment (what happened / why it matters / what to do next) is composed
  deterministically.

### Acceptance / regression

`apps/ai/tests/test_significant_event_pipeline.py` freezes the France 2027 case:
weight 283.1 on 2026-07-02 against a 284.9/June-30 milestone ⇒ milestone achieved,
mission **1/12 → 2/12**, MAJOR_WIN persisted (sticky, priority 2), available to
Beth immediately via `recent_cos_events`, a CoS-quality acknowledgment ("2 days
late", "2 of 12", why, next rung 279.9), the next milestone identified, notified
through the DNE — all **without** the 3-hour scheduler. Plus: the achievement
emits the event on the real save path; significance classification; the reaction
is enqueued (not run inline); the win survives CoS Event Engine re-detection.

---

## Phased follow-on work (deferred = phased, with a trigger — never "maybe")

v1 deliberately scopes to milestone/goal completion driven by the weight-milestone
evaluator. The architecture is additive-compatible with the rest:

| Phase | Work | Promotion trigger |
|------|------|-------------------|
| **P2 — Threshold-significant events** | Classify *ordinary logs that cross a boundary* as significant (a metric entering a clinical risk band, adherence dropping below a threshold, a new streak/record). Extends `classify_significance()` with a threshold tier; reuses the same reaction. | When the first non-completion "in the moment" reaction is requested (e.g. glucose entering a high band should notify now, not in 3h). |
| **P3 — Emit-nothing domains** | Wire domain events for the domains that currently emit none — **medical/labs first** (a new abnormal lab is mission-significant), then relationships, capture, notes, brain_training, scan. Each gains `emit_event` on its write path; the significance classifier already generalizes. | When lab ingestion or a relationship-lapse capability is next touched. medical/labs is the highest-value first mover (prediction/insight rules already exist but are unused because no lab event fires). |
| **P4 — Significance decay / freshness** | Auto-expire stale one-time wins from the standing read after N days (currently they persist until read/dismissed). | When the standing read shows a win older than ~2 weeks in production. |
| **P5 — Generalized milestone metrics** | The evaluator currently emits for `weight_lb` milestones only (Phase-1 objective scope). Emit for body-fat / steps / A1C / BP milestones as those evaluators land. | When the objective-milestone evaluator is generalized beyond weight (already a planned purpose-app phase). |

Each phase is additive: no phase changes the pipeline's shape, only what feeds it.

---

*Key files: `apps/ai/significant_events.py` (pipeline), `apps/ai/tasks.py`
(`react_to_significant_event_task`), `apps/core/events/subscribers.py`
(`on_milestone_completed_react` / `on_goal_completed_react`),
`apps/purpose/services/objective_weight_milestones.py` (emit on achievement),
`apps/ai/cos_event_engine.py` (`_WIN_PREFIX` sticky-win exemption),
`apps/ai/tests/test_significant_event_pipeline.py` (regression).*
