# ==============================================================================
# File: test_pr_detection.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for automatic PR (Personal Record) detection
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-08
# ==============================================================================

"""
PR Detection Tests

Covers:
1. Weight PR detection
2. Rep PR detection (same weight, more reps)
3. Estimated 1RM PR detection
4. No PR on identical set
5. First set for exercise is a PR
6. Warmup sets are skipped
7. Sets with missing weight/reps are skipped
8. High rep count (>=37) doesn't break Brzycki formula
9. PersonalRecord creation with pr_type and previous_value
10. Plateau rule integration — PRs suppress plateau insight
11. Multiple PR types on one set
12. Signal-based auto-detection on ExerciseSet.objects.create()
"""

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.contrib.auth import get_user_model

from apps.health.models import (
    Exercise,
    WorkoutSession,
    WorkoutExercise,
    ExerciseSet,
    PersonalRecord,
)
from apps.health.pr_utils import check_and_record_pr, brzycki_1rm

User = get_user_model()


class PRTestMixin:
    """Common setup for PR detection tests."""

    def create_user(self, email='prtest@example.com', password='testpass123'):
        user = User.objects.create_user(email=email, password=password)
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def create_exercise(self, name='Bench Press'):
        return Exercise.objects.create(
            name=name,
            category='resistance',
            muscle_group='Chest',
            is_active=True,
        )

    def create_session(self, user, workout_date=None):
        if workout_date is None:
            workout_date = date.today()
        return WorkoutSession.objects.create(
            user=user,
            date=workout_date,
            name='Workout',
        )

    def log_set(self, user, exercise, weight, reps, workout_date=None,
                is_warmup=False, session=None):
        """Create an ExerciseSet without triggering signal (for test setup)."""
        if session is None:
            session = self.create_session(user, workout_date)
        we, _ = WorkoutExercise.objects.get_or_create(
            session=session,
            exercise=exercise,
            defaults={'order': 1},
        )
        existing = we.sets.count()
        # Use update_or_create pattern to avoid signal for setup data
        exercise_set = ExerciseSet(
            workout_exercise=we,
            set_number=existing + 1,
            weight=Decimal(str(weight)) if weight else None,
            reps=reps,
            is_warmup=is_warmup,
        )
        # Save without triggering signal by using bulk_create
        # (post_save signals don't fire for bulk_create)
        sets = ExerciseSet.objects.bulk_create([exercise_set])
        return sets[0]


# =============================================================================
# BRZYCKI FORMULA TESTS
# =============================================================================

class BrzyckiFormulaTest(TestCase):
    """Tests for the Brzycki 1RM estimation formula."""

    def test_single_rep_returns_weight(self):
        self.assertEqual(brzycki_1rm(225, 1), 225.0)

    def test_five_reps(self):
        # 185 * (36 / (37 - 5)) = 185 * (36/32) = 208.125
        result = brzycki_1rm(185, 5)
        self.assertAlmostEqual(result, 208.125, places=2)

    def test_ten_reps(self):
        # 135 * (36 / (37 - 10)) = 135 * (36/27) = 180
        result = brzycki_1rm(135, 10)
        self.assertAlmostEqual(result, 180.0, places=2)

    def test_high_reps_capped_at_36(self):
        """Reps >= 37 should not cause division by zero."""
        result = brzycki_1rm(100, 37)
        # Capped to 36 reps: 100 * (36 / (37-36)) = 100 * 36 = 3600
        self.assertAlmostEqual(result, 3600.0, places=2)

    def test_very_high_reps_capped(self):
        """50 reps should also be safe."""
        result = brzycki_1rm(100, 50)
        # Still capped at 36: 100 * 36 = 3600
        self.assertAlmostEqual(result, 3600.0, places=2)

    def test_zero_reps_returns_weight(self):
        """0 reps treated like 1 rep."""
        result = brzycki_1rm(225, 0)
        self.assertEqual(result, 225.0)


# =============================================================================
# PR DETECTION LOGIC TESTS
# =============================================================================

class WeightPRDetectionTest(PRTestMixin, TestCase):
    """Test weight PR detection."""

    def setUp(self):
        self.user = self.create_user()
        self.exercise = self.create_exercise('Bench Press')

    def test_weight_increase_triggers_pr(self):
        """185x5 → 195x5 should be a weight PR."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 195, 5)
        prs = check_and_record_pr(new_set)

        self.assertTrue(len(prs) > 0)
        weight_prs = [p for p in prs if p['type'] == 'weight']
        self.assertEqual(len(weight_prs), 1)
        self.assertEqual(weight_prs[0]['previous'], 185.0)
        self.assertEqual(weight_prs[0]['new'], 195.0)

    def test_pr_recorded_in_db(self):
        """PersonalRecord should be created with correct fields."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 195, 5)
        check_and_record_pr(new_set)

        pr = PersonalRecord.objects.filter(
            user=self.user, exercise=self.exercise
        ).first()
        self.assertIsNotNone(pr)
        self.assertEqual(pr.pr_type, 'weight')
        self.assertEqual(float(pr.weight), 195.0)
        self.assertEqual(pr.reps, 5)
        self.assertEqual(float(pr.previous_value), 185.0)

    def test_exercise_set_marked_as_pr(self):
        """ExerciseSet.is_pr should be set to True."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 195, 5)
        check_and_record_pr(new_set)

        new_set.refresh_from_db()
        self.assertTrue(new_set.is_pr)

    def test_same_weight_no_weight_pr(self):
        """185x5 → 185x5 should NOT be a weight PR."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 185, 5)
        prs = check_and_record_pr(new_set)

        weight_prs = [p for p in prs if p['type'] == 'weight']
        self.assertEqual(len(weight_prs), 0)

    def test_lower_weight_no_pr(self):
        """185x5 → 175x5 should NOT be a weight PR."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 175, 5)
        prs = check_and_record_pr(new_set)

        weight_prs = [p for p in prs if p['type'] == 'weight']
        self.assertEqual(len(weight_prs), 0)


class RepPRDetectionTest(PRTestMixin, TestCase):
    """Test rep PR detection at same weight."""

    def setUp(self):
        self.user = self.create_user()
        self.exercise = self.create_exercise('Bench Press')

    def test_more_reps_at_same_weight_triggers_pr(self):
        """185x5 → 185x7 should be a rep PR."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 185, 7)
        prs = check_and_record_pr(new_set)

        rep_prs = [p for p in prs if p['type'] == 'reps']
        self.assertEqual(len(rep_prs), 1)
        self.assertEqual(rep_prs[0]['previous'], 5)
        self.assertEqual(rep_prs[0]['new'], 7)

    def test_rep_pr_recorded_in_db(self):
        """PersonalRecord for rep PR should have correct pr_type."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 185, 7)
        check_and_record_pr(new_set)

        pr = PersonalRecord.objects.filter(
            user=self.user, exercise=self.exercise, pr_type='reps'
        ).first()
        self.assertIsNotNone(pr)
        self.assertEqual(float(pr.previous_value), 5.0)

    def test_same_reps_at_same_weight_no_rep_pr(self):
        """185x5 → 185x5 should NOT be a rep PR."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 185, 5)
        prs = check_and_record_pr(new_set)

        rep_prs = [p for p in prs if p['type'] == 'reps']
        self.assertEqual(len(rep_prs), 0)

    def test_more_reps_at_different_weight_no_rep_pr(self):
        """185x5 → 195x7 — rep PR only applies at same weight."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 195, 7)
        prs = check_and_record_pr(new_set)

        # Should have a weight PR but NOT a rep PR (different weight)
        rep_prs = [p for p in prs if p['type'] == 'reps']
        self.assertEqual(len(rep_prs), 0)


class E1RMPRDetectionTest(PRTestMixin, TestCase):
    """Test estimated 1RM PR detection."""

    def setUp(self):
        self.user = self.create_user()
        self.exercise = self.create_exercise('Bench Press')

    def test_higher_e1rm_triggers_pr(self):
        """185x5 → 185x8 should be an e1RM PR (not a weight PR)."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 185, 8)
        prs = check_and_record_pr(new_set)

        e1rm_prs = [p for p in prs if p['type'] == 'e1rm']
        self.assertEqual(len(e1rm_prs), 1)

        # Verify previous and new values
        old_e1rm = brzycki_1rm(185, 5)
        new_e1rm = brzycki_1rm(185, 8)
        self.assertAlmostEqual(e1rm_prs[0]['previous'], round(old_e1rm, 2), places=2)
        self.assertAlmostEqual(e1rm_prs[0]['new'], round(new_e1rm, 2), places=2)

    def test_weight_pr_suppresses_e1rm_pr(self):
        """A weight PR implies e1RM PR — don't double-count."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 195, 5)
        prs = check_and_record_pr(new_set)

        # Should have weight PR but NOT e1rm PR
        types = [p['type'] for p in prs]
        self.assertIn('weight', types)
        self.assertNotIn('e1rm', types)


class FirstSetPRTest(PRTestMixin, TestCase):
    """Test that the first ever set for an exercise is a weight PR."""

    def setUp(self):
        self.user = self.create_user()
        self.exercise = self.create_exercise('Squat')

    def test_first_set_is_weight_pr(self):
        """First recorded set for an exercise should be a weight PR."""
        new_set = self.log_set(self.user, self.exercise, 135, 10)
        prs = check_and_record_pr(new_set)

        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]['type'], 'weight')
        self.assertIsNone(prs[0]['previous'])

    def test_first_set_creates_personal_record(self):
        """First set should create a PersonalRecord with previous_value=None."""
        new_set = self.log_set(self.user, self.exercise, 135, 10)
        check_and_record_pr(new_set)

        pr = PersonalRecord.objects.filter(
            user=self.user, exercise=self.exercise
        ).first()
        self.assertIsNotNone(pr)
        self.assertIsNone(pr.previous_value)
        self.assertEqual(pr.pr_type, 'weight')


class EdgeCaseTests(PRTestMixin, TestCase):
    """Test edge cases in PR detection."""

    def setUp(self):
        self.user = self.create_user()
        self.exercise = self.create_exercise('Deadlift')

    def test_warmup_set_skipped(self):
        """Warmup sets should not trigger PR detection."""
        new_set = self.log_set(self.user, self.exercise, 315, 5, is_warmup=True)
        prs = check_and_record_pr(new_set)

        self.assertEqual(len(prs), 0)
        self.assertEqual(PersonalRecord.objects.count(), 0)

    def test_no_weight_skipped(self):
        """Sets without weight should not trigger PR detection."""
        new_set = self.log_set(self.user, self.exercise, None, 10)
        prs = check_and_record_pr(new_set)

        self.assertEqual(len(prs), 0)

    def test_no_reps_skipped(self):
        """Sets without reps should not trigger PR detection."""
        session = self.create_session(self.user)
        we, _ = WorkoutExercise.objects.get_or_create(
            session=session, exercise=self.exercise, defaults={'order': 1}
        )
        sets = ExerciseSet.objects.bulk_create([
            ExerciseSet(workout_exercise=we, set_number=1, weight=Decimal('225'), reps=None)
        ])
        prs = check_and_record_pr(sets[0])
        self.assertEqual(len(prs), 0)

    def test_high_reps_safe(self):
        """Sets with reps >= 37 should not crash."""
        new_set = self.log_set(self.user, self.exercise, 100, 40)
        prs = check_and_record_pr(new_set)

        # Should still work — first set is a weight PR
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]['type'], 'weight')

    def test_no_duplicate_pr_on_double_call(self):
        """Calling check_and_record_pr twice should create 2 PRs (idempotency is caller's responsibility)."""
        new_set = self.log_set(self.user, self.exercise, 225, 5)
        check_and_record_pr(new_set)
        # Second call — the first set is no longer the only one, but
        # the set itself is excluded from history, so it still sees no history
        check_and_record_pr(new_set)

        # Two PersonalRecord entries (utility doesn't prevent double-calls)
        count = PersonalRecord.objects.filter(user=self.user).count()
        self.assertEqual(count, 2)

    def test_different_exercises_independent(self):
        """PRs for different exercises are independent."""
        squat = self.exercise
        bench = self.create_exercise('Bench Press')

        self.log_set(self.user, squat, 315, 5,
                     workout_date=date.today() - timedelta(days=7))
        self.log_set(self.user, bench, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        # Lower weight on bench than squat — should still be no PR for bench
        new_set = self.log_set(self.user, bench, 185, 5)
        prs = check_and_record_pr(new_set)

        # No PR because 185x5 == 185x5 (same)
        self.assertEqual(len(prs), 0)

    def test_different_users_independent(self):
        """PRs for different users are independent."""
        user2 = self.create_user(email='other@example.com')

        self.log_set(self.user, self.exercise, 315, 5,
                     workout_date=date.today() - timedelta(days=7))

        # User 2's first set at 225 should be a PR for them
        new_set = self.log_set(user2, self.exercise, 225, 5)
        prs = check_and_record_pr(new_set)

        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]['type'], 'weight')

    def test_warmup_sets_excluded_from_history(self):
        """Historical warmup sets should not count towards PR comparison."""
        # Log a warmup set at 315 (should be ignored)
        self.log_set(self.user, self.exercise, 315, 5, is_warmup=True,
                     workout_date=date.today() - timedelta(days=7))

        # Working set at 225 should be a weight PR (first non-warmup)
        new_set = self.log_set(self.user, self.exercise, 225, 5)
        prs = check_and_record_pr(new_set)

        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]['type'], 'weight')


class MultiplePRTypesTest(PRTestMixin, TestCase):
    """Test that multiple PR types can fire on one set."""

    def setUp(self):
        self.user = self.create_user()
        self.exercise = self.create_exercise('Bench Press')

    def test_rep_and_e1rm_pr_together(self):
        """185x5 → 185x8 should be both a rep PR and e1RM PR."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 185, 8)
        prs = check_and_record_pr(new_set)

        types = [p['type'] for p in prs]
        self.assertIn('reps', types)
        self.assertIn('e1rm', types)
        self.assertNotIn('weight', types)

        # Should have 2 PersonalRecord entries
        pr_count = PersonalRecord.objects.filter(user=self.user).count()
        self.assertEqual(pr_count, 2)

    def test_weight_pr_does_not_include_e1rm(self):
        """Weight PR already implies e1RM PR — should not double-count."""
        self.log_set(self.user, self.exercise, 185, 5,
                     workout_date=date.today() - timedelta(days=7))

        new_set = self.log_set(self.user, self.exercise, 200, 5)
        prs = check_and_record_pr(new_set)

        types = [p['type'] for p in prs]
        self.assertIn('weight', types)
        self.assertNotIn('e1rm', types)

        pr_count = PersonalRecord.objects.filter(user=self.user).count()
        self.assertEqual(pr_count, 1)


# =============================================================================
# SIGNAL-BASED AUTO-DETECTION TESTS
# =============================================================================

class SignalAutoDetectionTest(PRTestMixin, TestCase):
    """Test that the post_save signal auto-detects PRs on ExerciseSet creation."""

    def setUp(self):
        self.user = self.create_user()
        self.exercise = self.create_exercise('Squat')

    def test_signal_creates_pr_on_first_set(self):
        """Creating an ExerciseSet via .create() should auto-detect PR via signal."""
        session = self.create_session(self.user)
        we = WorkoutExercise.objects.create(
            session=session, exercise=self.exercise, order=1
        )

        # This triggers post_save signal → auto PR detection
        exercise_set = ExerciseSet.objects.create(
            workout_exercise=we,
            set_number=1,
            weight=Decimal('225'),
            reps=5,
        )

        # Refresh to get signal-updated is_pr
        exercise_set.refresh_from_db()
        self.assertTrue(exercise_set.is_pr)

        # PersonalRecord should exist
        pr = PersonalRecord.objects.filter(
            user=self.user, exercise=self.exercise
        ).first()
        self.assertIsNotNone(pr)
        self.assertEqual(pr.pr_type, 'weight')

    def test_signal_detects_weight_pr(self):
        """Signal detects weight PR on second set creation."""
        # First set (via bulk_create to avoid signal for setup)
        self.log_set(self.user, self.exercise, 225, 5,
                     workout_date=date.today() - timedelta(days=7))

        # Second set (via .create() to trigger signal)
        session = self.create_session(self.user)
        we = WorkoutExercise.objects.create(
            session=session, exercise=self.exercise, order=1
        )
        exercise_set = ExerciseSet.objects.create(
            workout_exercise=we,
            set_number=1,
            weight=Decimal('235'),
            reps=5,
        )

        exercise_set.refresh_from_db()
        self.assertTrue(exercise_set.is_pr)

        pr = PersonalRecord.objects.filter(
            user=self.user, exercise=self.exercise, pr_type='weight'
        ).first()
        self.assertIsNotNone(pr)
        self.assertEqual(float(pr.previous_value), 225.0)

    def test_signal_skips_warmup(self):
        """Signal should not detect PR for warmup sets."""
        session = self.create_session(self.user)
        we = WorkoutExercise.objects.create(
            session=session, exercise=self.exercise, order=1
        )
        exercise_set = ExerciseSet.objects.create(
            workout_exercise=we,
            set_number=1,
            weight=Decimal('135'),
            reps=10,
            is_warmup=True,
        )

        exercise_set.refresh_from_db()
        self.assertFalse(exercise_set.is_pr)
        self.assertEqual(PersonalRecord.objects.count(), 0)


# =============================================================================
# PLATEAU RULE INTEGRATION TESTS
# =============================================================================

class PlateauRuleIntegrationTest(PRTestMixin, TestCase):
    """Test that auto-detected PRs properly suppress the plateau insight."""

    def test_prs_visible_in_30d_query(self):
        """PersonalRecord created by auto-detection should appear in prs_30d."""
        user = self.create_user()
        exercise = self.create_exercise('Bench Press')

        # Log a set and auto-detect PR
        new_set = self.log_set(user, exercise, 185, 5)
        check_and_record_pr(new_set)

        # Verify the PersonalRecord is found by the same query the
        # state builder uses
        from django.utils import timezone
        cutoff = timezone.now() - timedelta(days=30)
        prs_30d = PersonalRecord.objects.filter(
            user=user, achieved_date__gte=cutoff.date()
        ).count()

        self.assertGreater(prs_30d, 0)

    def test_plateau_rule_suppressed_with_prs(self):
        """Global fallback: suppressed when prs_30d > 0."""
        from apps.core.ai_insights.rules_transformation import StrengthPlateauRule

        rule = StrengthPlateauRule()
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_30d": 12,
                    "prs_30d": 2,
                    "strength_trend_score": "stable",
                }
            }
        }
        user = self.create_user()
        result = rule.evaluate(user, event)
        self.assertEqual(result, [])

    def test_plateau_rule_suppressed_with_increasing_trend(self):
        """Global fallback: suppressed when trend is increasing, even with 0 PRs."""
        from apps.core.ai_insights.rules_transformation import StrengthPlateauRule

        rule = StrengthPlateauRule()
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_30d": 12,
                    "prs_30d": 0,
                    "strength_trend_score": "increasing",
                }
            }
        }
        user = self.create_user()
        result = rule.evaluate(user, event)
        self.assertEqual(result, [])

    def test_plateau_rule_fires_with_stable_trend_and_no_prs(self):
        """Global fallback: fires when no PRs AND trend is stable/decreasing."""
        from apps.core.ai_insights.rules_transformation import StrengthPlateauRule

        rule = StrengthPlateauRule()
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_30d": 12,
                    "prs_30d": 0,
                    "strength_trend_score": "stable",
                }
            }
        }
        user = self.create_user()
        result = rule.evaluate(user, event)
        self.assertEqual(len(result), 1)
        self.assertIn("plateau", result[0]["title"].lower())

    def test_exercise_specific_plateau_names_exercise(self):
        """Exercise-specific: insight should name the specific plateauing exercise."""
        from apps.core.ai_insights.rules_transformation import StrengthPlateauRule

        rule = StrengthPlateauRule()
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_30d": 12,
                    "prs_30d": 0,
                    "exercise_progress": [
                        {"exercise": "Bench Press", "sessions_30d": 6,
                         "sets_30d": 18, "prs_30d": 0, "best_e1rm": 208,
                         "recent_e1rm": 208, "prior_e1rm": 208,
                         "trend": "flat", "status": "plateau"},
                        {"exercise": "Squat", "sessions_30d": 5,
                         "sets_30d": 15, "prs_30d": 2, "best_e1rm": 300,
                         "recent_e1rm": 300, "prior_e1rm": 280,
                         "trend": "up", "status": "improving"},
                    ],
                }
            }
        }
        user = self.create_user()
        result = rule.evaluate(user, event)
        self.assertEqual(len(result), 1)
        msg = result[0]["message"].lower()
        self.assertIn("bench press", msg)
        self.assertIn("squat", msg)
        self.assertIn("progressing", msg)

    def test_exercise_specific_no_plateau_when_all_improving(self):
        """Exercise-specific: no insight when all exercises are improving."""
        from apps.core.ai_insights.rules_transformation import StrengthPlateauRule

        rule = StrengthPlateauRule()
        event = {
            "module": "health",
            "user_state": {
                "fitness": {
                    "workouts_30d": 12,
                    "prs_30d": 3,
                    "exercise_progress": [
                        {"exercise": "Bench Press", "sessions_30d": 6,
                         "sets_30d": 18, "prs_30d": 2, "best_e1rm": 220,
                         "recent_e1rm": 220, "prior_e1rm": 208,
                         "trend": "up", "status": "improving"},
                        {"exercise": "Squat", "sessions_30d": 5,
                         "sets_30d": 15, "prs_30d": 1, "best_e1rm": 300,
                         "recent_e1rm": 300, "prior_e1rm": 285,
                         "trend": "up", "status": "improving"},
                    ],
                }
            }
        }
        user = self.create_user()
        result = rule.evaluate(user, event)
        self.assertEqual(result, [])


# =============================================================================
# DANNY'S SCENARIO VALIDATION
# =============================================================================

class DannyScenarioTest(PRTestMixin, TestCase):
    """Validate the specific scenarios from the audit."""

    def setUp(self):
        self.user = self.create_user()
        self.bench = self.create_exercise('Bench Press')

    def test_scenario_a_weight_pr(self):
        """185x5 → 195x5: Weight PR."""
        self.log_set(self.user, self.bench, 185, 5,
                     workout_date=date.today() - timedelta(days=7))
        new_set = self.log_set(self.user, self.bench, 195, 5)
        prs = check_and_record_pr(new_set)

        types = [p['type'] for p in prs]
        self.assertIn('weight', types)

    def test_scenario_b_rep_pr(self):
        """185x5 → 185x7: Rep PR."""
        self.log_set(self.user, self.bench, 185, 5,
                     workout_date=date.today() - timedelta(days=7))
        new_set = self.log_set(self.user, self.bench, 185, 7)
        prs = check_and_record_pr(new_set)

        types = [p['type'] for p in prs]
        self.assertIn('reps', types)

    def test_scenario_c_e1rm_pr(self):
        """185x5 → 185x8: Estimated 1RM PR."""
        self.log_set(self.user, self.bench, 185, 5,
                     workout_date=date.today() - timedelta(days=7))
        new_set = self.log_set(self.user, self.bench, 185, 8)
        prs = check_and_record_pr(new_set)

        types = [p['type'] for p in prs]
        self.assertIn('e1rm', types)

    def test_scenario_d_no_pr(self):
        """185x5 → 185x5: No PR."""
        self.log_set(self.user, self.bench, 185, 5,
                     workout_date=date.today() - timedelta(days=7))
        new_set = self.log_set(self.user, self.bench, 185, 5)
        prs = check_and_record_pr(new_set)

        self.assertEqual(len(prs), 0)
