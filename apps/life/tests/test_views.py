"""
Life Module View Tests

Tests for Life module views: Calendar, Tasks, Events, etc.

Location: apps/life/tests/test_views.py
"""

from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.life.models import Project, Task, LifeEvent

User = get_user_model()


class CalendarViewTest(TestCase):
    """Tests for the calendar view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        # Accept terms if required
        self._accept_terms(self.user)
        self._complete_onboarding(self.user)

    def _accept_terms(self, user):
        """Helper to accept terms for a user."""
        try:
            from apps.users.models import TermsAcceptance
            from django.conf import settings
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Helper to complete onboarding for a user."""
        try:
            user.preferences.has_completed_onboarding = True
            user.preferences.save()
        except Exception:
            pass
    
    def test_calendar_requires_login(self):
        """Calendar page requires authentication."""
        response = self.client.get(reverse('life:calendar'))
        self.assertEqual(response.status_code, 302)
    
    def test_calendar_loads_for_authenticated_user(self):
        """Authenticated user can access calendar."""
        self.client.login(email='test@example.com', password='testpass123')
        response = self.client.get(reverse('life:calendar'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Calendar')
    
    def test_calendar_shows_current_month_events(self):
        """Calendar shows events for the current month."""
        self.client.login(email='test@example.com', password='testpass123')
        
        # Create an event for today
        LifeEvent.objects.create(
            user=self.user,
            title='Test Event Today',
            start_date=date.today()
        )
        
        response = self.client.get(reverse('life:calendar'))
        self.assertContains(response, 'Test Event Today')
    
    def test_calendar_month_navigation(self):
        """Calendar can navigate to different months."""
        self.client.login(email='test@example.com', password='testpass123')
        
        # Go to a specific month
        response = self.client.get(reverse('life:calendar') + '?year=2025&month=6')
        self.assertEqual(response.status_code, 200)


class EventViewTest(TestCase):
    """Tests for event CRUD views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self._accept_terms(self.user)
        self._complete_onboarding(self.user)
        self.client.login(email='test@example.com', password='testpass123')

    def _accept_terms(self, user):
        """Helper to accept terms for a user."""
        try:
            from apps.users.models import TermsAcceptance
            from django.conf import settings
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Helper to complete onboarding for a user."""
        try:
            user.preferences.has_completed_onboarding = True
            user.preferences.save()
        except Exception:
            pass
    
    def test_event_create_page_loads(self):
        """Event creation page loads."""
        response = self.client.get(reverse('life:event_create'))
        self.assertEqual(response.status_code, 200)
    
    def test_event_can_be_created(self):
        """User can create an event."""
        response = self.client.post(reverse('life:event_create'), {
            'title': 'New Event',
            'start_date': date.today().isoformat(),
            'event_type': 'personal',
            'is_all_day': 'on',
        })
        
        # Should redirect after creation
        self.assertEqual(response.status_code, 302)
        
        # Event should exist
        self.assertTrue(
            LifeEvent.objects.filter(user=self.user, title='New Event').exists()
        )
    
    def test_event_update_page_loads(self):
        """Event edit page loads."""
        event = LifeEvent.objects.create(
            user=self.user,
            title='Edit Me',
            start_date=date.today()
        )
        response = self.client.get(reverse('life:event_update', kwargs={'pk': event.pk}))
        self.assertEqual(response.status_code, 200)
    
    def test_event_can_be_updated(self):
        """User can update their event."""
        event = LifeEvent.objects.create(
            user=self.user,
            title='Original Title',
            start_date=date.today()
        )
        
        response = self.client.post(
            reverse('life:event_update', kwargs={'pk': event.pk}),
            {
                'title': 'Updated Title',
                'start_date': date.today().isoformat(),
                'event_type': 'personal',
                'is_all_day': 'on',
            }
        )
        
        event.refresh_from_db()
        self.assertEqual(event.title, 'Updated Title')
    
    def test_event_can_be_deleted(self):
        """User can delete their event."""
        event = LifeEvent.objects.create(
            user=self.user,
            title='Delete Me',
            start_date=date.today()
        )
        
        response = self.client.post(
            reverse('life:event_delete', kwargs={'pk': event.pk})
        )
        
        self.assertFalse(LifeEvent.objects.filter(pk=event.pk).exists())


class TaskViewTest(TestCase):
    """Tests for task views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self._accept_terms(self.user)
        self._complete_onboarding(self.user)
        self.client.login(email='test@example.com', password='testpass123')

    def _accept_terms(self, user):
        """Helper to accept terms for a user."""
        try:
            from apps.users.models import TermsAcceptance
            from django.conf import settings
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Helper to complete onboarding for a user."""
        try:
            user.preferences.has_completed_onboarding = True
            user.preferences.save()
        except Exception:
            pass
    
    def test_task_list_loads(self):
        """Task list page loads."""
        response = self.client.get(reverse('life:task_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_task_list_shows_user_tasks(self):
        """Task list shows the user's tasks."""
        Task.objects.create(user=self.user, title='My Task')
        
        response = self.client.get(reverse('life:task_list'))
        self.assertContains(response, 'My Task')
    
    def test_task_can_be_created(self):
        """User can create a task."""
        response = self.client.post(reverse('life:task_create'), {
            'title': 'New Task',
            'priority': 'soon',
        })

        self.assertTrue(
            Task.objects.filter(user=self.user, title='New Task').exists()
        )

    def test_task_toggle_completes_task(self):
        """Toggling an incomplete task marks it complete."""
        task = Task.objects.create(user=self.user, title='Toggle Test', is_completed=False)

        response = self.client.post(reverse('life:task_toggle', kwargs={'pk': task.pk}))

        task.refresh_from_db()
        self.assertTrue(task.is_completed)
        self.assertIsNotNone(task.completed_at)

    def test_task_toggle_uncompletes_task(self):
        """Toggling a completed task marks it incomplete (undo)."""
        task = Task.objects.create(user=self.user, title='Undo Test', is_completed=True)

        response = self.client.post(reverse('life:task_toggle', kwargs={'pk': task.pk}))

        task.refresh_from_db()
        self.assertFalse(task.is_completed)
        self.assertIsNone(task.completed_at)

    def test_completed_task_shows_undo_link(self):
        """Completed tasks display an Undo link in the task list."""
        task = Task.objects.create(user=self.user, title='Completed Task', is_completed=True)

        response = self.client.get(reverse('life:task_list') + '?show=all')

        self.assertContains(response, 'Undo')
        self.assertContains(response, f'action="{reverse("life:task_toggle", kwargs={"pk": task.pk})}"')

    def test_incomplete_task_no_undo_link(self):
        """Incomplete tasks do not display an Undo link."""
        task = Task.objects.create(user=self.user, title='Active Task', is_completed=False)

        response = self.client.get(reverse('life:task_list'))
        content = response.content.decode()

        # Count occurrences - there should be no Undo buttons for incomplete tasks
        self.assertNotIn('class="task-undo"', content)

    def test_task_create_preselects_project_from_query_param(self):
        """Task create form pre-selects project when ?project=ID is passed."""
        project = Project.objects.create(
            user=self.user,
            title='Test Project',
            status='active'
        )

        response = self.client.get(
            reverse('life:task_create') + f'?project={project.pk}'
        )

        self.assertEqual(response.status_code, 200)
        # The form should have the project in initial data
        self.assertEqual(response.context['form'].initial.get('project'), project)

    def test_task_create_with_project_redirects_to_project_detail(self):
        """Creating a task from project page redirects back to that project."""
        project = Project.objects.create(
            user=self.user,
            title='Test Project',
            status='active'
        )

        response = self.client.post(
            reverse('life:task_create') + f'?project={project.pk}',
            {
                'title': 'Task for Project',
                'priority': 'soon',
                'project': project.pk,
            }
        )

        # Should redirect to project detail page
        self.assertRedirects(response, reverse('life:project_detail', kwargs={'pk': project.pk}))

        # Task should be created and linked to project
        task = Task.objects.get(user=self.user, title='Task for Project')
        self.assertEqual(task.project, project)

    def test_task_create_with_invalid_project_id_ignores_param(self):
        """Task create form ignores invalid project IDs."""
        response = self.client.get(
            reverse('life:task_create') + '?project=9999'
        )

        self.assertEqual(response.status_code, 200)
        # The form should not have a project pre-selected
        self.assertIsNone(response.context['form'].initial.get('project'))

    def test_task_create_with_other_users_project_ignores_param(self):
        """Task create form ignores project IDs belonging to other users."""
        other_user = User.objects.create_user(
            email='other@example.com',
            password='testpass123'
        )
        self._accept_terms(other_user)

        other_project = Project.objects.create(
            user=other_user,
            title='Other Project',
            status='active'
        )

        response = self.client.get(
            reverse('life:task_create') + f'?project={other_project.pk}'
        )

        self.assertEqual(response.status_code, 200)
        # The form should not have the other user's project pre-selected
        self.assertIsNone(response.context['form'].initial.get('project'))


class ProjectViewTest(TestCase):
    """Tests for project views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email='test@example.com',
            password='testpass123'
        )
        self._accept_terms(self.user)
        self._complete_onboarding(self.user)
        self.client.login(email='test@example.com', password='testpass123')

    def _accept_terms(self, user):
        """Helper to accept terms for a user."""
        try:
            from apps.users.models import TermsAcceptance
            from django.conf import settings
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Helper to complete onboarding for a user."""
        try:
            user.preferences.has_completed_onboarding = True
            user.preferences.save()
        except Exception:
            pass
    
    def test_project_list_loads(self):
        """Project list page loads."""
        response = self.client.get(reverse('life:project_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_project_detail_loads(self):
        """Project detail page loads."""
        project = Project.objects.create(
            user=self.user,
            title='Test Project'
        )
        response = self.client.get(
            reverse('life:project_detail', kwargs={'pk': project.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Test Project')


class DataIsolationTest(TestCase):
    """Tests to ensure users can only see their own data."""

    def setUp(self):
        self.client = Client()
        self.user_a = User.objects.create_user(
            email='usera@example.com',
            password='testpass123'
        )
        self.user_b = User.objects.create_user(
            email='userb@example.com',
            password='testpass123'
        )

        # Accept terms for both users
        self._accept_terms(self.user_a)
        self._accept_terms(self.user_b)

        # Complete onboarding for both users
        self._complete_onboarding(self.user_a)
        self._complete_onboarding(self.user_b)

        # Create data for each user
        self.event_a = LifeEvent.objects.create(
            user=self.user_a,
            title='User A Event',
            start_date=date.today()
        )
        self.event_b = LifeEvent.objects.create(
            user=self.user_b,
            title='User B Event',
            start_date=date.today()
        )

        self.task_a = Task.objects.create(
            user=self.user_a,
            title='User A Task'
        )
        self.task_b = Task.objects.create(
            user=self.user_b,
            title='User B Task'
        )

    def _accept_terms(self, user):
        """Helper to accept terms for a user."""
        try:
            from apps.users.models import TermsAcceptance
            from django.conf import settings
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass

    def _complete_onboarding(self, user):
        """Helper to complete onboarding for a user."""
        try:
            user.preferences.has_completed_onboarding = True
            user.preferences.save()
        except Exception:
            pass
    
    def test_user_a_sees_only_their_events(self):
        """User A only sees their own events on calendar."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('life:calendar'))
        
        self.assertContains(response, 'User A Event')
        self.assertNotContains(response, 'User B Event')
    
    def test_user_b_sees_only_their_events(self):
        """User B only sees their own events on calendar."""
        self.client.login(email='userb@example.com', password='testpass123')
        response = self.client.get(reverse('life:calendar'))
        
        self.assertContains(response, 'User B Event')
        self.assertNotContains(response, 'User A Event')
    
    def test_user_a_sees_only_their_tasks(self):
        """User A only sees their own tasks."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('life:task_list'))
        
        self.assertContains(response, 'User A Task')
        self.assertNotContains(response, 'User B Task')
    
    def test_user_cannot_edit_other_users_event(self):
        """User A cannot edit User B's event."""
        self.client.login(email='usera@example.com', password='testpass123')
        
        # Try to access User B's event edit page
        response = self.client.get(
            reverse('life:event_update', kwargs={'pk': self.event_b.pk})
        )
        
        # Should get 404 (not found) because queryset filters by user
        self.assertEqual(response.status_code, 404)
    
    def test_user_cannot_delete_other_users_event(self):
        """User A cannot delete User B's event."""
        self.client.login(email='usera@example.com', password='testpass123')
        
        # Try to delete User B's event
        response = self.client.post(
            reverse('life:event_delete', kwargs={'pk': self.event_b.pk})
        )
        
        # Should get 404
        self.assertEqual(response.status_code, 404)
        
        # Event should still exist
        self.assertTrue(LifeEvent.objects.filter(pk=self.event_b.pk).exists())