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
    current_metrics = ("dietary_profile",)
    history_metrics = ()
    entity_types = ("recipe", "pantry_item", "meal_plan", "leftover", "consumption",
                    "dietary_profile")

    def current(self, metric):
        from apps.core.truth.current import CurrentTruth
        from apps.core.truth.freshness import CURRENT as _C, MISSING as _M
        if metric == "dietary_profile":
            prof = self._dietary_profile()
            if prof is None:
                return CurrentTruth.absent(_DOMAIN, metric, _M, source="meals",
                                           reason="no dietary profile set")
            d = self._dietary_dict(prof)
            return CurrentTruth.found(_DOMAIN, metric, "set", _C, source="meals", detail=d)
        raise KeyError(f"meals current unsupported: {metric!r} "
                       f"(have {self.current_metrics})")

    def describe(self, entity_type="recipe"):
        if entity_type in (None, "recipe"):
            return self._recipes()
        if entity_type == "pantry_item":
            return self._pantry_items()
        if entity_type == "meal_plan":
            return self._meal_plan_entries()
        if entity_type == "leftover":
            return self._leftovers()
        if entity_type == "consumption":
            return self._consumptions()
        if entity_type == "dietary_profile":
            prof = self._dietary_profile()
            return ([CompleteEntity(kind="dietary_profile", identity="Dietary profile",
                                    status="active", definition=self._dietary_dict(prof),
                                    freshness=CURRENT)] if prof else [])
        raise KeyError(f"meals describe unsupported: {entity_type!r} "
                       f"(have {self.entity_types})")

    def _dietary_profile(self):
        from apps.meals.models import DietaryProfile
        return DietaryProfile.objects.filter(user=self.user).first()

    @staticmethod
    def _dietary_dict(p):
        _g = lambda a: getattr(p, a, None)
        num = lambda v: float(v) if v is not None else None
        return {"carb_limit_daily": num(_g("carb_limit_daily")),
                "protein_target_daily": num(_g("protein_target_daily")),
                "calorie_target": num(_g("calorie_target")),
                "fat_limit_daily": num(_g("fat_limit_daily")),
                "dietary_flags": _g("dietary_flags") or None,
                "diabetes_sensitive": _g("diabetes_sensitive")}

    def describe_one(self, name):
        q = (name or "").strip().lower()
        if not q:
            return None
        for e in self._recipes():               # recipe by name first
            if q in e.identity.lower():
                return e
        # then any other meals entity by identity (dietary profile / pantry item / meal
        # plan / leftover / consumption) — previously only recipes were reachable by name.
        return self._entity_by_identity(
            name, ("dietary_profile", "pantry_item", "meal_plan", "leftover", "consumption"))

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
                    "image_url": (r.image.url if getattr(r, "image", None) else None),
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
            mp = e.meal_plan
            out.append(CompleteEntity(
                kind="meal_plan",
                identity=f"{e.date} {e.meal_type}: {rt or '(unset)'}",
                definition={"date": e.date.isoformat(), "meal_type": e.meal_type,
                            "recipe": rt, "serving_count": getattr(e, "serving_count", None)},
                status="planned",
                plan={"plan_start": (mp.start_date.isoformat()
                                     if getattr(mp, "start_date", None) else None),
                      "plan_end": (mp.end_date.isoformat()
                                   if getattr(mp, "end_date", None) else None),
                      "plan_notes": (getattr(mp, "notes", "") or "").strip() or None},
                freshness=CURRENT,
            ))
        return out

    def _leftovers(self):
        from apps.meals.services import leftover_queries
        hh = _household_for(self.user)
        if hh is None:
            return []
        out = []
        for lo in leftover_queries.available_leftovers(hh):
            title = lo.recipe_title or (lo.recipe.title if lo.recipe_id else "a meal")
            prepared = (lo.preparation.prepared_at.isoformat()
                        if lo.preparation_id and getattr(lo.preparation, "prepared_at", None)
                        else None)
            out.append(CompleteEntity(
                kind="leftover",
                identity=f"{lo.servings} serving(s) of {title}",
                definition={"recipe_title": title,
                            "recipe": (lo.recipe.title if lo.recipe_id else None),
                            "servings": float(lo.servings),
                            "storage_location": lo.storage_location or None},
                status=lo.disposition,
                plan={"expiration_date": (lo.expiration_date.isoformat()
                                          if lo.expiration_date else None),
                      "prepared_at": prepared},
                standing={"is_available": bool(lo.is_available),
                          "depleted_at": (lo.depleted_at.isoformat()
                                          if lo.depleted_at else None)},
                extensions={"notes": lo.notes} if lo.notes else {},
                freshness=CURRENT,
            ))
        return out

    def _consumptions(self):
        from apps.meals.models import MealConsumption
        hh = _household_for(self.user)
        if hh is None:
            return []
        out = []
        for c in (MealConsumption.objects.filter(household=hh, status="active")
                  .select_related("recipe", "leftover", "food_entry")
                  .order_by("-consumed_at")):
            title = c.recipe_title or (c.recipe.title if c.recipe_id else "a meal")
            out.append(CompleteEntity(
                kind="consumption",
                identity=f"Ate {c.servings_consumed} serving(s) of {title}",
                definition={"recipe_title": title,
                            "servings_consumed": float(c.servings_consumed),
                            "meal_type": c.meal_type or None,
                            "from_leftover": bool(c.leftover_id)},
                status="logged",
                plan={"consumed_at": (c.consumed_at.isoformat()
                                      if c.consumed_at else None)},
                freshness=CURRENT,
            ))
        return out
