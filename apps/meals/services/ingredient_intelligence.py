# ==============================================================================
# File: apps/meals/services/ingredient_intelligence.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Canonical Ingredient Intelligence — the single deterministic authority for
#   ingredient IDENTITY (is this name the same real-world ingredient as that one?).
# ==============================================================================
"""One deterministic answer to "are these two names the same ingredient?"

Before this module, every row-creating path (recipe enrichment, manual entry, barcode,
receipt, vision) funneled through ``get_or_create_ingredient``, whose only de-dup was an
exact ``canonical_name__iexact`` — so "Hamburger Buns" and "Hamburger Bun" became two rows,
and a recipe needing one showed a pantry gap while the other was stocked. The ``aliases``
field existed but was never populated; ``match_ingredient_name`` used fuzzy substring/Jaccard
matching (non-deterministic, unexplainable) only on the read side.

This module makes identity ONE deterministic, explainable truth that every seam consumes:

  IDENTITY  — same real-world ingredient (case, punctuation, whitespace, singular/plural,
              explicit synonyms, brand-independent). Resolves to ONE canonical Ingredient.
  NOT identity (handled elsewhere as SUBSTITUTION) — different-but-interchangeable things
              (Beef Patty vs Ground Beef; 2% vs Whole Milk). These are NEVER merged here;
              collapsing them would destroy real nutritional/product differences.

Determinism contract: NO fuzzy matching, NO AI, in any resolution used by a write path.
Every canonical relationship is explainable — a name resolves via (1) exact canonical,
(2) an explicit alias, or (3) a deterministic ``normalized_name`` key — and resolves
identically every time. ``normalized_name`` is a stored, indexed projection of the name
(lowercased, de-punctuated, whitespace-collapsed, head-noun singularized).
"""
import logging
import re

from django.db.models import Q

logger = logging.getLogger(__name__)

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")

# Irregular English plurals we normalize deterministically (explicit, not guessed).
_IRREGULAR_PLURALS = {
    "leaves": "leaf", "loaves": "loaf", "halves": "half", "knives": "knife",
    "potatoes": "potato", "tomatoes": "tomato", "berries": "berry",
    "cherries": "cherry", "peppers": "pepper",
}

# Words ending in 's' that are already singular — never strip these.
_SINGULAR_S_SUFFIXES = ("ss", "us", "is", "ous")


def _singularize(word: str) -> str:
    """Deterministic singular of one word. Conservative — only well-known English plural
    patterns; anything ambiguous is left unchanged so identity never merges by accident."""
    if word in _IRREGULAR_PLURALS:
        return _IRREGULAR_PLURALS[word]
    if len(word) <= 3:
        return word
    if word.endswith(_SINGULAR_S_SUFFIXES):
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"          # berries -> berry, patties -> patty
    if word.endswith("oes") and len(word) > 4:
        return word[:-2]                # tomatoes -> tomato
    if word.endswith(("ches", "shes", "xes", "zes", "ses")):
        return word[:-2]                # dishes -> dish, boxes -> box
    if word.endswith("s"):
        return word[:-1]                # buns -> bun, eggs -> egg
    return word


def normalize_name(raw: str) -> str:
    """The deterministic canonical KEY for an ingredient name.

    Lowercase, strip punctuation, collapse whitespace, and singularize the HEAD (last) word
    only — modifiers ("ground", "whole") are preserved so "whole milk" and "milk" stay
    distinct. Same input → same key, every time. Explainable and reversible in reasoning.
    """
    if not raw:
        return ""
    s = _PUNCT_RE.sub(" ", raw.lower())
    s = _WS_RE.sub(" ", s).strip()
    if not s:
        return ""
    words = s.split(" ")
    words[-1] = _singularize(words[-1])
    return " ".join(words)


def resolve_ingredient(raw_name: str, category: str = "other", *, create: bool = True):
    """THE canonical resolver — map any surface name to its one canonical Ingredient.

    Deterministic order (every step explainable):
      1. exact canonical_name (case-insensitive)
      2. explicit alias (exact, case-insensitive)
      3. normalized_name key (case/punct/whitespace/plural)
      4. create a new canonical Ingredient (only when create=True)

    When a surface form resolves to an existing ingredient by the normalized key (not by an
    exact/alias hit), the surface form is recorded as an alias — so search finds it and the
    relationship is visible. Returns the Ingredient, or None when create=False and no match.
    """
    from django.db import IntegrityError, transaction

    from apps.meals.models import Ingredient

    name_lower = (raw_name or "").lower().strip()
    if not name_lower:
        return None

    # 1. Exact canonical.
    ing = Ingredient.objects.filter(canonical_name__iexact=name_lower).first()
    if ing:
        return ing

    # 2. Explicit alias (deterministic exact membership).
    ing = Ingredient.objects.filter(aliases__contains=[name_lower]).first()
    if ing:
        return ing

    # 3. Deterministic normalized key.
    norm = normalize_name(name_lower)
    if norm:
        ing = Ingredient.objects.filter(normalized_name=norm).order_by("id").first()
        if ing:
            # Learn the surface form as an alias — but only on the write path, so a
            # read-only match (create=False) never mutates truth.
            if create:
                _record_alias(ing, name_lower)
            return ing

    if not create:
        return None

    # 4. Create a new canonical ingredient (first spelling wins as canonical).
    try:
        with transaction.atomic():
            ing = Ingredient.objects.create(
                canonical_name=name_lower,
                normalized_name=norm,
                category=category or "other",
            )
        logger.info("Ingredient Intelligence: created canonical '%s' (norm='%s')", name_lower, norm)
        return ing
    except IntegrityError:
        # Concurrent create on the same canonical_name — re-fetch.
        existing = Ingredient.objects.filter(canonical_name__iexact=name_lower).first()
        if existing:
            return existing
        raise


def _record_alias(ingredient, alias_lower: str) -> None:
    """Add a surface form to an ingredient's aliases if not already present (idempotent)."""
    if not alias_lower or alias_lower == (ingredient.canonical_name or "").lower():
        return
    aliases = list(ingredient.aliases or [])
    if alias_lower in (a.lower() for a in aliases):
        return
    aliases.append(alias_lower)
    ingredient.aliases = aliases
    ingredient.save(update_fields=["aliases", "updated_at"])


def search_ingredients(query: str, limit: int = 12):
    """The single ingredient SEARCH authority — case-insensitive substring across canonical
    name, aliases, and the normalized key. Powers manual-entry autocomplete and any other
    ingredient search, so search logic is never duplicated. Returns a queryset.
    """
    from apps.meals.models import Ingredient

    q = (query or "").strip()
    if not q:
        return Ingredient.objects.none()
    norm = normalize_name(q)
    filters = Q(canonical_name__icontains=q) | Q(aliases__icontains=q)
    if norm:
        filters |= Q(normalized_name__icontains=norm)
    return Ingredient.objects.filter(filters).order_by("canonical_name")[:limit]


def merge_duplicate_ingredients(*, apps_registry=None, logger_=None) -> int:
    """One-time deterministic de-duplication: fold Ingredients that share a normalized_name
    into a single survivor, repointing every FK and folding names into aliases. Safe to run
    repeatedly (idempotent once merged). Returns the number of duplicate rows removed.

    Determinism: survivor = the row with a nutrition_source if any, else the lowest id.
    RecipeIngredient FKs are repointed; PantryItems are repointed (or their quantity summed
    into the survivor's existing item in the same household, with the dup's InventoryTransactions
    repointed) so no household ends up with two rows for one ingredient.
    """
    from collections import defaultdict

    log = logger_ or logger
    if apps_registry is not None:
        Ingredient = apps_registry.get_model("meals", "Ingredient")
        RecipeIngredient = apps_registry.get_model("meals", "RecipeIngredient")
        PantryItem = apps_registry.get_model("meals", "PantryItem")
        InventoryTransaction = apps_registry.get_model("meals", "InventoryTransaction")
    else:
        from apps.meals.models import (
            Ingredient, InventoryTransaction, PantryItem, RecipeIngredient,
        )

    groups = defaultdict(list)
    for ing in Ingredient.objects.all().order_by("id"):
        key = ing.normalized_name or normalize_name(ing.canonical_name)
        if key:
            groups[key].append(ing)

    removed = 0
    for key, rows in groups.items():
        if len(rows) < 2:
            continue
        survivor = next((r for r in rows if r.nutrition_source_id), rows[0])
        dups = [r for r in rows if r.id != survivor.id]

        alias_set = {a.lower() for a in (survivor.aliases or [])}
        for dup in dups:
            RecipeIngredient.objects.filter(ingredient=dup).update(ingredient=survivor)

            for dup_item in PantryItem.objects.filter(ingredient=dup):
                surv_item = PantryItem.objects.filter(
                    household=dup_item.household, ingredient=survivor
                ).first()
                if surv_item is None:
                    dup_item.ingredient = survivor
                    dup_item.save(update_fields=["ingredient"])
                else:
                    surv_item.quantity = (surv_item.quantity or 0) + (dup_item.quantity or 0)
                    surv_item.save(update_fields=["quantity"])
                    InventoryTransaction.objects.filter(pantry_item=dup_item).update(
                        pantry_item=surv_item)
                    dup_item.delete()

            # Fold the dup's names into the survivor's aliases so search still finds them.
            for nm in [dup.canonical_name] + list(dup.aliases or []):
                nml = (nm or "").lower()
                if nml and nml != (survivor.canonical_name or "").lower() and nml not in alias_set:
                    alias_set.add(nml)
            dup.delete()
            removed += 1

        survivor.aliases = sorted(alias_set)
        survivor.save(update_fields=["aliases"])
        log.info("Ingredient Intelligence merge: '%s' absorbed %d duplicate(s)",
                 survivor.canonical_name, len(dups))

    return removed
