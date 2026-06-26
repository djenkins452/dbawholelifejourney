# Beth P25 — Personal Truth First (routing architecture)

> **Status: SHADOW (Phase 1–2). P25 routing is NOT active — current lane routing is
> unchanged.** A deterministic shadow classifier runs for telemetry only, so we can
> prove accuracy on real traffic before activating (Phase 3). Governed by
> `BETH_ARCHITECTURAL_PRINCIPLES.md` P25; protects `beth-stable-v1`.
> **Last updated:** 2026-06-26

## The principle (target architecture)

Replace load-bearing lane *ordering* with one explicit gate:

```
classification = classify_request(request)          # deterministic-first, one place
PERSONAL  → answer_from_wlj_truth()                  # warm SAE; fact / rhythm / health / retrieval
MIXED     → wlj_truth grounds a general answer       # truth first
AMBIGUOUS → ask_clarifying_question()                # deterministic; no warm, no planner
EXTERNAL  → answer_with_general_openai()             # sandboxed; no warm, no planner, no retrieval
```

The mature subsystems (Foundational Facts, Rhythm API/P24, Health Reasoning,
Clarification state, General Conversation) are **kept** as dispatch targets. What is
removed (later, Phase 4) is *lane order as the personal-vs-external arbiter* and the
*planner/SAE-warm tax* on non-personal requests.

## `classify_request(message, user, conversation)` — the four classes

Deterministic, ordered semantic rules (NOT lane order). Reuses the live lanes'
predicates (`_PERSONAL_PRONOUNS`, `_DOMAIN_WORDS`, `_NEXT_RHYTHM_SIGNALS`,
`_looks_general`, `clarify`). No LLM, no SAE warm, no side effects.

| Order | Rule | → Class | Confidence |
|------:|------|---------|-----------|
| 1 | matches an ambiguity trigger (`check in` / `help me` / `review this`) | **AMBIGUOUS** | 0.95 |
| 2 | explicit "in general / generally / most people / on average" | **EXTERNAL** | 0.90 |
| 3 | personal shape — rhythm signal, "review my …", or "my &lt;domain&gt;" | **PERSONAL** | 0.92 |
| 4 | advice shape (`should I`, `best … for me`, `recommend`) **+** pronoun/domain | **MIXED** | 0.80 |
| 5 | personal pronoun (`my/I/me`) or a WLJ-domain word | **PERSONAL** | 0.90 |
| 6 | general-knowledge shape (`_looks_general`) | **EXTERNAL** | 0.90 |
| 7 | none of the above | **AMBIGUOUS** | 0.40 |

Validated example table (all pass): `what is my weight?`→PERSONAL · `how am I
doing?`→PERSONAL · `check in`→AMBIGUOUS · `what should I do next?`→PERSONAL · `review
my week`→PERSONAL · `who was Abraham Lincoln?`→EXTERNAL · `explain
photosynthesis`→EXTERNAL · `what is Delphi?`→EXTERNAL · `should I eat fruit?`→MIXED ·
`what's the best exercise for me?`→MIXED.

## Shadow telemetry — how to read disagreement logs

One line per request (`BETH_P25_SHADOW`), emitted by `service.generate` after the
live router runs (no message content is logged):

```
BETH_P25_SHADOW current_lane=<lane> current_p25=<mapped> shadow_class=<P25>
                confidence=<0..1> signal=<matched_signal> agree=<bool> qlen=<n>
```
- `current_lane` — the live router's outcome (`foundational_facts`, `personal_reasoning`, `next_rhythm`, `clarification`, `clarification_reply`, `general_conversation`, or `tool_loop`).
- `current_p25` — that lane mapped to a P25 class (`LANE_TO_P25`).
- `shadow_class` / `confidence` / `signal` — the P25 classifier's decision.
- `agree` — `current_p25 == shadow_class`.

**Reading disagreements:**
- `agree=false` with `shadow_class=MIXED` → **expected** (current architecture has no
  MIXED concept; marks where P25 would blend truth + general).
- `agree=false` with `shadow_class=EXTERNAL` but `current_lane=personal_reasoning/tool_loop`
  → a request the planner handled that P25 would route to general (the Issue-#1 class).
- `agree=false` with `shadow_class=AMBIGUOUS` but `current_lane=personal_reasoning`
  → the `check in`-style misroute P25 would clarify.
- `agree=false` with `shadow_class=PERSONAL` but `current_lane=general_conversation`
  → a potential personalization miss to investigate.
Aggregate `agree=true` rate + the disagreement buckets are the **activation gate**.

## Phased rollout
- **Phase 1–2 (now):** constitution + this doc + shadow classifier + telemetry. No behavior change.
- **Phase 3 (separate milestone):** activate P25 routing behind a flag (`WLJ_COS_P25_ROUTING`, default off); legacy registry remains the off-path; instant flag rollback.
- **Phase 4:** remove legacy ordering once Phase 3 is validated; tool loop shrinks to the minimal PERSONAL fallback.

## Release track
P25 activation is its own milestone (`beth-stable-v3`). It is **not** part of
`beth-stable-v2`, which stays focused on P24, clarification state, the Responded
chip, and General-lane reliability.
