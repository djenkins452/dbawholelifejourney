# What's for Dinner? — WLJ Meal Intelligence Pillar

**Status:** COMPLETE (Backend + Frontend + Activation + Preview + Photo Intelligence)
**Created:** 2026-03-01
**Last Updated:** 2026-03-02

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
**Status:** COMPLETE

**Objective:** Convert recipes from plain text to structured, normalized ingredients linked to the FoodItem library.

**Models:**
- `Ingredient` — Canonical ingredient with category, storage info, substitution links
- `RecipeIngredient` — Structured link between Recipe and Ingredient with quantity/unit

**Services:**
- `IngredientParsingService` — Parse free text ("2 cups diced chicken breast") into structured data

**Deliverables:**
- [x] Create `apps/meals/` app structure
- [x] Add to INSTALLED_APPS
- [x] Ingredient model with fields: canonical_name, aliases, category, nutrition_source FK, carb_density, protein_density, storage_type, shelf_life_days, substitution_group, low_carb_alternative
- [x] RecipeIngredient model: recipe FK, ingredient FK, quantity, unit, preparation_notes, order_index
- [x] IngredientParsingService with deterministic parsing + AI fallback
- [x] Unit normalization (cups→ml, oz→g, etc.)
- [x] IngredientMatchingService (exact, alias, fuzzy)
- [x] 50+ parsing test scenarios
- [x] Admin registration

---

### Phase 2: Household Domain
**Status:** COMPLETE

**Objective:** Support multi-user households with shared meal planning.

**Models:**
- `Household` — name, primary_user, grocery_cycle_days
- `HouseholdMembership` — household, user, role
- `DietaryProfile` — carb/protein/calorie targets, diabetes flags

**Deliverables:**
- [x] Household model
- [x] HouseholdMembership model with admin/member roles
- [x] DietaryProfile model with diabetes_sensitive flag
- [x] Multi-user isolation tests
- [x] Permission enforcement tests (unique_together)

---

### Phase 3: Pantry & Inventory
**Status:** COMPLETE

**Objective:** Track what's in the household pantry with confidence scoring and expiration awareness.

**Models:**
- `PantryItem` — household, ingredient, quantity, confidence, expiration
- `InventoryTransaction` — delta tracking for pantry changes

**Services:**
- `InventoryGapService` — Compare recipe needs vs pantry stock

**Deliverables:**
- [x] PantryItem model with confidence_score and expiration tracking
- [x] InventoryTransaction model (manual, receipt, meal_plan sources)
- [x] InventoryGapService: missing, partial, expiring detection
- [x] Confidence decay algorithm (5%/day after 3 days, min 10%)
- [x] find_pantry_expiring_soon() utility
- [x] decay_all_pantry_confidence() batch utility
- [x] 27 inventory gap tests

---

### Phase 4: Recipe Nutrition Bridge
**Status:** COMPLETE

**Objective:** Calculate accurate per-serving nutrition for recipes using structured ingredients.

**Services:**
- `RecipeNutritionService` — Aggregate RecipeIngredient→FoodItem nutrients

**Deliverables:**
- [x] Nutrition aggregation from RecipeIngredient→FoodItem (18 nutrient fields)
- [x] Per-serving computation
- [x] Result caching (invalidate on ingredient edit)
- [x] Diabetes flag awareness (>45g carbs/serving)
- [x] get_recipe_macro_summary() for quick display
- [x] 25 macro accuracy tests

---

### Phase 5: Meal Scoring Engine
**Status:** COMPLETE

**Objective:** Rank recipes for "What's for dinner?" using deterministic scoring + AI re-ranking.

**Services:**
- `MealScoringService` — Multi-factor scoring with transparent weights

**Scoring factors (deterministic, weights sum to 1.0):**
- Inventory availability (weight: 0.25)
- Expiration urgency (weight: 0.15)
- Carb alignment (weight: 0.15)
- Protein alignment (weight: 0.10)
- Calendar time match (weight: 0.10)
- Grocery avoidance (weight: 0.15)
- Historical frequency (weight: 0.10)

**Deliverables:**
- [x] Deterministic scoring with weighted factors
- [x] Explanation block generation (top 3 factors)
- [x] PIE rules: MealFrequencyRule, PantryWasteRule, NutritionGapRule
- [x] PRIE rules: GroceryNeedsProjection, MealPlanAdherenceProjection
- [x] PGE rules: DinnerSuggestionGuidance, PantryAlertGuidance, MealPlanReminderGuidance
- [x] SAE state builder: build_meals_state() registered in MODULE_BUILDERS
- [x] Score stability tests + diabetes awareness tests
- [x] rank_recipes() for batch scoring

---

### Phase 6: Meal Plan Model
**Status:** COMPLETE

**Objective:** Generate optimized weekly meal plans.

**Models:**
- `MealPlan` — household, date range, projected cost, confidence
- `MealPlanEntry` — individual meal assignments with inventory impact

**Services:**
- `WeeklyOptimizationService` — 3-7 day plans minimizing waste/trips

**Deliverables:**
- [x] MealPlan model
- [x] MealPlanEntry model with inventory_impact_snapshot
- [x] WeeklyOptimizationService (greedy algorithm)
- [x] save_meal_plan() persistence
- [x] Store trip estimation
- [x] 12 optimization tests

---

### Phase 7: Receipt to Pantry Pipeline
**Status:** COMPLETE

**Objective:** Scan grocery receipts to auto-update pantry inventory.

**Models:**
- `Receipt` — raw text, parsed JSON, store, total
- `ReceiptItem` — matched ingredient, quantity, unit

**Services:**
- `ReceiptParsingService` — OCR→structured items→pantry update

**Deliverables:**
- [x] Receipt model with scan_log FK
- [x] ReceiptItem model
- [x] ReceiptParsingService (store/date detection, line item parsing)
- [x] Ingredient matching with confidence scoring
- [x] process_receipt_to_pantry() auto-update with InventoryTransactions
- [x] 10+ receipt parsing tests

---

### Phase 8: Advanced Intelligence
**Status:** COMPLETE

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
- [x] SubstitutionEngine: low-carb alternatives, substitution groups, pantry-based
- [x] EmotionalContextOverlay: mood→suggestion type (comfort, quick, healthy, balanced)
- [x] DecisionFatigueMode: 3-choice simplified with labels
- [x] FaithCalendarIntegration: fasting day detection
- [x] FinanceOverlay: weekly budget context from receipts
- [x] PredictiveGroceryCycle: consumption rate projection, expiring alerts
- [x] ProactiveNudgeScheduler: max 2/day, priority-ordered (expiring > plan > grocery)

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
| 1. Ingredient Normalization | COMPLETE | 2026-03-01 | 2026-03-01 | 0001_initial | 71 | Foundation: parsing, unit conversion, matching |
| 2. Household Domain | COMPLETE | 2026-03-01 | 2026-03-01 | 0001_initial | 8 | Household, membership, dietary profile |
| 3. Pantry & Inventory | COMPLETE | 2026-03-01 | 2026-03-01 | 0001_initial | 27 | Gap analysis, confidence decay, expiration |
| 4. Recipe Nutrition Bridge | COMPLETE | 2026-03-01 | 2026-03-02 | — | 25 | 18-nutrient aggregation, caching, diabetes flag |
| 5. Meal Scoring Engine | COMPLETE | 2026-03-02 | 2026-03-02 | — | 43 | 7-factor deterministic scoring + PIE/PRIE/PGE/SAE |
| 6. Meal Plan Model | COMPLETE | 2026-03-02 | 2026-03-02 | 0001_initial | 12 | Greedy optimizer, save_meal_plan |
| 7. Receipt to Pantry | COMPLETE | 2026-03-02 | 2026-03-02 | 0001_initial | 10 | OCR parsing, pantry auto-update |
| 8. Advanced Intelligence | COMPLETE | 2026-03-02 | 2026-03-02 | — | 0 | Substitution, emotional, faith, finance, nudges |

**Total tests: 193+**

---

## Services Created

| Service | Phase | File | Purpose |
|---------|-------|------|---------|
| IngredientParsingService | 1 | `apps/meals/services/ingredient_parser.py` | Parse free text → structured ingredients |
| UnitConversionService | 1 | `apps/meals/services/unit_conversion.py` | Normalize units (cups→ml, oz→g) |
| IngredientMatchingService | 1 | `apps/meals/services/ingredient_matching.py` | Match parsed names to Ingredient records |
| InventoryGapService | 3 | `apps/meals/services/inventory_gap.py` | Compare recipe needs vs pantry stock |
| RecipeNutritionService | 4 | `apps/meals/services/recipe_nutrition.py` | Aggregate per-serving nutrition from FoodItem |
| MealScoringService | 5 | `apps/meals/services/meal_scoring.py` | 7-factor deterministic scoring + ranking |
| WeeklyOptimizationService | 6 | `apps/meals/services/weekly_optimizer.py` | Greedy meal plan generation |
| ReceiptParsingService | 7 | `apps/meals/services/receipt_parser.py` | OCR → structured items → pantry update |
| SubstitutionEngine | 8 | `apps/meals/services/substitution_engine.py` | Ingredient swaps (diabetes-aware) |
| AdvancedIntelligence | 8 | `apps/meals/services/advanced_intelligence.py` | Emotional, faith, finance, nudge overlays |

---

## Intelligence Engine Integration

| Engine | File | Rules/Functions |
|--------|------|-----------------|
| **SAE** | `apps/core/ai_state/state_builder.py` | `build_meals_state()` — pantry status, active plans, dietary profile |
| **PIE** | `apps/core/ai_insights/rules_meals.py` | MealFrequencyRule, PantryWasteRule, NutritionGapRule |
| **PRIE** | `apps/core/ai_predictions/prediction_rules_meals.py` | GroceryNeedsProjection, MealPlanAdherenceProjection |
| **PGE** | `apps/core/ai_guidance/guidance_rules_meals.py` | DinnerSuggestionGuidance, PantryAlertGuidance, MealPlanReminderGuidance |

---

## Migrations Applied

| Migration | Phase | Description |
|-----------|-------|-------------|
| `meals/0001_initial` | 1-7 | All 11 models: Ingredient, RecipeIngredient, Household, HouseholdMembership, DietaryProfile, PantryItem, InventoryTransaction, MealPlan, MealPlanEntry, Receipt, ReceiptItem |
| `users/0071_add_meals_module_definition` | 9 | Add Meals ModuleDefinition for sidebar navigation |

---

## Phase 9: Frontend Implementation

**Status:** COMPLETE
**Completed:** 2026-03-02

**Objective:** Build the full UI layer — views, templates, CSS, navigation, UAIO intents — so users can access the Meal Intelligence system through the web interface.

**Deliverables:**
- [x] 10 class-based views in `apps/meals/views.py` (dashboard, suggestions, pantry + 3 AJAX, plan + generate, receipts, receipt detail, recipe intelligence)
- [x] 12 URL routes in `apps/meals/urls.py`
- [x] 6 main templates: dashboard, suggestions, pantry, meal_plan, receipt_upload, recipe_detail
- [x] 1 receipt detail template
- [x] 6 partials: subnav, meal_card, confidence_meter, macro_bar, risk_badge, reasoning_block
- [x] Comprehensive CSS (`static/css/meals.css`, ~800 lines, responsive)
- [x] Sidebar navigation via ModuleDefinition data migration
- [x] UAIO intents: suggest_dinner, plan_meal, scan_receipt, add_pantry_item
- [x] CoS context builder for conversational routing
- [x] 28 view tests (all passing)

**Files Created:**
- `apps/meals/views.py` — 10 views with MealsHouseholdMixin
- `apps/meals/urls.py` — 12 URL patterns
- `templates/meals/` — 7 main templates + 6 partials
- `static/css/meals.css` — Responsive design system
- `apps/users/migrations/0071_add_meals_module_definition.py`
- `apps/meals/tests/test_views.py` — 28 tests

**Files Modified:**
- `config/urls.py` — Added meals URL include
- `apps/core/context_processors.py` — Added meals to CORRECT_ROUTES
- `apps/core/ai_orchestrator/intent_engine.py` — Added MEALS_INTENTS
- `apps/core/ai_orchestrator/cos_context.py` — Added meals context builder

---

## Phase 10: Progressive Intelligence Activation

**Status:** COMPLETE
**Completed:** 2026-03-02

**Objective:** Enforce minimum data thresholds before enabling meal scoring. Prevent low-quality suggestions and broken first impressions. Guide users through a strategic onboarding flow.

**Activation Thresholds:**
- PantryItem count >= 5
- Recipe count >= 3

**State Diagram:**
```
┌─────────────┐     Threshold Met     ┌──────────────┐
│  Setup Mode │ ──────────────────────>│ Intelligence │
│  (blocked)  │                        │   Active     │
└──────┬──────┘                        └──────────────┘
       │                                      │
       ▼                                      ▼
 ┌───────────┐                         ┌────────────┐
 │  Wizard   │                         │ Normal UI  │
 │ /setup/   │                         │ Dashboard  │
 └───────────┘                         └────────────┘
```

**Deliverables:**
- [x] `MealActivationService` (`apps/meals/services/activation.py`) with cached threshold checks
- [x] `meals_activated_at` timestamp on Household model
- [x] Dashboard Setup Mode hero with progress bars and guided actions
- [x] Activation Moment hero (shown within 30 minutes of crossing threshold)
- [x] `MealsSetupView` 3-step wizard at `/meals/setup/`
- [x] Suggestions page activation gate (blocks scoring below threshold)
- [x] CoS context includes activation state (setup_needed / activated)
- [x] Dashboard side panel extracted to partial for DRY
- [x] Setup wizard CSS (progress indicators, option cards, step states)
- [x] 29 activation tests (all passing)
- [x] Soft-skip behavior: dashboard accessible but scoring blocked

**Files Created:**
- `apps/meals/services/activation.py` — ActivationStatus dataclass, get_activation_status(), cache
- `apps/meals/migrations/0002_add_meals_activated_at.py` — meals_activated_at field
- `templates/meals/setup.html` — 3-step wizard template
- `templates/meals/partials/_dashboard_side_panel.html` — Extracted side panel
- `apps/meals/tests/test_meal_activation.py` — 29 tests

**Files Modified:**
- `apps/meals/models.py` — Added meals_activated_at to Household
- `apps/meals/views.py` — Activation gates in Dashboard + Suggestions + new MealsSetupView
- `apps/meals/urls.py` — Added /setup/ route
- `templates/meals/dashboard.html` — Setup mode, activation moment, normal mode states
- `templates/meals/suggestions.html` — Setup Required gate
- `apps/core/ai_orchestrator/cos_context.py` — Activation state in meals context
- `static/css/meals.css` — Setup mode + wizard + activation moment styles
- `apps/meals/tests/test_views.py` — Updated tests for activation gate behavior

---

## Phase 11: Power Preview & Anticipation Layer

**Status:** COMPLETE
**Completed:** 2026-03-02

**Objective:** Transform Setup Mode from a data-collection prompt into a premium capability showcase. Create anticipation by showing locked previews of what activates after initialization.

**Design Philosophy:**
- Setup Mode should sell value, not ask for data
- Locked preview cards demonstrate system power before activation
- Capability-unlock language positions the system as a household optimization engine
- Every element communicates: "This system is worth the 3-minute setup"

**Deliverables:**
- [x] "Kitchen Intelligence Initialization" hero title with 6 capability tags (blood sugar protection, protein alignment, waste reduction, calendar awareness, grocery efficiency, family scaling)
- [x] 3 locked preview cards: Optimized Dinner (mock score 87, Chicken Stir Fry), Expiration Intelligence (mock waste alert), Grocery Optimization (mock weekly stats)
- [x] "Why This Matters" side panel replacing generic setup explanation
- [x] Setup wizard preamble: "You're 3 minutes away from activating a household optimization engine"
- [x] Capability-unlock step descriptions throughout wizard
- [x] Enhanced post-activation messaging: "Blood sugar protection, waste reduction, and dinner optimization are now active"
- [x] CSS: capability grid, locked preview cards with gradient overlay, lock icon badges, preview stats
- [x] 2 new tests: capability tag rendering, locked preview card rendering
- [x] All 59 meals tests passing

**Files Modified:**
- `templates/meals/dashboard.html` — Capability grid, locked preview cards section, updated messaging
- `templates/meals/setup.html` — Preamble, capability-unlock language, enhanced activation message
- `static/css/meals.css` — ~150 lines for new components
- `apps/meals/tests/test_meal_activation.py` — Updated assertions + 2 new tests
- `apps/meals/tests/test_views.py` — Updated dashboard assertion

---

---

## Phase 12 — Pantry Photo Intelligence (Session-Based)

**Status:** COMPLETE
**Completed:** 2026-03-02

**Objective:** Allow users to scan sections of their kitchen (fridge, pantry shelf, freezer) with photos, let AI detect food items, and confirm before adding to pantry. Session-based architecture with confidence tracking and drift modeling.

### Session Architecture

Each photo scan creates a `PantryScanSession` with:
- **Location type:** fridge, pantry, freezer
- **1-5 photo uploads** per session
- **AI detection pipeline:** Vision AI → label extraction → ingredient matching → confidence scoring
- **No auto-add:** All detections require user confirmation before PantryItem creation

### Models

| Model | Purpose |
|-------|---------|
| `PantryScanSession` | Session tracking: household, location, confidence, items detected/confirmed |
| `PantryPhotoUpload` | Individual photo with raw detection JSON |
| `PantryPhotoDetection` | Single detected item with confidence, matched ingredient, confirm/reject status |

### Flow

```
Select Location → Upload 1-5 Photos → AI Detection →
Ingredient Matching → Guided Confirmation →
Pantry Update → Session Confidence Score
```

### Confidence Modeling

- **Detection confidence:** Per-item AI confidence score (0-1)
- **Session confidence:** Average of confirmed detection scores
- **Drift calculation:** Overall pantry confidence decays based on:
  - Item age (5%/day after 3 days, min 10%)
  - Scan staleness (extra penalty if last scan >14 days ago)
- **Status levels:** high (≥75%), moderate (≥50%), low (≥25%), critical (<25%)

### Confirmation Flow

- User reviews detected items with editable ingredient dropdown and quantity
- Confirmed items → create/update PantryItem + InventoryTransaction (source="photo_scan")
- Rejected items → ignored, no pantry modification
- Duplicate ingredients within same session → only first confirmed

### CoS Integration

CoS context builder now includes:
- `overall_pantry_confidence` — drift-adjusted confidence score
- `days_since_last_scan` — for staleness detection
- `items_unconfirmed` — low-confidence item count

### Routes

| URL | View | Purpose |
|-----|------|---------|
| `/meals/pantry/scan/` | `PantryScanStartView` | POST: create session + upload photos |
| `/meals/pantry/scan/<id>/confirm/` | `PantryScanConfirmView` | GET: review, POST: confirm/cancel |
| `/meals/pantry/sessions/` | `PantryScanSessionsView` | Session history with pagination |

### Limitations

- Requires OpenAI Vision API (gpt-4o)
- Max 5 photos per session, 10MB per photo
- Detection quality depends on photo clarity and lighting
- No lifetime session cap
- Nudge system structured but not yet implemented

### Files Created/Modified

**New files:**
- `apps/meals/services/pantry_photo_detection.py` — Detection service + session service
- `apps/meals/tests/test_pantry_photo_scan_sessions.py` — 32 tests
- `templates/meals/pantry_scan_confirm.html` — Confirmation UI
- `templates/meals/pantry_scan_sessions.html` — Session history page
- `apps/meals/migrations/0003_phase12_pantry_photo_intelligence.py`

**Modified files:**
- `apps/meals/models.py` — 3 new models + photo_scan source choice
- `apps/meals/views.py` — 3 new views + pantry view scan sessions
- `apps/meals/urls.py` — 3 new routes
- `templates/meals/pantry.html` — Scan buttons + session history section
- `static/css/meals.css` — ~300 lines for scan components
- `apps/core/ai_orchestrator/cos_context.py` — Pantry confidence in CoS

### Test Coverage

32 tests covering: session creation, detection creation, confirmation creates PantryItem, rejection does not create PantryItem, overall_confidence calculation, drift calculation, multiple sessions allowed, duplicate detection handling, ingredient overrides, transaction source validation.

---

*This document is updated after each phase completion.*
