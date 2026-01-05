"""
Unit tests for the Intent Detector module.

Tests cover various query patterns to ensure accurate classification
of personal data queries.
"""

import unittest

from assistant.intent_detector import (
    COMPOUND_CONNECTORS,
    DATE_KEYWORDS,
    META_QUESTION_KEYWORDS,
    PERSONAL_DATA_KEYWORDS,
    detect_personal_data_intent,
)


class TestPersonalDataKeywords(unittest.TestCase):
    """Tests for PERSONAL_DATA_KEYWORDS dictionary."""

    def test_keywords_dictionary_has_expected_keys(self):
        """Ensure all expected data types are present."""
        expected_keys = [
            'weight', 'journal', 'medication', 'food', 'mood',
            'sleep', 'exercise', 'glucose', 'blood_pressure', 'faith', 'goals',
        ]
        for key in expected_keys:
            self.assertIn(key, PERSONAL_DATA_KEYWORDS)

    def test_each_data_type_has_keywords(self):
        """Each data type should have at least one keyword."""
        for data_type, keywords in PERSONAL_DATA_KEYWORDS.items():
            self.assertIsInstance(keywords, list, f"{data_type} should have a list")
            self.assertGreater(len(keywords), 0, f"{data_type} should have keywords")

    def test_keywords_are_lowercase(self):
        """All keywords should be lowercase for consistent matching."""
        for data_type, keywords in PERSONAL_DATA_KEYWORDS.items():
            for keyword in keywords:
                self.assertEqual(
                    keyword, keyword.lower(),
                    f"Keyword '{keyword}' in {data_type} should be lowercase"
                )


class TestDateKeywords(unittest.TestCase):
    """Tests for DATE_KEYWORDS list."""

    def test_date_keywords_is_list(self):
        """DATE_KEYWORDS should be a list."""
        self.assertIsInstance(DATE_KEYWORDS, list)

    def test_date_keywords_not_empty(self):
        """DATE_KEYWORDS should have entries."""
        self.assertGreater(len(DATE_KEYWORDS), 0)

    def test_includes_relative_time_words(self):
        """Should include common relative time references."""
        expected = ['since', 'last', 'this week', 'yesterday', 'today']
        for word in expected:
            self.assertIn(word, DATE_KEYWORDS, f"'{word}' should be in DATE_KEYWORDS")

    def test_includes_aggregation_words(self):
        """Should include aggregation-related words."""
        expected = ['average', 'total', 'how many', 'how much']
        for word in expected:
            self.assertIn(word, DATE_KEYWORDS, f"'{word}' should be in DATE_KEYWORDS")


class TestDetectPersonalDataIntentBasic(unittest.TestCase):
    """Basic tests for detect_personal_data_intent function."""

    def test_returns_dict(self):
        """Function should return a dictionary."""
        result = detect_personal_data_intent("test message")
        self.assertIsInstance(result, dict)

    def test_returns_expected_keys(self):
        """Result should contain all expected keys."""
        result = detect_personal_data_intent("test message")
        self.assertIn('is_personal_query', result)
        self.assertIn('data_types', result)
        self.assertIn('has_date_context', result)
        self.assertIn('is_meta_question', result)
        self.assertIn('is_compound_query', result)

    def test_empty_string_returns_false(self):
        """Empty string should not be detected as personal query."""
        result = detect_personal_data_intent("")
        self.assertFalse(result['is_personal_query'])
        self.assertEqual(result['data_types'], [])
        self.assertFalse(result['has_date_context'])
        self.assertFalse(result['is_meta_question'])
        self.assertFalse(result['is_compound_query'])

    def test_none_input_returns_false(self):
        """None input should not crash and return false."""
        result = detect_personal_data_intent(None)
        self.assertFalse(result['is_personal_query'])
        self.assertEqual(result['data_types'], [])
        self.assertFalse(result['is_meta_question'])
        self.assertFalse(result['is_compound_query'])

    def test_non_string_input_returns_false(self):
        """Non-string input should return false."""
        result = detect_personal_data_intent(123)
        self.assertFalse(result['is_personal_query'])


class TestWeightQueries(unittest.TestCase):
    """Tests for weight-related query detection."""

    def test_simple_weight_query(self):
        """Should detect 'my weight' as personal query."""
        result = detect_personal_data_intent("What is my weight?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('weight', result['data_types'])

    def test_weight_with_date(self):
        """Should detect date context in weight query."""
        result = detect_personal_data_intent("What was my weight last week?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('weight', result['data_types'])
        self.assertTrue(result['has_date_context'])

    def test_average_weight_query(self):
        """Should detect average weight query."""
        result = detect_personal_data_intent("What's my average weight this month?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('weight', result['data_types'])
        self.assertTrue(result['has_date_context'])

    def test_weight_loss_query(self):
        """Should detect weight loss related queries."""
        result = detect_personal_data_intent("How much weight have I lost since January?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('weight', result['data_types'])
        self.assertTrue(result['has_date_context'])


class TestJournalQueries(unittest.TestCase):
    """Tests for journal-related query detection."""

    def test_journal_entry_query(self):
        """Should detect journal entry queries."""
        result = detect_personal_data_intent("Show me my journal entries")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('journal', result['data_types'])

    def test_journal_with_date(self):
        """Should detect journal query with date."""
        result = detect_personal_data_intent("What did I journal about yesterday?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('journal', result['data_types'])
        self.assertTrue(result['has_date_context'])

    def test_gratitude_query(self):
        """Should detect gratitude as journal type."""
        result = detect_personal_data_intent("What have I been grateful for?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('journal', result['data_types'])


class TestMedicationQueries(unittest.TestCase):
    """Tests for medication-related query detection."""

    def test_medication_query(self):
        """Should detect medication queries."""
        result = detect_personal_data_intent("What medications am I taking?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('medication', result['data_types'])

    def test_supplement_query(self):
        """Should detect supplement as medication type."""
        result = detect_personal_data_intent("What supplements did I take today?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('medication', result['data_types'])
        self.assertTrue(result['has_date_context'])

    def test_vitamin_query(self):
        """Should detect vitamin as medication type."""
        result = detect_personal_data_intent("Have I taken my vitamins?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('medication', result['data_types'])


class TestFoodQueries(unittest.TestCase):
    """Tests for food-related query detection."""

    def test_food_query(self):
        """Should detect food queries."""
        result = detect_personal_data_intent("What food did I eat today?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('food', result['data_types'])
        self.assertTrue(result['has_date_context'])

    def test_calorie_query(self):
        """Should detect calorie queries."""
        result = detect_personal_data_intent("How many calories have I had?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('food', result['data_types'])

    def test_meal_query(self):
        """Should detect meal queries."""
        result = detect_personal_data_intent("What did I have for breakfast?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('food', result['data_types'])


class TestMoodQueries(unittest.TestCase):
    """Tests for mood-related query detection."""

    def test_mood_query(self):
        """Should detect mood queries."""
        result = detect_personal_data_intent("What has my mood been like?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('mood', result['data_types'])

    def test_feeling_query(self):
        """Should detect feeling as mood type."""
        result = detect_personal_data_intent("How have I been feeling lately?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('mood', result['data_types'])

    def test_anxiety_query(self):
        """Should detect anxiety as mood type."""
        result = detect_personal_data_intent("When did I feel anxious last week?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('mood', result['data_types'])
        self.assertTrue(result['has_date_context'])


class TestMultipleDataTypes(unittest.TestCase):
    """Tests for queries mentioning multiple data types."""

    def test_weight_and_mood(self):
        """Should detect multiple data types."""
        result = detect_personal_data_intent(
            "How has my weight and mood changed this month?"
        )
        self.assertTrue(result['is_personal_query'])
        self.assertIn('weight', result['data_types'])
        self.assertIn('mood', result['data_types'])
        self.assertTrue(result['has_date_context'])
        self.assertTrue(result['is_compound_query'])

    def test_food_and_exercise(self):
        """Should detect food and exercise."""
        result = detect_personal_data_intent(
            "What did I eat and how much did I exercise yesterday?"
        )
        self.assertTrue(result['is_personal_query'])
        self.assertIn('food', result['data_types'])
        self.assertIn('exercise', result['data_types'])
        self.assertTrue(result['is_compound_query'])


class TestDateContextDetection(unittest.TestCase):
    """Tests for date context detection."""

    def test_since_keyword(self):
        """Should detect 'since' as date context."""
        result = detect_personal_data_intent("My weight since December 1st")
        self.assertTrue(result['has_date_context'])

    def test_last_week(self):
        """Should detect 'last week' as date context."""
        result = detect_personal_data_intent("What did I journal last week?")
        self.assertTrue(result['has_date_context'])

    def test_specific_date(self):
        """Should detect specific date format."""
        result = detect_personal_data_intent("My weight on 12/25")
        self.assertTrue(result['has_date_context'])

    def test_iso_date_format(self):
        """Should detect ISO date format."""
        result = detect_personal_data_intent("My entries from 2024-01-15")
        self.assertTrue(result['has_date_context'])

    def test_month_name(self):
        """Should detect month names."""
        result = detect_personal_data_intent("My mood in January")
        self.assertTrue(result['has_date_context'])

    def test_average_keyword(self):
        """Should detect 'average' as date context."""
        result = detect_personal_data_intent("What is my average weight?")
        self.assertTrue(result['has_date_context'])


class TestNonPersonalQueries(unittest.TestCase):
    """Tests for queries that should NOT be detected as personal."""

    def test_general_question(self):
        """General questions should not be personal queries."""
        result = detect_personal_data_intent("How do I reset my password?")
        self.assertFalse(result['is_personal_query'])

    def test_about_feature(self):
        """Questions about features should not be personal."""
        result = detect_personal_data_intent("What can this app do?")
        self.assertFalse(result['is_personal_query'])

    def test_greeting(self):
        """Greetings should not be personal queries."""
        result = detect_personal_data_intent("Hello, how are you?")
        self.assertFalse(result['is_personal_query'])

    def test_help_request(self):
        """Help requests should not be personal queries."""
        result = detect_personal_data_intent("Can you help me?")
        self.assertFalse(result['is_personal_query'])

    def test_generic_statement(self):
        """Generic statements should not trigger detection."""
        result = detect_personal_data_intent("I like this application")
        self.assertFalse(result['is_personal_query'])


class TestCaseInsensitivity(unittest.TestCase):
    """Tests for case-insensitive matching."""

    def test_uppercase_query(self):
        """Should handle uppercase queries."""
        result = detect_personal_data_intent("WHAT IS MY WEIGHT?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('weight', result['data_types'])

    def test_mixed_case_query(self):
        """Should handle mixed case queries."""
        result = detect_personal_data_intent("What Is My JoUrNaL?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('journal', result['data_types'])


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and boundary conditions."""

    def test_partial_word_match_prevented(self):
        """Should not match partial words."""
        # 'wait' contains 'a' and 'i' but should not match personal pronouns
        result = detect_personal_data_intent("Please wait for the results")
        # No data types mentioned, so not personal
        self.assertFalse(result['is_personal_query'])

    def test_whitespace_handling(self):
        """Should handle extra whitespace."""
        result = detect_personal_data_intent("  What is   my weight  ?  ")
        self.assertTrue(result['is_personal_query'])

    def test_punctuation_handling(self):
        """Should handle various punctuation."""
        result = detect_personal_data_intent("My weight, mood, and sleep!")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('weight', result['data_types'])
        self.assertIn('mood', result['data_types'])
        self.assertIn('sleep', result['data_types'])


class TestAdditionalDataTypes(unittest.TestCase):
    """Tests for additional data types like sleep, exercise, glucose."""

    def test_sleep_query(self):
        """Should detect sleep queries."""
        result = detect_personal_data_intent("How many hours did I sleep?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('sleep', result['data_types'])

    def test_exercise_query(self):
        """Should detect exercise queries."""
        result = detect_personal_data_intent("How many steps have I walked?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('exercise', result['data_types'])

    def test_glucose_query(self):
        """Should detect glucose queries."""
        result = detect_personal_data_intent("What was my blood sugar this morning?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('glucose', result['data_types'])

    def test_blood_pressure_query(self):
        """Should detect blood pressure queries."""
        result = detect_personal_data_intent("What is my blood pressure?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('blood_pressure', result['data_types'])

    def test_faith_query(self):
        """Should detect faith/prayer queries."""
        result = detect_personal_data_intent("What scriptures have I read?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('faith', result['data_types'])

    def test_goals_query(self):
        """Should detect goals/habits queries."""
        result = detect_personal_data_intent("What is my habit streak?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('goals', result['data_types'])


class TestMetaQuestionKeywords(unittest.TestCase):
    """Tests for META_QUESTION_KEYWORDS list."""

    def test_meta_keywords_is_list(self):
        """META_QUESTION_KEYWORDS should be a list."""
        self.assertIsInstance(META_QUESTION_KEYWORDS, list)

    def test_meta_keywords_not_empty(self):
        """META_QUESTION_KEYWORDS should have entries."""
        self.assertGreater(len(META_QUESTION_KEYWORDS), 0)

    def test_includes_common_meta_phrases(self):
        """Should include common meta-question phrases."""
        expected = ['have i logged', 'did i log', 'have i tracked']
        for phrase in expected:
            self.assertIn(phrase, META_QUESTION_KEYWORDS)


class TestCompoundConnectors(unittest.TestCase):
    """Tests for COMPOUND_CONNECTORS list."""

    def test_compound_connectors_is_list(self):
        """COMPOUND_CONNECTORS should be a list."""
        self.assertIsInstance(COMPOUND_CONNECTORS, list)

    def test_compound_connectors_not_empty(self):
        """COMPOUND_CONNECTORS should have entries."""
        self.assertGreater(len(COMPOUND_CONNECTORS), 0)

    def test_includes_common_connectors(self):
        """Should include common compound connectors."""
        expected = [' and ', ' or ', ', ']
        for connector in expected:
            self.assertIn(connector, COMPOUND_CONNECTORS)


class TestMetaQuestionDetection(unittest.TestCase):
    """Tests for meta-question detection (asking about data existence)."""

    def test_have_i_logged_weight(self):
        """Should detect 'have I logged' as meta-question."""
        result = detect_personal_data_intent("Have I logged my weight today?")
        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['is_meta_question'])
        self.assertIn('weight', result['data_types'])
        self.assertTrue(result['has_date_context'])

    def test_did_i_log_food(self):
        """Should detect 'did I log' as meta-question."""
        result = detect_personal_data_intent("Did I log my food yesterday?")
        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['is_meta_question'])
        self.assertIn('food', result['data_types'])

    def test_have_i_tracked_mood(self):
        """Should detect 'have I tracked' as meta-question."""
        result = detect_personal_data_intent("Have I tracked my mood this week?")
        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['is_meta_question'])
        self.assertIn('mood', result['data_types'])

    def test_did_i_record_journal(self):
        """Should detect 'did I record' as meta-question."""
        result = detect_personal_data_intent("Did I record a journal entry?")
        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['is_meta_question'])
        self.assertIn('journal', result['data_types'])

    def test_any_entries_medication(self):
        """Should detect 'any entries' as meta-question."""
        result = detect_personal_data_intent("Do I have any entries for medication?")
        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['is_meta_question'])
        self.assertIn('medication', result['data_types'])

    def test_normal_query_not_meta(self):
        """Regular queries should not be meta-questions."""
        result = detect_personal_data_intent("What is my weight?")
        self.assertTrue(result['is_personal_query'])
        self.assertFalse(result['is_meta_question'])


class TestCompoundQueryDetection(unittest.TestCase):
    """Tests for compound query detection (multiple data types)."""

    def test_weight_and_mood_compound(self):
        """Should detect weight and mood as compound query."""
        result = detect_personal_data_intent(
            "Show me my weight and mood this week"
        )
        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['is_compound_query'])
        self.assertIn('weight', result['data_types'])
        self.assertIn('mood', result['data_types'])

    def test_food_or_exercise_compound(self):
        """Should detect food or exercise as compound query."""
        result = detect_personal_data_intent(
            "Did I track food or exercise today?"
        )
        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['is_compound_query'])
        self.assertIn('food', result['data_types'])
        self.assertIn('exercise', result['data_types'])

    def test_three_data_types_compound(self):
        """Should detect three data types as compound query."""
        result = detect_personal_data_intent(
            "How are my weight, mood, and sleep this month?"
        )
        self.assertTrue(result['is_personal_query'])
        self.assertTrue(result['is_compound_query'])
        self.assertEqual(len(result['data_types']), 3)

    def test_single_type_not_compound(self):
        """Single data type should not be compound query."""
        result = detect_personal_data_intent("What is my weight?")
        self.assertTrue(result['is_personal_query'])
        self.assertFalse(result['is_compound_query'])


class TestNewKeywordCoverage(unittest.TestCase):
    """Tests for newly added keywords."""

    def test_bmi_keyword(self):
        """Should detect BMI as weight type."""
        result = detect_personal_data_intent("What is my BMI?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('weight', result['data_types'])

    def test_weight_trend_keyword(self):
        """Should detect weight trend as weight type."""
        result = detect_personal_data_intent("Show me my weight trend")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('weight', result['data_types'])

    def test_macros_keyword(self):
        """Should detect macros as food type."""
        result = detect_personal_data_intent("How are my macros today?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('food', result['data_types'])

    def test_wellbeing_keyword(self):
        """Should detect wellbeing as mood type."""
        result = detect_personal_data_intent("How is my wellbeing?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('mood', result['data_types'])

    def test_mental_health_keyword(self):
        """Should detect mental health as mood type."""
        result = detect_personal_data_intent("How is my mental health this week?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('mood', result['data_types'])

    def test_sleep_quality_keyword(self):
        """Should detect sleep quality as sleep type."""
        result = detect_personal_data_intent("How was my sleep quality?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('sleep', result['data_types'])

    def test_fitness_keyword(self):
        """Should detect fitness as exercise type."""
        result = detect_personal_data_intent("What is my fitness level?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('exercise', result['data_types'])

    def test_yoga_keyword(self):
        """Should detect yoga as exercise type."""
        result = detect_personal_data_intent("Did I do yoga this week?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('exercise', result['data_types'])

    def test_insulin_keyword(self):
        """Should detect insulin as glucose type."""
        result = detect_personal_data_intent("When did I take my insulin?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('glucose', result['data_types'])

    def test_heart_rate_keyword(self):
        """Should detect heart rate as blood pressure type."""
        result = detect_personal_data_intent("What is my heart rate?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('blood_pressure', result['data_types'])

    def test_quiet_time_keyword(self):
        """Should detect quiet time as faith type."""
        result = detect_personal_data_intent("Did I have quiet time today?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('faith', result['data_types'])

    def test_milestone_keyword(self):
        """Should detect milestone as goals type."""
        result = detect_personal_data_intent("What milestones have I reached?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('goals', result['data_types'])

    def test_rx_keyword(self):
        """Should detect rx as medication type."""
        result = detect_personal_data_intent("What is my rx schedule?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('medication', result['data_types'])

    def test_morning_pages_keyword(self):
        """Should detect morning pages as journal type."""
        result = detect_personal_data_intent("Did I write my morning pages?")
        self.assertTrue(result['is_personal_query'])
        self.assertIn('journal', result['data_types'])


if __name__ == '__main__':
    unittest.main()
