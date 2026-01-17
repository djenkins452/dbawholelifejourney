"""
Reading Plans Tests

This test file covers:
1. Model tests for ReadingPlanTemplate, ReadingPlanDay, UserReadingPlan, UserReadingProgress
2. View tests for starting plans, marking progress, saving notes
3. Critical regression test: notes must be saved when marking day complete

Location: apps/faith/tests/test_reading_plans.py
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.faith.models import (
    ReadingPlanTemplate,
    ReadingPlanDay,
    UserReadingPlan,
    UserReadingProgress,
)

User = get_user_model()


class ReadingPlanTestMixin:
    """Common setup for reading plan tests."""

    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted, onboarding completed, and faith enabled."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._complete_onboarding(user)
        self._enable_faith(user)
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

    def _enable_faith(self, user):
        user.preferences.faith_enabled = True
        user.preferences.save()

    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)

    def create_reading_plan_template(self, title='Test Plan', duration_days=7, **kwargs):
        """Create a reading plan template with days."""
        defaults = {
            'slug': title.lower().replace(' ', '-'),
            'description': 'A test reading plan',
            'category': 'topical',
            'difficulty': 'beginner',
            'duration_days': duration_days,
            'is_active': True,
            'is_featured': False,
        }
        defaults.update(kwargs)
        template = ReadingPlanTemplate.objects.create(title=title, **defaults)

        # Create days for the plan
        for day_num in range(1, duration_days + 1):
            ReadingPlanDay.objects.create(
                plan=template,
                day_number=day_num,
                title=f'Day {day_num} Title',
                scripture_references=[f'Psalm {day_num}:1-10'],
                reflection_prompt=f'Reflection prompt for day {day_num}',
            )

        return template

    def start_reading_plan(self, user, template):
        """Helper to start a reading plan for a user."""
        user_plan = UserReadingPlan.objects.create(
            user=user,
            template=template,
            plan_status='active',
            current_day=1,
        )
        # Create progress entries for all days
        for day in template.days.all():
            UserReadingProgress.objects.create(
                user=user,
                user_plan=user_plan,
                plan_day=day,
                is_completed=False,
            )
        return user_plan


# =============================================================================
# 1. MODEL TESTS
# =============================================================================

class ReadingPlanTemplateModelTest(ReadingPlanTestMixin, TestCase):
    """Tests for ReadingPlanTemplate model."""

    def test_create_template(self):
        """Reading plan template can be created."""
        template = self.create_reading_plan_template(title='Finding Peace')
        self.assertEqual(template.title, 'Finding Peace')
        self.assertEqual(template.duration_days, 7)
        self.assertTrue(template.is_active)

    def test_template_has_days(self):
        """Template creates associated days."""
        template = self.create_reading_plan_template(duration_days=5)
        self.assertEqual(template.days.count(), 5)

    def test_template_str(self):
        """Template string representation."""
        template = self.create_reading_plan_template(title='My Plan')
        self.assertEqual(str(template), 'My Plan')


class UserReadingPlanModelTest(ReadingPlanTestMixin, TestCase):
    """Tests for UserReadingPlan model."""

    def setUp(self):
        self.user = self.create_user()
        self.template = self.create_reading_plan_template()

    def test_start_reading_plan(self):
        """User can start a reading plan."""
        user_plan = self.start_reading_plan(self.user, self.template)
        self.assertEqual(user_plan.plan_status, 'active')
        self.assertEqual(user_plan.current_day, 1)
        self.assertEqual(user_plan.user, self.user)

    def test_progress_percentage_zero(self):
        """Progress percentage is 0 when no days completed."""
        user_plan = self.start_reading_plan(self.user, self.template)
        self.assertEqual(user_plan.progress_percentage, 0)

    def test_progress_percentage_partial(self):
        """Progress percentage updates when days completed."""
        user_plan = self.start_reading_plan(self.user, self.template)
        # Mark 3 of 7 days complete
        for progress in user_plan.day_completions.all()[:3]:
            progress.mark_complete()
        self.assertEqual(user_plan.progress_percentage, 42)  # 3/7 = 42%

    def test_progress_percentage_complete(self):
        """Progress percentage is 100 when all days completed."""
        user_plan = self.start_reading_plan(self.user, self.template)
        for progress in user_plan.day_completions.all():
            progress.mark_complete()
        self.assertEqual(user_plan.progress_percentage, 100)

    def test_is_complete_false(self):
        """is_complete is False when days remain."""
        user_plan = self.start_reading_plan(self.user, self.template)
        self.assertFalse(user_plan.is_complete)

    def test_is_complete_true(self):
        """is_complete is True when all days done."""
        user_plan = self.start_reading_plan(self.user, self.template)
        for progress in user_plan.day_completions.all():
            progress.mark_complete()
        self.assertTrue(user_plan.is_complete)


class UserReadingProgressModelTest(ReadingPlanTestMixin, TestCase):
    """Tests for UserReadingProgress model."""

    def setUp(self):
        self.user = self.create_user()
        self.template = self.create_reading_plan_template()
        self.user_plan = self.start_reading_plan(self.user, self.template)

    def test_mark_complete(self):
        """mark_complete sets is_completed and completed_at."""
        progress = self.user_plan.day_completions.first()
        self.assertFalse(progress.is_completed)
        self.assertIsNone(progress.completed_at)

        progress.mark_complete()

        self.assertTrue(progress.is_completed)
        self.assertIsNotNone(progress.completed_at)

    def test_mark_complete_advances_current_day(self):
        """mark_complete advances current_day on parent plan."""
        progress = self.user_plan.day_completions.get(plan_day__day_number=1)
        self.assertEqual(self.user_plan.current_day, 1)

        progress.mark_complete()

        self.user_plan.refresh_from_db()
        self.assertEqual(self.user_plan.current_day, 2)

    def test_notes_can_be_saved(self):
        """Notes can be saved on progress."""
        progress = self.user_plan.day_completions.first()
        progress.notes = 'This is my reflection.'
        progress.save()

        progress.refresh_from_db()
        self.assertEqual(progress.notes, 'This is my reflection.')


# =============================================================================
# 2. VIEW TESTS - CRITICAL REGRESSION TEST FOR NOTES SAVING
# =============================================================================

class MarkDayCompleteViewTest(ReadingPlanTestMixin, TestCase):
    """
    Tests for marking reading plan days as complete.

    CRITICAL: This test ensures notes are saved when marking a day complete.
    This was a bug where notes were lost because mark_complete() used
    update_fields that didn't include 'notes'.
    """

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.template = self.create_reading_plan_template()
        self.user_plan = self.start_reading_plan(self.user, self.template)
        self.login_user()

    def test_mark_day_complete_saves_notes(self):
        """
        CRITICAL REGRESSION TEST: Notes must be saved when marking day complete.

        This test guards against the bug where notes were set on the progress
        object but not persisted because mark_complete() used update_fields
        that excluded 'notes'.
        """
        progress = self.user_plan.day_completions.get(plan_day__day_number=1)
        day_pk = progress.plan_day.pk

        url = reverse('faith:mark_day_complete', kwargs={
            'pk': self.user_plan.pk,
            'day_pk': day_pk,
        })

        notes_text = 'These are my important reflections on the reading.'
        response = self.client.post(url, {'notes': notes_text})

        # Should redirect on success
        self.assertEqual(response.status_code, 302)

        # CRITICAL: Notes must be saved to the database
        progress.refresh_from_db()
        self.assertEqual(progress.notes, notes_text)
        self.assertTrue(progress.is_completed)

    def test_mark_day_complete_without_notes(self):
        """Marking complete without notes still works."""
        progress = self.user_plan.day_completions.get(plan_day__day_number=1)
        day_pk = progress.plan_day.pk

        url = reverse('faith:mark_day_complete', kwargs={
            'pk': self.user_plan.pk,
            'day_pk': day_pk,
        })

        response = self.client.post(url, {})

        self.assertEqual(response.status_code, 302)
        progress.refresh_from_db()
        self.assertTrue(progress.is_completed)
        self.assertEqual(progress.notes, '')

    def test_mark_day_complete_updates_existing_notes(self):
        """Notes can be updated when marking complete."""
        progress = self.user_plan.day_completions.get(plan_day__day_number=1)
        progress.notes = 'Initial notes'
        progress.save()

        day_pk = progress.plan_day.pk
        url = reverse('faith:mark_day_complete', kwargs={
            'pk': self.user_plan.pk,
            'day_pk': day_pk,
        })

        new_notes = 'Updated notes with more reflection.'
        response = self.client.post(url, {'notes': new_notes})

        self.assertEqual(response.status_code, 302)
        progress.refresh_from_db()
        self.assertEqual(progress.notes, new_notes)

    def test_mark_day_complete_requires_login(self):
        """Marking day complete requires authentication."""
        self.client.logout()
        progress = self.user_plan.day_completions.first()

        url = reverse('faith:mark_day_complete', kwargs={
            'pk': self.user_plan.pk,
            'day_pk': progress.plan_day.pk,
        })

        response = self.client.post(url, {'notes': 'test'})
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url.lower())

    def test_cannot_mark_other_users_progress(self):
        """User cannot mark another user's progress as complete."""
        other_user = self.create_user(email='other@example.com')
        other_plan = self.start_reading_plan(other_user, self.template)
        progress = other_plan.day_completions.first()

        url = reverse('faith:mark_day_complete', kwargs={
            'pk': other_plan.pk,
            'day_pk': progress.plan_day.pk,
        })

        response = self.client.post(url, {'notes': 'hacked!'})
        self.assertEqual(response.status_code, 404)

        # Notes should not have been saved
        progress.refresh_from_db()
        self.assertEqual(progress.notes, '')


class ReadingPlanProgressViewTest(ReadingPlanTestMixin, TestCase):
    """Tests for viewing reading plan progress."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.template = self.create_reading_plan_template()
        self.user_plan = self.start_reading_plan(self.user, self.template)
        self.login_user()

    def test_progress_view_loads(self):
        """Progress view loads successfully."""
        url = reverse('faith:reading_plan_progress', kwargs={'pk': self.user_plan.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_progress_view_shows_current_day(self):
        """Progress view includes current day in context."""
        url = reverse('faith:reading_plan_progress', kwargs={'pk': self.user_plan.pk})
        response = self.client.get(url)
        self.assertIn('current_day', response.context)

    def test_progress_view_shows_notes(self):
        """Progress view shows saved notes."""
        progress = self.user_plan.day_completions.first()
        progress.notes = 'My saved reflection'
        progress.save()

        url = reverse('faith:reading_plan_progress', kwargs={'pk': self.user_plan.pk})
        response = self.client.get(url)
        self.assertContains(response, 'My saved reflection')


# =============================================================================
# 3. DATA ISOLATION TESTS
# =============================================================================

class ReadingPlanDataIsolationTest(ReadingPlanTestMixin, TestCase):
    """Tests that users can only see their own reading plan data."""

    def setUp(self):
        self.client = Client()
        self.user_a = self.create_user(email='usera@example.com')
        self.user_b = self.create_user(email='userb@example.com')
        self.template = self.create_reading_plan_template()

        self.plan_a = self.start_reading_plan(self.user_a, self.template)
        self.plan_b = self.start_reading_plan(self.user_b, self.template)

    def test_user_cannot_view_other_users_plan(self):
        """User cannot view another user's reading plan progress."""
        self.login_user(email='usera@example.com')

        url = reverse('faith:reading_plan_progress', kwargs={'pk': self.plan_b.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_user_sees_only_own_plans(self):
        """User can view their own plan progress but not others'."""
        self.login_user(email='usera@example.com')

        # Can view own plan progress
        url = reverse('faith:reading_plan_progress', kwargs={'pk': self.plan_a.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Cannot view other user's plan progress
        url = reverse('faith:reading_plan_progress', kwargs={'pk': self.plan_b.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


# =============================================================================
# 4. DELETE READING PLAN TESTS
# =============================================================================

class DeleteReadingPlanViewTest(ReadingPlanTestMixin, TestCase):
    """Tests for deleting completed reading plans."""

    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.template = self.create_reading_plan_template()
        self.user_plan = self.start_reading_plan(self.user, self.template)
        # Mark the plan as completed
        for progress in self.user_plan.day_completions.all():
            progress.mark_complete()
        self.user_plan.refresh_from_db()
        self.login_user()

    def test_delete_completed_plan(self):
        """Completed plan can be deleted."""
        self.assertEqual(self.user_plan.plan_status, 'completed')

        url = reverse('faith:delete_reading_plan', kwargs={'pk': self.user_plan.pk})
        response = self.client.post(url)

        # Should redirect on success
        self.assertEqual(response.status_code, 302)

        # Plan should be soft deleted (not visible in default manager)
        self.assertFalse(UserReadingPlan.objects.filter(pk=self.user_plan.pk).exists())
        # But still exists in all_objects manager
        self.assertTrue(UserReadingPlan.all_objects.filter(pk=self.user_plan.pk).exists())
        # And has deleted status
        deleted_plan = UserReadingPlan.all_objects.get(pk=self.user_plan.pk)
        self.assertEqual(deleted_plan.status, 'deleted')

    def test_cannot_delete_active_plan(self):
        """Active plan cannot be deleted via this endpoint."""
        # Create a new active plan
        template2 = self.create_reading_plan_template(title='Active Plan', slug='active-plan')
        active_plan = self.start_reading_plan(self.user, template2)
        self.assertEqual(active_plan.plan_status, 'active')

        url = reverse('faith:delete_reading_plan', kwargs={'pk': active_plan.pk})
        response = self.client.post(url)

        # Should return 404 because the view only finds completed plans
        self.assertEqual(response.status_code, 404)

        # Plan should still exist and be active
        active_plan.refresh_from_db()
        self.assertEqual(active_plan.plan_status, 'active')
        self.assertEqual(active_plan.status, 'active')

    def test_cannot_delete_other_users_plan(self):
        """User cannot delete another user's completed plan."""
        other_user = self.create_user(email='other@example.com')
        other_template = self.create_reading_plan_template(
            title='Other Plan', slug='other-plan'
        )
        other_plan = self.start_reading_plan(other_user, other_template)
        # Mark it complete
        for progress in other_plan.day_completions.all():
            progress.mark_complete()
        other_plan.refresh_from_db()

        url = reverse('faith:delete_reading_plan', kwargs={'pk': other_plan.pk})
        response = self.client.post(url)

        # Should return 404 because the view filters by current user
        self.assertEqual(response.status_code, 404)

        # Plan should still exist
        self.assertTrue(UserReadingPlan.objects.filter(pk=other_plan.pk).exists())

    def test_delete_requires_login(self):
        """Deleting a plan requires authentication."""
        self.client.logout()

        url = reverse('faith:delete_reading_plan', kwargs={'pk': self.user_plan.pk})
        response = self.client.post(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url.lower())

        # Plan should still exist
        self.assertTrue(UserReadingPlan.objects.filter(pk=self.user_plan.pk).exists())
