# ==============================================================================
# File: apps/ai/tests/test_health_certification_capabilities.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Health Knowledge Certification — the reusable platform capabilities
#   (comparison, adherence) + the nutrition macronutrient-adherence regression that
#   motivated the milestone ("do I need more carbs or are they in line?").
# ==============================================================================
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.ai.cos_services.domain_adherence import (
    adherence_capability_index,
    get_domain_adherence,
)
from apps.ai.cos_services.domain_comparison import get_domain_comparison
from apps.ai.cos_services.domain_history import get_domain_history

User = get_user_model()


def _today(user):
    from apps.core.utils import get_user_today
    return get_user_today(user)


class NutritionAdherenceRegressionTests(TestCase):
    """The reported failure: 'do I need more carbs or are they in line?' — carbs vs the
    carb target over a window, the half the CoS could not answer."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="adh@test.com", password="x")
        from apps.health.models import FoodEntry, NutritionGoals
        today = _today(cls.user)
        NutritionGoals.objects.create(
            user=cls.user, status="active",
            effective_from=today - timedelta(days=60),
            daily_calorie_target=2200, daily_protein_target_g=180,
            daily_carb_target_g=250, daily_fat_target_g=70,
            daily_fiber_target_g=30, daily_sugar_limit_g=50)
        # 7 days of carbs averaging well UNDER the 250 g target (~180 g).
        for i in range(7):
            FoodEntry.objects.create(
                user=cls.user, status="active", food_name="probe",
                serving_size=Decimal("1"), serving_unit="serving",
                quantity=Decimal("1"), meal_type="snack",
                logged_date=today - timedelta(days=i),
                total_calories=Decimal("1900"), total_protein_g=Decimal("150"),
                total_carbohydrates_g=Decimal("180"), total_fat_g=Decimal("60"),
                total_fiber_g=Decimal("20"), total_sugar_g=Decimal("40"))

    def test_carbs_have_a_registered_target(self):
        idx = adherence_capability_index()
        self.assertIn("carbs", idx.get("nutrition", ()))
        self.assertIn("protein", idx.get("nutrition", ()))

    def test_carb_adherence_answers_are_they_in_line(self):
        r = get_domain_adherence(self.user, "nutrition", "carbs", period="last_7_days")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["target"]["value"], 250.0)
        self.assertEqual(r["target"]["kind"], "target")   # reach, not limit
        self.assertEqual(r["actual"]["avg_daily"], 180.0)
        # signed variance: 70 g UNDER target — the deterministic evidence for "need more"
        self.assertEqual(r["variance"]["avg_daily_delta"], -70.0)
        self.assertEqual(r["variance"]["pct_of_target"], 72.0)
        self.assertEqual(r["days_under_target"], 7)

    def test_sugar_target_is_a_limit_not_a_reach(self):
        r = get_domain_adherence(self.user, "nutrition", "sugar", period="last_7_days")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["target"]["kind"], "limit")

    def test_macronutrient_intake_phrase_now_routes(self):
        # The exact miss: "macronutrient intake" was not a registered analysis subject.
        from apps.ai.cos_services.domain_analysis import get_domain_analysis
        for subj in ("macronutrients", "macronutrient_intake", "carbohydrates"):
            r = get_domain_analysis(self.user, "nutrition", subj)
            self.assertNotEqual(r["status"], "unsupported",
                                f"subject {subj!r} should route")

    def test_no_target_is_honest_not_zero(self):
        r = get_domain_adherence(self.user, "health", "sleep")
        self.assertEqual(r["status"], "no_target")
        self.assertIn("no target", r["reason"].lower())


class StepsAdherenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="stepadh@test.com", password="x")
        from apps.health.models import StepsEntry
        today = _today(cls.user)
        for i in range(7):
            StepsEntry.objects.create(
                user=cls.user, count=7000, goal=10000,
                logged_date=today - timedelta(days=i),
                recorded_at=timezone.now() - timedelta(days=i))

    def test_step_goal_adherence(self):
        r = get_domain_adherence(self.user, "health", "steps", period="last_7_days")
        self.assertEqual(r["status"], "ready")
        self.assertEqual(r["target"]["value"], 10000.0)
        self.assertEqual(r["actual"]["avg_daily"], 7000.0)
        self.assertEqual(r["variance"]["pct_of_target"], 70.0)


class ComparisonTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="cmp@test.com", password="x")
        from apps.health.models import WeightEntry
        now = timezone.now()
        # this week ~ 250, last week ~ 256 (falling)
        for i in range(7):
            WeightEntry.objects.create(user=cls.user, value=Decimal("250"), unit="lb",
                                       recorded_at=now - timedelta(days=i))
        for i in range(7, 14):
            WeightEntry.objects.create(user=cls.user, value=Decimal("256"), unit="lb",
                                       recorded_at=now - timedelta(days=i))

    def test_week_over_week_comparison(self):
        r = get_domain_comparison(self.user, "health", "weight",
                                  period_a="last_week", period_b="this_week")
        self.assertEqual(r["status"], "ready")
        self.assertTrue(r["period_a"]["present"])
        self.assertTrue(r["period_b"]["present"])
        # this_week avg (~250) is lower than last_week (~256) → falling
        self.assertEqual(r["change"]["average"]["direction"], "falling")
        self.assertLess(r["change"]["average"]["delta"], 0)

    def test_comparison_empty_when_no_data_either_period(self):
        u2 = User.objects.create_user(email="cmp2@test.com", password="x")
        r = get_domain_comparison(u2, "health", "weight",
                                  period_a="last_week", period_b="this_week")
        self.assertEqual(r["status"], "empty")

    def test_comparison_unsupported_metric(self):
        r = get_domain_comparison(self.user, "health", "bogus",
                                  period_a="last_week", period_b="this_week")
        self.assertEqual(r["status"], "unsupported")


class HistoryTrendWiringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="trendwire@test.com", password="x")
        from apps.health.models import WeightEntry
        now = timezone.now()
        for i in range(14):
            WeightEntry.objects.create(
                user=cls.user, value=Decimal(str(300 - i * 0.5)), unit="lb",
                recorded_at=now - timedelta(days=13 - i))

    def test_get_history_now_carries_change(self):
        r = get_domain_history(self.user, "health", "weight", period="last_7_days")
        self.assertEqual(r["status"], "ready")
        self.assertIn("change", r)
        self.assertIsNotNone(r["change"])
        self.assertIn(r["change"]["direction"], ("rising", "falling", "flat"))


class CapabilityAdvertisementTests(TestCase):
    def test_new_tools_registered(self):
        from apps.ai.model_interface.constitution import truth_tools
        names = {t["function"]["name"] for t in truth_tools()}
        self.assertIn("get_comparison", names)
        self.assertIn("get_adherence", names)

    def test_capability_index_advertises_new_surfaces(self):
        from apps.ai.cos_services.current_context import _capabilities
        caps = _capabilities()
        self.assertIn("truth_comparison", caps)
        self.assertIn("truth_adherence", caps)
        self.assertIn("carbs", caps["truth_adherence"].get("nutrition", []))
        self.assertIn("truth_comparison", caps["surface_roles"])
        self.assertIn("truth_adherence", caps["surface_roles"])

    def test_blood_pressure_and_body_composition_now_analyzable(self):
        from apps.ai.cos_services.current_context import _capabilities
        health_subjects = _capabilities()["truth_analysis"].get("health", [])
        self.assertIn("blood_pressure", health_subjects)
        self.assertIn("body_composition", health_subjects)
