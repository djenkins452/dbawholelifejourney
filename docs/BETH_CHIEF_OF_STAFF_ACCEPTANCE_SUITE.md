# Beth Chief-of-Staff Acceptance Suite — DESIGN (not yet implemented)

> **Status: design only.** This document specifies the *future* acceptance layer
> that sits **above** the Deep factual-trust suite. No code yet. It exists so the
> factual foundation (Deep) is built first and the Chief-of-Staff layer has a clear
> target to grow into. Governed by `WLJ_ARCHITECTURE_LAWS.md` and the Execution
> Playbook's **Gate 3 — Chief-of-Staff Quality** (`@WLJ_SYSTEM_PROMPTS/00_CORE_STARTUP/
> WLJ CLAUDE OPUS 4.8 EXECUTION PLAYBOOK.md`, §5). **Date:** 2026-06-28.

---

## Why two layers, and why Deep first

**Trust precedes intelligence. Beth earns the right to *reason* by first earning the
right to be *trusted*.** The acceptance system therefore has two stacked gates:

```
        ┌──────────────────────────────────────────────┐
  ABOVE │  CHIEF-OF-STAFF SUITE  (judgment, proactivity,│   ← this document (design)
        │  synthesis, tone, trust) — runs ONLY when Deep │
        │  is GREEN.                                      │
        ├──────────────────────────────────────────────┤
  GATE  │  DEEP — FACTUAL-TRUST SUITE  (Intent, Truth,    │   ← implemented now
        │  Freshness, Deterministic Retrieval, Stability,│      (acceptance_rules.py)
        │  Regression). Release gate for factual correct-│
        │  ness. Any critical failure ⇒ RED.             │
        └──────────────────────────────────────────────┘
```

**Hard ordering rule:** the Chief-of-Staff Suite **may not be scored if Deep is not
GREEN.** A brilliant-sounding answer built on a wrong, stale, or unstable fact is a
failure, not a near-miss. Deep gates the release; the CoS Suite gates *excellence*.

This mirrors the Playbook's three gates of done: **Engineering** and **Product**
(green tests, customer value) are necessary but not sufficient; **Gate 3 (Chief-of-
Staff Quality)** asks whether Beth behaves like an elite human Chief of Staff. The
CoS Acceptance Suite is the automated expression of Gate 3.

---

## What the CoS Suite measures (NOT factual correctness — that's Deep)

Deep proves the facts are right. The CoS Suite asks: *given correct facts, does Beth
act like an exceptional Chief of Staff?* Proposed evaluation dimensions:

| Dimension | The question it scores | Example failing behavior |
|---|---|---|
| **Judgment / prioritization** | Did Beth surface what *matters most*, not just what was asked? | Lists ten things with no sense of priority. |
| **Proactivity** | Did Beth flag the thing the user *should* know but didn't ask? | Answers literally; misses the looming refill / conflict. |
| **Cross-domain synthesis** | Did Beth connect domains a great CoS would (health × calendar × goals)? | Treats each domain in isolation. |
| **Appropriate confidence / humility** | Did Beth's certainty match the evidence (builds on Law 2)? | Confident tone over thin data; or hedging over solid data. |
| **Actionability** | Is there a clear, *right-sized* next step (not a coaching cliché)? | "Maintain momentum" / vague encouragement (already banned in Deep). |
| **Tone & relationship** | Warm, direct, peer-level — an elite CoS, not a chatbot or a coach. | Robotic, sycophantic, or lecturing. |
| **Continuity / memory** | Did Beth honor prior context and commitments? | Forgets what was said a turn ago; re-asks the known. |
| **The morning test** | *Would tomorrow morning's conversation feel better because of this?* | Technically correct, experientially flat. |

These are **judgment dimensions** — most require an LLM-judge or human rater, unlike
Deep's deterministic checks. That is precisely why Deep must be deterministic and
must gate first: we never ask a fuzzy judge to bless an answer whose facts we have
not already proven.

---

## Proposed structure (to implement later)

- **Reuse the existing harness contracts.** New question category `cos` with its own
  builders in `acceptance_rules.py`, depth `deep`, gated behind a Deep-GREEN
  precondition in `acceptance_service.py` / the `beth_acceptance` command.
- **Scenario-based, multi-turn.** Unlike Deep's single-shot factual probes, CoS
  scenarios are short conversations (a morning brief, a "what should I do today",
  a cross-domain trade-off) scored on the dimensions above.
- **Judge model + rubric, not keyword gates.** Each dimension gets a deterministic
  rubric the judge fills; scores roll up like Deep's grade, but the gate is
  *excellence* (e.g. ≥ a higher bar), not pass/fail correctness.
- **Golden transcripts.** Curated "this is what an elite CoS answer looks like"
  references per scenario, versioned, so quality is measured against an explicit bar
  and can't silently drift.
- **Promotion path.** A CoS scenario only enters the gating set once it is stable and
  agreed; until then it runs in **shadow** (scored, non-blocking) — the same
  discipline used for routing changes.

---

## Non-goals (for the design phase)

- No new Beth intelligence, coaching, or reasoning is built to satisfy this suite.
  The suite *measures*; it does not motivate feature work by itself.
- The CoS Suite never overrides Deep. Factual trust is non-negotiable and first.

---

## Relationship to the Architecture Laws

Deep operationalizes Laws **0 (Intent), 1 (Freshness), 2 (Confidence), 4
(Deterministic Retrieval), 5 (Stable Truth)** as release-blocking checks. The CoS
Suite operationalizes the *spirit above the Laws* — that **Beth is the product**, and
every subsystem exists to make her a Chief of Staff customers trust enough to rely on
every day. Deep makes her trustworthy; the CoS Suite makes her exceptional. Build
Deep first.

*Last updated: 2026-06-28 (design established).*
