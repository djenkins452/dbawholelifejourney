"""Tests for GoalMomentumService."""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.test import TestCase

from apps.dashboard_v2.models import GoalMomentumSnapshot
from apps.dashboard_v2.services.momentum_service import (
    DECAY_CONSTANT,
    GoalMomentumService,
)
from apps.users.models import TermsAcceptance, User


class GoalMomentumServiceTest(TestCase):
    """Tests for the GoalMomentumService."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="momentum@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

    def test_streak_to_score_zero(self):
        """Zero streak = zero score."""
        self.assertEqual(GoalMomentumService._streak_to_score(0), 0)

    def test_streak_to_score_seven_days(self):
        """7-day streak = 50 score."""
        self.assertEqual(GoalMomentumService._streak_to_score(7), 50)

    def test_streak_to_score_thirty_days(self):
        """30-day streak = 90 score."""
        self.assertEqual(GoalMomentumService._streak_to_score(30), 90)

    def test_streak_to_score_sixty_plus(self):
        """60+ day streak = 100 score."""
        self.assertEqual(GoalMomentumService._streak_to_score(60), 100)
        self.assertEqual(GoalMomentumService._streak_to_score(100), 100)

    def test_streak_to_score_interpolation(self):
        """Intermediate values are interpolated."""
        score = GoalMomentumService._streak_to_score(5)
        # Between 3 (25) and 7 (50): 5 is (5-3)/(7-3) = 50% of the way
        self.assertEqual(score, 38)  # 25 + 0.5 * 25 = 37.5, rounded to 38

    def test_get_all_momentum_no_goals(self):
        """Empty list when user has no active goals."""
        service = GoalMomentumService(self.user)
        result = service.get_all_momentum()
        self.assertEqual(result, [])

    @patch("apps.dashboard_v2.services.momentum_service.GoalMomentumService._compute_all")
    def test_get_all_momentum_caches(self, mock_compute):
        """Result is cached on second call."""
        mock_compute.return_value = [{"goal_id": 1, "momentum": 50}]
        service = GoalMomentumService(self.user)

        result1 = service.get_all_momentum()
        result2 = service.get_all_momentum()

        # Should only compute once; second call comes from cache
        mock_compute.assert_called_once()
        self.assertEqual(result1, result2)

    def test_compute_trend_stable_no_history(self):
        """With no snapshot history, trend should be stable."""
        from apps.purpose.models import LifeDomain, LifeGoal

        domain = LifeDomain.objects.create(name="Test", slug="test")
        goal = LifeGoal.objects.create(
            user=self.user, title="Test Goal", domain=domain, status="active"
        )

        service = GoalMomentumService(self.user)
        trend = service._compute_trend(goal, 50)
        self.assertEqual(trend, "stable")

    def test_compute_trend_rising(self):
        """Trend is rising when current score > 7d avg + 10."""
        from apps.purpose.models import LifeDomain, LifeGoal

        domain = LifeDomain.objects.create(name="Test", slug="test-rising")
        goal = LifeGoal.objects.create(
            user=self.user, title="Test Goal", domain=domain, status="active"
        )

        # Create historical snapshots with low scores
        today = date.today()
        for i in range(1, 6):
            GoalMomentumSnapshot.objects.create(
                user=self.user,
                goal=goal,
                snapshot_date=today - timedelta(days=i),
                momentum_score=30,
                progress_score=10,
            )

        service = GoalMomentumService(self.user)
        trend = service._compute_trend(goal, 60)  # 60 > 30 + 10
        self.assertEqual(trend, "rising")

    def test_compute_trend_falling(self):
        """Trend is falling when current score < 7d avg - 10."""
        from apps.purpose.models import LifeDomain, LifeGoal

        domain = LifeDomain.objects.create(name="Test", slug="test-falling")
        goal = LifeGoal.objects.create(
            user=self.user, title="Test Goal", domain=domain, status="active"
        )

        today = date.today()
        for i in range(1, 6):
            GoalMomentumSnapshot.objects.create(
                user=self.user,
                goal=goal,
                snapshot_date=today - timedelta(days=i),
                momentum_score=70,
                progress_score=50,
            )

        service = GoalMomentumService(self.user)
        trend = service._compute_trend(goal, 50)  # 50 < 70 - 10
        self.assertEqual(trend, "falling")

    def test_compute_and_persist(self):
        """compute_and_persist creates GoalMomentumSnapshot records."""
        from apps.purpose.models import LifeDomain, LifeGoal

        domain = LifeDomain.objects.create(name="Health", slug="health")
        goal = LifeGoal.objects.create(
            user=self.user, title="Healthy Lifestyle", domain=domain, status="active"
        )

        service = GoalMomentumService(self.user)
        service.compute_and_persist()

        snapshots = GoalMomentumSnapshot.objects.filter(user=self.user, goal=goal)
        self.assertEqual(snapshots.count(), 1)
        snapshot = snapshots.first()
        self.assertGreaterEqual(snapshot.momentum_score, 0)
        self.assertLessEqual(snapshot.momentum_score, 100)
