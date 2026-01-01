# ==============================================================================
# File: views.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: SMS notification views - verification, webhooks, history
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================
"""
SMS Views - Phone verification, webhook handling, and notification history.

Provides:
- Phone verification flow (send code, verify code)
- Twilio webhook handlers for incoming SMS and delivery status
- SMS notification history page for users
- Protected API endpoints for scheduled triggers
"""

import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import SMSNotification, SMSResponse
from .services import SMSNotificationService, TwilioService

logger = logging.getLogger(__name__)


# ==============================================================================
# Phone Verification Views
# ==============================================================================

class SendVerificationView(LoginRequiredMixin, View):
    """
    Send a verification code to the user's phone number.

    POST /sms/api/verify/send/
    Body: {"phone_number": "+1XXXXXXXXXX"}
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            phone_number = data.get('phone_number', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON'
            }, status=400)

        if not phone_number:
            return JsonResponse({
                'success': False,
                'error': 'Phone number is required'
            }, status=400)

        # Validate phone number format (basic E.164 check)
        if not phone_number.startswith('+') or len(phone_number) < 10:
            return JsonResponse({
                'success': False,
                'error': 'Invalid phone format. Use E.164 format: +1XXXXXXXXXX'
            }, status=400)

        # Rate limiting: max 5 verifications per hour per user
        from django.core.cache import cache
        cache_key = f"sms_verify_rate_{request.user.id}"
        attempts = cache.get(cache_key, 0)
        if attempts >= 5:
            return JsonResponse({
                'success': False,
                'error': 'Too many verification attempts. Try again in an hour.'
            }, status=429)

        # Send verification
        twilio = TwilioService()
        result = twilio.send_verification(phone_number)

        if result['success']:
            # Increment rate limit counter
            cache.set(cache_key, attempts + 1, 3600)  # 1 hour

            # Store phone number temporarily for verification
            request.session['pending_phone_verification'] = phone_number

            return JsonResponse({
                'success': True,
                'message': 'Verification code sent',
                'test_mode': result.get('test_mode', False)
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Failed to send verification')
            }, status=400)


class CheckVerificationView(LoginRequiredMixin, View):
    """
    Verify a phone number with the code sent via SMS.

    POST /sms/api/verify/check/
    Body: {"code": "123456"}
    """

    def post(self, request):
        try:
            data = json.loads(request.body)
            code = data.get('code', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False,
                'error': 'Invalid JSON'
            }, status=400)

        if not code or len(code) != 6:
            return JsonResponse({
                'success': False,
                'error': 'Invalid verification code'
            }, status=400)

        # Get pending phone number from session
        phone_number = request.session.get('pending_phone_verification')
        if not phone_number:
            return JsonResponse({
                'success': False,
                'error': 'No pending verification. Request a new code.'
            }, status=400)

        # Check verification
        twilio = TwilioService()
        result = twilio.check_verification(phone_number, code)

        if result['success'] and result['valid']:
            # Update user preferences
            prefs = request.user.preferences
            prefs.phone_number = phone_number
            prefs.phone_verified = True
            prefs.phone_verified_at = timezone.now()
            prefs.save(update_fields=[
                'phone_number', 'phone_verified', 'phone_verified_at', 'updated_at'
            ])

            # Clear session
            del request.session['pending_phone_verification']

            return JsonResponse({
                'success': True,
                'message': 'Phone number verified successfully',
                'phone_number': phone_number
            })
        else:
            error = 'Invalid or expired code'
            if result.get('error'):
                error = result['error']
            return JsonResponse({
                'success': False,
                'error': error
            }, status=400)


class RemovePhoneView(LoginRequiredMixin, View):
    """
    Remove verified phone number and disable SMS.

    POST /sms/api/phone/remove/
    """

    def post(self, request):
        prefs = request.user.preferences
        prefs.phone_number = ''
        prefs.phone_verified = False
        prefs.phone_verified_at = None
        prefs.sms_enabled = False
        prefs.sms_consent = False
        prefs.sms_consent_date = None
        prefs.save(update_fields=[
            'phone_number', 'phone_verified', 'phone_verified_at',
            'sms_enabled', 'sms_consent', 'sms_consent_date', 'updated_at'
        ])

        return JsonResponse({
            'success': True,
            'message': 'Phone number removed and SMS disabled'
        })


# ==============================================================================
# Twilio Webhook Views
# ==============================================================================

@method_decorator(csrf_exempt, name='dispatch')
class TwilioIncomingWebhookView(View):
    """
    Handle incoming SMS messages from Twilio.

    POST /sms/webhook/incoming/
    Twilio sends POST data with From, Body, MessageSid, etc.
    """

    def post(self, request):
        # Get Twilio signature for validation
        signature = request.META.get('HTTP_X_TWILIO_SIGNATURE', '')

        # Build URL for validation
        url = request.build_absolute_uri()

        # Get POST data
        from_number = request.POST.get('From', '')
        body = request.POST.get('Body', '')
        message_sid = request.POST.get('MessageSid', '')

        logger.info(f"Incoming SMS from {from_number}: {body[:50]}...")

        # Validate signature in production
        twilio = TwilioService()
        if not twilio.test_mode:
            if not twilio.validate_webhook_signature(url, dict(request.POST), signature):
                logger.warning(f"Invalid Twilio signature for message {message_sid}")
                return HttpResponse('Invalid signature', status=403)

        # Process the incoming message
        service = SMSNotificationService()
        result = service.process_incoming_reply(from_number, body, message_sid)

        logger.info(f"Processed incoming SMS: {result}")

        # Return TwiML response (empty is fine - no auto-reply)
        return HttpResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            content_type='application/xml'
        )


@method_decorator(csrf_exempt, name='dispatch')
class TwilioStatusWebhookView(View):
    """
    Handle SMS delivery status updates from Twilio.

    POST /sms/webhook/status/
    Twilio sends status updates (sent, delivered, failed, etc.)
    """

    def post(self, request):
        message_sid = request.POST.get('MessageSid', '')
        status = request.POST.get('MessageStatus', '')
        error_code = request.POST.get('ErrorCode', '')
        error_message = request.POST.get('ErrorMessage', '')

        logger.info(f"SMS status update: {message_sid} -> {status}")

        # Find and update the notification
        try:
            notification = SMSNotification.objects.get(twilio_sid=message_sid)

            if status == 'delivered':
                notification.mark_delivered()
            elif status in ('failed', 'undelivered'):
                reason = f"Error {error_code}: {error_message}" if error_code else 'Delivery failed'
                notification.mark_failed(reason)

        except SMSNotification.DoesNotExist:
            logger.warning(f"No notification found for SID: {message_sid}")

        return HttpResponse('OK')


# ==============================================================================
# Trigger API Views (for external cron)
# ==============================================================================

@method_decorator(csrf_exempt, name='dispatch')
class TriggerSendView(View):
    """
    Trigger sending of pending SMS notifications.

    POST /sms/api/trigger/send/
    Requires: X-Trigger-Token header matching SMS_TRIGGER_TOKEN setting
    """

    def post(self, request):
        # Validate trigger token
        token = request.META.get('HTTP_X_TRIGGER_TOKEN', '')
        expected_token = getattr(settings, 'SMS_TRIGGER_TOKEN', '')

        if not expected_token or token != expected_token:
            return JsonResponse({
                'success': False,
                'error': 'Invalid or missing trigger token'
            }, status=403)

        # Send pending notifications
        service = SMSNotificationService()
        results = service.send_pending_notifications()

        return JsonResponse({
            'success': True,
            'results': results
        })


@method_decorator(csrf_exempt, name='dispatch')
class TriggerScheduleView(View):
    """
    Trigger scheduling of SMS notifications for today.

    POST /sms/api/trigger/schedule/
    Requires: X-Trigger-Token header matching SMS_TRIGGER_TOKEN setting
    """

    def post(self, request):
        # Validate trigger token
        token = request.META.get('HTTP_X_TRIGGER_TOKEN', '')
        expected_token = getattr(settings, 'SMS_TRIGGER_TOKEN', '')

        if not expected_token or token != expected_token:
            return JsonResponse({
                'success': False,
                'error': 'Invalid or missing trigger token'
            }, status=403)

        # Schedule notifications for all users
        from .scheduler import SMSScheduler
        scheduler = SMSScheduler()
        results = scheduler.schedule_for_all_users()

        return JsonResponse({
            'success': True,
            'results': results
        })


# ==============================================================================
# User-Facing Views
# ==============================================================================

@login_required
def sms_history(request):
    """
    Display SMS notification history for the current user.

    GET /sms/history/
    """
    notifications = SMSNotification.objects.filter(
        user=request.user
    ).order_by('-scheduled_for')[:100]

    # Get user timezone for display
    import pytz
    user_tz = pytz.timezone(request.user.preferences.timezone)

    # Group by date (in user's timezone)
    grouped = {}
    for notification in notifications:
        # Convert to user timezone for grouping by local date
        local_time = notification.scheduled_for.astimezone(user_tz)
        date_key = local_time.date()
        if date_key not in grouped:
            grouped[date_key] = []
        grouped[date_key].append(notification)

    context = {
        'notifications': notifications,
        'grouped_notifications': grouped,
        'user_timezone': request.user.preferences.timezone,
    }

    return render(request, 'sms/history.html', context)


@login_required
def sms_status(request):
    """
    Get SMS configuration status for the current user.

    GET /sms/api/status/
    """
    try:
        prefs = request.user.preferences
    except Exception:
        return JsonResponse({
            'configured': False,
            'enabled': False,
        })

    twilio = TwilioService()

    return JsonResponse({
        'twilio_configured': twilio.is_configured,
        'verify_configured': twilio.verify_configured,
        'phone_number': prefs.phone_number if prefs.phone_verified else None,
        'phone_verified': prefs.phone_verified,
        'sms_enabled': prefs.sms_enabled,
        'sms_consent': prefs.sms_consent,
        'categories': {
            'medicine_reminders': prefs.sms_medicine_reminders,
            'medicine_refill_alerts': prefs.sms_medicine_refill_alerts,
            'task_reminders': prefs.sms_task_reminders,
            'event_reminders': prefs.sms_event_reminders,
            'prayer_reminders': prefs.sms_prayer_reminders,
            'fasting_reminders': prefs.sms_fasting_reminders,
        },
        'quiet_hours': {
            'enabled': prefs.sms_quiet_hours_enabled,
            'start': prefs.sms_quiet_start.strftime('%H:%M') if prefs.sms_quiet_start else '22:00',
            'end': prefs.sms_quiet_end.strftime('%H:%M') if prefs.sms_quiet_end else '07:00',
        }
    })
