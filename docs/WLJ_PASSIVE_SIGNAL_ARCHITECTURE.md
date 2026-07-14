# WLJ Passive Deterministic Signal Generation — Architecture Whitepaper

> **Status:** Architecture research (NOT implementation). Established 2026-07-13.
> **Origin:** The Signal Health investigation proved that WLJ's behavioral domains go
> "silent" not because the pipeline fails, but because their signals depend on
> **explicit user logging** the user doesn't do. Health already avoids this. This
> paper evaluates generalizing Health's model across the platform.

---

## 1. Thesis

**WLJ's intelligence is gated by signal density, and signal density is currently
gated by explicit user input.** A domain produces truth only when the user performs a
dedicated logging action (a `RelationshipInteraction` row, a `Transaction`, a prayer
log). Health is the exception: HealthKit and device data feed deterministic health
signals **passively**, with no logging ritual — which is exactly why Health is the
platform's most "intelligently healthy" domain.

The next major evolution of WLJ's intelligence architecture is to **derive the same
deterministic domain signals passively, from data the user already generates** —
journal, capture, conversations, photos, calendar, transaction feeds, reading plans —
rather than from a dedicated per-domain logging surface.

This is not a feature. It is a shift in where truth comes from:

> **From "signals you must log" → to "signals inferred deterministically from what
> you already do."**

## 2. The Pattern: Passive Signal Derivation

Each behavioral domain owns one or more **signal sources**. Today most domains have
exactly one source: an explicit-logging model. The pattern generalizes this to a
**source set** per signal type:

```
signal_type  ←  { explicit source, passive source₁, passive source₂, … }
```

Example — `relational_engagement` (relationships):

| Source | Kind | Deterministic evidence |
|---|---|---|
| `RelationshipInteraction` | explicit | user logged an interaction (today's behaviour) |
| journal `Mention`s of people | passive | user @mentioned N distinct people in a journal entry |
| calendar events with attendees | passive | user had a scheduled event involving named people |
| capture transcripts naming people | passive | a voice note referenced known contacts |

Each source computes the **same signal type** deterministically and independently;
Layer 1 merges them under a precedence/confidence rule (see §5).

The defining property that makes this WLJ and not "an AI guessing":

> **The model PERCEIVES; WLJ COMPUTES; WLJ KNOWS.**

A frontier model may *perceive* raw ambient data — extract named entities from a
journal entry, read attendees off a calendar, group faces in photos — but the **signal
itself is computed deterministically by WLJ** from those extracted facts. "User
@mentioned 3 distinct people today → `relational_engagement = 1.0`" is a deterministic
rule over a perceived fact, not a verdict about the user's social life.

## 3. The Determinism Boundary (the non-negotiable line)

Passive derivation is only legitimate when it stays on the deterministic side of the
line WLJ already enforces (`WLJ_LLM_TRUTH_ACTION_CONTRACT.md`):

- **Perception (model, provider-agnostic):** extract structured facts from ambient
  data — entities, mentions, attendees, amounts, dates. Fuzzy, probabilistic, replaceable.
- **Computation (WLJ, deterministic):** turn extracted facts into a signal via a fixed
  rule. Auditable, reproducible, provider-independent.

A passive source **must not** produce a signal from inference ("the model thinks the
user felt connected"). It produces a signal only from **deterministic evidence** that a
perceived fact exists (a mention is present; an amount was charged). If the evidence is
absent, the source returns nothing — exactly as `_compute_relational_engagement`
already returns `None` when `interaction_count == 0`.

This boundary is what lets passive signals be **Layer 1 Truth** rather than Layer 2
reasoning.

## 4. Constitutional Fit

Passive signal generation is not a new principle — it is the existing principles
applied more widely.

- **"The model reasons. WLJ knows." / Personal Truth Platform.** Perception is the
  model's; the deterministic signal is WLJ's. Truth stays owned by WLJ.
- **Provider-agnosticism.** Extraction sits behind the one model seam; the signal
  computation names no provider. Swapping the perception model changes nothing
  deterministic.
- **Facts, not verdicts (I.4).** A passively-derived signal is a fact (a deterministic
  score + provenance), never a verdict.
- **Simplicity — WLJ gets SIMPLER as models improve.** This is the strongest fit. Today
  every domain needs a bespoke logging UI to be intelligent. As perception models get
  better at reading journals/photos/calendars, **more domains become passively fed
  without new logging surfaces** — the platform sheds manual-entry scaffolding rather
  than accreting it. The "silent domain" class shrinks structurally.
- **Constitutional Review.** Introducing passive sources does **not** change a
  Constitutional Article — it uses the existing truth/perception boundary. Any *specific*
  passive source that would blur perception into verdict, or ingest a newly sensitive
  data class (photos, location), requires the normal privacy + review discipline, not a
  Constitutional amendment.

## 5. Effect on Layer 1 Truth

Layer 1 gains a **multi-source truth** shape per domain (Health already has this:
HealthKit + manual entry):

- **Source set + precedence.** Each signal type declares its sources and a
  deterministic merge rule (e.g. explicit-log wins; else highest-confidence passive
  source; else union of evidence). This must be *one* deterministic resolver per signal
  type — the same single-producer discipline Layer 1 already requires (cf. the sleep /
  execution single-source rules).
- **Provenance + confidence envelope.** Every signal carries its source and a
  confidence reflecting how it was derived (an explicit log > a calendar inference).
  The truth envelope (freshness/confidence/source) already exists — passive derivation
  populates `source` and lowers `confidence` honestly.
- **No fabrication.** The determinism boundary (§3) is the guardrail: a source emits a
  signal only on deterministic evidence, so multi-source does not become multi-guess.
- **Dedup across sources.** The same real-world event perceived by two sources (a
  journal entry *and* a calendar event about the same dinner) must not double-count —
  Layer 1 needs an occurrence-level dedup, analogous to the existing occurrence-scoped
  completion rule.

## 6. Effect on Signal Health

Passive derivation **dissolves the drought class** for covered domains:

- A domain is "silent" today when the user skipped its logging ritual. With passive
  sources, a domain is silent only when the user did *nothing* touching it across *all*
  ambient sources — which is a genuinely meaningful signal, not a logging gap.
- The **signal-eligibility** model (implemented 2026-07-13, ADR-29) extends cleanly: a
  domain is eligible when it has ≥1 **non-stubbed source** — explicit *or passive*.
  Finance becomes eligible the moment a real transactions feed exists; it stops being a
  coming-soon exclusion and becomes genuinely monitored.
- Signal Health shifts from monitoring *aggregate* domain output to monitoring **source
  health** — "is the journal→relational_engagement derivation running and producing?"
  — which is a truer operational question.
- **Diversity** monitoring stays scoped to behavioral domains (ADR-29); engine modules
  remain excluded. Passive sources may *increase* a domain's real diversity, but that is
  a product outcome, never a target to game.

## 7. Effect on Mission Intelligence

- **Continuity.** Mission progress currently stalls when a domain goes quiet for
  logging reasons. Passive signals make mission truth **continuous** — a relationship
  mission keeps advancing because journaling about a friend feeds it, with no separate
  log.
- **Mission Link density.** `mission_link` joins actions → signal types → goals. More
  signal sources means richer, more accurate action→mission attribution (an action the
  user already takes now counts toward a mission it always supported).
- **Deterministic, actionable CoS truth.** The CoS can say, deterministically,
  "relationship engagement is passively derived and has been zero across journal,
  capture and calendar for 14 days" — a fact worth surfacing, distinct from "you forgot
  to log," and safe to act on because it is deterministic.

## 8. Transition Path (phased — research, not committed work)

1. **Source inventory.** Per domain, enumerate ambient sources already present in WLJ
   (relationships ← journal `Mention`s / calendar; finance ← transactions / recurring
   bills; faith ← reading plans / prayer history) and which are deterministic today.
2. **Passive computers.** Add deterministic passive source computers alongside the
   explicit ones (mirroring `_compute_*` in `signal_aggregation.py`), each emitting the
   existing signal type with provenance + confidence, on deterministic evidence only.
3. **Layer 1 source resolver.** Define the per-signal-type merge/precedence + occurrence
   dedup (the single deterministic resolver).
4. **Signal Health re-basing.** Re-point eligibility to "has ≥1 non-stubbed source"
   and monitor source health; retire "silent = user didn't log."
5. **Privacy gating.** Sensitive ambient sources (photos, location, calendar) ship only
   behind explicit user consent and the existing privacy rules — perception of sensitive
   data is opt-in, per source.

## 9. Risks & Guardrails

- **Inference creep.** The single biggest risk: a passive source drifting from
  deterministic-evidence into model-guessed verdict. Guardrail: §3 boundary, enforced
  the same way Layer 1 already forbids fabrication.
- **Privacy surface.** Passive sources read more of the user's life. Each new ambient
  source is opt-in and privacy-reviewed; perception of a sensitive class is never on by
  default.
- **Double-counting.** Cross-source dedup (§5) is required or missions/health inflate.
- **Confidence honesty.** Passive signals must not present with explicit-log confidence.

## 10. Recommendation

This **is** a defining evolution of WLJ's intelligence architecture and it is
**Constitution-aligned** (it is the "model perceives, WLJ computes, WLJ gets simpler"
principle generalized). It should be adopted as a research track and sequenced after the
current Operations stabilization, starting with a **single reference domain**
(relationships, using the journal-`Mention` source that already exists) to prove the
source-set + resolver + provenance pattern end-to-end before generalizing — exactly how
Medication became the certified Layer 1 reference. No implementation is proposed here.
