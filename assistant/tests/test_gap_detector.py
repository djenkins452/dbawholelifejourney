"""
Unit tests for the Gap Detector module.

Owner: admin@wholelifejourney.com

Tests cover various gap detection scenarios to ensure accurate identification
and categorization of knowledge gaps.
"""

import unittest
from datetime import datetime
from unittest.mock import patch

from assistant.gap_detector import (
    CONTRACTION_FRAGMENTS,
    CONVERSATIONAL_WORDS,
    DATA_TYPES_WITH_METHODS,
    GapSeverity,
    GapType,
    STOP_WORDS,
    SUPPORTED_DATA_TYPES,
    SUPPORTED_QUERY_PATTERNS,
    categorize_gap_severity,
    detect_knowledge_gap,
    extract_potential_keywords,
)


class TestGapTypeEnum(unittest.TestCase):
    """Tests for GapType enum."""

    def test_gap_type_has_required_values(self):
        """GapType should have all required enum values."""
        expected_values = [
            'UNKNOWN_DATA_TYPE',
            'MISSING_KEYWORDS',
            'NO_DATA_METHOD',
            'UNSUPPORTED_QUERY_PATTERN',
        ]
        for value in expected_values:
            self.assertTrue(
                hasattr(GapType, value),
                f"GapType should have {value}"
            )

    def test_gap_type_values_are_strings(self):
        """GapType values should be lowercase strings."""
        for gap_type in GapType:
            self.assertIsInstance(gap_type.value, str)
            self.assertEqual(gap_type.value, gap_type.value.lower())


class TestGapSeverityEnum(unittest.TestCase):
    """Tests for GapSeverity enum."""

    def test_gap_severity_has_required_values(self):
        """GapSeverity should have LOW, MEDIUM, HIGH."""
        self.assertTrue(hasattr(GapSeverity, 'LOW'))
        self.assertTrue(hasattr(GapSeverity, 'MEDIUM'))
        self.assertTrue(hasattr(GapSeverity, 'HIGH'))

    def test_gap_severity_values(self):
        """GapSeverity values should match expected strings."""
        self.assertEqual(GapSeverity.LOW.value, 'low')
        self.assertEqual(GapSeverity.MEDIUM.value, 'medium')
        self.assertEqual(GapSeverity.HIGH.value, 'high')


class TestSupportedDataTypes(unittest.TestCase):
    """Tests for data type constants."""

    def test_supported_data_types_includes_expected(self):
        """SUPPORTED_DATA_TYPES should include all expected types."""
        expected = ['weight', 'journal', 'medication', 'food', 'mood']
        for dt in expected:
            self.assertIn(dt, SUPPORTED_DATA_TYPES)

    def test_data_types_with_methods_subset(self):
        """DATA_TYPES_WITH_METHODS should be subset of SUPPORTED_DATA_TYPES."""
        for dt in DATA_TYPES_WITH_METHODS:
            self.assertIn(dt, SUPPORTED_DATA_TYPES)


class TestDetectKnowledgeGapBasic(unittest.TestCase):
    """Basic tests for detect_knowledge_gap function."""

    def test_returns_dict(self):
        """Function should return a dictionary."""
        result = detect_knowledge_gap("test query")
        self.assertIsInstance(result, dict)

    def test_returns_expected_keys(self):
        """Result should contain all expected keys."""
        result = detect_knowledge_gap("test query")
        expected_keys = [
            'gap_detected', 'gap_type', 'original_query',
            'detected_intent', 'suggested_category', 'timestamp',
        ]
        for key in expected_keys:
            self.assertIn(key, result)

    def test_empty_query_returns_no_gap(self):
        """Empty query should not detect a gap."""
        result = detect_knowledge_gap("")
        self.assertFalse(result['gap_detected'])
        self.assertIsNone(result['gap_type'])

    def test_none_intent_returns_no_gap(self):
        """None intent result should not detect a gap."""
        result = detect_knowledge_gap("some query", intent_result=None)
        self.assertFalse(result['gap_detected'])

    def test_timestamp_is_datetime(self):
        """Result timestamp should be a datetime object."""
        result = detect_knowledge_gap("test query")
        self.assertIsInstance(result['timestamp'], datetime)

    def test_original_query_preserved(self):
        """Original query should be preserved in result."""
        query = "What was my weight yesterday?"
        result = detect_knowledge_gap(query)
        self.assertEqual(result['original_query'], query)


class TestDetectKnowledgeGapNoDataMethod(unittest.TestCase):
    """Tests for NO_DATA_METHOD gap detection."""

    def test_detects_no_method_for_sleep(self):
        """Should detect gap when sleep data type has no query method."""
        intent_result = {
            'is_personal_query': True,
            'data_types': ['sleep'],
            'has_date_context': True,
            'is_meta_question': False,
            'is_compound_query': False,
        }
        result = detect_knowledge_gap(
            "How many hours did I sleep last night?",
            intent_result=intent_result,
            data_result=None
        )
        self.assertTrue(result['gap_detected'])
        self.assertEqual(result['gap_type'], GapType.NO_DATA_METHOD)
        self.assertEqual(result['suggested_category'], 'sleep')

    def test_detects_no_method_for_exercise(self):
        """Should detect gap when exercise data type has no query method."""
        intent_result = {
            'is_personal_query': True,
            'data_types': ['exercise'],
            'has_date_context': True,
            'is_meta_question': False,
            'is_compound_query': False,
        }
        result = detect_knowledge_gap(
            "How many steps did I take yesterday?",
            intent_result=intent_result,
            data_result=None
        )
        self.assertTrue(result['gap_detected'])
        self.assertEqual(result['gap_type'], GapType.NO_DATA_METHOD)
        self.assertEqual(result['suggested_category'], 'exercise')

    def test_no_gap_when_data_exists(self):
        """Should not detect gap when data is returned."""
        intent_result = {
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_date_context': True,
            'is_meta_question': False,
            'is_compound_query': False,
        }
        data_result = {
            'weight': {
                'type': 'weight',
                'count': 10,
                'average': 175.5,
            }
        }
        result = detect_knowledge_gap(
            "What was my average weight last week?",
            intent_result=intent_result,
            data_result=data_result
        )
        self.assertFalse(result['gap_detected'])


class TestDetectKnowledgeGapMissingKeywords(unittest.TestCase):
    """Tests for MISSING_KEYWORDS gap detection."""

    def test_detects_missing_keywords(self):
        """Should detect gap when personal query has no detected data types."""
        intent_result = {
            'is_personal_query': True,
            'data_types': [],
            'has_date_context': True,
            'is_meta_question': False,
            'is_compound_query': False,
        }
        result = detect_knowledge_gap(
            "What was my hydration level yesterday?",
            intent_result=intent_result,
            data_result=None
        )
        self.assertTrue(result['gap_detected'])
        self.assertEqual(result['gap_type'], GapType.MISSING_KEYWORDS)


class TestDetectKnowledgeGapUnknownDataType(unittest.TestCase):
    """Tests for UNKNOWN_DATA_TYPE gap detection."""

    def test_detects_unknown_data_type(self):
        """Should detect gap when personal indicators exist but no data type detected."""
        intent_result = {
            'is_personal_query': False,
            'data_types': [],
            'has_date_context': False,
            'is_meta_question': False,
            'is_compound_query': False,
        }
        result = detect_knowledge_gap(
            "What was my caffeine intake today?",
            intent_result=intent_result,
            data_result=None
        )
        self.assertTrue(result['gap_detected'])
        self.assertEqual(result['gap_type'], GapType.UNKNOWN_DATA_TYPE)


class TestDetectKnowledgeGapUnsupportedPattern(unittest.TestCase):
    """Tests for UNSUPPORTED_QUERY_PATTERN gap detection."""

    def test_detects_comparison_pattern(self):
        """Should detect gap for comparison queries."""
        intent_result = {
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_date_context': True,
            'is_meta_question': False,
            'is_compound_query': False,
        }
        result = detect_knowledge_gap(
            "Compare my weight this week versus last week",
            intent_result=intent_result,
            data_result=None
        )
        self.assertTrue(result['gap_detected'])
        self.assertEqual(result['gap_type'], GapType.UNSUPPORTED_QUERY_PATTERN)
        self.assertEqual(result['suggested_category'], 'comparison queries')

    def test_detects_correlation_pattern(self):
        """Should detect gap for correlation queries."""
        intent_result = {
            'is_personal_query': True,
            'data_types': ['mood', 'sleep'],
            'has_date_context': True,
            'is_meta_question': False,
            'is_compound_query': True,
        }
        result = detect_knowledge_gap(
            "How does my sleep affect my mood?",
            intent_result=intent_result,
            data_result=None
        )
        self.assertTrue(result['gap_detected'])
        self.assertEqual(result['gap_type'], GapType.UNSUPPORTED_QUERY_PATTERN)
        self.assertIn('correlation', result['suggested_category'])

    def test_detects_prediction_pattern(self):
        """Should detect gap for predictive queries."""
        intent_result = {
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_date_context': False,
            'is_meta_question': False,
            'is_compound_query': False,
        }
        result = detect_knowledge_gap(
            "Will I reach my weight goal by next month?",
            intent_result=intent_result,
            data_result=None
        )
        self.assertTrue(result['gap_detected'])
        self.assertEqual(result['gap_type'], GapType.UNSUPPORTED_QUERY_PATTERN)
        self.assertIn('predict', result['suggested_category'])


class TestExtractPotentialKeywords(unittest.TestCase):
    """Tests for extract_potential_keywords function."""

    def test_returns_list(self):
        """Function should return a list."""
        result = extract_potential_keywords("test query")
        self.assertIsInstance(result, list)

    def test_empty_query_returns_empty_list(self):
        """Empty query should return empty list."""
        result = extract_potential_keywords("")
        self.assertEqual(result, [])

    def test_filters_stop_words(self):
        """Should filter out stop words."""
        result = extract_potential_keywords("what is the answer")
        for word in ['what', 'is', 'the']:
            self.assertNotIn(word, result)

    def test_filters_known_keywords(self):
        """Should filter out known personal data keywords."""
        result = extract_potential_keywords("what was my weight yesterday")
        self.assertNotIn('weight', result)
        self.assertNotIn('yesterday', result)

    def test_extracts_potential_new_keywords(self):
        """Should extract words that could be new data type indicators."""
        result = extract_potential_keywords("What was my hydration level yesterday?")
        self.assertIn('hydration', result)

    def test_prioritizes_words_after_my(self):
        """Words after 'my' should be prioritized."""
        result = extract_potential_keywords("my caffeine intake was high")
        # caffeine should appear before other candidates
        if 'caffeine' in result and 'high' in result:
            self.assertLess(result.index('caffeine'), result.index('high'))

    def test_filters_short_words(self):
        """Should filter out words shorter than 4 characters."""
        result = extract_potential_keywords("my cat is fat and the dog ran")
        self.assertNotIn('cat', result)
        self.assertNotIn('fat', result)
        self.assertNotIn('dog', result)
        self.assertNotIn('ran', result)

    def test_returns_unique_words(self):
        """Should not return duplicate words."""
        result = extract_potential_keywords("hydration hydration hydration level")
        self.assertEqual(len(result), len(set(result)))


class TestCategorizegapseverity(unittest.TestCase):
    """Tests for categorize_gap_severity function."""

    def test_missing_keywords_is_low(self):
        """MISSING_KEYWORDS should be LOW severity."""
        result = categorize_gap_severity(GapType.MISSING_KEYWORDS)
        self.assertEqual(result, GapSeverity.LOW)

    def test_no_data_method_is_medium(self):
        """NO_DATA_METHOD should be MEDIUM severity."""
        result = categorize_gap_severity(GapType.NO_DATA_METHOD)
        self.assertEqual(result, GapSeverity.MEDIUM)

    def test_unknown_data_type_is_high(self):
        """UNKNOWN_DATA_TYPE should be HIGH severity."""
        result = categorize_gap_severity(GapType.UNKNOWN_DATA_TYPE)
        self.assertEqual(result, GapSeverity.HIGH)

    def test_unsupported_query_pattern_is_high(self):
        """UNSUPPORTED_QUERY_PATTERN should be HIGH severity."""
        result = categorize_gap_severity(GapType.UNSUPPORTED_QUERY_PATTERN)
        self.assertEqual(result, GapSeverity.HIGH)

    def test_none_returns_low(self):
        """None gap type should return LOW severity."""
        result = categorize_gap_severity(None)
        self.assertEqual(result, GapSeverity.LOW)


class TestStopWords(unittest.TestCase):
    """Tests for STOP_WORDS constant."""

    def test_stop_words_is_set(self):
        """STOP_WORDS should be a set for O(1) lookup."""
        self.assertIsInstance(STOP_WORDS, set)

    def test_stop_words_contains_common_words(self):
        """STOP_WORDS should contain common English stop words."""
        expected = ['the', 'a', 'an', 'is', 'are', 'was', 'were', 'my', 'i']
        for word in expected:
            self.assertIn(word, STOP_WORDS)


class TestSupportedQueryPatterns(unittest.TestCase):
    """Tests for SUPPORTED_QUERY_PATTERNS constant."""

    def test_is_list(self):
        """SUPPORTED_QUERY_PATTERNS should be a list."""
        self.assertIsInstance(SUPPORTED_QUERY_PATTERNS, list)

    def test_contains_question_words(self):
        """Should contain common question words."""
        expected = ['what', 'how', 'when', 'show']
        for word in expected:
            self.assertIn(word, SUPPORTED_QUERY_PATTERNS)


class TestContractionFragments(unittest.TestCase):
    """Tests for CONTRACTION_FRAGMENTS constant and filtering."""

    def test_contraction_fragments_is_set(self):
        """CONTRACTION_FRAGMENTS should be a set for O(1) lookup."""
        self.assertIsInstance(CONTRACTION_FRAGMENTS, set)

    def test_contains_common_contraction_fragments(self):
        """Should contain common contraction fragments."""
        expected = ['didn', 'doesn', 'don', 'wouldn', 'couldn', 'shouldn',
                    'wasn', 'weren', 'isn', 'aren', 'hasn', 'haven', 'hadn']
        for word in expected:
            self.assertIn(word, CONTRACTION_FRAGMENTS)

    def test_filters_didnt_fragment(self):
        """Should filter 'didn' from 'didn't'."""
        result = extract_potential_keywords("I didn't log my hydration today")
        self.assertNotIn('didn', result)
        self.assertIn('hydration', result)

    def test_filters_wouldnt_fragment(self):
        """Should filter 'wouldn' from 'wouldn't'."""
        result = extract_potential_keywords("I wouldn't want to miss logging")
        self.assertNotIn('wouldn', result)

    def test_filters_couldnt_fragment(self):
        """Should filter 'couldn' from 'couldn't'."""
        result = extract_potential_keywords("I couldn't remember my meditation time")
        self.assertNotIn('couldn', result)
        self.assertIn('meditation', result)


class TestConversationalWords(unittest.TestCase):
    """Tests for CONVERSATIONAL_WORDS constant and filtering."""

    def test_conversational_words_is_set(self):
        """CONVERSATIONAL_WORDS should be a set for O(1) lookup."""
        self.assertIsInstance(CONVERSATIONAL_WORDS, set)

    def test_contains_everything_variants(self):
        """Should contain 'everything' and similar words."""
        expected = ['everything', 'something', 'nothing', 'anything',
                    'everyone', 'someone', 'anyone', 'nobody', 'somebody']
        for word in expected:
            self.assertIn(word, CONVERSATIONAL_WORDS)

    def test_filters_everything(self):
        """Should filter 'everything' as a conversational word."""
        result = extract_potential_keywords("Make sure everything looks like you want")
        self.assertNotIn('everything', result)

    def test_filters_something(self):
        """Should filter 'something' as a conversational word."""
        result = extract_potential_keywords("I want to track something about hydration")
        self.assertNotIn('something', result)
        self.assertIn('hydration', result)

    def test_filters_common_verbs(self):
        """Should filter common verbs like 'want', 'think', 'know'."""
        result = extract_potential_keywords("I want to know about my meditation")
        self.assertNotIn('want', result)
        self.assertNotIn('know', result)
        self.assertIn('meditation', result)


class TestFalsePositivePatterns(unittest.TestCase):
    """Tests for known false positive patterns that should be filtered."""

    def test_didnt_is_not_data_type(self):
        """'didn' from 'didn't' should never be flagged as a data type."""
        # This was a real false positive case
        result = extract_potential_keywords("I didn't log my weight today")
        self.assertNotIn('didn', result)

    def test_everything_is_not_data_type(self):
        """'everything' should never be flagged as a data type."""
        # This was a real false positive case
        result = extract_potential_keywords(
            "Wrong, you should have told me to go to preferences and make sure "
            "everything looks like you want it to"
        )
        self.assertNotIn('everything', result)

    def test_conversational_feedback_no_false_positives(self):
        """Conversational feedback should not extract false data types."""
        # User giving feedback about the app, not requesting data tracking
        result = extract_potential_keywords(
            "That's not what I wanted. You should have shown me something different."
        )
        self.assertNotIn('wanted', result)
        self.assertNotIn('something', result)
        self.assertNotIn('different', result)

    def test_real_data_types_still_extracted(self):
        """Real potential data types should still be extracted."""
        result = extract_potential_keywords("What was my hydration level yesterday?")
        self.assertIn('hydration', result)

    def test_caffeine_still_extracted(self):
        """Domain-relevant words like 'caffeine' should still be extracted."""
        result = extract_potential_keywords("How much caffeine did I have today?")
        self.assertIn('caffeine', result)

    def test_minimum_length_filters_short_words(self):
        """Words with fewer than 4 characters should be filtered."""
        result = extract_potential_keywords("my cat ate the bat")
        self.assertNotIn('cat', result)
        self.assertNotIn('ate', result)
        self.assertNotIn('bat', result)


class TestUINavigationWordsFiltered(unittest.TestCase):
    """Tests for filtering UI/navigation terms that are not data types."""

    def test_dashboard_is_not_data_type(self):
        """'dashboard' is a UI term, not a data type to be tracked."""
        result = extract_potential_keywords("how do I get to the dashboard")
        self.assertNotIn('dashboard', result)

    def test_settings_is_not_data_type(self):
        """'settings' is a UI term, not a data type to be tracked."""
        result = extract_potential_keywords("where are my settings")
        self.assertNotIn('settings', result)

    def test_page_is_not_data_type(self):
        """'page' is a UI term, not a data type to be tracked."""
        result = extract_potential_keywords("take me to the weight page")
        self.assertNotIn('page', result)

    def test_navigation_question_no_gap(self):
        """Navigation questions should not trigger unknown data type gap."""
        intent_result = {
            'is_personal_query': False,
            'data_types': [],
            'has_date_context': False,
            'is_meta_question': False,
            'is_compound_query': False,
        }
        result = detect_knowledge_gap(
            "how do I get to the dashboard",
            intent_result=intent_result,
            data_result=None
        )
        # Should NOT detect a gap - user is asking for navigation help
        # not asking to store "dashboard" as data
        self.assertFalse(result['gap_detected'])


class TestIntegrationScenarios(unittest.TestCase):
    """Integration tests for realistic gap detection scenarios."""

    def test_no_gap_for_supported_weight_query(self):
        """Supported weight query with data should not show gap."""
        intent_result = {
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_date_context': True,
            'is_meta_question': False,
            'is_compound_query': False,
        }
        data_result = {'weight': {'type': 'weight', 'count': 5}}

        result = detect_knowledge_gap(
            "What was my average weight last week?",
            intent_result=intent_result,
            data_result=data_result
        )
        self.assertFalse(result['gap_detected'])

    def test_gap_for_new_data_type_request(self):
        """Query for unrecognized data type should detect gap."""
        intent_result = {
            'is_personal_query': False,
            'data_types': [],
            'has_date_context': True,
            'is_meta_question': False,
            'is_compound_query': False,
        }

        result = detect_knowledge_gap(
            "How much water did I drink today?",
            intent_result=intent_result,
            data_result=None
        )
        # Should detect as unknown data type since "my" is not in query
        # but "i" is, indicating personal context
        self.assertTrue(result['gap_detected'])

    def test_no_gap_when_user_has_no_data(self):
        """Should not flag gap when user simply has no logged data."""
        intent_result = {
            'is_personal_query': True,
            'data_types': ['weight'],
            'has_date_context': True,
            'is_meta_question': False,
            'is_compound_query': False,
        }
        # Empty data result (user has no weight data)
        data_result = {}

        result = detect_knowledge_gap(
            "What was my weight last week?",
            intent_result=intent_result,
            data_result=data_result
        )
        # This is not a gap - we recognize weight, we just have no data
        self.assertFalse(result['gap_detected'])


if __name__ == '__main__':
    unittest.main()
