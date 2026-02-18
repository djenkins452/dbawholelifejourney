# Nutrition Log Upgrade Plan

**Created:** 2026-02-17
**Status:** Phase 0 — Plan (awaiting approval)
**Goal:** Rebuild the Nutrition Log to be best-in-class with correct nutrient math, copy/template features, and barcode accuracy controls.

---

## Current State Summary

### Existing Models (all in `apps/health/models.py`)
| Model | Purpose | Keep/Modify |
|-------|---------|-------------|
| `FoodItem` (line 2476) | Global food library with per-serving nutrients, barcode, source tracking | **Modify** — add version tracking, external_ids JSON |
| `CustomFood` (line 2599) | User-owned custom foods with recipe_ingredients JSON stub | **Modify** — repurpose as MealTemplate |
| `FoodEntry` (line 2647) | User's consumption log with total_* fields | **Modify** — add snapshot + audit fields |
| `DailyNutritionSummary` (line 2843) | Aggregated daily totals | **Keep** — no changes |
| `NutritionGoals` (line 3225) | User's daily targets | **Keep** — no changes |

### Key Bug Confirmed
`FoodEntry.calculate_totals()` reads from `food_item` or `custom_food` FK — but the create form fills `total_*` fields directly from autocomplete JS without multiplying by quantity. If user changes quantity after autofill, totals are NOT recalculated unless `calculate_totals()` is explicitly called. **The form never calls it.**

### Existing Data to Preserve
- All `FoodEntry` rows — these become the historical entries. The `total_*` fields already act as snapshots of what was logged.
- All `FoodItem` rows — global food library (recently cleared FatSecret cache for serving fix).
- All `CustomFood` rows — user's custom foods.
- All `DailyNutritionSummary` rows — daily aggregates.
- All `NutritionGoals` rows — user targets.

---

## Phase 1: Data Model Changes

### 1A. FoodItem — Add Version Tracking + External IDs

**New fields on existing FoodItem:**
```python
# Version tracking
version = PositiveIntegerField(default=1)  # bumped on any nutrient change

# External IDs (consolidate existing barcode + fatsecret_id + new ones)
external_ids = JSONField(default=dict)  # {"fatsecret_id": "...", "off_barcode": "...", "usda_fdb_id": "..."}
# Keep barcode and fatsecret_id columns for backward compat + indexing

# Label info
label_servings_per_container = DecimalField(max_digits=6, decimal_places=2, null=True)
# servings_per_container already exists — rename reference

# Verification
verified_by_user = ForeignKey(User, null=True, SET_NULL)  # who verified
# last_verified_at already exists
# is_verified already exists
```

**Migration strategy:** Add new fields with defaults, no data loss.

### 1B. FoodEntry — Add Snapshot JSON + Source Metadata

**New fields on existing FoodEntry:**
```python
# Immutable snapshot of per-serving nutrients at log time
snapshot_nutrients = JSONField(default=dict)
# Format: {"calories": 10, "protein_g": 0, "carbohydrates_g": 4, ...}
# This is PER SERVING — totals = snapshot * quantity

# Source reference
food_item_version = PositiveIntegerField(null=True)  # FoodItem.version at log time
data_source_used = CharField(max_length=30)  # 'local', 'fatsecret', 'openfoodfacts', 'ai_guess', 'user_override', 'quick_add', 'manual'
confidence_score = DecimalField(max_digits=5, decimal_places=2, null=True)  # 0-100

# Copy/template tracking
copied_from_entry = ForeignKey('self', null=True, SET_NULL)
applied_template = ForeignKey('MealTemplate', null=True, SET_NULL)
```

**Migration strategy:**
1. Add fields with `null=True` / defaults
2. Data migration: backfill `snapshot_nutrients` from existing `total_*` fields divided by `quantity` for every existing entry
3. Backfill `data_source_used` from existing `entry_source` field
4. Backfill `confidence_score` from existing `ai_confidence_score` (scale to 0-100)

### 1C. NutritionEntryAudit — New Model

```python
class NutritionEntryAudit(models.Model):
    CHANGE_TYPES = [
        ('quantity_change', 'Quantity Changed'),
        ('override_nutrients', 'Nutrients Overridden'),
        ('source_change', 'Source Changed'),
        ('copy_action', 'Copied from Another Entry'),
        ('template_apply', 'Template Applied'),
        ('edit', 'General Edit'),
    ]

    entry = ForeignKey(FoodEntry, on_delete=CASCADE, related_name='audit_trail')
    changed_by = ForeignKey(User, on_delete=CASCADE)
    changed_at = DateTimeField(auto_now_add=True)
    change_type = CharField(max_length=30, choices=CHANGE_TYPES)
    before_data = JSONField(default=dict)
    after_data = JSONField(default=dict)
```

### 1D. MealTemplate + MealTemplateItem — New Models

```python
class MealTemplate(UserOwnedModel):
    name = CharField(max_length=200)
    description = TextField(blank=True)
    default_meal_type = CharField(max_length=20, choices=FoodEntry.MEAL_CHOICES, default='snack')
    is_favorite = BooleanField(default=False)
    use_count = PositiveIntegerField(default=0)  # for popularity sorting
    # created_at/updated_at from UserOwnedModel

class MealTemplateItem(models.Model):
    template = ForeignKey(MealTemplate, on_delete=CASCADE, related_name='items')
    food_item = ForeignKey(FoodItem, on_delete=SET_NULL, null=True)
    custom_food = ForeignKey(CustomFood, on_delete=SET_NULL, null=True)
    food_name = CharField(max_length=300)  # snapshot for display even if FK deleted
    food_brand = CharField(max_length=200, blank=True)
    quantity = DecimalField(max_digits=8, decimal_places=2, default=1)
    serving_size = DecimalField(max_digits=8, decimal_places=2, default=1)
    serving_unit = CharField(max_length=50, default='serving')
    snapshot_nutrients = JSONField(default=dict)  # per-serving at time of template creation
    sort_order = PositiveSmallIntegerField(default=0)
```

**CustomFood relationship:** Keep `CustomFood` as-is for user's custom foods. `MealTemplate` is separate — it's a named group of items. A `MealTemplateItem` can reference either a `FoodItem` or `CustomFood`.

### 1E. FoodItemOverride — New Model (User Corrections)

```python
class FoodItemOverride(UserOwnedModel):
    food_item = ForeignKey(FoodItem, on_delete=CASCADE, related_name='user_overrides')
    overridden_nutrients = JSONField()  # {"calories": 10, "carbohydrates_g": 4, ...}
    override_reason = TextField(blank=True)  # "Label says 10 cal not 3"
    label_photo = ImageField(upload_to='nutrition_labels/', null=True)  # evidence
    # user from UserOwnedModel
    # created_at/updated_at from UserOwnedModel
```

**Behavior:** When user has an override for a FoodItem, the override nutrients are preferred for THAT user's future logs. Other users see the global FoodItem data. Single-tenant today but designed for multi-tenant correctness.

---

## Phase 2: Correct Nutrient Math

### Single Authoritative Function

```python
# apps/health/services/nutrition_calculator.py

def compute_totals(snapshot_per_serving: dict, quantity: Decimal) -> dict:
    """
    Multiply all per-serving nutrient values by quantity.
    Returns dict of total_* values.
    """
    totals = {}
    for key, value in snapshot_per_serving.items():
        if value is not None:
            totals[f'total_{key}'] = round(Decimal(str(value)) * quantity, 2)
        else:
            totals[f'total_{key}'] = None
    return totals

def build_snapshot(source) -> dict:
    """
    Build per-serving snapshot dict from FoodItem, CustomFood, or override.
    """
    fields = ['calories', 'protein_g', 'carbohydrates_g', 'fiber_g',
              'sugar_g', 'fat_g', 'saturated_fat_g', 'sodium_mg',
              'cholesterol_mg', 'potassium_mg']
    return {f: float(getattr(source, f, 0) or 0) for f in fields}
```

### Integration Points
1. **FoodEntry.save()** — Always recompute totals from `snapshot_nutrients * quantity` before save
2. **FoodEntryForm.save()** — Build snapshot from source, call `compute_totals`, populate `total_*` fields
3. **JS client-side** — Real-time preview using same formula (display only, server is truth)
4. **DailyNutritionSummary.recalculate()** — No change needed (already reads from `total_*` fields)

### Override Priority for Snapshot Building
When logging a FoodItem, snapshot source priority:
1. User's `FoodItemOverride` for this FoodItem (if exists)
2. `FoodItem` canonical data
3. Manual entry (user types values directly)

---

## Phase 3: Copy Features

### 3A. Copy Single Entry
- **Action:** "Copy to…" button on entry detail / entry row dropdown
- **Flow:** User picks target date + meal_type → new FoodEntry created with:
  - Same `snapshot_nutrients`, `food_item` FK, `food_name`, `serving_size`, etc.
  - `quantity` defaults to same but user can change
  - `copied_from_entry` = original entry PK
  - Audit record: `change_type='copy_action'`

### 3B. Copy Meal
- **Action:** "Copy Meal" dropdown on meal section header
- **Flow:** User picks source date + meal_type → target date + meal_type
- Creates one FoodEntry per source entry, all with `copied_from_entry` refs
- Times: reset to default meal time (e.g., breakfast=8:00am) or keep relative offsets (design choice: **reset to defaults** — simpler, avoids confusion)

### 3C. Copy Day
- **Action:** "Copy Day" button on daily view header
- **Flow:** User picks source date → target date
- Copies all meals. If target date has entries: warn and offer "Merge" (add alongside) or "Replace" (delete existing first)
- Each entry gets `copied_from_entry` ref

### API Endpoints
```
POST /health/physical/nutrition/api/copy-entry/     {entry_id, target_date, target_meal}
POST /health/physical/nutrition/api/copy-meal/      {source_date, source_meal, target_date, target_meal}
POST /health/physical/nutrition/api/copy-day/       {source_date, target_date, mode: merge|replace}
```

---

## Phase 4: Meal Templates

### Create Template
- **From single entry:** "Save as Template" → creates MealTemplate with 1 MealTemplateItem
- **From meal:** "Save Meal as Template" → creates MealTemplate with all entries in that meal as items
- User names the template, optionally marks as favorite

### Apply Template
- **In Add Food flow:** "Add Template" option alongside Search/Scan/Photo
- Selecting template: shows preview of all items with quantities
- "Log Template" creates multiple FoodEntry rows (one per item) with:
  - `applied_template` FK set
  - Each gets its own `snapshot_nutrients` from template item
  - Audit records: `change_type='template_apply'`
  - Template `use_count` incremented

### Template Management
- List/edit/delete templates at `/health/physical/nutrition/templates/`
- Edit individual items (change quantities, add/remove items)
- Favorite templates appear first in "Add Template" list

### URLs
```
GET       /health/physical/nutrition/templates/              → MealTemplateListView
GET/POST  /health/physical/nutrition/templates/create/       → MealTemplateCreateView
GET/POST  /health/physical/nutrition/templates/<pk>/edit/    → MealTemplateEditView
POST      /health/physical/nutrition/templates/<pk>/delete/  → MealTemplateDeleteView
POST      /health/physical/nutrition/templates/<pk>/apply/   → MealTemplateApplyView (API)
```

---

## Phase 5: Barcode Accuracy + User Overrides

### Barcode Result Display
When barcode returns a match, show:
- Food name + brand
- **Source badge** (FatSecret / Open Food Facts / AI Guess / Local Cache)
- **Confidence indicator** (High/Medium/Low based on source)
- All nutrient fields **editable** (pre-filled from source)
- "Compare to Label" toggle to show side-by-side

### User Override Flow
1. User edits any nutrient field → UI shows "Modified" badge
2. On save: if nutrients differ from source, create `FoodItemOverride`
3. Override stored per-user — future scans of same barcode prefer user's override
4. Optional: user can upload label photo as evidence

### Label Photo Evidence
```python
class NutritionLabelEvidence(models.Model):
    food_item = ForeignKey(FoodItem, on_delete=CASCADE)
    uploaded_by = ForeignKey(User, on_delete=CASCADE)
    image = ImageField(upload_to='nutrition_labels/%Y/%m/')
    uploaded_at = DateTimeField(auto_now_add=True)
    notes = TextField(blank=True)
```

### Source Priority Update (for logging)
1. User's `FoodItemOverride` for this FoodItem
2. Local DB `FoodItem` (verified)
3. Local DB `FoodItem` (unverified)
4. FatSecret API
5. Open Food Facts API
6. OpenAI (last resort, requires consent)

---

## Phase 6: UI Rebuild

### Primary Screen: Daily Nutrition Log (`/health/physical/nutrition/`)

**Layout:**
- Date selector (prev/next arrows + calendar picker)
- Daily summary bar (calories, protein, carbs, fat — with goal progress rings)
- Four meal sections: Breakfast, Lunch, Dinner, Snack
- Each meal section:
  - Header: meal name + total calories + "Add Food" / "Add Template" / "Copy Meal" buttons
  - Entry rows: food name, brand, qty × serving, calories, macros, source badge
  - Tap row to expand: full nutrients, notes, edit/copy/delete actions
- Bottom: "Copy Day" button

**Responsive design:** Card-based on mobile, table-like on desktop.

### Add Food Flow (modal or dedicated page)
1. **Find:** Search bar + Scan Barcode + Take Photo + Recent Foods + Favorites
2. **Confirm:** Show detected nutrients with source/confidence, editable fields, quantity selector
3. **Review:** Calculated totals preview (quantity × per-serving)
4. **Save:** Creates FoodEntry with snapshot

### Templates Screen
- List of user's templates with item count, total calories, favorite toggle
- Tap to expand items
- "Apply to Today" quick action

---

## Migration Strategy (Data Preservation)

### Step 1: Add New Fields (safe, no data loss)
- Add `snapshot_nutrients`, `food_item_version`, `data_source_used`, `confidence_score`, `copied_from_entry`, `applied_template` to FoodEntry
- Add `version`, `external_ids`, `verified_by_user` to FoodItem
- Create NutritionEntryAudit, MealTemplate, MealTemplateItem, FoodItemOverride, NutritionLabelEvidence models

### Step 2: Data Migration (backfill existing entries)
```python
# For every existing FoodEntry:
for entry in FoodEntry.objects.all():
    # Build snapshot from stored totals / quantity
    qty = entry.quantity or 1
    entry.snapshot_nutrients = {
        'calories': float(entry.total_calories / qty),
        'protein_g': float(entry.total_protein_g / qty),
        'carbohydrates_g': float(entry.total_carbohydrates_g / qty),
        'fiber_g': float(entry.total_fiber_g / qty),
        'sugar_g': float(entry.total_sugar_g / qty),
        'fat_g': float(entry.total_fat_g / qty),
        'saturated_fat_g': float(entry.total_saturated_fat_g / qty),
        'sodium_mg': float(entry.total_sodium_mg / qty) if entry.total_sodium_mg else None,
        'cholesterol_mg': float(entry.total_cholesterol_mg / qty) if entry.total_cholesterol_mg else None,
        'potassium_mg': float(entry.total_potassium_mg / qty) if entry.total_potassium_mg else None,
    }
    # Map entry_source → data_source_used
    source_map = {
        'manual': 'manual', 'barcode': 'local', 'camera': 'fatsecret',
        'voice': 'manual', 'quick_add': 'quick_add'
    }
    entry.data_source_used = source_map.get(entry.entry_source, 'manual')
    entry.save(update_fields=['snapshot_nutrients', 'data_source_used'])
```

### Step 3: Verify
- Confirm all existing entries have valid `snapshot_nutrients`
- Confirm `snapshot_nutrients * quantity ≈ total_*` fields (within rounding)

### Step 4: Wire New Logic
- Update `FoodEntry.save()` to always compute `total_*` from `snapshot_nutrients * quantity`
- Update views/forms to use new fields

**No existing model is removed. No existing data is lost.**

---

## Test Plan

### Unit Tests
- `compute_totals()` — quantity=1 returns same, quantity=2 doubles, quantity=0.5 halves
- `build_snapshot()` — correctly extracts from FoodItem, CustomFood, FoodItemOverride
- Snapshot immutability — changing FoodItem after logging doesn't change entry's snapshot
- Copy entry creates correct new entry with `copied_from_entry` ref
- Copy meal creates N entries matching source meal
- Copy day with merge vs replace modes
- Template apply creates N entries with correct snapshots
- Audit records created for all tracked change types
- Override priority: user override > FoodItem > API

### Integration Tests
- Barcode scan → create entry → verify snapshot + totals
- Search → select → change quantity → verify totals recalculated
- Quick add → verify entry_source and snapshot
- Full copy flow: log entries → copy to new date → verify identical nutrients

### Regression Tests
- Existing food autocomplete still works
- Existing barcode scan still works
- DailyNutritionSummary.recalculate() still correct
- NutritionGoals still functional
- All existing URLs still resolve

---

## File Change Summary

| File | Changes |
|------|---------|
| `apps/health/models.py` | Add fields to FoodItem, FoodEntry; add NutritionEntryAudit, MealTemplate, MealTemplateItem, FoodItemOverride, NutritionLabelEvidence |
| `apps/health/forms.py` | Update FoodEntryForm, add MealTemplateForm, CopyEntryForm, CopyMealForm, CopyDayForm |
| `apps/health/views.py` | Add copy views, template views; update create/edit to use snapshot+compute_totals |
| `apps/health/urls.py` | Add routes for templates, copy APIs |
| `apps/health/services/nutrition_calculator.py` | **New** — compute_totals, build_snapshot |
| `apps/health/migrations/` | Schema + data migrations |
| `static/js/food-autocomplete.js` | Add real-time total preview on quantity change |
| `static/js/nutrition-copy.js` | **New** — copy modal interactions |
| `templates/health/nutrition/home.html` | Rebuild with meal sections, copy/template actions |
| `templates/health/nutrition/food_entry_form.html` | Add source badge, confidence, snapshot preview |
| `templates/health/nutrition/templates_list.html` | **New** — template management |
| `templates/health/nutrition/copy_modal.html` | **New** — copy item/meal/day modal |

---

*This plan will be implemented phase by phase. Each phase will be committed and tested before proceeding to the next.*
