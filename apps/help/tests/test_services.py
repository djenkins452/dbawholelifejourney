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


class HelpChatServicePersonalDataQueryTest(TestCase):
    """Tests for personal data query integration in HelpChatService."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123"
        )

        # Create a test help article for fallback testing
        self.category = HelpCategory.objects.create(
            name="Features",
            slug="features"
        )
        self.weight_article = HelpArticle.objects.create(
            title="Weight Tracking Guide",
            slug="weight-tracking-guide",
            summary="Learn how to track your weight.",
            content="The weight tracking feature helps you monitor...",
            category=self.category,
            module="health",
            keywords="weight, tracking, log"
        )

    @patch('apps.help.services.process_assistant_message')
    def test_personal_query_detected_with_data(self, mock_process):
        """Test personal data query with data generates AI response."""
        # Mock process_assistant_message to return a personal query with data
        mock_process.return_value = {
            'system_prompt': 'Test system prompt with data context',
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_data': True,
        }

        service = HelpChatService(self.user)

        # Mock the AI response generation
        with patch.object(service, '_generate_ai_response') as mock_ai:
            mock_ai.return_value = "Your weight data shows an average of 175 lbs."

            response = service.generate_response("What was my average weight last week?")

            # Verify process_assistant_message was called
            mock_process.assert_called_once_with(
                user=self.user,
                message="What was my average weight last week?",
                base_system_prompt=mock_process.call_args[1]['base_system_prompt'],
            )

            # Verify AI response was generated
            mock_ai.assert_called_once()

            # Verify response contains AI-generated message
            self.assertEqual(response['message'], "Your weight data shows an average of 175 lbs.")
            self.assertEqual(response['articles'], [])

    @patch('apps.help.services.process_assistant_message')
    def test_personal_query_detected_no_data(self, mock_process):
        """Test personal data query without data returns helpful message."""
        # Mock process_assistant_message to return personal query but no data
        mock_process.return_value = {
            'system_prompt': '',
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_data': False,
        }

        service = HelpChatService(self.user)
        response = service.generate_response("What was my weight last week?")

        # Should return a message about no data
        self.assertIn("weight", response['message'].lower())
        self.assertIn("don't have any", response['message'])
        self.assertEqual(response['articles'], [])

    @patch('apps.help.services.process_assistant_message')
    def test_non_personal_query_falls_back_to_articles(self, mock_process):
        """Test non-personal queries fall back to help article search."""
        # Mock process_assistant_message to return not a personal query
        mock_process.return_value = {
            'system_prompt': '',
            'is_personal_query': False,
            'data_types': [],
            'has_data': False,
        }

        service = HelpChatService(self.user)
        response = service.generate_response("How do I log my weight?")

        # Should fall back to article search
        self.assertIn("Weight Tracking Guide", response['message'])
        self.assertTrue(len(response['articles']) > 0)

    @patch('apps.help.services.process_assistant_message')
    def test_personal_query_ai_failure_falls_back(self, mock_process):
        """Test AI generation failure falls back to help articles."""
        # Mock process_assistant_message to return personal query with data
        mock_process.return_value = {
            'system_prompt': 'Test system prompt',
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_data': True,
        }

        service = HelpChatService(self.user)

        # Mock AI response to fail (return None)
        with patch.object(service, '_generate_ai_response') as mock_ai:
            mock_ai.return_value = None

            response = service.generate_response("What was my weight?")

            # Should fall back to article search (will return no_results or found articles)
            # The key is that it doesn't crash and returns a valid response structure
            self.assertIn('message', response)
            self.assertIn('articles', response)

    @patch('apps.help.services.process_assistant_message')
    def test_process_assistant_message_exception_falls_back(self, mock_process):
        """Test exception in process_assistant_message falls back gracefully."""
        # Mock process_assistant_message to raise exception
        mock_process.side_effect = Exception("Database error")

        service = HelpChatService(self.user)
        response = service.generate_response("What was my weight?")

        # Should fall back to article search (not crash)
        self.assertIn('message', response)
        self.assertIn('articles', response)

    def test_coaching_style_instructions(self):
        """Test coaching style instructions are generated correctly."""
        service = HelpChatService(self.user)

        # Test default style
        instructions = service._get_coaching_style_instructions()
        self.assertIn("COACHING STYLE:", instructions)

    @patch('apps.help.services.HelpChatService._get_user_coaching_style')
    def test_direct_coach_style_instructions(self, mock_style):
        """Test direct coach style generates appropriate instructions."""
        mock_style.return_value = 'direct_coach'
        service = HelpChatService(self.user)

        instructions = service._get_coaching_style_instructions()
        self.assertIn("direct", instructions.lower())

    @patch('apps.ai.services.AIService')
    @patch('apps.help.services.process_assistant_message')
    def test_generate_ai_response_calls_ai_service(self, mock_process, mock_ai_class):
        """Test _generate_ai_response properly calls AIService."""
        # Setup mock process_assistant_message
        mock_process.return_value = {
            'system_prompt': 'System prompt with personal data',
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_data': True,
        }

        # Setup mock AIService
        mock_ai_instance = MagicMock()
        mock_ai_instance.is_available = True
        mock_ai_instance._call_api.return_value = "AI generated response"
        mock_ai_class.return_value = mock_ai_instance

        service = HelpChatService(self.user)
        response = service.generate_response("What was my weight?")

        # Verify AI service was called
        mock_ai_instance._call_api.assert_called_once()

        # Verify response is from AI
        self.assertEqual(response['message'], "AI generated response")

    @patch('apps.ai.services.AIService')
    @patch('apps.help.services.process_assistant_message')
    def test_ai_service_not_available_falls_back(self, mock_process, mock_ai_class):
        """Test AI service not available falls back to article search."""
        # Setup mock process_assistant_message
        mock_process.return_value = {
            'system_prompt': 'System prompt with personal data',
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_data': True,
        }

        # Setup mock AIService as not available
        mock_ai_instance = MagicMock()
        mock_ai_instance.is_available = False
        mock_ai_class.return_value = mock_ai_instance

        service = HelpChatService(self.user)
        response = service.generate_response("What was my weight?")

        # Should fall back to article search
        self.assertIn('message', response)
        self.assertIn('articles', response)
