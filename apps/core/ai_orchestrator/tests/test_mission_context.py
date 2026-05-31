"""Phase 1B — Beth mission awareness via purpose context pass-through.

Verifies that the deterministic mission block (and its fixed-mapping
coach_line) flows from build_goal_state → SAE goals module →
_build_purpose_context. No new context builder, no readiness, no
fabricated intelligence — CONTEXTUAL tier only.
"""
from datetime import date, timedelta

from django.test import TestCase

from apps.users.models import TermsAcceptance, User
from django.conf import settings


def _create_test_user(email="mission@example.com"):
    user = User.objects.create_user(email=email, password="pw-12345")
    TermsAcceptance.objects.create(
        user=user,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    user.preferences.has_completed_onboarding = True
    user.preferences.save()
    return user


class MissionPurposeContextTests(TestCase):
    def setUp(self):
        self.user = _create_test_user()

    def _rebuild(self):
        from apps.core.ai_state.state_engine import rebuild_user_state
        rebuild_user_state(self.user)

    def test_no_mission_block_without_foundational_goal(self):
        from apps.purpose.models import LifeGoal
        from apps.core.ai_orchestrator.cos_context import _build_purpose_context

        LifeGoal.objects.create(
            user=self.user, title="Plain", status="active",
        )
        self._rebuild()
        ctx = _build_purpose_context(self.user)
        self.assertNotIn("mission", ctx)

    def test_mission_block_with_rising_coach_line(self):
        from apps.purpose.models import GoalMilestone, LifeGoal
        from apps.dashboard_v2.models import GoalMomentumSnapshot
        from apps.core.ai_orchestrator.cos_context import _build_purpose_context

        goal = LifeGoal.objects.create(
            user=self.user,
            title="France 2027 Family 10K",
            status="active",
            is_foundational=True,
            target_date=date.today() + timedelta(days=120),
        )
        GoalMilestone.objects.create(
            goal=goal, title="Run 5K continuous", completed=False,
        )
        GoalMomentumSnapshot.objects.create(
            user=self.user,
            goal=goal,
            snapshot_date=date.today(),
            momentum_score=72,
            progress_score=40,
            momentum_trend="rising",
        )
        self._rebuild()
        ctx = _build_purpose_context(self.user)
        mission = ctx["mission"]
        self.assertEqual(mission["title"], "France 2027 Family 10K")
        self.assertEqual(mission["current_focus"], "Run 5K continuous")
        self.assertEqual(mission["days_remaining"], 120)
        self.assertEqual(mission["momentum_trend"], "rising")
        self.assertEqual(
            mission["coach_line"],
            "Momentum on your France 2027 Family 10K mission is improving — protect it.",
        )

    def test_mission_block_omits_coach_line_without_trend(self):
        from apps.purpose.models import LifeGoal
        from apps.core.ai_orchestrator.cos_context import _build_purpose_context

        LifeGoal.objects.create(
            user=self.user,
            title="No momentum yet",
            status="active",
            is_foundational=True,
        )
        self._rebuild()
        ctx = _build_purpose_context(self.user)
        mission = ctx["mission"]
        self.assertEqual(mission["title"], "No momentum yet")
        self.assertIsNone(mission["momentum_trend"])
        self.assertNotIn("coach_line", mission)

    def test_coach_line_never_contains_readiness_or_percentage(self):
        from apps.core.ai_orchestrator.cos_context import _MISSION_COACH_LINE

        for line in _MISSION_COACH_LINE.values():
            rendered = line.format(title="Test")
            self.assertNotIn("%", rendered)
            self.assertNotIn("ready", rendered.lower())
            self.assertNotIn("on track", rendered.lower())
