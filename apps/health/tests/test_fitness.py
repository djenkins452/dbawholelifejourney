# ==============================================================================
# File: test_fitness.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Comprehensive tests for fitness CRUD functionality (workouts & templates)
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2025-12-29
# Last Updated: 2025-12-29
# ==============================================================================

"""
Fitness Module - Comprehensive Tests

This test file covers:
1. Workout CRUD (Create, Read, Update, Delete)
2. Workout Template CRUD
3. Exercise and Set management
4. Cardio exercise handling
5. Data isolation between users
6. Personal records tracking
7. Edge cases and validation

Location: apps/health/tests/test_fitness.py
"""

from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.health.models import (
    Exercise,
    WorkoutSession,
    WorkoutExercise,
    ExerciseSet,
    CardioDetails,
    WorkoutTemplate,
    TemplateExercise,
    TemplateExerciseSet,
    PersonalRecord,
)

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class FitnessTestMixin:
    """Common setup for fitness tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def _accept_terms(self, user):
        from django.conf import settings
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(
            user=user,
            terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
        )

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)

    def create_exercise(self, name='Bench Press', category='resistance', muscle_group='Chest'):
        """Helper to create an exercise."""
        return Exercise.objects.create(
            name=name,
            category=category,
            muscle_group=muscle_group if category == 'resistance' else '',
            is_active=True,
        )

    def create_workout(self, user, name='Test Workout', workout_date=None, **kwargs):
        """Helper to create a workout session."""
        if workout_date is None:
            workout_date = date.today()
        return WorkoutSession.objects.create(
            user=user,
            date=workout_date,
            name=name,
            **kwargs
        )

    def create_template(self, user, name='Push Day', **kwargs):
        """Helper to create a workout template."""
        return WorkoutTemplate.objects.create(
            user=user,
            name=name,
            **kwargs
        )


# =============================================================================
# 1. EXERCISE MODEL TESTS
# =============================================================================

class ExerciseModelTest(FitnessTestMixin, TestCase):
    """Tests for the Exercise model."""

    def test_create_resistance_exercise(self):
        """Resistance exercise can be created."""
        exercise = self.create_exercise(
            name='Squat',
            category='resistance',
            muscle_group='Legs'
        )
        self.assertEqual(exercise.name, 'Squat')
        self.assertEqual(exercise.category, 'resistance')
        self.assertEqual(exercise.muscle_group, 'Legs')

    def test_create_cardio_exercise(self):
        """Cardio exercise can be created."""
        exercise = self.create_exercise(
            name='Running',
            category='cardio',
            muscle_group=''
        )
        self.assertEqual(exercise.name, 'Running')
        self.assertEqual(exercise.category, 'cardio')

    def test_exercise_str(self):
        """Exercise string representation."""
        exercise = self.create_exercise(name='Deadlift', muscle_group='Back')
        self.assertIn('Deadlift', str(exercise))

    def test_exercise_ordering(self):
        """Exercises are ordered by category and name."""
        self.create_exercise(name='Cycling', category='cardio', muscle_group='')
        self.create_exercise(name='Bicep Curl', category='resistance', muscle_group='Arms')

        exercises = Exercise.objects.all()
        # Cardio should come after resistance alphabetically
        self.assertEqual(exercises[0].category, 'cardio')


# =============================================================================
# 2. WORKOUT SESSION MODEL TESTS
# =============================================================================

class WorkoutSessionModelTest(FitnessTestMixin, TestCase):
    """Tests for the WorkoutSession model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_workout_session(self):
        """Workout session can be created."""
        workout = self.create_workout(self.user)
        self.assertEqual(workout.user, self.user)
        self.assertEqual(workout.name, 'Test Workout')

    def test_workout_str(self):
        """Workout string representation."""
        workout = self.create_workout(self.user, name='Leg Day')
        self.assertIn('Leg Day', str(workout))

    def test_workout_exercise_count(self):
        """Workout correctly counts exercises."""
        workout = self.create_workout(self.user)
        exercise = self.create_exercise()

        WorkoutExercise.objects.create(
            session=workout,
            exercise=exercise,
            order=0
        )

        self.assertEqual(workout.exercise_count, 1)

    def test_workout_total_sets(self):
        """Workout correctly counts total sets."""
        workout = self.create_workout(self.user)
        exercise = self.create_exercise()

        workout_ex = WorkoutExercise.objects.create(
            session=workout,
            exercise=exercise,
            order=0
        )

        for i in range(3):
            ExerciseSet.objects.create(
                workout_exercise=workout_ex,
                set_number=i + 1,
                weight=Decimal('135.0'),
                reps=10
            )

        self.assertEqual(workout.total_sets, 3)

    def test_workout_total_volume(self):
        """Workout correctly calculates total volume."""
        workout = self.create_workout(self.user)
        exercise = self.create_exercise()

        workout_ex = WorkoutExercise.objects.create(
            session=workout,
            exercise=exercise,
            order=0
        )

        # 3 sets of 10 reps at 100 lbs = 3000 volume
        for i in range(3):
            ExerciseSet.objects.create(
                workout_exercise=workout_ex,
                set_number=i + 1,
                weight=Decimal('100.0'),
                reps=10
            )

        self.assertEqual(workout.total_volume, 3000.0)

    def test_workout_ordering(self):
        """Workouts are ordered by date (most recent first)."""
        self.create_workout(
            self.user,
            name='Old Workout',
            workout_date=date.today() - timedelta(days=7)
        )
        new_workout = self.create_workout(
            self.user,
            name='New Workout',
            workout_date=date.today()
        )

        workouts = WorkoutSession.objects.filter(user=self.user)
        self.assertEqual(workouts[0], new_workout)


# =============================================================================
# 3. WORKOUT TEMPLATE MODEL TESTS
# =============================================================================

class WorkoutTemplateModelTest(FitnessTestMixin, TestCase):
    """Tests for the WorkoutTemplate model."""

    def setUp(self):
        self.user = self.create_user()

    def test_create_template(self):
        """Workout template can be created."""
        template = self.create_template(self.user, name='Upper Body')
        self.assertEqual(template.name, 'Upper Body')
        self.assertEqual(template.user, self.user)

    def test_template_str(self):
        """Template string representation."""
        template = self.create_template(self.user, name='Full Body')
        self.assertIn('Full Body', str(template))

    def test_template_exercise_count(self):
        """Template correctly counts exercises."""
        template = self.create_template(self.user)
        exercise = self.create_exercise()

        TemplateExercise.objects.create(
            template=template,
            exercise=exercise,
            order=0,
            default_sets=4
        )

        self.assertEqual(template.exercise_count, 1)

    def test_template_with_description(self):
        """Template can have a description."""
        template = self.create_template(
            self.user,
            name='Strength Day',
            description='Heavy compound movements'
        )
        self.assertEqual(template.description, 'Heavy compound movements')


# =============================================================================
# 4. WORKOUT CRUD VIEW TESTS
# =============================================================================

class WorkoutCRUDViewTest(FitnessTestMixin, TestCase):
    """Tests for workout CRUD views."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.exercise = self.create_exercise()
        self.login_user()

    def test_workout_list_loads(self):
        """Workout list page loads."""
        response = self.client.get(reverse('health:workout_list'))
        self.assertEqual(response.status_code, 200)

    def test_workout_list_shows_workouts(self):
        """Workout list shows user's workouts."""
        self.create_workout(self.user, name='My Workout')

        response = self.client.get(reverse('health:workout_list'))

        self.assertContains(response, 'My Workout')

    def test_workout_create_page_loads(self):
        """Workout create page loads."""
        response = self.client.get(reverse('health:workout_create'))
        self.assertEqual(response.status_code, 200)

    def test_workout_create_with_exercise(self):
        """Workout can be created with exercises via POST."""
        response = self.client.post(reverse('health:workout_create'), {
            'date': date.today().isoformat(),
            'name': 'New Workout',
            'notes': 'Great session',
            'exercise_id': [str(self.exercise.pk)],
            f'exercise_{self.exercise.pk}_set_1_weight': '135',
            f'exercise_{self.exercise.pk}_set_1_reps': '10',
        })

        # Should redirect to workout detail on success
        self.assertEqual(response.status_code, 302)

        # Verify workout was created
        workout = WorkoutSession.objects.filter(user=self.user, name='New Workout').first()
        self.assertIsNotNone(workout)

    def test_workout_detail_loads(self):
        """Workout detail page loads."""
        workout = self.create_workout(self.user)

        response = self.client.get(reverse('health:workout_detail', kwargs={'pk': workout.pk}))

        self.assertEqual(response.status_code, 200)

    def test_workout_update_page_loads(self):
        """Workout update page loads."""
        workout = self.create_workout(self.user)

        response = self.client.get(reverse('health:workout_update', kwargs={'pk': workout.pk}))

        self.assertEqual(response.status_code, 200)

    def test_workout_update_saves_changes(self):
        """Workout can be updated via POST."""
        workout = self.create_workout(self.user, name='Original Name')

        response = self.client.post(reverse('health:workout_update', kwargs={'pk': workout.pk}), {
            'date': date.today().isoformat(),
            'name': 'Updated Name',
            'notes': '',
        })

        self.assertEqual(response.status_code, 302)

        workout.refresh_from_db()
        self.assertEqual(workout.name, 'Updated Name')

    def test_workout_delete(self):
        """Workout can be deleted via POST."""
        workout = self.create_workout(self.user)

        response = self.client.post(reverse('health:workout_delete', kwargs={'pk': workout.pk}))

        self.assertEqual(response.status_code, 302)

        # Verify soft delete
        workout.refresh_from_db()
        self.assertEqual(workout.status, 'deleted')

    def test_workout_copy_redirects(self):
        """Workout copy redirects to create with copy parameter."""
        workout = self.create_workout(self.user)

        response = self.client.get(reverse('health:workout_copy', kwargs={'pk': workout.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertIn(f'copy={workout.pk}', response.url)


# =============================================================================
# 5. TEMPLATE CRUD VIEW TESTS
# =============================================================================

class TemplateCRUDViewTest(FitnessTestMixin, TestCase):
    """Tests for workout template CRUD views."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.exercise = self.create_exercise()
        self.login_user()

    def test_template_list_loads(self):
        """Template list page loads."""
        response = self.client.get(reverse('health:template_list'))
        self.assertEqual(response.status_code, 200)

    def test_template_list_shows_templates(self):
        """Template list shows user's templates."""
        self.create_template(self.user, name='Push Day')

        response = self.client.get(reverse('health:template_list'))

        self.assertContains(response, 'Push Day')

    def test_template_create_page_loads(self):
        """Template create page loads."""
        response = self.client.get(reverse('health:template_create'))
        self.assertEqual(response.status_code, 200)

    def test_template_create_with_exercise(self):
        """Template can be created with exercises via POST."""
        response = self.client.post(reverse('health:template_create'), {
            'name': 'New Template',
            'description': 'A great template',
            'exercise_id': [str(self.exercise.pk)],
            f'exercise_{self.exercise.pk}_default_sets': '4',
        })

        self.assertEqual(response.status_code, 302)

        template = WorkoutTemplate.objects.filter(user=self.user, name='New Template').first()
        self.assertIsNotNone(template)

    def test_template_detail_loads(self):
        """Template detail page loads."""
        template = self.create_template(self.user)

        response = self.client.get(reverse('health:template_detail', kwargs={'pk': template.pk}))

        self.assertEqual(response.status_code, 200)

    def test_template_update_page_loads(self):
        """Template update page loads."""
        template = self.create_template(self.user)

        response = self.client.get(reverse('health:template_update', kwargs={'pk': template.pk}))

        self.assertEqual(response.status_code, 200)

    def test_template_update_saves_changes(self):
        """Template can be updated via POST."""
        template = self.create_template(self.user, name='Original Template')

        response = self.client.post(reverse('health:template_update', kwargs={'pk': template.pk}), {
            'name': 'Updated Template',
            'description': 'Updated description',
        })

        self.assertEqual(response.status_code, 302)

        template.refresh_from_db()
        self.assertEqual(template.name, 'Updated Template')

    def test_template_delete(self):
        """Template can be deleted via POST."""
        template = self.create_template(self.user)

        response = self.client.post(reverse('health:template_delete', kwargs={'pk': template.pk}))

        self.assertEqual(response.status_code, 302)

        # Verify soft delete
        template.refresh_from_db()
        self.assertEqual(template.status, 'deleted')

    def test_use_template_redirects(self):
        """Use template redirects to create workout with template parameter."""
        template = self.create_template(self.user)

        response = self.client.get(reverse('health:template_use', kwargs={'pk': template.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertIn(f'template={template.pk}', response.url)


# =============================================================================
# 6. DATA ISOLATION TESTS
# =============================================================================

class FitnessDataIsolationTest(FitnessTestMixin, TestCase):
    """Tests to ensure users can only see their own fitness data."""

    def setUp(self):
        self.client = Client()
        self.user_a = self.create_user(email='usera@example.com')
        self.user_b = self.create_user(email='userb@example.com')

        self.workout_a = self.create_workout(self.user_a, name='User A Workout')
        self.workout_b = self.create_workout(self.user_b, name='User B Workout')

        self.template_a = self.create_template(self.user_a, name='User A Template')
        self.template_b = self.create_template(self.user_b, name='User B Template')

    def test_user_sees_only_own_workouts(self):
        """User only sees their own workouts in list."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('health:workout_list'))

        self.assertContains(response, 'User A Workout')
        self.assertNotContains(response, 'User B Workout')

    def test_user_sees_only_own_templates(self):
        """User only sees their own templates in list."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('health:template_list'))

        self.assertContains(response, 'User A Template')
        self.assertNotContains(response, 'User B Template')

    def test_user_cannot_view_other_users_workout(self):
        """User cannot view another user's workout detail."""
        self.client.login(email='usera@example.com', password='testpass123')

        response = self.client.get(
            reverse('health:workout_detail', kwargs={'pk': self.workout_b.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_user_cannot_view_other_users_template(self):
        """User cannot view another user's template detail."""
        self.client.login(email='usera@example.com', password='testpass123')

        response = self.client.get(
            reverse('health:template_detail', kwargs={'pk': self.template_b.pk})
        )

        self.assertEqual(response.status_code, 404)

    def test_user_cannot_delete_other_users_workout(self):
        """User cannot delete another user's workout."""
        self.client.login(email='usera@example.com', password='testpass123')

        response = self.client.post(
            reverse('health:workout_delete', kwargs={'pk': self.workout_b.pk})
        )

        self.assertEqual(response.status_code, 404)

        # Verify workout still exists
        self.workout_b.refresh_from_db()
        self.assertEqual(self.workout_b.status, 'active')

    def test_user_cannot_delete_other_users_template(self):
        """User cannot delete another user's template."""
        self.client.login(email='usera@example.com', password='testpass123')

        response = self.client.post(
            reverse('health:template_delete', kwargs={'pk': self.template_b.pk})
        )

        self.assertEqual(response.status_code, 404)

        # Verify template still exists
        self.template_b.refresh_from_db()
        self.assertEqual(self.template_b.status, 'active')


# =============================================================================
# 7. CARDIO EXERCISE TESTS
# =============================================================================

class CardioExerciseTest(FitnessTestMixin, TestCase):
    """Tests for cardio exercise handling."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.cardio_exercise = self.create_exercise(
            name='Running',
            category='cardio',
            muscle_group=''
        )
        self.login_user()

    def test_cardio_details_created(self):
        """Cardio details can be created for workout exercise."""
        workout = self.create_workout(self.user)

        workout_ex = WorkoutExercise.objects.create(
            session=workout,
            exercise=self.cardio_exercise,
            order=0
        )

        cardio = CardioDetails.objects.create(
            workout_exercise=workout_ex,
            duration_minutes=30,
            distance=Decimal('3.1'),
            intensity='medium'
        )

        self.assertEqual(cardio.duration_minutes, 30)
        self.assertEqual(cardio.distance, Decimal('3.1'))
        self.assertEqual(cardio.intensity, 'medium')

    def test_cardio_str(self):
        """Cardio details string representation."""
        workout = self.create_workout(self.user)
        workout_ex = WorkoutExercise.objects.create(
            session=workout,
            exercise=self.cardio_exercise,
            order=0
        )

        cardio = CardioDetails.objects.create(
            workout_exercise=workout_ex,
            duration_minutes=45,
            intensity='hard'
        )

        self.assertIn('45', str(cardio))


# =============================================================================
# 8. FITNESS HOME VIEW TEST
# =============================================================================

class FitnessHomeViewTest(FitnessTestMixin, TestCase):
    """Tests for the fitness home view."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_fitness_home_requires_login(self):
        """Fitness home requires authentication."""
        self.client.logout()
        response = self.client.get(reverse('health:fitness_home'))
        self.assertEqual(response.status_code, 302)

    def test_fitness_home_loads(self):
        """Fitness home page loads for authenticated user."""
        response = self.client.get(reverse('health:fitness_home'))
        self.assertEqual(response.status_code, 200)

    def test_fitness_home_shows_recent_workouts(self):
        """Fitness home shows recent workouts."""
        self.create_workout(self.user, name='Recent Workout')

        response = self.client.get(reverse('health:fitness_home'))

        self.assertContains(response, 'Recent Workout')

    def test_fitness_home_shows_templates(self):
        """Fitness home shows user's templates."""
        self.create_template(self.user, name='My Template')

        response = self.client.get(reverse('health:fitness_home'))

        self.assertContains(response, 'My Template')


# =============================================================================
# 9. PERSONAL RECORDS TESTS
# =============================================================================

class PersonalRecordsTest(FitnessTestMixin, TestCase):
    """Tests for personal records tracking."""

    def setUp(self):
        self.user = self.create_user()
        self.exercise = self.create_exercise()

    def test_create_personal_record(self):
        """Personal record can be created."""
        workout = self.create_workout(self.user)

        pr = PersonalRecord.objects.create(
            user=self.user,
            exercise=self.exercise,
            weight=Decimal('225.0'),
            reps=5,
            achieved_date=date.today(),
            workout_session=workout
        )

        self.assertEqual(pr.weight, Decimal('225.0'))
        self.assertEqual(pr.reps, 5)

    def test_estimated_1rm_calculation(self):
        """1RM is calculated correctly using Brzycki formula."""
        pr = PersonalRecord.objects.create(
            user=self.user,
            exercise=self.exercise,
            weight=Decimal('200.0'),
            reps=10,
            achieved_date=date.today()
        )

        # Brzycki formula: weight * 36 / (37 - reps)
        # 200 * 36 / (37 - 10) = 200 * 36 / 27 = 266.67
        self.assertAlmostEqual(pr.estimated_1rm, 266.67, delta=0.5)

    def test_single_rep_max_is_weight(self):
        """For 1 rep, estimated 1RM equals weight."""
        pr = PersonalRecord.objects.create(
            user=self.user,
            exercise=self.exercise,
            weight=Decimal('315.0'),
            reps=1,
            achieved_date=date.today()
        )

        self.assertEqual(pr.estimated_1rm, 315.0)


# =============================================================================
# 10. EDGE CASES AND VALIDATION
# =============================================================================

class FitnessEdgeCaseTest(FitnessTestMixin, TestCase):
    """Tests for edge cases and validation."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()

    def test_empty_workout_list(self):
        """Workout list loads with no entries."""
        response = self.client.get(reverse('health:workout_list'))
        self.assertEqual(response.status_code, 200)

    def test_empty_template_list(self):
        """Template list loads with no entries."""
        response = self.client.get(reverse('health:template_list'))
        self.assertEqual(response.status_code, 200)

    def test_workout_with_no_exercises(self):
        """Workout can be created without exercises."""
        workout = self.create_workout(self.user)
        self.assertEqual(workout.exercise_count, 0)
        self.assertEqual(workout.total_volume, 0)

    def test_workout_with_notes(self):
        """Workout can have notes."""
        workout = self.create_workout(self.user, notes='Felt strong today!')
        self.assertEqual(workout.notes, 'Felt strong today!')

    def test_workout_date_in_past(self):
        """Workout can be logged for past dates."""
        past_date = date.today() - timedelta(days=30)
        workout = self.create_workout(self.user, workout_date=past_date)
        self.assertEqual(workout.date, past_date)

    def test_exercise_set_with_zero_weight(self):
        """Exercise set can have zero weight (bodyweight exercises)."""
        workout = self.create_workout(self.user)
        exercise = self.create_exercise(name='Push-ups')

        workout_ex = WorkoutExercise.objects.create(
            session=workout,
            exercise=exercise,
            order=0
        )

        exercise_set = ExerciseSet.objects.create(
            workout_exercise=workout_ex,
            set_number=1,
            weight=None,
            reps=20
        )

        self.assertIsNone(exercise_set.weight)
        self.assertEqual(exercise_set.reps, 20)
        self.assertEqual(exercise_set.volume, 0)


# =============================================================================
# 11. LIVE WORKOUT AJAX ENDPOINTS
# =============================================================================

import json


class LiveWorkoutAjaxTest(FitnessTestMixin, TestCase):
    """Tests for live workout AJAX endpoints (Done button, rest timer)."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
        self.exercise = self.create_exercise()

    def test_start_workout_creates_session(self):
        """POST to start_workout_ajax creates a new workout session."""
        response = self.client.post(
            reverse('health:start_workout_ajax'),
            data=json.dumps({'name': 'Test Workout'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('workout_id', data)
        self.assertFalse(data['is_resumed'])

        # Verify workout created
        workout = WorkoutSession.objects.get(pk=data['workout_id'])
        self.assertEqual(workout.user, self.user)
        self.assertIsNotNone(workout.started_at)
        self.assertIsNone(workout.completed_at)

    def test_start_workout_resumes_existing(self):
        """Starting a workout when one exists today resumes it."""
        # Create an in-progress workout
        existing = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            started_at=timezone.now(),
        )

        response = self.client.post(
            reverse('health:start_workout_ajax'),
            data=json.dumps({}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['workout_id'], existing.pk)
        self.assertTrue(data['is_resumed'])

    def test_start_workout_with_template(self):
        """Starting workout with template_id uses template name."""
        template = self.create_template(self.user, name='Push Day')

        response = self.client.post(
            reverse('health:start_workout_ajax'),
            data=json.dumps({'template_id': template.pk}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        workout = WorkoutSession.objects.get(pk=data['workout_id'])
        self.assertEqual(workout.name, 'Push Day')

    def test_save_set_creates_exercise_and_set(self):
        """save_set_ajax creates WorkoutExercise and ExerciseSet."""
        # Start a workout
        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            started_at=timezone.now(),
        )

        response = self.client.post(
            reverse('health:save_set_ajax'),
            data=json.dumps({
                'workout_id': workout.pk,
                'exercise_id': self.exercise.pk,
                'set_number': 1,
                'weight': 135,
                'reps': 10,
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # Verify set created
        workout_ex = WorkoutExercise.objects.get(session=workout, exercise=self.exercise)
        exercise_set = ExerciseSet.objects.get(workout_exercise=workout_ex, set_number=1)
        self.assertEqual(exercise_set.weight, Decimal('135'))
        self.assertEqual(exercise_set.reps, 10)

    def test_save_set_updates_existing(self):
        """save_set_ajax updates an existing set."""
        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            started_at=timezone.now(),
        )
        workout_ex = WorkoutExercise.objects.create(
            session=workout,
            exercise=self.exercise,
            order=0
        )
        existing_set = ExerciseSet.objects.create(
            workout_exercise=workout_ex,
            set_number=1,
            weight=Decimal('100'),
            reps=8
        )

        # Update the set
        response = self.client.post(
            reverse('health:save_set_ajax'),
            data=json.dumps({
                'workout_id': workout.pk,
                'exercise_id': self.exercise.pk,
                'set_number': 1,
                'weight': 135,
                'reps': 10,
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)

        # Verify updated
        existing_set.refresh_from_db()
        self.assertEqual(existing_set.weight, Decimal('135'))
        self.assertEqual(existing_set.reps, 10)

    def test_save_set_requires_fields(self):
        """save_set_ajax requires workout_id, exercise_id, set_number."""
        response = self.client.post(
            reverse('health:save_set_ajax'),
            data=json.dumps({'workout_id': 1}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn('error', data)

    def test_save_set_validates_workout_ownership(self):
        """save_set_ajax rejects workouts belonging to other users."""
        other_user = self.create_user(email='other@example.com')
        other_workout = WorkoutSession.objects.create(
            user=other_user,
            date=date.today(),
            started_at=timezone.now(),
        )

        response = self.client.post(
            reverse('health:save_set_ajax'),
            data=json.dumps({
                'workout_id': other_workout.pk,
                'exercise_id': self.exercise.pk,
                'set_number': 1,
                'weight': 135,
                'reps': 10,
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 404)

    def test_save_cardio_creates_details(self):
        """save_cardio_ajax creates CardioDetails."""
        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            started_at=timezone.now(),
        )
        cardio_exercise = self.create_exercise(name='Running', category='cardio')

        response = self.client.post(
            reverse('health:save_cardio_ajax'),
            data=json.dumps({
                'workout_id': workout.pk,
                'exercise_id': cardio_exercise.pk,
                'duration': 30,
                'distance': 3.5,
                'intensity': 'medium',
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])

        # Verify cardio created
        workout_ex = WorkoutExercise.objects.get(session=workout, exercise=cardio_exercise)
        cardio = CardioDetails.objects.get(workout_exercise=workout_ex)
        self.assertEqual(cardio.duration_minutes, 30)
        self.assertEqual(cardio.distance, Decimal('3.5'))
        self.assertEqual(cardio.intensity, 'medium')

    def test_complete_workout_sets_completed_at(self):
        """complete_workout_ajax sets completed_at and calculates duration."""
        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            started_at=timezone.now() - timedelta(minutes=45),
        )

        response = self.client.post(
            reverse('health:complete_workout_ajax'),
            data=json.dumps({
                'workout_id': workout.pk,
                'notes': 'Great workout!',
                'name': 'Updated Name',
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('redirect_url', data)

        # Verify workout completed
        workout.refresh_from_db()
        self.assertIsNotNone(workout.completed_at)
        self.assertEqual(workout.notes, 'Great workout!')
        self.assertEqual(workout.name, 'Updated Name')
        self.assertGreater(workout.duration_minutes, 0)

    def test_get_workout_state_returns_exercises(self):
        """get_workout_state_ajax returns saved exercises and sets."""
        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            name='My Workout',
            started_at=timezone.now(),
        )
        workout_ex = WorkoutExercise.objects.create(
            session=workout,
            exercise=self.exercise,
            order=0
        )
        ExerciseSet.objects.create(
            workout_exercise=workout_ex,
            set_number=1,
            weight=Decimal('135'),
            reps=10
        )
        ExerciseSet.objects.create(
            workout_exercise=workout_ex,
            set_number=2,
            weight=Decimal('155'),
            reps=8
        )

        response = self.client.get(
            reverse('health:get_workout_state_ajax', kwargs={'workout_id': workout.pk})
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['workout_id'], workout.pk)
        self.assertEqual(data['name'], 'My Workout')
        self.assertEqual(len(data['exercises']), 1)
        self.assertEqual(len(data['exercises'][0]['sets']), 2)

    def test_ajax_endpoints_require_authentication(self):
        """AJAX endpoints return 401 for unauthenticated users."""
        self.client.logout()

        endpoints = [
            ('health:start_workout_ajax', 'POST', {}),
            ('health:save_set_ajax', 'POST', {}),
            ('health:save_cardio_ajax', 'POST', {}),
            ('health:complete_workout_ajax', 'POST', {}),
        ]

        for url_name, method, data in endpoints:
            if method == 'POST':
                response = self.client.post(
                    reverse(url_name),
                    data=json.dumps(data),
                    content_type='application/json'
                )
            self.assertEqual(response.status_code, 401, f"{url_name} should require auth")


# =============================================================================
# 9. TEMPLATE SYNC TESTS
# =============================================================================

class TemplateSyncTest(FitnessTestMixin, TestCase):
    """
    Tests for template weight/reps syncing functionality.

    When a workout is completed that was created from a template:
    1. The workout's set weights/reps should be synced back to the template
    2. Next time the template is used, those values should pre-populate
    """

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
        self.exercise = self.create_exercise(name='Bench Press')
        self.exercise2 = self.create_exercise(name='Squat', muscle_group='Legs')

    def test_complete_workout_syncs_to_template(self):
        """
        When a workout created from template is completed,
        the weights/reps should be saved to TemplateExerciseSet.
        """
        # Create template with exercise
        template = self.create_template(self.user, name='Push Day')
        template_exercise = TemplateExercise.objects.create(
            template=template,
            exercise=self.exercise,
            order=0,
            default_sets=3
        )

        # Verify no TemplateExerciseSet initially
        self.assertEqual(TemplateExerciseSet.objects.filter(
            template_exercise=template_exercise
        ).count(), 0)

        # Create workout from template
        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            name='Push Day',
            from_template=template,
            started_at=timezone.now() - timedelta(minutes=30),
        )

        # Add exercise with sets
        workout_ex = WorkoutExercise.objects.create(
            session=workout,
            exercise=self.exercise,
            order=0
        )
        ExerciseSet.objects.create(
            workout_exercise=workout_ex,
            set_number=1,
            weight=Decimal('135'),
            reps=10
        )
        ExerciseSet.objects.create(
            workout_exercise=workout_ex,
            set_number=2,
            weight=Decimal('155'),
            reps=8
        )
        ExerciseSet.objects.create(
            workout_exercise=workout_ex,
            set_number=3,
            weight=Decimal('175'),
            reps=6
        )

        # Complete the workout
        response = self.client.post(
            reverse('health:complete_workout_ajax'),
            data=json.dumps({'workout_id': workout.pk}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        # Verify TemplateExerciseSet was created with workout values
        template_sets = TemplateExerciseSet.objects.filter(
            template_exercise=template_exercise
        ).order_by('set_number')

        self.assertEqual(template_sets.count(), 3)

        set1 = template_sets.get(set_number=1)
        self.assertEqual(set1.weight, Decimal('135'))
        self.assertEqual(set1.reps, 10)

        set2 = template_sets.get(set_number=2)
        self.assertEqual(set2.weight, Decimal('155'))
        self.assertEqual(set2.reps, 8)

        set3 = template_sets.get(set_number=3)
        self.assertEqual(set3.weight, Decimal('175'))
        self.assertEqual(set3.reps, 6)

    def test_template_defaults_prepopulate_workout_form(self):
        """
        When creating a workout from a template that has saved defaults,
        those values should appear in template_defaults_json.
        """
        # Create template with exercise and set defaults
        template = self.create_template(self.user, name='Push Day')
        template_exercise = TemplateExercise.objects.create(
            template=template,
            exercise=self.exercise,
            order=0,
            default_sets=3
        )

        # Add set defaults (as if synced from previous workout)
        TemplateExerciseSet.objects.create(
            template_exercise=template_exercise,
            set_number=1,
            weight=Decimal('135'),
            reps=10
        )
        TemplateExerciseSet.objects.create(
            template_exercise=template_exercise,
            set_number=2,
            weight=Decimal('155'),
            reps=8
        )

        # Load workout form with template
        response = self.client.get(
            reverse('health:workout_create') + f'?template={template.pk}'
        )
        self.assertEqual(response.status_code, 200)

        # Verify template_defaults_json is in context
        self.assertIn('template_defaults_json', response.context)

        # Parse the JSON
        import json
        defaults = json.loads(response.context['template_defaults_json'])

        # Verify exercise defaults
        exercise_id = str(self.exercise.pk)
        self.assertIn(exercise_id, defaults)
        self.assertEqual(defaults[exercise_id]['default_sets'], 3)

        # Verify set defaults
        sets = defaults[exercise_id]['sets']
        self.assertEqual(sets['1']['weight'], 135.0)
        self.assertEqual(sets['1']['reps'], 10)
        self.assertEqual(sets['2']['weight'], 155.0)
        self.assertEqual(sets['2']['reps'], 8)

    def test_complete_workout_updates_existing_template_sets(self):
        """
        When completing a second workout from the same template,
        the template set defaults should be updated (not duplicated).
        """
        # Create template with exercise and existing set defaults
        template = self.create_template(self.user, name='Push Day')
        template_exercise = TemplateExercise.objects.create(
            template=template,
            exercise=self.exercise,
            order=0,
            default_sets=3
        )

        # Add initial set defaults
        TemplateExerciseSet.objects.create(
            template_exercise=template_exercise,
            set_number=1,
            weight=Decimal('135'),
            reps=10
        )
        TemplateExerciseSet.objects.create(
            template_exercise=template_exercise,
            set_number=2,
            weight=Decimal('155'),
            reps=8
        )

        # Create new workout from template with different values
        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            name='Push Day',
            from_template=template,
            started_at=timezone.now() - timedelta(minutes=30),
        )

        workout_ex = WorkoutExercise.objects.create(
            session=workout,
            exercise=self.exercise,
            order=0
        )
        ExerciseSet.objects.create(
            workout_exercise=workout_ex,
            set_number=1,
            weight=Decimal('145'),  # Increased from 135
            reps=12  # Increased from 10
        )
        ExerciseSet.objects.create(
            workout_exercise=workout_ex,
            set_number=2,
            weight=Decimal('165'),  # Increased from 155
            reps=10  # Increased from 8
        )

        # Complete the workout
        response = self.client.post(
            reverse('health:complete_workout_ajax'),
            data=json.dumps({'workout_id': workout.pk}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        # Verify template sets were updated, not duplicated
        template_sets = TemplateExerciseSet.objects.filter(
            template_exercise=template_exercise
        )
        self.assertEqual(template_sets.count(), 2)

        set1 = template_sets.get(set_number=1)
        self.assertEqual(set1.weight, Decimal('145'))
        self.assertEqual(set1.reps, 12)

        set2 = template_sets.get(set_number=2)
        self.assertEqual(set2.weight, Decimal('165'))
        self.assertEqual(set2.reps, 10)

    def test_complete_workout_adds_new_sets_to_template(self):
        """
        When workout has more sets than template default,
        the new sets should be added and default_sets updated.
        """
        # Create template with 2 default sets
        template = self.create_template(self.user, name='Push Day')
        template_exercise = TemplateExercise.objects.create(
            template=template,
            exercise=self.exercise,
            order=0,
            default_sets=2
        )

        # Create workout with 4 sets (more than default)
        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            name='Push Day',
            from_template=template,
            started_at=timezone.now() - timedelta(minutes=30),
        )

        workout_ex = WorkoutExercise.objects.create(
            session=workout,
            exercise=self.exercise,
            order=0
        )
        for i in range(1, 5):  # 4 sets
            ExerciseSet.objects.create(
                workout_exercise=workout_ex,
                set_number=i,
                weight=Decimal(str(100 + i * 10)),
                reps=10 - i
            )

        # Complete the workout
        response = self.client.post(
            reverse('health:complete_workout_ajax'),
            data=json.dumps({'workout_id': workout.pk}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        # Verify 4 template sets were created
        template_sets = TemplateExerciseSet.objects.filter(
            template_exercise=template_exercise
        )
        self.assertEqual(template_sets.count(), 4)

        # Verify default_sets was updated to 4
        template_exercise.refresh_from_db()
        self.assertEqual(template_exercise.default_sets, 4)

    def test_workout_without_template_does_not_sync(self):
        """
        Completing a workout NOT created from a template
        should not affect any templates.
        """
        # Create template
        template = self.create_template(self.user, name='Push Day')
        template_exercise = TemplateExercise.objects.create(
            template=template,
            exercise=self.exercise,
            order=0,
            default_sets=3
        )

        # Create workout WITHOUT from_template
        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            name='Random Workout',
            started_at=timezone.now() - timedelta(minutes=30),
        )

        workout_ex = WorkoutExercise.objects.create(
            session=workout,
            exercise=self.exercise,
            order=0
        )
        ExerciseSet.objects.create(
            workout_exercise=workout_ex,
            set_number=1,
            weight=Decimal('999'),
            reps=99
        )

        # Complete the workout
        response = self.client.post(
            reverse('health:complete_workout_ajax'),
            data=json.dumps({'workout_id': workout.pk}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        # Verify no TemplateExerciseSet was created
        template_sets = TemplateExerciseSet.objects.filter(
            template_exercise=template_exercise
        )
        self.assertEqual(template_sets.count(), 0)

    def test_multiple_exercises_sync_independently(self):
        """
        Template with multiple exercises should sync each correctly.
        """
        # Create template with two exercises
        template = self.create_template(self.user, name='Full Body')
        template_ex1 = TemplateExercise.objects.create(
            template=template,
            exercise=self.exercise,
            order=0,
            default_sets=3
        )
        template_ex2 = TemplateExercise.objects.create(
            template=template,
            exercise=self.exercise2,
            order=1,
            default_sets=3
        )

        # Create workout from template
        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            name='Full Body',
            from_template=template,
            started_at=timezone.now() - timedelta(minutes=30),
        )

        # Add both exercises with different weights
        workout_ex1 = WorkoutExercise.objects.create(
            session=workout,
            exercise=self.exercise,
            order=0
        )
        ExerciseSet.objects.create(
            workout_exercise=workout_ex1,
            set_number=1,
            weight=Decimal('135'),
            reps=10
        )

        workout_ex2 = WorkoutExercise.objects.create(
            session=workout,
            exercise=self.exercise2,
            order=1
        )
        ExerciseSet.objects.create(
            workout_exercise=workout_ex2,
            set_number=1,
            weight=Decimal('225'),
            reps=5
        )

        # Complete the workout
        response = self.client.post(
            reverse('health:complete_workout_ajax'),
            data=json.dumps({'workout_id': workout.pk}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        # Verify both template exercises have correct sets
        bench_sets = TemplateExerciseSet.objects.filter(template_exercise=template_ex1)
        squat_sets = TemplateExerciseSet.objects.filter(template_exercise=template_ex2)

        self.assertEqual(bench_sets.count(), 1)
        self.assertEqual(squat_sets.count(), 1)

        self.assertEqual(bench_sets.first().weight, Decimal('135'))
        self.assertEqual(squat_sets.first().weight, Decimal('225'))


class TemplateFormSetDefaultsTest(FitnessTestMixin, TestCase):
    """
    Tests for template form weight/reps saving functionality.

    The template create/edit form should allow users to save
    default weight and reps for each set in the template.
    """

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
        self.exercise = self.create_exercise(name='Bench Press')

    def test_create_template_saves_set_defaults(self):
        """
        Creating a template with weight/reps saves TemplateExerciseSet records.
        """
        response = self.client.post(
            reverse('health:template_create'),
            data={
                'name': 'Push Day',
                'description': 'Chest and triceps',
                'exercise_id': [self.exercise.pk],
                f'exercise_{self.exercise.pk}_default_sets': '3',
                f'exercise_{self.exercise.pk}_set_1_weight': '135',
                f'exercise_{self.exercise.pk}_set_1_reps': '10',
                f'exercise_{self.exercise.pk}_set_2_weight': '155',
                f'exercise_{self.exercise.pk}_set_2_reps': '8',
                f'exercise_{self.exercise.pk}_set_3_weight': '175',
                f'exercise_{self.exercise.pk}_set_3_reps': '6',
            }
        )

        self.assertEqual(response.status_code, 302)

        # Verify template was created
        template = WorkoutTemplate.objects.get(name='Push Day')
        template_exercise = template.template_exercises.first()

        # Verify set defaults were created
        set_defaults = TemplateExerciseSet.objects.filter(
            template_exercise=template_exercise
        ).order_by('set_number')

        self.assertEqual(set_defaults.count(), 3)

        self.assertEqual(set_defaults[0].weight, Decimal('135'))
        self.assertEqual(set_defaults[0].reps, 10)
        self.assertEqual(set_defaults[1].weight, Decimal('155'))
        self.assertEqual(set_defaults[1].reps, 8)
        self.assertEqual(set_defaults[2].weight, Decimal('175'))
        self.assertEqual(set_defaults[2].reps, 6)

    def test_update_template_updates_set_defaults(self):
        """
        Updating a template with new weight/reps updates TemplateExerciseSet records.
        """
        # Create template with initial set defaults
        template = self.create_template(self.user, name='Push Day')
        template_exercise = TemplateExercise.objects.create(
            template=template,
            exercise=self.exercise,
            order=0,
            default_sets=3
        )
        TemplateExerciseSet.objects.create(
            template_exercise=template_exercise,
            set_number=1,
            weight=Decimal('135'),
            reps=10
        )

        # Update template with new values
        response = self.client.post(
            reverse('health:template_update', kwargs={'pk': template.pk}),
            data={
                'name': 'Push Day Updated',
                'description': '',
                'exercise_id': [self.exercise.pk],
                f'exercise_{self.exercise.pk}_default_sets': '2',
                f'exercise_{self.exercise.pk}_set_1_weight': '145',
                f'exercise_{self.exercise.pk}_set_1_reps': '12',
                f'exercise_{self.exercise.pk}_set_2_weight': '165',
                f'exercise_{self.exercise.pk}_set_2_reps': '10',
            }
        )

        self.assertEqual(response.status_code, 302)

        # Verify template was updated
        template.refresh_from_db()
        self.assertEqual(template.name, 'Push Day Updated')

        # Get the new template_exercise (old one was deleted and recreated)
        template_exercise = template.template_exercises.first()

        # Verify set defaults were updated
        set_defaults = TemplateExerciseSet.objects.filter(
            template_exercise=template_exercise
        ).order_by('set_number')

        self.assertEqual(set_defaults.count(), 2)
        self.assertEqual(set_defaults[0].weight, Decimal('145'))
        self.assertEqual(set_defaults[0].reps, 12)
        self.assertEqual(set_defaults[1].weight, Decimal('165'))
        self.assertEqual(set_defaults[1].reps, 10)

    def test_template_detail_shows_set_defaults(self):
        """
        Template detail page displays saved weight/reps for each set.
        """
        # Create template with set defaults
        template = self.create_template(self.user, name='Push Day')
        template_exercise = TemplateExercise.objects.create(
            template=template,
            exercise=self.exercise,
            order=0,
            default_sets=2
        )
        TemplateExerciseSet.objects.create(
            template_exercise=template_exercise,
            set_number=1,
            weight=Decimal('135'),
            reps=10
        )
        TemplateExerciseSet.objects.create(
            template_exercise=template_exercise,
            set_number=2,
            weight=Decimal('155'),
            reps=8
        )

        response = self.client.get(
            reverse('health:template_detail', kwargs={'pk': template.pk})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '135')
        self.assertContains(response, '10 reps')
        self.assertContains(response, '155')
        self.assertContains(response, '8 reps')

    def test_template_form_shows_existing_set_defaults(self):
        """
        Template edit form pre-populates existing weight/reps values.
        """
        # Create template with set defaults
        template = self.create_template(self.user, name='Push Day')
        template_exercise = TemplateExercise.objects.create(
            template=template,
            exercise=self.exercise,
            order=0,
            default_sets=2
        )
        TemplateExerciseSet.objects.create(
            template_exercise=template_exercise,
            set_number=1,
            weight=Decimal('135'),
            reps=10
        )

        response = self.client.get(
            reverse('health:template_update', kwargs={'pk': template.pk})
        )

        self.assertEqual(response.status_code, 200)
        # The form should contain the saved values (weight may be 135 or 135.0)
        content = response.content.decode()
        self.assertTrue('value="135"' in content or 'value="135.0"' in content)
        self.assertContains(response, 'value="10"')


# =============================================================================
# ACTIVITY WORKOUT TESTS
# =============================================================================

class ActivityWorkoutTests(FitnessTestMixin, TestCase):
    """Tests for activity-based workouts (pickleball, walking, etc.)."""

    def setUp(self):
        self.user = self.create_user()
        self.login_user()

    def test_log_activity_creates_session(self):
        """log_activity_ajax creates a completed activity WorkoutSession."""
        import json
        response = self.client.post(
            reverse('health:log_activity_ajax'),
            data=json.dumps({
                'workout_type': 'Pickleball',
                'duration_minutes': 45,
                'intensity': 'high',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('redirect_url', data)

        workout = WorkoutSession.objects.get(pk=data['workout_id'])
        self.assertEqual(workout.session_mode, 'activity')
        self.assertEqual(workout.workout_type, 'Pickleball')
        self.assertEqual(workout.duration_minutes, 45)
        self.assertEqual(workout.intensity, 'high')
        self.assertIsNotNone(workout.started_at)
        self.assertIsNotNone(workout.completed_at)
        self.assertEqual(workout.source, 'manual')

    def test_activity_workout_no_exercises_required(self):
        """Activity workouts complete without any exercises."""
        workout = self.create_workout(
            self.user,
            name='Walking',
            session_mode='activity',
            workout_type='Walking',
            duration_minutes=30,
            intensity='low',
            started_at=timezone.now() - timedelta(minutes=30),
            completed_at=timezone.now(),
        )
        self.assertTrue(workout.is_activity)
        self.assertEqual(workout.exercise_count, 0)
        self.assertIsNotNone(workout.completed_at)

    def test_is_activity_property(self):
        """is_activity returns True for activity mode, False for structured."""
        activity = self.create_workout(self.user, session_mode='activity')
        structured = self.create_workout(self.user, name='Push Day')

        self.assertTrue(activity.is_activity)
        self.assertFalse(structured.is_activity)

    def test_log_activity_requires_duration(self):
        """log_activity_ajax rejects requests without duration."""
        import json
        response = self.client.post(
            reverse('health:log_activity_ajax'),
            data=json.dumps({'workout_type': 'Walking'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)

    def test_log_activity_with_optional_fields(self):
        """log_activity_ajax accepts optional calories and distance."""
        import json
        response = self.client.post(
            reverse('health:log_activity_ajax'),
            data=json.dumps({
                'workout_type': 'Running',
                'duration_minutes': 30,
                'intensity': 'high',
                'calories_burned': 350,
                'distance_miles': 3.2,
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        workout = WorkoutSession.objects.get(pk=response.json()['workout_id'])
        self.assertEqual(workout.calories_burned, 350)
        self.assertEqual(workout.distance_miles, Decimal('3.2'))

    def test_structured_workout_unaffected(self):
        """Existing structured workout flow still works identically."""
        import json
        # Start a structured workout
        response = self.client.post(
            reverse('health:start_workout_ajax'),
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        workout_id = response.json()['workout_id']
        workout = WorkoutSession.objects.get(pk=workout_id)
        self.assertEqual(workout.session_mode, 'structured')

    def test_edit_activity_workout(self):
        """Can edit an activity workout's duration and intensity."""
        workout = self.create_workout(
            self.user,
            name='Pickleball',
            session_mode='activity',
            workout_type='Pickleball',
            duration_minutes=30,
            intensity='moderate',
            started_at=timezone.now() - timedelta(minutes=30),
            completed_at=timezone.now(),
        )

        response = self.client.post(
            reverse('health:workout_update', kwargs={'pk': workout.pk}),
            data={
                'date': str(workout.date),
                'name': 'Pickleball',
                'notes': 'Great game!',
                'workout_type': 'Pickleball',
                'duration_minutes': '60',
                'intensity': 'high',
            },
        )
        self.assertEqual(response.status_code, 302)  # redirect

        workout.refresh_from_db()
        self.assertEqual(workout.duration_minutes, 60)
        self.assertEqual(workout.intensity, 'high')
        self.assertEqual(workout.notes, 'Great game!')

    def test_activity_str_representation(self):
        """Activity workout __str__ uses workout_type when no name set."""
        workout = self.create_workout(
            self.user,
            name='',
            session_mode='activity',
            workout_type='Pickleball',
        )
        self.assertIn('Pickleball', str(workout))


class ActivityRoutineThresholdTests(FitnessTestMixin, TestCase):
    """Tests for the duration threshold on routine auto-complete."""

    def setUp(self):
        self.user = self.create_user()

    def test_short_workout_no_routine_completion(self):
        """A 5-min workout does NOT auto-complete routine items."""
        from apps.life.models import Routine, RoutineSchedule, RoutineLog

        routine = Routine.objects.create(
            user=self.user, name='Morning', time_of_day='morning',
        )
        from datetime import time
        schedule = RoutineSchedule.objects.create(
            routine=routine, name='Workout',
            activity_type='workout', routine_type='activity',
            days_of_week='0,1,2,3,4,5,6',
            scheduled_time=time(7, 0),
        )

        # Log a 5-min walk (below threshold)
        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            session_mode='activity',
            workout_type='Walking',
            duration_minutes=5,
            intensity='low',
            started_at=timezone.now() - timedelta(minutes=5),
            completed_at=timezone.now(),
        )

        # No routine log should exist
        self.assertFalse(
            RoutineLog.objects.filter(schedule=schedule, scheduled_date=date.today()).exists()
        )

    def test_threshold_met_completes_routine(self):
        """A 15-min workout auto-completes routine items (above 10 min threshold)."""
        from apps.life.models import Routine, RoutineSchedule, RoutineLog

        routine = Routine.objects.create(
            user=self.user, name='Morning', time_of_day='morning',
        )
        from datetime import time
        schedule = RoutineSchedule.objects.create(
            routine=routine, name='Workout',
            activity_type='workout', routine_type='activity',
            days_of_week='0,1,2,3,4,5,6',
            scheduled_time=time(7, 0),
        )

        workout = WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            session_mode='activity',
            workout_type='Pickleball',
            duration_minutes=15,
            intensity='high',
            started_at=timezone.now() - timedelta(minutes=15),
            completed_at=timezone.now(),
        )

        self.assertTrue(
            RoutineLog.objects.filter(
                schedule=schedule, scheduled_date=date.today(),
                completion_source='workout',
            ).exists()
        )

    def test_multi_workout_aggregation(self):
        """Two short workouts totaling 25 min trigger routine completion on second save."""
        from apps.life.models import Routine, RoutineSchedule, RoutineLog

        routine = Routine.objects.create(
            user=self.user, name='Morning', time_of_day='morning',
        )
        from datetime import time
        schedule = RoutineSchedule.objects.create(
            routine=routine, name='Workout',
            activity_type='workout', routine_type='activity',
            days_of_week='0,1,2,3,4,5,6',
            scheduled_time=time(7, 0),
        )

        # First workout: 8 min (below threshold)
        WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            session_mode='activity',
            workout_type='Walking',
            duration_minutes=8,
            intensity='low',
            started_at=timezone.now() - timedelta(minutes=20),
            completed_at=timezone.now() - timedelta(minutes=12),
        )
        self.assertFalse(
            RoutineLog.objects.filter(schedule=schedule, scheduled_date=date.today()).exists()
        )

        # Second workout: 17 min (combined = 25 min, above threshold)
        WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            session_mode='activity',
            workout_type='Pickleball',
            duration_minutes=17,
            intensity='high',
            started_at=timezone.now() - timedelta(minutes=17),
            completed_at=timezone.now(),
        )
        self.assertTrue(
            RoutineLog.objects.filter(
                schedule=schedule, scheduled_date=date.today(),
                completion_source='workout',
            ).exists()
        )


class TrainingLoadSignalTests(FitnessTestMixin, TestCase):
    """Tests for the training_load signal computation."""

    def setUp(self):
        self.user = self.create_user()

    def test_training_load_signal_computed(self):
        """Training load signal is computed with intensity weighting."""
        from apps.core.ai_eae.signal_aggregation import SignalAggregationService
        from apps.core.ai_eae.models import SignalSnapshot

        WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            session_mode='activity',
            workout_type='Pickleball',
            duration_minutes=45,
            intensity='high',
            started_at=timezone.now() - timedelta(minutes=45),
            completed_at=timezone.now(),
        )

        SignalAggregationService.compute_daily_signals(self.user, date.today())

        snapshot = SignalSnapshot.objects.filter(
            user=self.user, date=date.today(), signal_type='training_load',
        ).first()
        self.assertIsNotNone(snapshot)
        # 45 min * 1.3 (high) = 58.5 weighted min → score = 1.0 (clamped)
        self.assertEqual(snapshot.score, 1.0)
        self.assertEqual(snapshot.source_signals['activity_level'], 'strong_activity')

    def test_health_activity_includes_activity_level(self):
        """health_activity signal includes activity_level classification."""
        from apps.core.ai_eae.signal_aggregation import SignalAggregationService
        from apps.core.ai_eae.models import SignalSnapshot

        WorkoutSession.objects.create(
            user=self.user,
            date=date.today(),
            session_mode='activity',
            workout_type='Walking',
            duration_minutes=25,
            intensity='low',
            started_at=timezone.now() - timedelta(minutes=25),
            completed_at=timezone.now(),
        )

        SignalAggregationService.compute_daily_signals(self.user, date.today())

        snapshot = SignalSnapshot.objects.filter(
            user=self.user, date=date.today(), signal_type='health_activity',
        ).first()
        self.assertIsNotNone(snapshot)
        self.assertIn('activity_level', snapshot.source_signals)
        self.assertEqual(snapshot.source_signals['activity_level'], 'moderate_activity')
        self.assertIn('session_modes', snapshot.source_signals)
        self.assertEqual(snapshot.source_signals['session_modes']['activity'], 1)

    def test_activity_level_classification(self):
        """Activity level classification produces correct labels."""
        from apps.core.ai_eae.signal_aggregation import _classify_activity_level

        self.assertEqual(_classify_activity_level(0), 'no_activity')
        self.assertEqual(_classify_activity_level(5), 'no_activity')
        self.assertEqual(_classify_activity_level(10), 'light_activity')
        self.assertEqual(_classify_activity_level(19), 'light_activity')
        self.assertEqual(_classify_activity_level(20), 'moderate_activity')
        self.assertEqual(_classify_activity_level(44), 'moderate_activity')
        self.assertEqual(_classify_activity_level(45), 'strong_activity')
        self.assertEqual(_classify_activity_level(90), 'strong_activity')
