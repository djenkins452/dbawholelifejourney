# Document 6 — Recommended Rollout Sequence

**Goal:** the fastest, lowest-risk path to *Danny using ChatGPT as his daily full-time Chief of Staff.* The sequence is ordered so that **each phase is independently usable** — value lands early, risk stays contained, and nothing is built before it's needed.

**Design rule for the sequence:** ship reads before writes (observe before acting), ship the always-on bundle first (it powers everything), and defer the unwired/absent items to the end (they're additive, not foundational).

---

## Phase 0 — Always-Loaded Context *(foundation — do first)*

**Ship:** `get_standing_context` (serialize `build_cos_context` / `build_executive_context`).

**Why first:** every later phase reasons over this bundle. With Phase 0 alone, ChatGPT can already answer "how am I doing?", "what's my weight?", "what should I focus on today?" from standing context — a *read-only* CoS that knows where Danny stands.

**Usable outcome:** a CoS that is *aware* — it can talk about Danny's current state, top risks, and recommended focus. No retrieval, no actions yet.

**Risk:** minimal — one serialization, no writes, no new logic.

---

## Phase 1 — Read Tools *(holistic awareness)*

**Ship:** `get_domain_state(domain)`, `get_dashboard_context`, `get_decision(mode)`.

**Why next:** turns "aware of the headline" into "able to look anywhere." `get_domain_state` un-strands every domain (health, faith, journal, goals, relationships, calendar, finance) for retrieval; `get_decision` gives canonical Execution/Risk/Fix answers.

**Usable outcome:** a **full holistic read-only CoS** — diagnostics (bounded), coaching from the whole person, "what goals am I neglecting," "what should I pray about." This is already a CoS Danny would use daily.

**Risk:** low — all serialization/reuse; still read-only, so no state-integrity risk.

---

## Phase 2 — Time-Based History *(memory)*

**Ship:** `search_history(domain, range)` (reuse `query_event_history`).

**Why here:** adds "have I been here before / what happened last month" — the historical dimension of coaching — without touching writes.

**Usable outcome:** a CoS that reasons across time, not just the present. Pattern-by-metric and episode recall.

**Risk:** low — existing wired handler.

---

## Phase 3 — Write Tools *(a CoS that acts)*

**Ship:** `execute_action(name, params)` dispatch with the Day-1 allowlist (`complete_task`, `create_task`, `update_task`, `create_journal_entry`, `log_prayer`, `log_habit`, `schedule_event`/`add_reminder`, `log_weight` + core health logs).

**Why after reads:** writes carry the real risk (state mutation, safety gates, auth scoping). Shipping them *after* the read CoS is proven means the integration, auth, and trust posture are already validated before any state can change.

**Usable outcome:** the CoS now *does things* — closes tasks, captures journals/prayers, schedules events, logs metrics. This is the moment it "feels real."

**Risk:** medium — mitigated by routing every write through the existing UAIO authority + safety gates (Doc 5 §3), starting with a tight allowlist, and confirmation discipline on ambiguous/destructive actions.

---

## Phase 4 — Advanced Coaching & Deferred Capabilities *(depth)*

**Ship (incrementally, each additive):**
- Widen the action allowlist to Phase-2 handlers (goals, faith logging, workouts, medication, notes, captures) — *same dispatch, more allowlist*.
- Wire the **existing** keyword-search engines: `search_notes` (`search_notes_cos`) and `search_capture` (`SearchService`) — closes the knowledge-retrieval gap.
- Add keyword/thematic `search_history`.
- (If/when an in-app client is in scope) `get_screen_context`.

**Why last:** these are the deferred items from the readiness audit. They're additive depth (knowledge recall, thematic history), not foundational. Each is cheap because the engines already exist — they need wiring, not building.

**Usable outcome:** the CoS gains deep recall and knowledge search — the PARTIAL/NOT-SUPPORTED experiences from Doc 4 become supported.

**Risk:** low–medium per item; each is independently shippable and non-blocking.

---

## Sequence at a Glance

```
Phase 0  Always-loaded context        → AWARE CoS            [1 serialization]      ◀ usable
Phase 1  Read tools                    → HOLISTIC READ CoS    [3 serialize/reuse]    ◀ daily-usable
Phase 2  Time-based history            → CoS WITH MEMORY      [1 reuse]              ◀ usable
Phase 3  Write tools (allowlisted)     → CoS THAT ACTS        [1 dispatch + gates]   ◀ feels real
Phase 4  Deferred depth (additive)     → DEEP COACHING CoS    [wire existing engines]
```

**Critical-path insight:** Danny has a genuinely usable daily Chief of Staff at the **end of Phase 1** (holistic read-only), and a CoS that *feels real* at the end of **Phase 3**. Phases 0–3 are almost entirely serialization and reuse of production code. The long tail (Phase 4) is additive and never blocks the switch.

---

## The Anti-Overengineering Bottom Line

The fastest path to a full-time ChatGPT CoS is **not** a build project — it is an **exposure project**. WLJ already computes the state, makes the decisions, stores the history, and executes the actions. Three of four phases to a *real* CoS are serialization and reuse. The sequence above orders that exposure to deliver a usable CoS as early as Phase 1 and protect state integrity by deferring writes to Phase 3 — minimum infrastructure, maximum and earliest value, WLJ unchanged throughout.

---

*Document 6 of 6. End of the Day-1 ChatGPT CoS Tool Catalog Architecture set.*
