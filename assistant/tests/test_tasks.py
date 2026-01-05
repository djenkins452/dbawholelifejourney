"""
Unit Tests for Background Task Functions.

Owner: admin@wholelifejourney.com

Tests for the assistant/tasks.py module covering:
- execute_improvement_task
- process_approved_tasks
- process_autonomous_tasks
- monitor_stuck_tasks
- get_queue_status
"""

import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from assistant.models import ImprovementTaskModel
from assistant.tasks import (
    MAX_RETRIES,
    STUCK_TASK_THRESHOLD_MINUTES,
    TASK_TIMEOUT_SECONDS,
    execute_improvement_task,
    get_queue_status,
    monitor_stuck_tasks,
    process_approved_tasks,
    process_autonomous_tasks,
)


class TestExecuteImprovementTask(TransactionTestCase):
    """Tests for execute_improvement_task function."""

    def setUp(self):
        """Set up test fixtures."""
        self.task = ImprovementTaskModel.objects.create(
            title="Test Task",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="Test query",
            suggested_fix="Test fix",
            status=ImprovementTaskModel.STATUS_APPROVED,
            requires_approval=False,
        )

    def test_execute_nonexistent_task(self):
        """Test executing a task that doesn't exist."""
        fake_id = str(uuid.uuid4())
        result = execute_improvement_task(fake_id)

        self.assertFalse(result['success'])
        self.assertIn('not found', result['message'])
        self.assertEqual(result['task_id'], fake_id)

    @patch('assistant.tasks.ImprovementExecutor')
    def test_execute_task_success(self, mock_executor_class):
        """Test successful task execution."""
        mock_executor = MagicMock()
        mock_executor.execute_task.return_value = MagicMock(
            success=True,
            message="Task completed successfully"
        )
        mock_executor_class.return_value = mock_executor

        result = execute_improvement_task(str(self.task.id))

        self.assertTrue(result['success'])
        self.assertEqual(result['task_id'], str(self.task.id))
        mock_executor.execute_task.assert_called_once()

    @patch('assistant.tasks.ImprovementExecutor')
    def test_execute_task_failure_suggests_retry(self, mock_executor_class):
        """Test that failed execution suggests retry when retries available."""
        mock_executor = MagicMock()
        mock_executor.execute_task.return_value = MagicMock(
            success=False,
            message="Execution failed"
        )
        mock_executor_class.return_value = mock_executor

        result = execute_improvement_task(str(self.task.id), retry_count=0)

        self.assertFalse(result['success'])
        self.assertTrue(result.get('should_retry', False))

    @patch('assistant.tasks.ImprovementExecutor')
    def test_execute_task_no_retry_after_max(self, mock_executor_class):
        """Test that no retry is suggested after max retries."""
        mock_executor = MagicMock()
        mock_executor.execute_task.return_value = MagicMock(
            success=False,
            message="Execution failed"
        )
        mock_executor_class.return_value = mock_executor

        result = execute_improvement_task(
            str(self.task.id),
            retry_count=MAX_RETRIES
        )

        self.assertFalse(result['success'])
        self.assertNotIn('should_retry', result)
        self.assertIn(str(MAX_RETRIES), result['message'])

    @patch('assistant.tasks.AutonomousExecutor')
    def test_execute_autonomous_task(self, mock_executor_class):
        """Test executing task with autonomous executor."""
        mock_executor = MagicMock()
        mock_executor.execute_task.return_value = MagicMock(
            success=True,
            message="Autonomous task completed"
        )
        mock_executor_class.return_value = mock_executor

        result = execute_improvement_task(str(self.task.id), autonomous=True)

        self.assertTrue(result['success'])
        mock_executor_class.assert_called_once()


class TestProcessApprovedTasks(TransactionTestCase):
    """Tests for process_approved_tasks function."""

    def test_no_approved_tasks(self):
        """Test when there are no approved tasks."""
        result = process_approved_tasks()

        self.assertEqual(result['processed'], 0)
        self.assertEqual(result['succeeded'], 0)
        self.assertEqual(result['failed'], 0)

    @patch('assistant.tasks.execute_improvement_task')
    def test_process_approved_tasks(self, mock_execute):
        """Test processing approved tasks."""
        # Create approved tasks
        task1 = ImprovementTaskModel.objects.create(
            title="Approved Task 1",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            original_query="Query 1",
            suggested_fix="Fix 1",
            status=ImprovementTaskModel.STATUS_APPROVED,
        )
        task2 = ImprovementTaskModel.objects.create(
            title="Approved Task 2",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            original_query="Query 2",
            suggested_fix="Fix 2",
            status=ImprovementTaskModel.STATUS_APPROVED,
        )

        mock_execute.side_effect = [
            {'success': True, 'task_id': str(task1.id)},
            {'success': False, 'task_id': str(task2.id), 'message': 'Error'},
        ]

        result = process_approved_tasks()

        self.assertEqual(result['processed'], 2)
        self.assertEqual(result['succeeded'], 1)
        self.assertEqual(result['failed'], 1)
        self.assertEqual(mock_execute.call_count, 2)


class TestProcessAutonomousTasks(TransactionTestCase):
    """Tests for process_autonomous_tasks function."""

    def test_no_autonomous_tasks(self):
        """Test when there are no autonomous tasks."""
        result = process_autonomous_tasks()

        self.assertEqual(result['processed'], 0)
        self.assertEqual(result['skipped'], 0)

    @patch('assistant.tasks.execute_improvement_task')
    @patch('assistant.tasks.AutonomousExecutor')
    def test_process_autonomous_tasks(self, mock_executor_class, mock_execute):
        """Test processing autonomous tasks."""
        # Create autonomous task
        task = ImprovementTaskModel.objects.create(
            title="Autonomous Task",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="Query",
            suggested_fix="Fix",
            status=ImprovementTaskModel.STATUS_NEW,
            requires_approval=False,
        )

        mock_executor = MagicMock()
        mock_executor.is_safe_for_autonomous.return_value = (True, "Safe")
        mock_executor_class.return_value = mock_executor

        mock_execute.return_value = {'success': True, 'task_id': str(task.id)}

        result = process_autonomous_tasks()

        self.assertEqual(result['processed'], 1)
        self.assertEqual(result['succeeded'], 1)
        self.assertEqual(result['skipped'], 0)

    @patch('assistant.tasks.AutonomousExecutor')
    def test_skip_unsafe_autonomous_tasks(self, mock_executor_class):
        """Test that unsafe tasks are skipped."""
        # Create autonomous task
        task = ImprovementTaskModel.objects.create(
            title="Unsafe Task",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="Query",
            suggested_fix="Fix",
            status=ImprovementTaskModel.STATUS_NEW,
            requires_approval=False,
        )

        mock_executor = MagicMock()
        mock_executor.is_safe_for_autonomous.return_value = (False, "Contains dangerous pattern")
        mock_executor_class.return_value = mock_executor

        result = process_autonomous_tasks()

        self.assertEqual(result['processed'], 1)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(result['succeeded'], 0)


class TestMonitorStuckTasks(TransactionTestCase):
    """Tests for monitor_stuck_tasks function."""

    def test_no_stuck_tasks(self):
        """Test when there are no stuck tasks."""
        result = monitor_stuck_tasks()

        self.assertEqual(result['stuck_count'], 0)
        self.assertFalse(result['notified'])

    @patch('assistant.tasks.AdminNotificationService')
    def test_detect_stuck_tasks(self, mock_notification_class):
        """Test detection of stuck tasks."""
        # Create a stuck task (in_progress for > 30 min)
        stuck_task = ImprovementTaskModel.objects.create(
            title="Stuck Task",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            original_query="Query",
            suggested_fix="Fix",
            status=ImprovementTaskModel.STATUS_IN_PROGRESS,
        )
        # Manually update updated_at to simulate stuck task
        old_time = timezone.now() - timedelta(minutes=STUCK_TASK_THRESHOLD_MINUTES + 5)
        ImprovementTaskModel.objects.filter(id=stuck_task.id).update(updated_at=old_time)

        mock_notification = MagicMock()
        mock_notification.notify_task_error.return_value = True
        mock_notification_class.return_value = mock_notification

        result = monitor_stuck_tasks()

        self.assertEqual(result['stuck_count'], 1)
        self.assertTrue(result['notified'])
        self.assertIn(str(stuck_task.id), result['tasks'])
        mock_notification.notify_task_error.assert_called_once()

    def test_recent_in_progress_not_stuck(self):
        """Test that recently started tasks are not flagged as stuck."""
        # Create a recently started task
        ImprovementTaskModel.objects.create(
            title="Recent Task",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            original_query="Query",
            suggested_fix="Fix",
            status=ImprovementTaskModel.STATUS_IN_PROGRESS,
        )

        result = monitor_stuck_tasks()

        self.assertEqual(result['stuck_count'], 0)


class TestGetQueueStatus(TransactionTestCase):
    """Tests for get_queue_status function."""

    def test_empty_queue(self):
        """Test queue status with no tasks."""
        status = get_queue_status()

        self.assertEqual(status['pending_approval'], 0)
        self.assertEqual(status['approved'], 0)
        self.assertEqual(status['autonomous'], 0)
        self.assertEqual(status['in_progress'], 0)
        self.assertEqual(status['stuck'], 0)
        self.assertEqual(status['completed_today'], 0)
        self.assertEqual(status['errors_today'], 0)

    def test_queue_status_counts(self):
        """Test queue status with various task states."""
        # Create tasks in various states
        ImprovementTaskModel.objects.create(
            title="Pending Task",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            original_query="Query",
            suggested_fix="Fix",
            status=ImprovementTaskModel.STATUS_PENDING_APPROVAL,
        )
        ImprovementTaskModel.objects.create(
            title="Approved Task",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            original_query="Query",
            suggested_fix="Fix",
            status=ImprovementTaskModel.STATUS_APPROVED,
        )
        ImprovementTaskModel.objects.create(
            title="Autonomous Task",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="Query",
            suggested_fix="Fix",
            status=ImprovementTaskModel.STATUS_NEW,
            requires_approval=False,
        )
        ImprovementTaskModel.objects.create(
            title="In Progress Task",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            original_query="Query",
            suggested_fix="Fix",
            status=ImprovementTaskModel.STATUS_IN_PROGRESS,
        )
        completed = ImprovementTaskModel.objects.create(
            title="Completed Task",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_LOW,
            original_query="Query",
            suggested_fix="Fix",
            status=ImprovementTaskModel.STATUS_COMPLETED,
            completed_at=timezone.now(),
        )
        error = ImprovementTaskModel.objects.create(
            title="Error Task",
            gap_type=ImprovementTaskModel.GAP_TYPE_MISSING_KEYWORDS,
            severity=ImprovementTaskModel.SEVERITY_MEDIUM,
            original_query="Query",
            suggested_fix="Fix",
            status=ImprovementTaskModel.STATUS_ERROR,
        )

        status = get_queue_status()

        self.assertEqual(status['pending_approval'], 1)
        self.assertEqual(status['approved'], 1)
        self.assertEqual(status['autonomous'], 1)
        self.assertEqual(status['in_progress'], 1)
        self.assertEqual(status['stuck'], 0)
        self.assertEqual(status['completed_today'], 1)
        self.assertEqual(status['errors_today'], 1)


class TestTaskTimeoutSettings(TestCase):
    """Tests for task timeout and retry settings."""

    def test_timeout_constant(self):
        """Test that timeout is set to 10 minutes."""
        self.assertEqual(TASK_TIMEOUT_SECONDS, 600)

    def test_max_retries_constant(self):
        """Test that max retries is set to 2."""
        self.assertEqual(MAX_RETRIES, 2)

    def test_stuck_threshold_constant(self):
        """Test that stuck threshold is set to 30 minutes."""
        self.assertEqual(STUCK_TASK_THRESHOLD_MINUTES, 30)
