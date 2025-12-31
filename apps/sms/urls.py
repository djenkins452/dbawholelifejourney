# ==============================================================================
# File: urls.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: URL patterns for SMS notification endpoints
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2025-12-30
# Last Updated: 2025-12-30
# ==============================================================================
"""
SMS URL Configuration

Routes:
- /sms/api/verify/send/ - Send phone verification code
- /sms/api/verify/check/ - Verify phone with code
- /sms/api/phone/remove/ - Remove verified phone
- /sms/api/status/ - Get SMS configuration status
- /sms/api/trigger/send/ - Trigger sending pending SMS (protected)
- /sms/api/trigger/schedule/ - Trigger scheduling SMS (protected)
- /sms/webhook/incoming/ - Twilio incoming SMS webhook
- /sms/webhook/status/ - Twilio delivery status webhook
- /sms/history/ - User SMS history page
"""

from django.urls import path

from . import views

app_name = 'sms'

urlpatterns = [
    # Phone verification API
    path('api/verify/send/', views.SendVerificationView.as_view(), name='verify_send'),
    path('api/verify/check/', views.CheckVerificationView.as_view(), name='verify_check'),
    path('api/phone/remove/', views.RemovePhoneView.as_view(), name='phone_remove'),

    # Status API
    path('api/status/', views.sms_status, name='status'),

    # Trigger API (for external cron)
    path('api/trigger/send/', views.TriggerSendView.as_view(), name='trigger_send'),
    path('api/trigger/schedule/', views.TriggerScheduleView.as_view(), name='trigger_schedule'),

    # Twilio webhooks
    path('webhook/incoming/', views.TwilioIncomingWebhookView.as_view(), name='webhook_incoming'),
    path('webhook/status/', views.TwilioStatusWebhookView.as_view(), name='webhook_status'),

    # User-facing pages
    path('history/', views.sms_history, name='history'),
]
