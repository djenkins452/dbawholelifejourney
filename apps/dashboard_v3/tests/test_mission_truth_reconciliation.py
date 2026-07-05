"""Dashboard Truth — mission commentary reconciles milestone HISTORY with the
CURRENT metric state.

Incident: "Goal Weight 284.9" was reached and title-form weight milestones
complete ONE-WAY (never auto-uncomplete), so the milestone stayed completed=True
even after the weight climbed back to 285.3. The mission card kept saying
"Milestone reached" — historically true, but NOT the mission's current state.

Contract: a milestone reached in the past is only presented as a CURRENT win if
the current metric still holds it. Otherwise the achievement becomes context and
the CURRENT state drives the message.
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.dashboard_v3.services.composer import (
    _build_mission_panel,
    _build_mission_status,
    _mission_progress_read,
)
from apps.purpose.models import GoalMilestone, LifeGoal
from apps.users.models import TermsAcceptance

User = get_user_model()


def _user(email="mtr@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u, terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"))
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


class MilestoneReconciliationTests(TestCase):
    def setUp(self):
        self.user = _user()
        self.today = timezone.localdate()
        self.goal = LifeGoal.objects.create(
            user=self.user, title="France 2027 Weight Mission",
            status="active", is_primary_mission=True,
        )
        # Title-form rung (the common shape, completes ONE-WAY) reached 3 days ago.
        self.reached = GoalMilestone.objects.create(
            goal=self.goal, title="Goal Weight of 284.9 lb",
            completed=True, completed_date=self.today - timedelta(days=3),
            sort_order=1,
        )
        # Next rung — still open.
        self.next = GoalMilestone.objects.create(
            goal=self.goal, title="Goal Weight of 279.9 lb",
            completed=False, sort_order=2,
        )

    def _prog(self, current_weight):
        return _mission_progress_read(
            self.goal, self.next, self.today, current_weight=current_weight)

    # ── The reported bug ────────────────────────────────────────────
    def test_regressed_weight_does_not_claim_current_milestone_win(self):
        prog = self._prog(285.3)
        self.assertEqual(prog["event"], "milestone_reached")
        self.assertIs(prog["last_holds"], False)  # 285.3 > 284.9 → not held now

        panel = _build_mission_panel(self.goal, None, prog)
        self.assertNotEqual(panel["label"], "Milestone reached")
        self.assertNotEqual(panel["trend"], "up")
        n = panel["narrative"]
        self.assertIn("You reached", n)
        self.assertIn("284.9", n)
        self.assertIn("285.3", n)              # CURRENT state stated
        self.assertIn("fluctuation", n)         # small gap → fluctuation framing
        self.assertIn("279.9", n)               # next focus named
        self.assertNotIn("Milestone reached", n)

    def test_status_state_is_not_celebratory_when_regressed(self):
        prog = self._prog(285.3)
        status = _build_mission_status(self.goal, None, [], self.today, prog)
        self.assertEqual(status["state"], "MAINTAINING")   # steady, not a WIN
        self.assertEqual(status["tone"], "flat")
        self.assertIn("Current weight is 285.3", status["narrative"])

    # ── Truth preserved: still held → still a win ───────────────────
    def test_at_or_below_target_still_reads_as_win(self):
        prog = self._prog(284.5)               # 284.5 ≤ 284.9 → held
        self.assertIs(prog["last_holds"], True)
        panel = _build_mission_panel(self.goal, None, prog)
        self.assertEqual(panel["label"], "Milestone reached")
        self.assertEqual(panel["trend"], "up")

    # ── A real drift (beyond fluctuation) reads as Slipping ─────────
    def test_large_regression_reads_as_slipping(self):
        prog = self._prog(290.0)               # 5.1 lb above → not fluctuation
        self.assertIs(prog["last_holds"], False)
        status = _build_mission_status(self.goal, None, [], self.today, prog)
        self.assertEqual(status["state"], "SLIPPING")
        self.assertIn("worth refocusing", status["narrative"])

    # ── No current weight → behaviour unchanged (never contradict blind) ─
    def test_no_current_weight_leaves_celebratory_read(self):
        prog = self._prog(None)
        self.assertIsNone(prog["last_holds"])
        panel = _build_mission_panel(self.goal, None, prog)
        self.assertEqual(panel["label"], "Milestone reached")

    # ── Non-weight milestone → not reconciled, celebratory preserved ─
    def test_non_weight_milestone_not_reconciled(self):
        self.reached.title = "Finish the first manuscript draft"
        self.reached.save(update_fields=["title"])
        prog = self._prog(285.3)               # weight irrelevant to this rung
        self.assertIsNone(prog["last_holds"])
        panel = _build_mission_panel(self.goal, None, prog)
        self.assertEqual(panel["label"], "Milestone reached")

    # ── Objective-metric rung reconciles the same way ───────────────
    def test_objective_metric_rung_reconciles(self):
        self.reached.objective_metric = "weight_lb"
        self.reached.objective_target_value = Decimal("284.9")
        self.reached.objective_operator = "lte"
        self.reached.save()
        prog = self._prog(285.3)
        self.assertIs(prog["last_holds"], False)
