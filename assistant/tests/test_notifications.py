"""
Tests for the Admin Notification Service.
"""

from django.core import mail
from django.test import TestCase, override_settings

from assistant.notifications import (
    ADMIN_EMAIL,
    AdminNotificationService,
    TaskInfo,
)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TestAdminNotificationService(TestCase):
    """Tests for AdminNotificationService."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AdminNotificationService()
        self.task = TaskInfo(
            task_id=42,
            title="Add new keyword detection",
            description="Add 'wellness' keyword to mood detection",
            severity="low",
        )

    def test_default_admin_email(self):
        """Test that default admin email is set correctly."""
        self.assertEqual(self.service.admin_email, ADMIN_EMAIL)

    def test_custom_admin_email(self):
        """Test that custom admin email can be set."""
        custom_email = "custom@example.com"
        service = AdminNotificationService(admin_email=custom_email)
        self.assertEqual(service.admin_email, custom_email)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TestNotifyTaskCreated(TestCase):
    """Tests for notify_task_created method."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AdminNotificationService()
        self.task = TaskInfo(
            task_id=42,
            title="Add new keyword detection",
            description="Add 'wellness' keyword to mood detection",
            severity="low",
        )

    def test_sends_email(self):
        """Test that task created notification sends email."""
        result = self.service.notify_task_created(self.task)

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

    def test_email_subject_contains_task_title(self):
        """Test that email subject contains task title."""
        self.service.notify_task_created(self.task)

        self.assertIn(self.task.title, mail.outbox[0].subject)
        self.assertIn("New Task Created", mail.outbox[0].subject)

    def test_email_sent_to_admin(self):
        """Test that email is sent to admin address."""
        self.service.notify_task_created(self.task)

        self.assertIn(self.service.admin_email, mail.outbox[0].to)

    def test_email_contains_task_id(self):
        """Test that email body contains task ID."""
        self.service.notify_task_created(self.task)

        self.assertIn(str(self.task.task_id), mail.outbox[0].body)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TestNotifyApprovalRequired(TestCase):
    """Tests for notify_approval_required method."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AdminNotificationService()
        self.task = TaskInfo(
            task_id=42,
            title="Modify data service",
            description="Add new query method",
            severity="high",
        )

    def test_sends_email(self):
        """Test that approval required notification sends email."""
        result = self.service.notify_approval_required(self.task)

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

    def test_email_subject_indicates_approval_needed(self):
        """Test that email subject indicates approval is needed."""
        self.service.notify_approval_required(self.task)

        self.assertIn("Approval Required", mail.outbox[0].subject)

    def test_includes_approval_url_when_provided(self):
        """Test that approval URL is included when provided."""
        approval_url = "https://example.com/approve/42"
        self.service.notify_approval_required(
            self.task,
            approval_url=approval_url
        )

        # URL should be in HTML version
        self.assertIn(approval_url, mail.outbox[0].alternatives[0][0])

    def test_includes_changes_preview(self):
        """Test that changes preview is included when provided."""
        changes = "def new_method():\n    pass"
        self.service.notify_approval_required(
            self.task,
            changes_preview=changes
        )

        self.assertIn(changes, mail.outbox[0].body)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TestNotifyTaskCompleted(TestCase):
    """Tests for notify_task_completed method."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AdminNotificationService()
        self.task = TaskInfo(
            task_id=42,
            title="Add new keyword detection",
            files_modified=["assistant/intent_detector.py"],
            git_diff="+    'wellness',",
        )

    def test_sends_email(self):
        """Test that task completed notification sends email."""
        result = self.service.notify_task_completed(self.task)

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

    def test_email_subject_indicates_completion(self):
        """Test that email subject indicates task completion."""
        self.service.notify_task_completed(self.task)

        self.assertIn("Task Completed", mail.outbox[0].subject)

    def test_includes_git_diff(self):
        """Test that git diff is included in email."""
        self.service.notify_task_completed(self.task)

        self.assertIn(self.task.git_diff, mail.outbox[0].body)

    def test_includes_files_modified(self):
        """Test that modified files are listed."""
        self.service.notify_task_completed(self.task)

        self.assertIn("intent_detector.py", mail.outbox[0].body)

    def test_includes_execution_time(self):
        """Test that execution time is included when provided."""
        self.service.notify_task_completed(self.task, execution_time=2.5)

        self.assertIn("2.5", mail.outbox[0].body)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TestNotifyTaskError(TestCase):
    """Tests for notify_task_error method."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AdminNotificationService()
        self.task = TaskInfo(
            task_id=42,
            title="Add new feature",
        )

    def test_sends_email(self):
        """Test that task error notification sends email."""
        result = self.service.notify_task_error(
            self.task,
            error_details="SyntaxError: invalid syntax"
        )

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

    def test_email_subject_indicates_error(self):
        """Test that email subject indicates error."""
        self.service.notify_task_error(
            self.task,
            error_details="Error occurred"
        )

        self.assertIn("Task Error", mail.outbox[0].subject)

    def test_includes_error_details(self):
        """Test that error details are included."""
        error = "SyntaxError: invalid syntax at line 42"
        self.service.notify_task_error(self.task, error_details=error)

        self.assertIn(error, mail.outbox[0].body)

    def test_includes_rollback_instructions(self):
        """Test that rollback instructions are included."""
        self.service.notify_task_error(
            self.task,
            error_details="Error",
            rollback_hash="abc123"
        )

        self.assertIn("git reset --hard abc123", mail.outbox[0].body)

    def test_indicates_rollback_status(self):
        """Test that rollback status is indicated."""
        self.service.notify_task_error(
            self.task,
            error_details="Error",
            rollback_successful=True
        )

        # Check HTML version for success message
        html_content = mail.outbox[0].alternatives[0][0]
        self.assertIn("rollback was successful", html_content.lower())


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TestNotifyAutoImprovement(TestCase):
    """Tests for notify_auto_improvement method."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AdminNotificationService()
        self.task = TaskInfo(
            task_id=42,
            title="Add keyword",
            severity="low",
            git_diff="+    'newkeyword',",
        )

    def test_sends_email(self):
        """Test that auto improvement notification sends email."""
        result = self.service.notify_auto_improvement(
            self.task,
            changes_made=["Added 'newkeyword' to mood detection"]
        )

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

    def test_email_subject_indicates_auto_improvement(self):
        """Test that email subject indicates auto improvement."""
        self.service.notify_auto_improvement(self.task, changes_made=[])

        self.assertIn("Auto-Improvement", mail.outbox[0].subject)

    def test_includes_changes_list(self):
        """Test that list of changes is included."""
        changes = [
            "Added 'wellness' keyword",
            "Updated test coverage",
        ]
        self.service.notify_auto_improvement(self.task, changes_made=changes)

        self.assertIn(changes[0], mail.outbox[0].body)
        self.assertIn(changes[1], mail.outbox[0].body)

    def test_includes_test_results(self):
        """Test that test results are included when provided."""
        test_results = "5 tests passed, 0 failed"
        self.service.notify_auto_improvement(
            self.task,
            changes_made=[],
            test_results=test_results
        )

        self.assertIn(test_results, mail.outbox[0].body)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TestNotifyDailySummary(TestCase):
    """Tests for notify_daily_summary method."""

    def setUp(self):
        """Set up test fixtures."""
        self.service = AdminNotificationService()

    def test_sends_email(self):
        """Test that daily summary notification sends email."""
        result = self.service.notify_daily_summary(
            tasks_created=5,
            tasks_completed=3,
            tasks_failed=1,
            tasks_pending_approval=1
        )

        self.assertTrue(result)
        self.assertEqual(len(mail.outbox), 1)

    def test_email_subject_indicates_summary(self):
        """Test that email subject indicates daily summary."""
        self.service.notify_daily_summary()

        self.assertIn("Daily Summary", mail.outbox[0].subject)

    def test_includes_all_counts(self):
        """Test that all task counts are included."""
        self.service.notify_daily_summary(
            tasks_created=5,
            tasks_completed=3,
            tasks_failed=1,
            tasks_pending_approval=2
        )

        body = mail.outbox[0].body
        self.assertIn("5", body)
        self.assertIn("3", body)
        self.assertIn("1", body)
        self.assertIn("2", body)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class TestTaskInfo(TestCase):
    """Tests for TaskInfo dataclass."""

    def test_default_values(self):
        """Test TaskInfo default values."""
        task = TaskInfo(task_id=1, title="Test")

        self.assertEqual(task.task_id, 1)
        self.assertEqual(task.title, "Test")
        self.assertEqual(task.description, "")
        self.assertEqual(task.severity, "medium")
        self.assertIsNone(task.files_modified)
        self.assertIsNone(task.git_diff)

    def test_all_fields(self):
        """Test TaskInfo with all fields."""
        task = TaskInfo(
            task_id=42,
            title="Full Task",
            description="Full description",
            severity="high",
            files_modified=["file1.py", "file2.py"],
            git_diff="+new code",
            error_message="An error",
            rollback_hash="abc123"
        )

        self.assertEqual(task.severity, "high")
        self.assertEqual(len(task.files_modified), 2)
        self.assertEqual(task.rollback_hash, "abc123")
