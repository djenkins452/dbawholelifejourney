# Document 3 — Action Capability Catalog

**Purpose:** Determine the minimum write/action tools for ChatGPT to feel like a *real* Chief of Staff — one that does things, not just reports.

**The decisive finding:** WLJ already implements **54 deterministic action handlers** (`apps/ai/action_handlers.py`), each routing through the Phase-2 UAIO execution path (the sole write authority, Law 8). The entire candidate write list — and far more — **already exists, is deterministic, and is in production.** The write surface is not a build problem; it is an *exposure* problem.

---

## 1. The Write Path Already Exists (verified)

Every candidate action maps to an existing handler:

| Candidate action | Existing handler (file:line) | Status |
|------------------|------------------------------|--------|
| `create_task()` | `handle_create_task` `action_handlers.py:3266` | **EXISTS** |
| `update_task()` | `handle_mutate_task` `:3757` | **EXISTS** |
| `complete_task()` | `handle_complete_task` `:3566` | **EXISTS** |
| `create_goal()` | `handle_create_goal` `:2955` | **EXISTS** |
| `update_goal()` | `handle_update_goal_progress` `:3019` | **EXISTS** |
| `create_journal_entry()` | `handle_create_journal_entry` `:2528` | **EXISTS** |
| `log_prayer()` | `handle_log_prayer` `:2678` | **EXISTS** |
| `log_scripture()` | `handle_save_verse` `:2801` | **EXISTS** |
| `create_note()` | (notes CRUD exists; via notes app) | **EXISTS** (app-level) |
| `schedule_event()` | `handle_create_event` `:4541` | **EXISTS** |
| `create_capture()` | (capture upload pipeline) | **EXISTS** (app-level) |
| `send_notification()` | delivery layer (`ai_delivery`) | **EXISTS** (infra) |

Beyond the candidates, handlers also exist for: `log_weight/glucose/blood_pressure/heart_rate/sleep/water/steps/food/workout/cardio`, `take_medication/supplement`, `start_fast/end_fast`, `log_habit`, `add_gratitude`, `mark_prayer_answered`, `add_faith_milestone`, `complete/skip routine`, `set_cos_name`, and more — **54 total** (`grep -c "def handle_"` = 54).

---

## 2. Classification — Day 1 Write Tools

Because the handlers already exist and are deterministic, classification is about *which to expose first*, not which to build. The minimum set that makes the CoS feel real:

| Action capability | Class | Existing handler | Execution path |
|-------------------|-------|------------------|----------------|
| **complete_task** | **DAY 1** | `handle_complete_task:3566` | Deterministic (UAIO) |
| **create_task** | **DAY 1** | `handle_create_task:3266` | Deterministic |
| **update/mutate_task** | **DAY 1** | `handle_mutate_task:3757` | Deterministic |
| **create_journal_entry** | **DAY 1** | `handle_create_journal_entry:2528` | Deterministic |
| **log_prayer** | **DAY 1** | `handle_log_prayer:2678` | Deterministic |
| **log_habit** | **DAY 1** | `handle_log_habit:3142` | Deterministic |
| **schedule_event / add_reminder** | **DAY 1** | `handle_create_event:4541` / `handle_add_reminder:5034` | Deterministic |
| **log_weight (+ core health logs)** | **DAY 1** | `handle_log_weight:746` (+ glucose/sleep/etc.) | Deterministic |
| **create_goal / update_goal_progress** | **PHASE 2** | `handle_create_goal:2955` | Deterministic |
| **save_verse / add_gratitude / faith_milestone** | **PHASE 2** | `:2801 / :2611 / :2891` | Deterministic |
| **log_workout / exercise_set / cardio** | **PHASE 2** | `:5326 / :5407 / :5514` | Deterministic |
| **take_medication / supplement / fasting** | **PHASE 2** | `:1923 / :1878 / :2366` | Deterministic |
| **create_note / create_capture** | **PHASE 2** | app-level | Deterministic |
| **log_transaction / shopping** | **FUTURE** | `:1503 / :5686` | Deterministic |
| **send_notification** (CoS-initiated) | **FUTURE** | delivery infra | Needs policy guardrails |

**Day-1 write set = task lifecycle + journal + prayer + habit + event + core health logs.** This is the "capture what I tell you, close what I did, put it on my calendar" core that makes a CoS feel alive. Everything else is the *same dispatch mechanism* with more handlers turned on — trivial incremental exposure, deferred only to keep the Day-1 test surface small.

---

## 3. The Minimalist Exposure Pattern (anti-overengineering)

Just as reads collapse to one parameterized accessor (Doc 1), writes should **not** be exposed as 54 separate tool definitions. WLJ already has a **dispatch layer** — `execute_intent()` in `intent_service.py` routes an intent name + params to the right handler. The Day-1 architecture exposes:

- **One action-dispatch tool** that accepts an action name + parameters and routes through the existing `execute_intent` → `action_handlers` path.
- A **Day-1 allowlist** restricting it to the ~10 capabilities in §2.

This reuses the entire deterministic write path (validation, the UAIO safety/execution gates, `ActionResult` returns) with **no new business logic** and a single integration point. Expanding to Phase 2/Future is just widening the allowlist.

---

## 4. Execution-Path Integrity (Law compliance)

- All writes continue through **UAIO — the sole write authority** (Law 8, Phase 2). ChatGPT does not write to models directly; it requests an action, the deterministic handler executes it.
- Existing **safety gates** (Learning Mode, validators) remain in force on the path — they are not bypassed by changing the conversational front-end.
- Handlers return structured `ActionResult` objects, so ChatGPT narrates *what the deterministic system did*, never asserts a write it didn't perform.
- **Confirmation discipline** (from the reasoning architecture, Doc 6): destructive or ambiguous actions surface a confirmation; the CoS does not silently mutate state.

---

## 5. Action Catalog — Final

```
DAY 1 (expose via single dispatch, allowlisted):
  complete_task · create_task · update_task
  create_journal_entry · log_prayer · log_habit
  schedule_event / add_reminder
  log_weight (+ core health logs: glucose, sleep)

PHASE 2 (widen allowlist — handlers already exist):
  create_goal · update_goal_progress · save_verse · add_gratitude
  log_workout/cardio · take_medication/supplement · fasting · create_note · create_capture

FUTURE (needs policy/guardrails, not new logic):
  log_transaction · CoS-initiated send_notification
```

**Bottom line:** the action layer is the *most* launch-ready part of the entire system — 54 deterministic handlers in production, reachable through one existing dispatch. Day-1 write capability is an allowlist + one integration point, not a build.

---

*Document 3 of 6. What these reads + writes make possible is mapped in Document 4.*
