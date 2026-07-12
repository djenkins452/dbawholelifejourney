"""Mission narrative must name the user's CURRENT deepest milestone, not an earlier one.

Regression for the reported symptom: with weight ≈283.5, milestones 289.9 and 284.9 both
completed (a single weigh-in crossed both on the SAME day) and 279.9 next, the "How things
are going" narrative kept naming 289.9. Root cause: `_mission_progress_read` selected the
"last completed" milestone with `order_by("-completed_date")` only — a same-day tie the DB
resolved to the earlier-created 289.9. The fix breaks the tie toward the most-progressed
rung (284.9), so the narrative reflects current deterministic state.
"""
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.dashboard_v3.services.composer import _mission_progress_read
from apps.purpose.models import GoalMilestone, LifeGoal
from apps.users.models import TermsAcceptance

User = get_user_model()


def _make_user(email="tiebreak@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0")
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class MissionMilestoneTiebreakTest(TestCase):
    def setUp(self):
        self.user = _make_user()
        self.goal = LifeGoal.objects.create(
            user=self.user, title="Weight mission", status="active",
            is_primary_mission=True,
        )
        completed_day = date.today()

        def ms(target, sort_order, completed, completed_date=None):
            return GoalMilestone.objects.create(
                goal=self.goal, title=f"Goal Weight {target}",
                objective_metric="weight_lb",
                objective_target_value=Decimal(target),
                objective_operator="lte",
                sort_order=sort_order,
                completed=completed,
                completed_date=completed_date,
            )

        # Both completed the SAME day (one weigh-in crossed both).
        ms("289.9", 0, True, completed_day)
        ms("284.9", 1, True, completed_day)
        self.next_ms = ms("279.9", 2, False)

    def test_last_completed_is_most_progressed_not_earliest(self):
        out = _mission_progress_read(
            self.goal, self.goal.next_milestone, date.today(), current_weight=283.5
        )
        # The narrative's "last completed" must be the deepest reached rung (284.9),
        # never the earlier 289.9 that shares the same completion date.
        self.assertEqual(out["last_title"], "Goal Weight 284.9")
        self.assertEqual(out["completed"], 2)
        # Next milestone is the current deterministic next rung.
        self.assertEqual(self.goal.next_milestone.title, "Goal Weight 279.9")
