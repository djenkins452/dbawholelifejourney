# WLJ Recipe & "What's for Dinner?" Capability Assessment

**Date:** 2026-03-01
**Scope:** Full technical and architectural investigation

---

## Table of Contents

1. [Phase 1 — Current State Analysis](#phase-1--current-state-analysis)
2. [Phase 2 — Competitive Analysis](#phase-2--competitive-analysis)
3. [Phase 3 — Design Target](#phase-3--design-target)
4. [Phase 4 — Architecture Proposal](#phase-4--architecture-proposal)
5. [Phase 5 — Implementation Roadmap](#phase-5--implementation-roadmap)
6. [Phase 6 — Risk & Complexity](#phase-6--risk--complexity)
7. [Phase 7 — Final Recommendation](#phase-7--final-recommendation)

---

## Phase 1 — Current State Analysis

### 1.1 Recipe Functionality

**Two separate recipe systems exist:**

#### System A: Family Recipe Collection (`apps/life/models.py:898-993`)

```
Recipe (UserOwnedModel)
├── title              CharField(200)
├── description         TextField           # Story behind the recipe
├── ingredients         TextField           # Plain text, one per line ⚠️
├── instructions        TextField           # Plain text
├── prep_time_minutes   PositiveIntegerField
├── cook_time_minutes   PositiveIntegerField
├── servings            PositiveIntegerField
├── difficulty          CharField(easy/medium/hard)
├── category            CharField(50)       # Breakfast, Dinner, etc.
├── tags                JSONField(list)     # vegetarian, quick, etc.
├── source              CharField(200)      # Where recipe came from
├── source_url          URLField
├── image               ImageField          # Upload to life/recipes/
├── notes               TextField           # Variations, tips, memories
├── is_favorite         BooleanField
└── @total_time_minutes (property)          # prep + cook
```

**Full CRUD:** 7 views, 8 URL routes, admin registration, soft delete support.

**Files:**
- Model: `apps/life/models.py:898-993`
- Views: `apps/life/views.py:1096-2493`
- URLs: `apps/life/urls.py:47-158`
- Templates: `templates/life/recipe_list.html`, `recipe_detail.html`, `recipe_form.html`, `recipe_confirm_delete.html`
- Admin: `apps/life/admin.py:57-61`
- Tests: `apps/life/tests/test_models.py:237-276`

#### System B: Meal Templates (`apps/health/models.py:4668-4765`)

```
MealTemplate (UserOwnedModel)
├── name               CharField(200)       # "Turkey Sandwich"
├── description         TextField
├── default_meal_type   CharField           # breakfast/lunch/dinner/snack
├── is_favorite         BooleanField
├── use_count           PositiveIntegerField
├── @total_calories     (property)
├── @item_count         (property)
└── items → MealTemplateItem[]
    ├── food_item       FK(FoodItem)        # Normalized food reference
    ├── custom_food     FK(CustomFood)      # Or custom food
    ├── food_name       CharField           # Snapshot
    ├── food_brand      CharField           # Snapshot
    ├── quantity         DecimalField
    ├── serving_size    DecimalField
    ├── serving_unit    CharField
    ├── snapshot_nutrients JSONField         # Per-serving at creation time
    └── sort_order      PositiveIntegerField
```

**4 views, admin with inline items, full nutrition calculation.**

#### System C: CustomFood as Recipe (`apps/health/models.py:2626-2671`)

```
CustomFood (UserOwnedModel)
├── is_recipe           BooleanField        # Flag for recipe mode
├── recipe_ingredients  JSONField(list)     # [{food_id, quantity, unit}]
└── ... (all macro/micro fields)
```

**Assessment:** Three disconnected recipe concepts. None linked to each other. No unified recipe-to-nutrition pipeline.

---

### 1.2 Ingredient Structure

| Question | Answer |
|----------|--------|
| Normalized Ingredient model? | **Partial.** `FoodItem` (2,476+ fields) is a global food library with full nutrition. But `Recipe.ingredients` is plain text. |
| Measurement handling? | **Yes** in FoodItem/FoodEntry (`serving_size`, `serving_unit`). **No** in Recipe. |
| Unit normalization? | **No.** No unit conversion system (e.g., cups → grams). |
| Quantity parsing? | **No.** No NLP parsing of "2 cups diced chicken" → structured data. |

**FoodItem Model** (`apps/health/models.py:2476-2624`) — The strong foundation:
- 300+ char name, brand, barcode, fatsecret_id
- 18 nutrient fields (macros + micros)
- 8 dietary flags (vegan, vegetarian, keto, gluten-free, dairy-free, nut-free, low-sodium, low-carb)
- Multi-source: manual, USDA, barcode, AI, FatSecret (1.9M+ foods), OpenFoodFacts
- Verification tracking with version history
- Net carbs property

**Gap:** Recipe ingredients are free text. No bridge from `Recipe.ingredients` → `FoodItem` references. This makes it impossible to:
- Calculate recipe nutrition automatically
- Match recipes against pantry inventory
- Auto-deduct ingredients after cooking
- Generate shopping lists from recipes

**Feasibility Assessment:**
- Matching recipes against pantry: **Requires ingredient normalization first** (structured RecipeIngredient model linking to FoodItem)
- Deducting ingredient amounts: **Requires unit conversion + pantry model** (not yet built)
- Multi-meal planning: **Requires MealPlan model + recipe-nutrition bridge**

---

### 1.3 Pantry / Inventory

| Question | Answer |
|----------|--------|
| Food pantry tracking? | **NO.** Does not exist. |
| Household inventory? | **Yes, but for insurance** — `InventoryItem` tracks household assets (electronics, furniture) with purchase price, condition, serial numbers, and photos. Not food. |
| Household concept? | **NO.** App is single-user. No Household, Family, or sharing models. |
| Shared data? | **NO.** All models are `UserOwnedModel` — strictly per-user. |
| Receipt storage? | **Partial.** `ScanLog` detects receipt category. `ImageAnalysis` extracts text. But no structured receipt-to-inventory pipeline. |
| Image upload? | **Yes.** `InventoryPhoto` for household items. `Recipe.image` for recipe photos. Scan app handles camera input. |
| OCR capability? | **Yes.** `ImageAnalysis.text_detected` stores OCR results from Vision AI. Receipt category is recognized. But no structured parsing of receipt line items. |

**Existing Shopping Lists** (`apps/life/models.py:1867-1951`):
```
ShoppingList (UserOwnedModel)
├── name               CharField(200)       # "Week 3 Meal Prep"
├── is_completed        BooleanField
├── completed_at        DateTimeField
├── notes               TextField
├── @item_count         (property)
├── @purchased_count    (property)
├── @progress_percent   (property)
└── items → ShoppingItem[]
    ├── name            CharField(200)
    ├── quantity         CharField(50)       # "2 lbs", "1 dozen"
    ├── category         CharField           # produce/protein/dairy/grains/frozen/pantry/beverages/supplements/household/other
    ├── is_purchased     BooleanField
    ├── purchased_at     DateTimeField
    └── notes            TextField
```

**Assessment:** Shopping list exists but is disconnected from recipes and nutrition. Items are plain text, not linked to FoodItem.

---

### 1.4 Chief of Staff (CoS) Capabilities

**CoS is a comprehensive context assembly system** — not a single engine. It operates via `build_cos_context(user)` in `apps/core/ai_orchestrator/cos_context.py` (146 KB).

**How CoS pulls contextual data:**
- 6+ parallel context builders via ThreadPoolExecutor
- Assembles: Blueprint state, governance profile, persona, today's plan, capacity snapshot, alignment score, pressure metrics, health signals, deadline snapshot, calendar events, module permissions, weekly pressure forecast

**CoS injects this as system prompt enrichment** for the personal assistant's LLM calls. It's Phase 1 (Interpretation), not execution.

**Can new domains integrate?**

| Capability | Status |
|-----------|--------|
| Multi-entity scoring | **Not built.** Existing PIE/PRIE rules are per-user, single-domain. A meal matching engine would need multi-entity scoring (recipes × preferences × inventory × nutrition goals). |
| Constraint filtering | **Supported.** NutritionGoals has `dietary_preferences` (JSON list) and `allergies` (JSON list). FoodItem has 8 dietary boolean flags. Filtering infrastructure exists. |
| Preference handling | **Partial.** NutritionGoals stores preferences. UserPreferences exists. But no meal-specific preference model (cuisine preferences, cooking time limits, kitchen equipment). |
| Multi-profile logic | **NOT supported.** Single-user architecture. No household profiles. |

**Engine integration for meal planning:**

The 14-engine architecture is well-suited for extension. New domain integration follows a documented pattern:

```
1. Define intents in intent_engine.py
2. Implement action handlers in action_handlers.py
3. Create SAE state builder (build_meal_planning_state)
4. Create PIE insight rules (rules_meal_planning.py)
5. Create PRIE prediction rules (prediction_rules_meal_planning.py)
6. Create PGE guidance rules (guidance_rules_meal_planning.py)
7. Register in scheduler management commands
```

**Verdict: A new MealMatchingEngine is NOT required as a standalone engine.** The existing PIE/PRIE/PGE framework can handle meal planning rules. However, a **MealScoringService** (not an engine) is needed for the multi-entity scoring logic that ranks recipes against constraints.

---

### 1.5 Current State Summary

| Component | Status | Quality |
|-----------|--------|---------|
| Recipe storage (life) | EXISTS | Good CRUD, missing nutrition link |
| Meal templates (health) | EXISTS | Good nutrition snapshots |
| FoodItem library | EXISTS | Excellent — 18 nutrients, 8 dietary flags, multi-source |
| Food search (3-tier) | EXISTS | Excellent — local + FatSecret + AI fallback |
| Nutrition tracking | EXISTS | Excellent — context-rich logging |
| Nutrition goals | EXISTS | Good — macros, preferences, allergies |
| Barcode scanning | EXISTS | Good — FatSecret + OpenFoodFacts |
| Vision AI (food) | EXISTS | Good — category detection, OCR |
| Shopping lists | EXISTS | Basic — plain text items, not linked |
| **Food pantry** | **MISSING** | Does not exist |
| **Household sharing** | **MISSING** | Single-user only |
| **Meal planning** | **MISSING** | No weekly/daily plan model |
| **Recipe-nutrition bridge** | **MISSING** | Recipe ingredients are free text |
| **Ingredient normalization** | **MISSING** | No parsing or unit conversion |
| **Receipt-to-pantry** | **MISSING** | OCR exists but no structured pipeline |
| **Dinner suggestions** | **MISSING** | No recommendation engine |
| **Multi-profile dietary** | **MISSING** | Single-user preferences only |

---

## Phase 2 — Competitive Analysis

### 2.1 App Profiles

#### Yummly (DISCONTINUED Dec 2024)
- **Was:** AI-powered recipe discovery with 2M+ recipes
- **Strengths:** Largest recipe database, personalized recommendations, taste profiles
- **Fatal Flaws:** Broken third-party links, unreliable dietary filters, 1.1-star rating at shutdown
- **Lesson:** Recipe aggregation without quality control fails. Own the recipe data.

#### Mealime
- **Strengths:** Best free tier, 30-minute recipe focus, auto-generated aisle-sorted shopping lists, beautiful UX
- **Weaknesses:** No calendar view, no AI, no desktop, no pantry tracking, curated-only recipes (can't add your own on free tier)
- **Pricing:** Free / $5.99/mo / $49.99/yr (Pro)
- **Family:** Shared account only (workaround)
- **Diabetes:** No specific support

#### Paprika 3
- **Strengths:** One-time purchase ($4.99-$29.99), excellent web recipe clipping, smart grocery list combining, cross-platform sync
- **Weaknesses:** No AI, no collaboration, basic pantry, aging UI, recipes trapped in app (no export), no updates in 2+ years
- **Family:** No sharing
- **Diabetes:** Manual tags only

#### Samsung Food (Whisk)
- **Strengths:** Free tier, Vision AI ingredient recognition, Samsung appliance integration, large recipe database
- **Weaknesses:** Buggy recipe editor, controversial "Health Score" labeling, aggressive ads, Samsung ecosystem lock-in
- **Pricing:** Free / $6.99/mo / $59.99/yr
- **Diabetes:** No specific support

#### KitchenPal
- **Strengths:** Barcode scanning (5M+ products), expiry tracking, shared grocery lists, dietary filters including diabetes
- **Weaknesses:** Primarily a pantry tracker, weak meal planning, limited recipe library
- **Pricing:** Free + Premium (family included)
- **Diabetes:** Yes (filter support)

#### NoWaste
- **Strengths:** Best-in-class receipt scanning (95%+ accuracy), AI recipes prioritizing expiring items, family sharing
- **Weaknesses:** Small recipe library, no meal planning calendar, pantry-first not meal-first
- **Pricing:** Free / $5.99/yr (Pro)
- **Family:** Yes

#### Carb Manager
- **Strengths:** 50K+ low-carb/keto recipes, blood glucose logging, ketone tracking, insulin logging, GKI tracking
- **Weaknesses:** Keto-focused (not general diabetes), no pantry, no receipt scanning, expensive
- **Pricing:** $8.49/mo / $39.99/yr
- **Diabetes:** Strong (glucose/carb tracking)

#### Eat This Much
- **Strengths:** Most automated meal planner — AI generates full weekly plans from calorie/macro targets, 6+ diet types
- **Weaknesses:** No pantry awareness, no diabetes-specific features, generated meals can be repetitive
- **Pricing:** ~$5/mo annual
- **Family:** No

#### mySugr (Roche)
- **Strengths:** Purpose-built diabetes management, CGM integration, coaching
- **Weaknesses:** Not a meal planning app — no recipes, no shopping, no pantry
- **Pricing:** $2.99/mo / $27.99/yr
- **Diabetes:** Primary focus

### 2.2 Comparison Matrix

| Feature | Mealime | Paprika | Samsung Food | KitchenPal | NoWaste | Carb Mgr | Eat This Much | mySugr |
|---------|---------|---------|-------------|------------|---------|----------|---------------|--------|
| Recipe Storage | Curated | Web clip | Web+manual | Limited | Limited | 50K+ | AI-gen | No |
| Meal Planning | Weekly | Calendar | Weekly | Basic | Basic | Yes | AI auto | No |
| Shopping Lists | Auto/aisle | Smart combine | Auto | Shared | Smart | No | Auto | No |
| Pantry Tracking | No | Basic | No | **Yes** | **Yes** | No | No | No |
| Barcode Scan | No | No | No | **Yes** | Yes | Yes | No | No |
| Receipt Scan | No | No | No | No | **Yes** | No | No | No |
| AI Recommendations | No | No | Vision AI | Basic | Yes | No | **Full auto** | No |
| Family Sharing | Workaround | No | Community | **Yes** | Yes | No | No | No |
| Dietary Filters | 8 types | Manual | Basic | Yes | Prefs | Keto | 6+ diets | Diabetes |
| Diabetes Support | No | No | No | Filter | No | **Glucose** | Macros | **CGM/A1C** |
| Expiry Tracking | No | No | No | **Yes** | **Yes** | No | No | No |
| Pricing | $5.99/mo | One-time | $6.99/mo | Freemium | $5.99/yr | $8.49/mo | ~$5/mo | $2.99/mo |

### 2.3 Key Competitive Gaps

**The market has NO app that unifies all three:**
1. Diabetes-aware meal planning
2. Pantry tracking with receipt scanning
3. AI-powered recipe suggestions from available ingredients

Each capability exists in isolation. The integration point is wide open.

**Specific gaps:**
- Yummly's shutdown leaves a vacuum in AI-powered recipe discovery
- CozZo (best combined pantry+recipes+shopping) is sundowning
- No app connects "what's in your pantry" → "what's safe for your blood sugar" → "here's a meal plan"
- Family sharing remains weak everywhere (shared accounts, not true multi-profile)
- Receipt scanning exists (NoWaste) but doesn't feed into meal planning

---

## Phase 3 — Design Target

### 3.1 Vision: "What's for Dinner?" Intelligence

The ideal WLJ solution is a **CoS-orchestrated meal intelligence system** that answers the daily question "What's for dinner?" by considering:

1. **What you have** (pantry inventory)
2. **What you need** (nutritional targets, dietary constraints)
3. **Who you're feeding** (household profiles with different needs)
4. **What you like** (taste preferences, cuisine preferences)
5. **How much time you have** (CoS capacity awareness)
6. **What's expiring** (waste reduction)
7. **What you haven't had recently** (variety optimization)

### 3.2 Core Capabilities Required

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERACTION LAYER                 │
│  "What's for dinner?" │ Weekly Plan │ Shopping List      │
└────────────┬────────────────────┬───────────────────────┘
             │                    │
┌────────────▼────────────────────▼───────────────────────┐
│              MEAL INTELLIGENCE SERVICE                    │
│  Recipe Scoring │ Constraint Filtering │ Gap Detection   │
└────────────┬────────────────────┬───────────────────────┘
             │                    │
┌────────────▼──────────┐  ┌─────▼───────────────────────┐
│   RECIPE ECOSYSTEM     │  │    INVENTORY ECOSYSTEM       │
│  Normalized Recipes    │  │  Pantry Items                │
│  Structured Ingredients│  │  Expiry Tracking             │
│  Nutrition Calculation │  │  Receipt Scanning            │
│  Recipe Discovery      │  │  Barcode Addition            │
└────────────┬──────────┘  └─────┬───────────────────────┘
             │                    │
┌────────────▼────────────────────▼───────────────────────┐
│              HOUSEHOLD LAYER                              │
│  Household │ Members │ Dietary Profiles │ Preferences    │
└────────────┬────────────────────────────────────────────┘
             │
┌────────────▼────────────────────────────────────────────┐
│         INTELLIGENCE PIPELINE INTEGRATION                │
│  SAE State │ PIE Insights │ PRIE Predictions │ PGE      │
│  CoS Context │ Daily Briefing │ Notifications           │
└─────────────────────────────────────────────────────────┘
```

### 3.3 Must-Support Features

| Feature | Description |
|---------|-------------|
| **Shared household pantry** | Multiple users see/modify same pantry. Real-time sync. |
| **Shared recipe library** | Household members share recipes. Personal favorites. |
| **Multi-profile dietary** | Each member has own dietary profile (diabetic, keto, allergies). |
| **Diabetes-friendly logic** | Low carb/sugar filtering, net carb calculation, glucose-aware suggestions. |
| **Balanced for non-diabetic** | Non-restrictive members get balanced suggestions alongside diabetic member. |
| **Weekly meal planning** | Calendar view. Assign meals to days. Drag-and-drop rearrangement. |
| **Auto shopping list** | Generated from meal plan minus pantry inventory. |
| **Inventory deduction** | Mark meal as cooked → deduct ingredients from pantry. |
| **Ingredient gap detection** | Real-time: "You need 3 items to make this recipe." |
| **Real-time dinner suggestions** | "What can I make right now with what I have?" |
| **Weekly planning suggestions** | AI-generated weekly plan considering all constraints. |
| **Store trip optimization** | Group shopping list by store section/aisle. |

---

## Phase 4 — Architecture Proposal

### 4.1 Data Models

#### Household & Membership

```
Household
├── id                  UUIDField (pk)
├── name                CharField(200)          # "The Jenkins Family"
├── created_by          FK(User)
├── invite_code         CharField(20, unique)   # For joining
├── settings            JSONField               # Shared preferences
├── created_at          DateTimeField
└── updated_at          DateTimeField

HouseholdMembership
├── id                  AutoField (pk)
├── household           FK(Household)
├── user                FK(User)
├── role                CharField                # owner, admin, member
├── nickname            CharField(50)            # "Dad", "Mom", "Kids"
├── joined_at           DateTimeField
├── is_active           BooleanField
└── UNIQUE(household, user)
```

#### Dietary Profile (per household member)

```
DietaryProfile
├── id                  AutoField (pk)
├── user                FK(User)
├── household           FK(Household, null)      # Optional household context
├── profile_name        CharField(100)           # "Danny's Diabetes Plan"
├── dietary_type        CharField                # diabetic, keto, vegan, etc.
├── restrictions        JSONField(list)          # ['gluten', 'dairy', 'nuts']
├── allergies           JSONField(list)          # ['shellfish', 'peanuts']
├── max_carbs_per_meal  PositiveIntegerField(null)
├── max_sugar_per_meal  PositiveIntegerField(null)
├── max_sodium_per_meal PositiveIntegerField(null)
├── calorie_target      PositiveIntegerField(null)
├── protein_target_g    PositiveIntegerField(null)
├── preferred_cuisines  JSONField(list)          # ['italian', 'mexican', 'asian']
├── disliked_foods      JSONField(list)          # ['brussels sprouts', 'liver']
├── max_cook_time_mins  PositiveIntegerField(null)
├── is_active           BooleanField
├── created_at          DateTimeField
└── updated_at          DateTimeField
```

#### Normalized Ingredient (Bridge Model)

```
Ingredient
├── id                  AutoField (pk)
├── name                CharField(200)           # "Chicken Breast"
├── canonical_name      CharField(200)           # Lowercase, normalized
├── food_item           FK(FoodItem, null)       # Link to nutrition DB
├── category            CharField                # protein, vegetable, grain, dairy, etc.
├── default_unit        CharField(50)            # "oz", "cups", "each"
├── is_verified         BooleanField
├── aliases             JSONField(list)          # ["chicken", "boneless chicken"]
├── created_at          DateTimeField
└── UNIQUE(canonical_name)

RecipeIngredient
├── id                  AutoField (pk)
├── recipe              FK(Recipe)
├── ingredient          FK(Ingredient)
├── quantity            DecimalField
├── unit                CharField(50)            # "cups", "oz", "tbsp"
├── preparation         CharField(100)           # "diced", "minced", "sliced"
├── is_optional         BooleanField
├── sort_order          PositiveIntegerField
├── notes               CharField(200)           # "or substitute tofu"
└── UNIQUE(recipe, ingredient, sort_order)

UnitConversion
├── id                  AutoField (pk)
├── ingredient          FK(Ingredient, null)     # Ingredient-specific (chicken: 1 cup = 5 oz)
├── from_unit           CharField(50)
├── to_unit             CharField(50)
├── conversion_factor   DecimalField             # multiply from_unit by this
├── is_approximate      BooleanField
└── UNIQUE(ingredient, from_unit, to_unit)
```

#### Pantry Inventory

```
PantryItem
├── id                  AutoField (pk)
├── household           FK(Household)
├── ingredient          FK(Ingredient)
├── quantity            DecimalField
├── unit                CharField(50)
├── expiry_date         DateField(null)
├── location            CharField                # fridge, freezer, pantry, counter
├── purchase_date       DateField(null)
├── purchase_price      DecimalField(null)
├── added_by            FK(User)
├── source              CharField                # manual, barcode, receipt, meal_deduct
├── barcode             CharField(50, null)
├── notes               CharField(200)
├── is_active           BooleanField             # False when fully consumed
├── created_at          DateTimeField
└── updated_at          DateTimeField

InventoryTransaction
├── id                  AutoField (pk)
├── pantry_item         FK(PantryItem)
├── transaction_type    CharField                # add, consume, adjust, expire, waste
├── quantity_change     DecimalField             # Positive for add, negative for consume
├── unit                CharField(50)
├── reason              CharField(200)           # "Cooked Chicken Stir Fry"
├── related_meal_plan   FK(MealPlanEntry, null)
├── related_receipt     FK(Receipt, null)
├── performed_by        FK(User)
├── created_at          DateTimeField
└── notes               CharField(200)
```

#### Receipt Processing

```
Receipt
├── id                  AutoField (pk)
├── household           FK(Household)
├── uploaded_by         FK(User)
├── store_name          CharField(200)
├── purchase_date       DateField
├── total_amount        DecimalField(null)
├── image_analysis      FK(ImageAnalysis, null)  # Link to existing scan system
├── processing_status   CharField                # pending, processed, failed, manual_review
├── raw_text            TextField                # OCR output
├── created_at          DateTimeField

ReceiptItem
├── id                  AutoField (pk)
├── receipt             FK(Receipt)
├── raw_text            CharField(300)           # "BNLS CHKN BRST 2.3LB"
├── ingredient          FK(Ingredient, null)     # Matched ingredient
├── pantry_item         FK(PantryItem, null)     # Created pantry item
├── quantity            DecimalField(null)
├── unit                CharField(50, null)
├── price               DecimalField(null)
├── confidence          FloatField               # Match confidence
├── is_food             BooleanField             # vs. household item
├── needs_review        BooleanField
└── created_at          DateTimeField
```

#### Meal Planning

```
MealPlan
├── id                  AutoField (pk)
├── household           FK(Household)
├── created_by          FK(User)
├── week_start          DateField                # Monday of the week
├── name                CharField(200)           # "Week of March 3"
├── status              CharField                # draft, active, completed
├── notes               TextField
├── created_at          DateTimeField
└── updated_at          DateTimeField

MealPlanEntry
├── id                  AutoField (pk)
├── meal_plan           FK(MealPlan)
├── recipe              FK(Recipe, null)         # Planned recipe
├── meal_template       FK(MealTemplate, null)   # Or meal template
├── planned_date        DateField
├── meal_type           CharField                # breakfast, lunch, dinner, snack
├── servings            PositiveIntegerField     # How many servings to make
├── assigned_to         ManyToMany(User)         # Who's eating this meal
├── is_cooked           BooleanField             # Mark when cooked
├── cooked_at           DateTimeField(null)
├── notes               CharField(200)
├── sort_order          PositiveIntegerField
├── created_at          DateTimeField
└── UNIQUE(meal_plan, planned_date, meal_type, sort_order)

ShoppingListGenerated
├── id                  AutoField (pk)
├── meal_plan           FK(MealPlan)
├── household           FK(Household)
├── created_by          FK(User)
├── name                CharField(200)
├── status              CharField                # draft, active, shopping, completed
├── created_at          DateTimeField
└── items → ShoppingListGeneratedItem[]

ShoppingListGeneratedItem
├── id                  AutoField (pk)
├── shopping_list       FK(ShoppingListGenerated)
├── ingredient          FK(Ingredient)
├── needed_quantity     DecimalField             # Total needed from all recipes
├── pantry_quantity     DecimalField             # Already have in pantry
├── buy_quantity        DecimalField             # needed - pantry
├── unit                CharField(50)
├── aisle_category      CharField                # produce, dairy, meat, etc.
├── is_purchased        BooleanField
├── purchased_at        DateTimeField(null)
├── actual_price        DecimalField(null)
├── notes               CharField(200)
└── sort_order          PositiveIntegerField     # By aisle category
```

### 4.2 Model Relationships Diagram

```
                    ┌──────────┐
                    │   User   │
                    └──┬───┬───┘
                       │   │
          ┌────────────┘   └────────────┐
          ▼                             ▼
  ┌───────────────┐            ┌────────────────┐
  │  Household    │◄──────────►│  Membership    │
  │  Membership   │            │  (role, active)│
  └───────┬───────┘            └────────────────┘
          │
          ▼
  ┌───────────────┐     ┌────────────────┐     ┌──────────────┐
  │   Household   │────►│  PantryItem    │────►│  Ingredient  │
  │               │     │  (qty, expiry) │     │  (canonical) │
  │               │     └───────┬────────┘     └──────┬───────┘
  │               │             │                     │
  │               │     ┌───────▼────────┐     ┌──────▼───────┐
  │               │     │  Inventory     │     │   FoodItem   │
  │               │     │  Transaction   │     │  (nutrition) │
  │               │     └────────────────┘     └──────────────┘
  │               │                                   ▲
  │               │     ┌────────────────┐            │
  │               │────►│   MealPlan     │     ┌──────┴───────┐
  │               │     │  (week_start)  │     │   Recipe     │
  │               │     └───────┬────────┘     │   Ingredient │
  │               │             │              │  (qty, unit) │
  │               │     ┌───────▼────────┐     └──────┬───────┘
  │               │     │  MealPlan      │            │
  │               │     │  Entry         │────────────┘
  │               │     │  (date, type)  │──►Recipe
  │               │     └───────┬────────┘
  │               │             │
  │               │     ┌───────▼────────┐
  │               │────►│  Shopping List │
  │               │     │  Generated     │
  │               │     └───────┬────────┘
  │               │             │
  │               │     ┌───────▼────────┐
  │               │     │  Shopping Item │──►Ingredient
  │               │     │  (need - have) │
  │               │     └────────────────┘
  │               │
  │               │     ┌────────────────┐
  │               │────►│   Receipt      │
  │               │     └───────┬────────┘
  │               │             │
  │               │     ┌───────▼────────┐
  │               │     │  ReceiptItem   │──►Ingredient
  │               │     │  (parsed)      │──►PantryItem
  │               │     └────────────────┘
  │               │
  │               │     ┌────────────────┐
  └───────────────┘────►│ DietaryProfile │
                        │ (per-member)   │
                        └────────────────┘
```

### 4.3 Service Architecture

#### MealScoringService (NEW — deterministic + AI hybrid)

```python
class MealScoringService:
    """Scores recipes against household constraints.

    NOT an engine in the 14-engine stack. This is a domain service
    called by PGE guidance rules and the "What's for Dinner?" view.
    """

    def score_recipe(self, recipe, household, profiles, pantry_state):
        """Returns 0-100 score with breakdown."""
        score = Score()

        # DETERMINISTIC (weight: 70%)
        score.add('nutrition_match', self._score_nutrition(recipe, profiles), weight=25)
        score.add('ingredient_availability', self._score_pantry_match(recipe, pantry_state), weight=20)
        score.add('dietary_compliance', self._score_dietary_fit(recipe, profiles), weight=15)
        score.add('variety', self._score_variety(recipe, household), weight=10)

        # AI-ENHANCED (weight: 30%)
        score.add('preference_match', self._score_preferences(recipe, profiles), weight=15)
        score.add('time_fit', self._score_time_fit(recipe, household), weight=10)
        score.add('expiry_priority', self._score_expiry_use(recipe, pantry_state), weight=5)

        return score.total, score.breakdown

    def suggest_dinner(self, household, meal_type='dinner'):
        """The "What's for Dinner?" entry point."""
        profiles = DietaryProfile.objects.filter(household=household, is_active=True)
        pantry = PantryItem.objects.filter(household=household, is_active=True)
        candidates = self._get_candidate_recipes(household)

        scored = [(r, *self.score_recipe(r, household, profiles, pantry))
                  for r in candidates]

        return sorted(scored, key=lambda x: x[1], reverse=True)[:10]

    def suggest_weekly_plan(self, household, week_start):
        """AI-assisted weekly plan generation."""
        # Use deterministic scoring for filtering
        # Use LLM for variety optimization and natural meal flow
        ...
```

#### InventoryGapService (NEW — deterministic)

```python
class InventoryGapService:
    """Detects what's missing for a recipe or meal plan."""

    def get_recipe_gaps(self, recipe, household):
        """Returns: {available: [], missing: [], partial: []}"""
        pantry = PantryItem.objects.filter(household=household, is_active=True)
        recipe_ingredients = RecipeIngredient.objects.filter(recipe=recipe)

        result = {'available': [], 'missing': [], 'partial': []}
        for ri in recipe_ingredients:
            pantry_qty = self._get_pantry_quantity(ri.ingredient, pantry)
            needed_qty = self._convert_units(ri.quantity, ri.unit, ri.ingredient)

            if pantry_qty >= needed_qty:
                result['available'].append(ri)
            elif pantry_qty > 0:
                result['partial'].append({
                    'ingredient': ri, 'have': pantry_qty, 'need': needed_qty
                })
            else:
                result['missing'].append(ri)

        return result

    def generate_shopping_list(self, meal_plan, household):
        """Generate shopping list from meal plan minus pantry."""
        ...
```

#### ReceiptParsingService (NEW — AI-powered)

```python
class ReceiptParsingService:
    """Parses grocery receipts into structured items."""

    def parse_receipt(self, image_analysis):
        """
        Uses existing Vision AI OCR output.
        LLM extracts line items → matches to Ingredient model.
        """
        raw_text = image_analysis.text_detected

        # Step 1: LLM extracts structured items from OCR text
        items = self._llm_extract_items(raw_text)

        # Step 2: Match to Ingredient model (fuzzy match + aliases)
        for item in items:
            item['ingredient'] = self._match_ingredient(item['name'])
            item['confidence'] = self._compute_confidence(item)

        return items
```

### 4.4 Engine Integration (within existing 14-engine stack)

**No new engines required.** New PIE/PRIE/PGE rules handle meal planning intelligence:

#### New PIE Rules (Pattern Insight Engine)

| Rule | Trigger | Insight |
|------|---------|---------|
| `MealPlanAdherenceRule` | Weekly check | "You cooked 4/7 planned meals this week" |
| `PantryExpiryRule` | Daily check | "3 items expiring in next 2 days" |
| `NutritionBalanceRule` | After meal plan | "Your Tuesday meals exceed carb targets" |
| `RecipeVarietyRule` | Weekly check | "You've repeated the same 3 dinners for 2 weeks" |
| `GrocerySpendRule` | After receipt | "Grocery spend trending 15% higher this month" |

#### New PRIE Rules (Prediction Engine)

| Rule | Output | Horizon |
|------|--------|---------|
| `MealPlanCompletionRule` | Will user follow this week's plan? | 7d |
| `PantryDepletionRule` | When will staples run out? | 14d/30d |
| `GroceryBudgetRule` | Projected monthly grocery spend | 30d |

#### New PGE Rules (Guidance Engine)

| Rule | Guidance |
|------|----------|
| `DinnerSuggestionRule` | "Based on your pantry: try Chicken Stir Fry tonight (35 min, 42g protein, 18g carbs)" |
| `MealPrepSuggestionRule` | "Sunday meal prep: make these 3 recipes to cover 5 weeknight dinners" |
| `ExpiryUsageRule` | "Use your expiring spinach tonight — here are 3 recipes" |
| `ShoppingTripRule` | "Your pantry is low on 8 staples. Here's an optimized shopping list" |

#### CoS Context Extension

Add to `cos_context.py` parallel builders:

```python
def _build_meal_planning_context(user):
    """Add meal planning awareness to CoS."""
    return {
        'meals_planned_this_week': int,
        'meals_cooked_this_week': int,
        'pantry_items_expiring_soon': int,
        'missing_ingredients_for_tonight': list,
        'grocery_budget_status': str,
        'dietary_compliance_score': float,
    }
```

### 4.5 AI Integration Strategy

| Component | Approach | Rationale |
|-----------|----------|-----------|
| **Recipe scoring** | **Deterministic** (70%) + AI (30%) | Nutrition math and constraint filtering must be exact. AI handles preference matching and variety optimization. |
| **Ingredient matching** | **Fuzzy match + LLM fallback** | "BNLS CHKN BRST" → "Chicken Breast" needs fuzzy matching. LLM handles edge cases. |
| **Receipt parsing** | **Vision AI → LLM extraction** | Existing Vision AI for OCR. LLM for structured extraction from messy receipt text. |
| **Weekly plan generation** | **Deterministic filter → LLM arrangement** | Filter eligible recipes by constraints (deterministic). LLM arranges into natural weekly flow. |
| **"What's for Dinner?"** | **Deterministic scoring → LLM presentation** | Score and rank recipes deterministically. LLM formats the recommendation with cooking tips. |
| **Ingredient normalization** | **Embeddings** | Recipe text "2 cups diced chicken breast" → nearest Ingredient via embedding similarity. Cache results. |
| **Unit conversion** | **Deterministic** | Pure math. Lookup table + conversion factors. No AI needed. |
| **Dietary compliance** | **Deterministic** | Boolean constraint checking against dietary profiles. Must be exact for medical safety. |
| **Pantry deduction** | **Deterministic** | Subtract consumed quantities. No AI — must be accurate for inventory tracking. |

**Embedding Strategy:**
- Pre-compute embeddings for all Ingredient canonical names + aliases
- At recipe import time, embed each ingredient line and match to nearest Ingredient
- Cache matches for reuse
- Confidence threshold: >0.85 auto-match, 0.60-0.85 suggest, <0.60 manual

---

## Phase 5 — Implementation Roadmap

### Phase 1: Data Foundation & Ingredient Normalization (2-3 weeks)

**Objective:** Create the normalized ingredient system that bridges recipes to nutrition.

**Models:**
- `Ingredient` (canonical food items with FoodItem links)
- `RecipeIngredient` (structured recipe-ingredient bridge)
- `UnitConversion` (measurement conversion table)

**Services:**
- `IngredientNormalizationService` — Parse free text → structured ingredients
- `UnitConversionService` — Convert between measurement units
- `IngredientMatchingService` — Fuzzy match text to Ingredient model

**Migrations:**
- Create Ingredient, RecipeIngredient, UnitConversion tables
- Data migration: Seed common ingredients from existing FoodItem database
- Data migration: Seed standard unit conversions

**API Endpoints:**
- `GET /api/ingredients/search/` — Autocomplete ingredient search
- `POST /api/ingredients/parse/` — Parse ingredient text to structured data

**Admin:**
- IngredientAdmin with alias management
- UnitConversionAdmin
- RecipeIngredientInline on RecipeAdmin

**Tests:**
- Ingredient model tests (CRUD, canonical name normalization)
- Unit conversion accuracy tests (cups↔oz, tbsp↔ml, etc.)
- Ingredient parsing tests (free text → structured)
- FoodItem linking tests

**Performance:**
- Index on `canonical_name` and `aliases` (GIN for JSONField)
- Embedding cache for fuzzy matching

**Security:**
- Ingredient data is non-sensitive
- User-created ingredients visible only to creator + household

---

### Phase 2: Household & Pantry Inventory (2-3 weeks)

**Objective:** Multi-user household with shared food pantry.

**Models:**
- `Household` (family unit with invite code)
- `HouseholdMembership` (user↔household with roles)
- `DietaryProfile` (per-member dietary constraints)
- `PantryItem` (food inventory with expiry tracking)
- `InventoryTransaction` (audit trail for pantry changes)

**Services:**
- `HouseholdService` — Create household, invite/join, manage roles
- `PantryService` — Add/remove/adjust pantry items
- `PantryTrackingService` — Expiry alerts, low-stock detection

**Migrations:**
- Create all household/pantry tables
- Optional: Migration to auto-create single-user households for existing users

**API Endpoints:**
- `POST /api/household/create/` — Create household
- `POST /api/household/join/` — Join via invite code
- `GET /api/pantry/` — List pantry items
- `POST /api/pantry/add/` — Add item (manual/barcode)
- `PATCH /api/pantry/<id>/adjust/` — Adjust quantity
- `GET /api/pantry/expiring/` — Items expiring soon

**Admin:**
- HouseholdAdmin with membership inline
- PantryItemAdmin with transaction inline
- DietaryProfileAdmin

**Tests:**
- Household CRUD, invitation flow, role management
- Pantry item lifecycle (add → consume → deplete)
- Transaction audit trail
- Multi-user access control
- Expiry detection

**Performance:**
- Index on household + is_active for pantry queries
- Index on expiry_date for expiry alerts

**Security:**
- Household data isolated between households
- Role-based permissions (owner/admin/member)
- Invite code rotation

---

### Phase 3: Recipe-Pantry Matching & Gap Detection (2 weeks)

**Objective:** Bridge recipes to pantry. Answer "Can I make this?"

**Services:**
- `InventoryGapService` — Calculate what's available vs. needed
- `RecipeNutritionService` — Calculate recipe nutrition from structured ingredients

**Migrations:**
- Add `nutrition_per_serving` JSONField to Recipe (cached calculation)

**API Endpoints:**
- `GET /api/recipes/<id>/availability/` — Pantry match for recipe
- `GET /api/recipes/makeable/` — Recipes you can make now
- `GET /api/recipes/<id>/nutrition/` — Calculated nutrition

**Views:**
- Update RecipeDetailView with pantry availability indicators
- Add "Can Make Now" filter to RecipeListView
- Ingredient gap display on recipe detail

**Tests:**
- Gap detection with full/partial/missing ingredients
- Unit conversion in gap calculation
- Nutrition calculation from structured ingredients
- Edge cases (no pantry, empty recipe)

**Performance:**
- Cache recipe nutrition calculations
- Batch pantry queries for list views

---

### Phase 4: CoS & Intelligence Integration (2 weeks)

**Objective:** Wire meal planning into the 14-engine intelligence stack.

**Intelligence Integration:**
- SAE: `build_meal_planning_state(user)` — pantry health, planning adherence, dietary compliance
- PIE: `MealPlanAdherenceRule`, `PantryExpiryRule`, `NutritionBalanceRule`, `RecipeVarietyRule`
- PRIE: `MealPlanCompletionRule`, `PantryDepletionRule`
- PGE: `DinnerSuggestionRule`, `ExpiryUsageRule`
- CoS: Add meal planning context to `_build_health_and_vitals()`

**Intent Registration:**
- Add meal planning intents to orchestrator
- Implement action handlers for meal logging via chat

**Tests:**
- SAE state builder tests
- PIE rule evaluation tests (applies + evaluate)
- PRIE prediction tests
- PGE guidance generation tests
- Integration test: action → SAE → PIE → PRIE → PGE chain

---

### Phase 5: Weekly Meal Planning (2-3 weeks)

**Objective:** Calendar-based weekly meal planning with AI suggestions.

**Models:**
- `MealPlan` (weekly plan container)
- `MealPlanEntry` (individual meal slots)

**Services:**
- `MealScoringService` — Score recipes against constraints
- `MealPlanService` — CRUD for meal plans
- `WeeklyPlanSuggestionService` — AI-generated weekly plans

**API Endpoints:**
- `GET /api/meal-plans/` — List meal plans
- `POST /api/meal-plans/` — Create plan
- `POST /api/meal-plans/<id>/entries/` — Add meal to plan
- `GET /api/meal-plans/<id>/suggest/` — AI suggest meals for empty slots
- `POST /api/meal-plans/<id>/shopping-list/` — Generate shopping list

**Views:**
- Weekly calendar view (responsive for mobile)
- Meal slot assignment (recipe picker)
- Plan overview with nutrition summary
- "What's for Dinner?" quick view

**Tests:**
- Meal plan CRUD
- AI suggestion generation
- Multi-profile constraint satisfaction
- Shopping list generation from plan

**Performance:**
- Prefetch recipes with ingredients for plan views
- Cache scoring results per household per day

---

### Phase 6: Smart Shopping Lists & Receipt Scanning (2-3 weeks)

**Objective:** Auto-generated shopping lists from meal plans. Receipt scanning to restock pantry.

**Models:**
- `ShoppingListGenerated` (auto-generated from meal plan)
- `ShoppingListGeneratedItem` (need - have = buy)
- `Receipt` (scanned grocery receipt)
- `ReceiptItem` (parsed line items)

**Services:**
- `ShoppingListGenerationService` — Meal plan → shopping list (minus pantry)
- `ReceiptParsingService` — Receipt image → structured items
- `ReceiptToPantryService` — Parsed receipt → pantry items

**API Endpoints:**
- `POST /api/receipts/scan/` — Upload receipt image
- `GET /api/receipts/<id>/items/` — View parsed items
- `POST /api/receipts/<id>/confirm/` — Confirm and add to pantry
- `GET /api/shopping-list/<id>/` — View generated list

**Views:**
- Shopping list view sorted by aisle
- Receipt scan confirmation UI (review parsed items)
- Receipt history

**Tests:**
- Shopping list generation (with/without pantry items)
- Receipt parsing accuracy
- Receipt-to-pantry pipeline
- Aisle sorting

**Performance:**
- Async receipt processing (Vision AI call)
- Cache ingredient matching results

---

### Phase 7: Image-Based Pantry Recognition (2-3 weeks)

**Objective:** Take a photo of your fridge/pantry → auto-detect items.

**Services:**
- `PantryVisionService` — Photo → detected items with quantities
- Integration with existing `ScanAnalyzeView` and `ImageAnalysis` model

**API Endpoints:**
- `POST /api/pantry/scan/` — Upload pantry photo
- `POST /api/pantry/scan/confirm/` — Confirm detected items

**Views:**
- Camera interface (reuse existing scan UI)
- Detection confirmation UI (review/edit detected items)

**Tests:**
- Vision detection accuracy
- Quantity estimation
- Existing item update vs. new item creation

**Performance:**
- Async Vision AI processing
- Progressive disclosure (show results as detected)

---

### Phase 8: Optimization Layer (2-3 weeks)

**Objective:** Advanced features — store trip optimization, meal prep planning, waste reduction.

**Services:**
- `StoreTripOptimizer` — Organize shopping by store layout
- `MealPrepPlanner` — Batch cooking suggestions
- `WasteReductionService` — Track waste, suggest improvements
- `BudgetTracker` — Grocery spend analytics

**Views:**
- Store trip optimized view
- Meal prep Sunday planning
- Waste analytics dashboard
- Grocery budget trends

**Tests:**
- Optimization algorithm tests
- Budget calculation accuracy
- Waste tracking pipeline

---

## Phase 6 — Risk & Complexity

### Complexity Ratings

| Phase | Technical | AI | Effort |
|-------|-----------|-----|--------|
| 1. Ingredient Normalization | 6/10 | 5/10 | 2-3 weeks |
| 2. Household & Pantry | 7/10 | 2/10 | 2-3 weeks |
| 3. Recipe-Pantry Matching | 5/10 | 3/10 | 2 weeks |
| 4. Intelligence Integration | 6/10 | 4/10 | 2 weeks |
| 5. Weekly Meal Planning | 7/10 | 7/10 | 2-3 weeks |
| 6. Shopping & Receipts | 7/10 | 8/10 | 2-3 weeks |
| 7. Image Pantry | 4/10 | 9/10 | 2-3 weeks |
| 8. Optimization | 8/10 | 6/10 | 2-3 weeks |

**Overall Technical Complexity: 7/10**
**Overall AI Complexity: 7/10**

### Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| **Ingredient normalization accuracy** | HIGH | Start with top 500 common ingredients. Use LLM fallback for edge cases. Manual review queue. |
| **Receipt OCR accuracy** | HIGH | Receipts vary wildly by store. Use confidence scoring. Always require user confirmation. |
| **Multi-user data integrity** | MEDIUM | Optimistic locking on pantry items. Transaction audit trail. Household-level permissions. |
| **Performance with large pantries** | MEDIUM | Index strategy. Cache recipe scores. Batch pantry queries. |
| **AI cost management** | MEDIUM | Deterministic logic for most scoring. LLM only for parsing and suggestions. Cache LLM results. |
| **Unit conversion accuracy** | MEDIUM | Comprehensive test suite. Approximate flag for imprecise conversions (e.g., "1 bunch of parsley"). |
| **Household sharing UX** | MEDIUM | Keep invitation flow simple. Clear role permissions. Graceful degradation to single-user. |
| **Scope creep** | HIGH | Each phase delivers standalone value. Can ship phases 1-3 and stop. |
| **Data integrity (pantry deduction)** | HIGH | Transaction-based with audit trail. "Undo" capability. Never auto-deduct without confirmation. |
| **Maintenance burden** | MEDIUM | Ingredient database needs ongoing curation. Receipt parsing models need retraining. |

---

## Phase 7 — Final Recommendation

### 7.1 Classification

**This is a Major WLJ Pillar** — not a lightweight add-on.

It touches: household architecture, multi-user data sharing, AI services, intelligence pipeline, scan infrastructure, new UI patterns (calendar, real-time suggestions), and introduces the first multi-user feature in WLJ.

**However**, it can be delivered incrementally with standalone value at each phase:
- **Phase 1-3 alone** = Useful recipe management with nutrition awareness
- **Phase 1-5** = Full meal planning system competitive with Mealime
- **Phase 1-8** = Category-defining feature with no direct competitor

### 7.2 Should This Introduce Family Plans?

**Yes, absolutely.** This is the natural entry point for household sharing because:
1. Meal planning is inherently a household activity
2. Pantry is shared physical space
3. Grocery shopping serves the household
4. Dietary profiles vary by family member

The Household model should be designed to support future sharing across other WLJ features (shared goals, family health tracking, etc.) but initially scoped to just meal planning.

### 7.3 CoS Architectural Changes Required?

**Minor.** The CoS context builder pattern already supports adding new parallel builders. Required changes:
1. Add `_build_meal_planning_context()` to parallel builders
2. Add meal planning intents to orchestrator intent sets
3. Create action handlers for meal planning actions
4. Register new PIE/PRIE/PGE rules

The three-phase pipeline is not affected. No new engines are needed.

### 7.4 Competitive Advantage

What makes this a **true differentiator**:

1. **Diabetes-First Meal Planning** — No competitor offers diabetes-aware meal planning that considers blood sugar history, carb targets, and medication timing. WLJ already tracks glucose, insulin, and has medical models. This integration is uniquely possible.

2. **CoS-Orchestrated Intelligence** — No competitor has an intelligence pipeline that observes patterns and proactively guides meal planning. The daily briefing saying "Your blood sugar was elevated after pasta meals this week — tonight's suggestion avoids high-carb options" is impossible in any competing app.

3. **Whole-Person Context** — WLJ knows the user's stress levels (journal), exercise schedule (fitness), sleep quality, medication timing, faith commitments (fasting), and work calendar. No meal planning app has this context. A suggestion that accounts for "you have a busy day tomorrow, here's a 20-minute high-protein meal" is uniquely WLJ.

4. **Receipt → Pantry → Meal Plan → Shopping List → Receipt** — The complete closed loop. No competitor achieves this. Most have 1-2 of these connected.

5. **Medical Safety Integration** — WLJ's medical module can flag food-drug interactions. "Don't eat grapefruit — it interacts with your statin" is a safety feature no meal planning app offers.

### 7.5 Recommended Starting Point

**Start with Phases 1-3** (6-8 weeks). This delivers:
- Normalized ingredients linked to nutrition database
- Recipe-to-nutrition calculation
- Pantry tracking (single user initially)
- "Can I make this?" with gap detection
- Foundation for all subsequent phases

Then evaluate user adoption before investing in Phases 4-8.

---

## Appendix A: Files Referenced

| File | Content |
|------|---------|
| `apps/life/models.py:898-993` | Recipe model |
| `apps/life/models.py:1867-1951` | ShoppingList + ShoppingItem |
| `apps/life/models.py:514-605` | InventoryItem + InventoryPhoto (household insurance) |
| `apps/life/views.py:1096-2493` | Recipe CRUD views |
| `apps/life/urls.py:47-158` | Recipe URL routes |
| `apps/life/admin.py:57-61` | RecipeAdmin |
| `apps/health/models.py:2476-2624` | FoodItem (global food library) |
| `apps/health/models.py:2626-2671` | CustomFood (is_recipe flag) |
| `apps/health/models.py:2674-2900` | FoodEntry (meal logging) |
| `apps/health/models.py:3338-3433` | NutritionGoals |
| `apps/health/models.py:4668-4765` | MealTemplate + MealTemplateItem |
| `apps/health/services/food_search.py` | 3-tier food search |
| `apps/health/services/nutrition_calculator.py` | Nutrition calculation |
| `apps/health/services/fatsecret.py` | FatSecret API client |
| `apps/health/services/ai_nutrition.py` | AI nutrition estimation |
| `apps/core/ai_orchestrator/cos_context.py` | CoS context builder |
| `apps/core/ai_orchestrator/intent_engine.py` | Intent registration |
| `apps/core/ai_orchestrator/orchestrator.py` | Main orchestrator |
| `apps/core/ai_state/state_builder.py` | SAE state builders |
| `apps/core/ai_insights/` | PIE insight rules |
| `apps/core/ai_predictions/` | PRIE prediction rules |
| `apps/core/ai_guidance/` | PGE guidance rules |
| `apps/scan/models.py` | ScanLog, ImageAnalysis |
| `apps/scan/views.py` | Barcode/receipt scanning |

## Appendix B: Competitive Landscape Key Finding

**No existing app unifies all three of:**
1. Diabetes-aware meal planning
2. Pantry tracking with receipt scanning
3. AI-powered recipe suggestions from available ingredients

**The integration opportunity is wide open.** WLJ's existing intelligence pipeline, health tracking, and medical integration make it uniquely positioned to fill this gap.
