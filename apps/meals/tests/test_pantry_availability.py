# ==============================================================================
# File: apps/meals/tests/test_pantry_availability.py
# Project: Whole Life Journey - Meal Intelligence
# Description: The single pantry-availability authority + the anti-drift guarantee that
#   Meal Suggestions (analyze_recipe_gaps) and recipe Preparation now agree on "is this in
#   the pantry?" for the SAME pantry state — the defect product validation surfaced.
# ==============================================================================
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.meals.models import (
    Household, HouseholdMembership, Ingredient, PantryItem, Recipe, RecipeIngredient,
)
from apps.meals.services.inventory_gap import analyze_recipe_gaps
from apps.meals.services.meal_scoring import score_recipe
from apps.meals.services.pantry_availability import (
    AVAIL_FULL, AVAIL_NEEDS_INFO, AVAIL_NONE, AVAIL_PARTIAL, get_pantry_availability,
)
from apps.meals.services.preparation import prepare_recipe
from apps.users.models import TermsAcceptance

User = get_user_model()


class AuthorityTests(TestCase):
    """The read-only get_pantry_availability authority."""

    def _pantry(self, unit="g", quantity="500", net=None, net_unit="", density=None):
        ing = Ingredient.objects.create(
            canonical_name="pa_ing", category="other",
            base_measure=("mass" if density else "count"),
            density_g_per_ml=(Decimal(density) if density else None))
        h = Household.objects.create(name="H", primary_user=None) if False else None
        return PantryItem(
            ingredient=ing, quantity=Decimal(quantity), unit=unit,
            net_content=(Decimal(net) if net else None), net_content_unit=net_unit)

    def test_none_pantry_is_none_status(self):
        a = get_pantry_availability(None, Decimal("2"), "tbsp")
        self.assertEqual(a.status, AVAIL_NONE)

    def test_same_unit_full_and_partial(self):
        p = self._pantry(unit="g", quantity="500")
        self.assertEqual(get_pantry_availability(p, Decimal("200"), "g").status, AVAIL_FULL)
        self.assertEqual(get_pantry_availability(p, Decimal("600"), "g").status, AVAIL_PARTIAL)

    def test_cross_unit_with_density_converts(self):
        # 1 cup flour = 236.588 ml * 0.53 = 125.39 g; 500 g on hand -> available.
        p = self._pantry(unit="g", quantity="500", density="0.53")
        a = get_pantry_availability(p, Decimal("1"), "cup")
        self.assertEqual(a.status, AVAIL_FULL)
        self.assertAlmostEqual(float(a.required_base), 125.39, delta=0.5)

    def test_cross_unit_without_density_needs_info(self):
        # volume recipe vs mass pantry, no density -> cannot bridge -> needs_info (fail closed).
        p = self._pantry(unit="g", quantity="500", density=None)
        self.assertEqual(get_pantry_availability(p, Decimal("1"), "cup").status, AVAIL_NEEDS_INFO)

    def test_zero_stock_is_none(self):
        p = self._pantry(unit="g", quantity="0")
        self.assertEqual(get_pantry_availability(p, Decimal("1"), "g").status, AVAIL_NONE)


class DriftGuaranteeTests(TestCase):
    """Suggestions and Preparation must agree on the SAME pantry state (the reported bug)."""

    def setUp(self):
        self.user = User.objects.create_user(email="pa@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.household = Household.objects.create(name="H", primary_user=self.user)
        HouseholdMembership.objects.create(household=self.household, user=self.user, role="admin")

    def test_suggestions_and_preparation_agree_on_convertible_item(self):
        # flour: mass, density 0.53. Pantry stored in grams; recipe calls for cups.
        # OLD naive Suggestions logic ("pantry.unit == needed_unit") wrongly scored this
        # PARTIAL/needs-store while Preparation fully deducted it. Now both agree.
        flour = Ingredient.objects.create(
            canonical_name="pa_flour", category="grain",
            base_measure="mass", density_g_per_ml=Decimal("0.53"))
        PantryItem.objects.create(
            household=self.household, ingredient=flour,
            quantity=Decimal("2270"), unit="g",           # a full 5 lb bag, in base grams
            net_content=Decimal("2270"), net_content_unit="g")
        recipe = Recipe.objects.create(user=self.user, title="Bread", ingredients="",
                                       instructions="bake", servings=1)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=flour,
                                        quantity=Decimal("1"), unit="cup", order_index=0)

        # Suggestions: the item is AVAILABLE (not partial) — the drift is gone.
        gaps = analyze_recipe_gaps(recipe, self.household)
        self.assertEqual(gaps.gaps[0].gap_type, "available")
        self.assertEqual(gaps.available_count, 1)
        self.assertEqual(gaps.availability_score, Decimal("1.0"))

        # Preparation: the item is APPLIED (fully deducted) — same verdict as Suggestions.
        result = prepare_recipe(household=self.household, user=self.user, recipe=recipe,
                                servings=Decimal("1"))
        self.assertEqual(result.deductions[0]["status"], "applied")

    def test_meal_score_reflects_full_availability(self):
        # A recipe whose ingredient is fully in the pantry scores > 0 AND its inventory
        # factor is maxed (availability now flows through the shared authority). The 0-in-the-
        # UI defect was a display artifact (0-1 fraction shown with floatformat:0); the raw
        # score is a real fraction, never literally zero, and rises with availability.
        rice = Ingredient.objects.create(canonical_name="pa_rice", category="grain")
        PantryItem.objects.create(household=self.household, ingredient=rice,
                                  quantity=Decimal("1000"), unit="g")
        recipe = Recipe.objects.create(user=self.user, title="Rice", ingredients="",
                                       instructions="cook", servings=1)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=rice,
                                        quantity=Decimal("200"), unit="g", order_index=0)

        score = score_recipe(recipe, self.household)
        self.assertGreater(score.total_score, Decimal("0"))
        inventory = next(f for f in score.factors if f.name == "inventory_availability")
        self.assertEqual(inventory.value, Decimal("1.0"))  # fully available via the authority
