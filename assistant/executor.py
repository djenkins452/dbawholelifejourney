"""
Improvement Executor Service for orchestrating the full improvement lifecycle.

Owner: admin@wholelifejourney.com

This module provides the main orchestrator that executes improvement tasks
through the full lifecycle with safety guarantees: validation, git snapshot,
file modification, testing, and commit or rollback.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

from .file_modifier import SafeFileModifier, ModificationType
from .git_service import GitProtectionService
from .models import ImprovementTaskModel
from .notifications import AdminNotificationService, TaskInfo
from .test_runner import MockTestRunner


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of an improvement task execution."""
    success: bool
    message: str
    task_id: Optional[str] = None
    git_commit_before: Optional[str] = None
    git_commit_after: Optional[str] = None
    test_output: Optional[str] = None
    execution_time: Optional[float] = None


class ImprovementExecutor:
    """
    Main orchestrator that executes improvement tasks through the full lifecycle.

    Coordinates between GitProtectionService, SafeFileModifier, MockTestRunner,
    and AdminNotificationService to safely execute improvement tasks with
    rollback capabilities.
    """

    def __init__(
        self,
        git_service: Optional[GitProtectionService] = None,
        file_modifier: Optional[SafeFileModifier] = None,
        test_runner: Optional[MockTestRunner] = None,
        notification_service: Optional[AdminNotificationService] = None
    ):
        """
        Initialize the improvement executor.

        Args:
            git_service: GitProtectionService instance. Created if not provided.
            file_modifier: SafeFileModifier instance. Created if not provided.
            test_runner: MockTestRunner instance. Created if not provided.
            notification_service: AdminNotificationService instance. Created if not provided.
        """
        self.git_service = git_service or GitProtectionService()
        self.file_modifier = file_modifier or SafeFileModifier()
        self.test_runner = test_runner or MockTestRunner()
        self.notification_service = notification_service or AdminNotificationService()

    def _create_task_info(
        self,
        task: ImprovementTaskModel,
        error_message: Optional[str] = None
    ) -> TaskInfo:
        """
        Create a TaskInfo object from an ImprovementTaskModel.

        Args:
            task: The ImprovementTaskModel instance.
            error_message: Optional error message to include.

        Returns:
            TaskInfo object for notifications.
        """
        return TaskInfo(
            task_id=str(task.id),
            title=task.title,
            description=task.suggested_fix,
            severity=task.severity,
            error_message=error_message,
            rollback_hash=task.git_commit_before if error_message else None
        )

    def _validate_task_status(self, task: ImprovementTaskModel) -> ExecutionResult:
        """
        Validate that the task is in an executable status.

        Step 1: Task must be APPROVED, or NEW for low-severity tasks
        that don't require approval.

        Args:
            task: The ImprovementTaskModel to validate.

        Returns:
            ExecutionResult indicating if validation passed.
        """
        logger.info(f"Validating task {task.id} status: {task.status}")

        # Allow APPROVED status
        if task.status == ImprovementTaskModel.STATUS_APPROVED:
            logger.info(f"Task {task.id} is APPROVED, execution allowed")
            return ExecutionResult(
                success=True,
                message="Task is approved for execution",
                task_id=str(task.id)
            )

        # Allow NEW status for low-severity tasks that don't require approval
        if (task.status == ImprovementTaskModel.STATUS_NEW and
            task.severity == ImprovementTaskModel.SEVERITY_LOW and
            not task.requires_approval):
            logger.info(f"Task {task.id} is NEW low-severity, execution allowed")
            return ExecutionResult(
                success=True,
                message="Low-severity task is ready for execution",
                task_id=str(task.id)
            )

        logger.warning(f"Task {task.id} is not in executable status: {task.status}")
        return ExecutionResult(
            success=False,
            message=f"Task is not in executable status. Current status: {task.status}. "
                    f"Task must be APPROVED, or NEW for low-severity tasks without approval requirement.",
            task_id=str(task.id)
        )

    def execute_task(self, task: ImprovementTaskModel) -> ExecutionResult:
        """
        Execute an improvement task through the full lifecycle.

        Main entry point for task execution. Orchestrates:
        1. Status validation (APPROVED or NEW for low-severity)
        2. Status update to IN_PROGRESS
        3. Git snapshot creation
        4. File modification application
        5. Status update to TESTING
        6. Test execution
        7a/7b. On success: commit changes, update to COMPLETED, notify admin
        8a/8b. On failure: rollback, update to ERROR, notify admin

        The entire execution is wrapped in try/except with rollback on any exception.

        Args:
            task: The ImprovementTaskModel to execute.

        Returns:
            ExecutionResult with success status and details.
        """
        start_time = time.time()
        snapshot_hash = None

        logger.info(f"Starting execution of task {task.id}: {task.title}")

        try:
            # Step 1: Validate task status
            validation_result = self._validate_task_status(task)
            if not validation_result.success:
                logger.error(f"Task {task.id} validation failed: {validation_result.message}")
                return validation_result

            # Step 2: Update status to IN_PROGRESS
            logger.info(f"Transitioning task {task.id} to IN_PROGRESS")
            try:
                task.transition_status(ImprovementTaskModel.STATUS_IN_PROGRESS)
            except Exception as e:
                logger.error(f"Failed to transition task {task.id} to IN_PROGRESS: {e}")
                return ExecutionResult(
                    success=False,
                    message=f"Failed to update status to IN_PROGRESS: {e}",
                    task_id=str(task.id)
                )

            # Step 3: Create git snapshot
            logger.info(f"Creating git snapshot for task {task.id}")
            snapshot_result = self.git_service.create_snapshot(str(task.id))
            if not snapshot_result.success:
                logger.error(f"Git snapshot failed for task {task.id}: {snapshot_result.message}")
                self._handle_error(
                    task,
                    f"Git snapshot failed: {snapshot_result.message}",
                    None
                )
                return ExecutionResult(
                    success=False,
                    message=f"Git snapshot failed: {snapshot_result.message}",
                    task_id=str(task.id)
                )

            snapshot_hash = snapshot_result.commit_hash
            task.git_commit_before = snapshot_hash
            task.save(update_fields=['git_commit_before'])
            logger.info(f"Git snapshot created at {snapshot_hash}")

            # Step 4: Apply file modification
            logger.info(f"Applying file modification for task {task.id}")
            modification_result = self._apply_task_modification(task)
            if not modification_result.success:
                logger.error(f"File modification failed for task {task.id}: {modification_result.message}")
                self._handle_error(task, modification_result.message, snapshot_hash)
                return modification_result

            # Step 5: Update status to TESTING
            logger.info(f"Transitioning task {task.id} to TESTING")
            try:
                task.transition_status(ImprovementTaskModel.STATUS_TESTING)
            except Exception as e:
                logger.error(f"Failed to transition task {task.id} to TESTING: {e}")
                self._handle_error(task, f"Failed to update status to TESTING: {e}", snapshot_hash)
                return ExecutionResult(
                    success=False,
                    message=f"Failed to update status to TESTING: {e}",
                    task_id=str(task.id)
                )

            # Step 6: Run tests
            logger.info(f"Running tests for task {task.id}")
            test_result = self._run_task_tests(task)

            execution_time = time.time() - start_time

            if test_result.passed:
                # Step 7a: Commit changes
                logger.info(f"Tests passed for task {task.id}, committing changes")
                return self._handle_success(task, test_result, snapshot_hash, execution_time)
            else:
                # Step 8a: Rollback on test failure
                logger.warning(f"Tests failed for task {task.id}, rolling back")
                error_message = f"Tests failed: {'; '.join(test_result.errors) or 'Unknown error'}"
                return self._handle_error(task, error_message, snapshot_hash, test_result.output)

        except Exception as e:
            # Wrap entire execution in try/except with rollback on any exception
            execution_time = time.time() - start_time
            logger.exception(f"Unexpected error executing task {task.id}: {e}")
            error_message = f"Unexpected error during execution: {e}"
            return self._handle_error(task, error_message, snapshot_hash)

    def _apply_task_modification(self, task: ImprovementTaskModel) -> ExecutionResult:
        """
        Apply the task's code_template modification.

        Args:
            task: The ImprovementTaskModel with code_template to apply.

        Returns:
            ExecutionResult indicating success or failure.
        """
        if not task.code_template:
            logger.warning(f"Task {task.id} has no code_template to apply")
            return ExecutionResult(
                success=True,
                message="No code template to apply (empty template)",
                task_id=str(task.id)
            )

        # Parse the code_template to determine modification type and target
        # Expected format in code_template:
        # FILE: <filename>
        # TYPE: <append|insert_after|replace>
        # PATTERN: <pattern> (optional, for insert_after/replace)
        # CODE:
        # <actual code>

        lines = task.code_template.strip().split('\n')
        file_path = None
        mod_type = ModificationType.APPEND
        pattern = None
        code_lines = []
        in_code_section = False

        for line in lines:
            if line.startswith('FILE:'):
                file_path = line[5:].strip()
            elif line.startswith('TYPE:'):
                type_str = line[5:].strip().lower()
                if type_str == 'insert_after':
                    mod_type = ModificationType.INSERT_AFTER
                elif type_str == 'replace':
                    mod_type = ModificationType.REPLACE
                else:
                    mod_type = ModificationType.APPEND
            elif line.startswith('PATTERN:'):
                pattern = line[8:].strip()
            elif line.startswith('CODE:'):
                in_code_section = True
            elif in_code_section:
                code_lines.append(line)

        if not file_path:
            logger.error(f"Task {task.id} code_template missing FILE: directive")
            return ExecutionResult(
                success=False,
                message="Code template missing FILE: directive",
                task_id=str(task.id)
            )

        code = '\n'.join(code_lines)

        if not code.strip():
            logger.warning(f"Task {task.id} code_template has empty CODE section")
            return ExecutionResult(
                success=True,
                message="No code to apply (empty CODE section)",
                task_id=str(task.id)
            )

        logger.info(f"Applying {mod_type.value} modification to {file_path}")

        result = self.file_modifier.apply_modification(
            file_path=file_path,
            modification_type=mod_type,
            code=code,
            pattern=pattern
        )

        if result.success:
            logger.info(f"Modification applied successfully to {file_path}")
            return ExecutionResult(
                success=True,
                message=f"Modification applied to {file_path}",
                task_id=str(task.id)
            )
        else:
            logger.error(f"Modification failed for {file_path}: {result.message}")
            return ExecutionResult(
                success=False,
                message=result.message,
                task_id=str(task.id)
            )

    def _run_task_tests(self, task: ImprovementTaskModel):
        """
        Run the task's test_template.

        Args:
            task: The ImprovementTaskModel with test_template to run.

        Returns:
            TestResult from the test runner.
        """
        from .test_runner import TestResult

        if not task.test_template:
            logger.info(f"Task {task.id} has no test_template, returning pass")
            return TestResult(
                passed=True,
                output="No tests to run (empty test template)"
            )

        # Generate test file and run it
        test_file = self.test_runner.generate_test_file(
            test_name=f"task_{task.id}",
            test_code=task.test_template
        )

        logger.info(f"Running test file: {test_file}")
        result = self.test_runner.run_single_test(test_file)

        # Cleanup test file
        self.test_runner.cleanup_test_files([test_file])

        return result

    def _handle_success(
        self,
        task: ImprovementTaskModel,
        test_result,
        snapshot_hash: Optional[str],
        execution_time: float
    ) -> ExecutionResult:
        """
        Handle successful task execution.

        Step 7a: Commit changes
        Step 7b: Update status to COMPLETED, notify admin

        Args:
            task: The ImprovementTaskModel that succeeded.
            test_result: The test result object.
            snapshot_hash: Git commit hash from before changes.
            execution_time: Time taken for execution in seconds.

        Returns:
            ExecutionResult indicating success.
        """
        # Step 7a: Commit changes
        commit_result = self.git_service.commit_changes(
            task_id=str(task.id),
            task_title=task.title
        )

        if commit_result.success:
            task.git_commit_after = commit_result.commit_hash
            task.save(update_fields=['git_commit_after'])
            logger.info(f"Changes committed for task {task.id}: {commit_result.commit_hash}")
        else:
            # Log warning but don't fail - changes are applied even without commit
            logger.warning(f"Failed to commit changes for task {task.id}: {commit_result.message}")

        # Step 7b: Update status to COMPLETED
        try:
            task.transition_status(ImprovementTaskModel.STATUS_COMPLETED)
            logger.info(f"Task {task.id} marked as COMPLETED")
        except Exception as e:
            logger.error(f"Failed to transition task {task.id} to COMPLETED: {e}")

        # Notify admin
        task_info = self._create_task_info(task)
        task_info.git_diff = self.git_service.get_commit_diff(commit_result.commit_hash) if commit_result.commit_hash else None

        self.notification_service.notify_task_completed(
            task=task_info,
            execution_time=execution_time,
            summary=f"Task completed successfully. Tests passed."
        )
        logger.info(f"Admin notified of task {task.id} completion")

        return ExecutionResult(
            success=True,
            message="Task completed successfully",
            task_id=str(task.id),
            git_commit_before=snapshot_hash,
            git_commit_after=commit_result.commit_hash if commit_result.success else None,
            test_output=test_result.output,
            execution_time=execution_time
        )

    def _handle_error(
        self,
        task: ImprovementTaskModel,
        error_message: str,
        snapshot_hash: Optional[str],
        test_output: Optional[str] = None
    ) -> ExecutionResult:
        """
        Handle task execution failure.

        Step 8a: Rollback to snapshot
        Step 8b: Update status to ERROR, notify admin

        Args:
            task: The ImprovementTaskModel that failed.
            error_message: Description of what went wrong.
            snapshot_hash: Git commit hash to rollback to.
            test_output: Optional test output for context.

        Returns:
            ExecutionResult indicating failure.
        """
        rollback_successful = False

        # Step 8a: Rollback to snapshot
        if snapshot_hash:
            logger.info(f"Rolling back task {task.id} to {snapshot_hash}")
            rollback_result = self.git_service.rollback_to_commit(snapshot_hash)
            rollback_successful = rollback_result.success
            if rollback_successful:
                logger.info(f"Rollback successful for task {task.id}")
            else:
                logger.error(f"Rollback failed for task {task.id}: {rollback_result.message}")

        # Step 8b: Update status to ERROR
        try:
            task.transition_status(
                ImprovementTaskModel.STATUS_ERROR,
                error_message=error_message
            )
            logger.info(f"Task {task.id} marked as ERROR")
        except Exception as e:
            logger.error(f"Failed to transition task {task.id} to ERROR: {e}")

        # Notify admin
        task_info = self._create_task_info(task, error_message=error_message)

        self.notification_service.notify_task_error(
            task=task_info,
            error_details=error_message,
            rollback_successful=rollback_successful,
            rollback_hash=snapshot_hash
        )
        logger.info(f"Admin notified of task {task.id} error")

        return ExecutionResult(
            success=False,
            message=error_message,
            task_id=str(task.id),
            git_commit_before=snapshot_hash,
            test_output=test_output
        )
