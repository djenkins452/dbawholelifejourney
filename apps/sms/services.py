# ==============================================================================
# File: services.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Twilio SMS service and notification management
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-31
# ==============================================================================
"""
SMS Services - Twilio integration and notification management.

Provides:
- TwilioService: Direct Twilio API integration for sending SMS and verification
- SMSNotificationService: High-level service for scheduling and managing notifications
"""

import hashlib
import hmac
import logging
import re
from base64 import b64encode
from datetime import timedelta
from typing import Optional
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from .models import SMSNotification, SMSResponse

logger = logging.getLogger(__name__)

# E.164 phone number format regex
E164_PATTERN = re.compile(r'^\+[1-9]\d{1,14}$')


class TwilioService:
    """
    Service for interacting with Twilio API.

    Handles:
    - Sending SMS messages
    - Phone verification via Twilio Verify
    - Webhook signature validation

    In test mode (TWILIO_TEST_MODE=True), logs messages instead of sending.
    """

    def __init__(self):
        """Initialize Twilio client with credentials from settings."""
        self.account_sid = getattr(settings, 'TWILIO_ACCOUNT_SID', '') or ''
        self.auth_token = getattr(settings, 'TWILIO_AUTH_TOKEN', '') or ''
        raw_phone = getattr(settings, 'TWILIO_PHONE_NUMBER', '') or ''
        self.verify_service_sid = getattr(settings, 'TWILIO_VERIFY_SERVICE_SID', '') or ''
        self.test_mode = getattr(settings, 'TWILIO_TEST_MODE', False)

        # Normalize and validate the phone number
        self.phone_number = self._normalize_phone_number(raw_phone)
        if raw_phone and not self.phone_number:
            logger.error(
                f"TWILIO_PHONE_NUMBER '{raw_phone}' is not valid E.164 format. "
                "Expected format: +1XXXXXXXXXX (e.g., +12025551234)"
            )

        self._client = None

    def _normalize_phone_number(self, phone: str) -> str:
        """
        Normalize a phone number to E.164 format.

        Args:
            phone: Raw phone number string

        Returns:
            Normalized phone number or empty string if invalid
        """
        if not phone:
            return ''

        # Remove whitespace, dashes, parentheses, dots
        cleaned = re.sub(r'[\s\-\(\)\.]', '', phone.strip())

        # If it doesn't start with +, assume US number and add +1
        if cleaned and not cleaned.startswith('+'):
            if cleaned.startswith('1') and len(cleaned) == 11:
                cleaned = '+' + cleaned
            elif len(cleaned) == 10:
                cleaned = '+1' + cleaned

        # Validate E.164 format
        if E164_PATTERN.match(cleaned):
            return cleaned

        return ''

    @property
    def is_configured(self):
        """Check if Twilio is properly configured."""
        return bool(
            self.account_sid and
            self.auth_token and
            self.phone_number
        )

    @property
    def verify_configured(self):
        """Check if Twilio Verify is properly configured."""
        return bool(self.is_configured and self.verify_service_sid)

    @property
    def client(self):
        """Lazy-load Twilio client."""
        if self._client is None and self.is_configured:
            try:
                from twilio.rest import Client
                self._client = Client(self.account_sid, self.auth_token)
            except ImportError:
                logger.error("Twilio package not installed. Run: pip install twilio")
                raise ImportError("twilio package is required for SMS functionality")
        return self._client

    def send_sms(self, to: str, message: str) -> dict:
        """
        Send an SMS message via Twilio.

        Args:
            to: Phone number in E.164 format (+1XXXXXXXXXX)
            message: Message body (max 320 chars for concatenated SMS)

        Returns:
            dict with 'success', 'sid', 'error' keys
        """
        # Test mode - log instead of sending (check first to skip config requirement)
        if self.test_mode:
            logger.info(f"[TEST MODE] SMS to {to}: {message}")
            # Generate a fake SID for testing
            fake_sid = f"SM_TEST_{timezone.now().strftime('%Y%m%d%H%M%S')}"
            return {
                'success': True,
                'sid': fake_sid,
                'error': None,
                'test_mode': True
            }

        if not self.is_configured:
            # Provide detailed error for missing configuration
            missing = []
            if not self.account_sid:
                missing.append('TWILIO_ACCOUNT_SID')
            if not self.auth_token:
                missing.append('TWILIO_AUTH_TOKEN')
            if not self.phone_number:
                missing.append('TWILIO_PHONE_NUMBER (must be E.164 format: +1XXXXXXXXXX)')
            error_msg = f"Twilio not configured. Missing: {', '.join(missing)}"
            logger.error(error_msg)
            return {
                'success': False,
                'sid': None,
                'error': error_msg
            }

        # Normalize destination phone number
        normalized_to = self._normalize_phone_number(to)
        if not normalized_to:
            error_msg = f"Invalid destination phone number: '{to}'. Must be E.164 format."
            logger.error(error_msg)
            return {
                'success': False,
                'sid': None,
                'error': error_msg
            }

        try:
            logger.info(f"Sending SMS from {self.phone_number} to {normalized_to}")
            sms = self.client.messages.create(
                body=message,
                from_=self.phone_number,
                to=normalized_to
            )
            logger.info(f"SMS sent successfully to {normalized_to}, SID: {sms.sid}")
            return {
                'success': True,
                'sid': sms.sid,
                'error': None
            }
        except Exception as e:
            # Log detailed error including from/to for debugging
            error_str = str(e)
            logger.error(
                f"Failed to send SMS - From: '{self.phone_number}', To: '{normalized_to}', "
                f"Error: {error_str}"
            )
            # Check for common Twilio errors and provide helpful messages
            if '21212' in error_str:
                error_str = (
                    f"Invalid 'From' number. TWILIO_PHONE_NUMBER='{self.phone_number}' "
                    "is not valid. Check Railway environment variable is in E.164 format "
                    "(+1XXXXXXXXXX) and the number is assigned to your Twilio account."
                )
            elif '21211' in error_str:
                error_str = (
                    f"Invalid 'To' number. Destination '{normalized_to}' is not valid. "
                    "Ensure the phone number is in E.164 format (+1XXXXXXXXXX)."
                )
            return {
                'success': False,
                'sid': None,
                'error': error_str
            }

    def send_verification(self, to: str) -> dict:
        """
        Send a phone verification code via Twilio Verify.

        Args:
            to: Phone number in E.164 format

        Returns:
            dict with 'success', 'status', 'error' keys
        """
        # Test mode - check first to skip config requirement
        if self.test_mode:
            logger.info(f"[TEST MODE] Verification code sent to {to}")
            return {
                'success': True,
                'status': 'pending',
                'error': None,
                'test_mode': True
            }

        if not self.verify_configured:
            return {
                'success': False,
                'status': None,
                'error': 'Twilio Verify not configured'
            }

        try:
            verification = self.client.verify.v2.services(
                self.verify_service_sid
            ).verifications.create(
                to=to,
                channel='sms'
            )
            logger.info(f"Verification sent to {to}, status: {verification.status}")
            return {
                'success': True,
                'status': verification.status,
                'error': None
            }
        except Exception as e:
            logger.error(f"Failed to send verification to {to}: {e}")
            return {
                'success': False,
                'status': None,
                'error': str(e)
            }

    def check_verification(self, to: str, code: str) -> dict:
        """
        Check a verification code via Twilio Verify.

        Args:
            to: Phone number in E.164 format
            code: 6-digit verification code

        Returns:
            dict with 'success', 'status', 'valid', 'error' keys
        """
        # Test mode - check first to skip config requirement
        if self.test_mode:
            is_valid = code == '123456'
            logger.info(f"[TEST MODE] Verification check for {to}: {'valid' if is_valid else 'invalid'}")
            return {
                'success': True,
                'status': 'approved' if is_valid else 'denied',
                'valid': is_valid,
                'error': None,
                'test_mode': True
            }

        if not self.verify_configured:
            return {
                'success': False,
                'status': None,
                'valid': False,
                'error': 'Twilio Verify not configured'
            }

        try:
            verification_check = self.client.verify.v2.services(
                self.verify_service_sid
            ).verification_checks.create(
                to=to,
                code=code
            )
            is_valid = verification_check.status == 'approved'
            logger.info(f"Verification check for {to}: {verification_check.status}")
            return {
                'success': True,
                'status': verification_check.status,
                'valid': is_valid,
                'error': None
            }
        except Exception as e:
            logger.error(f"Failed to check verification for {to}: {e}")
            return {
                'success': False,
                'status': None,
                'valid': False,
                'error': str(e)
            }

    def validate_webhook_signature(self, url: str, params: dict, signature: str) -> bool:
        """
        Validate Twilio webhook signature.

        Args:
            url: The full URL of the webhook
            params: POST parameters from the request
            signature: X-Twilio-Signature header value

        Returns:
            True if signature is valid
        """
        if not self.auth_token:
            return False

        # Build the validation string: URL + sorted params
        data = url
        for key in sorted(params.keys()):
            data += key + params[key]

        # Create HMAC-SHA1 signature
        expected = b64encode(
            hmac.new(
                self.auth_token.encode('utf-8'),
                data.encode('utf-8'),
                hashlib.sha1
            ).digest()
        ).decode('utf-8')

        return hmac.compare_digest(signature, expected)


class SMSNotificationService:
    """
    High-level service for managing SMS notifications.

    Handles:
    - Scheduling notifications for various reminder types
    - Sending pending notifications
    - Processing incoming replies
    - Quiet hours enforcement
    """

    # Message prefixes for branding
    MESSAGE_PREFIX = "WLJ:"

    def __init__(self):
        """Initialize the notification service."""
        self.twilio = TwilioService()

    def schedule_notification(
        self,
        user,
        category: str,
        message: str,
        scheduled_for,
        source_object=None
    ) -> Optional[SMSNotification]:
        """
        Schedule an SMS notification for a user.

        Args:
            user: User to send the notification to
            category: Notification category (medicine, task, etc.)
            message: Message content (will be prefixed with WLJ:)
            scheduled_for: When to send (datetime)
            source_object: Optional source object (Medicine, Task, etc.)

        Returns:
            SMSNotification instance or None if failed
        """
        # Check if user has SMS enabled
        if not self._is_sms_enabled(user, category):
            return None

        # Check quiet hours
        adjusted_time = self._adjust_for_quiet_hours(user, scheduled_for)

        # Build full message
        full_message = f"{self.MESSAGE_PREFIX} {message}"
        if len(full_message) > 320:
            full_message = full_message[:317] + "..."

        # Create notification
        notification = SMSNotification.objects.create(
            user=user,
            category=category,
            message=full_message,
            scheduled_for=adjusted_time,
        )

        # Link source object if provided
        if source_object:
            notification.content_type = ContentType.objects.get_for_model(source_object)
            notification.object_id = source_object.pk
            notification.save(update_fields=['content_type', 'object_id'])

        logger.info(f"Scheduled SMS {notification.notification_id} for {user.email} at {adjusted_time}")
        return notification

    def send_pending_notifications(self) -> dict:
        """
        Send all pending notifications that are due.

        Returns:
            dict with 'sent', 'failed', 'skipped' counts
        """
        now = timezone.now()
        pending = SMSNotification.objects.filter(
            status=SMSNotification.STATUS_PENDING,
            scheduled_for__lte=now
        ).select_related('user')

        results = {'sent': 0, 'failed': 0, 'skipped': 0}

        for notification in pending:
            # Get user's phone number
            phone = self._get_user_phone(notification.user)
            if not phone:
                notification.mark_failed("No verified phone number")
                results['skipped'] += 1
                continue

            # Check if SMS is still enabled
            if not self._is_sms_enabled(notification.user, notification.category):
                notification.mark_cancelled()
                results['skipped'] += 1
                continue

            # Send the SMS
            result = self.twilio.send_sms(phone, notification.message)

            if result['success']:
                notification.mark_sent(result.get('sid'))
                results['sent'] += 1
            else:
                notification.mark_failed(result.get('error', 'Unknown error'))
                results['failed'] += 1

        logger.info(f"Sent {results['sent']} SMS, {results['failed']} failed, {results['skipped']} skipped")
        return results

    def process_incoming_reply(self, from_number: str, body: str, twilio_sid: str = '') -> dict:
        """
        Process an incoming SMS reply.

        Args:
            from_number: Phone number that sent the reply
            body: Message body
            twilio_sid: Twilio message SID

        Returns:
            dict with processing results
        """
        # Find user by phone number
        user = self._find_user_by_phone(from_number)

        # Find the most recent notification to this user within 24 hours
        notification = None
        if user:
            cutoff = timezone.now() - timedelta(hours=24)
            notification = SMSNotification.objects.filter(
                user=user,
                status__in=[SMSNotification.STATUS_SENT, SMSNotification.STATUS_DELIVERED],
                sent_at__gte=cutoff
            ).order_by('-sent_at').first()

        # Parse the reply
        action, remind_minutes = SMSResponse.parse_reply(body)

        # Create response record
        response = SMSResponse.objects.create(
            notification=notification,
            user=user,
            from_number=from_number,
            body=body,
            twilio_sms_sid=twilio_sid,
            parsed_action=action,
            remind_minutes=remind_minutes,
        )

        # Update notification with response
        if notification:
            notification.record_response(body[:20])

        # Execute the action
        result = self._execute_action(response, notification)

        return {
            'response_id': str(response.response_id),
            'user_found': user is not None,
            'notification_found': notification is not None,
            'action': action,
            'result': result
        }

    def _is_sms_enabled(self, user, category: str) -> bool:
        """Check if SMS is enabled for this user and category."""
        try:
            prefs = user.preferences
        except Exception:
            return False

        if not prefs.sms_enabled or not prefs.sms_consent:
            return False

        if not prefs.phone_verified:
            return False

        # Check category-specific toggle
        category_toggles = {
            SMSNotification.CATEGORY_MEDICINE: prefs.sms_medicine_reminders,
            SMSNotification.CATEGORY_MEDICINE_REFILL: prefs.sms_medicine_refill_alerts,
            SMSNotification.CATEGORY_TASK: prefs.sms_task_reminders,
            SMSNotification.CATEGORY_EVENT: prefs.sms_event_reminders,
            SMSNotification.CATEGORY_PRAYER: prefs.sms_prayer_reminders,
            SMSNotification.CATEGORY_FASTING: prefs.sms_fasting_reminders,
            SMSNotification.CATEGORY_VERIFICATION: True,  # Always allow verification
            SMSNotification.CATEGORY_SYSTEM: True,  # Always allow system messages
        }

        return category_toggles.get(category, False)

    def _adjust_for_quiet_hours(self, user, scheduled_for):
        """
        Adjust scheduled time to respect quiet hours.

        If scheduled_for falls within quiet hours, push to quiet_end.
        """
        try:
            prefs = user.preferences
        except Exception:
            return scheduled_for

        if not prefs.sms_quiet_hours_enabled:
            return scheduled_for

        # Convert to user's timezone
        import pytz
        try:
            user_tz = pytz.timezone(prefs.timezone)
        except Exception:
            user_tz = pytz.UTC

        local_time = scheduled_for.astimezone(user_tz)
        current_time = local_time.time()

        quiet_start = prefs.sms_quiet_start
        quiet_end = prefs.sms_quiet_end

        # Convert string times to time objects if needed
        if isinstance(quiet_start, str):
            from datetime import time as dt_time
            parts = quiet_start.split(':')
            quiet_start = dt_time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        if isinstance(quiet_end, str):
            from datetime import time as dt_time
            parts = quiet_end.split(':')
            quiet_end = dt_time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)

        # Check if current time falls within quiet hours
        if quiet_start > quiet_end:
            # Quiet hours span midnight (e.g., 22:00 - 07:00)
            in_quiet_hours = current_time >= quiet_start or current_time < quiet_end
        else:
            # Quiet hours don't span midnight (e.g., 00:00 - 06:00)
            in_quiet_hours = quiet_start <= current_time < quiet_end

        if in_quiet_hours:
            # Push to quiet_end
            adjusted_local = local_time.replace(
                hour=quiet_end.hour,
                minute=quiet_end.minute,
                second=0,
                microsecond=0
            )
            # If quiet_end is earlier than current time, it's the next day
            if adjusted_local <= local_time:
                adjusted_local += timedelta(days=1)

            return adjusted_local.astimezone(pytz.UTC)

        return scheduled_for

    def _get_user_phone(self, user) -> Optional[str]:
        """Get user's verified phone number."""
        try:
            prefs = user.preferences
            if prefs.phone_verified and prefs.phone_number:
                return prefs.phone_number
        except Exception:
            pass
        return None

    def _find_user_by_phone(self, phone_number: str):
        """Find a user by their phone number."""
        from apps.users.models import UserPreferences

        # Normalize phone number (remove spaces, dashes)
        normalized = ''.join(c for c in phone_number if c.isdigit() or c == '+')

        try:
            prefs = UserPreferences.objects.select_related('user').get(
                phone_number=normalized,
                phone_verified=True
            )
            return prefs.user
        except UserPreferences.DoesNotExist:
            return None

    def _execute_action(self, response: SMSResponse, notification: Optional[SMSNotification]) -> str:
        """
        Execute the action based on the parsed reply.

        Returns a description of what was done.
        """
        if not notification:
            response.mark_processed("No notification to respond to")
            return "No matching notification found"

        category = notification.category
        action = response.parsed_action

        try:
            if action == SMSResponse.ACTION_DONE:
                result = self._handle_done_action(notification)
            elif action == SMSResponse.ACTION_REMIND:
                minutes = response.remind_minutes or 5
                result = self._handle_remind_action(notification, minutes)
            elif action == SMSResponse.ACTION_SKIP:
                result = self._handle_skip_action(notification)
            else:
                result = "Unknown command. Reply D=Done, R=Remind, N=Skip"

            response.mark_processed(result)
            notification.response_processed = True
            notification.save(update_fields=['response_processed', 'updated_at'])
            return result

        except Exception as e:
            logger.error(f"Error executing action for response {response.response_id}: {e}")
            response.mark_failed(str(e))
            return f"Error: {e}"

    def _handle_done_action(self, notification: SMSNotification) -> str:
        """Handle 'done' action based on notification category."""
        category = notification.category

        if category == SMSNotification.CATEGORY_MEDICINE:
            return self._mark_medicine_taken(notification)
        elif category == SMSNotification.CATEGORY_TASK:
            return self._mark_task_complete(notification)
        elif category == SMSNotification.CATEGORY_EVENT:
            return "Event acknowledged"
        else:
            return f"Marked {category} as done"

    def _handle_remind_action(self, notification: SMSNotification, minutes: int) -> str:
        """Handle 'remind' action - schedule a new reminder."""
        new_time = timezone.now() + timedelta(minutes=minutes)

        # Create a new notification
        new_notification = SMSNotification.objects.create(
            user=notification.user,
            category=notification.category,
            message=notification.message,
            scheduled_for=new_time,
            content_type=notification.content_type,
            object_id=notification.object_id,
        )

        return f"Reminder scheduled for {minutes} minutes"

    def _handle_skip_action(self, notification: SMSNotification) -> str:
        """Handle 'skip' action based on notification category."""
        category = notification.category

        if category == SMSNotification.CATEGORY_MEDICINE:
            return self._mark_medicine_skipped(notification)
        elif category == SMSNotification.CATEGORY_TASK:
            return "Task skipped for today"
        else:
            return f"Skipped {category}"

    def _mark_medicine_taken(self, notification: SMSNotification) -> str:
        """Create a medicine log entry marking dose as taken."""
        if not notification.content_type or not notification.object_id:
            return "Medicine taken (no log created - missing reference)"

        try:
            from apps.health.models import Medicine, MedicineLog

            medicine = Medicine.objects.get(pk=notification.object_id)
            MedicineLog.objects.create(
                user=notification.user,
                medicine=medicine,
                scheduled_date=timezone.now().date(),
                taken_at=timezone.now(),
                status=MedicineLog.STATUS_TAKEN,
            )
            return f"Logged {medicine.name} as taken"
        except Exception as e:
            logger.error(f"Failed to log medicine: {e}")
            return f"Medicine marked as taken (log error: {e})"

    def _mark_medicine_skipped(self, notification: SMSNotification) -> str:
        """Create a medicine log entry marking dose as skipped."""
        if not notification.content_type or not notification.object_id:
            return "Medicine skipped (no log created - missing reference)"

        try:
            from apps.health.models import Medicine, MedicineLog

            medicine = Medicine.objects.get(pk=notification.object_id)
            MedicineLog.objects.create(
                user=notification.user,
                medicine=medicine,
                scheduled_date=timezone.now().date(),
                status=MedicineLog.STATUS_SKIPPED,
            )
            return f"Logged {medicine.name} as skipped"
        except Exception as e:
            logger.error(f"Failed to log medicine skip: {e}")
            return f"Medicine marked as skipped (log error: {e})"

    def _mark_task_complete(self, notification: SMSNotification) -> str:
        """Mark a task as complete."""
        if not notification.content_type or not notification.object_id:
            return "Task marked complete (no update - missing reference)"

        try:
            from apps.life.models import Task

            task = Task.objects.get(pk=notification.object_id)
            task.is_completed = True
            task.completed_at = timezone.now()
            task.save(update_fields=['is_completed', 'completed_at', 'updated_at'])
            return f"Task '{task.title}' marked complete"
        except Exception as e:
            logger.error(f"Failed to complete task: {e}")
            return f"Task marked complete (update error: {e})"
