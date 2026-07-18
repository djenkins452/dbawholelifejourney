# ==============================================================================
# File: apps/meals/tests/test_food_lifecycle_certification.py
# Project: Whole Life Journey - Meal Intelligence
# Description: FOOD LIFECYCLE CERTIFICATION (Foundation 2). Behavioral proof of every
#   implemented transition, end to end:
#     Recipe save -> structured ingredients -> preparation -> pantry deduction ->
#     leftover -> consumption -> FoodEntry -> nutrition totals -> leftover reduction ->
#     discard/waste -> final disposition. Plus idempotency (no duplicate effects).
#   Each test = one certified transition in the matrix; test_full_lifecycle_walks_the
#   _whole_path proves the chain in a single run.
# ==============================================================================
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.health.models import FoodEntry, FoodItem
from apps.health.services.nutrition_queries import NutritionQueries
from apps.meals.models import (
    FoodWasteEvent, Household, HouseholdMembership, Ingredient,
    InventoryTransaction, Leftover, MealConsumption, PantryItem,
    PreparationEvent, Recipe, RecipeIngredient,
)
from apps.meals.services.consumption import consume_meal
from apps.meals.services.preparation import prepare_recipe
from apps.meals.services.waste import discard_leftover
from apps.users.models import TermsAcceptance

User = get_user_model()


class FoodLifecycleCertification(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="lifecycle@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.household = Household.objects.create(name="H", primary_user=self.user)
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin")

        self.food = FoodItem.objects.create(
            name="Chili", serving_size=Decimal("100"), serving_unit="g",
            calories=Decimal("250"), protein_g=Decimal("20"),
            carbohydrates_g=Decimal("30"), fat_g=Decimal("8"))
        self.ingredient = Ingredient.objects.create(
            canonical_name="lifechili", category="protein", nutrition_source=self.food)
        # Pantry unit "piece" matches what enrichment assigns to an unqualified line.
        self.pantry = PantryItem.objects.create(
            household=self.household, ingredient=self.ingredient,
            quantity=Decimal("20"), unit="piece")

    def _recipe_with_enriched_ingredient(self):
        # Recipe save -> enrichment writes RecipeIngredient (eager celery in tests).
        # "1 lifechili" parses to quantity=1, unit=piece, ingredient=lifechili (matches pantry).
        return Recipe.objects.create(
            user=self.user, title="Chili Bowl",
            ingredients="1 lifechili", instructions="simmer", servings=1)

    # ── Transition 1: Recipe save -> structured ingredients (enrichment) ──
    def test_recipe_save_produces_structured_ingredients(self):
        recipe = self._recipe_with_enriched_ingredient()
        self.assertTrue(RecipeIngredient.objects.filter(recipe=recipe).exists())

    # ── Full-path certification ──
    def test_full_lifecycle_walks_the_whole_path(self):
        # 1. Recipe -> structured ingredients
        recipe = self._recipe_with_enriched_ingredient()
        self.assertTrue(RecipeIngredient.objects.filter(recipe=recipe).exists())

        # 2-4. Preparation -> pantry deduction (InventoryTransaction) -> leftover
        prep_res = prepare_recipe(
            household=self.household, user=self.user, recipe=recipe,
            servings=Decimal("8"), leftover_servings=Decimal("8"))
        prep = PreparationEvent.objects.get(pk=prep_res.preparation_id)
        self.assertEqual(prep.preparation_status, PreparationEvent.PREP_COMPLETED)
        self.assertTrue(
            InventoryTransaction.objects.filter(source="preparation", preparation=prep).exists())
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("12"))  # 20 - (1 * 8 scale)
        leftover = Leftover.objects.get(pk=prep_res.leftover_id)
        self.assertEqual(leftover.servings, Decimal("8"))

        # 5-8. Consumption -> FoodEntry -> nutrition totals -> leftover reduction
        cons = consume_meal(user=self.user, household=self.household,
                            leftover=leftover, servings=Decimal("2"))
        self.assertEqual(cons.status, "ok")
        entry = FoodEntry.objects.get(pk=cons.food_entry_id)
        self.assertEqual(entry.total_calories, Decimal("500.00"))  # 250 * 2
        totals = NutritionQueries.get_daily_totals(self.user, date.today())
        self.assertEqual(totals["calories"], Decimal("500.00"))
        self.assertEqual(MealConsumption.objects.get(pk=cons.consumption_id).food_entry_id, entry.pk)
        leftover.refresh_from_db()
        self.assertEqual(leftover.servings, Decimal("6"))  # 8 - 2
        self.assertEqual(leftover.disposition, Leftover.DISP_AVAILABLE)

        # 9. Leftover -> discard (final disposition), no extra FoodEntry, no pantry change
        pantry_before = self.pantry.quantity
        waste = discard_leftover(user=self.user, household=self.household, leftover=leftover)
        self.assertEqual(waste.status, "ok")
        leftover.refresh_from_db()
        self.assertEqual(leftover.servings, Decimal("0"))
        self.assertEqual(leftover.disposition, Leftover.DISP_DISCARDED)
        self.assertTrue(FoodWasteEvent.objects.filter(leftover=leftover).exists())
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 1)  # discard != nutrition
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, pantry_before)  # no second deduction

    # ── Transition 10: retry/replay -> no duplicate effects ──
    def test_idempotency_across_the_spine(self):
        recipe = self._recipe_with_enriched_ingredient()
        prep = PreparationEvent.objects.get(
            pk=prepare_recipe(household=self.household, user=self.user, recipe=recipe,
                              servings=Decimal("8"), leftover_servings=Decimal("8")).preparation_id)
        leftover = prep.leftovers.first()
        # consume replay
        consume_meal(user=self.user, household=self.household, leftover=leftover,
                     servings=Decimal("2"), idempotency_key="k")
        consume_meal(user=self.user, household=self.household, leftover=leftover,
                     servings=Decimal("2"), idempotency_key="k")
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 1)
        leftover.refresh_from_db()
        self.assertEqual(leftover.servings, Decimal("6"))  # reduced once
        # discard replay
        discard_leftover(user=self.user, household=self.household, leftover=leftover,
                         servings=Decimal("1"), idempotency_key="w")
        discard_leftover(user=self.user, household=self.household, leftover=leftover,
                         servings=Decimal("1"), idempotency_key="w")
        self.assertEqual(FoodWasteEvent.objects.count(), 1)
        leftover.refresh_from_db()
        self.assertEqual(leftover.servings, Decimal("5"))  # 6 - 1, once
