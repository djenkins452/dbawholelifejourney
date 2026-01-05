"""
Tests for the ImprovementExecutor service.

Tests the full improvement task lifecycle with mocked dependencies.
"""

import uuid
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import TestCase

from assistant.executor import ImprovementExecutor, ExecutionResult
from assistant.file_modifier import ModificationResult
from assistant.git_service import GitResult
from assistant.models import ImprovementTaskModel
from assistant.test_runner import TestResult


class TestImprovementExecutorValidation(TestCase):
    """Tests for task status validation."""

    def setUp(self):
        """Set up test fixtures."""
        self.executor = ImprovementExecutor(
            git_service=MagicMock(),
            file_modifier=MagicMock(),
            test_runner=MagicMock(),
            notification_service=MagicMock()
        )

    def test_validate_approved_task_succeeds(self):
        """Test that APPROVED tasks pass validation."""
        task = MagicMock(spec=ImprovementTaskModel)
        task.id = uuid.uuid4()
        task.status = ImprovementTaskModel.STATUS_APPROVED

        result = self.executor._validate_task_status(task)

        self.assertTrue(result.success)
        self.assertIn("approved", result.message.lower())

    def test_validate_new_low_severity_task_succeeds(self):
        """Test that NEW low-severity tasks without approval requirement pass."""
        task = MagicMock(spec=ImprovementTaskModel)
        task.id = uuid.uuid4()
        task.status = ImprovementTaskModel.STATUS_NEW
        task.severity = ImprovementTaskModel.SEVERITY_LOW
        task.requires_approval = False

        result = self.executor._validate_task_status(task)

        self.assertTrue(result.success)

    def test_validate_new_high_severity_task_fails(self):
        """Test that NEW high-severity tasks fail validation."""
        task = MagicMock(spec=ImprovementTaskModel)
        task.id = uuid.uuid4()
        task.status = ImprovementTaskModel.STATUS_NEW
        task.severity = ImprovementTaskModel.SEVERITY_HIGH
        task.requires_approval = True

        result = self.executor._validate_task_status(task)

        self.assertFalse(result.success)

    def test_validate_pending_approval_fails(self):
        """Test that PENDING_APPROVAL tasks fail validation."""
        task = MagicMock(spec=ImprovementTaskModel)
        task.id = uuid.uuid4()
        task.status = ImprovementTaskModel.STATUS_PENDING_APPROVAL

        result = self.executor._validate_task_status(task)

        self.assertFalse(result.success)
        self.assertIn("not in executable status", result.message)


class TestImprovementExecutorExecution(TestCase):
    """Tests for task execution lifecycle."""

    def setUp(self):
        """Set up test fixtures with mocked services."""
        self.mock_git_service = MagicMock()
        self.mock_file_modifier = MagicMock()
        self.mock_test_runner = MagicMock()
        self.mock_notification_service = MagicMock()

        self.executor = ImprovementExecutor(
            git_service=self.mock_git_service,
            file_modifier=self.mock_file_modifier,
            test_runner=self.mock_test_runner,
            notification_service=self.mock_notification_service
        )

        # Create a mock task
        self.task = MagicMock(spec=ImprovementTaskModel)
        self.task.id = uuid.uuid4()
        self.task.title = "Test Task"
        self.task.status = ImprovementTaskModel.STATUS_APPROVED
        self.task.severity = ImprovementTaskModel.SEVERITY_LOW
        self.task.suggested_fix = "Fix the issue"
        self.task.code_template = ""
        self.task.test_template = ""
        self.task.git_commit_before = None
        self.task.git_commit_after = None

    def test_execute_task_success_flow(self):
        """Test successful task execution from start to finish."""
        # Configure mocks
        self.mock_git_service.create_snapshot.return_value = GitResult(
            success=True,
            message="Snapshot created",
            commit_hash="abc123"
        )
        self.mock_git_service.commit_changes.return_value = GitResult(
            success=True,
            message="Changes committed",
            commit_hash="def456"
        )
        self.mock_git_service.get_commit_diff.return_value = "diff output"

        self.mock_test_runner.generate_test_file.return_value = "/tmp/test.py"
        self.mock_test_runner.run_single_test.return_value = TestResult(
            passed=True,
            output="All tests passed"
        )

        # Execute
        result = self.executor.execute_task(self.task)

        # Verify success
        self.assertTrue(result.success)
        self.assertEqual(result.git_commit_before, "abc123")
        self.assertEqual(result.git_commit_after, "def456")

        # Verify status transitions
        self.task.transition_status.assert_any_call(ImprovementTaskModel.STATUS_IN_PROGRESS)
        self.task.transition_status.assert_any_call(ImprovementTaskModel.STATUS_TESTING)
        self.task.transition_status.assert_any_call(ImprovementTaskModel.STATUS_COMPLETED)

        # Verify notification
        self.mock_notification_service.notify_task_completed.assert_called_once()

    def test_execute_task_git_snapshot_failure(self):
        """Test that git snapshot failure triggers error handling."""
        self.mock_git_service.create_snapshot.return_value = GitResult(
            success=False,
            message="Working directory dirty"
        )

        result = self.executor.execute_task(self.task)

        self.assertFalse(result.success)
        self.assertIn("Git snapshot failed", result.message)
        self.mock_notification_service.notify_task_error.assert_called_once()

    def test_execute_task_test_failure_triggers_rollback(self):
        """Test that test failure triggers rollback."""
        # Configure successful setup
        self.mock_git_service.create_snapshot.return_value = GitResult(
            success=True,
            message="Snapshot created",
            commit_hash="abc123"
        )
        self.mock_git_service.rollback_to_commit.return_value = GitResult(
            success=True,
            message="Rolled back"
        )

        # Configure test failure
        self.mock_test_runner.generate_test_file.return_value = "/tmp/test.py"
        self.mock_test_runner.run_single_test.return_value = TestResult(
            passed=False,
            output="Test failed",
            errors=["AssertionError: Expected 1, got 2"]
        )

        result = self.executor.execute_task(self.task)

        # Verify failure and rollback
        self.assertFalse(result.success)
        self.mock_git_service.rollback_to_commit.assert_called_once_with("abc123")
        self.task.transition_status.assert_any_call(
            ImprovementTaskModel.STATUS_ERROR,
            error_message="Tests failed: AssertionError: Expected 1, got 2"
        )
        self.mock_notification_service.notify_task_error.assert_called_once()

    def test_execute_task_exception_triggers_rollback(self):
        """Test that unexpected exceptions trigger rollback."""
        self.mock_git_service.create_snapshot.return_value = GitResult(
            success=True,
            message="Snapshot created",
            commit_hash="abc123"
        )
        self.mock_git_service.rollback_to_commit.return_value = GitResult(
            success=True,
            message="Rolled back"
        )

        # Configure file modifier to raise exception
        self.task.code_template = "FILE: test.py\nTYPE: append\nCODE:\nprint('test')"
        self.mock_file_modifier.apply_modification.side_effect = Exception("Unexpected error")

        result = self.executor.execute_task(self.task)

        self.assertFalse(result.success)
        self.mock_git_service.rollback_to_commit.assert_called_once_with("abc123")


class TestImprovementExecutorModification(TestCase):
    """Tests for file modification parsing and application."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_git_service = MagicMock()
        self.mock_file_modifier = MagicMock()
        self.mock_test_runner = MagicMock()
        self.mock_notification_service = MagicMock()

        self.executor = ImprovementExecutor(
            git_service=self.mock_git_service,
            file_modifier=self.mock_file_modifier,
            test_runner=self.mock_test_runner,
            notification_service=self.mock_notification_service
        )

    def test_apply_modification_parses_template_correctly(self):
        """Test that code_template is parsed correctly."""
        task = MagicMock(spec=ImprovementTaskModel)
        task.id = uuid.uuid4()
        task.code_template = """FILE: intent_detector.py
TYPE: insert_after
PATTERN: DATA_TYPE_KEYWORDS = \\{
CODE:
    'new_keyword': 'new_type',"""

        self.mock_file_modifier.apply_modification.return_value = ModificationResult(
            success=True,
            message="Applied"
        )

        result = self.executor._apply_task_modification(task)

        self.assertTrue(result.success)
        self.mock_file_modifier.apply_modification.assert_called_once()

        # Verify the arguments
        call_args = self.mock_file_modifier.apply_modification.call_args
        self.assertEqual(call_args.kwargs['file_path'], 'intent_detector.py')
        self.assertIn('new_keyword', call_args.kwargs['code'])

    def test_apply_modification_handles_empty_template(self):
        """Test that empty code_template is handled gracefully."""
        task = MagicMock(spec=ImprovementTaskModel)
        task.id = uuid.uuid4()
        task.code_template = ""

        result = self.executor._apply_task_modification(task)

        self.assertTrue(result.success)
        self.mock_file_modifier.apply_modification.assert_not_called()

    def test_apply_modification_fails_without_file_directive(self):
        """Test that missing FILE directive fails."""
        task = MagicMock(spec=ImprovementTaskModel)
        task.id = uuid.uuid4()
        task.code_template = """TYPE: append
CODE:
print('test')"""

        result = self.executor._apply_task_modification(task)

        self.assertFalse(result.success)
        self.assertIn("FILE:", result.message)


class TestImprovementExecutorNotifications(TestCase):
    """Tests for notification handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_git_service = MagicMock()
        self.mock_file_modifier = MagicMock()
        self.mock_test_runner = MagicMock()
        self.mock_notification_service = MagicMock()

        self.executor = ImprovementExecutor(
            git_service=self.mock_git_service,
            file_modifier=self.mock_file_modifier,
            test_runner=self.mock_test_runner,
            notification_service=self.mock_notification_service
        )

    def test_success_notification_includes_execution_time(self):
        """Test that success notification includes execution time."""
        task = MagicMock(spec=ImprovementTaskModel)
        task.id = uuid.uuid4()
        task.title = "Test Task"
        task.severity = ImprovementTaskModel.SEVERITY_LOW
        task.suggested_fix = "Fix"

        test_result = TestResult(passed=True, output="OK")

        self.mock_git_service.commit_changes.return_value = GitResult(
            success=True,
            message="Committed",
            commit_hash="abc123"
        )
        self.mock_git_service.get_commit_diff.return_value = "diff"

        self.executor._handle_success(task, test_result, "before123", 5.5)

        call_args = self.mock_notification_service.notify_task_completed.call_args
        self.assertEqual(call_args.kwargs['execution_time'], 5.5)

    def test_error_notification_includes_rollback_status(self):
        """Test that error notification includes rollback status."""
        task = MagicMock(spec=ImprovementTaskModel)
        task.id = uuid.uuid4()
        task.title = "Test Task"
        task.severity = ImprovementTaskModel.SEVERITY_LOW
        task.suggested_fix = "Fix"

        self.mock_git_service.rollback_to_commit.return_value = GitResult(
            success=True,
            message="Rolled back"
        )

        self.executor._handle_error(task, "Something went wrong", "abc123")

        call_args = self.mock_notification_service.notify_task_error.call_args
        self.assertTrue(call_args.kwargs['rollback_successful'])
        self.assertEqual(call_args.kwargs['rollback_hash'], "abc123")


class TestImprovementExecutorIntegration(TestCase):
    """Integration tests with real model instances."""

    def test_create_task_info_from_model(self):
        """Test TaskInfo creation from ImprovementTaskModel."""
        executor = ImprovementExecutor(
            git_service=MagicMock(),
            file_modifier=MagicMock(),
            test_runner=MagicMock(),
            notification_service=MagicMock()
        )

        task = MagicMock(spec=ImprovementTaskModel)
        task.id = uuid.uuid4()
        task.title = "Add keyword support"
        task.suggested_fix = "Add 'exercise' keyword"
        task.severity = ImprovementTaskModel.SEVERITY_LOW
        task.git_commit_before = "abc123"

        task_info = executor._create_task_info(task, error_message="Test error")

        self.assertEqual(task_info.title, "Add keyword support")
        self.assertEqual(task_info.description, "Add 'exercise' keyword")
        self.assertEqual(task_info.severity, ImprovementTaskModel.SEVERITY_LOW)
        self.assertEqual(task_info.error_message, "Test error")
        self.assertEqual(task_info.rollback_hash, "abc123")
