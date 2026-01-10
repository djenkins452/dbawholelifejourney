# ==============================================================================
# File: feature_request_service.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Detects user feature requests ("I wish", "I want") and sends
#              notifications to admin when no matching solution exists
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-10
# ==============================================================================
"""
Feature Request Detection Service

Detects when users express wishes or wants in the AI Assistant that the system
doesn't currently handle, and sends notifications to admin for review.

This enables continuous improvement by capturing user needs that aren't yet met.

Usage:
    from apps.ai.feature_request_service import feature_request_service

    # In the assistant chat flow:
    was_feature_request = feature_request_service.check_and_notify(
        user=user,
        message="I wish I could track my sleep",
        intent_type='no_action'
    )
"""

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, List, Tuple

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

logger = logging.getLogger(__name__)


# Admin email for notifications
ADMIN_EMAIL = getattr(settings, 'ADMIN_EMAIL', 'admin@wholelifejourney.com')
DEFAULT_FROM_EMAIL = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@wholelifejourney.com')


# Patterns that indicate a feature request or wish
FEATURE_REQUEST_PATTERNS = [
    # "I wish" patterns
    r'\bi\s+wish\s+(?:i\s+)?(?:could|can|that|there\s+was|the\s+app)\b',
    r'\bi\s+wish\s+(?:it|this|wlj|the\s+app|the\s+assistant)\b',

    # "I want" patterns (feature-related, not data logging)
    r'\bi\s+want\s+(?:to\s+be\s+able|the\s+app|the\s+ability|a\s+way|a\s+feature)\b',
    r'\bi\s+want\s+(?:it|this|wlj)\s+to\b',

    # "Can you" / "Could you" requests for new features
    r'\bcan\s+(?:you|the\s+app|this|wlj)\s+(?:add|create|build|make|implement)\b',
    r'\bcould\s+(?:you|the\s+app|this|wlj)\s+(?:add|create|build|make|implement)\b',

    # "Would be nice" / "Would love" patterns
    r'\bit\s+would\s+be\s+(?:nice|great|helpful|awesome)\s+(?:if|to)\b',
    r'\bi\s+would\s+(?:love|like|prefer)\s+(?:if|to\s+be\s+able|a\s+way|the\s+ability)\b',

    # "There should be" patterns
    r'\bthere\s+should\s+be\s+(?:a\s+way|an\s+option|a\s+feature)\b',

    # "Why can't" / "Why isn't" patterns
    r'\bwhy\s+can\'?t\s+(?:i|you|the\s+app|this)\b',
    r'\bwhy\s+isn\'?t\s+there\s+(?:a\s+way|an\s+option)\b',

    # Feature suggestion patterns
    r'\b(?:feature\s+request|suggestion|idea)\s*[:\-]?\s+\b',
    r'\bplease\s+add\s+(?:a\s+)?(?:feature|option|ability|way)\b',
]

# Compile patterns for efficiency
COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in FEATURE_REQUEST_PATTERNS]


@dataclass
class FeatureRequestInfo:
    """Information about a detected feature request."""
    user_email: str
    user_name: str
    user_id: int
    message: str
    detected_pattern: str
    timestamp: str
    conversation_context: Optional[str] = None


class FeatureRequestService:
    """
    Service for detecting and notifying admin about user feature requests.

    When users express wishes or wants that the assistant can't fulfill,
    this service captures those requests and sends them to admin for review.
    """

    def __init__(self):
        self.admin_email = ADMIN_EMAIL
        self.from_email = DEFAULT_FROM_EMAIL
        # Cache key prefix for rate limiting notifications
        self.cache_prefix = "feature_request_"
        # Minimum time between notifications for same user + similar request
        self.rate_limit_hours = 24

    def detect_feature_request(self, message: str) -> Tuple[bool, Optional[str]]:
        """
        Detect if a message contains a feature request pattern.

        Args:
            message: The user's message to analyze

        Returns:
            Tuple of (is_feature_request, matched_pattern_description)
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

        Prevents spamming admin with duplicate/similar requests from same user.
        """
        # Create a cache key based on user and a hash of key words
        key_words = self._extract_key_words(message)
        cache_key = f"{self.cache_prefix}{user.id}_{hash(key_words)}"

        if cache.get(cache_key):
            logger.debug(f"Rate limited feature request notification for user {user.id}")
            return False

        return True

    def _extract_key_words(self, message: str) -> str:
        """Extract key words from message for rate limiting comparison."""
        # Simple extraction - remove common words, keep nouns/verbs
        stop_words = {
            'i', 'want', 'wish', 'to', 'be', 'able', 'could', 'can', 'would',
            'the', 'a', 'an', 'it', 'this', 'that', 'there', 'is', 'are',
            'was', 'were', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'should', 'if', 'for', 'on', 'in', 'at', 'by', 'with', 'from'
        }

        words = re.findall(r'\b[a-z]+\b', message.lower())
        key_words = [w for w in words if w not in stop_words and len(w) > 2]

        return ' '.join(sorted(key_words[:10]))  # Limit to 10 key words

    def mark_notified(self, user, message: str):
        """Mark that a notification was sent (for rate limiting)."""
        key_words = self._extract_key_words(message)
        cache_key = f"{self.cache_prefix}{user.id}_{hash(key_words)}"

        # Cache for rate_limit_hours
        cache.set(cache_key, True, timeout=self.rate_limit_hours * 3600)

    def check_and_notify(
        self,
        user,
        message: str,
        intent_type: str,
        conversation_context: Optional[str] = None
    ) -> bool:
        """
        Check if message is a feature request and send notification if needed.

        This is the main entry point. Call after intent recognition to capture
        requests that the system couldn't handle.

        Args:
            user: The User model instance
            message: The user's message
            intent_type: The intent recognized (or 'no_action')
            conversation_context: Optional recent conversation for context

        Returns:
            True if notification was sent, False otherwise
        """
        # Only check messages where no actionable intent was found
        if intent_type != 'no_action':
            return False

        # Check for feature request pattern
        is_request, pattern_match = self.detect_feature_request(message)

        if not is_request:
            return False

        # Check rate limiting
        if not self.should_notify(user, message):
            logger.info(
                f"Feature request detected but rate limited: user={user.id}, "
                f"pattern={pattern_match}"
            )
            return False

        # Build request info
        request_info = FeatureRequestInfo(
            user_email=user.email,
            user_name=user.get_full_name() or user.email,
            user_id=user.id,
            message=message,
            detected_pattern=pattern_match or "unknown",
            timestamp=timezone.now().strftime("%Y-%m-%d %H:%M:%S %Z"),
            conversation_context=conversation_context,
        )

        # Send notification
        success = self._send_notification(request_info)

        if success:
            self.mark_notified(user, message)
            logger.info(
                f"Feature request notification sent: user={user.id}, "
                f"pattern={pattern_match}, message={message[:50]}..."
            )

        return success

    def _send_notification(self, request_info: FeatureRequestInfo) -> bool:
        """
        Send email notification to admin about the feature request.

        Args:
            request_info: FeatureRequestInfo with all relevant details

        Returns:
            True if email was sent successfully
        """
        try:
            subject = f"[WLJ Assistant] Feature Request from {request_info.user_name}"

            context = {
                'request': request_info,
                'timestamp': timezone.now(),
                'admin_email': self.admin_email,
            }

            # Try to render HTML template
            try:
                html_content = render_to_string(
                    'assistant/emails/feature_request.html',
                    context
                )
            except Exception:
                # Fallback if template doesn't exist yet
                html_content = self._generate_fallback_html(request_info)

            # Generate plain text version
            plain_content = self._generate_plain_text(request_info)

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
            logger.error(f"Failed to send feature request notification: {e}")
            return False

    def _generate_plain_text(self, request_info: FeatureRequestInfo) -> str:
        """Generate plain text email content."""
        lines = [
            "WLJ Assistant - Feature Request Detected",
            "=" * 45,
            "",
            f"From: {request_info.user_name} ({request_info.user_email})",
            f"User ID: {request_info.user_id}",
            f"Timestamp: {request_info.timestamp}",
            "",
            "User Message:",
            "-" * 45,
            request_info.message,
            "-" * 45,
            "",
            f"Detected Pattern: \"{request_info.detected_pattern}\"",
            "",
        ]

        if request_info.conversation_context:
            lines.extend([
                "Recent Conversation Context:",
                "-" * 45,
                request_info.conversation_context,
                "-" * 45,
                "",
            ])

        lines.extend([
            "",
            "Action Required:",
            "- Review this feature request",
            "- Consider creating a project task if the feature would be valuable",
            "- The user expressed a need that the assistant couldn't fulfill",
            "",
            "---",
            f"Automated notification from WLJ Personal Assistant",
        ])

        return "\n".join(lines)

    def _generate_fallback_html(self, request_info: FeatureRequestInfo) -> str:
        """Generate fallback HTML if template not found."""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .container {{ background: #fff; border-radius: 8px; padding: 30px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .header {{ border-bottom: 2px solid #6366f1; padding-bottom: 15px; margin-bottom: 20px; }}
        .header h1 {{ color: #6366f1; font-size: 24px; margin: 0; }}
        .badge {{ display: inline-block; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: 600; background: #fef3c7; color: #92400e; }}
        .info-box {{ background: #f9fafb; border-radius: 6px; padding: 15px; margin: 15px 0; }}
        .message-box {{ background: #f3f4f6; border-left: 4px solid #6366f1; padding: 15px; margin: 15px 0; border-radius: 0 6px 6px 0; }}
        .action-box {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; margin: 15px 0; border-radius: 0 6px 6px 0; }}
        .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #6b7280; }}
        dt {{ font-weight: 600; color: #6b7280; font-size: 12px; text-transform: uppercase; }}
        dd {{ margin: 0 0 10px 0; color: #111827; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Feature Request Detected</h1>
        </div>

        <p><span class="badge">User Request</span></p>

        <div class="info-box">
            <dl>
                <dt>User</dt>
                <dd>{request_info.user_name} ({request_info.user_email})</dd>
                <dt>User ID</dt>
                <dd>{request_info.user_id}</dd>
                <dt>Timestamp</dt>
                <dd>{request_info.timestamp}</dd>
                <dt>Detected Pattern</dt>
                <dd>"{request_info.detected_pattern}"</dd>
            </dl>
        </div>

        <p><strong>User Message:</strong></p>
        <div class="message-box">
            {request_info.message}
        </div>

        <div class="action-box">
            <strong>Action Required:</strong>
            <ul>
                <li>Review this feature request</li>
                <li>Consider creating a project task if the feature would be valuable</li>
                <li>The user expressed a need that the assistant couldn't fulfill</li>
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
feature_request_service = FeatureRequestService()
