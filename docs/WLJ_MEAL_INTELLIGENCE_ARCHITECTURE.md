# WLJ Meal Intelligence — Canonical Domain Architecture

**Version:** 1.0 (Governing) · finalized 2026-07-18
**Authority:** Governing architecture for the Meal Intelligence domain. All future Meal Intelligence development conforms to this document; deviations require deliberate amendment, not drift.
**Companion documents:** `docs/WLJ_MEAL_INTELLIGENCE_TRUTH_CERTIFICATION.md` (the certification standard for each food truth) and `docs/WLJ_MEAL_INTELLIGENCE_ROADMAP.md` (the implementation milestones that realize this architecture).
**Audience:** Engineers and architects building any food, nutrition, pantry, recipe, shopping, or meal capability in WLJ.
**Scope note:** This document defines Meal Intelligence as a standalone Personal Truth Domain. It does not describe Chief of Staff integration; the Chief of Staff consumes this domain's truth through the standard truth boundary like any other domain.

---

## Executive Summary

Meal Intelligence is the Whole Life Journey domain responsible for a person's complete relationship with food. Its purpose is not "meal planning" — it is to become the deterministic operating system for the entire food lifecycle: from health goals and nutrition targets, through recipes, planning, shopping, and pantry, into preparation, consumption, and the health outcomes that result, and finally into the historical truth that makes the next cycle smarter.

The domain is organized around a single idea: **the food lifecycle is a stream of events, and every deterministic truth the user sees is a reproducible function of those events.** A user performs one real-world action — scans a receipt, cooks a meal, records that they ate — and Meal Intelligence deterministically propagates every downstream consequence. The user never does the same work twice.

That idea has a name, and it is the domain's defining workflow philosophy: **Capture Once. Reuse Everywhere.** One capture updates every downstream truth that depends on it — automatically, deterministically, without the user reconciling anything. It is not a convenience feature; it is the reason the domain's truth is modeled as events and folds, and it is the test every proposed feature must pass. (Full treatment in its own section below.)

Truth in this domain is partitioned along two axes. **Supply is shared; consumption is personal.** A household has one pantry, one grocery run, one shared recipe library; an individual has their own portions, targets, allergies, and physiological responses. This boundary is load-bearing: it is what allows WLJ to grow into genuine multi-person household support without a redesign, while never diluting the individual as the root of personal truth.

Meal Intelligence owns *what food is and how it functions* — the operational, deterministic truth. It does not own *what food means*; the Legacy domain projects meaning (stories, people, traditions, significance) onto the operational records Meal Intelligence owns.

---

## Product Philosophy

Whole Life Journey is a Personal Truth Platform. It owns the deterministic truth of a person's life; a conversational model reasons over that truth. Meal Intelligence is one truth domain within that platform, and it inherits the platform's discipline:

1. **The domain knows; it does not opine.** Meal Intelligence exposes facts — quantities, dates, macros, gaps, costs. It never encodes a verdict ("you're eating well"). Interpretation belongs to the reasoning layer, not the truth layer.
2. **Determinism where correctness, history, safety, or auditability demand it.** The domain builds deterministic machinery for inventory math, nutrition math, safety composition, event history, and action execution — and nowhere else. Where a capability could be met by better truth rather than more code, the domain improves the truth.
3. **The individual is the root of personal truth.** A household is a shared *context* a person participates in for supply; it is never a competing source of truth about the person.
4. **Simplicity scales down, not up.** As the platform and its models improve, Meal Intelligence should get simpler to reason about — more truth, fewer bespoke mechanisms. New capability is added as a reference library, an event source, or a derived read — not as a new subsystem.

The measure of the domain is whether a person can hand WLJ one action and trust that everything that logically follows from it is now true, everywhere, without their help.

---

## Architectural Principles

These eight principles govern every design decision in the domain.

**P1 — Capture Once. Reuse Everywhere.**
The user performs one action; WLJ performs every deterministic downstream update. A single capture propagates automatically to every truth that depends on it — no duplicate entry, no manual reconciliation. This is the domain's defining product principle and the reason the event-and-fold model below exists. (Detailed in its own section.)

**P2 — Two ledgers are authoritative; their state is a fold.**
Two truths are maintained as immutable, append-only event ledgers, and their "current state" is always a reproducible fold of that history:
- **Inventory** — the `InventoryTransaction` ledger folds into `PantryItem` current state.
- **Consumption** — `FoodEntry` events fold into daily nutrition state.
State is never authored directly where an event can produce it; history is never mutated, only appended. Other events (preparation, leftovers, waste) are *thin records that emit into these two ledgers* — the domain does not multiply ledgers beyond where correctness demands one.

**P3 — Enrich at the write boundary, never lazily on read.**
When a knowledge asset is saved, it is fully structured *then*. A recipe captured from any source is decomposed into structured, matched ingredients at the moment it is written — never left as free text for a read path to interpret later. Read paths may assume their inputs exist because the write path guaranteed them.

**P4 — One truth, one owner, one writer.**
Every entity has exactly one canonical producer. No truth is written by two subsystems; no derived value has two implementations. Duplicate producers are the definition of fragmentation and are prohibited.

**P5 — Capture is separate from activation.**
Ingestion captures *evidence*; a confirmation step commits *truth*. Vision OCR, barcode reads, and pantry photos produce candidate data that becomes canonical only through the confirmation-gated write path. This keeps machine perception from silently mutating a person's truth.

**P5a — Every acquisition method converges on one canonical write, and always degrades to manual.**
Pantry acquisition is deliberately multi-modal — barcode, receipt, vision scan (fridge/pantry/freezer), and **manual entry** — but there is exactly ONE write: `pantry_ingestion.finalize_pantry_item(source=…)`. Each method differs only in how it *perceives* the item; the resulting `PantryItem`, `InventoryTransaction`, container-truth resolution, and domain event are identical. **Manual entry is the universal fallback**: anything a user can buy, grow, cook, or receive — barcode-less produce, homemade food, bulk goods, restaurant leftovers, or an AI-recognition miss — can always be entered by hand and lands in the same canonical truth. A capture method that cannot degrade to manual is incomplete.

**P6 — Supply is household; consumption and health are personal.**
Every entity declares its scope. Supply and operational truth are household-scoped; consumption, targets, preferences, and physiological outcomes are person-scoped. The two scopes meet at exactly one seam (preparation → consumption).

**P7 — Safety composes across the household; individual truth does not.**
Safety constraints (allergies, medical restrictions, intolerances) combine as a **union** across everyone a meal is for — one unsafe member makes the meal unsafe. Nutrition targets, serving sizes, preferences, and health outcomes remain strictly per-person and never merge.

**P8 — Providers live behind a seam.**
All machine-perception and generation capabilities (receipt vision, pantry vision, recipe extraction, AI nutrition estimation, barcode resolution) sit behind a provider-agnostic boundary. The domain depends on the capability, never the vendor.

---

## Canonical Domain Model

The domain decomposes into layers by the *nature* of each truth — its mutability, its scope, and how it is produced. Layer assignment is the first decision for any new entity.

**Reference libraries** — shared, non-personal knowledge; cached from external providers.
`Ingredient` · `FoodItem` · `Store` · `Brand` · `CookingMethod` · `KitchenEquipment` (catalog) · `SeasonalAvailability` · barcode resolution.

**Knowledge assets** — authored, structured, reusable operational content, *accessible* to a household but not "owned" by it in the supply sense (see Scope).
`Recipe` (+ `RecipeIngredient`, `RecipeStep`, `RecipeEquipment`) · `MealTemplate`.

**Standing truth (household)** — durable shared context.
`Household` · `HouseholdMembership` · `StorePreference` · `OwnedKitchenEquipment` · `GroceryCadence`.

**Standing truth (person)** — durable individual facts and preferences.
`NutritionTarget` · `MicronutrientTarget` · `DietaryRestriction` · `FoodAllergy` · `FoodPreference` · `FavoriteRecipe` · `FavoriteFood`.

**Planning (household)** — forward intent, revisable, not yet fact.
`MealPlan` · `MealPlanEntry` · `ShoppingList` · `ShoppingListItem` · `ShoppingTrip` · `MealPrepPlan`.

**Supply & inventory (household)** — current state as a fold of the inventory ledger.
`InventoryTransaction` (ledger) · `PantryItem` (fold) · `Receipt` · `ReceiptItem` · `PantryScanSession`/`PantryPhotoUpload`/`PantryPhotoDetection` · `PriceObservation` · `ExpirationRecord`.

**Execution events** — the immutable spine of what actually happened.
`PreparationEvent` · `Leftover` · `WasteEvent` (household) · `ConsumptionEvent` = `FoodEntry` · `RestaurantMeal` (person).

**Derived & outcome truth** — read-computed, never authored, always reproducible.
`DailyNutritionSummary` · `RecipeNutrition` · `InventoryGapAnalysis` · `GroceryNeedProjection` · `MealGlucoseResponse` and future outcome classifiers.

---

## Canonical Ownership

**Owner** is the single authoritative producer. **Scope** is one of: Reference (shared, non-personal) · Knowledge (household-accessible, person-related) · Household (shared supply/operational) · Person (individual). Legacy appears only as a *projection* of meaning, never as an owner of operational truth.

| Entity | Owner | Scope |
|---|---|---|
| Ingredient | Meal Intelligence | Reference |
| FoodItem (nutrition-labeled) | Health | Reference |
| Store · Brand | Meal Intelligence | Reference |
| CookingMethod · KitchenEquipment (catalog) · SeasonalAvailability | Meal Intelligence | Reference |
| **Recipe** (operational record) | **Meal Intelligence** | **Knowledge** |
| RecipeIngredient · RecipeStep · RecipeEquipment | Meal Intelligence | Knowledge |
| MealTemplate (quick-log) | Health | Person |
| *Recipe meaning* (stories, people, traditions, photos, significance) | **Legacy (projection)** | projects onto recipe |
| Household · HouseholdMembership | Meal Intelligence | Household |
| StorePreference · OwnedKitchenEquipment · GroceryCadence | Meal Intelligence | Household |
| NutritionTarget · MicronutrientTarget | Health | Person |
| DietaryRestriction · FoodAllergy · FoodPreference | Health | Person |
| FavoriteRecipe | Meal Intelligence | Person |
| FavoriteFood (logged) | Health | Person |
| MealPlan · MealPlanEntry | Meal Intelligence | Household |
| ShoppingList · ShoppingListItem · ShoppingTrip · MealPrepPlan | Meal Intelligence | Household |
| InventoryTransaction (ledger) · PantryItem (fold) | Meal Intelligence | Household |
| Receipt · ReceiptItem | Meal Intelligence (→ Finance for spend) | Household |
| PantryScanSession / Upload / Detection | Meal Intelligence | Household |
| PriceObservation · ExpirationRecord | Meal Intelligence | Household |
| PreparationEvent · Leftover · WasteEvent | Meal Intelligence | Household |
| ConsumptionEvent = FoodEntry · RestaurantMeal | Health | Person |
| DailyNutritionSummary · MealGlucoseResponse (+ outcomes) | Health | Person |
| RecipeNutrition · InventoryGapAnalysis · GroceryNeedProjection | Meal Intelligence | derived |

**The governing sentence for Recipe:** *Meal Intelligence owns what a recipe is and how it functions — ingredients, quantities, servings, instructions, nutrition, preparation, substitutions, cost, and planning relationships. Legacy owns what the recipe means. A household has access to the recipe; each person maintains their own relationship with it.*

---

## Household vs Person Scope

This boundary is a hard architectural constraint.

**Household-scoped — the shared supply and operational context (one kitchen):**
Pantry inventory · the inventory ledger · grocery receipts · shopping lists and trips · stores and price history · meal plans · meal preparation · leftovers and food waste · kitchen equipment · grocery cadence · store preferences.

**Person-scoped — irreducibly individual truth:**
Portions consumed · food entries (consumption) · nutrition totals · macro targets · micronutrient targets · dietary restrictions · allergies · food preferences · favorite recipes · glucose and other health responses · dietary goals.

**Recipes are a distinct case — household-*accessible* knowledge, not household-*scoped* supply.**
A recipe is not owned by a household the way a pantry is. It is a knowledge asset the household has *access* to, which may originate from WLJ's own library, an import, a cookbook, the internet, an AI generation, a family source, or another user. Individuals maintain personal relationships *over* shared recipes — favorites, ratings, cooking history, personal notes, personal modifications, and Legacy annotations — without changing who owns the operational record. This distinction is what lets the architecture support shared libraries, public libraries, imports, and future recipe marketplaces without ever re-homing recipe ownership.

**The single seam where scopes cross.**
A `PreparationEvent` (household) consumes shared pantry stock and produces shared leftovers; it optionally attributes servings to individuals, each becoming a `ConsumptionEvent`/`FoodEntry` (person) that Health interprets for that individual's totals and outcomes. Supply flows household → person at exactly this point, and nowhere else.

**Design-for, do not overbuild.**
The multi-person household is a future product; its *shape* is preserved now, its *machinery* is not built now.
- Every household entity carries a `Household` reference from creation — even while a household has exactly one member. This single choice is what averts a later redesign, and it costs nothing today.
- Every person entity carries a `User` reference and is never reachable only through the household. Personal truth is never collapsed to the household.
- The existing `Household`/`HouseholdMembership` models are reused as-is. No invitations, expanded roles, permission matrices, or per-member allocation logic are introduced until a genuine multi-member product requires them.
- Present-day single-person operation is an explicit simplification (a household resolves to one member), never a structural assumption that household equals user.

---

## Truth Ownership

Each entity owns a precise, exclusive slice of truth.

- **Ingredient** owns canonical name, aliases, category, storage type, shelf life, substitution group, density, default unit, and its link to a nutrition source. It does not own quantity-on-hand or nutrient values.
- **FoodItem** owns per-serving macros and micronutrients, serving size, barcode, external identifiers, data-source provenance, and version. It does not own how much a person ate.
- **Recipe** owns the operational definition: title, source/provenance, servings, difficulty, category, tags, images, instructions, and the structured decomposition below. It does not own a person's feelings about it (favorites, notes) or its meaning (Legacy).
- **RecipeIngredient** owns the structured quantity/unit/ingredient-reference/preparation/optionality decomposition of one recipe line — the bridge from captured text to canonical `Ingredient`.
- **NutritionTarget** owns the single authoritative set of a person's calorie and macro targets (grams), limits, and effective dates. It is the one source of "what I am aiming for."
- **FoodAllergy / DietaryRestriction** own the typed, auditable, safety-critical set of what a person cannot or will not eat, with severity.
- **PantryItem** owns current quantity, storage location, confidence, last-confirmed time, and estimated expiration — all *derived from* the inventory ledger. It owns current state, not history.
- **InventoryTransaction** owns the immutable, signed, sourced record of every quantity change. It is the source of pantry truth; `PantryItem` is its fold.
- **Receipt / ReceiptItem** own the evidentiary record of an acquisition. Evidence, not inventory.
- **PriceObservation** owns product × store × time × unit-price — the source of price history.
- **MealPlan / MealPlanEntry** own the intended schedule of recipes across dates and meal types. Intent, never fact.
- **ShoppingList / ShoppingListItem** own the derived, editable set of items required to satisfy plan minus pantry, with purchase status.
- **PreparationEvent** owns the fact that a recipe was prepared, servings made, inventory consumed, and leftovers produced.
- **ConsumptionEvent (FoodEntry)** owns actual intake: food or recipe, portion, time, meal type, context, an immutable nutrient snapshot, and source. Health owns and interprets it.
- **MealGlucoseResponse** owns the classified physiological outcome of a consumption event — the template for all future food-to-outcome truth.
- **DailyNutritionSummary** owns nothing authoritative; it is a reproducible cache of the fold of consumption events.

Where an entity is a **fold** (PantryItem, DailyNutritionSummary), its ledger is authoritative and the fold is disposable and rebuildable. Where an entity is an **event** (InventoryTransaction, FoodEntry, PreparationEvent), it is immutable and append-only.

### Container Truth vs Remaining Truth (the deduction bridge)

A pantry item is a **package** ("1 bottle of ketchup"), but a recipe calls for a **culinary amount** ("2 tbsp"). Bridging the two deterministically requires two distinct truths, kept separate — and, critically, **stored truth is always an exact base quantity; container fractions and percentages are presentation only**:

- **Container Truth** (stable) — the *net contents of one full container*: `PantryItem.net_content` + `net_content_unit` (e.g. 591 ml). It does not change as the container is used, and it is acquisition-independent (a 591 ml bottle holds 591 ml whether it arrived by barcode, receipt, vision, or manual entry).
- **Remaining Truth** (canonical) — the *exact remaining amount*, stored in the base unit in `PantryItem.quantity` with `unit` == `net_content_unit` (e.g. `quantity = 312, unit = "ml"`). WLJ never stores "0.53 bottles" or "53%"; those are **derived at presentation** from `quantity ÷ net_content` (`PantryItem.remaining_containers` / `remaining_percent` / `remaining_display`). Truth stays exact; presentation stays flexible.

Separating stored truth from presentation removes a whole class of drift: there is one exact number in the base unit, and every view (312 ml · 53% · ≈half a bottle · 0.53 bottles) is a pure function of it. The inventory ledger folds to that same base quantity, and deduction subtracts base amounts directly — there is **no container-fraction arithmetic** in the write path.

The **substance properties** that make the bridge possible are canonical and live on the **Ingredient**, shared across every household: `base_measure` (mass / volume / count) and `density_g_per_ml` (what converts mass↔volume — a cup of flour → ml → grams). These are intrinsic to the substance, not to any one person's jar.

Resolution is deterministic and priority-ordered (`services/container_truth.py`): **Open Food Facts `product_quantity` → FoodItem serving × servings-per-container → Ingredient default → ask the user once.** It runs inside the single canonical write (`finalize_pantry_item`), which stores the acquired amount as an exact base quantity, so acquisition method never changes stored truth (*Capture Once, Reuse Everywhere*). The conversion engine (`services/unit_conversion.py`) resolves within-dimension and count↔count freely, mass↔volume **only when a density exists**, and returns `None` for every other pair — **no estimation, ever**. When the one bridging fact is genuinely absent, preparation fails **closed** with the actionable `needs_container_info` — captured **in the preparation workflow itself** ("what size is this bottle?"), which sets the container truth once and makes every future preparation automatic — never a silent dead-end and never a detour to a separate pantry screen.

---

## The Food Lifecycle

The complete lifecycle the domain exists to support, end to end:

```
 Health Goals
      ▼
 Nutrition Targets            (person: NutritionTarget, MicronutrientTarget)
      ▼
 Recipes                      (knowledge: Recipe + structured ingredients)
      ▼
 Meal Plan                    (household: MealPlan/Entry)
      ▼
 Shopping List                (household: derived from plan − pantry)
      ▼
 Shopping Trip → Receipt      (household: acquisition evidence)
      │                        ├──► Finance spend
      │                        └──► Price history (PriceObservation)
      ▼
 Inventory Ledger             (household: InventoryTransaction — authoritative)
      ▼
 Pantry (current state)       (household: PantryItem — fold of the ledger)
      ▼
 Meal Preparation             (household: PreparationEvent
      │                          ├─ emits inventory deduction
      │                          └─ produces Leftover)
      ▼
 Meal Consumed                (person: ConsumptionEvent = FoodEntry)
      ▼
 Nutrition Recorded           (person: DailyNutritionSummary — fold of FoodEntry)
      ▼
 Health Outcomes              (person: MealGlucoseResponse and future classifiers)
      ▼
 Analytics / Historical Truth
      ▼
 Continuous Improvement  ──►  feeds back into Preferences, Targets, and Planning
```

The two transitions in the middle — **Pantry → Preparation** and **Preparation → Consumption** — are the spine of the domain. They are what turn a set of food features into a food operating system: cooking deducts shared supply and produces leftovers; eating logs personal consumption and feeds personal health outcomes. Everything upstream (planning, shopping, pantry) and downstream (nutrition, outcomes, analytics) connects through this spine.

---

## Relationships

Canonical relationships (→ references; ◆ owns/composes; ⇒ emits event; ⟳ derived-from):

```
Household ◆── HouseholdMembership → User
Household ◆── PantryItem ⟳ InventoryTransaction (ledger)
Household ◆── MealPlan ◆── MealPlanEntry → Recipe
Household ◆── ShoppingList ◆── ShoppingListItem → Ingredient
Household ◆── Receipt ◆── ReceiptItem → Ingredient
                   ├─⇒ InventoryTransaction(source=receipt) ⟳→ PantryItem
                   ├─⇒ Finance.Transaction
                   └─⇒ PriceObservation → (Store, Brand, FoodItem)

Recipe ◆── RecipeIngredient → Ingredient → FoodItem      (enrichment at write)
Recipe ◆── RecipeStep → CookingMethod
Recipe → RecipeEquipment → KitchenEquipment(catalog) ← OwnedKitchenEquipment
Recipe ⟳ RecipeNutrition        (derived via RecipeIngredient → FoodItem)
Recipe ← FavoriteRecipe (person) · Legacy annotations (projection)

PreparationEvent → Recipe
      ├─⇒ InventoryTransaction(source=preparation) ⟳→ PantryItem   (deduct)
      ├─⇒ Leftover → PantryItem                                    (produce)
      └─⇒ ConsumptionEvent(s) attributed to persons

ConsumptionEvent = FoodEntry → (FoodItem | CustomFood | Recipe)
      ├─⟳→ DailyNutritionSummary
      ├─⇒ MealGlucoseResponse
      └─ compared against NutritionTarget (never owns it)

Person ◆── NutritionTarget ◆── MicronutrientTarget
Person ◆── DietaryRestriction · FoodAllergy · FoodPreference   (P7 safety union)
```

**Relationship rules that prevent re-fragmentation:**
- A recipe's ingredient list exists as structured `RecipeIngredient` rows the moment the recipe is written (P3); free text is never the canonical form.
- The pantry has both an inbound ledger (acquisition) and an outbound ledger (preparation/waste); it is never mutated except through `InventoryTransaction`.
- `FoodEntry` may reference the `Recipe` and `PreparationEvent` it came from, so consumption is traceable to its source without duplicating recipe data.
- A person's relationship with a recipe (favorite, rating, note, modification) is a separate person-scoped record; it never edits the shared recipe.

---

## Existing Production Assets

The following are production-quality and are **architectural constraints**: the domain consumes them; it does not rebuild them. Their internals are out of scope for redesign.

- **Receipt vision pipeline** — machine-perception OCR with format/HEIC/PDF handling, deduplication, and hallucination guarding. The acquisition-evidence capture stage feeding the inventory ledger.
- **Confirmation-gated ingestion** (the canonical pantry write) — a single authoritative writer with an audit trail. This *is* the reference implementation of P4 and P5, and the pattern every capture modality follows.
- **Pantry photo scanning** — a session-based vision capture modality into the same ledger.
- **Inventory transaction ledger** — the immutable, signed, sourced event store. The reference implementation of P2; extend its sources, never bypass it.
- **`FoodEntry`** — the canonical consumption event, with immutable snapshots, versioning, and audit. No parallel consumption record may be built.
- **Meal glucose response classifier** — the working food-to-health-outcome bridge and the template for future outcome truth.
- **Three-tier food search and barcode resolution** — the canonical name-to-`FoodItem` resolution service.
- **Nutrition calculation authority** — the single deterministic per-serving and aggregation math. All totals converge here; none are re-derived elsewhere.
- **Ingredient library and fuzzy matching** — the normalization layer between captured text and canonical structure.
- **Recipe capture, import, scanning, and browsing** — the recipe vision extraction and bulk-import capabilities relocate into this domain intact under Meal Intelligence ownership; they are preserved, not rewritten.

---

## Architecture Boundaries

- **Meal Intelligence ↔ Health** runs *through the ConsumptionEvent*. Meal Intelligence is authoritative for the lifecycle up to and including "a meal was prepared and eaten"; Health owns and interprets what that intake means physiologically. `FoodEntry` sits on the seam — written by Meal Intelligence's preparation/consumption path, owned by Health. Outcomes never mutate intake; intake never computes outcomes.
- **Meal Intelligence ↔ Legacy** is a *projection*. Legacy references and enriches operational records (recipes, and where relevant meals and traditions) with meaning; it never owns operational truth. Meal Intelligence owns what a thing *is*; Legacy owns what it *means*.
- **Meal Intelligence ↔ Finance** is one-directional: receipts emit spend transactions to Finance.
- **Meal Intelligence ↔ Providers** is provider-agnostic (P8). Vision, extraction, and estimation capabilities are swappable; the domain never names a vendor.
- **Reference vs Knowledge boundary:** `Ingredient` (a supply/recipe unit) and `FoodItem` (a nutrition-labeled product) are deliberately two libraries in a many-to-one relationship — one ingredient maps to many labeled products. This is not duplication; it is the correct separation between "what I cook with" and "what I count nutritionally."

---

## Future Extension Points

The domain grows by adding to three surfaces, never by restructuring:

1. **A new capture modality** (garden harvest, smart-kitchen device, a new scan type) becomes a new `InventoryTransaction` source or capture adapter feeding the existing ledger.
2. **New knowledge** (seasonal availability, coupons, store layouts, equipment) becomes a new reference-library table; nothing downstream changes.
3. **A new outcome** (weight, energy, mood response to food) becomes a new derived classifier over consumption events, following the glucose-response template.
4. **A new personal fact** (a preference, a restriction) becomes a person-scoped standing-truth entity — explicit and auditable.
5. **A new external action** (grocery ordering, delivery, meal subscription) becomes an adapter that consumes a `ShoppingList`/`ShoppingTrip`; never a new core store.

Each of the following future capabilities is a natural extension under this model, requiring no redesign:
family meal planning · household inventory · automatic grocery ordering · multiple grocery providers · restaurant optimization · meal subscriptions · garden planning · seasonal produce · holiday and vacation meal planning · nutrition coaching · food budgeting · price history · coupons · barcode scanning · smart-kitchen devices · vision-based pantry updates · shared and public recipe libraries · future recipe marketplaces · household consumption and shared shopping.

The architecture's extensibility is precisely its reference libraries (add rows), its two event ledgers (add sources), and its derived reads (pure functions). The prerequisites for all of it are the two mandatory foundations: the recipe-enrichment write path (P3) and the preparation/consumption execution spine (P2, P6).

---

## Capture Once. Reuse Everywhere.

This is the domain's defining product principle (P1) and the reason its truth is modeled as events and folds. The user performs one real-world action; WLJ performs every deterministic downstream update. Nothing is entered twice; nothing is reconciled by hand.

**Scanning a grocery receipt — one action:**
```
Receipt scanned  ──►  Inventory ledger updated (items added)
                 ──►  Pantry state recomputed
                 ──►  Purchase / shopping history recorded
                 ──►  Price history updated (PriceObservation)
                 ──►  Budget / spend history recorded (Finance)
                 ──►  Recommendation engine refreshed (grocery projections)
```

**Preparing a meal — one action:**
```
Preparation recorded  ──►  Preparation history updated
                      ──►  Inventory deducted (ledger)
                      ──►  Leftovers created (back into pantry)
                      ──►  Meal history updated
                      ──►  Consumption logging enabled per person
```

**Consuming a meal — one action:**
```
Consumption recorded  ──►  Food entry created
                      ──►  Nutrition totals updated
                      ──►  Health history updated
                      ──►  Outcomes classified (e.g. glucose response)
                      ──►  Analytics, trends, and progress refreshed
```

The propagation is deterministic and reproducible because it is nothing more than appending to a ledger and re-folding the reads that depend on it. This principle is the product-facing purpose of P2 (two ledgers) and P4 (one writer): a single captured event is the *only* place a fact is entered, and every dependent truth derives from it automatically. Any proposed feature that would ask the user to enter the same fact twice violates this principle and is wrong by construction.

---

## Architectural Constraints

Binding rules for all future Meal Intelligence work:

1. Every entity declares its layer and its scope (Reference · Knowledge · Household · Person) at creation.
2. Household entities carry a `Household` reference; person entities carry a `User` reference. Personal truth is never reachable only through a household.
3. Inventory is mutated only through `InventoryTransaction`. Nutrition totals are computed only through the single nutrition-calculation authority. No second producer of either.
4. Recipes are fully structured at write time (P3). Free-text ingredients are never the canonical representation.
5. Machine perception writes candidate evidence; only a confirmation step commits canonical truth (P5).
6. Safety composes as a union across everyone a meal is for; targets, portions, and outcomes never merge (P7).
7. Legacy may project onto operational records but never owns them.
8. External providers are reached only through the provider-agnostic seam (P8).
9. No feature asks the user to enter the same fact twice (P1).
10. Any deviation from this document is made by amending it deliberately — never by drift.

---

## Open Product Decisions

Q1 (recipe ownership), Q2 (household scope), and the household safety-composition rule are decided and encoded above. The following genuinely require Danny's long-term product vision; they are not engineering choices, and each changes the architecture. They may be settled at implementation-planning time.

**OPD-1 — Restaurant meal depth.** Should a restaurant meal remain "I ate out, and what I spent" (a lightweight consumption + spend record), or should it capture full menu-item nutrition (making `RestaurantMeal` a first-class, reference-data-hungry entity with its own external sourcing)? This bounds how much restaurant structure the domain commits to.

**OPD-2 — Preparation as an explicit step or an inferred one.** Is preparation a distinct household action the user takes ("I'm cooking this now" → deduct pantry, create leftovers), after which each person logs their portion — or does logging consumption alone auto-infer the preparation and deduction behind the scenes? This decides whether `PreparationEvent` is a first-class, user-facing event or an internal side effect of consumption. (Household scoping mildly favors an explicit event, since one person often cooks for several who each log their own portion, but this is a product call.)

All previously open questions that could be resolved by engineering have been resolved in this document: `MealTemplate` remains a distinct person-scoped quick-log convenience separate from the recipe knowledge asset; recipe library visibility (private / household / shared / public / imported) is modeled as a source/visibility dimension on the recipe from the start so future shared and public libraries need no re-homing; and household plan reconciliation follows P7 (safety union, per-person targets).

---

*Meal Intelligence Architecture v1.0. This document governs all Meal Intelligence design decisions. Amend it deliberately; do not drift from it.*
