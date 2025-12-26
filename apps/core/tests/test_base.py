"""
Base Test Utilities

Shared test setup, helper methods, and mixins used across all test files.
Keeps tests DRY and consistent.

Location: apps/core/tests/test_base.py
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class BaseTestCase(TestCase):
    """
    Base test case with common setup and helper methods.
    
    Provides:
    - Test user creation
    - Login helpers
    - Common assertions
    """
    
    @classmethod
    def setUpTestData(cls):
        """
        Set up data for the whole test class.
        Called once for the class (not per test method).
        Use for data that won't be modified by tests.
        """
        pass
    
    def setUp(self):
        """
        Set up for each test method.
        Creates a fresh client and test user for each test.
        """
        self.client = Client()
        self.user = self.create_user()
    
    def create_user(self, email='testuser@example.com', password='testpass123', **kwargs):
        """
        Create a test user with optional customization.
        
        Usage:
            user = self.create_user()
            user = self.create_user(email='other@example.com')
            user = self.create_user(first_name='John', last_name='Doe')
        """
        defaults = {
            'email': email,
            'password': password,
            'first_name': 'Test',
            'last_name': 'User',
        }
        defaults.update(kwargs)
        password = defaults.pop('password')
        user = User.objects.create_user(password=password, **defaults)
        return user
    
    def create_other_user(self, email='otheruser@example.com', **kwargs):
        """Create a second user for isolation tests."""
        return self.create_user(email=email, **kwargs)
    
    def login(self, user=None, password='testpass123'):
        """
        Log in a user.
        
        Usage:
            self.login()  # Logs in self.user
            self.login(other_user)  # Logs in specific user
        """
        if user is None:
            user = self.user
        result = self.client.login(email=user.email, password=password)
        self.assertTrue(result, f"Failed to log in user {user.email}")
        return result
    
    def logout(self):
        """Log out the current user."""
        self.client.logout()
    
    def get(self, url_name, *args, **kwargs):
        """
        Make a GET request using URL name.
        
        Usage:
            response = self.get('dashboard:home')
            response = self.get('life:event_detail', pk=1)
        """
        url = reverse(url_name, args=args, kwargs=kwargs) if isinstance(url_name, str) and ':' in url_name else url_name
        return self.client.get(url)
    
    def post(self, url_name, data=None, *args, **kwargs):
        """
        Make a POST request using URL name.
        
        Usage:
            response = self.post('life:event_create', {'title': 'Test'})
        """
        url = reverse(url_name, args=args, kwargs=kwargs) if isinstance(url_name, str) and ':' in url_name else url_name
        return self.client.post(url, data or {})
    
    def assertLoginRequired(self, url_name, *args, **kwargs):
        """
        Assert that a URL requires login.
        
        Usage:
            self.assertLoginRequired('dashboard:home')
            self.assertLoginRequired('life:event_detail', pk=1)
        """
        self.logout()
        url = reverse(url_name, args=args, kwargs=kwargs)
        response = self.client.get(url)
        # Should redirect to login page
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response.url)
    
    def assertPageLoads(self, url_name, *args, **kwargs):
        """
        Assert that a page loads successfully (200 OK).
        
        Usage:
            self.login()
            self.assertPageLoads('dashboard:home')
        """
        url = reverse(url_name, args=args, kwargs=kwargs)
        response = self.client.get(url)
        self.assertEqual(
            response.status_code, 
            200, 
            f"Expected 200 for {url}, got {response.status_code}"
        )
        return response
    
    def assertPageContains(self, url_name, text, *args, **kwargs):
        """
        Assert that a page contains specific text.
        
        Usage:
            self.login()
            self.assertPageContains('dashboard:home', 'Welcome')
        """
        response = self.assertPageLoads(url_name, *args, **kwargs)
        self.assertContains(response, text)
        return response


class AuthenticatedTestCase(BaseTestCase):
    """
    Test case that automatically logs in the user.
    
    Use this for tests where every test method needs an authenticated user.
    """
    
    def setUp(self):
        super().setUp()
        self.login()


class TwoUserTestCase(BaseTestCase):
    """
    Test case with two users for testing data isolation.
    
    Use this to ensure User A cannot see User B's data.
    """
    
    def setUp(self):
        super().setUp()
        self.user_a = self.user  # From BaseTestCase
        self.user_b = self.create_other_user()
    
    def login_as_a(self):
        """Log in as User A."""
        self.login(self.user_a)
    
    def login_as_b(self):
        """Log in as User B."""
        self.login(self.user_b)
