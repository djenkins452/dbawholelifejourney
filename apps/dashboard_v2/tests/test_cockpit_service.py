"""Tests for GoalCockpitService."""

from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.test import TestCase
from django.utils import timezone

from apps.dashboard_v2.services.cockpit_service import GoalCockpitService
from apps.users.models import TermsAcceptance, User


class GoalCockpitServiceTest(TestCase):
    """Tests for goal-based cockpit scoring."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="cockpit@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_get_cockpit_data_returns_three_domains(self):
        """get_cockpit_data() returns faith, health, work keys."""
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()

        self.assertIn("faith", data)
        self.assertIn("health", data)
        self.assertIn("work", data)

    def test_domain_structure(self):
        """Each domain has required fields."""
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()

        for key in ("faith", "health", "work"):
            domain = data[key]
            self.assertIn("score", domain)
            self.assertIn("trend", domain)
            self.assertIn("trend_delta", domain)
            self.assertIn("priority", domain)
            self.assertIn("label", domain)
            self.assertIn("color", domain)
            self.assertIn("components", domain)
            self.assertIsInstance(domain["score"], int)
            self.assertIn(domain["trend"], ("up", "down", "flat"))

    def test_faith_score_no_data(self):
        """Faith score is 0 when no faith activity exists."""
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()

        self.assertEqual(data["faith"]["score"], 0)
        self.assertEqual(data["faith"]["label"], "Faith")
        self.assertEqual(data["faith"]["color"], "#3b82f6")

    @patch("apps.dashboard_v2.services.cockpit_service.GoalCockpitService._faith_window")
    def test_faith_score_full_consistency(self, mock_window):
        """Faith score is 100 when all 8 days have Bible + prayer."""
        mock_window.return_value = {
            "bible_days": 8,
            "prayer_days": 8,
            "bible_daily": [1, 1, 1, 1, 1, 1, 1, 1],
            "prayer_daily": [1, 1, 1, 1, 1, 1, 1, 1],
        }
        service = GoalCockpitService(self.user)
        result = service._compute_faith()

        self.assertEqual(result["score"], 100)
        self.assertEqual(result["components"]["bible_days"], 8)
        self.assertEqual(result["components"]["prayer_days"], 8)

    @patch("apps.dashboard_v2.services.cockpit_service.GoalCockpitService._faith_window")
    def test_faith_score_partial(self, mock_window):
        """Faith score reflects partial consistency (8-day window)."""
        mock_window.return_value = {
            "bible_days": 4,
            "prayer_days": 5,
            "bible_daily": [1, 1, 0, 1, 0, 0, 1, 0],
            "prayer_daily": [1, 1, 1, 1, 0, 1, 0, 0],
        }
        service = GoalCockpitService(self.user)
        result = service._compute_faith()

        # (4/8 * 50) + (5/8 * 50) = 25 + 31.25 = 56.25 → 56
        expected = round((4 / 8 * 50) + (5 / 8 * 50))
        self.assertEqual(result["score"], expected)

    @patch("apps.core.ai_state.state_engine.get_state_value")
    def test_health_score_from_health_score_service(self, mock_gsv):
        """Health score uses HealthScoreService composite from SAE."""
        sae_data = {
            # HealthScoreService composite score + drivers
            'health.health_score': 72,
            'health.health_score_drivers': {
                'domains': {
                    'sleep': {'score': 80, 'weight': 20, 'detail': '7.2h avg'},
                    'recovery': {'score': 65, 'weight': 20, 'detail': 'Recovery: 65'},
                    'workout': {'score': 70, 'weight': 10, 'detail': '5/7 sessions'},
                },
                'missing_signals': ['glucose', 'nutrition'],
                'status': 'computed',
            },
            'health.health_score_prev_7d': 68,
            'health.recovery_score_today': 65,
            # Behavioral detail
            'medicine.adherence_score_7d': 90,
            'medicine.completed_7d': 18,
            'medicine.expected_7d': 20,
            'medicine.missed_7d': 2,
            'fitness.workout_adherence_score': 70,
            'fitness.workout_completed_7d': 5,
            'fitness.workout_expected_7d': 7,
            'fitness.workout_missed_7d': 2,
            'health.sleep_consistency_score': 57,
            'health.sleep_avg_hours_7d': 7.2,
            'health.sleep_good_nights_7d': 4,
            'health.sleep_entries_7d': 7,
            'health.water_consistency_score': 43,
            'health.water_avg_oz_7d': 48.0,
            'health.water_good_days_7d': 3,
            'health.water_tracked_days_7d': 7,
            'health.water_goal_oz': 64,
            # Vitals
            'health.bp_systolic': 128,
            'health.bp_diastolic': 82,
            'health.heart_rate_avg_7d': 68,
            'health.glucose_avg_7d': 105,
            'health.blood_oxygen_avg_7d': 97.5,
        }
        mock_gsv.side_effect = lambda user, path, default=None: sae_data.get(path, default)

        service = GoalCockpitService(self.user)
        result = service._compute_health()

        # Score comes from HealthScoreService, not custom formula
        self.assertEqual(result["score"], 72)
        self.assertEqual(result["label"], "Health")
        # Trend: 72 vs 68 = +4, within threshold → flat
        self.assertEqual(result["trend"], "flat")
        # Components still populated for panel
        self.assertEqual(result["components"]["medication"]["completed"], 18)
        self.assertEqual(result["components"]["workout"]["missed"], 2)
        self.assertEqual(result["components"]["sleep"]["avg_hours"], 7.2)
        # Vitals present
        self.assertEqual(result["components"]["vitals"]["bp_systolic"], 128)
        self.assertEqual(result["components"]["vitals"]["recovery_score"], 65)
        # Score domains present
        self.assertIn("sleep", result["components"]["score_domains"])
        self.assertEqual(result["components"]["missing_signals"], ["glucose", "nutrition"])

    def test_health_score_no_sae_data(self):
        """Health score is 0 when no SAE health_score exists."""
        service = GoalCockpitService(self.user)
        result = service._compute_health()

        self.assertEqual(result["score"], 0)

    def test_work_score_no_tasks(self):
        """Work score is 0 when no tasks or goals exist."""
        service = GoalCockpitService(self.user)
        result = service._compute_work()

        self.assertEqual(result["score"], 0)
        self.assertEqual(result["label"], "Work / Purpose")
        self.assertEqual(result["color"], "#f59e0b")

    def test_priority_flag(self):
        """Priority is True when score < 60 (except empty domains with no data)."""
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()

        for key in ("faith", "health", "work"):
            domain = data[key]
            # Empty domains (no data) return priority=False even with score=0
            if not domain.get("components"):
                continue
            if domain["score"] < 60:
                self.assertTrue(domain["priority"])
            else:
                self.assertFalse(domain["priority"])

    def test_trend_calculation(self):
        """Trend calculation produces correct direction."""
        service = GoalCockpitService(self.user)

        # Up: current > previous by more than threshold
        trend, delta = service._calc_trend(80, 70)
        self.assertEqual(trend, "up")
        self.assertEqual(delta, 10)

        # Down: current < previous by more than threshold
        trend, delta = service._calc_trend(60, 75)
        self.assertEqual(trend, "down")
        self.assertEqual(delta, -15)

        # Flat: difference within threshold
        trend, delta = service._calc_trend(75, 73)
        self.assertEqual(trend, "flat")

    def test_get_domain_detail(self):
        """get_domain_detail returns data for a valid domain."""
        service = GoalCockpitService(self.user)

        for domain in ("faith", "health", "work"):
            result = service.get_domain_detail(domain)
            self.assertIn("score", result)
            self.assertIn("components", result)

    def test_get_domain_detail_invalid(self):
        """get_domain_detail returns empty for invalid domain."""
        service = GoalCockpitService(self.user)
        result = service.get_domain_detail("invalid")
        self.assertEqual(result["score"], 0)
        self.assertEqual(result["label"], "Unknown")
