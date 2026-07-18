"""MealsDomainTruth — canonical Layer-1 interface to Meal-Intelligence truth.

Thin facade over the canonical meals models (Recipe / PantryItem / MealPlanEntry),
read live. Owns NO new retrieval logic and reads NO SAE snapshot. Household-scoped
truth resolves from the user's HouseholdMembership. Meals previously had NO provider —
a whole domain of stored truth (recipes, pantry, meal plans) was unreachable.

KEYSTONE: Recipe.ingredients (free-text, one per line) is the AUTHORITATIVE ingredient
truth. Recipe.structured_ingredients (RecipeIngredient rows) is a best-effort parse
overlay that may be empty — never report "0 ingredients" off it.
"""
from apps.core.truth.domain import DomainTruth, register_domain_truth
from apps.core.truth.entity import CompleteEntity
from apps.core.truth.freshness import CURRENT

_DOMAIN = "meals"


def _household_for(user):
    try:
        from apps.meals.models import HouseholdMembership
        m = (HouseholdMembership.objects.filter(user=user)
             .select_related("household").first())
        return m.household if m else None
    except Exception:
        return None


@register_domain_truth
class MealsDomainTruth(DomainTruth):
    domain = _DOMAIN
    current_metrics = ()
    history_metrics = ()
    entity_types = ("recipe", "pantry_item", "meal_plan")

    def describe(self, entity_type="recipe"):
        if entity_type in (None, "recipe"):
            return self._recipes()
        if entity_type == "pantry_item":
            return self._pantry_items()
        if entity_type == "meal_plan":
            return self._meal_plan_entries()
        raise KeyError(f"meals describe unsupported: {entity_type!r} "
                       f"(have {self.entity_types})")

    def describe_one(self, name):
        name = (name or "").strip().lower()
        if not name:
            return None
        for e in self._recipes():
            if name in e.identity.lower():
                return e
        return None

    def _recipes(self):
        from apps.meals.models import Recipe
        out = []
        qs = Recipe.objects.filter(user=self.user)
        try:
            qs = qs.prefetch_related("structured_ingredients__ingredient")
        except Exception:
            pass
        for r in qs:
            text_lines = [ln.strip() for ln in (getattr(r, "ingredients", "") or "").splitlines()
                          if ln.strip()]
            structured = []
            try:
                for ri in r.structured_ingredients.all():
                    structured.append(
                        {"name": getattr(ri.ingredient, "canonical_name", None),
                         "quantity": float(ri.quantity) if ri.quantity is not None else None,
                         "unit": ri.unit, "optional": ri.is_optional,
                         "prep": ri.preparation_notes or None})
            except Exception:
                structured = []
            out.append(CompleteEntity(
                kind="recipe",
                identity=r.title,
                definition={"category": (getattr(r, "category", None) or None),
                            "difficulty": (getattr(r, "difficulty", None) or None),
                            "servings": getattr(r, "servings", None),
                            "tags": (getattr(r, "tags", None) or None),
                            "source": (getattr(r, "source", None) or None),
                            "ingredient_count": len(text_lines)},
                status="active",
                plan={"ingredients_text": text_lines,
                      "structured_ingredients": structured,
                      "instructions": (getattr(r, "instructions", "") or "").strip() or None,
                      "prep_time_minutes": getattr(r, "prep_time_minutes", None),
                      "cook_time_minutes": getattr(r, "cook_time_minutes", None),
                      "total_time_minutes": getattr(r, "total_time_minutes", None)},
                standing={"is_favorite": bool(getattr(r, "is_favorite", False))},
                extensions={k: v for k, v in {
                    "description": (getattr(r, "description", "") or "").strip() or None,
                    "notes": (getattr(r, "notes", "") or "").strip() or None,
                    "source_url": (getattr(r, "source_url", None) or None),
                }.items() if v},
                freshness=CURRENT,
            ))
        out.sort(key=lambda e: e.identity.lower())
        return out

    def _pantry_items(self):
        from apps.meals.models import PantryItem
        hh = _household_for(self.user)
        if hh is None:
            return []
        out = []
        for p in (PantryItem.objects.filter(household=hh, quantity__gt=0)
                  .select_related("ingredient")):
            out.append(CompleteEntity(
                kind="pantry_item",
                identity=getattr(p.ingredient, "canonical_name", str(p.ingredient)),
                definition={"quantity": float(p.quantity), "unit": p.unit,
                            "storage_location": getattr(p, "storage_location", None)},
                status="in_stock",
                plan={"expiration_date": (p.expiration_date_estimated.isoformat()
                                          if getattr(p, "expiration_date_estimated", None)
                                          else None)},
                standing={"is_expired": getattr(p, "is_expired", None),
                          "days_until_expiration": getattr(p, "days_until_expiration", None),
                          "last_confirmed": (p.last_confirmed_at.isoformat()
                                             if getattr(p, "last_confirmed_at", None)
                                             else None)},
                freshness=CURRENT,
            ))
        out.sort(key=lambda e: e.identity.lower())
        return out

    def _meal_plan_entries(self):
        from apps.meals.models import MealPlanEntry
        hh = _household_for(self.user)
        if hh is None:
            return []
        out = []
        for e in (MealPlanEntry.objects.filter(meal_plan__household=hh)
                  .select_related("recipe", "meal_plan").order_by("date", "meal_type")):
            rt = getattr(e.recipe, "title", None) if e.recipe_id else None
            out.append(CompleteEntity(
                kind="meal_plan",
                identity=f"{e.date} {e.meal_type}: {rt or '(unset)'}",
                definition={"date": e.date.isoformat(), "meal_type": e.meal_type,
                            "recipe": rt, "serving_count": getattr(e, "serving_count", None)},
                status="planned",
                freshness=CURRENT,
            ))
        return out
