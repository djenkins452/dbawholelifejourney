"""
Unit tests for the Task Generator module.

Owner: admin@wholelifejourney.com

Tests cover task generation for various gap types to ensure proper
improvement tasks are created with appropriate templates.
"""

import unittest
from datetime import datetime

from assistant.gap_detector import GapSeverity, GapType
from assistant.task_generator import (
    PROJECT_NAME,
    ImprovementTask,
    generate_code_template,
    generate_improvement_task,
    generate_test_template,
)


class TestImprovementTaskDataclass(unittest.TestCase):
    """Tests for ImprovementTask dataclass."""

    def test_create_improvement_task(self):
        """Can create an ImprovementTask with all fields."""
        task = ImprovementTask(
            title="Test Task",
            description="Test description",
            gap_type=GapType.MISSING_KEYWORDS,
            severity=GapSeverity.LOW,
            original_query="What was my hydration?",
            suggested_fix="Add hydration keyword",
            code_template="# code here",
            test_requirements=["Test 1", "Test 2"],
            requires_approval=False,
        )
        self.assertEqual(task.title, "Test Task")
        self.assertEqual(task.gap_type, GapType.MISSING_KEYWORDS)
        self.assertFalse(task.requires_approval)

    def test_improvement_task_has_created_at(self):
        """ImprovementTask should have created_at timestamp."""
        task = ImprovementTask(
            title="Test",
            description="Test",
            gap_type=GapType.MISSING_KEYWORDS,
            severity=GapSeverity.LOW,
            original_query="test",
            suggested_fix="test",
            code_template="",
            test_requirements=[],
            requires_approval=False,
        )
        self.assertIsInstance(task.created_at, datetime)

    def test_to_dict(self):
        """to_dict() should return serializable dictionary."""
        task = ImprovementTask(
            title="Test Task",
            description="Test description",
            gap_type=GapType.MISSING_KEYWORDS,
            severity=GapSeverity.LOW,
            original_query="test query",
            suggested_fix="fix",
            code_template="# code",
            test_requirements=["req1"],
            requires_approval=False,
        )
        result = task.to_dict()

        self.assertIsInstance(result, dict)
        self.assertEqual(result['title'], "Test Task")
        self.assertEqual(result['gap_type'], 'missing_keywords')
        self.assertEqual(result['severity'], 'low')
        self.assertEqual(result['project'], PROJECT_NAME)
        self.assertIn('created_at', result)

    def test_to_dict_handles_gap_type_value(self):
        """to_dict() should convert GapType enum to string value."""
        task = ImprovementTask(
            title="Test",
            description="Test",
            gap_type=GapType.NO_DATA_METHOD,
            severity=GapSeverity.MEDIUM,
            original_query="test",
            suggested_fix="fix",
            code_template="",
            test_requirements=[],
            requires_approval=True,
        )
        result = task.to_dict()
        self.assertEqual(result['gap_type'], 'no_data_method')
        self.assertEqual(result['severity'], 'medium')


class TestGenerateImprovementTaskBasic(unittest.TestCase):
    """Basic tests for generate_improvement_task function."""

    def test_returns_none_when_no_gap(self):
        """Should return None when gap_detected is False."""
        gap_result = {'gap_detected': False}
        result = generate_improvement_task(gap_result)
        self.assertIsNone(result)

    def test_returns_improvement_task_when_gap_detected(self):
        """Should return ImprovementTask when gap is detected."""
        gap_result = {
            'gap_detected': True,
            'gap_type': GapType.MISSING_KEYWORDS,
            'original_query': 'What was my hydration?',
            'suggested_category': 'hydration',
        }
        result = generate_improvement_task(gap_result)
        self.assertIsInstance(result, ImprovementTask)

    def test_returns_none_when_gap_detected_missing(self):
        """Should return None when gap_detected key is missing."""
        gap_result = {'gap_type': GapType.MISSING_KEYWORDS}
        result = generate_improvement_task(gap_result)
        self.assertIsNone(result)


class TestMissingKeywordsTask(unittest.TestCase):
    """Tests for MISSING_KEYWORDS task generation."""

    def setUp(self):
        self.gap_result = {
            'gap_detected': True,
            'gap_type': GapType.MISSING_KEYWORDS,
            'original_query': 'What was my hydration level?',
            'suggested_category': 'hydration',
        }

    def test_generates_correct_title(self):
        """Title should reference the suggested category."""
        task = generate_improvement_task(self.gap_result)
        self.assertIn('hydration', task.title)
        self.assertIn('keyword', task.title.lower())

    def test_generates_correct_gap_type(self):
        """Gap type should be MISSING_KEYWORDS."""
        task = generate_improvement_task(self.gap_result)
        self.assertEqual(task.gap_type, GapType.MISSING_KEYWORDS)

    def test_severity_is_low(self):
        """MISSING_KEYWORDS should have LOW severity."""
        task = generate_improvement_task(self.gap_result)
        self.assertEqual(task.severity, GapSeverity.LOW)

    def test_requires_approval_is_false(self):
        """LOW severity should not require approval."""
        task = generate_improvement_task(self.gap_result)
        self.assertFalse(task.requires_approval)

    def test_description_includes_query(self):
        """Description should include the original query."""
        task = generate_improvement_task(self.gap_result)
        self.assertIn('hydration level', task.description)

    def test_code_template_references_intent_detector(self):
        """Code template should reference intent_detector.py."""
        task = generate_improvement_task(self.gap_result)
        self.assertIn('intent_detector', task.code_template)
        self.assertIn('hydration', task.code_template)

    def test_test_requirements_not_empty(self):
        """Test requirements should not be empty."""
        task = generate_improvement_task(self.gap_result)
        self.assertGreater(len(task.test_requirements), 0)


class TestNoDataMethodTask(unittest.TestCase):
    """Tests for NO_DATA_METHOD task generation."""

    def setUp(self):
        self.gap_result = {
            'gap_detected': True,
            'gap_type': GapType.NO_DATA_METHOD,
            'original_query': 'How many hours did I sleep?',
            'suggested_category': 'sleep',
        }

    def test_generates_correct_title(self):
        """Title should reference adding a query method."""
        task = generate_improvement_task(self.gap_result)
        self.assertIn('sleep', task.title)
        self.assertIn('method', task.title.lower())

    def test_generates_correct_gap_type(self):
        """Gap type should be NO_DATA_METHOD."""
        task = generate_improvement_task(self.gap_result)
        self.assertEqual(task.gap_type, GapType.NO_DATA_METHOD)

    def test_severity_is_medium(self):
        """NO_DATA_METHOD should have MEDIUM severity."""
        task = generate_improvement_task(self.gap_result)
        self.assertEqual(task.severity, GapSeverity.MEDIUM)

    def test_requires_approval_is_true(self):
        """MEDIUM severity should require approval."""
        task = generate_improvement_task(self.gap_result)
        self.assertTrue(task.requires_approval)

    def test_code_template_includes_method_definition(self):
        """Code template should include method definition pattern."""
        task = generate_improvement_task(self.gap_result)
        self.assertIn('get_sleep_data', task.code_template)
        self.assertIn('def ', task.code_template)

    def test_suggested_fix_references_data_service(self):
        """Suggested fix should reference data_service.py."""
        task = generate_improvement_task(self.gap_result)
        self.assertIn('data_service', task.suggested_fix)


class TestUnsupportedQueryPatternTask(unittest.TestCase):
    """Tests for UNSUPPORTED_QUERY_PATTERN task generation."""

    def setUp(self):
        self.gap_result = {
            'gap_detected': True,
            'gap_type': GapType.UNSUPPORTED_QUERY_PATTERN,
            'original_query': 'Compare my weight this week vs last week',
            'suggested_category': 'comparison queries',
        }

    def test_generates_correct_title(self):
        """Title should reference the pattern type."""
        task = generate_improvement_task(self.gap_result)
        self.assertIn('comparison', task.title.lower())

    def test_generates_correct_gap_type(self):
        """Gap type should be UNSUPPORTED_QUERY_PATTERN."""
        task = generate_improvement_task(self.gap_result)
        self.assertEqual(task.gap_type, GapType.UNSUPPORTED_QUERY_PATTERN)

    def test_severity_is_high(self):
        """UNSUPPORTED_QUERY_PATTERN should have HIGH severity."""
        task = generate_improvement_task(self.gap_result)
        self.assertEqual(task.severity, GapSeverity.HIGH)

    def test_requires_approval_is_true(self):
        """HIGH severity should require approval."""
        task = generate_improvement_task(self.gap_result)
        self.assertTrue(task.requires_approval)

    def test_code_template_includes_analysis_patterns(self):
        """Code template should include analysis function patterns."""
        task = generate_improvement_task(self.gap_result)
        # Should include comparison/correlation/prediction helpers
        self.assertIn('def ', task.code_template)


class TestUnknownDataTypeTask(unittest.TestCase):
    """Tests for UNKNOWN_DATA_TYPE task generation."""

    def setUp(self):
        self.gap_result = {
            'gap_detected': True,
            'gap_type': GapType.UNKNOWN_DATA_TYPE,
            'original_query': 'What was my caffeine intake?',
            'suggested_category': 'caffeine',
        }

    def test_generates_correct_title(self):
        """Title should reference evaluating new data type."""
        task = generate_improvement_task(self.gap_result)
        self.assertIn('caffeine', task.title)
        self.assertIn('data type', task.title.lower())

    def test_generates_correct_gap_type(self):
        """Gap type should be UNKNOWN_DATA_TYPE."""
        task = generate_improvement_task(self.gap_result)
        self.assertEqual(task.gap_type, GapType.UNKNOWN_DATA_TYPE)

    def test_severity_is_high(self):
        """UNKNOWN_DATA_TYPE should have HIGH severity."""
        task = generate_improvement_task(self.gap_result)
        self.assertEqual(task.severity, GapSeverity.HIGH)

    def test_requires_approval_is_true(self):
        """HIGH severity should require approval."""
        task = generate_improvement_task(self.gap_result)
        self.assertTrue(task.requires_approval)

    def test_code_template_includes_model_definition(self):
        """Code template should include model definition pattern."""
        task = generate_improvement_task(self.gap_result)
        self.assertIn('class', task.code_template)
        self.assertIn('models.Model', task.code_template)

    def test_suggested_fix_includes_multiple_steps(self):
        """Suggested fix should include multiple implementation steps."""
        task = generate_improvement_task(self.gap_result)
        self.assertIn('1.', task.suggested_fix)
        self.assertIn('2.', task.suggested_fix)


class TestGenerateCodeTemplate(unittest.TestCase):
    """Tests for generate_code_template function."""

    def test_missing_keywords_template(self):
        """MISSING_KEYWORDS template references PERSONAL_DATA_KEYWORDS."""
        template = generate_code_template(GapType.MISSING_KEYWORDS, 'hydration')
        self.assertIn('PERSONAL_DATA_KEYWORDS', template)
        self.assertIn('hydration', template)

    def test_no_data_method_template(self):
        """NO_DATA_METHOD template includes method definition."""
        template = generate_code_template(GapType.NO_DATA_METHOD, 'sleep')
        self.assertIn('get_sleep_data', template)
        self.assertIn('PersonalDataService', template)
        self.assertIn('query_map', template)

    def test_unsupported_pattern_template(self):
        """UNSUPPORTED_QUERY_PATTERN template includes analysis functions."""
        template = generate_code_template(
            GapType.UNSUPPORTED_QUERY_PATTERN, 'comparison'
        )
        self.assertIn('compare_data', template)
        self.assertIn('analyze_correlation', template)

    def test_unknown_data_type_template(self):
        """UNKNOWN_DATA_TYPE template includes model and full workflow."""
        template = generate_code_template(GapType.UNKNOWN_DATA_TYPE, 'caffeine')
        self.assertIn('class Caffeine', template)
        self.assertIn('models.Model', template)
        self.assertIn('PERSONAL_DATA_KEYWORDS', template)
        self.assertIn('SUPPORTED_DATA_TYPES', template)


class TestGenerateTestTemplate(unittest.TestCase):
    """Tests for generate_test_template function."""

    def test_missing_keywords_test_template(self):
        """MISSING_KEYWORDS test template includes keyword detection tests."""
        template = generate_test_template(GapType.MISSING_KEYWORDS, 'hydration')
        self.assertIn('hydration', template)
        self.assertIn('detect_personal_data_intent', template)
        self.assertIn('unittest.TestCase', template)

    def test_no_data_method_test_template(self):
        """NO_DATA_METHOD test template includes data retrieval tests."""
        template = generate_test_template(GapType.NO_DATA_METHOD, 'sleep')
        self.assertIn('get_sleep_data', template)
        self.assertIn('PersonalDataService', template)
        self.assertIn('since_date', template)

    def test_unsupported_pattern_test_template(self):
        """UNSUPPORTED_QUERY_PATTERN test template includes pattern tests."""
        template = generate_test_template(
            GapType.UNSUPPORTED_QUERY_PATTERN, 'comparison queries'
        )
        self.assertIn('recognized', template)
        self.assertIn('results', template)
        self.assertIn('regression', template)

    def test_unknown_data_type_test_template(self):
        """UNKNOWN_DATA_TYPE test template includes comprehensive tests."""
        template = generate_test_template(GapType.UNKNOWN_DATA_TYPE, 'caffeine')
        self.assertIn('Caffeine', template)
        self.assertIn('Model', template)
        self.assertIn('detect_personal_data_intent', template)
        self.assertIn('PersonalDataService', template)


class TestProjectNameConstant(unittest.TestCase):
    """Tests for PROJECT_NAME constant."""

    def test_project_name_is_string(self):
        """PROJECT_NAME should be a string."""
        self.assertIsInstance(PROJECT_NAME, str)

    def test_project_name_value(self):
        """PROJECT_NAME should be 'Personal Assistant Growth'."""
        self.assertEqual(PROJECT_NAME, 'Personal Assistant Growth')


class TestApprovalRequirements(unittest.TestCase):
    """Tests for approval requirements based on severity."""

    def test_low_severity_no_approval(self):
        """LOW severity tasks should not require approval."""
        gap_result = {
            'gap_detected': True,
            'gap_type': GapType.MISSING_KEYWORDS,
            'original_query': 'test',
            'suggested_category': 'test',
        }
        task = generate_improvement_task(gap_result)
        self.assertFalse(task.requires_approval)

    def test_medium_severity_requires_approval(self):
        """MEDIUM severity tasks should require approval."""
        gap_result = {
            'gap_detected': True,
            'gap_type': GapType.NO_DATA_METHOD,
            'original_query': 'test',
            'suggested_category': 'test',
        }
        task = generate_improvement_task(gap_result)
        self.assertTrue(task.requires_approval)

    def test_high_severity_requires_approval(self):
        """HIGH severity tasks should require approval."""
        gap_result = {
            'gap_detected': True,
            'gap_type': GapType.UNKNOWN_DATA_TYPE,
            'original_query': 'test',
            'suggested_category': 'test',
        }
        task = generate_improvement_task(gap_result)
        self.assertTrue(task.requires_approval)


if __name__ == '__main__':
    unittest.main()
