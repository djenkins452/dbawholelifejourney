"""
Tests for Help System Views
"""
import json
from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.help.models import HelpTopic, AdminHelpTopic

User = get_user_model()


class BaseHelpViewTest(TestCase):
    """Base class for help view tests with authentication helpers."""

    def _accept_terms(self, user):
        """Helper to accept terms for a user."""
        try:
            from apps.users.models import TermsAcceptance
            TermsAcceptance.objects.create(
                user=user,
                terms_version=settings.WLJ_SETTINGS.get('TERMS_VERSION', '1.0')
            )
        except (ImportError, Exception):
            pass


class HelpTopicAPIViewTests(BaseHelpViewTest):
    """Tests for the user help API endpoint."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self._accept_terms(self.user)
        self.topic = HelpTopic.objects.create(
            context_id="TEST_CONTEXT",
            help_id="test-help",
            title="Test Help Topic",
            description="Test description",
            content="## Test\n\nTest content with **markdown**.",
            app_name="test",
            is_active=True
        )

    def test_requires_authentication(self):
        """Test that the endpoint requires login."""
        response = self.client.get(
            reverse('help:api_topic', kwargs={'context_id': 'TEST_CONTEXT'})
        )
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_get_existing_topic(self):
        """Test fetching an existing help topic."""
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.get(
            reverse('help:api_topic', kwargs={'context_id': 'TEST_CONTEXT'})
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['found'])
        self.assertEqual(data['context_id'], 'TEST_CONTEXT')
        self.assertEqual(data['title'], 'Test Help Topic')
        self.assertIn('<h2>', data['content'])  # Markdown converted to HTML

    def test_get_nonexistent_topic(self):
        """Test fetching a non-existent help topic."""
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.get(
            reverse('help:api_topic', kwargs={'context_id': 'NONEXISTENT'})
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertFalse(data['found'])
        self.assertEqual(data['context_id'], 'NONEXISTENT')
        self.assertIn('no help content is available', data['content'].lower())

    def test_related_topics_included(self):
        """Test that related topics are included in response."""
        self.client.login(email="test@example.com", password="testpass123")

        related = HelpTopic.objects.create(
            context_id="RELATED_CONTEXT",
            help_id="related-help",
            title="Related Topic",
            content="Related content",
            is_active=True
        )
        self.topic.related_topics.add(related)

        response = self.client.get(
            reverse('help:api_topic', kwargs={'context_id': 'TEST_CONTEXT'})
        )

        data = json.loads(response.content)
        self.assertEqual(len(data['related']), 1)
        self.assertEqual(data['related'][0]['title'], 'Related Topic')


class AdminHelpTopicAPIViewTests(BaseHelpViewTest):
    """Tests for the admin help API endpoint."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            email="user@example.com",
            password="testpass123"
        )
        self._accept_terms(self.user)
        self.admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpass123"
        )
        self._accept_terms(self.admin_user)
        self.topic = AdminHelpTopic.objects.create(
            context_id="ADMIN_TEST",
            help_id="admin-test",
            title="Admin Test Topic",
            description="Admin description",
            content="## Admin Help\n\nAdmin content.",
            category="Testing",
            is_active=True
        )

    def test_requires_authentication(self):
        """Test that the endpoint requires login."""
        response = self.client.get(
            reverse('help:api_admin_topic', kwargs={'context_id': 'ADMIN_TEST'})
        )
        self.assertEqual(response.status_code, 302)

    def test_requires_staff_permission(self):
        """Test that non-staff users get 403."""
        self.client.login(email="user@example.com", password="testpass123")

        response = self.client.get(
            reverse('help:api_admin_topic', kwargs={'context_id': 'ADMIN_TEST'})
        )

        self.assertEqual(response.status_code, 403)

    def test_staff_can_access(self):
        """Test that staff users can access admin help."""
        self.client.login(email="admin@example.com", password="adminpass123")

        response = self.client.get(
            reverse('help:api_admin_topic', kwargs={'context_id': 'ADMIN_TEST'})
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertTrue(data['found'])
        self.assertEqual(data['title'], 'Admin Test Topic')
        self.assertEqual(data['category'], 'Testing')

    def test_get_nonexistent_admin_topic(self):
        """Test fetching a non-existent admin help topic."""
        self.client.login(email="admin@example.com", password="adminpass123")

        response = self.client.get(
            reverse('help:api_admin_topic', kwargs={'context_id': 'NONEXISTENT'})
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertFalse(data['found'])


class HelpSearchAPIViewTests(BaseHelpViewTest):
    """Tests for the help search API endpoint."""

    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self._accept_terms(self.user)
        self.admin_user = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpass123"
        )
        self._accept_terms(self.admin_user)
        HelpTopic.objects.create(
            context_id="SEARCH_TEST_1",
            help_id="search-test-1",
            title="Finding Your Dashboard",
            content="Learn about the dashboard",
            is_active=True
        )
        HelpTopic.objects.create(
            context_id="SEARCH_TEST_2",
            help_id="search-test-2",
            title="Journal Basics",
            content="How to use the journal",
            is_active=True
        )

    def test_requires_authentication(self):
        """Test that search requires login."""
        response = self.client.get(
            reverse('help:api_search'),
            {'q': 'dashboard'}
        )
        self.assertEqual(response.status_code, 302)

    def test_search_user_help(self):
        """Test searching user help topics."""
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.get(
            reverse('help:api_search'),
            {'q': 'dashboard', 'type': 'user'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['title'], 'Finding Your Dashboard')

    def test_search_requires_minimum_length(self):
        """Test that search requires at least 2 characters."""
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.get(
            reverse('help:api_search'),
            {'q': 'a'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        self.assertEqual(len(data['results']), 0)
        self.assertIn('error', data)
