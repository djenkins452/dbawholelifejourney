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


class FoodFrequencyTests(TestCase):
    """Track 2 — deterministic 'what do I eat most', owned by NutritionQueries."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="freq@example.com", password="x")
        for i in range(3):
            _food(cls.user, "Coffee", date(2026, 4, 1 + i), "breakfast", 5)
        for i in range(2):
            _food(cls.user, "Banana", date(2026, 4, 1 + i), "snack", 100)
        _food(cls.user, "Steak", date(2026, 4, 1), "dinner", 600)

    def test_ranked_by_frequency_with_deterministic_order(self):
        r = get_domain_entity(self.user, "nutrition", entity_type="frequent_food")
        self.assertEqual(r["status"], "ready")
        order = [(e["identity"], e["performance"]["times_logged"])
                 for e in r["entities"]]
        self.assertEqual(order[0], ("Coffee", 3))
        self.assertEqual(order[1], ("Banana", 2))
        self.assertEqual(order[2], ("Steak", 1))

    def test_tie_break_is_total_calories_then_name(self):
        # Two foods each logged once → higher-calorie first, then name.
        u2 = User.objects.create_user(email="freq2@example.com", password="x")
        _food(u2, "Zucchini", date(2026, 4, 1), "dinner", 50)
        _food(u2, "Apple", date(2026, 4, 1), "snack", 95)
        meals = NutritionQueries.top_foods(u2)
        self.assertEqual([m.identity for m in meals], ["Apple", "Zucchini"])

    def test_window_is_recorded_and_scopable(self):
        meals = NutritionQueries.top_foods(self.user, period="last_month")
        for m in meals:
            self.assertTrue(m.definition["window"])
            self.assertIn("times_logged", m.performance)


class NutritionAnalysisParticipationTests(TestCase):
    """Track 1 — nutrition participates in the Analysis surface by PURE composition."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="analysis@example.com", password="x")
        for i in range(5):
            _food(cls.user, f"Meal{i}", date(2026, 4, 1 + i), "dinner", 700)

    def test_nutrition_is_analysis_capable(self):
        from apps.ai.cos_services.domain_analysis import analysis_capable_domains
        self.assertIn("nutrition", analysis_capable_domains())

    def test_calories_analysis_holds_data_and_composes_evidence(self):
        from apps.ai.cos_services.domain_analysis import get_domain_analysis
        a = get_domain_analysis(self.user, "nutrition", "calories")
        self.assertEqual(a["status"], "ready")
        self.assertTrue(a["holds_data"])
        # composed from EXISTING surfaces: history windows + all_time + meal records
        self.assertIn("history", a)
        self.assertIn("all_time", a)
        self.assertTrue((a.get("records") or {}).get("present"))

    def test_every_declared_subject_has_real_history_and_entity_inputs(self):
        # The discipline: a subject may be declared ONLY if its inputs already exist.
        from apps.core.truth.domain import get_domain_truth
        truth = get_domain_truth(self.user, "nutrition")
        hist = set(truth.history_metrics)
        ents = set(truth.entity_types)
        for subj, m in truth.analysis_subjects.items():
            self.assertIn(m["history_metric"], hist, f"{subj}: history missing")
            if m.get("entity_type"):
                self.assertIn(m["entity_type"], ents, f"{subj}: entity missing")
