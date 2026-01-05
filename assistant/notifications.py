"""
Admin Notification Service for Personal Assistant improvements.

This module provides email notification capabilities to keep the admin
informed of all improvement task activities including creation, completion,
errors, and approval requests.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone


# Admin email for all notifications
ADMIN_EMAIL = getattr(settings, 'ADMIN_EMAIL', 'admin@wholelifejourney.com')

# Default sender email
DEFAULT_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@wholelifejourney.com')


@dataclass
class TaskInfo:
    """Information about an improvement task for notifications."""
    task_id: int
    title: str
    description: str = ""
    severity: str = "medium"  # low, medium, high
    files_modified: Optional[List[str]] = None
    git_diff: Optional[str] = None
    error_message: Optional[str] = None
    rollback_hash: Optional[str] = None


class AdminNotificationService:
    """
    Service for sending admin notifications about improvement task activities.

    All notifications are sent to the configured ADMIN_EMAIL address.
    """

    def __init__(self, admin_email: Optional[str] = None):
        """
        Initialize the notification service.

        Args:
            admin_email: Optional override for admin email address.
        """
        self.admin_email = admin_email or ADMIN_EMAIL
        self.from_email = DEFAULT_FROM_EMAIL

    def _send_email(
        self,
        subject: str,
        template_name: str,
        context: Dict,
        plain_text_template: Optional[str] = None
    ) -> bool:
        """
        Send an email notification.

        Args:
            subject: Email subject line.
            template_name: Path to HTML template.
            context: Context dictionary for template rendering.
            plain_text_template: Optional path to plain text template.

        Returns:
            True if email was sent successfully, False otherwise.
        """
        try:
            # Add common context
            context['timestamp'] = timezone.now()
            context['admin_email'] = self.admin_email

            # Render HTML content
            html_content = render_to_string(template_name, context)

            # Render plain text content
            if plain_text_template:
                plain_content = render_to_string(plain_text_template, context)
            else:
                # Generate plain text from HTML template name
                plain_template = template_name.replace('.html', '.txt')
                try:
                    plain_content = render_to_string(plain_template, context)
                except Exception:
                    # Fallback to a simple text version
                    plain_content = self._generate_plain_text(context)

            # Send the email
            send_mail(
                subject=subject,
                message=plain_content,
                from_email=self.from_email,
                recipient_list=[self.admin_email],
                html_message=html_content,
                fail_silently=False
            )
            return True

        except Exception as e:
            # Log the error but don't raise - notifications shouldn't break the system
            print(f"Failed to send notification email: {e}")
            return False

    def _generate_plain_text(self, context: Dict) -> str:
        """Generate a simple plain text message from context."""
        lines = [
            "WLJ Personal Assistant Notification",
            "=" * 40,
            "",
        ]

        if 'task' in context:
            task = context['task']
            lines.append(f"Task ID: {task.task_id}")
            lines.append(f"Title: {task.title}")
            if task.description:
                lines.append(f"Description: {task.description}")

        if 'message' in context:
            lines.append("")
            lines.append(context['message'])

        lines.append("")
        lines.append(f"Timestamp: {context.get('timestamp', timezone.now())}")

        return "\n".join(lines)

    def notify_task_created(self, task: TaskInfo) -> bool:
        """
        Send notification when a new improvement task is created.

        Args:
            task: TaskInfo object with task details.

        Returns:
            True if notification was sent successfully.
        """
        subject = f"[WLJ Assistant] New Task Created: {task.title}"

        context = {
            'task': task,
            'message': 'A new improvement task has been created.',
            'action_required': False,
        }

        return self._send_email(
            subject=subject,
            template_name='assistant/emails/task_created.html',
            context=context
        )

    def notify_approval_required(
        self,
        task: TaskInfo,
        approval_url: Optional[str] = None,
        changes_preview: Optional[str] = None
    ) -> bool:
        """
        Send notification when a task requires admin approval before execution.

        Args:
            task: TaskInfo object with task details.
            approval_url: URL to approve/reject the task (Phase 4 feature).
            changes_preview: Preview of changes that will be made.

        Returns:
            True if notification was sent successfully.
        """
        subject = f"[WLJ Assistant] Approval Required: {task.title}"

        context = {
            'task': task,
            'message': 'This task requires your approval before execution.',
            'action_required': True,
            'approval_url': approval_url,
            'changes_preview': changes_preview,
        }

        return self._send_email(
            subject=subject,
            template_name='assistant/emails/approval_required.html',
            context=context
        )

    def notify_task_completed(
        self,
        task: TaskInfo,
        execution_time: Optional[float] = None,
        summary: Optional[str] = None
    ) -> bool:
        """
        Send notification when a task has been successfully completed.

        Args:
            task: TaskInfo object with task details (including git_diff).
            execution_time: Time taken to complete the task in seconds.
            summary: Summary of changes made.

        Returns:
            True if notification was sent successfully.
        """
        subject = f"[WLJ Assistant] Task Completed: {task.title}"

        context = {
            'task': task,
            'message': 'The improvement task has been completed successfully.',
            'action_required': False,
            'execution_time': execution_time,
            'summary': summary,
            'files_modified': task.files_modified or [],
            'git_diff': task.git_diff,
        }

        return self._send_email(
            subject=subject,
            template_name='assistant/emails/task_completed.html',
            context=context
        )

    def notify_task_error(
        self,
        task: TaskInfo,
        error_details: str,
        rollback_successful: bool = False,
        rollback_hash: Optional[str] = None
    ) -> bool:
        """
        Send notification when a task encounters an error.

        Args:
            task: TaskInfo object with task details.
            error_details: Detailed error message.
            rollback_successful: Whether automatic rollback was successful.
            rollback_hash: Git commit hash that was rolled back to.

        Returns:
            True if notification was sent successfully.
        """
        subject = f"[WLJ Assistant] Task Error: {task.title}"

        # Prepare rollback instructions
        rollback_instructions = None
        if rollback_hash:
            rollback_instructions = f"""
To manually rollback, run:
    git reset --hard {rollback_hash}

Or to view what changed:
    git diff {rollback_hash}..HEAD
"""

        context = {
            'task': task,
            'message': 'An error occurred during task execution.',
            'action_required': True,
            'error_details': error_details,
            'rollback_successful': rollback_successful,
            'rollback_hash': rollback_hash,
            'rollback_instructions': rollback_instructions,
        }

        return self._send_email(
            subject=subject,
            template_name='assistant/emails/task_error.html',
            context=context
        )

    def notify_auto_improvement(
        self,
        task: TaskInfo,
        changes_made: List[str],
        test_results: Optional[str] = None
    ) -> bool:
        """
        Send notification for low-severity autonomous improvements.

        These are changes that were made automatically without requiring
        approval due to their low-risk nature.

        Args:
            task: TaskInfo object with task details.
            changes_made: List of changes that were made.
            test_results: Results of any validation tests run.

        Returns:
            True if notification was sent successfully.
        """
        subject = f"[WLJ Assistant] Auto-Improvement Applied: {task.title}"

        context = {
            'task': task,
            'message': 'A low-severity improvement was automatically applied.',
            'action_required': False,
            'changes_made': changes_made,
            'test_results': test_results,
            'git_diff': task.git_diff,
        }

        return self._send_email(
            subject=subject,
            template_name='assistant/emails/auto_improvement.html',
            context=context
        )

    def notify_daily_summary(
        self,
        tasks_created: int = 0,
        tasks_completed: int = 0,
        tasks_failed: int = 0,
        tasks_pending_approval: int = 0
    ) -> bool:
        """
        Send a daily summary of improvement task activity.

        Args:
            tasks_created: Number of tasks created today.
            tasks_completed: Number of tasks completed today.
            tasks_failed: Number of tasks that failed today.
            tasks_pending_approval: Number of tasks awaiting approval.

        Returns:
            True if notification was sent successfully.
        """
        subject = "[WLJ Assistant] Daily Summary"

        context = {
            'message': 'Daily summary of Personal Assistant activity.',
            'action_required': tasks_pending_approval > 0,
            'tasks_created': tasks_created,
            'tasks_completed': tasks_completed,
            'tasks_failed': tasks_failed,
            'tasks_pending_approval': tasks_pending_approval,
            'total_activity': tasks_created + tasks_completed + tasks_failed,
        }

        return self._send_email(
            subject=subject,
            template_name='assistant/emails/daily_summary.html',
            context=context
        )
