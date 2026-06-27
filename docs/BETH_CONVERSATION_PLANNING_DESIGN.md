# Executive Conversation Planning — Architecture Design (P31)

**Status:** Phase 1 IMPLEMENTED (`conversation_planner.py` + repair / morning check-in
lanes, deterministic, no migration). Phases 2–3 pending. Checkpoint: `beth-stable-v3`.
**Author:** Claude (P31). **Date:** 2026-06-27.

> **Phase 1 (shipped):** `apps/ai/chatgpt_cos/conversation_planner.py` (deterministic
> `plan()` + act classifier + state in `AssistantConversation.metadata`), wired as the
> `conversation_planner` lane (2nd, after `clarification_reply`). A GREETING opens with
> a light CHECK-IN (agenda held); a CRITIQUE triggers REPAIR (re-ground in time-aware
> state, no unrelated fact); a CHECK-IN response hands off to the deterministic
> BRIEFING (adaptive to negative feeling). Product decision: morning ALWAYS checks in
> first. Tests: `apps/ai/tests/test_p31_conversation_planning.py`. Acceptance bank
> stays isolated (state reset per question in `run_one`).

---

## 0. TL;DR & the core challenge

The proposal is **correct** — the two production defects are *conversation-strategy*
defects, not reasoning defects — but it must be built as a **thin deterministic
strategy + state layer in front of the existing pipeline**, NOT a new reasoning engine
or an LLM-on-every-turn planner. That preserves every v3 invariant (deterministic
truth, never-empty, graceful degradation) and adds the missing executive behavior.

```
  CURRENT:  message ─────────────► route_message / reasoning ──► narration
  PROPOSED: message ─► PLAN (deterministic) ─► route_message / reasoning ─► narration(plan)
                          ▲ reads conversation STATE + standing context + signals
                          ▼ writes the next conversation STATE
```

Two production problems, one root cause — **there is no conversation-level layer**:
1. *"Good morning" → immediate agenda dump.* The greeting routed straight to
   `build_daily_agenda` (a fact), with no step that asked *"what conversation should I
   have right now?"* — so it briefed when it should have **checked in first**.
2. *"Does that sound right to you?" → unrelated protein fact.* `route_message`
   classifies each message in isolation; there is no **conversation state** that knows
   the previous turn was a briefing and this turn is a **critique/repair**.

Both are the same gap: Beth plans *answers*, not *conversations*.

---

## 1. Architectural review — is "Executive Conversation Planning" the right abstraction?

**Yes, with one refinement and one explicit boundary.**

- **Refinement:** it is a *strategy + state* layer, not a new reasoning system. It
  decides *which conversation to have* and *how to open*; the existing lanes/reasoning
  still produce the *facts*; narration renders the *plan over the facts*. This avoids a
  parallel orchestrator (a Law-9 violation in this repo) and reuses everything.
- **Boundary:** the planner is **deterministic-first**. WLJ already owns the truth that
  decides strategy (time band, overnight sleep/meds, yesterday's journal/nutrition,
  signal severities, last message role). The LLM may *narrate* the plan, but the plan
  itself is computed deterministically so it survives an OpenAI outage (v3 invariant 5)
  and is testable with OpenAI disabled.

**Challenge considered and rejected:** *"Just make it an LLM 'conversation director'
that reads history and decides."* Repository evidence rejects this: (a) v3's value is
that every CoS capability degrades deterministically — an LLM-only planner reintroduces
the exact failure class P26–P30 eliminated; (b) the repo's whole CoS architecture is
"WLJ owns truth, ChatGPT narrates" (invariant 3) — strategy derived from owned truth is
deterministic by construction; (c) latency/cost of an extra LLM round-trip on *every*
turn. So: **deterministic planner, LLM narration**, with an optional LLM "strategy
hint" only as a non-authoritative enrichment in a later phase.

**Challenge considered and partially accepted:** *"Is a full FSM overkill?"* For v1,
yes — a full 9-state machine with all transitions is more than the two defects need.
The roadmap (§6) ships a **minimal planner + 4 live states** first and grows the FSM
only as scenarios demand it. The *model* (§4) is designed in full so v1 is
forward-compatible, but only a subset is wired in Phase 1.

---

## 2. High-level architecture & integration

One new deterministic component, inserted at the **single existing entry point**
(`ChatGPTCoSService.generate`, service.py) — *before* `route_message`:

```
ChatGPTCoSService.generate(conversation, message):
    plan = ConversationPlanner.plan(user, conversation, message)   # NEW, deterministic
    #   reads: conversation STATE (metadata), AssistantMessage history (last turns),
    #          _time_band, build_executive_summary, get_standing_context, signals
    #   writes: conversation.metadata["conversation_state"] (next state)

    if plan.handler == "repair":         return repair_lane(user, conversation, plan)   # NEW lane
    if plan.opening == "check_in_first": return checkin_open_lane(user, plan)           # NEW lane (deterministic)
    routed = route_message(user, message, conversation)            # EXISTING (unchanged)
    if routed: return _apply_plan_framing(routed, plan)            # plan shapes the OPENING only
    ... existing tool loop / emergency fallback (unchanged) ...
```

Integration map (everything reused, nothing duplicated):

| Need | Reused component | File |
|---|---|---|
| Conversation history | `AssistantMessage` (role/content/created_at) | `apps/ai/models.py` |
| Conversation STATE persistence | `AssistantConversation.metadata` JSONField (same pattern as `pending_clarification`) | `apps/ai/models.py`, `lanes.py` |
| Conversation type | existing `session_type` + `SESSION_TYPE_CHOICES` | `apps/ai/models.py` |
| Time band | `_time_band(user_now)` (early_morning/morning/midday/evening/late_evening) | `cos_briefing/executive_summary.py` |
| Deterministic briefing content | `build_executive_summary` (going_well / needs_attention / biggest_risk / lenses) | `cos_briefing/executive_summary.py` |
| Deterministic agenda | `build_daily_agenda`, rhythm_api | `cos_briefing/daily_agenda.py` |
| Always-loaded exec state | `get_standing_context` | `cos_services/standing_context.py` |
| Overnight facts (sleep/meds/supplements) | SAE `health_state` (already warmed in `generate`) | `ai_state` |
| Yesterday's signal (journal/nutrition/"ended strong") | unified signals / `executive_summary` state signals | `ai_signals`, `cos_briefing` |
| Conversation initiation precedents | `ProactiveCheckInService` | `apps/ai/proactive_checkins.py` |
| Routing to facts | `route_message` lane registry | `chatgpt_cos/lanes.py` |
| Never-empty / graceful degradation | `_emergency_fallback`, deterministic fallbacks | `service.py`, `reasoning/stages.py` |

**No migration:** conversation state lives in the existing `metadata` JSONField, exactly
like `pending_clarification`. **No parallel orchestrator:** the planner feeds the
existing pipeline.

---

## 3. Conversation Planner design

A pure-ish deterministic function (one cheap SAE/standing read, already warmed):

```
ConversationPlan = {
  objective:    one of {executive_briefing, emotional_checkin, accountability,
                        coaching, decision_support, encouragement, planning,
                        celebration, reflection, repair, smalltalk}
  opening:      one of {check_in_first, brief_immediately, ask_clarifying,
                        acknowledge_yesterday, congratulate, challenge, encourage,
                        repair_previous}
  should_brief_now: bool          # may be False even for "good morning"
  priority_topics: [sleep|nutrition|calendar|france|health|family|faith|work, ...]
  state_in:     ConversationState # current
  state_out:    ConversationState # next (persisted)
  handler:      one of {repair, checkin_open, route, briefing}   # which path runs
  evidence:     {time_band, last_role, overnight, yesterday, top_signals}  # for narration
}
```

**Inputs (all owned truth, deterministic):**
- `message` (this turn) + a cheap **conversational-act** classifier (see below).
- `conversation.metadata["conversation_state"]` (current state + turn count + last objective).
- last 1–3 `AssistantMessage` rows (role/content) — to detect critique/follow-up/agreement.
- `_time_band(get_user_now(user))`.
- `get_standing_context` / `build_executive_summary` (going_well/needs_attention/biggest_risk).
- SAE `health_state` overnight facts (sleep hours, meds_taken, supplements_taken).
- yesterday's signal (journal sentiment, nutrition adherence, "ended strong" recovery state).

**Decision process (deterministic, ordered):**
1. **Conversational act first.** Classify the message as one of
   `{greeting, critique, follow_up, correction, agreement, fresh_request, smalltalk}`
   using lexical cues + the *last assistant message role*. (Critique cues: "does that
   sound right", "are you sure", "that's not", "really?", "is that correct".)
   - `critique`/`correction` + last turn was Beth's answer → **objective=repair,
     handler=repair, opening=repair_previous**. (Fixes production defect #2.)
2. **Greeting + early_morning/morning + first turn of the day** → consult overnight +
   yesterday. If there is something *human* to acknowledge (rough yesterday, recovery,
   short sleep) → **objective=emotional_checkin, opening=check_in_first,
   should_brief_now=False** (acknowledge + one feeling question; agenda deferred).
   Else → **objective=executive_briefing, opening=brief_immediately**.
   (Fixes production defect #1.)
3. **Evening band** → reflection/closing objective (wrap-up, not "begin" actions —
   reuses the existing evening pivot in `build_daily_agenda`).
4. **Otherwise** → `handler=route` (let the existing lanes answer); the plan only
   shapes the **opening line** (e.g. acknowledge yesterday once, then answer).
5. Always compute `state_out` and persist it.

**State transitions:** see §4. Stale state self-clears (turn timestamps); a new
conversation (new `AssistantConversation` or >N hours idle) resets to `greeting`.

**Outputs feed three places:** the repair lane, the check-in-open lane, and (for the
`route` path) a thin `_apply_plan_framing` that prepends at most one acknowledgement
sentence — it never alters the deterministic FACT body (preserves v3 truth guarantees).

---

## 4. Conversation State model (first-class, persisted in metadata)

```
GREETING ─► CHECK_IN ─► BRIEFING ─► PLANNING ─► EXECUTION ─► REFLECTION ─► CLOSING
                 │           │           │
                 └──────────►└───────────┴────────► REPAIR ──► (back to prior state)
```

Persisted shape (no migration — `AssistantConversation.metadata`):
```json
"conversation_state": {
  "state": "briefing",
  "objective": "executive_briefing",
  "turn": 4,
  "last_state": "check_in",
  "last_beth_act": "briefed",
  "topics_open": ["nutrition", "sleep"],
  "updated_at": "<iso>"
}
```

Transition rules (deterministic):
- `GREETING → CHECK_IN` when the planner chooses `check_in_first` (human signal present).
- `CHECK_IN → BRIEFING` when the user responds to the feeling question OR asks for the
  agenda ("what's on today", "brief me").
- `* → REPAIR` when a **critique/correction** act follows a Beth answer; `REPAIR →`
  previous state when resolved.
- `BRIEFING → PLANNING → EXECUTION` as the user moves from "what" to "what should I do"
  to "doing it" (reuses existing focus/agenda intents).
- `* → REFLECTION/CLOSING` in the evening band or on "wrap up my day" (existing lane).
- Idle reset: a gap > `CONVERSATION_RESET_HOURS` (or a new active conversation) → `GREETING`.

REPAIR is the smallest first-class state that fixes production defect #2 and is the
highest-value addition; it is in Phase 1.

---

## 5. Worked examples

**Morning (rough yesterday, short sleep) — the target behavior:**
`"Good morning"` → act=greeting, band=early_morning, overnight={sleep 6.1h, meds ✓,
supps ✓}, yesterday={journal: hard, recovery: ended_strong, nutrition: missed}.
Plan: objective=emotional_checkin, opening=check_in_first, should_brief_now=False.
Beth: *"Good morning, Danny. Yesterday wasn't your strongest, but you finished much
stronger than you started. You got about six hours of sleep and you've already taken
your meds and supplements. Before we dive into today — how are you feeling this
morning?"* State → CHECK_IN. Agenda waits for the reply.

**Morning (clean day):** no human signal → objective=executive_briefing,
opening=brief_immediately → existing agenda, but framed as a briefing. State → BRIEFING.

**Conversation repair — the second defect:**
prev Beth turn = briefing; user=`"Does that sound right to you?"` → act=critique →
objective=repair, handler=repair. Repair lane re-examines the **previous answer**
(from history), validates it against deterministic state, and responds to the
*critique* ("Fair question — let me sanity-check that. The 6:45 protein shake is your
earliest scheduled item, but you've logged 0 g protein so far, so yes, it's the right
first move…") rather than emitting a new isolated fact. State → REPAIR → BRIEFING.

**Evening review:** band=evening → objective=reflection, opening=acknowledge_yesterday/
today → existing evening `build_daily_agenda` wrap-up. State → REFLECTION → CLOSING.

**Weekly review / goal review:** objective=planning/coaching; priority_topics seeded
from `build_executive_summary.needs_attention` + mission (France) — reuses goal
reasoning, opens by naming the week's biggest lever.

**Decision support:** act=fresh_request with a decision cue → objective=decision_support
→ existing `get_decision` path; opening states the recommended call first.

**Executive coaching / accountability:** an open commitment from prior turns (in
`topics_open`) + missed execution signal → objective=accountability, opening=challenge
("You said you'd protect the morning block — it slipped twice this week. What's getting
in the way?").

---

## 6. Implementation roadmap (smallest safe first)

**Phase 1 — Conversation state + Repair + Morning check-in (highest value, lowest risk).**
- New `apps/ai/chatgpt_cos/conversation_planner.py`: deterministic `plan()` + the
  conversational-act classifier + state read/write helpers (mirroring
  `pending_clarification`). Pure; no migration.
- New deterministic lanes: `_repair_lane` (re-examine prior answer from history) and
  `_checkin_open_lane` (acknowledge overnight/yesterday + one feeling question, from
  `build_executive_summary` + SAE). Wire `plan()` into `generate()` before
  `route_message`; only `repair` and `check_in_first` short-circuit — everything else
  falls through to today's pipeline UNCHANGED (byte-identical for all current passing
  behavior).
- Ships the two production fixes. Fully testable with OpenAI disabled.

**Phase 2 — Plan-framed openings + fuller FSM.**
- `_apply_plan_framing` adds at most one acknowledgement sentence to routed answers
  (acknowledge_yesterday/congratulate/encourage), never touching the fact body.
- Add PLANNING/EXECUTION/REFLECTION/CLOSING transitions; seed `topics_open` from
  signals; evening reflection objective.

**Phase 3 — Adaptive + optional LLM strategy hint.**
- Adaptive briefing depth based on the user's check-in reply ("I'm exhausted" → lighter
  brief, protect recovery; "let's go" → full brief).
- OPTIONAL: a non-authoritative LLM "strategy hint" that can only *reorder/soften* the
  deterministic plan, never override the deterministic fact body or the never-empty
  guarantees. Gated behind a flag; off by default.

Each phase is independently shippable and reverts cleanly. v3 remains the restore point.

---

## 7. Acceptance testing (scenario-based — a new dimension)

This is the first feature that needs **multi-turn dialogue** Acceptance, not isolated
intents. Add a scenario harness alongside the question bank:

- **Morning check-in scenario:** `["Good morning"]` (rough-yesterday fixture) → asserts
  the response acknowledges yesterday + overnight AND ends with a feeling question AND
  does NOT dump the agenda; state → CHECK_IN. Then `["I'm okay, a bit tired"]` →
  adaptive lighter brief.
- **Conversation repair scenario:** `["Good morning", "Does that sound right to you?"]`
  → the 2nd response references/sanity-checks the PREVIOUS answer, not a new fact; no
  assistant-unavailable; state passes through REPAIR.
- **Executive briefing scenario (clean day):** `["Good morning"]` (no human signal) →
  immediate briefing with evidence + a concrete first action.
- **Adaptive briefing:** same opener, two different user replies → two different brief
  depths.
- **Evening reflection scenario:** `["wrap up my day"]` → reflection/closing, no "begin"
  actions.

All scenarios validate, with **OpenAI disabled**: non-empty, no outage message, evidence
from WLJ state used, concrete next action present, and **correct conversation-state
transition**. These become permanent regression (every production conversation defect →
a permanent scenario test), and feed a new Acceptance "conversation quality" suite
distinct from the intent suites.

---

## What I will NOT do (guardrails)
- No new reasoning engine / parallel orchestrator. No migration. No always-on LLM
  planner. No rewrite of the "Good morning" prompt. The deterministic fact bodies and
  the v3 never-empty / graceful-degradation invariants are preserved exactly.
