# -*- coding: utf-8 -*-
"""
Admin Console - Comprehensive Tests

This test file covers:
1. Admin access control (staff required)
2. Dashboard view
3. Site configuration management
4. Theme management
5. Category management
6. User management views

Location: apps/admin_console/tests.py
"""

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model

from apps.core.models import SiteConfiguration

User = get_user_model()


# =============================================================================
# TEST HELPERS
# =============================================================================

class AdminTestMixin:
    """Common setup for admin tests."""

    def create_user(self, email='user@example.com', password='testpass123',
                    is_staff=False, is_superuser=False):
        """Create a test user with terms accepted and onboarding completed."""
        user = User.objects.create_user(
            email=email,
            password=password,
            is_staff=is_staff,
            is_superuser=is_superuser
        )
        self._accept_terms(user)
        self._complete_onboarding(user)
        return user

    def create_admin(self, email='admin@example.com', password='adminpass123'):
        """Create a staff user."""
        return self.create_user(
            email=email,
            password=password,
            is_staff=True
        )

    def create_superuser(self, email='super@example.com', password='superpass123'):
        """Create a superuser."""
        return self.create_user(
            email=email,
            password=password,
            is_staff=True,
            is_superuser=True
        )

    def _accept_terms(self, user):
        from apps.users.models import TermsAcceptance
        TermsAcceptance.objects.create(user=user, terms_version='1.0')

    def _complete_onboarding(self, user):
        """Mark user onboarding as complete."""
        user.preferences.has_completed_onboarding = True
        user.preferences.save()

    def get_or_create_default_project(self):
        """Get or create a default project for tests."""
        from apps.admin_console.models import AdminProject
        project, _ = AdminProject.objects.get_or_create(
            name='Test Project',
            defaults={
                'description': 'Default project for tests',
                'status': 'open'
            }
        )
        return project

    def make_executable_description(self, title='Test Task'):
        """
        Create a valid executable task description for tests.

        Returns a dict conforming to the WLJ Executable Task Standard.
        """
        return {
            'objective': f'Complete {title}',
            'inputs': [],
            'actions': ['Execute the task'],
            'output': 'Task completed successfully'
        }

    def login_admin(self, email='admin@example.com', password='adminpass123'):
        return self.client.login(email=email, password=password)

    def login_user(self, email='user@example.com', password='testpass123'):
        return self.client.login(email=email, password=password)


# =============================================================================
# 1. ACCESS CONTROL TESTS
# =============================================================================

class AdminAccessControlTest(AdminTestMixin, TestCase):
    """Tests for admin access control."""
    
    def setUp(self):
        self.client = Client()
        self.regular_user = self.create_user()
        self.admin_user = self.create_admin()
    
    def test_dashboard_requires_login(self):
        """Admin dashboard requires authentication."""
        response = self.client.get(reverse('admin_console:dashboard'))
        self.assertEqual(response.status_code, 302)
    
    def test_dashboard_requires_staff(self):
        """Admin dashboard requires staff status."""
        self.login_user()
        response = self.client.get(reverse('admin_console:dashboard'))
        self.assertEqual(response.status_code, 302)
    
    def test_dashboard_accessible_to_staff(self):
        """Admin dashboard accessible to staff users."""
        self.login_admin()
        response = self.client.get(reverse('admin_console:dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_site_config_requires_staff(self):
        """Site config requires staff status."""
        self.login_user()
        response = self.client.get(reverse('admin_console:site_config'))
        self.assertEqual(response.status_code, 302)
    
    def test_site_config_accessible_to_staff(self):
        """Site config accessible to staff."""
        self.login_admin()
        response = self.client.get(reverse('admin_console:site_config'))
        self.assertEqual(response.status_code, 200)
    
    def test_theme_list_requires_staff(self):
        """Theme list requires staff status."""
        self.login_user()
        response = self.client.get(reverse('admin_console:theme_list'))
        self.assertEqual(response.status_code, 302)
    
    def test_user_list_requires_staff(self):
        """User list requires staff status."""
        self.login_user()
        response = self.client.get(reverse('admin_console:user_list'))
        self.assertEqual(response.status_code, 302)


# =============================================================================
# 2. DASHBOARD VIEW TESTS
# =============================================================================

class AdminDashboardTest(AdminTestMixin, TestCase):
    """Tests for admin dashboard view."""
    
    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()
    
    def test_dashboard_loads(self):
        """Dashboard page loads."""
        response = self.client.get(reverse('admin_console:dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_dashboard_has_stats(self):
        """Dashboard shows statistics."""
        response = self.client.get(reverse('admin_console:dashboard'))
        self.assertIn('total_users', response.context)
    
    def test_dashboard_shows_recent_users(self):
        """Dashboard shows recent users."""
        for i in range(3):
            self.create_user(email='user{}@example.com'.format(i))
        
        response = self.client.get(reverse('admin_console:dashboard'))
        self.assertIn('recent_users', response.context)


# =============================================================================
# 3. SITE CONFIGURATION TESTS
# =============================================================================

class SiteConfigurationTest(AdminTestMixin, TestCase):
    """Tests for site configuration management."""
    
    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()
    
    def test_site_config_loads(self):
        """Site config page loads."""
        response = self.client.get(reverse('admin_console:site_config'))
        self.assertEqual(response.status_code, 200)
    
    def test_site_config_has_config_in_context(self):
        """Site config includes configuration in context."""
        response = self.client.get(reverse('admin_console:site_config'))
        self.assertIn('config', response.context)
    
    def test_update_site_name(self):
        """Site name can be updated."""
        response = self.client.post(reverse('admin_console:site_config'), {
            'site_name': 'My Custom Site',
            'tagline': 'A great tagline',
            'footer_text': 'Copyright 2025',
        })
        self.assertIn(response.status_code, [200, 302])
    
    def test_toggle_registration(self):
        """Registration toggle can be changed."""
        config, _ = SiteConfiguration.objects.get_or_create(pk=1)
        original = config.allow_registration
        
        config.allow_registration = not original
        config.save()
        
        config.refresh_from_db()
        self.assertNotEqual(config.allow_registration, original)


# =============================================================================
# 4. THEME MANAGEMENT TESTS
# =============================================================================

class ThemeManagementTest(AdminTestMixin, TestCase):
    """Tests for theme management."""
    
    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()
    
    def test_theme_list_loads(self):
        """Theme list page loads."""
        response = self.client.get(reverse('admin_console:theme_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_theme_create_loads(self):
        """Theme create page loads."""
        response = self.client.get(reverse('admin_console:theme_create'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 5. CATEGORY MANAGEMENT TESTS
# =============================================================================

class CategoryManagementTest(AdminTestMixin, TestCase):
    """Tests for category management."""
    
    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()
    
    def test_category_list_loads(self):
        """Category list page loads."""
        response = self.client.get(reverse('admin_console:category_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_category_create_loads(self):
        """Category create page loads."""
        response = self.client.get(reverse('admin_console:category_create'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 6. USER MANAGEMENT TESTS
# =============================================================================

class UserManagementTest(AdminTestMixin, TestCase):
    """Tests for user management views."""
    
    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()
    
    def test_user_list_loads(self):
        """User list page loads."""
        response = self.client.get(reverse('admin_console:user_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_user_list_shows_users(self):
        """User list displays users."""
        for i in range(3):
            self.create_user(email='testuser{}@example.com'.format(i))
        
        response = self.client.get(reverse('admin_console:user_list'))
        self.assertTrue(
            'users' in response.context or 
            'object_list' in response.context
        )


# =============================================================================
# 7. SUPERUSER VS STAFF TESTS
# =============================================================================

class SuperuserVsStaffTest(AdminTestMixin, TestCase):
    """Tests for superuser vs regular staff access."""
    
    def setUp(self):
        self.client = Client()
        self.staff = self.create_admin()
        self.superuser = self.create_superuser()
    
    def test_staff_can_access_dashboard(self):
        """Regular staff can access admin dashboard."""
        self.client.login(email='admin@example.com', password='adminpass123')
        response = self.client.get(reverse('admin_console:dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_superuser_can_access_dashboard(self):
        """Superuser can access admin dashboard."""
        self.client.login(email='super@example.com', password='superpass123')
        response = self.client.get(reverse('admin_console:dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_superuser_can_access_django_admin(self):
        """Superuser can access Django admin."""
        from django.conf import settings
        self.client.login(email='super@example.com', password='superpass123')
        # Admin URL is configurable via ADMIN_URL_PATH (Security Fix H-4)
        admin_path = getattr(settings, 'ADMIN_URL_PATH', 'admin')
        response = self.client.get(f'/{admin_path}/')
        self.assertIn(response.status_code, [200, 302])


# =============================================================================
# 8. EDGE CASES
# =============================================================================

class AdminEdgeCaseTest(AdminTestMixin, TestCase):
    """Edge case tests for admin console."""
    
    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()
    
    def test_empty_theme_list(self):
        """Theme list handles no themes."""
        response = self.client.get(reverse('admin_console:theme_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_empty_category_list(self):
        """Category list handles no categories."""
        response = self.client.get(reverse('admin_console:category_list'))
        self.assertEqual(response.status_code, 200)
    
    def test_single_user_in_list(self):
        """User list works with single user."""
        response = self.client.get(reverse('admin_console:user_list'))
        self.assertEqual(response.status_code, 200)


# =============================================================================
# 9. TEST HISTORY VIEWS TESTS
# =============================================================================

class TestRunListViewTest(AdminTestMixin, TestCase):
    """Tests for test run list view."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()

    def test_test_run_list_loads(self):
        """Test run list page loads."""
        response = self.client.get(reverse('admin_console:test_run_list'))
        self.assertEqual(response.status_code, 200)

    def test_test_run_list_requires_staff(self):
        """Test run list requires staff status."""
        regular_user = self.create_user()
        self.login_user()
        response = self.client.get(reverse('admin_console:test_run_list'))
        self.assertEqual(response.status_code, 302)

    def test_test_run_list_has_context(self):
        """Test run list has expected context."""
        response = self.client.get(reverse('admin_console:test_run_list'))
        self.assertIn('test_runs', response.context)
        self.assertIn('total_runs', response.context)
        self.assertIn('passed_runs', response.context)
        self.assertIn('failed_runs', response.context)
        self.assertIn('debug', response.context)

    def test_test_run_list_shows_test_runs(self):
        """Test run list shows test runs."""
        from apps.core.models import TestRun

        # Create test runs
        TestRun.objects.create(
            status='passed',
            total_tests=10,
            passed=10,
            failed=0,
            errors=0,
            duration_seconds=5.0
        )
        TestRun.objects.create(
            status='failed',
            total_tests=10,
            passed=8,
            failed=2,
            errors=0,
            duration_seconds=6.0
        )

        response = self.client.get(reverse('admin_console:test_run_list'))
        self.assertEqual(response.context['total_runs'], 2)
        self.assertEqual(response.context['passed_runs'], 1)
        self.assertEqual(response.context['failed_runs'], 1)

    def test_empty_test_run_list(self):
        """Test run list handles no runs."""
        response = self.client.get(reverse('admin_console:test_run_list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_runs'], 0)


class TestRunDetailViewTest(AdminTestMixin, TestCase):
    """Tests for test run detail view."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()

    def test_test_run_detail_loads(self):
        """Test run detail page loads."""
        from apps.core.models import TestRun

        test_run = TestRun.objects.create(
            status='passed',
            total_tests=10,
            passed=10
        )

        response = self.client.get(
            reverse('admin_console:test_run_detail', kwargs={'pk': test_run.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_test_run_detail_has_context(self):
        """Test run detail has test_run in context."""
        from apps.core.models import TestRun

        test_run = TestRun.objects.create(
            status='passed',
            total_tests=10,
            passed=10
        )

        response = self.client.get(
            reverse('admin_console:test_run_detail', kwargs={'pk': test_run.pk})
        )
        self.assertEqual(response.context['test_run'], test_run)
        self.assertIn('details', response.context)

    def test_test_run_detail_with_details(self):
        """Test run detail shows app details."""
        from apps.core.models import TestRun, TestRunDetail
        import json

        test_run = TestRun.objects.create(
            status='failed',
            total_tests=10,
            passed=8,
            failed=2
        )
        TestRunDetail.objects.create(
            test_run=test_run,
            app_name='journal',
            passed=5,
            failed=1,
            total=6,
            failed_tests=json.dumps(['test_something'])
        )

        response = self.client.get(
            reverse('admin_console:test_run_detail', kwargs={'pk': test_run.pk})
        )
        self.assertEqual(response.status_code, 200)
        details = list(response.context['details'])
        self.assertEqual(len(details), 1)
        self.assertEqual(details[0].app_name, 'journal')


class TestRunDeleteViewTest(AdminTestMixin, TestCase):
    """Tests for test run delete view."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()

    def test_test_run_delete_page_loads(self):
        """Test run delete confirmation page loads."""
        from apps.core.models import TestRun

        test_run = TestRun.objects.create(
            status='passed',
            total_tests=10,
            passed=10
        )

        response = self.client.get(
            reverse('admin_console:test_run_delete', kwargs={'pk': test_run.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_test_run_delete_works(self):
        """Test run can be deleted."""
        from apps.core.models import TestRun

        test_run = TestRun.objects.create(
            status='passed',
            total_tests=10,
            passed=10
        )
        pk = test_run.pk

        response = self.client.post(
            reverse('admin_console:test_run_delete', kwargs={'pk': pk})
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(TestRun.objects.filter(pk=pk).exists())


class RunTestsViewTest(AdminTestMixin, TestCase):
    """Tests for run tests view."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()

    def test_run_tests_requires_staff(self):
        """Run tests requires staff status."""
        regular_user = self.create_user()
        self.login_user()
        response = self.client.get(reverse('admin_console:run_tests'))
        self.assertEqual(response.status_code, 302)

    def test_run_tests_blocked_in_production(self):
        """Run tests is blocked when DEBUG=False."""
        from django.test import override_settings

        with override_settings(DEBUG=False):
            response = self.client.get(reverse('admin_console:run_tests'))
            # Should redirect to test run list with error message
            self.assertEqual(response.status_code, 302)
            self.assertRedirects(response, reverse('admin_console:test_run_list'))

    def test_run_tests_url_exists(self):
        """Run tests URL exists and is accessible to staff."""
        # Note: We don't actually run the tests in this test
        # Just verify the URL resolves and view can be accessed
        from django.urls import resolve

        resolved = resolve('/admin-console/tests/run/')
        self.assertEqual(resolved.view_name, 'admin_console:run_tests')


# =============================================================================
# 10. NEXT TASKS API TESTS
# =============================================================================

class NextTasksAPITest(AdminTestMixin, TestCase):
    """Tests for the next tasks API endpoint."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.regular_user = self.create_user()

    def test_next_tasks_requires_authentication(self):
        """Next tasks API requires authentication."""
        response = self.client.get('/api/admin/project/next-tasks/')
        self.assertEqual(response.status_code, 403)

    def test_next_tasks_requires_staff(self):
        """Next tasks API requires staff status."""
        self.login_user()
        response = self.client.get('/api/admin/project/next-tasks/')
        self.assertEqual(response.status_code, 403)

    def test_next_tasks_accessible_to_staff(self):
        """Next tasks API is accessible to staff users."""
        self.login_admin()
        response = self.client.get('/api/admin/project/next-tasks/')
        self.assertEqual(response.status_code, 200)

    def test_next_tasks_returns_json(self):
        """Next tasks API returns JSON."""
        self.login_admin()
        response = self.client.get('/api/admin/project/next-tasks/')
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_next_tasks_returns_empty_list_when_no_active_phase(self):
        """Next tasks API returns empty list when no active phase."""
        self.login_admin()
        response = self.client.get('/api/admin/project/next-tasks/')
        import json
        data = json.loads(response.content)
        self.assertEqual(data, [])

    def test_next_tasks_returns_tasks_from_active_phase(self):
        """Next tasks API returns tasks from active phase."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

        # Create an active phase
        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test objective',
            status='in_progress'
        )

        # Create default project for tasks
        project = self.get_or_create_default_project()

        # Create tasks
        task1 = AdminTask.objects.create(
            title='Task 1',
            description=self.make_executable_description('Task 1'),
            category='feature',
            priority=1,
            status='ready',
            effort='S',
            phase=phase,
            project=project,
            created_by='human'
        )
        task2 = AdminTask.objects.create(
            title='Task 2',
            description=self.make_executable_description('Task 2'),
            category='bug',
            priority=2,
            status='backlog',
            effort='M',
            phase=phase,
            project=project,
            created_by='claude'
        )

        self.login_admin()
        response = self.client.get('/api/admin/project/next-tasks/')
        import json
        data = json.loads(response.content)

        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]['title'], 'Task 1')
        self.assertEqual(data[0]['priority'], 1)
        self.assertEqual(data[0]['status'], 'ready')
        self.assertEqual(data[0]['phase_number'], 1)

    def test_next_tasks_does_not_return_done_tasks(self):
        """Next tasks API does not return done tasks."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        AdminTask.objects.create(
            title='Done Task',
            description='Done',
            category='feature',
            priority=1,
            status='done',
            effort='S',
            phase=phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )
        AdminTask.objects.create(
            title='Ready Task',
            description='Ready',
            category='feature',
            priority=2,
            status='ready',
            effort='S',
            phase=phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        self.login_admin()
        response = self.client.get('/api/admin/project/next-tasks/')
        import json
        data = json.loads(response.content)

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], 'Ready Task')

    def test_next_tasks_does_not_return_tasks_from_future_phases(self):
        """Next tasks API does not return tasks from future phases."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

        active_phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Active Phase',
            objective='Current',
            status='in_progress'
        )
        future_phase = AdminProjectPhase.objects.create(
            phase_number=2,
            name='Future Phase',
            objective='Later',
            status='not_started'
        )

        AdminTask.objects.create(
            title='Active Task',
            description='Current task',
            category='feature',
            priority=1,
            status='ready',
            effort='S',
            phase=active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )
        AdminTask.objects.create(
            title='Future Task',
            description='Later task',
            category='feature',
            priority=1,
            status='ready',
            effort='S',
            phase=future_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        self.login_admin()
        response = self.client.get('/api/admin/project/next-tasks/')
        import json
        data = json.loads(response.content)

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], 'Active Task')

    def test_next_tasks_respects_limit_param(self):
        """Next tasks API respects limit parameter."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        for i in range(10):
            AdminTask.objects.create(
                title=f'Task {i}',
                description=f'Description {i}',
                category='feature',
                priority=i,
                status='ready',
                effort='S',
                phase=phase,
                project=self.get_or_create_default_project(),
                created_by='human'
            )

        self.login_admin()
        response = self.client.get('/api/admin/project/next-tasks/?limit=3')
        import json
        data = json.loads(response.content)

        self.assertEqual(len(data), 3)

    def test_next_tasks_default_limit_is_5(self):
        """Next tasks API defaults to limit of 5."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        for i in range(10):
            AdminTask.objects.create(
                title=f'Task {i}',
                description=f'Description {i}',
                category='feature',
                priority=i,
                status='ready',
                effort='S',
                phase=phase,
                project=self.get_or_create_default_project(),
                created_by='human'
            )

        self.login_admin()
        response = self.client.get('/api/admin/project/next-tasks/')
        import json
        data = json.loads(response.content)

        self.assertEqual(len(data), 5)

    def test_next_tasks_orders_by_priority_then_created_at(self):
        """Next tasks API orders by priority, then created_at."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from django.utils import timezone
        import datetime

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        # Create tasks with same priority but different created times
        task1 = AdminTask.objects.create(
            title='Task A',
            description='A',
            category='feature',
            priority=1,
            status='ready',
            effort='S',
            phase=phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )
        task2 = AdminTask.objects.create(
            title='Task B',
            description='B',
            category='feature',
            priority=1,
            status='ready',
            effort='S',
            phase=phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )
        task3 = AdminTask.objects.create(
            title='Task C',
            description='C',
            category='feature',
            priority=2,
            status='ready',
            effort='S',
            phase=phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        self.login_admin()
        response = self.client.get('/api/admin/project/next-tasks/')
        import json
        data = json.loads(response.content)

        # Should be ordered by priority first, then by created_at (oldest first)
        self.assertEqual(data[0]['priority'], 1)
        self.assertEqual(data[1]['priority'], 1)
        self.assertEqual(data[2]['priority'], 2)


# =============================================================================
# 11. TASK STATUS TRANSITION TESTS
# =============================================================================

class TaskStatusTransitionModelTest(AdminTestMixin, TestCase):
    """Tests for AdminTask status transition validation."""

    def setUp(self):
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        self.client = Client()

        # Create an active phase
        self.active_phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Active Phase',
            objective='Test',
            status='in_progress'
        )

        # Create an inactive phase
        self.inactive_phase = AdminProjectPhase.objects.create(
            phase_number=2,
            name='Future Phase',
            objective='Later',
            status='not_started'
        )

    def test_valid_transition_backlog_to_ready(self):
        """Task can transition from backlog to ready."""
        from apps.admin_console.models import AdminTask
        task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='backlog',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )
        self.assertTrue(AdminTask.is_valid_transition('backlog', 'ready'))

    def test_valid_transition_ready_to_in_progress(self):
        """Task can transition from ready to in_progress."""
        from apps.admin_console.models import AdminTask
        self.assertTrue(AdminTask.is_valid_transition('ready', 'in_progress'))

    def test_valid_transition_in_progress_to_done(self):
        """Task can transition from in_progress to done."""
        from apps.admin_console.models import AdminTask
        self.assertTrue(AdminTask.is_valid_transition('in_progress', 'done'))

    def test_valid_transition_in_progress_to_blocked(self):
        """Task can transition from in_progress to blocked."""
        from apps.admin_console.models import AdminTask
        self.assertTrue(AdminTask.is_valid_transition('in_progress', 'blocked'))

    def test_valid_transition_blocked_to_ready(self):
        """Task can transition from blocked to ready."""
        from apps.admin_console.models import AdminTask
        self.assertTrue(AdminTask.is_valid_transition('blocked', 'ready'))

    def test_invalid_transition_backlog_to_in_progress(self):
        """Task cannot transition directly from backlog to in_progress."""
        from apps.admin_console.models import AdminTask
        self.assertFalse(AdminTask.is_valid_transition('backlog', 'in_progress'))

    def test_invalid_transition_backlog_to_done(self):
        """Task cannot transition directly from backlog to done."""
        from apps.admin_console.models import AdminTask
        self.assertFalse(AdminTask.is_valid_transition('backlog', 'done'))

    def test_invalid_transition_done_to_anything(self):
        """Done tasks cannot transition to any status."""
        from apps.admin_console.models import AdminTask
        self.assertFalse(AdminTask.is_valid_transition('done', 'ready'))
        self.assertFalse(AdminTask.is_valid_transition('done', 'in_progress'))
        self.assertFalse(AdminTask.is_valid_transition('done', 'backlog'))

    def test_transition_to_in_progress_allowed_regardless_of_phase(self):
        """Task can move to in_progress regardless of phase status.

        This test verifies that the phase status validation has been removed,
        allowing Claude to work on Ready tasks in any phase.
        """
        from apps.admin_console.models import AdminTask

        task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='ready',
            effort='S',
            phase=self.inactive_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        # Should NOT raise - phase status no longer blocks transition
        result = task.validate_status_transition('in_progress')
        self.assertTrue(result)

    def test_transition_to_blocked_requires_reason(self):
        """Task cannot move to blocked without a reason."""
        from apps.admin_console.models import AdminTask, TaskStatusTransitionError

        task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='in_progress',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        with self.assertRaises(TaskStatusTransitionError) as context:
            task.validate_status_transition('blocked')
        self.assertIn('reason', str(context.exception))

    def test_transition_to_blocked_with_reason_succeeds(self):
        """Task can move to blocked with a reason."""
        from apps.admin_console.models import AdminTask

        task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='in_progress',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        self.assertTrue(task.validate_status_transition('blocked', reason='Waiting for approval'))

    def test_transition_status_creates_activity_log(self):
        """transition_status creates an activity log entry."""
        from apps.admin_console.models import AdminTask, AdminActivityLog

        task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='backlog',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        log = task.transition_status('ready', created_by='human')

        self.assertIsNotNone(log)
        self.assertEqual(log.task, task)
        self.assertIn('backlog', log.action)
        self.assertIn('ready', log.action)
        self.assertEqual(log.created_by, 'human')

    def test_transition_status_with_reason_includes_reason_in_log(self):
        """transition_status includes reason in activity log."""
        from apps.admin_console.models import AdminTask

        task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='in_progress',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        log = task.transition_status('blocked', reason='API unavailable', created_by='claude')

        self.assertIn('API unavailable', log.action)
        self.assertEqual(log.created_by, 'claude')

    def test_transition_status_updates_blocked_reason_field(self):
        """transition_status sets blocked_reason when moving to blocked."""
        from apps.admin_console.models import AdminTask

        task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='in_progress',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        task.transition_status('blocked', reason='Waiting for review')
        task.refresh_from_db()

        self.assertEqual(task.blocked_reason, 'Waiting for review')

    def test_transition_status_clears_blocked_reason_on_unblock(self):
        """transition_status clears blocked_reason when unblocking."""
        from apps.admin_console.models import AdminTask

        task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='blocked',
            blocked_reason='Some reason',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        task.transition_status('ready')
        task.refresh_from_db()

        self.assertEqual(task.blocked_reason, '')

    def test_same_status_transition_returns_none(self):
        """Transitioning to same status returns None (no-op)."""
        from apps.admin_console.models import AdminTask

        task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='ready',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        log = task.transition_status('ready')
        self.assertIsNone(log)


# =============================================================================
# 12. TASK STATUS UPDATE API TESTS
# =============================================================================

class TaskStatusUpdateAPITest(AdminTestMixin, TestCase):
    """Tests for the task status update API endpoint."""

    def setUp(self):
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        self.client = Client()
        self.admin = self.create_admin()
        self.regular_user = self.create_user()

        # Create an active phase
        self.active_phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Active Phase',
            objective='Test',
            status='in_progress'
        )

        # Create test tasks
        self.backlog_task = AdminTask.objects.create(
            title='Backlog Task',
            description='In backlog',
            category='feature',
            status='backlog',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )
        self.ready_task = AdminTask.objects.create(
            title='Ready Task',
            description='Ready to start',
            category='feature',
            status='ready',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )
        self.in_progress_task = AdminTask.objects.create(
            title='In Progress Task',
            description='Being worked on',
            category='feature',
            status='in_progress',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

    def test_status_update_requires_authentication(self):
        """Status update API requires authentication."""
        import json
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)

    def test_status_update_requires_staff(self):
        """Status update API requires staff status."""
        import json
        self.login_user()
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)

    def test_status_update_accessible_to_staff(self):
        """Status update API is accessible to staff users."""
        import json
        self.login_admin()
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

    def test_status_update_returns_json(self):
        """Status update API returns JSON."""
        import json
        self.login_admin()
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_status_update_returns_updated_task(self):
        """Status update API returns updated task data."""
        import json
        self.login_admin()
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertEqual(data['id'], self.backlog_task.pk)
        self.assertEqual(data['status'], 'ready')
        self.assertEqual(data['title'], 'Backlog Task')

    def test_status_update_includes_activity_log(self):
        """Status update API includes activity log in response."""
        import json
        self.login_admin()
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        data = json.loads(response.content)
        self.assertIn('activity_log', data)
        self.assertIn('backlog', data['activity_log']['action'])
        self.assertIn('ready', data['activity_log']['action'])

    def test_status_update_invalid_transition_returns_400(self):
        """Status update API returns 400 for invalid transition."""
        import json
        self.login_admin()
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({'status': 'done'}),  # backlog -> done is invalid
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn('error', data)

    def test_status_update_missing_status_returns_400(self):
        """Status update API returns 400 when status is missing."""
        import json
        self.login_admin()
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn('error', data)
        self.assertIn('status', data['error'])

    def test_status_update_invalid_status_returns_400(self):
        """Status update API returns 400 for invalid status value."""
        import json
        self.login_admin()
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({'status': 'invalid_status'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn('error', data)

    def test_status_update_nonexistent_task_returns_404(self):
        """Status update API returns 404 for nonexistent task."""
        import json
        self.login_admin()
        response = self.client.patch(
            '/admin-console/api/admin/project/tasks/99999/status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_status_update_blocked_without_reason_returns_400(self):
        """Status update API returns 400 when blocking without reason."""
        import json
        self.login_admin()
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.in_progress_task.pk}/status/',
            data=json.dumps({'status': 'blocked'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content)
        self.assertIn('reason', data['error'])

    def test_status_update_blocked_with_reason_succeeds(self):
        """Status update API succeeds when blocking with reason."""
        import json
        self.login_admin()
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.in_progress_task.pk}/status/',
            data=json.dumps({'status': 'blocked', 'reason': 'Waiting for API'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'blocked')
        self.assertEqual(data['blocked_reason'], 'Waiting for API')

    def test_status_update_invalid_json_returns_400(self):
        """Status update API returns 400 for invalid JSON."""
        self.login_admin()
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data='not valid json',
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_full_workflow_backlog_to_done(self):
        """Full workflow from backlog to done."""
        import json
        self.login_admin()

        # backlog -> ready
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        # ready -> in_progress
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({'status': 'in_progress'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        # in_progress -> done
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.backlog_task.pk}/status/',
            data=json.dumps({'status': 'done'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'done')

    def test_workflow_with_blocking(self):
        """Workflow with blocking and unblocking."""
        import json
        self.login_admin()

        # in_progress -> blocked
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.in_progress_task.pk}/status/',
            data=json.dumps({'status': 'blocked', 'reason': 'Waiting for approval'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'blocked')
        self.assertEqual(data['blocked_reason'], 'Waiting for approval')

        # blocked -> ready
        response = self.client.patch(
            f'/admin-console/api/admin/project/tasks/{self.in_progress_task.pk}/status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'ready')
        self.assertEqual(data['blocked_reason'], '')  # Cleared


# =============================================================================
# 13. BLOCKER TASK CREATION TESTS
# =============================================================================

class BlockerTaskCreationTest(AdminTestMixin, TestCase):
    """Tests for blocker task creation functionality."""

    def setUp(self):
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        self.client = Client()
        self.admin = self.create_admin()

        # Create an active phase
        self.active_phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Active Phase',
            objective='Test',
            status='in_progress'
        )

        # Create a task in progress
        self.in_progress_task = AdminTask.objects.create(
            title='Working Task',
            description='Currently being worked on',
            category='feature',
            priority=2,
            status='in_progress',
            effort='M',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='claude'
        )

    def test_create_blocker_task_success(self):
        """Blocker task is created with correct attributes."""
        from apps.admin_console.services import create_blocker_task

        blocker_task, blocked_task, blocker_log, blocked_log = create_blocker_task(
            blocked_task=self.in_progress_task,
            title='Configure API Key',
            description='Working on Working Task. The OPENAI_API_KEY is missing. Configure OPENAI_API_KEY in environment.',
            category='infra',
            effort='S',
            created_by='claude'
        )

        # Verify blocker task was created correctly
        self.assertEqual(blocker_task.title, 'Configure API Key')
        self.assertIn('OPENAI_API_KEY', blocker_task.description)
        self.assertEqual(blocker_task.category, 'infra')
        self.assertEqual(blocker_task.status, 'ready')
        self.assertEqual(blocker_task.effort, 'S')
        self.assertEqual(blocker_task.created_by, 'claude')
        self.assertEqual(blocker_task.phase, self.active_phase)

    def test_create_blocker_task_priority(self):
        """Blocker task priority is equal to or higher than blocked task."""
        from apps.admin_console.services import create_blocker_task

        blocker_task, _, _, _ = create_blocker_task(
            blocked_task=self.in_progress_task,
            title='Get Business Approval',
            description='Need business decision on feature scope.',
            category='business',
            effort='M',
            created_by='human'
        )

        # Priority should be same or higher (lower number)
        self.assertLessEqual(blocker_task.priority, self.in_progress_task.priority)

    def test_create_blocker_task_updates_original_task(self):
        """Original task is updated to blocked status with reference."""
        from apps.admin_console.services import create_blocker_task
        from apps.admin_console.models import AdminTask

        blocker_task, blocked_task, _, _ = create_blocker_task(
            blocked_task=self.in_progress_task,
            title='Manual Server Setup',
            description='Working on Working Task. Server needs manual configuration. SSH to server and configure firewall.',
            category='infra',
            effort='S',
            created_by='claude'
        )

        # Refresh from database
        blocked_task.refresh_from_db()

        # Verify blocked task was updated
        self.assertEqual(blocked_task.status, 'blocked')
        self.assertIn('Manual Server Setup', blocked_task.blocked_reason)
        self.assertIn(str(blocker_task.pk), blocked_task.blocked_reason)
        self.assertEqual(blocked_task.blocking_task, blocker_task)

    def test_create_blocker_task_creates_activity_logs(self):
        """Activity logs are created for both tasks."""
        from apps.admin_console.services import create_blocker_task
        from apps.admin_console.models import AdminActivityLog

        initial_log_count = AdminActivityLog.objects.count()

        blocker_task, blocked_task, blocker_log, blocked_log = create_blocker_task(
            blocked_task=self.in_progress_task,
            title='Get Credentials',
            description='Need external account credentials.',
            category='infra',
            effort='S',
            created_by='claude'
        )

        # Two logs should be created
        self.assertEqual(AdminActivityLog.objects.count(), initial_log_count + 2)

        # Verify blocker log
        self.assertEqual(blocker_log.task, blocker_task)
        self.assertIn('Blocker task created', blocker_log.action)
        self.assertIn(self.in_progress_task.title, blocker_log.action)
        self.assertEqual(blocker_log.created_by, 'claude')

        # Verify blocked log
        self.assertEqual(blocked_log.task, blocked_task)
        self.assertIn('Task blocked', blocked_log.action)
        self.assertIn('Get Credentials', blocked_log.action)
        self.assertEqual(blocked_log.created_by, 'claude')

    def test_create_blocker_task_invalid_category_raises_error(self):
        """Creating blocker with invalid category raises ValueError."""
        from apps.admin_console.services import create_blocker_task

        with self.assertRaises(ValueError) as context:
            create_blocker_task(
                blocked_task=self.in_progress_task,
                title='Some Task',
                description='Description',
                category='feature',  # Not allowed for blockers
                effort='S',
                created_by='claude'
            )

        self.assertIn('infra', str(context.exception))
        self.assertIn('business', str(context.exception))

    def test_create_blocker_task_invalid_effort_raises_error(self):
        """Creating blocker with invalid effort raises ValueError."""
        from apps.admin_console.services import create_blocker_task

        with self.assertRaises(ValueError) as context:
            create_blocker_task(
                blocked_task=self.in_progress_task,
                title='Some Task',
                description='Description',
                category='infra',
                effort='L',  # Only S or M allowed for blockers
                created_by='claude'
            )

        self.assertIn("'S'", str(context.exception))
        self.assertIn("'M'", str(context.exception))

    def test_create_blocker_task_only_in_progress_tasks(self):
        """Can only create blocker for in_progress tasks."""
        from apps.admin_console.models import AdminTask
        from apps.admin_console.services import create_blocker_task

        # Create a task in ready status
        ready_task = AdminTask.objects.create(
            title='Ready Task',
            description='Not started yet',
            category='feature',
            priority=1,
            status='ready',
            effort='S',
            phase=self.active_phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        with self.assertRaises(ValueError) as context:
            create_blocker_task(
                blocked_task=ready_task,
                title='Blocker',
                description='Description',
                category='infra',
                effort='S',
                created_by='claude'
            )

        self.assertIn('in_progress', str(context.exception))
        self.assertIn('ready', str(context.exception))

    def test_create_blocker_task_business_category(self):
        """Blocker task can be created with business category."""
        from apps.admin_console.services import create_blocker_task

        blocker_task, _, _, _ = create_blocker_task(
            blocked_task=self.in_progress_task,
            title='Get Pricing Approval',
            description='Working on pricing feature. Need business decision on pricing tiers. Approval required from product team.',
            category='business',
            effort='M',
            created_by='human'
        )

        self.assertEqual(blocker_task.category, 'business')

    def test_blocking_task_relationship(self):
        """Blocking task relationship is properly set."""
        from apps.admin_console.services import create_blocker_task
        from apps.admin_console.models import AdminTask

        blocker_task, blocked_task, _, _ = create_blocker_task(
            blocked_task=self.in_progress_task,
            title='Environment Setup',
            description='Missing config.',
            category='infra',
            effort='S',
            created_by='claude'
        )

        # Verify relationship from blocked task
        blocked_task.refresh_from_db()
        self.assertEqual(blocked_task.blocking_task, blocker_task)

        # Verify reverse relationship (blocks)
        self.assertEqual(blocker_task.blocks.count(), 1)
        self.assertEqual(blocker_task.blocks.first(), blocked_task)


class BlockerTaskQueryTests(AdminTestMixin, TestCase):
    """Tests for blocker task query functions."""

    def setUp(self):
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

        # Create phases
        self.phase1 = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Phase 1',
            objective='Test',
            status='in_progress'
        )
        self.phase2 = AdminProjectPhase.objects.create(
            phase_number=2,
            name='Phase 2',
            objective='Later',
            status='not_started'
        )

        # Create some tasks
        self.task1 = AdminTask.objects.create(
            title='Task 1',
            description='Description 1',
            category='feature',
            priority=1,
            status='in_progress',
            effort='M',
            phase=self.phase1,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

    def test_get_blocked_tasks_returns_blocked_only(self):
        """get_blocked_tasks returns only blocked tasks."""
        from apps.admin_console.models import AdminTask
        from apps.admin_console.services import get_blocked_tasks, create_blocker_task

        # Create a blocker
        create_blocker_task(
            blocked_task=self.task1,
            title='Blocker 1',
            description='Blocks Task 1',
            category='infra',
            effort='S',
            created_by='claude'
        )

        blocked_tasks = get_blocked_tasks()
        self.assertEqual(blocked_tasks.count(), 1)
        self.assertEqual(blocked_tasks.first().title, 'Task 1')

    def test_get_blocked_tasks_filters_by_phase(self):
        """get_blocked_tasks can filter by phase."""
        from apps.admin_console.models import AdminTask
        from apps.admin_console.services import get_blocked_tasks, create_blocker_task

        # Create a blocked task in phase 2
        task2 = AdminTask.objects.create(
            title='Task 2',
            description='Description 2',
            category='feature',
            priority=1,
            status='in_progress',
            effort='M',
            phase=self.phase2,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        # Block both tasks
        create_blocker_task(
            blocked_task=self.task1,
            title='Blocker 1',
            description='Blocks Task 1',
            category='infra',
            effort='S',
            created_by='claude'
        )
        create_blocker_task(
            blocked_task=task2,
            title='Blocker 2',
            description='Blocks Task 2',
            category='infra',
            effort='S',
            created_by='claude'
        )

        # Filter by phase 1
        phase1_blocked = get_blocked_tasks(phase=self.phase1)
        self.assertEqual(phase1_blocked.count(), 1)
        self.assertEqual(phase1_blocked.first().title, 'Task 1')

        # Filter by phase 2
        phase2_blocked = get_blocked_tasks(phase=self.phase2)
        self.assertEqual(phase2_blocked.count(), 1)
        self.assertEqual(phase2_blocked.first().title, 'Task 2')

    def test_get_blocker_tasks_returns_blockers(self):
        """get_blocker_tasks returns tasks that are blocking other tasks."""
        from apps.admin_console.services import get_blocker_tasks, create_blocker_task

        # Create a blocker
        blocker_task, _, _, _ = create_blocker_task(
            blocked_task=self.task1,
            title='Blocker 1',
            description='Blocks Task 1',
            category='infra',
            effort='S',
            created_by='claude'
        )

        blocker_tasks = get_blocker_tasks()
        self.assertEqual(blocker_tasks.count(), 1)
        self.assertEqual(blocker_tasks.first().title, 'Blocker 1')

    def test_get_blocker_tasks_filters_by_phase(self):
        """get_blocker_tasks can filter by phase."""
        from apps.admin_console.models import AdminTask
        from apps.admin_console.services import get_blocker_tasks, create_blocker_task

        # Create a blocked task in phase 2
        task2 = AdminTask.objects.create(
            title='Task 2',
            description='Description 2',
            category='feature',
            priority=1,
            status='in_progress',
            effort='M',
            phase=self.phase2,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        # Block both tasks
        blocker1, _, _, _ = create_blocker_task(
            blocked_task=self.task1,
            title='Blocker 1',
            description='Blocks Task 1',
            category='infra',
            effort='S',
            created_by='claude'
        )
        blocker2, _, _, _ = create_blocker_task(
            blocked_task=task2,
            title='Blocker 2',
            description='Blocks Task 2',
            category='infra',
            effort='S',
            created_by='claude'
        )

        # Filter by phase 1
        phase1_blockers = get_blocker_tasks(phase=self.phase1)
        self.assertEqual(phase1_blockers.count(), 1)
        self.assertEqual(phase1_blockers.first().title, 'Blocker 1')


class BlockerModelFieldTests(AdminTestMixin, TestCase):
    """Tests for the blocking_task model field."""

    def setUp(self):
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

        self.phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        self.task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            priority=1,
            status='ready',
            effort='S',
            phase=self.phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

    def test_blocking_task_is_nullable(self):
        """blocking_task field can be null."""
        self.assertIsNone(self.task.blocking_task)

    def test_blocking_task_can_be_set(self):
        """blocking_task field can be set to another task."""
        from apps.admin_console.models import AdminTask

        blocker = AdminTask.objects.create(
            title='Blocker Task',
            description='Blocker',
            category='infra',
            priority=1,
            status='ready',
            effort='S',
            phase=self.phase,
            project=self.get_or_create_default_project(),
            created_by='claude'
        )

        self.task.blocking_task = blocker
        self.task.save()

        self.task.refresh_from_db()
        self.assertEqual(self.task.blocking_task, blocker)

    def test_blocking_task_set_null_on_delete(self):
        """blocking_task is set to null when blocker is deleted."""
        from apps.admin_console.models import AdminTask

        blocker = AdminTask.objects.create(
            title='Blocker Task',
            description='Blocker',
            category='infra',
            priority=1,
            status='ready',
            effort='S',
            phase=self.phase,
            project=self.get_or_create_default_project(),
            created_by='claude'
        )

        self.task.blocking_task = blocker
        self.task.save()

        # Delete the blocker
        blocker.delete()

        # Verify blocking_task is now null
        self.task.refresh_from_db()
        self.assertIsNone(self.task.blocking_task)

    def test_blocks_reverse_relationship(self):
        """blocks reverse relationship works correctly."""
        from apps.admin_console.models import AdminTask

        blocker = AdminTask.objects.create(
            title='Blocker Task',
            description='Blocker',
            category='infra',
            priority=1,
            status='ready',
            effort='S',
            phase=self.phase,
            project=self.get_or_create_default_project(),
            created_by='claude'
        )

        # Create multiple tasks blocked by the same blocker
        task1 = AdminTask.objects.create(
            title='Blocked Task 1',
            description='Blocked 1',
            category='feature',
            priority=1,
            status='blocked',
            effort='S',
            phase=self.phase,
            project=self.get_or_create_default_project(),
            created_by='human',
            blocking_task=blocker
        )
        task2 = AdminTask.objects.create(
            title='Blocked Task 2',
            description='Blocked 2',
            category='feature',
            priority=2,
            status='blocked',
            effort='S',
            phase=self.phase,
            project=self.get_or_create_default_project(),
            created_by='human',
            blocking_task=blocker
        )

        # Verify reverse relationship
        self.assertEqual(blocker.blocks.count(), 2)
        self.assertIn(task1, blocker.blocks.all())
        self.assertIn(task2, blocker.blocks.all())


# =============================================================================
# 14. PROJECT METRICS SERVICE TESTS
# =============================================================================

class ProjectMetricsServiceTest(AdminTestMixin, TestCase):
    """Tests for the get_project_metrics service function."""

    def test_metrics_with_no_tasks(self):
        """Metrics returns zeros when no tasks exist."""
        from apps.admin_console.services import get_project_metrics

        metrics = get_project_metrics()

        self.assertIsNone(metrics['active_phase'])
        self.assertEqual(metrics['global']['total_tasks'], 0)
        self.assertEqual(metrics['global']['completed_tasks'], 0)
        self.assertEqual(metrics['global']['remaining_tasks'], 0)
        self.assertEqual(metrics['global']['blocked_tasks'], 0)
        self.assertEqual(metrics['active_phase_metrics']['total_tasks'], 0)
        self.assertEqual(metrics['tasks_created_by_claude'], 0)
        self.assertEqual(metrics['high_priority_remaining_tasks'], 0)

    def test_metrics_with_no_active_phase(self):
        """Metrics returns None for active_phase when no phase is active."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import get_project_metrics

        # Create a phase that's not active
        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Inactive Phase',
            objective='Test',
            status='not_started'
        )
        AdminTask.objects.create(
            title='Task 1',
            description='Description',
            category='feature',
            status='backlog',
            effort='S',
            phase=phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        metrics = get_project_metrics()

        self.assertIsNone(metrics['active_phase'])
        self.assertEqual(metrics['global']['total_tasks'], 1)
        self.assertEqual(metrics['active_phase_metrics']['total_tasks'], 0)

    def test_metrics_global_counts(self):
        """Metrics computes global counts correctly."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import get_project_metrics

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        # Create tasks with various statuses
        AdminTask.objects.create(
            title='Done Task 1', description='D', category='feature',
            status='done', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Done Task 2', description='D', category='feature',
            status='done', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Blocked Task', description='D', category='feature',
            status='blocked', blocked_reason='Waiting', effort='S',
            phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Ready Task', description='D', category='feature',
            status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Backlog Task', description='D', category='feature',
            status='backlog', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        metrics = get_project_metrics()

        self.assertEqual(metrics['global']['total_tasks'], 5)
        self.assertEqual(metrics['global']['completed_tasks'], 2)
        self.assertEqual(metrics['global']['remaining_tasks'], 3)
        self.assertEqual(metrics['global']['blocked_tasks'], 1)

    def test_metrics_active_phase_counts(self):
        """Metrics computes active phase counts correctly."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import get_project_metrics

        # Create two phases, one active
        active_phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Active Phase',
            objective='Current',
            status='in_progress'
        )
        inactive_phase = AdminProjectPhase.objects.create(
            phase_number=2,
            name='Inactive Phase',
            objective='Later',
            status='not_started'
        )

        # Create tasks in active phase
        AdminTask.objects.create(
            title='Active Done', description='D', category='feature',
            status='done', effort='S', phase=active_phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Active Ready', description='D', category='feature',
            status='ready', effort='S', phase=active_phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Active Blocked', description='D', category='feature',
            status='blocked', blocked_reason='Waiting', effort='S',
            phase=active_phase, project=self.get_or_create_default_project(), created_by='human'
        )

        # Create tasks in inactive phase
        AdminTask.objects.create(
            title='Inactive Task', description='D', category='feature',
            status='backlog', effort='S', phase=inactive_phase, project=self.get_or_create_default_project(), created_by='human'
        )

        metrics = get_project_metrics()

        self.assertEqual(metrics['active_phase'], 1)
        self.assertEqual(metrics['active_phase_metrics']['total_tasks'], 3)
        self.assertEqual(metrics['active_phase_metrics']['completed_tasks'], 1)
        self.assertEqual(metrics['active_phase_metrics']['remaining_tasks'], 2)
        self.assertEqual(metrics['active_phase_metrics']['blocked_tasks'], 1)

    def test_metrics_tasks_created_by_claude(self):
        """Metrics counts tasks created by Claude."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import get_project_metrics

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        AdminTask.objects.create(
            title='Human Task', description='D', category='feature',
            status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Claude Task 1', description='D', category='feature',
            status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='claude'
        )
        AdminTask.objects.create(
            title='Claude Task 2', description='D', category='infra',
            status='done', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='claude'
        )

        metrics = get_project_metrics()

        self.assertEqual(metrics['tasks_created_by_claude'], 2)

    def test_metrics_high_priority_remaining_tasks(self):
        """Metrics counts high priority remaining tasks."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import get_project_metrics

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        # Priority 1 (high), remaining
        AdminTask.objects.create(
            title='P1 Ready', description='D', category='feature',
            priority=1, status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        # Priority 2 (high), remaining
        AdminTask.objects.create(
            title='P2 Backlog', description='D', category='feature',
            priority=2, status='backlog', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        # Priority 1 (high), but done - should not count
        AdminTask.objects.create(
            title='P1 Done', description='D', category='feature',
            priority=1, status='done', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        # Priority 3 (not high), remaining - should not count
        AdminTask.objects.create(
            title='P3 Ready', description='D', category='feature',
            priority=3, status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        metrics = get_project_metrics()

        self.assertEqual(metrics['high_priority_remaining_tasks'], 2)

    def test_metrics_is_read_only(self):
        """Metrics function does not mutate any data."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import get_project_metrics

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )
        task = AdminTask.objects.create(
            title='Task', description='D', category='feature',
            status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        # Call metrics multiple times
        metrics1 = get_project_metrics()
        metrics2 = get_project_metrics()

        # Task should still exist and be unchanged
        task.refresh_from_db()
        self.assertEqual(task.status, 'ready')
        self.assertEqual(AdminTask.objects.count(), 1)

        # Results should be consistent
        self.assertEqual(metrics1, metrics2)


# =============================================================================
# 15. PROJECT METRICS API TESTS
# =============================================================================

class ProjectMetricsAPITest(AdminTestMixin, TestCase):
    """Tests for the project metrics API endpoint."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.regular_user = self.create_user()

    def test_metrics_requires_authentication(self):
        """Metrics API requires authentication."""
        response = self.client.get('/api/admin/project/metrics/')
        self.assertEqual(response.status_code, 403)

    def test_metrics_requires_staff(self):
        """Metrics API requires staff status."""
        self.login_user()
        response = self.client.get('/api/admin/project/metrics/')
        self.assertEqual(response.status_code, 403)

    def test_metrics_accessible_to_staff(self):
        """Metrics API is accessible to staff users."""
        self.login_admin()
        response = self.client.get('/api/admin/project/metrics/')
        self.assertEqual(response.status_code, 200)

    def test_metrics_returns_json(self):
        """Metrics API returns JSON."""
        self.login_admin()
        response = self.client.get('/api/admin/project/metrics/')
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_metrics_returns_expected_structure(self):
        """Metrics API returns expected JSON structure."""
        self.login_admin()
        response = self.client.get('/api/admin/project/metrics/')
        import json
        data = json.loads(response.content)

        self.assertIn('active_phase', data)
        self.assertIn('global', data)
        self.assertIn('active_phase_metrics', data)
        self.assertIn('tasks_created_by_claude', data)
        self.assertIn('high_priority_remaining_tasks', data)

        # Check nested structure
        self.assertIn('total_tasks', data['global'])
        self.assertIn('completed_tasks', data['global'])
        self.assertIn('remaining_tasks', data['global'])
        self.assertIn('blocked_tasks', data['global'])

        self.assertIn('total_tasks', data['active_phase_metrics'])
        self.assertIn('completed_tasks', data['active_phase_metrics'])
        self.assertIn('remaining_tasks', data['active_phase_metrics'])
        self.assertIn('blocked_tasks', data['active_phase_metrics'])

    def test_metrics_returns_zeros_when_no_data(self):
        """Metrics API returns zeros when no tasks exist."""
        self.login_admin()
        response = self.client.get('/api/admin/project/metrics/')
        import json
        data = json.loads(response.content)

        self.assertIsNone(data['active_phase'])
        self.assertEqual(data['global']['total_tasks'], 0)
        self.assertEqual(data['global']['completed_tasks'], 0)
        self.assertEqual(data['global']['remaining_tasks'], 0)
        self.assertEqual(data['global']['blocked_tasks'], 0)

    def test_metrics_with_tasks(self):
        """Metrics API returns correct counts with tasks."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

        phase = AdminProjectPhase.objects.create(
            phase_number=3,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        # Create various tasks
        AdminTask.objects.create(
            title='Done Task', description='D', category='feature',
            status='done', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Ready Task', description='D', category='feature',
            status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='claude'
        )
        AdminTask.objects.create(
            title='Blocked Task', description='D', category='feature',
            status='blocked', blocked_reason='Waiting', effort='S',
            phase=phase, project=self.get_or_create_default_project(), created_by='claude', priority=1
        )

        self.login_admin()
        response = self.client.get('/api/admin/project/metrics/')
        import json
        data = json.loads(response.content)

        self.assertEqual(data['active_phase'], 3)
        self.assertEqual(data['global']['total_tasks'], 3)
        self.assertEqual(data['global']['completed_tasks'], 1)
        self.assertEqual(data['global']['remaining_tasks'], 2)
        self.assertEqual(data['global']['blocked_tasks'], 1)
        self.assertEqual(data['active_phase_metrics']['total_tasks'], 3)
        self.assertEqual(data['tasks_created_by_claude'], 2)
        self.assertEqual(data['high_priority_remaining_tasks'], 1)


# =============================================================================
# 16. SYSTEM STATE SNAPSHOT TESTS
# =============================================================================

class SystemStateSnapshotServiceTest(AdminTestMixin, TestCase):
    """Tests for the SystemStateSnapshot dataclass and build function."""

    def test_snapshot_with_no_active_phase(self):
        """Snapshot returns null-safe values when no active phase."""
        from apps.admin_console.services import build_system_state_snapshot

        snapshot = build_system_state_snapshot()

        self.assertIsNone(snapshot.active_phase_number)
        self.assertIsNone(snapshot.active_phase_name)
        self.assertIsNone(snapshot.active_phase_status)
        self.assertIsNone(snapshot.active_phase_objective)
        self.assertEqual(snapshot.open_tasks_count, 0)
        self.assertEqual(snapshot.blocked_tasks_count, 0)
        self.assertIsNotNone(snapshot.last_updated)

    def test_snapshot_with_active_phase(self):
        """Snapshot returns correct phase info when active phase exists."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import build_system_state_snapshot

        phase = AdminProjectPhase.objects.create(
            phase_number=5,
            name='Test Phase',
            objective='Test objective',
            status='in_progress'
        )

        snapshot = build_system_state_snapshot()

        self.assertEqual(snapshot.active_phase_number, 5)
        self.assertEqual(snapshot.active_phase_name, 'Test Phase')
        self.assertEqual(snapshot.active_phase_status, 'in_progress')
        self.assertEqual(snapshot.active_phase_objective, 'Test objective')

    def test_snapshot_counts_open_tasks(self):
        """Snapshot counts open tasks (backlog, ready, in_progress) correctly."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import build_system_state_snapshot

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        # Open tasks
        AdminTask.objects.create(
            title='Backlog Task', description='D', category='feature',
            status='backlog', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Ready Task', description='D', category='feature',
            status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='In Progress Task', description='D', category='feature',
            status='in_progress', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        # Not open (done)
        AdminTask.objects.create(
            title='Done Task', description='D', category='feature',
            status='done', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        snapshot = build_system_state_snapshot()

        self.assertEqual(snapshot.open_tasks_count, 3)

    def test_snapshot_counts_blocked_tasks(self):
        """Snapshot counts blocked tasks correctly."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import build_system_state_snapshot

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        # Blocked tasks
        AdminTask.objects.create(
            title='Blocked Task 1', description='D', category='feature',
            status='blocked', blocked_reason='Waiting', effort='S',
            phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Blocked Task 2', description='D', category='feature',
            status='blocked', blocked_reason='API issue', effort='S',
            phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        # Not blocked
        AdminTask.objects.create(
            title='Ready Task', description='D', category='feature',
            status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        snapshot = build_system_state_snapshot()

        self.assertEqual(snapshot.blocked_tasks_count, 2)

    def test_snapshot_only_counts_active_phase_tasks(self):
        """Snapshot only counts tasks from the active phase."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import build_system_state_snapshot

        active_phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Active Phase',
            objective='Current',
            status='in_progress'
        )
        future_phase = AdminProjectPhase.objects.create(
            phase_number=2,
            name='Future Phase',
            objective='Later',
            status='not_started'
        )

        # Tasks in active phase
        AdminTask.objects.create(
            title='Active Task 1', description='D', category='feature',
            status='ready', effort='S', phase=active_phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Active Task 2', description='D', category='feature',
            status='blocked', blocked_reason='Wait', effort='S',
            phase=active_phase, project=self.get_or_create_default_project(), created_by='human'
        )

        # Tasks in future phase (should not be counted)
        AdminTask.objects.create(
            title='Future Task', description='D', category='feature',
            status='backlog', effort='S', phase=future_phase, project=self.get_or_create_default_project(), created_by='human'
        )

        snapshot = build_system_state_snapshot()

        self.assertEqual(snapshot.open_tasks_count, 1)
        self.assertEqual(snapshot.blocked_tasks_count, 1)

    def test_snapshot_is_read_only(self):
        """Snapshot function does not mutate any data."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import build_system_state_snapshot

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )
        task = AdminTask.objects.create(
            title='Task', description='D', category='feature',
            status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        # Call snapshot multiple times
        snapshot1 = build_system_state_snapshot()
        snapshot2 = build_system_state_snapshot()

        # Data should be unchanged
        task.refresh_from_db()
        phase.refresh_from_db()
        self.assertEqual(task.status, 'ready')
        self.assertEqual(phase.status, 'in_progress')


class RequestScopedSnapshotTest(AdminTestMixin, TestCase):
    """Tests for request-scoped snapshot caching."""

    def test_get_snapshot_without_request_builds_fresh(self):
        """get_system_state_snapshot without request builds fresh snapshot."""
        from apps.admin_console.services import get_system_state_snapshot

        snapshot1 = get_system_state_snapshot()
        snapshot2 = get_system_state_snapshot()

        # Both should work but be independent snapshots
        self.assertIsNotNone(snapshot1)
        self.assertIsNotNone(snapshot2)

    def test_get_snapshot_with_request_caches(self):
        """get_system_state_snapshot with request caches on request object."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import get_system_state_snapshot

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        # Create a mock request object
        class MockRequest:
            pass

        request = MockRequest()

        # First call should build and cache
        snapshot1 = get_system_state_snapshot(request)
        self.assertIsNotNone(snapshot1)

        # Second call should return cached snapshot
        snapshot2 = get_system_state_snapshot(request)

        # Should be the same object
        self.assertIs(snapshot1, snapshot2)


# =============================================================================
# 17. SYSTEM STATE API TESTS
# =============================================================================

class SystemStateAPITest(AdminTestMixin, TestCase):
    """Tests for the system state API endpoint."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.regular_user = self.create_user()

    def test_system_state_requires_authentication(self):
        """System state API requires authentication."""
        response = self.client.get('/api/admin/project/system-state/')
        self.assertEqual(response.status_code, 403)

    def test_system_state_requires_staff(self):
        """System state API requires staff status."""
        self.login_user()
        response = self.client.get('/api/admin/project/system-state/')
        self.assertEqual(response.status_code, 403)

    def test_system_state_accessible_to_staff(self):
        """System state API is accessible to staff users."""
        self.login_admin()
        response = self.client.get('/api/admin/project/system-state/')
        self.assertEqual(response.status_code, 200)

    def test_system_state_returns_json(self):
        """System state API returns JSON."""
        self.login_admin()
        response = self.client.get('/api/admin/project/system-state/')
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_system_state_returns_expected_structure(self):
        """System state API returns expected JSON structure."""
        self.login_admin()
        response = self.client.get('/api/admin/project/system-state/')
        import json
        data = json.loads(response.content)

        self.assertIn('active_phase', data)
        self.assertIn('objective', data)
        self.assertIn('open_tasks', data)
        self.assertIn('blocked_tasks', data)
        self.assertIn('last_updated', data)

    def test_system_state_no_active_phase(self):
        """System state API returns null for active_phase when no phase active."""
        self.login_admin()
        response = self.client.get('/api/admin/project/system-state/')
        import json
        data = json.loads(response.content)

        self.assertIsNone(data['active_phase'])
        self.assertIsNone(data['objective'])
        self.assertEqual(data['open_tasks'], 0)
        self.assertEqual(data['blocked_tasks'], 0)

    def test_system_state_with_active_phase(self):
        """System state API returns correct phase info."""
        from apps.admin_console.models import AdminProjectPhase

        AdminProjectPhase.objects.create(
            phase_number=5,
            name='Blocker Task Creation',
            objective='Define blocker creation logic',
            status='in_progress'
        )

        self.login_admin()
        response = self.client.get('/api/admin/project/system-state/')
        import json
        data = json.loads(response.content)

        self.assertEqual(data['active_phase']['number'], 5)
        self.assertEqual(data['active_phase']['name'], 'Blocker Task Creation')
        self.assertEqual(data['active_phase']['status'], 'in_progress')
        self.assertEqual(data['objective'], 'Define blocker creation logic')

    def test_system_state_counts_tasks(self):
        """System state API returns correct task counts."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        # Open tasks
        AdminTask.objects.create(
            title='Ready Task', description='D', category='feature',
            status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='In Progress Task', description='D', category='feature',
            status='in_progress', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )
        AdminTask.objects.create(
            title='Backlog Task', description='D', category='feature',
            status='backlog', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        # Blocked task
        AdminTask.objects.create(
            title='Blocked Task', description='D', category='feature',
            status='blocked', blocked_reason='Waiting', effort='S',
            phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        # Done task (should not be counted in either)
        AdminTask.objects.create(
            title='Done Task', description='D', category='feature',
            status='done', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        self.login_admin()
        response = self.client.get('/api/admin/project/system-state/')
        import json
        data = json.loads(response.content)

        self.assertEqual(data['open_tasks'], 3)
        self.assertEqual(data['blocked_tasks'], 1)

    def test_system_state_last_updated_is_iso_timestamp(self):
        """System state API returns ISO formatted timestamp."""
        self.login_admin()
        response = self.client.get('/api/admin/project/system-state/')
        import json
        from datetime import datetime

        data = json.loads(response.content)

        # Should be parseable as ISO timestamp
        timestamp = datetime.fromisoformat(data['last_updated'].replace('Z', '+00:00'))
        self.assertIsNotNone(timestamp)

    def test_system_state_is_read_only(self):
        """System state API does not modify any data."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )
        task = AdminTask.objects.create(
            title='Task', description='D', category='feature',
            status='ready', effort='S', phase=phase, project=self.get_or_create_default_project(), created_by='human'
        )

        self.login_admin()

        # Call API multiple times
        self.client.get('/api/admin/project/system-state/')
        self.client.get('/api/admin/project/system-state/')

        # Data should be unchanged
        task.refresh_from_db()
        phase.refresh_from_db()
        self.assertEqual(task.status, 'ready')
        self.assertEqual(phase.status, 'in_progress')


# =============================================================================
# 18. PREFLIGHT GUARD TESTS (Phase 11.1)
# =============================================================================

class PreflightExecutionCheckServiceTest(AdminTestMixin, TestCase):
    """Tests for the preflight_execution_check service function."""

    def test_preflight_fails_when_no_phases_exist(self):
        """Preflight fails when no AdminProjectPhase records exist."""
        from apps.admin_console.services import preflight_execution_check

        result = preflight_execution_check()

        self.assertFalse(result.success)
        self.assertEqual(len(result.errors), 1)
        self.assertIn('No AdminProjectPhase records exist', result.errors[0])

    def test_preflight_fails_when_no_active_phase(self):
        """Preflight fails when no phase has status='in_progress'."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import preflight_execution_check

        # Create a phase but not active
        AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='not_started'
        )

        result = preflight_execution_check()

        self.assertFalse(result.success)
        self.assertEqual(len(result.errors), 1)
        self.assertIn('No active phase found', result.errors[0])

    def test_preflight_fails_when_multiple_active_phases(self):
        """Preflight fails when multiple phases are in_progress."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import preflight_execution_check

        # Create two active phases (normally shouldn't happen)
        AdminProjectPhase.objects.create(
            phase_number=1,
            name='Phase 1',
            objective='Test',
            status='in_progress'
        )
        # Bypass save() validation to create second active phase
        AdminProjectPhase.objects.create(
            phase_number=2,
            name='Phase 2',
            objective='Test',
            status='in_progress'
        )
        # Force both to be in_progress
        AdminProjectPhase.objects.update(status='in_progress')

        result = preflight_execution_check()

        self.assertFalse(result.success)
        self.assertEqual(len(result.errors), 1)
        self.assertIn('Multiple active phases found', result.errors[0])

    def test_preflight_fails_when_no_tasks_for_active_phase(self):
        """Preflight fails when active phase has no tasks."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import preflight_execution_check

        AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )

        result = preflight_execution_check()

        self.assertFalse(result.success)
        self.assertEqual(len(result.errors), 1)
        self.assertIn('No tasks found for active phase', result.errors[0])

    def test_preflight_succeeds_when_all_checks_pass(self):
        """Preflight succeeds when all checks pass."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import preflight_execution_check

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )
        AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='ready',
            effort='S',
            phase=phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        result = preflight_execution_check()

        self.assertTrue(result.success)
        self.assertEqual(len(result.errors), 0)

    def test_preflight_is_read_only(self):
        """Preflight check does not modify any data."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        from apps.admin_console.services import preflight_execution_check

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )
        task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='ready',
            effort='S',
            phase=phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        # Call preflight multiple times
        preflight_execution_check()
        preflight_execution_check()

        # Data should be unchanged
        task.refresh_from_db()
        phase.refresh_from_db()
        self.assertEqual(task.status, 'ready')
        self.assertEqual(phase.status, 'in_progress')


class PreflightCheckAPITest(AdminTestMixin, TestCase):
    """Tests for the preflight check API endpoint."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.regular_user = self.create_user()

    def test_preflight_requires_authentication(self):
        """Preflight API requires authentication."""
        response = self.client.get('/api/admin/project/preflight/')
        self.assertEqual(response.status_code, 403)

    def test_preflight_requires_staff(self):
        """Preflight API requires staff status."""
        self.login_user()
        response = self.client.get('/api/admin/project/preflight/')
        self.assertEqual(response.status_code, 403)

    def test_preflight_accessible_to_staff(self):
        """Preflight API is accessible to staff users."""
        self.login_admin()
        response = self.client.get('/api/admin/project/preflight/')
        self.assertEqual(response.status_code, 200)

    def test_preflight_returns_json(self):
        """Preflight API returns JSON."""
        self.login_admin()
        response = self.client.get('/api/admin/project/preflight/')
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_preflight_returns_expected_structure(self):
        """Preflight API returns expected JSON structure."""
        self.login_admin()
        response = self.client.get('/api/admin/project/preflight/')
        import json
        data = json.loads(response.content)

        self.assertIn('success', data)
        self.assertIn('errors', data)
        self.assertIsInstance(data['success'], bool)
        self.assertIsInstance(data['errors'], list)

    def test_preflight_fails_when_no_phases(self):
        """Preflight API returns failure when no phases exist."""
        self.login_admin()
        response = self.client.get('/api/admin/project/preflight/')
        import json
        data = json.loads(response.content)

        self.assertFalse(data['success'])
        self.assertEqual(len(data['errors']), 1)

    def test_preflight_succeeds_with_valid_data(self):
        """Preflight API returns success when all checks pass."""
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test',
            status='in_progress'
        )
        AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='ready',
            effort='S',
            phase=phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

        self.login_admin()
        response = self.client.get('/api/admin/project/preflight/')
        import json
        data = json.loads(response.content)

        self.assertTrue(data['success'])
        self.assertEqual(data['errors'], [])


# =============================================================================
# 19. PHASE SEEDING TESTS (Phase 11.1)
# =============================================================================

class PhaseSeedingServiceTest(AdminTestMixin, TestCase):
    """Tests for the seed_admin_project_phases service function."""

    def test_seeding_creates_11_phases_when_empty(self):
        """Seeding creates 11 phases when table is empty."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import seed_admin_project_phases

        result = seed_admin_project_phases()

        self.assertTrue(result['seeded'])
        self.assertEqual(result['phase_count'], 11)
        self.assertEqual(AdminProjectPhase.objects.count(), 11)

    def test_seeding_sets_phase_1_to_in_progress(self):
        """Seeding sets phase 1 to in_progress."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import seed_admin_project_phases

        seed_admin_project_phases()

        phase_1 = AdminProjectPhase.objects.get(phase_number=1)
        self.assertEqual(phase_1.status, 'in_progress')

    def test_seeding_sets_other_phases_to_not_started(self):
        """Seeding sets phases 2-11 to not_started."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import seed_admin_project_phases

        seed_admin_project_phases()

        for i in range(2, 12):
            phase = AdminProjectPhase.objects.get(phase_number=i)
            self.assertEqual(phase.status, 'not_started')

    def test_seeding_is_idempotent(self):
        """Seeding does nothing when phases already exist."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import seed_admin_project_phases

        # Create a phase first
        AdminProjectPhase.objects.create(
            phase_number=1,
            name='Existing Phase',
            objective='Test',
            status='in_progress'
        )

        result = seed_admin_project_phases()

        self.assertFalse(result['seeded'])
        self.assertEqual(result['phase_count'], 1)
        self.assertEqual(AdminProjectPhase.objects.count(), 1)

    def test_seeding_does_not_overwrite_existing_data(self):
        """Seeding never modifies existing phases."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import seed_admin_project_phases

        # Create a custom phase
        AdminProjectPhase.objects.create(
            phase_number=5,
            name='Custom Phase 5',
            objective='Custom objective',
            status='complete'
        )

        seed_admin_project_phases()

        phase_5 = AdminProjectPhase.objects.get(phase_number=5)
        self.assertEqual(phase_5.name, 'Custom Phase 5')
        self.assertEqual(phase_5.status, 'complete')


class SeedPhasesAPITest(AdminTestMixin, TestCase):
    """Tests for the seed phases API endpoint."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.regular_user = self.create_user()

    def test_seed_phases_requires_authentication(self):
        """Seed phases API requires authentication."""
        response = self.client.post('/api/admin/project/seed-phases/')
        self.assertEqual(response.status_code, 403)

    def test_seed_phases_requires_staff(self):
        """Seed phases API requires staff status."""
        self.login_user()
        response = self.client.post('/api/admin/project/seed-phases/')
        self.assertEqual(response.status_code, 403)

    def test_seed_phases_accessible_to_staff(self):
        """Seed phases API is accessible to staff users."""
        self.login_admin()
        response = self.client.post('/api/admin/project/seed-phases/')
        self.assertEqual(response.status_code, 200)

    def test_seed_phases_returns_json(self):
        """Seed phases API returns JSON."""
        self.login_admin()
        response = self.client.post('/api/admin/project/seed-phases/')
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_seed_phases_returns_expected_structure(self):
        """Seed phases API returns expected JSON structure."""
        self.login_admin()
        response = self.client.post('/api/admin/project/seed-phases/')
        import json
        data = json.loads(response.content)

        self.assertIn('seeded', data)
        self.assertIn('phase_count', data)
        self.assertIn('message', data)

    def test_seed_phases_creates_phases(self):
        """Seed phases API creates phases when table is empty."""
        from apps.admin_console.models import AdminProjectPhase

        self.login_admin()
        response = self.client.post('/api/admin/project/seed-phases/')
        import json
        data = json.loads(response.content)

        self.assertTrue(data['seeded'])
        self.assertEqual(data['phase_count'], 11)
        self.assertEqual(AdminProjectPhase.objects.count(), 11)

    def test_seed_phases_is_idempotent(self):
        """Seed phases API does nothing when phases exist."""
        from apps.admin_console.models import AdminProjectPhase

        AdminProjectPhase.objects.create(
            phase_number=1,
            name='Existing',
            objective='Test',
            status='in_progress'
        )

        self.login_admin()
        response = self.client.post('/api/admin/project/seed-phases/')
        import json
        data = json.loads(response.content)

        self.assertFalse(data['seeded'])
        self.assertEqual(data['phase_count'], 1)


class SeedAdminProjectPhasesCommandTest(AdminTestMixin, TestCase):
    """Tests for the seed_admin_project_phases management command."""

    def test_command_creates_phases_when_empty(self):
        """Command creates 11 phases when table is empty."""
        from django.core.management import call_command
        from apps.admin_console.models import AdminProjectPhase
        from io import StringIO

        out = StringIO()
        call_command('seed_admin_project_phases', stdout=out)

        self.assertEqual(AdminProjectPhase.objects.count(), 11)
        self.assertIn('PHASE SEEDING', out.getvalue())

    def test_command_skips_when_phases_exist(self):
        """Command does nothing when phases already exist."""
        from django.core.management import call_command
        from apps.admin_console.models import AdminProjectPhase
        from io import StringIO

        AdminProjectPhase.objects.create(
            phase_number=1,
            name='Existing',
            objective='Test',
            status='in_progress'
        )

        out = StringIO()
        call_command('seed_admin_project_phases', stdout=out)

        self.assertEqual(AdminProjectPhase.objects.count(), 1)
        self.assertIn('already exist', out.getvalue())


# =============================================================================
# PHASE 13 - INLINE EDITING API TESTS
# =============================================================================

class InlineStatusUpdateAPITest(AdminTestMixin, TestCase):
    """Tests for InlineStatusUpdateAPIView (Phase 13)."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.regular_user = self.create_user()

        # Create a phase and task
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        self.phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test objective',
            status='in_progress'
        )
        self.task = AdminTask.objects.create(
            title='Test Task',
            description='Test description',
            category='feature',
            priority=3,
            status='backlog',
            effort='M',
            phase=self.phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

    def test_inline_status_requires_admin(self):
        """Inline status update requires admin permission."""
        self.login_user()
        import json
        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)

    def test_inline_status_returns_404_for_missing_task(self):
        """Inline status update returns 404 for non-existent task."""
        self.login_admin()
        import json
        response = self.client.patch(
            '/admin-console/api/projects/tasks/99999/inline-status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_inline_status_backlog_to_ready(self):
        """Can change status from backlog to ready."""
        from apps.admin_console.models import AdminTask
        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertTrue(data['changed'])
        self.assertEqual(data['task']['status'], 'ready')

        # Verify database was updated
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, 'ready')

    def test_inline_status_ready_to_backlog(self):
        """Can change status from ready to backlog."""
        from apps.admin_console.models import AdminTask
        self.task.status = 'ready'
        self.task.save()

        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-status/',
            data=json.dumps({'status': 'backlog'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertTrue(data['changed'])
        self.assertEqual(data['task']['status'], 'backlog')

    def test_inline_status_allows_in_progress(self):
        """Inline status update allows in_progress."""
        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-status/',
            data=json.dumps({'status': 'in_progress'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['task']['status'], 'in_progress')

    def test_inline_status_blocked_requires_reason(self):
        """Inline status update to blocked requires reason."""
        self.login_admin()
        import json

        # Without reason should fail
        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-status/',
            data=json.dumps({'status': 'blocked'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

        # With reason should succeed
        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-status/',
            data=json.dumps({'status': 'blocked', 'reason': 'Waiting for dependency'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

    def test_inline_status_allows_done(self):
        """Inline status update allows done."""
        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-status/',
            data=json.dumps({'status': 'done'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['task']['status'], 'done')

    def test_inline_status_allows_change_from_in_progress(self):
        """Can use inline status edit when task is in_progress."""
        self.task.status = 'in_progress'
        self.task.save()

        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertEqual(data['task']['status'], 'ready')

    def test_inline_status_no_change_same_status(self):
        """No change when setting same status."""
        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-status/',
            data=json.dumps({'status': 'backlog'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertFalse(data['changed'])

    def test_inline_status_creates_activity_log(self):
        """Inline status change creates an activity log."""
        from apps.admin_console.models import AdminActivityLog
        self.login_admin()
        import json

        initial_count = AdminActivityLog.objects.filter(task=self.task).count()

        self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-status/',
            data=json.dumps({'status': 'ready'}),
            content_type='application/json'
        )

        final_count = AdminActivityLog.objects.filter(task=self.task).count()
        self.assertEqual(final_count, initial_count + 1)

        # Check log content
        log = AdminActivityLog.objects.filter(task=self.task).latest('created_at')
        self.assertIn('inline edit', log.action)
        self.assertEqual(log.created_by, 'human')


class InlinePriorityUpdateAPITest(AdminTestMixin, TestCase):
    """Tests for InlinePriorityUpdateAPIView (Phase 13)."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.regular_user = self.create_user()

        # Create a phase and task
        from apps.admin_console.models import AdminProject, AdminProjectPhase, AdminTask
        self.phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test objective',
            status='in_progress'
        )
        self.task = AdminTask.objects.create(
            title='Test Task',
            description='Test description',
            category='feature',
            priority=3,
            status='backlog',
            effort='M',
            phase=self.phase,
            project=self.get_or_create_default_project(),
            created_by='human'
        )

    def test_inline_priority_requires_admin(self):
        """Inline priority update requires admin permission."""
        self.login_user()
        import json
        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-priority/',
            data=json.dumps({'priority': 1}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)

    def test_inline_priority_returns_404_for_missing_task(self):
        """Inline priority update returns 404 for non-existent task."""
        self.login_admin()
        import json
        response = self.client.patch(
            '/admin-console/api/projects/tasks/99999/inline-priority/',
            data=json.dumps({'priority': 1}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)

    def test_inline_priority_update_success(self):
        """Can change priority successfully."""
        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-priority/',
            data=json.dumps({'priority': 1}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertTrue(data['changed'])
        self.assertEqual(data['task']['priority'], 1)

        # Verify database was updated
        self.task.refresh_from_db()
        self.assertEqual(self.task.priority, 1)

    def test_inline_priority_all_valid_values(self):
        """All values 1-5 are accepted."""
        self.login_admin()
        import json

        for priority in [1, 2, 3, 4, 5]:
            response = self.client.patch(
                f'/admin-console/api/projects/tasks/{self.task.pk}/inline-priority/',
                data=json.dumps({'priority': priority}),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 200)

            data = json.loads(response.content)
            self.assertTrue(data['success'])
            self.assertEqual(data['task']['priority'], priority)

    def test_inline_priority_rejects_zero(self):
        """Priority 0 is rejected."""
        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-priority/',
            data=json.dumps({'priority': 0}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

        data = json.loads(response.content)
        self.assertIn('must be between 1 and 5', data['error'])

    def test_inline_priority_rejects_six(self):
        """Priority 6 is rejected."""
        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-priority/',
            data=json.dumps({'priority': 6}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_inline_priority_rejects_negative(self):
        """Negative priority is rejected."""
        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-priority/',
            data=json.dumps({'priority': -1}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

    def test_inline_priority_rejects_string(self):
        """Non-integer priority is rejected."""
        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-priority/',
            data=json.dumps({'priority': 'high'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)

        data = json.loads(response.content)
        self.assertIn('must be an integer', data['error'])

    def test_inline_priority_no_change_same_value(self):
        """No change when setting same priority."""
        self.login_admin()
        import json

        response = self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-priority/',
            data=json.dumps({'priority': 3}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertTrue(data['success'])
        self.assertFalse(data['changed'])

    def test_inline_priority_creates_activity_log(self):
        """Inline priority change creates an activity log."""
        from apps.admin_console.models import AdminActivityLog
        self.login_admin()
        import json

        initial_count = AdminActivityLog.objects.filter(task=self.task).count()

        self.client.patch(
            f'/admin-console/api/projects/tasks/{self.task.pk}/inline-priority/',
            data=json.dumps({'priority': 1}),
            content_type='application/json'
        )

        final_count = AdminActivityLog.objects.filter(task=self.task).count()
        self.assertEqual(final_count, initial_count + 1)

        # Check log content
        log = AdminActivityLog.objects.filter(task=self.task).latest('created_at')
        self.assertIn('inline edit', log.action)
        self.assertEqual(log.created_by, 'human')

    def test_inline_priority_works_on_any_status(self):
        """Priority can be changed regardless of task status."""
        self.login_admin()
        import json

        # Test on various statuses
        for status in ['backlog', 'ready', 'in_progress', 'blocked', 'done']:
            self.task.status = status
            if status == 'blocked':
                self.task.blocked_reason = 'Test reason'
            self.task.save()

            response = self.client.patch(
                f'/admin-console/api/projects/tasks/{self.task.pk}/inline-priority/',
                data=json.dumps({'priority': 2}),
                content_type='application/json'
            )
            self.assertEqual(response.status_code, 200,
                           f"Priority change failed for status '{status}'")


# =============================================================================
# Claude Code Ready Tasks API Tests
# =============================================================================

class ReadyTasksAPITests(AdminTestMixin, TestCase):
    """
    Tests for the Claude Code Ready Tasks API endpoint.

    This endpoint allows Claude Code to fetch tasks with 'ready' status
    for the "What's Next?" protocol.
    """

    def setUp(self):
        """Set up test fixtures."""
        self.client = Client()
        self.admin = self.create_admin()

        # Create phase and project
        from apps.admin_console.models import AdminProjectPhase, AdminProject, AdminTask
        self.phase, _ = AdminProjectPhase.objects.get_or_create(
            phase_number=1,
            defaults={
                'name': 'Phase 1',
                'objective': 'Test phase',
                'status': 'in_progress'
            }
        )
        self.project = self.get_or_create_default_project()

        # Create tasks with different statuses
        AdminTask._skip_executable_validation = True
        self.ready_task = AdminTask.objects.create(
            title='Ready Task 1',
            description=self.make_executable_description('Ready Task 1'),
            category='feature',
            priority=1,
            status='ready',
            effort='M',
            phase=self.phase,
            project=self.project,
            created_by='claude'
        )
        self.backlog_task = AdminTask.objects.create(
            title='Backlog Task',
            description=self.make_executable_description('Backlog Task'),
            category='feature',
            priority=2,
            status='backlog',
            effort='S',
            phase=self.phase,
            project=self.project,
            created_by='human'
        )
        AdminTask._skip_executable_validation = False

    @override_settings(CLAUDE_API_KEY='test-api-key-12345')
    def test_requires_api_key(self):
        """Request without API key returns 401."""
        response = self.client.get('/admin-console/api/claude/ready-tasks/')
        self.assertEqual(response.status_code, 401)

    @override_settings(CLAUDE_API_KEY='test-api-key-12345')
    def test_invalid_api_key_returns_401(self):
        """Request with wrong API key returns 401."""
        response = self.client.get(
            '/admin-console/api/claude/ready-tasks/',
            HTTP_X_CLAUDE_API_KEY='wrong-key'
        )
        self.assertEqual(response.status_code, 401)

    @override_settings(CLAUDE_API_KEY='test-api-key-12345')
    def test_valid_api_key_returns_200(self):
        """Request with valid API key returns 200."""
        response = self.client.get(
            '/admin-console/api/claude/ready-tasks/',
            HTTP_X_CLAUDE_API_KEY='test-api-key-12345'
        )
        self.assertEqual(response.status_code, 200)

    @override_settings(CLAUDE_API_KEY='test-api-key-12345')
    def test_returns_only_ready_tasks(self):
        """Only tasks with status='ready' are returned."""
        import json
        response = self.client.get(
            '/admin-console/api/claude/ready-tasks/',
            HTTP_X_CLAUDE_API_KEY='test-api-key-12345'
        )
        data = json.loads(response.content)

        # Should only include ready tasks
        self.assertEqual(data['count'], 1)
        self.assertEqual(len(data['tasks']), 1)
        self.assertEqual(data['tasks'][0]['title'], 'Ready Task 1')

    @override_settings(CLAUDE_API_KEY='test-api-key-12345')
    def test_returns_executable_task_structure(self):
        """Response includes full executable task description."""
        import json
        response = self.client.get(
            '/admin-console/api/claude/ready-tasks/',
            HTTP_X_CLAUDE_API_KEY='test-api-key-12345'
        )
        data = json.loads(response.content)

        task = data['tasks'][0]
        self.assertIn('description', task)
        self.assertIn('objective', task['description'])
        self.assertIn('inputs', task['description'])
        self.assertIn('actions', task['description'])
        self.assertIn('output', task['description'])

    @override_settings(CLAUDE_API_KEY='test-api-key-12345')
    def test_respects_limit_parameter(self):
        """Limit parameter restricts number of returned tasks."""
        import json
        from apps.admin_console.models import AdminTask

        # Create more ready tasks
        AdminTask._skip_executable_validation = True
        for i in range(5):
            AdminTask.objects.create(
                title=f'Ready Task Extra {i}',
                description=self.make_executable_description(f'Extra {i}'),
                category='feature',
                priority=i + 2,
                status='ready',
                effort='S',
                phase=self.phase,
                project=self.project,
                created_by='claude'
            )
        AdminTask._skip_executable_validation = False

        response = self.client.get(
            '/admin-console/api/claude/ready-tasks/?limit=3',
            HTTP_X_CLAUDE_API_KEY='test-api-key-12345'
        )
        data = json.loads(response.content)

        self.assertEqual(len(data['tasks']), 3)

    @override_settings(CLAUDE_API_KEY='test-api-key-12345')
    def test_tasks_ordered_by_priority(self):
        """Tasks are returned ordered by priority (lowest first)."""
        import json
        from apps.admin_console.models import AdminTask

        # Create task with lower priority (higher number = lower priority)
        AdminTask._skip_executable_validation = True
        AdminTask.objects.create(
            title='Lower Priority Task',
            description=self.make_executable_description('Lower Priority'),
            category='feature',
            priority=10,
            status='ready',
            effort='M',
            phase=self.phase,
            project=self.project,
            created_by='human'
        )
        AdminTask._skip_executable_validation = False

        response = self.client.get(
            '/admin-console/api/claude/ready-tasks/',
            HTTP_X_CLAUDE_API_KEY='test-api-key-12345'
        )
        data = json.loads(response.content)

        # First task should be highest priority (lowest number)
        self.assertEqual(data['tasks'][0]['priority'], 1)

    @override_settings(CLAUDE_API_KEY='')
    def test_returns_500_if_api_key_not_configured(self):
        """Returns 500 if CLAUDE_API_KEY is not set on server."""
        response = self.client.get(
            '/admin-console/api/claude/ready-tasks/',
            HTTP_X_CLAUDE_API_KEY='any-key'
        )
        self.assertEqual(response.status_code, 500)


class AdminProjectCreateViewTest(AdminTestMixin, TestCase):
    """Tests for AdminProjectCreateView including popup mode."""

    def setUp(self):
        """Set up test data."""
        self.admin = self.create_admin()
        self.client.login(email='admin@example.com', password='adminpass123')

    def test_create_project_normal_mode(self):
        """Test creating a project in normal (non-popup) mode."""
        from apps.admin_console.models import AdminProject

        initial_count = AdminProject.objects.count()

        response = self.client.post(
            '/admin-console/projects/new/',
            {
                'name': 'Test New Project',
                'description': 'A test project description'
            }
        )

        # Should redirect to project list
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin-console/projects/', response.url)

        # Project should be created
        self.assertEqual(AdminProject.objects.count(), initial_count + 1)
        project = AdminProject.objects.get(name='Test New Project')
        self.assertEqual(project.description, 'A test project description')

    def test_create_project_popup_mode(self):
        """Test creating a project in popup mode."""
        from apps.admin_console.models import AdminProject

        initial_count = AdminProject.objects.count()

        response = self.client.post(
            '/admin-console/projects/new/?popup=1',
            {
                'name': 'Popup Test Project',
                'description': 'Created from popup'
            }
        )

        # Should render success page (not redirect)
        self.assertEqual(response.status_code, 200)

        # Project should be created
        self.assertEqual(AdminProject.objects.count(), initial_count + 1)
        project = AdminProject.objects.get(name='Popup Test Project')
        self.assertEqual(project.description, 'Created from popup')

        # Response should contain the created project info for JavaScript
        self.assertIn(b'projectCreated', response.content)
        self.assertIn(b'Popup Test Project', response.content)

    def test_create_project_popup_mode_get(self):
        """Test GET request to popup mode renders form."""
        response = self.client.get('/admin-console/projects/new/?popup=1')
        self.assertEqual(response.status_code, 200)
        # Popup mode should render standalone HTML (not extending base.html)
        self.assertIn(b'popup-container', response.content)
        # Should include the form
        self.assertIn(b'id_name', response.content)

    def test_create_project_from_intake_redirects_back(self):
        """Test creating a project from task intake redirects back to intake."""
        from apps.admin_console.models import AdminProject

        response = self.client.post(
            '/admin-console/projects/new/?from=intake',
            {
                'name': 'Project From Intake',
                'description': 'Created from task intake form'
            }
        )

        # Should redirect to task intake
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin-console/projects/intake/', response.url)

        # Project should be created
        self.assertTrue(AdminProject.objects.filter(name='Project From Intake').exists())

    def test_create_project_from_intake_cancel_links_to_intake(self):
        """Test that cancel button goes back to intake when from=intake."""
        response = self.client.get('/admin-console/projects/new/?from=intake')
        self.assertEqual(response.status_code, 200)
        # Cancel link should point to task intake
        self.assertIn(b'/admin-console/projects/intake/', response.content)


# =============================================================================
# DATA LOAD CONFIG TESTS
# =============================================================================

class DataLoadConfigModelTests(TestCase, AdminTestMixin):
    """Tests for DataLoadConfig model."""

    def test_create_data_load_config(self):
        """Test creating a DataLoadConfig entry."""
        from apps.admin_console.models import DataLoadConfig

        config = DataLoadConfig.objects.create(
            loader_name='test_loader',
            display_name='Test Loader',
            loader_type='fixture',
            description='A test data loader'
        )

        self.assertEqual(config.loader_name, 'test_loader')
        self.assertEqual(config.display_name, 'Test Loader')
        self.assertFalse(config.is_loaded)
        self.assertIsNone(config.loaded_at)

    def test_mark_loaded(self):
        """Test marking a loader as complete."""
        from apps.admin_console.models import DataLoadConfig

        config = DataLoadConfig.objects.create(
            loader_name='test_loader',
            display_name='Test Loader',
        )

        config.mark_loaded(loaded_by='test', records_created=5, records_updated=3)

        self.assertTrue(config.is_loaded)
        self.assertIsNotNone(config.loaded_at)
        self.assertEqual(config.loaded_by, 'test')
        self.assertEqual(config.records_created, 5)
        self.assertEqual(config.records_updated, 3)

    def test_reset(self):
        """Test resetting a loader."""
        from apps.admin_console.models import DataLoadConfig

        config = DataLoadConfig.objects.create(
            loader_name='test_loader',
            display_name='Test Loader',
        )
        config.mark_loaded(loaded_by='test')

        config.reset()

        self.assertFalse(config.is_loaded)
        self.assertIsNone(config.loaded_at)
        self.assertEqual(config.loaded_by, '')
        self.assertEqual(config.records_created, 0)

    def test_is_loader_complete(self):
        """Test checking if a loader is complete."""
        from apps.admin_console.models import DataLoadConfig

        # Not complete when doesn't exist
        self.assertFalse(DataLoadConfig.is_loader_complete('nonexistent'))

        # Not complete when exists but not loaded
        config = DataLoadConfig.objects.create(
            loader_name='test_loader',
            display_name='Test Loader',
        )
        self.assertFalse(DataLoadConfig.is_loader_complete('test_loader'))

        # Complete after mark_loaded
        config.mark_loaded()
        self.assertTrue(DataLoadConfig.is_loader_complete('test_loader'))

    def test_register_loader(self):
        """Test registering a new loader."""
        from apps.admin_console.models import DataLoadConfig

        # Create new
        config = DataLoadConfig.register_loader(
            loader_name='new_loader',
            display_name='New Loader',
            loader_type='command',
            description='New loader description'
        )

        self.assertEqual(config.loader_name, 'new_loader')
        self.assertEqual(config.loader_type, 'command')

        # Idempotent - returns existing
        config2 = DataLoadConfig.register_loader(
            loader_name='new_loader',
            display_name='Different Name',  # Should be ignored
        )

        self.assertEqual(config.pk, config2.pk)
        self.assertEqual(config2.display_name, 'New Loader')  # Original name kept

    def test_unique_loader_name(self):
        """Test that loader_name is unique."""
        from django.db import IntegrityError
        from apps.admin_console.models import DataLoadConfig

        DataLoadConfig.objects.create(
            loader_name='unique_test',
            display_name='Test 1',
        )

        with self.assertRaises(IntegrityError):
            DataLoadConfig.objects.create(
                loader_name='unique_test',
                display_name='Test 2',
            )

    def test_str_representation(self):
        """Test string representation."""
        from apps.admin_console.models import DataLoadConfig

        config = DataLoadConfig.objects.create(
            loader_name='test',
            display_name='Test Display',
        )

        self.assertIn('Test Display', str(config))
        self.assertIn('○', str(config))  # Not loaded indicator

        config.mark_loaded()
        self.assertIn('✓', str(config))  # Loaded indicator


class DataLoadConfigViewTests(TestCase, AdminTestMixin):
    """Tests for DataLoadConfig admin views."""

    def setUp(self):
        self.admin = self.create_admin()
        self.client.login(email='admin@example.com', password='adminpass123')

    def test_dataload_list_requires_staff(self):
        """Data loader list requires staff access."""
        self.client.logout()
        user = self.create_user()
        self.client.login(email='user@example.com', password='testpass123')

        response = self.client.get('/admin-console/dataload/')
        self.assertEqual(response.status_code, 302)

    def test_dataload_list_accessible_to_staff(self):
        """Data loader list is accessible to staff."""
        response = self.client.get('/admin-console/dataload/')
        self.assertEqual(response.status_code, 200)

    def test_dataload_list_shows_loaders(self):
        """Data loader list shows configured loaders."""
        from apps.admin_console.models import DataLoadConfig

        DataLoadConfig.objects.create(
            loader_name='test_loader',
            display_name='Test Loader Display',
            loader_type='fixture',
        )

        response = self.client.get('/admin-console/dataload/')
        self.assertContains(response, 'Test Loader Display')

    def test_dataload_reset_single(self):
        """Test resetting a single loader."""
        from apps.admin_console.models import DataLoadConfig

        config = DataLoadConfig.objects.create(
            loader_name='reset_test',
            display_name='Reset Test',
        )
        config.mark_loaded()
        self.assertTrue(config.is_loaded)

        response = self.client.post(f'/admin-console/dataload/{config.pk}/reset/')
        self.assertEqual(response.status_code, 302)

        config.refresh_from_db()
        self.assertFalse(config.is_loaded)

    def test_dataload_reset_all(self):
        """Test resetting all loaders."""
        from apps.admin_console.models import DataLoadConfig

        for i in range(3):
            config = DataLoadConfig.objects.create(
                loader_name=f'reset_all_{i}',
                display_name=f'Reset All Test {i}',
            )
            config.mark_loaded()

        # All should be loaded
        self.assertEqual(
            DataLoadConfig.objects.filter(is_loaded=True).count(),
            3
        )

        response = self.client.post('/admin-console/dataload/reset-all/')
        self.assertEqual(response.status_code, 302)

        # All should be reset
        self.assertEqual(
            DataLoadConfig.objects.filter(is_loaded=True).count(),
            0
        )