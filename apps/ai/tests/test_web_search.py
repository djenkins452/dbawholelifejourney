"""
Tests for Web Search & General Knowledge Service.

Project: Whole Life Journey
Path: apps/ai/tests/test_web_search.py
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase


class NeedsWebSearchTests(TestCase):
    """Tests for the needs_web_search pattern matcher."""

    def test_weather_queries_detected(self):
        from apps.ai.web_search_service import needs_web_search

        self.assertTrue(needs_web_search("What's the weather today?"))
        self.assertTrue(needs_web_search("weather in Nashville"))
        self.assertTrue(needs_web_search("What's the forecast for tomorrow?"))
        self.assertTrue(needs_web_search("What's the temperature outside?"))
        self.assertTrue(needs_web_search("Is it going to rain today?"))

    def test_general_knowledge_detected(self):
        from apps.ai.web_search_service import needs_web_search

        self.assertTrue(needs_web_search("What is intermittent fasting?"))
        self.assertTrue(needs_web_search("How does creatine work?"))
        self.assertTrue(needs_web_search("What are the benefits of cold showers?"))
        self.assertTrue(needs_web_search("How much protein should I eat per day?"))
        self.assertTrue(needs_web_search("What does the Bible say about forgiveness?"))
        self.assertTrue(needs_web_search("How to do a proper deadlift?"))
        self.assertTrue(needs_web_search("Calories in a banana"))
        self.assertTrue(needs_web_search("Recipe for chicken stir fry"))
        self.assertTrue(needs_web_search("Tips for better sleep"))
        self.assertTrue(needs_web_search("Difference between HIIT and LISS"))
        self.assertTrue(needs_web_search("Is it safe to fast for 48 hours?"))

    def test_personal_data_queries_excluded(self):
        from apps.ai.web_search_service import needs_web_search

        self.assertFalse(needs_web_search("What's my weight trend?"))
        self.assertFalse(needs_web_search("How much did I sleep last night?"))
        self.assertFalse(needs_web_search("Log 180 pounds"))
        self.assertFalse(needs_web_search("Track my water intake"))
        self.assertFalse(needs_web_search("Show me my goals"))
        self.assertFalse(needs_web_search("What did I journal about yesterday?"))
        self.assertFalse(needs_web_search("Undo my last entry"))

    def test_action_intents_excluded(self):
        from apps.ai.web_search_service import needs_web_search

        self.assertFalse(needs_web_search("Add a prayer request"))
        self.assertFalse(needs_web_search("Create a new goal"))
        self.assertFalse(needs_web_search("Start a fast"))
        self.assertFalse(needs_web_search("Record my blood pressure"))

    def test_casual_conversation_not_matched(self):
        from apps.ai.web_search_service import needs_web_search

        self.assertFalse(needs_web_search("Good morning!"))
        self.assertFalse(needs_web_search("Thank you"))
        self.assertFalse(needs_web_search("I had a great day"))


class GetQueryTypeTests(TestCase):
    """Tests for query type classification."""

    def test_weather_classification(self):
        from apps.ai.web_search_service import get_query_type

        self.assertEqual(get_query_type("What's the weather?"), "weather")
        self.assertEqual(get_query_type("forecast tomorrow"), "weather")

    def test_general_knowledge_classification(self):
        from apps.ai.web_search_service import get_query_type

        self.assertEqual(get_query_type("What is creatine?"), "general_knowledge")
        self.assertEqual(get_query_type("Benefits of meditation"), "general_knowledge")
        self.assertEqual(get_query_type("How to cook quinoa"), "general_knowledge")

    def test_unknown_classification(self):
        from apps.ai.web_search_service import get_query_type

        self.assertEqual(get_query_type("Hello there"), "unknown")
        self.assertEqual(get_query_type("Great job"), "unknown")


class SearchWebRoutingTests(TestCase):
    """Tests for search_web routing logic."""

    @patch("apps.ai.web_search_service.get_weather")
    def test_routes_weather_to_weather_api(self, mock_weather):
        from apps.ai.web_search_service import search_web

        mock_weather.return_value = "Sunny, 72°F"
        result = search_web("What's the weather in Nashville?")
        mock_weather.assert_called_once()
        self.assertEqual(result, "Sunny, 72°F")

    @patch("apps.ai.web_search_service.get_general_knowledge")
    def test_routes_knowledge_to_openai(self, mock_knowledge):
        from apps.ai.web_search_service import search_web

        mock_knowledge.return_value = "Creatine is a natural compound..."
        result = search_web("What is creatine?")
        mock_knowledge.assert_called_once_with("What is creatine?")
        self.assertEqual(result, "Creatine is a natural compound...")

    def test_returns_none_for_unknown(self):
        from apps.ai.web_search_service import search_web

        result = search_web("Hello there")
        self.assertIsNone(result)


class GeneralKnowledgeTests(TestCase):
    """Tests for the general knowledge handler."""

    @patch("openai.OpenAI")
    def test_calls_openai_with_correct_model(self, mock_openai_cls):
        from apps.ai.web_search_service import get_general_knowledge

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Creatine is a compound that helps produce ATP."
        mock_client.chat.completions.create.return_value = mock_response

        result = get_general_knowledge("What is creatine?")

        self.assertIsNotNone(result)
        self.assertIn("creatine", result.lower())

        # Verify the call used gpt-4o-mini and low temperature
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertEqual(call_kwargs["model"], "gpt-4o-mini")
        self.assertEqual(call_kwargs["temperature"], 0.3)

    @patch("openai.OpenAI")
    def test_returns_none_on_failure(self, mock_openai_cls):
        from apps.ai.web_search_service import get_general_knowledge

        mock_openai_cls.side_effect = Exception("API unavailable")

        result = get_general_knowledge("What is creatine?")
        self.assertIsNone(result)

    def test_system_prompt_exists(self):
        from apps.ai.web_search_service import GENERAL_KNOWLEDGE_SYSTEM_PROMPT

        self.assertIn("factual", GENERAL_KNOWLEDGE_SYSTEM_PROMPT.lower())
        self.assertIn("concise", GENERAL_KNOWLEDGE_SYSTEM_PROMPT.lower())


class WeatherExistingTests(TestCase):
    """Ensure existing weather functionality still works."""

    def test_extract_location(self):
        from apps.ai.web_search_service import _extract_location

        self.assertEqual(_extract_location("weather in Nashville"), "nashville")
        self.assertEqual(_extract_location("Nashville weather"), "nashville")
        self.assertIsNone(_extract_location("what is the weather"))

    def test_weather_code_to_text(self):
        from apps.ai.web_search_service import _weather_code_to_text

        self.assertEqual(_weather_code_to_text(0), "Clear sky")
        self.assertEqual(_weather_code_to_text(63), "Moderate rain")
        self.assertEqual(_weather_code_to_text(95), "Thunderstorm")
