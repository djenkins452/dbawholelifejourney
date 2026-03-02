# What's for Dinner? — WLJ Meal Intelligence Pillar

**Status:** IN PROGRESS
**Created:** 2026-03-01
**Last Updated:** 2026-03-01

---

## Vision

Transform WLJ from a nutrition tracker into a household meal intelligence system. Answer the daily question "What's for dinner?" with personalized, nutrition-aware, inventory-conscious, budget-friendly recommendations that respect dietary needs, calendar constraints, and emotional context.

**Core principle:** Deterministic scoring first, AI ranking second. Every recommendation is explainable and evidence-backed.

---

## Domain Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    MEAL INTELLIGENCE                     │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │Ingredient│  │Household │  │  Pantry  │             │
│  │Normalize │→ │  Domain  │→ │Inventory │             │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘             │
│       │              │              │                    │
│  ┌────▼─────┐  ┌────▼─────┐  ┌────▼─────┐             │
│  │ Recipe   │  │   Meal   │  │ Receipt  │             │
│  │Nutrition │→ │ Scoring  │→ │→ Pantry  │             │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘             │
│       │              │              │                    │
│       └──────┐  ┌────▼─────┐  ┌────┘                   │
│              │  │Meal Plan │  │                         │
│              └→ │Optimizer │ ←┘                         │
│                 └────┬─────┘                            │
│                      │                                  │
│              ┌───────▼──────────┐                       │
│              │    Advanced      │                       │
│              │  Intelligence    │                       │
│              │ (Substitution,   │                       │
│              │  Emotional,      │                       │
│              │  Finance, Faith) │                       │
│              └──────────────────┘                       │
└─────────────────────────────────────────────────────────┘
```

**New app:** `apps/meals/` — bridges `apps/life/` (recipes, shopping) and `apps/health/` (nutrition, food items)

---

## Existing Assets (Leveraged)

| Asset | Location | Status |
|-------|----------|--------|
| Recipe model (plain text) | `apps/life/models.py:901` | Extend with structured ingredients |
| FoodItem library (1.9M+) | `apps/health/models.py:2476` | Link as nutrition source |
| FoodEntry tracking | `apps/health/models.py:2674` | Feed meal history |
| MealTemplate | `apps/health/models.py:4668` | Inform scoring |
| ShoppingList/Item | `apps/life/models.py:1867` | Auto-generate from plans |
| NutritionGoals | `apps/health/models.py:3338` | Constraint for scoring |
| Vision AI/OCR | `apps/scan/` | Receipt parsing |
| Intelligence engines | `apps/core/ai_*/` | PIE/PRIE/PGE rules |
| CoS context | `apps/cos/` + `apps/core/ai_orchestrator/cos_context.py` | Inject meal state |

---

## Phase Breakdown

### Phase 1: Ingredient Normalization (FOUNDATION)
**Status:** IN PROGRESS

**Objective:** Convert recipes from plain text to structured, normalized ingredients linked to the FoodItem library.

**Models:**
- `Ingredient` — Canonical ingredient with category, storage info, substitution links
- `RecipeIngredient` — Structured link between Recipe and Ingredient with quantity/unit

**Services:**
- `IngredientParsingService` — Parse free text ("2 cups diced chicken breast") into structured data

**Deliverables:**
- [ ] Create `apps/meals/` app structure
- [ ] Add to INSTALLED_APPS
- [ ] Ingredient model with fields: canonical_name, aliases, category, nutrition_source FK, carb_density, protein_density, storage_type, shelf_life_days, substitution_group, low_carb_alternative
- [ ] RecipeIngredient model: recipe FK, ingredient FK, quantity, unit, preparation_notes, order_index
- [ ] IngredientParsingService with deterministic parsing + AI fallback
- [ ] Unit normalization (cups→ml, oz→g, etc.)
- [ ] Data migration for existing recipes
- [ ] 50+ parsing test scenarios
- [ ] Admin registration

---

### Phase 2: Household Domain
**Status:** PENDING

**Objective:** Support multi-user households with shared meal planning.

**Models:**
- `Household` — name, primary_user, grocery_cycle_days
- `HouseholdMembership` — household, user, role
- `DietaryProfile` — carb/protein/calorie targets, diabetes flags

**Deliverables:**
- [ ] Household model
- [ ] HouseholdMembership model with admin/member roles
- [ ] DietaryProfile model with diabetes_sensitive flag
- [ ] Auto-create default household per existing user (data migration)
- [ ] Multi-user isolation tests
- [ ] Permission enforcement tests

---

### Phase 3: Pantry & Inventory
**Status:** PENDING

**Objective:** Track what's in the household pantry with confidence scoring and expiration awareness.

**Models:**
- `PantryItem` — household, ingredient, quantity, confidence, expiration
- `InventoryTransaction` — delta tracking for pantry changes

**Services:**
- `InventoryGapService` — Compare recipe needs vs pantry stock

**Deliverables:**
- [ ] PantryItem model with confidence_score and expiration tracking
- [ ] InventoryTransaction model (manual, receipt, meal_plan sources)
- [ ] InventoryGapService: missing, partial, expiring detection
- [ ] Confidence decay algorithm
- [ ] Quantity depletion logic tests
- [ ] Expiration modeling tests

---

### Phase 4: Recipe Nutrition Bridge
**Status:** PENDING

**Objective:** Calculate accurate per-serving nutrition for recipes using structured ingredients.

**Services:**
- `RecipeNutritionService` — Aggregate RecipeIngredient→FoodItem nutrients

**Deliverables:**
- [ ] Nutrition aggregation from RecipeIngredient→FoodItem
- [ ] Per-serving computation
- [ ] Result caching (invalidate on ingredient edit)
- [ ] Diabetes flag awareness
- [ ] Macro accuracy validation tests

---

### Phase 5: Meal Scoring Engine
**Status:** PENDING

**Objective:** Rank recipes for "What's for dinner?" using deterministic scoring + AI re-ranking.

**Services:**
- `MealScoringService` — Multi-factor scoring with transparent weights

**Scoring factors (deterministic):**
- Inventory availability (0-1)
- Expiration urgency (0-1)
- Carb alignment (0-1)
- Protein alignment (0-1)
- Calendar time match (0-1)
- Grocery avoidance (0-1)
- Historical success rate (0-1)

**AI layer:** Re-rank top 5, explain reasoning

**Deliverables:**
- [ ] Deterministic scoring with weighted factors
- [ ] AI re-ranking layer
- [ ] Explanation block generation
- [ ] PIE rules for meal patterns
- [ ] PRIE rules for meal predictions
- [ ] PGE rules for meal guidance
- [ ] SAE state builder for meals module
- [ ] CoS context injection
- [ ] Score stability tests
- [ ] Deterministic weight integrity tests

---

### Phase 6: Meal Plan Model
**Status:** PENDING

**Objective:** Generate optimized weekly meal plans.

**Models:**
- `MealPlan` — household, date range, projected cost, confidence
- `MealPlanEntry` — individual meal assignments with inventory impact

**Services:**
- `WeeklyOptimizationService` — 3-7 day plans minimizing waste/trips

**Deliverables:**
- [ ] MealPlan model
- [ ] MealPlanEntry model with inventory_impact_snapshot
- [ ] WeeklyOptimizationService
- [ ] Auto-generate ShoppingList from plan gaps
- [ ] Calendar event awareness
- [ ] Optimization consistency tests

---

### Phase 7: Receipt to Pantry Pipeline
**Status:** PENDING

**Objective:** Scan grocery receipts to auto-update pantry inventory.

**Models:**
- `Receipt` — raw text, parsed JSON, store, total
- `ReceiptItem` — matched ingredient, quantity, unit

**Services:**
- `ReceiptParsingService` — OCR→structured items→pantry update

**Deliverables:**
- [ ] Receipt model
- [ ] ReceiptItem model
- [ ] ReceiptParsingService using existing OCR
- [ ] Ingredient matching with AI disambiguation
- [ ] PantryItem auto-update
- [ ] 20+ receipt parsing tests

---

### Phase 8: Advanced Intelligence
**Status:** PENDING

**Objective:** Layered intelligence for holistic meal recommendations.

**Services:**
- SubstitutionEngine — ingredient swaps (diabetes-aware, allergy-safe)
- EmotionalContextOverlay — mood-aware comfort food vs healthy
- DecisionFatigueMode — simplified choices when overwhelmed
- FaithCalendarIntegration — Lenten/fasting calendar awareness
- FinanceOverlay — budget-aware recommendations
- PredictiveGroceryCycle — predict shopping needs
- ProactiveNudgeScheduler — max 2 nudges/day, calendar-aware timing

**Deliverables:**
- [ ] SubstitutionEngine with low-carb alternatives
- [ ] EmotionalContextOverlay using journal mood
- [ ] DecisionFatigueMode (3-choice max)
- [ ] FaithCalendarIntegration
- [ ] FinanceOverlay with budget constraints
- [ ] PredictiveGroceryCycle
- [ ] ProactiveNudgeScheduler (max 2/day)
- [ ] Confidence threshold enforcement
- [ ] Transparent reasoning for all suggestions

---

## Engine Integration Plan

| Engine | Integration Point |
|--------|------------------|
| **SAE** | `build_meals_state(user)` — pantry status, active plans, last meal |
| **PIE** | `rules_meals.py` — meal frequency patterns, nutrition gaps, waste patterns |
| **PRIE** | `prediction_rules_meals.py` — grocery needs, meal preferences trajectory |
| **PGE** | `guidance_rules_meals.py` — meal suggestions, pantry alerts, plan reminders |
| **CoS** | Inject meal context into every LLM interaction |
| **UAIO** | Intents: `plan_meal`, `add_pantry_item`, `scan_receipt`, `suggest_dinner` |

---

## Performance Considerations

- **Ingredient parsing:** Cache parsed results, batch FoodItem lookups
- **Scoring engine:** Pre-compute static scores, only recalculate dynamic factors
- **Nutrition calculation:** Cache per-recipe, invalidate on ingredient change
- **Pantry queries:** Index on household + ingredient, confidence decay runs async
- **Meal plan optimization:** Cap at 7-day horizon, use greedy algorithm first
- **Receipt parsing:** Async processing, don't block UI

---

## Risk Register

| Risk | Mitigation |
|------|-----------|
| Ingredient parsing accuracy | Deterministic first, AI fallback, confidence scoring |
| FoodItem matching ambiguity | Fuzzy match + user confirmation for low confidence |
| Pantry quantity drift | Confidence decay over time, periodic confirmation prompts |
| Scoring engine complexity | Transparent weights, deterministic core, AI only for top-N |
| Migration data loss | Non-destructive: add new fields, keep old `ingredients` text |
| Performance on large pantries | Indexed queries, cached aggregations |
| Multi-household complexity | Start with single-user households, extend later |

---

## Completion Tracking

| Phase | Status | Started | Completed | Migrations | Tests | Notes |
|-------|--------|---------|-----------|------------|-------|-------|
| 1. Ingredient Normalization | IN PROGRESS | 2026-03-01 | — | — | — | Foundation phase |
| 2. Household Domain | PENDING | — | — | — | — | |
| 3. Pantry & Inventory | PENDING | — | — | — | — | |
| 4. Recipe Nutrition Bridge | PENDING | — | — | — | — | |
| 5. Meal Scoring Engine | PENDING | — | — | — | — | |
| 6. Meal Plan Model | PENDING | — | — | — | — | |
| 7. Receipt to Pantry | PENDING | — | — | — | — | |
| 8. Advanced Intelligence | PENDING | — | — | — | — | |

---

## Services Created

| Service | Phase | File | Purpose |
|---------|-------|------|---------|
| — | — | — | — |

---

## Migrations Applied

| Migration | Phase | Description |
|-----------|-------|-------------|
| — | — | — |

---

*This document is updated after each phase completion.*
