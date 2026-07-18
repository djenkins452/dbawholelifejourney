# ==============================================================================
# File: apps/health/tests/test_nutrition_summary.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: The canonical nutrition day-summary composer + health.nutrition
#   Current Context page-summary provider (Foundation 1 — Canonical Truth).
#   Verifies: one deterministic source (build_nutrition_summary → NutritionQueries)
#   feeds both the page and the assistant; soft-deleted entries are excluded from
#   totals (the NutritionStatsView bug class); the provider emits deterministic facts
#   (no verdicts) and never raises on a plain date.
# ==============================================================================
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.current_context import _PAGE_SUMMARY_PROVIDERS
from apps.health.models import FoodEntry, NutritionGoals
from apps.health.services.nutrition_summary import (
    build_nutrition_progress, build_nutrition_summary,
)

User = get_user_model()


def _food(user, when, cals, protein, carbs, fat, meal=None):
    return FoodEntry.objects.create(
        user=user, logged_date=when,
        meal_type=meal or FoodEntry.MEAL_BREAKFAST, food_name="Test Food",
        quantity=Decimal("1"), serving_size=Decimal("1"), serving_unit="serving",
        status="active",
        total_calories=Decimal(str(cals)), total_protein_g=Decimal(str(protein)),
        total_carbohydrates_g=Decimal(str(carbs)), total_fat_g=Decimal(str(fat)))


class BuildNutritionSummaryTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="nsum@test.com", password="x")
        self.today = date.today()

    def test_empty_day_reports_no_entries_and_zero_totals(self):
        s = build_nutrition_summary(self.user, target_date=self.today)
        self.assertFalse(s["has_entries"])
        self.assertEqual(s["entry_count"], 0)
        self.assertEqual(s["totals"]["calories"], Decimal("0"))
        self.assertIsNone(s["goals"])
        self.assertIsNone(s["targets"])
        self.assertEqual(s["progress"], {})

    def test_totals_sum_active_entries(self):
        _food(self.user, self.today, 500, 40, 50, 20)
        _food(self.user, self.today, 300, 10, 30, 10, meal=FoodEntry.MEAL_LUNCH)
        s = build_nutrition_summary(self.user, target_date=self.today)
        self.assertTrue(s["has_entries"])
        self.assertEqual(s["entry_count"], 2)
        self.assertEqual(s["totals"]["calories"], Decimal("800"))
        self.assertEqual(s["totals"]["protein_g"], Decimal("50"))

    def test_soft_deleted_entries_are_excluded(self):
        # The bug class this consolidation fixes: a stat path counting deleted entries.
        _food(self.user, self.today, 500, 40, 50, 20)
        deleted = _food(self.user, self.today, 999, 99, 99, 99)
        deleted.soft_delete()
        s = build_nutrition_summary(self.user, target_date=self.today)
        self.assertEqual(s["entry_count"], 1)
        self.assertEqual(s["totals"]["calories"], Decimal("500"))

    def test_progress_is_a_deterministic_percentage_against_targets(self):
        _food(self.user, self.today, 1000, 50, 100, 30)
        NutritionGoals.objects.create(
            user=self.user, daily_calorie_target=2000,
            daily_protein_target_g=100, daily_carb_target_g=200,
            daily_fat_target_g=60, effective_until=None)
        s = build_nutrition_summary(self.user, target_date=self.today)
        self.assertEqual(s["targets"]["calories"], 2000)
        self.assertEqual(s["progress"]["calories"], 50)   # 1000/2000
        self.assertEqual(s["progress"]["protein_g"], 50)  # 50/100


class BuildNutritionProgressTests(TestCase):
    """The dashboard-tile builder — the canonical replacement for the retired
    UserPreferences.get_nutrition_progress (single NutritionGoals target store)."""

    def setUp(self):
        self.user = User.objects.create_user(email="nprog@test.com", password="x")
        self.today = date.today()

    def test_returns_none_without_a_calorie_target(self):
        _food(self.user, self.today, 500, 40, 50, 20)
        self.assertIsNone(build_nutrition_progress(self.user, target_date=self.today))

    def test_tile_shape_from_nutrition_goals(self):
        _food(self.user, self.today, 1000, 60, 100, 30)
        NutritionGoals.objects.create(
            user=self.user, daily_calorie_target=2000,
            daily_protein_target_g=120, daily_carb_target_g=200,
            daily_fat_target_g=60, effective_until=None)
        p = build_nutrition_progress(self.user, target_date=self.today)
        self.assertEqual(p["calories"]["current"], 1000)
        self.assertEqual(p["calories"]["goal"], 2000)
        self.assertEqual(p["calories"]["remaining"], 1000)
        self.assertEqual(p["calories"]["progress_percent"], 50)
        self.assertEqual(p["protein"]["current_g"], 60.0)
        self.assertEqual(p["protein"]["goal_g"], 120)
        self.assertEqual(p["protein"]["progress_percent"], 50)


class NutritionPageSummaryProviderTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="nprov@test.com", password="x")
        self.provider = _PAGE_SUMMARY_PROVIDERS.get("health.nutrition")

    def test_provider_is_registered(self):
        self.assertIsNotNone(self.provider)

    def test_empty_day_content_is_deterministic_and_does_not_raise(self):
        # Regression: provider must format a plain date without timezone.localtime().
        out = self.provider(self.user, {})
        self.assertEqual(out["title"], "Nutrition")
        self.assertIn("no food logged", out["content"])

    def test_populated_content_states_facts_not_verdicts(self):
        _food(self.user, date.today(), 600, 45, 40, 20)
        out = self.provider(self.user, {"date": str(date.today())})
        self.assertIn("Nutrition overview", out["content"])
        self.assertIn("600", out["content"])
        # Facts only — no verdict language.
        lowered = out["content"].lower()
        for verdict in ("on track", "good job", "too much", "you should"):
            self.assertNotIn(verdict, lowered)
