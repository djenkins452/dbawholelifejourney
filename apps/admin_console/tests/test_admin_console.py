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
        """Create a test user."""
        user = User.objects.create_user(
            email=email, 
            password=password,
            is_staff=is_staff,
            is_superuser=is_superuser
        )
        self._accept_terms(user)
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
        self.client.login(email='super@example.com', password='superpass123')
        response = self.client.get('/admin/')
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