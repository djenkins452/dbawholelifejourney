"""
Tests for the Mock Test Runner.
"""

import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch

from assistant.test_runner import MockTestRunner, TestResult


class TestTestResult(TestCase):
    """Tests for TestResult dataclass."""

    def test_default_values(self):
        """Test TestResult default values."""
        result = TestResult(passed=True, output="test output")

        self.assertTrue(result.passed)
        self.assertEqual(result.output, "test output")
        self.assertEqual(result.errors, [])
        self.assertEqual(result.duration, 0.0)
        self.assertIsNone(result.test_file)

    def test_all_fields(self):
        """Test TestResult with all fields."""
        result = TestResult(
            passed=False,
            output="test output",
            errors=["error1", "error2"],
            duration=1.5,
            test_file="/path/to/test.py"
        )

        self.assertFalse(result.passed)
        self.assertEqual(len(result.errors), 2)
        self.assertEqual(result.duration, 1.5)
        self.assertEqual(result.test_file, "/path/to/test.py")


class TestMockTestRunnerInit(TestCase):
    """Tests for MockTestRunner initialization."""

    def test_default_initialization(self):
        """Test default initialization creates test directory."""
        runner = MockTestRunner()

        self.assertTrue(runner.test_dir.exists())
        self.assertTrue(runner.test_dir.name == 'auto_generated')

    def test_custom_base_path(self):
        """Test initialization with custom base path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = MockTestRunner(base_path=temp_dir)

            expected_test_dir = Path(temp_dir) / 'assistant' / 'tests' / 'auto_generated'
            self.assertEqual(runner.test_dir, expected_test_dir)
            self.assertTrue(runner.test_dir.exists())


class TestGenerateTestFile(TestCase):
    """Tests for generate_test_file method."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.runner = MockTestRunner(base_path=self.temp_dir)

    def test_generates_file(self):
        """Test that generate_test_file creates a file."""
        test_code = '''
class TestExample(unittest.TestCase):
    def test_something(self):
        self.assertTrue(True)
'''
        filepath = self.runner.generate_test_file("example", test_code)

        self.assertTrue(Path(filepath).exists())
        self.assertIn("test_example_", filepath)

    def test_includes_default_imports(self):
        """Test that generated file includes default imports."""
        test_code = "# test code"
        filepath = self.runner.generate_test_file("imports", test_code)

        content = Path(filepath).read_text()
        self.assertIn("import unittest", content)
        self.assertIn("from unittest.mock import", content)

    def test_includes_custom_imports(self):
        """Test that generated file includes custom imports."""
        test_code = "# test code"
        custom_imports = ["import json", "from pathlib import Path"]

        filepath = self.runner.generate_test_file(
            "custom_imports",
            test_code,
            imports=custom_imports
        )

        content = Path(filepath).read_text()
        self.assertIn("import json", content)
        self.assertIn("from pathlib import Path", content)

    def test_unique_filenames(self):
        """Test that multiple calls generate unique filenames."""
        filepaths = []
        for _ in range(3):
            filepath = self.runner.generate_test_file("unique", "# test")
            filepaths.append(filepath)

        # All paths should be unique
        self.assertEqual(len(set(filepaths)), 3)

    def tearDown(self):
        """Clean up generated files."""
        self.runner.cleanup_test_files()


class TestParseTestResults(TestCase):
    """Tests for parse_test_results method."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = MockTestRunner()

    def test_parse_failed_tests(self):
        """Test parsing failed test output."""
        output = """
FAILED test_example.py::TestClass::test_method - AssertionError
FAILED test_other.py::test_func - ValueError
"""
        errors = self.runner.parse_test_results(output)

        self.assertEqual(len(errors), 2)
        self.assertTrue(any("test_example.py" in e for e in errors))

    def test_parse_assertion_errors(self):
        """Test parsing assertion errors."""
        output = "AssertionError: expected 1 but got 2"
        errors = self.runner.parse_test_results(output)

        self.assertTrue(any("Assertion error" in e for e in errors))

    def test_parse_import_errors(self):
        """Test parsing import errors."""
        output = "ImportError: No module named 'nonexistent'"
        errors = self.runner.parse_test_results(output)

        self.assertTrue(any("ImportError" in e for e in errors))

    def test_parse_syntax_errors(self):
        """Test parsing syntax errors."""
        output = "SyntaxError: invalid syntax"
        errors = self.runner.parse_test_results(output)

        self.assertTrue(any("Syntax error" in e for e in errors))

    def test_clean_output_returns_empty(self):
        """Test that clean output returns no errors."""
        output = "test_example.py::test_method PASSED"
        errors = self.runner.parse_test_results(output)

        self.assertEqual(errors, [])


class TestRunSingleTest(TestCase):
    """Tests for run_single_test method."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.runner = MockTestRunner(base_path=self.temp_dir)

    @patch('assistant.test_runner.subprocess.run')
    def test_successful_test(self, mock_run):
        """Test running a successful test."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="1 passed",
            stderr=""
        )

        result = self.runner.run_single_test("/path/to/test.py")

        self.assertTrue(result.passed)
        self.assertIn("1 passed", result.output)
        self.assertEqual(result.test_file, "/path/to/test.py")

    @patch('assistant.test_runner.subprocess.run')
    def test_failed_test(self, mock_run):
        """Test running a failed test."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="FAILED test.py::test_method",
            stderr=""
        )

        result = self.runner.run_single_test("/path/to/test.py")

        self.assertFalse(result.passed)

    @patch('assistant.test_runner.subprocess.run')
    def test_timeout_handling(self, mock_run):
        """Test handling of test timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=30)

        result = self.runner.run_single_test("/path/to/test.py", timeout=30)

        self.assertFalse(result.passed)
        self.assertIn("timed out", result.errors[0].lower())

    @patch('assistant.test_runner.subprocess.run')
    def test_exception_handling(self, mock_run):
        """Test handling of unexpected exceptions."""
        mock_run.side_effect = Exception("Unexpected error")

        result = self.runner.run_single_test("/path/to/test.py")

        self.assertFalse(result.passed)
        self.assertTrue(any("failed" in e.lower() for e in result.errors))

    @patch('assistant.test_runner.subprocess.run')
    def test_records_duration(self, mock_run):
        """Test that duration is recorded."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="passed",
            stderr=""
        )

        result = self.runner.run_single_test("/path/to/test.py")

        self.assertGreaterEqual(result.duration, 0)


class TestCleanupTestFiles(TestCase):
    """Tests for cleanup_test_files method."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.runner = MockTestRunner(base_path=self.temp_dir)

    def test_cleanup_specific_files(self):
        """Test cleaning up specific files."""
        # Generate some test files
        filepath1 = self.runner.generate_test_file("cleanup1", "# test")
        filepath2 = self.runner.generate_test_file("cleanup2", "# test")

        # Clean up only the first one
        removed = self.runner.cleanup_test_files([filepath1])

        self.assertEqual(removed, 1)
        self.assertFalse(Path(filepath1).exists())
        self.assertTrue(Path(filepath2).exists())

    def test_cleanup_all_files(self):
        """Test cleaning up all auto-generated files."""
        # Generate multiple test files
        for i in range(3):
            self.runner.generate_test_file(f"cleanup_all_{i}", "# test")

        # Clean up all
        removed = self.runner.cleanup_test_files()

        self.assertEqual(removed, 3)

    def test_preserves_init_file(self):
        """Test that cleanup preserves __init__.py."""
        init_file = self.runner.test_dir / '__init__.py'
        init_file.write_text("# preserved")

        self.runner.generate_test_file("to_remove", "# test")
        self.runner.cleanup_test_files()

        self.assertTrue(init_file.exists())


class TestValidateIntentDetection(TestCase):
    """Tests for validate_intent_detection method."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = MockTestRunner()

    @patch.object(MockTestRunner, 'run_single_test')
    @patch.object(MockTestRunner, 'generate_test_file')
    def test_generates_and_runs_test(self, mock_generate, mock_run):
        """Test that validate_intent_detection generates and runs a test."""
        mock_generate.return_value = "/path/to/test.py"
        mock_run.return_value = TestResult(passed=True, output="passed")

        result = self.runner.validate_intent_detection(
            keyword="testword",
            expected_data_type="weight"
        )

        mock_generate.assert_called_once()
        mock_run.assert_called_once_with("/path/to/test.py")
        self.assertTrue(result.passed)

    @patch.object(MockTestRunner, 'run_single_test')
    @patch.object(MockTestRunner, 'generate_test_file')
    def test_cleans_up_after_run(self, mock_generate, mock_run):
        """Test that test files are cleaned up after run."""
        mock_generate.return_value = "/path/to/test.py"
        mock_run.return_value = TestResult(passed=True, output="passed")

        with patch.object(self.runner, 'cleanup_test_files') as mock_cleanup:
            self.runner.validate_intent_detection(
                keyword="testword",
                expected_data_type="weight"
            )
            mock_cleanup.assert_called_once_with(["/path/to/test.py"])


class TestValidateDataQuery(TestCase):
    """Tests for validate_data_query method."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = MockTestRunner()

    @patch.object(MockTestRunner, 'run_single_test')
    @patch.object(MockTestRunner, 'generate_test_file')
    def test_generates_and_runs_test(self, mock_generate, mock_run):
        """Test that validate_data_query generates and runs a test."""
        mock_generate.return_value = "/path/to/test.py"
        mock_run.return_value = TestResult(passed=True, output="passed")

        result = self.runner.validate_data_query(
            method_name="get_weight_data",
            expected_keys=["total_entries", "average"]
        )

        mock_generate.assert_called_once()
        mock_run.assert_called_once_with("/path/to/test.py")
        self.assertTrue(result.passed)


class TestRunValidationSuite(TestCase):
    """Tests for run_validation_suite method."""

    def setUp(self):
        """Set up test fixtures."""
        self.runner = MockTestRunner()

    @patch.object(MockTestRunner, 'validate_intent_detection')
    @patch.object(MockTestRunner, 'validate_data_query')
    def test_runs_intent_tests(self, mock_data, mock_intent):
        """Test running intent detection tests in suite."""
        mock_intent.return_value = TestResult(passed=True, output="passed")

        results = self.runner.run_validation_suite(
            intent_tests=[
                {"keyword": "test", "expected_data_type": "weight"}
            ]
        )

        mock_intent.assert_called_once()
        self.assertIn("intent_weight_test", results)

    @patch.object(MockTestRunner, 'validate_intent_detection')
    @patch.object(MockTestRunner, 'validate_data_query')
    def test_runs_data_query_tests(self, mock_data, mock_intent):
        """Test running data query tests in suite."""
        mock_data.return_value = TestResult(passed=True, output="passed")

        results = self.runner.run_validation_suite(
            data_query_tests=[
                {"method_name": "get_weight_data", "expected_keys": ["total"]}
            ]
        )

        mock_data.assert_called_once()
        self.assertIn("data_query_get_weight_data", results)

    @patch.object(MockTestRunner, 'validate_intent_detection')
    @patch.object(MockTestRunner, 'validate_data_query')
    def test_runs_mixed_suite(self, mock_data, mock_intent):
        """Test running mixed validation suite."""
        mock_intent.return_value = TestResult(passed=True, output="passed")
        mock_data.return_value = TestResult(passed=True, output="passed")

        results = self.runner.run_validation_suite(
            intent_tests=[
                {"keyword": "test", "expected_data_type": "weight"}
            ],
            data_query_tests=[
                {"method_name": "get_weight_data", "expected_keys": ["total"]}
            ]
        )

        self.assertEqual(len(results), 2)
