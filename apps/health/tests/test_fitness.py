# ==============================================================================
# File: test_fitness.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Comprehensive tests for fitness CRUD functionality (workouts & templates)
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
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
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

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
        cardio = self.create_exercise(name='Cycling', category='cardio', muscle_group='')
        resistance = self.create_exercise(name='Bicep Curl', category='resistance', muscle_group='Arms')

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
        old_workout = self.create_workout(
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
        workout = self.create_workout(self.user, name='My Workout')

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
        template = self.create_template(self.user, name='Push Day')

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
        workout = self.create_workout(self.user, name='Recent Workout')

        response = self.client.get(reverse('health:fitness_home'))

        self.assertContains(response, 'Recent Workout')

    def test_fitness_home_shows_templates(self):
        """Fitness home shows user's templates."""
        template = self.create_template(self.user, name='My Template')

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
