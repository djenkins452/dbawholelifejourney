# WLJ Ingredient Intelligence — Canonical Ingredient Identity

**Status:** Foundation shipped 2026-07-20 · **Governing module:** `apps/meals/services/ingredient_intelligence.py`

Ingredient Intelligence is the single deterministic authority that answers one question for
the whole Meal Intelligence ecosystem: **do two different names represent the same real-world
ingredient?** It exists because that truth was previously undefined — every acquisition path
created ingredients by exact string, so "Hamburger Bun" and "Hamburger Buns" became two rows
and a recipe needing one showed a pantry gap while the other was stocked.

---

## The core distinction: Identity vs. Substitution

These are two different relationships and must never be conflated.

| | **Identity** (Ingredient Intelligence owns this) | **Substitution** (the substitution engine owns this) |
|---|---|---|
| Question | Same real-world thing? | Different things that can swap? |
| Examples | Hamburger Bun ⇄ Hamburger Buns; Ketchup ⇄ Catsup ⇄ Tomato Ketchup; Mayo ⇄ Mayonnaise | Beef Patty ⇄ Ground Beef; 2% Milk ⇄ Whole Milk; butter ⇄ margarine |
| Result | **One canonical `Ingredient`** | Two ingredients, a *related* link |
| Basis | case · punctuation · whitespace · singular/plural · explicit synonym | `substitution_group` / category / `low_carb_alternative` |

**Why the line matters:** merging a variant into identity destroys real truth — 2% milk and
whole milk have different macros; a beef patty is a formed product, ground beef is raw. So the
answers to the product-validation questions are:
- *Hamburger Bun vs Hamburger Buns* → **same identity** (plural). Resolve to one.
- *Beef Patty vs Ground Beef* → **NOT the same identity** (substitution). Do not merge.
- *Whole Milk vs Milk* → **NOT the same identity** (variant/modifier preserved).

---

## Determinism contract

**No fuzzy matching. No AI. Ever, in any resolution used by a production path.** Every
canonical relationship is explainable and resolves identically every time. The retired
`match_ingredient_name` fuzzy substring/Jaccard logic is gone.

Resolution proceeds in a fixed, explainable order:

1. **Exact** — `canonical_name` (case-insensitive).
2. **Alias** — the name is an explicit member of some ingredient's `aliases`.
3. **Normalized key** — `normalized_name` (the deterministic identity key).
4. **Create** — a new canonical ingredient (write paths only).

When a surface form resolves by the normalized key, it is recorded as an **alias** on the
canonical ingredient — so the relationship becomes visible and search finds it. Read-only
resolution (`create=False`) never mutates.

### `normalized_name` — the identity key

`normalize_name(raw)` lowercases, strips punctuation, collapses whitespace, and singularizes
the **head (last) word only** using conservative, well-known English plural rules (irregulars
table + `-ies→-y`, `-oes→-o`, `-ches/-shes/-xes/-zes/-ses→` drop `-es`, else drop trailing
`-s`; guarded against `-ss/-us/-is/-ous` and words ≤3 chars). Modifiers are preserved, so
"whole milk" ≠ "milk". The key is stored on `Ingredient.normalized_name` (indexed) and kept
in sync by `Ingredient.save()`.

---

## Ownership — what Ingredient Intelligence owns

The `Ingredient` model is the single home for: `canonical_name`, `aliases`,
`normalized_name`, `category`, `base_measure` + `density_g_per_ml` + `default_quantity/unit`
(Container Truth substance properties), `substitution_group` / `low_carb_alternative`
(relatedness), and search. These truths are **not** scattered across Pantry, Recipes,
Receipts, or Vision — those subsystems consume the resolved identity.

---

## The seams — one resolver, every path converges

Every name→Ingredient resolution goes through Ingredient Intelligence:

| Seam | Function | Used by |
|---|---|---|
| Row creation | `resolve_ingredient(name, category, create=True)` (via `get_or_create_ingredient`) | recipe enrichment · manual entry · barcode · receipt routing · vision confirm |
| Read-only link | `resolve_ingredient(..., create=False)` (via `match_ingredient_name`) | receipt/vision candidate linking |
| Search | `search_ingredients(query)` | manual-entry autocomplete (and any future ingredient search) |
| De-duplication | `merge_duplicate_ingredients()` | one-time migration `meals/0019` |

Everything downstream — `preparation`, `inventory_gap`, `pantry_availability`,
`substitution_engine`, `pantry_ingestion` — is keyed on the resolved FK and needed **no
change**: fix the resolver, and the whole system converges on one identity per real ingredient.

The acquisition source never determines identity:

```
Recipe · Receipt · Vision · Barcode · Manual
                    │
        resolve_ingredient()   ← the one deterministic gate
                    │
            Canonical Ingredient
```

---

## Existing-data de-duplication

`merge_duplicate_ingredients()` folds pre-existing rows that share a `normalized_name` into a
single deterministic survivor (the row with a `nutrition_source`, else lowest id): repoints
`RecipeIngredient` FKs, repoints `PantryItem`s (summing quantity + repointing
`InventoryTransaction`s when a household already has the survivor), and folds the dup names
into the survivor's aliases. Idempotent. Run once by `meals/0019` (which also backfills
`normalized_name` and seeds a small curated set of true-synonym aliases; the seed skips the
test database).

---

## Certification

`apps/meals/tests/test_ingredient_intelligence.py` (17 tests): normalization (plural/case/
punct collapse; variants preserved), resolution (plural→one row, alias, read-only), no-fuzzy
matching, search, merge (fold + quantity-sum), the save hook, and the exact reported bug
(recipe "Hamburger Bun" + pantry "Hamburger Buns" → **available**). See also
`WLJ_MEAL_INTELLIGENCE_TRUTH_CERTIFICATION.md` (identity row).
