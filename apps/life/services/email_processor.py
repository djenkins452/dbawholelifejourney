"""
Email Processing Service

Uses AI to extract action items from emails and create tasks.
"""

import json
import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class EmailProcessingService:
    """
    Process emails and extract action items using AI.

    Uses OpenAI to analyze email content and identify actionable items,
    then creates corresponding Task records in the Life module.
    """

    # System prompt for action item extraction
    ACTION_ITEM_PROMPT = """You are analyzing an email to extract action items for a personal task management system.

Your job is to:
1. Identify any clear action items, requests, or tasks directed at the recipient
2. Return them as a JSON object with an "action_items" array
3. If no action items exist, return an empty array

For each action item found, extract:
- title: A clear, actionable task title (max 100 chars, start with a verb)
- notes: Relevant context from the email (max 500 chars)
- priority: "now" (urgent/deadline today), "soon" (this week), or "someday" (when time permits)
- due_date: ISO date string (YYYY-MM-DD) if a deadline is mentioned, null otherwise

Example response format:
{
    "action_items": [
        {
            "title": "Reply to John about project timeline",
            "notes": "John asked for updated timeline by Friday. He mentioned concerns about Q2 deliverables.",
            "priority": "soon",
            "due_date": "2026-01-24"
        }
    ]
}

If no action items, return:
{
    "action_items": []
}

IMPORTANT RULES:
- Only extract genuine action items that require the recipient to DO something
- Do NOT create tasks for:
  * Newsletters or promotional content
  * Automated notifications (shipping updates, receipts, confirmations)
  * FYI/informational emails with no specific request
  * Social media notifications
  * Marketing emails
  * Subscription digests
- Focus on emails where someone is asking the recipient to take action
- Be conservative - when in doubt, don't create a task

Return ONLY valid JSON, no other text."""

    def __init__(self, user):
        """
        Initialize the email processor.

        Args:
            user: Django User instance to create tasks for.
        """
        self.user = user

    def process_email(self, email: dict) -> dict:
        """
        Process a single email and extract action items.

        Args:
            email: Email dict with id, subject, sender, body, etc.

        Returns:
            Dict with: action_items (count), tasks_created (count), skipped (bool), reason (str)
        """
        from apps.life.models import ProcessedEmail

        # Check if already processed
        if ProcessedEmail.objects.filter(
            user=self.user,
            gmail_message_id=email['id']
        ).exists():
            return {
                'action_items': 0,
                'tasks_created': 0,
                'skipped': True,
                'reason': 'already_processed'
            }

        # Build prompt for AI
        # Truncate body to avoid token limits
        body_truncated = email.get('body', '')[:4000]

        user_prompt = f"""Analyze this email for action items:

Subject: {email.get('subject', '(No Subject)')}
From: {email.get('sender', 'Unknown')}
Date: {email.get('date', 'Unknown')}

Email Body:
{body_truncated}
"""

        try:
            # Call AI to extract action items
            response = self._call_ai(user_prompt)

            if not response:
                return self._record_processed(email, 0, 0, 'ai_unavailable')

            # Parse AI response
            try:
                result = json.loads(response)
            except json.JSONDecodeError:
                # Try to extract JSON from response if it has extra text
                import re
                json_match = re.search(r'\{[\s\S]*\}', response)
                if json_match:
                    result = json.loads(json_match.group())
                else:
                    logger.error(f"AI response not valid JSON: {response[:200]}")
                    return self._record_processed(email, 0, 0, 'parse_error')

            action_items = result.get('action_items', [])

            if not action_items:
                return self._record_processed(email, 0, 0, 'no_action_items')

            # Create tasks
            tasks_created = self._create_tasks(email, action_items)

            return self._record_processed(email, len(action_items), tasks_created, '')

        except json.JSONDecodeError as e:
            logger.error(f"AI response parse error: {e}")
            return self._record_processed(email, 0, 0, 'parse_error')
        except Exception as e:
            logger.error(f"Email processing error: {e}", exc_info=True)
            return self._record_processed(email, 0, 0, f'error: {str(e)[:100]}')

    def _call_ai(self, user_prompt: str) -> Optional[str]:
        """
        Call the AI service to analyze email content.

        Args:
            user_prompt: The prompt with email content.

        Returns:
            AI response string or None if unavailable.
        """
        try:
            from apps.ai.services import AIService

            ai_service = AIService()

            # Check if AI is available
            if not ai_service.is_available():
                logger.warning("AI service not available for email processing")
                return None

            # Use the internal _call_api method
            response = ai_service._call_api(
                system_prompt=self.ACTION_ITEM_PROMPT,
                user_prompt=user_prompt,
                max_tokens=1000
            )

            return response

        except ImportError:
            logger.error("AIService not available")
            return None
        except Exception as e:
            logger.error(f"AI call error: {e}")
            return None

    @transaction.atomic
    def _create_tasks(self, email: dict, action_items: list) -> int:
        """
        Create Task records from extracted action items.

        Args:
            email: Original email dict.
            action_items: List of action item dicts from AI.

        Returns:
            Number of tasks created.
        """
        from apps.life.models import Task

        created = 0

        for item in action_items:
            # Parse due date if provided
            due_date = None
            if item.get('due_date'):
                try:
                    from datetime import datetime
                    due_date = datetime.strptime(item['due_date'], '%Y-%m-%d').date()
                except (ValueError, TypeError):
                    pass

            # Validate priority
            priority = item.get('priority', 'someday')
            if priority not in ('now', 'soon', 'someday'):
                priority = 'someday'

            # Create the task
            Task.objects.create(
                user=self.user,
                title=item.get('title', 'Email action item')[:300],
                notes=item.get('notes', '')[:2000],
                priority=priority,
                due_date=due_date,
                # Email source tracking
                email_source_id=email['id'],
                email_source_subject=email.get('subject', '')[:500],
                email_source_sender=email.get('sender', '')[:255],
                email_source_date=email.get('date_parsed'),
            )
            created += 1

            logger.info(
                f"Created task from email: '{item.get('title', '')[:50]}' "
                f"for user {self.user.email}"
            )

        return created

    def _record_processed(self, email: dict, found: int, created: int, reason: str) -> dict:
        """
        Record that an email has been processed.

        Args:
            email: Original email dict.
            found: Number of action items found.
            created: Number of tasks created.
            reason: Skip/error reason if applicable.

        Returns:
            Result dict for the caller.
        """
        from apps.life.models import ProcessedEmail

        ProcessedEmail.objects.create(
            user=self.user,
            gmail_message_id=email['id'],
            action_items_found=found,
            tasks_created=created,
            skipped_reason=reason,
        )

        return {
            'action_items': found,
            'tasks_created': created,
            'skipped': bool(reason),
            'reason': reason,
        }
