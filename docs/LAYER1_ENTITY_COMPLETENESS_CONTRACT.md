# Layer 1 — Entity Completeness (Architectural Law)

## The Law (permanent, business-first, implementation-independent)

> **A canonical entity is complete when it can completely answer the natural business
> questions about itself from a single deterministic retrieval.**

This is the law. It does not name dimensions, fields, or types. It is a statement about a
**business capability**: ask a natural question about the entity, and Layer 1 can answer
it — fully, deterministically, in one retrieval — without the caller assembling fragments.

Supporting principles (Layer 1 constitution):
- Layer 1 owns business truth and exposes **complete business objects**.
- Higher layers **retrieve** a complete object; they never assemble fragmented truth from
  multiple Layer 1 calls.
- Truth is **deterministic** and carries its trust properties (Freshness, Confidence).

The law is what must never change. *How* an entity satisfies it may evolve.

---

## The current canonical implementation of the law

Today, an entity satisfies the law by describing itself across **six business
dimensions**. These dimensions are **not the law** — they are the present-day, canonical
way we guarantee an entity can answer its natural questions. New universal dimensions may
be added in future without changing the law or the architecture.

| Dimension | The natural business question it answers |
|---|---|
| **Identity** | What is it? |
| **Definition** | What specifies it? |
| **Status** | What lifecycle state is it in? |
| **Plan** | What is *supposed* to happen? |
| **Standing** | What is happening *now*, relative to the plan? |
| **Performance** | How has it gone over time? |

…each carried with **Freshness** and **Confidence**. The dimension set is **open**: a
domain may attach additional dimensions (an entity's `extensions`) when a natural question
isn't covered by the canonical six; a dimension that proves universal is later promoted to
a named dimension. Adding a dimension evolves the implementation — it does not change the
law.

### The dimensions across canonical entities

| Entity | Identity | Definition | Status | Plan | Standing | Performance |
|---|---|---|---|---|---|---|
| **Medication** | name | dose, category, purpose | active/discontinued | schedule | taken today | 7/30/90-day adherence |
| **Goal** | title | target, metric, why | active/achieved/abandoned | deadline + target | progress to date | pace, % to target, trend |
| **Task** | title | description, priority | todo/done/overdue | due date | done? overdue? | completion streak |
| **Calendar Event** | title | time, location, attendees | upcoming/past/cancelled | start/end | happening today? | attendance history |
| **Relationship** | person | role, desired cadence | active/lapsed | contact cadence | last contact / due | contact-frequency trend |
| **Journal / Habit** | date/name | prompt, cadence | logged/active/paused | intended cadence | done today? | streak, rate |
| **Workout** | type | planned exercises | planned/completed | sets/reps | done today? | weekly volume, PRs |

---

## Implementation (reviewed — kept, as the best current expression of the law)

- **`CompleteEntity`** (`apps/core/truth/entity.py`) — the current canonical implementation
  of the law. Its named fields are the six dimensions; an open `extensions` map carries any
  further dimensions a domain introduces. The contract is visible in the type, yet the
  dimension set is not closed.
- **`DomainTruth.describe(entity_type) → list[CompleteEntity]`** — the single deterministic
  retrieval. The verb is the business operation ("the entity describes itself"); the return
  satisfies the law.
- A domain composes any aggregate (e.g. overall adherence) **inside Layer 1**, so the higher
  layer still makes one call. **Medication is the reference implementation.**

This is reviewed and kept: it satisfies the law (one deterministic retrieval, complete
object), makes the *current* dimensions visible in the type, and stays open to new
dimensions — so the law remains business-first and implementation-independent.

### Conformance (what regression enforces)

A domain conforms to the law when `describe()` returns entities that can answer the natural
questions about themselves. In practice the regression checks the canonical dimensions are
populated (where the domain has them) and that one retrieval answers the entity's natural
questions — not that a fixed list of fields exists forever.
