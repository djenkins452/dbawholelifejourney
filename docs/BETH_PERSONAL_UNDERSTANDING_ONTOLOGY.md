# Personal Understanding — Ontology & Architecture (P36.1, design only)

**Status:** DESIGN ONLY. No code. Supersedes the P36 framing (BehaviorDirective is
demoted to a derived consumer). **Date:** 2026-06-27.

> The objective is not a larger memory system. It is a richer, increasingly accurate
> **understanding** of Danny that improves every future recommendation, conversation,
> coaching moment, and executive decision — without accumulating disconnected memories.

---

## 1. Architectural review (and where I challenge the proposal)

The proposed stack — `Identity → Preferences → Patterns → Understanding → Behavior
Adaptation → Executive Interpretation` — is directionally right but **conflates two
different axes**, and I recommend separating them:

- **Axis A — the pipeline (stages):** `Observation → Understanding → Behavior Adaptation
  → Executive Interpretation`. Four stages, each owned by one layer.
- **Axis B — the *kind* of understanding (a field, not a layer):** identity, value,
  preference, pattern, sensitivity, communication-style, capability, relationship.

So `Identity / Preferences / Patterns` are **kinds of Understanding**, not separate
layers. Collapsing them avoids a rigid six-tier stack and a proliferation of tables.

**The central correction (the user's hypothesis is correct):** `Understanding` is the
**primary abstraction**; `BehaviorDirective` is **one derived consumer** of it. One
Understanding fans out to *many* behavior adaptations:

```
Observation: "Danny consistently treats weekends differently."
        ↓ (synthesis, compression, confidence)
UNDERSTANDING: "Weekends are intentional recovery; weekend routine timing is not a
               discipline signal."   ← ONE rich, confidence-weighted belief
        ↓ (derivation — many adaptations from one understanding)
Behavior adaptations:  • don't elevate weekend showers
                       • soften the weekend morning briefing
                       • drop unnecessary urgency on weekends
                       • coach with latitude, not correction
        ↓
Executive Interpretation → Conversation Planner → Composer
```

Three more challenges:
1. **Do not add a third fact store.** WLJ already has `ai_memory.PersonalFact` and
   `ai_eae.ExtractedFact` (source-weighted confidence, polymorphic source). Those are the
   **Observation layer**. `Understanding` sits *above* them; it does not replace them.
2. **Don't store free-text "behavior adaptations" on the Understanding.** Derive them
   (so they stay consistent and explainable). The Understanding stores *implications*;
   directives are generated from implications.
3. **Sensitivity is a first-class dimension, not a pattern.** The abuse/Detroit example
   isn't "remember Nell" — it's an Understanding of kind=`sensitivity` whose *single*
   conclusion ("this topic is emotionally activating") drives many behaviors (slow down,
   empathy, avoid references, prioritize emotional safety). This must be modeled
   explicitly because its behavior adaptations are protective, not optimizing.

## 2. Current knowledge model (what exists today)

| Component | Role today | Verdict |
|---|---|---|
| `ai_memory.PersonalFact` | biographical facts (LLM-extracted), confidence, source | **Observation** — survives |
| `ai_eae.ExtractedFact` | facts with `confidence = LLM_conf × source_weight`, polymorphic source | **Observation** — survives (the richer store) |
| `ai_eae.SignalSnapshot` / `EAEState` | longitudinal signals + confidence machinery | **Observation / evidence** — survives, reused |
| journal / conversation / health history | raw longitudinal data | **Observation** — survives |
| `Executive Interpretation` (`ExecutiveSignals`) | judgment | **Consumer** — survives, gains Understanding inputs |
| `BehaviorDirective` (P36) | behavior change keyed for compression | **Re-parented** — becomes a *derived consumer* of Understanding |
| "What I Know About You" surface | renders raw observations (repetitive log) | **Changes** — renders Understandings instead |

Weakness today: there is **no synthesis layer**. Observations never compress into beliefs;
the same idea appears as many rows; nothing decays; nothing merges.

## 3. Proposed Personal Understanding ontology

The primary object is **`Understanding`** — a synthesized, confidence-weighted belief
about Danny, deduplicated by a canonical concept key.

```
Understanding(user)
  concept_key      : canonical id for dedup/merge ("weekend-recovery-orientation",
                     "journaling-core-practice", "topic-sensitivity:detroit-abuse")
  kind             : identity | value | preference | pattern | sensitivity |
                     communication | capability | relationship
  statement        : the belief, in Beth's words
  meaning          : why it's true / what it reveals about Danny
  affected_domains : [health, faith, work, family, execution, communication, emotional…]
  implications     : structured hints that DERIVE behavior (not free text adaptations)
  sensitivity      : none | elevated | high     (drives protective behavior)
  confidence       : 0..1
  evidence         : { summary, observation_refs:[…], source_mix:{told,observed,…} }
  evidence_count   : reinforcement count (longitudinal weight)
  status           : forming | active | weakening | contradicted | retired
  decay_half_life  : per-kind (identity=years, preference=months, pattern=weeks)
  created_at / last_reinforced_at / last_challenged_at
```

`BehaviorDirective` (existing) gains a nullable `understanding` FK and becomes the
**derived adaptation**: `derive_directives(understanding) → [BehaviorDirective…]`. Every
output answers *Observation, Meaning, Confidence, Evidence, Affected domains,
Implications, Behavior adaptations, Explainability* — but those live across the right
objects (most on Understanding; adaptations derived).

## 4. Layer ownership (one responsibility per layer)

1. **Observation** — `PersonalFact`/`ExtractedFact`/`SignalSnapshot`/journal/chat. Owns
   *raw facts and signals*. No synthesis. (Unchanged.)
2. **Understanding** (NEW) — owns *synthesized beliefs*: compression, confidence,
   evolution, merge, retire, explainability. The primary abstraction.
3. **Behavior Adaptation** — `BehaviorDirective`, *derived from* Understanding. Owns
   *concrete, consumable behavior changes* (the structured keys interpretation honors).
4. **Executive Interpretation** — owns *judgment* (`ExecutiveSignals`); consumes
   directives + reads Understanding directly for richer context (sensitivity/tone).
5. **Conversation Planner / Composer** — own *conversation strategy / wording*; consume
   the resulting judgment + communication/sensitivity understandings.

## 5. Lifecycle (how understanding evolves)

```
observation arrives (told / observed / derived)
   → MATCH to an existing Understanding by concept_key (semantic/deterministic)
       ├─ match  → REINFORCE (confidence ↑ with diminishing returns, evidence appended,
       │           evidence_count++, last_reinforced=now)  ← compression happens here
       └─ no match → new Understanding (status=forming, low confidence)
forming → active   when confidence ≥ θ_active AND evidence_count ≥ N
active → weakening when contradicted OR decayed below θ_active
weakening → retired/contradicted   when confidence < θ_retire
merge: two understandings sharing a concept → one richer statement (max evidence, union
       of domains, reconciled confidence)
derive: when an active understanding crosses θ_actionable or changes, (re)derive its
        BehaviorDirectives
```

## 6. Compression strategy (the whole point)

- **Concept-keyed collapse:** "Danny journals" / "journals regularly" / "values
  journaling" / "journaled 48×" → **one** Understanding `journaling-core-practice`
  (evidence_count=48, high confidence). The 48 journal entries remain in the Observation
  layer (real data); the *understanding* is singular.
- **Merge near-duplicates** by concept_key / semantic similarity.
- **Surface renders Understandings**, never the raw observation log. "What I Know About
  You" becomes "What I understand about you" — a short, rich, evolving list.
- **Net effect:** observations grow linearly with life; *understandings stay roughly
  constant and get richer.* Memory doesn't pile up; understanding sharpens.

## 7. Confidence evolution

- **Base** by source: confirmed/told high, observed/derived lower (reuse the existing
  `ExtractedFact` source-weighting — don't reinvent).
- **Reinforce:** +Δ per corroboration, diminishing toward 1.0.
- **Decay:** time-based, **kind-specific half-life** — identity barely decays; patterns
  decay fast (a stale pattern shouldn't drive behavior). A background job applies decay.
- **Contradict:** −Δ (largest for `corrected` by Danny) → weakening → retired.
- **Gate:** only confidence ≥ θ_actionable derives directives / influences behavior. Beth
  acts on what she's *sure enough* of, and softens claims she's unsure of.

## 8. How downstream systems consume understanding

- **Executive Interpretation:** structured behavior via derived directives (already wired
  in P36: `deprioritize:`, `tone:`); plus reads `sensitivity` understandings to set
  pacing/empathy on `ExecutiveSignals`.
- **Conversation Planner:** reads `communication` + `sensitivity` understandings (e.g.
  high-sensitivity topic → slow down, empathy, avoid references, emotional-safety
  objective).
- **Composer:** reads `tone` and value understandings for wording.
- **Recommendations / coaching:** read `pattern` understandings (sleep<6h → execution↓ →
  protect proactively).
- **Explainability everywhere:** any adaptation traces to its Understanding → evidence,
  confidence, last_reinforced, decay rule. Beth always answers "why do you believe this?"

## 9. Migration strategy

- One **additive** model: `Understanding` (new table). No change to observation stores.
- `BehaviorDirective` gains a **nullable** `understanding` FK (additive) — existing P36
  directives keep working as legacy/standalone; new ones are derived.
- **No destructive migration.** Converging `PersonalFact` + `ExtractedFact` into one
  canonical Observation store is a *later, separate* effort — not required here, and not a
  schema migration but a synthesis-input choice.
- Synthesis backfill (turn today's observations into Understandings) is a **background
  job**, not a migration — re-runnable, idempotent by concept_key.

## 10. What Phase 2 should actually implement (smallest valuable slice)

1. The `Understanding` model + the nullable `BehaviorDirective.understanding` FK.
2. A **deterministic synthesis service** `synthesize(user)`: map existing observations to
   concept-keyed Understandings (dedup/compress), confidence from source + reinforcement;
   idempotent. (LLM synthesis is optional, flag-gated enrichment — deterministic first.)
3. `derive_directives(understanding)` — one Understanding → many directives (reusing the
   P36 directive consumer, unchanged).
4. **Prove the fan-out end-to-end on ONE understanding** (the weekend-recovery example):
   a single Understanding drives ≥3 distinct behavior adaptations across the brief.
5. A **decay** job + `explain(understanding)`.
6. Re-point "What I Know About You" to render Understandings (compressed).

Phase 2 deliberately does **not** build the full learning loop for every kind; it proves
the architecture (observation → understanding → many adaptations → judgment) on one rich
understanding, with compression, confidence, and explainability working.

---

### Survives / Changes / Disappears
- **Survives:** PersonalFact, ExtractedFact, SignalSnapshot, EAE confidence machinery,
  journal/chat history, Executive Interpretation, the P36 directive *consumer* wiring.
- **Changes:** BehaviorDirective is re-parented (derived from Understanding); the
  "What I Know About You" surface renders Understandings.
- **Disappears:** the observation-log *presentation*; the long-term goal of two parallel
  fact stores (converge later, not now).
