# ==============================================================================
# File: apps/meals/tests/test_pantry_manual_entry.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Manual Pantry Entry — the universal-fallback acquisition path. Proves manual
#   entry ends in the SAME canonical PantryItem as every other path (finalize_pantry_item),
#   reuses ingredients (no duplicates), captures Container Truth up front, and that the
#   resulting item is consumable by recipe Preparation.
# ==============================================================================
import json
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.meals.models import (
    Household, HouseholdMembership, Ingredient, InventoryTransaction, PantryItem,
    Recipe, RecipeIngredient,
)
from apps.meals.services.preparation import prepare_recipe
from apps.users.models import TermsAcceptance

User = get_user_model()


class ManualEntryBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="manual@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.household = Household.objects.create(name="H", primary_user=self.user)
        HouseholdMembership.objects.create(household=self.household, user=self.user, role="admin")
        self.client = Client()
        self.client.force_login(self.user)

    def _add(self, **data):
        return self.client.post("/meals/pantry/add/", data)


class ManualAddTests(ManualEntryBase):
    def test_creates_canonical_pantry_item_via_finalize(self):
        # New ingredient, manual source, quantity + location -> one canonical PantryItem +
        # a source="manual" InventoryTransaction (identical shape to every other path).
        resp = self._add(new_ingredient_name="Homemade Salsa", category="condiment",
                         quantity="2", unit="piece", storage_location="fridge")
        self.assertEqual(resp.status_code, 302)
        ing = Ingredient.objects.get(canonical_name="homemade salsa")
        item = PantryItem.objects.get(household=self.household, ingredient=ing)
        self.assertEqual(item.quantity, Decimal("2"))
        self.assertEqual(item.storage_location, "fridge")
        self.assertTrue(InventoryTransaction.objects.filter(
            pantry_item=item, source="manual").exists())

    def test_reuses_existing_ingredient_by_id_no_duplicate(self):
        existing = Ingredient.objects.create(canonical_name="bulk flour", category="grain")
        before = Ingredient.objects.count()
        self._add(ingredient_id=str(existing.id), quantity="1", unit="piece",
                  storage_location="pantry")
        self.assertEqual(Ingredient.objects.count(), before)  # no new ingredient
        self.assertTrue(PantryItem.objects.filter(
            household=self.household, ingredient=existing).exists())

    def test_new_name_matching_existing_reuses_case_insensitive(self):
        Ingredient.objects.create(canonical_name="fresh bread", category="grain")
        before = Ingredient.objects.count()
        # Typed a new name that already exists (different case) -> get_or_create reuses it.
        self._add(new_ingredient_name="Fresh Bread", category="grain",
                  quantity="1", unit="piece", storage_location="pantry")
        self.assertEqual(Ingredient.objects.count(), before)

    def test_requires_an_ingredient(self):
        before = PantryItem.objects.count()
        self._add(quantity="1", unit="piece", storage_location="pantry")  # no id, no name
        self.assertEqual(PantryItem.objects.count(), before)  # nothing created

    def test_captures_container_truth_up_front(self):
        # Manual "2 bottles of ketchup, 20 fl oz each" — captured once, applied to the
        # Ingredient (canonical) AND the PantryItem (exact base quantity).
        self._add(new_ingredient_name="Farmers Ketchup", category="condiment",
                  quantity="2", unit="piece", storage_location="pantry",
                  net_content_amount="20", net_content_unit="fl_oz", container_type="bottle")
        ing = Ingredient.objects.get(canonical_name="farmers ketchup")
        self.assertEqual(ing.base_measure, "volume")            # canonical substance truth
        item = PantryItem.objects.get(ingredient=ing)
        # 20 fl oz = 591.48 ml per container; 2 containers -> ~1182.96 ml stored (exact base).
        self.assertEqual(item.net_content_unit, "ml")
        self.assertAlmostEqual(float(item.net_content), 591.48, delta=1.0)
        self.assertAlmostEqual(float(item.quantity), 1182.96, delta=2.0)

    def test_sets_explicit_expiration_and_never_invents_one(self):
        # With an explicit date -> stored; without -> none invented (ingredient has no shelf life).
        self._add(new_ingredient_name="Local Butcher Steak", category="protein",
                  quantity="1", unit="piece", storage_location="fridge",
                  expiration_date="2026-08-01")
        item = PantryItem.objects.get(ingredient__canonical_name="local butcher steak")
        self.assertEqual(str(item.expiration_date_estimated), "2026-08-01")

        self._add(new_ingredient_name="Garden Tomatoes", category="vegetable",
                  quantity="5", unit="piece", storage_location="pantry")
        item2 = PantryItem.objects.get(ingredient__canonical_name="garden tomatoes")
        self.assertIsNone(item2.expiration_date_estimated)


class IngredientSearchTests(ManualEntryBase):
    def test_substring_case_insensitive_and_create_option_implicit(self):
        Ingredient.objects.create(canonical_name="ketchup", category="condiment")
        Ingredient.objects.create(canonical_name="protein powder", category="protein")
        Ingredient.objects.create(canonical_name="protein bar", category="protein")

        resp = self.client.get("/meals/pantry/ingredient-search/", {"q": "KET"})
        names = [r["name"] for r in resp.json()["results"]]
        self.assertIn("ketchup", names)

        resp2 = self.client.get("/meals/pantry/ingredient-search/", {"q": "prot"})
        names2 = [r["name"] for r in resp2.json()["results"]]
        self.assertIn("protein powder", names2)
        self.assertIn("protein bar", names2)

    def test_empty_query_returns_no_results(self):
        resp = self.client.get("/meals/pantry/ingredient-search/", {"q": ""})
        self.assertEqual(resp.json()["results"], [])


class ManualEntryConsumptionTests(ManualEntryBase):
    def test_manually_added_item_is_consumable_by_preparation(self):
        # End-to-end: manual add with Container Truth -> recipe consumes it -> deducted.
        self._add(new_ingredient_name="Bulk Olive Oil", category="fat",
                  quantity="1", unit="piece", storage_location="pantry",
                  net_content_amount="500", net_content_unit="ml", container_type="bottle")
        ing = Ingredient.objects.get(canonical_name="bulk olive oil")
        item = PantryItem.objects.get(ingredient=ing)
        self.assertAlmostEqual(float(item.quantity), 500.0, delta=1.0)  # exact base ml

        recipe = Recipe.objects.create(user=self.user, title="Dressing", ingredients="",
                                       instructions="mix", servings=1)
        RecipeIngredient.objects.create(recipe=recipe, ingredient=ing,
                                        quantity=Decimal("2"), unit="tbsp", order_index=0)
        result = prepare_recipe(household=self.household, user=self.user, recipe=recipe,
                                servings=Decimal("1"))
        self.assertEqual(result.deductions[0]["status"], "applied")  # 2 tbsp = 29.574 ml
        item.refresh_from_db()
        self.assertAlmostEqual(float(item.quantity), 470.43, delta=1.0)  # 500 - 29.574
