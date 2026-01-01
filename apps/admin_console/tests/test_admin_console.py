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

from django.test import TestCase, Client
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
        from apps.admin_console.models import AdminProjectPhase, AdminTask

        # Create an active phase
        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Test Phase',
            objective='Test objective',
            status='in_progress'
        )

        # Create tasks
        task1 = AdminTask.objects.create(
            title='Task 1',
            description='Description 1',
            category='feature',
            priority=1,
            status='ready',
            effort='S',
            phase=phase,
            created_by='human'
        )
        task2 = AdminTask.objects.create(
            title='Task 2',
            description='Description 2',
            category='bug',
            priority=2,
            status='backlog',
            effort='M',
            phase=phase,
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
        from apps.admin_console.models import AdminProjectPhase, AdminTask

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
        from apps.admin_console.models import AdminProjectPhase, AdminTask

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
        from apps.admin_console.models import AdminProjectPhase, AdminTask

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
                created_by='human'
            )

        self.login_admin()
        response = self.client.get('/api/admin/project/next-tasks/?limit=3')
        import json
        data = json.loads(response.content)

        self.assertEqual(len(data), 3)

    def test_next_tasks_default_limit_is_5(self):
        """Next tasks API defaults to limit of 5."""
        from apps.admin_console.models import AdminProjectPhase, AdminTask

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
                created_by='human'
            )

        self.login_admin()
        response = self.client.get('/api/admin/project/next-tasks/')
        import json
        data = json.loads(response.content)

        self.assertEqual(len(data), 5)

    def test_next_tasks_orders_by_priority_then_created_at(self):
        """Next tasks API orders by priority, then created_at."""
        from apps.admin_console.models import AdminProjectPhase, AdminTask
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
        from apps.admin_console.models import AdminProjectPhase, AdminTask
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

    def test_transition_to_in_progress_requires_active_phase(self):
        """Task cannot move to in_progress if phase is not active."""
        from apps.admin_console.models import AdminTask, TaskStatusTransitionError

        task = AdminTask.objects.create(
            title='Test Task',
            description='Test',
            category='feature',
            status='ready',
            effort='S',
            phase=self.inactive_phase,
            created_by='human'
        )

        with self.assertRaises(TaskStatusTransitionError) as context:
            task.validate_status_transition('in_progress')
        self.assertIn('not active', str(context.exception))

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
        from apps.admin_console.models import AdminProjectPhase, AdminTask
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
            created_by='human'
        )
        self.ready_task = AdminTask.objects.create(
            title='Ready Task',
            description='Ready to start',
            category='feature',
            status='ready',
            effort='S',
            phase=self.active_phase,
            created_by='human'
        )
        self.in_progress_task = AdminTask.objects.create(
            title='In Progress Task',
            description='Being worked on',
            category='feature',
            status='in_progress',
            effort='S',
            phase=self.active_phase,
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
        from apps.admin_console.models import AdminProjectPhase, AdminTask
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
        from apps.admin_console.models import AdminProjectPhase, AdminTask

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
        from apps.admin_console.models import AdminProjectPhase, AdminTask

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
            created_by='human',
            blocking_task=blocker
        )

        # Verify reverse relationship
        self.assertEqual(blocker.blocks.count(), 2)
        self.assertIn(task1, blocker.blocks.all())
        self.assertIn(task2, blocker.blocks.all())