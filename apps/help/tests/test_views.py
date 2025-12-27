"""
Tests for Help System Views
"""
import json
from django.test import TestCase, Client
from django.urls import reverse
from django.conf import settings
from django.contrib.auth import get_user_model

from apps.help.models import (
    HelpTopic, AdminHelpTopic,
    HelpCategory, HelpArticle, HelpConversation, HelpMessage
)

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


# =============================================================================
# WLJ ASSISTANT CHAT BOT VIEW TESTS
# =============================================================================


class HelpCenterViewTest(BaseHelpViewTest):
    """Tests for the Help Center view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self._accept_terms(self.user)
        self.category = HelpCategory.objects.create(
            name="Getting Started",
            slug="getting-started"
        )

    def test_help_center_requires_login(self):
        """Test help center requires authentication."""
        response = self.client.get(reverse('help:center'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url.lower())

    def test_help_center_authenticated(self):
        """Test help center loads for authenticated user."""
        self.client.login(email="test@example.com", password="testpass123")
        response = self.client.get(reverse('help:center'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Help Center")

    def test_help_center_shows_categories(self):
        """Test help center displays categories."""
        self.client.login(email="test@example.com", password="testpass123")
        response = self.client.get(reverse('help:center'))
        self.assertContains(response, "Getting Started")


class HelpArticleViewTest(BaseHelpViewTest):
    """Tests for the Help Article view."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self._accept_terms(self.user)
        self.category = HelpCategory.objects.create(
            name="Features",
            slug="features"
        )
        self.article = HelpArticle.objects.create(
            title="Using the Journal",
            slug="using-journal",
            summary="Learn to use the journal",
            content="Full article content here...",
            category=self.category
        )

    def test_article_view_requires_login(self):
        """Test article view requires authentication."""
        response = self.client.get(reverse('help:article', kwargs={'slug': 'using-journal'}))
        self.assertEqual(response.status_code, 302)

    def test_article_view_shows_content(self):
        """Test article view displays article content."""
        self.client.login(email="test@example.com", password="testpass123")
        response = self.client.get(reverse('help:article', kwargs={'slug': 'using-journal'}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Using the Journal")
        self.assertContains(response, "Full article content here")

    def test_article_view_404_for_inactive(self):
        """Test inactive articles return 404."""
        self.article.is_active = False
        self.article.save()

        self.client.login(email="test@example.com", password="testpass123")
        response = self.client.get(reverse('help:article', kwargs={'slug': 'using-journal'}))
        self.assertEqual(response.status_code, 404)


class ChatAPITest(BaseHelpViewTest):
    """Tests for Chat API endpoints."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self._accept_terms(self.user)
        self.article = HelpArticle.objects.create(
            title="Using the Journal",
            slug="using-journal",
            summary="Learn to use the journal",
            content="Full content...",
            keywords="journal, entries"
        )

    def test_chat_start_requires_login(self):
        """Test chat start requires authentication."""
        response = self.client.post(
            reverse('help:chat_start'),
            data=json.dumps({}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 302)

    def test_chat_start_creates_conversation(self):
        """Test chat start creates a new conversation."""
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.post(
            reverse('help:chat_start'),
            data=json.dumps({'module': 'dashboard', 'url': '/dashboard/'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('conversation_id', data)
        self.assertIn('message', data)
        self.assertIn('WLJ assistant', data['message'])

        # Verify conversation was created
        conversation = HelpConversation.objects.get(id=data['conversation_id'])
        self.assertEqual(conversation.user, self.user)
        self.assertEqual(conversation.context_module, 'dashboard')

    def test_chat_message_requires_conversation(self):
        """Test chat message requires a valid conversation."""
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.post(
            reverse('help:chat_message'),
            data=json.dumps({'message': 'Hello'}),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 400)

    def test_chat_message_sends_and_receives(self):
        """Test sending a message and receiving a response."""
        self.client.login(email="test@example.com", password="testpass123")

        # Start conversation
        start_response = self.client.post(
            reverse('help:chat_start'),
            data=json.dumps({}),
            content_type='application/json'
        )
        conversation_id = json.loads(start_response.content)['conversation_id']

        # Send message
        response = self.client.post(
            reverse('help:chat_message'),
            data=json.dumps({
                'conversation_id': conversation_id,
                'message': 'How do I use the journal?'
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('message', data)

        # Verify messages were saved
        conversation = HelpConversation.objects.get(id=conversation_id)
        # Welcome message + user message + assistant response = 3
        self.assertEqual(conversation.messages.count(), 3)

    def test_chat_end_deletes_conversation(self):
        """Test ending chat deletes the conversation."""
        self.client.login(email="test@example.com", password="testpass123")

        # Start conversation
        start_response = self.client.post(
            reverse('help:chat_start'),
            data=json.dumps({}),
            content_type='application/json'
        )
        conversation_id = json.loads(start_response.content)['conversation_id']

        # End conversation
        response = self.client.post(
            reverse('help:chat_end'),
            data=json.dumps({
                'conversation_id': conversation_id,
                'send_email': False
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data['success'])

        # Verify conversation was deleted
        self.assertFalse(HelpConversation.objects.filter(id=conversation_id).exists())

    def test_chat_search(self):
        """Test search endpoint."""
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.get(
            reverse('help:chat_search'),
            {'q': 'journal'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('results', data)
        self.assertTrue(len(data['results']) > 0)

    def test_chat_search_short_query(self):
        """Test search with short query returns empty."""
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.get(
            reverse('help:chat_search'),
            {'q': 'a'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['results'], [])

    def test_chat_suggestions(self):
        """Test suggestions endpoint."""
        self.client.login(email="test@example.com", password="testpass123")

        response = self.client.get(
            reverse('help:chat_suggestions'),
            {'module': 'journal'}
        )

        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('suggestions', data)
