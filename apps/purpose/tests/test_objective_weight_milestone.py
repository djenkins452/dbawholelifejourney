"""Phase 1 trust fix — objective weight milestone evaluator.

Covers:
  - Bidirectional convergence (the headline trust contract)
  - Decimal boundary semantics (the 289.9 production case)
  - Idempotency
  - Achievement-milestone back-compat (untouched)
  - WeightEntry signal trigger (no manual eval call needed)
  - Initial evaluation after wiring (no future-save required)
  - recompute_objective_milestones operational repair utility
"""

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.health.models import WeightEntry
from apps.purpose.models import GoalMilestone, LifeGoal
from apps.purpose.services.objective_weight_milestones import (
    evaluate_weight_milestones,
    recompute_objective_milestones,
)
from apps.users.models import TermsAcceptance


User = get_user_model()


def _make_user(email="milestone-trust@test.com"):
    u = User.objects.create_user(email=email, password="x" * 20)
    TermsAcceptance.objects.create(
        user=u,
        terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
    )
    u.preferences.has_completed_onboarding = True
    u.preferences.save()
    return u


def _make_objective_milestone(user, *, target):
    """Helper — create a goal + one objective weight milestone."""
    goal = LifeGoal.objects.create(
        user=user,
        title="France 2027 Family 10K Mission",
        description="test",
    )
    return GoalMilestone.objects.create(
        goal=goal,
        title="Goal Weight of 289.9",
        objective_metric="weight_lb",
        objective_target_value=Decimal(str(target)),
        objective_operator="lte",
    )


def _log_weight(user, lb):
    return WeightEntry.objects.create(
        user=user, value=Decimal(str(lb)), unit="lb",
        recorded_at=timezone.now(),
    )


# ── Core evaluator behavior ────────────────────────────────────────

class BoundarySemanticsTests(TestCase):
    """The 289.9 production case + boundary correctness."""

    def setUp(self):
        self.user = _make_user("boundary@test.com")
        self.milestone = _make_objective_milestone(self.user, target=289.9)

    def test_completes_at_decimal_target_boundary(self):
        """At exactly 289.9 lb with `lte` operator, the milestone is
        complete. Confirms the user's explicit boundary semantics.

        Note: the WeightEntry post_save signal runs the evaluator
        eagerly, so the milestone is already complete by the time we
        observe it. The state assertion is the truth that matters."""
        _log_weight(self.user, 289.9)
        evaluate_weight_milestones(self.user)  # idempotent extra call
        self.milestone.refresh_from_db()
        self.assertTrue(self.milestone.completed)
        self.assertEqual(self.milestone.completed_date, timezone.localdate())

    def test_completes_below_decimal_target_headline_case(self):
        """The literal production failure mode: weight 288.8, target
        289.9 → should be complete. This is the trust break."""
        _log_weight(self.user, 288.8)
        evaluate_weight_milestones(self.user)
        self.milestone.refresh_from_db()
        self.assertTrue(self.milestone.completed)

    def test_incomplete_when_above_decimal_target(self):
        """Target 289.9, weight 290.0 → stays incomplete."""
        _log_weight(self.user, 290.0)
        evaluate_weight_milestones(self.user)
        self.milestone.refresh_from_db()
        self.assertFalse(self.milestone.completed)
        self.assertIsNone(self.milestone.completed_date)


class BidirectionalConvergenceTests(TestCase):
    """Reality wins — milestone state moves BOTH directions.
    The headline trust contract."""

    def setUp(self):
        self.user = _make_user("bidir@test.com")
        self.milestone = _make_objective_milestone(self.user, target=289.9)

    def test_completes_then_uncompletes_on_weight_regression(self):
        """Was complete at 288.8; weight climbs to 292 → milestone
        auto-uncompletes. This is the architectural property the
        user specifically flagged ('one-way completion is wrong')."""
        # Stage 1: complete
        _log_weight(self.user, 288.8)
        evaluate_weight_milestones(self.user)
        self.milestone.refresh_from_db()
        self.assertTrue(self.milestone.completed)
        # Stage 2: regression
        _log_weight(self.user, 292.0)
        evaluate_weight_milestones(self.user)
        self.milestone.refresh_from_db()
        self.assertFalse(self.milestone.completed)
        self.assertIsNone(
            self.milestone.completed_date,
            "regression must clear completed_date — incomplete rows "
            "should not retain a historical completion date",
        )

    def test_re_completes_after_returning_to_target(self):
        """Bidirectional truly means BOTH ways — drop back below
        target and the milestone re-completes. The signal converges
        on every save; the assertions check the resulting state."""
        _log_weight(self.user, 288.8)  # signal → complete
        _log_weight(self.user, 292.0)  # signal → uncomplete
        _log_weight(self.user, 285.0)  # signal → re-complete
        evaluate_weight_milestones(self.user)  # idempotent
        self.milestone.refresh_from_db()
        self.assertTrue(
            self.milestone.completed,
            "milestone must re-complete when weight returns below target",
        )


class IdempotencyTests(TestCase):
    """Calling the evaluator when state already matches must not
    churn DB rows or fire spurious updated_at writes."""

    def setUp(self):
        self.user = _make_user("idem@test.com")
        self.milestone = _make_objective_milestone(self.user, target=289.9)

    def test_no_op_when_state_unchanged(self):
        """After the WeightEntry post_save signal converges the
        milestone, every subsequent evaluator call must be a no-op
        (no DB writes, no updated_at churn). This is the idempotency
        contract."""
        _log_weight(self.user, 288.8)
        # Signal already fired during create. Explicit calls below
        # must each report 0 changes.
        first = evaluate_weight_milestones(self.user)
        second = evaluate_weight_milestones(self.user)
        self.assertEqual(first, 0, "first explicit eval should be a no-op")
        self.assertEqual(second, 0, "second explicit eval should be a no-op")
        # State is still correctly complete.
        self.milestone.refresh_from_db()
        self.assertTrue(self.milestone.completed)


# ── Back-compat: achievement milestones must stay manual ──────────

class AchievementMilestoneUnchangedTests(TestCase):
    """Manual achievement milestones (no objective_metric) must NOT
    be touched by the evaluator. This is the back-compat contract."""

    def setUp(self):
        self.user = _make_user("ach@test.com")
        self.goal = LifeGoal.objects.create(
            user=self.user, title="Tour de France 2027", description=""
        )
        self.ran_10k = GoalMilestone.objects.create(
            goal=self.goal, title="Run first 10K",
            # Explicitly NO objective_metric → achievement, manual.
        )
        self.objective = GoalMilestone.objects.create(
            goal=self.goal, title="Goal Weight of 289.9",
            objective_metric="weight_lb",
            objective_target_value=Decimal("289.9"),
            objective_operator="lte",
        )

    def test_evaluator_ignores_achievement_milestones(self):
        _log_weight(self.user, 250.0)  # well below ANY weight target
        evaluate_weight_milestones(self.user)
        self.ran_10k.refresh_from_db()
        self.assertFalse(
            self.ran_10k.completed,
            "achievement milestone must NEVER auto-complete — Phase 1 "
            "back-compat contract",
        )
        # Objective milestone DOES complete.
        self.objective.refresh_from_db()
        self.assertTrue(self.objective.completed)

    def test_manual_mark_complete_on_achievement_still_works(self):
        """Manual achievement toggle path unchanged."""
        self.ran_10k.mark_complete()
        self.ran_10k.refresh_from_db()
        self.assertTrue(self.ran_10k.completed)
        self.assertEqual(self.ran_10k.completed_date, timezone.localdate())


# ── Resilience ─────────────────────────────────────────────────────

class ResilienceTests(TestCase):
    def test_missing_weight_entry_no_crash(self):
        """User has no WeightEntry at all → evaluator returns 0,
        no rows touched, no exception."""
        user = _make_user("noweight@test.com")
        _make_objective_milestone(user, target=289.9)
        result = evaluate_weight_milestones(user)
        self.assertEqual(result, 0)


# ── Signal trigger ────────────────────────────────────────────────

class WeightEntrySignalTriggerTests(TestCase):
    """The whole point of Phase 1: WeightEntry save → milestone
    converges WITHOUT an explicit evaluator call."""

    def setUp(self):
        self.user = _make_user("signal@test.com")
        self.milestone = _make_objective_milestone(self.user, target=289.9)

    def test_creating_weight_entry_auto_completes_milestone(self):
        # No explicit evaluator call — only the post_save signal.
        _log_weight(self.user, 288.8)
        self.milestone.refresh_from_db()
        self.assertTrue(self.milestone.completed)

    def test_updating_weight_entry_re_evaluates_bidirectionally(self):
        entry = _log_weight(self.user, 285.0)
        self.milestone.refresh_from_db()
        self.assertTrue(self.milestone.completed)
        # Edit (not create) the weight to a regression value.
        entry.value = Decimal("292.0")
        entry.save()  # update path
        self.milestone.refresh_from_db()
        self.assertFalse(
            self.milestone.completed,
            "editing a weight should trigger bidirectional convergence",
        )


# ── Initial evaluation against existing data ──────────────────────

class InitialEvaluationAgainstExistingDataTests(TestCase):
    """The user's explicit requirement: evaluator runs against the
    current/latest weight immediately, NOT only future saves. This
    test simulates the wiring migration's initial pass."""

    def test_evaluator_uses_pre_existing_weight_entries(self):
        user = _make_user("initial@test.com")
        # Step 1: weight history exists BEFORE the milestone is wired.
        # No objective milestone exists yet, so the signal does nothing.
        _log_weight(user, 285.0)
        _log_weight(user, 288.8)  # latest
        # Step 2: wire the milestone NOW (simulating migration).
        milestone = _make_objective_milestone(user, target=289.9)
        self.assertFalse(
            milestone.completed,
            "precondition: no signal could fire because milestone "
            "didn't exist when weights were logged",
        )
        # Step 3: initial evaluation — no new WeightEntry save involved.
        # This is exactly what the wiring migration must do.
        changed = evaluate_weight_milestones(user)
        self.assertEqual(changed, 1)
        milestone.refresh_from_db()
        self.assertTrue(
            milestone.completed,
            "evaluator must look up the LATEST existing WeightEntry and "
            "converge immediately — not wait for the next save",
        )


# ── recompute_objective_milestones operational utility ───────────

class RecomputeUtilityTests(TestCase):
    """Repair path mirroring SAE rebuild philosophy: deterministic
    convergence callable from views / tasks / management commands."""

    def setUp(self):
        self.user = _make_user("recompute@test.com")
        self.milestone = _make_objective_milestone(self.user, target=289.9)

    def test_recompute_converges_drifted_state(self):
        """Simulate drift: weight = 288.8 (complete-worthy) but
        milestone.completed=False due to a missed signal / data
        backfill. recompute should converge."""
        _log_weight(self.user, 288.8)  # signal already converges
        # Force the milestone OUT of sync (manual override simulating
        # a drifted DB row — what an admin DB edit or signal-miss
        # would look like).
        GoalMilestone.objects.filter(pk=self.milestone.pk).update(
            completed=False, completed_date=None,
        )
        self.milestone.refresh_from_db()
        self.assertFalse(self.milestone.completed)
        # Repair via the operational utility.
        n = recompute_objective_milestones(self.user)
        self.assertEqual(n, 1, "recompute must detect the drift and converge")
        self.milestone.refresh_from_db()
        self.assertTrue(self.milestone.completed)

    def test_recompute_is_no_op_when_state_correct(self):
        _log_weight(self.user, 288.8)
        evaluate_weight_milestones(self.user)
        n = recompute_objective_milestones(self.user)
        # Already converged → no mutations.
        self.assertEqual(n, 0)
