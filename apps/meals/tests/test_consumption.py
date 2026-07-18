# ==============================================================================
# File: apps/meals/tests/test_consumption.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Foundation 2, Increment 3 — the consumption bridge, end-to-end:
#   Preparation -> Consumption -> canonical FoodEntry -> Nutrition -> Leftover -> Health.
# ==============================================================================
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.health.models import FoodEntry, FoodItem
from apps.health.services.nutrition_queries import NutritionQueries
from apps.meals.models import (
    Household, HouseholdMembership, Ingredient, Leftover, MealConsumption,
    PantryItem, PreparationEvent, Recipe, RecipeIngredient,
)
from apps.meals.services.consumption import consume_meal
from apps.meals.services.preparation import prepare_recipe
from apps.users.models import TermsAcceptance

User = get_user_model()


class ConsumptionBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="consume@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        self.household = Household.objects.create(name="H", primary_user=self.user)
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin")

        # A FoodItem gives the recipe REAL nutrition (200 cal / 20 P / 10 C / 5 F per serving).
        self.food = FoodItem.objects.create(
            name="Roast Chicken", serving_size=Decimal("100"), serving_unit="g",
            calories=Decimal("200"), protein_g=Decimal("20"),
            carbohydrates_g=Decimal("10"), fat_g=Decimal("5"))
        self.ingredient = Ingredient.objects.create(
            canonical_name="consumechicken", category="protein",
            nutrition_source=self.food)

        self.recipe = Recipe.objects.create(
            user=self.user, title="Chicken Plate", ingredients="", instructions="cook",
            servings=1)
        RecipeIngredient.objects.create(
            recipe=self.recipe, ingredient=self.ingredient,
            quantity=Decimal("1"), unit="serving", order_index=0)
        self.pantry = PantryItem.objects.create(
            household=self.household, ingredient=self.ingredient,
            quantity=Decimal("100"), unit="serving")

    def _prepare(self, servings=8, leftover=8):
        return prepare_recipe(
            household=self.household, user=self.user, recipe=self.recipe,
            servings=Decimal(str(servings)), leftover_servings=Decimal(str(leftover)))

    def _consume(self, **kw):
        return consume_meal(household=self.household, user=self.user, **kw)


class ConsumptionNutritionTests(ConsumptionBase):

    def test_consume_creates_canonical_foodentry_with_scaled_macros(self):
        r = self._consume(recipe=self.recipe, servings=Decimal("2"))
        self.assertEqual(r.status, "ok")
        entry = FoodEntry.objects.get(pk=r.food_entry_id)
        self.assertEqual(entry.user_id, self.user.id)
        self.assertEqual(entry.food_name, "Chicken Plate")
        # 200 cal/serving * 2 servings = 400  (computed by nutrition_calculator, not us)
        self.assertEqual(entry.total_calories, Decimal("400.00"))
        self.assertEqual(entry.total_protein_g, Decimal("40.00"))

    def test_partial_servings(self):
        r = self._consume(recipe=self.recipe, servings=Decimal("0.5"))
        entry = FoodEntry.objects.get(pk=r.food_entry_id)
        self.assertEqual(entry.total_calories, Decimal("100.00"))  # 200 * 0.5

    def test_no_duplicate_nutrition_writer(self):
        # The nutrition record IS a health.FoodEntry; MealConsumption only links to it.
        r = self._consume(recipe=self.recipe, servings=Decimal("1"))
        mc = MealConsumption.objects.get(pk=r.consumption_id)
        self.assertEqual(mc.food_entry_id, r.food_entry_id)
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 1)

    def test_nutrition_flows_into_canonical_daily_read(self):
        # Proves "update nutrition + health truth": the FoodEntry shows up in the
        # canonical NutritionQueries daily totals (the one nutrition read authority).
        self._consume(recipe=self.recipe, servings=Decimal("3"))
        totals = NutritionQueries.get_daily_totals(self.user, date.today())
        self.assertEqual(totals["calories"], Decimal("600.00"))  # 200 * 3
        self.assertEqual(totals["protein_g"], Decimal("60.00"))


class ConsumptionLeftoverTests(ConsumptionBase):

    def test_reduces_leftovers(self):
        prep = self._prepare(servings=8, leftover=8).preparation_id
        prep = PreparationEvent.objects.get(pk=prep)
        r = self._consume(preparation=prep, servings=Decimal("2"))
        self.assertEqual(r.leftover_remaining, 6.0)  # 8 - 2
        lo = Leftover.objects.get(pk=r.leftover_id)
        self.assertEqual(lo.servings, Decimal("6.00"))

    def test_multiple_consumptions_from_one_preparation(self):
        prep = PreparationEvent.objects.get(pk=self._prepare(8, 8).preparation_id)
        self._consume(preparation=prep, servings=Decimal("2"))   # 8 -> 6
        r2 = self._consume(preparation=prep, servings=Decimal("3"))  # 6 -> 3
        self.assertEqual(r2.leftover_remaining, 3.0)
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 2)
        self.assertEqual(MealConsumption.objects.count(), 2)

    def test_leftovers_not_assumed_consumed_when_absent(self):
        prep = PreparationEvent.objects.get(
            pk=self._prepare(servings=4, leftover=0).preparation_id)  # no leftover
        r = self._consume(preparation=prep, servings=Decimal("1"))
        self.assertEqual(r.status, "ok")
        self.assertIsNone(r.leftover_id)
        self.assertIsNotNone(r.food_entry_id)  # nutrition still logged

    def test_leftover_never_negative(self):
        prep = PreparationEvent.objects.get(pk=self._prepare(8, 2).preparation_id)
        r = self._consume(preparation=prep, servings=Decimal("5"))  # eat more than left
        self.assertEqual(r.leftover_remaining, 0.0)


class ConsumptionIdempotencyTests(ConsumptionBase):

    def test_same_key_never_double_logs(self):
        prep = PreparationEvent.objects.get(pk=self._prepare(8, 8).preparation_id)
        r1 = self._consume(preparation=prep, servings=Decimal("2"), idempotency_key="c1")
        r2 = self._consume(preparation=prep, servings=Decimal("2"), idempotency_key="c1")
        self.assertEqual(r1.status, "ok")
        self.assertEqual(r2.status, "replayed")
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 1)
        self.assertEqual(MealConsumption.objects.count(), 1)
        lo = Leftover.objects.get(pk=r1.leftover_id)
        self.assertEqual(lo.servings, Decimal("6.00"))  # reduced ONCE

    def test_fail_closed_rollback(self):
        with patch("apps.meals.services.consumption.MealConsumption.objects.create",
                   side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self._consume(recipe=self.recipe, servings=Decimal("1"))
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 0)
        self.assertEqual(MealConsumption.objects.count(), 0)


class ConsumptionEndToEndViewTests(ConsumptionBase):

    def test_full_lifecycle_via_views(self):
        self.client.force_login(self.user)
        # Prepare (increment 2)
        prep_resp = self.client.post(
            reverse("meals:prepare_recipe", args=[self.recipe.pk]),
            {"servings": "8", "leftover_servings": "8", "idempotency_key": "p1"})
        self.assertEqual(prep_resp.status_code, 200)
        prep = PreparationEvent.objects.get(household=self.household)
        # Consume (increment 3)
        cons_resp = self.client.post(
            reverse("meals:consume_meal", args=[prep.pk]),
            {"servings": "2", "idempotency_key": "cv1"})
        self.assertEqual(cons_resp.status_code, 200)
        self.assertContains(cons_resp, "Meal logged")
        # FoodEntry created + nutrition in the canonical daily read + leftover reduced
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 1)
        totals = NutritionQueries.get_daily_totals(self.user, date.today())
        self.assertEqual(totals["calories"], Decimal("400.00"))  # 200 * 2
        self.assertEqual(prep.leftovers.first().servings, Decimal("6.00"))

    def test_view_refresh_is_idempotent(self):
        self.client.force_login(self.user)
        prep = PreparationEvent.objects.get(pk=self._prepare(8, 8).preparation_id)
        url = reverse("meals:consume_meal", args=[prep.pk])
        self.client.post(url, {"servings": "2", "idempotency_key": "cv2"})
        self.client.post(url, {"servings": "2", "idempotency_key": "cv2"})  # refresh
        self.assertEqual(FoodEntry.objects.filter(user=self.user).count(), 1)
        self.assertEqual(prep.leftovers.first().servings, Decimal("6.00"))
