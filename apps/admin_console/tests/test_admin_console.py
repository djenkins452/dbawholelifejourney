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