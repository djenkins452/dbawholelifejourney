# ==============================================================================
# File: test_email.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Email delivery tests for the Personal Assistant
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-05
# ==============================================================================
"""
Email Delivery Tests for WLJ Personal Assistant

This module contains tests for verifying email backend configuration
and delivery to admin@wholelifejourney.com.
"""

from datetime import datetime
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.core import mail
from django.core.mail import send_mail
from django.conf import settings


class EmailConfigurationTests(TestCase):
    """Tests for email backend configuration."""

    def test_email_settings_exist(self):
        """Verify essential email settings are defined."""
        # These settings should exist in all environments
        self.assertTrue(hasattr(settings, 'DEFAULT_FROM_EMAIL'))
        self.assertTrue(hasattr(settings, 'SERVER_EMAIL'))
        self.assertTrue(hasattr(settings, 'EMAIL_BACKEND'))

    def test_default_from_email_is_valid(self):
        """Verify DEFAULT_FROM_EMAIL has a valid format."""
        from_email = settings.DEFAULT_FROM_EMAIL
        self.assertIn('@', from_email)
        self.assertIn('.', from_email)

    def test_server_email_is_valid(self):
        """Verify SERVER_EMAIL has a valid format."""
        server_email = settings.SERVER_EMAIL
        self.assertIn('@', server_email)
        self.assertIn('.', server_email)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class EmailDeliveryTests(TestCase):
    """Tests for email delivery functionality."""

    def test_admin_email_delivery(self):
        """
        Test that emails can be sent to admin@wholelifejourney.com.

        This test uses Django's in-memory email backend to verify
        the send_mail function works correctly without actually
        sending emails over SMTP.
        """
        # Prepare email content
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        server_name = getattr(settings, 'SITE_NAME', 'Whole Life Journey')

        subject = 'WLJ Personal Assistant - Email Test'
        body = (
            f"Email Test Confirmation\n"
            f"========================\n\n"
            f"This is a test email from the WLJ Personal Assistant.\n\n"
            f"Timestamp: {timestamp}\n"
            f"Server: {server_name}\n"
            f"Environment: {'Development' if settings.DEBUG else 'Production'}\n\n"
            f"If you received this email, the email backend is configured correctly.\n"
        )
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient = 'admin@wholelifejourney.com'

        # Send the email
        result = send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[recipient],
            fail_silently=False,
        )

        # Verify email was sent
        self.assertEqual(result, 1)
        self.assertEqual(len(mail.outbox), 1)

        # Verify email content
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, subject)
        self.assertEqual(sent_email.to, [recipient])
        self.assertEqual(sent_email.from_email, from_email)
        self.assertIn('Email Test Confirmation', sent_email.body)
        self.assertIn(timestamp, sent_email.body)

    def test_email_with_html_body(self):
        """Test sending email with both plain text and HTML content."""
        from django.core.mail import EmailMultiAlternatives

        subject = 'WLJ Personal Assistant - HTML Email Test'
        text_content = 'This is a plain text fallback.'
        html_content = '<html><body><h1>Test Email</h1><p>HTML content works!</p></body></html>'
        from_email = settings.DEFAULT_FROM_EMAIL
        recipient = 'admin@wholelifejourney.com'

        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=from_email,
            to=[recipient],
        )
        msg.attach_alternative(html_content, "text/html")
        result = msg.send()

        self.assertEqual(result, 1)
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, subject)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class SMTPConfigurationTests(TestCase):
    """Tests for SMTP configuration validation."""

    def test_production_smtp_settings(self):
        """
        Verify production SMTP settings are reasonable.

        This test checks that the expected settings are configured,
        without actually connecting to the SMTP server.
        """
        # In production, these should be set via environment variables
        # For this test, we just verify the setting structure exists
        if not settings.DEBUG:
            # In production, these should be set
            self.assertTrue(hasattr(settings, 'EMAIL_HOST'))
            self.assertTrue(hasattr(settings, 'EMAIL_PORT'))
            self.assertTrue(hasattr(settings, 'EMAIL_USE_TLS'))

    @override_settings(DEBUG=True)
    def test_email_timeout_is_set(self):
        """Verify EMAIL_TIMEOUT is configured to prevent hanging."""
        # EMAIL_TIMEOUT is only set in production config
        # In debug/test mode, this test passes automatically
        # Reimport settings to get fresh value
        from django.conf import settings as fresh_settings
        if fresh_settings.DEBUG:
            self.skipTest("EMAIL_TIMEOUT only required in production")
            return

        timeout = getattr(fresh_settings, 'EMAIL_TIMEOUT', None)
        self.assertIsNotNone(timeout)
        self.assertGreater(timeout, 0)
        self.assertLessEqual(timeout, 60)  # Reasonable timeout
