"""
Life Module - Comprehensive Tests

This test file covers:
1. Model tests (Project, Task, LifeEvent)
2. View tests (loading, authentication)
3. Form validation tests
4. Edge case tests
5. Business logic tests (completion, recurrence, progress)
6. Data isolation tests
7. Calendar tests

Location: apps/life/tests/test_life_comprehensive.py
"""

from datetime import date, datetime, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.life.models import Project, Task, LifeEvent

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class LifeTestMixin:
    """Common setup for life tests."""
    
    def create_user(self, email='test@example.com', password='testpass123'):
        """Create a test user with terms accepted and life enabled."""
        user = User.objects.create_user(email=email, password=password)
        self._accept_terms(user)
        self._enable_life(user)
        return user
    
    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=user, terms_version='1.0')
    
    def _enable_life(self, user):
        user.preferences.life_enabled = True
        user.preferences.save()
    
    def login_user(self, email='test@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)
    
    def create_project(self, user, title='Test Project', **kwargs):
        """Helper to create a project."""
        return Project.objects.create(user=user, title=title, **kwargs)
    
    def create_task(self, user, title='Test Task', **kwargs):
        """Helper to create a task."""
        return Task.objects.create(user=user, title=title, **kwargs)
    
    def create_event(self, user, title='Test Event', **kwargs):
        """Helper to create a life event."""
        defaults = {
            'start_date': date.today(),
            'event_type': 'personal',
        }
        defaults.update(kwargs)
        return LifeEvent.objects.create(user=user, title=title, **defaults)


# =============================================================================
# 1. PROJECT MODEL TESTS
# =============================================================================

class ProjectModelTest(LifeTestMixin, TestCase):
    """Tests for the Project model."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_create_project(self):
        """Project can be created."""
        project = self.create_project(self.user)
        self.assertEqual(project.title, 'Test Project')
        self.assertEqual(project.status, 'active')
    
    def test_project_default_values(self):
        """Project has correct default values."""
        project = self.create_project(self.user)
        self.assertEqual(project.status, 'active')
        self.assertEqual(project.priority, 'someday')
    
    def test_project_str(self):
        """Project string is the title."""
        project = self.create_project(self.user, title='Home Renovation')
        self.assertEqual(str(project), 'Home Renovation')
    
    def test_project_statuses(self):
        """Project supports different statuses."""
        for status in ['active', 'paused', 'completed', 'archived']:
            project = self.create_project(
                self.user, 
                title=f'{status} project',
                status=status
            )
            self.assertEqual(project.status, status)
    
    def test_project_priorities(self):
        """Project supports different priorities."""
        for priority in ['now', 'soon', 'someday']:
            project = self.create_project(
                self.user,
                title=f'{priority} project',
                priority=priority
            )
            self.assertEqual(project.priority, priority)
    
    def test_project_with_dates(self):
        """Project can have start and target dates."""
        project = self.create_project(
            self.user,
            start_date=date.today(),
            target_date=date.today() + timedelta(days=30)
        )
        self.assertIsNotNone(project.start_date)
        self.assertIsNotNone(project.target_date)
    
    def test_project_is_overdue(self):
        """Project is_overdue property works."""
        past_date = date.today() - timedelta(days=10)
        project = self.create_project(
            self.user,
            target_date=past_date,
            status='active'
        )
        self.assertTrue(project.is_overdue)
    
    def test_project_not_overdue_when_completed(self):
        """Completed project is not overdue."""
        past_date = date.today() - timedelta(days=10)
        project = self.create_project(
            self.user,
            target_date=past_date,
            status='completed'
        )
        self.assertFalse(project.is_overdue)
    
    def test_project_task_count(self):
        """Project tracks task count."""
        project = self.create_project(self.user)
        self.create_task(self.user, project=project, title='Task 1')
        self.create_task(self.user, project=project, title='Task 2')
        
        self.assertEqual(project.task_count, 2)
    
    def test_project_progress_percentage(self):
        """Project calculates progress percentage."""
        project = self.create_project(self.user)
        task1 = self.create_task(self.user, project=project, is_completed=True)
        task2 = self.create_task(self.user, project=project, is_completed=False)
        
        self.assertEqual(project.progress_percentage, 50)
    
    def test_project_ordering(self):
        """Projects are ordered by most recent first."""
        old = self.create_project(self.user, title='Old')
        new = self.create_project(self.user, title='New')
        
        projects = Project.objects.filter(user=self.user)
        self.assertEqual(projects[0], new)


# =============================================================================
# 2. TASK MODEL TESTS
# =============================================================================

class TaskModelTest(LifeTestMixin, TestCase):
    """Tests for the Task model."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_create_task(self):
        """Task can be created."""
        task = self.create_task(self.user)
        self.assertEqual(task.title, 'Test Task')
        self.assertFalse(task.is_completed)
    
    def test_task_default_values(self):
        """Task has correct default values."""
        task = self.create_task(self.user)
        self.assertFalse(task.is_completed)
        self.assertEqual(task.priority, 'someday')
        self.assertFalse(task.is_recurring)
    
    def test_task_str(self):
        """Task string is the title."""
        task = self.create_task(self.user, title='Buy groceries')
        self.assertEqual(str(task), 'Buy groceries')
    
    def test_task_with_project(self):
        """Task can belong to a project."""
        project = self.create_project(self.user)
        task = self.create_task(self.user, project=project)
        
        self.assertEqual(task.project, project)
        self.assertIn(task, project.tasks.all())
    
    def test_standalone_task(self):
        """Task can exist without a project."""
        task = self.create_task(self.user)
        self.assertIsNone(task.project)
    
    def test_mark_complete(self):
        """mark_complete() sets completion status."""
        task = self.create_task(self.user)
        task.mark_complete()
        
        self.assertTrue(task.is_completed)
        self.assertIsNotNone(task.completed_at)
    
    def test_mark_incomplete(self):
        """mark_incomplete() clears completion status."""
        task = self.create_task(self.user, is_completed=True)
        task.mark_incomplete()
        
        self.assertFalse(task.is_completed)
        self.assertIsNone(task.completed_at)
    
    def test_task_is_overdue(self):
        """Task is_overdue property works."""
        past_date = date.today() - timedelta(days=5)
        task = self.create_task(self.user, due_date=past_date)
        
        self.assertTrue(task.is_overdue)
    
    def test_completed_task_not_overdue(self):
        """Completed task is not overdue."""
        past_date = date.today() - timedelta(days=5)
        task = self.create_task(
            self.user, 
            due_date=past_date, 
            is_completed=True
        )
        
        self.assertFalse(task.is_overdue)
    
    def test_task_effort_choices(self):
        """Task supports effort levels."""
        for effort in ['quick', 'small', 'medium', 'large']:
            task = self.create_task(self.user, effort=effort)
            self.assertEqual(task.effort, effort)
    
    def test_recurring_task(self):
        """Task can be recurring."""
        task = self.create_task(
            self.user,
            is_recurring=True,
            recurrence_pattern='weekly'
        )
        self.assertTrue(task.is_recurring)
        self.assertEqual(task.recurrence_pattern, 'weekly')


# =============================================================================
# 3. LIFE EVENT MODEL TESTS
# =============================================================================

class LifeEventModelTest(LifeTestMixin, TestCase):
    """Tests for the LifeEvent model."""
    
    def setUp(self):
        self.user = self.create_user()
    
    def test_create_event(self):
        """Event can be created."""
        event = self.create_event(self.user)
        self.assertEqual(event.title, 'Test Event')
    
    def test_event_types(self):
        """Event supports different types."""
        types = ['personal', 'family', 'household', 'faith', 'health', 'work']
        for event_type in types:
            event = self.create_event(
                self.user,
                title=f'{event_type} event',
                event_type=event_type
            )
            self.assertEqual(event.event_type, event_type)
    
    def test_event_str(self):
        """Event string includes title."""
        event = self.create_event(self.user, title='Doctor Appointment')
        self.assertIn('Doctor Appointment', str(event))
    
    def test_event_with_time(self):
        """Event can have start and end times."""
        event = LifeEvent.objects.create(
            user=self.user,
            title='Meeting',
            start_date=date.today(),
            start_time=datetime.now().time(),
            end_time=(datetime.now() + timedelta(hours=1)).time(),
            event_type='work'
        )
        self.assertIsNotNone(event.start_time)
    
    def test_all_day_event(self):
        """Event can be all-day."""
        event = self.create_event(
            self.user,
            is_all_day=True
        )
        self.assertTrue(event.is_all_day)


# =============================================================================
# 4. VIEW TESTS - Basic Loading
# =============================================================================

class LifeViewBasicTest(LifeTestMixin, TestCase):
    """Basic view loading tests."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
    
    # --- Authentication Required ---
    
    def test_life_home_requires_login(self):
        """Life home redirects anonymous users."""
        response = self.client.get(reverse('life:home'))
        self.assertEqual(response.status_code, 302)
    
    def test_project_list_requires_login(self):
        """Project list requires authentication."""
        response = self.client.get(reverse('life:project_list'))
        self.assertEqual(response.status_code, 302)
    
    def test_task_list_requires_login(self):
        """Task list requires authentication."""
        response = self.client.get(reverse('life:task_list'))
        self.assertEqual(response.status_code, 302)
    
    # --- Authenticated Access ---
    
    def test_life_home_loads(self):
        """Life home loads for authenticated user."""
        self.login_user()
        response = self.client.get(reverse('life:home'))
        self.assertEqual(response.status_code, 200)
    
    def test_project_list_loads(self):
        """Project list page loads."""
        self.login_user()
        response = self.client.get(reverse('life:project_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_project_create_loads(self):
        """Project create page loads."""
        self.login_user()
        response = self.client.get(reverse('life:project_create'))
        self.assertEqual(response.status_code, 200)
    
    def test_task_list_loads(self):
        """Task list page loads."""
        self.login_user()
        response = self.client.get(reverse('life:task_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_task_create_loads(self):
        """Task create page loads."""
        self.login_user()
        response = self.client.get(reverse('life:task_create'))
        self.assertEqual(response.status_code, 200)
    
    def test_calendar_loads(self):
        """Calendar page loads."""
        self.login_user()
        response = self.client.get(reverse('life:calendar'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 5. FORM VALIDATION TESTS
# =============================================================================

class LifeFormTest(LifeTestMixin, TestCase):
    """Tests for life form validation."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_create_project_via_model(self):
        """Project can be created via model."""
        project = self.create_project(self.user, title='New Project')
        self.assertTrue(
            Project.objects.filter(user=self.user, title='New Project').exists()
        )
    
    def test_create_task_via_model(self):
        """Task can be created via model."""
        task = self.create_task(self.user, title='New Task')
        self.assertTrue(
            Task.objects.filter(user=self.user, title='New Task').exists()
        )
    
    def test_project_create_has_form(self):
        """Project create page has form."""
        response = self.client.get(reverse('life:project_create'))
        self.assertIn('form', response.context)
    
    def test_task_create_has_form(self):
        """Task create page has form."""
        response = self.client.get(reverse('life:task_create'))
        self.assertIn('form', response.context)


# =============================================================================
# 6. EDGE CASE TESTS
# =============================================================================

class LifeEdgeCaseTest(LifeTestMixin, TestCase):
    """Tests for edge cases."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_project_list_empty(self):
        """Project list loads with no projects."""
        response = self.client.get(reverse('life:project_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_task_list_empty(self):
        """Task list loads with no tasks."""
        response = self.client.get(reverse('life:task_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_long_project_title(self):
        """Project handles long title."""
        long_title = 'A' * 200
        project = self.create_project(self.user, title=long_title)
        self.assertEqual(project.title, long_title)
    
    def test_long_task_title(self):
        """Task handles long title."""
        long_title = 'B' * 300
        task = self.create_task(self.user, title=long_title)
        self.assertEqual(task.title, long_title)
    
    def test_project_with_no_tasks(self):
        """Project with no tasks has 0% progress."""
        project = self.create_project(self.user)
        self.assertEqual(project.progress_percentage, 0)
    
    def test_project_all_tasks_complete(self):
        """Project with all tasks complete has 100% progress."""
        project = self.create_project(self.user)
        self.create_task(self.user, project=project, is_completed=True)
        self.create_task(self.user, project=project, is_completed=True)
        
        self.assertEqual(project.progress_percentage, 100)


# =============================================================================
# 7. BUSINESS LOGIC TESTS
# =============================================================================

class LifeBusinessLogicTest(LifeTestMixin, TestCase):
    """Tests for business logic."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_filter_active_projects(self):
        """Can filter active projects."""
        active = self.create_project(self.user, status='active')
        completed = self.create_project(self.user, status='completed')
        
        active_projects = Project.objects.filter(user=self.user, status='active')
        self.assertEqual(active_projects.count(), 1)
    
    def test_filter_incomplete_tasks(self):
        """Can filter incomplete tasks."""
        complete = self.create_task(self.user, is_completed=True)
        incomplete = self.create_task(self.user, is_completed=False)
        
        incomplete_tasks = Task.objects.filter(
            user=self.user, is_completed=False
        )
        self.assertEqual(incomplete_tasks.count(), 1)
    
    def test_filter_tasks_by_priority(self):
        """Can filter tasks by priority."""
        now_task = self.create_task(self.user, priority='now')
        someday_task = self.create_task(self.user, priority='someday')
        
        now_tasks = Task.objects.filter(user=self.user, priority='now')
        self.assertEqual(now_tasks.count(), 1)
    
    def test_filter_overdue_tasks(self):
        """Can filter overdue tasks."""
        overdue = self.create_task(
            self.user, 
            due_date=date.today() - timedelta(days=5)
        )
        future = self.create_task(
            self.user, 
            due_date=date.today() + timedelta(days=5)
        )
        
        overdue_tasks = [t for t in Task.objects.filter(user=self.user) if t.is_overdue]
        self.assertEqual(len(overdue_tasks), 1)


# =============================================================================
# 8. DATA ISOLATION TESTS
# =============================================================================

class LifeDataIsolationTest(LifeTestMixin, TestCase):
    """Tests to ensure users can only see their own life data."""
    
    def setUp(self):
        self.client = Client()
        self.user_a = self.create_user(email='usera@example.com')
        self.user_b = self.create_user(email='userb@example.com')
        
        self.project_a = self.create_project(self.user_a, title='User A Project')
        self.project_b = self.create_project(self.user_b, title='User B Project')
        
        self.task_a = self.create_task(self.user_a, title='User A Task')
        self.task_b = self.create_task(self.user_b, title='User B Task')
    
    def test_user_sees_only_own_projects(self):
        """User only sees their own projects."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('life:project_list'))
        
        self.assertContains(response, 'User A Project')
        self.assertNotContains(response, 'User B Project')
    
    def test_user_sees_only_own_tasks(self):
        """User only sees their own tasks."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(reverse('life:task_list'))
        
        self.assertContains(response, 'User A Task')
        self.assertNotContains(response, 'User B Task')
    
    def test_user_cannot_view_other_users_project(self):
        """User cannot view another user's project detail."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('life:project_detail', kwargs={'pk': self.project_b.pk})
        )
        self.assertEqual(response.status_code, 404)
    
    def test_user_cannot_edit_other_users_task(self):
        """User cannot edit another user's task."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.get(
            reverse('life:task_update', kwargs={'pk': self.task_b.pk})
        )
        self.assertEqual(response.status_code, 404)
    
    def test_user_cannot_delete_other_users_project(self):
        """User cannot delete another user's project."""
        self.client.login(email='usera@example.com', password='testpass123')
        response = self.client.post(
            reverse('life:project_delete', kwargs={'pk': self.project_b.pk})
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Project.objects.filter(pk=self.project_b.pk).exists())


# =============================================================================
# 9. CONTEXT TESTS
# =============================================================================

class LifeContextTest(LifeTestMixin, TestCase):
    """Tests for view context data."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_project_list_has_projects(self):
        """Project list includes projects in context."""
        self.create_project(self.user)
        
        response = self.client.get(reverse('life:project_list'))
        
        self.assertTrue(
            'object_list' in response.context or 'projects' in response.context
        )
    
    def test_task_list_has_tasks(self):
        """Task list includes tasks in context."""
        self.create_task(self.user)
        
        response = self.client.get(reverse('life:task_list'))
        
        self.assertTrue(
            'object_list' in response.context or 'tasks' in response.context
        )
    
    def test_project_detail_has_project(self):
        """Project detail includes project in context."""
        project = self.create_project(self.user)
        
        response = self.client.get(
            reverse('life:project_detail', kwargs={'pk': project.pk})
        )
        
        self.assertEqual(response.context['object'], project)


# =============================================================================
# 10. DELETE TESTS
# =============================================================================

class LifeDeleteTest(LifeTestMixin, TestCase):
    """Tests for deleting life entries."""
    
    def setUp(self):
        self.client = Client()
        self.user = self.create_user()
        self.login_user()
    
    def test_delete_project(self):
        """Project can be deleted."""
        project = self.create_project(self.user)
        
        response = self.client.post(
            reverse('life:project_delete', kwargs={'pk': project.pk})
        )
        
        self.assertIn(response.status_code, [200, 302])
    
    def test_delete_task(self):
        """Task can be deleted."""
        task = self.create_task(self.user)
        
        response = self.client.post(
            reverse('life:task_delete', kwargs={'pk': task.pk})
        )
        
        self.assertIn(response.status_code, [200, 302])
    
    def test_delete_project_cascades_to_tasks(self):
        """Deleting project deletes its tasks."""
        project = self.create_project(self.user)
        task = self.create_task(self.user, project=project)
        task_pk = task.pk
        
        project.delete()
        
        self.assertFalse(Task.objects.filter(pk=task_pk).exists())