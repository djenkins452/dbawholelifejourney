# Beth Production Validation Checklist

> **Run this checklist against production after any release that touches the CoS
> chat pipeline, reasoning lane, streaming/recovery, or the chat templates.**
> Maps to the Golden Behaviors in `BETH_GOLDEN_BEHAVIORS.md`.
> **Last updated:** 2026-06-25

**How to use:** perform each scenario on a real CoS account in production. Mark
PASS only if *every* expected outcome holds. Any FAIL blocks the release and
should trigger rollback (`BETH_ROLLBACK_AND_RECOVERY.md`).

**Diagnostic aid:** every stage emits a `BETH_LIFECYCLE` log line keyed by a single
correlation id (`cid`). To debug a failure, grep production logs for the request's
`cid` and read the ordered stages (`BETH_REQUEST_SUBMITTED` → … → `BETH_TASK_FINALLY`
and the `BETH_RENDER_*` lines).

---

## A. Navigation Durability  *(GB-1.1, 1.3, 1.4, 1.6, 2.x)*

1. Open the floating chat.
2. Ask: **"How am I doing overall with my health goals?"**
3. Immediately navigate to another module (e.g. Health → Journal).
4. Return before completion.

**Expected:**
- [ ] The question is still visible.
- [ ] **Exactly one** thinking indicator ("… is reviewing your information…") with animated dots.
- [ ] No duplicate indicators or duplicate question bubbles.
- [ ] When generation completes, the indicator disappears and the answer renders in its place.
- [ ] The answer was **not** reissued by the user.

---

## B. Full Assistant Page  *(GB-1, GB-2 on `/assistant/`)*

Repeat scenario A starting from the `/assistant/` page.

**Expected:**
- [ ] Exactly one thinking indicator (panel surface).
- [ ] No duplicate bubbles.
- [ ] The final answer replaces the indicator.

---

## C. Refresh Durability  *(GB-1.2, 1.6)*

1. Submit a reasoning question.
2. While still processing, hard-refresh the browser (F5).

**Expected:**
- [ ] The question remains visible after reload.
- [ ] The thinking indicator reappears immediately.
- [ ] No duplicate indicators.
- [ ] The answer appears when ready.

---

## D. Return After Completion  *(GB-1.4, 2.3, 2.5)*

1. Submit a reasoning question.
2. Navigate away.
3. Wait until generation should be complete.
4. Return.

**Expected:**
- [ ] **No** thinking indicator.
- [ ] The final answer is already rendered.
- [ ] No stale/orphaned placeholder remains.

---

## E. Multiple In-Flight Requests  *(GB-2 — HIGHEST RISK)*

1. Submit Question A.
2. Immediately submit Question B before A completes.

**Expected:**
- [ ] Both answers complete and render.
- [ ] No crossed indicators (an answer never appears under the wrong question).
- [ ] No orphaned indicators.
- [ ] No lingering thinking placeholder once both answers are shown.
- [ ] At most one thinking indicator visible at a time per surface (single-marker design — this is expected, not a defect).

---

## F. Completion Notification  *(GB-1.5)*

1. Ask a reasoning question that takes ≥12s.
2. Navigate away / close the tab before it finishes.
3. Return later (or reopen).

**Expected:**
- [ ] A notification ("… finished your response") appears in the bell, persists across reload/login.
- [ ] Clicking it opens the conversation scrolled to the exact answer (`/assistant/?beth_msg=<id>`).
- [ ] No duplicate notifications (exactly one per long-running job).

---

## G. Health Reasoning Quality  *(GB-3, GB-4.1)*

Ask each, on a real account:

1. **"What is my biggest health risk right now?"**
2. **"How am I doing overall with my health goals?"**
3. **"What should I focus on from a health perspective today?"**
   *(Note: maps to the not-yet-implemented `health_focus_today` intent — expect a
   graceful health answer or an honest decline, NOT a crash or legacy fallback.)*

**Validation for each (expected outcomes):**
- [ ] **Always returns an answer** (never blank, never "empty response").
- [ ] **Health-only** — no journal/faith/finance/task content bleeds in.
- [ ] **No internal labels** — no `LOW`/`MED`/`HIGH`, no enum codes, no `SAE.*` paths, no field names.
- [ ] **Non-alarmist**, evidence-based, coaching tone.
- [ ] A morning question with a 0 nutrition counter is **not** framed as a risk.

---

## H. Reliability / Fallback  *(GB-4)*

1. (If a planner outage can be simulated in staging) Confirm an implemented health
   intent still answers via the deterministic path.

**Expected:**
- [ ] Implemented intents (`biggest_health_risk`, `overall_progress`) answer even if the planner LLM fails.
- [ ] No silent fall-through to the legacy tool loop.

---

## Sign-off

| Field | Value |
|-------|-------|
| Release / commit | __________ |
| Validated by | __________ |
| Date | __________ |
| Result | ☐ PASS (ship)  ☐ FAIL (rollback) |
| Notes / `cid`s investigated | __________ |
