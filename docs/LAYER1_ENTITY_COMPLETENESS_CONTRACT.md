# Layer 1 — Entity Completeness Contract

> Layer 1 owns business truth and exposes **complete business objects**. Higher layers
> retrieve a complete object; they never assemble fragmented truth from multiple Layer 1
> calls. This contract is defined from **business truth first** — the implementation
> reflects it, it does not define it.

## The contract (business level)

When someone asks about a canonical entity, Layer 1 must guarantee the entity
**completely describes itself** across six business dimensions:

| Dimension | The business question it answers |
|---|---|
| **Identity** | What is it? (the human name/title) |
| **Definition** | What specifies it? (its defining attributes) |
| **Status** | What lifecycle state is it in? |
| **Plan** | What is *supposed* to happen? (intended schedule / target / cadence) |
| **Standing** | What is happening *now*, relative to the plan? (today / current) |
| **Performance** | How has it gone over time? (history / trend / rate) |

…carried with the Layer 1 trust properties already in force: **Freshness** and
**Confidence**. An entity is not "complete" until all six dimensions (where the domain
has them) are present in a single retrieval.

## The contract across canonical entities

| Entity | Identity | Definition | Status | Plan | Standing | Performance |
|---|---|---|---|---|---|---|
| **Medication** | name | dose, category, purpose | active/discontinued | schedule | taken today | 7/30/90-day adherence |
| **Goal** | title | target, metric, why | active/achieved/abandoned | deadline + target value | progress to date | pace, % to target, trend |
| **Task** | title | description, priority | todo/done/overdue | due date | done? overdue? | completion streak |
| **Calendar Event** | title | time, location, attendees | upcoming/past/cancelled | start/end | happening today? | attendance history |
| **Relationship** | person | role, desired cadence | active/lapsed | contact cadence | last contact / due to reach out | contact-frequency trend |
| **Journal Entry / streak** | date/topic | prompt, mood | drafted/logged | intended cadence | written today? | streak, frequency |
| **Habit** | name | cadence, target | active/paused | how often | done today? | streak, completion rate |
| **Workout** | type | planned exercises | planned/completed | sets/reps/plan | done today? | weekly volume, PRs |

The dimensions are universal; only the *content* per dimension is domain-specific.

## Implementation chosen — `CompleteEntity` + `describe()`, not `profile()`

`profile(entity)` was a generic method returning a per-domain dict — the business concept
("a complete self-describing entity") was invisible and each domain invented its own
shape. The chosen implementation makes the **entity** first-class:

- **`CompleteEntity`** (`apps/core/truth/entity.py`) — one Layer 1 dataclass whose fields
  ARE the contract dimensions: `kind, identity, definition, status, plan, standing,
  performance, freshness, confidence`. Every domain returns this same shape.
- **`DomainTruth.describe(entity_type)`** → `list[CompleteEntity]`. The verb is the
  business operation ("the entity describes itself"); the return is the contract shape.
- A domain may also expose a **summary** (the aggregate across its entities — e.g. overall
  adherence) composed *inside Layer 1*, so the higher layer still makes one call.

**Medication is the reference implementation.** Every future canonical domain implements
`describe()` returning `CompleteEntity` objects in the same shape. When a domain adds a new
entity, it is not complete until its `CompleteEntity` populates every dimension the domain
has — enforced by regression.

## Why this is the better architecture

- The business contract is **visible in the type** — `CompleteEntity`'s fields are the
  six dimensions; you cannot return a half-described entity without leaving a dimension empty.
- The shape is **identical across domains** — Beth (and dashboards, reports, exports) learn
  one shape, not one bespoke dict per domain.
- It is **self-policing** — a new entity that omits a dimension is visibly incomplete.
- It preserves the Layer 1 laws — freshness + confidence travel on every entity.
