# DRAFT — Three Truth Surfaces & the Personal Truth Profile

> **STATUS: DESIGN DRAFT FOR REVIEW. NOT CANONICAL. NOT FROZEN.**
> This document exists to be reviewed and refined *before* anything is written into the
> canonical contracts. It contains four proposed drafts (Parts A–D). **No code, no
> models, no registries, and no standing-context changes are created by this document.**
> When a part is approved, it is transcribed into the canonical doc named in its banner
> and this draft is retired.
>
> **Grounding (repo truth, not greenfield):** a first slice already ships —
> `apps/ai/cos_services/personal_truth.py` (the composer) + the `get_user_truth` tool.
> It is already a read-only, cross-domain, provenance-bearing projection with per-fact
> `module`+`source`, conflict-surfacing (`_nutrition_target_contradictions`), and one
> composer feeding both standing context and the tool. **This design formalizes what
> shipped and specifies the roadmap (derived/verified facts, the owner registry, the
> surface taxonomy, the additional fact dimensions).** Where this design and the shipped
> code differ, that is a *proposed refinement*, called out as such — not a description of
> current behavior.

---

## Part 0 — Decided vs open (read first)

**Decided in review (Danny, 2026-07-17):**
- Three Truth Surfaces become an explicit governing concept.
- The Personal Truth **Profile** is a deterministic **projection, never a store**.
- Every durable-fact type maps to an authoritative owner; a fact with **no owner may
  stay Derived forever but may never become Verified**.
- Provenance lifecycle: **Explicit / Derived / Verified**; Observed truth carries
  **confidence**; a derived fact **never silently becomes explicit**.
- Additional fact dimensions: identity spine, constraints, confidence, recency,
  sensitivity, and **conflict is surfaced, never reconciled**.
- Standing-context responsibilities are cleanly separated (Current Context / Personal
  Truth Profile / Execution Truth / Mission / AI Relationship).
- **Placement:** taxonomy defined in the Truth/Action Contract, enforced from the
  Architecture Laws, implemented via the Model Interface accessors, PTP as one instance.
  The **enumeration does not go in the Constitution** (keep it extensible); at most the
  single "one-question-per-surface, projection-only" invariant is elevated later, via a
  Constitutional Review, once proven.

**Open questions for this review (collected in Part E):** the owner for "favorite/
avoided foods"; the PTP↔Mission line for targets; whether Forward Truth / Relational
Truth become 4th/5th surfaces; sensitivity surface-gating policy; and the derived-fact
recompute cadence.

---

# PART A — PROPOSED DRAFT for `WLJ_LLM_TRUTH_ACTION_CONTRACT.md` §3 (The Truth Boundary)

> Insert as a new subsection (e.g. **§3.8 The Three Truth Surfaces**), after §3.2
> (the truth-tool envelope) and referencing it. Not yet transcribed.

## §3.8 The Three Truth Surfaces

WLJ exposes truth to the model through truth tools (§3.2). Those tools are not
interchangeable: they answer three fundamentally different **question-shapes**, and a
tool answers **exactly one**. Naming the three prevents the drift where a record-level
lookup is answered with domain aggregates, or a momentary status is mistaken for a
standing fact (incident class: the truth-accessibility gap, 2026-07-17).

| Surface | Question-shape | Returns | Example callers |
|---|---|---|---|
| **Entity Truth** | *"What happened?"* | one **episodic record** | a meal, a workout, a journal entry, a glucose reading, a transaction |
| **Domain State** | *"Where does this domain stand right now?"* | current **momentary** deterministic state of one domain | nutrition status, health status, financial status, execution status |
| **Personal Truth Profile** | *"Who is this person?"* | **durable standing facts** | conditions, targets, constraints, preferences, standing routines |

**The three rules that make this a contract, not a diagram:**

1. **One question-shape per surface.** A truth tool answers exactly one of the three. A
   tool that blends them (a "status" that also returns records, a "profile" that returns
   today's plan) is a defect, not a convenience.
2. **Classify the accessor by the question it answers, never by where the data lives.**
   The same underlying dataset may surface through more than one accessor. A workout
   schedule is the tie-break example: the standing *definition* ("trains 5×/week,
   mornings") is **Personal Truth Profile**; current *adherence* is **Domain State**;
   today's *session* is **Entity/Execution**. One dataset, three accessors, three
   question-shapes.
3. **Surface-type is orthogonal to delivery-mode.** *Which surface* a truth belongs to
   is independent of *how it reaches the model*: pulled on demand via a truth tool, or
   pushed every turn in the executive-context envelope (§3.6). Entity Truth is pulled;
   the Personal Truth Profile is pushed standing; Domain State is both. Do not conflate
   "surface" with "delivered-standing."

**Envelope.** All three return the standard truth-tool envelope (§3.2): value(s) +
source + freshness + confidence + provenance. Nothing here introduces a parallel
envelope.

**The set is open.** Three surfaces are the current, load-bearing set. Candidates for a
future surface (e.g. **Forward Truth** — "what is likely / where are we headed", from
deterministic predictions and Mission trajectory; **Relational Truth** — "who relates to
whom", the Person graph) are why the enumeration is defined here and in the Laws, and
**not** frozen in the Constitution: a new surface must be addable by contract, not by
amendment. A new surface is legitimate only if it answers a genuinely new question-shape
and obeys rules 1–3.

---

# PART B — PROPOSED DRAFT for `WLJ_ARCHITECTURE_LAWS.md` (Amendment B)

> The Laws own the Answer Precondition Pipeline; step 6 is RETRIEVE. The Laws govern
> *how* you retrieve but do not yet classify *what* is retrievable. Amendment B fills
> that slot and is the **enforcement anchor** for Part A. Not yet transcribed.

## Amendment B (proposed) — The Retrieval Surface Classification

**Every retrieval targets exactly one of the three Truth Surfaces (Entity Truth /
Domain State / Personal Truth Profile), and a surface answers exactly one
question-shape.** Retrieval that cannot name its surface, or a surface that answers more
than one question-shape, is a Law-0 violation (answering a different question than was
asked) surfacing at the retrieval layer.

- **Companion to Law 0 (Intent Before Retrieval).** Law 0 fixes *which domains*;
  Amendment B fixes *which surface within them*. Intent selects the question-shape; the
  question-shape selects the surface. "Questions determine retrieval" now includes
  "questions determine the surface."
- **Companion to Law 3 (Orchestration/Strategy).** The STRATEGY step chooses retrieval
  vs enumeration+enrichment vs reasoning; Amendment B constrains the retrieval option to
  a single declared surface.
- **Enforcement (proposed, specified in Part D, built later):** truth accessors declare
  their surface-type; a contract test rejects an accessor that declares more than one
  surface-type or (for a `durable_profile` accessor) owns a writable model. The Laws
  state the rule; the test makes blending fail CI. *(This describes a proposed test; it
  is not created by this draft.)*

---

# PART C — PROPOSED DRAFT: Model Interface additions

> Destined for `WLJ_MODEL_INTERFACE_DESIGN.md`. It already names `get_entity` and
> `get_domain_state`; this formalizes the trio and adds `get_durable_facts`. **Interface
> contract only — conceptual shapes, no code, no implementation.**

The three surfaces are reached through three accessor families. Each returns the §3.2
envelope. Signatures below are **conceptual** (illustrative shape, not code):

### C.1 `get_entity` — Entity Truth (exists)
- **Question:** "What happened? / show me this record."
- **Shape:** `get_entity(user, domain, entity_type, selector) → { record, envelope }`
- **Returns:** one episodic record (or a bounded, explicitly-scoped set), record-level.
- **Backed by:** the DomainTruth `get_entity` surfaces already shipped (journal entry,
  nutrition food, workout, …). Registry: DomainTruth.
- **Delivery:** pulled on demand.

### C.2 `get_domain_state` — Domain State (exists)
- **Question:** "Where does this domain stand right now?"
- **Shape:** `get_domain_state(user, domain) → { current_state, envelope }`
- **Returns:** current momentary deterministic state of one domain (facts, not verdicts).
- **Backed by:** the SAE state builders (`build_health_state`, `build_relationships_
  state`, execution state, …). Registry: the domain-state registry — **already a
  separate registry from `get_entity`** (this is the distinction the taxonomy makes
  permanent).
- **Delivery:** pulled on demand and/or summarized into the envelope.

### C.3 `get_durable_facts` — Personal Truth Profile (proposed; new)
- **Question:** "Who is this person? (standing facts, this domain's contribution)"
- **Shape:** `get_durable_facts(user, domain) → { facts: [DurableFact], envelope }`
  where a **DurableFact** carries (conceptually): `key`, `value`, `unit?`,
  `owner_module`, `source_accessor`, `provenance ∈ {explicit, derived, verified}`,
  `confidence?` (for derived), `as_of` / `valid_until?`, `sensitivity`, and — where
  present — a surfaced `conflict`.
- **Returns:** the durable, decision-relevant facts a domain owns, as a bounded,
  curated set (not analytics).
- **Backed by (proposed refinement):** each domain exposes its own `get_durable_facts`;
  the **Personal Truth Profile composer** (`personal_truth.py`, shipped) aggregates them.
  *Today the composer reads module surfaces directly; the refinement is to formalize a
  per-domain `get_durable_facts` provider so the composer never re-derives.* One source
  feeds both the domain's own use and the Profile (no second producer).
- **Delivery:** composed once per turn into the executive-context envelope (background-
  computed, request-path-safe) **and** available via the `get_user_truth` tool.

**Invariant across all three:** an accessor declares exactly one surface-type; a
`get_durable_facts` provider has **no writable model** (projection only).

---

# PART D — PROPOSED OUTLINE: `WLJ_PERSONAL_TRUTH_PROFILE.md`

> Outline only — section headers + intent. To be expanded into the full contract after
> this review. **No models/registries created here; the registry below is described, not
> built.**

**§0. First sentence (non-negotiable).** "The Personal Truth Profile is a deterministic
**projection**, not a storage model. It owns nothing, stores no authority, and has no
writable model of its own." Everything else is subordinate to this line.

**§1. What it is / is not.** Is: deterministic, cross-domain, read-only, composed,
provenance-bearing, delivered standing + via `get_user_truth`. Is not: a store, a second
authority, a DomainTruth/entity/history replacement, an LLM profile, a
reasoning/recommendation engine, a key-value dumping ground. *(Both lists exist in the
shipped module docstring — promote them to the contract.)*

**§2. Place in the Three Truth Surfaces.** The "who is this person?" surface; sibling to
Entity Truth and Domain State (Part A). Answers one question-shape; classified by the
question, not the data's origin.

**§3. The fact model (DurableFact).** Fields and their meaning:
- `key`, `value`, `unit?`, `owner_module`, `source_accessor`.
- **`provenance ∈ {explicit, derived, verified}`** — see §4.
- **`confidence`** — required for `derived` (e.g. "Premier Protein 45g · 52 occurrences ·
  high"); lets the model reason without inventing certainty.
- **`as_of` / `valid_until?`** — durable ≠ permanent; §6.
- **`sensitivity`** — §7.
- **`conflict?`** — §5.

**§4. The Explicit / Derived / Verified lifecycle.**
- **Explicit** — the owner holds a user-supplied fact. *(Shipped: Slice 1.)*
- **Derived** — no owner-stored standing fact; the Profile computed it deterministically
  from episodic records (no LLM). *(Roadmap: derived slice.)*
- **Verified** — the owner holds a fact whose provenance says *confirmed-from-derived*.
- **The three states are COMPUTED from the owners' data — never stored in the Profile.**
- **Hard invariant:** a Derived fact becomes Verified **only** through an explicit user
  confirmation event that **writes to the owner**; it never becomes Explicit implicitly.
  This boundary is trust-critical and is enforced by a contract test.
- **Consequence for owners:** owners need a "confirmed-from-derived" provenance marker.
  *(Cross-cutting requirement to flag.)*

**§5. The Owner Registry (described, not built).** Every durable-fact **type** maps:
`fact-type → authoritative owner → read accessor → confirmation write-path`. Rule: a
fact-type with **no owner may remain Derived forever but may never be Verified** (no
place to write ⇒ no verification ⇒ no temptation to store it in the Profile). *This
registry is the structural guarantee behind §0; this document specifies its shape only.*

**§6. Confidence, recency & validity.** Derived facts carry confidence + support count;
all facts carry `as_of`; facts may carry `valid_until` and a re-derivation cadence.
Stale derived facts decay or re-derive; they are never asserted as current.

**§7. Conflict — surfaced, never reconciled.** When Explicit and Derived (or two owners)
disagree on the same fact, the Profile presents **both**, tagged, and does not explain or
choose. Reasoning belongs to the model; facts belong to WLJ. *(Shipped precedent:
`_nutrition_target_contradictions` — generalize it.)*

**§8. Sensitivity & surface-gating.** Each fact carries a sensitivity tier; sensitive
facts (medical, mental-health, reproductive — note the existing *blocked* reproductive
boundary) obey a surface policy so they are not narrated in inappropriate contexts.

**§9. Categories (curated, bounded).**
- **Identity spine** — canonical `people.Person` self-anchor (name, pronouns, DOB/age,
  timezone/locale) + at-a-glance unique relationships (spouse, children). *(Depends on
  the Person-consolidation landing; currently absent from Slice 1.)*
- **Constraints / hard limits** — allergies, contraindications, dietary/religious
  restrictions, accessibility needs, safety-critical facts (high salience).
- **Targets** — nutrition/health/goal targets *(shipped)*.
- **Conditions & medications** — *(shipped)*.
- **Preferences & avoidances** — favorite/avoided foods, coaching content preferences
  (recommendation-shaping, **not** persona — that's AI Relationship).
- **Standing routines** — the durable *definition* (not today's session).
- **Declared priorities & relationship preferences** — *(shipped: priorities,
  relationship)*.

**§10. Boundaries (draw them here or they blur in code).**
- **vs AI Relationship** — content vs voice. The Profile is the facts the model reasons
  *from*; AI Relationship is the stance it reasons *with*. Coaching prefs that shape
  *recommendations* are Profile; those that shape *tone/persona* are AI Relationship.
- **vs Mission** — facts vs progress. Mission owns active goals + trajectory; the Profile
  may hold a target *value* but never progress.
- **vs Domain State** — standing vs momentary (the workout-schedule tie-break, Part A).
- **vs Entity Truth** — distillation vs the event stream.

**§11. Request-path safety.** Cross-domain aggregation is **background-computed +
cached**; the request path reads a pre-computed snapshot and returns `pending` if absent
— never a live fallback (per `WLJ_REQUEST_PATH_SAFETY.md`).

**§12. Invariants & contract tests (specified, not built).**
- No writable model (projection-only) — CI test.
- Each provider declares exactly one surface-type (`durable_profile`).
- Derived→Verified only via explicit confirmation writing to the owner — CI test.
- Ownerless fact-types cannot be Verified — CI test.
- No LLM import in the composer — CI test.
- One composer feeds standing context and `get_user_truth` — no duplicate retrieval.

**§13. Standing-context placement.** Delivered every turn beside AI Relationship and
Mission (the standing cluster), distinct from Current Context and Execution Truth (the
momentary cluster). *(Shipped: already in standing context + tool.)*

**§14. Phasing.**
- **Slice 1 — Explicit durable facts.** *Shipped* (`personal_truth.py` + `get_user_truth`).
- **Slice 2 — Derived facts + confidence** (deterministic aggregation only).
- **Slice 3 — Verified lifecycle** (confirm-to-owner + owner provenance marker + registry).
- **Slice 4 — Identity spine** (gated on Person-consolidation).
- **Cross-cutting — sensitivity gating, recency/validity, the surface registry + tests.**

**§15. Governance.** This contract defines the Profile; the Three Truth Surfaces are
defined in the Truth/Action Contract (Part A) and enforced from the Laws (Part B). The
Constitution is not amended by this contract; elevation of the single
"one-question-per-surface, projection-only" invariant to an Article is a separate,
later, explicit Constitutional Review.

---

# PART E — Open questions for this review

1. **Ownerless facts.** "Favorite/avoided foods" has no obvious authoritative owner
   today. Options: (a) stays permanently Derived (never Verified); (b) create a small
   `FoodPreference` owner in the meals/nutrition domain; (c) fold into an existing
   preferences store. Which?
2. **PTP ↔ Mission for targets.** Does a target *value* live in the Profile, in Mission,
   or is it referenced from Mission? (Avoid two owners.)
3. **A 4th/5th surface?** Do **Forward Truth** (predictions/trajectory) and **Relational
   Truth** (the Person graph) become surfaces, or fold into Domain State / the identity
   spine? (Decides how open we make the taxonomy's wording now.)
4. **Sensitivity surface-gating policy.** What is the default narration policy for
   sensitive facts, and who sets a fact's tier — the owning module?
5. **Derived recompute cadence.** Background frequency + invalidation triggers for
   derived facts (tie to existing intelligence cycles rather than a new scheduler?).
6. **AI Relationship as an owner.** The review listed "relationship preference → AI
   Relationship" as an owner. Is AI Relationship a genuine authoritative *store*, or does
   a preferences store own it and AI Relationship consume it? (One-authority check.)

---

*End of draft. Nothing here is canonical until transcribed into the named docs after
review. This file creates no code, models, registries, or standing-context changes.*
