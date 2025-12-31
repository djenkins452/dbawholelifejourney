# ==============================================================================
# File: models.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: SMS notification models for tracking sent/scheduled SMS and responses
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================
"""
SMS Models - Tracking SMS notifications and user responses.

This module provides models for:
- SMSNotification: Scheduled/sent SMS notifications with delivery status
- SMSResponse: Incoming SMS replies and parsed actions

The SMS system supports reminders for:
- Medicine doses and refill alerts
- Task due dates
- Calendar events
- Prayer reminders
- Fasting window reminders
"""

import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class SMSNotification(TimeStampedModel):
    """
    Tracks each SMS notification sent or scheduled.

    Uses a generic foreign key to link to the source object (Medicine, Task, etc.)
    for flexible reminder types.
    """

    # Status choices
    STATUS_PENDING = 'pending'
    STATUS_SENT = 'sent'
    STATUS_DELIVERED = 'delivered'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_SENT, 'Sent'),
        (STATUS_DELIVERED, 'Delivered'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    # Category choices - what type of reminder this is
    CATEGORY_MEDICINE = 'medicine'
    CATEGORY_MEDICINE_REFILL = 'medicine_refill'
    CATEGORY_TASK = 'task'
    CATEGORY_EVENT = 'event'
    CATEGORY_PRAYER = 'prayer'
    CATEGORY_FASTING = 'fasting'
    CATEGORY_SIGNIFICANT_EVENT = 'significant_event'
    CATEGORY_VERIFICATION = 'verification'
    CATEGORY_SYSTEM = 'system'

    CATEGORY_CHOICES = [
        (CATEGORY_MEDICINE, 'Medicine Dose'),
        (CATEGORY_MEDICINE_REFILL, 'Medicine Refill'),
        (CATEGORY_TASK, 'Task'),
        (CATEGORY_EVENT, 'Event'),
        (CATEGORY_PRAYER, 'Prayer'),
        (CATEGORY_FASTING, 'Fasting'),
        (CATEGORY_SIGNIFICANT_EVENT, 'Significant Event'),
        (CATEGORY_VERIFICATION, 'Verification'),
        (CATEGORY_SYSTEM, 'System'),
    ]

    # Fields
    notification_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Unique ID for this notification"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sms_notifications',
        help_text="User this notification is for"
    )

    # Message content
    category = models.CharField(
        max_length=20,
        choices=CATEGORY_CHOICES,
        db_index=True,
        help_text="Type of reminder"
    )
    message = models.CharField(
        max_length=320,  # Allow concatenated SMS (2x160)
        help_text="SMS message content"
    )

    # Scheduling
    scheduled_for = models.DateTimeField(
        db_index=True,
        help_text="When to send this SMS (UTC)"
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
        help_text="Delivery status"
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the SMS was sent"
    )
    delivered_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When delivery was confirmed"
    )
    failed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When sending failed"
    )
    failure_reason = models.CharField(
        max_length=500,
        blank=True,
        help_text="Error message if failed"
    )

    # Twilio tracking
    twilio_sid = models.CharField(
        max_length=50,
        blank=True,
        help_text="Twilio message SID for tracking"
    )

    # Generic FK to source object (Medicine, Task, LifeEvent, etc.)
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Type of source object"
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of source object"
    )
    source_object = GenericForeignKey('content_type', 'object_id')

    # Response tracking
    response_code = models.CharField(
        max_length=20,
        blank=True,
        help_text="User's reply code (D, R, N, etc.)"
    )
    response_received_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When user replied"
    )
    response_processed = models.BooleanField(
        default=False,
        help_text="Has the response been processed?"
    )

    class Meta:
        ordering = ['-scheduled_for']
        verbose_name = 'SMS Notification'
        verbose_name_plural = 'SMS Notifications'
        indexes = [
            models.Index(fields=['user', '-scheduled_for']),
            models.Index(fields=['status', 'scheduled_for']),
            models.Index(fields=['category', '-scheduled_for']),
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f"{self.get_category_display()} SMS for {self.user.email} - {self.status}"

    def mark_sent(self, twilio_sid=None):
        """Mark notification as sent."""
        self.status = self.STATUS_SENT
        self.sent_at = timezone.now()
        if twilio_sid:
            self.twilio_sid = twilio_sid
        self.save(update_fields=['status', 'sent_at', 'twilio_sid', 'updated_at'])

    def mark_delivered(self):
        """Mark notification as delivered."""
        self.status = self.STATUS_DELIVERED
        self.delivered_at = timezone.now()
        self.save(update_fields=['status', 'delivered_at', 'updated_at'])

    def mark_failed(self, reason=''):
        """Mark notification as failed."""
        self.status = self.STATUS_FAILED
        self.failed_at = timezone.now()
        self.failure_reason = reason[:500]
        self.save(update_fields=['status', 'failed_at', 'failure_reason', 'updated_at'])

    def mark_cancelled(self):
        """Cancel a pending notification."""
        if self.status == self.STATUS_PENDING:
            self.status = self.STATUS_CANCELLED
            self.save(update_fields=['status', 'updated_at'])

    def record_response(self, response_code):
        """Record a user's reply to this notification."""
        self.response_code = response_code.upper()
        self.response_received_at = timezone.now()
        self.save(update_fields=['response_code', 'response_received_at', 'updated_at'])


class SMSResponse(TimeStampedModel):
    """
    Tracks incoming SMS replies from users.

    When a user replies to an SMS notification, this model stores
    the raw reply and parsed action.
    """

    # Parsed action choices
    ACTION_DONE = 'done'
    ACTION_REMIND = 'remind'
    ACTION_SKIP = 'skip'
    ACTION_UNKNOWN = 'unknown'

    ACTION_CHOICES = [
        (ACTION_DONE, 'Done/Taken'),
        (ACTION_REMIND, 'Remind Later'),
        (ACTION_SKIP, 'Skip'),
        (ACTION_UNKNOWN, 'Unknown'),
    ]

    response_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
        help_text="Unique ID for this response"
    )

    # Link to the notification being replied to
    notification = models.ForeignKey(
        SMSNotification,
        on_delete=models.CASCADE,
        related_name='responses',
        null=True,
        blank=True,
        help_text="The notification this is a reply to"
    )

    # User (determined from phone number)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sms_responses',
        null=True,
        blank=True,
        help_text="User who sent this reply"
    )

    # Raw message data
    from_number = models.CharField(
        max_length=20,
        help_text="Phone number that sent the reply"
    )
    body = models.TextField(
        help_text="Raw message body"
    )
    twilio_sms_sid = models.CharField(
        max_length=50,
        blank=True,
        help_text="Twilio SID of the incoming message"
    )

    # Parsed action
    parsed_action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        default=ACTION_UNKNOWN,
        help_text="Parsed action from the reply"
    )
    remind_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Minutes to wait before reminding again (if action=remind)"
    )

    # Processing
    received_at = models.DateTimeField(
        default=timezone.now,
        help_text="When the reply was received"
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the action was executed"
    )
    action_taken = models.CharField(
        max_length=200,
        blank=True,
        help_text="Description of what action was taken"
    )
    processing_error = models.TextField(
        blank=True,
        help_text="Error message if processing failed"
    )

    class Meta:
        ordering = ['-received_at']
        verbose_name = 'SMS Response'
        verbose_name_plural = 'SMS Responses'
        indexes = [
            models.Index(fields=['from_number', '-received_at']),
            models.Index(fields=['user', '-received_at']),
            models.Index(fields=['parsed_action', '-received_at']),
        ]

    def __str__(self):
        action = self.get_parsed_action_display()
        return f"Reply from {self.from_number}: {action}"

    def mark_processed(self, action_description=''):
        """Mark this response as processed."""
        self.processed_at = timezone.now()
        self.action_taken = action_description[:200]
        self.save(update_fields=['processed_at', 'action_taken', 'updated_at'])

    def mark_failed(self, error_message):
        """Mark this response as failed to process."""
        self.processing_error = error_message
        self.save(update_fields=['processing_error', 'updated_at'])

    @classmethod
    def parse_reply(cls, body):
        """
        Parse a user's SMS reply into an action.

        Returns tuple of (action, remind_minutes).

        Reply codes:
        - D, d, done, yes, taken, took, y -> done
        - R, R5, R10, R15, R30, remind -> remind (with optional minutes)
        - N, n, skip, no, not, later -> skip
        """
        body = body.strip().lower()

        # Check for done/taken
        if body in ('d', 'done', 'yes', 'taken', 'took', 'y', '1'):
            return (cls.ACTION_DONE, None)

        # Check for skip
        if body in ('n', 'no', 'skip', 'not', 'later', 'nope', '0'):
            return (cls.ACTION_SKIP, None)

        # Check for remind with optional minutes
        if body.startswith('r'):
            # Try to extract minutes (r5, r10, r15, r30, r60)
            try:
                minutes_str = body[1:].strip()
                if minutes_str:
                    minutes = int(minutes_str)
                    # Validate reasonable range (1-120 minutes)
                    if 1 <= minutes <= 120:
                        return (cls.ACTION_REMIND, minutes)
                # Default remind time: 5 minutes
                return (cls.ACTION_REMIND, 5)
            except ValueError:
                if body == 'remind':
                    return (cls.ACTION_REMIND, 5)

        return (cls.ACTION_UNKNOWN, None)
