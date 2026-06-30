# Layer 2 Constitution — Executive Reasoning

> The governing document for Layer 2. Layer 1 (Canonical Truth) answers **"what is
> true?"** Layer 2 answers **"what does that truth mean in this conversation?"** Layer 2
> reasons OVER truth and **never creates truth**.

## First principles

1. **Layer 2 never creates truth.** Every reasoning engine reads a Layer 1 fact/value and
   returns a *judgement*; it never writes, mutates, or invents a truth value. Risk is read
   from Layer 1's interpretation, never manufactured from a bare number.
2. **Consume Layer 1 only through its public interfaces** (Current Truth, History,
   Freshness, Confidence, Stability, Domain Truth, the Deterministic Provider Registry).
   Layer 1 is frozen; Layer 2 must never modify it. A change that would touch Layer 1 stops
   for formal change control.
3. **The user owns the request; the metric owns the method.** Comparison Target (what the
   user asked) is honored first and always; Comparison Semantics (how a metric should be
   compared) is additive, never substitutive.
4. **Anchor discipline.** The Active Subject moves only on a primary question or an explicit
   refocus; comparisons reason against it without moving it.
5. **Fulfil the objective, not the literal prompt.** A comparison goal produces the
   comparison; an explanation goal explains.
6. **Reasoning is transparent and confidence-bearing.** A conclusion carries why it was
   reached and how trustworthy it is (weakest-link confidence).
7. **Trust is the success metric.** Every reasoning path asks: does this increase or
   decrease customer trust? Production conversations are the backlog, not synthetic tests.

## Capabilities (certified scope)

Conversation Object · Conversation Goal · Active Subject · Referential Resolution ·
Comparison Semantics · Intent Fulfillment · Reasoning Confidence · Risk Reasoning ·
Priority Reasoning · Reason Explanation & Transparency · Natural Follow-up.

## Reusable reasoning engines

`apps/ai/chatgpt_cos/reasoning/engines.py` — `reasoning_confidence` (weakest link),
`assess_risk` (read-only from interpretation), `prioritize` (rank by significance),
`explain` (transparency). Built once; consumed by the conversation layer and every domain.

## Layer boundary (enforced by tests)

| Layer 2 may CONSUME (read-only) | Layer 2 OWNS |
|---|---|
| Current Truth, History, Freshness, Confidence, Stability, Domain Truth, Provider Registry | Conversation Objects, Goals, Active Subject, Comparison Semantics, Intent Fulfillment, Referential Resolution, the reasoning engines, Presentation reasoning |

`test_layer2_certification.py::Layer2DeepTests` proves reasoning does not mutate a Layer 1
fact; `Layer2SmokeTests` proves Layer 1 stays certified + frozen.

## Change control

Layer 2 is **frozen** on certification. Changes follow the Layer 1 discipline: repository
investigation → root cause → reusable capability → regression → acceptance → conversation
replay → permanent protection. Never patch symptoms.

## Deferred to Layer 3 (named)

Action Selection / execution · Cross-Domain Conflict Resolution · Recommendation ranking
across domains · Deep-Timeline Retrieval (a Layer 1 change-control item, not Layer 2).
