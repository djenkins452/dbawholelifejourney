# ==============================================================================
# File: bug_report_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Detects bug reports ("Fix this:", "bug:", etc.) and sends
#              notifications to admin for review
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-17
# ==============================================================================
"""
Bug Report Detection Service

Detects when users report bugs or issues in the AI Assistant using phrases like
"Fix this:" or "bug:". When detected:
1. Creates an AdminTask in the "Bug Reports" project with status 'backlog'
2. Sends an email notification to admin for review
3. Returns acknowledgment message for the user

Usage:
    from apps.ai.bug_report_service import bug_report_service

    # In the assistant chat flow:
    result = bug_report_service.check_and_notify(
        user=user,
        message="Fix this: the button doesn't work",
        conversation_context="Recent chat messages..."
    )
    if result:
        # result contains acknowledgment message
"""

import logging
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


# Admin email for notifications
ADMIN_EMAIL = getattr(settings, 'ADMIN_EMAIL', 'admin@wholelifejourney.com')
DEFAULT_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@wholelifejourney.com')


# Patterns that indicate a bug report
BUG_REPORT_PATTERNS = [
    # "Fix this:" pattern - primary trigger
    r'\bfix\s+this\s*[:\-]',

    # "Bug:" pattern
    r'\bbug\s*[:\-]',

    # "Error:" pattern
    r'\berror\s*[:\-]',

    # "Issue:" pattern
    r'\bissue\s*[:\-]',

    # "Problem:" pattern
    r'\bproblem\s*[:\-]',

    # "Broken:" pattern
    r'\bbroken\s*[:\-]',

    # "Not working" pattern
    r'\bnot\s+working\s*[:\-]',

    # "Something is wrong" pattern
    r'\bsomething\s+is\s+wrong\s*[:\-]?',
]

# Compile patterns for efficiency
COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in BUG_REPORT_PATTERNS]


@dataclass
class BugReportInfo:
    """Information about a detected bug report."""
    user_email: str
    user_name: str
    user_id: int
    message: str
    detected_pattern: str
    timestamp: str
    conversation_context: Optional[str] = None
    image_data: Optional[str] = None  # Base64 image if attached
    image_mime_type: Optional[str] = None
    task_id: Optional[int] = None
    task_url: Optional[str] = None


class BugReportService:
    """
    Service for detecting and notifying admin about user bug reports.

    When users report bugs or issues using "Fix this:" or similar phrases,
    this service:
    1. Creates an AdminTask in the "Bug Reports" project (status: backlog)
    2. Sends an email notification to admin for review
    """

    # Project name for bug reports
    BUG_REPORTS_PROJECT = "Bug Reports"

    # Acknowledgment message for users
    ACKNOWLEDGMENT_MESSAGE = (
        "I've sent your report to our support team. "
        "Thank you for helping us improve! We'll look into this and may reach out "
        "if we need more details."
    )

    def __init__(self):
        self.admin_email = ADMIN_EMAIL
        self.from_email = DEFAULT_FROM_EMAIL
        # Cache key prefix for rate limiting notifications
        self.cache_prefix = "bug_report_"
        # Minimum time between notifications for same user + similar report
        self.rate_limit_minutes = 5  # Shorter than feature requests - bugs are urgent

    def detect_bug_report(self, message: str) -> Tuple[bool, Optional[str]]:
        """
        Detect if a message contains a bug report pattern.

        Args:
            message: The user's message to analyze

        Returns:
            Tuple of (is_bug_report, matched_pattern_description)
        """
        message_lower = message.lower()

        for pattern in COMPILED_PATTERNS:
            match = pattern.search(message_lower)
            if match:
                return True, match.group(0).strip()

        return False, None

    def should_notify(self, user, message: str) -> bool:
        """
        Check if we should send a notification (rate limiting).

        Prevents spamming admin with duplicate/similar reports from same user.
        """
        # Create a cache key based on user and a hash of key words
        key_words = self._extract_key_words(message)
        cache_key = f"{self.cache_prefix}{user.id}_{hash(key_words)}"

        if cache.get(cache_key):
            logger.debug(f"Rate limited bug report notification for user {user.id}")
            return False

        return True

    def _extract_key_words(self, message: str) -> str:
        """Extract key words from message for rate limiting comparison."""
        stop_words = {
            'fix', 'this', 'bug', 'error', 'issue', 'problem', 'broken',
            'i', 'the', 'a', 'an', 'is', 'are', 'was', 'were', 'not',
            'working', 'it', 'that', 'there', 'something', 'wrong'
        }

        words = re.findall(r'\b[a-z]+\b', message.lower())
        key_words = [w for w in words if w not in stop_words and len(w) > 2]

        return ' '.join(sorted(key_words[:10]))

    def mark_notified(self, user, message: str):
        """Mark that a notification was sent (for rate limiting)."""
        key_words = self._extract_key_words(message)
        cache_key = f"{self.cache_prefix}{user.id}_{hash(key_words)}"

        # Cache for rate_limit_minutes
        cache.set(cache_key, True, timeout=self.rate_limit_minutes * 60)

    def _extract_bug_description(self, message: str) -> str:
        """
        Extract the actual bug description from the message.

        Removes the trigger phrase ("Fix this:", "Bug:", etc.) to get
        just the description of what's wrong.
        """
        # Remove trigger patterns from the beginning
        cleaned = message
        for pattern in COMPILED_PATTERNS:
            cleaned = pattern.sub('', cleaned, count=1)

        return cleaned.strip()

    def _create_admin_task(self, report_info: BugReportInfo) -> Optional[int]:
        """
        Create an AdminTask in the "Bug Reports" project.

        Args:
            report_info: BugReportInfo with all relevant details

        Returns:
            The created task ID, or None if creation failed
        """
        import traceback

        try:
            from apps.admin_console.models import (
                AdminTask,
                AdminProject,
                AdminProjectPhase
            )

            logger.info(f"Creating bug report task for user {report_info.user_id}")

            # Get or create the "Bug Reports" project
            try:
                project, created = AdminProject.objects.get_or_create(
                    name=self.BUG_REPORTS_PROJECT,
                    defaults={
                        'description': 'Bug reports from AI Assistant users',
                        'status': 'open',
                        'priority': 2,  # High priority for bugs
                    }
                )
                if created:
                    logger.info(f"Created '{self.BUG_REPORTS_PROJECT}' project")
            except Exception as e:
                logger.error(f"Failed to get/create project: {e}")
                raise

            # Get Phase 1 for new tasks
            try:
                phase = AdminProjectPhase.objects.filter(phase_number=1).first()
                if not phase:
                    phase = AdminProjectPhase.objects.first()
                    if not phase:
                        phase, _ = AdminProjectPhase.objects.get_or_create(
                            phase_number=1,
                            defaults={
                                'name': 'Phase 1',
                                'objective': 'Initial phase for new tasks',
                                'status': 'in_progress',
                            }
                        )
            except Exception as e:
                logger.error(f"Failed to get/create phase: {e}")
                raise

            # Extract bug description
            bug_description = self._extract_bug_description(report_info.message)

            # Generate task title
            title = bug_description[:80] if bug_description else "Bug report from user"
            if len(bug_description) > 80:
                title = title[:77] + "..."

            # Build task description
            description = {
                "objective": f"Investigate and fix: {bug_description[:100]}",
                "inputs": [
                    f"User report: {report_info.message}",
                    f"Reported by: {report_info.user_name} ({report_info.user_email})",
                    f"Timestamp: {report_info.timestamp}",
                ],
                "actions": [
                    "Review the user's bug report and conversation context",
                    "Attempt to reproduce the issue",
                    "Identify the root cause",
                    "Implement a fix",
                    "Test the fix thoroughly",
                    "Consider if similar issues could exist elsewhere",
                    "Reply to user if needed to confirm fix or get more details",
                ],
                "output": f"Bug fixed: {bug_description[:60]}",
            }

            if report_info.conversation_context:
                description["inputs"].append(
                    f"Conversation context: {report_info.conversation_context[:500]}"
                )

            if report_info.image_data:
                description["inputs"].append("User attached an image/screenshot")

            # Create the task
            task = AdminTask(
                title=title,
                description=description,
                category='bug',
                priority=2,  # High priority for bugs
                status='backlog',
                effort='S',  # Start small, can be updated
                phase=phase,
                project=project,
                created_by='user_report',
            )
            task.save(skip_validation=False)

            logger.info(f"Created AdminTask #{task.id} for bug report from user {report_info.user_id}")
            return task.id

        except Exception as e:
            logger.error(
                f"Failed to create AdminTask for bug report: {e}\n"
                f"User: {report_info.user_id}\n"
                f"Traceback: {traceback.format_exc()}"
            )
            return None

    def check_and_notify(
        self,
        user,
        message: str,
        conversation_context: Optional[str] = None,
        image_data: Optional[str] = None,
        image_mime_type: Optional[str] = None
    ) -> Optional[str]:
        """
        Check if message is a bug report and create task + send notification.

        This is the main entry point. Call to detect bug reports and
        handle them appropriately.

        Args:
            user: The User model instance
            message: The user's message
            conversation_context: Optional recent conversation for context
            image_data: Optional base64 encoded image
            image_mime_type: Optional MIME type of image

        Returns:
            Acknowledgment message if bug report was detected and handled,
            None otherwise
        """
        # Check for bug report pattern
        is_report, pattern_match = self.detect_bug_report(message)

        if not is_report:
            return None

        # Check rate limiting
        if not self.should_notify(user, message):
            logger.info(
                f"Bug report detected but rate limited: user={user.id}, "
                f"pattern={pattern_match}"
            )
            # Still acknowledge to user even if rate limited
            return self.ACKNOWLEDGMENT_MESSAGE

        # Build report info
        report_info = BugReportInfo(
            user_email=user.email,
            user_name=user.get_full_name() or user.email,
            user_id=user.id,
            message=message,
            detected_pattern=pattern_match or "unknown",
            timestamp=timezone.now().strftime("%Y-%m-%d %H:%M:%S %Z"),
            conversation_context=conversation_context,
            image_data=image_data,
            image_mime_type=image_mime_type,
        )

        # Create AdminTask
        task_id = self._create_admin_task(report_info)
        report_info.task_id = task_id

        # Generate task URL if task was created
        if task_id:
            try:
                task_path = reverse('admin_console:admin_task_update', kwargs={'pk': task_id})
                site_domain = getattr(settings, 'SITE_DOMAIN', 'https://wholelifejourney.com')
                report_info.task_url = f"{site_domain}{task_path}"
            except Exception as e:
                logger.warning(f"Failed to generate task URL: {e}")

        # Send email notification
        email_sent = self._send_notification(report_info)

        # Mark as notified
        if task_id or email_sent:
            self.mark_notified(user, message)
            logger.info(
                f"Bug report processed: user={user.id}, "
                f"pattern={pattern_match}, task_id={task_id}, "
                f"email_sent={email_sent}, message={message[:50]}..."
            )

        return self.ACKNOWLEDGMENT_MESSAGE

    def _send_notification(self, report_info: BugReportInfo) -> bool:
        """
        Send email notification to admin about the bug report.

        Args:
            report_info: BugReportInfo with all relevant details

        Returns:
            True if email was sent successfully
        """
        try:
            subject = f"[WLJ Bug Report] Issue from {report_info.user_name}"

            context = {
                'report': report_info,
                'timestamp': timezone.now(),
                'admin_email': self.admin_email,
            }

            # Try to render HTML template
            try:
                html_content = render_to_string(
                    'assistant/emails/bug_report.html',
                    context
                )
            except Exception:
                # Fallback if template doesn't exist yet
                html_content = self._generate_fallback_html(report_info)

            # Generate plain text version
            plain_content = self._generate_plain_text(report_info)

            # Send email
            send_mail(
                subject=subject,
                message=plain_content,
                from_email=self.from_email,
                recipient_list=[self.admin_email],
                html_message=html_content,
                fail_silently=False,
            )

            return True

        except Exception as e:
            logger.error(f"Failed to send bug report notification: {e}")
            return False

    def _generate_plain_text(self, report_info: BugReportInfo) -> str:
        """Generate plain text email content."""
        lines = [
            "WLJ Assistant - Bug Report",
            "=" * 45,
            "",
            f"From: {report_info.user_name} ({report_info.user_email})",
            f"User ID: {report_info.user_id}",
            f"Timestamp: {report_info.timestamp}",
            "",
            "Bug Report:",
            "-" * 45,
            report_info.message,
            "-" * 45,
            "",
            f"Detected Pattern: \"{report_info.detected_pattern}\"",
            "",
        ]

        if report_info.task_id:
            lines.extend([
                f"Task Created: #{report_info.task_id}",
                f"Task URL: {report_info.task_url or 'N/A'}",
                "",
            ])

        if report_info.conversation_context:
            lines.extend([
                "Recent Conversation Context:",
                "-" * 45,
                report_info.conversation_context,
                "-" * 45,
                "",
            ])

        if report_info.image_data:
            lines.append("Note: User attached an image/screenshot (see HTML email)")
            lines.append("")

        lines.extend([
            "Action Required:",
            "- Investigate this bug report",
            "- Attempt to reproduce the issue",
            "- Consider reaching out to the user for more details",
            "",
            "---",
            "Automated notification from WLJ Personal Assistant",
        ])

        return "\n".join(lines)

    def _generate_fallback_html(self, report_info: BugReportInfo) -> str:
        """Generate fallback HTML if template not found."""
        image_section = ""
        if report_info.image_data and report_info.image_mime_type:
            image_section = f"""
            <p><strong>Attached Screenshot:</strong></p>
            <div style="margin: 15px 0; max-width: 100%;">
                <img src="data:{report_info.image_mime_type};base64,{report_info.image_data}"
                     style="max-width: 100%; height: auto; border-radius: 6px; border: 1px solid #e5e7eb;">
            </div>
            """

        task_section = ""
        if report_info.task_id:
            task_section = f"""
            <div style="background: #ecfdf5; border-left: 4px solid #10b981; padding: 15px; margin: 15px 0; border-radius: 0 6px 6px 0;">
                <strong>Task Created:</strong> #{report_info.task_id}
                {f'<br><a href="{report_info.task_url}">View Task</a>' if report_info.task_url else ''}
            </div>
            """

        context_section = ""
        if report_info.conversation_context:
            context_section = f"""
            <p><strong>Recent Conversation Context:</strong></p>
            <div style="background: #f3f4f6; padding: 15px; margin: 15px 0; border-radius: 6px; font-size: 13px; white-space: pre-wrap;">
{report_info.conversation_context}
            </div>
            """

        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .container {{ background: #fff; border-radius: 8px; padding: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ border-bottom: 2px solid #ef4444; padding-bottom: 15px; margin-bottom: 20px; }}
        .header h1 {{ color: #ef4444; font-size: 24px; margin: 0; }}
        .badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; background: #fee2e2; color: #dc2626; }}
        .info-box {{ background: #f9fafb; border-radius: 6px; padding: 15px; margin: 15px 0; }}
        .message-box {{ background: #fef2f2; border-left: 4px solid #ef4444; padding: 15px; margin: 15px 0; border-radius: 0 6px 6px 0; }}
        .action-box {{ background: #fff7ed; border-left: 4px solid #f97316; padding: 15px; margin: 15px 0; border-radius: 0 6px 6px 0; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }}
        dt {{ font-weight: 600; color: #6b7280; font-size: 12px; text-transform: uppercase; }}
        dd {{ margin: 0 0 10px 0; color: #111827; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Bug Report</h1>
        </div>

        <p><span class="badge">User Report</span></p>

        <div class="info-box">
            <dl>
                <dt>User</dt>
                <dd>{report_info.user_name} ({report_info.user_email})</dd>
                <dt>User ID</dt>
                <dd>{report_info.user_id}</dd>
                <dt>Timestamp</dt>
                <dd>{report_info.timestamp}</dd>
                <dt>Detected Pattern</dt>
                <dd>"{report_info.detected_pattern}"</dd>
            </dl>
        </div>

        {task_section}

        <p><strong>Bug Report:</strong></p>
        <div class="message-box">
            {report_info.message}
        </div>

        {image_section}

        {context_section}

        <div class="action-box">
            <strong>Action Required:</strong>
            <ul>
                <li>Investigate this bug report</li>
                <li>Attempt to reproduce the issue</li>
                <li>Consider reaching out to the user for more details</li>
            </ul>
        </div>

        <div class="footer">
            <p>This is an automated notification from the WLJ Personal Assistant.</p>
            <p>Sent to: {self.admin_email}</p>
        </div>
    </div>
</body>
</html>
"""


# Singleton instance
bug_report_service = BugReportService()
