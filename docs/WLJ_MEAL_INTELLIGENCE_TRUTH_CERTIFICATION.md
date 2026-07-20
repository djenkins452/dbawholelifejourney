# WLJ Meal Intelligence — Truth Certification Standard

**Version:** 1.0
**Authority:** The certification standard for the Meal Intelligence domain. Defines what it means for each food truth to become a *certified deterministic truth domain*, exactly as other WLJ truth domains are certified.
**Companion to:** `docs/WLJ_MEAL_INTELLIGENCE_ARCHITECTURE.md` (governing architecture) and `docs/WLJ_MEAL_INTELLIGENCE_ROADMAP.md` (implementation milestones).
**Scope note:** This is a *standard*, not a test plan and not a certification run. It defines the bar; it does not attempt to clear it. It aligns with `docs/LAYER1_DOMAIN_FRAMEWORK.md` (how a canonical truth domain is built and certified) and the platform Truth Retrieval Certification program (deterministic question specs + live acceptance).

---

## 1. Purpose

Meal Intelligence is a Personal Truth Platform domain. A domain is not "done" when its features work — it is done when its **deterministic truth is provably correct, single-sourced, reproducible, and answerable**. Certification is how WLJ proves that. This document defines, for every food truth, the owner, the primary truth it holds, its current maturity, the criteria it must meet to be certified, and the representative deterministic questions a certified truth must answer correctly.

A truth that is not yet certified may still ship; it simply may not be *relied upon* as authoritative until it passes. Certification is the gate between "the feature exists" and "the platform guarantees the answer."

---

## 2. What "certified deterministic truth" means here

A Meal Intelligence truth is **certified** when it satisfies all seven gates. These are the domain's architectural principles restated as verifiable acceptance conditions.

| Gate | Certification condition |
|---|---|
| **G1 — Single owner** | Exactly one domain/app is the authoritative producer (per the ownership table in the architecture). No second producer exists. |
| **G2 — Single writer** | The truth is mutated through exactly one write path. Ledger-backed truths mutate only by appending to their ledger. |
| **G3 — Structured at write** | The truth is fully structured when captured (not deferred to a read path). Read paths may assume their inputs exist. |
| **G4 — Reproducible** | Any derived/fold truth (pantry state, nutrition totals) can be recomputed from its ledger and yields the same result. Caches are disposable. |
| **G5 — Scoped & provenanced** | The truth declares its scope (Reference · Knowledge · Household · Person) and carries provenance (source, confidence, freshness) where applicable. |
| **G6 — Request-path safe** | The truth is readable on the request path without heavy computation or inline model calls; expensive derivations are pre-computed. |
| **G7 — Deterministically answerable** | A defined set of representative deterministic questions is answered correctly and identically on repeat, from the canonical truth alone (no inference). |

A domain that meets G1–G6 is **structurally certified**; a domain that additionally passes G7 against its representative question set is **answer-certified** — the full bar.

---

## 3. Maturity ladder

Every food truth sits at one rung. Certification advances a truth up the ladder; the target for a Layer-1 canonical truth is **M4+**.

| Rung | Name | Meaning |
|---|---|---|
| **M0** | Absent | The truth is not modeled, or exists only as unstructured text/JSON. |
| **M1** | Stored | A canonical model exists and holds the data, but with drift risk (multiple producers, or unstructured). |
| **M2** | Single-sourced | One owner, one writer (G1–G2). Fragmentation eliminated. |
| **M3** | Structured & reproducible | Structured at write; folds are reproducible; scoped & provenanced (G3–G5). |
| **M4** | Answer-certified | Passes its representative deterministic question set on the request-path-safe read (G6–G7). |
| **M5** | Lifecycle-connected | Participates correctly in *Capture Once, Reuse Everywhere* — its capture propagates to, and it is fed by, the events that should touch it. |

Certification is per-truth, not per-screen. A domain may be M4 for one truth and M1 for another; the roadmap advances them deliberately.

---

## 4. Per-truth certification register

For each food truth: **canonical owner**, **primary truth it holds**, **current maturity** (as of this standard's authoring, grounded in the inventory phase), **certification criteria** (what advancing it requires beyond the universal gates), and **representative deterministic questions** (the answerable bar — illustrative, not exhaustive).

> "Current maturity" reflects the code as inventoried; it is a starting line, not a claim of certification. It will move as the roadmap executes.

### Recipes
- **Owner / scope:** Meal Intelligence / Knowledge (household-accessible; person-related)
- **Primary truth:** the operational definition of a preparable dish — structured ingredients, quantities, servings, steps, derived nutrition, equipment, cost, provenance.
- **Current maturity:** **M1.** Recipe records exist but ingredients are unstructured free text; structured `RecipeIngredient` is never written, so nutrition/gap/scoring derive from empty input. Ownership is not yet consolidated under Meal Intelligence.
- **Certification criteria:** structured-at-write ingredient decomposition (G3); recipe nutrition reproducible from structure (G4); provenance/source dimension present (G5); person-relationships (favorite/rating/note) modeled separately from the shared record.
- **Representative questions:** *What are the exact ingredients and quantities of this recipe? · How many servings does it make? · What is its per-serving nutrition? · Which of my pantry items does it use? · Where did this recipe originate?*

### Ingredients (reference library)
- **Owner / scope:** Meal Intelligence / Reference
- **Primary truth:** canonical ingredient identity — name, aliases, category, storage type, shelf life, substitution group, density, default unit, nutrition link.
- **Current maturity:** **M2–M3.** Canonical library with matching exists; nutrition links are incomplete.
- **Certification criteria:** high nutrition-source link coverage (G5); deterministic name→canonical resolution.
- **Representative questions:** *What is the canonical form of "AP flour"? · What category and storage type is this ingredient? · What is its default unit and typical shelf life?*

### Pantry
- **Owner / scope:** Meal Intelligence / Household
- **Primary truth:** current on-hand inventory state — quantity, location, confidence, last-confirmed, estimated expiration — as a fold of the inventory ledger.
- **Current maturity:** **M3.** Canonical single-writer and fold in place; decay runs only lazily on read; not yet decremented by consumption.
- **Certification criteria:** state fully reproducible from the ledger (G4); confidence/expiration maintained on a schedule (G6); connected to preparation deduction (M5).
- **Representative questions:** *How much of X do I have right now? · Where is it stored? · What is expiring within N days? · When was this item last confirmed?*

### Inventory ledger
- **Owner / scope:** Meal Intelligence / Household
- **Primary truth:** the immutable, signed, sourced record of every quantity change.
- **Current maturity:** **M3.** Exemplary event ledger; some defined sources (meal_plan, expiration) unused because the emitting events don't yet exist.
- **Certification criteria:** every quantity change flows through the ledger with a valid source (G2); no out-of-band pantry mutation.
- **Representative questions:** *Why did my quantity of X change on this date? · What added this item to my pantry? · What consumed it?*

### Shopping Lists
- **Owner / scope:** Meal Intelligence / Household
- **Primary truth:** the derived, editable set of items required to satisfy plan minus pantry, with purchase status.
- **Current maturity:** **M0–M1.** No canonical persisted list (the optimizer computes then discards; a headless orphan model exists elsewhere).
- **Certification criteria:** one owned, persisted list deterministically derived from plan − pantry (G1, G4); no duplicate producer.
- **Representative questions:** *What do I need to buy for this week's plan? · Which items are already covered by my pantry? · What is still unpurchased on my list?*

### Receipts
- **Owner / scope:** Meal Intelligence / Household
- **Primary truth:** the evidentiary record of an acquisition — items, store, totals, confidence, dedup identity.
- **Current maturity:** **M3–M4.** Vision capture, dedup, and confirmation-gated routing are production-grade.
- **Certification criteria:** capture-vs-activation separation preserved (G3/confirmation); one receipt → deterministic fan-out (M5).
- **Representative questions:** *What did I buy on this receipt? · From which store, and what did it total? · Is this a duplicate of another receipt?*

### Meal Plans
- **Owner / scope:** Meal Intelligence / Household
- **Primary truth:** the intended schedule of recipes across dates and meal types.
- **Current maturity:** **M1–M2.** Plans exist but optimize over starved recipe data.
- **Certification criteria:** plan reflects real recipe nutrition/feasibility (depends on Recipe M3); household-scoped with per-person reconciliation rules (safety union, per-person targets).
- **Representative questions:** *What is planned for dinner Thursday? · Which recipes are in this week's plan? · Does this plan respect every eater's allergies?*

### Food Entries (Consumption)
- **Owner / scope:** Health / Person
- **Primary truth:** actual intake — food/recipe, portion, time, meal, immutable nutrient snapshot, source.
- **Current maturity:** **M3–M4.** Rich, snapshotted, audited consumption record; not yet fed by the preparation/consumption bridge.
- **Certification criteria:** intake reproducible into daily totals (G4); fed by the cook/eat spine (M5); one nutrition-math authority.
- **Representative questions:** *What did I eat yesterday? · What were my total macros for a given day? · When did I last eat X?*

### Nutrition Targets
- **Owner / scope:** Health / Person
- **Primary truth:** the single authoritative calorie/macro/micronutrient targets and limits, with effective dates.
- **Current maturity:** **M1.** Targets stored in multiple places (grams vs percentages) with drift.
- **Certification criteria:** one canonical store (G1); all consumers read through it (G2); micronutrient targets modeled.
- **Representative questions:** *What is my daily calorie target? · What are my macro targets in grams? · What target was in effect on a past date?*

### Price History
- **Owner / scope:** Meal Intelligence / Household
- **Primary truth:** product × store × time × unit-price observations.
- **Current maturity:** **M0.** Prices are captured on receipts but never stored as history.
- **Certification criteria:** deterministic PriceObservation emitted per confirmed receipt item (M5); reproducible price series.
- **Representative questions:** *What did I last pay for X, and where? · How has the price of X changed over time? · Which store is cheapest for X?*

### Stores
- **Owner / scope:** Meal Intelligence / Reference
- **Primary truth:** store/retailer identity (and, as preference, the household's relationship to it).
- **Current maturity:** **M0.** Store is free text on receipts; no canonical entity.
- **Certification criteria:** canonical store identity (G1); receipts and prices reference it.
- **Representative questions:** *Which stores do I shop at? · What did I buy at store Y? · What is my preferred store for category Z?*

### Meal Preparation
- **Owner / scope:** Meal Intelligence / Household
- **Primary truth:** the fact that a recipe was prepared — servings made, inventory consumed, leftovers produced.
- **Current maturity:** **M0.** No preparation event exists; cooking is unmodeled.
- **Certification criteria:** a thin `PreparationEvent` that emits inventory deduction and leftovers and enables per-person consumption (M5) — the spine.
- **Representative questions:** *When did I last cook X? · What did preparing this meal consume from my pantry? · What leftovers did it produce?*

### Leftovers
- **Owner / scope:** Meal Intelligence / Household
- **Primary truth:** a pantry-tracked item produced by preparation and consumed later.
- **Current maturity:** **M0.** Unmodeled.
- **Certification criteria:** leftovers enter the inventory ledger on preparation and decrement on consumption (M5).
- **Representative questions:** *What leftovers do I have and from when? · How old is this leftover? · What can I make from my leftovers?*

### Restaurant Meals
- **Owner / scope:** Health / Person (consumption subtype)
- **Primary truth:** a consumption event that occurred away from home, with spend.
- **Current maturity:** **M1.** A macro-less restaurant-receipt bridge exists.
- **Certification criteria:** consistent consumption record; depth (spend-only vs full nutrition) is a product decision (see architecture OPD-1).
- **Representative questions:** *When did I last eat out, and where? · What did I spend eating out this month? · (if deep) what did I eat at restaurant Y?*

### Allergies & Dietary Restrictions (safety truth)
- **Owner / scope:** Health / Person
- **Primary truth:** the typed, auditable, safety-critical set of what a person cannot/will not eat, with severity.
- **Current maturity:** **M1.** Stored as untyped JSON.
- **Certification criteria:** first-class typed entities (G5); compose as a **union** across a household meal (P7); never merged with targets.
- **Representative questions:** *What am I allergic to? · Is this recipe safe for me? · Is this planned meal safe for everyone eating it?*

---

## 4b. Food Lifecycle Certification (Foundation 2 — implemented & passing)

Behavioral certification of the **operational food lifecycle** — every implemented
transition has a canonical producer and a passing behavioral proof. Tests live in
`apps/meals/tests/` and run green (see the changelog entries for Foundation 2).

| # | Transition | Canonical producer | Behavioral proof (test module) | Status |
|---|---|---|---|---|
| 1 | Recipe save → structured ingredients | `enrich_recipe_ingredients` (write-boundary signal) | `test_recipe_enrichment` · `test_food_lifecycle_certification` | ✅ |
| 2 | Recipe → preparation | `prepare_recipe` | `test_preparation` · `test_food_lifecycle_certification` | ✅ |
| 3 | Preparation → pantry deduction | `deduct_pantry_item` → `InventoryTransaction(source="preparation")` | `test_preparation` (deduction+txn) | ✅ |
| 4 | Preparation → leftover | `prepare_recipe` → `Leftover` | `test_preparation` · `test_food_lifecycle_certification` | ✅ |
| 5 | Preparation/leftover → consumption | `consume_meal` | `test_consumption` · `test_leftover_management` | ✅ |
| 6 | Consumption → FoodEntry | `consume_meal` (reuses `FoodEntry.calculate_totals`) | `test_consumption` (scaled macros) | ✅ |
| 7 | FoodEntry → nutrition totals | `NutritionQueries.get_daily_totals` | `test_consumption` · `test_food_lifecycle_certification` | ✅ |
| 8 | Consumption → leftover reduction (+ terminal disposition) | `consume_meal` | `test_leftover_management` | ✅ |
| 9 | Leftover → discard/waste (final disposition) | `discard_leftover` → `FoodWasteEvent` | `test_leftover_management` · `test_food_lifecycle_certification` | ✅ |
| 10 | Leftover → deterministic expiration | `expire_due_leftovers` (scheduled) | `test_leftover_management` | ✅ |
| 11 | Retry/replay → no duplicate effects | idempotency keys (prep/consume/discard) | all four suites | ✅ |
| 12 | Package pantry unit → culinary recipe unit deduction | `container_truth.resolve_net_content` + `convert_between` (via `_deduct_one`) | `test_pantry_container_truth` (8 reference ingredients + partial/insufficient) | ✅ |
| 13 | Missing bridging fact → actionable ask (fail closed) | `_deduct_one` → `needs_container_info` | `test_pantry_container_truth` · `test_preparation` | ✅ |
| 14 | Manual entry → same canonical PantryItem as every scan (Capture Once) | `PantryManualAddView` → `finalize_pantry_item(source="manual")`; ingredient reuse via `get_or_create_ingredient`; up-front `capture_container_truth` | `test_pantry_manual_entry` (9 — incl. end-to-end preparation consumption) | ✅ |

**Container Truth invariants** (enforced): net contents of one full container
(`net_content`) is distinct from the remaining amount (`quantity`); **Remaining Truth is
stored as an exact base quantity** in the base unit (e.g. 312 ml), never as a container
fraction — container counts and percentages are DERIVED at presentation
(`remaining_containers` / `remaining_percent`) from `quantity ÷ net_content`; the ledger
folds to that same base quantity; mass↔volume converts **only** with an Ingredient density
and is otherwise refused (no estimation); count substances stay on the legacy unit-matching
path so no existing weight/volume deduction regresses; resolution is acquisition-independent
(one resolver inside `finalize_pantry_item`, which stores the exact base quantity) and
idempotent; when no source resolves the fact, deduction leaves stock **untouched** and
returns `needs_container_info` (captured in-workflow) rather than the retired dead-end
`unsupported_conversion`.

**Leftover legal state transitions** (enforced): `AVAILABLE → {CONSUMED, DISCARDED,
EXPIRED}`; the latter three are terminal. Invariants proven by test: quantities never
negative; consume/discard above available rejected; consumed/discarded/expired leftover
cannot be consumed or discarded; a repeated idempotency key subtracts once; failures
roll back (fail-closed) leaving no partial truth. Discard/expiration never create a
`FoodEntry`, never count as nutrition, and never re-deduct pantry.

**Not certified here** (out of scope, later milestones): grocery-list generation,
meal-plan automation, recommendations, price intelligence, external ordering, CoS.

---

## 5. Certification process (how a food truth is certified)

Aligned with the platform's two-owner Truth Retrieval Certification pattern:

1. **Owner-1 (deterministic):** author the truth's representative deterministic question set and its expected answers derived from canonical fixtures — the structural specification of "correct."
2. **Owner-2 (live):** exercise those questions against the real request-path-safe read of the truth and confirm identical, reproducible answers with no inference.
3. **Advance the rung:** a truth is marked M4 (answer-certified) only when Owner-2 passes with zero missing-truth failures; M5 when its *Capture Once* propagation is verified end to end.
4. **Record:** certification status per truth is tracked alongside the roadmap; a truth regresses if a later change reintroduces a second producer or breaks reproducibility.

Certification is evidence-gated: a passing unit test is not certification. The truth must answer its questions on the real read path.

---

## 6. Certification target order

Truths are certified in dependency order, matching the roadmap: consolidate single-sourced truths first (Nutrition Targets, Ingredients), then structure Recipes, then connect the lifecycle (Preparation, Consumption, Pantry deduction), then the derived supply truths (Shopping Lists, Price History, Stores), then the outcome and automation truths. A truth cannot be answer-certified before the truths it derives from are.

---

*Meal Intelligence Truth Certification Standard v1.0. Defines the bar; does not clear it. Certification runs are executed per the roadmap, evidence-gated, one truth at a time.*
