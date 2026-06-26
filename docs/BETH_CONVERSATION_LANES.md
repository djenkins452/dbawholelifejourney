# Beth Conversation Lanes

> **The framework-first routing contract for the ChatGPT CoS path.** Implemented by
> `apps/ai/chatgpt_cos/lanes.py` + `service.py::generate`; enforced by
> `apps/ai/tests/test_conversation_lanes.py`. Governed by
> `BETH_ARCHITECTURAL_PRINCIPLES.md` (P1–P3, P5, P6, P8–P11, P13, P22, P23).
> **Last updated:** 2026-06-26

## The ordered lane registry

```
route_message(user, message)  →  first lane to return non-None wins
  1. Foundational Facts Lane    (existing — personal scalar facts)
  2. Personal Reasoning Lane    (existing — the 4 health intents)
  3. Clarification Lane         (NEW — deterministic; asks instead of failing)
  4. General Conversation Lane  (NEW — sandboxed; non-personal knowledge)
  ── all decline → service.generate() runs the Tool Loop (terminal fallback, P8)
```

Each lane is a callable `run(user, message) -> dict | None`. `None` = decline →
advance. The two existing lanes are **wrapped, not modified** (called directly, so
their decline/error semantics are byte-for-byte unchanged). Registry/template based
— **no special-casing, no if/else tree** (P6/P13). Add a lane or ambiguity type by
appending to a registry, not by branching.

Every lane result is task-compatible: `{answer, tools_called: [...], ...}` (plus
`lane`, and for clarification `ambiguity_type`). The durability stack never inspects
which lane answered — durability/recovery/notifications/thinking indicators are
untouched.

## Lane 3 — Clarification (deterministic, no OpenAI)

`AMBIGUITY_TYPES` registry; each entry = `{type, triggers, response}`. A multi-word
trigger matches as a substring only within a short (≤4-word) request; a single-word
trigger must match exactly — so specific requests are never stolen.

| Ambiguity type | Triggers (sample) | Response framing |
|----------------|-------------------|------------------|
| `daily_checkin_candidate` | "check in", "checkin", "daily check in" | Daily Check-In options (today / next / health & energy / goals / full Whole Life) |
| `unspecified_help` | "help me", "i need help", "help" | offers health / goals / schedule / faith / projects / general |
| `unspecified_review` | "review this", "can you review", "review" | asks: document / goals / schedule / something else |

### `check in` (this phase)
Danny's meaning: *"look at my day and tell me what to do next and what's coming up."*
That is a **future Daily Check-In Lane / Daily Executive Brief**. **It is intentionally
NOT built in this phase** — `check in` is handled as a Clarification case with
Daily Check-In framing. **No calendar/task/goal/health data is pulled.** Promotion
trigger: when the Daily Check-In Lane is built, `daily_checkin_candidate` graduates
from a clarification into a dedicated lane (P21).

## Lane 4 — General Conversation (sandboxed)

- **Claim (conservative):** the message must contain **no** personal pronoun
  (`my/i/me/...`) and **no** WLJ-domain word, and must look like a general-knowledge
  request (opener like "who was", "what is", "explain", "define", "write out", …).
  Anything personal/WLJ **declines** → tool loop (which can fetch real data) — so a
  personal question is never answered from a data-less lane.
- **Sandbox (P1/P3/P11):** the prompt carries ONLY the question. No SAE, no standing
  context, no personal facts. Instruction explicitly forbids referencing personal data.
- **Always answers once it claims (P5):** LLM failure → deterministic graceful
  fallback ("I couldn't reach it just now. Please try again.").
- **Known conservative limitation:** a pure-general question that happens to contain a
  domain noun (e.g. "what is glucose") declines to the tool loop rather than the
  General lane. Safe by design; refine later if needed.

## Guarantees (tested)
- `check in` → Clarification, `daily_checkin_candidate`, Daily Check-In framing.
- Clarification is deterministic — **requires no OpenAI** (works with OpenAI down).
- Clarification never reaches the tool loop.
- The four health intents + personal questions are **never** claimed by the new lanes
  (routing preserved; no contamination).
- General lane prompt contains no personal payload; deterministic fallback on failure.
- All lanes decline → `route_message` returns `None` → tool-loop terminal fallback.
