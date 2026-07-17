# DRAFT — Three Truth Surfaces & the Personal Truth Profile

> **STATUS: DESIGN DRAFT FOR REVIEW — v2 (deep review). NOT CANONICAL. NOT FROZEN.**
> Design-only. Creates no code, models, registries, or standing-context changes.
> v1 introduced the four proposed drafts (Parts A–D) + open questions (Part E).
> **v2 resolves Part E through a grounded owner analysis and, where an answer changed
> another, restructures the proposal (it did — three times; see the changelog at the
> end of this file).**
>
> **Grounding (repo truth, verified 2026-07-17):** Slice 1 already ships —
> `apps/ai/cos_services/personal_truth.py` (composer) + `get_user_truth` tool: read-only,
> cross-domain, per-fact `module`+`source` provenance, conflict-surfacing
> (`_nutrition_target_contradictions`), one composer feeding standing context + the tool.
> Owner models were read directly from the codebase for the analysis in Part D.

---

## Part 0 — What v2 changed (so reviewers see the deltas)

The deep review changed three things that ripple through Parts A–D:

1. **AI Relationship is a *projection*, not an owner** (verified: `get_ai_relationship`
   is a projection service with `AIRelationshipProjectionTests`). So "relationship/
   coaching preference → AI Relationship owner" (v1) was **wrong**. The leaf owners are
   `UserPreferences.ai_coaching_style`, `ai.LearnedCommunicationPreference`,
   `ai.ResponsePreference`. PTP and AI Relationship are **sibling projections** over the
   same owners, cut by **content (PTP) vs voice (AI Relationship)**. → restructures Part
   D §9/§10.
2. **Safety-critical categories are ownerless AND underivable** (allergies, injuries —
   no model exists; you cannot deterministically derive an allergy from an event stream).
   The v1 rule "ownerless ⇒ Derived forever" is unsafe here: you can't derive it either.
   → the lifecycle becomes a **decision tree with a safety carve-out** (Part D §4), and a
   **prerequisite backlog** appears (Part D §16): some categories cannot enter PTP *at
   all* until an owner model is created.
3. **"Derive from absence" is forbidden** — the direct application of the Health-Sync /
   Flights-Climbed lesson (absence of records ≠ a fact) to PTP derivation. "Foods
   avoided" cannot be derived from *not* logging a food. → new invariant (Part D §4).

Everything else in v1 stands.

---

# PART A — PROPOSED DRAFT for `WLJ_LLM_TRUTH_ACTION_CONTRACT.md` §3 (The Truth Boundary)

> Insert as **§3.8 The Three Truth Surfaces**, after §3.2. Not yet transcribed.

## §3.8 The Three Truth Surfaces

WLJ exposes truth to the model through truth tools (§3.2). Those tools answer three
different **question-shapes**, and a tool answers **exactly one**.

| Surface | Question-shape | Returns | Example callers |
|---|---|---|---|
| **Entity Truth** | *"What happened?"* | one **episodic record** | a meal, workout, journal entry, glucose reading, transaction |
| **Domain State** | *"Where does this domain stand right now?"* | current **momentary** deterministic state of one domain | nutrition / health / financial / execution status |
| **Personal Truth Profile** | *"Who is this person?"* | **durable standing facts** | conditions, targets, constraints, preferences, standing routines |

**The three contract rules:**

1. **One question-shape per surface.** A blended tool (a "status" that also returns
   records; a "profile" that returns today's plan) is a defect.
2. **Classify the accessor by the question it answers, not by where the data lives.**
   Same dataset, multiple accessors. Tie-break example — a workout schedule: standing
   *definition* → Personal Truth Profile; current *adherence* → Domain State; today's
   *session* → Entity/Execution.
3. **Surface-type is orthogonal to delivery-mode.** Which surface ≠ how it's delivered
   (pulled on demand vs pushed standing in the executive-context envelope §3.6). Entity
   Truth is pulled; the Profile is pushed standing; Domain State is both.

**Envelope.** All three return the standard §3.2 envelope (value + source + freshness +
confidence + provenance). No parallel envelope.

### §3.8.1 What is NOT a truth surface (the fence — added v2)

These are frequently confused with a truth surface and must be kept out of the taxonomy,
or the classification erodes:

- **Deterministic Understanding** — deterministic *assessments* of current state ("on
  track with medication"), not facts. It is an interpretation layer over Domain State,
  not a fourth surface. (Assessment ≠ fact.)
- **Executive Reflection** — facts/learning about the *assistant's* performance (EIOs),
  not about the *user*. Different subject entirely; never a personal truth.
- **Future Prediction / forecasts** — "what is *likely*." A prediction is not a durable
  fact and not a record. See §3.8.2.
- **Recommendations / verdicts** — the model's reasoning output, never a WLJ truth
  surface.

Rule: *a truth surface returns facts the user's world already makes true. Assessments,
predictions, reflections, and recommendations are computed **over** truth, not truth.*

### §3.8.2 The set is open — Forward and Relational (added v2)

- **Forward Truth** ("what is likely / where are we headed" — deterministic predictions
  like projected A1c, weight projection; Mission trajectory). This *is* a genuinely
  distinct question-shape. **Disposition: recognized future 4th surface, NOT promoted
  now.** It currently rides inside Domain State briefings and Mission. Promote it the day
  a dedicated forecast accessor is needed; until then it is folded, explicitly flagged
  here so it isn't misfiled as Domain State permanently.
- **Relational Truth** ("who relates to whom" — the Person graph). **Disposition: folds
  into the existing three, never a separate surface.** Salient standing relationships →
  Profile (identity spine); an individual relationship record → Entity Truth;
  relationship health/activity → Domain State. It is the cleanest demonstration of rule 2
  (one domain, three accessors by question-shape).

The taxonomy is **three today, open by construction** — a new surface is added by
contract (here + the Laws), never by constitutional amendment.

---

# PART B — PROPOSED DRAFT for `WLJ_ARCHITECTURE_LAWS.md` (Amendment B)

> Enforcement anchor for Part A, at the RETRIEVE step. Not yet transcribed.

## Amendment B (proposed) — The Retrieval Surface Classification

**Every retrieval targets exactly one of the three Truth Surfaces, and a surface answers
exactly one question-shape.** Retrieval that cannot name its surface, or a surface
answering more than one question-shape, is a Law-0 violation (answering a different
question than was asked) surfacing at the retrieval layer.

- **Companion to Law 0.** Law 0 fixes *which domains*; Amendment B fixes *which surface
  within them*. Intent → question-shape → surface.
- **Companion to Law 3.** STRATEGY's retrieval option is constrained to one declared
  surface.
- **Enforcement (specified, built later):** accessors declare their surface-type; a
  contract test rejects multi-surface accessors and any `durable_profile` accessor that
  owns a writable model.
- **Fence (from §3.8.1):** assessments (Deterministic Understanding), predictions,
  reflection, and recommendations are **not** retrieval surfaces; they are computed over
  retrieved truth and must not be registered as one.

---

# PART C — PROPOSED DRAFT: Model Interface additions

> Destined for `WLJ_MODEL_INTERFACE_DESIGN.md` (already names `get_entity` /
> `get_domain_state`). Interface contract only — conceptual shapes, no code.

Three accessor families, one per surface; each returns the §3.2 envelope.

### C.1 `get_entity` — Entity Truth (exists)
`get_entity(user, domain, entity_type, selector) → { record, envelope }` — one episodic
record. Backed by the DomainTruth `get_entity` surfaces. Pulled on demand.

### C.2 `get_domain_state` — Domain State (exists)
`get_domain_state(user, domain) → { current_state, envelope }` — current momentary
domain state (facts, not verdicts). Backed by SAE state builders; **already a separate
registry from `get_entity`** — the distinction the taxonomy makes permanent.

### C.3 `get_durable_facts` — Personal Truth Profile (proposed; new)
`get_durable_facts(user, domain) → { facts: [DurableFact], envelope }`. A **DurableFact**
carries: `key`, `value`, `unit?`, **`owner_module`**, **`source_accessor`**, **`provenance
∈ {explicit, derived, verified}`**, `confidence?` (derived), `as_of` / `valid_until?`,
`sensitivity`, `conflict?`. Bounded/curated, not analytics. The **PTP composer**
(`personal_truth.py`) aggregates per-domain `get_durable_facts` providers — one source
feeds both the domain and the Profile (no re-derivation). Delivered standing (background-
computed) + via `get_user_truth`. **Invariant:** a `get_durable_facts` provider has **no
writable model**.

---

# PART D — PROPOSED OUTLINE: `WLJ_PERSONAL_TRUTH_PROFILE.md`  *(v2 — expanded from the owner analysis)*

**§0. First sentence.** "The Personal Truth Profile is a deterministic **projection**,
not a storage model. It owns nothing, stores no authority, and has no writable model."

**§1. Is / is not.** (Promote both lists from the shipped module docstring.)

**§2. Place in the Three Truth Surfaces.** The "who is this person?" surface.

**§3. The DurableFact model.** Fields per Part C.3.

### §4. The provenance lifecycle — a decision tree (RESTRUCTURED in v2)

Provenance is **computed from owners' data, never stored in the Profile.** For each
candidate fact:

```
1. Does an authoritative OWNER hold a user-supplied value?
      → EXPLICIT.  (verifiable-by-definition; already user-asserted)
2. Else: is it deterministically DERIVABLE from PRESENT episodic records?
      → DERIVED (with confidence + support count). Never Verified while ownerless.
      → Becomes VERIFIED only when the user explicitly confirms AND the confirmation
        writes to an owner (which records "confirmed-from-derived").
3. Else (no owner, not derivable):
      → does NOT appear in the Profile.
4. SAFETY CARVE-OUT: if the fact is safety-critical (allergy, contraindication, injury)
   it may appear ONLY as EXPLICIT from a first-class owner. It is NEVER derived, NEVER
   guessed, and absent until an owner exists. A wrong safety fact is worse than none.
```

**Two hard invariants (contract tests):**
- **Never derive from absence.** A derived fact asserts only PRESENCE proven by records.
  "Not logged" is not "avoided"; "no workout row" is not "rest day preference." (Direct
  application of the Health-Sync lesson — absence ≠ fact.)
- **Observed never silently becomes Explicit.** Derived→Verified requires an explicit
  user-confirmation event that writes to the owner. Enforced, not policy.

### §5. The Owner Registry — foundation table (NEW in v2; the answer to the owner problem)

The registry maps `fact-type → authoritative owner → read accessor → confirm write-path`.
This table is its seed. **It is also a one-authority audit instrument:** building it
forces every durable-fact type to name a single owner and surfaces existing violations.

| Category | Authoritative owner (store) | Exists? | Projection source | Can be Verified? | In PTP? |
|---|---|---|---|---|---|
| **Identity spine** (name, pronouns, DOB, tz/locale) | `people.Person` (is_self) + `users.UserPreferences` | ✅ (gated on Person-consolidation) | people.Person / UserPreferences | Explicit | **Yes** (identity spine) |
| **Medical conditions** | `health.MedicalCondition` | ✅ | MedicalCondition | Explicit | **Yes** (shipped) |
| **Medications** | `health.MedicationEvent` / MedicineQueries | ✅ | MedicineQueries.active | Explicit | **Yes** (shipped) |
| **Allergies** | — **none** | ❌ | — (not derivable) | **No** | **No — needs owner first** (safety) |
| **Injuries** | — **none** | ❌ | — | **No** | **No — needs owner first** (safety) |
| **Nutrition targets** | `health.NutritionGoals` (canonical) — **conflicts with** `meals.DietaryProfile` | ✅ (DUAL) | NutritionGoals; conflict surfaced | Explicit | **Yes** (shipped) — needs canonical-owner designation |
| **Favorite foods** | — none (`FoodPreference` proposed) | ❌ | derivable (meal-log frequency) | Derived-only until owner | **Yes** as Derived |
| **Foods avoided** | — none / overlaps allergies | ❌ | **NOT derivable** (absence≠avoidance) | No | **Only if explicitly owned** |
| **Supplements** | — none (execution `supplement_dose` only) | ❌ (no standing store) | weak | Derived-only until owner | tentative |
| **Exercise preferences** | — likely none | ❌? | maybe derivable | Derived-only until owner | tentative |
| **Workout schedule** | `health.WorkoutSchedule` (+ `life.RoutineSchedule`) | ✅ | WorkoutSchedule | Explicit | **Yes** (standing definition; not today's session) |
| **Coaching preferences** | `users.UserPreferences.ai_coaching_style` + `ai.LearnedCommunicationPreference` | ✅ | those owners | Explicit / Verified | **Content-shaping subset → Yes**; voice → AI Relationship |
| **Communication preferences** | `ai.ResponsePreference` / `ai.LearnedCommunicationPreference` | ✅ | those owners | Explicit / Verified | **Mostly voice → AI Relationship**; content subset → PTP |
| **Relationship preferences** | leaf owner (UserPreferences / relationship settings) — **NOT "AI Relationship"** | partial | underlying store | depends on owner | boundary case (content → PTP) |
| **Faith preferences** | faith settings / UserPreferences (**verify at impl**) | ? | TBD | TBD | verify |
| **Financial preferences** | finance profile (**verify at impl**) | ? | TBD | TBD | verify |
| **Projects** | `life.Project` | ✅ | life.Project | Explicit | **No** — active work (Domain/Mission), not standing identity |
| **Long-term priorities** | `core.UserPriorityProfile` | ✅ | UserPriorityProfile | Explicit | **Yes** (shipped; standing values) |
| **Goals** | `purpose.LifeGoal` | ✅ | LifeGoal | Explicit | **Durable aspects yes** (existence + target); **progress → Mission** |
| **Mission targets** | `purpose` (mission over LifeGoal / GoalSignalSource) | ✅ | mission_link | Explicit | **Mission surface**, referenced by PTP, not owned |
| **Constraints** (composite) | MedicalCondition + Allergy(∅) + DietaryProfile.dietary_flags | partial | multiple | mixed | **Partial** — limited by ownerless allergies |
| **Safety-critical** (composite) | MedicalCondition + Allergy(∅) + Injury(∅) | partial (**gaps**) | multiple | mixed | **Owned parts yes; allergies/injuries need owners** |

**§6. Confidence, recency & validity.** Derived facts carry confidence + support count;
all facts carry `as_of`; `valid_until` + re-derivation where relevant. Stale derived
facts re-derive or decay — never asserted as current.

**§7. Conflict — surfaced, never reconciled.** Present both values, tagged; never
explain or choose. (Shipped precedent: `_nutrition_target_contradictions`.) The
nutrition dual-owner is the live example: PTP surfaces the conflict; the *domain* must
designate the canonical owner (§16).

**§8. Sensitivity & surface-gating.** The **owning module** sets each fact's sensitivity
tier; PTP carries it. Default narration policy is conservative; hard-blocked categories
(reproductive — existing boundary) stay out entirely. (Full policy deferred; the
carry+flag requirement is fixed now.)

**§9. Categories.** As the §5 table. Note the **AI-Relationship correction**: coaching/
communication/relationship preferences are owned by `UserPreferences` /
`LearnedCommunicationPreference` / `ResponsePreference` — **AI Relationship is a sibling
projection, never the owner.** PTP projects the *content* of these prefs; AI Relationship
projects their *voice*.

**§10. Boundaries (v2 — hardened).**
- **vs AI Relationship** — both are *projections over the same preference owners*; cut by
  **content (PTP) vs voice (AI Relationship)**. Neither owns.
- **vs Mission** — PTP holds a goal's *existence + target* (durable); Mission holds its
  *progress + trajectory*. One owner (LifeGoal), two consumers.
- **vs Domain State** — standing definition vs current status (workout-schedule tie-break).
- **vs Entity Truth** — the durable distillation vs the event record.
- **vs Current Context** — who the person *is* vs what they're *looking at now*.
- **vs Deterministic Understanding** — durable *fact* vs momentary deterministic
  *assessment*. DU is not a truth surface (§3.8.1); PTP never carries an assessment.
- **vs Reflection** — facts about the *user* vs learning about the *assistant*. Reflection
  never writes to PTP.
- **vs Future Prediction** — present-tense durable fact vs "what's likely." Predictions
  are Forward Truth (§3.8.2), never a personal-truth fact.

**§11. Request-path safety.** Background-computed + cached snapshot; request path reads
it, returns `pending` if absent, never live-aggregates.

**§12–15.** (Unchanged from v1: contract tests; standing-context placement; phasing —
Slice 1 shipped, then Derived+confidence, Verified lifecycle, identity spine; governance
— taxonomy in Contract+Laws, not Constitution.)

### §16. Prerequisite backlog (NEW in v2 — what must exist BEFORE certain categories enter PTP)

- **Create first-class owners (blocking, safety):** `Allergy`, `Injury`. Underivable +
  safety-critical ⇒ absent from PTP until owned. *(Design flags this; does not build it.)*
- **Create owners to unlock Verified:** `FoodPreference` (favorites/avoided), a standing
  `Supplement` store. Until then: favorites = Derived-only; avoided = omitted (never
  derived).
- **Designate a canonical owner (one-authority fix):** nutrition targets —
  `NutritionGoals` canonical; `DietaryProfile` becomes a consumer or a defined-precedence
  source. PTP keeps surfacing the conflict until the domain resolves it.
- **Verify at implementation:** exercise / faith / financial preference owners.

This backlog is *domain work the Profile depends on*, not Profile work — which reinforces
that PTP is a projection with real upstream dependencies, and the Owner Registry is the
coordination + one-authority-audit artifact.

---

# PART E — RESOLVED (v2)

**E1 — Ownerless favorite/avoided foods.** No owner today. **Favorites** are derivable
(meal-log frequency) → **Derived-only until a `FoodPreference` owner exists**; only then
Verifiable. **Avoided** is **not** safely derivable (absence ≠ avoidance) → **omitted
unless explicitly owned**; overlaps allergies (safety) → belongs with the Allergy owner.
*Resolution: create `FoodPreference` (favorites) + route "avoided" through the Allergy/
constraint owner; do not derive avoidance.*

**E2 — PTP ↔ Mission for targets.** Target *value* owned by `NutritionGoals`, projected
to PTP as a durable fact; Mission *references* it when a goal is about it. No dual
ownership; progress stays in Mission.

**E3 — 4th/5th surfaces.** **Forward Truth** = recognized future 4th surface, **folded
for now** (rides in Domain State + Mission), promoted when a forecast accessor is needed.
**Relational Truth** = **folds into the existing three** (identity spine / Entity /
Domain State), never separate. Taxonomy stays **three, explicitly open**.

**E4 — Sensitivity gating.** The **owning module** sets the tier; PTP carries + flags it;
conservative default narration; hard-blocked categories stay out. Full policy deferred;
carry+flag fixed now.

**E5 — Derived recompute cadence.** Tie to existing intelligence cycles (SAME cycle /
PIE–PRIE) + invalidate on the owning domain's write events. **No new scheduler.**

**E6 — AI Relationship as owner.** **No.** Verified: it's a *projection*
(`get_ai_relationship`). Leaf owners are `UserPreferences.ai_coaching_style`,
`LearnedCommunicationPreference`, `ResponsePreference`. PTP and AI Relationship are
sibling projections cut by content vs voice.

**Remaining genuinely open (need Danny):**
- **O1 — Create the safety owners now or gate PTP?** Do we schedule `Allergy`/`Injury`
  owner models as a prerequisite milestone, or ship PTP without safety-critical
  constraints until then? (I recommend: create the owners — safety facts are the highest-
  value durable truth, and their absence is itself a product risk.)
- **O2 — Nutrition dual-owner:** designate `NutritionGoals` canonical and demote
  `DietaryProfile` to consumer, or define an explicit precedence? (A domain-level
  one-authority decision the registry forces.)
- **O3 — Faith/financial/exercise preference owners:** confirm or create.

---

# Governance — re-evaluated after the deep review (unchanged conclusion, one addition)

Placement stands: **taxonomy defined in the Truth/Action Contract (§3.8), enforced from
the Architecture Laws (Amendment B), implemented via the Model Interface trio, PTP as one
instance; enumeration NOT in the Constitution** (keep it open; elevate at most the single
"one-question-per-surface, projection-only" invariant later, via Review).

**Addition (v2):** the **Owner Registry is a Constitution one-authority *audit
instrument*,** not just PTP plumbing — it forces every durable-fact type to name a single
owner and surfaces existing violations (nutrition dual-owner). That elevates its
importance: it should be built early and referenced by the one-authority discipline, not
treated as PTP-internal detail.

---

## Changelog (this draft)
- **v2 (2026-07-17)** — deep review. Resolved Part E (E1–E6) via a grounded owner
  analysis (Part D §5 table). Three restructurings: AI Relationship is a projection not
  an owner (§9/§10); safety carve-out + "never derive from absence" in the lifecycle
  (§4); prerequisite owner backlog (§16). Added the §3.8.1 "not-a-surface" fence and the
  §3.8.2 Forward/Relational disposition. Three genuinely-open items remain (O1–O3).
- **v1 (2026-07-17)** — initial four drafts (Parts A–D) + open questions (Part E).

*Nothing here is canonical until transcribed into the named docs after review. This file
creates no code, models, registries, or standing-context changes.*
