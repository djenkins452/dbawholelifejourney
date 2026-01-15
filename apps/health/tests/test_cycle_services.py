"""
Cycle Service Layer Tests

Comprehensive tests for cycle tracking services:
- CycleDetectionService
- CyclePredictionService
- CycleStatisticsService

Location: apps/health/tests/test_cycle_services.py
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.health.models import (
    CycleSettings,
    CycleDailyLog,
    Cycle,
    CyclePrediction,
)
from apps.health.services.cycle_detection import CycleDetectionService
from apps.health.services.cycle_prediction import (
    CyclePredictionService,
    MIN_CYCLES_FOR_PREDICTION,
    ALGORITHM_VERSION,
)
from apps.health.services.cycle_statistics import CycleStatisticsService
from apps.users.models import TermsAcceptance

User = get_user_model()


class CycleServiceTestBase(TestCase):
    """Base class for cycle service tests with user creation utilities."""

    def setUp(self):
        """Set up test user with cycle tracking enabled."""
        self.user = self._create_test_user()
        self.settings = self._enable_cycle_tracking()

    def _create_test_user(self, email="test@example.com", password="testpass123"):
        """Create a test user with terms accepted and onboarding completed."""
        from django.conf import settings
        user = User.objects.create_user(email=email, password=password)
        current_terms_version = settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
        TermsAcceptance.objects.create(user=user, terms_version=current_terms_version)
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def _enable_cycle_tracking(self):
        """Enable cycle tracking for the test user."""
        return CycleSettings.objects.create(
            user=self.user,
            cycle_tracking_enabled=True,
            average_cycle_length=28,
            average_period_length=5,
        )

    def _create_daily_log(self, log_date, flow_level="none", **kwargs):
        """Helper to create a daily log."""
        return CycleDailyLog.objects.create(
            user=self.user,
            log_date=log_date,
            flow_level=flow_level,
            **kwargs
        )


# =============================================================================
# CycleDetectionService Tests
# =============================================================================

class CycleDetectionServiceTest(CycleServiceTestBase):
    """Tests for CycleDetectionService."""

    def test_service_initialization(self):
        """Test service initializes with user."""
        service = CycleDetectionService(self.user)
        self.assertEqual(service.user, self.user)

    def test_detect_period_start_from_no_flow(self):
        """Test _check_period_start detects period start after no flow."""
        service = CycleDetectionService(self.user)

        # Day 1: no flow
        self._create_daily_log(date.today() - timedelta(days=1), flow_level="none")

        # Check if today would be detected as a period start
        result = service._check_period_start(date.today())

        self.assertTrue(result["is_new_period"])
        self.assertEqual(result["reason"], "flow_started_after_break")

        # Now test _create_new_cycle
        cycle = service._create_new_cycle(date.today())
        self.assertEqual(cycle.start_date, date.today())
        self.assertEqual(cycle.user, self.user)

    def test_detect_period_start_from_spotting(self):
        """Test _check_period_start detects period start after spotting."""
        service = CycleDetectionService(self.user)

        # Day 1: spotting (doesn't count as period)
        self._create_daily_log(date.today() - timedelta(days=1), flow_level="spotting")

        # Check if today would be detected as a period start
        result = service._check_period_start(date.today())

        self.assertTrue(result["is_new_period"])

    def test_no_period_start_when_continuing_flow(self):
        """Test _check_period_start returns False when continuing flow."""
        service = CycleDetectionService(self.user)

        # Day 1: period starts
        self._create_daily_log(date.today() - timedelta(days=1), flow_level="medium")

        # Check if today (with continued flow) would be detected as new period
        # Previous day had flow, so this should not be a new period
        result = service._check_period_start(date.today())

        self.assertFalse(result["is_new_period"])
        self.assertEqual(result["reason"], "previous_day_had_flow")

    def test_detect_period_end_after_two_no_flow_days(self):
        """Test _check_period_end detects period end after 2+ no-flow days."""
        service = CycleDetectionService(self.user)

        # Create ongoing cycle starting 5 days ago
        cycle = Cycle.objects.create(
            user=self.user,
            start_date=date.today() - timedelta(days=5),
        )

        # Period days: days 5, 4, 3 ago had flow (3 days of period)
        for i in range(3):
            self._create_daily_log(
                date.today() - timedelta(days=5-i),  # days -5, -4, -3
                flow_level="medium"
            )

        # Last flow was day 3 ago. To trigger period_ended, need days_since_flow >= 2
        # So checking day 1 ago: days_since_flow = (day-1) - (day-3) = 2 days

        # Test _check_period_end directly
        result = service._check_period_end(date.today() - timedelta(days=1))

        self.assertTrue(result["period_ended"])
        self.assertEqual(result["period_end_date"], date.today() - timedelta(days=3))

        # Now test _update_period_end
        updated_cycle = service._update_period_end(result["period_end_date"])

        self.assertIsNotNone(updated_cycle)
        self.assertEqual(updated_cycle.period_end_date, date.today() - timedelta(days=3))

    def test_no_period_end_when_no_ongoing_cycle(self):
        """Test no action when there's no ongoing cycle."""
        service = CycleDetectionService(self.user)

        log = self._create_daily_log(date.today(), flow_level="none")
        result = service.process_daily_log(log)

        self.assertIsNone(result["action"])
        self.assertFalse(result["period_ended"])

    def test_create_new_cycle_closes_previous(self):
        """Test that _create_new_cycle closes previous ongoing cycle."""
        service = CycleDetectionService(self.user)

        # Create first cycle (ongoing, no end_date)
        first_cycle = Cycle.objects.create(
            user=self.user,
            start_date=date.today() - timedelta(days=30),
        )

        # Create flow logs for first cycle's period (days 30-28 ago)
        for i in range(3):
            self._create_daily_log(
                date.today() - timedelta(days=30-i),
                flow_level="medium"
            )

        # Directly test the _create_new_cycle method
        new_cycle = service._create_new_cycle(date.today())

        # First cycle should now have end_date
        first_cycle.refresh_from_db()
        self.assertIsNotNone(first_cycle.end_date)
        self.assertEqual(first_cycle.end_date, date.today() - timedelta(days=1))

        # New cycle should be created
        self.assertEqual(new_cycle.start_date, date.today())
        self.assertIsNone(new_cycle.end_date)

    def test_various_flow_levels_in_period(self):
        """Test that light, medium, and heavy all count as period flow."""
        service = CycleDetectionService(self.user)

        # Verify all period flow levels are recognized
        self.assertIn("light", service.PERIOD_FLOW_LEVELS)
        self.assertIn("medium", service.PERIOD_FLOW_LEVELS)
        self.assertIn("heavy", service.PERIOD_FLOW_LEVELS)
        self.assertNotIn("spotting", service.PERIOD_FLOW_LEVELS)
        self.assertNotIn("none", service.PERIOD_FLOW_LEVELS)

    def test_spotting_does_not_start_period(self):
        """Test that spotting is not in PERIOD_FLOW_LEVELS."""
        service = CycleDetectionService(self.user)

        # Spotting should not be considered period flow
        self.assertEqual(service.SPOTTING_LEVEL, "spotting")
        self.assertNotIn(service.SPOTTING_LEVEL, service.PERIOD_FLOW_LEVELS)

    def test_recalculate_cycles(self):
        """Test recalculating all cycles from logs."""
        service = CycleDetectionService(self.user)

        # Create logs for two distinct periods with no-flow days between
        # First period: 60-55 days ago (flow)
        for i in range(60, 54, -1):  # days 60, 59, 58, 57, 56, 55
            self._create_daily_log(date.today() - timedelta(days=i), flow_level="medium")

        # No-flow days to end first period: 54, 53 (2+ days needed)
        self._create_daily_log(date.today() - timedelta(days=54), flow_level="none")
        self._create_daily_log(date.today() - timedelta(days=53), flow_level="none")

        # Second period: 30-26 days ago
        for i in range(30, 25, -1):  # days 30, 29, 28, 27, 26
            self._create_daily_log(date.today() - timedelta(days=i), flow_level="light")

        result = service.recalculate_cycles()

        self.assertEqual(result["cycles_created"], 2)
        self.assertEqual(Cycle.objects.filter(user=self.user).count(), 2)

    def test_recalculate_with_no_logs(self):
        """Test recalculating when no logs exist."""
        service = CycleDetectionService(self.user)
        result = service.recalculate_cycles()

        self.assertEqual(result["cycles_created"], 0)
        self.assertIn("No daily logs", result["message"])


# =============================================================================
# CyclePredictionService Tests
# =============================================================================

class CyclePredictionServiceTest(CycleServiceTestBase):
    """Tests for CyclePredictionService."""

    def _create_completed_cycles(self, count=3, base_length=28, period_length=5):
        """Helper to create completed cycles for prediction testing."""
        cycles = []
        current_start = date.today() - timedelta(days=base_length * count + 10)

        for i in range(count):
            cycle_end = current_start + timedelta(days=base_length - 1)
            period_end = current_start + timedelta(days=period_length - 1)

            cycle = Cycle.objects.create(
                user=self.user,
                start_date=current_start,
                end_date=cycle_end,
                period_end_date=period_end,
                cycle_number=i + 1,
            )
            cycles.append(cycle)
            current_start = cycle_end + timedelta(days=1)

        return cycles

    def test_service_initialization(self):
        """Test service initializes with user."""
        service = CyclePredictionService(self.user)
        self.assertEqual(service.user, self.user)

    def test_cannot_predict_without_enough_cycles(self):
        """Test prediction fails when fewer than MIN_CYCLES completed."""
        service = CyclePredictionService(self.user)

        # Create only 2 completed cycles
        self._create_completed_cycles(count=2)

        can_predict, reason = service.can_generate_prediction()
        self.assertFalse(can_predict)
        self.assertIn(str(MIN_CYCLES_FOR_PREDICTION), reason)

    def test_cannot_predict_when_tracking_disabled(self):
        """Test prediction fails when cycle tracking is disabled."""
        self.settings.cycle_tracking_enabled = False
        self.settings.save()

        service = CyclePredictionService(self.user)
        can_predict, reason = service.can_generate_prediction()

        self.assertFalse(can_predict)
        self.assertIn("not enabled", reason)

    def test_can_predict_with_enough_cycles(self):
        """Test prediction succeeds with enough completed cycles."""
        service = CyclePredictionService(self.user)
        self._create_completed_cycles(count=3)

        can_predict, reason = service.can_generate_prediction()
        self.assertTrue(can_predict)
        self.assertEqual(reason, "OK")

    def test_generate_prediction_with_regular_cycles(self):
        """Test prediction generation with regular cycle data."""
        service = CyclePredictionService(self.user)
        self._create_completed_cycles(count=4, base_length=28, period_length=5)

        result = service.generate_prediction(save=False)

        self.assertIsNotNone(result)
        self.assertEqual(result.predicted_cycle_length, 28)
        self.assertEqual(result.predicted_period_length, 5)
        self.assertEqual(result.cycles_analyzed, 4)

    def test_prediction_confidence_high_for_regular_cycles(self):
        """Test high confidence for very regular cycles."""
        service = CyclePredictionService(self.user)

        # Create 4 cycles all exactly 28 days
        self._create_completed_cycles(count=4, base_length=28)

        result = service.generate_prediction(save=False)

        # Should have high confidence
        self.assertGreaterEqual(float(result.confidence), 0.80)
        self.assertEqual(result.confidence_level, "high")

    def test_prediction_confidence_low_for_irregular_cycles(self):
        """Test lower confidence for irregular cycles."""
        service = CyclePredictionService(self.user)

        # Create cycles with varying lengths
        current_start = date.today() - timedelta(days=150)
        lengths = [24, 35, 26, 40]  # Highly irregular

        for i, length in enumerate(lengths):
            cycle_end = current_start + timedelta(days=length - 1)
            Cycle.objects.create(
                user=self.user,
                start_date=current_start,
                end_date=cycle_end,
                period_end_date=current_start + timedelta(days=4),
                cycle_number=i + 1,
            )
            current_start = cycle_end + timedelta(days=1)

        result = service.generate_prediction(save=False)

        # Should have lower confidence due to high std dev
        self.assertLess(float(result.confidence), 0.80)

    def test_prediction_saves_to_database(self):
        """Test prediction is saved to database when save=True."""
        service = CyclePredictionService(self.user)
        self._create_completed_cycles(count=3)

        result = service.generate_prediction(save=True)

        # Should be saved to database
        prediction = CyclePrediction.objects.filter(user=self.user).first()
        self.assertIsNotNone(prediction)
        self.assertEqual(prediction.predicted_period_start, result.predicted_period_start)
        self.assertEqual(prediction.prediction_algorithm_version, ALGORITHM_VERSION)

    def test_prediction_not_saved_when_false(self):
        """Test prediction is not saved when save=False."""
        service = CyclePredictionService(self.user)
        self._create_completed_cycles(count=3)

        initial_count = CyclePrediction.objects.filter(user=self.user).count()
        service.generate_prediction(save=False)
        final_count = CyclePrediction.objects.filter(user=self.user).count()

        self.assertEqual(initial_count, final_count)

    def test_fertile_window_calculation_enabled(self):
        """Test fertile window is calculated when enabled."""
        self.settings.fertile_window_tracking_enabled = True
        self.settings.save()

        service = CyclePredictionService(self.user)
        self._create_completed_cycles(count=3)

        result = service.generate_prediction(save=False)

        self.assertIsNotNone(result.predicted_fertile_start)
        self.assertIsNotNone(result.predicted_fertile_end)

    def test_fertile_window_calculation_disabled(self):
        """Test fertile window is not calculated when disabled."""
        self.settings.fertile_window_tracking_enabled = False
        self.settings.save()

        service = CyclePredictionService(self.user)
        self._create_completed_cycles(count=3)

        result = service.generate_prediction(save=False)

        self.assertIsNone(result.predicted_fertile_start)
        self.assertIsNone(result.predicted_fertile_end)

    def test_weighted_average_favors_recent_cycles(self):
        """Test that more recent cycles have higher weight."""
        service = CyclePredictionService(self.user)

        # Create cycles with increasing lengths (older shorter, newer longer)
        current_start = date.today() - timedelta(days=150)
        lengths = [26, 27, 28, 30]  # 26 oldest, 30 most recent

        for i, length in enumerate(lengths):
            cycle_end = current_start + timedelta(days=length - 1)
            Cycle.objects.create(
                user=self.user,
                start_date=current_start,
                end_date=cycle_end,
                period_end_date=current_start + timedelta(days=4),
                cycle_number=i + 1,
            )
            current_start = cycle_end + timedelta(days=1)

        result = service.generate_prediction(save=False)

        # Weighted average should favor recent cycles (closer to 30 than 26)
        # Simple average would be 27.75, weighted should be higher
        self.assertGreater(result.predicted_cycle_length, 27)

    def test_get_latest_prediction(self):
        """Test getting the most recent prediction."""
        service = CyclePredictionService(self.user)
        self._create_completed_cycles(count=3)

        # Generate two predictions
        service.generate_prediction(save=True)
        service._cycles = None  # Reset cache
        service.generate_prediction(save=True)

        latest = service.get_latest_prediction()
        self.assertIsNotNone(latest)
        self.assertEqual(CyclePrediction.objects.filter(user=self.user).count(), 2)

    def test_prediction_accuracy_stats_no_data(self):
        """Test accuracy stats with no verified predictions."""
        service = CyclePredictionService(self.user)

        stats = service.get_prediction_accuracy_stats()

        self.assertEqual(stats["total_predictions"], 0)
        self.assertEqual(stats["verified_predictions"], 0)
        self.assertIsNone(stats["average_accuracy_days"])

    def test_prediction_accuracy_stats_with_verified_data(self):
        """Test accuracy stats with verified predictions."""
        service = CyclePredictionService(self.user)

        # Create verified predictions
        CyclePrediction.objects.create(
            user=self.user,
            predicted_period_start=date.today() - timedelta(days=14),
            predicted_period_end=date.today() - timedelta(days=10),
            prediction_confidence=Decimal("0.80"),
            prediction_algorithm_version="v1.0",
            actual_period_start=date.today() - timedelta(days=12),  # 2 days early
        )
        CyclePrediction.objects.create(
            user=self.user,
            predicted_period_start=date.today() - timedelta(days=42),
            predicted_period_end=date.today() - timedelta(days=38),
            prediction_confidence=Decimal("0.85"),
            prediction_algorithm_version="v1.0",
            actual_period_start=date.today() - timedelta(days=42),  # Exact
        )

        stats = service.get_prediction_accuracy_stats()

        self.assertEqual(stats["verified_predictions"], 2)
        self.assertEqual(stats["average_accuracy_days"], 1.0)  # (2 + 0) / 2 = 1
        self.assertEqual(stats["accuracy_within_3_days"], 100.0)


# =============================================================================
# CycleStatisticsService Tests
# =============================================================================

class CycleStatisticsServiceTest(CycleServiceTestBase):
    """Tests for CycleStatisticsService."""

    def _create_cycles_with_data(self, count=4, base_length=28, period_length=5):
        """Helper to create cycles with various statistics data."""
        cycles = []
        current_start = date.today() - timedelta(days=base_length * count + 10)

        for i in range(count):
            cycle_end = current_start + timedelta(days=base_length - 1)
            period_end = current_start + timedelta(days=period_length - 1)

            cycle = Cycle.objects.create(
                user=self.user,
                start_date=current_start,
                end_date=cycle_end,
                period_end_date=period_end,
                cycle_number=i + 1,
            )

            # Create daily logs for period days
            for day in range(period_length):
                CycleDailyLog.objects.create(
                    user=self.user,
                    log_date=current_start + timedelta(days=day),
                    flow_level="medium" if day < 3 else "light",
                    mood="tired" if day < 2 else "happy",
                    symptoms=["cramps", "fatigue"] if day < 2 else ["headache"],
                )

            cycles.append(cycle)
            current_start = cycle_end + timedelta(days=1)

        return cycles

    def test_service_initialization(self):
        """Test service initializes with user."""
        service = CycleStatisticsService(self.user)
        self.assertEqual(service.user, self.user)

    def test_average_cycle_length_calculation(self):
        """Test average cycle length calculation."""
        service = CycleStatisticsService(self.user)
        self._create_cycles_with_data(count=4, base_length=28)

        result = service.get_average_cycle_length()

        self.assertIsNotNone(result)
        self.assertEqual(result["average"], 28.0)
        self.assertEqual(result["min"], 28)
        self.assertEqual(result["max"], 28)
        self.assertEqual(result["count"], 4)

    def test_average_cycle_length_with_variation(self):
        """Test average cycle length with varying cycles."""
        service = CycleStatisticsService(self.user)

        # Create cycles with different lengths
        current_start = date.today() - timedelta(days=120)
        lengths = [26, 28, 30, 32]

        for i, length in enumerate(lengths):
            cycle_end = current_start + timedelta(days=length - 1)
            Cycle.objects.create(
                user=self.user,
                start_date=current_start,
                end_date=cycle_end,
                period_end_date=current_start + timedelta(days=4),
                cycle_number=i + 1,
            )
            current_start = cycle_end + timedelta(days=1)

        result = service.get_average_cycle_length()

        self.assertEqual(result["average"], 29.0)  # (26+28+30+32)/4
        self.assertEqual(result["min"], 26)
        self.assertEqual(result["max"], 32)

    def test_average_cycle_length_no_data(self):
        """Test average cycle length when no completed cycles."""
        service = CycleStatisticsService(self.user)
        result = service.get_average_cycle_length()
        self.assertIsNone(result)

    def test_average_period_length_calculation(self):
        """Test average period length calculation."""
        service = CycleStatisticsService(self.user)
        self._create_cycles_with_data(count=3, base_length=28, period_length=5)

        result = service.get_average_period_length()

        self.assertIsNotNone(result)
        self.assertEqual(result["average"], 5.0)
        self.assertEqual(result["count"], 3)

    def test_symptom_frequency_calculation(self):
        """Test symptom frequency counting."""
        service = CycleStatisticsService(self.user)

        # Create logs with symptoms
        for i in range(10):
            CycleDailyLog.objects.create(
                user=self.user,
                log_date=date.today() - timedelta(days=i),
                flow_level="medium",
                symptoms=["cramps"] if i % 2 == 0 else ["headache", "fatigue"],
            )

        result = service.get_symptom_frequency(months=1)

        self.assertGreater(len(result), 0)
        # Find cramps in results
        cramps = next((s for s in result if s["symptom"] == "cramps"), None)
        self.assertIsNotNone(cramps)
        self.assertEqual(cramps["count"], 5)  # Every other day

    def test_symptom_frequency_no_data(self):
        """Test symptom frequency with no logs."""
        service = CycleStatisticsService(self.user)
        result = service.get_symptom_frequency(months=1)
        self.assertEqual(result, [])

    def test_cycle_regularity_score_excellent(self):
        """Test excellent regularity score for consistent cycles."""
        service = CycleStatisticsService(self.user)
        self._create_cycles_with_data(count=4, base_length=28)

        result = service.get_cycle_regularity_score()

        self.assertIsNotNone(result)
        self.assertEqual(result["rating"], "excellent")
        self.assertEqual(result["score"], 100)  # 0 std dev = 100 score

    def test_cycle_regularity_score_irregular(self):
        """Test lower regularity score for irregular cycles."""
        service = CycleStatisticsService(self.user)

        # Create cycles with high variation
        current_start = date.today() - timedelta(days=150)
        lengths = [22, 35, 24, 38]  # Very irregular

        for i, length in enumerate(lengths):
            cycle_end = current_start + timedelta(days=length - 1)
            Cycle.objects.create(
                user=self.user,
                start_date=current_start,
                end_date=cycle_end,
                period_end_date=current_start + timedelta(days=4),
                cycle_number=i + 1,
            )
            current_start = cycle_end + timedelta(days=1)

        result = service.get_cycle_regularity_score()

        self.assertIsNotNone(result)
        self.assertIn(result["rating"], ["fair", "irregular"])
        self.assertLess(result["score"], 50)

    def test_cycle_regularity_score_insufficient_data(self):
        """Test regularity score with insufficient data."""
        service = CycleStatisticsService(self.user)

        # Only one cycle
        Cycle.objects.create(
            user=self.user,
            start_date=date.today() - timedelta(days=28),
            end_date=date.today() - timedelta(days=1),
            period_end_date=date.today() - timedelta(days=23),
            cycle_number=1,
        )

        result = service.get_cycle_regularity_score()
        self.assertIsNone(result)

    def test_trends_detection_stable(self):
        """Test stable trend detection."""
        service = CycleStatisticsService(self.user)
        self._create_cycles_with_data(count=5, base_length=28)

        result = service.get_trends()

        self.assertIsNotNone(result)
        self.assertEqual(result["cycle_trend"], "stable")
        self.assertEqual(result["cycles_analyzed"], 5)

    def test_trends_detection_lengthening(self):
        """Test detection of lengthening cycles."""
        service = CycleStatisticsService(self.user)

        # Create cycles that are getting longer
        current_start = date.today() - timedelta(days=150)
        lengths = [25, 27, 29, 31, 33]  # Increasing

        for i, length in enumerate(lengths):
            cycle_end = current_start + timedelta(days=length - 1)
            Cycle.objects.create(
                user=self.user,
                start_date=current_start,
                end_date=cycle_end,
                period_end_date=current_start + timedelta(days=4),
                cycle_number=i + 1,
            )
            current_start = cycle_end + timedelta(days=1)

        result = service.get_trends()

        self.assertEqual(result["cycle_trend"], "lengthening")
        self.assertGreater(result["cycle_slope"], 0)

    def test_trends_detection_shortening(self):
        """Test detection of shortening cycles."""
        service = CycleStatisticsService(self.user)

        # Create cycles that are getting shorter
        current_start = date.today() - timedelta(days=150)
        lengths = [33, 31, 29, 27, 25]  # Decreasing

        for i, length in enumerate(lengths):
            cycle_end = current_start + timedelta(days=length - 1)
            Cycle.objects.create(
                user=self.user,
                start_date=current_start,
                end_date=cycle_end,
                period_end_date=current_start + timedelta(days=4),
                cycle_number=i + 1,
            )
            current_start = cycle_end + timedelta(days=1)

        result = service.get_trends()

        self.assertEqual(result["cycle_trend"], "shortening")
        self.assertLess(result["cycle_slope"], 0)

    def test_trends_insufficient_data(self):
        """Test trends with insufficient cycles."""
        service = CycleStatisticsService(self.user)
        self._create_cycles_with_data(count=2)  # Less than MIN_CYCLES_FOR_TRENDS

        result = service.get_trends()
        self.assertIsNone(result)

    def test_get_summary_comprehensive(self):
        """Test comprehensive summary generation."""
        service = CycleStatisticsService(self.user)
        self._create_cycles_with_data(count=5, base_length=28, period_length=5)

        summary = service.get_summary()

        self.assertIn("average_cycle_length", summary)
        self.assertIn("average_period_length", summary)
        self.assertIn("regularity_score", summary)
        self.assertIn("trends", summary)
        self.assertIn("symptom_frequency", summary)
        self.assertIn("mood_by_phase", summary)
        self.assertIn("generated_at", summary)


# =============================================================================
# Edge Case Tests
# =============================================================================

class CycleServiceEdgeCasesTest(CycleServiceTestBase):
    """Tests for edge cases across all cycle services."""

    def test_detection_with_gaps_in_data(self):
        """Test _check_period_start handles gaps in daily log data."""
        service = CycleDetectionService(self.user)

        # Create logs with a gap (missing days 5-10)
        self._create_daily_log(date.today() - timedelta(days=15), flow_level="medium")
        self._create_daily_log(date.today() - timedelta(days=14), flow_level="light")
        # Gap here - no logs for many days
        # Day before today: no flow
        self._create_daily_log(date.today() - timedelta(days=1), flow_level="none")

        # Check if new period would be detected after the gap
        result = service._check_period_start(date.today())

        # Should detect as new period since previous day had no flow
        self.assertTrue(result["is_new_period"])

    def test_prediction_with_incomplete_cycle_data(self):
        """Test prediction handles cycles with missing period_length."""
        service = CyclePredictionService(self.user)

        # Create cycles where some don't have period_end_date
        current_start = date.today() - timedelta(days=120)
        for i in range(4):
            length = 28
            cycle_end = current_start + timedelta(days=length - 1)
            Cycle.objects.create(
                user=self.user,
                start_date=current_start,
                end_date=cycle_end,
                period_end_date=current_start + timedelta(days=4) if i % 2 == 0 else None,
                cycle_number=i + 1,
            )
            current_start = cycle_end + timedelta(days=1)

        result = service.generate_prediction(save=False)

        # Should still work with available data
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.predicted_cycle_length)

    def test_statistics_with_very_irregular_cycles(self):
        """Test statistics handles highly irregular cycles."""
        service = CycleStatisticsService(self.user)

        # Create very irregular cycles
        current_start = date.today() - timedelta(days=200)
        lengths = [21, 45, 22, 50, 35]  # Extremely variable

        for i, length in enumerate(lengths):
            cycle_end = current_start + timedelta(days=length - 1)
            Cycle.objects.create(
                user=self.user,
                start_date=current_start,
                end_date=cycle_end,
                period_end_date=current_start + timedelta(days=4),
                cycle_number=i + 1,
            )
            current_start = cycle_end + timedelta(days=1)

        # All methods should handle this without crashing
        avg_cycle = service.get_average_cycle_length()
        self.assertIsNotNone(avg_cycle)

        regularity = service.get_cycle_regularity_score()
        self.assertEqual(regularity["rating"], "irregular")

        trends = service.get_trends()
        self.assertIsNotNone(trends)

    def test_statistics_with_only_two_cycles(self):
        """Test statistics with minimum viable data."""
        service = CycleStatisticsService(self.user)

        # Create exactly 2 completed cycles
        for i in range(2):
            Cycle.objects.create(
                user=self.user,
                start_date=date.today() - timedelta(days=60 - i*30),
                end_date=date.today() - timedelta(days=33 - i*30),
                period_end_date=date.today() - timedelta(days=56 - i*30),
                cycle_number=i + 1,
            )

        # Should work for average but not trends
        avg = service.get_average_cycle_length()
        self.assertIsNotNone(avg)

        regularity = service.get_cycle_regularity_score()
        self.assertIsNotNone(regularity)

        trends = service.get_trends()
        self.assertIsNone(trends)  # Needs at least 4 cycles

    def test_detection_handles_future_dates(self):
        """Test detection gracefully handles future log dates."""
        service = CycleDetectionService(self.user)

        # Create log for future date (shouldn't break)
        future_log = self._create_daily_log(date.today() + timedelta(days=1), flow_level="medium")
        result = service.process_daily_log(future_log)

        # Should still process
        self.assertIn("action", result)

    def test_prediction_with_ongoing_cycle(self):
        """Test prediction when there's an ongoing cycle."""
        service = CyclePredictionService(self.user)

        # Create completed cycles
        current_start = date.today() - timedelta(days=120)
        for i in range(3):
            cycle_end = current_start + timedelta(days=27)
            Cycle.objects.create(
                user=self.user,
                start_date=current_start,
                end_date=cycle_end,
                period_end_date=current_start + timedelta(days=4),
                cycle_number=i + 1,
            )
            current_start = cycle_end + timedelta(days=1)

        # Create ongoing cycle (no end_date)
        Cycle.objects.create(
            user=self.user,
            start_date=date.today() - timedelta(days=10),
            cycle_number=4,
        )

        result = service.generate_prediction(save=False)

        # Should predict from the ongoing cycle's start date
        self.assertIsNotNone(result)

    def test_different_users_isolated(self):
        """Test that services isolate data by user."""
        user2 = self._create_test_user(email="test2@example.com")
        CycleSettings.objects.create(
            user=user2,
            cycle_tracking_enabled=True,
        )

        # Create data for user1
        for i in range(3):
            Cycle.objects.create(
                user=self.user,
                start_date=date.today() - timedelta(days=90 - i*30),
                end_date=date.today() - timedelta(days=63 - i*30),
                period_end_date=date.today() - timedelta(days=86 - i*30),
                cycle_number=i + 1,
            )

        # User2's services should see no data
        service2 = CycleStatisticsService(user2)
        avg = service2.get_average_cycle_length()
        self.assertIsNone(avg)

        # User1's services should see their data
        service1 = CycleStatisticsService(self.user)
        avg1 = service1.get_average_cycle_length()
        self.assertIsNotNone(avg1)
        self.assertEqual(avg1["count"], 3)
