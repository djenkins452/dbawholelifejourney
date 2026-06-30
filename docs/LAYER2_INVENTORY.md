# Layer 2 — Executive Reasoning: Inventory

> Layer 1 answers *"what is true?"* Layer 2 answers *"what does that truth mean in this
> conversation?"* Layer 2 reasons OVER truth; it never creates truth. Classified by
> **reusable reasoning capability**, not by feature.

## Reasoning capabilities — what exists, where, and gaps

| Reasoning capability | Status | Lives in | Notes |
|---|---|---|---|
| **Conversation Continuation** (carry topic/frame across turns) | ✅ built | `conversation_memory.py`, `conversation_object.py` | the active conversation frame |
| **Context Engine / Active Subject** (which object owns the conversation) | ✅ built | `conversation_object.py` (TOPICS, active_subject), `referential.py` | anchor never drifts |
| **Question Classification / Disambiguation** (reference vs new subject) | ✅ built | `referential.py::_classify_reference`, `foundational_facts.py::classify_foundational_fact` | guards against hijacking full questions |
| **Conversation Goal reasoning** (review→compare→trend→investigate) | ✅ built | `conversation_object.py::evolve_goal` | the objective, evolves |
| **Intent Fulfillment** (accomplish the objective, not the literal prompt) | ✅ built | `fulfillment.py` | comparison IS the answer |
| **Decision reasoning — Comparison Semantics** (how to compare each metric) | ✅ built | `conversation_object.py::COMPARISON_SEMANTICS`, `referential.py::_compare` | target honored, semantics additive |
| **Reason Explanation** (why she said it / what it means) | ✅ built | `conversation_memory.py::compose_why/compose_meaning/compose_concern` | from the stored fact |
| **Natural Follow-up generation** (what changed / anything else / is that an average) | ✅ built | `conversation_memory.py::compose_what_changed/compose_more/compose_is_average` | topic-aware |
| **Priority reasoning** (rank by significance) | ✅ built | `apps/core/blueprint/briefing.py::_significance` | executive briefing tiers |
| **Reasoning Confidence** (how trustworthy is a conclusion) | ◑ partial → **consolidated** | Layer 1 `confidence`, `comparison_confidence` | unified in `reasoning.py` |
| **Risk reasoning** (flag elevated/uncertain) | ◑ partial → **consolidated** | glucose clinical interpretation (Layer 1) | surfaced via `reasoning.py::assess_risk` (consumes, never invents) |
| **Reasoning Transparency** (state the basis) | ◑ partial → **consolidated** | inline explanations | `reasoning.py::explain` |
| **Recommendation reasoning / ranking** | ◑ partial | comparison recommendation (additive average) | scoped; full ranking → Layer 3 |
| **Conflict Detection** (contradictory truth) | ◑ partial | Layer 1 Stability + temporal_warning | detection of contradictions → Layer 3 |
| **Action selection / Action prioritization** | ⛔ Layer 3 | — | acting on truth, not reasoning over it |

## Duplication found & resolved

- **Confidence** was computed ad hoc (`comparison_confidence`, Layer 1 `confidence`). Layer 2
  consolidates the *combination* rule (weakest-link) in `reasoning.py::reasoning_confidence`
  — it does not re-derive any single confidence (those stay Layer 1).
- **Risk** was read inline from glucose interpretation. `assess_risk` makes the read reusable
  for any domain whose Layer 1 fact carries an interpretation — without creating risk.

## What incorrectly resided elsewhere — and the boundary

Nothing in Layer 1 was moved. Layer 2 reasoning that was *inlined* into the conversation
modules is now also exposed as named reusable engines in `reasoning.py`, so a new domain
consumes the engine instead of re-implementing the pattern. Layer 1 truth modules
(`apps/core/truth/*`, `fact_registry`) are consumed read-only.

## Layer boundary (enforced)

Layer 2 **consumes** Layer 1: Current Truth, History, Freshness, Confidence, Stability,
Domain Truth, the Deterministic Provider Registry — **read-only**. Layer 2 **owns**:
Conversation Objects, Goals, Active Subject, Comparison Semantics, Intent Fulfillment,
Referential Resolution, the reasoning engines, and the Presentation reasoning. Layer 2
never modifies a Layer 1 object.

## Deferred to Layer 3 (named)

- Action selection / execution (doing, not reasoning).
- Cross-domain conflict resolution and recommendation ranking across domains.
- Deep-timeline retrieval (needs Layer 1 history extension — a Layer 1 change-control item).
