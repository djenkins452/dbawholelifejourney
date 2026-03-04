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
