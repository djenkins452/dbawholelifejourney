# ==============================================================================
# File: test_email.py
# Project: Whole Life Journey - Django 5.x Personal Wellness/Journaling App
# Description: Management command to test email configuration by sending a test
#              email via the configured SMTP backend
# Owner: Danny Jenkins (dannyjenkins71@gmail.com)
# Created: 2026-01-03
# Last Updated: 2026-01-03
# ==============================================================================

"""
Test Email Management Command

Sends a test email to verify SMTP configuration is working correctly.
Useful for validating Railway environment variables and SMTP connectivity.

Usage:
    python manage.py test_email recipient@example.com
    python manage.py test_email recipient@example.com --subject "Custom Subject"
"""

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Send a test email to verify SMTP configuration"

    def add_arguments(self, parser):
        parser.add_argument(
            "recipient",
            type=str,
            help="Email address to send the test email to",
        )
        parser.add_argument(
            "--subject",
            type=str,
            default="WLJ Test Email - SMTP Configuration Verified",
            help="Custom subject line for the test email",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show configuration without sending email",
        )

    def handle(self, *args, **options):
        recipient = options["recipient"]
        subject = options["subject"]
        dry_run = options["dry_run"]

        # Display current configuration
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("EMAIL CONFIGURATION")
        self.stdout.write("=" * 60)

        backend = getattr(settings, "EMAIL_BACKEND", "Not set")
        self.stdout.write(f"Backend:      {backend}")

        if "smtp" in backend.lower():
            host = getattr(settings, "EMAIL_HOST", "Not set")
            port = getattr(settings, "EMAIL_PORT", "Not set")
            use_tls = getattr(settings, "EMAIL_USE_TLS", False)
            use_ssl = getattr(settings, "EMAIL_USE_SSL", False)
            user = getattr(settings, "EMAIL_HOST_USER", "Not set")
            password_set = bool(getattr(settings, "EMAIL_HOST_PASSWORD", ""))

            self.stdout.write(f"Host:         {host}")
            self.stdout.write(f"Port:         {port}")
            self.stdout.write(f"TLS:          {use_tls}")
            self.stdout.write(f"SSL:          {use_ssl}")
            self.stdout.write(f"Username:     {user}")
            self.stdout.write(f"Password:     {'***SET***' if password_set else 'NOT SET'}")

        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "Not set")
        self.stdout.write(f"From Address: {from_email}")
        self.stdout.write(f"Recipient:    {recipient}")
        self.stdout.write("=" * 60 + "\n")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("DRY RUN - No email sent")
            )
            return

        # Validate configuration
        if "console" in backend.lower():
            self.stdout.write(
                self.style.WARNING(
                    "Using console backend - email will print to stdout, not sent via SMTP"
                )
            )

        # Compose email
        timestamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S %Z")
        message = f"""
This is a test email from Whole Life Journey.

Sent at: {timestamp}
From: {from_email}
To: {recipient}

If you received this email, your SMTP configuration is working correctly!

---
Email Backend: {backend}
Server: {getattr(settings, 'EMAIL_HOST', 'N/A')}:{getattr(settings, 'EMAIL_PORT', 'N/A')}
TLS Enabled: {getattr(settings, 'EMAIL_USE_TLS', False)}

This email was sent using the Django management command:
    python manage.py test_email {recipient}
"""

        try:
            self.stdout.write("Sending test email...")
            result = send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=[recipient],
                fail_silently=False,
            )

            if result == 1:
                self.stdout.write(
                    self.style.SUCCESS(f"\n✓ Test email sent successfully to {recipient}")
                )
                self.stdout.write(
                    self.style.SUCCESS("Check your inbox (and spam folder) to confirm delivery.")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"\n⚠ send_mail returned {result} - email may not have been sent")
                )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"\n✗ Failed to send email: {e}")
            )
            self.stdout.write("\nTroubleshooting tips:")
            self.stdout.write("  1. Verify EMAIL_HOST_USER and EMAIL_HOST_PASSWORD are set")
            self.stdout.write("  2. Confirm SMTP credentials are correct")
            self.stdout.write("  3. Check if port 587 is blocked (try 465 with SSL)")
            self.stdout.write("  4. Ensure EMAIL_HOST_USER matches DEFAULT_FROM_EMAIL domain")
            raise CommandError(f"Email send failed: {e}")
