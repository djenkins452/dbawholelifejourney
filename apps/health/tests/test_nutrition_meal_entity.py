# ==============================================================================
# File: apps/health/tests/test_nutrition_meal_entity.py
# Description: The MEAL truth surface — exposing the existing deterministic meal
#              aggregation (NutritionQueries.get_meal_totals) as a conversational
#              entity, exactly as `food` is. No new model, no duplicate aggregation.
# ==============================================================================
from datetime import date, time

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_entity import get_domain_entity
from apps.core.truth.catalog import truth_catalog
from apps.core.truth.domain import get_domain_truth
from apps.health.models import FoodEntry
from apps.health.services.nutrition_queries import NutritionQueries

User = get_user_model()


def _food(user, name, d, meal, cal, *, t=None):
    return FoodEntry.objects.create(
        user=user, food_name=name, serving_size="1", serving_unit="each",
        logged_date=d, logged_time=t, meal_type=meal, total_calories=cal,
        total_protein_g=10)


class MealSurfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="meal@example.com", password="x")
        # April 7: lunch + dinner (dinner is the latest meal of the day).
        _food(cls.user, "Salad", date(2026, 4, 7), "lunch", 200, t=time(12, 30))
        _food(cls.user, "Pizza", date(2026, 4, 7), "dinner", 300)   # no time
        _food(cls.user, "Breakfast Bar", date(2026, 4, 6), "breakfast", 150)

    def test_catalog_advertises_meal(self):
        self.assertIn("meal", truth_catalog()["nutrition"]["entities"])

    def test_last_meal_is_most_recent_day_dinner_first(self):
        # 'what was my last meal' → unscoped meal describe, newest meal first.
        r = get_domain_entity(self.user, "nutrition", entity_type="meal")
        self.assertEqual(r["status"], "ready")
        first = r["entities"][0]
        self.assertEqual(first["identity"], "Dinner — 2026-04-07")
        self.assertEqual([i["food_name"] for i in first["definition"]["items"]],
                         ["Pizza"])

    def test_meal_filter_returns_that_meal(self):
        r = get_domain_entity(self.user, "nutrition", entity_type="meal",
                              filters={"meal": "lunch"})
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["entities"][0]["identity"], "Lunch — 2026-04-07")

    def test_date_scoped_returns_all_that_days_meals(self):
        r = get_domain_entity(self.user, "nutrition", entity_type="meal",
                              filters={"on_date": "2026-04-07"})
        ids = {e["identity"] for e in r["entities"]}
        self.assertEqual(ids, {"Lunch — 2026-04-07", "Dinner — 2026-04-07"})

    def test_empty_day_is_honest_not_fabricated(self):
        r = get_domain_entity(self.user, "nutrition", entity_type="meal",
                              filters={"on_date": "2026-04-01"})
        self.assertEqual(r["status"], "empty")

    def test_meal_totals_reuse_canonical_producer(self):
        # The meal entity's performance totals MUST equal get_meal_totals — proving we
        # expose the existing aggregation, not a re-derived one.
        meals = NutritionQueries.describe_meals(self.user, on_date=date(2026, 4, 7))
        dinner = next(m for m in meals if m.definition["meal_type"] == "dinner")
        canonical = NutritionQueries.get_meal_totals(self.user, date(2026, 4, 7))["dinner"]
        self.assertEqual(dinner.performance["calories"], float(canonical["calories"]))
        self.assertEqual(dinner.performance["protein_g"], float(canonical["protein_g"]))

    def test_describe_one_by_meal_name(self):
        truth = get_domain_truth(self.user, "nutrition")
        self.assertEqual(truth.describe_one("dinner").identity, "Dinner — 2026-04-07")
        self.assertEqual(truth.describe_one("last meal").identity, "Dinner — 2026-04-07")

    def test_food_entity_still_works(self):
        r = get_domain_entity(self.user, "nutrition", entity_type="food")
        self.assertEqual(r["status"], "ready")
        self.assertTrue(r["entities"])
