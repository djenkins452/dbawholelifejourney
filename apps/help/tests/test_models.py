"""
Tests for Help System Models
"""
from django.test import TestCase
from django.core.cache import cache

from apps.help.models import HelpTopic, AdminHelpTopic


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
