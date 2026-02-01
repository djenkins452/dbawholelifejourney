# ==============================================================================
# File: send_test_sms.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to send a test SMS message
# Owner: Danny Jenkins (admin@wholelifejourney.com)
# Created: 2026-01-07
# Last Updated: 2026-01-07
# ==============================================================================
"""
Send Test SMS Management Command

Sends a test SMS message to verify Twilio configuration.

Usage:
    python manage.py send_test_sms +18651234567
    python manage.py send_test_sms +18651234567 --message "Custom test message"
"""

from django.core.management.base import BaseCommand

from apps.sms.services import TwilioService


class Command(BaseCommand):
    help = 'Send a test SMS message to verify Twilio configuration'

    def add_arguments(self, parser):
        parser.add_argument(
            'phone_number',
            type=str,
            help='Phone number to send test SMS to (E.164 format: +1XXXXXXXXXX)',
        )
        parser.add_argument(
            '--message',
            type=str,
            default='WLJ Test: Your Twilio SMS integration is working!',
            help='Custom message to send (default: test message)',
        )

    def handle(self, *args, **options):
        phone_number = options['phone_number']
        message = options['message']

        self.stdout.write(f"Sending test SMS to {phone_number}...")
        self.stdout.write(f"Message: {message}")

        # Check Twilio configuration
        twilio = TwilioService()

        self.stdout.write("\nTwilio Configuration:")
        self.stdout.write(f"  Account SID: {'Set' if twilio.account_sid else 'NOT SET'}")
        self.stdout.write(f"  Auth Token: {'Set' if twilio.auth_token else 'NOT SET'}")
        self.stdout.write(f"  Phone Number: {twilio.phone_number or 'NOT SET'}")
        self.stdout.write(f"  Test Mode: {twilio.test_mode}")
        self.stdout.write(f"  Is Configured: {twilio.is_configured}")

        if not twilio.is_configured and not twilio.test_mode:
            self.stdout.write(self.style.ERROR(
                "\nTwilio is not configured. Set environment variables:\n"
                "  TWILIO_ACCOUNT_SID\n"
                "  TWILIO_AUTH_TOKEN\n"
                "  TWILIO_PHONE_NUMBER"
            ))
            return

        # Send the test SMS
        self.stdout.write("\nSending SMS...")
        result = twilio.send_sms(phone_number, message)

        if result['success']:
            if result.get('test_mode'):
                self.stdout.write(self.style.SUCCESS(
                    f"\n[TEST MODE] SMS logged successfully!"
                    f"\n  SID: {result['sid']}"
                    f"\n  (Message was logged, not actually sent)"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"\nSMS sent successfully!"
                    f"\n  SID: {result['sid']}"
                ))
        else:
            self.stdout.write(self.style.ERROR(
                f"\nFailed to send SMS!"
                f"\n  Error: {result['error']}"
            ))
