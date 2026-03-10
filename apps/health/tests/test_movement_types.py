# ==============================================================================
# File: test_movement_types.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Tests for exercise movement type classification, bodyweight/time
#              set tracking, volume calculation, and PR detection.
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-03-10
# ==============================================================================
"""
Movement Type Tests

Covers:
1. Exercise classification — movement_type values for known exercises
2. Volume calculation — weighted, bodyweight, time-based
3. save_set_ajax bodyweight — auto-populates bodyweight_used
4. save_set_ajax time — stores duration_seconds
5. save_set_ajax weighted — existing behavior unchanged
6. PR detection time — longest hold PR
7. PR detection bodyweight — rep PR for bodyweight exercises
8. Optional weight for bodyweight — weight stored correctly
9. Template sync — duration_seconds synced on complete
10. Backward compat — existing records unaffected
11. Fitness utilities — volume queries
"""

import json
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.health.models import (
    Exercise,
    ExerciseSet,
    PersonalRecord,
    TemplateExercise,
    TemplateExerciseSet,
    WeightEntry,
    WorkoutExercise,
    WorkoutSession,
    WorkoutTemplate,
)

User = get_user_model()


class MovementTypeTestMixin:
    """Common setup for movement type tests."""

    def create_user(self, email="test@example.com", password="testpass123"):
        user = User.objects.create_user(email=email, password=password)
        from apps.users.models import TermsAcceptance

        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get("TERMS_VERSION", "1.0"),
        )
        user.preferences.has_completed_onboarding = True
        user.preferences.save()
        return user

    def login_user(self, email="test@example.com", password="testpass123"):
        return self.client.login(email=email, password=password)

    def create_exercise(self, name="Bench Press", category="resistance",
                        movement_type="weighted", muscle_group="Chest"):
        return Exercise.objects.create(
            name=name, category=category, movement_type=movement_type,
            muscle_group=muscle_group, is_active=True,
        )

    def create_workout(self, user, date_val=None):
        return WorkoutSession.objects.create(
            user=user,
            date=date_val or date.today(),
            name="Test Workout",
            started_at=timezone.now(),
        )


# =============================================================================
# 1. Exercise Classification
# =============================================================================

class ExerciseClassificationTests(MovementTypeTestMixin, TestCase):
    """Test movement_type classification on exercises."""

    def test_default_movement_type_is_weighted(self):
        exercise = self.create_exercise(name="Squat")
        self.assertEqual(exercise.movement_type, "weighted")

    def test_bodyweight_exercise(self):
        exercise = self.create_exercise(name="Push-ups", movement_type="bodyweight")
        self.assertEqual(exercise.movement_type, "bodyweight")

    def test_time_exercise(self):
        exercise = self.create_exercise(name="Plank", movement_type="time")
        self.assertEqual(exercise.movement_type, "time")

    def test_movement_type_choices(self):
        choices = dict(Exercise.MOVEMENT_TYPE_CHOICES)
        self.assertIn("weighted", choices)
        self.assertIn("bodyweight", choices)
        self.assertIn("time", choices)

    def test_data_migration_classified_pushups(self):
        """Data migration should have set Push-ups as bodyweight."""
        try:
            exercise = Exercise.objects.get(name="Push-ups")
            self.assertEqual(exercise.movement_type, "bodyweight")
        except Exercise.DoesNotExist:
            self.skipTest("Push-ups not in exercise library")

    def test_data_migration_classified_plank(self):
        """Data migration should have set Plank as time."""
        try:
            exercise = Exercise.objects.get(name="Plank")
            self.assertEqual(exercise.movement_type, "time")
        except Exercise.DoesNotExist:
            self.skipTest("Plank not in exercise library")


# =============================================================================
# 2. Volume Calculation
# =============================================================================

class VolumeCalculationTests(MovementTypeTestMixin, TestCase):
    """Test ExerciseSet.volume property for different movement types."""

    def setUp(self):
        self.user = self.create_user()
        self.workout = self.create_workout(self.user)

    def test_weighted_volume(self):
        """weight × reps for weighted exercises."""
        exercise = self.create_exercise(name="Bench")
        we = WorkoutExercise.objects.create(
            session=self.workout, exercise=exercise, order=0
        )
        s = ExerciseSet.objects.create(
            workout_exercise=we, set_number=1,
            weight=Decimal("185.0"), reps=10,
        )
        self.assertAlmostEqual(s.volume, 1850.0)

    def test_bodyweight_volume_with_bodyweight(self):
        """bodyweight_used × reps for bodyweight exercises."""
        exercise = self.create_exercise(name="Push-ups-test", movement_type="bodyweight")
        we = WorkoutExercise.objects.create(
            session=self.workout, exercise=exercise, order=0
        )
        s = ExerciseSet.objects.create(
            workout_exercise=we, set_number=1,
            reps=20, bodyweight_used=Decimal("180.0"),
        )
        self.assertAlmostEqual(s.volume, 3600.0)

    def test_bodyweight_volume_no_bodyweight(self):
        """Volume is 0 if bodyweight_used not recorded."""
        exercise = self.create_exercise(name="Pullup-test", movement_type="bodyweight")
        we = WorkoutExercise.objects.create(
            session=self.workout, exercise=exercise, order=0
        )
        s = ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, reps=10,
        )
        self.assertEqual(s.volume, 0)

    def test_time_volume_is_zero(self):
        """Time-based exercises have no volume concept."""
        exercise = self.create_exercise(name="Plank-test", movement_type="time")
        we = WorkoutExercise.objects.create(
            session=self.workout, exercise=exercise, order=0
        )
        s = ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, duration_seconds=120,
        )
        self.assertEqual(s.volume, 0)

    def test_weighted_with_added_weight_bodyweight(self):
        """Bodyweight exercise with added weight uses weight × reps."""
        exercise = self.create_exercise(name="Weighted-pullup", movement_type="bodyweight")
        we = WorkoutExercise.objects.create(
            session=self.workout, exercise=exercise, order=0
        )
        s = ExerciseSet.objects.create(
            workout_exercise=we, set_number=1,
            weight=Decimal("45.0"), reps=8,
        )
        # weight × reps takes priority
        self.assertAlmostEqual(s.volume, 360.0)

    def test_total_volume_property(self):
        """WorkoutExercise.total_volume sums all non-warmup sets."""
        exercise = self.create_exercise(name="DB Row")
        we = WorkoutExercise.objects.create(
            session=self.workout, exercise=exercise, order=0
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=1,
            weight=Decimal("50.0"), reps=10,
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=2,
            weight=Decimal("50.0"), reps=10,
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=3,
            weight=Decimal("50.0"), reps=8, is_warmup=True,
        )
        # Only non-warmup: 500 + 500 = 1000 (warmup excluded)
        self.assertAlmostEqual(we.total_volume, 1000.0)


# =============================================================================
# 3-5. save_set_ajax Tests
# =============================================================================

class SaveSetAjaxTests(MovementTypeTestMixin, TestCase):
    """Test save_set_ajax endpoint for all movement types."""

    def setUp(self):
        self.user = self.create_user()
        self.login_user()
        self.workout = self.create_workout(self.user)

    def _save_set(self, payload):
        return self.client.post(
            "/health/physical/fitness/api/save-set/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_weighted_set_save(self):
        """Standard weighted set saves weight and reps."""
        exercise = self.create_exercise(name="Squat-test")
        resp = self._save_set({
            "workout_id": self.workout.pk,
            "exercise_id": exercise.pk,
            "set_number": 1,
            "weight": 225,
            "reps": 5,
            "movement_type": "weighted",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])

        es = ExerciseSet.objects.get(pk=data["set_id"])
        self.assertEqual(float(es.weight), 225.0)
        self.assertEqual(es.reps, 5)
        self.assertIsNone(es.duration_seconds)

    def test_bodyweight_set_auto_fetches_bodyweight(self):
        """Bodyweight set auto-populates bodyweight_used from WeightEntry."""
        WeightEntry.objects.create(
            user=self.user,
            value=Decimal("180.5"), unit="lb",
        )
        exercise = self.create_exercise(
            name="Pushup-save-test", movement_type="bodyweight"
        )
        resp = self._save_set({
            "workout_id": self.workout.pk,
            "exercise_id": exercise.pk,
            "set_number": 1,
            "reps": 20,
            "movement_type": "bodyweight",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])

        es = ExerciseSet.objects.get(pk=data["set_id"])
        self.assertEqual(es.reps, 20)
        self.assertIsNone(es.weight)
        # bodyweight_used should be auto-populated
        self.assertIsNotNone(es.bodyweight_used)
        self.assertAlmostEqual(float(es.bodyweight_used), 180.5, places=1)

    def test_bodyweight_set_with_added_weight(self):
        """Bodyweight exercise with optional added weight."""
        exercise = self.create_exercise(
            name="Weighted-dip-test", movement_type="bodyweight"
        )
        resp = self._save_set({
            "workout_id": self.workout.pk,
            "exercise_id": exercise.pk,
            "set_number": 1,
            "weight": 45,
            "reps": 8,
            "movement_type": "bodyweight",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        es = ExerciseSet.objects.get(pk=data["set_id"])
        self.assertEqual(float(es.weight), 45.0)
        self.assertEqual(es.reps, 8)
        # bodyweight_used NOT populated because weight was provided
        self.assertIsNone(es.bodyweight_used)

    def test_time_set_save(self):
        """Time-based set saves duration_seconds."""
        exercise = self.create_exercise(
            name="Plank-save-test", movement_type="time"
        )
        resp = self._save_set({
            "workout_id": self.workout.pk,
            "exercise_id": exercise.pk,
            "set_number": 1,
            "movement_type": "time",
            "duration_seconds": 90,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])

        es = ExerciseSet.objects.get(pk=data["set_id"])
        self.assertEqual(es.duration_seconds, 90)
        self.assertIsNone(es.weight)
        self.assertIsNone(es.reps)


# =============================================================================
# 6-7. PR Detection Tests
# =============================================================================

class TimePRDetectionTests(MovementTypeTestMixin, TestCase):
    """Test PR detection for time-based exercises."""

    def setUp(self):
        self.user = self.create_user()
        self.exercise = self.create_exercise(
            name="Plank-PR-test", movement_type="time"
        )

    def test_first_time_set_is_pr(self):
        """First time-based set is automatically a PR."""
        from apps.health.pr_utils import check_and_record_pr

        workout = self.create_workout(self.user)
        we = WorkoutExercise.objects.create(
            session=workout, exercise=self.exercise, order=0
        )
        s = ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, duration_seconds=60,
        )
        prs = check_and_record_pr(s)
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["type"], "time")
        self.assertEqual(prs[0]["new"], 60)

    def test_longer_hold_beats_pr(self):
        """Longer hold creates a new time PR."""
        from apps.health.pr_utils import check_and_record_pr

        # First workout — establish baseline
        w1 = self.create_workout(self.user, date.today() - timedelta(days=1))
        we1 = WorkoutExercise.objects.create(
            session=w1, exercise=self.exercise, order=0
        )
        s1 = ExerciseSet.objects.create(
            workout_exercise=we1, set_number=1, duration_seconds=60,
        )
        check_and_record_pr(s1)

        # Second workout — beat PR
        w2 = self.create_workout(self.user)
        we2 = WorkoutExercise.objects.create(
            session=w2, exercise=self.exercise, order=0
        )
        s2 = ExerciseSet.objects.create(
            workout_exercise=we2, set_number=1, duration_seconds=90,
        )
        prs = check_and_record_pr(s2)
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["type"], "time")
        self.assertEqual(prs[0]["previous"], 60)
        self.assertEqual(prs[0]["new"], 90)

    def test_shorter_hold_no_pr(self):
        """Shorter hold does not create a PR."""
        from apps.health.pr_utils import check_and_record_pr

        w1 = self.create_workout(self.user, date.today() - timedelta(days=1))
        we1 = WorkoutExercise.objects.create(
            session=w1, exercise=self.exercise, order=0
        )
        s1 = ExerciseSet.objects.create(
            workout_exercise=we1, set_number=1, duration_seconds=90,
        )
        check_and_record_pr(s1)

        w2 = self.create_workout(self.user)
        we2 = WorkoutExercise.objects.create(
            session=w2, exercise=self.exercise, order=0
        )
        s2 = ExerciseSet.objects.create(
            workout_exercise=we2, set_number=1, duration_seconds=60,
        )
        prs = check_and_record_pr(s2)
        self.assertEqual(len(prs), 0)

    def test_time_pr_record_created(self):
        """Time PR creates a PersonalRecord with duration_seconds."""
        from apps.health.pr_utils import check_and_record_pr

        workout = self.create_workout(self.user)
        we = WorkoutExercise.objects.create(
            session=workout, exercise=self.exercise, order=0
        )
        s = ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, duration_seconds=120,
        )
        check_and_record_pr(s)

        # May have multiple PRs from signal + manual call; check latest
        pr = PersonalRecord.objects.filter(
            user=self.user, exercise=self.exercise, pr_type="time"
        ).order_by("-achieved_date").first()
        self.assertIsNotNone(pr)
        self.assertEqual(pr.duration_seconds, 120)
        self.assertIsNone(pr.weight)
        self.assertIsNone(pr.reps)


class BodyweightPRDetectionTests(MovementTypeTestMixin, TestCase):
    """Test PR detection for bodyweight exercises."""

    def setUp(self):
        self.user = self.create_user()
        self.exercise = self.create_exercise(
            name="Pullup-PR-test", movement_type="bodyweight"
        )

    def test_first_bodyweight_set_is_pr(self):
        """First bodyweight set is automatically a rep PR."""
        from apps.health.pr_utils import check_and_record_pr

        workout = self.create_workout(self.user)
        we = WorkoutExercise.objects.create(
            session=workout, exercise=self.exercise, order=0
        )
        s = ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, reps=10,
        )
        prs = check_and_record_pr(s)
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["type"], "reps")
        self.assertEqual(prs[0]["new"], 10)

    def test_more_reps_beats_pr(self):
        """More reps beats the bodyweight rep PR."""
        from apps.health.pr_utils import check_and_record_pr

        w1 = self.create_workout(self.user, date.today() - timedelta(days=1))
        we1 = WorkoutExercise.objects.create(
            session=w1, exercise=self.exercise, order=0
        )
        s1 = ExerciseSet.objects.create(
            workout_exercise=we1, set_number=1, reps=10,
        )
        check_and_record_pr(s1)

        w2 = self.create_workout(self.user)
        we2 = WorkoutExercise.objects.create(
            session=w2, exercise=self.exercise, order=0
        )
        s2 = ExerciseSet.objects.create(
            workout_exercise=we2, set_number=1, reps=15,
        )
        prs = check_and_record_pr(s2)
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0]["type"], "reps")
        self.assertEqual(prs[0]["previous"], 10)
        self.assertEqual(prs[0]["new"], 15)


# =============================================================================
# 8. Template Sync Tests
# =============================================================================

class TemplateSyncTests(MovementTypeTestMixin, TestCase):
    """Test workout data syncs back to template including duration_seconds."""

    def setUp(self):
        self.user = self.create_user()

    def test_time_exercise_syncs_duration(self):
        """Completing a workout syncs duration_seconds to template."""
        from apps.health.views import _sync_workout_to_template

        exercise = self.create_exercise(name="Plank-sync", movement_type="time")
        template = WorkoutTemplate.objects.create(
            user=self.user, name="Core Template"
        )
        te = TemplateExercise.objects.create(
            template=template, exercise=exercise, order=0, default_sets=1
        )

        workout = WorkoutSession.objects.create(
            user=self.user, date=date.today(), name="Test",
            started_at=timezone.now(),
            completed_at=timezone.now(),
            from_template=template,
        )
        we = WorkoutExercise.objects.create(
            session=workout, exercise=exercise, order=0
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, duration_seconds=90,
        )

        _sync_workout_to_template(workout)

        tes = TemplateExerciseSet.objects.get(
            template_exercise=te, set_number=1
        )
        self.assertEqual(tes.duration_seconds, 90)

    def test_weighted_exercise_sync_unchanged(self):
        """Standard weighted exercise template sync still works."""
        from apps.health.views import _sync_workout_to_template

        exercise = self.create_exercise(name="Bench-sync")
        template = WorkoutTemplate.objects.create(
            user=self.user, name="Push Template"
        )
        te = TemplateExercise.objects.create(
            template=template, exercise=exercise, order=0, default_sets=3
        )

        workout = WorkoutSession.objects.create(
            user=self.user, date=date.today(), name="Test",
            started_at=timezone.now(),
            completed_at=timezone.now(),
            from_template=template,
        )
        we = WorkoutExercise.objects.create(
            session=workout, exercise=exercise, order=0
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=1,
            weight=Decimal("185.0"), reps=8,
        )

        _sync_workout_to_template(workout)

        tes = TemplateExerciseSet.objects.get(
            template_exercise=te, set_number=1
        )
        self.assertEqual(float(tes.weight), 185.0)
        self.assertEqual(tes.reps, 8)
        self.assertIsNone(tes.duration_seconds)


# =============================================================================
# 9. Backward Compatibility
# =============================================================================

class BackwardCompatTests(MovementTypeTestMixin, TestCase):
    """Ensure existing records are unaffected by movement type changes."""

    def test_existing_weighted_sets_unaffected(self):
        """Existing weighted sets still calculate volume correctly."""
        user = self.create_user()
        workout = self.create_workout(user)
        exercise = self.create_exercise(name="Deadlift-compat")
        we = WorkoutExercise.objects.create(
            session=workout, exercise=exercise, order=0
        )
        s = ExerciseSet.objects.create(
            workout_exercise=we, set_number=1,
            weight=Decimal("315.0"), reps=5,
        )
        self.assertAlmostEqual(s.volume, 1575.0)
        self.assertIsNone(s.duration_seconds)
        self.assertIsNone(s.bodyweight_used)

    def test_exercise_default_movement_type(self):
        """New exercises default to 'weighted'."""
        exercise = Exercise.objects.create(
            name="New Exercise", category="resistance"
        )
        self.assertEqual(exercise.movement_type, "weighted")

    def test_pr_type_choices_include_time(self):
        """PR_TYPE_CHOICES includes the new 'time' option."""
        choices = dict(PersonalRecord.PR_TYPE_CHOICES)
        self.assertIn("time", choices)
        self.assertEqual(choices["time"], "Longest Hold")

    def test_model_str_methods(self):
        """Updated __str__ methods work for all types."""
        user = self.create_user()
        exercise = self.create_exercise(name="Plank-str", movement_type="time")
        workout = self.create_workout(user)
        we = WorkoutExercise.objects.create(
            session=workout, exercise=exercise, order=0
        )

        # Time-based set
        s = ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, duration_seconds=90,
        )
        self.assertEqual(str(s), "Set 1: 1:30")

        # Time PR
        pr = PersonalRecord.objects.create(
            user=user, exercise=exercise, achieved_date=date.today(),
            pr_type="time", duration_seconds=120,
        )
        self.assertIn("2:00", str(pr))
        self.assertIn("Longest Hold", str(pr))

        # Template set
        template = WorkoutTemplate.objects.create(
            user=user, name="Test"
        )
        te = TemplateExercise.objects.create(
            template=template, exercise=exercise, order=0
        )
        tes = TemplateExerciseSet.objects.create(
            template_exercise=te, set_number=1, duration_seconds=60,
        )
        self.assertEqual(str(tes), "Set 1: 1:00")


# =============================================================================
# 10. Fitness Utilities
# =============================================================================

class FitnessUtilsTests(MovementTypeTestMixin, TestCase):
    """Test fitness query utilities."""

    def setUp(self):
        self.user = self.create_user()

    def test_get_weekly_volume(self):
        """Get weekly volume calculation."""
        from apps.health.services.fitness_utils import get_weekly_volume

        today = date.today()
        monday = today - timedelta(days=today.weekday())

        workout = WorkoutSession.objects.create(
            user=self.user, date=monday, name="Test",
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        exercise = self.create_exercise(name="Squat-vol")
        we = WorkoutExercise.objects.create(
            session=workout, exercise=exercise, order=0
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=1,
            weight=Decimal("225.0"), reps=5,
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=2,
            weight=Decimal("225.0"), reps=5,
        )

        result = get_weekly_volume(self.user, monday)
        self.assertAlmostEqual(result["total_volume"], 2250.0)
        self.assertEqual(result["set_count"], 2)
        self.assertEqual(result["workout_count"], 1)

    def test_get_longest_hold(self):
        """Get longest hold for a time-based exercise."""
        from apps.health.services.fitness_utils import get_longest_hold

        exercise = self.create_exercise(name="Plank-hold", movement_type="time")

        workout = WorkoutSession.objects.create(
            user=self.user, date=date.today(), name="Core",
            started_at=timezone.now(),
            completed_at=timezone.now(),
        )
        we = WorkoutExercise.objects.create(
            session=workout, exercise=exercise, order=0
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=1, duration_seconds=60,
        )
        ExerciseSet.objects.create(
            workout_exercise=we, set_number=2, duration_seconds=90,
        )

        result = get_longest_hold(self.user, exercise)
        self.assertEqual(result, 90)

    def test_get_longest_hold_no_data(self):
        """Returns None when no time-based sets exist."""
        from apps.health.services.fitness_utils import get_longest_hold

        exercise = self.create_exercise(name="Plank-no-data", movement_type="time")
        result = get_longest_hold(self.user, exercise)
        self.assertIsNone(result)

    def test_get_personal_bests(self):
        """Retrieves all PR types for an exercise."""
        from apps.health.services.fitness_utils import get_personal_bests

        exercise = self.create_exercise(name="Bench-PB")
        workout = self.create_workout(self.user)

        PersonalRecord.objects.create(
            user=self.user, exercise=exercise,
            weight=Decimal("225.0"), reps=5,
            achieved_date=date.today(),
            workout_session=workout,
            pr_type="weight",
        )

        bests = get_personal_bests(self.user, exercise)
        self.assertIsNotNone(bests["weight"])
        self.assertEqual(bests["weight"]["value"], 225.0)


# =============================================================================
# 11. Rest Timer Consistency Tests
# =============================================================================

class RestTimerConsistencyTests(MovementTypeTestMixin, TestCase):
    """
    Verify rest timer behavior is consistent across all exercise types.

    The rest timer is a client-side JavaScript feature. These tests verify:
    1. The JS template contains a centralized onSetCompleted() that calls
       startRestTimer(), and both markSetDone/markTimeDone use it.
    2. The save-set API returns success=True for all movement types,
       which is the trigger that causes onSetCompleted() to fire.
    3. The four timer functions are present and structurally intact.
    """

    def setUp(self):
        self.user = self.create_user()
        self.login_user()
        self.workout = self.create_workout(self.user)

    def _get_template_content(self):
        """Load the workout form template content for JS analysis."""
        import os
        template_path = os.path.join(
            settings.BASE_DIR, "templates", "health", "fitness", "workout_form.html"
        )
        with open(template_path, "r") as f:
            return f.read()

    # ---- JS structure tests (template analysis) ----

    def test_onSetCompleted_function_exists(self):
        """Centralized onSetCompleted() function must exist."""
        content = self._get_template_content()
        self.assertIn("function onSetCompleted(setRow)", content)

    def test_onSetCompleted_calls_startRestTimer(self):
        """onSetCompleted() must call startRestTimer()."""
        content = self._get_template_content()
        # Find the onSetCompleted function body
        start = content.index("function onSetCompleted(setRow)")
        # Find the next function definition (closing brace area)
        block = content[start:start + 300]
        self.assertIn("startRestTimer()", block)

    def test_markSetDone_calls_onSetCompleted(self):
        """markSetDone() (weighted/bodyweight) must call onSetCompleted()."""
        content = self._get_template_content()
        start = content.index("async function markSetDone(")
        end = content.index("async function markCardioDone(")
        block = content[start:end]
        self.assertIn("onSetCompleted(setRow)", block)
        # Must NOT directly call startRestTimer — that's onSetCompleted's job
        # (The only startRestTimer call should be inside onSetCompleted)
        self.assertNotIn("startRestTimer()", block,
            "markSetDone should call onSetCompleted, not startRestTimer directly")

    def test_markTimeDone_calls_onSetCompleted(self):
        """markTimeDone() (time-based) must call onSetCompleted()."""
        content = self._get_template_content()
        start = content.index("async function markTimeDone(")
        end = content.index("function addExercise()")
        block = content[start:end]
        self.assertIn("onSetCompleted(setRow)", block)
        # Must NOT directly call startRestTimer
        self.assertNotIn("startRestTimer()", block,
            "markTimeDone should call onSetCompleted, not startRestTimer directly")

    def test_startRestTimer_called_only_in_onSetCompleted(self):
        """startRestTimer() invocations must only be inside onSetCompleted."""
        content = self._get_template_content()
        # Count all startRestTimer() calls (excluding the function definition line)
        import re
        # Match startRestTimer() calls, not the function definition
        calls = re.findall(r'(?<!function )startRestTimer\(\)', content)
        # Should be exactly 1 call: inside onSetCompleted
        self.assertEqual(len(calls), 1,
            f"startRestTimer() should be called exactly once (inside onSetCompleted), "
            f"found {len(calls)} calls")

    def test_timer_functions_present(self):
        """All four timer functions must be present in the template."""
        content = self._get_template_content()
        self.assertIn("function startRestTimer()", content)
        self.assertIn("function stopRestTimer()", content)
        self.assertIn("function dismissRestTimer()", content)
        self.assertIn("function formatTime(seconds)", content)

    # ---- API consistency tests (all types return success) ----

    def _save_set(self, payload):
        return self.client.post(
            "/health/physical/fitness/api/save-set/",
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_weighted_set_returns_success(self):
        """Weighted set save returns success=True (triggers rest timer)."""
        exercise = self.create_exercise(name="Bench-timer", movement_type="weighted")
        resp = self._save_set({
            "workout_id": self.workout.pk,
            "exercise_id": exercise.pk,
            "set_number": 1,
            "weight": 185,
            "reps": 8,
            "movement_type": "weighted",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    def test_bodyweight_set_returns_success(self):
        """Bodyweight set save returns success=True (triggers rest timer)."""
        exercise = self.create_exercise(name="Pullup-timer", movement_type="bodyweight")
        resp = self._save_set({
            "workout_id": self.workout.pk,
            "exercise_id": exercise.pk,
            "set_number": 1,
            "reps": 12,
            "movement_type": "bodyweight",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    def test_time_set_returns_success(self):
        """Time-based set save returns success=True (triggers rest timer)."""
        exercise = self.create_exercise(name="Plank-timer", movement_type="time")
        resp = self._save_set({
            "workout_id": self.workout.pk,
            "exercise_id": exercise.pk,
            "set_number": 1,
            "movement_type": "time",
            "duration_seconds": 60,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["success"])

    def test_all_types_return_identical_success_shape(self):
        """All movement types return the same response shape."""
        exercises = {
            "weighted": self.create_exercise(name="Squat-shape", movement_type="weighted"),
            "bodyweight": self.create_exercise(name="Dip-shape", movement_type="bodyweight"),
            "time": self.create_exercise(name="Hold-shape", movement_type="time"),
        }
        payloads = {
            "weighted": {"weight": 225, "reps": 5, "movement_type": "weighted"},
            "bodyweight": {"reps": 15, "movement_type": "bodyweight"},
            "time": {"duration_seconds": 45, "movement_type": "time"},
        }

        for mtype, exercise in exercises.items():
            payload = {
                "workout_id": self.workout.pk,
                "exercise_id": exercise.pk,
                "set_number": 1,
                **payloads[mtype],
            }
            resp = self._save_set(payload)
            data = resp.json()
            self.assertEqual(resp.status_code, 200, f"{mtype} failed with {resp.status_code}")
            self.assertTrue(data["success"], f"{mtype} did not return success=True")
            self.assertIn("set_id", data, f"{mtype} missing set_id")
            self.assertIn("workout_exercise_id", data, f"{mtype} missing workout_exercise_id")
