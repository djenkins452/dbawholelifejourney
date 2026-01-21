"""
WLJ Values Guardrails - Content Filtering Service

Part of Task 9.3: AI Assistant Search Gateway

This service filters user input and AI output to ensure alignment with
WLJ culture: faith-positive, wellness-focused, encouraging, and
protective of user dignity.

Filtering approach:
- ALLOWED: Content passes through unchanged
- BLOCKED: Content blocked with honest message + option to appeal

When blocked, the user sees:
"I'm sorry, that request falls outside of the content we provide.
If you feel you have reached this in error, please respond 'yes'
and I will notify our support team."

If user responds "yes", we:
1. Send email to admin@wholelifejourney.com with user info and blocked message
2. Mark the message as appealed
"""

import re
import logging
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

logger = logging.getLogger(__name__)


class FilterStatus(Enum):
    """Possible outcomes of content filtering."""
    ALLOWED = "allowed"
    BLOCKED = "blocked"


@dataclass
class FilterResult:
    """
    Result of content filtering.

    Attributes:
        status: The filtering outcome (ALLOWED or BLOCKED)
        message: Response message for BLOCKED cases
        matched_pattern: Name of the pattern that matched (for logging/tracking)
        category: Category of the matched pattern (for analytics)
    """
    status: FilterStatus
    message: str = ""
    matched_pattern: str = ""
    category: str = ""

    @property
    def is_allowed(self) -> bool:
        return self.status == FilterStatus.ALLOWED

    @property
    def is_blocked(self) -> bool:
        return self.status == FilterStatus.BLOCKED


# The standard blocked message - honest and direct
BLOCKED_MESSAGE = (
    "I'm sorry, that request falls outside of the content we provide. "
    "If you feel you have reached this in error, please respond 'yes' "
    "and I will notify our support team."
)

# Message shown after user appeals
APPEAL_CONFIRMATION_MESSAGE = (
    "Thank you for letting us know. I've notified our support team who will "
    "review this and may reach out to you. Is there something else I can help "
    "you with today?"
)


class ValuesFilter:
    """
    Content filtering service for WLJ values alignment.

    Uses admin-configured patterns from ValuesGuardrailPattern model
    to detect inappropriate content.
    """

    def __init__(self):
        self._compiled_patterns_cache = None

    def _get_patterns(self, for_input: bool = True):
        """
        Get compiled patterns for filtering.

        Args:
            for_input: True for user input patterns, False for AI output patterns
        """
        from apps.ai.models import ValuesGuardrailPattern

        if for_input:
            patterns = ValuesGuardrailPattern.get_input_patterns()
        else:
            patterns = ValuesGuardrailPattern.get_output_patterns()

        compiled = []
        for pattern in patterns:
            try:
                compiled.append({
                    'name': pattern.name,
                    'regex': re.compile(pattern.pattern, re.IGNORECASE),
                    'category': pattern.category,
                })
            except re.error as e:
                logger.error(f"Invalid regex in pattern '{pattern.name}': {e}")
        return compiled

    def filter_input(self, text: str) -> FilterResult:
        """
        Filter user input for inappropriate content.

        Args:
            text: The user's message text

        Returns:
            FilterResult with filtering outcome
        """
        if not text or not text.strip():
            return FilterResult(status=FilterStatus.ALLOWED)

        text = text.strip()
        patterns = self._get_patterns(for_input=True)

        # Check each pattern in order (sorted by sort_order in model)
        for pattern in patterns:
            if pattern['regex'].search(text):
                logger.info(
                    f"Values filter blocked content - pattern '{pattern['name']}' "
                    f"(category: {pattern['category']})"
                )
                return FilterResult(
                    status=FilterStatus.BLOCKED,
                    message=BLOCKED_MESSAGE,
                    matched_pattern=pattern['name'],
                    category=pattern['category'],
                )

        return FilterResult(status=FilterStatus.ALLOWED)

    def filter_output(self, text: str) -> FilterResult:
        """
        Filter AI output for inappropriate content.

        This is a safety check to ensure AI responses don't contain
        content that violates WLJ values.

        Args:
            text: The AI's response text

        Returns:
            FilterResult with filtering outcome
        """
        if not text or not text.strip():
            return FilterResult(status=FilterStatus.ALLOWED)

        text = text.strip()
        patterns = self._get_patterns(for_input=False)

        for pattern in patterns:
            if pattern['regex'].search(text):
                logger.warning(
                    f"AI output blocked by values filter - pattern '{pattern['name']}' "
                    f"(category: {pattern['category']})"
                )
                return FilterResult(
                    status=FilterStatus.BLOCKED,
                    message="I apologize, let me rephrase. How can I help you today?",
                    matched_pattern=pattern['name'],
                    category=pattern['category'],
                )

        return FilterResult(status=FilterStatus.ALLOWED)

    def is_appeal_response(self, text: str) -> bool:
        """
        Check if user's response is an appeal (responding "yes" to blocked message).

        Args:
            text: The user's message text

        Returns:
            True if this looks like an appeal response
        """
        if not text:
            return False

        text = text.strip().lower()
        # Match "yes", "yes.", "yes!", etc.
        return text in ('yes', 'yes.', 'yes!', 'y', 'yeah', 'yep', 'yup')


def send_appeal_notification(user, message_content: str, pattern_name: str, conversation_id: int):
    """
    Send email notification to admin about a user appeal.

    Args:
        user: The User object who sent the message
        message_content: The content that was blocked
        pattern_name: Name of the pattern that triggered the block
        conversation_id: ID of the conversation for admin review
    """
    from django.core.mail import send_mail
    from django.conf import settings
    from django.utils import timezone

    subject = f"[WLJ] Content Filter Appeal from {user.get_full_name() or user.email}"

    message = f"""
A user has appealed a content filter block.

USER INFORMATION
----------------
Name: {user.get_full_name() or 'Not provided'}
Email: {user.email}
User ID: {user.id}

BLOCKED MESSAGE
---------------
Pattern that triggered block: {pattern_name}
Message content:
{message_content}

DETAILS
-------
Time: {timezone.now().strftime('%Y-%m-%d %H:%M:%S %Z')}
Conversation ID: {conversation_id}

REVIEW LINK
-----------
https://wholelifejourney.com/admin/ai/assistantmessage/?conversation__id={conversation_id}

Please review and determine if this was a false positive.
If the filter pattern needs adjustment, update it at:
https://wholelifejourney.com/admin/ai/valuesguardrailpattern/
"""

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=['admin@wholelifejourney.com'],
            fail_silently=False,
        )
        logger.info(f"Appeal notification sent for user {user.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send appeal notification: {e}")
        return False


# Module-level singleton for convenience
_filter_instance = None


def get_values_filter() -> ValuesFilter:
    """Get the singleton ValuesFilter instance."""
    global _filter_instance
    if _filter_instance is None:
        _filter_instance = ValuesFilter()
    return _filter_instance


def filter_user_input(text: str) -> FilterResult:
    """
    Convenience function to filter user input.

    Args:
        text: The user's message text

    Returns:
        FilterResult with filtering outcome
    """
    return get_values_filter().filter_input(text)


def filter_ai_output(text: str) -> FilterResult:
    """
    Convenience function to filter AI output.

    Args:
        text: The AI's response text

    Returns:
        FilterResult with filtering outcome
    """
    return get_values_filter().filter_output(text)


def check_appeal_response(text: str) -> bool:
    """
    Convenience function to check if text is an appeal response.

    Args:
        text: The user's message text

    Returns:
        True if this is an appeal response
    """
    return get_values_filter().is_appeal_response(text)
