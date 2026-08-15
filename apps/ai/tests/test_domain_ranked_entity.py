# ==============================================================================
# File: apps/ai/tests/test_domain_ranked_entity.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Model Interface — the RANKED-ENTITY branch. Verifies get_ranked_entity ranks
#   canonical MEAL entities by their ALREADY-authoritative carb value (no recompute, no
#   arbitrary field), returns canonical references, handles missing/empty/limit honestly,
#   and is registry-controlled. Closes nutrition.meals_most_carbs (Phase 3+).
# ==============================================================================
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ai.cos_services.domain_ranked_entity import (
    RANKING_SUBJECTS,
    get_domain_ranked_entity,
    ranked_entity_capability_index,
)

User = get_user_model()


class DomainRankedEntityServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="rank@test.com", password="x")

    def _food(self, days_ago, meal_type, carbs, *, name="Food", calories=200):
        from apps.core.utils import get_user_today
        from apps.health.models import FoodEntry
        d = get_user_today(self.user) - timedelta(days=days_ago)
        return FoodEntry.objects.create(
            user=self.user, food_name=name, meal_type=meal_type, logged_date=d,
            quantity=Decimal("1"), serving_size=Decimal("1"), serving_unit="serving",
            total_calories=Decimal(str(calories)),
            total_carbohydrates_g=Decimal(str(carbs)), status="active")

    # --- registry / capability wiring ---
    def test_meal_by_carbs_is_registered(self):
        self.assertIn("meal_by_carbs", RANKING_SUBJECTS)
        self.assertIn("meal_by_carbs",
                      ranked_entity_capability_index().get("nutrition", ()))

    # --- the core deterministic ranking ---
    def test_ranks_meal_occurrences_by_carbs_desc(self):
        # Two days; each meal's carbs = sum of its foods (the canonical value).
        self._food(2, "dinner", 70, name="Pasta")       # dinner d-2 = 70
        self._food(2, "lunch", 40, name="Sandwich")     # lunch  d-2 = 40
        self._food(1, "dinner", 30, name="Rice")
        self._food(1, "dinner", 25, name="Beans")       # dinner d-1 = 55
        self._food(1, "breakfast", 20, name="Oats")     # breakfast d-1 = 20
        r = get_domain_ranked_entity(self.user, "meal_by_carbs", period="last 7 days")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["measure"], "carbohydrates_g")
        self.assertEqual(r["unit"], "g")
        self.assertEqual(r["aggregation"], "occurrence")
        vals = [(x["name"], x["value"]) for x in r["results"]]
        # dinner d-2 (70) > dinner d-1 (55) > lunch d-2 (40) > breakfast d-1 (20)
        self.assertEqual([v for _, v in vals], [70.0, 55.0, 40.0, 20.0])
        # the top entity carries a canonical reference + the day.
        self.assertIn("Dinner", r["results"][0]["name"])
        self.assertTrue(r["results"][0]["ref"])
        self.assertEqual(r["granularity"], "ranked_entity")

    def test_value_is_the_canonical_total_not_recomputed(self):
        # The ranked value must EQUAL get_meal_totals (the authority), proving no shadow calc.
        from apps.core.utils import get_user_today
        from apps.health.services.nutrition_queries import NutritionQueries
        self._food(1, "dinner", 33)
        self._food(1, "dinner", 27)                    # dinner total carbs = 60
        r = get_domain_ranked_entity(self.user, "meal_by_carbs", period="last 7 days")
        d = get_user_today(self.user) - timedelta(days=1)
        authoritative = float(NutritionQueries.get_meal_totals(self.user, d)["dinner"]["carbs_g"])
        self.assertEqual(r["results"][0]["value"], round(authoritative, 2))
        self.assertEqual(r["results"][0]["value"], 60.0)

    def test_contribution_pct_and_total(self):
        self._food(1, "dinner", 75)
        self._food(1, "lunch", 25)
        r = get_domain_ranked_entity(self.user, "meal_by_carbs", period="last 7 days")
        self.assertEqual(r["total"], 100.0)
        self.assertEqual(r["results"][0]["contribution_pct"], 75.0)

    def test_ascending_and_limit(self):
        for i, c in enumerate([10, 20, 30, 40], start=1):
            self._food(i, "dinner", c)
        asc = get_domain_ranked_entity(self.user, "meal_by_carbs",
                                       period="last 7 days", order="asc", limit=2)
        self.assertEqual([x["value"] for x in asc["results"]], [10.0, 20.0])

    # --- honest statuses ---
    def test_no_meals_is_empty(self):
        r = get_domain_ranked_entity(self.user, "meal_by_carbs", period="last 7 days")
        self.assertEqual(r["status"], "empty")

    def test_unsupported_subject(self):
        r = get_domain_ranked_entity(self.user, "meal_by_unicorns", period="last 7 days")
        self.assertEqual(r["status"], "unsupported")
        self.assertIn("meal_by_carbs", r["supported_subjects"])

    def test_unresolvable_period(self):
        self._food(1, "dinner", 50)
        r = get_domain_ranked_entity(self.user, "meal_by_carbs", period="qwerty")
        self.assertEqual(r["status"], "unsupported")

    def test_deterministic(self):
        self._food(1, "dinner", 40)
        self._food(1, "lunch", 40)                     # tie → deterministic ref order
        a = get_domain_ranked_entity(self.user, "meal_by_carbs", period="last 7 days")
        b = get_domain_ranked_entity(self.user, "meal_by_carbs", period="last 7 days")
        self.assertEqual([x["ref"] for x in a["results"]],
                         [x["ref"] for x in b["results"]])
