# WLJ — Whole-Life Executive Understanding

*North-star design. Subordinate to `docs/WLJ_ARCHITECTURE_LAWS.md`. If this conflicts
with the Architecture Laws, the Laws win.*

Last updated: 2026-07-05

---

## 1. Product goal

Beth must behave like an exceptional human Chief of Staff for any paying customer:
know the whole person, understand what matters most, explain why, notice what the
customer would miss, warn early, recognize opportunity, recommend the one
highest-leverage action, and **admit clearly when WLJ does not yet have enough
canonical truth** — grounding every factual claim in deterministic WLJ truth, never
guessing.

The acceptance gate is behavioral, not architectural: *does this make Beth act more
like an elite Chief of Staff?*

## 2. Architecture goal

Strengthen the **existing** path — do not build a new brain, engine, or parallel
pipeline:

```
Raw Data → Signals → Canonical State (SAE) → Deterministic Intelligence
        → Executive Understanding (interpret / ExecutiveSignals) → Conversation
```

One executive brain (`interpret()` → `ExecutiveSignals`) synthesizes everything into
one picture. Every consumer (morning brief, decision support, dashboard, the LLM
prompt) presents that one understanding in the context of its own responsibility.

## 3. Chief-of-Staff capability model

- **KNOW** — situational awareness; retrieve any fact/detail/history on demand;
  remember important conversations/evidence; honestly flag missing/stale truth.
- **UNDERSTAND** — explain *why* something changed; recognize long-term patterns;
  connect cross-domain patterns; know what matters *most* now (the headline).
- **ANTICIPATE** — detect risks early; recognize opportunities.
- **ACT** — recommend the next best action (whole-life); evaluate a voiced decision;
  execute & track follow-through; coach toward goals.
- **RELATE** — listen & reconcile the user's own reports; be proactive at the right
  moment; prove/verify claims; speak as one coherent person.

## 4. Current gaps (repository-grounded)

The truth almost always **exists** and much of it is **computed**. The failures
cluster in **UNDERSTAND + ANTICIPATE**, and every one is a *reachability + synthesis*
gap, not a compute gap:

- `apps/core/ai_insights/` (`Insight`) and `apps/core/ai_predictions/`
  (`Prediction`, per-domain rules) and `apps/core/ai_cross_domain/`
  (`DomainCorrelation`) and `apps/core/ai_guidance/` (`GuidanceItem`) compute risks,
  predictions, patterns, and guidance — but a grep of the `cos_services` tool surface
  and `interpret()` for `Insight`/`Prediction`/`correlation` returns **nothing**.
  This intelligence is **stranded**: Beth cannot reach or synthesize it.
- `interpret()` (`executive_interpretation.py`) synthesizes only sleep + tasks +
  subjective + accomplishments; it hand-codes domains and consumes no intelligence.
- `build_cos_intelligence()` (`apps/ai/cos_intelligence.py`) already reaches the LLM
  every turn and composes goal-pace / recommendation-effectiveness / executive lenses
  / events / the cross-domain attention ranking — but **not** the
  `Insight/Prediction/GuidanceItem/DomainCorrelation` feed.

**Conclusion:** WLJ has been building the filing cabinet (retrieval plane) and the
voice (narration) well; the *intelligence* — the part that makes a Chief of Staff
worth paying for — is built but stranded. Make it reachable and synthesized.

## 5. How the Canonical Truth Plane supports the goal

`apps/core/truth/` (`DomainTruth`: `current`/`describe`/`history`/`state` + registry +
`build_executive_briefing`) is the intended uniform reachability substrate. It is the
*means*, not the end. It must be extended to surface the **intelligence** outputs (not
just current metrics), and `interpret()` must synthesize those. Rolling retrieval
faces to every domain for point-fact parity is lower value than making the existing
intelligence reachable + synthesized.

## 6. How intelligence becomes reachable + synthesized

- **Reachable (every turn):** `build_cos_intelligence()` gains an `intelligence`
  block — top active `Insight` (risks/opportunities by severity), `Prediction`
  (forward-looking, with confidence + horizon), `DomainCorrelation` (patterns), and
  `GuidanceItem` — read from the persisted, pre-computed records (no live compute).
  `cos_intelligence_narrative()` renders it declaratively with **basis + confidence**,
  and says "not enough evidence yet" when empty.
- **Synthesized (one brain):** `interpret()` consumes the same intelligence read and
  exposes `risks / opportunities / patterns / predictions / guidance` on
  `ExecutiveSignals`, folding the single most significant risk into `biggest_risk`
  and, when it is the dominant thing today, into the `executive_picture`. The morning
  brief, decision support, and the executive prompt block then reflect it for free.

## 7. Guardrails

- No raw ORM access from the LLM; no LLM-created facts (tools/context return
  deterministic truth + confidence; the LLM narrates only).
- No request-path heavy computation — read **persisted, pre-computed** intelligence
  (bounded, indexed, top-N, degrade-safe); never recompute insights/predictions on the
  request path.
- No duplicated truth; modify before adding (Architecture Law 5).
- One executive brain: `interpret()` remains the sole cross-domain ranking authority.
  Domains may report their own significance; they never decide whole-life priority.
- Streaming and non-streaming parity preserved (both consume the same context).
- Every factual claim cites deterministic basis; unavailable truth is stated honestly.

## 8. Staged rollout

- **Stage 1 (this doc's implementation):** make the existing
  `Insight/Prediction/GuidanceItem/DomainCorrelation` reachable (via
  `build_cos_intelligence`) **and** synthesized (via `interpret()`). Smallest safe
  diff on the existing executive path. Prove the felt capabilities: explain why /
  risk / opportunity / pattern / highest-leverage action / admit unavailable.
- **Stage 2:** extend `DomainTruth` with `executive_read()` (state + insights +
  predictions per domain) for a small evidence-based domain set; `interpret()`
  consumes it uniformly, replacing hand-coded reads (strangler).
- **Stage 3:** expose `describe()` as a detail-inspection tool; converge history;
  widen reachability to more domains as production conversations demand.

## 9. Acceptance criteria

Production-style questions, answered from deterministic truth + intelligence (never
generic advice, never hallucinated intelligence):

- "How am I doing overall?" / "Why?" — situational read + the driving insight/pattern.
- "Biggest risk?" — top `Prediction`/`Insight` risk with basis + confidence.
- "What opportunity am I missing?" — top positive insight / correlation.
- "What pattern do you see?" — top `DomainCorrelation` narrative.
- "What should I do next?" — the highest-leverage action, grounded.
- "What changed recently?" — recent events/insights.
- "What are you basing that on?" / "Do you know that or are you guessing?" — the basis
  and confidence, or an honest "WLJ doesn't have enough evidence yet."

## 10. Definition of done (Stage 1)

Beth references relevant insight/prediction/correlation/guidance when present;
`interpret()` reflects the top risk in the executive picture; unavailable intelligence
is admitted honestly; touched paths have tests; streaming/non-streaming parity holds.
