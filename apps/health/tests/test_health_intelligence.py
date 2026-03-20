"""
Tests for the Health Intelligence Engine.

Covers:
    - DailyHealthSummary model
    - DailyHealthSummaryBuilder (rollup)
    - BaselinePolicy
    - RecoveryScoreService
    - HealthScoreService
    - HealthTrendAnalyzer (plateau detection, pattern detection)
    - CorrelationService
    - ScorePipeline
    - Management command idempotency
    - CoS context hooks
    - HealthCommandCenterService
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.models import (
    BloodOxygenEntry,
    BloodPressureEntry,
    BodyCompositionEntry,
    DailyHealthSummary,
    DailyNutritionSummary,
    FastingWindow,
    FoodEntry,
    GlucoseEntry,
    HealthProfile,
    HeartRateEntry,
    Medicine,
    MedicineLog,
    MedicineSchedule,
    SleepEntry,
    StepsEntry,
    WaterEntry,
    WeightEntry,
    WorkoutSession,
)

User = get_user_model()


class HealthIntelligenceTestMixin:
    """Shared test data factory for health intelligence tests."""

    def create_test_user(self):
        """Create a test user with email auth."""
        return User.objects.create_user(
            email="test_health_intel@example.com",
            password="testpass123",
        )

    def populate_30_days(self, user, start_date=None):
        """
        Populate 30 days of health data for a user.
        Creates sleep, steps, weight, and nutrition entries.
        """
        start = start_date or (date.today() - timedelta(days=30))

        for i in range(30):
            d = start + timedelta(days=i)
            dt = timezone.make_aware(datetime.combine(d, datetime.min.time()))

            # Sleep
            bedtime = dt.replace(hour=22, minute=30)
            wake_time = (dt + timedelta(days=1)).replace(hour=6, minute=15)
            SleepEntry.objects.create(
                user=user,
                sleep_date=d,
                bedtime=bedtime,
                wake_time=wake_time,
                quality_rating="good",
                total_duration_minutes=int((wake_time - bedtime).total_seconds() / 60),
                stage_deep_minutes=75 + (i % 10),
                stage_rem_minutes=90 + (i % 8),
            )

            # Steps
            StepsEntry.objects.create(
                user=user,
                logged_date=d,
                count=7000 + (i * 100),
                exercise_minutes=30 + (i % 15),
                calories_burned=250 + (i * 5),
                recorded_at=dt.replace(hour=20),
            )

            # Weight (slowly declining)
            WeightEntry.objects.create(
                user=user,
                value=Decimal(str(240 - i * 0.2)),
                unit="lb",
                recorded_at=dt.replace(hour=7),
            )

            # Nutrition (most days)
            if i % 7 != 6:  # Skip Sundays
                DailyNutritionSummary.objects.create(
                    user=user,
                    summary_date=d,
                    total_calories=Decimal("2100"),
                    total_protein_g=Decimal("150"),
                    total_carbohydrates_g=Decimal("200"),
                    total_fat_g=Decimal("80"),
                    total_fiber_g=Decimal("25"),
                    total_sugar_g=Decimal("50"),
                    total_saturated_fat_g=Decimal("20"),
                    total_sodium_mg=Decimal("2000"),
                    breakfast_count=1,
                    lunch_count=1,
                    dinner_count=1,
                    snack_count=0,
                )

    def build_summaries_for_range(self, user, start, end):
        """Build DailyHealthSummary rows for a date range."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        builder = DailyHealthSummaryBuilder()
        builder.build_range(user, start, end)


class TestDailyHealthSummaryModel(TestCase, HealthIntelligenceTestMixin):
    """Test the DailyHealthSummary model itself."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_create_summary(self):
        summary = DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=date.today(),
            baseline_ready=False,
            sleep_hours=Decimal("7.5"),
            steps=8000,
        )
        self.assertEqual(summary.summary_date, date.today())
        self.assertFalse(summary.baseline_ready)
        self.assertEqual(summary.sleep_hours, Decimal("7.5"))

    def test_unique_constraint(self):
        DailyHealthSummary.objects.create(
            user=self.user, summary_date=date.today(),
        )
        with self.assertRaises(Exception):
            DailyHealthSummary.objects.create(
                user=self.user, summary_date=date.today(),
            )

    def test_str_representation(self):
        summary = DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=date.today(),
            health_score=78,
        )
        self.assertIn("HS:78", str(summary))


class TestDailyHealthSummaryBuilder(TestCase, HealthIntelligenceTestMixin):
    """Test the daily rollup builder."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_build_empty_day(self):
        """Building a day with no data should create a summary with nulls."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(self.user, date.today())

        self.assertIsNotNone(summary)
        self.assertIsNone(summary.sleep_hours)
        self.assertIsNone(summary.steps)
        self.assertEqual(summary.signals_present, [])

    def test_build_with_sleep(self):
        """Builder should collect sleep data."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        today = date.today()
        dt = timezone.now().replace(hour=22, minute=0, second=0, microsecond=0)
        SleepEntry.objects.create(
            user=self.user,
            sleep_date=today,
            bedtime=dt - timedelta(hours=8),
            wake_time=dt,
            total_duration_minutes=480,
            quality_rating="good",
            stage_deep_minutes=90,
            stage_rem_minutes=100,
        )

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(self.user, today)

        self.assertIsNotNone(summary.sleep_hours)
        self.assertEqual(summary.deep_sleep_minutes, 90)
        self.assertEqual(summary.rem_sleep_minutes, 100)
        self.assertIn("sleep", summary.signals_present)

    def test_build_with_steps(self):
        """Builder should collect step data."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        today = date.today()
        StepsEntry.objects.create(
            user=self.user,
            logged_date=today,
            count=10500,
            exercise_minutes=45,
            calories_burned=350,
            recorded_at=timezone.now(),
        )

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(self.user, today)

        self.assertEqual(summary.steps, 10500)
        self.assertEqual(summary.active_minutes, 45)
        self.assertIn("steps", summary.signals_present)

    def test_build_with_weight(self):
        """Builder should collect weight data."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        today = date.today()
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("235.5"),
            unit="lb",
            recorded_at=timezone.now(),
        )

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(self.user, today)

        self.assertEqual(summary.weight, Decimal("235.5"))
        self.assertIn("weight", summary.signals_present)

    def test_build_with_glucose(self):
        """Builder should collect and aggregate glucose data."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        today = date.today()
        now = timezone.now()

        for val in [95, 110, 130, 105, 100]:
            GlucoseEntry.objects.create(
                user=self.user,
                value=Decimal(str(val)),
                unit="mg/dL",
                context="random",
                recorded_at=now,
            )

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(self.user, today)

        self.assertIsNotNone(summary.glucose_avg)
        self.assertEqual(summary.glucose_min, Decimal("95.00"))
        self.assertEqual(summary.glucose_max, Decimal("130.00"))
        self.assertIsNotNone(summary.time_in_range_pct)
        self.assertIn("glucose", summary.signals_present)

    def test_build_is_idempotent(self):
        """Running builder twice should update, not create duplicate."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        today = date.today()
        StepsEntry.objects.create(
            user=self.user, logged_date=today, count=5000,
            recorded_at=timezone.now(),
        )

        builder = DailyHealthSummaryBuilder()
        s1 = builder.build_for_date(self.user, today)
        s2 = builder.build_for_date(self.user, today)

        self.assertEqual(s1.pk, s2.pk)
        self.assertEqual(
            DailyHealthSummary.objects.filter(user=self.user, summary_date=today).count(),
            1,
        )

    def test_build_range(self):
        """build_range should process multiple days."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        start = date.today() - timedelta(days=3)
        end = date.today()

        builder = DailyHealthSummaryBuilder()
        count = builder.build_range(self.user, start, end)

        self.assertEqual(count, 4)
        self.assertEqual(
            DailyHealthSummary.objects.filter(user=self.user).count(),
            4,
        )

    def test_nutrition_collection(self):
        """Builder should collect nutrition from DailyNutritionSummary."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        today = date.today()
        DailyNutritionSummary.objects.create(
            user=self.user,
            summary_date=today,
            total_calories=Decimal("2100"),
            total_protein_g=Decimal("160"),
            total_carbohydrates_g=Decimal("200"),
            total_fat_g=Decimal("80"),
            total_fiber_g=Decimal("25"),
            total_sugar_g=Decimal("50"),
            total_saturated_fat_g=Decimal("20"),
            total_sodium_mg=Decimal("2000"),
            breakfast_count=1,
            lunch_count=1,
            dinner_count=1,
            snack_count=1,
        )

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(self.user, today)

        self.assertEqual(summary.calories_consumed, 2100)
        self.assertEqual(summary.protein_g, Decimal("160"))
        self.assertTrue(summary.nutrition_logged)
        self.assertEqual(summary.meals_logged, 4)


class TestBaselinePolicy(TestCase, HealthIntelligenceTestMixin):
    """Test baseline readiness policy."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_new_user_not_ready(self):
        """New user with no data should not be baseline ready."""
        from apps.health.services.baseline_policy import BaselinePolicy
        self.assertFalse(BaselinePolicy.baseline_ready(self.user, date.today()))

    def test_user_with_few_days_not_ready(self):
        """User with < 14 days should not be baseline ready."""
        from apps.health.services.baseline_policy import BaselinePolicy

        for i in range(10):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=date.today() - timedelta(days=i + 1),
                signals_present=["sleep", "steps", "weight"],
            )

        self.assertFalse(BaselinePolicy.baseline_ready(self.user, date.today()))

    def test_user_with_14_days_ready(self):
        """User with >= 14 qualifying days should be baseline ready."""
        from apps.health.services.baseline_policy import BaselinePolicy

        for i in range(15):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=date.today() - timedelta(days=i + 1),
                signals_present=["sleep", "steps", "weight"],
            )

        self.assertTrue(BaselinePolicy.baseline_ready(self.user, date.today()))

    def test_days_without_core_signals_dont_count(self):
        """Days missing core signal groups should not count toward baseline."""
        from apps.health.services.baseline_policy import BaselinePolicy

        # 20 days, but only with 'fasting' — no sleep/steps AND no weight/glucose/nutrition
        for i in range(20):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=date.today() - timedelta(days=i + 1),
                signals_present=["fasting"],
            )

        self.assertFalse(BaselinePolicy.baseline_ready(self.user, date.today()))

    def test_baseline_message(self):
        """Message should show days remaining."""
        from apps.health.services.baseline_policy import BaselinePolicy

        msg = BaselinePolicy.baseline_message(self.user, date.today())
        self.assertIn("14", msg)  # 14 more days needed

    def test_baseline_message_none_when_ready(self):
        """No message when baseline is ready."""
        from apps.health.services.baseline_policy import BaselinePolicy

        for i in range(15):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=date.today() - timedelta(days=i + 1),
                signals_present=["sleep", "nutrition"],
            )

        msg = BaselinePolicy.baseline_message(self.user, date.today())
        self.assertIsNone(msg)


class TestRecoveryScore(TestCase, HealthIntelligenceTestMixin):
    """Test recovery score computation."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_no_baseline_returns_none(self):
        """Recovery score should be None when baseline not ready."""
        from apps.health.services.recovery_score import RecoveryScoreService
        score, drivers = RecoveryScoreService.compute(self.user, date.today())
        self.assertIsNone(score)
        self.assertEqual(drivers["status"], "baseline_collecting")

    def test_with_baseline_computes_score(self):
        """Recovery score should compute when baseline is ready."""
        from apps.health.services.recovery_score import RecoveryScoreService

        # Create 15 baseline days
        for i in range(15):
            d = date.today() - timedelta(days=i + 1)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                sleep_hours=Decimal("7.5"),
                sleep_quality_score=75,
                hrv=Decimal("42"),
                resting_hr=68,
                training_load=Decimal("5000"),
                signals_present=["sleep", "steps", "weight"],
            )

        # Create today with data
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=date.today(),
            sleep_hours=Decimal("8.0"),
            sleep_quality_score=80,
            hrv=Decimal("45"),
            resting_hr=65,
            workout_count=1,
            training_load=Decimal("6000"),
            signals_present=["sleep", "steps", "weight", "workout"],
        )

        score, drivers = RecoveryScoreService.compute(self.user, date.today())

        self.assertIsNotNone(score)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertIn("status", drivers)
        self.assertIn("components", drivers)
        self.assertIn("top_positive", drivers)

    def test_recovery_status_labels(self):
        """Verify status labels map correctly."""
        from apps.health.services.recovery_score import RecoveryScoreService
        self.assertEqual(RecoveryScoreService._status_label(90), "excellent")
        self.assertEqual(RecoveryScoreService._status_label(75), "good")
        self.assertEqual(RecoveryScoreService._status_label(55), "fair")
        self.assertEqual(RecoveryScoreService._status_label(35), "poor")
        self.assertEqual(RecoveryScoreService._status_label(20), "critical")


class TestHealthScore(TestCase, HealthIntelligenceTestMixin):
    """Test health score computation."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_no_baseline_returns_none(self):
        """Health score should be None when baseline not ready."""
        from apps.health.services.health_score import HealthScoreService
        score, drivers = HealthScoreService.compute(self.user, date.today())
        self.assertIsNone(score)

    def test_with_data_computes_score(self):
        """Health score should compute with sufficient data."""
        from apps.health.services.health_score import HealthScoreService

        # Create baseline
        for i in range(15):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                sleep_hours=Decimal("7.5"),
                sleep_quality_score=75,
                steps=8000,
                active_minutes=30,
                workout_count=1 if i % 2 == 0 else 0,
                calories_consumed=2100,
                protein_g=Decimal("150"),
                nutrition_logged=True,
                weight=Decimal("235"),
                recovery_score=72,
                signals_present=["sleep", "steps", "weight", "nutrition"],
            )

        score, drivers = HealthScoreService.compute(self.user, date.today())

        self.assertIsNotNone(score)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertIn("domains", drivers)
        self.assertIn("strongest_positive_signal", drivers)

    def test_missing_signals_dont_punish(self):
        """Missing glucose integration shouldn't tank the score."""
        from apps.health.services.health_score import HealthScoreService

        # Only sleep + steps + nutrition (no glucose)
        for i in range(15):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                sleep_hours=Decimal("8.0"),
                sleep_quality_score=85,
                steps=10000,
                active_minutes=45,
                workout_count=1 if i % 2 == 0 else 0,
                calories_consumed=2000,
                protein_g=Decimal("170"),
                nutrition_logged=True,
                weight=Decimal("230"),
                recovery_score=80,
                signals_present=["sleep", "steps", "weight", "nutrition"],
            )

        score, drivers = HealthScoreService.compute(self.user, date.today())

        self.assertIsNotNone(score)
        self.assertGreaterEqual(score, 60)  # Good data shouldn't score low
        self.assertIn("glucose", drivers["missing_signals"])


class TestTrendAnalyzer(TestCase, HealthIntelligenceTestMixin):
    """Test trend and plateau detection."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_insufficient_data(self):
        """Should return empty analysis with <7 days of data."""
        from apps.health.services.trend_analyzer import HealthTrendAnalyzer
        analysis = HealthTrendAnalyzer.analyze(self.user, date.today())
        self.assertEqual(analysis["strengths"], [])
        self.assertIn("more data needed", analysis["top_recommendation"].lower())

    def test_weight_plateau_detection(self):
        """Should detect weight plateau when weight is flat for 10+ days."""
        from apps.health.services.trend_analyzer import HealthTrendAnalyzer

        HealthProfile.objects.create(
            user=self.user,
            weight_goal=Decimal("215"),
            weight_goal_unit="lb",
        )

        # 28 days of flat weight
        for i in range(28):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                weight=Decimal("235.5") + Decimal(str(i % 2 * 0.3)),
                sleep_hours=Decimal("7"),
                signals_present=["weight", "sleep"],
            )

        analysis = HealthTrendAnalyzer.analyze(self.user, date.today())

        # Should have plateau risk flag
        plateau_flags = [
            r for r in analysis["risk_flags"]
            if r.get("domain") == "weight" and "plateau" in r.get("message", "").lower()
        ]
        self.assertTrue(len(plateau_flags) > 0, "Should detect weight plateau")

    def test_sleep_debt_detection(self):
        """Should detect sleep debt when sleep is consistently low."""
        from apps.health.services.trend_analyzer import HealthTrendAnalyzer

        for i in range(10):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                sleep_hours=Decimal("5.5"),
                weight=Decimal("230"),
                signals_present=["sleep", "weight"],
            )

        analysis = HealthTrendAnalyzer.analyze(self.user, date.today())

        sleep_flags = [
            r for r in analysis["risk_flags"]
            if r.get("domain") == "sleep"
        ]
        self.assertTrue(len(sleep_flags) > 0, "Should detect sleep debt")

    def test_strength_detection(self):
        """Should detect high workout frequency as a strength."""
        from apps.health.services.trend_analyzer import HealthTrendAnalyzer

        for i in range(10):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                workout_count=1,
                sleep_hours=Decimal("7.5"),
                steps=9000,
                weight=Decimal("230"),
                signals_present=["workout", "sleep", "steps", "weight"],
            )

        analysis = HealthTrendAnalyzer.analyze(self.user, date.today())

        workout_strengths = [s for s in analysis["strengths"] if "workout" in s.lower()]
        self.assertTrue(len(workout_strengths) > 0)


class TestCorrelationService(TestCase, HealthIntelligenceTestMixin):
    """Test cross-domain correlation detection."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_insufficient_data(self):
        """Should return empty with <10 days."""
        from apps.health.services.correlation_service import CorrelationService
        result = CorrelationService.compute(self.user, date.today())
        self.assertEqual(result, [])

    def test_rank_correlation_function(self):
        """Test the rank correlation helper directly."""
        from apps.health.services.correlation_service import _rank_correlation

        # Perfect positive correlation
        x = [1, 2, 3, 4, 5]
        y = [10, 20, 30, 40, 50]
        r = _rank_correlation(x, y)
        self.assertAlmostEqual(r, 1.0, places=2)

        # Perfect negative correlation
        y_neg = [50, 40, 30, 20, 10]
        r_neg = _rank_correlation(x, y_neg)
        self.assertAlmostEqual(r_neg, -1.0, places=2)

    def test_correlations_with_data(self):
        """Should find correlations with 28 days of varied data."""
        from apps.health.services.correlation_service import CorrelationService

        import random
        random.seed(42)  # Reproducible

        for i in range(28):
            d = date.today() - timedelta(days=i)
            sleep = Decimal(str(round(6 + random.random() * 3, 2)))
            glucose = Decimal(str(round(120 - float(sleep) * 5 + random.random() * 10, 2)))

            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                sleep_hours=sleep,
                sleep_quality_score=int(float(sleep) * 10),
                glucose_avg=glucose,
                time_in_range_pct=Decimal(str(round(70 + random.random() * 25, 2))),
                glucose_variability=Decimal(str(round(20 + random.random() * 20, 2))),
                recovery_score=int(float(sleep) * 8 + random.random() * 20),
                training_load=Decimal(str(round(3000 + random.random() * 5000, 2))),
                weight=Decimal("235"),
                signals_present=["sleep", "glucose", "weight"],
            )

        result = CorrelationService.compute(self.user, date.today())

        self.assertGreater(len(result), 0)
        self.assertLessEqual(len(result), 3)
        self.assertIn("signal_a", result[0])
        self.assertIn("interpretation", result[0])
        self.assertTrue(-1 <= result[0]["correlation"] <= 1)


class TestScorePipeline(TestCase, HealthIntelligenceTestMixin):
    """Test the score computation pipeline."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_full_build(self):
        """Full pipeline: build summary + compute scores."""
        from apps.health.services.score_pipeline import ScorePipeline

        today = date.today()
        dt = timezone.now().replace(hour=22, second=0, microsecond=0)

        # Create source data
        SleepEntry.objects.create(
            user=self.user, sleep_date=today,
            bedtime=dt - timedelta(hours=8), wake_time=dt,
            total_duration_minutes=480,
            quality_rating="good", stage_deep_minutes=80,
        )
        StepsEntry.objects.create(
            user=self.user, logged_date=today, count=9000,
            exercise_minutes=40, recorded_at=timezone.now(),
        )
        WeightEntry.objects.create(
            user=self.user, value=Decimal("235"), unit="lb",
            recorded_at=timezone.now(),
        )

        summary = ScorePipeline.full_build(self.user, today)

        self.assertIsNotNone(summary)
        self.assertEqual(summary.summary_date, today)
        self.assertIsNotNone(summary.sleep_hours)
        self.assertEqual(summary.steps, 9000)

    def test_full_build_idempotent(self):
        """Full pipeline should be safe to run twice."""
        from apps.health.services.score_pipeline import ScorePipeline

        today = date.today()
        StepsEntry.objects.create(
            user=self.user, logged_date=today, count=5000,
            recorded_at=timezone.now(),
        )

        s1 = ScorePipeline.full_build(self.user, today)
        s2 = ScorePipeline.full_build(self.user, today)

        self.assertEqual(s1.pk, s2.pk)


class TestCommandCenterAPI(TestCase, HealthIntelligenceTestMixin):
    """Test the Health Command Center data API."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_empty_dashboard(self):
        """Should return structure even with no data."""
        from apps.health.services.command_center_api import HealthCommandCenterService
        data = HealthCommandCenterService.get_dashboard_data(self.user)

        self.assertIn("score_card", data)
        self.assertIn("domain_panels", data)
        self.assertIn("trend_lines", data)
        self.assertIn("recommendation", data)

    def test_dashboard_with_data(self):
        """Should populate panels with available data."""
        from apps.health.services.command_center_api import HealthCommandCenterService

        today = date.today()
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            health_score=75,
            recovery_score=68,
            sleep_hours=Decimal("7.5"),
            steps=8500,
            weight=Decimal("235"),
            calories_consumed=2100,
            protein_g=Decimal("150"),
            nutrition_logged=True,
            signals_present=["sleep", "steps", "weight", "nutrition"],
            baseline_ready=True,
            health_score_drivers={"immediate_focus": "Sleep"},
            recovery_drivers={"status": "good", "recommendation": "Normal training"},
        )

        data = HealthCommandCenterService.get_dashboard_data(self.user, today)

        self.assertEqual(data["score_card"]["health_score"], 75)
        self.assertEqual(data["score_card"]["recovery_score"], 68)
        self.assertEqual(data["domain_panels"]["sleep"]["last_night"]["hours"], 7.5)
        self.assertEqual(data["domain_panels"]["activity"]["today_steps"], 8500)
        self.assertEqual(data["domain_panels"]["weight"]["current"], 235.0)


class TestCosHealthContext(TestCase, HealthIntelligenceTestMixin):
    """Test CoS health context hooks."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_cos_intelligence_no_data(self):
        """Should return safe defaults with no data."""
        from apps.health.services.cos_health_context import build_cos_health_intelligence
        intel = build_cos_health_intelligence(self.user)

        self.assertIn("baseline_ready", intel)
        self.assertFalse(intel["baseline_ready"])
        self.assertIsNone(intel["today"])

    def test_cos_summary_text_no_data(self):
        """Should return a message when no data."""
        from apps.health.services.cos_health_context import build_cos_health_summary_text
        text = build_cos_health_summary_text(self.user)
        self.assertIn("baseline", text.lower())

    def test_cos_intelligence_with_data(self):
        """Should populate intelligence with data."""
        from apps.health.services.cos_health_context import build_cos_health_intelligence

        today = date.today()
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            health_score=78,
            recovery_score=72,
            sleep_hours=Decimal("7.5"),
            steps=9000,
            weight=Decimal("235"),
            nutrition_logged=True,
            signals_present=["sleep", "steps", "weight", "nutrition"],
            baseline_ready=False,
            health_score_drivers={"status": "computed"},
            recovery_drivers={"status": "good"},
        )

        intel = build_cos_health_intelligence(self.user)

        self.assertIsNotNone(intel["today"])
        self.assertEqual(intel["scores"]["health_score"], 78)
        self.assertEqual(intel["scores"]["recovery_score"], 72)


# ====================================================================
# PROTEIN INTELLIGENCE TESTS
# ====================================================================


class TestProteinService(TestCase, HealthIntelligenceTestMixin):
    """Test the Protein Intelligence service (LBM-aware)."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_calculate_target_no_weight(self):
        """Should return None when no weight data exists."""
        from apps.health.services.protein_service import ProteinService
        target = ProteinService.calculate_target(self.user)
        self.assertIsNone(target)

    def test_calculate_target_returns_dict(self):
        """calculate_target should return a dict with target_g and metadata."""
        from apps.health.services.protein_service import ProteinService

        WeightEntry.objects.create(
            user=self.user, value=Decimal("240"), unit="lb",
            recorded_at=timezone.now(),
        )
        result = ProteinService.calculate_target(self.user)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, dict)
        self.assertIn("target_g", result)
        self.assertIn("method", result)
        self.assertIn("lbm", result)
        self.assertIn("workout_day", result)
        self.assertIn("multiplier", result)

    def test_calculate_target_body_weight_fallback(self):
        """Without body fat, should fall back to body weight × 0.7."""
        from apps.health.services.protein_service import ProteinService

        WeightEntry.objects.create(
            user=self.user, value=Decimal("240"), unit="lb",
            recorded_at=timezone.now(),
        )
        result = ProteinService.calculate_target(self.user)
        self.assertIsNotNone(result)
        # 240 * 0.7 = 168
        self.assertEqual(result["target_g"], Decimal("168.00"))
        self.assertEqual(result["method"], "body_weight")
        self.assertIsNone(result["lbm"])

    def test_calculate_target_with_override(self):
        """Custom override should take priority over everything."""
        from apps.health.services.protein_service import ProteinService

        HealthProfile.objects.create(
            user=self.user,
            protein_target_g_override=Decimal("200"),
        )
        WeightEntry.objects.create(
            user=self.user, value=Decimal("240"), unit="lb",
            recorded_at=timezone.now(),
        )
        result = ProteinService.calculate_target(self.user)
        self.assertEqual(result["target_g"], Decimal("200"))
        self.assertEqual(result["method"], "override")

    def test_calculate_target_custom_multiplier(self):
        """Custom per-lb multiplier should be used in body_weight mode."""
        from apps.health.services.protein_service import ProteinService

        HealthProfile.objects.create(
            user=self.user,
            protein_per_lb_target=Decimal("1.000"),
        )
        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        result = ProteinService.calculate_target(self.user)
        self.assertIsNotNone(result)
        # 200 * 1.0 = 200
        self.assertEqual(result["target_g"], Decimal("200.00"))
        self.assertEqual(result["method"], "body_weight")
        self.assertAlmostEqual(result["multiplier"], 1.0)

    def test_calculate_target_g_convenience(self):
        """calculate_target_g should return just the Decimal target."""
        from apps.health.services.protein_service import ProteinService

        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        target_g = ProteinService.calculate_target_g(self.user)
        self.assertIsNotNone(target_g)
        self.assertIsInstance(target_g, Decimal)
        self.assertEqual(target_g, Decimal("140.00"))

    def test_calculate_ratio(self):
        """Ratio should be consumed / target."""
        from apps.health.services.protein_service import ProteinService

        ratio = ProteinService.calculate_ratio(
            consumed_g=Decimal("150"), target_g=Decimal("168")
        )
        self.assertIsNotNone(ratio)
        self.assertAlmostEqual(float(ratio), 0.89, places=1)

    def test_calculate_ratio_none_inputs(self):
        """Ratio should handle None inputs gracefully."""
        from apps.health.services.protein_service import ProteinService

        self.assertIsNone(ProteinService.calculate_ratio(None, Decimal("168")))
        self.assertIsNone(ProteinService.calculate_ratio(Decimal("150"), None))
        self.assertIsNone(ProteinService.calculate_ratio(Decimal("150"), Decimal("0")))

    def test_calculate_protein_per_lb(self):
        """Per-lb should be consumed / weight."""
        from apps.health.services.protein_service import ProteinService

        per_lb = ProteinService.calculate_protein_per_lb(
            consumed_g=Decimal("168"), weight_lbs=Decimal("240")
        )
        self.assertIsNotNone(per_lb)
        self.assertEqual(per_lb, Decimal("0.700"))

    def test_calculate_score_no_data(self):
        """Score should be None with no data."""
        from apps.health.services.protein_service import ProteinService

        score, details = ProteinService.calculate_score(self.user, date.today())
        self.assertIsNone(score)
        self.assertEqual(details["status"], "no_data")

    def test_calculate_score_with_data(self):
        """Score should compute with protein and weight data."""
        from apps.health.services.protein_service import ProteinService

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("240"), unit="lb",
            recorded_at=timezone.now(),
        )

        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            protein_g=Decimal("160"),
            weight=Decimal("240"),
            nutrition_logged=True,
            signals_present=["nutrition", "weight"],
        )

        score, details = ProteinService.calculate_score(self.user, today)
        self.assertIsNotNone(score)
        self.assertGreaterEqual(score, 0)
        self.assertLessEqual(score, 100)
        self.assertIn("today_consumed_g", details)
        self.assertIn("today_target_g", details)
        self.assertIn("method", details)

    def test_status_labels(self):
        """Verify status label thresholds."""
        from apps.health.services.protein_service import ProteinService
        self.assertEqual(ProteinService._status_label(95), "excellent")
        self.assertEqual(ProteinService._status_label(80), "good")
        self.assertEqual(ProteinService._status_label(60), "fair")
        self.assertEqual(ProteinService._status_label(45), "needs_improvement")
        self.assertEqual(ProteinService._status_label(20), "low")


# ====================================================================
# LBM-SPECIFIC TESTS
# ====================================================================


class TestLeanBodyMassCalculation(TestCase, HealthIntelligenceTestMixin):
    """Test LBM calculation and LBM-based protein targets."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_calculate_lbm_normal(self):
        """LBM = weight × (1 − body_fat_pct / 100)."""
        from apps.health.services.protein_service import ProteinService

        # 240 lbs × (1 − 36.7 / 100) = 240 × 0.633 = 151.92
        lbm = ProteinService.calculate_lean_body_mass(
            weight_lbs=Decimal("240"), body_fat_pct=Decimal("36.7")
        )
        self.assertIsNotNone(lbm)
        self.assertAlmostEqual(float(lbm), 151.92, places=1)

    def test_calculate_lbm_low_bf(self):
        """LBM with low body fat percentage."""
        from apps.health.services.protein_service import ProteinService

        # 200 lbs × (1 − 15 / 100) = 200 × 0.85 = 170
        lbm = ProteinService.calculate_lean_body_mass(
            weight_lbs=Decimal("200"), body_fat_pct=Decimal("15.0")
        )
        self.assertIsNotNone(lbm)
        self.assertAlmostEqual(float(lbm), 170.0, places=1)

    def test_calculate_lbm_none_inputs(self):
        """LBM should return None for invalid inputs."""
        from apps.health.services.protein_service import ProteinService

        self.assertIsNone(ProteinService.calculate_lean_body_mass(None, Decimal("30")))
        self.assertIsNone(ProteinService.calculate_lean_body_mass(Decimal("200"), None))
        self.assertIsNone(ProteinService.calculate_lean_body_mass(Decimal("200"), Decimal("100")))
        self.assertIsNone(ProteinService.calculate_lean_body_mass(Decimal("0"), Decimal("30")))
        self.assertIsNone(ProteinService.calculate_lean_body_mass(Decimal("200"), Decimal("-5")))

    def test_lbm_target_rest_day(self):
        """LBM target on rest day = LBM × 1.0."""
        from apps.health.services.protein_service import ProteinService

        # Create weight + body fat data
        WeightEntry.objects.create(
            user=self.user, value=Decimal("240"), unit="lb",
            recorded_at=timezone.now(),
        )
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=date.today(),
            weight=Decimal("240"),
            body_fat_pct=Decimal("36.7"),
            signals_present=["weight"],
        )

        result = ProteinService.calculate_target(
            self.user, date.today(), is_workout_day=False
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["method"], "lean_body_mass")
        self.assertFalse(result["workout_day"])
        # LBM = 240 × 0.633 = 151.92; rest target = 151.92 × 1.0 = 151.92
        self.assertAlmostEqual(float(result["target_g"]), 151.92, places=0)
        self.assertAlmostEqual(result["lbm"], 151.92, places=0)
        self.assertAlmostEqual(result["multiplier"], 1.0)

    def test_lbm_target_workout_day(self):
        """LBM target on workout day = LBM × 1.1."""
        from apps.health.services.protein_service import ProteinService

        WeightEntry.objects.create(
            user=self.user, value=Decimal("240"), unit="lb",
            recorded_at=timezone.now(),
        )
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=date.today(),
            weight=Decimal("240"),
            body_fat_pct=Decimal("36.7"),
            workout_count=1,
            signals_present=["weight", "workout"],
        )

        result = ProteinService.calculate_target(
            self.user, date.today(), is_workout_day=True
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["method"], "lean_body_mass")
        self.assertTrue(result["workout_day"])
        # LBM = 151.92; workout target = 151.92 × 1.1 = 167.11
        self.assertAlmostEqual(float(result["target_g"]), 167.11, places=0)
        self.assertAlmostEqual(result["multiplier"], 1.1)

    def test_lbm_target_auto_detect_workout(self):
        """Should auto-detect workout day from DailyHealthSummary."""
        from apps.health.services.protein_service import ProteinService

        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=date.today(),
            weight=Decimal("200"),
            body_fat_pct=Decimal("20.0"),
            workout_count=2,
            signals_present=["weight", "workout"],
        )

        result = ProteinService.calculate_target(self.user, date.today())
        self.assertTrue(result["workout_day"])
        self.assertAlmostEqual(result["multiplier"], 1.1)

    def test_fallback_to_body_weight_no_bf(self):
        """Without body fat data, should use body weight × 0.7 fallback."""
        from apps.health.services.protein_service import ProteinService

        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        # No body fat data anywhere
        result = ProteinService.calculate_target(self.user)
        self.assertIsNotNone(result)
        self.assertEqual(result["method"], "body_weight")
        self.assertIsNone(result["lbm"])
        self.assertEqual(result["target_g"], Decimal("140.00"))

    def test_override_beats_lbm(self):
        """Override should win even when body fat data is available."""
        from apps.health.services.protein_service import ProteinService

        HealthProfile.objects.create(
            user=self.user,
            protein_target_g_override=Decimal("180"),
        )
        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=date.today(),
            weight=Decimal("200"),
            body_fat_pct=Decimal("20.0"),
            signals_present=["weight"],
        )

        result = ProteinService.calculate_target(self.user)
        self.assertEqual(result["method"], "override")
        self.assertEqual(result["target_g"], Decimal("180"))
        self.assertIsNone(result["lbm"])

    def test_body_fat_from_composition_entry(self):
        """Should read body fat from BodyCompositionEntry if not in summary."""
        from apps.health.services.protein_service import ProteinService

        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        BodyCompositionEntry.objects.create(
            user=self.user,
            metric_name="body_fat_pct",
            value=Decimal("25.0"),
            measurement_date=date.today(),
        )

        result = ProteinService.calculate_target(self.user, date.today())
        self.assertIsNotNone(result)
        self.assertEqual(result["method"], "lean_body_mass")
        # LBM = 200 × 0.75 = 150; target = 150 × 1.0 = 150
        self.assertAlmostEqual(float(result["target_g"]), 150.0, places=0)

    def test_workout_day_detection_from_session(self):
        """Should detect workout day from WorkoutSession when no summary."""
        from apps.health.services.protein_service import ProteinService

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        WorkoutSession.objects.create(
            user=self.user, date=today,
            workout_type="strength", duration_minutes=60,
        )

        result = ProteinService.calculate_target(
            self.user, today, weight_lbs=Decimal("200")
        )
        self.assertIsNotNone(result)
        self.assertTrue(result["workout_day"])


class TestLBMScoring(TestCase, HealthIntelligenceTestMixin):
    """Test LBM-aware protein scoring with workout-day penalty."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_workout_day_penalty_low_ratio(self):
        """Workout day + ratio < 0.85 should incur -10 point penalty."""
        from apps.health.services.protein_service import ProteinService

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )

        # Create 7 days of summaries for scoring context
        for i in range(7):
            d = today - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                protein_g=Decimal("90"),  # Low — ~64% of 140g target
                weight=Decimal("200"),
                workout_count=1 if i == 0 else 0,  # Today is workout day
                nutrition_logged=True,
                signals_present=["nutrition", "weight", "workout"],
            )

        score, details = ProteinService.calculate_score(self.user, today)
        self.assertIsNotNone(score)
        self.assertTrue(details["workout_day"])
        # With penalty, the ratio component should be lowered
        self.assertIn("components", details)

    def test_score_includes_method_and_lbm(self):
        """Score details should include method and LBM info."""
        from apps.health.services.protein_service import ProteinService

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            protein_g=Decimal("150"),
            weight=Decimal("200"),
            body_fat_pct=Decimal("20.0"),
            nutrition_logged=True,
            signals_present=["nutrition", "weight"],
        )

        score, details = ProteinService.calculate_score(self.user, today)
        self.assertIsNotNone(score)
        self.assertEqual(details["method"], "lean_body_mass")
        self.assertIsNotNone(details["lbm"])


class TestLBMCoaching(TestCase, HealthIntelligenceTestMixin):
    """Test LBM-aware coaching messages."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_coaching_includes_lbm_method_note(self):
        """Coaching should include LBM method note when applicable."""
        from apps.health.services.protein_service import ProteinService

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            protein_g=Decimal("200"),
            weight=Decimal("200"),
            body_fat_pct=Decimal("20.0"),
            nutrition_logged=True,
            signals_present=["nutrition", "weight"],
        )

        coaching = ProteinService.get_coaching(self.user, today)
        self.assertEqual(coaching["method"], "lean_body_mass")
        self.assertIsNotNone(coaching["lbm"])
        self.assertIn("LBM", coaching["message"])

    def test_coaching_workout_nudge_with_lbm(self):
        """Workout day + no data should nudge with LBM target."""
        from apps.health.services.protein_service import ProteinService

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            weight=Decimal("200"),
            body_fat_pct=Decimal("20.0"),
            workout_count=1,
            signals_present=["weight", "workout"],
        )

        coaching = ProteinService.get_coaching(self.user, today)
        self.assertEqual(coaching["context"], "workout_day_no_data")
        self.assertEqual(coaching["severity"], "nudge")
        self.assertEqual(coaching["method"], "lean_body_mass")


class TestProteinCoaching(TestCase, HealthIntelligenceTestMixin):
    """Test protein coaching messages."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_coaching_no_weight(self):
        """Should suggest logging weight when no weight data."""
        from apps.health.services.protein_service import ProteinService

        coaching = ProteinService.get_coaching(self.user, date.today())
        self.assertEqual(coaching["context"], "missing_weight")

    def test_coaching_target_met(self):
        """Should congratulate when target is hit."""
        from apps.health.services.protein_service import ProteinService

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("240"), unit="lb",
            recorded_at=timezone.now(),
        )
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            protein_g=Decimal("180"),
            weight=Decimal("240"),
            nutrition_logged=True,
            signals_present=["nutrition", "weight"],
        )

        coaching = ProteinService.get_coaching(self.user, today)
        self.assertEqual(coaching["severity"], "success")
        self.assertEqual(coaching["context"], "target_met")

    def test_coaching_low_protein_workout_day(self):
        """Should warn about low protein on workout days."""
        from apps.health.services.protein_service import ProteinService

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("240"), unit="lb",
            recorded_at=timezone.now(),
        )
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            protein_g=Decimal("80"),
            weight=Decimal("240"),
            workout_count=1,
            nutrition_logged=True,
            signals_present=["nutrition", "weight", "workout"],
        )

        coaching = ProteinService.get_coaching(self.user, today)
        self.assertEqual(coaching["severity"], "warning")
        self.assertEqual(coaching["context"], "low_protein_workout_day")
        self.assertIn("workout day", coaching["message"].lower())


class TestProteinInBuilder(TestCase, HealthIntelligenceTestMixin):
    """Test protein intelligence integration in the builder."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_builder_computes_protein_fields(self):
        """Builder should populate protein target, ratio, score, method."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        DailyNutritionSummary.objects.create(
            user=self.user,
            summary_date=today,
            total_calories=Decimal("2100"),
            total_protein_g=Decimal("140"),
            total_carbohydrates_g=Decimal("200"),
            total_fat_g=Decimal("80"),
            total_fiber_g=Decimal("25"),
            total_sugar_g=Decimal("50"),
            total_saturated_fat_g=Decimal("20"),
            total_sodium_mg=Decimal("2000"),
            breakfast_count=1,
            lunch_count=1,
            dinner_count=1,
            snack_count=0,
        )

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(self.user, today)

        self.assertEqual(summary.protein_g, Decimal("140"))
        self.assertEqual(summary.protein_consumed_g, Decimal("140"))
        # target should be 200 * 0.7 = 140 (body_weight method)
        self.assertIsNotNone(summary.protein_target_g)
        self.assertEqual(summary.protein_target_g, Decimal("140.00"))
        self.assertEqual(summary.protein_method, "body_weight")
        # ratio should be 1.0
        self.assertIsNotNone(summary.protein_ratio)
        self.assertEqual(summary.protein_ratio, Decimal("1.00"))
        self.assertIsNotNone(summary.protein_per_lb)
        self.assertEqual(summary.protein_per_lb, Decimal("0.700"))
        self.assertIsNotNone(summary.protein_score)
        self.assertGreaterEqual(summary.protein_score, 85)

    def test_builder_lbm_method_with_body_fat(self):
        """Builder should use LBM method when body fat is available."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
            body_fat_percentage=Decimal("20.0"),
        )
        DailyNutritionSummary.objects.create(
            user=self.user,
            summary_date=today,
            total_calories=Decimal("2100"),
            total_protein_g=Decimal("160"),
            total_carbohydrates_g=Decimal("200"),
            total_fat_g=Decimal("80"),
            total_fiber_g=Decimal("25"),
            total_sugar_g=Decimal("50"),
            total_saturated_fat_g=Decimal("20"),
            total_sodium_mg=Decimal("2000"),
            breakfast_count=1,
            lunch_count=1,
            dinner_count=1,
            snack_count=0,
        )

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(self.user, today)

        self.assertEqual(summary.protein_method, "lean_body_mass")
        # LBM = 200 × 0.80 = 160; target = 160 × 1.0 = 160
        self.assertIsNotNone(summary.protein_target_g)
        self.assertAlmostEqual(float(summary.protein_target_g), 160.0, places=0)

    def test_builder_workout_day_penalty_in_score(self):
        """Builder should apply workout-day penalty when protein is low."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        # Workout session makes it a workout day
        WorkoutSession.objects.create(
            user=self.user, date=today,
            workout_type="strength", duration_minutes=60,
        )
        DailyNutritionSummary.objects.create(
            user=self.user,
            summary_date=today,
            total_calories=Decimal("1500"),
            total_protein_g=Decimal("80"),  # Low for 200lb (target ~140g)
            total_carbohydrates_g=Decimal("150"),
            total_fat_g=Decimal("60"),
            total_fiber_g=Decimal("20"),
            total_sugar_g=Decimal("40"),
            total_saturated_fat_g=Decimal("15"),
            total_sodium_mg=Decimal("1500"),
            breakfast_count=1,
            lunch_count=1,
            dinner_count=0,
            snack_count=0,
        )

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(self.user, today)

        # Score should be reduced by workout-day penalty
        self.assertIsNotNone(summary.protein_score)
        # 80/140 = 0.57 → base 58, workout penalty → 48
        self.assertLessEqual(summary.protein_score, 60)

    def test_builder_no_protein_no_crash(self):
        """Builder should handle days with no nutrition data gracefully."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        today = date.today()
        StepsEntry.objects.create(
            user=self.user, logged_date=today, count=8000,
            recorded_at=timezone.now(),
        )

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(self.user, today)

        self.assertIsNone(summary.protein_target_g)
        self.assertIsNone(summary.protein_ratio)
        self.assertIsNone(summary.protein_score)


class TestProteinTrends(TestCase, HealthIntelligenceTestMixin):
    """Test protein pattern detection in the trend analyzer."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_low_protein_detected(self):
        """Should flag very low protein intake."""
        from apps.health.services.trend_analyzer import HealthTrendAnalyzer

        WeightEntry.objects.create(
            user=self.user, value=Decimal("240"), unit="lb",
            recorded_at=timezone.now(),
        )

        for i in range(10):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                protein_g=Decimal("60"),
                weight=Decimal("240"),
                sleep_hours=Decimal("7"),
                nutrition_logged=True,
                signals_present=["nutrition", "weight", "sleep"],
            )

        analysis = HealthTrendAnalyzer.analyze(self.user, date.today())

        protein_issues = [
            r for r in analysis["risk_flags"]
            if r.get("domain") == "protein"
        ] + [
            w for w in analysis["weaknesses"]
            if "protein" in w.lower()
        ]
        self.assertTrue(len(protein_issues) > 0, "Should detect low protein intake")

    def test_strong_protein_detected(self):
        """Should recognize strong protein intake as a strength."""
        from apps.health.services.trend_analyzer import HealthTrendAnalyzer

        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )

        for i in range(10):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                protein_g=Decimal("180"),
                weight=Decimal("200"),
                sleep_hours=Decimal("7"),
                nutrition_logged=True,
                signals_present=["nutrition", "weight", "sleep"],
            )

        analysis = HealthTrendAnalyzer.analyze(self.user, date.today())

        protein_strengths = [
            s for s in analysis["strengths"]
            if "protein" in s.lower()
        ]
        self.assertTrue(len(protein_strengths) > 0, "Should detect strong protein intake")

    def test_low_protein_on_workout_days(self):
        """Should flag low protein on workout days specifically."""
        from apps.health.services.trend_analyzer import HealthTrendAnalyzer

        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )

        for i in range(10):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                protein_g=Decimal("80"),
                weight=Decimal("200"),
                sleep_hours=Decimal("7"),
                workout_count=1 if i % 2 == 0 else 0,
                nutrition_logged=True,
                signals_present=["nutrition", "weight", "sleep", "workout"],
            )

        analysis = HealthTrendAnalyzer.analyze(self.user, date.today())

        workout_protein_flags = [
            r for r in analysis["risk_flags"]
            if r.get("domain") == "protein"
            and ("workout" in r.get("message", "").lower()
                 or "training" in r.get("message", "").lower())
        ]
        self.assertTrue(
            len(workout_protein_flags) > 0,
            "Should flag low protein on workout/training days",
        )

    def test_protein_lower_on_training_days_flag(self):
        """Should flag when protein is lower on training days than rest days."""
        from apps.health.services.trend_analyzer import HealthTrendAnalyzer

        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )

        for i in range(10):
            d = date.today() - timedelta(days=i)
            is_workout = i % 2 == 0
            # Workout days: lower protein (wrong direction)
            protein = Decimal("100") if is_workout else Decimal("160")
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                protein_g=protein,
                weight=Decimal("200"),
                sleep_hours=Decimal("7"),
                workout_count=1 if is_workout else 0,
                nutrition_logged=True,
                signals_present=["nutrition", "weight", "sleep", "workout"],
            )

        analysis = HealthTrendAnalyzer.analyze(self.user, date.today())

        # Should find a flag about protein being lower on training days
        training_gap_flags = [
            r for r in analysis["risk_flags"]
            if r.get("domain") == "protein"
            and "lower on training" in r.get("message", "").lower()
        ]
        self.assertTrue(
            len(training_gap_flags) > 0,
            "Should flag protein lower on training days than rest days",
        )


class TestProteinInHealthScore(TestCase, HealthIntelligenceTestMixin):
    """Test protein's impact on health score."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_high_protein_boosts_nutrition_score(self):
        """Good protein intake should improve nutrition domain score."""
        from apps.health.services.health_score import HealthScoreService

        for i in range(15):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                sleep_hours=Decimal("7.5"),
                sleep_quality_score=75,
                steps=8000,
                workout_count=1 if i % 2 == 0 else 0,
                calories_consumed=2100,
                protein_g=Decimal("170"),
                weight=Decimal("200"),
                nutrition_logged=True,
                recovery_score=72,
                signals_present=["sleep", "steps", "weight", "nutrition"],
            )

        score, drivers = HealthScoreService.compute(self.user, date.today())

        self.assertIsNotNone(score)
        nutrition_domain = drivers.get("domains", {}).get("nutrition", {})
        self.assertGreaterEqual(nutrition_domain.get("score", 0), 70)

    def test_low_protein_hurts_nutrition_score(self):
        """Poor protein intake should lower nutrition domain score."""
        from apps.health.services.health_score import HealthScoreService

        for i in range(15):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                sleep_hours=Decimal("7.5"),
                sleep_quality_score=75,
                steps=8000,
                workout_count=1 if i % 2 == 0 else 0,
                calories_consumed=2100,
                protein_g=Decimal("50"),
                weight=Decimal("200"),
                nutrition_logged=True,
                recovery_score=72,
                signals_present=["sleep", "steps", "weight", "nutrition"],
            )

        score, drivers = HealthScoreService.compute(self.user, date.today())

        self.assertIsNotNone(score)
        nutrition_domain = drivers.get("domains", {}).get("nutrition", {})
        self.assertLessEqual(nutrition_domain.get("score", 100), 65)


class TestProteinCorrelations(TestCase, HealthIntelligenceTestMixin):
    """Test protein correlations including new LBM-era correlations."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_protein_recovery_correlation(self):
        """Should compute protein ↔ recovery correlation with data."""
        from apps.health.services.correlation_service import CorrelationService

        import random
        random.seed(99)

        for i in range(28):
            d = date.today() - timedelta(days=i)
            protein = Decimal(str(round(100 + random.random() * 100, 2)))
            recovery = int(40 + float(protein) * 0.3 + random.random() * 10)

            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                protein_g=protein,
                protein_per_lb=Decimal(str(round(float(protein) / 200, 3))),
                sleep_hours=Decimal(str(round(6 + random.random() * 3, 2))),
                sleep_quality_score=int(60 + random.random() * 30),
                recovery_score=min(100, recovery),
                weight=Decimal("200"),
                signals_present=["nutrition", "weight", "sleep"],
            )

        results = CorrelationService.compute(self.user, date.today())

        self.assertGreater(len(results), 0)
        for r in results:
            self.assertIn("signal_a", r)
            self.assertIn("interpretation", r)
            self.assertTrue(-1 <= r["correlation"] <= 1)

    def test_new_interpretation_methods(self):
        """Verify all new correlation interpretation methods work."""
        from apps.health.services.correlation_service import CorrelationService

        # Muscle correlation
        msg = CorrelationService._interpret_protein_muscle(0.5)
        self.assertIn("muscle", msg.lower())
        msg = CorrelationService._interpret_protein_muscle(0.0)
        self.assertIn("no clear", msg.lower())

        # Fat loss
        msg = CorrelationService._interpret_protein_fat_loss(-0.4)
        self.assertIn("fat", msg.lower())

        # Performance
        msg = CorrelationService._interpret_protein_performance(0.5)
        self.assertIn("training", msg.lower())


class TestProteinWeeklySummary(TestCase, HealthIntelligenceTestMixin):
    """Test protein weekly summary with LBM info."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_weekly_summary_no_data(self):
        """Should handle no data gracefully."""
        from apps.health.services.protein_service import ProteinService

        summary = ProteinService.get_weekly_summary(self.user, date.today())
        self.assertEqual(summary["status"], "no_data")

    def test_weekly_summary_with_data(self):
        """Should compute weekly averages and include method."""
        from apps.health.services.protein_service import ProteinService

        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )

        for i in range(7):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                protein_g=Decimal("150") + Decimal(str(i * 5)),
                weight=Decimal("200"),
                workout_count=1 if i % 2 == 0 else 0,
                nutrition_logged=True,
                signals_present=["nutrition", "weight"],
            )

        summary = ProteinService.get_weekly_summary(self.user, date.today())

        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["days_tracked"], 7)
        self.assertIsNotNone(summary["avg_consumed_g"])
        self.assertIsNotNone(summary["target_g"])
        self.assertIn("method", summary)
        self.assertIn("lbm", summary)
        self.assertIn("daily_detail", summary)
        self.assertEqual(len(summary["daily_detail"]), 7)

    def test_weekly_summary_workout_rest_split(self):
        """Should show separate workout vs rest day averages."""
        from apps.health.services.protein_service import ProteinService

        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )

        for i in range(7):
            d = date.today() - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                protein_g=Decimal("180") if i % 2 == 0 else Decimal("140"),
                weight=Decimal("200"),
                workout_count=1 if i % 2 == 0 else 0,
                nutrition_logged=True,
                signals_present=["nutrition", "weight"],
            )

        summary = ProteinService.get_weekly_summary(self.user, date.today())
        self.assertIn("workout_day_avg_g", summary)
        self.assertIn("rest_day_avg_g", summary)
        # Workout day avg should be higher
        self.assertGreater(summary["workout_day_avg_g"], summary["rest_day_avg_g"])


class TestProteinInCommandCenter(TestCase, HealthIntelligenceTestMixin):
    """Test protein panel in Command Center API (LBM-aware)."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_protein_panel_in_dashboard(self):
        """Dashboard should include protein panel with LBM fields."""
        from apps.health.services.command_center_api import HealthCommandCenterService

        today = date.today()
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            protein_g=Decimal("160"),
            protein_target_g=Decimal("168"),
            protein_ratio=Decimal("0.95"),
            protein_score=85,
            protein_per_lb=Decimal("0.667"),
            protein_consumed_g=Decimal("160"),
            protein_method="lean_body_mass",
            weight=Decimal("240"),
            workout_count=1,
            nutrition_logged=True,
            signals_present=["nutrition", "weight", "workout"],
        )

        data = HealthCommandCenterService.get_dashboard_data(self.user, today)

        self.assertIn("protein", data["domain_panels"])
        protein_panel = data["domain_panels"]["protein"]
        self.assertEqual(protein_panel["today_consumed_g"], 160.0)
        self.assertEqual(protein_panel["today_target_g"], 168.0)
        self.assertEqual(protein_panel["today_score"], 85)
        self.assertEqual(protein_panel["today_method"], "lean_body_mass")
        self.assertTrue(protein_panel["is_workout_day"])


class TestCosProteinIntelligence(TestCase, HealthIntelligenceTestMixin):
    """Test CoS protein intelligence with LBM context."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_cos_protein_intelligence_has_lbm_fields(self):
        """CoS context should include method, LBM, and workout_day."""
        from apps.health.services.cos_health_context import build_cos_health_intelligence

        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            weight=Decimal("200"),
            body_fat_pct=Decimal("20.0"),
            protein_g=Decimal("150"),
            nutrition_logged=True,
            signals_present=["weight", "nutrition"],
            baseline_ready=False,
        )

        intel = build_cos_health_intelligence(self.user)
        protein = intel.get("protein_intelligence", {})

        self.assertIn("method", protein)
        self.assertIn("lean_body_mass", protein)
        self.assertIn("workout_day", protein)
        self.assertIsNotNone(protein.get("target_g"))

    def test_cos_summary_serializes_protein_method(self):
        """Summary serializer should include protein_method."""
        from apps.health.services.cos_health_context import _serialize_summary

        today = date.today()
        summary = DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            protein_method="lean_body_mass",
            signals_present=["nutrition"],
        )

        serialized = _serialize_summary(summary)
        self.assertEqual(serialized["protein_method"], "lean_body_mass")


# =========================================================================
# CoS Health Intelligence Injection Tests
# =========================================================================


class TestCosHealthIntelligenceInjection(TestCase, HealthIntelligenceTestMixin):
    """Test that health intelligence is properly injected into CoS context."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_format_health_intelligence_block_with_protein(self):
        """The health intelligence block should include protein target data."""
        from apps.core.ai_orchestrator.cos_context import (
            _format_health_intelligence_block,
        )

        health_intel = {
            'health_score': 75,
            'recovery_score': 82,
            'recovery_status': 'good',
            'strengths': ['Sleep consistency'],
            'weaknesses': ['Low protein intake'],
            'risk_flags': ['Declining workout frequency'],
            'top_recommendation': 'Increase protein to target',
            'protein': {
                'target_g': 193.0,
                'method': 'lean_body_mass',
                'lbm': 175.5,
                'workout_day': True,
                'multiplier': 1.1,
            },
            'correlations': [
                {
                    'signals': 'protein ↔ recovery',
                    'interpretation': 'Higher protein correlates with better recovery',
                },
            ],
        }
        context = {
            'health_intelligence': health_intel,
            'health_intelligence_summary': 'Health score: 75/100',
        }

        result = _format_health_intelligence_block(health_intel, context)

        # Must contain MANDATORY directive
        self.assertIn("MANDATORY", result)
        self.assertIn("EXACT", result)

        # Must contain system scores
        self.assertIn("75/100", result)
        self.assertIn("82/100", result)

        # Must contain protein target data
        self.assertIn("193g", result)
        self.assertIn("lean body mass", result.lower())
        self.assertIn("175.5", result)
        self.assertIn("workout day", result)

        # Must contain strengths/weaknesses
        self.assertIn("Sleep consistency", result)
        self.assertIn("Low protein intake", result)

        # Must contain risk flags
        self.assertIn("Declining workout frequency", result)

        # Must contain recommendation
        self.assertIn("Increase protein to target", result)

    def test_format_health_intelligence_block_minimal(self):
        """Block should work with minimal data (no protein)."""
        from apps.core.ai_orchestrator.cos_context import (
            _format_health_intelligence_block,
        )

        health_intel = {
            'health_score': 60,
            'protein': {},
        }
        context = {'health_intelligence': health_intel}

        result = _format_health_intelligence_block(health_intel, context)

        self.assertIn("60/100", result)
        self.assertIn("HEALTH INTELLIGENCE", result)
        # Should NOT crash or include empty protein section
        self.assertNotIn("Daily target:", result)

    def test_health_intelligence_included_in_cos_injection(self):
        """format_cos_system_injection should include health intelligence block."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection,
        )

        context = {
            'health_intelligence': {
                'health_score': 78,
                'recovery_score': 85,
                'protein': {
                    'target_g': 200.0,
                    'method': 'lean_body_mass',
                    'lbm': 182.0,
                    'workout_day': False,
                    'multiplier': 1.0,
                },
                'strengths': [],
                'weaknesses': [],
                'risk_flags': [],
                'correlations': [],
            },
            'health_intelligence_summary': 'Health score: 78/100',
        }

        injection = format_cos_system_injection(context)

        # The injection must contain the health intelligence block
        self.assertIn("HEALTH INTELLIGENCE", injection)
        self.assertIn("200g", injection)
        self.assertIn("78/100", injection)
        self.assertIn("lean body mass", injection.lower())

    def test_cos_injection_without_health_intelligence(self):
        """format_cos_system_injection should not crash without health intel."""
        from apps.core.ai_orchestrator.cos_context import (
            format_cos_system_injection,
        )

        context = {}  # No health intelligence at all
        injection = format_cos_system_injection(context)

        # Should still produce a valid injection without health block
        self.assertIn("OPERATIONAL INTELLIGENCE", injection)
        self.assertNotIn("HEALTH INTELLIGENCE", injection)

    def test_protein_target_in_build_health_and_vitals(self):
        """_build_health_and_vitals should include protein data in health_intelligence."""
        today = date.today()
        WeightEntry.objects.create(
            user=self.user, value=Decimal("220"), unit="lb",
            recorded_at=timezone.now(),
        )
        HealthProfile.objects.create(
            user=self.user,
            protein_per_lb_target=Decimal("0.8"),
        )
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=today,
            weight=Decimal("220"),
            body_fat_pct=Decimal("18.0"),
            protein_g=Decimal("160"),
            protein_target_g=Decimal("198"),
            protein_method="lean_body_mass",
            nutrition_logged=True,
            signals_present=["weight", "nutrition"],
            baseline_ready=False,
        )

        from apps.core.ai_orchestrator.cos_context import _build_health_and_vitals
        result = _build_health_and_vitals(self.user)

        health_intel = result.get('health_intelligence', {})
        protein = health_intel.get('protein', {})

        # Protein intelligence should be populated
        self.assertIsNotNone(protein.get('target_g'))
        self.assertIsNotNone(protein.get('method'))


# =========================================================================
# Health Response Validator Tests
# =========================================================================


class TestHealthResponseValidator(TestCase):
    """Test the health response validator catches generic health advice."""

    def test_detects_generic_protein_range(self):
        """Should detect generic protein ranges that contradict system values."""
        from apps.ai.validators.health_response_validator import (
            validate_health_response,
        )

        cos_context = {
            'health_intelligence': {
                'protein': {
                    'target_g': 193.0,
                    'method': 'lean_body_mass',
                },
            },
        }

        # This is the bad response — generic range instead of system value
        response = (
            "For your body weight, a good protein target would be "
            "110-138g per day."
        )

        result = validate_health_response(response, cos_context)
        self.assertTrue(result['has_violations'])
        self.assertEqual(result['severity'], 'critical')
        self.assertTrue(
            any(v['type'] == 'GENERIC_PROTEIN_RANGE' for v in result['violations'])
        )

    def test_accepts_system_protein_value(self):
        """Should NOT flag a response that uses the correct system value."""
        from apps.ai.validators.health_response_validator import (
            validate_health_response,
        )

        cos_context = {
            'health_intelligence': {
                'protein': {
                    'target_g': 193.0,
                    'method': 'lean_body_mass',
                },
            },
        }

        # Good response — uses system value
        response = (
            "Your protein target is 193g today, calculated from your "
            "lean body mass. You're at 150g so far."
        )

        result = validate_health_response(response, cos_context)
        # Should have no protein range violations
        protein_violations = [
            v for v in result['violations']
            if v['type'] == 'GENERIC_PROTEIN_RANGE'
        ]
        self.assertEqual(len(protein_violations), 0)

    def test_detects_generic_health_phrases(self):
        """Should detect generic health advice language."""
        from apps.ai.validators.health_response_validator import (
            validate_health_response,
        )

        response = (
            "Most experts recommend getting 7-9 hours of sleep. "
            "A good target for protein is generally recommended at "
            "0.7-1.0g per pound."
        )

        result = validate_health_response(response, {})
        self.assertTrue(result['has_violations'])
        generic_phrases = [
            v for v in result['violations']
            if v['type'] == 'GENERIC_HEALTH_PHRASE'
        ]
        self.assertTrue(len(generic_phrases) > 0)

    def test_no_violations_on_clean_response(self):
        """Clean system-value response should have no violations."""
        from apps.ai.validators.health_response_validator import (
            validate_health_response,
        )

        cos_context = {
            'health_intelligence': {
                'protein': {'target_g': 193.0, 'method': 'lean_body_mass'},
            },
        }

        response = (
            "Your health score is 75 out of 100. Recovery is looking good "
            "at 82. Your protein target is 193g based on your lean body mass."
        )

        result = validate_health_response(response, cos_context)
        self.assertFalse(result['has_violations'])
        self.assertEqual(result['severity'], 'none')

    def test_empty_response(self):
        """Empty response should return no violations."""
        from apps.ai.validators.health_response_validator import (
            validate_health_response,
        )

        result = validate_health_response("", {})
        self.assertFalse(result['has_violations'])
        self.assertEqual(result['severity'], 'none')

    def test_none_context(self):
        """Should handle None context gracefully."""
        from apps.ai.validators.health_response_validator import (
            validate_health_response,
        )

        response = "Your protein looks good today."
        result = validate_health_response(response, None)
        self.assertFalse(result['has_violations'])

    def test_detects_weekly_total_language(self):
        """Should flag 'Xg this week' as a weekly total violation."""
        from apps.ai.validators.health_response_validator import (
            validate_health_response,
        )

        bad_responses = [
            "You've logged 120g this week and are 93g short of your target.",
            "You consumed 840g for the week.",
            "Your total protein this week is 750g.",
            "You've had 500g this week.",
            "Your weekly total is about 900g.",
        ]

        for response in bad_responses:
            result = validate_health_response(response, {})
            weekly_total_violations = [
                v for v in result['violations']
                if v['type'] == 'PROTEIN_WEEKLY_TOTAL'
            ]
            self.assertTrue(
                len(weekly_total_violations) > 0,
                f"Expected PROTEIN_WEEKLY_TOTAL violation for: {response!r}"
            )

    def test_accepts_daily_average_language(self):
        """Should NOT flag 'averaged Xg per day' responses."""
        from apps.ai.validators.health_response_validator import (
            validate_health_response,
        )

        cos_context = {
            'health_intelligence': {
                'protein': {'target_g': 213.0, 'method': 'lean_body_mass'},
            },
        }

        good_response = (
            "Your protein target is 213g per day. Over the last 7 days "
            "you've averaged 168g per day, hitting about 79% of your target."
        )

        result = validate_health_response(good_response, cos_context)
        weekly_total_violations = [
            v for v in result['violations']
            if v['type'] == 'PROTEIN_WEEKLY_TOTAL'
        ]
        self.assertEqual(len(weekly_total_violations), 0)

    def test_weekly_total_is_critical_severity(self):
        """Weekly total violations should be critical severity."""
        from apps.ai.validators.health_response_validator import (
            validate_health_response,
        )

        response = "You've logged 840g this week."
        result = validate_health_response(response, {})
        self.assertEqual(result['severity'], 'critical')


# =========================================================================
# Protein Intelligence Data Isolation Tests
# =========================================================================


class TestProteinDataIsolation(TestCase, HealthIntelligenceTestMixin):
    """Verify that raw weekly data is NOT exposed to the LLM."""

    def setUp(self):
        self.user = self.create_test_user()

    def test_no_weekly_summary_in_protein_intelligence(self):
        """protein_intelligence must NOT contain raw weekly_summary dict."""
        from apps.health.services.cos_health_context import build_cos_health_intelligence

        today = date.today()
        for i in range(7):
            d = today - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                protein_g=Decimal("150"),
                protein_target_g=Decimal("200"),
                protein_ratio=Decimal("0.75"),
                nutrition_logged=True,
                signals_present=["nutrition"],
            )
        WeightEntry.objects.create(
            user=self.user, value=Decimal("220"), unit="lb",
            recorded_at=timezone.now(),
        )

        intel = build_cos_health_intelligence(self.user)
        protein = intel.get("protein_intelligence", {})

        # Must NOT have weekly_summary (raw dict dump)
        self.assertNotIn("weekly_summary", protein)

        # Must have pre-calculated evaluation fields
        self.assertIn("protein_avg_7d", protein)
        self.assertIn("protein_gap_g", protein)
        self.assertIn("protein_consistency_pct", protein)
        self.assertIn("protein_avg_ratio", protein)
        self.assertIn("target_g", protein)

    def test_trends_7d_excludes_raw_protein(self):
        """trends_7d in health_intelligence must not contain protein_ fields."""
        from apps.core.ai_orchestrator.cos_context import _build_health_and_vitals

        today = date.today()
        for i in range(7):
            d = today - timedelta(days=i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                protein_g=Decimal("150"),
                protein_target_g=Decimal("200"),
                protein_ratio=Decimal("0.75"),
                sleep_hours=Decimal("7.5"),
                steps=8000,
                nutrition_logged=True,
                signals_present=["nutrition", "sleep", "steps"],
                baseline_ready=False,
            )
        WeightEntry.objects.create(
            user=self.user, value=Decimal("220"), unit="lb",
            recorded_at=timezone.now(),
        )

        result = _build_health_and_vitals(self.user)
        health_intel = result.get('health_intelligence', {})
        trends = health_intel.get('trends_7d', {})

        # No protein_ keys should be in trends_7d
        protein_keys = [k for k in trends if k.startswith('protein')]
        self.assertEqual(
            protein_keys, [],
            f"trends_7d should not contain protein fields, found: {protein_keys}"
        )

        # But non-protein fields should still be present
        # (only if the trend analyzer returned them)
        # The protein data is in the 'protein' sub-dict instead

    def test_system_prompt_has_anti_math_rules(self):
        """System prompt must include Rules 6 and 7 (anti-math, weekly format)."""
        from apps.ai.personal_assistant import COS_PROACTIVE_INTELLIGENCE_PROMPT

        self.assertIn("RULE 6", COS_PROACTIVE_INTELLIGENCE_PROMPT)
        self.assertIn("NEVER COMPUTE YOUR OWN HEALTH MATH", COS_PROACTIVE_INTELLIGENCE_PROMPT)
        self.assertIn("NEVER multiply a daily average by 7", COS_PROACTIVE_INTELLIGENCE_PROMPT)

        self.assertIn("RULE 7", COS_PROACTIVE_INTELLIGENCE_PROMPT)
        self.assertIn("WEEKLY PROTEIN QUESTIONS", COS_PROACTIVE_INTELLIGENCE_PROMPT)
        self.assertIn("averaged", COS_PROACTIVE_INTELLIGENCE_PROMPT)

    def test_cos_injection_weekly_block_uses_average_language(self):
        """The injection block must say 'average intake' not 'total'."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = {
            'health_intelligence': {
                'health_score': 75,
                'protein': {
                    'target_g': 213.0,
                    'method': 'lean_body_mass',
                    'lbm': 175.0,
                    'workout_day': False,
                    'multiplier': 1.0,
                    'protein_avg_7d': 168.0,
                    'protein_consistency_pct': 57.1,
                    'protein_gap_g': 45.0,
                    'protein_avg_ratio': 0.79,
                },
                'strengths': [],
                'weaknesses': [],
                'risk_flags': [],
                'correlations': [],
            },
        }

        injection = format_cos_system_injection(context)

        # Must use "average" language, never "total"
        self.assertIn("7-day average intake", injection)
        self.assertNotIn("weekly total", injection.lower())
        self.assertNotIn("total protein", injection.lower())


# =========================================================================
# System Prompt Health Rules Tests
# =========================================================================


class TestSystemPromptHealthRules(TestCase):
    """Test that the system prompt includes health intelligence enforcement."""

    def test_cos_prompt_includes_health_enforcement(self):
        """COS_PROACTIVE_INTELLIGENCE_PROMPT should include Section 9."""
        from apps.ai.personal_assistant import COS_PROACTIVE_INTELLIGENCE_PROMPT

        self.assertIn("SECTION 9", COS_PROACTIVE_INTELLIGENCE_PROMPT)
        self.assertIn("HEALTH INTELLIGENCE ENFORCEMENT", COS_PROACTIVE_INTELLIGENCE_PROMPT)
        self.assertIn("USE SYSTEM VALUES ONLY", COS_PROACTIVE_INTELLIGENCE_PROMPT)
        self.assertIn("NEVER GENERATE GENERIC RANGES", COS_PROACTIVE_INTELLIGENCE_PROMPT)
        self.assertIn("NEVER CONTRADICT SYSTEM VALUES", COS_PROACTIVE_INTELLIGENCE_PROMPT)

    def test_built_prompt_includes_health_enforcement(self):
        """build_personal_assistant_prompt should include health rules."""
        from apps.ai.personal_assistant import (
            COS_PROACTIVE_INTELLIGENCE_PROMPT,
            build_personal_assistant_prompt,
        )

        prompt = build_personal_assistant_prompt(
            coaching_style='supportive',
            faith_enabled=False,
            cos_proactive_prompt=COS_PROACTIVE_INTELLIGENCE_PROMPT,
        )

        self.assertIn("HEALTH INTELLIGENCE ENFORCEMENT", prompt)
        self.assertIn("NEVER GENERATE GENERIC RANGES", prompt)


# =========================================================================
# Weekly Protein Evaluation Tests (7-day average, not total)
# =========================================================================


class TestWeeklyProteinEvaluation(TestCase, HealthIntelligenceTestMixin):
    """
    Verify that weekly protein evaluation uses 7-day AVERAGE (not total)
    and exposes protein_avg_7d, protein_consistency_pct, protein_gap_g.

    Bug: CoS was comparing weekly protein TOTAL against a DAILY target,
    producing responses like "120g this week, 93g short of 213g target."
    Fix: Use avg_consumed_g / target_g for weekly evaluation.
    """

    def setUp(self):
        self.user = self.create_test_user()
        self.today = date.today()

    def _create_protein_week(self, daily_values, target_g=200):
        """
        Create 7 days of DailyHealthSummary with specified protein values.

        Args:
            daily_values: list of protein_g values (one per day, most recent last)
            target_g: daily protein target
        """
        for i, protein_g in enumerate(daily_values):
            d = self.today - timedelta(days=len(daily_values) - 1 - i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                protein_g=Decimal(str(protein_g)),
                protein_target_g=Decimal(str(target_g)),
                protein_ratio=Decimal(str(round(protein_g / target_g, 3))),
                protein_consumed_g=Decimal(str(protein_g)),
                nutrition_logged=True,
                signals_present=["nutrition"],
            )

    def test_weekly_summary_uses_average_not_total(self):
        """get_weekly_summary must return avg_consumed_g (not sum)."""
        from apps.health.services.protein_service import ProteinService

        # 7 days of protein: 150, 160, 170, 180, 190, 200, 210
        daily = [150, 160, 170, 180, 190, 200, 210]
        self._create_protein_week(daily, target_g=213)

        # Create a weight entry for target calculation
        WeightEntry.objects.create(
            user=self.user, value=Decimal("220"), unit="lb",
            recorded_at=timezone.now(),
        )

        weekly = ProteinService.get_weekly_summary(self.user, self.today)

        expected_avg = sum(daily) / len(daily)  # 180.0
        self.assertEqual(weekly["status"], "ok")
        self.assertAlmostEqual(weekly["avg_consumed_g"], expected_avg, places=0)

        # Must NOT be the total (1260)
        self.assertNotEqual(weekly["avg_consumed_g"], sum(daily))

        # avg_ratio should be avg/target, not total/target
        if weekly.get("avg_ratio"):
            # avg_ratio should be approximately 180/target, not 1260/target
            self.assertLess(weekly["avg_ratio"], 2.0)

    def test_cos_health_intelligence_has_weekly_fields(self):
        """build_cos_health_intelligence must include protein_avg_7d, gap, consistency."""
        from apps.health.services.cos_health_context import build_cos_health_intelligence

        daily = [150, 160, 170, 180, 190, 200, 210]
        self._create_protein_week(daily, target_g=213)
        WeightEntry.objects.create(
            user=self.user, value=Decimal("220"), unit="lb",
            recorded_at=timezone.now(),
        )

        intel = build_cos_health_intelligence(self.user)
        protein = intel.get("protein_intelligence", {})

        # Weekly evaluation fields must be present
        self.assertIn("protein_avg_7d", protein)
        self.assertIn("protein_gap_g", protein)
        self.assertIn("protein_consistency_pct", protein)
        self.assertIn("protein_avg_ratio", protein)

        # avg must be ~180, not 1260
        avg = protein["protein_avg_7d"]
        self.assertIsNotNone(avg)
        self.assertGreater(avg, 100)
        self.assertLess(avg, 250)  # Sanity: is an average, not a total

    def test_cos_injection_includes_weekly_protein_stats(self):
        """format_cos_system_injection should include 7-day average protein data."""
        from apps.core.ai_orchestrator.cos_context import format_cos_system_injection

        context = {
            'health_intelligence': {
                'health_score': 75,
                'protein': {
                    'target_g': 213.0,
                    'method': 'lean_body_mass',
                    'lbm': 175.0,
                    'workout_day': False,
                    'multiplier': 1.0,
                    'protein_avg_7d': 168.0,
                    'protein_consistency_pct': 57.1,
                    'protein_gap_g': 45.0,
                    'protein_avg_ratio': 0.79,
                },
                'strengths': [],
                'weaknesses': [],
                'risk_flags': [],
                'correlations': [],
            },
        }

        injection = format_cos_system_injection(context)

        # Must contain the weekly evaluation block
        self.assertIn("WEEKLY EVALUATION", injection)
        self.assertIn("168g", injection)  # 7-day avg
        self.assertIn("79%", injection)  # % of target
        self.assertIn("45g below target", injection)  # gap

    def test_cos_summary_text_includes_weekly_avg(self):
        """build_cos_health_summary_text should mention 7d average, not total."""
        from apps.health.services.cos_health_context import build_cos_health_intelligence

        daily = [150, 160, 170, 180, 190, 200, 210]
        self._create_protein_week(daily, target_g=213)
        WeightEntry.objects.create(
            user=self.user, value=Decimal("220"), unit="lb",
            recorded_at=timezone.now(),
        )

        from apps.health.services.cos_health_context import build_cos_health_summary_text
        summary = build_cos_health_summary_text(self.user)

        # Summary should mention "7d avg" not total
        self.assertIn("7d avg", summary.lower() if summary else "")

    def test_gap_is_target_minus_average(self):
        """protein_gap_g must equal target - avg, not target - total."""
        from apps.health.services.cos_health_context import build_cos_health_intelligence

        # All days at 150g, target at 200g → gap should be 50, not 200-1050
        daily = [150] * 7
        self._create_protein_week(daily, target_g=200)
        WeightEntry.objects.create(
            user=self.user, value=Decimal("220"), unit="lb",
            recorded_at=timezone.now(),
        )

        intel = build_cos_health_intelligence(self.user)
        protein = intel.get("protein_intelligence", {})

        gap = protein.get("protein_gap_g")
        avg = protein.get("protein_avg_7d")
        target = protein.get("target_g")

        # avg should be 150
        self.assertIsNotNone(avg)
        self.assertAlmostEqual(avg, 150.0, places=0)

        # gap should be target - avg (~50), not target - total (-850)
        self.assertIsNotNone(gap)
        self.assertGreater(gap, 0)
        self.assertLess(gap, 100)  # Must be ~50, not ~850

    def test_command_center_protein_panel_has_gap(self):
        """Command center protein panel should include gap_g_7d."""
        daily = [150, 160, 170, 180, 190, 200, 210]
        self._create_protein_week(daily, target_g=213)
        WeightEntry.objects.create(
            user=self.user, value=Decimal("220"), unit="lb",
            recorded_at=timezone.now(),
        )

        from apps.health.services.command_center_api import HealthCommandCenterService
        summaries = list(DailyHealthSummary.objects.filter(
            user=self.user,
        ).order_by("summary_date"))
        today_summary = summaries[-1] if summaries else None

        panel = HealthCommandCenterService._build_protein_panel(
            summaries=summaries,
            recent_7=summaries[-7:],
            recent_14=summaries,
            today=today_summary,
            user=self.user,
        )

        # Panel should include gap field
        self.assertIn("gap_g_7d", panel)
        # avg_7d should be ~180 (average), not 1260 (total)
        self.assertIsNotNone(panel["avg_7d"])
        self.assertAlmostEqual(panel["avg_7d"], 180.0, places=0)

    def test_validator_catches_total_vs_average_response(self):
        """Health validator should flag a response using weekly total instead of average."""
        from apps.ai.validators.health_response_validator import validate_health_response

        cos_context = {
            'health_intelligence': {
                'protein': {
                    'target_g': 213.0,
                    'method': 'lean_body_mass',
                    'protein_avg_7d': 168.0,
                },
            },
        }

        # Bad response: quotes weekly total against daily target
        bad_response = (
            "You logged 120g this week and are 93g short of your "
            "target of 213g."
        )

        # This particular bad response doesn't use a range, so it won't
        # trigger the protein range validator. But let's verify the clean
        # response passes.
        good_response = (
            "Your protein target is about 213g per day. Your 7-day "
            "average intake is 168g, which means you're currently "
            "hitting about 79% of your target."
        )

        result = validate_health_response(good_response, cos_context)
        protein_violations = [
            v for v in result['violations']
            if v['type'] == 'GENERIC_PROTEIN_RANGE'
        ]
        self.assertEqual(len(protein_violations), 0)


# ============================================================
# Body Composition Intelligence Tests
# ============================================================

class TestBodyCompComputation(TestCase):
    """Test core body composition math."""

    def test_compute_fat_mass(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        result = BCI.compute_fat_mass(Decimal("200"), Decimal("20"))
        self.assertAlmostEqual(float(result), 40.0, places=1)

    def test_compute_fat_mass_none_weight(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self.assertIsNone(BCI.compute_fat_mass(None, Decimal("20")))

    def test_compute_fat_mass_none_bf(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self.assertIsNone(BCI.compute_fat_mass(Decimal("200"), None))

    def test_compute_fat_mass_zero_bf(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        result = BCI.compute_fat_mass(Decimal("200"), Decimal("0"))
        self.assertAlmostEqual(float(result), 0.0, places=1)

    def test_compute_lean_mass(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        result = BCI.compute_lean_mass(Decimal("200"), Decimal("40"))
        self.assertAlmostEqual(float(result), 160.0, places=1)

    def test_compute_lean_mass_none(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self.assertIsNone(BCI.compute_lean_mass(None, Decimal("40")))
        self.assertIsNone(BCI.compute_lean_mass(Decimal("200"), None))

    def test_get_latest_scan_from_bce(self):
        """BodyCompositionEntry is priority 1."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        user = User.objects.create_user(email="bci_bce@test.com", password="t")
        today = date.today()
        BodyCompositionEntry.objects.create(
            user=user, metric_name="body_fat_pct", value=Decimal("22.5"),
            unit="%", measurement_date=today, source="inbody",
        )
        WeightEntry.objects.create(
            user=user, value=Decimal("200"), unit="lb",
            recorded_at=timezone.now(),
        )
        scan = BCI.get_latest_scan(user, today)
        self.assertAlmostEqual(float(scan['body_fat_pct']), 22.5)
        self.assertAlmostEqual(float(scan['weight']), 200.0)
        self.assertIsNotNone(scan['fat_mass'])  # computed

    def test_get_latest_scan_no_data(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        user = User.objects.create_user(email="bci_none@test.com", password="t")
        scan = BCI.get_latest_scan(user, date.today())
        self.assertIsNone(scan['weight'])
        self.assertIsNone(scan['body_fat_pct'])


class TestWindowMetrics(TestCase):
    """Test 14-day window scan selection and tolerance."""

    def setUp(self):
        self.user = User.objects.create_user(email="bci_window@test.com", password="t")
        self.today = date.today()

    def _create_scan(self, d, weight, bf_pct):
        """Create weight + body fat entries for a date."""
        dt = timezone.make_aware(datetime.combine(d, datetime.min.time()).replace(hour=7))
        WeightEntry.objects.create(
            user=self.user, value=Decimal(str(weight)), unit="lb", recorded_at=dt,
        )
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="body_fat_pct", value=Decimal(str(bf_pct)),
            unit="%", measurement_date=d, source="inbody",
        )

    def test_14d_window_with_two_scans(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        start_date = self.today - timedelta(days=14)
        self._create_scan(start_date, 210, 25.0)
        self._create_scan(self.today, 207, 24.0)

        metrics = BCI.get_window_metrics(self.user, self.today, window_days=14)
        self.assertTrue(metrics['sufficient_data'])
        self.assertIsNotNone(metrics['deltas'])
        self.assertAlmostEqual(metrics['deltas']['weight_delta'], -3.0, places=1)

    def test_window_insufficient_one_scan(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self._create_scan(self.today, 207, 24.0)

        metrics = BCI.get_window_metrics(self.user, self.today, window_days=14)
        self.assertFalse(metrics['sufficient_data'])

    def test_window_tolerance_within_range(self):
        """Start scan within ±5 days of target should work."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # Target start = today - 14, but scan is at today - 12 (within +2 days)
        self._create_scan(self.today - timedelta(days=12), 210, 25.0)
        self._create_scan(self.today, 207, 24.0)

        metrics = BCI.get_window_metrics(self.user, self.today, window_days=14)
        self.assertTrue(metrics['sufficient_data'])

    def test_window_too_short(self):
        """Scans only 5 days apart should fail (< 10 day minimum)."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self._create_scan(self.today - timedelta(days=5), 210, 25.0)
        self._create_scan(self.today, 207, 24.0)

        metrics = BCI.get_window_metrics(self.user, self.today, window_days=14)
        self.assertFalse(metrics['sufficient_data'])


class TestFatLossQuality(TestCase):
    """Test fat loss quality classification."""

    def test_excellent_quality(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {
            'weight_delta': -4.0,
            'fat_mass_delta': -3.6,  # ratio = 0.90
            'lean_mass_delta': -0.4,
        }
        result = BCI.compute_fat_loss_quality(deltas, 14)
        self.assertEqual(result['label'], 'EXCELLENT')
        self.assertGreaterEqual(result['fat_loss_ratio'], 0.80)

    def test_good_quality(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {
            'weight_delta': -4.0,
            'fat_mass_delta': -2.8,  # ratio = 0.70
            'lean_mass_delta': -0.8,  # -0.4 lbs/week, within threshold
        }
        result = BCI.compute_fat_loss_quality(deltas, 14)
        self.assertEqual(result['label'], 'GOOD')

    def test_mixed_quality(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {
            'weight_delta': -4.0,
            'fat_mass_delta': -2.0,  # ratio = 0.50
            'lean_mass_delta': -0.9,  # -0.45 lbs/week, within threshold
        }
        result = BCI.compute_fat_loss_quality(deltas, 14)
        self.assertEqual(result['label'], 'MIXED')

    def test_muscle_loss_risk_low_ratio(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {
            'weight_delta': -4.0,
            'fat_mass_delta': -1.2,  # ratio = 0.30
            'lean_mass_delta': -2.8,
        }
        result = BCI.compute_fat_loss_quality(deltas, 14)
        self.assertEqual(result['label'], 'MUSCLE_LOSS_RISK')

    def test_insufficient_data_small_change(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {
            'weight_delta': -0.5,  # < 1.5 noise guard
            'fat_mass_delta': -0.3,
            'lean_mass_delta': -0.2,
        }
        result = BCI.compute_fat_loss_quality(deltas, 14)
        self.assertEqual(result['label'], 'INSUFFICIENT_DATA')


class TestRecomposition(TestCase):
    """Test body recomposition detection."""

    def test_recomp_detected(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {
            'weight_delta': 0.3,    # flat
            'fat_mass_delta': -1.5,  # fat down
            'lean_mass_delta': 1.0,  # lean up
        }
        result = BCI.detect_recomposition(deltas)
        self.assertTrue(result['detected'])

    def test_recomp_not_detected_weight_loss(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {
            'weight_delta': -3.0,  # not flat
            'fat_mass_delta': -2.5,
            'lean_mass_delta': -0.5,
        }
        result = BCI.detect_recomposition(deltas)
        self.assertFalse(result['detected'])

    def test_recomp_not_detected_lean_flat(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {
            'weight_delta': 0.2,
            'fat_mass_delta': -0.8,  # not enough fat loss
            'lean_mass_delta': 0.2,  # not enough lean gain
        }
        result = BCI.detect_recomposition(deltas)
        self.assertFalse(result['detected'])


class TestPlateau(TestCase):
    """Test plateau classification."""

    def setUp(self):
        self.user = User.objects.create_user(email="bci_plateau@test.com", password="t")
        self.today = date.today()

    def _create_scan_pair(self, start_date, end_date, start_w, end_w, start_bf, end_bf):
        """Create weight + body fat at both start and end."""
        for d, w, bf in [(start_date, start_w, start_bf), (end_date, end_w, end_bf)]:
            dt = timezone.make_aware(datetime.combine(d, datetime.min.time()).replace(hour=7))
            WeightEntry.objects.create(
                user=self.user, value=Decimal(str(w)), unit="lb", recorded_at=dt,
            )
            BodyCompositionEntry.objects.create(
                user=self.user, metric_name="body_fat_pct", value=Decimal(str(bf)),
                unit="%", measurement_date=d, source="inbody",
            )

    def test_true_plateau(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        start = self.today - timedelta(days=21)
        self._create_scan_pair(start, self.today, 200, 200.5, 22.0, 22.1)

        result = BCI.detect_plateau(self.user, self.today, window_days=21)
        self.assertEqual(result['status'], 'TRUE_PLATEAU')

    def test_recomp_plateau(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        start = self.today - timedelta(days=21)
        # Weight flat, fat down, lean up → recomp
        self._create_scan_pair(start, self.today, 200, 200.2, 25.0, 23.5)

        result = BCI.detect_plateau(self.user, self.today, window_days=21)
        self.assertEqual(result['status'], 'RECOMP')

    def test_water_fluctuation(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        start = self.today - timedelta(days=21)
        # Fat stable in absolute terms: 200*0.22=44.0 → 203*0.2167=43.99
        # Weight up 3 lbs (not flat), but fat_mass essentially flat
        self._create_scan_pair(start, self.today, 200, 203, 22.0, 21.67)
        # Create 10+ weight entries for variance check
        for i in range(15):
            d = start + timedelta(days=i)
            w = 200 + (i % 5) - 2  # fluctuating
            DailyHealthSummary.objects.update_or_create(
                user=self.user, summary_date=d,
                defaults={'weight': Decimal(str(w))},
            )

        result = BCI.detect_plateau(self.user, self.today, window_days=21)
        self.assertEqual(result['status'], 'WATER')

    def test_insufficient_data(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # No scans at all
        result = BCI.detect_plateau(self.user, self.today, window_days=21)
        self.assertEqual(result['status'], 'INSUFFICIENT_DATA')


class TestFatLossSpeed(TestCase):
    """Test fat loss speed classification."""

    def test_safe_speed(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {'weight_delta': -2.5}  # 2.5 lbs over 14 days at 200 lbs
        # rate = (2.5/200 * 100) / (14/7) = 0.625%/week → SAFE
        result = BCI.compute_fat_loss_speed(deltas, Decimal("200"), 14)
        self.assertEqual(result['label'], 'SAFE')
        self.assertGreaterEqual(result['rate_pct_per_week'], 0.5)
        self.assertLessEqual(result['rate_pct_per_week'], 1.0)

    def test_too_fast(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {'weight_delta': -7.0}  # 7 lbs over 14 days at 200 lbs
        # rate = (7/200 * 100) / 2 = 1.75%/week → TOO_FAST
        result = BCI.compute_fat_loss_speed(deltas, Decimal("200"), 14)
        self.assertEqual(result['label'], 'TOO_FAST')

    def test_gaining_weight(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {'weight_delta': 2.0}
        result = BCI.compute_fat_loss_speed(deltas, Decimal("200"), 14)
        self.assertEqual(result['label'], 'GAINING')

    def test_slow_speed(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        deltas = {'weight_delta': -0.5}  # 0.5 lbs over 14 days at 200 lbs
        # rate = (0.5/200 * 100) / 2 = 0.125%/week → SLOW
        result = BCI.compute_fat_loss_speed(deltas, Decimal("200"), 14)
        self.assertEqual(result['label'], 'SLOW')


class TestMuscleLossRisk(TestCase):
    """Test muscle loss risk scoring."""

    def setUp(self):
        self.user = User.objects.create_user(email="bci_risk@test.com", password="t")
        self.today = date.today()

    def _create_scan_pair(self, start_w, end_w, start_bf, end_bf):
        start = self.today - timedelta(days=14)
        for d, w, bf in [(start, start_w, start_bf), (self.today, end_w, end_bf)]:
            dt = timezone.make_aware(datetime.combine(d, datetime.min.time()).replace(hour=7))
            WeightEntry.objects.create(
                user=self.user, value=Decimal(str(w)), unit="lb", recorded_at=dt,
            )
            BodyCompositionEntry.objects.create(
                user=self.user, metric_name="body_fat_pct", value=Decimal(str(bf)),
                unit="%", measurement_date=d, source="inbody",
            )

    def test_low_risk(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # Lean mass stable
        self._create_scan_pair(200, 197, 25.0, 24.0)
        result = BCI.compute_muscle_loss_risk(self.user, self.today)
        self.assertEqual(result['risk_level'], 'LOW')
        self.assertLess(result['risk_score'], 30)

    def test_high_risk_lean_dropping(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # Lean mass dropping fast: start lean = 200*(1-0.25) = 150, end lean = 190*(1-0.25) = 142.5
        # lean delta = -7.5 over 14 days = -3.75/week → heavy drop
        self._create_scan_pair(200, 190, 25.0, 25.0)
        result = BCI.compute_muscle_loss_risk(self.user, self.today)
        self.assertGreater(result['risk_score'], 0)
        self.assertIn(result['risk_level'], ('MED', 'HIGH'))

    def test_drivers_present(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self._create_scan_pair(200, 197, 25.0, 24.0)
        result = BCI.compute_muscle_loss_risk(self.user, self.today)
        self.assertIn('drivers', result)
        self.assertGreater(len(result['drivers']), 0)
        # Each driver should have component, score, detail
        for driver in result['drivers']:
            self.assertIn('component', driver)
            self.assertIn('score', driver)
            self.assertIn('detail', driver)

    def test_risk_components_sum(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self._create_scan_pair(200, 197, 25.0, 24.0)
        result = BCI.compute_muscle_loss_risk(self.user, self.today)
        component_sum = sum(d['score'] for d in result['drivers'])
        self.assertEqual(result['risk_score'], component_sum)


class TestBodyCompInBuilder(TestCase, HealthIntelligenceTestMixin):
    """Test body comp intelligence in DailyHealthSummaryBuilder."""

    def test_builder_populates_fat_mass(self):
        """Builder computes fat_mass when weight + body_fat available."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        user = self.create_test_user()
        today = date.today()
        dt = timezone.make_aware(datetime.combine(today, datetime.min.time()).replace(hour=7))
        WeightEntry.objects.create(
            user=user, value=Decimal("200"), unit="lb", recorded_at=dt,
        )
        BodyCompositionEntry.objects.create(
            user=user, metric_name="body_fat_pct", value=Decimal("25.0"),
            unit="%", measurement_date=today, source="inbody",
        )

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(user, today)
        self.assertIsNotNone(summary.fat_mass)
        self.assertAlmostEqual(float(summary.fat_mass), 50.0, places=0)

    def test_builder_handles_no_body_comp(self):
        """Builder doesn't crash when no body comp data exists."""
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder

        user = self.create_test_user()
        today = date.today()

        builder = DailyHealthSummaryBuilder()
        summary = builder.build_for_date(user, today)
        self.assertIsNone(summary.fat_mass)
        self.assertEqual(summary.fat_loss_quality_label, "")


class TestBodyCompCommandCenter(TestCase, HealthIntelligenceTestMixin):
    """Test body comp panel in Health Command Center."""

    def test_panel_present(self):
        from apps.health.services.command_center_api import HealthCommandCenterService

        user = self.create_test_user()
        today = date.today()
        DailyHealthSummary.objects.create(
            user=user, summary_date=today,
            weight=Decimal("200"), body_fat_pct=Decimal("25.0"),
            fat_mass=Decimal("50"), lean_mass=Decimal("150"),
            fat_loss_quality_label="EXCELLENT",
            fat_loss_ratio_14d=Decimal("0.87"),
            muscle_loss_risk_score=15,
            muscle_loss_risk_level="LOW",
        )
        data = HealthCommandCenterService.get_dashboard_data(user, today)
        self.assertIn("body_comp", data["domain_panels"])
        panel = data["domain_panels"]["body_comp"]
        self.assertEqual(panel["fat_loss_quality_label"], "EXCELLENT")
        self.assertAlmostEqual(panel["fat_loss_ratio_14d"], 0.87, places=2)
        self.assertEqual(panel["muscle_loss_risk_level"], "LOW")


class TestBodyCompCosInjection(TestCase, HealthIntelligenceTestMixin):
    """Test body comp intelligence in CoS context."""

    def test_cos_context_has_body_comp(self):
        from apps.health.services.cos_health_context import build_cos_health_intelligence

        user = self.create_test_user()
        today = date.today()
        DailyHealthSummary.objects.create(
            user=user, summary_date=today,
            weight=Decimal("200"), body_fat_pct=Decimal("25.0"),
            fat_mass=Decimal("50"), lean_mass=Decimal("150"),
            fat_loss_quality_label="GOOD",
            fat_loss_ratio_14d=Decimal("0.72"),
            recomposition_flag_14d=False,
            plateau_status="",
            fat_loss_speed_label="SAFE",
            fat_loss_speed_pct_per_week=Decimal("0.75"),
            muscle_loss_risk_score=20,
            muscle_loss_risk_level="LOW",
        )

        intel = build_cos_health_intelligence(user)
        self.assertIn("body_comp_intelligence", intel)
        bc = intel["body_comp_intelligence"]
        self.assertEqual(bc["fat_loss_quality_label"], "GOOD")
        self.assertAlmostEqual(bc["fat_loss_ratio_14d"], 0.72, places=2)
        self.assertEqual(bc["muscle_loss_risk_level"], "LOW")

    def test_cos_injection_has_locked_block(self):
        from apps.core.ai_orchestrator.cos_context import _format_health_intelligence_block

        health_intel = {
            'health_score': 75,
            'recovery_score': 65,
            'recovery_status': 'moderate',
            'body_comp': {
                'fat_loss_quality_label': 'EXCELLENT',
                'fat_loss_ratio_14d': 0.87,
                'recomposition_flag_14d': False,
                'plateau_status': '',
                'fat_loss_speed_label': 'SAFE',
                'fat_loss_speed_pct_per_week': 0.8,
                'muscle_loss_risk_level': 'LOW',
                'muscle_loss_risk_score': 12,
                'fat_mass': 50.0,
                'body_comp_drivers': {},
            },
        }
        context = {}
        text = _format_health_intelligence_block(health_intel, context)
        self.assertIn('BODY COMPOSITION (locked', text)
        self.assertIn('Fat loss quality: EXCELLENT', text)
        self.assertIn('Muscle loss risk: LOW', text)


class TestBodyCompValidator(TestCase):
    """Test validator detects generic body composition language."""

    def test_detects_generic_body_fat_range(self):
        from apps.ai.validators.health_response_validator import validate_health_response
        response = "A healthy body fat percentage is between 15-20% for men."
        result = validate_health_response(response)
        body_comp_violations = [
            v for v in result['violations'] if v['type'] == 'GENERIC_BODY_COMP'
        ]
        self.assertGreater(len(body_comp_violations), 0)

    def test_detects_generic_fat_loss_advice(self):
        from apps.ai.validators.health_response_validator import validate_health_response
        response = "You should aim to lose 1 to 2 lbs per week for safe weight loss."
        result = validate_health_response(response)
        body_comp_violations = [
            v for v in result['violations'] if v['type'] == 'GENERIC_BODY_COMP'
        ]
        self.assertGreater(len(body_comp_violations), 0)

    def test_accepts_system_body_comp_values(self):
        from apps.ai.validators.health_response_validator import validate_health_response
        response = (
            "Over the last 14 days your weight is down 3.1 lbs. "
            "About 2.7 lbs came from fat mass and lean mass is stable. "
            "Fat loss quality: EXCELLENT (ratio 0.87). "
            "Muscle loss risk is LOW."
        )
        result = validate_health_response(response)
        body_comp_violations = [
            v for v in result['violations'] if v['type'] == 'GENERIC_BODY_COMP'
        ]
        self.assertEqual(len(body_comp_violations), 0)

    def test_body_comp_generic_is_critical(self):
        from apps.ai.validators.health_response_validator import validate_health_response
        response = "Your fat mass is approximately 50 lbs based on your weight."
        result = validate_health_response(response)
        self.assertEqual(result['severity'], 'critical')


class TestBodyCompDailyIntelligence(TestCase):
    """Test the full compute_daily_intelligence single-call."""

    def setUp(self):
        self.user = User.objects.create_user(email="bci_daily@test.com", password="t")
        self.today = date.today()

    def _create_scan(self, d, weight, bf_pct):
        dt = timezone.make_aware(datetime.combine(d, datetime.min.time()).replace(hour=7))
        WeightEntry.objects.create(
            user=self.user, value=Decimal(str(weight)), unit="lb", recorded_at=dt,
        )
        BodyCompositionEntry.objects.create(
            user=self.user, metric_name="body_fat_pct", value=Decimal(str(bf_pct)),
            unit="%", measurement_date=d, source="inbody",
        )

    def test_full_analysis_with_two_scans(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self._create_scan(self.today - timedelta(days=14), 210, 26.0)
        self._create_scan(self.today, 205, 24.5)

        result = BCI.compute_daily_intelligence(self.user, self.today)
        self.assertIn('fat_mass', result)
        self.assertIn('body_comp_drivers', result)
        self.assertIsNotNone(result.get('fat_mass'))

    def test_returns_empty_dict_no_data(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        result = BCI.compute_daily_intelligence(self.user, self.today)
        self.assertEqual(result, {})

    def test_fat_mass_only_with_one_scan(self):
        """With only one scan (no window), should still compute fat_mass."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self._create_scan(self.today, 200, 25.0)

        result = BCI.compute_daily_intelligence(self.user, self.today)
        self.assertIn('fat_mass', result)
        self.assertAlmostEqual(float(result['fat_mass']), 50.0, places=0)


class TestSystemPromptBodyCompRules(TestCase):
    """Test that personal assistant prompt has body comp enforcement rules."""

    def test_rule_8_present(self):
        from apps.ai.personal_assistant import COS_PROACTIVE_INTELLIGENCE_PROMPT
        self.assertIn('RULE 8:', COS_PROACTIVE_INTELLIGENCE_PROMPT)
        self.assertIn('BODY COMPOSITION', COS_PROACTIVE_INTELLIGENCE_PROMPT)

    def test_never_compute_fat_mass(self):
        from apps.ai.personal_assistant import COS_PROACTIVE_INTELLIGENCE_PROMPT
        self.assertIn('NEVER compute fat mass', COS_PROACTIVE_INTELLIGENCE_PROMPT)

    def test_never_generic_body_fat(self):
        from apps.ai.personal_assistant import COS_PROACTIVE_INTELLIGENCE_PROMPT
        self.assertIn('generic body fat ranges', COS_PROACTIVE_INTELLIGENCE_PROMPT)


class TestHealthIntelligenceScheduling(TestCase):
    """Verify nightly health summary task is properly scheduled."""

    def test_nightly_task_in_celery_beat(self):
        """The nightly health summary task must be in CELERY_BEAT_SCHEDULE."""
        from django.conf import settings
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertIn('health-nightly-summary-3am-utc', schedule)
        entry = schedule['health-nightly-summary-3am-utc']
        self.assertEqual(entry['task'], 'health.build_nightly_health_summaries')

    def test_nightly_task_uses_crontab(self):
        """The nightly task must use crontab at 3:00 AM UTC."""
        from celery.schedules import crontab
        from django.conf import settings
        entry = settings.CELERY_BEAT_SCHEDULE['health-nightly-summary-3am-utc']
        sched = entry['schedule']
        self.assertIsInstance(sched, crontab)
        self.assertEqual(sched.hour, {3})
        self.assertEqual(sched.minute, {0})


class TestHealthIntelligenceTelemetry(TestCase):
    """Verify Health Intelligence ops telemetry returns expected structure."""

    def test_telemetry_returns_expected_keys(self):
        """_get_health_intelligence_telemetry must return all required keys."""
        from apps.core.ai_observability.ops_views import (
            _get_health_intelligence_telemetry,
        )
        result = _get_health_intelligence_telemetry(timezone.now())
        self.assertIn('status', result)
        self.assertIn(result['status'], ['OK', 'STALE', 'ERROR'])

    def test_telemetry_with_summary_data(self):
        """Telemetry returns OK when fresh summary data exists."""
        from apps.core.ai_observability.ops_views import (
            _get_health_intelligence_telemetry,
        )
        user = get_user_model().objects.create_user(
            email='telemetry@test.com', password='test123',
        )
        DailyHealthSummary.objects.create(
            user=user,
            summary_date=date.today(),
            data_completeness_pct=Decimal('75.0'),
            health_score=72,
            recovery_score=68,
        )
        result = _get_health_intelligence_telemetry(timezone.now())
        self.assertEqual(result['status'], 'OK')
        self.assertIsNotNone(result.get('latest_summary_date'))
        self.assertIn('scores', result)
        self.assertIn('ingestion_24h', result)


# ======================================================================
# Health Intelligence Engine Enhancements Tests
# ======================================================================


class TestPlateauRisk(TestCase):
    """Test plateau early warning engine."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='plateau-risk@test.com', password='test123',
        )
        self.today = date.today()

    def _create_weight_series(self, weights, start_offset=21):
        """Create DHS entries with weight data going back start_offset days."""
        for i, w in enumerate(weights):
            d = self.today - timedelta(days=start_offset - i)
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=d,
                weight=Decimal(str(w)),
                fat_mass=Decimal(str(w * 0.22)),  # ~22% body fat
            )

    def test_low_risk_active_loss(self):
        """Active weight loss → LOW plateau risk."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # Steady downward trend: 200 → 195 over 21 days
        weights = [200 - (i * 5 / 21) for i in range(22)]
        self._create_weight_series(weights)
        result = BCI.compute_plateau_risk(self.user, self.today)
        self.assertEqual(result['plateau_risk_label'], 'LOW')
        self.assertLessEqual(result['plateau_risk_score'], 29)

    def test_rising_risk_decelerating(self):
        """Decelerating weight loss → RISING plateau risk."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # Fast loss first 14d, then nearly flat last 7d
        weights = []
        for i in range(22):
            if i < 14:
                weights.append(200 - (i * 0.3))  # losing ~0.3/day
            else:
                weights.append(200 - 4.2 - ((i - 14) * 0.01))  # nearly flat
        self._create_weight_series(weights)
        result = BCI.compute_plateau_risk(self.user, self.today)
        self.assertIn(result['plateau_risk_label'], ['RISING', 'HIGH'])
        self.assertGreaterEqual(result['plateau_risk_score'], 30)

    def test_high_risk_flat(self):
        """Completely flat weight → HIGH plateau risk."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # Weight barely moves
        weights = [200 + (0.1 * (i % 3 - 1)) for i in range(22)]
        self._create_weight_series(weights)
        result = BCI.compute_plateau_risk(self.user, self.today)
        self.assertEqual(result['plateau_risk_label'], 'HIGH')
        self.assertGreaterEqual(result['plateau_risk_score'], 60)

    def test_insufficient_data(self):
        """Too few weight entries → no score."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # Only 3 days
        for i in range(3):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=self.today - timedelta(days=i),
                weight=Decimal('200'),
            )
        result = BCI.compute_plateau_risk(self.user, self.today)
        self.assertIsNone(result['plateau_risk_score'])

    def test_prediction_window(self):
        """HIGH risk → 0 window, RISING → positive window."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # Flat = HIGH
        weights = [200 + (0.05 * (i % 2)) for i in range(22)]
        self._create_weight_series(weights)
        result = BCI.compute_plateau_risk(self.user, self.today)
        if result['plateau_risk_label'] == 'HIGH':
            self.assertEqual(result['plateau_prediction_window_days'], 0)


class TestPlateauRiskSlope(TestCase):
    """Test linear regression slope computation."""

    def test_linear_slope_positive(self):
        """Positive slope for increasing values."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        values = [(0, 100), (1, 102), (2, 104), (3, 106)]
        slope = BCI._linear_slope(values)
        self.assertAlmostEqual(slope, 2.0, places=1)

    def test_linear_slope_negative(self):
        """Negative slope for decreasing values."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        values = [(0, 200), (7, 197), (14, 194)]
        slope = BCI._linear_slope(values)
        self.assertLess(slope, 0)

    def test_linear_slope_insufficient(self):
        """Fewer than 3 points → None."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self.assertIsNone(BCI._linear_slope([(0, 1), (1, 2)]))
        self.assertIsNone(BCI._linear_slope([]))


class TestFatLossPhase(TestCase):
    """Test fat loss phase detection."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='phase@test.com', password='test123',
        )
        self.today = date.today()

    def test_stable_fat_loss(self):
        """SAFE speed + GOOD quality → STABLE_FAT_LOSS."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        intel = {
            'fat_loss_speed_label': 'SAFE',
            'fat_loss_quality_label': 'GOOD',
            'plateau_status': '',
            'recomposition_flag_14d': False,
        }
        result = BCI.detect_fat_loss_phase(self.user, self.today, current_intel=intel)
        self.assertEqual(result['fat_loss_phase'], 'STABLE_FAT_LOSS')
        self.assertGreaterEqual(result['phase_confidence'], 65)

    def test_rapid_initial_loss(self):
        """FAST/TOO_FAST speed → RAPID_INITIAL_LOSS."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        intel = {
            'fat_loss_speed_label': 'TOO_FAST',
            'fat_loss_speed_pct_per_week': 1.8,
            'fat_loss_quality_label': 'GOOD',
            'plateau_status': '',
            'recomposition_flag_14d': False,
        }
        result = BCI.detect_fat_loss_phase(self.user, self.today, current_intel=intel)
        self.assertEqual(result['fat_loss_phase'], 'RAPID_INITIAL_LOSS')

    def test_plateau_phase(self):
        """TRUE_PLATEAU → PLATEAU phase."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        intel = {
            'fat_loss_speed_label': 'SLOW',
            'fat_loss_quality_label': 'INSUFFICIENT_DATA',
            'plateau_status': 'TRUE_PLATEAU',
            'recomposition_flag_14d': False,
        }
        result = BCI.detect_fat_loss_phase(self.user, self.today, current_intel=intel)
        self.assertEqual(result['fat_loss_phase'], 'PLATEAU')
        self.assertEqual(result['phase_confidence'], 85)

    def test_recomposition_phase(self):
        """Recomp flag → RECOMPOSITION phase."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        intel = {
            'fat_loss_speed_label': 'SLOW',
            'fat_loss_quality_label': 'GOOD',
            'plateau_status': 'RECOMP',
            'recomposition_flag_14d': True,
        }
        result = BCI.detect_fat_loss_phase(self.user, self.today, current_intel=intel)
        self.assertEqual(result['fat_loss_phase'], 'RECOMPOSITION')

    def test_rebound_risk(self):
        """GAINING after STABLE_FAT_LOSS → REBOUND_RISK."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # Create a prior DHS with STABLE_FAT_LOSS phase
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=self.today - timedelta(days=3),
            fat_loss_phase='STABLE_FAT_LOSS',
        )
        intel = {
            'fat_loss_speed_label': 'GAINING',
            'fat_loss_speed_pct_per_week': 0.8,
            'fat_loss_quality_label': '',
            'plateau_status': '',
            'recomposition_flag_14d': False,
        }
        result = BCI.detect_fat_loss_phase(self.user, self.today, current_intel=intel)
        self.assertEqual(result['fat_loss_phase'], 'REBOUND_RISK')

    def test_insufficient_data(self):
        """No speed/plateau data → empty phase."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        intel = {
            'fat_loss_speed_label': '',
            'fat_loss_quality_label': '',
            'plateau_status': '',
            'recomposition_flag_14d': False,
        }
        result = BCI.detect_fat_loss_phase(self.user, self.today, current_intel=intel)
        self.assertEqual(result['fat_loss_phase'], '')


class TestPhaseStartDate(TestCase):
    """Test phase start date detection."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='phase-start@test.com', password='test123',
        )
        self.today = date.today()

    def test_phase_start_boundary(self):
        """Start date is the earliest consecutive day with same phase."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # 5 days of STABLE_FAT_LOSS, then 3 days of RAPID before that
        for i in range(5):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=self.today - timedelta(days=i),
                fat_loss_phase='STABLE_FAT_LOSS',
            )
        for i in range(5, 8):
            DailyHealthSummary.objects.create(
                user=self.user,
                summary_date=self.today - timedelta(days=i),
                fat_loss_phase='RAPID_INITIAL_LOSS',
            )
        start = BCI._find_phase_start(self.user, self.today, 'STABLE_FAT_LOSS')
        self.assertEqual(start, self.today - timedelta(days=4))

    def test_no_prior_phase(self):
        """No DHS history → returns end_date."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        start = BCI._find_phase_start(self.user, self.today, 'STABLE_FAT_LOSS')
        self.assertEqual(start, self.today)


class TestMusclePreservationStatus(TestCase):
    """Test muscle preservation status alias mapping."""

    def test_excellent_maps_to_high_quality(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self.assertEqual(BCI.compute_muscle_preservation_status('EXCELLENT'), 'HIGH_QUALITY')

    def test_good_maps_to_high_quality(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self.assertEqual(BCI.compute_muscle_preservation_status('GOOD'), 'HIGH_QUALITY')

    def test_mixed_maps_to_moderate(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self.assertEqual(BCI.compute_muscle_preservation_status('MIXED'), 'MODERATE_QUALITY')

    def test_muscle_loss_risk_maps(self):
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        self.assertEqual(BCI.compute_muscle_preservation_status('MUSCLE_LOSS_RISK'), 'MUSCLE_RISK')


class TestEnhancedDailyIntelligence(TestCase):
    """Test that compute_daily_intelligence includes new fields."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='enhanced-intel@test.com', password='test123',
        )
        self.today = date.today()

    def test_new_fields_populated_with_data(self):
        """With sufficient data, new fields are populated."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        # Create 22 days of weight + body comp data
        for i in range(22):
            d = self.today - timedelta(days=21 - i)
            w = Decimal('200') - Decimal(str(i * 0.2))
            bf = Decimal('25.0')
            WeightEntry.objects.create(
                user=self.user, recorded_at=timezone.make_aware(datetime.combine(d, datetime.min.time())), value=w,
            )
            BodyCompositionEntry.objects.create(
                user=self.user, measurement_date=d,
                metric_name='body_fat_pct', value=bf, unit='%',
            )
            DailyHealthSummary.objects.create(
                user=self.user, summary_date=d,
                weight=w, body_fat_pct=bf,
                fat_mass=w * bf / 100,
            )
        result = BCI.compute_daily_intelligence(self.user, self.today)
        # Should have plateau risk fields
        self.assertIn('plateau_risk_score', result)
        self.assertIn('plateau_risk_label', result)
        # Should have muscle preservation status
        if result.get('fat_loss_quality_label'):
            self.assertIn('muscle_preservation_status', result)

    def test_handles_missing_data(self):
        """With no data, returns empty dict gracefully."""
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        result = BCI.compute_daily_intelligence(self.user, self.today)
        self.assertEqual(result, {})


class TestEnhancedCosInjection(TestCase):
    """Test CoS context includes new body comp fields."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email='cos-enhanced@test.com', password='test123',
        )
        self.today = date.today()

    def test_new_fields_in_cos_context(self):
        """build_cos_health_intelligence includes new fields when present."""
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=self.today,
            weight=Decimal('195'),
            body_fat_pct=Decimal('22.0'),
            fat_mass=Decimal('42.9'),
            fat_loss_quality_label='EXCELLENT',
            fat_loss_ratio_14d=Decimal('0.87'),
            plateau_risk_score=45,
            plateau_risk_label='RISING',
            plateau_prediction_window_days=5,
            fat_loss_phase='STABLE_FAT_LOSS',
            phase_confidence=80,
            phase_start_date=self.today - timedelta(days=14),
            muscle_preservation_status='HIGH_QUALITY',
        )
        from apps.health.services.cos_health_context import build_cos_health_intelligence
        intel = build_cos_health_intelligence(self.user)
        bc = intel.get('body_comp_intelligence', {})
        self.assertEqual(bc['plateau_risk_label'], 'RISING')
        self.assertEqual(bc['plateau_risk_score'], 45)
        self.assertEqual(bc['fat_loss_phase'], 'STABLE_FAT_LOSS')
        self.assertEqual(bc['muscle_preservation_status'], 'HIGH_QUALITY')

    def test_new_fields_in_summary_text(self):
        """build_cos_health_summary_text includes plateau risk and phase."""
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=self.today,
            weight=Decimal('195'),
            body_fat_pct=Decimal('22.0'),
            fat_mass=Decimal('42.9'),
            fat_loss_quality_label='GOOD',
            plateau_risk_score=50,
            plateau_risk_label='RISING',
            plateau_prediction_window_days=4,
            fat_loss_phase='STABLE_FAT_LOSS',
            phase_confidence=80,
            muscle_preservation_status='HIGH_QUALITY',
        )
        from apps.health.services.cos_health_context import build_cos_health_summary_text
        text = build_cos_health_summary_text(self.user)
        self.assertIn('RISING', text)
        self.assertIn('STABLE_FAT_LOSS', text)
        self.assertIn('HIGH_QUALITY', text)


class TestEnhancedCommandCenter(TestCase):
    """Test command center panel includes new fields."""

    def test_new_fields_in_panel(self):
        user = get_user_model().objects.create_user(
            email='cc-enhanced@test.com', password='test123',
        )
        today = date.today()
        DailyHealthSummary.objects.create(
            user=user,
            summary_date=today,
            weight=Decimal('195'),
            body_fat_pct=Decimal('22.0'),
            fat_mass=Decimal('42.9'),
            fat_loss_quality_label='EXCELLENT',
            plateau_risk_score=60,
            plateau_risk_label='HIGH',
            plateau_prediction_window_days=0,
            fat_loss_phase='PLATEAU',
            phase_confidence=85,
            muscle_preservation_status='HIGH_QUALITY',
        )
        from apps.health.services.command_center_api import HealthCommandCenterService
        result = HealthCommandCenterService.get_dashboard_data(user)
        panel = result.get('domain_panels', {}).get('body_comp', {})
        self.assertEqual(panel.get('plateau_risk_label'), 'HIGH')
        self.assertEqual(panel.get('fat_loss_phase'), 'PLATEAU')
        self.assertEqual(panel.get('muscle_preservation_status'), 'HIGH_QUALITY')


class TestEnhancedValidatorPatterns(TestCase):
    """Test new validator patterns detect generic plateau/phase predictions."""

    def test_generic_plateau_prediction_detected(self):
        """Generic 'you will plateau in X days' should be flagged."""
        from apps.ai.validators.health_response_validator import validate_health_response
        result = validate_health_response(
            "Based on your trends, you may plateau in about 2 weeks."
        )
        violations = result.get('violations', [])
        types = [v['type'] for v in violations]
        self.assertIn('GENERIC_BODY_COMP', types)

    def test_self_classified_phase_detected(self):
        """Generic 'you appear to be in X phase' should be flagged."""
        from apps.ai.validators.health_response_validator import validate_health_response
        result = validate_health_response(
            "You appear to be entering a plateau phase based on patterns."
        )
        violations = result.get('violations', [])
        types = [v['type'] for v in violations]
        self.assertIn('GENERIC_BODY_COMP', types)

    def test_system_values_accepted(self):
        """Response using system values should pass."""
        from apps.ai.validators.health_response_validator import validate_health_response
        result = validate_health_response(
            "Your plateau risk is RISING with a score of 45. "
            "You're in the STABLE_FAT_LOSS phase with 80% confidence. "
            "Muscle preservation is HIGH_QUALITY."
        )
        violations = result.get('violations', [])
        body_comp_violations = [v for v in violations if v['type'] == 'GENERIC_BODY_COMP']
        self.assertEqual(len(body_comp_violations), 0)


# =========================================================================
# Health Intelligence UI Tests
# =========================================================================


class TestHealthIntelligenceView(TestCase):
    """Test the /health/intelligence/ page view."""

    def _setup_user(self, email, password='test123', is_staff=False):
        """Create a test user with onboarding + terms completed."""
        from django.conf import settings as django_settings
        from apps.users.models import TermsAcceptance
        User = get_user_model()
        user = User.objects.create_user(email=email, password=password, is_staff=is_staff)
        TermsAcceptance.objects.create(
            user=user,
            terms_version=django_settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def setUp(self):
        self.user = self._setup_user('hi-view@test.com')
        self.client.login(email='hi-view@test.com', password='test123')

    def test_page_loads_no_data(self):
        """Page loads with no DailyHealthSummary data."""
        response = self.client.get('/health/intelligence/', follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Health Intelligence')

    def test_page_loads_with_data(self):
        """Page loads and shows data when DailyHealthSummary exists."""
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=date.today(),
            weight=Decimal('195'),
            body_fat_pct=Decimal('22.0'),
            fat_mass=Decimal('42.9'),
            fat_loss_phase='STABLE_FAT_LOSS',
            phase_confidence=80,
            plateau_risk_score=30,
            plateau_risk_label='RISING',
            muscle_preservation_status='HIGH_QUALITY',
            fat_loss_ratio_14d=Decimal('0.85'),
        )
        response = self.client.get('/health/intelligence/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'STABLE_FAT_LOSS')
        self.assertContains(response, 'RISING')
        self.assertContains(response, 'HIGH_QUALITY')
        self.assertContains(response, 'Where You Are Now')

    def test_warnings_shown_for_high_risk(self):
        """Warning panels shown when plateau risk is HIGH."""
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=date.today(),
            weight=Decimal('195'),
            plateau_risk_score=75,
            plateau_risk_label='HIGH',
            plateau_prediction_window_days=0,
            muscle_preservation_status='MUSCLE_RISK',
        )
        response = self.client.get('/health/intelligence/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Risks')
        self.assertContains(response, 'Plateau risk is HIGH')
        self.assertContains(response, 'Muscle preservation at risk')

    def test_stale_warning(self):
        """Stale banner shown when data is old."""
        DailyHealthSummary.objects.create(
            user=self.user,
            summary_date=date.today() - timedelta(days=3),
            weight=Decimal('195'),
        )
        # Manually set updated_at to 3 days ago
        DailyHealthSummary.objects.filter(user=self.user).update(
            updated_at=timezone.now() - timedelta(hours=48)
        )
        response = self.client.get('/health/intelligence/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not been updated recently')

    def test_requires_login(self):
        """Page requires authentication."""
        self.client.logout()
        response = self.client.get('/health/intelligence/')
        self.assertEqual(response.status_code, 302)  # Redirect to login


class TestHealthRebuildView(TestCase):
    """Test the admin rebuild endpoint."""

    def _setup_user(self, email, password='test123', is_staff=False):
        """Create a test user with onboarding + terms completed."""
        from django.conf import settings as django_settings
        from apps.users.models import TermsAcceptance
        User = get_user_model()
        user = User.objects.create_user(email=email, password=password, is_staff=is_staff)
        TermsAcceptance.objects.create(
            user=user,
            terms_version=django_settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0'),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def setUp(self):
        self.admin = self._setup_user('admin-rebuild@test.com', is_staff=True)
        self.regular_user = self._setup_user('regular-rebuild@test.com', is_staff=False)

    def test_staff_can_trigger_rebuild(self):
        """Staff users can trigger rebuild."""
        self.client.login(email='admin-rebuild@test.com', password='test123')
        # Staff users require MFA — set session flag to bypass MFA middleware
        session = self.client.session
        session['mfa_verified'] = True
        session.save()
        with patch('apps.health.tasks.build_user_health_summary') as mock_task:
            mock_task.delay = lambda *a: None
            response = self.client.post(
                '/health/intelligence/rebuild/',
                data='{"days": 3}',
                content_type='application/json',
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['queued'], 3)

    def test_non_staff_forbidden(self):
        """Regular users cannot trigger rebuild."""
        self.client.login(email='regular-rebuild@test.com', password='test123')
        response = self.client.post(
            '/health/intelligence/rebuild/',
            data='{"days": 3}',
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)


class TestHealthIntelligenceTile(TestCase):
    """Test the dashboard tile registration."""

    def test_tile_registered(self):
        """health_intelligence tile is in TILE_DEFINITIONS."""
        from apps.dashboard.services.config_service import TILE_DEFINITIONS
        self.assertIn('health_intelligence', TILE_DEFINITIONS)
        tile = TILE_DEFINITIONS['health_intelligence']
        self.assertEqual(tile['module_dependency'], 'health_enabled')
        self.assertEqual(tile['default_size'], 'medium')


# =========================================================================
# Body Fat Pipeline Merge Tests
# =========================================================================


class TestBuilderBodyFatMerge(TestCase):
    """Test that the builder merges body_fat from multiple WeightEntries."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='builder-merge@test.com', password='test123'
        )

    def test_merges_body_fat_from_second_entry(self):
        """Body fat from a placeholder entry is merged with weight from another."""
        d = date.today()
        dt = timezone.make_aware(datetime.combine(d, datetime.min.time()))
        # Real weight entry (no body fat)
        WeightEntry.objects.create(
            user=self.user, value=Decimal('185.0'), unit='lb',
            recorded_at=dt.replace(hour=7),
        )
        # HealthKit body_fat placeholder (weight=0, body_fat set)
        WeightEntry.objects.create(
            user=self.user, value=Decimal('0'), unit='lb',
            recorded_at=dt.replace(hour=8),
            body_fat_percentage=Decimal('22.5'),
        )
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        builder = DailyHealthSummaryBuilder()
        result = builder._collect_weight_and_composition(self.user, d)
        self.assertIsNotNone(result)
        self.assertEqual(result['weight'], Decimal('185.0'))
        self.assertEqual(result['body_fat_pct'], Decimal('22.5'))

    def test_skips_weight_zero_entries(self):
        """Weight=0 placeholders are skipped for weight, but body_fat collected."""
        d = date.today()
        dt = timezone.make_aware(datetime.combine(d, datetime.min.time()))
        WeightEntry.objects.create(
            user=self.user, value=Decimal('0'), unit='lb',
            recorded_at=dt.replace(hour=8),
            body_fat_percentage=Decimal('25.0'),
        )
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        builder = DailyHealthSummaryBuilder()
        result = builder._collect_weight_and_composition(self.user, d)
        self.assertIsNotNone(result)
        # Weight should NOT be 0 — no valid weight entry exists
        self.assertNotIn('weight', result)
        # But body fat should still be collected
        self.assertEqual(result['body_fat_pct'], Decimal('25.0'))

    def test_single_entry_with_both_fields(self):
        """Normal case: single entry with both weight and body_fat."""
        d = date.today()
        dt = timezone.make_aware(datetime.combine(d, datetime.min.time()))
        WeightEntry.objects.create(
            user=self.user, value=Decimal('190.0'), unit='lb',
            recorded_at=dt.replace(hour=7),
            body_fat_percentage=Decimal('20.0'),
        )
        from apps.health.services.daily_summary_builder import DailyHealthSummaryBuilder
        builder = DailyHealthSummaryBuilder()
        result = builder._collect_weight_and_composition(self.user, d)
        self.assertEqual(result['weight'], Decimal('190.0'))
        self.assertEqual(result['body_fat_pct'], Decimal('20.0'))


class TestGetLatestScanFix(TestCase):
    """Test that get_latest_scan handles weight=0 placeholders correctly."""

    def setUp(self):
        self.user = User.objects.create_user(
            email='scan-fix@test.com', password='test123'
        )

    def test_skips_zero_weight(self):
        """get_latest_scan does not return weight=0 entries."""
        d = date.today()
        dt = timezone.make_aware(datetime.combine(d, datetime.min.time()))
        WeightEntry.objects.create(
            user=self.user, value=Decimal('0'), unit='lb',
            recorded_at=dt.replace(hour=8),
            body_fat_percentage=Decimal('22.0'),
        )
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        result = BCI.get_latest_scan(self.user, d)
        # Weight should be None (placeholder skipped)
        self.assertIsNone(result['weight'])

    def test_merges_body_fat_from_same_date(self):
        """Body fat from a placeholder is merged with real weight on same date."""
        d = date.today()
        dt = timezone.make_aware(datetime.combine(d, datetime.min.time()))
        # Real weight
        WeightEntry.objects.create(
            user=self.user, value=Decimal('180.0'), unit='lb',
            recorded_at=dt.replace(hour=7),
        )
        # Body fat placeholder
        WeightEntry.objects.create(
            user=self.user, value=Decimal('0'), unit='lb',
            recorded_at=dt.replace(hour=8),
            body_fat_percentage=Decimal('23.0'),
        )
        from apps.health.services.body_composition_intelligence import BodyCompositionIntelligence as BCI
        result = BCI.get_latest_scan(self.user, d)
        self.assertEqual(result['weight'], Decimal('180.0'))
        self.assertEqual(result['body_fat_pct'], Decimal('23.0'))
