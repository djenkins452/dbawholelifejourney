# ==============================================================================
# File: apps/health/tests/test_nutrition_entity_truth.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The Nutrition ENTITY truth surface — the actual FOODS the user logged.
#   Root cause fix (2026-07-17 personalization defect): the Model Interface reached
#   nutrition AGGREGATES (calorie/protein targets, totals) but not the food ITEMS, so
#   "what have I eaten?" returned "no meal details" and personalized menus ignored the
#   user's real foods (e.g. their 45g protein shake). Additive: extends the canonical
#   NutritionQueries + a new NutritionDomainTruth (distinct registry from
#   get_domain_state('nutrition'), which is unchanged).
# ==============================================================================
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_entity import (
    entity_capability_index, get_domain_entity,
)
from apps.ai.cos_services.domain_state import get_domain_state
from apps.health.models import FoodEntry
from apps.health.services.nutrition_queries import NutritionQueries

User = get_user_model()


def _food(user, days_ago, name, protein, meal=None, brand="", cals=Decimal("160")):
    return FoodEntry.objects.create(
        user=user, logged_date=date.today() - timedelta(days=days_ago),
        meal_type=meal or FoodEntry.MEAL_BREAKFAST, food_name=name, food_brand=brand,
        quantity=Decimal("1"), serving_size=Decimal("1"), serving_unit="serving",
        status="active", total_calories=cals, total_protein_g=Decimal(str(protein)),
        total_carbohydrates_g=Decimal("5"), total_fat_g=Decimal("3"))


class NutritionEntitySurfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="nent@test.com", password="x")
        _food(self.user, 1, "Protein Shake", 45, brand="Premier")
        _food(self.user, 1, "Grilled Chicken", 52, meal=FoodEntry.MEAL_LUNCH)

    def test_nutrition_is_now_entity_capable(self):
        self.assertEqual(entity_capability_index().get("nutrition"), ("food",))

    def test_what_have_i_eaten_returns_the_actual_foods_with_macros(self):
        r = get_domain_entity(self.user, "nutrition", entity_type="food")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["count"], 2)
        names = {e["definition"]["food_name"] for e in r["entities"]}
        self.assertEqual(names, {"Protein Shake", "Grilled Chicken"})
        # macros are real record truth, not aggregates
        shake = next(e for e in r["entities"]
                     if e["definition"]["food_name"] == "Protein Shake")
        self.assertEqual(shake["performance"]["protein_g"], 45.0)
        self.assertEqual(shake["definition"]["brand"], "Premier")

    def test_the_45g_protein_shake_is_retrievable_by_name(self):
        # The exact personalization the user expected: know WHICH shake + its 45g.
        r = get_domain_entity(self.user, "nutrition", name="protein shake")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["entity"]["performance"]["protein_g"], 45.0)

    def test_empty_when_no_food_logged(self):
        other = User.objects.create_user(email="nofood@test.com", password="x")
        r = get_domain_entity(other, "nutrition", entity_type="food")
        self.assertEqual(r["status"], "empty")

    def test_queries_layer_returns_complete_entities(self):
        ents = NutritionQueries.describe(self.user)
        self.assertEqual(len(ents), 2)
        self.assertEqual(ents[0].kind, "food")


class NutritionStateUnregressedTests(TestCase):
    """The new DomainTruth entity surface must NOT change the separate SAE-backed
    get_domain_state('nutrition') path (different registry)."""

    def test_get_domain_state_nutrition_still_resolves(self):
        u = User.objects.create_user(email="nstate@test.com", password="x")
        s = get_domain_state(u, "nutrition")
        self.assertIn(s.get("status"), ("ready", "pending", "empty"))

    def test_other_entity_domains_unchanged(self):
        idx = entity_capability_index()
        self.assertIn("workout", idx.get("health", ()))
        self.assertIn("entry", idx.get("journal", ()))
        self.assertIn("food", idx.get("nutrition", ()))
