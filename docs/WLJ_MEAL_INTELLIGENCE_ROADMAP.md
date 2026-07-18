# WLJ Meal Intelligence — Implementation Roadmap

**Version:** 1.0
**Authority:** The implementation plan engineering follows to realize the Meal Intelligence architecture. Sequenced by dependency, not by feature appeal.
**Companion to:** `docs/WLJ_MEAL_INTELLIGENCE_ARCHITECTURE.md` (governing architecture) and `docs/WLJ_MEAL_INTELLIGENCE_TRUTH_CERTIFICATION.md` (certification standard).
**Scope note:** This roadmap defines *milestones*, not implementation prompts and not code. No time estimates. Each milestone is executed and certified before the next begins where a dependency exists. Chief of Staff integration is out of scope for the entire roadmap.

---

## How to read this roadmap

The architecture has two mandatory foundations, and everything else composes on them: **(F1) recipes are structured at write time**, and **(F2) the preparation/consumption execution spine exists**. Until F1 exists, recipe-derived truth is starved; until F2 exists, the lifecycle does not close. The milestones are ordered so these foundations come early, the truths that depend on them come next, and genuinely new external capability comes last.

Two rules apply to **every** milestone and are not repeated in each:
- **Household-readiness constraint:** every supply/operational entity created or touched carries a `Household` reference; every consumption/health entity carries a `User` reference. We design for a future multi-person household; we do not build household product mechanics (invitations, roles, permissions, allocation).
- **Preserve production assets:** the receipt vision pipeline, confirmation-gated ingestion, pantry photo scan, inventory ledger, `FoodEntry`, the glucose classifier, food search, barcode, and the nutrition-math authority are constraints — consumed, relocated if necessary, never rewritten.

Each milestone advances specific truths up the certification ladder; the "Certifies" line names them.

---

## Milestone 1 — Canonical Truth Consolidation

**Objective.** Eliminate the fragmentation that makes downstream truth unreliable: collapse duplicate producers to one, converge duplicate calculations, and retire dead/duplicate code — before any new capability is built on top.

**Dependencies.** None. This is the safe foundation.

**Major deliverables.**
- One canonical `NutritionTarget` store (absolute grams authoritative); percentage/other stores become read-through projections.
- All nutrition totals routed through the single nutrition-calculation authority; the stray aggregate that omits the active-status filter corrected.
- Duplicate grocery-need projection reduced to one producer.
- Dead/legacy code retired (superseded receipt writer, dormant sync fallback, unused overlays consciously wired or removed, stale nav backups).
- A single nutrition page-summary provider fed by the same query layer the page render uses.

**Risks.** Target consolidation touches multiple read surfaces (nutrition page, dashboard tile) — a wrong reconciliation could shift displayed numbers. Mitigation: consolidate onto the existing math authority and verify identical output across all consumers before removing the old paths.

**Acceptance criteria.** One target store with all consumers reading it identically; one daily-total value per day regardless of screen; no duplicate producers remain; dead code removed with the app check clean. **Certifies:** Nutrition Targets → M2, Ingredients confirmed M2–M3.

---

## Milestone 2 — Recipe Ownership & Enrichment (Foundation F1)

**Objective.** Establish Meal Intelligence as the canonical owner of recipes and guarantee that every recipe is fully structured at write time, so recipe nutrition, gap analysis, scoring, and substitution operate on real data.

**Dependencies.** M1 (nutrition math authority stable, needed for recipe nutrition).

**Major deliverables.**
- Canonical recipe ownership under Meal Intelligence, with the production recipe capture/import/scan/browse capabilities preserved and relocated intact (not rewritten).
- Structured ingredient decomposition produced at the recipe write boundary (save, scan, and bulk import), using the existing parser and ingredient matcher.
- Recipe nutrition derived deterministically and reproducibly from structured ingredients → the food reference library.
- Recipe provenance/source dimension (WLJ / import / internet / cookbook / AI / family) and person-scoped recipe relationships (favorite, rating, note, personal modification) modeled separately from the shared record.
- Legacy able to project meaning onto the recipe without owning it.

**Risks.** (a) Relocating recipe ownership is a data-move with existing references — must preserve every recipe and its links. (b) Free-text → structured parsing has inherent ambiguity; low-confidence parses must be surfaced for confirmation, never silently guessed (capture ≠ activation). Mitigation: confirmation-gated enrichment; provenance/confidence on every structured line; reversible migration.

**Acceptance criteria.** Every newly written recipe has structured ingredients with confidence; recipe nutrition returns a real per-serving result with provenance; a person's favorite/rating/note does not mutate the shared recipe; Legacy annotations attach without ownership. **Certifies:** Recipes → M3.

---

## Milestone 3 — Lifecycle Connectivity (Foundation F2, the spine)

**Objective.** Close the food lifecycle: make cooking and eating first-class events that deterministically update inventory and nutrition — the transition that turns features into an operating system.

**Dependencies.** M2 (real recipe nutrition is required for consumption to carry macros).

**Major deliverables.**
- A `PreparationEvent` that consumes shared pantry stock (emitting inventory-deduction transactions with a valid source) and produces leftovers back into inventory.
- A consumption bridge: preparing/eating a planned or recipe meal writes person-scoped `FoodEntry` consumption carrying the recipe's real macros, attributed per person.
- Leftovers modeled as pantry-tracked items produced by preparation and decremented on consumption.
- Meal-history truth (what was cooked/eaten) distinct from raw intake, derivable from the events.
- The household→person scope seam realized at exactly this point (preparation is household; consumption is person).

**Risks.** This is the highest-value and highest-coordination milestone: it spans the household/person boundary and two ledgers. A wrong scoping here would be expensive to unwind. Mitigation: the boundary is already specified in the architecture; deduction and consumption are separate emissions from one user action (Capture Once), each reproducible from its ledger.

**Acceptance criteria.** One "I cooked / I ate this" action deterministically deducts the correct pantry quantities, creates leftovers, and logs per-person nutrition with real macros — with every downstream truth reproducible from the events and no double entry. **Certifies:** Meal Preparation, Leftovers → M4/M5; Pantry deduction → M5; Consumption → M5.

---

## Milestone 4 — Supply & Inventory Intelligence

**Objective.** Complete the supply-side derived truths and make pantry maintenance reliable, so planning and shopping run on accurate, current state.

**Dependencies.** M2 (structured recipes for gap analysis) and M3 (pantry reflects consumption).

**Major deliverables.**
- A persisted, owned `ShoppingList` deterministically derived from plan − pantry; the orphaned external list retired/absorbed; the missing navigation surface added.
- `PriceObservation` emitted per confirmed receipt item; canonical `Store` (and `Brand`) reference identity introduced; price history queryable.
- Scheduled pantry maintenance (confidence decay, expiration surfacing) moved off the read path onto background computation.
- Recipe-vs-pantry gap analysis and grocery projection running on real structured data, single-producer.

**Risks.** Background scheduling must obey the request-path-safety rule (no heavy compute on request; pre-compute and read). Price/store introduction must not retro-break existing receipt routing. Mitigation: follow the established safe-enqueue/pre-compute pattern; additive reference entities.

**Acceptance criteria.** A shopping list is generated deterministically from a plan and reflects current pantry; price history accrues automatically from receipts; pantry confidence/expiration update on schedule, not on read. **Certifies:** Shopping Lists → M4, Price History → M4, Stores → M2–M3, Pantry → M4.

---

## Milestone 5 — Automation (Capture Once completeness)

**Objective.** Ensure every capture event fans out to *every* truth that depends on it, and eliminate any remaining place the user must do duplicate work.

**Dependencies.** M1–M4 (the truths that capture events feed must exist and be single-sourced).

**Major deliverables.**
- End-to-end verification and completion of the three Capture Once chains (receipt, preparation, consumption) so each one action updates every listed downstream truth.
- Proactive, deterministic surfaces that require no user input: expiring-item surfacing, leftover reuse suggestions, grocery-cycle timing, restock projection — all reading pre-computed truth.
- Any residual manual reconciliation step identified and removed.

**Risks.** Automation must never fabricate truth — projections and suggestions are facts (numbers/dates), not verdicts, and must be clearly derived. Mitigation: automation reads existing deterministic truth only; no new inference layer.

**Acceptance criteria.** For each capture type, a single user action is shown to update every dependent truth with nothing entered twice; proactive surfaces derive entirely from pre-computed truth on the request path. **Certifies:** all lifecycle truths → M5.

---

## Milestone 6 — External Integrations

**Objective.** Extend beyond WLJ's boundary — the only genuinely net-new external capability — as adapters over already-certified truth.

**Dependencies.** M4 (a real shopping list and store/price truth to act on) and M5 (reliable propagation).

**Major deliverables.**
- Grocery ordering / delivery as an adapter that consumes a `ShoppingList` / `ShoppingTrip` (provider-agnostic; never a new core store).
- Price/coupon optimization and store optimization over accrued price history.
- Additional capture modalities (smart-kitchen, vision-based updates, garden harvest) as new inventory-ledger sources.

**Risks.** External providers introduce failure modes, credentials, and irreversible actions — all of which sit behind a seam and require explicit user confirmation for any outward action. Mitigation: adapters over the provider-agnostic boundary; ordering is a confirmed action, never automatic.

**Acceptance criteria.** An external action is driven entirely from certified internal truth through an adapter, with user confirmation for anything outward-facing and no change to the core domain model. **Certifies:** external-action extension points validated without core redesign.

---

## Cross-cutting: certification track

Certification is not a milestone; it runs alongside every milestone. As each milestone completes, the truths it delivers are advanced up the ladder in `WLJ_MEAL_INTELLIGENCE_TRUTH_CERTIFICATION.md` — structurally certified (G1–G6), then answer-certified (G7) against their representative deterministic questions, then lifecycle-connected (M5). A truth is never certified ahead of the truths it derives from.

## Cross-cutting: household readiness

Woven through M1–M5, never a separate build: every entity carries its scope reference from creation so that a future household-activation milestone (out of scope here) can light up multi-person behavior without a data-model redesign. The safety-union / per-person-target rule is honored anywhere planning reconciles multiple eaters.

---

## Post-roadmap (explicitly out of scope now)

- **Household activation** — turning the designed-for multi-person shape into a shipped multi-person product (membership UX, per-member views, shared vs private surfaces).
- **Chief of Staff integration** — the CoS consuming this domain's certified truth. Addressed in the CoS workstream, after the domain is answer-certified.

---

*Meal Intelligence Implementation Roadmap v1.0. Milestones are dependency-ordered; foundations (F1 recipe enrichment, F2 the execution spine) come first. No implementation has begun.*
