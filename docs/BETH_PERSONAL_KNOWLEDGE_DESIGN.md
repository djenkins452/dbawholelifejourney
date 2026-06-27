# Personal Knowledge & Adaptive Understanding — Design (P36)

**Status:** Phase 1 IMPLEMENTED (Layer-4 Behavior Guidance + Interpretation consumer).
Phases 2–3 designed, pending. **Date:** 2026-06-27.

---

## 1. Architectural review (challenge: new engine, or evolution?)

**Evolution — not a new engine.** Repository evidence is decisive: WLJ already has the
storage and confidence machinery.

- `apps/core/ai_memory/models.py` — `PersonalFact` (fact_type/subject/text/confidence/
  source), `LearnedMapping` (phrase→meaning, confidence, usage_count), `ContextSnapshot`,
  `ClarificationLog`. + `life_fact_extractor` (LLM extraction).
- `apps/core/ai_eae/models.py` — `ExtractedFact` (**confidence = LLM_confidence ×
  source_weight** — the prompt's "different evidence → different confidence" already
  exists), `SignalSnapshot`, `EAEState`, `EAEDecisionLog`, `EAEOverride`.

So adding a **third fact store** would be exactly the duplication the prompt warns
against. The thing that does **not** exist anywhere is **Layer 4 — Behavior Guidance**:
nothing converts knowledge into "why should this change how Beth behaves?" directives
that the Interpretation Engine / Conversation Planner / Composer **consume**. Today
facts are *stored* and *displayed* ("What I Know About You") but never *adapt behavior*.
That gap — knowledge → behavior change — is the whole point of P36, and it is one new,
non-duplicative concept.

**Therefore:** add the missing Layer-4 directive type + a deterministic consumer seam in
the Executive Interpretation Engine (P35 made interpretation the single owner of
judgment — so it is the correct place for learned knowledge to change behavior). Reuse
everything else.

## 2. Current knowledge audit

- **Strengths:** real persistence (`PersonalFact`), source-weighted confidence
  (`ExtractedFact`), longitudinal signals (`SignalSnapshot`), an extraction pipeline,
  and a decision/override log (EAE). A strong foundation.
- **Weaknesses:** (a) **no behavior layer** — facts never change a recommendation,
  conversation, or decision (the prompt's core test "why should this change how Beth
  behaves?" is unanswerable today); (b) **two fact stores** (PersonalFact + ExtractedFact)
  with overlapping purpose; (c) the "What I Know About You" surface reads as an
  **observation log** ("journaled 48 times / values journaling") — repetitive, not
  compressed, not behavior-changing.
- **Duplication:** the same understanding appears as many rows ("Danny journals" /
  "journals regularly" / "values journaling") with no compression to ONE richer item.
- **Missing concepts:** behavior_change, evidence_count (reinforcement), status
  (active/weak/retired), a compression/merge key, and a downstream consumer.

## 3. Knowledge model

**Every learned item is a behavior DIRECTIVE, keyed for compression:**

```
BehaviorDirective(user)
  layer        : identity | preference | pattern | guidance   (the 4 layers)
  key          : structured, e.g. "deprioritize:shower" | "tone:direct" |
                 "recovery_activity:motorcycle"  ← the COMPRESSION + behavior unit
  observation  : "Danny typically delays showering on weekends."
  meaning      : "Weekend shower timing is not an indicator of discipline."
  behavior_change : "Don't elevate weekend shower timing into the day's priorities."
  confidence   : 0..1
  source       : told | observed | derived | confirmed | corrected
  evidence     : free text (for "why do you think that?")
  evidence_count : longitudinal reinforcement count
  status       : active | weak | retired
```

- **Ownership:** the directive store owns *what was learned*; the **Interpretation
  Engine** owns *how it changes the judgment*; the **Composer** owns *how it's said*.
- **Lifecycle / confidence:** `learn()` upserts by `(user, key)` — re-learning
  **reinforces** (confidence ↑, evidence_count ↑) rather than duplicating (compression).
  `contradict()` **weakens** (confidence ↓ → `weak` → `retired`). Source sets the
  starting confidence (told/confirmed high, observed/derived lower then earned up).
- **Compression:** one row per `(user, key)`. "Danny journals" × 48 → one directive
  with evidence_count=48, not 48 rows. Knowledge gets *richer*, not *larger*.
- **Behavior adaptation:** the Interpretation Engine reads active, confident
  (≥0.5) directives and applies the structured `key`: `deprioritize:<x>` removes `<x>`
  from the day's priorities/agenda; `tone:<style>` sets a wording hint; `recovery_activity:<x>`
  surfaces the preferred recovery activity when energy is the limiter.
- **Explainability:** `directive.explain()` → "Because <observation> (<source>; seen
  N×; C% confident), I <behavior_change>." Every adapted behavior traces to evidence;
  Beth never invents understanding.

## 4. Implementation roadmap

- **Phase 1 (shipped):** the `BehaviorDirective` model (one additive migration), the
  `behavior_guidance` provider (learn / compress / reinforce / contradict / explain /
  active-map), and the Interpretation consumer (`deprioritize` honored end-to-end so a
  learned preference visibly changes the brief). Fully defensive: no directives → zero
  behavior change → all existing behavior byte-identical.
- **Phase 2:** the **learning loop** — derive directives from longitudinal signals
  (sleep<6h → execution↓ pattern), from explicit "remember that I…" statements
  (source=told), and from corrections (source=corrected, weakens the prior). Compress
  the "What I Know About You" surface to directives. Confidence decay over time.
- **Phase 3:** richer behavior keys (tone/wording in the Composer; Conversation Planner
  reading communication preferences), contradiction-driven merge/retire, and an
  Acceptance "Adaptive Understanding" suite over multi-session histories.

**Migration strategy:** one additive model = one schema migration (new table, no change
to existing tables), applied on deploy via the Procfile `migrate`. Zero data backfill.
