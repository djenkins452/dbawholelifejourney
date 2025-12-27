"""
Tests for Help System Models
"""
from django.test import TestCase
from django.core.cache import cache
from django.contrib.auth import get_user_model

from apps.help.models import (
    HelpTopic, AdminHelpTopic,
    HelpCategory, HelpArticle, HelpConversation, HelpMessage
)

User = get_user_model()


class HelpTopicModelTests(TestCase):
    """Tests for HelpTopic model."""

    def setUp(self):
        """Set up test data."""
        cache.clear()
        self.topic = HelpTopic.objects.create(
            context_id="TEST_CONTEXT",
            help_id="test-help",
            title="Test Help Topic",
            description="A test help topic",
            content="## Test Content\n\nThis is test content.",
            app_name="test",
            order=1,
            is_active=True
        )

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    def test_help_topic_creation(self):
        """Test that a HelpTopic can be created."""
        self.assertEqual(self.topic.context_id, "TEST_CONTEXT")
        self.assertEqual(self.topic.title, "Test Help Topic")
        self.assertTrue(self.topic.is_active)

    def test_help_topic_str(self):
        """Test HelpTopic string representation."""
        self.assertEqual(str(self.topic), "TEST_CONTEXT: Test Help Topic")

    def test_get_by_context_found(self):
        """Test retrieving a help topic by context ID."""
        topic = HelpTopic.get_by_context("TEST_CONTEXT")
        self.assertIsNotNone(topic)
        self.assertEqual(topic.title, "Test Help Topic")

    def test_get_by_context_not_found(self):
        """Test retrieving a non-existent help topic."""
        topic = HelpTopic.get_by_context("NONEXISTENT_CONTEXT")
        self.assertIsNone(topic)

    def test_get_by_context_inactive(self):
        """Test that inactive topics are not returned."""
        self.topic.is_active = False
        self.topic.save()
        cache.clear()

        topic = HelpTopic.get_by_context("TEST_CONTEXT")
        self.assertIsNone(topic)

    def test_get_all_active(self):
        """Test retrieving all active topics."""
        HelpTopic.objects.create(
            context_id="ANOTHER_CONTEXT",
            help_id="another-help",
            title="Another Topic",
            content="Content",
            is_active=True
        )
        HelpTopic.objects.create(
            context_id="INACTIVE_CONTEXT",
            help_id="inactive-help",
            title="Inactive Topic",
            content="Content",
            is_active=False
        )

        topics = HelpTopic.get_all_active()
        self.assertEqual(len(topics), 2)

    def test_unique_context_id(self):
        """Test that context_id must be unique."""
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            HelpTopic.objects.create(
                context_id="TEST_CONTEXT",  # Same as setUp
                help_id="duplicate-help",
                title="Duplicate",
                content="Content"
            )

    def test_caching(self):
        """Test that topics are cached."""
        # First call - should hit database
        topic1 = HelpTopic.get_by_context("TEST_CONTEXT")
        self.assertIsNotNone(topic1)

        # Verify it's cached
        cached = cache.get("help_topic_TEST_CONTEXT")
        self.assertIsNotNone(cached)

        # Second call - should use cache
        topic2 = HelpTopic.get_by_context("TEST_CONTEXT")
        self.assertEqual(topic1.pk, topic2.pk)


class AdminHelpTopicModelTests(TestCase):
    """Tests for AdminHelpTopic model."""

    def setUp(self):
        """Set up test data."""
        cache.clear()
        self.topic = AdminHelpTopic.objects.create(
            context_id="ADMIN_TEST",
            help_id="admin-test",
            title="Admin Test Topic",
            description="Admin test description",
            content="## Admin Content\n\nAdmin help content.",
            category="Testing",
            order=1,
            is_active=True
        )

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    def test_admin_help_topic_creation(self):
        """Test that an AdminHelpTopic can be created."""
        self.assertEqual(self.topic.context_id, "ADMIN_TEST")
        self.assertEqual(self.topic.category, "Testing")

    def test_admin_help_topic_str(self):
        """Test AdminHelpTopic string representation."""
        self.assertEqual(str(self.topic), "ADMIN_TEST: Admin Test Topic")

    def test_get_by_context_found(self):
        """Test retrieving an admin help topic by context ID."""
        topic = AdminHelpTopic.get_by_context("ADMIN_TEST")
        self.assertIsNotNone(topic)
        self.assertEqual(topic.title, "Admin Test Topic")

    def test_get_by_context_not_found(self):
        """Test retrieving a non-existent admin help topic."""
        topic = AdminHelpTopic.get_by_context("NONEXISTENT")
        self.assertIsNone(topic)

    def test_get_all_active_grouped_by_category(self):
        """Test retrieving all active admin topics."""
        AdminHelpTopic.objects.create(
            context_id="ADMIN_ANOTHER",
            help_id="admin-another",
            title="Another Admin Topic",
            content="Content",
            category="Another Category",
            is_active=True
        )

        topics = AdminHelpTopic.get_all_active()
        self.assertEqual(len(topics), 2)


# =============================================================================
# WLJ ASSISTANT CHAT BOT MODEL TESTS
# =============================================================================


class HelpCategoryModelTest(TestCase):
    """Tests for the HelpCategory model."""

    def test_create_category(self):
        """Test creating a help category."""
        category = HelpCategory.objects.create(
            name="Getting Started",
            slug="getting-started",
            description="Learn the basics",
            icon="R"  # Use simple character for test
        )
        self.assertEqual(str(category), "Getting Started")
        self.assertEqual(category.slug, "getting-started")
        self.assertTrue(category.is_active)

    def test_category_ordering(self):
        """Test categories are ordered by sort_order."""
        cat1 = HelpCategory.objects.create(name="Second", slug="second", sort_order=2)
        cat2 = HelpCategory.objects.create(name="First", slug="first", sort_order=1)
        cat3 = HelpCategory.objects.create(name="Third", slug="third", sort_order=3)

        categories = list(HelpCategory.objects.all())
        self.assertEqual(categories[0], cat2)
        self.assertEqual(categories[1], cat1)
        self.assertEqual(categories[2], cat3)

    def test_get_active_categories(self):
        """Test getting only active categories."""
        cache.clear()
        active = HelpCategory.objects.create(name="Active", slug="active", is_active=True)
        inactive = HelpCategory.objects.create(name="Inactive", slug="inactive", is_active=False)

        active_categories = HelpCategory.get_active_categories()
        self.assertIn(active, active_categories)
        self.assertNotIn(inactive, active_categories)


class HelpArticleModelTest(TestCase):
    """Tests for the HelpArticle model."""

    def setUp(self):
        self.category = HelpCategory.objects.create(
            name="Features",
            slug="features"
        )

    def test_create_article(self):
        """Test creating a help article."""
        article = HelpArticle.objects.create(
            title="Using the Journal",
            slug="using-journal",
            summary="Learn to use the journal",
            content="Full content here...",
            category=self.category,
            module="journal",
            keywords="journal, entries, writing"
        )
        self.assertEqual(str(article), "Using the Journal")
        self.assertEqual(article.module, "journal")
        self.assertTrue(article.is_active)

    def test_keywords_list(self):
        """Test parsing keywords into a list."""
        article = HelpArticle.objects.create(
            title="Test",
            slug="test",
            summary="Test",
            content="Content",
            keywords="journal, entries, WRITING, mood "
        )
        keywords = article.keywords_list
        self.assertEqual(keywords, ["journal", "entries", "writing", "mood"])

    def test_keywords_list_empty(self):
        """Test keywords_list with no keywords."""
        article = HelpArticle.objects.create(
            title="Test",
            slug="test",
            summary="Test",
            content="Content",
            keywords=""
        )
        self.assertEqual(article.keywords_list, [])

    def test_get_by_module(self):
        """Test getting articles by module."""
        cache.clear()
        journal_article = HelpArticle.objects.create(
            title="Journal Help",
            slug="journal-help",
            summary="Help for journal",
            content="Content",
            module="journal"
        )
        health_article = HelpArticle.objects.create(
            title="Health Help",
            slug="health-help",
            summary="Help for health",
            content="Content",
            module="health"
        )

        journal_articles = HelpArticle.get_by_module("journal")
        self.assertIn(journal_article, journal_articles)
        self.assertNotIn(health_article, journal_articles)


class HelpConversationModelTest(TestCase):
    """Tests for the HelpConversation model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )

    def test_create_conversation(self):
        """Test creating a conversation."""
        conversation = HelpConversation.objects.create(
            user=self.user,
            context_module="dashboard",
            context_url="/dashboard/"
        )
        self.assertEqual(conversation.user, self.user)
        self.assertEqual(conversation.context_module, "dashboard")
        self.assertEqual(conversation.message_count, 0)

    def test_message_count(self):
        """Test message count property."""
        conversation = HelpConversation.objects.create(user=self.user)

        # Add messages
        HelpMessage.objects.create(
            conversation=conversation,
            content="Hello",
            is_user=True
        )
        HelpMessage.objects.create(
            conversation=conversation,
            content="Hi there!",
            is_user=False
        )

        self.assertEqual(conversation.message_count, 2)

    def test_get_messages_for_email(self):
        """Test formatting messages for email."""
        conversation = HelpConversation.objects.create(user=self.user)

        HelpMessage.objects.create(
            conversation=conversation,
            content="How do I use the journal?",
            is_user=True
        )
        HelpMessage.objects.create(
            conversation=conversation,
            content="Here's how to use the journal...",
            is_user=False
        )

        email_text = conversation.get_messages_for_email()
        self.assertIn("You:", email_text)
        self.assertIn("WLJ Assistant:", email_text)
        self.assertIn("How do I use the journal?", email_text)


class HelpMessageModelTest(TestCase):
    """Tests for the HelpMessage model."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )
        self.conversation = HelpConversation.objects.create(user=self.user)

    def test_create_user_message(self):
        """Test creating a user message."""
        message = HelpMessage.objects.create(
            conversation=self.conversation,
            content="How do I track my weight?",
            is_user=True
        )
        self.assertTrue(message.is_user)
        self.assertIn("User:", str(message))

    def test_create_assistant_message(self):
        """Test creating an assistant message."""
        message = HelpMessage.objects.create(
            conversation=self.conversation,
            content="You can track your weight in the Health module.",
            is_user=False
        )
        self.assertFalse(message.is_user)
        self.assertIn("Assistant:", str(message))

    def test_message_ordering(self):
        """Test messages are ordered by creation time."""
        msg1 = HelpMessage.objects.create(
            conversation=self.conversation,
            content="First",
            is_user=True
        )
        msg2 = HelpMessage.objects.create(
            conversation=self.conversation,
            content="Second",
            is_user=False
        )

        messages = list(self.conversation.messages.all())
        self.assertEqual(messages[0], msg1)
        self.assertEqual(messages[1], msg2)
