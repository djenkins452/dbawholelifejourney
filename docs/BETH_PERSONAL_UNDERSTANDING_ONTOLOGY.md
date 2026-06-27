# Personal Understanding — Evidence-First Ontology & Architecture (P36.1 → P36.2)

**Status:** DESIGN ONLY. No code. Supersedes the P36 framing (BehaviorDirective is a
derived consumer). v2 adds the **Pattern** stage and the **Evidence-First** mandate.
**Date:** 2026-06-27.

> Beth does not become wiser because an LLM thinks harder. Beth becomes wiser because she
> continuously transforms **evidence → pattern → understanding → better judgment**. The
> objective is not a larger memory system; it is a sharper, evidence-backed understanding
> of Danny that improves every recommendation, conversation, and decision.

---

## 0. The defining principle — Evidence-First

Every understanding **originates from evidence**, discovered by a **deterministic**
detector — never from LLM intuition, prompts, or assumptions. The deterministic system
*discovers the pattern and establishes the confidence*. The LLM's role is strictly
**downstream and optional**: it may later **summarize, explain, narrate, or reflect** on
understanding that already exists — it must **never originate** it. This is the same
invariant that made v3 robust ("WLJ owns truth; ChatGPT narrates"), now applied to
self-knowledge. Beth must always answer *"Why do you believe that?"* with evidence.

## 1. Architectural review (challenges)

The proposed pipeline is correct, with one added stage and three challenges:

```
Observations
   ↓  DETERMINISTIC pattern detection (the only thing that ORIGINATES understanding)
Patterns
   ↓  promotion when a pattern is confident enough
Personal Understanding         ← the PRIMARY abstraction
   ↓  derivation (one understanding → many)
Behavior Adaptation            ← BehaviorDirective, now a DERIVED consumer
   ↓
Executive Interpretation → Conversation Planning → Composer → Narration
   ↑
LLM (optional): summarize / explain / narrate / reflect — never originate
```

- **Challenge A — `Identity / Preferences / Patterns` are not pipeline layers.** They are
  *kinds* of Understanding (a field). The pipeline stages are Observation → Pattern →
  Understanding → Adaptation → Interpretation. (A "pattern" the user lists as a *stage* is
  the deterministic detection step; a "pattern" as a *kind* is a behavioral regularity —
  same word, two roles, both kept, clearly separated below.)
- **Challenge B — Do not add a third fact store.** `ai_memory.PersonalFact` and
  `ai_eae.ExtractedFact` (source-weighted confidence, polymorphic source) are the
  **Observation layer**. Understanding sits *above* them.
- **Challenge C — Don't store free-text behaviors on the Understanding.** Store
  *implications*; **derive** the adaptations (so they stay consistent and explainable).

**BehaviorDirective verdict (the user's hypothesis, confirmed):** it is **one derived
consumer** of Personal Understanding, not the primary storage. One Understanding fans out
to many adaptations. Keep the P36 directive *consumer wiring*; re-parent its *origin*.

## 2. Current P36 implementation review

P36 Phase 1 shipped `BehaviorDirective` (keyed, compressing, confidence, source, evidence,
explain) + an Interpretation consumer (`deprioritize:` honored end-to-end). It correctly
proves *knowledge → behavior change*. Its only flaw is **altitude**: it stores the
*adaptation* as if it were the knowledge. The richer model stores the *understanding* and
derives the adaptation. So P36 is the correct **bottom** of the stack, missing the layer
above it.

## 3. The five concepts (crisp definitions)

- **Observation** — a single, raw, timestamped, sourced evidentiary fact or event: one
  journal entry; "today's shower was at 1pm"; "Danny said he had childhood trauma involving
  Nell from Detroit". Atomic. Lives in the Observation layer (PersonalFact / ExtractedFact
  / SignalSnapshot / journal / chat). *Beth remembers these.*
- **Pattern** — a **deterministically detected regularity** across many observations:
  "weekend shower delayed in 5 of the last 6 weekends". It is *evidence about a regularity*
  — a rule + window + hit/miss tally + a confidence that rises with corroboration and falls
  with contradiction. A pattern is **not yet a belief**; it is the machinery that *earns*
  one. Detected by deterministic detectors, never the LLM.
- **Understanding** — a durable, synthesized **belief** about Danny, promoted from one or
  more confident patterns/observations: "Weekend routine timing is not a useful indicator
  of discipline for Danny." It carries meaning, affected domains, implications, sensitivity,
  confidence, decay, and evidence pointers. *Beth understands these.* The PRIMARY abstraction.
- **Behavior Adaptation** — a concrete, consumable behavior change **derived** from an
  understanding (the existing `BehaviorDirective`, e.g. `deprioritize:shower`, `tone:direct`).
  One understanding → many adaptations.
- **Executive Interpretation** — the judgment layer (`ExecutiveSignals`, P35) that consumes
  adaptations + reads understandings directly (e.g. sensitivity → pacing) to shape the brief.

How **understanding differs from behavior**: understanding is *what Beth believes and why*
(durable, explainable, evidence-backed); behavior is the *consequence* (derived, swappable).
Behavior is downstream of knowledge — never the knowledge itself.

How **many behaviors emerge from one understanding**: the understanding's `implications`
(structured) are expanded by a deterministic `derive()` step into multiple directives —
e.g. weekend-recovery → {deprioritize weekend shower, soften the weekend morning brief,
drop weekend urgency, coach with latitude}. Change the understanding once; all derived
behaviors update consistently.

## 4. Ontology (schema sketch — final schema chosen in Phase 2)

```
Observation        : (existing stores — unchanged)

Pattern (deterministic detector output; captured as structured EVIDENCE, not a new store)
  rule            : declarative detector id ("weekend_routine_delayed")
  window          : evaluation window (e.g. last 6 weekends)
  hits / misses   : the tally (rises/falls deterministically)
  confidence      : f(hits, misses, recency)   ← established by the detector, not the LLM
  observation_refs: pointers to the supporting observations

Understanding(user)                              ← PRIMARY abstraction
  concept_key     : canonical dedup/merge id ("weekend-recovery-orientation",
                    "topic-sensitivity:detroit-abuse", "journaling-core-practice")
  kind            : identity | value | preference | pattern | sensitivity |
                    communication | capability | relationship
  statement       : the belief, in Beth's words
  meaning         : why it's true / what it reveals
  affected_domains: [health, faith, work, family, execution, communication, emotional…]
  implications    : structured hints that DERIVE behavior (not free-text behaviors)
  sensitivity     : none | elevated | high       (drives PROTECTIVE behavior)
  confidence      : 0..1                          (from the underlying patterns)
  evidence        : { patterns:[…], observation_refs:[…], source_mix:{told,observed,…} }
  status          : forming | active | weakening | contradicted | retired
  decay_half_life : per-kind (identity≈years, preference≈months, pattern≈weeks)
  created / last_reinforced / last_challenged

BehaviorDirective : (existing) + nullable FK → Understanding   ← DERIVED consumer
```

A pattern need **not** be its own table: it is the deterministic detector's output, stored
as structured `evidence` on the Understanding it supports (explainable, no store
proliferation). A separate `PatternObservation` table is an *option* only if we later want
independent longitudinal pattern history.

## 5. How understanding evolves over months and years

```
Day 1     a single observation         → no understanding (one data point ≠ a belief)
Weeks     observations recur           → a Pattern forms; confidence climbs deterministically
Pattern crosses θ_active               → a forming Understanding becomes ACTIVE; behaviors derive
Months    continued corroboration      → confidence saturates; the belief is trusted, low-touch
Explicit "remember that I…" (told)     → instant high-confidence Understanding (no waiting)
Contradiction / correction by Danny    → confidence drops → weakening → retired/superseded
Silence (no reinforcement)             → kind-specific DECAY; stale patterns fade so they stop
                                          driving behavior; identity barely moves
Two beliefs about one concept          → MERGE into one richer statement
```

Net: **observations grow linearly with life; understandings stay roughly constant and get
*sharper*.** That is the difference between a memory database and wisdom.

## 6. Confidence evolution

- **Origin (deterministic):** pattern confidence = f(hits, misses, recency, sample size).
  Source sets the *floor* (told/confirmed high; observed/derived earn it). Reuse the
  existing `ExtractedFact` source-weighting — don't reinvent.
- **Reinforce:** each corroborating observation raises confidence with diminishing returns.
- **Decay:** time-based, **kind-specific half-life** — a stale "pattern"-kind belief loses
  confidence quickly (it shouldn't drive behavior on old evidence); identity barely decays.
- **Gate:** only confidence ≥ θ_actionable derives behavior. Below it, Beth holds the belief
  *tentatively* and softens any claim ("it looks like…").

## 7. How contradictory evidence weakens understanding

- A miss in the pattern window lowers pattern confidence → lowers the Understanding.
- An explicit **correction by Danny** (`source=corrected`) applies the largest decrement and
  can immediately move a belief to `weakening`/`retired` — Danny's word outweighs inference.
- A directly **contradictory understanding** (same concept, opposite statement) triggers a
  reconciliation: the better-evidenced one wins; the loser is superseded with a trail
  (explainability is preserved — Beth can say *what she used to think and why she changed*).
- Nothing is silently overwritten; weakening and retirement are logged.

## 8. How downstream systems consume understanding

- **Executive Interpretation:** structured behavior via derived directives (P36 wiring,
  unchanged: `deprioritize:`, `tone:`); plus reads `sensitivity`/`pattern` understandings
  directly to set pacing, protective framing, and proactive coaching on `ExecutiveSignals`.
- **Conversation Planner:** reads `communication` + `sensitivity` understandings (e.g.
  high-sensitivity topic → slow down, empathy, avoid references, emotional-safety objective).
- **Composer:** reads `tone`/value understandings for wording.
- **Explainability everywhere:** every adaptation traces understanding → patterns →
  observations, with confidence + last_reinforced + decay rule.

## 9. Smallest safe Phase 2 (deterministic, evidence-first)

1. **`Understanding` model** (one additive migration) + nullable `BehaviorDirective.understanding`
   FK (additive). No change to observation stores.
2. **One deterministic pattern detector**, end-to-end, for the weekend-recovery example:
   it reads existing observations (routine completion times), computes the hit/miss tally,
   establishes confidence, and on θ_active promotes a forming Understanding to active. No LLM.
3. **`derive(understanding) → [BehaviorDirective…]`** — prove **one understanding → ≥3
   distinct adaptations** flowing into the brief (reuse the P36 consumer unchanged).
4. **Confidence + decay + contradiction** working on that one understanding (a miss weakens
   it; an explicit correction retires it), with `explain()` tracing to evidence.
5. Re-point "What I Know About You" to render **Understandings** (compressed), not the raw log.
6. **LLM stays out of origination.** A flag-gated LLM *explainer/summariser* over existing
   Understandings is an optional later add — never the source of belief.

Phase 2 proves the architecture (observation → pattern → understanding → many adaptations →
judgment) on **one** rich understanding, deterministically, with compression, confidence,
decay, contradiction, and explainability — not the full detector library for every kind.

---

### Survives / Evolves / Disappears
- **Survives:** PersonalFact, ExtractedFact, SignalSnapshot, EAE confidence machinery,
  journal/chat/signal history, Executive Interpretation, the P36 directive *consumer* wiring.
- **Evolves:** BehaviorDirective is re-parented (derived from Understanding); "What I Know
  About You" renders Understandings.
- **Disappears:** the observation-*log* presentation; the long-term goal of two parallel
  fact stores (converge later, not now). No LLM-originated personality.
