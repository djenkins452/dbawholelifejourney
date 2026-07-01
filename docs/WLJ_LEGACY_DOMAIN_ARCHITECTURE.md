# WLJ Legacy Domain — Architecture Baseline

> **Status:** Canonical architecture reference (baseline v1). Implementation follows this document; this document does not follow implementation.
> **Domain class:** `PRESERVATION` (new — see §13).
> **Established:** 2026-07-01
> **Governs:** Everything the Legacy domain ingests, holds, connects, elicits, and produces — for decades.
> **Companion laws:** `WLJ_ARCHITECTURE_LAWS.md`, `LAYER1_ENTITY_COMPLETENESS_CONTRACT.md`, `LAYER1_CONSTITUTION.md`, `INTELLIGENCE_ARCHITECTURE.md`, `SIGNAL_TAXONOMY.md`, `docs/domain_registry`.

---

## 0. How to read this document

This is an **architecture baseline**, not a design spec. It defines *what must be true* about the Legacy domain forever, and *why*, at a level of abstraction that survives every technology change beneath it. It deliberately does **not** contain Django models, APIs, schemas, or implementation.

It exists to answer one question for every future implementation team:

> *When we build the thing that preserves a human life, what are the rules we are not allowed to break?*

Two audiences are assumed to read it: WLJ engineers (who must see how Legacy plugs into the existing platform without introducing a competing model), and a hypothetical steward in 2075 (who must be able to trust, interpret, and migrate the record long after this platform, and possibly this company, are gone).

**A note on lineage.** Legacy began as Danny's autobiography. That origin is discarded here on purpose. An autobiography is a *single output of a single subject authored once*. This document is optimized for the opposite: **every future WLJ user, every person they choose to preserve, captured continuously across generations, rendered into many outputs, none of which are the truth.** Where this document and the autobiography structure disagree, the autobiography structure is wrong.

---

## 1. Legacy Vision

### 1.1 What Legacy is

Legacy is a **Personal Legacy Operating System**: a preservation domain whose job is to hold a human life accurately enough that people who never met the subject can genuinely come to know them.

It preserves the **substance of a life** — people, relationships, stories, events, places, artifacts, media, voice, documents, sayings, values, lessons, humor, and the small identity-defining details that history forgets — as a single, provenance-first, conflict-preserving **assertion graph**. Every product a family will ever want (memoir, timeline, family tree, museum, documentary, an AI that can speak in the subject's voice) is a **projection** of that graph, generated on demand and thrown away without loss. The graph is the asset. The outputs are disposable.

### 1.2 What Legacy is not

- **Not autobiography software.** A memoir is one output, authored by projection, never the canonical store.
- **Not genealogy software.** A family tree is a projection; ancestry-as-data-entry is not the goal. Legacy cares about *who someone was*, not primarily *who begat whom*.
- **Not document/photo storage.** Files are **evidence carriers**, not the record. A photo with no attested meaning is an unpreserved photo.
- **Not scrapbook or journaling software.** Journaling captures the present as it happens; Legacy reconstructs a life associatively across time, most of it from memory, much of it after the fact, some of it after death.
- **Not a chronology engine.** Human memory is associative, not chronological (§4). Any architecture that forces chronological entry has already failed the subject.

### 1.3 Why Legacy belongs inside WLJ

WLJ's constitution already holds the two things a legacy system most needs and most products lack:

1. **A Canonical Truth discipline** — deterministic retrieval, provenance, freshness, confidence, and stability, expressed once and consumed everywhere (`expose, don't rebuild`). Legacy is the highest-stakes possible application of that discipline: the truth of a person, meant to outlive them.
2. **A Chief of Staff (Beth)** — an assistant that already reasons over composed, deterministic state rather than raw signals. Legacy needs exactly one new thing from an assistant that no other product has built well: **elicitation** — the ability to ask the question that unlocks the memory. WLJ already has the substrate to make that assistant grounded and safe.

Legacy is also the domain that gives WLJ a reason to exist beyond a single lifetime. Every other domain (Health, Faith, Finance, Productivity) serves the *living operator*. Legacy serves the operator's *descendants*. It is the only WLJ domain whose primary user may not be born yet.

### 1.4 How Legacy differs from every existing legacy or memoir product

Existing products optimize for **capture-and-store** or **author-and-publish**. Legacy optimizes for **attest-corroborate-preserve-project**. Concretely, four differences no competitor holds together:

1. **Truth is testimonial, not authored.** The canonical layer records *who claimed what, when, how, and with what corroboration* — never a single settled narrative. Conflicting memories are preserved as data, not resolved away (§2).
2. **Preservation is continuous, not a project.** The record grows for decades and keeps growing after the subject dies, contributed to by many people (§6, §14).
3. **The interview is a first-class engine, not a feature.** The methodology that produced the richest preservation — sensory, relational, meaning-seeking, associative questioning — is architected, not left to a chat prompt (§5).
4. **Significance and loss-risk are computable.** The system knows what matters and what is about to be lost forever, and triages preservation accordingly (§7, §12).

---

## 2. Canonical Truth Model (the load-bearing section)

This is the most important section. Everything else derives from it.

### 2.1 The core reframe: operational truth vs. preservation truth

WLJ's existing Canonical Truth was built for **operational** domains. In an operational domain, truth is **measured, single-valued, freshness-decaying, and conflict-resolved**: your current weight is one number, newer readings supersede older ones, and if two sources disagree you reconcile them.

Legacy is a **preservation** domain, and every one of those properties inverts:

| Property | Operational truth (Health, Finance…) | Preservation truth (Legacy) |
|---|---|---|
| Origin | Measured / sensed / logged | **Attested** (recalled, testified, documented) |
| Cardinality | Single current value | **Many co-existing accounts** |
| Time behaviour | Decays — newer supersedes older | **Does not decay** — 1962 is as true in 2075; the *risk of loss* grows, not staleness |
| Conflict | A bug — resolve to one value | **Data — preserve the disagreement** |
| Absence | Temporary (data will arrive) | Often **permanent and meaningful** (the witness died) |
| Threat model | Wrong / stale data | **Lost data, and fabricated data** |

**Therefore Legacy must not reuse the operational truth structure.** It reuses the *contract* (deterministic retrieval, provenance, confidence, stability, expose-don't-rebuild) but redefines the *nature* of truth. This is the deliberate break from the autobiography/operational model the platform was first built around.

### 2.2 The three layers of Legacy truth

Legacy truth is a strict three-layer stack. Higher layers are composed from lower layers and never overwrite them.

1. **Attestation (evidence).** A single claim, from a single source, at a single moment, about the graph. *"Danny (2026-03-14, voice interview) says: it rained the day we moved into the Redlands house."* An attestation is **immutable and append-only**. It records its source, its medium, its date of capture, the subject's relationship to what is claimed (first-hand / second-hand / inherited-family-lore / inferred), and its native uncertainty ("I think", "I'm sure", "someone once told me"). Attestations are never edited and never deleted — they can only be superseded by *later attestations*, which are themselves preserved. **Evidence is the floor of the system.**

2. **Assertion (canonical truth).** The graph's *held position* about a node, an edge, or a fact, **composed deterministically** from all attestations that bear on it. An assertion carries: its supporting attestations, a **corroboration state**, a **confidence envelope**, and — critically — its **conflict set** (the co-existing incompatible accounts, each with its own provenance). An assertion **never collapses a conflict into one answer.** "Was it raining?" resolves to *"Danny says yes (first-hand); Aunt Carol says it was clear (first-hand); unresolved."* That unresolved disagreement **is** the canonical truth, and it is itself often meaningful. Assertions are what higher layers retrieve.

3. **Projection (output).** Any rendering derived from assertions — a memoir paragraph, a timeline row, an avatar's spoken sentence. **Projections are never canonical and can never feed back into evidence** except through the explicit promotion gate (§2.7). A projection that contradicts its assertions is a bug of the same severity as a Visual Truth Contract violation.

### 2.3 What constitutes evidence

Evidence is anything that can *support or contest* an assertion:

- **Human testimony** (interview answers, written recollections, submitted stories) — the primary and most perishable source.
- **Media** (photo, audio, video, scanned document, letter) — evidence *carriers*; a photo can corroborate "the house was blue" without anyone saying so.
- **Artifacts** (physical objects, with their own attestations about provenance and meaning).
- **External records** (a birth certificate, a newspaper clipping, a gravestone) — high-objectivity evidence for *facts*, silent on *meaning*.

Every piece of evidence carries **provenance** (§2.4). Evidence with no provenance is quarantined, not canonical.

### 2.4 Provenance (first-class, non-negotiable)

Provenance is the spine of preservation truth. Every attestation and every evidence carrier records, at minimum:

- **Source** — who/what produced this claim (a Person node, or an external record).
- **Author relationship** — first-hand, second-hand, inherited lore, reconstructed, or system-inferred.
- **Medium & capture context** — interview / upload / import / posthumous contribution; the device, the date, the session.
- **Native confidence** — the source's own expressed certainty, preserved verbatim in spirit ("I'm certain" vs "maybe").
- **Custody chain** — for artifacts and inherited stories, how it came to the subject and how it came into the system.

Provenance is **immutable**. This is what lets the record remain trustworthy in 2075 when the subject is no longer alive to ask.

### 2.5 Confidence and corroboration

Confidence in Legacy is **composed deterministically** — never narrated into existence by an LLM (this mirrors the platform's F8 rule and Law 2). But its inputs differ from operational confidence. Legacy confidence composes from:

- **Author relationship** (first-hand > second-hand > inherited > inferred),
- **Corroboration** (independent attestations that agree — the single biggest confidence multiplier),
- **Evidence class** (an external record or a photograph corroborating testimony raises confidence sharply),
- **Source native confidence** (the teller's own certainty),
- **Conflict** (an unresolved contradiction *caps* confidence — it can never read as settled).

The verdict vocabulary is **preservation-shaped**, not currency-shaped. Where operational truth reads `fresh | stale | pending | absent`, a Legacy assertion reads:

`attested` · `corroborated` · `contested` · `single-source` · `inferred` · `unverifiable` · `lost`

Note there is no `stale`. A memory does not go stale. What Legacy tracks *instead* of staleness is **capture recency** (when the record was last enriched) and **preservation risk** (§7, §12) — and those drive the *interview*, not the *truth*.

### 2.6 Conflicting memories, the unknown, and the unknowable

These are three distinct first-class states, and conflating them is a design failure:

- **Conflict** — multiple incompatible attestations exist. Preserved as a conflict set on the assertion. Never auto-resolved. Beth may *surface* a conflict to a human ("Your sister remembers this differently — want to record both?") but the system never silently picks a winner.
- **Unknown** — no attestation exists yet, but one plausibly could. This is a **gap**, and gaps are the raw material of the interview engine (§5). Unknowns are assets, not holes.
- **Unknowable** — no attestation can ever exist (the only witness is dead; the fact is lost). This must be **recordable as a fact in itself** — *"we do not know, and we no longer can."* A system that cannot represent "this is lost" will silently pretend completeness, which is the exact failure the Regret Test (§12) is built to prevent.

`None` (never asked / unknown) and a recorded *absence* (asked, and the answer is "there was nothing") are as distinct here as `None` vs `0` in the Signal Conventions — and must never be interchanged.

### 2.7 Derived content and the promotion gate

The system will generate **candidate** truth: a theme it noticed recurring, a relationship it inferred from co-occurrence, a date it estimated, an AI-drafted narrative. **None of this is canonical.** Derived content lives in a separate candidate layer and can become an attestation **only** by passing an explicit **promotion gate**: a human with authority confirms it, and it is then stored as an attestation *attributed to that human's confirmation of a system suggestion* — never laundered into looking first-hand. This is the Legacy expression of "Beth consumes composed briefings, not raw signals, and outputs never become canonical."

### 2.8 What becomes canonical — summary

Canonical = the **assertion graph**: nodes, edges, and the attestations/provenance/confidence/conflict that back them. Canonical ≠ any file, any narrative, any timeline, any avatar utterance. The test for "is this canonical?" is: *if we deleted it, would we lose truth, or only lose a view of truth?* Only the former is canonical.

---

## 3. Core Object Model

Legacy is **graph-first** (§4). Objects come in four tiers: **nodes**, **edges**, **cross-cutting dimensions**, and **projections**. The prompt's suggested list is deliberately re-sorted here, because several items on it are outputs, not objects.

### 3.1 First-class canonical nodes

- **Person** — the central node. A Person may simultaneously be a *subject* (whose life is preserved), a *contributor* (who attests), and a *referent* (mentioned by others). One human = one Person node, many roles.
- **Place** — a location with meaning, at any granularity (a country, a house, a chair-by-the-window). Places are powerful associative anchors.
- **Event** — a bounded happening in space-time. Events may be fuzzy, approximate, or disputed. *An Event is what happened.*
- **Memory / Story** — a **narrated recollection**. *A Memory is someone's account of what happened.* This is the testimonial unit and it is **distinct from Event**: many Memories can attest one Event, and their divergence is preserved (§2.6). This distinction is the object-model consequence of testimonial truth and is non-optional.
- **Artifact** — a physical object with meaning (a bracelet, a chair, a tool).
- **Media** — a digital/physical carrier of evidence: **Photo, Audio, Video, Document/Letter** are modality subtypes of one Media concept, so preservation, migration, and provenance are handled once.
- **Utterance** — a saying, quote, joke, nickname, catchphrase, blessing. The carrier of *voice and identity in miniature*. First-class because a family saying preserves identity more efficiently than a paragraph of biography.
- **Fragment (Identity Marker)** — a deliberately lightweight node for the small, "insignificant" identity-defining details: a smell, a sound, a habit, a favorite chair, a gesture, a food. First-class specifically so the architecture can honor §11 without forcing these into heavyweight Event/Story structures. Fragments attach to almost anything.

### 3.2 Meaning-layer nodes (attested *or* derived-then-promoted)

- **Value** — what the person stood for.
- **Lesson** — what they learned or taught.
- **Theme** — a recurring pattern across a life.
- **Tradition** — a repeated, meaning-bearing practice.
- **Belief** — a spiritual/worldview commitment (integrates naturally with WLJ Faith).

These are canonical **only** when attested by a human or promoted through the gate (§2.7). A theme the *system* noticed is a candidate until confirmed. This is the sharpest line in the object model: **meaning must be claimed or confirmed, never silently asserted by the machine.**

### 3.3 First-class edges (relationships)

**Relationship is an edge, and edges are as canonical as nodes.** A Legacy edge is **typed, directional, time-bounded, attested, and significance-bearing**. "Danny → *mentored by* → Coach Ellis, 1985–1989, first-hand, high family significance" is a canonical object in its own right. Relationships between *people* are the most important edges, but every connection in §4 is an edge.

### 3.4 Cross-cutting dimensions (attach to nodes *and* edges)

- **Provenance** (§2.4)
- **Confidence / Corroboration** (§2.5)
- **Significance** (§7)
- **Preservation state** — completeness, fragility/loss-risk, capture recency (§7, §12)

### 3.5 Explicitly NOT objects — they are projections (§8)

**Timeline, Family Tree, Memoir, Character Encyclopedia, Photo Archive, Digital Museum, Podcast, Documentary, Children's/Grandchildren's Edition, AI Avatar.** Every one is a *view* over the graph. Placing any of them in the object model is the single most common way this kind of system rots, because the moment a timeline is a stored object, it starts to drift from the assertions it should be derived from. **Chronology is a lens, not a store.**

### 3.6 First-class citizenship — the ranking

If forced to name the true first-class citizens (the ones the whole architecture must protect first): **Person, Memory/Story, and the Relationship edge**, backed by **Attestation + Provenance**. Everything else is in service of connecting those or preserving the evidence for them.

---

## 4. Knowledge Graph Architecture

### 4.1 Why a graph, and why associative

The central discovery is architectural, not cosmetic: **human memory is associative, not chronological.** A photograph unlocks a person; a place unlocks a decade; a joke unlocks five forgotten stories. An architecture that stores a life as a timeline models the *output* and destroys the *access pattern*. Legacy therefore stores a life as a **richly typed, weighted, bidirectional knowledge graph**, and chronology is derived from it — never the reverse.

### 4.2 Everything is a node; every meaning is an edge

People, Places, Events, Stories, Artifacts, Media, Utterances, Fragments, Values, Lessons, Themes, Traditions, Beliefs — all nodes. Their connections — *was-at, depicts, evokes, mentions, happened-during, gifted-by, taught, reminds-of, belongs-to-tradition, expresses-value, took-place-at* — are typed edges. Two properties make the graph work for preservation:

- **Edges are attested and provenanced too.** A connection is a claim ("this photo depicts Grandpa") and carries the same evidence discipline as a fact.
- **Edges carry an associative weight — the "evocation strength."** How strongly does this node bring the other to mind? This weight is *learned from the interview itself* (§5): when recalling the workshop reliably surfaces the grandfather, that edge strengthens. This is what makes recall feel human.

### 4.3 How associative recall works

Recall is **weighted graph traversal from an anchor**, not a query over a table. Given any node (a photo just uploaded, a person just named, a place just mentioned), the graph can surface *what it connects to, ranked by evocation strength and significance*. This powers three things at once: the **interview** ("you mentioned the workshop — who else was there?"), **capture** (a new photo instantly proposes the people/places/events it likely connects to), and **discovery** (the system notices that many strong edges converge on one under-preserved node — a high-value gap).

### 4.4 The graph is self-describing

The ontology (the set of node types, edge types, and dimensions) is **stored with the graph, not only in code.** A steward in 2075 opening an export must be able to learn what the edges *mean* from the data itself. This is a hard requirement of the Fifty-Year Test (§10): the semantics travel with the data.

### 4.5 Layering onto WLJ

The graph is the Legacy domain's Layer-1 canonical store. It **exposes** complete objects through a `describe()`-style contract (§13.3); it does not ask higher layers to reassemble a person from fragments. Beth, outputs, and every future interface read the same exposed objects — `expose, don't rebuild`.

---

## 5. Interview Architecture

The interview *is* the product. The methodology that produced the richest preservation must be architected as an engine, not left to prompt-craft.

### 5.1 Conversation philosophy

Beth-as-interviewer obeys four laws that distinguish it from all "life story" chatbots:

1. **Associative, not chronological.** The engine never defaults to *"what happened next?"* It follows the graph's strongest evocative edges. Chronology is reconstructed later, by projection.
2. **Sensory, relational, and meaning-seeking before factual.** The productive questions were: *What did you smell? Who was there? Why does this matter? Who made you feel important? What changed because of this? What don't we see in this picture? What did this object mean? What did this person leave in you?* These are not decoration — they are the questions that preserve *identity* rather than *chronicle*.
3. **One thread at a time, followed to depth.** A single joke is pursued until the five stories behind it surface, rather than marching through a questionnaire.
4. **Comfortable with silence and refusal.** Some memories are painful or private. The engine records *"the subject chose not to answer"* as a first-class, respected state — never nags, never treats a boundary as a gap to be closed.

### 5.2 Discovery strategy — where to point the interview

The engine does not ask randomly. It is driven by a composed **Preservation Briefing** (§9): the ranked set of the most valuable places to dig, computed as

> **Priority ≈ Significance × Loss-Risk × Incompleteness**

(§7, §12). High-significance + high-fragility + low-completeness = the next question. This is the Legacy analog of operational prioritization, and it is what makes the interview *strategic* rather than exhaustive.

### 5.3 Follow-up strategy and memory expansion

Every answer mutates the graph and *regenerates* the next best question. A newly named person becomes a node with its own gaps; a newly mentioned place becomes an anchor; a strengthened edge redirects the thread. The follow-up engine expands memory by **traversing outward from what was just said**, using the sensory/relational/meaning repertoire, until the vein is exhausted — then returns to the briefing for the next high-value anchor.

### 5.4 The Question Repertoire (canonical)

The proven question archetypes are stored as a **canonical, versioned repertoire**, each archetype tagged by *which dimension of which node type it enriches* (sensory→Fragment, presence→Person/Event edge, meaning→Value/Lesson, causal→Event chain, absence→"what don't we see"). This makes the interviewing methodology a **preserved, improvable asset of the platform** — not tribal knowledge in a prompt. Danny's hundreds of conversations become the seed corpus for this repertoire; every future user benefits from it.

### 5.5 Modality-specific interviewing

The engine specializes by anchor type, because the productive questions differ:

- **Photo interviewing** — *who/where/when, why it was kept, what's outside the frame, who took it, what happened right after.*
- **Artifact interviewing** — *provenance, custody, meaning, what it stood for, who it should go to.*
- **People interviewing** — *what they were like, what they left in you, a saying of theirs, a moment that defined them.*
- **Place interviewing** — *sensory anchors first (smell, sound, light), then who and what happened there.*

Each specialization is a strategy over the same graph and the same repertoire — not a separate product.

### 5.6 How Beth differs from traditional interview software

Traditional software runs a fixed questionnaire and stores answers in fields. Beth runs a **graph-aware, significance-driven, associative elicitation loop** whose questions are *generated from what is missing and what matters*, whose follow-ups are *generated from what was just said*, and whose methodology *improves over time and across all users*. It interviews to *fill the most valuable, most fragile gaps first* — not to complete a form.

---

## 6. Capture Architecture — continuous preservation, not data entry

### 6.1 The loop (not a pipeline)

Legacy grows for decades. Capture is a **loop** that never terminates:

```
Evidence arrives (photo / recording / story / artifact / document / posthumous contribution)
      ↓
Provisional node(s) + attestation created, provenance stamped
      ↓
Associative graph proposes likely people / places / events / themes  (candidate edges)
      ↓
Interview triggered on the highest-value gaps the new evidence opened
      ↓
Attestations attached → assertions (re)composed → conflicts preserved
      ↓
Edges confirmed / strengthened; significance & loss-risk (re)scored
      ↓
New gaps surfaced → new interview opportunities queued
      ↺  (returns to the top for the rest of the life, and beyond the life)
```

### 6.2 Capture is many-channel and low-friction

Evidence enters by every channel a life actually leaves it: a photo upload, a voice note, a passing remark to Beth in another domain, a scanned box of letters, a relative's submission after a funeral. Every entry point produces the same thing — a provisional, provenanced attestation — so the discipline is uniform regardless of source.

### 6.3 Capture never blocks on completeness

A photo with no story is still captured (as an unpreserved carrier with an open gap), not rejected. Incompleteness is the *normal, permanent* state of a life record and the engine that drives the interview — never an error. This is the deepest difference from data-entry software: **there is no "done."**

### 6.4 The Preservation Insight Engine (PRIE-analog)

Capture events fire into a Legacy post-execution engine analogous to PIE/PRIE/CDCE (§13.4): it detects gaps, over-mentioned-but-under-preserved nodes ("you've referenced your grandfather twelve times and we have no story about him"), rising loss-risk, emerging candidate themes, and corroboration opportunities. Its output is the composed **Preservation Briefing** Beth narrates and interviews from — **never raw signals handed to the LLM** (§9).

---

## 7. Significance Architecture

### 7.1 Verdict: Significance is first-class — but never a scalar

Legacy **requires** a first-class Significance concept that does not exist elsewhere in WLJ. But the naive model (a single 0–1 importance score) is wrong for three reasons, and the architecture must reflect all three:

1. **Significance is perspectival.** A handmade bracelet is emotionally significant to Danny, family-significant to his daughter, historically insignificant to the world. Significance is always *significance-to-someone*, and the same object holds several at once.
2. **Significance is typed.** The prompt's own list is right: **historical, personal, emotional, family, spiritual, future**. These are distinct axes, not points on one scale.
3. **Significance is temporal.** A photo becomes *more* significant the day the person in it dies. A house gains significance when it's sold. Significance is a value that **changes as the graph changes**, and its history is itself worth preserving.

So Significance is modeled as a **first-class, multi-typed, perspectival, time-varying dimension** attached to nodes *and* edges — not a field, and not a single number.

### 7.2 Should Significance be part of Canonical Truth? Yes — with a hard rule

Significance is canonical **when it is attested** ("this bracelet mattered because my daughter made it") and **candidate** when the system merely infers it (frequent mention, dense connections, emotional language). The candidate significance may drive *interview prioritization* freely, but it may only become *canonical significance* through the promotion gate (§2.7). The system may **act on** inferred significance (to decide what to ask) long before it may **assert** it.

### 7.3 What Significance is *for*

Significance is the Legacy domain's prioritization currency. Combined with **Loss-Risk** and **Incompleteness**, it produces the preservation priority that drives the interview (§5.2) and the Regret defense (§12):

> **Preservation Priority ≈ Significance × Loss-Risk × Incompleteness**

This is why Significance must be first-class: without it, the system cannot know what to protect first, and a life is finite in the time available to preserve it.

---

## 8. Output Architecture

### 8.1 The one rule

**Every output is a projection of the graph at a moment in time. No output is ever canonical. No output ever feeds back into evidence except through the promotion gate (§2.7).** Delete every output and lose nothing but views; delete the graph and lose the person.

### 8.2 Two projection classes

- **Deterministic projections** — timeline, family tree, photo archive, character encyclopedia, museum. These are *reproducible*: same graph state → same structure (this is Law 5 / Stability applied to Legacy). They render facts, and they must render **provenance, confidence, and conflict** honestly — a contested memory is shown as contested, a single-source claim is marked as such.
- **Generative projections** — memoir prose, podcast, documentary narration, children's/grandchildren's editions, and the AI avatar. These use an LLM to *narrate over assertions*, exactly as Beth narrates over composed state elsewhere in WLJ. They are bound by three inviolable constraints:
  1. **Grounding** — every generative claim traces to attestations; nothing is invented.
  2. **Honesty of uncertainty** — contested and low-confidence facts are never presented as settled; the unknowable is never smoothed over.
  3. **Attribution** — generated narrative is always marked as generated and never re-enters the evidence floor.

### 8.3 The AI avatar — the highest-stakes projection

An AI that speaks in the subject's voice (potentially after death) is the most dangerous output and gets its own hard limits: it may speak **only** from attested truth, **must** mark confidence and refuse when unattested ("I don't have a memory of that"), **must never fabricate** a memory or an opinion the subject never expressed, and is governed by the consent and custodianship rules of §14. An avatar that invents is not a feature bug — it is a violation of the person. The architecture treats "the avatar made something up" with the same severity the platform treats a Canonical Truth breach.

### 8.4 Audience-shaped projections

The same graph renders differently for a five-year-old grandchild, an adult child, and a historian. Audience is a **parameter of projection**, never a fork of the truth. There is one record and many readings.

---

## 9. Beth Integration

### 9.1 Beth becomes a preservation partner

In operational domains Beth reasons over current state. In Legacy, Beth gains a new posture: **elicitation and stewardship**. She notices, connects, remembers what's missing, and asks the question that unlocks the memory:

- *"You've mentioned your grandfather twelve times but never told me a story about him."*
- *"This photo you just added — is that the same lake house you talked about last spring?"*
- *"Your sister remembers the move differently. Want me to keep both?"*
- *"You've never told me what your mother's laugh sounded like."*

### 9.2 One brain, composed — never raw signals

Legacy obeys the platform's constitutional principle **P18 — Beth consumes composed briefings, not raw signals.** The Preservation Insight Engine (§6.4) composes a deterministic **Preservation Briefing** — the ranked gaps, the promising associative threads, the rising loss-risks, the corroboration opportunities, each with its verdict already inside — and Beth *narrates and interviews over that*. Beth never traverses the raw graph to reason, exactly as she never reasons over raw PIE/PRIE/CDCE signals elsewhere. Proactive Beth and conversational Beth share the one composed brain, as they already do via `build_cos_intelligence()`.

### 9.3 Beth answers Legacy questions through the Answer Precondition Pipeline

"What was my grandfather like?" runs the same pipeline as any personal question (§13.5): intent → scope → freshness(=capture recency) → completeness → confidence → strategy → retrieve → stability → reason → narrate. The Legacy-specific twist: **confidence composition surfaces conflict rather than hiding it**, and the honest partial answer ("I have three stories about him, all from you; your sister could add more") is a first-class, correct answer — never fabricated completeness.

### 9.4 Cross-domain: Legacy enriches the rest of WLJ

Because Legacy is a WLJ domain, Beth can connect it to the living operator: a Faith belief attested in Legacy informs Faith; a value the operator says they want to pass on becomes a lens on present decisions. Legacy exposes its assertions to the CoS standing read like any domain — it is not a walled garden.

---

## 10. Fifty-Year Architecture Test

Assume WLJ, this company, today's file formats, and today's AI paradigm are all gone by 2075. Does the architecture survive? It must pass six tests, and each maps to a requirement already stated above.

1. **Substrate independence.** Canonical truth is a semantic graph + provenance, not rows in a product's database and not any vendor's AI. Storage, format, and model can all be replaced beneath it. *(→ §2, §4.4)*
2. **Self-describing semantics.** The ontology travels with the data, so a future steward can interpret the edges without today's source code. *(→ §4.4)*
3. **Format migration is assumed, not feared.** Media are evidence *carriers* with preservation-grade metadata; formats will be migrated across decades, and the *meaning* (attestations, edges) is independent of the *carrier* (the JPEG, the MP3). *(→ §3.1 Media, §6)*
4. **Export is a right, not a feature.** The entire graph + evidence + provenance is exportable in open, documented form at any time. Legacy is designed to **outlive the platform** — portability is constitutional, not a checkbox. *(→ §14)*
5. **Trust without the subject.** Because provenance and corroboration are first-class and immutable, the record stays trustworthy after the primary source is dead and can no longer be asked. This is the whole point. *(→ §2.4, §2.5)*
6. **Additive to technologies we can't imagine.** New node types, edge types, significance types, output types, and capture modalities attach without redesign (open dimension set, registry-by-key). A 2075 capture device or a 2075 output format is a new adapter, not a new architecture. *(→ §13, and WLJ's "deferred = phased, additive-compatible" principle.)*

If any test failed, the fix would be to push more of the meaning *out of the code and into the self-describing graph*. The architecture is designed so that has already happened.

---

## 11. Preserving the "insignificant" (the identity layer)

The recurring discovery: the small things preserved identity more than the big ones — a family saying, the smell of eucalyptus, a favorite restaurant, a tree in the front yard, a coach's favorite phrase, a handmade bracelet, a childhood nickname, a favorite chair, a laugh, a tradition.

The architecture honors this deliberately, without drowning:

- **The Fragment node (§3.1)** exists precisely for these — deliberately lightweight so a smell or a saying costs almost nothing to preserve and attaches anywhere.
- **The Utterance node (§3.1)** captures sayings, nicknames, and jokes as first-class carriers of voice.
- **The sensory/relational Question Repertoire (§5.4)** actively *elicits* these — the "insignificant" details are captured because Beth asks for them, not because a user thinks to volunteer them.
- **Significance handles the flood (§7).** Fragments are cheap to store and are *ranked, not gated* — the system keeps everything small but *surfaces* only what significance and connectivity make meaningful. The architecture does not decide a detail is worthless; it decides how prominently to render it. Nothing identity-bearing is discarded; the graph simply weights what matters.

The design stance: **capture liberally, rank ruthlessly, discard almost nothing.** Storage of a saying is trivial; the regret of having lost a mother's laugh is not.

---

## 12. The Regret Test (answered before concluding)

> *If this system became the only surviving record of a person's life one hundred years from now, what would future generations regret that we failed to preserve?*

The honest answer — and it drove several decisions above:

1. **Voice, laugh, and manner** — *how* they said things, not just what. → drove first-class **Media(Audio/Video)** as evidence and the **avatar's** grounding-in-real-voice constraint (§3.1, §8.3).
2. **The small identity details** — the sayings, smells, habits, the favorite chair. → drove the **Fragment** and **Utterance** nodes and the sensory repertoire (§3.1, §5.4, §11).
3. **The *why* and the meaning**, not just the facts — what things meant, what a person left in you. → drove the **meaning-layer nodes** and the meaning-seeking questions (§3.2, §5.1).
4. **The disagreements and the ambiguity** — a flattened, tidied, single-narrative life is a *lie of omission*. → drove **conflict-preserving assertions** and the refusal to auto-resolve (§2.2, §2.6).
5. **What was lost, marked as lost** — a record that silently pretends completeness robs descendants of knowing what to grieve or seek. → drove the **unknowable-as-first-class-state** rule (§2.6).
6. **The perishable testimony of others** — the elderly relative who is the only witness. → drove **Loss-Risk** as a first-class, computable dimension and the triage that interviews the most fragile sources first (§7, §5.2).
7. **The record itself, lost to platform death or format rot.** → drove the **Fifty-Year Test**: substrate independence, self-describing semantics, and export-as-a-right (§10).

The critique those answers forced back into the design: an earlier draft treated significance as a single score and had no concept of loss-risk. Both were fixed above, because *the regret is not "we recorded the wrong thing" — it is "we ran out of time to record the fragile, meaningful thing, and never even knew it was slipping away."* The architecture's central job is to make that fragility **visible and actionable while the sources are still alive.**

---

## 13. Integration with the WLJ Platform

Legacy must plug into the existing platform, not compete with it. It reuses every platform *contract* and introduces exactly one new domain *class*.

### 13.1 A new Domain Class: `PRESERVATION`

The existing classes — `BEHAVIORAL`, `INFLUENCE`, `KNOWLEDGE`, `CONTEXT`, `SYSTEM` — do not fit. Legacy is not a daily-signal life domain (`BEHAVIORAL`), not a cross-domain ingestion source (`INFLUENCE`), and is richer than a structured knowledge store (`KNOWLEDGE`). Legacy is **preservation**: append-only, testimonial, conflict-preserving, loss-aware, multi-contributor, and designed to outlive its owner. This warrants a new `DomainClass.PRESERVATION`, added additively per the registry-by-key philosophy. `PRESERVATION` participates in CoS (Beth) but is **exempt from operational-signal expectations** (no daily 0–1 normalized signals, no freshness-as-decay).

### 13.2 Domain Registry

Legacy registers a `DomainCapability` like every domain — canonical `name` (`legacy`), `display_name`, `domain_class=PRESERVATION`, its `primary` node types, its Beth `intent_types` (largely elicitation/retrieval/output rather than operational actions), its `context_builders` (the Preservation Briefing), and `related_domains` (Faith, Journal, Capture). It is auto-discovered at startup like any other. No special-casing.

### 13.3 Layer 1 conformance — reuse the contract, redefine the dimensions

Legacy conforms to the **Entity Completeness Law** ("*a canonical entity is complete when it can completely answer the natural business questions about itself from a single deterministic retrieval*") via a `describe()`-style Domain Truth facade. But it **redefines the canonical dimensions**, as the OPEN dimension-set rule explicitly permits. The operational six (Identity, Definition, Status, Plan, Standing, Performance) do not fit a life record. Legacy's dimensions for, e.g., a **Person** are:

- **Identity** — who they are.
- **Provenance** — how we know anything about them.
- **Account** — the attested memories, stories, utterances, and fragments (with conflict preserved).
- **Relationships** — the typed edges to other people/places/events.
- **Significance** — perspectival, typed, time-varying.
- **Preservation state** — completeness, loss-risk, capture recency.

This is the deliberate, contract-honoring redesign the platform's own OPEN-dimension rule anticipates: Legacy is the first `PRESERVATION`-class domain, and it contributes the first preservation-shaped dimension set. If these prove universal across future preservation entities, they are promoted to named dimensions per the standard process.

### 13.4 Intelligence engine analogs

Legacy participates in the three-phase pipeline (Interpretation → Execution → Post-Execution) with preservation-shaped analogs:

- **SUE/SLCME/HTIE** (interpretation) are reused directly — semantic understanding, context memory, and temporal reasoning matter as much for "the summer we moved" as for "yesterday."
- **UAIO** remains the single execution authority for any Legacy action (capture, promotion, output generation).
- A **Preservation Insight Engine** (post-execution, PIE/PRIE/CDCE-analog) detects gaps, loss-risk, over-referenced-under-preserved nodes, candidate themes, and corroboration opportunities — composing the **Preservation Briefing**. It **feeds the composer, not Beth directly** (P18).
- Outputs flow through the **E3 (Evidence & Explainability)** discipline: every projection can show its provenance. This is not new work — it is Legacy's most natural use of an engine that already exists.

### 13.5 The Laws (0–5), read for preservation

- **Law 0 — Intent before retrieval.** "What was Grandpa like?" scopes to the Legacy graph and the relevant Person, not the whole life.
- **Law 1 — Freshness before reasoning**, reinterpreted: *capture recency*, not decay. The verdict vocabulary is preservation-shaped (§2.5). "Stale" does not exist; "at-risk" and "single-source" do.
- **Law 2 — Confidence before conversation.** Composed deterministically from author-relationship + corroboration + evidence class; conflict caps it; the honest partial answer is first-class.
- **Law 3 — Orchestration before reasoning.** "Write my mother's memoir" is a workflow (retrieve assertions → order by projection → narrate per audience), never one giant prompt.
- **Law 4 — Deterministic retrieval never falls back to AI failure.** A photo archive or a family tree is deterministic; if retrieval fails, report the failure — never answer a factual life-question with "assistant unavailable."
- **Law 5 — Stable truth.** A life must not drift. The same graph state renders the same *facts* every time; conflict stays conflict; corrected memory changes truth *only* when a new attestation arrives. **This is the moral core of a legacy system: the dead cannot correct the record, so the record must not silently change.**
- **The unifying rule holds unchanged:** *Questions determine retrieval; retrieval never determines the answer.*

### 13.6 Signals

Legacy does **not** emit operational per-day signals (this would violate the None-vs-0 and freshness semantics of the Signal Taxonomy). It may optionally expose a **standing preservation state** — coverage/completeness of the record and aggregate loss-risk exposure — to the CoS standing read, so Beth can proactively steward ("three of the people you care most about have no recorded stories, and two of your oldest sources are the only witnesses left"). This is a *state*, not a signal, and it is computed in the background per the observability performance law — never on the request path.

---

## 14. Succession & Custodianship (a requirement no operational domain has)

Every other WLJ domain serves a living operator and its data may die or be deleted with them. **Legacy is the opposite: it is designed to outlive its subject and to keep growing after death.** This forces first-class concepts nothing else in WLJ needs:

- **Subject lifecycle.** A Person-subject transitions from *living author* (attests their own life) to *subject-of-record* (others attest on their behalf). The architecture must handle this transition without corrupting provenance — posthumous attestations are marked as such, never laundered into first-hand.
- **Multi-contributor authorship.** A life is co-authored — the subject, their siblings, their children, their grandchildren. Every attestation carries its author; the graph is a **shared, multi-contributor record**, not a single-author document.
- **Custodianship & succession.** Ownership must transfer across generations. Who inherits the record, who may add to it, who may generate outputs (especially the avatar), and who may *see* what — governed by explicit, inheritable custodianship rules.
- **Consent across time.** The subject's consent (what may be shared, what stays private, what the avatar may say) must be recorded *while they are alive* and *respected after they are gone*. Consent is canonical and immutable.
- **Portability as inheritance.** Export-as-a-right (§10) is also succession: a family must be able to take the whole record with them, independent of the platform's survival.

This section exists because the Regret Test's deepest answer is not about any single memory — it is about **the record itself surviving the person and the platform, in the right hands, with the subject's wishes intact.**

---

## 15. Change Control & Phasing

This document is the constitution; it changes rarely and deliberately.

- **Additive-compatible always.** Per WLJ's "deferred = phased, not maybe" principle, v1 implementation must not foreclose any concept here. New node/edge/significance/output/capture types attach by key without redesign.
- **The truth model is immutable in spirit.** Attestation → Assertion → Projection, provenance-first, conflict-preserving, outputs-never-canonical: these cannot be "optimized away" in a sprint. Any proposal that lets an output become canonical, silently resolves a conflict, or lets the LLM source its own truth is rejected at the door.
- **The repertoire and the ontology improve continuously.** The Question Repertoire (§5.4) and the self-describing ontology (§4.4) are *meant* to grow — that is versioned evolution, not constitutional change.
- **Phasing** (indicative, non-binding on this baseline): (1) graph + attestation/provenance core and manual capture; (2) associative interview engine + repertoire seeded from existing conversations; (3) significance + loss-risk triage; (4) deterministic projections; (5) generative projections under E3 grounding; (6) succession, multi-contributor, and avatar under full consent governance. Each phase is additive over the same graph.

---

## Appendix — Glossary (canonical terms)

- **Attestation** — an immutable, provenanced single claim from a single source; the evidence floor.
- **Assertion** — the graph's deterministically-composed canonical position, carrying confidence, corroboration, and a preserved conflict set.
- **Projection** — any output derived from assertions; never canonical.
- **Provenance** — the immutable record of who claimed what, when, how, and with what relationship to the truth.
- **Corroboration** — independent attestations that agree; the primary confidence multiplier.
- **Conflict set** — the co-existing incompatible accounts preserved on an assertion.
- **Fragment (Identity Marker)** — lightweight node for small identity-defining details (a smell, a saying, a chair).
- **Utterance** — a saying, quote, joke, nickname — voice in miniature.
- **Significance** — first-class, multi-typed, perspectival, time-varying importance dimension.
- **Loss-Risk** — computable fragility: the probability the source or evidence becomes permanently unavailable.
- **Preservation Priority** — Significance × Loss-Risk × Incompleteness; what the interview digs into next.
- **Preservation Briefing** — the composed, deterministic state object Beth narrates and interviews over (never raw signals).
- **Promotion gate** — the explicit, human-authorized path by which derived/candidate content becomes an attributed attestation.
- **Preservation state** — completeness + loss-risk + capture recency of a node.
- **`PRESERVATION`** — the new WLJ Domain Class for append-only, testimonial, loss-aware, multi-contributor, outlive-the-owner domains.

---

*This document is the permanent architectural foundation for the WLJ Legacy Domain. Implementation follows it. It is intended to remain buildable-from for years without redesigning the underlying philosophy — and, if it has done its job, usable by families generations from now.*
