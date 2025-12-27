"""
Tests for Help Chat Services.
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch, MagicMock

from apps.help.models import HelpCategory, HelpArticle
from apps.help.services import HelpChatService


User = get_user_model()


class HelpChatServiceTest(TestCase):
    """Tests for the HelpChatService."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )

        # Create test categories
        self.category = HelpCategory.objects.create(
            name="Features",
            slug="features"
        )

        # Create test articles
        self.journal_article = HelpArticle.objects.create(
            title="Using the Journal",
            slug="using-journal",
            summary="Learn how to create and manage journal entries.",
            content="The journal is for recording your thoughts...",
            category=self.category,
            module="journal",
            keywords="journal, entries, writing, mood"
        )

        self.health_article = HelpArticle.objects.create(
            title="Health Tracking",
            slug="health-tracking",
            summary="Track your weight, fitness, and other health metrics.",
            content="The health module helps you monitor...",
            category=self.category,
            module="health",
            keywords="health, weight, fitness, tracking"
        )

        self.general_article = HelpArticle.objects.create(
            title="Getting Started",
            slug="getting-started",
            summary="Welcome to Whole Life Journey!",
            content="This is your personal life operating system...",
            category=self.category,
            module="general",
            keywords="start, welcome, introduction, overview"
        )

    def test_service_initialization(self):
        """Test service initializes correctly."""
        service = HelpChatService(self.user)
        self.assertEqual(service.user, self.user)
        self.assertIsNotNone(service.tone)

    def test_get_welcome_message(self):
        """Test getting welcome message."""
        service = HelpChatService(self.user)
        welcome = service.get_welcome_message()
        self.assertIn("WLJ assistant", welcome)
        self.assertIn("help", welcome)

    def test_search_articles_by_title(self):
        """Test searching articles by title."""
        service = HelpChatService(self.user)
        results = service.search_articles("journal")

        self.assertTrue(len(results) > 0)
        titles = [a.title for a in results]
        self.assertIn("Using the Journal", titles)

    def test_search_articles_by_keywords(self):
        """Test searching articles by keywords."""
        service = HelpChatService(self.user)
        results = service.search_articles("fitness")

        self.assertTrue(len(results) > 0)
        titles = [a.title for a in results]
        self.assertIn("Health Tracking", titles)

    def test_search_articles_with_module_priority(self):
        """Test that module matching boosts article score."""
        service = HelpChatService(self.user)

        # Search without module priority
        results_no_module = service.search_articles("tracking")

        # Search with journal module priority
        results_with_module = service.search_articles("tracking", module="health")

        # Health article should be first when health module is prioritized
        if results_with_module:
            self.assertEqual(results_with_module[0].module, "health")

    def test_search_articles_empty_query(self):
        """Test search with empty query returns nothing."""
        service = HelpChatService(self.user)
        results = service.search_articles("")
        self.assertEqual(results, [])

    def test_search_articles_short_query(self):
        """Test search with too short query returns nothing."""
        service = HelpChatService(self.user)
        results = service.search_articles("a")
        self.assertEqual(results, [])

    def test_generate_response_with_match(self):
        """Test generating a response when articles match."""
        service = HelpChatService(self.user)
        response = service.generate_response("How do I use the journal?")

        self.assertIn("message", response)
        self.assertIn("articles", response)
        self.assertTrue(len(response["articles"]) > 0)
        self.assertIn("Using the Journal", response["message"])

    def test_generate_response_no_match(self):
        """Test generating a response when no articles match."""
        service = HelpChatService(self.user)
        response = service.generate_response("xyznonexistentfeature123")

        self.assertIn("message", response)
        self.assertEqual(len(response["articles"]), 0)

    def test_get_suggestions_for_module(self):
        """Test getting suggestions for a specific module."""
        service = HelpChatService(self.user)
        suggestions = service.get_suggestions_for_module("journal")

        # Should include journal-specific articles
        modules = [a.module for a in suggestions]
        self.assertIn("journal", modules)

    def test_get_closing_message(self):
        """Test getting closing message."""
        service = HelpChatService(self.user)
        closing = service.get_closing_message()
        self.assertIsInstance(closing, str)
        self.assertTrue(len(closing) > 0)

    def test_tone_templates_exist(self):
        """Test all coaching styles have tone templates."""
        expected_styles = [
            'supportive', 'direct_coach', 'gentle_guide',
            'wise_mentor', 'cheerful_friend', 'calm_companion',
            'accountability_partner'
        ]

        for style in expected_styles:
            self.assertIn(style, HelpChatService.TONE_TEMPLATES)
            template = HelpChatService.TONE_TEMPLATES[style]
            self.assertIn('greeting', template)
            self.assertIn('found_single', template)
            self.assertIn('not_found', template)


class HelpChatServiceWithPreferencesTest(TestCase):
    """Tests for HelpChatService with user preferences."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )

    @patch('apps.help.services.HelpChatService._get_user_coaching_style')
    def test_direct_coach_tone(self, mock_style):
        """Test direct coach style uses appropriate tone."""
        mock_style.return_value = 'direct_coach'
        service = HelpChatService(self.user)

        self.assertEqual(service.tone, HelpChatService.TONE_TEMPLATES['direct_coach'])
        self.assertIn("need to know", service.tone['found_single'])

    @patch('apps.help.services.HelpChatService._get_user_coaching_style')
    def test_cheerful_friend_tone(self, mock_style):
        """Test cheerful friend style uses appropriate tone."""
        mock_style.return_value = 'cheerful_friend'
        service = HelpChatService(self.user)

        self.assertEqual(service.tone, HelpChatService.TONE_TEMPLATES['cheerful_friend'])
        self.assertIn("Awesome", service.tone['found_single'])

    @patch('apps.help.services.HelpChatService._get_user_coaching_style')
    def test_unknown_style_uses_default(self, mock_style):
        """Test unknown coaching style falls back to default."""
        mock_style.return_value = 'nonexistent_style'
        service = HelpChatService(self.user)

        self.assertEqual(service.tone, HelpChatService.TONE_TEMPLATES['supportive'])
