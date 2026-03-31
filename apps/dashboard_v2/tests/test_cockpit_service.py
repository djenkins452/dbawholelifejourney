"""Tests for GoalCockpitService — dynamic goal-driven cockpit."""

from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from apps.dashboard_v2.services.cockpit_service import (
    BaseDomainScorer,
    FaithDomainScorer,
    GenericDomainScorer,
    GoalCockpitService,
    HealthDomainScorer,
    WorkDomainScorer,
)
from apps.purpose.models import GoalMilestone, HabitGoal, LifeDomain, LifeGoal
from apps.users.models import TermsAcceptance, User


class CockpitTestMixin:
    """Shared setup for cockpit tests — creates LifeDomains and user.

    Patches get_state_value globally to prevent Python 3.9 recursion errors
    in HealthScoreService during test DB queries. Tests that need specific
    SAE values should override with their own @patch.
    """

    def setUp(self):
        # Patch SAE state reads to avoid HealthScoreService recursion on Python 3.9
        self._gsv_patcher = patch(
            "apps.core.ai_state.state_engine.get_state_value",
            return_value=None,
        )
        self._gsv_patcher.start()
        self.addCleanup(self._gsv_patcher.stop)

        self.user = User.objects.create_user(
            email="cockpit@test.com", password="testpass123"
        )
        TermsAcceptance.objects.create(
            user=self.user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        self.user.preferences.has_completed_onboarding = True
        self.user.preferences.save()

        # Create LifeDomains
        self.faith_domain = LifeDomain.objects.get_or_create(
            slug="faith",
            defaults={"name": "Faith", "color": "#8b5cf6", "sort_order": 1},
        )[0]
        self.health_domain = LifeDomain.objects.get_or_create(
            slug="health",
            defaults={"name": "Health", "color": "#ef4444", "sort_order": 2},
        )[0]
        self.work_domain = LifeDomain.objects.get_or_create(
            slug="work",
            defaults={"name": "Work", "color": "#3b82f6", "sort_order": 3},
        )[0]
        self.family_domain = LifeDomain.objects.get_or_create(
            slug="family",
            defaults={"name": "Family", "color": "#ec4899", "sort_order": 4},
        )[0]
        self.finances_domain = LifeDomain.objects.get_or_create(
            slug="finances",
            defaults={"name": "Finances", "color": "#10b981", "sort_order": 5},
        )[0]


class GoalCockpitDomainActivationTest(CockpitTestMixin, TestCase):
    """Tests for dynamic domain activation logic."""

    def test_no_goals_returns_empty(self):
        """User with no goals and no SAE signals gets empty cockpit."""
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()
        self.assertEqual(data, [])

    def test_single_goal_shows_single_domain(self):
        """User with one active goal in Faith sees only Faith dial."""
        LifeGoal.objects.create(
            user=self.user, title="Grow in faith", domain=self.faith_domain, status="active",
        )
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["slug"], "faith")

    def test_multiple_goals_shows_multiple_domains(self):
        """User with goals in three domains sees three dials."""
        LifeGoal.objects.create(
            user=self.user, title="Faith goal", domain=self.faith_domain, status="active",
        )
        LifeGoal.objects.create(
            user=self.user, title="Health goal", domain=self.health_domain, status="active",
        )
        LifeGoal.objects.create(
            user=self.user, title="Work goal", domain=self.work_domain, status="active",
        )
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()

        slugs = {d["slug"] for d in data}
        self.assertEqual(slugs, {"faith", "health", "work"})

    def test_completed_goals_not_shown(self):
        """Completed goals don't activate a domain."""
        LifeGoal.objects.create(
            user=self.user, title="Done goal", domain=self.faith_domain, status="completed",
        )
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()
        self.assertEqual(data, [])

    def test_habit_goals_activate_domain(self):
        """Active HabitGoals activate the domain even without LifeGoals."""
        HabitGoal.objects.create(
            user=self.user, name="Exercise daily", domain=self.health_domain,
            status="active", purpose="Stay healthy",
            start_date="2026-01-01", end_date="2026-12-31",
        )
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["slug"], "health")

    def test_max_five_dials(self):
        """Cockpit caps at 5 dials even with more active domains."""
        domains = [self.faith_domain, self.health_domain, self.work_domain,
                   self.family_domain, self.finances_domain]
        # Create a 6th domain
        learning = LifeDomain.objects.get_or_create(
            slug="learning",
            defaults={"name": "Learning", "color": "#f59e0b", "sort_order": 6},
        )[0]
        domains.append(learning)

        for domain in domains:
            LifeGoal.objects.create(
                user=self.user, title=f"{domain.name} goal",
                domain=domain, status="active",
            )

        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()
        self.assertLessEqual(len(data), 5)

    @patch("apps.dashboard_v2.services.cockpit_service.GoalCockpitService._get_signal_active_domains")
    def test_sae_signals_activate_domain(self, mock_signals):
        """Domain with SAE signals but no goals still appears."""
        # Simulate health having signal activity
        mock_signals.return_value = {"health"}

        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()

        slugs = {d["slug"] for d in data}
        self.assertIn("health", slugs)

    def test_labels_from_model(self):
        """Labels and colors come from LifeDomain model, not hardcoded."""
        LifeGoal.objects.create(
            user=self.user, title="Test goal", domain=self.faith_domain, status="active",
        )
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()

        self.assertEqual(data[0]["label"], self.faith_domain.name)
        self.assertEqual(data[0]["color"], self.faith_domain.color)

    def test_get_active_domain_slugs(self):
        """get_active_domain_slugs returns set of slugs for validation."""
        LifeGoal.objects.create(
            user=self.user, title="Faith goal", domain=self.faith_domain, status="active",
        )
        LifeGoal.objects.create(
            user=self.user, title="Work goal", domain=self.work_domain, status="active",
        )
        service = GoalCockpitService(self.user)
        slugs = service.get_active_domain_slugs()
        self.assertIn("faith", slugs)
        self.assertIn("work", slugs)
        self.assertNotIn("family", slugs)


class DomainStructureTest(CockpitTestMixin, TestCase):
    """Tests for domain data structure."""

    def test_domain_has_required_fields(self):
        """Each domain dict has all required fields."""
        LifeGoal.objects.create(
            user=self.user, title="Goal", domain=self.faith_domain, status="active",
        )
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()
        domain = data[0]

        for field in ("slug", "label", "color", "score", "trend",
                      "trend_delta", "priority", "components", "goal_progress"):
            self.assertIn(field, domain, f"Missing field: {field}")

        self.assertIsInstance(domain["score"], int)
        self.assertIn(domain["trend"], ("up", "down", "flat"))

    def test_domain_detail_works(self):
        """get_domain_detail returns data for an active domain."""
        LifeGoal.objects.create(
            user=self.user, title="Goal", domain=self.faith_domain, status="active",
        )
        service = GoalCockpitService(self.user)
        result = service.get_domain_detail("faith")
        self.assertIn("score", result)
        self.assertEqual(result["slug"], "faith")

    def test_domain_detail_invalid(self):
        """get_domain_detail returns empty for unknown domain slug."""
        service = GoalCockpitService(self.user)
        result = service.get_domain_detail("nonexistent")
        self.assertEqual(result["score"], 0)


class FaithScorerTest(CockpitTestMixin, TestCase):
    """Tests for faith domain scoring."""

    def test_faith_score_no_data(self):
        """Faith score is 0 when no faith activity exists."""
        LifeGoal.objects.create(
            user=self.user, title="Faith goal", domain=self.faith_domain, status="active",
        )
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()
        faith = next(d for d in data if d["slug"] == "faith")

        self.assertEqual(faith["score"], 0)
        self.assertEqual(faith["label"], self.faith_domain.name)


class HealthScorerTest(CockpitTestMixin, TestCase):
    """Tests for health domain scoring."""

    def setUp(self):
        super().setUp()
        # Stop the global SAE mock so we can use test-specific mock values
        self._gsv_patcher.stop()

    @patch("apps.core.ai_state.state_engine.get_state_value")
    def test_health_score_from_sae(self, mock_gsv):
        """Health score uses HealthScoreService composite from SAE."""
        sae_data = {
            'health.health_score': 72,
            'health.health_score_drivers': {
                'domains': {'sleep': {'score': 80, 'weight': 20, 'detail': '7.2h'}},
                'missing_signals': ['glucose'],
                'status': 'computed',
            },
            'health.health_score_prev_7d': 68,
            'health.recovery_score_today': 65,
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
            'health.bp_systolic': 128,
            'health.bp_diastolic': 82,
            'health.heart_rate_avg_7d': 68,
            'health.glucose_avg_7d': 105,
            'health.blood_oxygen_avg_7d': 97.5,
        }
        mock_gsv.side_effect = lambda user, path, default=None: sae_data.get(path, default)

        # Health activates via SAE signals, not just goals
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()

        health = next(d for d in data if d["slug"] == "health")
        self.assertEqual(health["score"], 72)
        self.assertEqual(health["components"]["medication"]["completed"], 18)
        self.assertEqual(health["components"]["vitals"]["bp_systolic"], 128)


class WorkScorerTest(CockpitTestMixin, TestCase):
    """Tests for work/purpose domain scoring."""

    def test_work_score_no_tasks(self):
        """Work score is 0 when no tasks or goals exist."""
        LifeGoal.objects.create(
            user=self.user, title="Work goal", domain=self.work_domain, status="active",
        )
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()
        work = next(d for d in data if d["slug"] == "work")

        self.assertEqual(work["score"], 0)
        self.assertEqual(work["label"], self.work_domain.name)


class GenericScorerTest(CockpitTestMixin, TestCase):
    """Tests for generic domain scorer (non-specialized domains)."""

    def test_generic_scorer_for_unknown_domain(self):
        """Domains without specialized scorers use GenericDomainScorer."""
        LifeGoal.objects.create(
            user=self.user, title="Family goal", domain=self.family_domain, status="active",
        )
        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()

        family = next(d for d in data if d["slug"] == "family")
        self.assertEqual(family["label"], "Family")
        self.assertIn("milestones", family["components"])
        self.assertIn("habits", family["components"])
        self.assertIn("tasks", family["components"])

    def test_generic_scorer_with_milestones(self):
        """Generic scorer computes milestone completion."""
        goal = LifeGoal.objects.create(
            user=self.user, title="Family goal", domain=self.family_domain, status="active",
        )
        GoalMilestone.objects.create(goal=goal, title="M1", completed=True)
        GoalMilestone.objects.create(goal=goal, title="M2", completed=False)

        service = GoalCockpitService(self.user)
        data = service.get_cockpit_data()
        family = next(d for d in data if d["slug"] == "family")

        # 1/2 milestones = 50% for milestone component
        self.assertGreater(family["score"], 0)


class TrendCalculationTest(CockpitTestMixin, TestCase):
    """Tests for trend calculation helper."""

    def test_trend_up(self):
        """Trend is 'up' when score increases beyond threshold."""
        trend, delta = BaseDomainScorer._calc_trend(80, 70)
        self.assertEqual(trend, "up")
        self.assertEqual(delta, 10)

    def test_trend_down(self):
        """Trend is 'down' when score decreases beyond threshold."""
        trend, delta = BaseDomainScorer._calc_trend(60, 75)
        self.assertEqual(trend, "down")
        self.assertEqual(delta, -15)

    def test_trend_flat(self):
        """Trend is 'flat' when difference is within threshold."""
        trend, delta = BaseDomainScorer._calc_trend(75, 73)
        self.assertEqual(trend, "flat")
