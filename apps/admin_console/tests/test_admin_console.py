# ==============================================================================
# File: apps/admin_console/tests/test_admin_console.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Comprehensive tests for admin console functionality
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-01
# Last Updated: 2026-01-01
# ==============================================================================
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
7. Project phase awareness (Phase 2)

Location: apps/admin_console/tests/test_admin_console.py
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
# 10. PROJECT PHASE AWARENESS TESTS (Phase 2)
# =============================================================================

class PhaseStatusRuleTest(AdminTestMixin, TestCase):
    """Tests for phase status rules - only one in_progress at a time."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()

    def test_setting_phase_in_progress_updates_others(self):
        """When a phase is set to in_progress, other non-complete phases become not_started."""
        from apps.admin_console.models import AdminProjectPhase

        # Create multiple phases
        phase1 = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Phase 1',
            objective='Objective 1',
            status='in_progress'
        )
        phase2 = AdminProjectPhase.objects.create(
            phase_number=2,
            name='Phase 2',
            objective='Objective 2',
            status='not_started'
        )
        phase3 = AdminProjectPhase.objects.create(
            phase_number=3,
            name='Phase 3',
            objective='Objective 3',
            status='not_started'
        )

        # Set phase2 to in_progress
        phase2.status = 'in_progress'
        phase2.save()

        # Reload phase1
        phase1.refresh_from_db()

        # Phase1 should now be not_started (since it wasn't complete)
        self.assertEqual(phase1.status, 'not_started')
        self.assertEqual(phase2.status, 'in_progress')

    def test_complete_phases_not_affected(self):
        """Complete phases are not affected when another is set to in_progress."""
        from apps.admin_console.models import AdminProjectPhase

        phase1 = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Phase 1',
            objective='Objective 1',
            status='complete'
        )
        phase2 = AdminProjectPhase.objects.create(
            phase_number=2,
            name='Phase 2',
            objective='Objective 2',
            status='not_started'
        )

        # Set phase2 to in_progress
        phase2.status = 'in_progress'
        phase2.save()

        # Phase1 should still be complete
        phase1.refresh_from_db()
        self.assertEqual(phase1.status, 'complete')


class PhaseValidationTest(AdminTestMixin, TestCase):
    """Tests for phase status validation."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()

    def test_cannot_change_complete_to_in_progress(self):
        """Complete phases cannot be changed to in_progress without override."""
        from django.core.exceptions import ValidationError
        from apps.admin_console.models import AdminProjectPhase

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Phase 1',
            objective='Objective 1',
            status='complete'
        )

        phase.status = 'in_progress'

        with self.assertRaises(ValidationError):
            phase.save()

    def test_admin_override_allows_complete_to_in_progress(self):
        """Admin override allows changing complete to in_progress."""
        from apps.admin_console.models import AdminProjectPhase

        phase = AdminProjectPhase.objects.create(
            phase_number=1,
            name='Phase 1',
            objective='Objective 1',
            status='complete'
        )

        # Use the override method
        phase.set_in_progress_with_override()

        phase.refresh_from_db()
        self.assertEqual(phase.status, 'in_progress')


class GetActivePhaseTest(AdminTestMixin, TestCase):
    """Tests for get_active_phase() helper function."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.login_admin()

    def test_get_active_phase_returns_in_progress(self):
        """get_active_phase returns the in_progress phase."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import get_active_phase

        AdminProjectPhase.objects.create(
            phase_number=1,
            name='Phase 1',
            objective='Objective 1',
            status='complete'
        )
        phase2 = AdminProjectPhase.objects.create(
            phase_number=2,
            name='Phase 2',
            objective='Objective 2',
            status='in_progress'
        )

        active = get_active_phase()
        self.assertEqual(active.pk, phase2.pk)

    def test_get_active_phase_activates_lowest_not_complete(self):
        """get_active_phase activates lowest phase_number that is not complete."""
        from apps.admin_console.models import AdminProjectPhase
        from apps.admin_console.services import get_active_phase

        AdminProjectPhase.objects.create(
            phase_number=1,
            name='Phase 1',
            objective='Objective 1',
            status='complete'
        )
        phase2 = AdminProjectPhase.objects.create(
            phase_number=2,
            name='Phase 2',
            objective='Objective 2',
            status='not_started'
        )
        AdminProjectPhase.objects.create(
            phase_number=3,
            name='Phase 3',
            objective='Objective 3',
            status='not_started'
        )

        active = get_active_phase()
        self.assertEqual(active.pk, phase2.pk)
        self.assertEqual(active.status, 'in_progress')

    def test_get_active_phase_returns_none_when_no_phases(self):
        """get_active_phase returns None when no phases exist."""
        from apps.admin_console.services import get_active_phase

        active = get_active_phase()
        self.assertIsNone(active)


class ActivePhaseAPITest(AdminTestMixin, TestCase):
    """Tests for active phase API endpoint."""

    def setUp(self):
        self.client = Client()
        self.admin = self.create_admin()
        self.regular_user = self.create_user()
        self.login_admin()

    def test_api_requires_staff(self):
        """API endpoint requires staff status."""
        self.login_user()
        response = self.client.get(reverse('admin_console:api_active_phase'))
        self.assertEqual(response.status_code, 302)

    def test_api_returns_active_phase(self):
        """API returns the active phase data."""
        from apps.admin_console.models import AdminProjectPhase
        import json

        AdminProjectPhase.objects.create(
            phase_number=1,
            name='Core Infrastructure',
            objective='Build the foundation',
            status='in_progress'
        )

        response = self.client.get(reverse('admin_console:api_active_phase'))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['phase_number'], 1)
        self.assertEqual(data['name'], 'Core Infrastructure')
        self.assertEqual(data['status'], 'in_progress')
        self.assertEqual(data['objective'], 'Build the foundation')

    def test_api_returns_404_when_no_phases(self):
        """API returns 404 when no phases exist."""
        response = self.client.get(reverse('admin_console:api_active_phase'))
        self.assertEqual(response.status_code, 404)

    def test_api_activates_next_phase_if_none_active(self):
        """API activates the next phase if none is in_progress."""
        from apps.admin_console.models import AdminProjectPhase
        import json

        AdminProjectPhase.objects.create(
            phase_number=1,
            name='Phase 1',
            objective='Objective 1',
            status='complete'
        )
        AdminProjectPhase.objects.create(
            phase_number=2,
            name='Phase 2',
            objective='Objective 2',
            status='not_started'
        )

        response = self.client.get(reverse('admin_console:api_active_phase'))
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content)
        self.assertEqual(data['phase_number'], 2)
        self.assertEqual(data['status'], 'in_progress')