# ==============================================================================
# File: apps/meals/tests/test_recipe_prepare_entrypoint.py
# Project: Whole Life Journey - Meal Intelligence
# Description: Regression — the Foundation 2 "Record Preparation" entry point must be
#   visible on the recipe detail page users actually browse to (life:recipe_detail),
#   not stranded on the meals intelligence page reachable only from meal cards.
#   (Defect found in the first real-world validation, 2026-07-18.)
# ==============================================================================
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.meals.models import (
    Household, HouseholdMembership, Ingredient, PantryItem, PreparationEvent,
    Recipe, RecipeIngredient,
)
from apps.users.models import TermsAcceptance

User = get_user_model()


class RecipePrepareEntryPointTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="entry@test.com", password="x")
        TermsAcceptance.objects.create(
            user=self.user, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()
        self.household = Household.objects.create(name="H", primary_user=self.user)
        HouseholdMembership.objects.create(
            household=self.household, user=self.user, role="admin")
        self.recipe = Recipe.objects.create(
            user=self.user, title="Tacos", ingredients="", instructions="cook",
            servings=4)
        self.ingredient = Ingredient.objects.create(canonical_name="entrybeef", category="protein")
        RecipeIngredient.objects.create(
            recipe=self.recipe, ingredient=self.ingredient,
            quantity=Decimal("2"), unit="cup", order_index=0)
        PantryItem.objects.create(
            household=self.household, ingredient=self.ingredient,
            quantity=Decimal("10"), unit="cup")
        self.client.force_login(self.user)

    def test_life_recipe_detail_exposes_the_prepare_entrypoint(self):
        resp = self.client.get(reverse("life:recipe_detail", args=[self.recipe.pk]))
        self.assertEqual(resp.status_code, 200)
        # The action the user can click is present and points at the F2 workflow.
        self.assertContains(resp, reverse("meals:prepare_recipe", args=[self.recipe.pk]))
        self.assertContains(resp, "I cooked this")

    def test_preparing_from_that_page_records_a_preparation(self):
        # Exactly what the button on the life page does.
        resp = self.client.post(
            reverse("meals:prepare_recipe", args=[self.recipe.pk]),
            {"servings": "4", "leftover_servings": "2", "idempotency_key": "entry-1"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Preparation recorded")
        prep = PreparationEvent.objects.filter(
            household=self.household, recipe=self.recipe).first()
        self.assertIsNotNone(prep)
        self.assertEqual(prep.preparation_status, PreparationEvent.PREP_COMPLETED)
